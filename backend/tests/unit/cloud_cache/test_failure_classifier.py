from __future__ import annotations

import pytest

from sakuraplayer.cloud_cache.failure_classifier import (
    DeterministicSourceFailure,
    classify_cloud_problem,
    classify_remote_files,
)
from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile


def test_only_stable_submit_not_found_code_is_deterministic() -> None:
    assert classify_cloud_problem("cloud115_source_unavailable") == (
        DeterministicSourceFailure(
            failure_code="cloud115_source_unavailable",
            rejection_reason_code="cloud115_source_unavailable",
        )
    )


@pytest.mark.parametrize(
    "code",
    [
        "cloud115_offline_failed",
        "cloud115_offline_invalid",
        "cloud115_unavailable",
        "cloud115_rate_limited",
        "cloud115_credentials_expired",
        "cloud115_offline_quota_exceeded",
        "cloud115_submit_uncertain",
        "cloud115_protocol_error",
        "unknown_code",
    ],
)
def test_transient_ambiguous_and_unknown_codes_never_reject(code: str) -> None:
    assert classify_cloud_problem(code) is None


def test_blocked_remote_file_is_deterministic_without_raw_evidence() -> None:
    failure = classify_remote_files(
        (
            _file("normal", blocked=False),
            _file("blocked", blocked=True),
        )
    )

    assert failure == DeterministicSourceFailure(
        failure_code="cloud115_source_blocked",
        rejection_reason_code="cloud115_source_blocked",
    )
    assert "upstream" not in repr(failure).lower()
    assert "blocked.mkv" not in repr(failure).lower()


def test_absent_or_unknown_blocked_flag_never_rejects() -> None:
    assert classify_remote_files((_file("normal", blocked=False),)) is None
    assert classify_remote_files((_file("unknown", blocked=None),)) is None


def _file(file_id: str, *, blocked: bool | None) -> RemoteFile:
    return RemoteFile(
        file_id=file_id,
        parent_cid="task",
        name=f"{file_id}.mkv",
        size_bytes=1024,
        pickcode=f"pick-{file_id}",
        sha1=None,
        is_directory=False,
        is_video=True,
        duration_seconds=None,
        blocked=blocked,
    )
