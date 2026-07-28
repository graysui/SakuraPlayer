from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.identity.models import AdminUser, Base
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession
from sakuraplayer.playback.session import PlaybackProblem, PlaybackSessionService
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from sakuraplayer.resources.models import ResourceSource  # noqa: F401

NOW = datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)


def test_signatures_bind_session_epoch_user_agent_and_expiry() -> None:
    factory, admin, job_id, media_ids = _context()
    service = PlaybackSessionService(
        factory,
        signing_key=b"p" * 32,
        now=lambda: NOW,
    )
    manifest = service.create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="original",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )

    assert manifest.required_user_agent == WINDOWS_USER_AGENT
    assert [item.media.id for item in manifest.media_queue] == media_ids
    assert len({item.session_id for item in manifest.media_queue}) == 2
    assert manifest.expires_at == NOW + timedelta(hours=12)

    parsed = urlparse(manifest.stream_url)
    query = parse_qs(parsed.query)
    context = service.validate_stream(
        playback_session_id=manifest.session_id,
        expires=int(query["expires"][0]),
        signature=query["signature"][0],
        user_agent=WINDOWS_USER_AGENT,
    )
    assert context.pickcode == "pickcode-0"

    with pytest.raises(PlaybackProblem, match="playback_signature_invalid"):
        service.validate_stream(
            playback_session_id=manifest.session_id,
            expires=int(query["expires"][0]),
            signature="0" * 64,
            user_agent=WINDOWS_USER_AGENT,
        )
    with pytest.raises(PlaybackProblem, match="playback_user_agent_mismatch"):
        service.validate_stream(
            playback_session_id=manifest.session_id,
            expires=int(query["expires"][0]),
            signature=query["signature"][0],
            user_agent="wrong-user-agent",
        )
    with factory.begin() as session:
        stored = session.get(AdminUser, admin.admin_id)
        assert stored is not None
        stored.session_epoch += 1
    with pytest.raises(PlaybackProblem, match="playback_session_revoked"):
        service.validate_stream(
            playback_session_id=manifest.session_id,
            expires=int(query["expires"][0]),
            signature=query["signature"][0],
            user_agent=WINDOWS_USER_AGENT,
        )


def test_each_click_creates_new_sessions_and_refreshes_cache_ttl() -> None:
    factory, admin, job_id, media_ids = _context()
    service = PlaybackSessionService(
        factory,
        signing_key=b"p" * 32,
        now=lambda: NOW,
        ttl_hours=lambda: 48,
    )
    first = service.create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="original",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )
    second = service.create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="original",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )

    assert first.session_id != second.session_id
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        assert _as_utc(job.last_accessed_at) == NOW
        assert _as_utc(job.expires_at) == NOW + timedelta(hours=48)


def test_manifest_limits_subtitles_to_selected_media_and_declares_track_source() -> (
    None
):
    factory, admin, job_id, media_ids = _context()
    unselected_media_id = uuid.uuid4()
    selected_subtitle_id = uuid.uuid4()
    global_subtitle_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            RemoteMedia(
                id=unselected_media_id,
                cache_job_id=job_id,
                file_id="unselected-file",
                pickcode="unselected-pickcode",
                parent_cid="task",
                name="other.mkv",
                size_bytes=300_000_000,
                duration_seconds=1200,
                candidate_id=uuid.uuid4(),
                sequence_no=0,
                selection_score=90,
                selection_evidence=[],
                is_valid=True,
                created_at=NOW,
            )
        )
        for subtitle in (
            RemoteSubtitle(
                id=selected_subtitle_id,
                cache_job_id=job_id,
                media_id=media_ids[0],
                file_id="subtitle-selected",
                pickcode="subtitle-pick-selected",
                parent_cid="task",
                name="movie.part1.srt",
                extension="srt",
                size_bytes=128,
                match_score=110,
                match_evidence=["exact_stem"],
                created_at=NOW,
            ),
            RemoteSubtitle(
                id=global_subtitle_id,
                cache_job_id=job_id,
                media_id=None,
                file_id="subtitle-global",
                pickcode="subtitle-pick-global",
                parent_cid="task",
                name="global.ass",
                extension="ass",
                size_bytes=256,
                match_score=0,
                match_evidence=[],
                created_at=NOW,
            ),
            RemoteSubtitle(
                id=uuid.uuid4(),
                cache_job_id=job_id,
                media_id=unselected_media_id,
                file_id="subtitle-unselected",
                pickcode="subtitle-pick-unselected",
                parent_cid="task",
                name="other.vtt",
                extension="vtt",
                size_bytes=64,
                match_score=110,
                match_evidence=["exact_stem"],
                created_at=NOW,
            ),
        ):
            session.add(subtitle)

    manifest = PlaybackSessionService(
        factory, signing_key=b"p" * 32, now=lambda: NOW
    ).create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="original",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )

    assert manifest.cache_job_id == job_id
    assert manifest.embedded_tracks_source == "client_player"
    assert manifest.subtitle_cache_expires_at == manifest.expires_at
    assert [
        (item.id, item.media_id, item.selected_by_default)
        for item in manifest.subtitles
    ] == [
        (selected_subtitle_id, media_ids[0], True),
        (global_subtitle_id, None, False),
    ]


