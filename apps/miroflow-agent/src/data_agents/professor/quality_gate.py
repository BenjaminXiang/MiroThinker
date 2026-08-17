# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Quality gate for professor records — three-level validation.

L1: Hard blocks (release prevented)
L2: Quality markers (released with status flag)
L3: Statistical alerts (aggregate-level warnings)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Literal

from src.data_agents.contracts import (
    SHENZHEN_INSTITUTION_KEYWORDS,
    QualityStatus,
    normalize_quality_status,
)

from .models import EnrichedProfessorProfile
from .name_selection import is_obvious_non_person_name, looks_like_profile_blob
from .summary_generator import BOILERPLATE_KEYWORDS as SUMMARY_BOILERPLATE_KEYWORDS

_QUALITY_GATE_REFUSAL_KEYWORDS = frozenset(
    {
        "由于您提供的教授信息极度匮乏",
        "无法构建符合您要求",
        "无法构建符合学术规范",
        "无法构建符合学术规范且达到",
        "若需生成符合学术规范",
        "若要生成高质量的学术摘要",
        "请补充以下关键维度信息",
    }
)
BOILERPLATE_KEYWORDS = SUMMARY_BOILERPLATE_KEYWORDS | _QUALITY_GATE_REFUSAL_KEYWORDS
READER_ARTIFACT_MARKERS = ("URL Source:", "Published Time:", "Markdown Content:")
HSS_DEPARTMENT_KEYWORDS = frozenset(
    {
        "法学院",
        "法学",
        "教育学",
        "教育学部",
        "文学",
        "文学院",
        "外语",
        "外国语",
        "历史",
        "哲学",
        "新闻",
        "传播",
        "社会学",
        "人文",
        "马克思主义",
        "艺术",
        "创意设计",
        "设计学院",
    }
)
HSS_PROJECT_KEYWORDS = frozenset(
    {
        "国家社科",
        "社科基金",
        "哲学社会科学",
        "教育部人文",
        "教育部社科",
        "人文社科",
        "教改",
    }
)
HSS_AWARD_KEYWORDS = frozenset(
    {
        "教学成果",
        "哲学社会科学",
        "社科",
        "人文社科",
        "优秀成果",
    }
)

QUALITY_GATE_REPORTED_BY = "professor_quality_gate"

QUALITY_REASON_STAGE: dict[str, str] = {
    "missing_canonical_name": "name_extraction",
    "non_person_name": "name_extraction",
    "missing_official_source": "coverage",
    "reader_artifact_detected": "data_quality_flag",
    "profile_blob_detected": "data_quality_flag",
    "missing_current_institution": "affiliation",
    "missing_title_or_department": "affiliation",
    "missing_research_topic": "research_directions",
    "missing_profile_summary": "coverage",
    "missing_verified_paper_signal": "paper_attribution",
    "identity_unresolved": "identity_gate",
    "same_name_conflict": "identity_gate",
    "field_contradiction": "data_quality_flag",
}

_DISPLAY_ONLY_RULE_IDS = frozenset({"human_override", "external_blocking_issue"})


@dataclass(frozen=True)
class QualityResult:
    passed_l1: bool
    quality_status: QualityStatus
    l1_failures: list[str]
    l2_flags: list[str]
    quality_detail: str | None = None


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ProfessorFactState:
    fact_type: str
    value_raw: str
    source_page_id: str | None = None
    value_normalized: str | None = None
    subtype: str | None = None
    status: str = "active"
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProfessorAffiliationState:
    institution: str
    department: str | None = None
    title: str | None = None
    is_primary: bool = False
    is_current: bool = True
    source_page_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProfessorIssueState:
    stage: str
    reported_by: str
    description: str
    reported_at: datetime | None = None
    resolved: bool = False


