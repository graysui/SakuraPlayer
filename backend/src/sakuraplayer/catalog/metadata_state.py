from __future__ import annotations

from collections.abc import Iterable

ALL_STAGES = (
    "javdb_core",
    "images",
    "dmm",
    "actor_map",
    "gfriends",
    "translation",
)
OPTIONAL_STAGES = ALL_STAGES[1:]
PRIORITY_BY_REASON = {
    "manual_or_search": 10,
    "ranking": 20,
    "daily": 30,
    "initial": 40,
    "history": 50,
}


class MetadataStateError(ValueError):
    pass


class MetadataStageExecutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def priority_for_reason(reason: str) -> int:
    try:
        return PRIORITY_BY_REASON[reason]
    except KeyError:
        raise MetadataStateError("invalid metadata queue reason") from None


def validate_enrichment_stages(stages: Iterable[str]) -> tuple[str, ...]:
    values = tuple(stages)
    if not values or len(set(values)) != len(values):
        raise MetadataStateError("invalid metadata enrichment stages")
    if any(stage not in OPTIONAL_STAGES for stage in values):
        raise MetadataStateError("invalid metadata enrichment stages")
    selected = set(values)
    return tuple(stage for stage in OPTIONAL_STAGES if stage in selected)


def stage_plan(
    *,
    retry_mode: str,
    requested_stages: Iterable[str],
) -> dict[str, str]:
    requested = tuple(requested_stages)
    if retry_mode == "full":
        if requested:
            raise MetadataStateError("full metadata attempt cannot select stages")
        return {stage: "pending" for stage in ALL_STAGES}
    if retry_mode != "missing_enrichment":
        raise MetadataStateError("invalid metadata retry mode")
    selected = set(validate_enrichment_stages(requested))
    return {
        stage: "pending" if stage in selected else "skipped" for stage in ALL_STAGES
    }


__all__ = [
    "ALL_STAGES",
    "OPTIONAL_STAGES",
    "MetadataStateError",
    "MetadataStageExecutionError",
    "priority_for_reason",
    "stage_plan",
    "validate_enrichment_stages",
]
