from __future__ import annotations

import json
from pathlib import Path

from sakuraplayer.cloud_cache.file_scanner import (
    MIN_VIDEO_BYTES,
    scan_remote_files,
)
from sakuraplayer.cloud_cache.media_selection import plan_media_selection
from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile
from sakuraplayer.cloud_cache.subtitle_locator import locate_subtitles

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "cloud_cache" / "media-tree.json"
)


def test_fixture_freezes_video_threshold_ad_tokens_and_subtitle_limits() -> None:
    movie_number, files = _fixture()

    scanned = scan_remote_files(files)

    video_ids = {item.file_id for item in scanned.videos}
    assert "video-threshold" in video_ids
    assert "video-small" not in video_ids
    assert "video-ad" not in video_ids
    assert "video-sample" not in video_ids
    assert "video-word" in video_ids
    assert "video-blocked" not in video_ids
    assert {"duplicate-a", "duplicate-b"}.issubset(video_ids)
    assert (
        len([item for item in scanned.videos if item.name == "duplicate-feature.mkv"])
        == 2
    )
    assert {item.name.rsplit(".", 1)[-1] for item in scanned.subtitles} == {
        "srt",
        "ass",
        "ssa",
        "vtt",
    }
    assert "sub-large" not in {item.file_id for item in scanned.subtitles}
    assert MIN_VIDEO_BYTES == 256 * 1024 * 1024
    assert movie_number == "IPX-001"


def test_continuous_segments_form_one_ordered_candidate_but_gaps_do_not() -> None:
    movie_number, files = _fixture()
    scanned = scan_remote_files(files)

    plan = plan_media_selection(scanned.videos, movie_number=movie_number)

    segment_items = [
        item for item in plan.media if item.file.file_id.startswith("part-")
    ]
    assert [item.sequence_no for item in segment_items] == [0, 1]
    assert len({item.candidate_key for item in segment_items}) == 1
    gap_items = [item for item in plan.media if item.file.file_id.startswith("gap-")]
    assert len({item.candidate_key for item in gap_items}) == 2


def test_unique_number_evidence_auto_selects_but_close_candidates_wait() -> None:
    movie_number, files = _fixture()
    scanned = scan_remote_files(files)
    decisive_files = tuple(
        item
        for item in scanned.videos
        if item.file_id in {"video-main", "video-other", "video-word"}
    )
    plan = plan_media_selection(decisive_files, movie_number=movie_number)

    selected_ids = {
        item.file.file_id
        for item in plan.media
        if item.candidate_key == plan.selected_candidate_key
    }
    assert selected_ids == {"video-main"}
    assert plan.requires_selection is False

    close_files = tuple(
        item for item in scanned.videos if item.file_id in {"video-other", "video-word"}
    )
    ambiguous = plan_media_selection(close_files, movie_number=movie_number)
    assert ambiguous.selected_candidate_key is None
    assert ambiguous.requires_selection is True


def test_subtitle_locator_prefers_exact_stem_then_language_suffix() -> None:
    movie_number, files = _fixture()
    scanned = scan_remote_files(files)
    plan = plan_media_selection(scanned.videos, movie_number=movie_number)

    located = locate_subtitles(scanned.subtitles, plan.media)

    by_id = {item.file.file_id: item for item in located}
    assert by_id["sub-srt"].media_file_id == "video-main"
    assert by_id["sub-srt"].match_score == 110
    assert by_id["sub-ass"].media_file_id == "video-main"
    assert by_id["sub-ass"].match_score == 90
    assert by_id["sub-ssa"].media_file_id is None
    assert [item.file.file_id for item in located[:2]] == ["sub-srt", "sub-ass"]


def _fixture() -> tuple[str, tuple[RemoteFile, ...]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    files = tuple(
        RemoteFile(
            file_id=item["file_id"],
            parent_cid=item["parent_cid"],
            name=item["name"],
            size_bytes=item["size_bytes"],
            pickcode=item["pickcode"],
            sha1=None,
            is_directory=False,
            is_video=item["is_video"],
            duration_seconds=item["duration_seconds"],
            blocked=item["blocked"],
        )
        for item in payload["files"]
    )
    return payload["movie_number"], files
