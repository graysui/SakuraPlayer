from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Port,
    Cloud115Problem,
    CloudCredentialStatus,
    CredentialProbe,
    HlsInfo,
    HlsVariant,
    OfflineStatus,
    OriginalUrl,
    RemoteFile,
)
from tests.fakes.cloud115_state import StatefulFakeCloud115

NOW = datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)


def test_stateful_fake_implements_port_and_tracks_directory_lifecycle() -> None:
    fake = StatefulFakeCloud115(cookie_snapshot="UID=private-cookie")
    assert isinstance(fake, Cloud115Port)
    fake.seed_directory("root-cid", "0", "SakuraPlayer-Cache")

    created = asyncio.run(fake.find_or_create_directory("root-cid", "cache-task-113"))
    assert fake.directory_exists(created.cid)
    assert asyncio.run(fake.directory_info(created.cid)).parent_cid == "root-cid"

    fake.move_directory(created.cid, "outside-cid")
    assert asyncio.run(fake.directory_info(created.cid)).parent_cid == "outside-cid"
    fake.move_directory(created.cid, "root-cid")
    asyncio.run(fake.delete_managed_entries((created.cid,), "root-cid"))
    assert not fake.directory_exists(created.cid)


def test_stateful_fake_advances_offline_and_recursive_file_state() -> None:
    fake = StatefulFakeCloud115()
    fake.seed_directory("root-cid", "0", "SakuraPlayer-Cache")
    fake.seed_directory("task-cid", "root-cid", "cache-task-113")
    submission = asyncio.run(
        fake.submit_offline("magnet:?xt=urn:btih:private", "task-cid")
    )
    assert fake.offline_task(submission.info_hash).status is OfflineStatus.QUEUED

    video = RemoteFile(
        file_id="video-id",
        parent_cid="task-cid",
        name="ABP-113.mp4",
        size_bytes=512 * 1024 * 1024,
        pickcode="video-pickcode",
        sha1="a" * 40,
        is_directory=False,
        is_video=True,
        duration_seconds=3600,
    )
    fake.seed_files("task-cid", (video,))
    fake.set_offline_status(
        submission.info_hash,
        OfflineStatus.COMPLETED,
        percent_done=100.0,
    )

    page = asyncio.run(fake.list_offline_tasks(page=1, page_size=1000))
    files = asyncio.run(_collect_files(fake, "task-cid"))
    assert page.tasks[0].status is OfflineStatus.COMPLETED
    assert page.tasks[0].task_cid == "task-cid"
    assert files == (video,)
    assert fake.file_exists("video-id")


def test_stateful_fake_injects_one_shot_faults_without_losing_state() -> None:
    fake = StatefulFakeCloud115()
    fake.seed_directory("root-cid", "0", "SakuraPlayer-Cache")
    fake.inject_fault(
        "directory_info",
        Cloud115Problem("cloud115_unavailable", retry_after_seconds=3),
    )

    with pytest.raises(Cloud115Problem) as failed:
        asyncio.run(fake.directory_info("root-cid"))
    assert failed.value.code == "cloud115_unavailable"
    assert asyncio.run(fake.directory_info("root-cid")).cid == "root-cid"


def test_stateful_fake_models_credential_and_accepted_uncertain_submission() -> None:
    fake = StatefulFakeCloud115(cookie_snapshot="UID=private-cookie")
    fake.seed_directory("task-cid", "0", "cache-task-113")
    fake.set_credential_probe(CredentialProbe(CloudCredentialStatus.EXPIRED, None))
    assert asyncio.run(fake.probe_credentials()).status is CloudCredentialStatus.EXPIRED
    fake.inject_post_fault(
        "submit_offline",
        Cloud115Problem("cloud115_submit_uncertain"),
    )

    with pytest.raises(Cloud115Problem) as uncertain:
        asyncio.run(fake.submit_offline("magnet:?xt=urn:btih:private", "task-cid"))
    assert uncertain.value.code == "cloud115_submit_uncertain"
    page = asyncio.run(fake.list_offline_tasks(page=1, page_size=1000))
    assert len(page.tasks) == 1
    assert page.tasks[0].task_cid == "task-cid"


def test_stateful_fake_keeps_secrets_and_capability_payloads_out_of_repr() -> None:
    cookie = "UID=private-cookie"
    magnet = "magnet:?xt=urn:btih:private"
    subtitle = b"private subtitle body"
    original_url = "https://video.115cdn.com/path?capability=private"
    hls_url = "https://video.115cdn.com/master.m3u8?capability=private"
    fake = StatefulFakeCloud115(cookie_snapshot=cookie)
    fake.seed_directory("task-cid", "0", "cache-task-113")
    fake.seed_original(
        OriginalUrl(
            url=original_url,
            expires_at=NOW,
            file_id="video-id",
            file_name="ABP-113.mp4",
            file_size_bytes=512 * 1024 * 1024,
            sha1="a" * 40,
            pickcode="video-pickcode",
            user_agent="SakuraPlayer/1.0 (Windows; x64)",
        )
    )
    fake.seed_hls(
        HlsInfo(
            pickcode="video-pickcode",
            variants=(
                HlsVariant(
                    url=hls_url,
                    bandwidth=1_000_000,
                    resolution="1920x1080",
                    label="1080p",
                    user_agent="SakuraPlayer/1.0 (Windows; x64)",
                ),
            ),
        )
    )
    fake.seed_small_file("subtitle-pickcode", subtitle)
    asyncio.run(fake.submit_offline(magnet, "task-cid"))

    printable = repr(fake) + repr(fake.calls)
    for secret in (cookie, magnet, subtitle.decode(), original_url, hls_url):
        assert secret not in printable


async def _collect_files(
    fake: StatefulFakeCloud115,
    cid: str,
) -> tuple[RemoteFile, ...]:
    return tuple([item async for item in fake.list_files_recursive(cid)])
