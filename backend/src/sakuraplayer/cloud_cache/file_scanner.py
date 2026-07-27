from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable

from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile

MIN_VIDEO_BYTES = 256 * 1024 * 1024
MAX_SUBTITLE_BYTES = 8 * 1024 * 1024
VIDEO_EXTENSIONS = frozenset(
    {"mp4", "mkv", "avi", "mov", "m4v", "wmv", "flv", "ts", "m2ts", "webm"}
)
SUBTITLE_EXTENSIONS = frozenset({"srt", "ass", "ssa", "vtt"})
_EXCLUDED_TOKENS = frozenset(
    {
        "sample",
        "trailer",
        "preview",
        "promo",
        "advertisement",
        "ads",
        "cm",
        "试看",
        "試看",
        "样片",
        "樣片",
        "预告",
        "預告",
        "广告",
        "廣告",
    }
)
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class FileScanResult:
    videos: tuple[RemoteFile, ...]
    subtitles: tuple[RemoteFile, ...]


def scan_remote_files(files: Iterable[RemoteFile]) -> FileScanResult:
    videos: list[RemoteFile] = []
    subtitles: list[RemoteFile] = []
    seen_ids: set[str] = set()
    for item in files:
        if item.is_directory:
            continue
        if item.file_id in seen_ids:
            raise ValueError("duplicate remote file id")
        seen_ids.add(item.file_id)
        if not item.file_id or not item.parent_cid or not item.pickcode:
            continue
        extension = file_extension(item.name)
        if (
            extension in VIDEO_EXTENSIONS
            and item.size_bytes >= MIN_VIDEO_BYTES
            and item.blocked is not True
            and not has_excluded_stem_token(item.name)
        ):
            videos.append(item)
        elif (
            extension in SUBTITLE_EXTENSIONS
            and 1 <= item.size_bytes <= MAX_SUBTITLE_BYTES
            and item.blocked is not True
        ):
            subtitles.append(item)
    return FileScanResult(
        videos=tuple(sorted(videos, key=_file_order)),
        subtitles=tuple(sorted(subtitles, key=_file_order)),
    )


def file_extension(name: str) -> str:
    suffix = PurePath(unicodedata.normalize("NFKC", name)).suffix
    return suffix[1:].casefold() if suffix.startswith(".") else ""


def normalized_stem(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name)
    suffix = PurePath(normalized).suffix
    return normalized[: -len(suffix)].casefold() if suffix else normalized.casefold()


def stem_tokens(name: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(normalized_stem(name)))


def has_excluded_stem_token(name: str) -> bool:
    return any(token in _EXCLUDED_TOKENS for token in stem_tokens(name))


def _file_order(item: RemoteFile) -> tuple[str, str, str]:
    return (
        item.parent_cid,
        unicodedata.normalize("NFKC", item.name).casefold(),
        item.file_id,
    )


__all__ = [
    "FileScanResult",
    "MAX_SUBTITLE_BYTES",
    "MIN_VIDEO_BYTES",
    "SUBTITLE_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "file_extension",
    "normalized_stem",
    "scan_remote_files",
    "stem_tokens",
]
