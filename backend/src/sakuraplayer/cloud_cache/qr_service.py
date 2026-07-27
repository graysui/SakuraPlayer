from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, TypeVar

from sakuraplayer.cloud_cache.binding_service import Cloud115ScopeFactory
from sakuraplayer.cloud_cache.ports.cloud115 import QrLoginResult, QrStatus, QrToken

T = TypeVar("T")
QrSessionStatus = Literal["waiting", "scanned", "confirmed", "expired", "canceled"]


class QrSessionProblem(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class QrSessionView:
    id: uuid.UUID
    status: QrSessionStatus
    expires_at: datetime
    image_png: bytes | None = field(default=None, repr=False)


@dataclass(slots=True)
class _QrRecord:
    id: uuid.UUID
    token: QrToken | None = field(repr=False)
    image_png: bytes = field(repr=False)
    status: QrStatus
    expires_at: datetime
    consumed: bool
    operation_lock: asyncio.Lock
    login_result: QrLoginResult | None = field(default=None, repr=False)


class QrSessionService:
    def __init__(
        self,
        cloud_factory: Cloud115ScopeFactory,
        *,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = timedelta(minutes=5),
        capacity: int = 8,
    ) -> None:
        if ttl <= timedelta(0) or capacity < 1:
            raise ValueError("QR ttl and capacity must be positive")
        self._cloud_factory = cloud_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._ttl = ttl
        self._capacity = capacity
        self._records: dict[uuid.UUID, _QrRecord] = {}
        self._store_lock = asyncio.Lock()
        self._pending_creates = 0

    async def create(self) -> QrSessionView:
        reservation_released = False
        async with self._store_lock:
            self._purge_expired()
            if len(self._records) + self._pending_creates >= self._capacity:
                raise QrSessionProblem("cloud115_qr_session_capacity", 429)
            self._pending_creates += 1
        try:
            async with self._cloud_factory(None) as cloud:
                upstream = await cloud.create_qr_session()
        except BaseException:
            async with self._store_lock:
                self._pending_creates -= 1
            raise
        current = self._now()
        record = _QrRecord(
            id=uuid.uuid4(),
            token=upstream.token,
            image_png=upstream.image_png,
            status=QrStatus.WAITING,
            expires_at=current + self._ttl,
            consumed=False,
            operation_lock=asyncio.Lock(),
        )
        try:
            async with self._store_lock:
                self._pending_creates -= 1
                reservation_released = True
                self._purge_expired()
                self._records[record.id] = record
        except BaseException:
            async with self._store_lock:
                if not reservation_released:
                    self._pending_creates -= 1
            raise
        return self._view(record, include_image=True)

    async def poll(self, session_id: uuid.UUID) -> QrSessionView:
        record = await self._get(session_id)
        async with record.operation_lock:
            if record.consumed:
                return self._view(record)
            if self._is_locally_expired(record):
                self._expire(record)
                return self._view(record)
            if record.status in {QrStatus.EXPIRED, QrStatus.CANCELED}:
                return self._view(record)
            token = self._token(record)
            async with self._cloud_factory(None) as cloud:
                record.status = await cloud.poll_qr_session(token)
            if record.status in {QrStatus.EXPIRED, QrStatus.CANCELED}:
                self._discard_sensitive(record)
            return self._view(record)

    async def confirm(
        self,
        session_id: uuid.UUID,
        save: Callable[[QrLoginResult], Awaitable[T]],
    ) -> T:
        record = await self._get(session_id)
        async with record.operation_lock:
            if record.consumed:
                raise QrSessionProblem("cloud115_qr_session_consumed", 409)
            if self._is_locally_expired(record):
                self._expire(record)
                raise QrSessionProblem("cloud115_qr_session_not_confirmed", 409)
            if record.login_result is not None:
                result = record.login_result
            elif record.status not in {QrStatus.EXPIRED, QrStatus.CANCELED}:
                token = self._token(record)
                async with self._cloud_factory(None) as cloud:
                    record.status = await cloud.poll_qr_session(token)
                    if record.status != QrStatus.CONFIRMED:
                        if record.status in {QrStatus.EXPIRED, QrStatus.CANCELED}:
                            self._discard_sensitive(record)
                        raise QrSessionProblem("cloud115_qr_session_not_confirmed", 409)
                    result = await cloud.finish_qr_session(token)
                    record.login_result = result
            else:
                raise QrSessionProblem("cloud115_qr_session_not_confirmed", 409)
            saved = await save(result)
            record.consumed = True
            record.token = None
            record.image_png = b""
            record.login_result = None
            return saved

    async def _get(self, session_id: uuid.UUID) -> _QrRecord:
        async with self._store_lock:
            record = self._records.get(session_id)
        if record is None:
            raise QrSessionProblem("cloud115_qr_session_not_found", 404)
        return record

    def _purge_expired(self) -> None:
        current = self._now()
        for record in self._records.values():
            if record.expires_at <= current:
                self._expire(record)
        self._records = {
            key: record
            for key, record in self._records.items()
            if record.expires_at > current
        }

    def _is_locally_expired(self, record: _QrRecord) -> bool:
        return record.expires_at <= self._now()

    @staticmethod
    def _expire(record: _QrRecord) -> None:
        record.status = QrStatus.EXPIRED
        QrSessionService._discard_sensitive(record)

    @staticmethod
    def _discard_sensitive(record: _QrRecord) -> None:
        record.token = None
        record.image_png = b""
        record.login_result = None

    @staticmethod
    def _token(record: _QrRecord) -> QrToken:
        if record.token is None:
            raise QrSessionProblem("cloud115_qr_session_consumed", 409)
        return record.token

    @staticmethod
    def _view(record: _QrRecord, *, include_image: bool = False) -> QrSessionView:
        return QrSessionView(
            id=record.id,
            status=record.status.value,
            expires_at=record.expires_at,
            image_png=record.image_png if include_image else None,
        )


__all__ = ["QrSessionProblem", "QrSessionService", "QrSessionView"]
