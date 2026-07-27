from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from sakuraplayer.cloud_cache.file_scanner import (
    MIN_VIDEO_BYTES,
    file_extension,
    normalized_stem,
    stem_tokens,
)
from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile

AUTO_SELECTION_SCORE_GAP = 80
_SEGMENT = re.compile(
    r"^(?P<base>.*?)[\s._\-\[(]+(?P<label>cd|disc|disk|part|pt)"
    r"[\s._-]*(?P<number>[1-9]\d?)[\])]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ScoredMedia:
    file: RemoteFile
    candidate_key: str
    sequence_no: int
    selection_score: int
    selection_evidence: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class MediaSelectionPlan:
    media: tuple[ScoredMedia, ...]
    selected_candidate_key: str | None
    requires_selection: bool


def plan_media_selection(
    files: Iterable[RemoteFile],
    *,
    movie_number: str,
) -> MediaSelectionPlan:
    items = tuple(files)
    if not items:
        return MediaSelectionPlan((), None, False)
    groups = _candidate_groups(items)
    scored_groups: list[tuple[str, tuple[ScoredMedia, ...], int, int]] = []
    for candidate_key, members in groups:
        continuous = len(members) > 1
        scored_members = tuple(
            _score_media(
                item,
                candidate_key=candidate_key,
                sequence_no=index,
                movie_number=movie_number,
            )
            for index, item in enumerate(members)
        )
        score = max(item.selection_score for item in scored_members)
        if continuous:
            score += 20
            scored_members = tuple(
                ScoredMedia(
                    file=item.file,
                    candidate_key=item.candidate_key,
                    sequence_no=item.sequence_no,
                    selection_score=item.selection_score + 20,
                    selection_evidence=item.selection_evidence
                    + (("continuous_segments", 20),),
                )
                for item in scored_members
            )
        total_size = sum(item.file.size_bytes for item in scored_members)
        scored_groups.append((candidate_key, scored_members, score, total_size))
    scored_groups.sort(key=lambda value: (-value[2], -value[3], value[0]))
    if len(scored_groups) == 1:
        selected = scored_groups[0][0]
    elif scored_groups[0][2] - scored_groups[1][2] >= AUTO_SELECTION_SCORE_GAP:
        selected = scored_groups[0][0]
    else:
        selected = None
    media = tuple(item for _, members, _, _ in scored_groups for item in members)
    return MediaSelectionPlan(
        media=media,
        selected_candidate_key=selected,
        requires_selection=selected is None,
    )


def _candidate_groups(
    files: tuple[RemoteFile, ...],
) -> list[tuple[str, tuple[RemoteFile, ...]]]:
    segment_buckets: dict[tuple[str, str, str], list[tuple[int, RemoteFile]]] = {}
    singles: list[RemoteFile] = []
    for item in files:
        match = _SEGMENT.fullmatch(normalized_stem(item.name))
        if match is None:
            singles.append(item)
            continue
        base = match.group("base").strip(" ._-[]()")
        if not base:
            singles.append(item)
            continue
        key = (item.parent_cid, file_extension(item.name), base)
        segment_buckets.setdefault(key, []).append((int(match.group("number")), item))

    groups: list[tuple[str, tuple[RemoteFile, ...]]] = []
    for key, numbered in segment_buckets.items():
        numbered.sort(key=lambda value: (value[0], _stable_file_key(value[1])))
        numbers = [number for number, _ in numbered]
        if len(numbers) >= 2 and numbers == list(range(1, len(numbers) + 1)):
            candidate_key = "segment:" + "\x1f".join(key)
            groups.append((candidate_key, tuple(item for _, item in numbered)))
        else:
            singles.extend(item for _, item in numbered)
    groups.extend((f"single:{item.file_id}", (item,)) for item in singles)
    groups.sort(key=lambda value: value[0])
    return groups


def _score_media(
    item: RemoteFile,
    *,
    candidate_key: str,
    sequence_no: int,
    movie_number: str,
) -> ScoredMedia:
    evidence: list[tuple[str, int]] = [("valid_video", 10)]
    score = 10
    if item.is_video is True:
        evidence.append(("upstream_video", 10))
        score += 10
    if item.duration_seconds is not None and item.duration_seconds >= 1200:
        evidence.append(("duration_20m", 10))
        score += 10
    if _contains_movie_number(item.name, movie_number):
        evidence.append(("movie_number", 100))
        score += 100
    size_score = min(item.size_bytes // MIN_VIDEO_BYTES, 40)
    if size_score:
        evidence.append(("size_units", int(size_score)))
        score += int(size_score)
    return ScoredMedia(
        file=item,
        candidate_key=candidate_key,
        sequence_no=sequence_no,
        selection_score=score,
        selection_evidence=tuple(evidence),
    )


def _contains_movie_number(name: str, movie_number: str) -> bool:
    wanted = tuple(
        token.casefold()
        for token in re.findall(
            r"[^\W_]+", unicodedata.normalize("NFKC", movie_number), re.UNICODE
        )
    )
    actual = stem_tokens(name)
    if not wanted or len(wanted) > len(actual):
        return False
    return any(
        actual[index : index + len(wanted)] == wanted
        for index in range(len(actual) - len(wanted) + 1)
    )


def _stable_file_key(item: RemoteFile) -> tuple[str, str]:
    return (unicodedata.normalize("NFKC", item.name).casefold(), item.file_id)


__all__ = [
    "AUTO_SELECTION_SCORE_GAP",
    "MediaSelectionPlan",
    "ScoredMedia",
    "plan_media_selection",
]
