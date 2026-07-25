from __future__ import annotations

import pytest

from sakuraplayer.resources.number_normalizer import normalize_movie_number


@pytest.mark.parametrize(
    ("raw_number", "expected"),
    [
        ("abp 001", "ABP-001"),
        ("ABP_001", "ABP-001"),
        ("abp001", "ABP-001"),
        ("  ABP-001  ", "ABP-001"),
        ("ＡＢＰ－００１", "ABP-001"),
        ("t28/123", "T28-123"),
        ("fc2 ppv 1234567", "FC2-PPV-1234567"),
        ("FC2-PPV-1234567", "FC2-PPV-1234567"),
        ("fc2_1234567", "FC2-PPV-1234567"),
    ],
)
def test_normalizes_contract_movie_number_samples(
    raw_number: str,
    expected: str,
) -> None:
    assert normalize_movie_number(raw_number) == expected


@pytest.mark.parametrize(
    "raw_number",
    [
        None,
        "",
        "   ",
        "12345",
        "A-123",
        "ABP-1",
        "T28123",
        "ABP-123-CD",
        "ABP-123 FC2-1234567",
        "FC2-PPV-1234",
        "FC2-PPV-12345678901",
        "x" * 129,
    ],
)
def test_rejects_movie_numbers_that_cannot_be_reliably_normalized(
    raw_number: str | None,
) -> None:
    assert normalize_movie_number(raw_number) is None
