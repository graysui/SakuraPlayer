from __future__ import annotations

import logging
import re
import shutil
import threading
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from sakuraplayer.resources.avdb_crypto import AvdbAssetError, decrypt_asset_file
from sakuraplayer.resources.avdb_release import FetchedRelease
from sakuraplayer.resources.sync_service import (
    AvdbSyncQueue,
    AvdbSyncService,
    ClaimedRequest,
    Importer,
)
from sakuraplayer.shared.redaction import stable_error_code

_LOGGER = logging.getLogger(__name__)
_MANAGED_PLAINTEXT_DIRECTORY = re.compile(
    r"\.avdb-plaintext-"
    r"(?P<request_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})-"
    r"(?P<claim_token>[0-9a-f]{32})"
)


class ReleaseClient(Protocol):
    def fetch_release(
        self,
        *,
        mode: str,
        destination: Path,
        validator,
    ) -> FetchedRelease: ...


class ReleaseClientFactory(Protocol):
    def __call__(self, repository: str) -> ReleaseClient: ...


class _RequestLeaseKeeper:
    def __init__(
        self,
        *,
        queue: AvdbSyncQueue,
        claim: ClaimedRequest,
        lease_duration: timedelta,
        heartbeat_interval: timedelta,
    ) -> None:
        self._queue = queue
        self._claim = claim
        self._lease_duration = lease_duration
        self._interval_seconds = heartbeat_interval.total_seconds()
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="avdb-request-heartbeat",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def assert_owned(self) -> None:
        if self._lost.is_set():
            raise RuntimeError("AVdb request claim was lost")

    def renew_now(self) -> None:
        self.assert_owned()
        self._queue.renew(
            self._claim,
            lease_duration=self._lease_duration,
        )

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._queue.renew(
                    self._claim,
                    lease_duration=self._lease_duration,
                )
            except Exception:
                self._lost.set()
                _LOGGER.error("avdb_request_heartbeat_failed")
                return


class AvdbWorkerConsumer:
    def __init__(
        self,
        *,
        queue: AvdbSyncQueue,
        release_client: ReleaseClient | None = None,
        release_client_factory: ReleaseClientFactory | None = None,
        source_loader: Callable[[], str | None] | None = None,
        sync_service: AvdbSyncService,
        asset_directory: Path,
        plaintext_directory: Path,
        request_lease_duration: timedelta = timedelta(minutes=10),
        heartbeat_interval: timedelta = timedelta(minutes=1),
    ) -> None:
        if (
            request_lease_duration <= timedelta(0)
            or heartbeat_interval <= timedelta(0)
            or heartbeat_interval >= request_lease_duration
        ):
            raise ValueError("invalid AVdb request heartbeat")
        self._queue = queue
        self._release_client = release_client
        self._release_client_factory = release_client_factory
        self._source_loader = source_loader
        if (release_client is None) == (release_client_factory is None):
            raise ValueError(
                "provide exactly one release client or release client factory"
            )
        if release_client_factory is not None and source_loader is None:
            raise ValueError("source loader is required for release client factory")
        self._sync_service = sync_service
        self._asset_directory = Path(asset_directory)
        self._plaintext_directory = Path(plaintext_directory)
        self._request_lease_duration = request_lease_duration
        self._heartbeat_interval = heartbeat_interval

    def run_once(self, *, worker_id: str, importer: Importer) -> str:
        self._cleanup_stale_plaintext_directories()
        claim = self._queue.claim_next(
            worker_id,
            lease_duration=self._request_lease_duration,
        )
        if claim is None:
            return "idle"
        lease_keeper = _RequestLeaseKeeper(
            queue=self._queue,
            claim=claim,
            lease_duration=self._request_lease_duration,
            heartbeat_interval=self._heartbeat_interval,
        )
        release: FetchedRelease | None = None
        plaintext_directory = self._plaintext_directory / (
            f".avdb-plaintext-{claim.request_id}-{claim.claim_token.hex}"
        )
        lease_keeper.start()
        try:
            self._create_plaintext_directory(plaintext_directory)
            release_client = self._release_client
            if self._release_client_factory is not None:
                assert self._source_loader is not None
                repository = self._source_loader()
                if repository is None:
                    raise AvdbAssetError("mgdb_source_not_configured")
                release_client = self._release_client_factory(repository)
            assert release_client is not None
            release = release_client.fetch_release(
                mode=claim.mode,
                destination=self._asset_directory,
                validator=lambda path: decrypt_asset_file(
                    path,
                    temp_directory=plaintext_directory,
                ),
            )
            lease_keeper.assert_owned()
            outcome = self._sync_service.sync(release, importer=importer)
            lease_keeper.assert_owned()
            if outcome.status != "completed":
                raise RuntimeError("AVdb release is already being synchronized")
            lease_keeper.renew_now()
            lease_keeper.stop()
            lease_keeper.assert_owned()
            lease_keeper.renew_now()
            self._queue.complete(claim, run_id=outcome.run_id)
            return "completed"
        except Exception as error:
            lease_keeper.stop()
            code = stable_error_code(getattr(error, "code", None))
            try:
                self._queue.fail(claim, code=code, detail=code)
            except RuntimeError:
                _LOGGER.error("avdb_request_claim_lost")
            return "failed"
        finally:
            if release is not None:
                self._close_validations(release)
            self._cleanup_plaintext_directory(plaintext_directory)

    @staticmethod
    def _close_validations(release: FetchedRelease) -> None:
        for asset in release.assets:
            close = getattr(asset.validation, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    _LOGGER.error("avdb_plaintext_cleanup_failed")

    @staticmethod
    def _cleanup_plaintext_directory(directory: Path) -> None:
        try:
            if directory.is_symlink():
                directory.unlink(missing_ok=True)
            elif directory.exists():
                shutil.rmtree(directory)
        except OSError:
            _LOGGER.error("avdb_plaintext_directory_cleanup_failed")

    def _cleanup_stale_plaintext_directories(self) -> None:
        try:
            if not self._plaintext_directory.exists():
                return
            if (
                self._plaintext_directory.is_symlink()
                or not self._plaintext_directory.is_dir()
            ):
                _LOGGER.error("avdb_plaintext_root_invalid")
                return
            for candidate in self._plaintext_directory.iterdir():
                match = _MANAGED_PLAINTEXT_DIRECTORY.fullmatch(candidate.name)
                if match is None:
                    continue
                try:
                    active = self._queue.is_claim_active(
                        uuid.UUID(match.group("request_id")),
                        uuid.UUID(hex=match.group("claim_token")),
                    )
                except Exception:
                    _LOGGER.error("avdb_plaintext_claim_check_failed")
                    return
                if not active:
                    self._cleanup_plaintext_directory(candidate)
        except OSError:
            _LOGGER.error("avdb_plaintext_sweep_failed")

    def _create_plaintext_directory(self, directory: Path) -> None:
        try:
            self._plaintext_directory.mkdir(parents=True, exist_ok=True)
            if (
                self._plaintext_directory.is_symlink()
                or not self._plaintext_directory.is_dir()
            ):
                raise AvdbAssetError()
            expected_parent = self._plaintext_directory.resolve(strict=True)
            directory.mkdir(mode=0o700)
            if (
                self._plaintext_directory.is_symlink()
                or directory.is_symlink()
                or directory.resolve(strict=True).parent != expected_parent
            ):
                self._cleanup_plaintext_directory(directory)
                raise AvdbAssetError()
        except AvdbAssetError:
            raise
        except OSError:
            raise AvdbAssetError() from None
