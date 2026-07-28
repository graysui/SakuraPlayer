from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    Cloud115Binding,
    Notification,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.cloud_cache.notifications import notification_payload
from sakuraplayer.events.snapshot import SnapshotExtensionView

_ACTIVE_STATUSES = (
    "queued",
    "submitting",
    "offlining",
    "submit_uncertain",
    "resolving",
    "awaiting_selection",
    "ready",
    "cancelling",
    "cleaning",
    "cleanup_failed",
)


class CacheSnapshotExtension:
    def snapshot(self, session: Session, *, limit: int) -> SnapshotExtensionView:
        jobs = list(
            session.scalars(
                select(CacheJob)
                .order_by(
                    case((CacheJob.status.in_(_ACTIVE_STATUSES), 0), else_=1),
                    CacheJob.updated_at.desc(),
                    CacheJob.id.desc(),
                )
                .limit(limit)
            )
        )
        counts = {
            capacity_class: int(count)
            for capacity_class, count in session.execute(
                select(CacheJob.capacity_class, func.count(CacheJob.id))
                .where(CacheJob.capacity_class != "released")
                .group_by(CacheJob.capacity_class)
            )
        }
        binding = session.scalar(
            select(Cloud115Binding).where(Cloud115Binding.singleton_key.is_(True))
        )
        notifications = list(
            session.scalars(
                select(Notification)
                .where(Notification.read_at.is_(None))
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            )
        )
        return SnapshotExtensionView(
            cache_jobs=[cache_job_payload(session, job) for job in jobs],
            cloud115_binding=binding_payload(binding),
            notifications=[notification_payload(item) for item in notifications],
            cache_queued=counts.get("queued", 0),
            cache_running=counts.get("running", 0),
            cache_ready=counts.get("ready", 0),
        )


def cache_job_payload(session: Session, job: CacheJob) -> dict[str, object]:
    media_rows = list(
        session.scalars(select(RemoteMedia).where(RemoteMedia.cache_job_id == job.id))
    )
    group_rank: dict[uuid.UUID, tuple[int, int]] = {}
    for item in media_rows:
        score, size = group_rank.get(item.candidate_id, (0, 0))
        group_rank[item.candidate_id] = (
            max(score, item.selection_score),
            size + item.size_bytes,
        )
    media_rows.sort(
        key=lambda item: (
            -group_rank[item.candidate_id][0],
            -group_rank[item.candidate_id][1],
            str(item.candidate_id),
            item.sequence_no,
            item.id,
        )
    )
    selected = tuple(
        session.scalars(
            select(CacheJobMediaSelection.media_id)
            .where(CacheJobMediaSelection.cache_job_id == job.id)
            .order_by(CacheJobMediaSelection.sequence_no)
        )
    )
    subtitle_rows = list(
        session.scalars(
            select(RemoteSubtitle).where(RemoteSubtitle.cache_job_id == job.id)
        )
    )
    extension_order = {"srt": 0, "ass": 1, "ssa": 2, "vtt": 3}
    subtitle_rows.sort(
        key=lambda item: (
            -item.match_score,
            extension_order[item.extension],
            item.name.casefold(),
            item.id,
        )
    )
    default_id = next(
        (
            item.id
            for item in subtitle_rows
            if item.media_id is not None and item.media_id in selected
        ),
        None,
    )
    return {
        "id": str(job.id),
        "movie_id": str(job.movie_id),
        "source_id": str(job.source_id),
        "status": job.status,
        "remote_percent": float(job.remote_percent),
        "error_code": job.failure_code,
        "media_candidates": [
            {
                "id": str(item.id),
                "candidate_id": str(item.candidate_id),
                "name": item.name,
                "size_bytes": item.size_bytes,
                "duration_seconds": item.duration_seconds,
                "sequence_no": item.sequence_no,
                "is_valid": item.is_valid,
            }
            for item in media_rows
        ],
        "selected_media_ids": [str(media_id) for media_id in selected],
        "subtitles": [
            {
                "id": str(item.id),
                "media_id": str(item.media_id) if item.media_id is not None else None,
                "name": item.name,
                "format": item.extension,
                "language": None,
                "selected_by_default": item.id == default_id,
            }
            for item in subtitle_rows
        ],
        "ready_at": _utc_iso(job.ready_at),
        "expires_at": _utc_iso(job.expires_at),
        "created_at": _utc_iso(job.created_at),
        "updated_at": _utc_iso(job.updated_at),
    }


def binding_payload(binding: Cloud115Binding | None) -> dict[str, object]:
    if binding is None:
        return {
            "bound": False,
            "status": "unbound",
            "display_name": None,
            "cache_root_ready": False,
            "last_verified_at": None,
        }
    return {
        "bound": True,
        "status": binding.status,
        "display_name": binding.display_name,
        "cache_root_ready": binding.status != "detached",
        "last_verified_at": _utc_iso(binding.last_verified_at),
    }


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "CacheSnapshotExtension",
    "binding_payload",
    "cache_job_payload",
]
