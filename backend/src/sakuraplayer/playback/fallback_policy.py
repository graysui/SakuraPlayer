from __future__ import annotations

ORIGINAL_HLS_FALLBACK_CODES = frozenset({"cloud115_original_unavailable"})


def should_fallback_to_hls(code: str) -> bool:
    return code in ORIGINAL_HLS_FALLBACK_CODES


__all__ = ["ORIGINAL_HLS_FALLBACK_CODES", "should_fallback_to_hls"]