def test_compatibility_creates_new_sessions_with_signed_mode() -> None:
    factory, admin, job_id, media_ids = _context()
    service = PlaybackSessionService(factory, signing_key=b"p" * 32, now=lambda: NOW)

    original = service.create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="original",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )
    compatibility = service.create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="compatibility",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )

    assert original.session_id != compatibility.session_id
    assert compatibility.mode == "compatibility"
    with factory() as session:
        stored = session.get(PlaybackSession, compatibility.session_id)
        assert stored is not None
        assert stored.mode == "compatibility"


def test_create_rejects_non_selected_media_and_client_mismatch() -> None:
    factory, admin, job_id, _media_ids = _context()
    service = PlaybackSessionService(factory, signing_key=b"p" * 32, now=lambda: NOW)

    with pytest.raises(PlaybackProblem, match="state_conflict"):
        service.create(
            admin=admin,
            cache_job_id=job_id,
            media_id=uuid.uuid4(),
            mode="original",
            platform="windows",
            client_instance_id=admin.client_instance_id,
        )
    with pytest.raises(PlaybackProblem, match="validation_failed"):
        service.create(
            admin=admin,
            cache_job_id=job_id,
            media_id=_media_ids[0],
            mode="original",
            platform="windows",
            client_instance_id=uuid.uuid4(),
        )


@pytest.mark.parametrize("lease_state", ["missing", "ended", "expired"])
def test_stream_requires_an_active_lease(lease_state: str) -> None:
    factory, admin, job_id, media_ids = _context()
    service = PlaybackSessionService(factory, signing_key=b"p" * 32, now=lambda: NOW)
    manifest = service.create(
        admin=admin,
        cache_job_id=job_id,
        media_id=media_ids[0],
        mode="original",
        platform="windows",
        client_instance_id=admin.client_instance_id,
    )
    parsed = urlparse(manifest.stream_url)
    query = parse_qs(parsed.query)
    with factory.begin() as session:
        lease = session.scalar(
            select(PlaybackLease).where(
                PlaybackLease.playback_session_id == manifest.session_id
            )
        )
        assert lease is not None
        if lease_state == "missing":
            session.delete(lease)
        elif lease_state == "ended":
            lease.ended_at = NOW
        else:
            lease.last_heartbeat_at = NOW - timedelta(seconds=2)
            lease.expires_at = NOW - timedelta(seconds=1)

    with pytest.raises(PlaybackProblem, match="playback_media_detached"):
        service.validate_stream(
            playback_session_id=manifest.session_id,
            expires=int(query["expires"][0]),
            signature=query["signature"][0],
            user_agent=WINDOWS_USER_AGENT,
        )


def _context() -> tuple[sessionmaker, CurrentAdmin, uuid.UUID, list[uuid.UUID]]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    admin_id = uuid.uuid4()
    client_instance_id = uuid.uuid4()
    job_id = uuid.uuid4()
    media_ids = [uuid.uuid4(), uuid.uuid4()]
    with factory.begin() as session:
        session.add(
            AdminUser(
                id=admin_id,
                singleton_key=True,
                username="admin",
                password_hash="$argon2id$fixture",
                session_epoch=4,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            CacheJob(
                id=job_id,
                movie_id=uuid.uuid4(),
                source_id=uuid.uuid4(),
                binding_id=uuid.uuid4(),
                status="ready",
                capacity_class="ready",
                account_key="account",
                cache_root_cid="root",
                task_dir_cid="task",
                task_dir_name="cache-task",
                remote_percent=100,
                ready_at=NOW - timedelta(hours=1),
                last_accessed_at=NOW - timedelta(hours=1),
                expires_at=NOW + timedelta(hours=23),
                created_at=NOW - timedelta(hours=1),
                updated_at=NOW - timedelta(hours=1),
            )
        )
        for sequence_no, media_id in enumerate(media_ids):
            session.add(
                RemoteMedia(
                    id=media_id,
                    cache_job_id=job_id,
                    file_id=f"file-{sequence_no}",
                    pickcode=f"pickcode-{sequence_no}",
                    parent_cid="task",
                    name=f"movie.part{sequence_no + 1}.mkv",
                    size_bytes=300_000_000,
                    duration_seconds=1200,
                    candidate_id=uuid.uuid4(),
                    sequence_no=sequence_no,
                    selection_score=100,
                    selection_evidence=[],
                    is_valid=True,
                    created_at=NOW,
                )
            )
            session.add(
                CacheJobMediaSelection(
                    cache_job_id=job_id,
                    sequence_no=sequence_no,
                    media_id=media_id,
                )
            )
    return (
        factory,
        CurrentAdmin(
            admin_id=admin_id,
            username="admin",
            session_id=uuid.uuid4(),
            client_instance_id=client_instance_id,
            session_epoch=4,
        ),
        job_id,
        media_ids,
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)
