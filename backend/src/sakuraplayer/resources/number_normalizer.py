from __future__ import annotations

import re
import unicodedata

_FC2_NUMBER = re.compile(r"^FC2[\s._/-]*(?:PPV[\s._/-]*)?(?P<number>[0-9]{5,10})$")
_SEPARATED_STANDARD_NUMBER = re.compile(
    r"^(?P<prefix>[A-Z][A-Z0-9]{1,15})[\s._/-]+(?P<number>[0-9]{2,10})$"
)
_COMPACT_STANDARD_NUMBER = re.compile(
    r"^(?P<prefix>[A-Z]{2,16})(?P<number>[0-9]{2,10})$"
)
_MAX_RAW_LENGTH = 128


def normalize_movie_number(raw_number: str | None) -> str | None:
    if raw_number is None:
        return None
    stripped = raw_number.strip()
    if not stripped or len(stripped) > _MAX_RAW_LENGTH:
        return None

    normalized = unicodedata.normalize("NFKC", stripped).upper()
    if len(normalized) > _MAX_RAW_LENGTH:
        return None

    fc2 = _FC2_NUMBER.fullmatch(normalized)
    if fc2 is not None:
        return f"FC2-PPV-{fc2.group('number')}"
    if normalized.startswith("FC2"):
        return None

    standard = _SEPARATED_STANDARD_NUMBER.fullmatch(normalized)
    if standard is None:
        standard = _COMPACT_STANDARD_NUMBER.fullmatch(normalized)
    if standard is None:
        return None
    return f"{standard.group('prefix')}-{standard.group('number')}"
