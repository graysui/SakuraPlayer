from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.events.outbox import DomainEventWriter, EventLog
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


def test_authenticated_snapshot_is_bounded_and_websocket_resumes() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    writer = DomainEventWriter(now=lambda: NOW)
    current_time = [NOW]
    event_log = EventLog(factory, now=lambda: current_time[0])
    queue = MetadataQueue(factory, now=lambda: NOW, event_writer=writer)
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        event_snapshot_service=EventSnapshotService(factory, event_log),
        event_log=event_log,
    )
    try:
        with TestClient(app) as client:
            headers = _auth_headers(client)
            assert client.get("/api/v1/events/snapshot").status_code == 401
            for index in range(105):
                movie = Movie(
                    id=uuid.uuid4(),
                    normalized_number=f"EVENT-{index:03d}",
                    raw_numbers=[f"EVENT-{index:03d}"],
                    catalog_state="raw_only",
                    created_at=NOW,
                    updated_at=NOW,
                )
                with factory.begin() as session:
                    session.add(movie)
                queue.enqueue(
                    movie_id=movie.id,
                    normalized_number=movie.normalized_number,
                    sort_date=None,
                    reason="daily",
                )
            events = event_log.read_after(None)

            snapshot = client.get("/api/v1/events/snapshot", headers=headers)
            assert snapshot.status_code == 200
            assert snapshot.headers["Cache-Control"] == "no-store"
            body = snapshot.json()
            assert body["snapshot_version"] == 105
            assert body["queues"]["metadata_queued"] == 105
            assert len(body["metadata_jobs"]) == 100
            assert body["cache_jobs"] == []
            assert body["cloud115_binding"]["status"] == "unbound"

            with client.websocket_connect(
                f"/api/v1/events/ws?after_event_id={events[0].event_id}",
                headers=headers,
            ) as websocket:
                first = websocket.receive_json()
                assert first["event_id"] == str(events[1].event_id)
                assert first["sequence"] == 2

            with pytest.raises(WebSocketDisconnect) as anonymous:
                with client.websocket_connect("/api/v1/events/ws"):
                    pass
            assert anonymous.value.code == 4401

            current_time[0] = NOW + timedelta(days=31)
            expired_snapshot = client.get(
                "/api/v1/events/snapshot", headers=headers
            ).json()
            assert expired_snapshot["snapshot_version"] == 105
            assert expired_snapshot["last_event_id"] is None
            with pytest.raises(WebSocketDisconnect) as expired:
                with client.websocket_connect(
                    f"/api/v1/events/ws?after_event_id={events[0].event_id}",
                    headers=headers,
                ) as websocket:
                    websocket.receive_json()
            assert expired.value.code == 4409

            logout = client.post("/api/v1/auth/logout", headers=headers)
            assert logout.status_code == 204
            with pytest.raises(WebSocketDisconnect) as revoked:
                with client.websocket_connect(
                    "/api/v1/events/ws",
                    headers=headers,
                ):
                    pass
            assert revoked.value.code == 4403
    finally:
        engine.dispose()


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
