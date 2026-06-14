# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Quality gate for professor records — three-level validation.

L1: Hard blocks (release prevented)
L2: Quality markers (released with status flag)
L3: Statistical alerts (aggregate-level warnings)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Literal

from psycopg.types.json import Jsonb

from src.data_agents.contracts import (
    SHENZHEN_INSTITUTION_KEYWORDS,
    QualityStatus,
    normalize_quality_status,
)

from .models import EnrichedProfessorProfile
from .name_selection import is_obvious_non_person_name, looks_like_profile_blob
from .profile_sections import extract_research_overview_text
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
PROFESSOR_READY_REQUIRED_RULES = (
    "missing_canonical_name",
    "missing_current_institution",
    "missing_title_or_department",
    "missing_research_topic",
    "missing_profile_summary",
    "missing_verified_paper_signal",
)
QUALITY_REASON_STAGE_MAP = {
    "missing_canonical_name": "name_extraction",
    "non_person_name": "name_extraction",
    "missing_official_source": "coverage",
    "reader_artifact_detected": "data_quality_flag",
    "profile_blob_detected": "data_quality_flag",
    "missing_current_institution": "affiliation",
    "missing_title_or_department": "affiliation",
    "missing_research_topic": "research_directions",
    "missing_profile_summary": "coverage",
    "profile_summary_too_short": "coverage",
    "profile_summary_too_long": "coverage",
    "profile_summary_not_chinese": "coverage",
    "shallow_or_repetitive_profile_summary": "data_quality_flag",
    "missing_research_overview_zh": "research_directions",
    "missing_verified_paper_signal": "paper_attribution",
    "missing_professor_paper_summary": "paper_attribution",
    "duplicate_verified_paper_links": "paper_attribution",
    "identity_unresolved": "identity_gate",
    "same_name_conflict": "identity_gate",
    "field_contradiction": "data_quality_flag",
}
_LOW_CONFIDENCE_RULES = {
    "missing_official_source",
    "non_person_name",
    "reader_artifact_detected",
    "profile_blob_detected",
}
_NEEDS_REVIEW_SIGNALS = {"same_name_conflict", "field_contradiction"}
_CONTACT_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HTTP_PREFIXES = ("http://", "https://")
_CHINESE_CHAR_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]")
_SUMMARY_TERM_SPLIT_RE = re.compile(r"[、,，;；/｜|]\s*")


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


@dataclass(frozen=True)
class SourcePageState:
    page_id: object
    url: str
    is_official_source: bool
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProfessorAffiliationState:
    institution: str | None
    department: str | None = None
    title: str | None = None
    is_primary: bool = False
    is_current: bool = True
    source_page_id: object | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ProfessorFactState:
    fact_type: str
    value_raw: str
    source_page_id: object | None = None
    status: str = "active"
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PipelineIssueState:
    issue_id: object
    stage: str
    reported_by: str
    description: str
    reported_at: datetime | None = None
    resolved: bool = False


ProfessorAdminActionName = Literal["confirm_ready", "send_to_review"]


@dataclass(frozen=True)
class ProfessorAdminAction:
    action: ProfessorAdminActionName
    observed_data_updated_at: datetime


@dataclass(frozen=True)
class ProfessorCanonicalState:
    professor_id: str
    canonical_name: str | None
    identity_status: str = "resolved"
    lifecycle_state: str = "active"
    lifecycle_merged_into_id: str | None = None
    profile_summary: str | None = None
    updated_at: datetime | None = None
    primary_official_profile_page_id: object | None = None
    aliases: tuple[str, ...] = ()
    paper_summary: str | None = None
    profile_raw_text: str | None = None
    source_pages: tuple[SourcePageState, ...] = ()
    affiliations: tuple[ProfessorAffiliationState, ...] = ()
    facts: tuple[ProfessorFactState, ...] = ()
    open_issues: tuple[PipelineIssueState, ...] = ()
    low_quality_signals: frozenset[str] = frozenset()
    anomaly_signals: frozenset[str] = frozenset()
    has_paper_candidates: bool = False
    has_verified_paper_signal: bool = False
    has_duplicate_verified_papers: bool = False
    has_research_overview_source: bool = False
    has_research_overview_zh: bool = False
    latest_admin_action: ProfessorAdminAction | None = None


@dataclass(frozen=True)
class ProfessorQualityReason:
    rule_id: str
    stage: str | None = None
    description: str | None = None
    persist: bool = True


