"""Refresh orchestration: metric computation and the markdown view."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "refresh_professor_projection.py"
)
_spec = importlib.util.spec_from_file_location("refresh_professor_projection", _SCRIPT)
assert _spec and _spec.loader
refresh = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = refresh
_spec.loader.exec_module(refresh)


def _report(linked: int = 100, projected: int = 90, total: int = 400) -> dict:
    return {
        "population": {
            "professors": total,
            "papers": 2000,
            "edges": 1000,
            "professors_with_edges": linked,
            "projected_professors": projected,
            "rejected_professors": linked - projected,
            "rejected_by_reason": {"implausible_name": 5},
            "email_dropped": 12,
        },
        "document_gap": {
            "papers_with_professor_ids": 0,
            "professors_with_paper_count": 20,
            "professors_with_directions": 180,
            "template_summaries": 200,
            "template_summary_pct": 50.0,
        },
    }


def _scores(values: list[float]) -> list[dict]:
    return [
        {"professor_id": f"p{index}", "coherence_top3": value, "coherence": value}
        for index, value in enumerate(values)
    ]


def test_metrics_compute_counts_and_percentages() -> None:
    scores = _scores([0.1, 0.2, 0.35, 0.4, 0.5])
    allowlist = {
        "p2": {"flags": [], "paper_count": 10},
        "p3": {"flags": ["template_summary"], "paper_count": 5},
        "p4": {"flags": [], "paper_count": 7},
    }
    review = {"p0": {}, "p1": {}}

    metrics = refresh.compute_metrics(
        report=_report(),
        scores=scores,
        allowlist=allowlist,
        review=review,
        threshold=0.33,
    )

    assert metrics["population"]["linked_pct"] == 25.0
    assert metrics["coherence"]["scored"] == 5
    assert metrics["coherence"]["unscorable_no_directions"] == 85
    assert metrics["coherence"]["allowlist"] == 3
    assert metrics["coherence"]["review"] == 2
    assert metrics["coherence"]["median"] == 0.35
    assert metrics["overlay"]["effective_records"] == 3
    assert metrics["overlay"]["flagged_records"] == 1
    assert metrics["overlay"]["papers_covered"] == 22


def test_metrics_handle_no_scored_professors() -> None:
    metrics = refresh.compute_metrics(
        report=_report(), scores=[], allowlist={}, review={}, threshold=0.33
    )

    assert metrics["coherence"]["median"] is None
    assert metrics["coherence"]["allowlist_pct_of_scored"] == 0.0
    assert metrics["overlay"]["effective_records"] == 0


def test_markdown_surfaces_the_tracked_numbers() -> None:
    metrics = refresh.compute_metrics(
        report=_report(),
        scores=_scores([0.4]),
        allowlist={"p0": {"flags": [], "paper_count": 3}},
        review={},
        threshold=0.33,
    )

    markdown = refresh.render_markdown(metrics)

    assert "教授 / 论文 / 边" in markdown
    assert "有链接教授" in markdown
    assert "白名单（≥0.33）" in markdown
    assert "模板简介" in markdown
