from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api/pipeline")

INSTITUTION_COVERAGE_SQL = """
WITH primary_aff AS (
    SELECT DISTINCT ON (pa.professor_id)
        pa.professor_id,
        COALESCE(NULLIF(BTRIM(pa.institution), ''), '[unknown]') AS institution
    FROM professor_affiliation pa
    WHERE pa.is_primary = true
      AND pa.is_current = true
    ORDER BY
        pa.professor_id,
        pa.created_at DESC NULLS LAST,
        pa.affiliation_id DESC
),
verified_professors AS (
    SELECT DISTINCT ppl.professor_id
    FROM professor_paper_link ppl
    JOIN primary_aff pa ON pa.professor_id = ppl.professor_id
    WHERE ppl.link_status = 'verified'
),
research_direction_professors AS (
    SELECT DISTINCT pf.professor_id
    FROM professor_fact pf
    JOIN primary_aff pa ON pa.professor_id = pf.professor_id
    WHERE pf.fact_type = 'research_topic'
      AND pf.status = 'active'
),
institution_professor_rollup AS (
    SELECT
        pa.institution,
        COUNT(DISTINCT pa.professor_id)::int AS professor_count,
        COUNT(DISTINCT vp.professor_id)::int AS with_verified_papers,
        COUNT(DISTINCT rdp.professor_id)::int AS with_research_directions
    FROM primary_aff pa
    LEFT JOIN verified_professors vp ON vp.professor_id = pa.professor_id
    LEFT JOIN research_direction_professors rdp ON rdp.professor_id = pa.professor_id
    GROUP BY pa.institution
),
institution_link_rollup AS (
    SELECT
        pa.institution,
        COUNT(ppl.link_id)::int AS total_link_count,
        COUNT(*) FILTER (WHERE ppl.link_status = 'rejected')::int AS rejected_link_count,
        COUNT(DISTINCT p.paper_id) FILTER (
            WHERE COALESCE(NULLIF(BTRIM(p.authors_display), ''), '') = ''
        )::int AS empty_authors_papers,
        AVG(ppl.topic_consistency_score)::double precision AS avg_topic_consistency_score
    FROM primary_aff pa
    LEFT JOIN professor_paper_link ppl ON ppl.professor_id = pa.professor_id
    LEFT JOIN paper p ON p.paper_id = ppl.paper_id
    GROUP BY pa.institution
)
SELECT
    ipr.institution,
    ipr.professor_count,
    ipr.with_verified_papers,
    ipr.with_research_directions,
    COALESCE(ilr.empty_authors_papers, 0) AS empty_authors_papers,
    COALESCE(
        ilr.rejected_link_count::double precision / NULLIF(ilr.total_link_count, 0),
        0.0
    ) AS identity_gate_rejection_rate,
    ilr.avg_topic_consistency_score
FROM institution_professor_rollup ipr
LEFT JOIN institution_link_rollup ilr ON ilr.institution = ipr.institution
ORDER BY ipr.professor_count DESC, ipr.institution ASC
"""

SOURCE_BREAKDOWN_SQL = """
WITH link_rows AS (
    SELECT
        COALESCE(
            NULLIF(BTRIM(split_part(ppl.evidence_api_source, ':', 1)), ''),
            'unknown'
        ) AS evidence_api_source_bucket,
        COALESCE(NULLIF(BTRIM(ppl.verified_by), ''), 'unassigned') AS verified_by_bucket,
        COALESCE(NULLIF(BTRIM(ppl.link_status), ''), 'unknown') AS link_status_bucket
    FROM professor_paper_link ppl
)
SELECT
    'by_evidence_api_source' AS bucket_kind,
    evidence_api_source_bucket AS bucket_name,
    COUNT(*)::int AS bucket_count
FROM link_rows
GROUP BY evidence_api_source_bucket
UNION ALL
SELECT
    'by_verified_by' AS bucket_kind,
    verified_by_bucket AS bucket_name,
    COUNT(*)::int AS bucket_count
FROM link_rows
GROUP BY verified_by_bucket
UNION ALL
SELECT
    'by_link_status' AS bucket_kind,
    link_status_bucket AS bucket_name,
    COUNT(*)::int AS bucket_count
FROM link_rows
GROUP BY link_status_bucket
ORDER BY bucket_kind ASC, bucket_count DESC, bucket_name ASC
"""


class InstitutionCoverage(BaseModel):
    institution: str
    professor_count: int
    with_verified_papers: int
    with_research_directions: int
    empty_authors_papers: int
    identity_gate_rejection_rate: float
    avg_topic_consistency_score: float | None = None
    anomaly_flags: list[str] = Field(default_factory=list)


class SourceBreakdown(BaseModel):
    by_evidence_api_source: dict[str, int] = Field(default_factory=dict)
    by_verified_by: dict[str, int] = Field(default_factory=dict)
    by_link_status: dict[str, int] = Field(default_factory=dict)


def _anomaly_flags(row: dict[str, Any]) -> list[str]:
    professor_count = row["professor_count"]
    paper_coverage = (
        row["with_verified_papers"] / professor_count if professor_count else 0.0
    )

    flags: list[str] = []
    if row["identity_gate_rejection_rate"] > 0.6:
        flags.append("high_rejection_rate")
    if paper_coverage < 0.2:
        flags.append("low_paper_coverage")
    if row["with_research_directions"] == 0:
        flags.append("no_directions")
    return flags


@router.get(
    "/coverage-by-institution",
    response_model=list[InstitutionCoverage],
)
def list_coverage(
    anomaly_only: bool = False,
    conn: Any = Depends(get_pg_conn),
) -> list[InstitutionCoverage]:
    rows = conn.execute(INSTITUTION_COVERAGE_SQL).fetchall()

    items: list[InstitutionCoverage] = []
    for raw_row in rows:
        row = dict(raw_row)
        row["anomaly_flags"] = _anomaly_flags(row)
        item = InstitutionCoverage.model_validate(row)
        if anomaly_only and not item.anomaly_flags:
            continue
        items.append(item)

    return items


@router.get("/source-breakdown", response_model=SourceBreakdown)
def get_source_breakdown(
    conn: Any = Depends(get_pg_conn),
) -> SourceBreakdown:
    breakdown = SourceBreakdown()

    for raw_row in conn.execute(SOURCE_BREAKDOWN_SQL).fetchall():
        row = dict(raw_row)
        bucket = getattr(breakdown, row["bucket_kind"])
        bucket[row["bucket_name"]] = row["bucket_count"]

    return breakdown
