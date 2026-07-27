from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from typing import cast

import pytest

from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Port,
    Cloud115Problem,
    CloudCredentialStatus,
    CredentialProbe,
    DirectoryBreadcrumb,
    DirectoryInfo,
    OfflineStatus,
    OfflineSubmission,
    OfflineTaskPage,
    OfflineTaskSnapshot,
    OriginalUrl,
    QrSession,
    QrStatus,
    QrToken,
    RemoteDirectory,
    RemoteFile,
)
from tests.fakes.cloud115 import FakeCloud115


def test_dtos_are_frozen_and_offline_snapshot_has_no_source_payload() -> None:
    token = QrToken(uid="qr-1", time=123, sign="signature")
    with pytest.raises(FrozenInstanceError):
        token.uid = "changed"  # type: ignore[misc]

    names = {field.name for field in fields(OfflineTaskSnapshot)}
    assert "magnet" not in names
    assert "url" not in names
    assert "source_url" not in names
    assert "raw_response" not in names


def test_problem_only_retains_stable_safe_fields() -> None:
    problem = Cloud115Problem("cloud115_rate_limited", retry_after_seconds=7)

    assert str(problem) == "cloud115_rate_limited"
    assert problem.code == "cloud115_rate_limited"
    assert problem.retry_after_seconds == 7
    assert vars(problem) == {
        "code": "cloud115_rate_limited",
        "retry_after_seconds": 7,
    }

    with pytest.raises(ValueError):
        Cloud115Problem("Cloud URL https://example.invalid/?token=secret")
    with pytest.raises(ValueError):
        Cloud115Problem("cloud115_rate_limited", retry_after_seconds=-1)


@pytest.mark.asyncio
async def test_fake_implements_protocol_and_consumes_scripted_results() -> None:
    token = QrToken(uid="qr-1", time=123, sign="signature")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token=token, image_png=b"\x89PNG\r\n")],
        qr_statuses=[QrStatus.WAITING, QrStatus.CONFIRMED],
        credential_probes=[
            CredentialProbe(
                status=CloudCredentialStatus.ALIVE,
                cookie_snapshot="UID=updated",
            )
        ],
        directories=[RemoteDirectory(cid="10", parent_cid="0", name="cache")],
        offline_submissions=[OfflineSubmission(info_hash="a" * 40)],
        offline_pages=[
            OfflineTaskPage(
                page=1,
                page_count=1,
                page_size=100,
                total_tasks=1,
                tasks=(
                    OfflineTaskSnapshot(
                        info_hash="a" * 40,
                        name="task",
                        size_bytes=1,
                        status=OfflineStatus.RUNNING,
                        percent_done=25.0,
                        task_cid="11",
                    ),
                ),
            )
        ],
        credential_snapshot="UID=updated",
    )
    assert isinstance(fake, Cloud115Port)
    port = cast(Cloud115Port, fake)

    assert (await port.create_qr_session()).token == token
    assert await port.poll_qr_session(token) is QrStatus.WAITING
    assert await port.poll_qr_session(token) is QrStatus.CONFIRMED
    assert (await port.probe_credentials()).cookie_snapshot == "UID=updated"
    assert port.credential_snapshot() == "UID=updated"
    assert (await port.find_or_create_directory("0", "cache")).cid == "10"
    assert (await port.submit_offline("magnet:?xt=urn:btih:secret", "11")).info_hash
    assert (await port.list_offline_tasks()).tasks[0].status is OfflineStatus.RUNNING

    submit_call = fake.calls[-2]
    assert submit_call.operation == "submit_offline"
    assert "magnet:" not in repr(submit_call)
    assert "secret" not in repr(submit_call)


@pytest.mark.asyncio
async def test_fake_can_script_stable_failures() -> None:
    fake = FakeCloud115(credential_probes=[Cloud115Problem("cloud115_unavailable")])

    with pytest.raises(Cloud115Problem) as raised:
        await fake.probe_credentials()
    assert raised.value.code == "cloud115_unavailable"


@pytest.mark.asyncio
async def test_fake_orchestrates_media_move_concurrent_url_and_cleanup_failure() -> (
    None
):
    original = OriginalUrl(
        url="https://cdn.115.com/video?t=1893456000",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        file_id="video-1",
        file_name="movie.mkv",
        file_size_bytes=1024,
        sha1="ABC",
        pickcode="pick",
        user_agent="SakuraPlayer-Test/1",
    )
    files = (
        RemoteFile(
            file_id="video-1",
            parent_cid="task-1",
            name="movie.mkv",
            size_bytes=1024,
            pickcode="pick",
            sha1="ABC",
            is_directory=False,
            is_video=True,
        ),
        RemoteFile(
            file_id="subtitle-1",
            parent_cid="task-1",
            name="movie.ass",
            size_bytes=64,
            pickcode="subtitle-pick",
            sha1="DEF",
            is_directory=False,
            is_video=False,
        ),
    )
    fake = FakeCloud115(
        directory_infos=[
            DirectoryInfo(
                cid="task-1",
                parent_cid="moved-root",
                name="task",
                path=(DirectoryBreadcrumb("moved-root", "cache"),),
            )
        ],
        file_batches=[files],
        original_urls=[original] * 5,
        delete_results=[Cloud115Problem("cloud115_unavailable")],
    )

    moved = await fake.directory_info("task-1")
    assert moved.parent_cid == "moved-root"
    assert [item async for item in fake.list_files_recursive("task-1")] == list(files)
    urls = await asyncio.gather(
        *(fake.resolve_original("pick", "SakuraPlayer-Test/1") for _ in range(5))
    )
    assert all(item.url == original.url for item in urls)
    assert original.url not in repr(fake.calls)
    with pytest.raises(Cloud115Problem) as cleanup:
        await fake.delete_managed_entries(("video-1",), "task-1")
    assert cleanup.value.code == "cloud115_unavailable"
