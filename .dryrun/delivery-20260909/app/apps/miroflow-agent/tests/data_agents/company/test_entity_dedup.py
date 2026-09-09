from __future__ import annotations

from datetime import date

from src.data_agents.company.entity_dedup import (
    build_signal_event_dedup_key,
    explain_signal_event_dedup_key,
    jaccard_similarity,
    match_company_alias,
    normalize_name,
)


def test_normalize_name_removes_common_company_noise():
    assert normalize_name("深圳市 示例科技（深圳）有限公司") == "示例科技深圳"


def test_match_company_alias_accepts_normalized_exact_match():
    decision = match_company_alias("深圳市示例科技有限公司", "示例科技")

    assert decision.is_match is True
    assert decision.reasoning == "normalized_names_equal"


def test_jaccard_similarity_rejects_unrelated_aliases():
    score = jaccard_similarity("深圳示例机器人", "南山生物医药")
    decision = match_company_alias("深圳示例机器人", "南山生物医药")

    assert score < 0.3
    assert decision.is_match is False


def test_signal_event_dedup_key_uses_company_type_and_date_only():
    first = build_signal_event_dedup_key(
        company_id="COMP-1",
        event_type="funding",
        event_date=date(2026, 5, 1),
    )
    second = build_signal_event_dedup_key(
        company_id="COMP-1",
        event_type="funding",
        event_date="2026-05-01",
    )
    changed_date = build_signal_event_dedup_key(
        company_id="COMP-1",
        event_type="funding",
        event_date="2026-05-02",
    )

    assert first == second
    assert first != changed_date
    assert len(first) == 20


def test_explain_signal_event_dedup_key_returns_reasoning():
    decision = explain_signal_event_dedup_key(
        company_id="COMP-1", event_type="funding", event_date="20260501"
    )

    assert decision.dedup_key
    assert "company_id=COMP-1" in decision.reasoning
    assert "event_date=2026-05-01" in decision.reasoning