@dataclass(frozen=True)
class ProfessorQualityEvaluation:
    professor_id: str
    quality_status: QualityStatus
    reasons: tuple[ProfessorQualityReason, ...]
    canonical_watermark: datetime | None = None


def evaluate_professor_quality(
    state: ProfessorCanonicalState,
) -> ProfessorQualityEvaluation:
    """Evaluate canonical professor quality from persisted-state signals."""
    watermark = _canonical_watermark(state)
    admin_action = state.latest_admin_action
    if admin_action is not None and _admin_action_is_fresh(admin_action, watermark):
        status: QualityStatus = (
            "ready" if admin_action.action == "confirm_ready" else "needs_review"
        )
        return ProfessorQualityEvaluation(
            professor_id=state.professor_id,
            quality_status=status,
            reasons=(
                ProfessorQualityReason(
                    rule_id="human_override",
                    description=f"fresh admin action: {admin_action.action}",
                    persist=False,
                ),
            ),
            canonical_watermark=watermark,
        )

    needs_review = _needs_review_reasons(state)
    if needs_review:
        return ProfessorQualityEvaluation(
            professor_id=state.professor_id,
            quality_status="needs_review",
            reasons=tuple(needs_review),
            canonical_watermark=watermark,
        )

    low_confidence = _low_confidence_reasons(state)
    if low_confidence:
        return ProfessorQualityEvaluation(
            professor_id=state.professor_id,
            quality_status="low_confidence",
            reasons=tuple(low_confidence),
            canonical_watermark=watermark,
        )

    enrichment = _needs_enrichment_reasons(state)
    if enrichment:
        return ProfessorQualityEvaluation(
            professor_id=state.professor_id,
            quality_status="needs_enrichment",
            reasons=tuple(enrichment),
            canonical_watermark=watermark,
        )

    return ProfessorQualityEvaluation(
        professor_id=state.professor_id,
        quality_status="ready",
        reasons=(),
        canonical_watermark=watermark,
    )


