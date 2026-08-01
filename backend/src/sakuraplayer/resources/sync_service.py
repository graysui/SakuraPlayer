from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.models import AvdbAsset, AvdbSyncRequest, AvdbSyncRun
from sakuraplayer.shared.redaction import stable_error_code

_SHA256 = re.compile(r"[0-9a-f]{64}")
_EMPTY_STATS = {"inserted": 0, "pending": 0, "skipped": 0, "updated": 0}
_MANIFEST_FIELDS = frozenset({"algorithm", "iterations", "kdf", "key_length"})


class RowStream(Protocol):
    manifest_summary: Mapping[str, object]

    def iter_rows(self) -> Iterator[dict[str, object]]: ...


class AvdbSyncFailed(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = stable_error_code(code)
        super().__init__(self.code)


class RunClaimLost(RuntimeError):
    code = "state_conflict"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class BatchStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    pending: int = 0

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.as_dict().values()):
            raise ValueError("batch stats cannot be negative")

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "pending": self.pending,
            "skipped": self.skipped,
            "updated": self.updated,
        }


@dataclass(frozen=True)
class SyncOutcome:
    run_id: uuid.UUID
    status: str
    idempotent: bool


@dataclass(frozen=True)
class SuccessfulSyncSnapshot:
    run_id: uuid.UUID
    mode: str
    repository: str
    release_id: str
    cursor: dict[str, object]
    stats: dict[str, int]
    completed_at: datetime


@dataclass(frozen=True)
class EnqueueOutcome:
    request_id: uuid.UUID
    created: bool


@dataclass(frozen=True)
class ClaimedRequest:
    request_id: uuid.UUID
    mode: str
    claim_owner: str
    claim_token: uuid.UUID
    claim_expires_at: datetime


@dataclass(frozen=True)
class _RunClaim:
    run_id: uuid.UUID
    claim_token: uuid.UUID
    should_process: bool
    status: str
    cursor: dict[str, object]
    stats: BatchStats


Importer = Callable[[str, tuple[dict[str, object], ...]], BatchStats]


class AvdbSyncQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def enqueue(self, mode: str) -> EnqueueOutcome:
        if mode not in {"incremental_30d", "full_reconcile"}:
            raise ValueError("invalid AVdb synchronization mode")
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("queue clock must be timezone-aware")
        scheduled_for = current.astimezone(timezone.utc).replace(
            second=0,
            microsecond=0,
        )
        request_id = uuid.uuid4()
        try:
            with self._session_factory.begin() as session:
                session.add(
                    AvdbSyncRequest(
                        id=request_id,
                        mode=mode,
                        scheduled_for=scheduled_for,
                        status="queued",
                        claim_owner=None,
                        claim_token=None,
                        claimed_at=None,
                        claim_expires_at=None,
                        attempt_count=0,
                        created_at=current.astimezone(timezone.utc),
                        completed_at=None,
                        failure_code=None,
                        failure_detail=None,
                        sync_run_id=None,
                    )
                )
        except IntegrityError:
            with self._session_factory() as session:
                existing = session.scalar(
                    select(AvdbSyncRequest).where(
                        AvdbSyncRequest.mode == mode,
                        AvdbSyncRequest.scheduled_for == scheduled_for,
                    )
                )
                if existing is None:
                    raise
                return EnqueueOutcome(existing.id, created=False)
        return EnqueueOutcome(request_id, created=True)

    def ensure_initial_full(self) -> EnqueueOutcome | None:
        with self._session_factory() as session:
            existing_request = session.scalar(
                select(AvdbSyncRequest.id)
                .where(AvdbSyncRequest.mode == "full_reconcile")
                .limit(1)
            )
            existing_run = session.scalar(
                select(AvdbSyncRun.id)
                .where(AvdbSyncRun.mode == "full_reconcile")
                .limit(1)
            )
        if existing_request is not None or existing_run is not None:
            return None
        return self.enqueue("full_reconcile")

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_duration: timedelta,
    ) -> ClaimedRequest | None:
        if not worker_id or len(worker_id) > 64 or lease_duration <= timedelta(0):
            raise ValueError("invalid AVdb worker claim")
        current = self._utc_now()
        expires_at = current + lease_duration
        claim_token = uuid.uuid4()
        with self._session_factory.begin() as session:
            request = session.scalar(
                select(AvdbSyncRequest)
                .where(
                    or_(
                        AvdbSyncRequest.status == "queued",
                        (
                            (AvdbSyncRequest.status == "claimed")
                            & (AvdbSyncRequest.claim_expires_at <= current)
                        ),
                    )
                )
                .order_by(AvdbSyncRequest.scheduled_for, AvdbSyncRequest.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if request is None:
                return None
            request.status = "claimed"
            request.claim_owner = worker_id
            request.claim_token = claim_token
            request.claimed_at = current
            request.claim_expires_at = expires_at
            request.attempt_count += 1
            request.completed_at = None
            request.failure_code = None
            request.failure_detail = None
            request.sync_run_id = None
            return ClaimedRequest(
                request_id=request.id,
                mode=request.mode,
                claim_owner=worker_id,
                claim_token=claim_token,
                claim_expires_at=expires_at,
            )

    def renew(
        self,
        claim: ClaimedRequest,
        *,
        lease_duration: timedelta,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("invalid AVdb request lease")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AvdbSyncRequest)
                .where(
                    AvdbSyncRequest.id == claim.request_id,
                    AvdbSyncRequest.status == "claimed",
                    AvdbSyncRequest.claim_owner == claim.claim_owner,
                    AvdbSyncRequest.claim_token == claim.claim_token,
                    AvdbSyncRequest.claim_expires_at > current,
                )
                .values(claim_expires_at=current + lease_duration)
            )
            if result.rowcount != 1:
                raise RuntimeError("AVdb request claim was lost")

    def is_claim_active(
        self,
        request_id: uuid.UUID,
        claim_token: uuid.UUID,
    ) -> bool:
        current = self._utc_now()
        with self._session_factory() as session:
            active = session.scalar(
                select(AvdbSyncRequest.id).where(
                    AvdbSyncRequest.id == request_id,
                    AvdbSyncRequest.status == "claimed",
                    AvdbSyncRequest.claim_token == claim_token,
                    AvdbSyncRequest.claim_expires_at > current,
                )
            )
        return active is not None

    def complete(self, claim: ClaimedRequest, *, run_id: uuid.UUID) -> None:
        self._finish(claim, status="completed", code=None, detail=None, run_id=run_id)

    def fail(self, claim: ClaimedRequest, *, code: str, detail: str) -> None:
        safe_code = stable_error_code(code)
        self._finish(
            claim,
            status="failed",
            code=safe_code,
            detail=stable_error_code(detail),
            run_id=None,
        )

    def _finish(
        self,
        claim: ClaimedRequest,
        *,
        status: str,
        code: str | None,
        detail: str | None,
        run_id: uuid.UUID | None,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AvdbSyncRequest)
                .where(
                    AvdbSyncRequest.id == claim.request_id,
                    AvdbSyncRequest.status == "claimed",
                    AvdbSyncRequest.claim_owner == claim.claim_owner,
                    AvdbSyncRequest.claim_token == claim.claim_token,
                    AvdbSyncRequest.claim_expires_at > current,
                )
                .values(
                    status=status,
                    claim_owner=None,
                    claim_token=None,
                    claim_expires_at=None,
                    completed_at=current,
                    failure_code=code,
                    failure_detail=detail,
                    sync_run_id=run_id,
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("AVdb request claim was lost")

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("queue clock must be timezone-aware")
        return current.astimezone(timezone.utc)


class AvdbSyncService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        batch_size: int = 1000,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch size must be positive")
        self._session_factory = session_factory
        self._batch_size = batch_size
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lease_duration = timedelta(minutes=10)

    def sync(self, release: FetchedRelease, *, importer: Importer) -> SyncOutcome:
        self._validate_release(release)
        claim = self._start_run(release)
        if not claim.should_process:
            return SyncOutcome(
                run_id=claim.run_id,
                status=claim.status,
                idempotent=True,
            )

        run_id = claim.run_id
        cumulative = claim.stats
        resume_cursor = claim.cursor
        current_asset_id: uuid.UUID | None = None
        try:
            for asset_index, asset in enumerate(release.assets, start=1):
                stream = self._row_stream(asset)
                current_asset_id, imported = self._record_or_resume_asset(
                    run_id,
                    asset,
                    stream,
                    claim.claim_token,
                )
                if imported:
                    current_asset_id = None
                    continue
                row_offset = (
                    int(resume_cursor.get("row_offset", 0))
                    if resume_cursor.get("asset_name") == asset.name
                    and resume_cursor.get("asset_index") == asset_index
                    else 0
                )
                rows = stream.iter_rows()
                for _ in range(row_offset):
                    try:
                        next(rows)
                    except StopIteration:
                        raise ValueError(
                            "saved AVdb cursor exceeds asset rows"
                        ) from None
                for batch in self._batches(rows):
                    delta = importer(asset.name, batch)
                    if not isinstance(delta, BatchStats):
                        raise TypeError("importer must return BatchStats")
                    cumulative = self._add_stats(cumulative, delta)
                    row_offset += len(batch)
                    self._advance(
                        run_id,
                        cursor={
                            "asset_index": asset_index,
                            "asset_name": asset.name,
                            "row_offset": row_offset,
                        },
                        stats=cumulative,
                        claim_token=claim.claim_token,
                    )
                self._set_asset_status(
                    current_asset_id,
                    "imported",
                    run_id=run_id,
                    claim_token=claim.claim_token,
                )
                current_asset_id = None
            self._complete(run_id, claim.claim_token)
            return SyncOutcome(run_id=run_id, status="completed", idempotent=False)
        except RunClaimLost as error:
            raise AvdbSyncFailed(error.code) from None
        except Exception as error:
            code = stable_error_code(getattr(error, "code", None))
            try:
                if current_asset_id is not None:
                    self._set_asset_status(
                        current_asset_id,
                        "failed",
                        run_id=run_id,
                        claim_token=claim.claim_token,
                    )
                self._fail(run_id, claim.claim_token, code)
            except RunClaimLost:
                raise AvdbSyncFailed("state_conflict") from None
            raise AvdbSyncFailed(code) from None

    def latest_successful(self, mode: str) -> SuccessfulSyncSnapshot | None:
        if mode not in {"incremental_30d", "full_reconcile"}:
            raise ValueError("invalid AVdb synchronization mode")
        with self._session_factory() as session:
            run = session.scalar(
                select(AvdbSyncRun)
                .where(
                    AvdbSyncRun.mode == mode,
                    AvdbSyncRun.status == "completed",
                )
                .order_by(AvdbSyncRun.completed_at.desc(), AvdbSyncRun.id.desc())
                .limit(1)
            )
            if run is None or run.completed_at is None:
                return None
            return SuccessfulSyncSnapshot(
                run_id=run.id,
                mode=run.mode,
                repository=run.repository,
                release_id=run.release_id,
                cursor=dict(run.cursor),
                stats={key: int(value) for key, value in run.stats.items()},
                completed_at=run.completed_at,
            )

    def _start_run(self, release: FetchedRelease) -> _RunClaim:
        run_id = uuid.uuid4()
        claim_token = uuid.uuid4()
        current = self._utc_now()
        expires_at = current + self._lease_duration
        try:
            with self._session_factory.begin() as session:
                session.add(
                    AvdbSyncRun(
                        id=run_id,
                        mode=release.mode,
                        repository=release.repository,
                        release_id=release.release_id,
                        status="running",
                        cursor={},
                        started_at=current,
                        completed_at=None,
                        failure_code=None,
                        failure_detail=None,
                        stats=dict(_EMPTY_STATS),
                        claim_token=claim_token,
                        claim_expires_at=expires_at,
                        attempt_count=1,
                    )
                )
        except IntegrityError:
            with self._session_factory.begin() as session:
                existing = session.scalar(
                    select(AvdbSyncRun)
                    .where(
                        AvdbSyncRun.repository == release.repository,
                        AvdbSyncRun.release_id == release.release_id,
                        AvdbSyncRun.mode == release.mode,
                    )
                    .with_for_update()
                )
                if existing is None:
                    raise
                active_expiry = existing.claim_expires_at
                if active_expiry is not None and active_expiry.tzinfo is None:
                    active_expiry = active_expiry.replace(tzinfo=timezone.utc)
                if existing.status == "completed" or (
                    existing.status == "running"
                    and active_expiry is not None
                    and active_expiry > current
                ):
                    return _RunClaim(
                        run_id=existing.id,
                        claim_token=claim_token,
                        should_process=False,
                        status=existing.status,
                        cursor=dict(existing.cursor),
                        stats=self._stats_from_mapping(existing.stats),
                    )
                existing.status = "running"
                existing.completed_at = None
                existing.failure_code = None
                existing.failure_detail = None
                existing.claim_token = claim_token
                existing.claim_expires_at = expires_at
                existing.attempt_count += 1
                return _RunClaim(
                    run_id=existing.id,
                    claim_token=claim_token,
                    should_process=True,
                    status="running",
                    cursor=dict(existing.cursor),
                    stats=self._stats_from_mapping(existing.stats),
                )
        return _RunClaim(
            run_id=run_id,
            claim_token=claim_token,
            should_process=True,
            status="running",
            cursor={},
            stats=BatchStats(),
        )

    def _record_or_resume_asset(
        self,
        run_id: uuid.UUID,
        asset: FetchedAsset,
        stream: RowStream,
        claim_token: uuid.UUID,
    ) -> tuple[uuid.UUID, bool]:
        asset_id = uuid.uuid4()
        manifest = dict(stream.manifest_summary)
        if set(manifest) != _MANIFEST_FIELDS:
            raise ValueError("unsafe AVdb manifest summary")
        with self._session_factory.begin() as session:
            self._assert_run_claim(session, run_id, claim_token)
            existing = session.scalar(
                select(AvdbAsset)
                .where(
                    AvdbAsset.sync_run_id == run_id,
                    AvdbAsset.asset_name == asset.name,
                )
                .with_for_update()
            )
            if existing is not None:
                if (
                    existing.sha256 != asset.sha256
                    or existing.byte_size != asset.byte_size
                    or existing.manifest != manifest
                ):
                    raise ValueError(
                        "AVdb resumed asset does not match persisted asset"
                    )
                imported = existing.status == "imported"
                if not imported:
                    existing.status = "decrypted"
                return existing.id, imported
            session.add(
                AvdbAsset(
                    id=asset_id,
                    sync_run_id=run_id,
                    asset_name=asset.name,
                    sha256=asset.sha256,
                    byte_size=asset.byte_size,
                    manifest=manifest,
                    status="decrypted",
                )
            )
        return asset_id, False

    def _advance(
        self,
        run_id: uuid.UUID,
        *,
        cursor: dict[str, object],
        stats: BatchStats,
        claim_token: uuid.UUID,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AvdbSyncRun)
                .where(
                    AvdbSyncRun.id == run_id,
                    AvdbSyncRun.status == "running",
                    AvdbSyncRun.claim_token == claim_token,
                    AvdbSyncRun.claim_expires_at > current,
                )
                .values(
                    cursor=cursor,
                    stats=stats.as_dict(),
                    claim_expires_at=current + self._lease_duration,
                )
            )
            if result.rowcount != 1:
                raise RunClaimLost

    def _set_asset_status(
        self,
        asset_id: uuid.UUID,
        status: str,
        *,
        run_id: uuid.UUID,
        claim_token: uuid.UUID,
    ) -> None:
        with self._session_factory.begin() as session:
            self._assert_run_claim(session, run_id, claim_token)
            result = session.execute(
                update(AvdbAsset)
                .where(
                    AvdbAsset.id == asset_id,
                    AvdbAsset.sync_run_id == run_id,
                )
                .values(status=status)
            )
            if result.rowcount != 1:
                raise RuntimeError("AVdb asset was not found")

    def _complete(self, run_id: uuid.UUID, claim_token: uuid.UUID) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AvdbSyncRun)
                .where(
                    AvdbSyncRun.id == run_id,
                    AvdbSyncRun.status == "running",
                    AvdbSyncRun.claim_token == claim_token,
                    AvdbSyncRun.claim_expires_at > current,
                )
                .values(
                    status="completed",
                    completed_at=current,
                    claim_token=None,
                    claim_expires_at=None,
                )
            )
            if result.rowcount != 1:
                raise RunClaimLost

    def _fail(self, run_id: uuid.UUID, claim_token: uuid.UUID, code: str) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AvdbSyncRun)
                .where(
                    AvdbSyncRun.id == run_id,
                    AvdbSyncRun.status == "running",
                    AvdbSyncRun.claim_token == claim_token,
                    AvdbSyncRun.claim_expires_at > current,
                )
                .values(
                    status="failed",
                    completed_at=current,
                    failure_code=code,
                    failure_detail=code,
                    claim_token=None,
                    claim_expires_at=None,
                )
            )
            if result.rowcount != 1:
                raise RunClaimLost

    def _batches(
        self,
        rows: Iterable[dict[str, object]],
    ) -> Iterator[tuple[dict[str, object], ...]]:
        batch: list[dict[str, object]] = []
        for row in rows:
            batch.append(row)
            if len(batch) == self._batch_size:
                yield tuple(batch)
                batch = []
        if batch:
            yield tuple(batch)

    @staticmethod
    def _row_stream(asset: FetchedAsset) -> RowStream:
        stream = asset.validation
        if not hasattr(stream, "manifest_summary") or not callable(
            getattr(stream, "iter_rows", None)
        ):
            raise ValueError("asset validation did not provide a CSV stream")
        return stream

    @staticmethod
    def _add_stats(total: BatchStats, delta: BatchStats) -> BatchStats:
        return BatchStats(
            inserted=total.inserted + delta.inserted,
            updated=total.updated + delta.updated,
            skipped=total.skipped + delta.skipped,
            pending=total.pending + delta.pending,
        )

    @staticmethod
    def _stats_from_mapping(value: Mapping[str, object]) -> BatchStats:
        try:
            return BatchStats(
                inserted=int(value.get("inserted", 0)),
                updated=int(value.get("updated", 0)),
                skipped=int(value.get("skipped", 0)),
                pending=int(value.get("pending", 0)),
            )
        except (TypeError, ValueError):
            raise ValueError("invalid persisted AVdb stats") from None

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("sync clock must be timezone-aware")
        return current.astimezone(timezone.utc)

    def _assert_run_claim(
        self,
        session: Session,
        run_id: uuid.UUID,
        claim_token: uuid.UUID,
    ) -> None:
        owner = session.scalar(
            select(AvdbSyncRun.id)
            .where(
                AvdbSyncRun.id == run_id,
                AvdbSyncRun.status == "running",
                AvdbSyncRun.claim_token == claim_token,
                AvdbSyncRun.claim_expires_at > self._utc_now(),
            )
            .with_for_update()
        )
        if owner is None:
            raise RunClaimLost

    @staticmethod
    def _validate_release(release: FetchedRelease) -> None:
        expected_assets = 1 if release.mode == "incremental_30d" else 2
        if (
            release.mode not in {"incremental_30d", "full_reconcile"}
            or len(release.assets) != expected_assets
            or not release.repository
            or not release.release_id
        ):
            raise ValueError("invalid fetched release")
        for asset in release.assets:
            if (
                _SHA256.fullmatch(asset.sha256) is None
                or asset.byte_size <= 0
                or not asset.name
            ):
                raise ValueError("invalid fetched asset")
