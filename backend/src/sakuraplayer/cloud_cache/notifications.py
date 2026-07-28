from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.models import Notification
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.api import ApiProblem

NOTIFICATION_RETENTION = timedelta(days=30)


class NotificationProblem(LookupError):
    code = "notification_not_found"


@dataclass(frozen=True, slots=True)
class NotificationView:
    id: uuid.UUID
    type: str
    resource_id: uuid.UUID | None
    error_code: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationWriter:
    def __init__(
        self,
        event_writer: DomainEventWriter,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._event_writer = event_writer
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create(
        self,
        session: Session,
        *,
        notification_type: str,
        resource_id: uuid.UUID | None,
        error_code: str | None,
        dedupe_key: str,
    ) -> Notification:
        existing = session.scalar(
            select(Notification).where(Notification.dedupe_key == dedupe_key)
        )
        if existing is not None:
            self._validate_existing(
                existing,
                notification_type=notification_type,
                resource_id=resource_id,
                error_code=error_code,
            )
            return existing
        current = self._utc_now()
        notification = Notification(
            id=uuid.uuid4(),
            type=notification_type,
            resource_id=resource_id,
            error_code=error_code,
            dedupe_key=dedupe_key,
            created_at=current,
            read_at=None,
        )
        try:
            with session.begin_nested():
                session.add(notification)
                session.flush([notification])
        except IntegrityError:
            existing = session.scalar(
                select(Notification).where(Notification.dedupe_key == dedupe_key)
            )
            if existing is None:
                raise
            self._validate_existing(
                existing,
                notification_type=notification_type,
                resource_id=resource_id,
                error_code=error_code,
            )
            return existing
        self._event_writer.append(
            session,
            stream="notification",
            aggregate_id=notification.id,
            event_type="notification.created.v1",
            payload=notification_payload(notification),
        )
        return notification

    @staticmethod
    def _validate_existing(
        notification: Notification,
        *,
        notification_type: str,
        resource_id: uuid.UUID | None,
        error_code: str | None,
    ) -> None:
        if (
            notification.type != notification_type
            or notification.resource_id != resource_id
            or notification.error_code != error_code
        ):
            raise ValueError("notification dedupe conflict")

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("notification clock must be timezone-aware")
        return current.astimezone(timezone.utc)


class NotificationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        event_writer: DomainEventWriter | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._event_writer = event_writer or DomainEventWriter(now=now)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def mark_read(self, notification_id: uuid.UUID) -> NotificationView:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            notification = session.get(
                Notification,
                notification_id,
                with_for_update=True,
            )
            if notification is None:
                raise NotificationProblem
            if notification.read_at is None:
                notification.read_at = current
                self._event_writer.append(
                    session,
                    stream="notification",
                    aggregate_id=notification.id,
                    event_type="notification.read.v1",
                    payload=notification_payload(notification),
                )
            return notification_view(notification)

    def prune_expired(self) -> int:
        cutoff = self._utc_now() - NOTIFICATION_RETENTION
        with self._session_factory.begin() as session:
            result = session.execute(
                delete(Notification).where(Notification.created_at <= cutoff)
            )
        return int(result.rowcount or 0)

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("notification clock must be timezone-aware")
        return current.astimezone(timezone.utc)


class NotificationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    resource_id: uuid.UUID | None
    error_code: str | None
    created_at: datetime
    read_at: datetime | None


def create_notification_api(
    service: NotificationService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/notifications",
        tags=["Events"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.put("/{notification_id}/read", response_model=NotificationOutput)
    def mark_notification_read(notification_id: uuid.UUID) -> NotificationView:
        try:
            return service.mark_read(notification_id)
        except NotificationProblem:
            raise ApiProblem(
                status_code=404,
                code="notification_not_found",
                message="notification not found",
            ) from None

    return router


def notification_payload(notification: Notification) -> dict[str, object]:
    return {
        "id": str(notification.id),
        "type": notification.type,
        "resource_id": (
            str(notification.resource_id)
            if notification.resource_id is not None
            else None
        ),
        "error_code": notification.error_code,
        "created_at": _utc_iso(notification.created_at),
        "read_at": _utc_iso(notification.read_at),
    }


def notification_view(notification: Notification) -> NotificationView:
    created_at = _as_utc(notification.created_at)
    assert created_at is not None
    return NotificationView(
        id=notification.id,
        type=notification.type,
        resource_id=notification.resource_id,
        error_code=notification.error_code,
        created_at=created_at,
        read_at=_as_utc(notification.read_at),
    )


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "NOTIFICATION_RETENTION",
    "NotificationOutput",
    "NotificationProblem",
    "NotificationService",
    "NotificationView",
    "NotificationWriter",
    "create_notification_api",
    "notification_payload",
    "notification_view",
]
