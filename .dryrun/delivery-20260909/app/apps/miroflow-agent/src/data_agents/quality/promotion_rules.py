"""W13-D2 option C quality_status promotion rules."""

from __future__ import annotations

from typing import Any, Mapping, TypeAlias

from src.data_agents.company.canonical_import import _evaluate_xlsx_baseline_readiness
from src.data_agents.contracts import QualityStatus
from src.data_agents.paper.quality_promotion import (
    NEEDS_ENRICHMENT,
    PaperEnrichmentSignals,
    evaluate_paper_promotion,
)
from src.data_agents.patent.quality_promotion import (
    PatentEnrichmentSignals,
    evaluate_patent_promotion,
)
from src.data_agents.professor.quality_gate import (
    ProfessorAffiliationState,
    ProfessorCanonicalState,
    ProfessorFactState,
    SourcePageState,
    evaluate_professor_quality,
)
from src.data_agents.professor.profile_summary_contract import (
    profile_summary_contract_violations,
)

PromotionStatus: TypeAlias = QualityStatus
PipelineIssueCode: TypeAlias = str

_PROFESSOR_CONFIRMED_STATUSES = {"confirmed", "resolved"}


def evaluate_professor(
    row: Mapping[str, Any],
) -> tuple[PromotionStatus, PipelineIssueCode | None]:
    """Evaluate professor promotion by delegating to the canonical gate."""
    state = _professor_state(row)
    evaluation = evaluate_professor_quality(state)
    return evaluation.quality_status, _professor_issue(row, evaluation.quality_status)


def evaluate_company(
    row: Mapping[str, Any],
) -> tuple[PromotionStatus, PipelineIssueCode | None]:
    """Evaluate company promotion using the existing write-time readiness path."""
    if _has_company_baseline_fields(row):
        readiness = _evaluate_xlsx_baseline_readiness(
            {
                "company_name_xlsx": _first_text(
                    row,
                    "company_name_xlsx",
                    "registered_name",
                    "canonical_name",
                    "company_name",
                ),
                "industry": _first_text(row, "industry", "sub_industry"),
                "description": _first_text(row, "description", "profile_summary"),
                "business": _text(row, "business"),
                "project_name": _text(row, "project_name"),
            },
            identity_status=_text(row, "identity_status") or "resolved",
            has_latest_snapshot=not _truthy(row.get("missing_latest_snapshot")),
        )
        return readiness.quality_status, _company_issue_from_blockers(
            readiness.blockers
        )

    # No company write-time state machine exists for the legacy narrative batch
    # rows, so preserve the prior batch issue classification for that shape.
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
    """Evaluate paper promotion by delegating to the canonical state machine."""
    current_status = _text(row, "quality_status") or "needs_review"
    decision = evaluate_paper_promotion(
        current_status=current_status,
        signals=PaperEnrichmentSignals(
            has_title=bool(_first_text(row, "title_clean", "title")),
            has_year=row.get("year") is not None,
            has_venue=bool(_text(row, "venue")),
            has_authors=bool(_first_text(row, "authors_display", "authors")),
            has_abstract=bool(_text(row, "abstract_clean")),
            has_summary_zh=bool(_text(row, "summary_zh")),
            summary_zh_boilerplate_rejected=_truthy(
                row.get("summary_zh_boilerplate_rejected")
            ),
        ),
    )
    issue_code = None
    if decision.next_status != "ready" and _text(row, "abstract_clean"):
        issue_code = "paper_partial_metadata"
    return decision.next_status, issue_code


def evaluate_patent(
    row: Mapping[str, Any],
) -> tuple[PromotionStatus, PipelineIssueCode | None]:
    """Evaluate patent promotion by delegating to the canonical state machine."""
    decision = evaluate_patent_promotion(
        current_status=_text(row, "quality_status") or NEEDS_ENRICHMENT,
        signals=PatentEnrichmentSignals(
            has_patent_number=bool(_first_text(row, "patent_number", "publication_no")),
            has_title=bool(_first_text(row, "title_clean", "title")),
            has_patent_type=bool(_text(row, "patent_type")),
            has_any_date=bool(
                row.get("filing_date")
                or row.get("grant_date")
                or row.get("publication_date")
            ),
            has_applicants_or_inventors=bool(
                row.get("applicants_parsed")
                or row.get("inventors_parsed")
                or _text(row, "applicants_display")
                or _text(row, "inventors_display")
            ),
            xlsx_merged=_truthy(row.get("xlsx_merged")),
        ),
    )
    return decision.next_status, None


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row, key)
        if value:
            return value
    return ""


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def _professor_state(row: Mapping[str, Any]) -> ProfessorCanonicalState:
    identity_status = _text(row, "identity_status")
    if identity_status == "confirmed":
        identity_status = "resolved"
    return ProfessorCanonicalState(
        professor_id=_first_text(row, "professor_id", "id") or "batch_professor",
        canonical_name=_first_text(row, "canonical_name", "name") or "batch professor",
        identity_status=identity_status or "resolved",
        profile_summary=_text(row, "profile_summary"),
        primary_official_profile_page_id="batch_official_source",
        source_pages=(
            SourcePageState(
                page_id="batch_official_source",
                url=_text(row, "official_source_url") or "batch://official-source",
                is_official_source=True,
            ),
        ),
        affiliations=(
            ProfessorAffiliationState(
                institution=_text(row, "institution") or "batch institution",
                department=_text(row, "department") or "batch department",
                title=_text(row, "title") or "batch title",
                is_primary=True,
            ),
        ),
        facts=(
            ProfessorFactState(
                fact_type="research_topic",
                value_raw=_first_text(row, "research_topic", "research_directions")
                or "batch research topic",
            ),
        ),
    )


def _professor_issue(
    row: Mapping[str, Any],
    quality_status: str,
) -> PipelineIssueCode | None:
    if quality_status == "ready":
        return None
    if _text(row, "identity_status") not in _PROFESSOR_CONFIRMED_STATUSES:
        return None
    return _professor_summary_issue(_text(row, "profile_summary"))


def _has_company_baseline_fields(row: Mapping[str, Any]) -> bool:
    return any(
        _text(row, key)
        for key in (
            "company_name_xlsx",
            "registered_name",
            "canonical_name",
            "company_name",
            "industry",
            "sub_industry",
            "description",
            "business",
            "project_name",
        )
    )


def _company_issue_from_blockers(
    blockers: tuple[str, ...],
) -> PipelineIssueCode | None:
    if not blockers:
        return None
    if "missing_meaningful_baseline_field" in blockers:
        return "company_no_narrative"
    return blockers[0]


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
