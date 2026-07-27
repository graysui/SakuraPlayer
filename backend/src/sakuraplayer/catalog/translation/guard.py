from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")


class TranslationGuardrailError(RuntimeError):
    code = "translation_guardrail_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class ProtectedFields:
    number: str
    actors: tuple[str, ...]
    maker: str | None
    series: str | None
    tags: tuple[str, ...]


def require_unchanged_protected(
    expected: ProtectedFields,
    returned: ProtectedFields,
) -> None:
    if (
        _normalize(expected.number) != _normalize(returned.number)
        or _normalize_many(expected.actors) != _normalize_many(returned.actors)
        or _normalize_optional(expected.maker) != _normalize_optional(returned.maker)
        or _normalize_optional(expected.series) != _normalize_optional(returned.series)
        or _normalize_many(expected.tags) != _normalize_many(returned.tags)
    ):
        raise TranslationGuardrailError


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized.strip()).casefold()


def _normalize_optional(value: str | None) -> str | None:
    return None if value is None else _normalize(value)


def _normalize_many(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(_normalize(value) for value in values))


__all__ = [
    "ProtectedFields",
    "TranslationGuardrailError",
    "require_unchanged_protected",
]
