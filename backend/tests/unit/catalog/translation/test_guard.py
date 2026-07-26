from __future__ import annotations

import pytest

from sakuraplayer.catalog.translation.guard import (
    ProtectedFields,
    TranslationGuardrailError,
    require_unchanged_protected,
)


def protected() -> ProtectedFields:
    return ProtectedFields(
        number="ABP-123",
        actors=("Actor One", "Ａｃｔｏｒ Two"),
        maker="Fixture Maker",
        series=None,
        tags=("Drama", "Featured"),
    )


def test_protected_comparison_normalizes_without_mutating_display_values() -> None:
    expected = protected()
    returned = ProtectedFields(
        number=" abp-123 ",
        actors=("actor two", " actor   one "),
        maker="fixture maker",
        series=None,
        tags=(" featured ", "DRAMA"),
    )

    require_unchanged_protected(expected, returned)

    assert expected.number == "ABP-123"
    assert expected.actors == ("Actor One", "Ａｃｔｏｒ Two")
    assert expected.tags == ("Drama", "Featured")


@pytest.mark.parametrize(
    "returned",
    [
        ProtectedFields("ABP-124", ("Actor One", "Actor Two"), "Fixture Maker", None, ("Drama", "Featured")),
        ProtectedFields("ABP-123", ("Actor One",), "Fixture Maker", None, ("Drama", "Featured")),
        ProtectedFields("ABP-123", ("Actor One", "Actor Two"), "Other Maker", None, ("Drama", "Featured")),
        ProtectedFields("ABP-123", ("Actor One", "Actor Two"), "Fixture Maker", "Series", ("Drama", "Featured")),
        ProtectedFields("ABP-123", ("Actor One", "Actor Two"), "Fixture Maker", None, ("Drama", "Other")),
    ],
)
def test_any_protected_change_is_rejected(returned: ProtectedFields) -> None:
    with pytest.raises(TranslationGuardrailError) as error:
        require_unchanged_protected(protected(), returned)

    assert error.value.code == "translation_guardrail_failed"
    assert str(error.value) == "translation_guardrail_failed"
