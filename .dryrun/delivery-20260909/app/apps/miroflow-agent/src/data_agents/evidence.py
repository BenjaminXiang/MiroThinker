from __future__ import annotations

from datetime import datetime, timezone

from .contracts import Evidence, EvidenceSourceType


def build_evidence(
    *,
    source_type: EvidenceSourceType,
    source_url: str | None = None,
    source_file: str | None = None,
    fetched_at: datetime | None = None,
    snippet: str | None = None,
    confidence: float | None = None,
) -> Evidence:
    return Evidence(
        source_type=source_type,
        source_url=source_url,
        source_file=source_file,
        fetched_at=fetched_at or datetime.now(timezone.utc),
        snippet=snippet,
        confidence=confidence,
    )


def merge_evidence(*evidence_groups: list[Evidence]) -> list[Evidence]:
    seen: set[tuple] = set()
    merged: list[Evidence] = []
    for group in evidence_groups:
        for item in group:
            key = (
                item.source_type,
                item.source_url,
                item.source_file,
                item.fetched_at,
                item.snippet,
                item.confidence,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged
