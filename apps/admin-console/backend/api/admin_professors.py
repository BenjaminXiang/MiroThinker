from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn
from src.data_agents.professor.quality_gate import (
    ProfessorAdminAction,
    evaluate_professor_quality,
    load_professor_canonical_state,
)

router = APIRouter(prefix="/api/admin/professor", tags=["admin-professor"])

ADMIN_ACTIONS = {"confirm_ready", "send_to_review", "flag_recrawl"}
QUALITY_STATUSES = {"ready", "needs_review", "low_confidence", "needs_enrichment"}
_RULE_RE = re.compile(r"\[[^:\]]+:([^\]]+)\]")


class MarkProfessorRequest(BaseModel):
    action: Literal["confirm_ready", "send_to_review", "flag_recrawl"]
    note: str | None = Field(default=None, max_length=2000)


def _actor_from_header(x_admin_actor: str | None) -> str:
    actor = (x_admin_actor or "").strip()
    return actor or "admin-console"


def _rule_id_from_issue(row: dict[str, Any]) -> str | None:
    evidence = row.get("evidence_snapshot") or {}
    if isinstance(evidence, dict) and evidence.get("rule_id"):
        return str(evidence["rule_id"])
    match = _RULE_RE.search(str(row.get("description") or ""))
    return match.group(1) if match else None