@dataclass(frozen=True)
class ProfessorAdminActionState:
    action: Literal["confirm_ready", "send_to_review"]
    observed_data_updated_at: datetime | None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ProfessorCanonicalState:
    professor_id: str
    canonical_name: str | None
    identity_status: str = "resolved"
    primary_official_profile_page_id: str | None = None
    profile_summary: str | None = None
    updated_at: datetime | None = None
    facts: tuple[ProfessorFactState, ...] = ()
    affiliations: tuple[ProfessorAffiliationState, ...] = ()
    open_issues: tuple[ProfessorIssueState, ...] = ()
    aliases: tuple[str, ...] = ()
    official_source_names: tuple[str, ...] = ()
    accepted_identity_names: tuple[str, ...] = ()
    has_paper_candidates: bool = False
    has_verified_paper_link: bool = False


@dataclass(frozen=True)
class ProfessorQualityReason:
    rule_id: str
    severity: Literal["high", "medium", "low"]
    description: str
    stage: str | None
    persist: bool = True


@dataclass(frozen=True)
class ProfessorQualityEvaluation:
    quality_status: QualityStatus
    reasons: tuple[ProfessorQualityReason, ...]
    canonical_watermark: datetime | None = None


@dataclass(frozen=True)
class ProfessorQualityPersistenceReport:
    professor_id: str
    quality_status: QualityStatus
    issues_inserted: int
    issues_resolved: int


@dataclass(frozen=True)
class QualityReport:
    total_count: int
    released_count: int
    blocked_count: int
    ready_count: int
    needs_review_count: int
    low_confidence_count: int
    needs_enrichment_count: int
    legacy_breakdown: dict[str, int]
    alerts: list[str]

    @property
    def incomplete_count(self) -> int:
        return self.legacy_breakdown.get("incomplete", 0)

    @property
    def shallow_summary_count(self) -> int:
        return self.legacy_breakdown.get("shallow_summary", 0)


def evaluate_professor_quality(
    canonical_state: ProfessorCanonicalState,
    *,
    latest_admin_action: ProfessorAdminActionState | None = None,
) -> ProfessorQualityEvaluation:
    """Evaluate persisted professor canonical state without reading or writing SQL."""
    watermark = _canonical_watermark(canonical_state)
    if _admin_override_is_fresh(latest_admin_action, watermark):
        override_status: QualityStatus = (
            "ready"
            if latest_admin_action and latest_admin_action.action == "confirm_ready"
            else "needs_review"
        )
        return ProfessorQualityEvaluation(
            quality_status=override_status,
            reasons=(
                _quality_reason(
                    "human_override",
                    severity="medium",
                    persist=False,
                    description="fresh human admin override",
                ),
            ),
            canonical_watermark=watermark,
        )

    reasons: list[ProfessorQualityReason] = []

    reasons.extend(_needs_review_reasons(canonical_state))
    reasons.extend(_low_confidence_reasons(canonical_state))
    reasons.extend(_enrichment_reasons(canonical_state))

    reason_ids = {reason.rule_id for reason in reasons}
    if any(_is_needs_review_reason(reason.rule_id) for reason in reasons):
        status: QualityStatus = "needs_review"
    elif any(_is_low_confidence_reason(reason.rule_id) for reason in reasons):
        status = "low_confidence"
    elif not reason_ids:
        status = "ready"
    else:
        status = "needs_enrichment"

    return ProfessorQualityEvaluation(
        quality_status=status,
        reasons=tuple(reasons),
        canonical_watermark=watermark,
    )


