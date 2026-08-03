from __future__ import annotations

import hmac
import json
import logging
import os
import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from sakuraplayer.identity.crypto import SecretDecryptionError
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.avdb_crypto import (
    MAX_OUTER_BYTES,
    AvdbAssetError,
    validate_asset_name,
)

MGDB_SOURCE_KEY = "mgdb.source"
_API_ROOT = "https://api.github.com/repos"
MAX_RELEASE_METADATA_BYTES = 1024 * 1024
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0, pool=10.0)
_API_HOSTS = frozenset({"api.github.com"})
_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReleaseAsset:
    repository: str
    release_id: str
    tag: str
    logical_name: str
    name: str
    url: str
    size: int
    declared_sha256: str | None


@dataclass(frozen=True)
class ReleaseCandidate:
    repository: str
    release_id: str
    tag: str
    assets: tuple[ReleaseAsset, ...]


@dataclass(frozen=True)
class FetchedAsset:
    name: str
    path: Path
    sha256: str
    byte_size: int
    validation: object


@dataclass(frozen=True)
class FetchedRelease:
    repository: str
    release_id: str
    tag: str
    mode: str
    assets: tuple[FetchedAsset, ...]


@dataclass(frozen=True)
class AvdbSourceSnapshot:
    repository: str
    source_url: str
    version: int


class EncryptedAvdbSourceStore:
    def __init__(self, repository: EncryptedSettingRepository) -> None:
        self._repository = repository

    def save(self, source_url: str, *, expected_version: int):
        normalized = normalize_github_source(source_url)
        payload = json.dumps(
            {"repository": normalized},
            separators=(",", ":"),
        ).encode("utf-8")
        setting = self._repository.create_or_compare_and_set_secret(
            MGDB_SOURCE_KEY,
            expected_version=expected_version,
            value=payload,
        )
        return AvdbSourceSnapshot(
            repository=normalized,
            source_url=github_source_url(normalized),
            version=setting.version,
        )

    def load(self) -> AvdbSourceSnapshot | None:
        try:
            setting = self._repository.get_secret(MGDB_SOURCE_KEY)
        except SecretDecryptionError:
            raise ValueError("MGDB source setting is invalid") from None
        if setting is None:
            return None
        if len(setting.value) > 512:
            raise ValueError("MGDB source setting is too large")
        try:
            payload = json.loads(setting.value.decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"repository"}:
                raise ValueError
            repository = payload["repository"]
            if not isinstance(repository, str):
                raise ValueError
            repository = _validate_repository(repository)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise ValueError("MGDB source setting is invalid") from None
        return AvdbSourceSnapshot(
            repository=repository,
            source_url=github_source_url(repository),
            version=setting.version,
        )

    def clear(self, *, expected_version: int) -> None:
        self._repository.delete_secret(
            MGDB_SOURCE_KEY,
            expected_version=expected_version,
        )


