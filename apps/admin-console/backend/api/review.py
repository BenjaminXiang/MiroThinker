from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

import psycopg
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.api.data import PaperSummaryWithProvenance
from backend.deps import get_pg_conn

router = APIRouter()

PipelineStage = Literal[
    "discovery",
    "name_extraction",
    "affiliation",
    "paper_attribution",
    "paper_quality",
    "research_directions",
    "identity_gate",
    "coverage",
    "data_quality_flag",
]
PipelineSeverity = Literal["high", "medium", "low"]

ISSUE_COLUMNS_SQL = """
    issue_id,
    professor_id,
    link_id,
    institution,
    stage,
    severity,
    description,
    evidence_snapshot,
    reported_by,
    reported_at,
    resolved,
    resolved_at,
    resolution_notes,
    resolution_round
"""


class ProfessorSample(BaseModel):
    professor_id: str
    canonical_name: str
    canonical_name_en: str | None = None
    institution: str | None = None
    primary_profile_url: str | None = None
    research_directions: list[str] = Field(default_factory=list)
    research_directions_source: str | None = None
    verified_papers: list[PaperSummaryWithProvenance] = Field(default_factory=list)
    rejected_papers: list[PaperSummaryWithProvenance] = Field(default_factory=list)
    facts_by_type: dict[str, int] = Field(default_factory=dict)


class PipelineIssueCreate(BaseModel):
    professor_id: str | None = None
    link_id: str | None = None
    institution: str | None = None
    stage: PipelineStage
    severity: PipelineSeverity
    description: str
    reported_by: str

    @model_validator(mode="after")
    def validate_has_target(self) -> PipelineIssueCreate:
        if (
            self.professor_id is None
            and self.link_id is None
            and self.institution is None
        ):
            raise ValueError(
                "issue requires at least one target (professor_id, link_id, or institution)"
            )
        return self


class PipelineIssue(BaseModel):
    issue_id: str
    professor_id: str | None = None
    link_id: str | None = None
    institution: str | None = None
    stage: str
    severity: str
    description: str
    evidence_snapshot: dict[str, Any] | None = None
    reported_by: str
    reported_at: datetime
    resolved: bool
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    resolution_round: str | None = None

    # psycopg returns uuid.UUID for uuid columns; coerce to string so the
    # wire format stays simple and tests can use the IDs as URL segments.
    @field_validator("issue_id", "link_id", mode="before")
    @classmethod
    def _uuid_to_str(cls, value):
        if value is None:
            return None
        return str(value)


class ResolveIssueRequest(BaseModel):
    resolution_notes: str | None = None
    resolution_round: str | None = None


SAMPLE_PROFESSORS_SQL = """
SELECT
    p.professor_id,
    p.canonical_name,
    p.canonical_name_en,
    primary_affiliation.institution,
    sp.url AS primary_profile_url,
    NULL::text AS research_directions_source
FROM professor p
LEFT JOIN LATERAL (
    SELECT pa.institution
    FROM professor_affiliation pa
    WHERE pa.professor_id = p.professor_id
      AND pa.is_primary = true
    ORDER BY
        pa.is_current DESC,
        pa.start_year DESC NULLS LAST,
        pa.created_at DESC NULLS LAST,
        pa.affiliation_id DESC
    LIMIT 1
) primary_affiliation ON TRUE
LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
WHERE primary_affiliation.institution = COALESCE(%s, primary_affiliation.institution)
ORDER BY hashtext(p.professor_id || COALESCE(%s, 'default'))
LIMIT %s
"""

SAMPLE_FACT_COUNTS_SQL = """
SELECT
    pf.professor_id,
    pf.fact_type,
    count(*)::int AS fact_count
FROM professor_fact pf
WHERE pf.professor_id = ANY(%s)
  AND pf.status = 'active'
GROUP BY pf.professor_id, pf.fact_type
ORDER BY pf.professor_id, pf.fact_type
"""

SAMPLE_RESEARCH_DIRECTIONS_SQL = """
SELECT professor_id, research_direction
FROM (
    SELECT
        pf.professor_id,
        COALESCE(pf.value_normalized, pf.value_raw) AS research_direction,
        row_number() OVER (
            PARTITION BY pf.professor_id
            ORDER BY
                pf.confidence DESC NULLS LAST,
                pf.created_at DESC NULLS LAST,
                pf.fact_id ASC
        ) AS rank_in_professor
    FROM professor_fact pf
    WHERE pf.professor_id = ANY(%s)
      AND pf.fact_type = 'research_topic'
      AND pf.status = 'active'
) ranked
WHERE rank_in_professor <= 5
ORDER BY professor_id, rank_in_professor
"""

