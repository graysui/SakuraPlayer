from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI

from sakuraplayer.cloud_cache.models import RemoteSubtitle
from sakuraplayer.playback.subtitle_api import create_subtitle_api
from sakuraplayer.playback.subtitle_lifecycle import (
    CACHE_CLEANED_EVENT,
    create_subtitle_lifecycle,
)
from sakuraplayer.playback.subtitles import (
    SubtitleProblem,
    subtitle_download_filename,
    subtitle_media_type,
)

NOW = datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("extension", "media_type"),
    [
        ("srt", "application/x-subrip"),
        ("ass", "text/x-ssa"),
        ("ssa", "text/x-ssa"),
        ("vtt", "text/vtt"),
    ],
)
def test_subtitle_mime_and_safe_filename(extension: str, media_type: str) -> None:
    subtitle_id = uuid.uuid4()

    assert subtitle_media_type(extension) == media_type
    assert subtitle_download_filename(subtitle_id, extension) == (
        f"{subtitle_id}.{extension}"
    )


def test_unsupported_subtitle_format_has_stable_error() -> None:
    with pytest.raises(SubtitleProblem) as raised:
        subtitle_media_type("txt")

    assert raised.value.status_code == 422
    assert raised.value.code == "subtitle_format_unsupported"


def test_lifecycle_maps_only_its_cache_job_and_local_expiry() -> None:
    cache_job_id = uuid.uuid4()
    expires_at = NOW + timedelta(hours=12)
    lifecycle = create_subtitle_lifecycle(
        cache_job_id=cache_job_id, session_expires_at=expires_at
    )

    assert lifecycle.embedded_tracks_source == "client_player"
    assert lifecycle.is_expired(now=expires_at)
    assert not lifecycle.is_expired(now=expires_at - timedelta(microseconds=1))
    assert lifecycle.matches_cache_event(
        event_type=CACHE_CLEANED_EVENT, resource_id=cache_job_id
    )
    assert not lifecycle.matches_cache_event(
        event_type=CACHE_CLEANED_EVENT, resource_id=uuid.uuid4()
    )
    assert not lifecycle.matches_cache_event(
        event_type="cache.job.failed.v1", resource_id=cache_job_id
    )


def test_remote_subtitle_metadata_has_no_body_or_client_path_columns() -> None:
    columns = set(RemoteSubtitle.__table__.columns.keys())

    assert columns == {
        "id",
        "cache_job_id",
        "media_id",
        "file_id",
        "pickcode",
        "parent_cid",
        "name",
        "extension",
        "size_bytes",
        "match_score",
        "match_evidence",
        "created_at",
    }


def test_actual_openapi_declares_binary_subtitle_response() -> None:
    app = FastAPI()
    app.include_router(
        create_subtitle_api(
            object(),  # type: ignore[arg-type]
            current_admin_dependency=lambda: None,
        )
    )

    operation = app.openapi()["paths"][
        "/api/v1/playback/sessions/{playback_session_id}/subtitles/{subtitle_id}"
    ]["get"]
    success = operation["responses"]["200"]

    assert operation["operationId"] == "downloadSubtitle"
    assert set(success["content"]) == {
        "application/x-subrip",
        "text/vtt",
        "text/x-ssa",
    }
    assert "application/json" not in success["content"]
    assert success["headers"]["X-Content-Type-Options"]["schema"]["const"] == (
        "nosniff"
    )
    assert set(operation["responses"]) == {
        "200",
        "401",
        "404",
        "413",
        "422",
        "429",
        "502",
        "503",
    }
    for status in ("401", "404", "413", "422", "429", "502", "503"):
        schema = operation["responses"][status]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ApiError"}