def load_professor_canonical_state(
    conn: Any, professor_id: str
) -> ProfessorCanonicalState:
    row = conn.execute(
        """
        SELECT professor_id,
               canonical_name,
               aliases,
               identity_status,
               lifecycle_state,
               lifecycle_merged_into_id,
               primary_official_profile_page_id,
               profile_summary,
               paper_summary,
               profile_raw_text,
               updated_at
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"professor not found: {professor_id}")

    link_row = conn.execute(
        """
        SELECT count(*)::int AS candidate_count,
               count(*) FILTER (WHERE link_status = 'verified')::int AS verified_count
          FROM professor_paper_link
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    candidate_count = int(_row_get(link_row, "candidate_count", 0) or 0)
    verified_count = int(_row_get(link_row, "verified_count", 1) or 0)

    profile_raw_text = _optional_str(_row_get(row, "profile_raw_text", 9))
    return ProfessorCanonicalState(
        professor_id=str(_row_get(row, "professor_id", 0)),
        canonical_name=_optional_str(_row_get(row, "canonical_name", 1)),
        aliases=tuple(_row_get(row, "aliases", 2) or ()),
        identity_status=str(_row_get(row, "identity_status", 3) or ""),
        lifecycle_state=str(_row_get(row, "lifecycle_state", 4) or "active"),
        lifecycle_merged_into_id=_optional_str(
            _row_get(row, "lifecycle_merged_into_id", 5)
        ),
        primary_official_profile_page_id=_row_get(
            row, "primary_official_profile_page_id", 6
        ),
        profile_summary=_optional_str(_row_get(row, "profile_summary", 7)),
        paper_summary=_optional_str(_row_get(row, "paper_summary", 8)),
        profile_raw_text=profile_raw_text,
        updated_at=_row_get(row, "updated_at", 10),
        source_pages=tuple(_load_source_pages(conn, professor_id)),
        affiliations=tuple(_load_affiliations(conn, professor_id)),
        facts=tuple(_load_facts(conn, professor_id)),
        open_issues=tuple(_load_open_issues(conn, professor_id)),
        has_paper_candidates=candidate_count > 0,
        has_verified_paper_signal=verified_count > 0,
        has_duplicate_verified_papers=_has_duplicate_verified_paper_links(
            conn, professor_id
        ),
        has_research_overview_source=extract_research_overview_text(profile_raw_text)
        is not None,
        has_research_overview_zh=_has_research_overview_zh(conn, professor_id),
    )


def load_professor_canonical_states(
    conn: Any, professor_ids: Sequence[str] | None = None
) -> list[ProfessorCanonicalState]:
    if professor_ids is None:
        rows = conn.execute(
            """
            SELECT professor_id
              FROM professor
             WHERE identity_status <> 'merged_into'
             ORDER BY professor_id
            """
        ).fetchall()
        selected_ids = [str(_row_get(row, "professor_id", 0)) for row in rows]
    else:
        selected_ids = list(professor_ids)
    return [load_professor_canonical_state(conn, professor_id) for professor_id in selected_ids]


def persist_professor_quality_evaluation(
    conn: Any, evaluation: ProfessorQualityEvaluation
) -> None:
    conn.execute(
        """
        UPDATE professor
           SET quality_status = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (evaluation.quality_status, evaluation.professor_id),
    )

    active_descriptions: set[str] = set()
    for reason in evaluation.reasons:
        if not reason.persist:
            continue
        stage = reason.stage or QUALITY_REASON_STAGE_MAP[reason.rule_id]
        description = reason.description or f"professor quality gate: {reason.rule_id}"
        active_descriptions.add(description)
        _upsert_quality_gate_issue(
            conn,
            professor_id=evaluation.professor_id,
            stage=stage,
            description=description,
            reason=reason,
            quality_status=evaluation.quality_status,
        )

    _resolve_stale_quality_gate_issues(
        conn,
        professor_id=evaluation.professor_id,
        active_descriptions=active_descriptions,
    )


def evaluate_and_persist_professor_quality(
    conn: Any, professor_id: str
) -> ProfessorQualityEvaluation:
    state = load_professor_canonical_state(conn, professor_id)
    evaluation = evaluate_professor_quality(state)
    persist_professor_quality_evaluation(conn, evaluation)
    return evaluation


def _load_source_pages(conn: Any, professor_id: str) -> list[SourcePageState]:
    rows = conn.execute(
        """
        SELECT DISTINCT sp.page_id,
               sp.url,
               sp.is_official_source,
               COALESCE(sp.fetched_at, sp.created_at) AS updated_at
          FROM source_page sp
         WHERE (sp.owner_scope_kind = 'professor' AND sp.owner_scope_ref = %s)
            OR sp.page_id IN (
                SELECT primary_official_profile_page_id
                  FROM professor
                 WHERE professor_id = %s
                   AND primary_official_profile_page_id IS NOT NULL
                UNION
                SELECT source_page_id
                  FROM professor_affiliation
                 WHERE professor_id = %s
                UNION
                SELECT source_page_id
                  FROM professor_fact
                 WHERE professor_id = %s
            )
        """,
        (professor_id, professor_id, professor_id, professor_id),
    ).fetchall()
    return [
        SourcePageState(
            page_id=_row_get(row, "page_id", 0),
            url=str(_row_get(row, "url", 1) or ""),
            is_official_source=bool(_row_get(row, "is_official_source", 2)),
            updated_at=_row_get(row, "updated_at", 3),
        )
        for row in rows
    ]


def _load_affiliations(conn: Any, professor_id: str) -> list[ProfessorAffiliationState]:
    rows = conn.execute(
        """
        SELECT institution,
               department,
               title,
               is_primary,
               is_current,
               source_page_id,
               updated_at
          FROM professor_affiliation
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchall()
    return [
        ProfessorAffiliationState(
            institution=_optional_str(_row_get(row, "institution", 0)),
            department=_optional_str(_row_get(row, "department", 1)),
            title=_optional_str(_row_get(row, "title", 2)),
            is_primary=bool(_row_get(row, "is_primary", 3)),
            is_current=bool(_row_get(row, "is_current", 4)),
            source_page_id=_row_get(row, "source_page_id", 5),
            updated_at=_row_get(row, "updated_at", 6),
        )
        for row in rows
    ]


def _load_facts(conn: Any, professor_id: str) -> list[ProfessorFactState]:
    rows = conn.execute(
        """
        SELECT fact_type,
               value_raw,
               source_page_id,
               status,
               updated_at
          FROM professor_fact
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchall()
    return [
        ProfessorFactState(
            fact_type=str(_row_get(row, "fact_type", 0) or ""),
            value_raw=str(_row_get(row, "value_raw", 1) or ""),
            source_page_id=_row_get(row, "source_page_id", 2),
            status=str(_row_get(row, "status", 3) or ""),
            updated_at=_row_get(row, "updated_at", 4),
        )
        for row in rows
    ]


def _load_open_issues(conn: Any, professor_id: str) -> list[PipelineIssueState]:
    rows = conn.execute(
        """
        SELECT issue_id,
               stage,
               reported_by,
               description,
               reported_at,
               resolved
          FROM pipeline_issue
         WHERE professor_id = %s
           AND resolved = false
        """,
        (professor_id,),
    ).fetchall()
    return [
        PipelineIssueState(
            issue_id=_row_get(row, "issue_id", 0),
            stage=str(_row_get(row, "stage", 1) or ""),
            reported_by=str(_row_get(row, "reported_by", 2) or ""),
            description=str(_row_get(row, "description", 3) or ""),
            reported_at=_row_get(row, "reported_at", 4),
            resolved=bool(_row_get(row, "resolved", 5)),
        )
        for row in rows
    ]


def _has_research_overview_zh(conn: Any, professor_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM professor_profile_section
         WHERE professor_id = %s
           AND section_type = 'research_overview'
           AND language = 'zh'
           AND content IS NOT NULL
           AND length(trim(content)) > 0
         LIMIT 1
        """,
        (professor_id,),
    ).fetchone()
    return row is not None


def _has_duplicate_verified_paper_links(conn: Any, professor_id: str) -> bool:
    row = conn.execute(
        """
        WITH resolved_links AS (
            SELECT DISTINCT COALESCE(pma.canonical_paper_id, ppl.paper_id)
                   AS resolved_paper_id
              FROM professor_paper_link AS ppl
              LEFT JOIN paper_merge_alias AS pma
                ON pma.old_paper_id = ppl.paper_id
             WHERE ppl.professor_id = %s
               AND ppl.link_status = 'verified'
        ),
        grouped AS (
            SELECT
                lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g'))
                    AS normalized_title,
                p.year,
                count(DISTINCT p.paper_id)::int AS n
              FROM resolved_links AS rl
              JOIN paper AS p ON p.paper_id = rl.resolved_paper_id
             WHERE COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')
               AND trim(COALESCE(p.title_clean, '')) <> ''
             GROUP BY
                lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                p.year
            HAVING count(DISTINCT p.paper_id) > 1
        )
        SELECT count(*)::int AS duplicate_group_count
          FROM grouped
        """,
        (professor_id,),
    ).fetchone()
    return int(_row_get(row, "duplicate_group_count", 0) or 0) > 0


def _upsert_quality_gate_issue(
    conn: Any,
    *,
    professor_id: str,
    stage: str,
    description: str,
    reason: ProfessorQualityReason,
    quality_status: str,
) -> None:
    evidence_snapshot = Jsonb(
        json.loads(
            json.dumps(
                {
                    "rule_id": reason.rule_id,
                    "quality_status": quality_status,
                    "persist": reason.persist,
                },
                ensure_ascii=False,
                default=str,
            )
        )
    )
    row = conn.execute(
        """
        SELECT issue_id
          FROM pipeline_issue
         WHERE professor_id = %s
           AND description_hash = md5(%s)
           AND stage = %s
           AND reported_by = %s
           AND resolved = false
         LIMIT 1
        """,
        (professor_id, description, stage, QUALITY_GATE_REPORTED_BY),
    ).fetchone()
    if row is not None:
        issue_id = _row_get(row, "issue_id", 0)
        conn.execute(
            """
            UPDATE pipeline_issue
               SET evidence_snapshot = %s,
                   reported_at = GREATEST(reported_at, now())
             WHERE issue_id = %s
            """,
            (evidence_snapshot, issue_id),
        )
        return

    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, stage, severity, description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            stage,
            _severity_for_quality_status(quality_status),
            description,
            evidence_snapshot,
            QUALITY_GATE_REPORTED_BY,
        ),
    )


