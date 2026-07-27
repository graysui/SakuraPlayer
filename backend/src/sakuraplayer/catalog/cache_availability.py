from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.ports import SourceAvailability
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
)
from sakuraplayer.resources.models import ResourceSource


class CacheSourceAvailabilityPort:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_many(
        self,
        source_ids: tuple[uuid.UUID, ...],
    ) -> dict[uuid.UUID, SourceAvailability]:
        if not source_ids:
            return {}
        unique_ids = tuple(dict.fromkeys(source_ids))
        with self._session_factory() as session:
            sources = {
                source.id: source.identification_status
                for source in session.scalars(
                    select(ResourceSource).where(ResourceSource.id.in_(unique_ids))
                )
            }
            jobs = list(
                session.scalars(
                    select(CacheJob)
                    .where(CacheJob.source_id.in_(unique_ids))
                    .order_by(CacheJob.created_at.desc(), CacheJob.id.desc())
                )
            )
            selected_sizes: dict[uuid.UUID, int] = {
                job_id: int(total_size)
                for job_id, total_size in session.execute(
                    select(
                        CacheJobMediaSelection.cache_job_id,
                        func.sum(RemoteMedia.size_bytes),
                    )
                    .join(
                        RemoteMedia, RemoteMedia.id == CacheJobMediaSelection.media_id
                    )
                    .where(
                        CacheJobMediaSelection.cache_job_id.in_(
                            tuple(job.id for job in jobs)
                        )
                    )
                    .group_by(CacheJobMediaSelection.cache_job_id)
                ).all()
            }
        latest: dict[uuid.UUID, CacheJob] = {}
        active: dict[uuid.UUID, CacheJob] = {}
        for job in jobs:
            latest.setdefault(job.source_id, job)
            if job.capacity_class != "released":
                active.setdefault(job.source_id, job)
        result: dict[uuid.UUID, SourceAvailability] = {}
        for source_id in unique_ids:
            if sources.get(source_id) == "rejected":
                result[source_id] = SourceAvailability(state="rejected")
                continue
            latest_job = active.get(source_id) or latest.get(source_id)
            if latest_job is None or latest_job.status in {"cleaned", "detached"}:
                result[source_id] = SourceAvailability()
            elif latest_job.status in {"failed", "cleanup_failed"}:
                result[source_id] = SourceAvailability(state="failed")
            elif latest_job.status == "ready":
                result[source_id] = SourceAvailability(
                    state="ready",
                    video_file_size_bytes=(
                        int(selected_sizes[latest_job.id])
                        if latest_job.id in selected_sizes
                        else None
                    ),
                )
            elif latest_job.status == "queued":
                result[source_id] = SourceAvailability(state="queued")
            else:
                result[source_id] = SourceAvailability(state="running")
        return result


__all__ = ["CacheSourceAvailabilityPort"]
