from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import uuid

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.actor_mapping import (
    ActorMappingProblem,
    ActorMappingReconciler,
    parse_actor_mapping,
)
from sakuraplayer.catalog.gfriends import (
    GfriendsAssetReconciler,
    GfriendsProblem,
    parse_gfriends,
)
from sakuraplayer.catalog.models import (
    ActorMappingSnapshot,
    GfriendsSnapshot,
    ProviderSnapshotRequest,
)
from sakuraplayer.shared.redaction import stable_error_code


ACTOR_MAPPING_URL = (
    "https://raw.githubusercontent.com/li-peifeng/"
    "Jav-Actors-Mapping/main/actor-mapping.xml"
)
GFRIENDS_FILETREE_URL = (
    "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Filetree.json"
)


class SnapshotProblem(RuntimeError):
    def __init__(self, code: str = "provider_snapshot_invalid") -> None:
        self.code = stable_error_code(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class SnapshotSource:
    name: str
    url: str
    max_bytes: int
    suffix: str
    upstream_error: str
    validate: Callable[[bytes], object]

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if (
            not self.name
            or parsed.scheme != "https"
            or parsed.hostname != "raw.githubusercontent.com"
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or not parsed.path
            or parsed.query
            or parsed.fragment
            or self.max_bytes <= 0
            or not self.suffix.startswith(".")
        ):
            raise ValueError("invalid provider snapshot source")


ACTOR_MAPPING_SOURCE = SnapshotSource(
    name="actor_mapping",
    url=ACTOR_MAPPING_URL,
    max_bytes=16 * 1024 * 1024,
    suffix=".xml",
    upstream_error="actor_mapping_upstream_error",
    validate=parse_actor_mapping,
)
GFRIENDS_SOURCE = SnapshotSource(
    name="gfriends",
    url=GFRIENDS_FILETREE_URL,
    max_bytes=32 * 1024 * 1024,
    suffix=".json",
    upstream_error="gfriends_upstream_error",
    validate=parse_gfriends,
)


@dataclass(frozen=True)
class DownloadedSnapshot:
    source: SnapshotSource
    payload: bytes
    sha256: str
    byte_size: int
    validation: object


@dataclass(frozen=True)
class CurrentSnapshot:
    snapshot_id: uuid.UUID
    source_name: str
    sha256: str
    byte_size: int
    relative_path: str


class ProviderSnapshotDownloader:
    def __init__(self, http_client: httpx.Client) -> None:
        self._http_client = http_client

    def fetch(self, source: SnapshotSource) -> DownloadedSnapshot:
        current_url = source.url
        try:
            for redirect_count in range(4):
                with self._http_client.stream(
                    "GET",
                    current_url,
                    follow_redirects=False,
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location or redirect_count == 3:
                            raise SnapshotProblem
                        current_url = urljoin(current_url, location)
                        if current_url != source.url:
                            raise SnapshotProblem
                        continue
                    if response.status_code != 200:
                        raise SnapshotProblem(source.upstream_error)
                    declared = response.headers.get("Content-Length")
                    if declared is not None:
                        try:
                            declared_size = int(declared)
                        except ValueError:
                            raise SnapshotProblem from None
                        if declared_size < 0 or declared_size > source.max_bytes:
                            raise SnapshotProblem
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > source.max_bytes:
                            raise SnapshotProblem
                    payload = bytes(body)
                    if not payload:
                        raise SnapshotProblem
                    try:
                        validation = source.validate(payload)
                    except ValueError:
                        raise SnapshotProblem from None
                    return DownloadedSnapshot(
                        source=source,
                        payload=payload,
                        sha256=hashlib.sha256(payload).hexdigest(),
                        byte_size=len(payload),
                        validation=validation,
                    )
        except SnapshotProblem:
            raise
        except (httpx.HTTPError, OSError):
            raise SnapshotProblem(source.upstream_error) from None
        raise SnapshotProblem


class ProviderSnapshotStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def store(self, downloaded: DownloadedSnapshot) -> str:
        relative = (
            Path("metadata")
            / downloaded.source.name
            / f"{downloaded.sha256}{downloaded.source.suffix}"
        )
        target = self._root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if (
                target.stat().st_size != downloaded.byte_size
                or hashlib.sha256(target.read_bytes()).hexdigest() != downloaded.sha256
            ):
                raise SnapshotProblem
            return relative.as_posix()
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(downloaded.payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return relative.as_posix()


class ProviderSnapshotRegistry:
    _MODELS = {
        "actor_mapping": ActorMappingSnapshot,
        "gfriends": GfriendsSnapshot,
    }

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def activate(
        self,
        downloaded: DownloadedSnapshot,
        *,
        relative_path: str,
        apply: Callable[[Session, uuid.UUID], object] | None = None,
    ) -> uuid.UUID:
        model = self._model(downloaded.source.name)
        path = Path(relative_path)
        if path.is_absolute() or not path.parts or any(part == ".." for part in path.parts):
            raise SnapshotProblem
        current = self._utc_now()
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(model).where(model.sha256 == downloaded.sha256).with_for_update()
            )
            if existing is not None and (
                existing.byte_size != downloaded.byte_size
                or existing.relative_path != path.as_posix()
            ):
                raise SnapshotProblem
            active = session.scalar(
                select(model).where(model.status == "current").with_for_update()
            )
            if active is not None and active.id != getattr(existing, "id", None):
                active.status = "superseded"
                session.flush()
            if existing is None:
                existing = model(
                    id=uuid.uuid4(),
                    sha256=downloaded.sha256,
                    byte_size=downloaded.byte_size,
                    relative_path=path.as_posix(),
                    status="current",
                    fetched_at=current,
                    activated_at=current,
                )
                session.add(existing)
            else:
                existing.status = "current"
                existing.fetched_at = current
                existing.activated_at = current
            session.flush()
            if apply is not None:
                apply(session, existing.id)
                session.flush()
            return existing.id

    def current(self, source_name: str) -> CurrentSnapshot | None:
        model = self._model(source_name)
        with self._session_factory() as session:
            snapshot = session.scalar(select(model).where(model.status == "current"))
            if snapshot is None:
                return None
            return CurrentSnapshot(
                snapshot_id=snapshot.id,
                source_name=source_name,
                sha256=snapshot.sha256,
                byte_size=snapshot.byte_size,
                relative_path=snapshot.relative_path,
            )

    @classmethod
    def _model(cls, source_name: str):
        try:
            return cls._MODELS[source_name]
        except KeyError:
            raise ValueError("invalid provider snapshot source") from None

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("provider snapshot registry clock must be timezone-aware")
        return current.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProviderSnapshotRefreshOutcome:
    snapshot_ids: tuple[tuple[str, uuid.UUID], ...]
    failures: tuple[tuple[str, str], ...]


class ProviderSnapshotRefreshService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        http_client: httpx.Client,
        cache_root: Path,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._downloader = ProviderSnapshotDownloader(http_client)
        self._store = ProviderSnapshotStore(cache_root)
        self.registry = ProviderSnapshotRegistry(session_factory, now=now)
        self._actor_mapping = ActorMappingReconciler(session_factory, now=now)
        self._gfriends = GfriendsAssetReconciler(session_factory, now=now)

    def refresh_all(self) -> ProviderSnapshotRefreshOutcome:
        snapshot_ids: list[tuple[str, uuid.UUID]] = []
        failures: list[tuple[str, str]] = []
        for source in (ACTOR_MAPPING_SOURCE, GFRIENDS_SOURCE):
            try:
                downloaded = self._downloader.fetch(source)
                relative_path = self._store.store(downloaded)
                if source.name == "actor_mapping":
                    apply = lambda session, snapshot_id: self._actor_mapping.rebuild_in_session(
                        session,
                        downloaded.validation,
                    )
                else:
                    apply = lambda session, snapshot_id: self._gfriends.rebuild_in_session(
                        session,
                        downloaded.validation,
                        snapshot_id=snapshot_id,
                    )
                snapshot_id = self.registry.activate(
                    downloaded,
                    relative_path=relative_path,
                    apply=apply,
                )
                snapshot_ids.append((source.name, snapshot_id))
            except (SnapshotProblem, ActorMappingProblem, GfriendsProblem) as error:
                failures.append((source.name, error.code))
        return ProviderSnapshotRefreshOutcome(
            snapshot_ids=tuple(snapshot_ids),
            failures=tuple(failures),
        )


@dataclass(frozen=True)
class ProviderSnapshotEnqueueOutcome:
    request_id: uuid.UUID
    created: bool


@dataclass(frozen=True)
class ProviderSnapshotClaim:
    request_id: uuid.UUID
    claim_owner: str
    claim_token: uuid.UUID
    claim_expires_at: datetime


class ProviderSnapshotQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def enqueue(self) -> ProviderSnapshotEnqueueOutcome:
        current = self._utc_now()
        scheduled_for = current.replace(second=0, microsecond=0)
        request_id = uuid.uuid4()
        try:
            with self._session_factory.begin() as session:
                session.add(
                    ProviderSnapshotRequest(
                        id=request_id,
                        scheduled_for=scheduled_for,
                        status="queued",
                        claim_owner=None,
                        claim_token=None,
                        claim_expires_at=None,
                        attempt_count=0,
                        created_at=current,
                        completed_at=None,
                        failure_code=None,
                    )
                )
        except IntegrityError:
            with self._session_factory() as session:
                existing = session.scalar(
                    select(ProviderSnapshotRequest).where(
                        ProviderSnapshotRequest.scheduled_for == scheduled_for
                    )
                )
                if existing is None:
                    raise
                return ProviderSnapshotEnqueueOutcome(existing.id, created=False)
        return ProviderSnapshotEnqueueOutcome(request_id, created=True)

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_duration: timedelta,
    ) -> ProviderSnapshotClaim | None:
        if not worker_id or len(worker_id) > 128 or lease_duration <= timedelta(0):
            raise ValueError("invalid provider snapshot claim")
        current = self._utc_now()
        claim_token = uuid.uuid4()
        expires_at = current + lease_duration
        with self._session_factory.begin() as session:
            request = session.scalar(
                select(ProviderSnapshotRequest)
                .where(
                    or_(
                        ProviderSnapshotRequest.status == "queued",
                        (
                            (ProviderSnapshotRequest.status == "claimed")
                            & (ProviderSnapshotRequest.claim_expires_at <= current)
                        ),
                    )
                )
                .order_by(
                    ProviderSnapshotRequest.scheduled_for,
                    ProviderSnapshotRequest.id,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if request is None:
                return None
            request.status = "claimed"
            request.claim_owner = worker_id
            request.claim_token = claim_token
            request.claim_expires_at = expires_at
            request.attempt_count += 1
            request.completed_at = None
            request.failure_code = None
            return ProviderSnapshotClaim(
                request_id=request.id,
                claim_owner=worker_id,
                claim_token=claim_token,
                claim_expires_at=expires_at,
            )

    def complete(self, claim: ProviderSnapshotClaim) -> None:
        self._finish(claim, status="completed", code=None)

    def renew(
        self,
        claim: ProviderSnapshotClaim,
        *,
        lease_duration: timedelta,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("invalid provider snapshot lease")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(ProviderSnapshotRequest)
                .where(
                    ProviderSnapshotRequest.id == claim.request_id,
                    ProviderSnapshotRequest.status == "claimed",
                    ProviderSnapshotRequest.claim_owner == claim.claim_owner,
                    ProviderSnapshotRequest.claim_token == claim.claim_token,
                    ProviderSnapshotRequest.claim_expires_at > current,
                )
                .values(claim_expires_at=current + lease_duration)
            )
            if result.rowcount != 1:
                raise RuntimeError("provider snapshot request claim was lost")

    def fail(self, claim: ProviderSnapshotClaim, *, code: str) -> None:
        self._finish(claim, status="failed", code=stable_error_code(code))

    def _finish(
        self,
        claim: ProviderSnapshotClaim,
        *,
        status: str,
        code: str | None,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(ProviderSnapshotRequest)
                .where(
                    ProviderSnapshotRequest.id == claim.request_id,
                    ProviderSnapshotRequest.status == "claimed",
                    ProviderSnapshotRequest.claim_owner == claim.claim_owner,
                    ProviderSnapshotRequest.claim_token == claim.claim_token,
                    ProviderSnapshotRequest.claim_expires_at > current,
                )
                .values(
                    status=status,
                    claim_owner=None,
                    claim_token=None,
                    claim_expires_at=None,
                    completed_at=current,
                    failure_code=code,
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("provider snapshot request claim was lost")

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("provider snapshot queue clock must be timezone-aware")
        return current.astimezone(timezone.utc)


__all__ = [
    "ACTOR_MAPPING_SOURCE",
    "GFRIENDS_SOURCE",
    "CurrentSnapshot",
    "DownloadedSnapshot",
    "ProviderSnapshotClaim",
    "ProviderSnapshotDownloader",
    "ProviderSnapshotEnqueueOutcome",
    "ProviderSnapshotQueue",
    "ProviderSnapshotRefreshOutcome",
    "ProviderSnapshotRefreshService",
    "ProviderSnapshotRegistry",
    "ProviderSnapshotStore",
    "SnapshotProblem",
    "SnapshotSource",
]
