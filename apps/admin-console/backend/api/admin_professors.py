from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api/admin/professor")

AdminProfessorMarkAction = Literal["confirm_ready", "send_to_review", "flag_recrawl"]
QualityStatus = Literal["ready", "needs_review", "low_confidence", "needs_enrichment"]
SortBy = Literal[
    "canonical_name",
    "quality_status",
    "open_issue_count",
    "latest_admin_action",
    "official_source",
]
SortOrder = Literal["asc", "desc"]


class AdminProfessorMarkRequest(BaseModel):
    action: AdminProfessorMarkAction
    actor: str = "admin-console"
    note: str | None = None


class AdminProfessorMarkResponse(BaseModel):
    professor_id: str
    action: AdminProfessorMarkAction
    quality_status: str


def _row_get(row: object, key: str, index: int, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return row[index]  # type: ignore[index]


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _quality_to_identity_status(quality_status: str) -> str:
    return "resolved" if quality_status == "ready" else "unverified"


_RESEARCH_SECTION_LABELS = (
    "研究领域",
    "研究方向",
    "Research Interests",
    "Research Areas",
    "Research Directions",
)
_RESEARCH_SECTION_STOP_LABELS = (
    "主要项目",
    "科研项目",
    "研究成果",
    "代表性论文",
    "学术论文",
    "论文",
    "专利",
    "教育经历",
    "教育背景",
    "工作经历",
    "奖励荣誉",
    "荣誉奖项",
    "学术兼职",
    "社会兼职",
    "教学课程",
    "研究生指导",
    "个人简介",
)


def _clean_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n:：")


def _starts_with_section_stop_label(value: str) -> bool:
    prefix = value.lstrip(" :：")
    return any(
        re.match(re.escape(label), prefix, flags=re.IGNORECASE)
        for label in _RESEARCH_SECTION_STOP_LABELS
    )


def _extract_research_overview(profile_raw_text: Any) -> str | None:
    if not isinstance(profile_raw_text, str) or not profile_raw_text.strip():
        return None

    raw = _clean_inline_text(profile_raw_text)
    label_matches = sorted(
        {
            match.span(): match
            for label in _RESEARCH_SECTION_LABELS
            for match in re.finditer(re.escape(label), raw, flags=re.IGNORECASE)
        }.values(),
        key=lambda match: match.start(),
    )

    for label_match in label_matches:
        body = raw[label_match.end() :].strip(" :：")
        if not body or _starts_with_section_stop_label(body):
            continue

        stop_positions = [
            match.start()
            for label in _RESEARCH_SECTION_STOP_LABELS
            if (
                match := re.search(
                    re.escape(label),
                    body,
                    flags=re.IGNORECASE,
                )
            )
            is not None
            and match.start() > 20
        ]
        if stop_positions:
            body = body[: min(stop_positions)]

        overview = _clean_inline_text(body)
        if len(overview) >= 20:
            return overview

    return None


def _sort_clause(sort_by: SortBy, sort_order: SortOrder) -> str:
    direction = "DESC" if sort_order == "desc" else "ASC"
    columns = {
        "canonical_name": "p.canonical_name",
        "quality_status": "p.quality_status",
        "open_issue_count": "open_issue_count",
        "latest_admin_action": "latest_admin_action",
        "official_source": "has_official_source",
    }
    return f"{columns[sort_by]} {direction}, p.professor_id ASC"


@router.get("")
def list_admin_professors(
    quality_status: QualityStatus | None = Query(default=None),
    reason_rule_id: str | None = Query(default=None),
    latest_admin_action: str | None = Query(default=None),
    official_source: bool | None = Query(default=None),
    sort_by: SortBy = "open_issue_count",
    sort_order: SortOrder = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    conditions: list[str] = []
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }
    if quality_status is not None:
        conditions.append("p.quality_status = %(quality_status)s")
        params["quality_status"] = quality_status
    if reason_rule_id is not None:
        conditions.append("%(reason_rule_id)s = ANY(COALESCE(i.reason_rule_ids, ARRAY[]::text[]))")
        params["reason_rule_id"] = reason_rule_id
    if latest_admin_action is not None:
        conditions.append("a.action = %(latest_admin_action)s")
        params["latest_admin_action"] = latest_admin_action
    if official_source is not None:
        conditions.append("COALESCE(s.has_official_source, false) = %(official_source)s")
        params["official_source"] = official_source
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    order_by = _sort_clause(sort_by, sort_order)

    rows = conn.execute(
        f"""
        WITH issue_summary AS (
            SELECT professor_id,
                   count(*) FILTER (WHERE resolved = false) AS open_issue_count,
                   array_remove(
                       array_agg(DISTINCT evidence_snapshot->>'rule_id')
                         FILTER (WHERE resolved = false),
                       NULL
                   ) AS reason_rule_ids
              FROM pipeline_issue
             WHERE professor_id IS NOT NULL
             GROUP BY professor_id
        ),
        action_summary AS (
            SELECT DISTINCT ON (professor_id)
                   professor_id,
                   action,
                   created_at
              FROM professor_admin_action
             WHERE professor_id IS NOT NULL
             ORDER BY professor_id, created_at DESC
        ),
        source_summary AS (
            SELECT owner_scope_ref AS professor_id,
                   bool_or(is_official_source) AS has_official_source
              FROM source_page
             WHERE owner_scope_kind = 'professor'
             GROUP BY owner_scope_ref
        )
        SELECT p.professor_id,
               p.canonical_name AS display_name,
               pa.institution,
               pa.department,
               p.quality_status,
               p.lifecycle_state,
               COALESCE(i.open_issue_count, 0) AS open_issue_count,
               a.action AS latest_admin_action,
               COALESCE(s.has_official_source, false) AS has_official_source,
               COALESCE(i.reason_rule_ids, ARRAY[]::text[]) AS reason_rule_ids,
               count(*) OVER() AS total_count
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id
           AND pa.is_primary = true
           AND pa.is_current = true
          LEFT JOIN issue_summary i ON i.professor_id = p.professor_id
          LEFT JOIN action_summary a ON a.professor_id = p.professor_id
          LEFT JOIN source_summary s ON s.professor_id = p.professor_id
          {where}
         ORDER BY {order_by}
         OFFSET %(offset)s
         LIMIT %(page_size)s
        """,
        params,
    ).fetchall()

    total = int(_row_get(rows[0], "total_count", 10, 0)) if rows else 0
    items = [
        {
            "professor_id": _row_get(row, "professor_id", 0),
            "display_name": _row_get(row, "display_name", 1),
            "institution": _row_get(row, "institution", 2),
            "department": _row_get(row, "department", 3),
            "quality_status": _row_get(row, "quality_status", 4),
            "lifecycle_state": _row_get(row, "lifecycle_state", 5),
            "open_issue_count": int(_row_get(row, "open_issue_count", 6, 0) or 0),
            "latest_admin_action": _row_get(row, "latest_admin_action", 7),
            "has_official_source": bool(_row_get(row, "has_official_source", 8, False)),
            "reason_rule_ids": _json_list(_row_get(row, "reason_rule_ids", 9)),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{professor_id}/mark", response_model=AdminProfessorMarkResponse)
def mark_admin_professor(
    professor_id: str,
    body: AdminProfessorMarkRequest,
    conn: Any = Depends(get_pg_conn),
) -> AdminProfessorMarkResponse:
    current = _load_professor_mark_state(conn, professor_id)
    observed_at = _observed_data_updated_at(conn, professor_id)
    actor = body.actor.strip()
    if not actor:
        raise HTTPException(status_code=422, detail="actor must be non-empty")

    next_quality_status = str(current["quality_status"])
    if body.action == "confirm_ready":
        next_quality_status = "ready"
        _update_professor_quality(conn, professor_id, next_quality_status)
    elif body.action == "send_to_review":
        next_quality_status = "needs_review"
        _update_professor_quality(conn, professor_id, next_quality_status)
    elif body.action == "flag_recrawl":
        _file_recrawl_issue(conn, professor_id=professor_id, actor=actor, note=body.note)

    conn.execute(
        """
        INSERT INTO professor_admin_action (
            professor_id,
            action,
            actor,
            note,
            observed_data_updated_at
        )
        VALUES (
            %(professor_id)s,
            %(action)s,
            %(actor)s,
            %(note)s,
            %(observed_data_updated_at)s
        )
        """,
        {
            "professor_id": professor_id,
            "action": body.action,
            "actor": actor,
            "note": body.note,
            "observed_data_updated_at": observed_at,
        },
    )
    conn.commit()
    return AdminProfessorMarkResponse(
        professor_id=professor_id,
        action=body.action,
        quality_status=next_quality_status,
    )


@router.get("/{professor_id}")
def get_admin_professor_detail(
    professor_id: str,
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    prof = _load_professor_mark_state(conn, professor_id)
    affiliations = _load_affiliations(conn, professor_id)
    facts = _load_facts(conn, professor_id)
    papers = _load_papers(conn, professor_id)
    patents = _load_patents(conn, professor_id)
    sources = _load_sources(conn, professor_id)
    issues = _load_issues(conn, professor_id)
    actions = _load_actions(conn, professor_id)
    overview_section = _load_research_overview_section(conn, professor_id)
    research_overview = _row_get(overview_section, "content", 0) or _extract_research_overview(
        _row_get(prof, "profile_raw_text", 15)
    )

    reasons = []
    for issue in issues:
        evidence = _row_get(issue, "evidence_snapshot", 4) or {}
        if isinstance(evidence, dict):
            rule_id = evidence.get("rule_id")
        else:
            rule_id = None
        reasons.append(
            {
                "rule_id": rule_id or _row_get(issue, "stage", 1),
                "stage": _row_get(issue, "stage", 1),
                "severity": _row_get(issue, "severity", 2),
                "description": _row_get(issue, "description", 3),
            }
        )

    sections = {
        "identity": {
            "professor_id": professor_id,
            "canonical_name": _row_get(prof, "canonical_name", 1),
            "canonical_name_en": _row_get(prof, "canonical_name_en", 2),
            "institution": _row_get(prof, "institution", 3),
            "department": _row_get(prof, "department", 4),
            "title": _row_get(prof, "title", 5),
            "identity_status": _row_get(prof, "identity_status", 11),
            "lifecycle_state": _row_get(prof, "lifecycle_state", 12),
            "lifecycle_merged_into_id": _row_get(prof, "lifecycle_merged_into_id", 13),
        },
        "contact": {"email": _row_get(prof, "email", 6)},
        "research_output": {
            "research_overview": research_overview,
            "facts": _json_list(facts),
            "papers": _json_list(papers),
            "patents": _json_list(patents),
            "paper_summary": _row_get(prof, "paper_summary", 9),
            "patent_summary": _row_get(prof, "patent_summary", 10),
        },
        "experience": {
            "status": "populated" if affiliations else "not_extracted",
            "affiliations": _json_list(affiliations),
        },
        "cleaned_summary": {"profile_summary": _row_get(prof, "profile_summary", 8)},
        "sources_evidence": {"sources": _json_list(sources), "admin_actions": _json_list(actions)},
        "quality_diagnosis": {
            "status": _row_get(prof, "quality_status", 7),
            "reasons": reasons,
            "open_issue_count": len(issues),
        },
    }
    return {"professor_id": professor_id, "sections": sections}


def _load_professor_mark_state(conn: Any, professor_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               pa.institution,
               pa.department,
               pa.title,
               contact.email,
               p.quality_status,
               p.profile_summary,
               p.paper_summary,
               p.patent_summary,
               p.identity_status,
               p.lifecycle_state,
               p.lifecycle_merged_into_id,
               p.updated_at,
               p.profile_raw_text
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id
           AND pa.is_primary = true
           AND pa.is_current = true
          LEFT JOIN LATERAL (
            SELECT pf.value_raw AS email
              FROM professor_fact pf
             WHERE pf.professor_id = p.professor_id
               AND pf.fact_type = 'contact'
               AND pf.status = 'active'
             ORDER BY pf.confidence DESC NULLS LAST, pf.updated_at DESC NULLS LAST
             LIMIT 1
          ) contact ON true
         WHERE p.professor_id = %(professor_id)s
        """,
        {"professor_id": professor_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Professor not found")
    return row


def _load_research_overview_section(conn: Any, professor_id: str) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT pps.content,
               pps.generation_method,
               pps.source_language,
               sp.url AS source_page_url
          FROM professor_profile_section pps
          LEFT JOIN source_page sp ON sp.page_id = pps.source_page_id
         WHERE pps.professor_id = %(professor_id)s
           AND pps.section_type = 'research_overview'
           AND pps.language = 'zh'
         ORDER BY pps.updated_at DESC, pps.created_at DESC
         LIMIT 1
        """,
        {"professor_id": professor_id},
    ).fetchone()


def _observed_data_updated_at(conn: Any, professor_id: str) -> datetime:
    row = conn.execute(
        """
        SELECT GREATEST(
            COALESCE((SELECT updated_at FROM professor WHERE professor_id = %(professor_id)s), '-infinity'::timestamptz),
            COALESCE((SELECT max(updated_at) FROM professor_affiliation WHERE professor_id = %(professor_id)s), '-infinity'::timestamptz),
            COALESCE((SELECT max(updated_at) FROM professor_fact WHERE professor_id = %(professor_id)s), '-infinity'::timestamptz),
            COALESCE((
                SELECT max(GREATEST(reported_at, COALESCE(resolved_at, reported_at)))
                  FROM pipeline_issue
                 WHERE professor_id = %(professor_id)s
                   AND reported_by IS DISTINCT FROM 'professor_quality_gate'
            ), '-infinity'::timestamptz)
        ) AS observed_data_updated_at
        """,
        {"professor_id": professor_id},
    ).fetchone()
    return _row_get(row, "observed_data_updated_at", 0) or datetime.now(timezone.utc)


def _update_professor_quality(conn: Any, professor_id: str, quality_status: str) -> None:
    conn.execute(
        """
        UPDATE professor
           SET quality_status = %(quality_status)s,
               identity_status = %(identity_status)s,
               updated_at = now()
         WHERE professor_id = %(professor_id)s
        """,
        {
            "professor_id": professor_id,
            "quality_status": quality_status,
            "identity_status": _quality_to_identity_status(quality_status),
        },
    )


def _file_recrawl_issue(
    conn: Any, *, professor_id: str, actor: str, note: str | None
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id,
            stage,
            severity,
            description,
            evidence_snapshot,
            reported_by
        )
        VALUES (
            %(professor_id)s,
            'coverage',
            'medium',
            %(description)s,
            %(evidence_snapshot)s,
            'admin-console'
        )
        """,
        {
            "professor_id": professor_id,
            "description": "admin requested professor recrawl",
            "evidence_snapshot": Jsonb({"actor": actor, "note": note}),
        },
    )


def _load_affiliations(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT pa.institution,
               pa.department,
               pa.title,
               pa.is_primary,
               pa.is_current,
               sp.url AS source_page_url
          FROM professor_affiliation pa
          LEFT JOIN source_page sp ON sp.page_id = pa.source_page_id
         WHERE pa.professor_id = %(professor_id)s
         ORDER BY pa.is_primary DESC, pa.is_current DESC, pa.created_at ASC
        """,
        {"professor_id": professor_id},
    ).fetchall()


def _load_facts(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT pf.fact_type,
               pf.value_raw,
               pf.confidence,
               sp.url AS source_page_url
          FROM professor_fact pf
          LEFT JOIN source_page sp ON sp.page_id = pf.source_page_id
         WHERE pf.professor_id = %(professor_id)s
           AND pf.status = 'active'
         ORDER BY pf.fact_type ASC, pf.confidence DESC NULLS LAST
        """,
        {"professor_id": professor_id},
    ).fetchall()


def _load_papers(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        WITH resolved_links AS (
            SELECT COALESCE(pma.canonical_paper_id, ppl.paper_id) AS resolved_paper_id,
                   ppl.topic_consistency_score,
                   ppl.evidence_page_id,
                   ppl.is_officially_listed
              FROM professor_paper_link ppl
              LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = ppl.paper_id
             WHERE ppl.professor_id = %(professor_id)s
               AND ppl.link_status = 'verified'
        ),
        ranked_papers AS (
            SELECT p.paper_id,
                   p.title_clean,
                   p.year,
                   p.quality_status,
                   p.canonical_source,
                   p.doi,
                   p.arxiv_id,
                   pft.pdf_url,
                   CASE
                       WHEN NULLIF(BTRIM(p.doi), '') IS NOT NULL
                            AND p.doi ~* '^https?://'
                         THEN p.doi
                       WHEN NULLIF(BTRIM(p.doi), '') IS NOT NULL
                         THEN 'https://doi.org/' || p.doi
                       WHEN NULLIF(BTRIM(p.arxiv_id), '') IS NOT NULL
                         THEN 'https://arxiv.org/abs/' || p.arxiv_id
                       ELSE pft.pdf_url
                   END AS external_url,
                   sp.url AS source_page_url,
                   row_number() OVER (
                       PARTITION BY
                           lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                           p.year
                       ORDER BY
                           CASE WHEN p.canonical_source = 'prof_page_only' THEN 1 ELSE 0 END,
                           COALESCE(p.quality_status = 'ready', false) DESC,
                           rl.is_officially_listed DESC,
                           rl.topic_consistency_score DESC NULLS LAST,
                           p.citation_count DESC NULLS LAST,
                           p.paper_id ASC
                   ) AS duplicate_rank
              FROM resolved_links rl
              JOIN paper p ON p.paper_id = rl.resolved_paper_id
              LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id
              LEFT JOIN source_page sp ON sp.page_id = rl.evidence_page_id
             WHERE COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')
        )
        SELECT paper_id,
               title_clean,
               year,
               quality_status,
               canonical_source,
               doi,
               arxiv_id,
               pdf_url,
               external_url,
               source_page_url
          FROM ranked_papers
         WHERE duplicate_rank = 1
         ORDER BY year DESC NULLS LAST, paper_id ASC
         LIMIT 20
        """,
        {"professor_id": professor_id},
    ).fetchall()


def _load_patents(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT patent.patent_id,
               patent.title_clean,
               patent.patent_number
          FROM professor_patent_link ppl
          JOIN patent ON patent.patent_id = ppl.patent_id
         WHERE ppl.professor_id = %(professor_id)s
         ORDER BY patent.publication_date DESC NULLS LAST, patent.patent_id ASC
         LIMIT 20
        """,
        {"professor_id": professor_id},
    ).fetchall()


def _load_sources(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT url,
               page_role,
               is_official_source,
               fetched_at
          FROM source_page
         WHERE owner_scope_kind = 'professor'
           AND owner_scope_ref = %(professor_id)s
         ORDER BY is_official_source DESC, fetched_at DESC NULLS LAST
         LIMIT 50
        """,
        {"professor_id": professor_id},
    ).fetchall()


def _load_issues(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT issue_id,
               stage,
               severity,
               description,
               evidence_snapshot,
               reported_by,
               reported_at
          FROM pipeline_issue
         WHERE professor_id = %(professor_id)s
           AND resolved = false
         ORDER BY reported_at DESC
        """,
        {"professor_id": professor_id},
    ).fetchall()


def _load_actions(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT action,
               actor,
               note,
               observed_data_updated_at,
               created_at
          FROM professor_admin_action
         WHERE professor_id = %(professor_id)s
         ORDER BY created_at DESC
         LIMIT 20
        """,
        {"professor_id": professor_id},
    ).fetchall()
