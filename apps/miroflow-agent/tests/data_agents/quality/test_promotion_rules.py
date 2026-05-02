from __future__ import annotations

from src.data_agents.quality.promotion_rules import (
    evaluate_company,
    evaluate_paper,
    evaluate_professor,
)


def _text(length: int) -> str:
    return "x" * length


def test_evaluate_professor_high_ready() -> None:
    assert evaluate_professor(
        {"identity_status": "confirmed", "profile_summary": _text(150)}
    ) == ("ready", None)


def test_evaluate_professor_resolved_matches_confirmed_schema_semantics() -> None:
    assert evaluate_professor(
        {"identity_status": "resolved", "profile_summary": _text(150)}
    ) == ("ready", None)


def test_evaluate_professor_medium_summary_too_short() -> None:
    assert evaluate_professor(
        {"identity_status": "confirmed", "profile_summary": _text(149)}
    ) == ("needs_review", "professor_summary_too_short")


def test_evaluate_professor_low_unconfirmed_no_issue() -> None:
    assert evaluate_professor(
        {"identity_status": "unverified", "profile_summary": _text(200)}
    ) == ("needs_review", None)


def test_evaluate_company_high_ready() -> None:
    assert evaluate_company(
        {
            "profile_summary": _text(100),
            "technology_route_summary": "route summary",
        }
    ) == ("ready", None)


def test_evaluate_company_medium_partial_narrative() -> None:
    assert evaluate_company(
        {"profile_summary": _text(100), "technology_route_summary": None}
    ) == ("needs_review", "company_partial_narrative")


def test_evaluate_company_low_no_narrative() -> None:
    assert evaluate_company(
        {"profile_summary": None, "technology_route_summary": ""}
    ) == ("needs_review", "company_no_narrative")


def test_evaluate_paper_high_ready() -> None:
    assert evaluate_paper(
        {
            "summary_zh": _text(150),
            "abstract_clean": "abstract",
            "identity_status": "confirmed",
        }
    ) == ("ready", None)


def test_evaluate_paper_medium_partial_metadata() -> None:
    assert evaluate_paper(
        {
            "summary_zh": None,
            "abstract_clean": "abstract",
            "identity_status": "unverified",
        }
    ) == ("needs_review", "paper_partial_metadata")


def test_evaluate_paper_low_no_abstract_no_issue() -> None:
    assert evaluate_paper(
        {
            "summary_zh": None,
            "abstract_clean": None,
            "identity_status": "unverified",
        }
    ) == ("needs_review", None)
