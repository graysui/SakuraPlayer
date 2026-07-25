from sakuraplayer.resources.source_labels import derive_source_labels


def test_derives_all_supported_labels_from_explicit_evidence() -> None:
    labels = derive_source_labels(
        section="中文字幕",
        category="无码破解 有码",
        title="4K原版 无码破解",
    )

    assert {(item.label, item.evidence) for item in labels} == {
        ("subtitle", "section=中文字幕"),
        ("cracked", "category=无码破解 有码"),
        ("censored", "category=无码破解 有码"),
    }


def test_does_not_infer_cracked_or_censored_from_ambiguous_sections() -> None:
    uncensored = derive_source_labels(
        section="亚洲无码",
        category=None,
        title="普通标题",
    )
    historical_4k = derive_source_labels(
        section="4K原版",
        category=None,
        title="普通标题",
    )

    assert uncensored == ()
    assert {(item.label, item.evidence) for item in historical_4k} == {
        ("4k", "section=4K原版"),
    }


def test_uses_title_only_for_an_explicit_cracked_marker() -> None:
    labels = derive_source_labels(
        section="亚洲无码",
        category=None,
        title="无码破解 高清资源",
    )

    assert {(item.label, item.evidence) for item in labels} == {
        ("cracked", "title=无码破解"),
    }


def test_classifies_the_17202_cracked_fixture_baseline() -> None:
    fixture = [
        derive_source_labels(
            section="亚洲无码",
            category="无码破解",
            title=f"Fixture {index}",
        )
        for index in range(17_202)
    ]

    assert len(fixture) == 17_202
    assert all(
        {(item.label, item.evidence) for item in labels}
        == {("cracked", "category=无码破解")}
        for labels in fixture
    )
