from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.api.app import create_app
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import CacheJob, Notification
from sakuraplayer.cloud_cache.notifications import (
    NotificationService,
    NotificationWriter,
)
from sakuraplayer.cloud_cache.snapshot import CacheSnapshotExtension
from sakuraplayer.events.outbox import DomainEventWriter, EventLog
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.models import PlaybackSession

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


def test_snapshot_recovers_unread_notification_and_read_is_idempotent() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    event_writer = DomainEventWriter(now=lambda: NOW)
    notification_writer = NotificationWriter(event_writer, now=lambda: NOW)
    notification_service = NotificationService(
        factory,
        event_writer=event_writer,
        now=lambda: NOW,
    )
    job = _ready_job()
    with factory.begin() as session:
        session.add(job)
        session.flush()
        CacheEventPublisher(event_writer, notification_writer).publish_cache(
            session,
            job,
            event_type="cache.job.ready.v1",
            notification_type="cache_ready",
        )
    with factory() as session:
        notification_id = session.scalar(select(Notification.id))
    assert notification_id is not None

    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    event_log = EventLog(factory)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        event_snapshot_service=EventSnapshotService(
            factory,
            event_log,
            extension=CacheSnapshotExtension(),
        ),
        event_log=event_log,
        notification_service=notification_service,
    )
    try:
        with TestClient(app) as client:
            headers = _auth_headers(client)
            snapshot = client.get("/api/v1/events/snapshot", headers=headers)
            assert snapshot.status_code == 200
            body = snapshot.json()
            assert body["queues"] == {
                "metadata_queued": 0,
                "metadata_running": 0,
                "cache_queued": 0,
                "cache_running": 0,
                "cache_ready": 1,
            }
            assert body["cache_jobs"][0]["status"] == "ready"
            assert [item["type"] for item in body["notifications"]] == ["cache_ready"]

            path = f"/api/v1/notifications/{notification_id}/read"
            assert client.put(path).status_code == 401
            first = client.put(path, headers=headers)
            repeated = client.put(path, headers=headers)
            assert first.status_code == repeated.status_code == 200
            assert first.json()["read_at"] == repeated.json()["read_at"]
            assert (
                client.get("/api/v1/events/snapshot", headers=headers).json()[
                    "notifications"
                ]
                == []
            )
        with factory() as session:
            assert session.scalar(select(func.count(PlaybackSession.id))) == 0
    finally:
        engine.dispose()


def _ready_job() -> CacheJob:
    return CacheJob(
        id=uuid.uuid4(),
        movie_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        status="ready",
        capacity_class="ready",
        account_key="snapshot-account",
        cache_root_cid="snapshot-root",
        task_dir_cid="snapshot-task-cid",
        task_dir_name="snapshot-task",
        remote_percent=100,
        ready_at=NOW,
        last_accessed_at=NOW,
        expires_at=NOW + timedelta(hours=24),
        created_at=NOW,
        updated_at=NOW,
    )


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN.decode("ascii")},
        json={
            "username": "admin",
            "password": "correct horse battery staple",
            "client_instance_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