def _latest_admin_action(conn: Any, professor_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT action_id,
               action,
               actor,
               note,
               observed_data_updated_at,
               created_at
          FROM professor_admin_action
         WHERE professor_id = %s
         ORDER BY created_at DESC, action_id DESC
         LIMIT 1
        """,
        (professor_id,),
    ).fetchone()
    return dict(row) if row else None


def _canonical_watermark(conn: Any, professor_id: str) -> datetime:
    row = conn.execute(
        """
        SELECT COALESCE(max(watermark), now()) AS watermark
          FROM (
                SELECT p.updated_at AS watermark
                  FROM professor p
                 WHERE p.professor_id = %s
                UNION ALL
                SELECT pf.updated_at
                  FROM professor_fact pf
                 WHERE pf.professor_id = %s
                UNION ALL
                SELECT pa.updated_at
                  FROM professor_affiliation pa
                 WHERE pa.professor_id = %s
                UNION ALL
                SELECT pi.reported_at
                  FROM pipeline_issue pi
                 WHERE pi.professor_id = %s
                   AND pi.resolved = false
                   AND pi.reported_by <> 'professor_quality_gate'
          ) watermarks
        """,
        (professor_id, professor_id, professor_id, professor_id),
    ).fetchone()
    return row["watermark"]


@router.get("")
def list_admin_professors(
    quality_status: str | None = Query(default=None),
    reason_rule_id: str | None = Query(default=None),
    latest_admin_action: str | None = Query(default=None),
    has_official_source: bool | None = Query(default=None),
    sort_by: str = Query(default="display_name"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    if quality_status and quality_status not in QUALITY_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid quality_status")
    if latest_admin_action and latest_admin_action not in ADMIN_ACTIONS:
        raise HTTPException(status_code=422, detail="Invalid latest_admin_action")

    conditions: list[str] = []
    params: list[Any] = []
    if quality_status:
        conditions.append("p.quality_status = %s")
        params.append(quality_status)
    if reason_rule_id:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                  FROM pipeline_issue pi_filter
                 WHERE pi_filter.professor_id = p.professor_id
                   AND pi_filter.resolved = false
                   AND (
                        pi_filter.evidence_snapshot->>'rule_id' = %s
                        OR substring(pi_filter.description from '\\[[^:\\]]+:([^\\]]+)\\]') = %s
                   )
            )
            """
        )
        params.extend([reason_rule_id, reason_rule_id])
    if latest_admin_action:
        conditions.append("latest_action.action = %s")
        params.append(latest_admin_action)
    if has_official_source is not None:
        conditions.append("sp.page_id IS NOT NULL = %s")
        params.append(has_official_source)

    sort_columns = {
        "display_name": "p.canonical_name",
        "quality_status": "p.quality_status",
        "open_issue_count": "COALESCE(open_issues.open_issue_count, 0)",
        "latest_admin_action": "latest_action.action",
        "has_official_source": "sp.page_id",
    }
    sort_column = sort_columns.get(sort_by, "p.canonical_name")
    order_sql = "DESC" if sort_order == "desc" else "ASC"
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        WITH open_issues AS (
            SELECT professor_id,
                   count(*)::int AS open_issue_count,
                   array_remove(
                       array_agg(DISTINCT COALESCE(
                           evidence_snapshot->>'rule_id',
                           substring(description from '\\[[^:\\]]+:([^\\]]+)\\]')
                       )),
                       NULL
                   ) AS reason_rule_ids
              FROM pipeline_issue
             WHERE resolved = false
             GROUP BY professor_id
        )
        SELECT p.professor_id,
               p.canonical_name AS display_name,
               primary_affiliation.institution,
               p.quality_status,
               COALESCE(open_issues.open_issue_count, 0) AS open_issue_count,
               COALESCE(open_issues.reason_rule_ids, ARRAY[]::text[]) AS reason_rule_ids,
               sp.page_id IS NOT NULL AS official_source_present,
               latest_action.action AS latest_admin_action,
               latest_action.created_at AS latest_admin_action_at,
               count(*) OVER() AS total_count
          FROM professor p
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
           AND sp.is_official_source = true
          LEFT JOIN LATERAL (
              SELECT pa.institution
                FROM professor_affiliation pa
               WHERE pa.professor_id = p.professor_id
               ORDER BY pa.is_primary DESC,
                        pa.is_current DESC,
                        pa.created_at DESC,
                        pa.affiliation_id DESC
               LIMIT 1
          ) primary_affiliation ON true
          LEFT JOIN open_issues
            ON open_issues.professor_id = p.professor_id
          LEFT JOIN LATERAL (
              SELECT action, created_at
                FROM professor_admin_action paa
               WHERE paa.professor_id = p.professor_id
               ORDER BY created_at DESC, action_id DESC
               LIMIT 1
          ) latest_action ON true
          {where_sql}
         ORDER BY {sort_column} {order_sql} NULLS LAST, p.professor_id ASC
         LIMIT %s OFFSET %s
        """,
        (*params, page_size, offset),
    ).fetchall()

    total = int(rows[0]["total_count"]) if rows else 0
    items = []
    for row in rows:
        latest_action = None
        if row.get("latest_admin_action"):
            latest_action = {
                "action": row["latest_admin_action"],
                "created_at": row["latest_admin_action_at"],
            }
        items.append(
            {
                "professor_id": row["professor_id"],
                "display_name": row["display_name"],
                "institution": row["institution"],
                "quality_status": row["quality_status"],
                "open_issue_count": row["open_issue_count"],
                "latest_admin_action": latest_action,
                "official_source_present": row["official_source_present"],
                "reason_rule_ids": row["reason_rule_ids"] or [],
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{professor_id}")
def get_admin_professor_detail(
    professor_id: str,
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    professor = conn.execute(
        """
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               p.canonical_name_zh,
               p.aliases,
               p.discipline_family,
               p.identity_status,
               p.quality_status,
               p.profile_summary,
               p.h_index,
               p.citation_count,
               p.paper_count,
               p.updated_at,
               sp.page_id AS primary_source_page_id,
               sp.url AS primary_source_url,
               sp.fetched_at AS primary_source_fetched_at,
               sp.page_role AS primary_source_role,
               sp.is_official_source AS primary_source_is_official
          FROM professor p
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if professor is None:
        raise HTTPException(status_code=404, detail="Professor not found")

    affiliations = [
        dict(row)
        for row in conn.execute(
            """
            SELECT pa.institution,
                   pa.department,
                   pa.title,
                   pa.is_primary,
                   pa.is_current,
                   pa.updated_at,
                   sp.url AS source_url,
                   sp.page_role AS source_role,
                   sp.fetched_at AS source_fetched_at,
                   sp.is_official_source
              FROM professor_affiliation pa
              LEFT JOIN source_page sp ON sp.page_id = pa.source_page_id
             WHERE pa.professor_id = %s
             ORDER BY pa.is_primary DESC,
                      pa.is_current DESC,
                      pa.created_at DESC,
                      pa.affiliation_id DESC
            """,
            (professor_id,),
        ).fetchall()
    ]
    facts = [
        _fact_payload(row)
        for row in conn.execute(
            """
            SELECT pf.fact_type,
                   pf.value_raw,
                   pf.value_normalized,
                   pf.evidence_span,
                   pf.confidence,
                   pf.status,
                   pf.updated_at,
                   sp.url AS source_url,
                   sp.page_role AS source_role,
                   sp.fetched_at AS source_fetched_at,
                   sp.is_official_source
              FROM professor_fact pf
              LEFT JOIN source_page sp ON sp.page_id = pf.source_page_id
             WHERE pf.professor_id = %s
               AND pf.status = 'active'
             ORDER BY pf.fact_type, pf.created_at, pf.fact_id
            """,
            (professor_id,),
        ).fetchall()
    ]
    open_issues = [
        _issue_payload(row)
        for row in conn.execute(
            """
            SELECT issue_id,
                   stage,
                   severity,
                   description,
                   evidence_snapshot,
                   reported_by,
                   reported_at
              FROM pipeline_issue
             WHERE professor_id = %s
               AND resolved = false
             ORDER BY severity DESC, reported_at DESC, issue_id DESC
            """,
            (professor_id,),
        ).fetchall()
    ]

    latest_action = _latest_admin_action(conn, professor_id)
    latest_action_input = (
        ProfessorAdminAction(
            action=str(latest_action["action"]),
            observed_data_updated_at=latest_action["observed_data_updated_at"],
        )
        if latest_action
        else None
    )
    state = load_professor_canonical_state(conn, professor_id)
    evaluation = evaluate_professor_quality(
        state,
        latest_admin_action=latest_action_input,
    )
    primary_affiliation = affiliations[0] if affiliations else {}
    facts_by_type = _facts_by_type(facts)
    experience_facts = {
        fact_type: values
        for fact_type, values in facts_by_type.items()
        if fact_type in {"education", "work_experience", "award", "academic_position"}
    }
    contact_facts = {
        fact_type: values
        for fact_type, values in facts_by_type.items()
        if fact_type in {"contact", "homepage"}
    }
    research_facts = facts_by_type.get("research_topic", [])

    return {
        "identity": {
            "professor_id": professor["professor_id"],
            "canonical_name": professor["canonical_name"],
            "canonical_name_en": professor["canonical_name_en"],
            "canonical_name_zh": professor["canonical_name_zh"],
            "aliases": professor["aliases"] or [],
            "institution": primary_affiliation.get("institution"),
            "department": primary_affiliation.get("department"),
            "title": primary_affiliation.get("title"),
            "discipline_family": professor["discipline_family"],
            "identity_status": professor["identity_status"],
        },
        "contact": {
            "facts": contact_facts,
            "official_profile_url": professor["primary_source_url"],
        },
        "research_and_output": {
            "research_topics": research_facts,
            "h_index": professor["h_index"],
            "citation_count": professor["citation_count"],
            "paper_count": professor["paper_count"],
            "representative_papers": [],
        },
        "experience": {
            "status": "populated" if experience_facts else "not_extracted",
            "facts": experience_facts,
        },
        "cleaned_summary": {
            "profile_summary": professor["profile_summary"],
        },
        "sources_and_evidence": {
            "primary_source": {
                "page_id": professor["primary_source_page_id"],
                "url": professor["primary_source_url"],
                "fetched_at": professor["primary_source_fetched_at"],
                "page_role": professor["primary_source_role"],
                "is_official_source": professor["primary_source_is_official"],
            },
            "affiliations": affiliations,
            "provenance": facts,
        },
        "quality_diagnosis": {
            "status": evaluation.quality_status,
            "reasons": [
                {
                    "rule_id": reason.rule_id,
                    "stage": reason.stage,
                    "message": reason.message,
                }
                for reason in evaluation.reasons
            ],
            "open_issues": open_issues,
            "latest_admin_action": latest_action,
        },
    }


