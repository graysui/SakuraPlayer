from __future__ import annotations

from sqlalchemy.orm import Session

from sakuraplayer.cloud_cache.models import CacheJob, Cloud115Binding
from sakuraplayer.cloud_cache.notifications import NotificationWriter
from sakuraplayer.cloud_cache.snapshot import binding_payload, cache_job_payload
from sakuraplayer.events.outbox import DomainEventWriter

_CACHE_EVENT_TYPES = frozenset(
    {
        "cache.job.created.v1",
        "cache.job.updated.v1",
        "cache.job.selection_required.v1",
        "cache.job.ready.v1",
        "cache.job.failed.v1",
        "cache.job.cancelled.v1",
        "cache.job.cleaned.v1",
        "cache.job.cleanup_failed.v1",
        "cache.job.detached.v1",
    }
)


class CacheEventPublisher:
    def __init__(
        self,
        event_writer: DomainEventWriter,
        notification_writer: NotificationWriter,
    ) -> None:
        self._event_writer = event_writer
        self._notifications = notification_writer

    def publish_cache(
        self,
        session: Session,
        job: CacheJob,
        *,
        event_type: str,
        notification_type: str | None = None,
        extra: dict[str, object] | None = None,
        publish_event: bool = True,
    ) -> None:
        if event_type not in _CACHE_EVENT_TYPES:
            raise ValueError("invalid cache event type")
        if publish_event:
            payload = cache_job_payload(session, job)
            if extra is not None:
                payload.update(extra)
            self._event_writer.append(
                session,
                stream="cache",
                aggregate_id=job.id,
                event_type=event_type,
                payload=payload,
            )
        if notification_type is not None:
            suffix = notification_type.removeprefix("cache_")
            self._notifications.create(
                session,
                notification_type=notification_type,
                resource_id=job.id,
                error_code=(
                    job.failure_code if notification_type == "cache_failed" else None
                ),
                dedupe_key=f"cache:{job.id}:{suffix}",
            )

    def publish_credential(
        self,
        session: Session,
        binding: Cloud115Binding,
        *,
        previous_status: str | None,
        status: str | None = None,
    ) -> None:
        payload = binding_payload(binding)
        if status is not None:
            payload["status"] = status
            payload["bound"] = status != "unbound"
            if status == "unbound":
                payload["cache_root_ready"] = False
        self._event_writer.append(
            session,
            stream="credential",
            aggregate_id=binding.id,
            event_type="credential.cloud115.changed.v1",
            payload=payload,
        )
        effective_status = str(payload["status"])
        if effective_status == "expired" and previous_status != "expired":
            self._notifications.create(
                session,
                notification_type="credential_expired",
                resource_id=binding.id,
                error_code="cloud115_credentials_expired",
                dedupe_key=(
                    f"credential:{binding.id}:{binding.credential_version}:expired"
                ),
            )


__all__ = ["CacheEventPublisher"]