def normalize_github_source(source_url: str) -> str:
    if not isinstance(source_url, str):
        raise ValueError("MGDB source must be a URL")
    try:
        parsed = urlparse(source_url.strip())
        port = parsed.port
    except ValueError:
        raise ValueError("MGDB source URL is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() not in {"github.com", "api.github.com"}
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MGDB source URL is invalid")
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname.lower() == "api.github.com":
        if len(parts) != 3 or parts[0].lower() != "repos":
            raise ValueError("MGDB source URL is invalid")
        owner, repository = parts[1:]
    else:
        if len(parts) != 2:
            raise ValueError("MGDB source URL is invalid")
        owner, repository = parts
    return _validate_repository(f"{owner}/{repository}")


def github_source_url(repository: str) -> str:
    return f"https://github.com/{_validate_repository(repository)}"


def _validate_repository(repository: str) -> str:
    parts = repository.split("/")
    if len(parts) != 2 or any(
        not part
        or len(part) > 100
        or any(
            char
            not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
            for char in part
        )
        for part in parts
    ):
        raise ValueError("MGDB repository is invalid")
    return "/".join(parts)


@dataclass(frozen=True)
class _TemporaryAsset:
    descriptor: ReleaseAsset
    path: Path
    sha256: str
    byte_size: int
    validation: object


class GitHubAvdbReleaseClient:
    def __init__(
        self,
        *,
        http_client: httpx.Client,
        repository: str,
        backup_repository: str | None = None,
    ) -> None:
        self._http = http_client
        self._repository = _validate_repository(repository)
        self._backup_repository = (
            _validate_repository(backup_repository)
            if backup_repository is not None
            else None
        )

    def fetch_release(
        self,
        *,
        mode: str,
        destination: Path,
        validator: Callable[[Path], object],
    ) -> FetchedRelease:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        primary_error: AvdbAssetError | None = None
        try:
            primary = self._discover(self._repository, mode=mode, tag=None)
        except AvdbAssetError as error:
            primary_error = error
            primary = None
        if primary is None:
            try:
                backup = (
                    self._discover(self._backup_repository, mode=mode, tag=None)
                    if self._backup_repository is not None
                    else None
                )
            except AvdbAssetError:
                raise
            if backup is None:
                if primary_error is not None:
                    raise primary_error
                raise AvdbAssetError("service_unavailable")
            selected = self._fetch_candidate(backup, destination)
            selected = self._validate_candidate(selected, validator)
            return self._commit(backup, mode, destination, selected)

        try:
            backup = (
                self._discover(
                    self._backup_repository,
                    mode=mode,
                    tag=primary.tag,
                )
                if self._backup_repository is not None
                else None
            )
        except AvdbAssetError:
            backup = None
        primary_files: tuple[_TemporaryAsset, ...] | None = None
        backup_files: tuple[_TemporaryAsset, ...] | None = None
        try:
            try:
                primary_files = self._fetch_candidate(primary, destination)
            except AvdbAssetError:
                if backup is None:
                    raise
            if backup is not None:
                try:
                    backup_files = self._fetch_candidate(backup, destination)
                except AvdbAssetError:
                    if primary_files is None:
                        raise
            if primary_files is not None and backup_files is not None:
                self._require_matching_digests(primary_files, backup_files)
            if primary_files is not None:
                self._cleanup(backup_files or ())
                primary_files = self._validate_candidate(primary_files, validator)
                return self._commit(primary, mode, destination, primary_files)
            if backup is None or backup_files is None:
                raise AvdbAssetError("service_unavailable")
            backup_files = self._validate_candidate(backup_files, validator)
            return self._commit(backup, mode, destination, backup_files)
        except Exception:
            self._cleanup(primary_files or ())
            self._cleanup(backup_files or ())
            raise

    def _discover(
        self,
        repository: str,
        *,
        mode: str,
        tag: str | None,
    ) -> ReleaseCandidate | None:
        endpoint = "latest" if tag is None else f"tags/{tag}"
        try:
            raw = self._read_metadata(
                f"{_API_ROOT}/{repository}/releases/{endpoint}",
                headers={"Accept": "application/vnd.github+json"},
            )
            try:
                payload = httpx.Response(200, content=raw).json()
            except ValueError:
                raise AvdbAssetError() from None
            return self._parse_release(repository, payload, mode=mode, expected_tag=tag)
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status in {404, 429} or status >= 500:
                return None
            raise AvdbAssetError() from None
        except httpx.HTTPError:
            return None

    def _read_metadata(self, url: str, *, headers: dict[str, str]) -> bytes:
        current_url = url
        current_headers = headers
        for _ in range(_MAX_REDIRECTS + 1):
            if not self._is_allowed_url(current_url, _API_HOSTS):
                raise AvdbAssetError()
            with self._http.stream(
                "GET",
                current_url,
                headers=current_headers,
                follow_redirects=False,
                timeout=_REQUEST_TIMEOUT,
            ) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise AvdbAssetError()
                    current_url = urljoin(current_url, location)
                    current_headers = {}
                    continue
                response.raise_for_status()
                return self._read_limited(response, MAX_RELEASE_METADATA_BYTES)
        raise AvdbAssetError()

    def _parse_release(
        self,
        repository: str,
        payload: Any,
        *,
        mode: str,
        expected_tag: str | None,
    ) -> ReleaseCandidate:
        if not isinstance(payload, dict):
            raise AvdbAssetError()
        release_id = payload.get("id")
        tag = payload.get("tag_name")
        assets = payload.get("assets")
        if (
            not isinstance(release_id, (str, int))
            or isinstance(release_id, bool)
            or not isinstance(tag, str)
            or _TAG.fullmatch(tag) is None
            or (expected_tag is not None and tag != expected_tag)
            or not isinstance(assets, list)
        ):
            raise AvdbAssetError()

        selected: dict[str, ReleaseAsset] = {}
        for item in assets:
            descriptor = self._parse_asset(
                repository,
                str(release_id),
                tag,
                mode,
                item,
            )
            if descriptor is None:
                continue
            if descriptor.logical_name in selected:
                raise AvdbAssetError()
            selected[descriptor.logical_name] = descriptor
        required = (
            {"incremental"}
            if mode == "incremental_30d"
            else {
                "sehuatang",
                "x1080x",
            }
        )
        if (
            mode not in {"incremental_30d", "full_reconcile"}
            or set(selected) != required
        ):
            raise AvdbAssetError()
        return ReleaseCandidate(
            repository=repository,
            release_id=str(release_id),
            tag=tag,
            assets=tuple(selected[key] for key in sorted(selected)),
        )

    def _parse_asset(
        self,
        repository: str,
        release_id: str,
        tag: str,
        mode: str,
        payload: object,
    ) -> ReleaseAsset | None:
        if not isinstance(payload, dict):
            return None
        name = payload.get("name")
        if not isinstance(name, str):
            return None
        try:
            validate_asset_name(name, mode=mode)
        except AvdbAssetError:
            return None
        if mode == "incremental_30d":
            logical_name = "incremental"
        elif name.startswith("All_sehuatang_"):
            logical_name = "sehuatang"
        else:
            logical_name = "x1080x"
        url = payload.get("browser_download_url")
        size = payload.get("size")
        if (
            not isinstance(url, str)
            or not self._is_allowed_url(url, _DOWNLOAD_HOSTS)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 < size <= MAX_OUTER_BYTES
        ):
            raise AvdbAssetError()
        declared = payload.get("digest")
        declared_sha256: str | None = None
        if declared is not None:
            if not isinstance(declared, str):
                raise AvdbAssetError()
            match = _DIGEST.fullmatch(declared)
            if match is None:
                raise AvdbAssetError()
            declared_sha256 = match.group(1)
        return ReleaseAsset(
            repository=repository,
            release_id=release_id,
            tag=tag,
            logical_name=logical_name,
            name=name,
            url=url,
            size=size,
            declared_sha256=declared_sha256,
        )

    def _fetch_candidate(
        self,
        candidate: ReleaseCandidate,
        destination: Path,
    ) -> tuple[_TemporaryAsset, ...]:
        fetched: list[_TemporaryAsset] = []
        try:
            for descriptor in candidate.assets:
                fetched.append(self._download(descriptor, destination))
        except Exception:
            self._cleanup(fetched)
            raise
        return tuple(fetched)

    def _download(
        self,
        descriptor: ReleaseAsset,
        destination: Path,
    ) -> _TemporaryAsset:
        temporary = destination / f".{descriptor.name}.part-{uuid.uuid4().hex}"
        digest = sha256()
        byte_size = 0
        success = False
        try:
            current_url = descriptor.url
            for _ in range(_MAX_REDIRECTS + 1):
                if not self._is_allowed_url(current_url, _DOWNLOAD_HOSTS):
                    raise AvdbAssetError()
                with self._http.stream(
                    "GET",
                    current_url,
                    follow_redirects=False,
                    timeout=_REQUEST_TIMEOUT,
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise AvdbAssetError()
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    self._validate_content_length(response, MAX_OUTER_BYTES)
                    with temporary.open("xb") as output:
                        for chunk in response.iter_bytes():
                            if not chunk:
                                continue
                            byte_size += len(chunk)
                            if byte_size > MAX_OUTER_BYTES:
                                raise AvdbAssetError()
                            digest.update(chunk)
                            output.write(chunk)
                    break
            else:
                raise AvdbAssetError()
            actual_digest = digest.hexdigest()
            if byte_size != descriptor.size:
                raise AvdbAssetError()
            if descriptor.declared_sha256 is not None and not hmac.compare_digest(
                actual_digest,
                descriptor.declared_sha256,
            ):
                raise AvdbAssetError("avdb_asset_digest_mismatch")
            result = _TemporaryAsset(
                descriptor=descriptor,
                path=temporary,
                sha256=actual_digest,
                byte_size=byte_size,
                validation=None,
            )
            success = True
            return result
        except AvdbAssetError:
            raise
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            raise AvdbAssetError("service_unavailable") from None
        except Exception:
            raise AvdbAssetError("internal_error") from None
        finally:
            if not success:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate_candidate(
        assets: tuple[_TemporaryAsset, ...],
        validator: Callable[[Path], object],
    ) -> tuple[_TemporaryAsset, ...]:
        validated: list[_TemporaryAsset] = []
        try:
            for asset in assets:
                try:
                    result = validator(asset.path)
                except AvdbAssetError:
                    raise
                except Exception:
                    raise AvdbAssetError("internal_error") from None
                validated.append(
                    _TemporaryAsset(
                        descriptor=asset.descriptor,
                        path=asset.path,
                        sha256=asset.sha256,
                        byte_size=asset.byte_size,
                        validation=result,
                    )
                )
            return tuple(validated)
        except Exception:
            GitHubAvdbReleaseClient._close_validations(validated)
            GitHubAvdbReleaseClient._cleanup(assets)
            raise

    @staticmethod
    def _require_matching_digests(
        primary: tuple[_TemporaryAsset, ...],
        backup: tuple[_TemporaryAsset, ...],
    ) -> None:
        primary_digests = {
            asset.descriptor.logical_name: asset.sha256 for asset in primary
        }
        backup_digests = {
            asset.descriptor.logical_name: asset.sha256 for asset in backup
        }
        if primary_digests != backup_digests:
            raise AvdbAssetError("avdb_asset_digest_mismatch")

    @staticmethod
    def _commit(
        candidate: ReleaseCandidate,
        mode: str,
        destination: Path,
        assets: tuple[_TemporaryAsset, ...],
    ) -> FetchedRelease:
        identity = sha256(
            f"{candidate.repository}\0{candidate.release_id}\0{mode}".encode("utf-8")
        ).hexdigest()[:24]
        final_directory = destination / f"release-{identity}"
        staging_directory = destination / f".release-{identity}.part-{uuid.uuid4().hex}"
        committed: list[FetchedAsset] = []
        if final_directory.exists():
            try:
                committed = GitHubAvdbReleaseClient._reuse_committed(
                    final_directory,
                    assets,
                )
            except Exception:
                GitHubAvdbReleaseClient._close_validations(assets)
                GitHubAvdbReleaseClient._cleanup(assets)
                raise
            GitHubAvdbReleaseClient._cleanup(assets)
            return FetchedRelease(
                repository=candidate.repository,
                release_id=candidate.release_id,
                tag=candidate.tag,
                mode=mode,
                assets=tuple(committed),
            )
        try:
            staging_directory.mkdir()
            for asset in assets:
                staged_path = staging_directory / asset.descriptor.name
                os.replace(asset.path, staged_path)
                committed.append(
                    FetchedAsset(
                        name=asset.descriptor.name,
                        path=final_directory / asset.descriptor.name,
                        sha256=asset.sha256,
                        byte_size=asset.byte_size,
                        validation=asset.validation,
                    )
                )
            os.replace(staging_directory, final_directory)
        except Exception as error:
            commit_error = error
            if final_directory.exists():
                try:
                    committed = GitHubAvdbReleaseClient._reuse_committed(
                        final_directory,
                        assets,
                    )
                except AvdbAssetError as reuse_error:
                    committed = []
                    commit_error = reuse_error
                else:
                    GitHubAvdbReleaseClient._cleanup(assets)
                    if staging_directory.exists():
                        shutil.rmtree(staging_directory)
                    return FetchedRelease(
                        repository=candidate.repository,
                        release_id=candidate.release_id,
                        tag=candidate.tag,
                        mode=mode,
                        assets=tuple(committed),
                    )
            GitHubAvdbReleaseClient._close_validations(assets)
            GitHubAvdbReleaseClient._cleanup(assets)
            if staging_directory.exists():
                shutil.rmtree(staging_directory)
            if isinstance(commit_error, AvdbAssetError):
                raise
            raise AvdbAssetError("internal_error") from None
        return FetchedRelease(
            repository=candidate.repository,
            release_id=candidate.release_id,
            tag=candidate.tag,
            mode=mode,
            assets=tuple(committed),
        )

    @staticmethod
    def _reuse_committed(
        final_directory: Path,
        assets: tuple[_TemporaryAsset, ...],
    ) -> list[FetchedAsset]:
        try:
            if final_directory.is_symlink() or not final_directory.is_dir():
                raise AvdbAssetError("state_conflict")
            expected = {asset.descriptor.name: asset for asset in assets}
            entries = list(final_directory.iterdir())
            if {entry.name for entry in entries} != set(expected):
                raise AvdbAssetError("state_conflict")
            committed: list[FetchedAsset] = []
            for asset in assets:
                name = asset.descriptor.name
                path = final_directory / name
                if path.is_symlink() or not path.is_file():
                    raise AvdbAssetError("state_conflict")
                digest = sha256()
                byte_size = 0
                with path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        byte_size += len(chunk)
                        digest.update(chunk)
                if byte_size != asset.byte_size or not hmac.compare_digest(
                    digest.hexdigest(),
                    asset.sha256,
                ):
                    raise AvdbAssetError("state_conflict")
                committed.append(
                    FetchedAsset(
                        name=name,
                        path=path,
                        sha256=asset.sha256,
                        byte_size=asset.byte_size,
                        validation=asset.validation,
                    )
                )
            return committed
        except AvdbAssetError:
            raise
        except OSError:
            raise AvdbAssetError("state_conflict") from None

    @staticmethod
    def _cleanup(assets: tuple[_TemporaryAsset, ...] | list[_TemporaryAsset]) -> None:
        for asset in assets:
            asset.path.unlink(missing_ok=True)

    @staticmethod
    def _close_validations(
        assets: tuple[_TemporaryAsset, ...] | list[_TemporaryAsset],
    ) -> None:
        for asset in assets:
            close = getattr(asset.validation, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except Exception:
                _LOGGER.error("avdb_plaintext_cleanup_failed")

    @staticmethod
    def _read_limited(response: httpx.Response, maximum: int) -> bytes:
        GitHubAvdbReleaseClient._validate_content_length(response, maximum)
        content = bytearray()
        for chunk in response.iter_bytes():
            if len(chunk) > maximum - len(content):
                raise AvdbAssetError()
            content.extend(chunk)
        if not content:
            raise AvdbAssetError()
        return bytes(content)

    @staticmethod
    def _validate_content_length(response: httpx.Response, maximum: int) -> None:
        declared = response.headers.get("content-length")
        if declared is None:
            return
        try:
            value = int(declared)
        except ValueError:
            raise AvdbAssetError() from None
        if not 0 < value <= maximum:
            raise AvdbAssetError()

    @staticmethod
    def _is_allowed_url(url: str, hosts: frozenset[str]) -> bool:
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.lower() in hosts
            and port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
