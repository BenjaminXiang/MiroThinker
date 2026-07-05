from __future__ import annotations

import pytest

from src.data_agents.contracts import QualityStatus
from src.data_agents.paper.milvus_backfill import _is_indexable_paper
from src.data_agents.quality.gating_contract import (
    is_indexable,
    normalize_quality_status,
    promote_monotonic,
)


CANONICAL_STATUSES = set(QualityStatus.__args__)


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("ready", "ready"),
        ("needs_review", "needs_review"),
        ("low_confidence", "low_confidence"),
        ("needs_enrichment", "needs_enrichment"),
        ("partial", "partial"),
        ("rejected", "rejected"),
        ("incomplete", "needs_review"),
        ("shallow_summary", "needs_review"),
        ("unknown_legacy_status", "needs_review"),
        (None, "needs_review"),
    ],
)
def test_normalize_quality_status(raw_status: str | None, expected: str) -> None:
    normalized = normalize_quality_status(raw_status)

    assert normalized == expected
    assert normalized in CANONICAL_STATUSES


def test_promote_monotonic_holds_and_promotes_forward() -> None:
    assert promote_monotonic("needs_enrichment", "partial") == "partial"
    assert promote_monotonic("partial", "needs_enrichment") == "partial"
    assert promote_monotonic("low_confidence", "ready") == "ready"
    assert promote_monotonic("rejected", "ready") == "rejected"


def test_promote_monotonic_never_auto_degrades_ready() -> None:
    assert promote_monotonic("ready", "needs_enrichment") == "ready"
    assert promote_monotonic("ready", "partial") == "ready"
    assert (
        promote_monotonic(
            "ready",
            "needs_review",
            admin_action="flag_for_review",
        )
        == "needs_review"
    )


def test_is_indexable_admits_only_partial_papers_with_rich_text() -> None:
    assert is_indexable(
        "partial",
        identity_status="confirmed",
        paper_has_rich_text=True,
    )
    assert not is_indexable(
        "partial",
        identity_status="confirmed",
        paper_has_rich_text=False,
    )
    assert not is_indexable(
        "needs_enrichment",
        identity_status="confirmed",
        paper_has_rich_text=True,
    )
    assert is_indexable(
        "ready",
        identity_status="confirmed",
        paper_has_rich_text=False,
    )
    assert not is_indexable(
        "partial",
        identity_status="rejected",
        paper_has_rich_text=True,
    )
    assert not is_indexable(
        "partial",
        identity_status="merged",
        paper_has_rich_text=True,
    )


@pytest.mark.parametrize(
    "row",
    [
        {"quality_status": "ready", "identity_status": "confirmed"},
        {"quality_status": "ready", "identity_status": "unverified"},
        {"quality_status": "ready", "identity_status": "rejected"},
        {"quality_status": "ready", "identity_status": "merged"},
        {"quality_status": "needs_enrichment", "identity_status": "confirmed"},
        {"quality_status": "rejected", "identity_status": "confirmed"},
    ],
)
def test_is_indexable_parity(row: dict[str, str]) -> None:
    assert is_indexable(
        row["quality_status"],
        identity_status=row["identity_status"],
    ) == _is_indexable_paper(row)
