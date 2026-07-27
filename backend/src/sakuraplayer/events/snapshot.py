from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.metadata_api import MetadataAdminService, MetadataJobView
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.events.outbox import EventLog

SNAPSHOT_ITEM_LIMIT = 100


@dataclass(frozen=True)
class SnapshotExtensionView:
    cache_jobs: list[dict[str, object]]
    cloud115_binding: dict[str, object]
    notifications: list[dict[str, object]]
    cache_queued: int = 0
    cache_running: int = 0
    cache_ready: int = 0


class SnapshotExtension(Protocol):
    def snapshot(self, session: Session, *, limit: int) -> SnapshotExtensionView: ...


class EmptySnapshotExtension:
    def snapshot(self, session: Session, *, limit: int) -> SnapshotExtensionView:
        del session, limit
        return SnapshotExtensionView(
            cache_jobs=[],
            cloud115_binding={
                "bound": False,
                "status": "unbound",
                "display_name": None,
                "cache_root_ready": False,
                "last_verified_at": None,
            },
            notifications=[],
        )


@dataclass(frozen=True)
class QueueSnapshotView:
    metadata_queued: int
    metadata_running: int
    cache_queued: int
    cache_running: int
    cache_ready: int


@dataclass(frozen=True)
class EventSnapshotView:
    snapshot_version: int
    last_event_id: uuid.UUID | None
    queues: QueueSnapshotView
    cache_jobs: list[dict[str, object]]
    metadata_jobs: list[MetadataJobView]
    cloud115_binding: dict[str, object]
    notifications: list[dict[str, object]]


class EventSnapshotService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_log: EventLog,
        *,
        extension: SnapshotExtension | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._event_log = event_log
        self._extension = extension or EmptySnapshotExtension()

    def get(self) -> EventSnapshotView:
        with self._session_factory.begin() as session:
            snapshot_version, last_event_id = self._event_log.watermark(session)
            counts = {
                status: int(count)
                for status, count in session.execute(
                    select(MetadataJob.status, func.count(MetadataJob.id)).group_by(
                        MetadataJob.status
                    )
                )
            }
            jobs = list(
                session.scalars(
                    select(MetadataJob)
                    .order_by(
                        case(
                            (MetadataJob.status.in_(("queued", "running")), 0),
                            else_=1,
                        ),
                        func.coalesce(
                            MetadataJob.finished_at,
                            MetadataJob.created_at,
                        ).desc(),
                        MetadataJob.id.desc(),
                    )
                    .limit(SNAPSHOT_ITEM_LIMIT)
                )
            )
            metadata_jobs = MetadataAdminService.views_in_session(session, jobs)
            extension = self._extension.snapshot(
                session,
                limit=SNAPSHOT_ITEM_LIMIT,
            )
            return EventSnapshotView(
                snapshot_version=snapshot_version,
                last_event_id=last_event_id,
                queues=QueueSnapshotView(
                    metadata_queued=counts.get("queued", 0),
                    metadata_running=counts.get("running", 0),
                    cache_queued=extension.cache_queued,
                    cache_running=extension.cache_running,
                    cache_ready=extension.cache_ready,
                ),
                cache_jobs=extension.cache_jobs[:SNAPSHOT_ITEM_LIMIT],
                metadata_jobs=metadata_jobs,
                cloud115_binding=extension.cloud115_binding,
                notifications=extension.notifications[:SNAPSHOT_ITEM_LIMIT],
            )


__all__ = [
    "EmptySnapshotExtension",
    "EventSnapshotService",
    "EventSnapshotView",
    "QueueSnapshotView",
    "SNAPSHOT_ITEM_LIMIT",
    "SnapshotExtension",
    "SnapshotExtensionView",
]
