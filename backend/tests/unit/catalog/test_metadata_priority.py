import pytest

from sakuraplayer.catalog.metadata_state import (
    ALL_STAGES,
    OPTIONAL_STAGES,
    MetadataStateError,
    priority_for_reason,
    stage_plan,
    validate_enrichment_stages,
)


@pytest.mark.parametrize(
    ("reason", "priority"),
    [
        ("manual_or_search", 10),
        ("ranking", 20),
        ("daily", 30),
        ("initial", 40),
        ("history", 50),
    ],
)
def test_priority_mapping_is_fixed(reason: str, priority: int) -> None:
    assert priority_for_reason(reason) == priority


def test_unknown_reason_is_rejected() -> None:
    with pytest.raises(MetadataStateError):
        priority_for_reason("background")


def test_full_attempt_starts_every_stage_pending() -> None:
    assert stage_plan(retry_mode="full", requested_stages=()) == {
        stage: "pending" for stage in ALL_STAGES
    }


def test_enrichment_retry_only_runs_explicit_optional_stages() -> None:
    requested = validate_enrichment_stages(("translation", "images"))

    assert requested == ("images", "translation")
    assert stage_plan(
        retry_mode="missing_enrichment",
        requested_stages=requested,
    ) == {
        "javdb_core": "skipped",
        "images": "pending",
        "dmm": "skipped",
        "actor_map": "skipped",
        "gfriends": "skipped",
        "translation": "pending",
    }


@pytest.mark.parametrize(
    "stages",
    [(), ("javdb_core",), ("images", "images"), ("unknown",)],
)
def test_invalid_enrichment_retry_stage_sets_are_rejected(
    stages: tuple[str, ...],
) -> None:
    with pytest.raises(MetadataStateError):
        validate_enrichment_stages(stages)


def test_optional_stage_catalog_does_not_include_core() -> None:
    assert "javdb_core" not in OPTIONAL_STAGES
