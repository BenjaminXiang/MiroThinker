"""W13-D2 option C quality_status promotion rules."""

from __future__ import annotations

from typing import Any, Literal, Mapping, TypeAlias

from src.data_agents.professor.profile_summary_contract import (
    profile_summary_contract_violations,
)

PromotionStatus: TypeAlias = Literal["ready", "needs_review"]
PipelineIssueCode: TypeAlias = Literal[
    "professor_summary_english_dominant",
    "professor_summary_not_chinese",
    "professor_summary_too_short",
    "professor_summary_too_long",
    "company_partial_narrative",
    "company_no_narrative",
    "paper_partial_metadata",
]

_PROFESSOR_CONFIRMED_STATUSES = {"confirmed", "resolved"}


def evaluate_professor(
    row: Mapping[str, Any],
) -> tuple[PromotionStatus, PipelineIssueCode | None]:
    """Evaluate professor W13-D2 promotion status."""
    identity_status = _text(row, "identity_status")
    if identity_status not in _PROFESSOR_CONFIRMED_STATUSES:
        return "needs_review", None

    issue_code = _professor_summary_issue(_text(row, "profile_summary"))
    if issue_code is not None:
        return "needs_review", issue_code
    return "ready", None


def evaluate_company(
    row: Mapping[str, Any],
) -> tuple[PromotionStatus, PipelineIssueCode | None]:
    """Evaluate company W13-D2 promotion status."""
    profile_summary = _text(row, "profile_summary")
    technology_route_summary = _text(row, "technology_route_summary")
    has_profile = bool(profile_summary)
    has_technology_route = bool(technology_route_summary)

    if has_profile and has_technology_route and len(profile_summary) >= 100:
        return "ready", None
    if has_profile or has_technology_route:
        return "needs_review", "company_partial_narrative"
    return "needs_review", "company_no_narrative"


def evaluate_paper(
    row: Mapping[str, Any],
) -> tuple[PromotionStatus, PipelineIssueCode | None]:
    """Evaluate paper W13-D2 promotion status."""
    summary_zh = _text(row, "summary_zh")
    abstract_clean = _text(row, "abstract_clean")
    identity_status = _text(row, "identity_status") or "unverified"

    if len(summary_zh) >= 150 and identity_status == "confirmed":
        return "ready", None
    if abstract_clean:
        return "needs_review", "paper_partial_metadata"
    return "needs_review", None


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _professor_summary_issue(summary: str) -> PipelineIssueCode | None:
    violations = profile_summary_contract_violations(summary)
    if "profile_summary_not_chinese" in violations:
        return "professor_summary_not_chinese"
    if (
        "profile_summary_too_short" in violations
        or "profile_summary_missing" in violations
    ):
        return "professor_summary_too_short"
    if "profile_summary_too_long" in violations:
        return "professor_summary_too_long"
    if "profile_summary_english_dominant" in violations:
        return "professor_summary_english_dominant"
    return None
