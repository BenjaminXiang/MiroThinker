"""Unit tests for synthesis-depth fixes (Fix 1: list-entity enrichment).

Pure helpers + render paths — no DB, no LLM. Integration behavior (deeper answers)
is eval-verified per CLAUDE.md §8 (eval_first, not unit-TDD for synthesis).
"""
from __future__ import annotations

from backend.api.chat import (
    _build_evidence_blocks,
    _compact_company_rich,
    _compact_prof_rich,
    _enrich_list_entities,
)


# --- _compact_prof_rich ---
def test_compact_prof_rich_picks_top_award_and_summary() -> None:
    facts = {
        "awards": ["国家杰青", "教育部一等奖"],
        "profile_summary": "从事具身智能与强化学习研究",
    }
    out = _compact_prof_rich(facts)
    assert "国家杰青" in out
    assert "具身智能" in out


def test_compact_prof_rich_empty_returns_empty() -> None:
    assert _compact_prof_rich({}) == ""


def test_compact_prof_rich_falls_back_to_education() -> None:
    out = _compact_prof_rich({"education": ["清华大学博士"]})
    assert "清华大学" in out


# --- _compact_company_rich ---
def test_compact_company_rich_picks_product_and_team() -> None:
    facts = {
        "company_products": ["PANVIS-A 血管介入手术机器人"],
        "company_team": ["郭书祥（创始人/董事长）"],
    }
    out = _compact_company_rich(facts)
    assert "PANVIS-A" in out
    assert "郭书祥" in out


def test_compact_company_rich_empty_returns_empty() -> None:
    assert _compact_company_rich({}) == ""


# --- _enrich_list_entities (DI'd fetchers, no DB) ---
def test_enrich_list_entities_attaches_rich_summary() -> None:
    payload = {
        "matched_professors": [
            {"professor_id": "p1"},
            {"professor_id": "p2"},  # empty facts -> no key
        ],
        "matched_objects": [{"company_id": "c1"}, {"id": "paper-x"}],  # 2nd has no company_id
    }
    prof_fn = lambda conn, pid: {"awards": ["杰青"]} if pid == "p1" else {}
    company_fn = lambda conn, cid: {"company_products": ["PANVIS-A"]}
    _enrich_list_entities(
        payload, conn=object(), prof_rich_fn=prof_fn, company_rich_fn=company_fn
    )
    assert "rich_summary" in payload["matched_professors"][0]
    assert "杰青" in payload["matched_professors"][0]["rich_summary"]
    assert "rich_summary" not in payload["matched_professors"][1]
    assert "PANVIS-A" in payload["matched_objects"][0]["rich_summary"]
    assert "rich_summary" not in payload["matched_objects"][1]


# --- _build_evidence_blocks surfaces rich_summary in BOTH list paths ---
def test_build_evidence_blocks_surfaces_prof_list_rich_path_a() -> None:
    payload = {
        "matched_professors": [
            {
                "professor_id": "p1",
                "canonical_name": "张三",
                "institution": "清华大学",
                "rich_summary": "奖项：国家杰青",
            }
        ]
    }
    text, _ = _build_evidence_blocks(payload)
    assert "张三" in text
    assert "国家杰青" in text  # rich surfaced, not just name+institution


def test_build_evidence_blocks_surfaces_company_list_rich_path_b() -> None:
    payload = {
        "matched_objects": [
            {
                "company_id": "c1",
                "canonical_name": "爱博合创",
                "rich_summary": "产品：PANVIS-A",
            }
        ]
    }
    text, _ = _build_evidence_blocks(payload)
    assert "爱博合创" in text
    assert "PANVIS-A" in text