SAMPLE_VERIFIED_PAPERS_SQL = """
SELECT
    professor_id,
    paper_id,
    title_clean,
    year,
    venue,
    citation_count,
    authors_display,
    canonical_source,
    topic_consistency_score,
    link_status,
    match_reason,
    rejected_reason,
    verified_by,
    verified_at,
    evidence_api_source,
    evidence_page_url,
    is_officially_listed
FROM (
    SELECT
        ppl.professor_id,
        p.paper_id,
        p.title_clean,
        p.year,
        p.venue,
        p.citation_count,
        p.authors_display,
        p.canonical_source,
        ppl.topic_consistency_score,
        ppl.link_status,
        ppl.match_reason,
        ppl.rejected_reason,
        ppl.verified_by,
        ppl.verified_at,
        ppl.evidence_api_source,
        ep.url AS evidence_page_url,
        ppl.is_officially_listed,
        row_number() OVER (
            PARTITION BY ppl.professor_id
            ORDER BY
                ppl.topic_consistency_score DESC NULLS LAST,
                p.citation_count DESC NULLS LAST,
                p.year DESC NULLS LAST,
                p.title_clean ASC
        ) AS rank_in_professor
    FROM professor_paper_link ppl
    JOIN paper p ON p.paper_id = ppl.paper_id
    LEFT JOIN source_page ep ON ep.page_id = ppl.evidence_page_id
    WHERE ppl.professor_id = ANY(%s)
      AND ppl.link_status = 'verified'
) ranked
WHERE rank_in_professor <= 3
ORDER BY professor_id, rank_in_professor
"""

SAMPLE_REJECTED_PAPERS_SQL = """
SELECT
    professor_id,
    paper_id,
    title_clean,
    year,
    venue,
    citation_count,
    authors_display,
    canonical_source,
    topic_consistency_score,
    link_status,
    match_reason,
    rejected_reason,
    verified_by,
    verified_at,
    evidence_api_source,
    evidence_page_url,
    is_officially_listed
FROM (
    SELECT
        ppl.professor_id,
        p.paper_id,
        p.title_clean,
        p.year,
        p.venue,
        p.citation_count,
        p.authors_display,
        p.canonical_source,
        ppl.topic_consistency_score,
        ppl.link_status,
        ppl.match_reason,
        ppl.rejected_reason,
        ppl.verified_by,
        ppl.verified_at,
        ppl.evidence_api_source,
        ep.url AS evidence_page_url,
        ppl.is_officially_listed,
        row_number() OVER (
            PARTITION BY ppl.professor_id
            ORDER BY
                ppl.rejected_at DESC NULLS LAST,
                p.citation_count DESC NULLS LAST,
                p.year DESC NULLS LAST,
                p.title_clean ASC
        ) AS rank_in_professor
    FROM professor_paper_link ppl
    JOIN paper p ON p.paper_id = ppl.paper_id
    LEFT JOIN source_page ep ON ep.page_id = ppl.evidence_page_id
    WHERE ppl.professor_id = ANY(%s)
      AND ppl.link_status = 'rejected'
) ranked
WHERE rank_in_professor <= 3
ORDER BY professor_id, rank_in_professor
"""

PROFESSOR_SNAPSHOT_SQL = """
SELECT
    p.professor_id,
    p.canonical_name,
    p.canonical_name_en,
    primary_affiliation.institution,
    sp.url AS primary_profile_url
FROM professor p
LEFT JOIN LATERAL (
    SELECT pa.institution
    FROM professor_affiliation pa
    WHERE pa.professor_id = p.professor_id
      AND pa.is_primary = true
    ORDER BY
        pa.is_current DESC,
        pa.start_year DESC NULLS LAST,
        pa.created_at DESC NULLS LAST,
        pa.affiliation_id DESC
    LIMIT 1
) primary_affiliation ON TRUE
LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
WHERE p.professor_id = %s
"""

PROFESSOR_RESEARCH_TOPICS_SQL = """
SELECT COALESCE(pf.value_normalized, pf.value_raw) AS research_topic
FROM professor_fact pf
WHERE pf.professor_id = %s
  AND pf.fact_type = 'research_topic'
  AND pf.status = 'active'
ORDER BY
    pf.confidence DESC NULLS LAST,
    pf.created_at DESC NULLS LAST,
    pf.fact_id ASC
LIMIT 5
"""

