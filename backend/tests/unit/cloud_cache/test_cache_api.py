from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.cloud_cache.capacity import CacheCapacitySnapshot
from sakuraplayer.cloud_cache.media_selection_api import MediaSelectionResult
from sakuraplayer.cloud_cache.play_request import (
    CacheJobPage,
    CacheJobView,
    PlayRequestResult,
    RemoteMediaView,
    SubtitleView,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService

NOW = datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


class CacheServiceStub:
    def __init__(self) -> None:
        media_id = uuid.uuid4()
        self.job = CacheJobView(
            id=uuid.uuid4(),
            movie_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            status="submitting",
            remote_percent=0,
            ready_at=None,
            last_accessed_at=None,
            expires_at=None,
            failure_code=None,
            created_at=NOW,
            updated_at=NOW,
            media_candidates=(
                RemoteMediaView(
                    id=media_id,
                    candidate_id=uuid.uuid4(),
                    name="movie.mkv",
                    size_bytes=1_000_000_000,
                    duration_seconds=3600,
                    sequence_no=0,
                    is_valid=True,
                ),
            ),
            selected_media_ids=(media_id,),
            subtitles=(
                SubtitleView(
                    id=uuid.uuid4(),
                    name="movie.ass",
                    format="ass",
                    language=None,
                    selected_by_default=True,
                ),
            ),
        )
        self.create_calls = 0

    def create(self, *, movie_id, source_id, idempotency_key):
        self.create_calls += 1
        assert movie_id == self.job.movie_id
        assert source_id == self.job.source_id
        assert idempotency_key == "request-key-0001"
        return PlayRequestResult(disposition="started", job=self.job)

    def get(self, job_id):
        assert job_id == self.job.id
        return self.job

    def list(self, *, statuses=(), cursor=None, limit=24):
        assert statuses == ("submitting",)
        assert cursor is None
        assert limit == 24
        return CacheJobPage(
            items=[self.job],
            capacity=CacheCapacitySnapshot(running=1, queued=0, ready=0),
            next_cursor=None,
        )

    def select_media(self, *, job_id, media_ids):
        assert job_id == self.job.id
        assert media_ids == self.job.selected_media_ids
        return MediaSelectionResult(status="ready", selected_media_ids=media_ids)


class CleanupServiceStub:
    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        self.calls = 0

    def request(self, job_id: uuid.UUID):
        assert job_id == self.job_id
        self.calls += 1
        return None


def test_cache_api_is_authenticated_strict_and_redacted(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    cache = CacheServiceStub()
    cleanup = CleanupServiceStub(cache.job.id)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        cache_service=cache,
        cache_cleanup_service=cleanup,  # type: ignore[arg-type]
    )
    schema = app.openapi()
    selection_path = schema["paths"][
        "/api/v1/cache-jobs/{cache_job_id}/media-selection"
    ]["put"]
    selection_schema = schema["components"]["schemas"]["MediaSelectionInput"]
    assert selection_path["security"] == [{"HTTPBearer": []}]
    assert selection_schema["additionalProperties"] is False
    assert selection_schema["properties"]["media_ids"] == {
        "items": {"type": "string", "format": "uuid"},
        "type": "array",
        "maxItems": 100,
        "minItems": 1,
        "uniqueItems": True,
        "title": "Media Ids",
    }
    assert schema["paths"]["/api/v1/cache-jobs/{cache_job_id}/cleanup"]["post"][
        "security"
    ] == [{"HTTPBearer": []}]
    try:
        with TestClient(app) as client:
            path = f"/api/v1/movies/{cache.job.movie_id}/play-requests"
            assert (
                client.post(
                    path, json={"source_id": str(cache.job.source_id)}
                ).status_code
                == 401
            )
            headers = _auth_headers(client)
            invalid = client.post(
                path,
                headers={**headers, "Idempotency-Key": "request-key-0001"},
                json={
                    "source_id": str(cache.job.source_id),
                    "magnet": "must-not-cross-api-boundary",
                },
            )
            created = client.post(
                path,
                headers={**headers, "Idempotency-Key": "request-key-0001"},
                json={"source_id": str(cache.job.source_id)},
            )
            listing = client.get(
                "/api/v1/cache-jobs?status=submitting",
                headers=headers,
            )
            detail = client.get(
                f"/api/v1/cache-jobs/{cache.job.id}",
                headers=headers,
            )
            unauthenticated_selection = client.put(
                f"/api/v1/cache-jobs/{cache.job.id}/media-selection",
                json={"media_ids": [str(cache.job.selected_media_ids[0])]},
            )
            invalid_selection = client.put(
                f"/api/v1/cache-jobs/{cache.job.id}/media-selection",
                headers=headers,
                json={
                    "media_ids": [str(cache.job.selected_media_ids[0])],
                    "candidate_id": str(uuid.uuid4()),
                },
            )
            duplicate_selection = client.put(
                f"/api/v1/cache-jobs/{cache.job.id}/media-selection",
                headers=headers,
                json={
                    "media_ids": [
                        str(cache.job.selected_media_ids[0]),
                        str(cache.job.selected_media_ids[0]),
                    ]
                },
            )
            selection = client.put(
                f"/api/v1/cache-jobs/{cache.job.id}/media-selection",
                headers=headers,
                json={"media_ids": [str(cache.job.selected_media_ids[0])]},
            )
            unauthenticated_cleanup = client.post(
                f"/api/v1/cache-jobs/{cache.job.id}/cleanup"
            )
            cleanup_response = client.post(
                f"/api/v1/cache-jobs/{cache.job.id}/cleanup",
                headers=headers,
            )
    finally:
        engine.dispose()

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_failed"
    assert cache.create_calls == 1
    assert unauthenticated_selection.status_code == 401
    assert invalid_selection.status_code == 422
    assert duplicate_selection.status_code == 422
    assert selection.status_code == 200
    assert unauthenticated_cleanup.status_code == 401
    assert cleanup_response.status_code == 202
    assert cleanup_response.headers["cache-control"] == "no-store"
    assert cleanup.calls == 1
    assert selection.json()["selected_media_ids"] == [
        str(cache.job.selected_media_ids[0])
    ]
    assert created.status_code == 202
    assert created.json()["disposition"] == "started"
    assert "wait_deadline" not in created.json()
    assert listing.json()["capacity"] == {
        "running": 1,
        "running_limit": 2,
        "queued": 0,
        "queued_limit": 10,
        "ready": 0,
        "ready_limit": 20,
    }
    for response in (created, listing, detail):
        assert response.status_code in {200, 202}
        assert response.headers["cache-control"] == "no-store"
        assert isinstance(response.json().get("media_candidates", []), list)
        assert "magnet" not in response.text
        assert "account_key" not in response.text
        assert "cache_root_cid" not in response.text
        assert "claim_token" not in response.text
    assert detail.json()["media_candidates"][0] == {
        "id": str(cache.job.media_candidates[0].id),
        "candidate_id": str(cache.job.media_candidates[0].candidate_id),
        "name": "movie.mkv",
        "size_bytes": 1_000_000_000,
        "duration_seconds": 3600,
        "sequence_no": 0,
        "is_valid": True,
    }
    assert detail.json()["subtitles"][0]["selected_by_default"] is True


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
