# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Quality gate for professor records — three-level validation.

L1: Hard blocks (release prevented)
L2: Quality markers (released with status flag)
L3: Statistical alerts (aggregate-level warnings)
"""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
import json
import re

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

PROFESSOR_QUALITY_GATE_REPORTER = "professor_quality_gate"
PROFESSOR_QUALITY_STATUSES = frozenset(
    {"ready", "needs_enrichment", "low_confidence", "needs_review"}
)
PROFESSOR_QUALITY_STAGE_BY_RULE_ID = {
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


@dataclass(frozen=True, slots=True)
class ProfessorAffiliationState:
    institution: str | None
    is_current: bool = True
    is_primary: bool = True
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProfessorContactFact:
    subtype: str
    value: str
    source_page_id: str | None
    is_active: bool = True
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProfessorIssueSignal:
    stage: str
    reported_by: str
    reported_at: datetime | None = None
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class ProfessorAdminAction:
    action: str
    observed_data_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProfessorCanonicalState:
    professor_id: str
    canonical_name: str | None
    identity_status: str | None
    current_institution: str | None
    title: str | None
    department: str | None
    research_topics: tuple[str, ...] = ()
    profile_summary: str | None = None
    has_official_source: bool = False
    has_paper_candidates: bool = False
    has_verified_paper_signal: bool = False
    same_name_conflict: bool = False
    non_person_name: bool = False
    reader_artifact_detected: bool = False
    profile_blob_detected: bool = False
    title_department_conflict: bool = False
    affiliations: tuple[ProfessorAffiliationState, ...] = ()
    contact_facts: tuple[ProfessorContactFact, ...] = ()
    open_issues: tuple[ProfessorIssueSignal, ...] = ()
    canonical_watermark: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProfessorQualityReason:
    rule_id: str
    stage: str | None
    message: str
    persist_issue: bool = True


@dataclass(frozen=True, slots=True)
class ProfessorQualityEvaluation:
    quality_status: str
    reasons: tuple[ProfessorQualityReason, ...]


def evaluate_professor_quality(
    state: ProfessorCanonicalState,
    *,
    latest_admin_action: ProfessorAdminAction | None = None,
) -> ProfessorQualityEvaluation:
    """Evaluate professor quality from persisted canonical state.

    This pure evaluator is the professor-domain four-state contract used
    by canonical writes and standalone re-evaluation. It intentionally
    ignores quality-gate-authored issues when detecting external
    blocking issues, preventing the gate from blocking itself.
    """
    watermark = _canonical_watermark(state)
    if _admin_action_is_fresh(latest_admin_action, watermark):
        if latest_admin_action and latest_admin_action.action == "confirm_ready":
            return ProfessorQualityEvaluation(
                quality_status="ready",
                reasons=(
                    ProfessorQualityReason(
                        rule_id="human_override",
                        stage=None,
                        message="fresh admin confirm_ready override",
                        persist_issue=False,
                    ),
                ),
            )
        if latest_admin_action and latest_admin_action.action == "send_to_review":
            return ProfessorQualityEvaluation(
                quality_status="needs_review",
                reasons=(
                    ProfessorQualityReason(
                        rule_id="human_override",
                        stage=None,
                        message="fresh admin send_to_review override",
                        persist_issue=False,
                    ),
                ),
            )

    anomaly_reasons = _needs_review_reasons(state)
    low_confidence_reasons = _low_confidence_reasons(state)
    enrichment_reasons = _needs_enrichment_reasons(state)

    reasons = anomaly_reasons + low_confidence_reasons + enrichment_reasons
    if anomaly_reasons:
        status = "needs_review"
    elif low_confidence_reasons:
        status = "low_confidence"
    elif not enrichment_reasons:
        status = "ready"
    else:
        status = "needs_enrichment"

    return ProfessorQualityEvaluation(
        quality_status=status,
        reasons=tuple(reasons),
    )


def load_professor_canonical_state(conn, professor_id: str) -> ProfessorCanonicalState:
    professor_row = conn.execute(
        """
        SELECT professor_id,
               canonical_name,
               identity_status,
               primary_official_profile_page_id,
               profile_summary,
               updated_at
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if professor_row is None:
        raise ValueError(f"Professor not found: {professor_id}")

    affiliation_rows = conn.execute(
        """
        SELECT institution,
               department,
               title,
               is_current,
               is_primary,
               updated_at
          FROM professor_affiliation
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchall()
    fact_rows = conn.execute(
        """
        SELECT fact_type,
               value_raw,
               source_page_id,
               updated_at
          FROM professor_fact
         WHERE professor_id = %s
           AND status = 'active'
        """,
        (professor_id,),
    ).fetchall()
    issue_rows = conn.execute(
        """
        SELECT stage,
               reported_by,
               reported_at,
               resolved
          FROM pipeline_issue
         WHERE professor_id = %s
           AND resolved = false
        """,
        (professor_id,),
    ).fetchall()
    paper_signal_row = conn.execute(
        """
        SELECT count(*) AS paper_candidates,
               count(*) FILTER (WHERE link_status = 'verified') AS verified_paper_signals
          FROM professor_paper_link
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()

    primary_affiliation = _select_primary_current_affiliation(affiliation_rows)
    affiliations = tuple(
        ProfessorAffiliationState(
            institution=_row_get(row, "institution", 0),
            is_current=bool(_row_get(row, "is_current", 3)),
            is_primary=bool(_row_get(row, "is_primary", 4)),
            updated_at=_row_get(row, "updated_at", 5),
        )
        for row in affiliation_rows
    )
    contacts = tuple(
        contact
        for row in fact_rows
        if (
            contact := _contact_from_fact_row(row)
        )
        is not None
    )
    research_topics = tuple(
        value
        for row in fact_rows
        if _row_get(row, "fact_type", 0) == "research_topic"
        and (value := _normalize_optional_text(_row_get(row, "value_raw", 1)))
    )
    open_issues = tuple(
        ProfessorIssueSignal(
            stage=str(_row_get(row, "stage", 0)),
            reported_by=str(_row_get(row, "reported_by", 1)),
            reported_at=_row_get(row, "reported_at", 2),
            resolved=bool(_row_get(row, "resolved", 3)),
        )
        for row in issue_rows
    )
    watermark_values = [
        value
        for value in (
            _row_get(professor_row, "updated_at", 5),
            *(affiliation.updated_at for affiliation in affiliations),
            *(_row_get(row, "updated_at", 3) for row in fact_rows),
            *(contact.updated_at for contact in contacts),
        )
        if value is not None
    ]

    return ProfessorCanonicalState(
        professor_id=str(_row_get(professor_row, "professor_id", 0)),
        canonical_name=_row_get(professor_row, "canonical_name", 1),
        identity_status=_row_get(professor_row, "identity_status", 2),
        current_institution=(
            _row_get(primary_affiliation, "institution", 0)
            if primary_affiliation is not None
            else None
        ),
        title=(
            _row_get(primary_affiliation, "title", 2)
            if primary_affiliation is not None
            else None
        ),
        department=(
            _row_get(primary_affiliation, "department", 1)
            if primary_affiliation is not None
            else None
        ),
        research_topics=research_topics,
        profile_summary=_row_get(professor_row, "profile_summary", 4),
        has_official_source=bool(
            _row_get(professor_row, "primary_official_profile_page_id", 3)
        ),
        has_paper_candidates=(
            int(_row_get(paper_signal_row, "paper_candidates", 0) or 0) > 0
            if paper_signal_row is not None
            else False
        ),
        has_verified_paper_signal=(
            int(_row_get(paper_signal_row, "verified_paper_signals", 1) or 0) > 0
            if paper_signal_row is not None
            else False
        ),
        affiliations=affiliations,
        contact_facts=contacts,
        open_issues=open_issues,
        canonical_watermark=max(watermark_values) if watermark_values else None,
    )


def persist_professor_quality_evaluation(
    conn,
    *,
    professor_id: str,
    evaluation: ProfessorQualityEvaluation,
) -> dict[str, int]:
    conn.execute(
        """
        UPDATE professor
           SET quality_status = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (evaluation.quality_status, professor_id),
    )

    persisted_descriptions: list[str] = []
    issues_upserted = 0
    for reason in evaluation.reasons:
        if not reason.persist_issue or reason.stage is None:
            continue
        description = _quality_issue_description(reason)
        persisted_descriptions.append(description)
        insert_cursor = conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                link_id,
                institution,
                stage,
                severity,
                description,
                evidence_snapshot,
                reported_by
            )
            VALUES (%s, NULL, NULL, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                professor_id,
                reason.stage,
                _severity_for_quality_status(evaluation.quality_status),
                description,
                json.dumps(
                    {
                        "professor_id": professor_id,
                        "quality_status": evaluation.quality_status,
                        "rule_id": reason.rule_id,
                    },
                    ensure_ascii=False,
                ),
                PROFESSOR_QUALITY_GATE_REPORTER,
            ),
        )
        issues_upserted += _cursor_rowcount(insert_cursor)

    if persisted_descriptions:
        stale_cursor = conn.execute(
            """
            UPDATE pipeline_issue
               SET resolved = true,
                   resolved_at = now(),
                   resolution_notes = 'resolved by professor quality re-evaluation'
             WHERE professor_id = %s
               AND reported_by = %s
               AND resolved = false
               AND description <> ALL(%s)
            """,
            (
                professor_id,
                PROFESSOR_QUALITY_GATE_REPORTER,
                persisted_descriptions,
            ),
        )
    else:
        stale_cursor = conn.execute(
            """
            UPDATE pipeline_issue
               SET resolved = true,
                   resolved_at = now(),
                   resolution_notes = 'resolved by professor quality re-evaluation'
             WHERE professor_id = %s
               AND reported_by = %s
               AND resolved = false
            """,
            (professor_id, PROFESSOR_QUALITY_GATE_REPORTER),
        )

    return {
        "issues_upserted": issues_upserted,
        "stale_issues_reconciled": _cursor_rowcount(stale_cursor),
    }


def _cursor_rowcount(cursor: object) -> int:
    rowcount = getattr(cursor, "rowcount", 0)
    return rowcount if isinstance(rowcount, int) and rowcount > 0 else 0


def _needs_review_reasons(
    state: ProfessorCanonicalState,
) -> tuple[ProfessorQualityReason, ...]:
    reasons: list[ProfessorQualityReason] = []
    if _normalize_optional_text(state.identity_status) != "resolved":
        reasons.append(_reason("identity_unresolved", "identity is not resolved"))
    if state.same_name_conflict:
        reasons.append(_reason("same_name_conflict", "same-name conflict is open"))
    if _has_field_contradiction(state):
        reasons.append(
            _reason("field_contradiction", "contradictory canonical facts detected")
        )
    for issue in _external_open_issues(state):
        reasons.append(
            ProfessorQualityReason(
                rule_id="external_blocking_issue",
                stage=issue.stage,
                message=f"external open pipeline issue at stage {issue.stage}",
                persist_issue=False,
            )
        )
    return tuple(reasons)


def _row_get(row: object, key: str, index: int) -> object:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]  # type: ignore[index]
    except (IndexError, TypeError):
        return None


def _select_primary_current_affiliation(rows: object) -> object | None:
    if not isinstance(rows, list | tuple):
        return None
    current_rows = [row for row in rows if bool(_row_get(row, "is_current", 3))]
    primary_rows = [row for row in current_rows if bool(_row_get(row, "is_primary", 4))]
    candidates = primary_rows or current_rows
    return candidates[0] if candidates else None


def _contact_from_fact_row(row: object) -> ProfessorContactFact | None:
    fact_type = _normalize_optional_text(_row_get(row, "fact_type", 0))
    if fact_type not in {"contact", "homepage"}:
        return None
    value = _normalize_optional_text(_row_get(row, "value_raw", 1))
    if not value:
        return None
    return ProfessorContactFact(
        subtype="email" if fact_type == "contact" else "homepage",
        value=value,
        source_page_id=_normalize_optional_text(_row_get(row, "source_page_id", 2)),
        is_active=True,
        updated_at=_row_get(row, "updated_at", 3),
    )


def _quality_issue_description(reason: ProfessorQualityReason) -> str:
    return f"[professor_quality_gate:{reason.rule_id}] {reason.message}"


def _severity_for_quality_status(quality_status: str) -> str:
    if quality_status == "needs_review":
        return "high"
    if quality_status == "low_confidence":
        return "medium"
    return "low"


def _low_confidence_reasons(
    state: ProfessorCanonicalState,
) -> tuple[ProfessorQualityReason, ...]:
    reasons: list[ProfessorQualityReason] = []
    canonical_name = _normalize_optional_text(state.canonical_name)
    if state.non_person_name or (
        canonical_name
        and (
            is_obvious_non_person_name(canonical_name)
            or looks_like_profile_blob(canonical_name)
        )
    ):
        reasons.append(_reason("non_person_name", "canonical name is not a person"))
    if not state.has_official_source:
        reasons.append(_reason("missing_official_source", "official source missing"))
    if state.reader_artifact_detected:
        reasons.append(
            _reason("reader_artifact_detected", "reader artifact detected")
        )
    if state.profile_blob_detected:
        reasons.append(_reason("profile_blob_detected", "profile blob detected"))
    return tuple(reasons)


def _needs_enrichment_reasons(
    state: ProfessorCanonicalState,
) -> tuple[ProfessorQualityReason, ...]:
    reasons: list[ProfessorQualityReason] = []
    if not _normalize_optional_text(state.canonical_name):
        reasons.append(_reason("missing_canonical_name", "canonical name missing"))
    if not _normalize_optional_text(state.current_institution):
        reasons.append(
            _reason("missing_current_institution", "current institution missing")
        )
    if not (
        _normalize_optional_text(state.title)
        or _normalize_optional_text(state.department)
    ):
        reasons.append(
            _reason("missing_title_or_department", "title or department missing")
        )
    if not any(_normalize_optional_text(topic) for topic in state.research_topics):
        reasons.append(_reason("missing_research_topic", "research topic missing"))
    if not _normalize_optional_text(state.profile_summary):
        reasons.append(_reason("missing_profile_summary", "profile summary missing"))
    if state.has_paper_candidates and not state.has_verified_paper_signal:
        reasons.append(
            _reason(
                "missing_verified_paper_signal",
                "paper candidates lack verified attribution signal",
            )
        )
    return tuple(reasons)


def _reason(rule_id: str, message: str) -> ProfessorQualityReason:
    return ProfessorQualityReason(
        rule_id=rule_id,
        stage=PROFESSOR_QUALITY_STAGE_BY_RULE_ID[rule_id],
        message=message,
        persist_issue=True,
    )


def _external_open_issues(
    state: ProfessorCanonicalState,
) -> tuple[ProfessorIssueSignal, ...]:
    return tuple(
        issue
        for issue in state.open_issues
        if not issue.resolved and issue.reported_by != PROFESSOR_QUALITY_GATE_REPORTER
    )


def _canonical_watermark(state: ProfessorCanonicalState) -> datetime | None:
    values: list[datetime] = []
    if state.canonical_watermark is not None:
        values.append(state.canonical_watermark)
    values.extend(
        issue.reported_at
        for issue in _external_open_issues(state)
        if issue.reported_at is not None
    )
    values.extend(
        affiliation.updated_at
        for affiliation in state.affiliations
        if affiliation.updated_at is not None
    )
    values.extend(
        contact.updated_at
        for contact in state.contact_facts
        if contact.updated_at is not None
    )
    return max(values) if values else None


def _admin_action_is_fresh(
    action: ProfessorAdminAction | None,
    watermark: datetime | None,
) -> bool:
    if action is None or action.action not in {"confirm_ready", "send_to_review"}:
        return False
    if action.observed_data_updated_at is None:
        return watermark is None
    if watermark is None:
        return True
    return action.observed_data_updated_at >= watermark


def _has_field_contradiction(state: ProfessorCanonicalState) -> bool:
    if state.title_department_conflict:
        return True
    if _has_conflicting_primary_affiliations(state.affiliations):
        return True
    if _has_conflicting_same_source_contacts(state.contact_facts):
        return True
    return False


def _has_conflicting_primary_affiliations(
    affiliations: tuple[ProfessorAffiliationState, ...],
) -> bool:
    active_primary_institutions = {
        normalized
        for affiliation in affiliations
        if affiliation.is_current
        and affiliation.is_primary
        and (normalized := _normalize_for_compare(affiliation.institution))
    }
    return len(active_primary_institutions) > 1


def _has_conflicting_same_source_contacts(
    contact_facts: tuple[ProfessorContactFact, ...],
) -> bool:
    values_by_key: dict[tuple[str, str], set[str]] = {}
    for fact in contact_facts:
        if not fact.is_active or fact.subtype not in {"email", "homepage"}:
            continue
        source_page_id = _normalize_optional_text(fact.source_page_id)
        value = _normalize_for_compare(fact.value)
        if not source_page_id or not value:
            continue
        key = (fact.subtype, source_page_id)
        values_by_key.setdefault(key, set()).add(value)
    return any(len(values) > 1 for values in values_by_key.values())


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    item = str(value).strip()
    return item or None


def _normalize_for_compare(value: object) -> str | None:
    item = _normalize_optional_text(value)
    if item is None:
        return None
    return re.sub(r"\s+", "", item).casefold()


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
