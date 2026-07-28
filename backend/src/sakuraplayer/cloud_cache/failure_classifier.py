from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile

SOURCE_UNAVAILABLE = "cloud115_source_unavailable"
SOURCE_BLOCKED = "cloud115_source_blocked"
DETERMINISTIC_FAILURE_CODES = frozenset({SOURCE_UNAVAILABLE, SOURCE_BLOCKED})


@dataclass(frozen=True, slots=True)
class DeterministicSourceFailure:
    failure_code: str
    rejection_reason_code: str


def classify_cloud_problem(code: str) -> DeterministicSourceFailure | None:
    if code != SOURCE_UNAVAILABLE:
        return None
    return _failure(SOURCE_UNAVAILABLE)


def classify_remote_files(
    files: Iterable[RemoteFile],
) -> DeterministicSourceFailure | None:
    if any(item.blocked is True for item in files):
        return _failure(SOURCE_BLOCKED)
    return None


def classify_rejection_reason(
    reason_code: str | None,
) -> DeterministicSourceFailure | None:
    if reason_code not in DETERMINISTIC_FAILURE_CODES:
        return None
    return _failure(reason_code)


def _failure(code: str) -> DeterministicSourceFailure:
    return DeterministicSourceFailure(
        failure_code=code,
        rejection_reason_code=code,
    )


__all__ = [
    "DETERMINISTIC_FAILURE_CODES",
    "DeterministicSourceFailure",
    "classify_cloud_problem",
    "classify_rejection_reason",
    "classify_remote_files",
]
