from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLabelEvidence:
    label: str
    evidence: str


def derive_source_labels(
    *,
    section: str,
    category: str | None,
    title: str,
) -> tuple[SourceLabelEvidence, ...]:
    labels: list[SourceLabelEvidence] = []
    category_text = category or ""
    if section == "中文字幕":
        labels.append(SourceLabelEvidence("subtitle", "section=中文字幕"))
    if "无码破解" in category_text:
        labels.append(SourceLabelEvidence("cracked", f"category={category_text}"))
    elif "无码破解" in title:
        labels.append(SourceLabelEvidence("cracked", "title=无码破解"))
    if section == "4K原版":
        labels.append(SourceLabelEvidence("4k", "section=4K原版"))
    if "有码" in category_text:
        labels.append(SourceLabelEvidence("censored", f"category={category_text}"))
    return tuple(labels)
