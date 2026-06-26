from __future__ import annotations

import scripts.run_patent_type_inference_backfill as backfill


def _row(**overrides):
    values = {
        "patent_id": "PAT-1",
        "patent_number": "CN115709471A",
        "patent_type": None,
        "quality_status": "partial",
        "title_clean": "一种测试专利",
        "applicants_parsed": ["深圳市测试公司有限公司"],
        "inventors_parsed": [],
        "filing_date": "2026-05-01",
        "grant_date": None,
    }
    values.update(overrides)
    return values


def test_patent_type_backfill_decision_promotes_missing_type_to_ready() -> None:
    decision = backfill.build_backfill_decision(_row())

    assert decision is not None
    assert decision.patent_id == "PAT-1"
    assert decision.inferred_type == "发明"
    assert decision.old_quality_status == "partial"
    assert decision.new_quality_status == "ready"
    assert decision.is_promoted_to_ready
    assert not decision.is_ready_degraded


def test_patent_type_backfill_decision_skips_existing_source_type() -> None:
    decision = backfill.build_backfill_decision(
        _row(patent_type="发明", patent_number="CN223200311U")
    )

    assert decision is None