LINK_AND_PAPER_SNAPSHOT_SQL = """
SELECT
    ppl.link_id,
    ppl.professor_id,
    ppl.paper_id,
    ppl.link_status,
    ppl.match_reason,
    ppl.rejected_reason,
    ppl.topic_consistency_score,
    ppl.verified_by,
    ppl.verified_at,
    ppl.evidence_api_source,
    ep.url AS evidence_page_url,
    ppl.is_officially_listed,
    p.title_clean,
    p.year,
    p.venue,
    p.authors_display,
    p.doi,
    p.openalex_id,
    p.canonical_source
FROM professor_paper_link ppl
LEFT JOIN paper p ON p.paper_id = ppl.paper_id
LEFT JOIN source_page ep ON ep.page_id = ppl.evidence_page_id
WHERE ppl.link_id = %s
"""


def _sample_paper_groups(
    conn: Any,
    professor_ids: list[str],
    *,
    query: str,
) -> dict[str, list[PaperSummaryWithProvenance]]:
    grouped: dict[str, list[PaperSummaryWithProvenance]] = defaultdict(list)
    if not professor_ids:
        return grouped
    rows = conn.execute(query, (professor_ids,)).fetchall()
    for row in rows:
        payload = dict(row)
        professor_id = payload.pop("professor_id")
        grouped[professor_id].append(
            PaperSummaryWithProvenance.model_validate(payload)
        )
    return grouped


def _pipeline_issue_from_row(row: Any) -> PipelineIssue:
    payload = dict(row)
    return PipelineIssue.model_validate(payload)


def _professor_snapshot(conn: Any, professor_id: str) -> tuple[str | None, dict[str, Any]]:
    row = conn.execute(PROFESSOR_SNAPSHOT_SQL, (professor_id,)).fetchone()
    if row is None:
        return None, {"error": "target not found", "professor_id": professor_id}

    payload = dict(row)
    research_topics = [
        topic_row["research_topic"]
        for topic_row in conn.execute(PROFESSOR_RESEARCH_TOPICS_SQL, (professor_id,)).fetchall()
        if topic_row["research_topic"]
    ]
    institution = payload.get("institution")
    return institution, {
        "professor_id": payload["professor_id"],
        "canonical_name": payload["canonical_name"],
        "canonical_name_en": payload["canonical_name_en"],
        "institution": institution,
        "primary_profile_url": payload["primary_profile_url"],
        "research_topics": research_topics,
    }


