from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from sakuraplayer.cloud_cache.ports.cloud115 import (
    QrLoginResult,
    QrSession,
    QrStatus,
    QrToken,
)
from sakuraplayer.cloud_cache.qr_service import QrSessionProblem, QrSessionService
from tests.fakes.cloud115 import FakeCloud115


def _factory(fake: FakeCloud115):
    @asynccontextmanager
    async def create(_cookies: str | None):
        yield fake

    return create


@pytest.mark.asyncio
async def test_qr_session_create_poll_confirm_and_consume() -> None:
    token = QrToken(uid="private-upstream-token", time=1, sign="private-sign")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token, b"PNG-private")],
        qr_statuses=[QrStatus.SCANNED, QrStatus.CONFIRMED],
        qr_results=[QrLoginResult("account-private", "UID=private-cookie")],
    )
    service = QrSessionService(
        _factory(fake),
        now=lambda: datetime(2026, 7, 27, tzinfo=timezone.utc),
    )

    created = await service.create()
    assert created.status == "waiting"
    assert created.image_png == b"PNG-private"
    assert created.id != uuid.UUID(int=0)
    assert "private-upstream-token" not in repr(created)

    scanned = await service.poll(created.id)
    assert scanned.status == "scanned"
    assert scanned.image_png is None

    saved: list[QrLoginResult] = []

    async def save(result: QrLoginResult) -> str:
        saved.append(result)
        return "bound"

    assert await service.confirm(created.id, save) == "bound"
    assert saved[0].account_key == "account-private"
    with pytest.raises(QrSessionProblem) as consumed:
        await service.confirm(created.id, save)
    assert consumed.value.code == "cloud115_qr_session_consumed"
    assert "private-upstream-token" not in repr(fake.calls)
    assert "private-cookie" not in repr(fake.calls)


@pytest.mark.asyncio
async def test_qr_local_expiry_does_not_call_upstream() -> None:
    current = datetime(2026, 7, 27, tzinfo=timezone.utc)
    fake = FakeCloud115(
        qr_sessions=[QrSession(QrToken(uid="uid", time=1, sign="sign"), b"PNG")]
    )
    service = QrSessionService(
        _factory(fake), now=lambda: current, ttl=timedelta(seconds=1)
    )
    created = await service.create()
    current += timedelta(seconds=2)

    expired = await service.poll(created.id)
    assert expired.status == "expired"
    assert [call.operation for call in fake.calls] == ["create_qr_session"]


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [QrStatus.EXPIRED, QrStatus.CANCELED])
async def test_upstream_terminal_state_destroys_token_and_png(
    terminal: QrStatus,
) -> None:
    token = QrToken(uid="uid-private", time=1, sign="sign-private")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token, b"PNG-private")],
        qr_statuses=[terminal],
    )
    service = QrSessionService(_factory(fake))
    created = await service.create()

    terminal_view = await service.poll(created.id)
    assert terminal_view.status == terminal.value
    assert terminal_view.image_png is None
    assert "uid-private" not in repr(service)
    assert "PNG-private" not in repr(service)


@pytest.mark.asyncio
async def test_qr_capacity_and_not_found_are_stable() -> None:
    token = QrToken(uid="uid", time=1, sign="sign")
    fake = FakeCloud115(qr_sessions=[QrSession(token, b"PNG")])
    service = QrSessionService(_factory(fake), capacity=1)
    await service.create()

    with pytest.raises(QrSessionProblem) as capacity:
        await service.create()
    assert capacity.value.code == "cloud115_qr_session_capacity"
    assert capacity.value.status_code == 429

    with pytest.raises(QrSessionProblem) as missing:
        await service.poll(uuid.uuid4())
    assert missing.value.code == "cloud115_qr_session_not_found"
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_create_purges_expired_record_and_destroys_sensitive_material() -> None:
    current = datetime(2026, 7, 27, tzinfo=timezone.utc)
    fakes = iter(
        [
            FakeCloud115(
                qr_sessions=[
                    QrSession(
                        QrToken(uid="expired-private", time=1, sign="sign-private"),
                        b"PNG-private",
                    )
                ]
            ),
            FakeCloud115(
                qr_sessions=[QrSession(QrToken(uid="new", time=2, sign="new"), b"PNG")]
            ),
        ]
    )

    @asynccontextmanager
    async def factory(_cookies: str | None):
        yield next(fakes)

    service = QrSessionService(
        factory, now=lambda: current, ttl=timedelta(seconds=1), capacity=1
    )
    await service.create()
    current += timedelta(seconds=2)

    await service.create()

    assert "expired-private" not in repr(service)
    assert "PNG-private" not in repr(service)


@pytest.mark.asyncio
async def test_qr_confirm_requires_confirmed_upstream_state() -> None:
    token = QrToken(uid="uid", time=1, sign="sign")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token, b"PNG")],
        qr_statuses=[QrStatus.WAITING],
    )
    service = QrSessionService(_factory(fake))
    created = await service.create()

    async def save(_result: QrLoginResult) -> None:
        raise AssertionError("save must not run")

    with pytest.raises(QrSessionProblem) as pending:
        await service.confirm(created.id, save)
    assert pending.value.code == "cloud115_qr_session_not_confirmed"


@pytest.mark.asyncio
async def test_qr_finish_result_is_reused_when_local_binding_retry_is_needed() -> None:
    token = QrToken(uid="uid-private", time=1, sign="sign-private")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token, b"PNG")],
        qr_statuses=[QrStatus.CONFIRMED],
        qr_results=[QrLoginResult("account-private", "UID=private-cookie")],
    )
    service = QrSessionService(_factory(fake))
    created = await service.create()
    attempts = 0

    async def save(_result: QrLoginResult) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("local_binding_failed")
        return "bound"

    with pytest.raises(RuntimeError, match="local_binding_failed"):
        await service.confirm(created.id, save)
    assert await service.confirm(created.id, save) == "bound"
    assert [call.operation for call in fake.calls] == [
        "create_qr_session",
        "poll_qr_session",
        "finish_qr_session",
    ]
    assert "private-cookie" not in repr(service)


@pytest.mark.asyncio
async def test_cached_login_result_is_destroyed_at_local_expiry() -> None:
    current = datetime(2026, 7, 27, tzinfo=timezone.utc)
    token = QrToken(uid="uid-private", time=1, sign="sign-private")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token, b"PNG")],
        qr_statuses=[QrStatus.CONFIRMED],
        qr_results=[QrLoginResult("account-private", "UID=private-cookie")],
    )
    service = QrSessionService(
        _factory(fake), now=lambda: current, ttl=timedelta(seconds=1)
    )
    created = await service.create()

    async def fail_local(_result: QrLoginResult) -> None:
        raise RuntimeError("local_binding_failed")

    with pytest.raises(RuntimeError):
        await service.confirm(created.id, fail_local)
    current += timedelta(seconds=2)
    with pytest.raises(QrSessionProblem) as expired:
        await service.confirm(created.id, fail_local)
    assert expired.value.code == "cloud115_qr_session_not_confirmed"
    assert "private-cookie" not in repr(service)
