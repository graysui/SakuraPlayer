from __future__ import annotations

import pytest

from sakuraplayer.cloud_cache.infrastructure.cloud115.adapter import Cloud115Adapter
from sakuraplayer.cloud_cache.infrastructure.cloud115.cipher import (
    decrypt_response,
    encrypt_payload,
)
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem, OfflineStatus


def test_historical_directory_short_fields_are_mapped() -> None:
    directory = Cloud115Adapter.parse_remote_file(
        {"cid": "10", "pid": "0", "n": "cache", "te": "7", "tp": "6"}
    )
    video = Cloud115Adapter.parse_remote_file(
        {
            "fid": "20",
            "cid": "10",
            "n": "movie.mkv",
            "s": "1024",
            "sha": "ABC",
            "pc": "pick",
            "iv": 1,
            "play_long": "123.0",
            "ic": "1",
        }
    )

    assert directory.is_directory is True
    assert directory.parent_cid == "0"
    assert video.is_directory is False
    assert video.size_bytes == 1024
    assert video.duration_seconds == 123
    assert video.blocked is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (-1, OfflineStatus.FAILED),
        (0, OfflineStatus.QUEUED),
        (1, OfflineStatus.RUNNING),
        (2, OfflineStatus.COMPLETED),
    ],
)
def test_historical_offline_status_mapping(raw: int, expected: OfflineStatus) -> None:
    task = Cloud115Adapter.parse_offline_task(
        {
            "info_hash": "a" * 40,
            "name": "task",
            "size": "42",
            "status": raw,
            "percentDone": "75.5",
            "url": "magnet:?xt=urn:btih:not-copied",
        }
    )

    assert task.status is expected
    assert task.percent_done == 75.5
    assert "magnet:" not in repr(task)


def test_unknown_offline_status_is_protocol_error() -> None:
    with pytest.raises(Cloud115Problem) as raised:
        Cloud115Adapter.parse_offline_task(
            {
                "info_hash": "a" * 40,
                "name": "task",
                "size": 1,
                "status": 9,
            }
        )
    assert raised.value.code == "cloud115_protocol_error"


def test_downurl_request_cipher_is_deterministic_fixture() -> None:
    encoded = encrypt_payload({"pickcode": "abc123", "user_id": "123"})

    assert encoded == (
        b"RKlJ5oiS7/DuAqkaj5893nyKun74VH1d4EsuvhLtYd0KjD2kYKMC5a/lovz/8QiN"
        b"ZGagKM1AIZU3zumhtOs09GswmSPz8XpZ8vbIGq4wNocl6f3FYCdVpeBXNkAwbZQw"
        b"fFLoKwsvZZW1ZeodsToONClkXHsb6S4zxzKzV6gJAI4="
    )


def test_invalid_downurl_cipher_has_stable_safe_error() -> None:
    with pytest.raises(Cloud115Problem) as raised:
        decrypt_response("not-valid-base64")
    assert raised.value.code == "cloud115_protocol_error"
    assert str(raised.value) == "cloud115_protocol_error"