def _resolve_stale_quality_gate_issues(
    conn: Any, *, professor_id: str, active_descriptions: set[str]
) -> None:
    rows = conn.execute(
        """
        SELECT issue_id, description
          FROM pipeline_issue
         WHERE professor_id = %s
           AND reported_by = %s
           AND resolved = false
        """,
        (professor_id, QUALITY_GATE_REPORTED_BY),
    ).fetchall()
    for row in rows:
        description = str(_row_get(row, "description", 1) or "")
        if description in active_descriptions:
            continue
        conn.execute(
            """
            UPDATE pipeline_issue
               SET resolved = true,
                   resolved_at = now(),
                   resolution_notes = 'resolved by professor quality re-evaluation'
             WHERE issue_id = %s
            """,
            (_row_get(row, "issue_id", 0),),
        )


def _severity_for_quality_status(status: str) -> str:
    if status == "needs_review":
        return "high"
    if status == "low_confidence":
        return "medium"
    return "low"


def _row_get(row: object, key: str, index: int) -> object:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row.get(key)
    return row[index]  # type: ignore[index]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _needs_review_reasons(
    state: ProfessorCanonicalState,
) -> list[ProfessorQualityReason]:
    reasons: list[ProfessorQualityReason] = []
    if (state.identity_status or "").strip() != "resolved":
        reasons.append(_persisted_reason("identity_unresolved"))
    external_issues = [
        issue
        for issue in state.open_issues
        if not issue.resolved and issue.reported_by != QUALITY_GATE_REPORTED_BY
    ]
    if external_issues:
        reasons.append(
            ProfessorQualityReason(
                rule_id="external_blocking_issue",
                description="open external pipeline_issue blocks quality evaluation",
                persist=False,
            )
        )
    if "same_name_conflict" in state.anomaly_signals:
        reasons.append(_persisted_reason("same_name_conflict"))
    if _has_field_contradiction(state) or "field_contradiction" in state.anomaly_signals:
        reasons.append(_persisted_reason("field_contradiction"))
    if state.has_duplicate_verified_papers:
        reasons.append(_persisted_reason("duplicate_verified_paper_links"))
    if _profile_summary_is_shallow_or_repetitive(state.profile_summary):
        reasons.append(_persisted_reason("shallow_or_repetitive_profile_summary"))
    return reasons