def load_professor_canonical_state(
    conn,
    professor_id: str,
) -> ProfessorCanonicalState:
    """Load the persisted canonical state required by the pure evaluator."""
    professor_row = conn.execute(
        """
        SELECT
            professor_id,
            canonical_name,
            identity_status,
            primary_official_profile_page_id::text,
            profile_summary,
            updated_at
        FROM professor
        WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if professor_row is None:
        raise ValueError(f"professor not found: {professor_id}")

    facts = tuple(
        ProfessorFactState(
            fact_type=_row_value(row, "fact_type", 0),
            value_raw=_row_value(row, "value_raw", 1),
            value_normalized=_row_value(row, "value_normalized", 2),
            source_page_id=_row_value(row, "source_page_id", 3),
            status=_row_value(row, "status", 4) or "active",
            updated_at=_row_value(row, "updated_at", 5),
        )
        for row in conn.execute(
            """
            SELECT
                fact_type,
                value_raw,
                value_normalized,
                source_page_id::text,
                status,
                updated_at
            FROM professor_fact
            WHERE professor_id = %s
            """,
            (professor_id,),
        ).fetchall()
    )
    affiliations = tuple(
        ProfessorAffiliationState(
            institution=_row_value(row, "institution", 0),
            department=_row_value(row, "department", 1),
            title=_row_value(row, "title", 2),
            is_primary=bool(_row_value(row, "is_primary", 3)),
            is_current=bool(_row_value(row, "is_current", 4)),
            source_page_id=_row_value(row, "source_page_id", 5),
            updated_at=_row_value(row, "updated_at", 6),
        )
        for row in conn.execute(
            """
            SELECT
                institution,
                department,
                title,
                is_primary,
                is_current,
                source_page_id::text,
                updated_at
            FROM professor_affiliation
            WHERE professor_id = %s
            """,
            (professor_id,),
        ).fetchall()
    )
    open_issues = tuple(
        ProfessorIssueState(
            stage=_row_value(row, "stage", 0),
            reported_by=_row_value(row, "reported_by", 1),
            description=_row_value(row, "description", 2),
            reported_at=_row_value(row, "reported_at", 3),
            resolved=bool(_row_value(row, "resolved", 4)),
        )
        for row in conn.execute(
            """
            SELECT stage, reported_by, description, reported_at, resolved
            FROM pipeline_issue
            WHERE professor_id = %s
              AND resolved = false
            """,
            (professor_id,),
        ).fetchall()
    )
    paper_signal_row = conn.execute(
        """
        SELECT
            EXISTS (
                SELECT 1
                FROM professor_paper_link
                WHERE professor_id = %s
            ) AS has_paper_candidates,
            EXISTS (
                SELECT 1
                FROM professor_paper_link
                WHERE professor_id = %s
                  AND link_status = 'verified'
            ) AS has_verified_paper_link
        """,
        (professor_id, professor_id),
    ).fetchone()

    return ProfessorCanonicalState(
        professor_id=_row_value(professor_row, "professor_id", 0),
        canonical_name=_row_value(professor_row, "canonical_name", 1),
        identity_status=_row_value(professor_row, "identity_status", 2),
        primary_official_profile_page_id=_row_value(
            professor_row,
            "primary_official_profile_page_id",
            3,
        ),
        profile_summary=_row_value(professor_row, "profile_summary", 4),
        updated_at=_row_value(professor_row, "updated_at", 5),
        facts=facts,
        affiliations=affiliations,
        open_issues=open_issues,
        has_paper_candidates=bool(_row_value(paper_signal_row, "has_paper_candidates", 0)),
        has_verified_paper_link=bool(
            _row_value(paper_signal_row, "has_verified_paper_link", 1)
        ),
    )


def persist_professor_quality_evaluation(
    conn,
    *,
    professor_id: str,
    evaluation: ProfessorQualityEvaluation,
) -> ProfessorQualityPersistenceReport:
    """Persist professor quality_status and quality-gate-authored issue rows."""
    conn.execute(
        """
        UPDATE professor
           SET quality_status = %s,
               updated_at = now()
         WHERE professor_id = %s
           AND quality_status IS DISTINCT FROM %s
        """,
        (evaluation.quality_status, professor_id, evaluation.quality_status),
    )

    existing_rows = _fetch_open_quality_gate_issues(conn, professor_id)
    existing_descriptions = {
        _row_value(row, "description", 1) for row in existing_rows
    }
    current_descriptions: set[str] = set()
    inserted = 0
    for reason in evaluation.reasons:
        if not reason.persist:
            continue
        description = _pipeline_issue_description(reason)
        current_descriptions.add(description)
        if description in existing_descriptions:
            continue
        cursor = conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                stage,
                severity,
                description,
                evidence_snapshot,
                reported_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                professor_id,
                reason.stage,
                reason.severity,
                description,
                _jsonb_payload(
                    {
                        "rule_id": reason.rule_id,
                        "quality_status": evaluation.quality_status,
                    }
                ),
                QUALITY_GATE_REPORTED_BY,
            ),
        )
        inserted += int(getattr(cursor, "rowcount", 1) or 0)

    resolved = 0
    for row in existing_rows:
        issue_id = _row_value(row, "issue_id", 0)
        description = _row_value(row, "description", 1)
        if description in current_descriptions:
            continue
        conn.execute(
            """
            UPDATE pipeline_issue
               SET resolved = true,
                   resolved_at = now(),
                   resolution_notes = %s,
                   resolution_round = %s
             WHERE issue_id = %s
               AND reported_by = %s
               AND resolved = false
            """,
            (
                "quality gate stale reason cleared",
                "prof-quality-status-rework",
                issue_id,
                QUALITY_GATE_REPORTED_BY,
            ),
        )
        resolved += 1

    return ProfessorQualityPersistenceReport(
        professor_id=professor_id,
        quality_status=evaluation.quality_status,
        issues_inserted=inserted,
        issues_resolved=resolved,
    )


def _row_value(row, key: str, index: int):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]


def _fetch_open_quality_gate_issues(
    conn,
    professor_id: str,
):
    return conn.execute(
        """
        SELECT issue_id, description
        FROM pipeline_issue
        WHERE professor_id = %s
          AND reported_by = %s
          AND resolved = false
        """,
        (professor_id, QUALITY_GATE_REPORTED_BY),
    ).fetchall()


def _pipeline_issue_description(reason: ProfessorQualityReason) -> str:
    return f"{reason.rule_id}: {reason.description}"


def _jsonb_payload(payload: dict[str, str]):
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return payload
    return Jsonb(payload)


def _quality_reason(
    rule_id: str,
    *,
    severity: Literal["high", "medium", "low"],
    description: str,
    persist: bool = True,
) -> ProfessorQualityReason:
    return ProfessorQualityReason(
        rule_id=rule_id,
        severity=severity,
        description=description,
        stage=None if rule_id in _DISPLAY_ONLY_RULE_IDS else QUALITY_REASON_STAGE[rule_id],
        persist=persist and rule_id not in _DISPLAY_ONLY_RULE_IDS,
    )


def _needs_review_reasons(
    state: ProfessorCanonicalState,
) -> list[ProfessorQualityReason]:
    reasons: list[ProfessorQualityReason] = []
    if (state.identity_status or "").strip() != "resolved":
        reasons.append(
            _quality_reason(
                "identity_unresolved",
                severity="high",
                description="identity_status is not resolved",
            )
        )

    if _has_same_name_conflict(state):
        reasons.append(
            _quality_reason(
                "same_name_conflict",
                severity="high",
                description="canonical name conflicts with accepted identity names",
            )
        )

    if _has_field_contradiction(state):
        reasons.append(
            _quality_reason(
                "field_contradiction",
                severity="high",
                description="active canonical fields contain a machine-detectable contradiction",
            )
        )

    if _external_open_issues(state):
        reasons.append(
            _quality_reason(
                "external_blocking_issue",
                severity="high",
                persist=False,
                description="external open pipeline_issue blocks quality evaluation",
            )
        )
    return reasons


def _low_confidence_reasons(
    state: ProfessorCanonicalState,
) -> list[ProfessorQualityReason]:
    reasons: list[ProfessorQualityReason] = []
    canonical_name = _clean_state_text(state.canonical_name)
    if canonical_name and (
        is_obvious_non_person_name(canonical_name)
        or looks_like_profile_blob(canonical_name)
    ):
        reasons.append(
            _quality_reason(
                "non_person_name",
                severity="high",
                description="canonical_name does not look like a person name",
            )
        )
    if canonical_name and looks_like_profile_blob(canonical_name):
        reasons.append(
            _quality_reason(
                "profile_blob_detected",
                severity="medium",
                description="canonical_name looks like a copied profile blob",
            )
        )
    if not state.primary_official_profile_page_id:
        reasons.append(
            _quality_reason(
                "missing_official_source",
                severity="medium",
                description="no official source page is linked to this professor",
            )
        )
    if _state_has_reader_artifact(state):
        reasons.append(
            _quality_reason(
                "reader_artifact_detected",
                severity="medium",
                description="reader extraction artifact appears in canonical fields",
            )
        )
    return _dedupe_reasons(reasons)


def _enrichment_reasons(
    state: ProfessorCanonicalState,
) -> list[ProfessorQualityReason]:
    reasons: list[ProfessorQualityReason] = []
    if not _clean_state_text(state.canonical_name):
        reasons.append(
            _quality_reason(
                "missing_canonical_name",
                severity="high",
                description="canonical_name is missing",
            )
        )

    current_affiliations = _current_affiliations(state)
    if not any(_clean_state_text(affiliation.institution) for affiliation in current_affiliations):
        reasons.append(
            _quality_reason(
                "missing_current_institution",
                severity="medium",
                description="no current institution is present",
            )
        )
    if not any(
        _clean_state_text(affiliation.title)
        or _clean_state_text(affiliation.department)
        for affiliation in current_affiliations
    ):
        reasons.append(
            _quality_reason(
                "missing_title_or_department",
                severity="medium",
                description="no current title or department is present",
            )
        )

    if not any(
        fact.fact_type == "research_topic"
        and fact.status == "active"
        and _clean_state_text(fact.value_raw)
        for fact in state.facts
    ):
        reasons.append(
            _quality_reason(
                "missing_research_topic",
                severity="medium",
                description="no active research_topic fact is present",
            )
        )

    if not _clean_state_text(state.profile_summary):
        reasons.append(
            _quality_reason(
                "missing_profile_summary",
                severity="medium",
                description="profile_summary is missing",
            )
        )

    if state.has_paper_candidates and not state.has_verified_paper_link:
        reasons.append(
            _quality_reason(
                "missing_verified_paper_signal",
                severity="medium",
                description="paper candidates exist but no verified professor-paper signal exists",
            )
        )
    return _dedupe_reasons(reasons)


def _is_needs_review_reason(rule_id: str) -> bool:
    return rule_id in {
        "identity_unresolved",
        "same_name_conflict",
        "field_contradiction",
        "external_blocking_issue",
    }


def _is_low_confidence_reason(rule_id: str) -> bool:
    return rule_id in {
        "non_person_name",
        "missing_official_source",
        "reader_artifact_detected",
        "profile_blob_detected",
    }


def _external_open_issues(
    state: ProfessorCanonicalState,
) -> tuple[ProfessorIssueState, ...]:
    return tuple(
        issue
        for issue in state.open_issues
        if not issue.resolved and issue.reported_by != QUALITY_GATE_REPORTED_BY
    )


def _canonical_watermark(state: ProfessorCanonicalState) -> datetime | None:
    values: list[datetime] = []
    if state.updated_at is not None:
        values.append(state.updated_at)
    values.extend(fact.updated_at for fact in state.facts if fact.updated_at is not None)
    values.extend(
        affiliation.updated_at
        for affiliation in state.affiliations
        if affiliation.updated_at is not None
    )
    values.extend(
        issue.reported_at
        for issue in _external_open_issues(state)
        if issue.reported_at is not None
    )
    return max(values) if values else None


def _admin_override_is_fresh(
    action: ProfessorAdminActionState | None,
    watermark: datetime | None,
) -> bool:
    if action is None or action.action not in {"confirm_ready", "send_to_review"}:
        return False
    if action.observed_data_updated_at is None:
        return False
    if watermark is None:
        return True
    return _coerce_aware(action.observed_data_updated_at) >= _coerce_aware(watermark)


def _coerce_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _has_same_name_conflict(state: ProfessorCanonicalState) -> bool:
    names = (
        (state.canonical_name,)
        + state.official_source_names
        + state.accepted_identity_names
    )
    normalized = {
        _normalize_identity_text(name)
        for name in names
        if _normalize_identity_text(name)
    }
    return len(normalized) > 1


def _has_field_contradiction(state: ProfessorCanonicalState) -> bool:
    return any(
        (
            _has_multiple_primary_current_institutions(state),
            _has_conflicting_contact_facts(state),
            _has_contradictory_title_department_pair(state),
        )
    )


def _has_multiple_primary_current_institutions(
    state: ProfessorCanonicalState,
) -> bool:
    institutions = {
        _normalize_identity_text(affiliation.institution)
        for affiliation in state.affiliations
        if affiliation.is_current
        and affiliation.is_primary
        and _normalize_identity_text(affiliation.institution)
    }
    return len(institutions) > 1


def _has_conflicting_contact_facts(state: ProfessorCanonicalState) -> bool:
    by_key: dict[tuple[str | None, str | None], set[str]] = {}
    for fact in state.facts:
        if fact.status != "active" or fact.fact_type != "contact":
            continue
        if fact.subtype not in {"primary_email", "official_homepage"}:
            continue
        key = (fact.source_page_id, fact.subtype)
        value = _normalize_identity_text(fact.value_normalized or fact.value_raw)
        if not value:
            continue
        by_key.setdefault(key, set()).add(value)
    return any(len(values) > 1 for values in by_key.values())


def _has_contradictory_title_department_pair(
    state: ProfessorCanonicalState,
) -> bool:
    for affiliation in _current_affiliations(state):
        title = _clean_state_text(affiliation.title)
        department = _clean_state_text(affiliation.department)
        if not title or not department:
            continue
        if _looks_like_title(department) and _normalize_identity_text(
            title
        ) != _normalize_identity_text(department):
            return True
    return False


def _current_affiliations(
    state: ProfessorCanonicalState,
) -> tuple[ProfessorAffiliationState, ...]:
    return tuple(affiliation for affiliation in state.affiliations if affiliation.is_current)


def _state_has_reader_artifact(state: ProfessorCanonicalState) -> bool:
    values: list[str | None] = [state.canonical_name, state.profile_summary]
    for affiliation in state.affiliations:
        values.extend([affiliation.title, affiliation.department])
    return any(
        marker in (value or "")
        for value in values
        for marker in READER_ARTIFACT_MARKERS
    )


def _clean_state_text(value: str | None) -> str:
    return (value or "").strip()


def _normalize_identity_text(value: str | None) -> str:
    text = _clean_state_text(value).lower()
    if not text:
        return ""
    return re.sub(r"[\s,，.。;；:：()（）/|\\]+", "", text).replace("-", "")


def _looks_like_title(value: str) -> bool:
    normalized = _clean_state_text(value)
    return normalized in {
        "教授",
        "副教授",
        "讲师",
        "助理教授",
        "研究员",
        "副研究员",
        "院士",
        "博士后",
    }


def _dedupe_reasons(
    reasons: list[ProfessorQualityReason],
) -> list[ProfessorQualityReason]:
    seen: set[str] = set()
    deduped: list[ProfessorQualityReason] = []
    for reason in reasons:
        if reason.rule_id in seen:
            continue
        seen.add(reason.rule_id)
        deduped.append(reason)
    return deduped


def evaluate_quality(
    profile: EnrichedProfessorProfile,
    *,
    shenzhen_keywords: tuple[str, ...] = SHENZHEN_INSTITUTION_KEYWORDS,
) -> QualityResult:
    l1_failures: list[str] = []
    l2_flags: list[str] = []

    # L1 — hard blocks
    if not profile.name or not profile.name.strip():
        l1_failures.append("name_empty")
    elif is_obvious_non_person_name(profile.name) or looks_like_profile_blob(
        profile.name
    ):
        l1_failures.append("name_not_person")

    if not profile.institution or not profile.institution.strip():
        l1_failures.append("institution_empty")
    elif not any(kw in profile.institution for kw in shenzhen_keywords):
        l1_failures.append("institution_not_shenzhen")

    if not any(
        url
        for url in profile.evidence_urls
        if _is_likely_official(url, shenzhen_keywords)
    ):
        l1_failures.append("missing_official_evidence")

    if not has_minimum_academic_signal(profile):
        l1_failures.append("insufficient_academic_signal")

    if _has_reader_artifact(profile):
        l1_failures.append("reader_artifact_detected")

    summary = profile.profile_summary
    if not summary:
        l1_failures.append("summary_missing")
    else:
        summary_length = _check_profile_summary_length(profile)
        if not summary_length.passed and summary_length.code:
            l1_failures.append(summary_length.code)
        summary_boilerplate = _check_profile_summary_boilerplate(profile)
        if not summary_boilerplate.passed and summary_boilerplate.code:
            l1_failures.append(summary_boilerplate.code)

    passed_l1 = len(l1_failures) == 0

    # L2 — quality markers
    if summary and (len(summary) < 200 or len(summary) > 300):
        l2_flags.append("summary_length_suboptimal")

    if not profile.research_directions:
        l2_flags.append("incomplete")

    if (
        summary
        and len(summary) >= 200
        and not _has_specific_research_terms(summary, profile.research_directions)
    ):
        l2_flags.append("shallow_summary")

    if not has_scholarly_output_signal(profile):
        l2_flags.append("needs_enrichment")

    quality_status: QualityStatus = "ready"
    quality_detail: str | None = None
    if not passed_l1:
        quality_status = "low_confidence"
        quality_detail = "low_confidence"
        if "name_not_person" in l1_failures:
            quality_detail = "low_confidence"
    elif l2_flags:
        # Canonical priority: needs_enrichment > needs_review(shallow/incomplete).
        if "needs_enrichment" in l2_flags:
            quality_status = "needs_enrichment"
            quality_detail = "needs_enrichment"
        elif "incomplete" in l2_flags:
            quality_status = "needs_review"
            quality_detail = "incomplete"
        else:
            quality_status = "needs_review"
            quality_detail = "shallow_summary"

    return QualityResult(
        passed_l1=passed_l1,
        quality_status=quality_status,
        l1_failures=l1_failures,
        l2_flags=l2_flags,
        quality_detail=quality_detail,
    )


def _check_profile_summary_length(
    profile: EnrichedProfessorProfile,
    *,
    min_length: int = 150,
) -> CheckResult:
    text = (profile.profile_summary or "").strip()
    if len(text) < min_length:
        return CheckResult(
            passed=False,
            code="profile_summary_too_short",
            message=f"profile_summary length {len(text)} < {min_length}",
        )
    return CheckResult(passed=True)


def _check_profile_summary_boilerplate(
    profile: EnrichedProfessorProfile,
) -> CheckResult:
    text = profile.profile_summary or ""
    for keyword in BOILERPLATE_KEYWORDS:
        if keyword in text:
            return CheckResult(
                passed=False,
                code="profile_summary_boilerplate",
                message=f"contains banned phrase: {keyword}",
            )
    return CheckResult(passed=True)


def build_quality_report(
    results: list[tuple[EnrichedProfessorProfile, QualityResult]],
) -> QualityReport:
    total = len(results)
    released = sum(1 for _, qr in results if qr.passed_l1)
    blocked = total - released

    ready = 0
    needs_review = 0
    low_confidence = 0
    needs_enrichment = 0
    legacy_breakdown = {
        "ready": 0,
        "incomplete": 0,
        "shallow_summary": 0,
        "needs_enrichment": 0,
        "needs_review": 0,
        "low_confidence": 0,
    }
    for _, qr in results:
        if not qr.passed_l1:
            canonical_status = normalize_quality_status(qr.quality_status)
            if canonical_status == "low_confidence":
                low_confidence += 1
                legacy_breakdown["low_confidence"] += 1
            continue
        canonical_status = normalize_quality_status(qr.quality_status)
        if canonical_status == "ready":
            ready += 1
        elif canonical_status == "needs_review":
            needs_review += 1
        elif canonical_status == "low_confidence":
            low_confidence += 1
        elif canonical_status == "needs_enrichment":
            needs_enrichment += 1

        legacy_key = qr.quality_detail or str(qr.quality_status)
        if legacy_key in legacy_breakdown:
            legacy_breakdown[legacy_key] += 1

    alerts: list[str] = []
    if released > 0 and ready / released < 0.7:
        alerts.append(
            f"ready_ratio_low: {ready}/{released} = {ready / released:.1%} < 70%"
        )

    # Per-institution coverage alert
    institution_counts: dict[str, int] = {}
    for profile, qr in results:
        inst = profile.institution
        if inst:
            institution_counts[inst] = institution_counts.get(inst, 0) + 1
    for inst, count in institution_counts.items():
        released_for_inst = sum(
            1 for p, qr in results if p.institution == inst and qr.passed_l1
        )
        if count > 0 and released_for_inst / count < 0.8:
            alerts.append(
                f"low_release_rate:{inst}: {released_for_inst}/{count} = "
                f"{released_for_inst / count:.1%}"
            )

    return QualityReport(
        total_count=total,
        released_count=released,
        blocked_count=blocked,
        ready_count=ready,
        needs_review_count=needs_review,
        low_confidence_count=low_confidence,
        needs_enrichment_count=needs_enrichment,
        legacy_breakdown=legacy_breakdown,
        alerts=alerts,
    )


def _is_likely_official(url: str, institution_keywords: tuple[str, ...]) -> bool:
    """Heuristic: URL contains .edu.cn or institution-related domain."""
    url_lower = url.lower()
    if ".edu.cn" in url_lower:
        return True
    if ".ac.cn" in url_lower:
        return True
    return False


def _has_specific_research_terms(
    summary: str,
    directions: list[str],
) -> bool:
    """Check if summary contains at least one specific research term."""
    if not directions:
        return False
    normalized_summary = _normalize_term_text(summary)
    if not normalized_summary:
        return False
    for direction in directions:
        normalized_direction = _normalize_term_text(direction)
        if not normalized_direction:
            continue
        if normalized_direction in normalized_summary:
            return True
        for token in _extract_research_term_tokens(normalized_direction):
            if token in normalized_summary:
                return True
    return False


def _normalize_term_text(value: str) -> str:
    return (
        value.strip()
        .replace("（", "(")
        .replace("）", ")")
        .replace("：", ":")
        .replace("，", ",")
        .replace("；", ";")
        .replace("　", " ")
    )


def _extract_research_term_tokens(direction: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[、,，;；/()（）:：]+", direction):
        normalized = chunk.strip()
        if not normalized:
            continue
        parts.append(normalized)
        parts.extend(
            piece.strip()
            for piece in re.split(r"[的与及和]", normalized)
            if piece.strip()
        )

    seen: set[str] = set()
    tokens: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        cjk_length = len(re.findall(r"[\u4e00-\u9fff]", part))
        ascii_length = len(re.findall(r"[A-Za-z0-9+\-]", part))
        if cjk_length >= 4 or ascii_length >= 3:
            tokens.append(part)
    return tokens


def _has_paper_signal(profile: EnrichedProfessorProfile) -> bool:
    has_top_papers = len(profile.top_papers) > 0
    has_paper_count = (profile.paper_count or 0) > 0
    return has_top_papers or has_paper_count


def has_minimum_academic_signal(profile: EnrichedProfessorProfile) -> bool:
    return any(
        (
            bool((profile.title or "").strip()),
            bool((profile.department or "").strip()),
            bool(profile.research_directions),
            has_scholarly_output_signal(profile),
            bool(profile.awards),
            bool(profile.academic_positions),
            bool(profile.education_structured),
            bool(profile.work_experience),
        )
    )


def has_scholarly_output_signal(profile: EnrichedProfessorProfile) -> bool:
    if _has_paper_signal(profile):
        return True
    if not _is_hss_profile(profile):
        return False
    return _has_hss_project_signal(profile.projects) or _has_hss_award_signal(
        profile.awards
    )


def _is_hss_profile(profile: EnrichedProfessorProfile) -> bool:
    department = (profile.department or "").strip()
    if not department:
        return False
    return any(keyword in department for keyword in HSS_DEPARTMENT_KEYWORDS)


def _has_hss_project_signal(projects: list[str]) -> bool:
    return any(
        keyword in project for project in projects for keyword in HSS_PROJECT_KEYWORDS
    )


def _has_hss_award_signal(awards: list[str]) -> bool:
    return any(keyword in award for award in awards for keyword in HSS_AWARD_KEYWORDS)


def _has_reader_artifact(profile: EnrichedProfessorProfile) -> bool:
    candidate_values = (
        profile.name,
        profile.name_en,
        profile.title,
        profile.profile_summary,
    )
    return any(
        marker in (value or "")
        for value in candidate_values
        for marker in READER_ARTIFACT_MARKERS
    )