@router.post("/{professor_id}/mark")
def mark_admin_professor(
    professor_id: str,
    body: MarkProfessorRequest,
    x_admin_actor: str | None = Header(default=None, alias="X-Admin-Actor"),
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    professor = conn.execute(
        "SELECT quality_status FROM professor WHERE professor_id = %s",
        (professor_id,),
    ).fetchone()
    if professor is None:
        raise HTTPException(status_code=404, detail="Professor not found")

    actor = _actor_from_header(x_admin_actor)
    watermark = _canonical_watermark(conn, professor_id)
    pipeline_issue = None
    with conn.transaction():
        action = conn.execute(
            """
            INSERT INTO professor_admin_action (
                professor_id,
                action,
                actor,
                note,
                observed_data_updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING action_id,
                      professor_id,
                      action,
                      actor,
                      note,
                      observed_data_updated_at,
                      created_at
            """,
            (professor_id, body.action, actor, body.note, watermark),
        ).fetchone()
        if body.action in {"confirm_ready", "send_to_review"}:
            next_status = "ready" if body.action == "confirm_ready" else "needs_review"
            conn.execute(
                """
                UPDATE professor
                   SET quality_status = %s,
                       updated_at = now()
                 WHERE professor_id = %s
                """,
                (next_status, professor_id),
            )
        else:
            next_status = str(professor["quality_status"])
            pipeline_issue = conn.execute(
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
                    %s,
                    'data_quality_flag',
                    'medium',
                    %s,
                    %s::jsonb,
                    'admin:flag_recrawl'
                )
                ON CONFLICT DO NOTHING
                RETURNING issue_id, stage, reported_by
                """,
                (
                    professor_id,
                    body.note or "Admin requested professor re-crawl",
                    json.dumps(
                        {
                            "action": body.action,
                            "actor": actor,
                            "professor_id": professor_id,
                        }
                    ),
                ),
            ).fetchone()
    response = {
        "professor_id": professor_id,
        "quality_status": next_status,
        "admin_action": dict(action),
    }
    if pipeline_issue is not None:
        response["pipeline_issue"] = dict(pipeline_issue)
    elif body.action == "flag_recrawl":
        response["pipeline_issue"] = {
            "stage": "data_quality_flag",
            "reported_by": "admin:flag_recrawl",
        }
    return response


def _fact_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_type": row["fact_type"],
        "value_raw": row["value_raw"],
        "value_normalized": row["value_normalized"],
        "evidence_span": row["evidence_span"],
        "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
        "status": row["status"],
        "updated_at": row["updated_at"],
        "source_url": row["source_url"],
        "source_role": row["source_role"],
        "source_fetched_at": row["source_fetched_at"],
        "is_official_source": row["is_official_source"],
    }


def _issue_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["rule_id"] = _rule_id_from_issue(payload)
    return payload


def _facts_by_type(facts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault(str(fact["fact_type"]), []).append(fact)
    return grouped