def _low_confidence_reasons(
    state: ProfessorCanonicalState,
) -> list[ProfessorQualityReason]:
    reasons: list[ProfessorQualityReason] = []
    if not _has_official_source(state):
        reasons.append(_persisted_reason("missing_official_source"))
    for signal in sorted(state.low_quality_signals):
        if signal in _LOW_CONFIDENCE_RULES and signal != "missing_official_source":
            reasons.append(_persisted_reason(signal))
    canonical_name = (state.canonical_name or "").strip()
    if canonical_name and (
        is_obvious_non_person_name(canonical_name)
        or looks_like_profile_blob(canonical_name)
    ):
        reasons.append(_persisted_reason("non_person_name"))
    return _dedupe_reasons(reasons)


def _needs_enrichment_reasons(
    state: ProfessorCanonicalState,
) -> list[ProfessorQualityReason]:
    reasons: list[ProfessorQualityReason] = []
    if not (state.canonical_name or "").strip():
        reasons.append(_persisted_reason("missing_canonical_name"))
    if not _current_institution(state):
        reasons.append(_persisted_reason("missing_current_institution"))
    if not _has_title_or_department(state):
        reasons.append(_persisted_reason("missing_title_or_department"))
    if not _active_facts_of_type(state, "research_topic"):
        reasons.append(_persisted_reason("missing_research_topic"))
    if not (state.profile_summary or "").strip():
        reasons.append(_persisted_reason("missing_profile_summary"))
    else:
        summary_reason = _profile_summary_contract_reason(state.profile_summary)
        if summary_reason is not None:
            reasons.append(_persisted_reason(summary_reason))
    if state.has_research_overview_source and not state.has_research_overview_zh:
        reasons.append(_persisted_reason("missing_research_overview_zh"))
    if state.has_paper_candidates and not state.has_verified_paper_signal:
        reasons.append(_persisted_reason("missing_verified_paper_signal"))
    if state.has_verified_paper_signal and not (state.paper_summary or "").strip():
        reasons.append(_persisted_reason("missing_professor_paper_summary"))
    return reasons


def _profile_summary_contract_reason(summary: str | None) -> str | None:
    text = (summary or "").strip()
    if not text:
        return "missing_profile_summary"
    if not _CHINESE_CHAR_RE.search(text):
        return "profile_summary_not_chinese"
    length = len(text)
    if length < 200:
        return "profile_summary_too_short"
    if length > 300:
        return "profile_summary_too_long"
    return None


