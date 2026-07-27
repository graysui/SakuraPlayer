from datetime import datetime, timedelta, timezone

from sakuraplayer.cloud_cache.play_disposition import play_disposition

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


def test_only_new_running_job_gets_sixty_second_wait_deadline() -> None:
    started = play_disposition("submitting", created=True, now=NOW)
    assert started.name == "started"
    assert started.wait_deadline == NOW + timedelta(seconds=60)

    assert play_disposition("queued", created=True, now=NOW).name == "queued"
    assert play_disposition("ready", created=False, now=NOW).name == "ready"
    assert (
        play_disposition("ready", created=False, replayed=True, now=NOW).name
        == "reused"
    )
    assert play_disposition("offlining", created=False, now=NOW).name == "reused"
    assert play_disposition("submitting", created=False, now=NOW).wait_deadline is None
