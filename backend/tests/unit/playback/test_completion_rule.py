from __future__ import annotations

from decimal import Decimal

import pytest

from sakuraplayer.playback.progress import completion_state


@pytest.mark.parametrize(
    ("position", "duration", "completed", "stored_position"),
    [
        (Decimal("9499"), Decimal("10000"), False, Decimal("9499")),
        (Decimal("9500"), Decimal("10000"), True, Decimal("0")),
        (Decimal("879"), Decimal("1000"), False, Decimal("879")),
        (Decimal("880"), Decimal("1000"), False, Decimal("880")),
        (Decimal("881"), Decimal("1000"), True, Decimal("0")),
        (Decimal("1001"), Decimal("1000"), True, Decimal("0")),
        (Decimal("0"), Decimal("100"), False, Decimal("0")),
        (Decimal("42.5"), None, False, Decimal("42.5")),
    ],
)
def test_completion_rule_has_exact_thresholds(
    position: Decimal,
    duration: Decimal | None,
    completed: bool,
    stored_position: Decimal,
) -> None:
    result = completion_state(position_seconds=position, duration_seconds=duration)

    assert result.completed is completed
    assert result.position_seconds == stored_position
    assert result.duration_seconds == duration


@pytest.mark.parametrize(
    ("position", "duration"),
    [
        (Decimal("-0.001"), Decimal("100")),
        (Decimal("NaN"), Decimal("100")),
        (Decimal("Infinity"), Decimal("100")),
        (Decimal("1"), Decimal("0")),
        (Decimal("1"), Decimal("0.0004")),
        (Decimal("1"), Decimal("-1")),
        (Decimal("1"), Decimal("NaN")),
    ],
)
def test_completion_rule_rejects_invalid_numeric_input(
    position: Decimal,
    duration: Decimal | None,
) -> None:
    with pytest.raises(ValueError, match="progress value"):
        completion_state(position_seconds=position, duration_seconds=duration)