def _profile_summary_is_shallow_or_repetitive(summary: str | None) -> bool:
    text = (summary or "").strip()
    if not text:
        return False
    if _profile_summary_contract_reason(text) is not None:
        return False
    terms = [
        term.strip()
        for term in _SUMMARY_TERM_SPLIT_RE.split(text)
        if len(term.strip()) >= 2
    ]
    if len(terms) >= 8:
        normalized_terms = [_normalize_summary_term(term) for term in terms]
        unique_terms = {term for term in normalized_terms if term}
        if unique_terms and len(unique_terms) / len(normalized_terms) < 0.55:
            return True
        if any(normalized_terms.count(term) >= 3 for term in unique_terms):
            return True
    compact = re.sub(r"\s+", "", text)
    for width in range(4, 13):
        chunks = [
            compact[index : index + width]
            for index in range(0, max(0, len(compact) - width + 1), width)
        ]
        if not chunks:
            continue
        for chunk in set(chunks):
            if chunk and compact.count(chunk) >= 4:
                return True
    return False


def _normalize_summary_term(term: str) -> str:
    return re.sub(r"[\s。；;，,、：:（）()]+", "", term).lower()


def _persisted_reason(rule_id: str) -> ProfessorQualityReason:
    return ProfessorQualityReason(
        rule_id=rule_id,
        stage=QUALITY_REASON_STAGE_MAP[rule_id],
        description=f"professor quality gate: {rule_id}",
    )


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


def _has_official_source(state: ProfessorCanonicalState) -> bool:
    if state.primary_official_profile_page_id is not None:
        return True
    return any(page.is_official_source for page in state.source_pages)


def _current_primary_affiliations(
    state: ProfessorCanonicalState,
) -> list[ProfessorAffiliationState]:
    return [
        affiliation
        for affiliation in state.affiliations
        if affiliation.is_current and affiliation.is_primary
    ]


def _current_institution(state: ProfessorCanonicalState) -> str | None:
    for affiliation in _current_primary_affiliations(state):
        institution = (affiliation.institution or "").strip()
        if institution:
            return institution
    for affiliation in state.affiliations:
        if not affiliation.is_current:
            continue
        institution = (affiliation.institution or "").strip()
        if institution:
            return institution
    return None


def _has_title_or_department(state: ProfessorCanonicalState) -> bool:
    for affiliation in state.affiliations:
        if not affiliation.is_current:
            continue
        if (affiliation.title or "").strip() or (affiliation.department or "").strip():
            return True
    return False


def _active_facts_of_type(
    state: ProfessorCanonicalState, fact_type: str
) -> list[ProfessorFactState]:
    return [
        fact
        for fact in state.facts
        if fact.status == "active"
        and fact.fact_type == fact_type
        and (fact.value_raw or "").strip()
    ]


def _has_field_contradiction(state: ProfessorCanonicalState) -> bool:
    primary_institutions = {
        _normalize_conflict_value(affiliation.institution)
        for affiliation in _current_primary_affiliations(state)
        if _normalize_conflict_value(affiliation.institution)
    }
    if len(primary_institutions) > 1:
        return True
    if _has_contact_fact_contradiction(state):
        return True
    return False


def _has_contact_fact_contradiction(state: ProfessorCanonicalState) -> bool:
    by_key: dict[tuple[object | None, str], set[str]] = {}
    for fact in _active_facts_of_type(state, "contact"):
        subtype = _contact_subtype(fact.value_raw)
        if subtype is None:
            continue
        key = (fact.source_page_id, subtype)
        by_key.setdefault(key, set()).add(_normalize_conflict_value(fact.value_raw))
    return any(len(values) > 1 for values in by_key.values())


def _contact_subtype(value: str) -> str | None:
    normalized = value.strip().lower()
    if _CONTACT_EMAIL_RE.match(normalized):
        return "email"
    if normalized.startswith(_HTTP_PREFIXES):
        return "homepage"
    return None


def _normalize_conflict_value(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").strip().lower())


def _canonical_watermark(state: ProfessorCanonicalState) -> datetime | None:
    candidates: list[datetime] = []
    if state.updated_at is not None:
        candidates.append(state.updated_at)
    candidates.extend(
        affiliation.updated_at
        for affiliation in state.affiliations
        if affiliation.updated_at is not None
    )
    candidates.extend(fact.updated_at for fact in state.facts if fact.updated_at is not None)
    candidates.extend(
        issue.reported_at
        for issue in state.open_issues
        if issue.reported_at is not None and issue.reported_by != QUALITY_GATE_REPORTED_BY
    )
    return max(candidates) if candidates else None


def _admin_action_is_fresh(
    action: ProfessorAdminAction, watermark: datetime | None
) -> bool:
    if watermark is None:
        return True
    return action.observed_data_updated_at >= watermark


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