def _paper_and_link_snapshot(
    conn: Any,
    link_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = conn.execute(LINK_AND_PAPER_SNAPSHOT_SQL, (link_id,)).fetchone()
    if row is None:
        error = {"error": "target not found", "link_id": link_id}
        return error, error

    payload = dict(row)
    paper_snapshot = {
        "paper_id": payload["paper_id"],
        "title_clean": payload["title_clean"],
        "authors_display": payload["authors_display"],
        "venue": payload["venue"],
        "year": payload["year"],
        "doi": payload["doi"],
        "openalex_id": payload["openalex_id"],
        "canonical_source": payload["canonical_source"],
    }
    link_snapshot = {
        "link_id": str(payload["link_id"]),
        "professor_id": payload["professor_id"],
        "paper_id": payload["paper_id"],
        "link_status": payload["link_status"],
        "match_reason": payload["match_reason"],
        "rejected_reason": payload["rejected_reason"],
        "topic_consistency_score": payload["topic_consistency_score"],
        "verified_by": payload["verified_by"],
        "verified_at": payload["verified_at"],
        "evidence_api_source": payload["evidence_api_source"],
        "evidence_page_url": payload["evidence_page_url"],
        "is_officially_listed": payload["is_officially_listed"],
    }
    return paper_snapshot, link_snapshot


def _build_evidence_snapshot(
    conn: Any,
    body: PipelineIssueCreate,
) -> tuple[str | None, str | None, dict[str, Any]]:
    professor_id = body.professor_id
    link_id = body.link_id
    professor_snapshot: dict[str, Any] | None = None
    paper_snapshot: dict[str, Any] | None = None
    link_snapshot: dict[str, Any] | None = None

    if professor_id is not None:
        _, professor_snapshot = _professor_snapshot(conn, professor_id)
        if professor_snapshot.get("error") == "target not found":
            professor_id = None

    if link_id is not None:
        paper_snapshot, link_snapshot = _paper_and_link_snapshot(conn, link_id)
        if link_snapshot.get("error") == "target not found":
            link_id = None

    snapshot = {
        "type": f"{body.stage}_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "professor": professor_snapshot,
        "paper": paper_snapshot,
        "link": link_snapshot,
        "institution": body.institution,
    }
    return professor_id, link_id, snapshot


@router.get("/api/review/sample", response_model=list[ProfessorSample])
def sample_professors(
    institution: str | None = Query(default=None),
    n: int = Query(default=10, ge=1, le=100),
    seed: str | None = Query(default=None),
    conn: Any = Depends(get_pg_conn),
) -> list[ProfessorSample]:
    sample_rows = conn.execute(SAMPLE_PROFESSORS_SQL, (institution, seed, n)).fetchall()
    if not sample_rows:
        return []

    base_rows = [dict(row) for row in sample_rows]
    professor_ids = [row["professor_id"] for row in base_rows]

    fact_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for row in conn.execute(SAMPLE_FACT_COUNTS_SQL, (professor_ids,)).fetchall():
        fact_counts[row["professor_id"]][row["fact_type"]] = int(row["fact_count"])

    research_directions: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute(
        SAMPLE_RESEARCH_DIRECTIONS_SQL, (professor_ids,)
    ).fetchall():
        research_directions[row["professor_id"]].append(row["research_direction"])

    verified_papers = _sample_paper_groups(
        conn,
        professor_ids,
        query=SAMPLE_VERIFIED_PAPERS_SQL,
    )
    rejected_papers = _sample_paper_groups(
        conn,
        professor_ids,
        query=SAMPLE_REJECTED_PAPERS_SQL,
    )

    return [
        ProfessorSample(
            professor_id=row["professor_id"],
            canonical_name=row["canonical_name"],
            canonical_name_en=row["canonical_name_en"],
            institution=row["institution"],
            primary_profile_url=row["primary_profile_url"],
            research_directions=research_directions.get(row["professor_id"], []),
            research_directions_source=row["research_directions_source"],
            verified_papers=verified_papers.get(row["professor_id"], []),
            rejected_papers=rejected_papers.get(row["professor_id"], []),
            facts_by_type=fact_counts.get(row["professor_id"], {}),
        )
        for row in base_rows
    ]


@router.post("/api/review/issues", response_model=PipelineIssue, status_code=201)
def report_issue(
    body: PipelineIssueCreate,
    conn: Any = Depends(get_pg_conn),
) -> PipelineIssue:
    try:
        with conn.transaction():
            professor_id, link_id, evidence_snapshot = _build_evidence_snapshot(
                conn, body
            )
            created_row = conn.execute(
                f"""
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {ISSUE_COLUMNS_SQL}
                """,
                (
                    professor_id,
                    link_id,
                    body.institution,
                    body.stage,
                    body.severity,
                    body.description,
                    Jsonb(jsonable_encoder(evidence_snapshot)),
                    body.reported_by,
                ),
            ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="duplicate open issue") from exc
    except psycopg.errors.CheckViolation as exc:
        constraint_name = getattr(getattr(exc, "diag", None), "constraint_name", "")
        if constraint_name == "ck_pipeline_issue_has_target":
            raise HTTPException(
                status_code=400,
                detail=(
                    "issue requires at least one target "
                    "(professor_id, link_id, or institution)"
                ),
            ) from exc
        raise HTTPException(status_code=400, detail="invalid issue payload") from exc

    if created_row is None:
        raise HTTPException(status_code=500, detail="Issue insert failed")
    return _pipeline_issue_from_row(created_row)


@router.get("/api/review/issues", response_model=list[PipelineIssue])
def list_issues(
    resolved: bool | None = Query(default=None),
    stage: PipelineStage | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Any = Depends(get_pg_conn),
) -> list[PipelineIssue]:
    rows = conn.execute(
        f"""
        SELECT {ISSUE_COLUMNS_SQL}
        FROM pipeline_issue
        WHERE (%s::boolean IS NULL OR resolved = %s::boolean)
          AND (%s::text IS NULL OR stage = %s::text)
        ORDER BY reported_at DESC
        LIMIT %s
        """,
        (resolved, resolved, stage, stage, limit),
    ).fetchall()
    return [_pipeline_issue_from_row(row) for row in rows]


@router.patch("/api/review/issues/{issue_id}/resolve", response_model=PipelineIssue)
def resolve_issue(
    issue_id: str,
    body: ResolveIssueRequest,
    conn: Any = Depends(get_pg_conn),
) -> PipelineIssue:
    with conn.transaction():
        row = conn.execute(
            f"""
            UPDATE pipeline_issue
               SET resolved = true,
                   resolved_at = now(),
                   resolution_notes = %s,
                   resolution_round = %s
             WHERE issue_id = %s
         RETURNING {ISSUE_COLUMNS_SQL}
            """,
            (body.resolution_notes, body.resolution_round, issue_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return _pipeline_issue_from_row(row)
