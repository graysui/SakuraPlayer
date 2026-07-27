from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from sakuraplayer.cloud_cache.file_scanner import file_extension, normalized_stem
from sakuraplayer.cloud_cache.media_selection import ScoredMedia
from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile

_LANGUAGE_SUFFIX = re.compile(r"(?:[\s._-]+)(?:zh|chs|cht|cn|中文)$", re.IGNORECASE)
_EXTENSION_ORDER = {"srt": 0, "ass": 1, "ssa": 2, "vtt": 3}


@dataclass(frozen=True, slots=True)
class LocatedSubtitle:
    file: RemoteFile
    media_file_id: str | None
    match_score: int
    match_evidence: tuple[str, ...]


def locate_subtitles(
    subtitles: Iterable[RemoteFile],
    media: Iterable[ScoredMedia],
) -> tuple[LocatedSubtitle, ...]:
    media_items = tuple(media)
    located = tuple(_locate(item, media_items) for item in subtitles)
    return tuple(
        sorted(
            located,
            key=lambda item: (
                -item.match_score,
                _EXTENSION_ORDER[file_extension(item.file.name)],
                unicodedata.normalize("NFKC", item.file.name).casefold(),
                item.file.file_id,
            ),
        )
    )


def _locate(
    subtitle: RemoteFile,
    media: tuple[ScoredMedia, ...],
) -> LocatedSubtitle:
    subtitle_stem = normalized_stem(subtitle.name)
    stripped_stem = _LANGUAGE_SUFFIX.sub("", subtitle_stem)
    matches: list[tuple[int, str, tuple[str, ...]]] = []
    for candidate in media:
        media_stem = normalized_stem(candidate.file.name)
        score = 0
        evidence: list[str] = []
        if subtitle_stem == media_stem:
            score = 100
            evidence.append("exact_stem")
        elif stripped_stem != subtitle_stem and stripped_stem == media_stem:
            score = 80
            evidence.append("language_suffix_stem")
        if score and subtitle.parent_cid == candidate.file.parent_cid:
            score += 10
            evidence.append("same_parent")
        if score:
            matches.append((score, candidate.file.file_id, tuple(evidence)))
    if not matches:
        return LocatedSubtitle(subtitle, None, 0, ())
    matches.sort(key=lambda value: (-value[0], value[1]))
    score, media_file_id, resolved_evidence = matches[0]
    return LocatedSubtitle(subtitle, media_file_id, score, resolved_evidence)


__all__ = ["LocatedSubtitle", "locate_subtitles"]
