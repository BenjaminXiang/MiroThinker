from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn
from src.data_agents.company.enrichment_batch import build_miss_reason_buckets
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
)

router = APIRouter(prefix="/api/pipeline")
logger = logging.getLogger(__name__)

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


class PipelineRunItem(BaseModel):
    run_id: str
    run_kind: str
    status: str
    run_scope: dict[str, Any] = Field(default_factory=dict)
    triggered_by: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    items_processed: int | None = None
    items_failed: int | None = None
    error_summary: dict[str, Any] | None = None


class PipelineRunListResponse(BaseModel):
    items: list[PipelineRunItem]
    total: int


class PipelineRunSourcePage(BaseModel):
    page_id: str
    url: str
    title: str | None = None
    clean_text_path: str | None = None
    fetched_at: datetime | None = None


class CompanyEnrichmentCompanyDiagnostic(BaseModel):
    company_id: str
    status: str
    current_stage: str | None = None
    miss_reason: str | None = None
    last_error: str | None = None
    query_count: int = 0
    source_result_count: int = 0
    accepted_source_count: int = 0
    rejected_source_count: int = 0
    product_count: int = 0
    scenario_count: int = 0
    official_product_count: int = 0
    funding_event_count: int = 0
    vector_refreshed: bool = False
    stage_status: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class CompanyEnrichmentBatchStatus(BaseModel):
    batch_id: str
    status: str
    current_stage: str | None = None
    progress_percent: float = 0.0
    companies_total: int
    companies_selected: int
    companies_processed: int
    companies_succeeded: int
    companies_failed: int
    query_count: int = 0
    source_result_count: int = 0
    accepted_source_count: int = 0
    rejected_source_count: int = 0
    product_count: int = 0
    scenario_count: int = 0
    official_product_count: int = 0
    funding_event_count: int = 0
    vector_refreshed_count: int = 0
    llm_failure_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    current_stage_counts: dict[str, int] = Field(default_factory=dict)
    miss_reasons: dict[str, int] = Field(default_factory=dict)
    official_failure_reasons: dict[str, int] = Field(default_factory=dict)
    rejected_candidate_reasons: dict[str, int] = Field(default_factory=dict)
    source_counts_by_adapter: dict[str, dict[str, int]] = Field(default_factory=dict)
    runner_pid: int | None = None
    runner_log_path: str | None = None
    runner_heartbeat_at: datetime | None = None
    runner_last_seen_at: datetime | None = None
    runner_is_stale: bool = False
    last_completed_company_id: str | None = None
    miss_reason_buckets: dict[str, int] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)
    company_diagnostics: list[CompanyEnrichmentCompanyDiagnostic] = Field(
        default_factory=list
    )
    company_diagnostics_truncated: bool = False
    last_error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class PipelineRunDetail(PipelineRunItem):
    source_pages: list[PipelineRunSourcePage] = Field(default_factory=list)
    company_enrichment_batches: list[CompanyEnrichmentBatchStatus] = Field(
        default_factory=list
    )


class PipelineRunActionResponse(BaseModel):
    task_id: str
    status: str
    domain: str
    parent_run_id: str


CompanyEnrichmentStagePreset = Literal[
    "trusted_xlsx",
    "high_trust_sources",
    "full",
]


class CompanyEnrichmentBatchStartRequest(BaseModel):
    limit: int | None = Field(default=100, ge=1, le=10000)
    chunk_size: int = Field(default=20, ge=1, le=500)
    stage_preset: CompanyEnrichmentStagePreset = "high_trust_sources"
    include_failed: bool = False
    skip_milvus: bool = False


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


@router.get("/runs", response_model=PipelineRunListResponse)
def list_pipeline_runs(
    domain: str | None = None,
    triggered_by: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> PipelineRunListResponse:
    rows = conn.execute(
        """
        SELECT
            run_id,
            run_kind,
            status,
            run_scope,
            triggered_by,
            started_at,
            finished_at,
            items_processed,
            items_failed,
            error_summary,
            count(*) OVER()::int AS total_count
          FROM pipeline_run
         WHERE (%(domain)s::text IS NULL OR run_scope->>'domain' = %(domain)s::text)
           AND (%(triggered_by)s::text IS NULL OR triggered_by = %(triggered_by)s::text)
           AND (%(status)s::text IS NULL OR status = %(status)s::text)
         ORDER BY started_at DESC
         LIMIT %(limit)s
        """,
        {
            "domain": domain,
            "triggered_by": triggered_by,
            "status": status,
            "limit": limit,
        },
    ).fetchall()
    items = [_pipeline_run_item(row) for row in rows]
    total = int(_row_value(rows[0], "total_count", 10)) if rows else 0
    return PipelineRunListResponse(items=items, total=total)


@router.get("/runs/{run_id}", response_model=PipelineRunDetail)
def get_pipeline_run(
    run_id: UUID,
    conn: Any = Depends(get_pg_conn),
) -> PipelineRunDetail:
    row = conn.execute(
        """
        SELECT
            run_id,
            run_kind,
            status,
            run_scope,
            triggered_by,
            started_at,
            finished_at,
            items_processed,
            items_failed,
            error_summary
          FROM pipeline_run
         WHERE run_id = %(run_id)s
         LIMIT 1
        """,
        {"run_id": run_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    source_pages = conn.execute(
        """
        SELECT page_id, url, title, clean_text_path, fetched_at
          FROM source_page
         WHERE run_id = %(run_id)s
            OR fetch_run_id = %(run_id)s
         ORDER BY fetched_at DESC NULLS LAST, page_id ASC
        """,
        {"run_id": run_id},
    ).fetchall()
    company_enrichment_batches = conn.execute(
        """
        WITH batch_rows AS (
            SELECT
                batch_id,
                status,
                current_stage,
                companies_total,
                companies_selected,
                companies_processed,
                companies_succeeded,
                companies_failed,
                last_error,
                created_at,
                started_at,
                finished_at,
                updated_at,
                runner_pid,
                runner_log_path,
                runner_heartbeat_at,
                runner_last_seen_at,
                last_completed_company_id,
                miss_reason_buckets,
                quality_report
              FROM company_enrichment_batch
             WHERE upload_task_id = %(run_id)s
        ),
        state_rollup AS (
            SELECT
                s.batch_id,
                COALESCE(sum(s.query_count), 0)::int AS query_count,
                COALESCE(sum(s.source_result_count), 0)::int AS source_result_count,
                COALESCE(sum(s.accepted_source_count), 0)::int AS accepted_source_count,
                COALESCE(sum(s.rejected_source_count), 0)::int AS rejected_source_count,
                COALESCE(sum(s.product_count), 0)::int AS product_count,
                COALESCE(sum(s.scenario_count), 0)::int AS scenario_count,
                COALESCE(sum(s.official_product_count), 0)::int AS official_product_count,
                COALESCE(sum(s.event_count), 0)::int AS funding_event_count,
                count(*) FILTER (WHERE s.milvus_refreshed_at IS NOT NULL)::int
                    AS vector_refreshed_count
              FROM company_enrichment_company_state s
              JOIN batch_rows b ON b.batch_id = s.batch_id
             GROUP BY s.batch_id
        ),
        status_counts AS (
            SELECT batch_id, jsonb_object_agg(status_bucket, status_count) AS payload
              FROM (
                SELECT
                    s.batch_id,
                    COALESCE(NULLIF(BTRIM(s.status), ''), 'unknown') AS status_bucket,
                    count(*)::int AS status_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                 GROUP BY s.batch_id, COALESCE(NULLIF(BTRIM(s.status), ''), 'unknown')
              ) grouped
             GROUP BY batch_id
        ),
        current_stage_counts AS (
            SELECT batch_id, jsonb_object_agg(stage_bucket, stage_count) AS payload
              FROM (
                SELECT
                    s.batch_id,
                    COALESCE(NULLIF(BTRIM(s.current_stage), ''), 'unknown')
                        AS stage_bucket,
                    count(*)::int AS stage_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                 GROUP BY
                    s.batch_id,
                    COALESCE(NULLIF(BTRIM(s.current_stage), ''), 'unknown')
              ) grouped
             GROUP BY batch_id
        ),
        miss_reasons AS (
            SELECT batch_id, jsonb_object_agg(reason, reason_count) AS payload
              FROM (
                SELECT
                    s.batch_id,
                    NULLIF(BTRIM(s.miss_reason), '') AS reason,
                    count(*)::int AS reason_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                 WHERE NULLIF(BTRIM(s.miss_reason), '') IS NOT NULL
                 GROUP BY s.batch_id, NULLIF(BTRIM(s.miss_reason), '')
              ) grouped
             GROUP BY batch_id
        ),
        official_failure_reasons AS (
            SELECT batch_id, jsonb_object_agg(reason, reason_count) AS payload
              FROM (
                SELECT batch_id, reason, count(*)::int AS reason_count
                  FROM (
                    SELECT
                        s.batch_id,
                        COALESCE(
                            NULLIF(
                                BTRIM(
                                    s.stage_status #>> '{official_product_capture,miss_reason}'
                                ),
                                ''
                            ),
                            NULLIF(
                                BTRIM(
                                    s.stage_status #>> '{official_product_capture,last_error}'
                                ),
                                ''
                            ),
                            NULLIF(BTRIM(s.miss_reason), '')
                        ) AS reason
                      FROM company_enrichment_company_state s
                      JOIN batch_rows b ON b.batch_id = s.batch_id
                     WHERE s.stage_status ? 'official_product_capture'
                  ) candidates
                 WHERE reason IS NOT NULL
                 GROUP BY batch_id, reason
              ) grouped
             GROUP BY batch_id
        ),
        rejected_candidate_reasons AS (
            SELECT batch_id, jsonb_object_agg(reason, reason_count) AS payload
              FROM (
                SELECT
                    s.batch_id,
                    reason.key AS reason,
                    sum((reason.value)::int)::int AS reason_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                  CROSS JOIN LATERAL jsonb_each_text(
                    COALESCE(
                        s.stage_status #>
                            '{source_product_extract,rejected_facts,rejected_candidate_reasons}',
                        '{}'::jsonb
                    )
                  ) AS reason(key, value)
                 GROUP BY s.batch_id, reason.key
              ) grouped
             GROUP BY batch_id
        ),
        source_counts AS (
            SELECT batch_id, jsonb_object_agg(source_adapter, payload) AS payload
              FROM (
                SELECT
                    a.batch_id,
                    COALESCE(NULLIF(BTRIM(a.source_adapter), ''), 'unknown')
                        AS source_adapter,
                    jsonb_build_object(
                        'query_count', count(*)::int,
                        'result_count', COALESCE(sum(a.result_count), 0)::int,
                        'accepted_count', COALESCE(sum(a.accepted_count), 0)::int,
                        'rejected_count', COALESCE(sum(
                            a.rejected_offsite
                            + a.rejected_irrelevant_path
                            + a.rejected_name_mismatch
                        ), 0)::int
                    ) AS payload
                  FROM company_enrichment_search_audit a
                  JOIN batch_rows b ON b.batch_id = a.batch_id
                 GROUP BY
                    a.batch_id,
                    COALESCE(NULLIF(BTRIM(a.source_adapter), ''), 'unknown')
              ) grouped
             GROUP BY batch_id
        ),
        llm_rollup AS (
            SELECT
                s.batch_id,
                COALESCE(sum(
                    COALESCE(
                        NULLIF(
                            stage.value #>>
                                '{llm_task_outcome,structured_output_failures}',
                            ''
                        )::int,
                        0
                    )
                ), 0)::int AS llm_failure_count
              FROM company_enrichment_company_state s
              JOIN batch_rows b ON b.batch_id = s.batch_id
              CROSS JOIN LATERAL jsonb_each(s.stage_status) AS stage(key, value)
             GROUP BY s.batch_id
        ),
        company_diagnostics AS (
            SELECT
                b.batch_id,
                COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'company_id', s.company_id,
                            'status', s.status,
                            'current_stage', s.current_stage,
                            'miss_reason', s.miss_reason,
                            'last_error', s.last_error,
                            'query_count', s.query_count,
                            'source_result_count', s.source_result_count,
                            'accepted_source_count', s.accepted_source_count,
                            'rejected_source_count', s.rejected_source_count,
                            'product_count', s.product_count,
                            'scenario_count', s.scenario_count,
                            'official_product_count', s.official_product_count,
                            'funding_event_count', s.event_count,
                            'vector_refreshed', s.milvus_refreshed_at IS NOT NULL,
                            'stage_status', s.stage_status,
                            'updated_at', s.updated_at
                        )
                        ORDER BY
                            CASE s.status
                                WHEN 'failed' THEN 0
                                WHEN 'partial' THEN 1
                                WHEN 'running' THEN 2
                                ELSE 3
                            END,
                            s.updated_at DESC NULLS LAST,
                            s.company_id ASC
                    ) FILTER (WHERE s.company_id IS NOT NULL),
                    '[]'::jsonb
                ) AS payload,
                (COALESCE(max(s.total_count), 0) > 50) AS truncated
              FROM batch_rows b
              LEFT JOIN LATERAL (
                SELECT s.*, count(*) OVER ()::int AS total_count
                  FROM company_enrichment_company_state s
                 WHERE s.batch_id = b.batch_id
                 ORDER BY
                    CASE s.status
                        WHEN 'failed' THEN 0
                        WHEN 'partial' THEN 1
                        WHEN 'running' THEN 2
                        ELSE 3
                    END,
                    s.updated_at DESC NULLS LAST,
                    s.company_id ASC
                 LIMIT 50
              ) s ON TRUE
             GROUP BY b.batch_id
        )
        SELECT
            b.batch_id,
            b.status,
            b.current_stage,
            b.companies_total,
            b.companies_selected,
            b.companies_processed,
            b.companies_succeeded,
            b.companies_failed,
            COALESCE(sr.query_count, 0) AS query_count,
            COALESCE(sr.source_result_count, 0) AS source_result_count,
            COALESCE(sr.accepted_source_count, 0) AS accepted_source_count,
            COALESCE(sr.rejected_source_count, 0) AS rejected_source_count,
            COALESCE(sr.product_count, 0) AS product_count,
            COALESCE(sr.scenario_count, 0) AS scenario_count,
            COALESCE(sr.official_product_count, 0) AS official_product_count,
            COALESCE(sr.funding_event_count, 0) AS funding_event_count,
            COALESCE(sr.vector_refreshed_count, 0) AS vector_refreshed_count,
            COALESCE(lr.llm_failure_count, 0) AS llm_failure_count,
            COALESCE(sc.payload, '{}'::jsonb) AS status_counts,
            COALESCE(csc.payload, '{}'::jsonb) AS current_stage_counts,
            COALESCE(mr.payload, '{}'::jsonb) AS miss_reasons,
            COALESCE(ofr.payload, '{}'::jsonb) AS official_failure_reasons,
            COALESCE(rcr.payload, '{}'::jsonb) AS rejected_candidate_reasons,
            COALESCE(src.payload, '{}'::jsonb) AS source_counts_by_adapter,
            COALESCE(cd.payload, '[]'::jsonb) AS company_diagnostics,
            COALESCE(cd.truncated, false) AS company_diagnostics_truncated,
            b.last_error,
            b.created_at,
            b.started_at,
            b.finished_at,
            b.updated_at,
            b.runner_pid,
            b.runner_log_path,
            b.runner_heartbeat_at,
            b.runner_last_seen_at,
            b.last_completed_company_id,
            COALESCE(b.miss_reason_buckets, '{}'::jsonb) AS miss_reason_buckets,
            COALESCE(b.quality_report, '{}'::jsonb) AS quality_report
          FROM batch_rows b
          LEFT JOIN state_rollup sr ON sr.batch_id = b.batch_id
          LEFT JOIN llm_rollup lr ON lr.batch_id = b.batch_id
          LEFT JOIN status_counts sc ON sc.batch_id = b.batch_id
          LEFT JOIN current_stage_counts csc ON csc.batch_id = b.batch_id
          LEFT JOIN miss_reasons mr ON mr.batch_id = b.batch_id
          LEFT JOIN official_failure_reasons ofr ON ofr.batch_id = b.batch_id
          LEFT JOIN rejected_candidate_reasons rcr ON rcr.batch_id = b.batch_id
          LEFT JOIN source_counts src ON src.batch_id = b.batch_id
          LEFT JOIN company_diagnostics cd ON cd.batch_id = b.batch_id
         ORDER BY b.created_at DESC, b.batch_id ASC
        """,
        {"run_id": run_id},
    ).fetchall()
    item = _pipeline_run_item(row)
    return PipelineRunDetail(
        **item.model_dump(),
        source_pages=[
            PipelineRunSourcePage(
                page_id=str(_row_value(page, "page_id", 0)),
                url=str(_row_value(page, "url", 1)),
                title=_row_value(page, "title", 2),
                clean_text_path=_row_value(page, "clean_text_path", 3),
                fetched_at=_row_value(page, "fetched_at", 4),
            )
            for page in source_pages
        ],
        company_enrichment_batches=[
            _company_enrichment_batch_status(batch)
            for batch in company_enrichment_batches
        ],
    )


@router.get(
    "/company-enrichment-batches/{batch_id}",
    response_model=CompanyEnrichmentBatchStatus,
)
def get_company_enrichment_batch(
    batch_id: UUID,
    conn: Any = Depends(get_pg_conn),
) -> CompanyEnrichmentBatchStatus:
    row = _load_company_enrichment_batch_status_row(conn, batch_id=batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Company enrichment batch not found")
    return _company_enrichment_batch_status(row)


@router.post(
    "/company-enrichment-batches/{batch_id}/start",
    response_model=PipelineRunActionResponse,
)
async def start_company_enrichment_batch(
    batch_id: UUID,
    request: CompanyEnrichmentBatchStartRequest,
    conn: Any = Depends(get_pg_conn),
) -> PipelineRunActionResponse:
    row = conn.execute(
        """
        SELECT batch_id, status, upload_task_id, companies_selected
          FROM company_enrichment_batch
         WHERE batch_id = %(batch_id)s
         LIMIT 1
        """,
        {"batch_id": batch_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Company enrichment batch not found")
    status = str(_row_value(row, "status", 1))
    if status == "running":
        raise HTTPException(status_code=400, detail="Company enrichment batch is already running")

    parent_run_id = _row_value(row, "upload_task_id", 2)
    options = request.model_dump()
    task_id = open_pipeline_run(
        conn,
        run_kind="backfill_real",
        run_scope={
            "source": "admin-console",
            "domain": "company",
            "action": "company_enrichment_batch",
            "batch_id": str(batch_id),
            "options": options,
        },
        parent_run_id=parent_run_id,
        triggered_by="admin-console",
    )
    _commit_if_supported(conn)

    task = asyncio.create_task(
        _run_company_enrichment_batch_task(
            task_id=task_id,
            batch_id=batch_id,
            parent_run_id=parent_run_id,
            **options,
        )
    )
    task.add_done_callback(_log_background_task_failure)

    return PipelineRunActionResponse(
        task_id=str(task_id),
        status="scheduled",
        domain="company",
        parent_run_id=str(parent_run_id or ""),
    )


@router.post(
    "/company-enrichment-batches/{batch_id}/restart-stale",
    response_model=PipelineRunActionResponse,
)
async def restart_stale_company_enrichment_batch(
    batch_id: UUID,
    request: CompanyEnrichmentBatchStartRequest,
    conn: Any = Depends(get_pg_conn),
) -> PipelineRunActionResponse:
    row = conn.execute(
        """
        SELECT
            batch_id, status, upload_task_id, companies_selected,
            runner_heartbeat_at
          FROM company_enrichment_batch
         WHERE batch_id = %(batch_id)s
         LIMIT 1
        """,
        {"batch_id": batch_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Company enrichment batch not found")
    status = str(_row_value(row, "status", 1))
    heartbeat_at = _row_value(row, "runner_heartbeat_at", 4)
    if status == "running" and not _is_runner_stale(
        status=status,
        heartbeat_at=heartbeat_at,
    ):
        raise HTTPException(
            status_code=400,
            detail="Company enrichment batch is still receiving heartbeat",
        )
    if status == "running":
        conn.execute(
            """
            UPDATE company_enrichment_batch
               SET status = 'failed',
                   current_stage = 'failed',
                   last_error = COALESCE(last_error, 'stale_runner_restart'),
                   finished_at = COALESCE(finished_at, now()),
                   updated_at = now()
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        )
        conn.execute(
            """
            UPDATE company_enrichment_company_state
               SET status = 'failed',
                   last_error = COALESCE(last_error, 'stale_runner_restart'),
                   finished_at = COALESCE(finished_at, now()),
                   updated_at = now()
             WHERE batch_id = %(batch_id)s
               AND status = 'running'
            """,
            {"batch_id": batch_id},
        )

    parent_run_id = _row_value(row, "upload_task_id", 2)
    options = request.model_dump()
    options["include_failed"] = True
    task_id = open_pipeline_run(
        conn,
        run_kind="backfill_real",
        run_scope={
            "source": "admin-console",
            "domain": "company",
            "action": "company_enrichment_batch_restart_stale",
            "batch_id": str(batch_id),
            "options": options,
        },
        parent_run_id=parent_run_id,
        triggered_by="admin-console",
    )
    _commit_if_supported(conn)

    task = asyncio.create_task(
        _run_company_enrichment_batch_task(
            task_id=task_id,
            batch_id=batch_id,
            parent_run_id=parent_run_id,
            **options,
        )
    )
    task.add_done_callback(_log_background_task_failure)

    return PipelineRunActionResponse(
        task_id=str(task_id),
        status="scheduled",
        domain="company",
        parent_run_id=str(parent_run_id or ""),
    )


@router.post("/runs/{run_id}/milvus-backfill", response_model=PipelineRunActionResponse)
async def trigger_milvus_backfill(
    run_id: UUID,
    dry_run: bool = False,
    conn: Any = Depends(get_pg_conn),
) -> PipelineRunActionResponse:
    row = conn.execute(
        """
        SELECT
            run_id,
            run_kind,
            status,
            run_scope,
            triggered_by,
            started_at,
            finished_at,
            items_processed,
            items_failed,
            error_summary
          FROM pipeline_run
         WHERE run_id = %(run_id)s
         LIMIT 1
        """,
        {"run_id": run_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    parent = _pipeline_run_item(row)
    domain = _milvus_backfill_domain(parent.run_scope)
    task_id = open_pipeline_run(
        conn,
        run_kind="backfill_real",
        run_scope={
            "source": "admin-console",
            "domain": domain,
            "action": "milvus_backfill",
            "dry_run": dry_run,
            "parent_run_kind": parent.run_kind,
            "parent_run_id": parent.run_id,
        },
        parent_run_id=run_id,
        triggered_by="admin-console",
    )
    _commit_if_supported(conn)

    task = asyncio.create_task(
        _run_milvus_backfill_task(task_id=task_id, domain=domain, dry_run=dry_run)
    )
    task.add_done_callback(_log_background_task_failure)

    return PipelineRunActionResponse(
        task_id=str(task_id),
        status="scheduled",
        domain=domain,
        parent_run_id=str(run_id),
    )


@router.post(
    "/runs/{run_id}/retrieval-validation",
    response_model=PipelineRunActionResponse,
)
async def trigger_retrieval_validation(
    run_id: UUID,
    conn: Any = Depends(get_pg_conn),
) -> PipelineRunActionResponse:
    row = conn.execute(
        """
        SELECT
            run_id,
            run_kind,
            status,
            run_scope,
            triggered_by,
            started_at,
            finished_at,
            items_processed,
            items_failed,
            error_summary
          FROM pipeline_run
         WHERE run_id = %(run_id)s
         LIMIT 1
        """,
        {"run_id": run_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    parent = _pipeline_run_item(row)
    if parent.run_kind != "import_xlsx":
        raise HTTPException(
            status_code=400,
            detail="Retrieval validation can only run for import_xlsx runs",
        )
    if parent.status == "running":
        raise HTTPException(
            status_code=400,
            detail="Retrieval validation requires a finished import run",
        )
    domain = _pipeline_run_domain(parent.run_scope)
    if domain == "company":
        raise HTTPException(
            status_code=400,
            detail=(
                "Company XLSX uploads use company enrichment batches for post-import "
                "processing; global retrieval validation is not available for company "
                "upload runs."
            ),
        )
    task_id = open_pipeline_run(
        conn,
        run_kind="answer_readiness_eval",
        run_scope={
            "source": "admin-console",
            "domain": domain,
            "action": "retrieval_validation",
            "parent_run_kind": parent.run_kind,
            "parent_run_id": parent.run_id,
        },
        parent_run_id=run_id,
        triggered_by="admin-console",
    )
    _commit_if_supported(conn)

    task = asyncio.create_task(
        _run_retrieval_validation_task(
            task_id=task_id,
            parent_run_id=run_id,
            domain=domain,
        )
    )
    task.add_done_callback(_log_background_task_failure)

    return PipelineRunActionResponse(
        task_id=str(task_id),
        status="scheduled",
        domain=domain,
        parent_run_id=str(run_id),
    )


def _load_company_enrichment_batch_status_row(
    conn: Any,
    *,
    batch_id: UUID,
) -> Any | None:
    return conn.execute(
        """
        WITH batch_rows AS (
            SELECT
                batch_id, status, current_stage, companies_total,
                companies_selected, companies_processed, companies_succeeded,
                companies_failed, last_error, created_at, started_at,
                finished_at, updated_at, runner_pid, runner_log_path,
                runner_heartbeat_at, runner_last_seen_at,
                last_completed_company_id, miss_reason_buckets, quality_report
              FROM company_enrichment_batch
             WHERE batch_id = %(batch_id)s
        ),
        state_rollup AS (
            SELECT
                s.batch_id,
                COALESCE(sum(s.query_count), 0)::int AS query_count,
                COALESCE(sum(s.source_result_count), 0)::int AS source_result_count,
                COALESCE(sum(s.accepted_source_count), 0)::int AS accepted_source_count,
                COALESCE(sum(s.rejected_source_count), 0)::int AS rejected_source_count,
                COALESCE(sum(s.product_count), 0)::int AS product_count,
                COALESCE(sum(s.scenario_count), 0)::int AS scenario_count,
                COALESCE(sum(s.official_product_count), 0)::int AS official_product_count,
                COALESCE(sum(s.event_count), 0)::int AS funding_event_count,
                count(*) FILTER (WHERE s.milvus_refreshed_at IS NOT NULL)::int
                    AS vector_refreshed_count
              FROM company_enrichment_company_state s
              JOIN batch_rows b ON b.batch_id = s.batch_id
             GROUP BY s.batch_id
        ),
        status_counts AS (
            SELECT batch_id, jsonb_object_agg(status_bucket, status_count) AS payload
              FROM (
                SELECT s.batch_id,
                       COALESCE(NULLIF(BTRIM(s.status), ''), 'unknown')
                           AS status_bucket,
                       count(*)::int AS status_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                 GROUP BY s.batch_id,
                          COALESCE(NULLIF(BTRIM(s.status), ''), 'unknown')
              ) grouped
             GROUP BY batch_id
        ),
        current_stage_counts AS (
            SELECT batch_id, jsonb_object_agg(stage_bucket, stage_count) AS payload
              FROM (
                SELECT s.batch_id,
                       COALESCE(NULLIF(BTRIM(s.current_stage), ''), 'unknown')
                           AS stage_bucket,
                       count(*)::int AS stage_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                 GROUP BY s.batch_id,
                          COALESCE(NULLIF(BTRIM(s.current_stage), ''), 'unknown')
              ) grouped
             GROUP BY batch_id
        ),
        miss_reasons AS (
            SELECT batch_id, jsonb_object_agg(reason, reason_count) AS payload
              FROM (
                SELECT s.batch_id,
                       NULLIF(BTRIM(s.miss_reason), '') AS reason,
                       count(*)::int AS reason_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                 WHERE NULLIF(BTRIM(s.miss_reason), '') IS NOT NULL
                 GROUP BY s.batch_id, NULLIF(BTRIM(s.miss_reason), '')
             ) grouped
             GROUP BY batch_id
        ),
        official_failure_reasons AS (
            SELECT batch_id, jsonb_object_agg(reason, reason_count) AS payload
              FROM (
                SELECT batch_id, reason, count(*)::int AS reason_count
                  FROM (
                    SELECT
                        s.batch_id,
                        COALESCE(
                            NULLIF(
                                BTRIM(
                                    s.stage_status #>> '{official_product_capture,miss_reason}'
                                ),
                                ''
                            ),
                            NULLIF(
                                BTRIM(
                                    s.stage_status #>> '{official_product_capture,last_error}'
                                ),
                                ''
                            ),
                            NULLIF(BTRIM(s.miss_reason), '')
                        ) AS reason
                      FROM company_enrichment_company_state s
                      JOIN batch_rows b ON b.batch_id = s.batch_id
                     WHERE s.stage_status ? 'official_product_capture'
                  ) candidates
                 WHERE reason IS NOT NULL
                 GROUP BY batch_id, reason
              ) grouped
             GROUP BY batch_id
        ),
        rejected_candidate_reasons AS (
            SELECT batch_id, jsonb_object_agg(reason, reason_count) AS payload
              FROM (
                SELECT
                    s.batch_id,
                    reason.key AS reason,
                    sum((reason.value)::int)::int AS reason_count
                  FROM company_enrichment_company_state s
                  JOIN batch_rows b ON b.batch_id = s.batch_id
                  CROSS JOIN LATERAL jsonb_each_text(
                    COALESCE(
                        s.stage_status #>
                            '{source_product_extract,rejected_facts,rejected_candidate_reasons}',
                        '{}'::jsonb
                    )
                  ) AS reason(key, value)
                 GROUP BY s.batch_id, reason.key
              ) grouped
             GROUP BY batch_id
        ),
        source_counts AS (
            SELECT batch_id, jsonb_object_agg(source_adapter, payload) AS payload
              FROM (
                SELECT
                    a.batch_id,
                    COALESCE(NULLIF(BTRIM(a.source_adapter), ''), 'unknown')
                        AS source_adapter,
                    jsonb_build_object(
                        'query_count', count(*)::int,
                        'result_count', COALESCE(sum(a.result_count), 0)::int,
                        'accepted_count', COALESCE(sum(a.accepted_count), 0)::int,
                        'rejected_count', COALESCE(sum(
                            a.rejected_offsite
                            + a.rejected_irrelevant_path
                            + a.rejected_name_mismatch
                        ), 0)::int
                    ) AS payload
                  FROM company_enrichment_search_audit a
                  JOIN batch_rows b ON b.batch_id = a.batch_id
                 GROUP BY
                    a.batch_id,
                    COALESCE(NULLIF(BTRIM(a.source_adapter), ''), 'unknown')
              ) grouped
             GROUP BY batch_id
        ),
        llm_rollup AS (
            SELECT
                s.batch_id,
                COALESCE(sum(
                    COALESCE(
                        NULLIF(
                            stage.value #>>
                                '{llm_task_outcome,structured_output_failures}',
                            ''
                        )::int,
                        0
                    )
                ), 0)::int AS llm_failure_count
              FROM company_enrichment_company_state s
              JOIN batch_rows b ON b.batch_id = s.batch_id
              CROSS JOIN LATERAL jsonb_each(s.stage_status) AS stage(key, value)
             GROUP BY s.batch_id
        ),
        company_diagnostics AS (
            SELECT
                b.batch_id,
                COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'company_id', s.company_id,
                            'status', s.status,
                            'current_stage', s.current_stage,
                            'miss_reason', s.miss_reason,
                            'last_error', s.last_error,
                            'query_count', s.query_count,
                            'source_result_count', s.source_result_count,
                            'accepted_source_count', s.accepted_source_count,
                            'rejected_source_count', s.rejected_source_count,
                            'product_count', s.product_count,
                            'scenario_count', s.scenario_count,
                            'official_product_count', s.official_product_count,
                            'funding_event_count', s.event_count,
                            'vector_refreshed', s.milvus_refreshed_at IS NOT NULL,
                            'stage_status', s.stage_status,
                            'updated_at', s.updated_at
                        )
                        ORDER BY
                            CASE s.status
                                WHEN 'failed' THEN 0
                                WHEN 'partial' THEN 1
                                WHEN 'running' THEN 2
                                ELSE 3
                            END,
                            s.updated_at DESC NULLS LAST,
                            s.company_id ASC
                    ) FILTER (WHERE s.company_id IS NOT NULL),
                    '[]'::jsonb
                ) AS payload,
                (COALESCE(max(s.total_count), 0) > 50) AS truncated
              FROM batch_rows b
              LEFT JOIN LATERAL (
                SELECT s.*, count(*) OVER ()::int AS total_count
                  FROM company_enrichment_company_state s
                 WHERE s.batch_id = b.batch_id
                 ORDER BY
                    CASE s.status
                        WHEN 'failed' THEN 0
                        WHEN 'partial' THEN 1
                        WHEN 'running' THEN 2
                        ELSE 3
                    END,
                    s.updated_at DESC NULLS LAST,
                    s.company_id ASC
                 LIMIT 50
              ) s ON TRUE
             GROUP BY b.batch_id
        )
        SELECT
            b.batch_id, b.status, b.current_stage, b.companies_total,
            b.companies_selected, b.companies_processed, b.companies_succeeded,
            b.companies_failed,
            COALESCE(sr.query_count, 0) AS query_count,
            COALESCE(sr.source_result_count, 0) AS source_result_count,
            COALESCE(sr.accepted_source_count, 0) AS accepted_source_count,
            COALESCE(sr.rejected_source_count, 0) AS rejected_source_count,
            COALESCE(sr.product_count, 0) AS product_count,
            COALESCE(sr.scenario_count, 0) AS scenario_count,
            COALESCE(sr.official_product_count, 0) AS official_product_count,
            COALESCE(sr.funding_event_count, 0) AS funding_event_count,
            COALESCE(sr.vector_refreshed_count, 0) AS vector_refreshed_count,
            COALESCE(lr.llm_failure_count, 0) AS llm_failure_count,
            COALESCE(sc.payload, '{}'::jsonb) AS status_counts,
            COALESCE(csc.payload, '{}'::jsonb) AS current_stage_counts,
            COALESCE(mr.payload, '{}'::jsonb) AS miss_reasons,
            COALESCE(ofr.payload, '{}'::jsonb) AS official_failure_reasons,
            COALESCE(rcr.payload, '{}'::jsonb) AS rejected_candidate_reasons,
            COALESCE(src.payload, '{}'::jsonb) AS source_counts_by_adapter,
            COALESCE(cd.payload, '[]'::jsonb) AS company_diagnostics,
            COALESCE(cd.truncated, false) AS company_diagnostics_truncated,
            b.last_error, b.created_at, b.started_at, b.finished_at, b.updated_at,
            b.runner_pid, b.runner_log_path, b.runner_heartbeat_at,
            b.runner_last_seen_at, b.last_completed_company_id,
            COALESCE(b.miss_reason_buckets, '{}'::jsonb) AS miss_reason_buckets,
            COALESCE(b.quality_report, '{}'::jsonb) AS quality_report
          FROM batch_rows b
          LEFT JOIN state_rollup sr ON sr.batch_id = b.batch_id
          LEFT JOIN llm_rollup lr ON lr.batch_id = b.batch_id
          LEFT JOIN status_counts sc ON sc.batch_id = b.batch_id
          LEFT JOIN current_stage_counts csc ON csc.batch_id = b.batch_id
          LEFT JOIN miss_reasons mr ON mr.batch_id = b.batch_id
          LEFT JOIN official_failure_reasons ofr ON ofr.batch_id = b.batch_id
          LEFT JOIN rejected_candidate_reasons rcr ON rcr.batch_id = b.batch_id
          LEFT JOIN source_counts src ON src.batch_id = b.batch_id
          LEFT JOIN company_diagnostics cd ON cd.batch_id = b.batch_id
         LIMIT 1
        """,
        {"batch_id": batch_id},
    ).fetchone()


def _company_enrichment_batch_status(batch: Any) -> CompanyEnrichmentBatchStatus:
    selected = int(_row_value(batch, "companies_selected", 4) or 0)
    processed = int(_row_value(batch, "companies_processed", 5) or 0)
    progress = round((processed / selected) * 100, 2) if selected else 0.0
    miss_reasons = _int_map(_row_value(batch, "miss_reasons", 20))
    official_failure_reasons = _int_map(
        _row_value(batch, "official_failure_reasons", 21)
    )
    rejected_candidate_reasons = _int_map(
        _row_value(batch, "rejected_candidate_reasons", 22)
    )
    miss_reason_buckets = _int_map(
        _row_value_or(batch, "miss_reason_buckets", 36, {})
    )
    if not miss_reason_buckets:
        miss_reason_buckets = build_miss_reason_buckets(
            miss_reasons=miss_reasons,
            official_failure_reasons=official_failure_reasons,
            rejected_candidate_reasons=rejected_candidate_reasons,
        )
    quality_report = _json_object(_row_value_or(batch, "quality_report", 37, {}))
    if not quality_report:
        quality_report = _company_enrichment_quality_report(
            batch=batch,
            processed=processed,
            selected=selected,
            miss_reason_buckets=miss_reason_buckets,
        )
    runner_heartbeat_at = _row_value_or(batch, "runner_heartbeat_at", 33, None)
    return CompanyEnrichmentBatchStatus(
        batch_id=str(_row_value(batch, "batch_id", 0)),
        status=str(_row_value(batch, "status", 1)),
        current_stage=_row_value(batch, "current_stage", 2),
        progress_percent=progress,
        companies_total=int(_row_value(batch, "companies_total", 3) or 0),
        companies_selected=selected,
        companies_processed=processed,
        companies_succeeded=int(_row_value(batch, "companies_succeeded", 6) or 0),
        companies_failed=int(_row_value(batch, "companies_failed", 7) or 0),
        query_count=int(_row_value(batch, "query_count", 8) or 0),
        source_result_count=int(_row_value(batch, "source_result_count", 9) or 0),
        accepted_source_count=int(_row_value(batch, "accepted_source_count", 10) or 0),
        rejected_source_count=int(_row_value(batch, "rejected_source_count", 11) or 0),
        product_count=int(_row_value(batch, "product_count", 12) or 0),
        scenario_count=int(_row_value(batch, "scenario_count", 13) or 0),
        official_product_count=int(_row_value(batch, "official_product_count", 14) or 0),
        funding_event_count=int(_row_value(batch, "funding_event_count", 15) or 0),
        vector_refreshed_count=int(_row_value(batch, "vector_refreshed_count", 16) or 0),
        llm_failure_count=int(_row_value(batch, "llm_failure_count", 17) or 0),
        status_counts=_int_map(_row_value(batch, "status_counts", 18)),
        current_stage_counts=_int_map(_row_value(batch, "current_stage_counts", 19)),
        miss_reasons=miss_reasons,
        official_failure_reasons=official_failure_reasons,
        rejected_candidate_reasons=rejected_candidate_reasons,
        source_counts_by_adapter=_nested_int_map(
            _row_value(batch, "source_counts_by_adapter", 23)
        ),
        runner_pid=_optional_int(_row_value_or(batch, "runner_pid", 31, None)),
        runner_log_path=_row_value_or(batch, "runner_log_path", 32, None),
        runner_heartbeat_at=runner_heartbeat_at,
        runner_last_seen_at=_row_value_or(batch, "runner_last_seen_at", 34, None),
        runner_is_stale=_is_runner_stale(
            status=str(_row_value(batch, "status", 1)),
            heartbeat_at=runner_heartbeat_at,
        ),
        last_completed_company_id=_row_value_or(
            batch, "last_completed_company_id", 35, None
        ),
        miss_reason_buckets=miss_reason_buckets,
        quality_report=quality_report,
        company_diagnostics=[
            CompanyEnrichmentCompanyDiagnostic.model_validate(diagnostic)
            for diagnostic in _json_list(_row_value(batch, "company_diagnostics", 24))
        ],
        company_diagnostics_truncated=bool(
            _row_value(batch, "company_diagnostics_truncated", 25)
        ),
        last_error=_row_value(batch, "last_error", 26),
        created_at=_row_value(batch, "created_at", 27),
        started_at=_row_value(batch, "started_at", 28),
        finished_at=_row_value(batch, "finished_at", 29),
        updated_at=_row_value(batch, "updated_at", 30),
    )


def _pipeline_run_item(row: Any) -> PipelineRunItem:
    return PipelineRunItem(
        run_id=str(_row_value(row, "run_id", 0)),
        run_kind=str(_row_value(row, "run_kind", 1)),
        status=str(_row_value(row, "status", 2)),
        run_scope=_json_object(_row_value(row, "run_scope", 3)),
        triggered_by=_row_value(row, "triggered_by", 4),
        started_at=_row_value(row, "started_at", 5),
        finished_at=_row_value(row, "finished_at", 6),
        items_processed=_row_value(row, "items_processed", 7),
        items_failed=_row_value(row, "items_failed", 8),
        error_summary=_optional_json_object(_row_value(row, "error_summary", 9)),
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


def _row_value_or(row: Any, key: str, index: int, default: Any) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except IndexError:
        return default


def _company_enrichment_quality_report(
    *,
    batch: Any,
    processed: int,
    selected: int,
    miss_reason_buckets: dict[str, int],
) -> dict[str, Any]:
    diagnostics = _json_list(_row_value(batch, "company_diagnostics", 24))
    failed_samples = [
        {
            "company_id": str(item.get("company_id") or ""),
            "status": str(item.get("status") or ""),
            "reason": item.get("miss_reason") or item.get("last_error"),
        }
        for item in diagnostics
        if isinstance(item, dict)
        and str(item.get("status") or "") in {"failed", "partial"}
    ][:5]
    return {
        "headline": f"{processed}/{selected} companies processed",
        "companies_selected": selected,
        "companies_processed": processed,
        "companies_succeeded": int(_row_value(batch, "companies_succeeded", 6) or 0),
        "companies_failed": int(_row_value(batch, "companies_failed", 7) or 0),
        "product_count": int(_row_value(batch, "product_count", 12) or 0),
        "scenario_count": int(_row_value(batch, "scenario_count", 13) or 0),
        "funding_event_count": int(_row_value(batch, "funding_event_count", 15) or 0),
        "accepted_source_count": int(_row_value(batch, "accepted_source_count", 10) or 0),
        "rejected_source_count": int(_row_value(batch, "rejected_source_count", 11) or 0),
        "miss_reason_buckets": dict(miss_reason_buckets),
        "failed_company_samples": failed_samples,
    }


def _is_runner_stale(*, status: str, heartbeat_at: datetime | None) -> bool:
    if status != "running" or heartbeat_at is None:
        return False
    if heartbeat_at.tzinfo is None:
        normalized = heartbeat_at.replace(tzinfo=timezone.utc)
    else:
        normalized = heartbeat_at.astimezone(timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - normalized).total_seconds()
    return age_seconds > 7200


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_json_object(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        try:
            result[str(key)] = int(raw or 0)
        except (TypeError, ValueError):
            continue
    return result


def _nested_int_map(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, int]] = {}
    for key, raw in value.items():
        if not isinstance(raw, dict):
            continue
        result[str(key)] = _int_map(raw)
    return result


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _milvus_backfill_domain(scope: dict[str, Any]) -> str:
    return _pipeline_run_domain(scope)


def _pipeline_run_domain(scope: dict[str, Any]) -> str:
    domain = scope.get("domain")
    if domain not in {"company", "patent", "paper", "professor"}:
        raise HTTPException(
            status_code=400,
            detail="Pipeline run does not declare a supported domain",
        )
    return str(domain)


async def _run_milvus_backfill_task(
    *, task_id: UUID, domain: str, dry_run: bool = False
) -> None:
    try:
        summary = await asyncio.to_thread(
            _run_milvus_backfill_command,
            domain=domain,
            dry_run=dry_run,
        )
    except Exception as exc:
        logger.exception("Milvus backfill task failed before command execution")
        _close_milvus_backfill_run(
            task_id,
            status="failed",
            items_processed=0,
            items_failed=1,
            result_summary={
                "domain": domain,
                "dry_run": dry_run,
                "milvus_backfill_status": "failed",
                "error": str(exc),
            },
            error_summary={"message": str(exc)},
        )
        return

    returncode = int(summary.get("returncode") or 0)
    status = "succeeded" if returncode == 0 else "failed"
    _close_milvus_backfill_run(
        task_id,
        status=status,
        items_processed=1 if status == "succeeded" else 0,
        items_failed=0 if status == "succeeded" else 1,
        result_summary={
            **summary,
            "domain": domain,
            "dry_run": dry_run,
            "milvus_backfill_status": status,
        },
        error_summary=None
        if status == "succeeded"
        else {"message": str(summary.get("stderr") or "Milvus backfill failed")},
    )


def _run_milvus_backfill_command(*, domain: str, dry_run: bool = False) -> dict[str, Any]:
    agent_dir = _repo_root() / "apps" / "miroflow-agent"
    env = os.environ.copy()
    if not env.get("DATABASE_URL") and env.get("DATABASE_URL_TEST"):
        env["DATABASE_URL"] = env["DATABASE_URL_TEST"]
    milvus_uri = (
        env.get("CHAT_MILVUS_URI")
        or env.get("MILVUS_URI")
        or str(agent_dir / "milvus.db")
    )
    timeout = int(env.get("ADMIN_MILVUS_BACKFILL_TIMEOUT_SECONDS", "1800"))
    command = [
        "uv",
        "run",
        "python",
        "scripts/run_milvus_backfill.py",
        "--domain",
        domain,
        "--milvus-uri",
        milvus_uri,
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(
        command,
        cwd=agent_dir,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-4000:],
    }


async def _run_retrieval_validation_task(
    *,
    task_id: UUID,
    parent_run_id: UUID,
    domain: str,
) -> None:
    try:
        summary = await asyncio.to_thread(
            _run_retrieval_validation_command,
            parent_run_id=parent_run_id,
            domain=domain,
        )
    except Exception as exc:
        logger.exception("Retrieval validation task failed before command execution")
        _close_retrieval_validation_run(
            task_id,
            parent_run_id=parent_run_id,
            status="failed",
            items_processed=0,
            items_failed=1,
            result_summary={
                "domain": domain,
                "action": "retrieval_validation",
                "retrieval_validation_status": "failed",
                "error": str(exc),
            },
            error_summary={"message": str(exc)},
        )
        return

    result = str(summary.get("result") or "UNKNOWN")
    returncode = int(summary.get("returncode") or 0)
    failures = _optional_int(summary.get("failures"))
    status = "succeeded" if returncode == 0 and result == "PASS" else "failed"
    gates = summary.get("gates")
    items_processed = len(gates) if isinstance(gates, list) and gates else 1
    _close_retrieval_validation_run(
        task_id,
        parent_run_id=parent_run_id,
        status=status,
        items_processed=items_processed,
        items_failed=failures if failures is not None else (0 if status == "succeeded" else 1),
        result_summary={
            **summary,
            "domain": domain,
            "action": "retrieval_validation",
            "retrieval_validation_status": status,
        },
        error_summary=None
        if status == "succeeded"
        else {"message": str(summary.get("result") or "Retrieval validation failed")},
    )


def _run_retrieval_validation_command(
    *,
    parent_run_id: UUID,
    domain: str,
) -> dict[str, Any]:
    root = _repo_root()
    script = root / "apps" / "admin-console" / "scripts" / "host_e2e_agentic_rag.sh"
    stamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    log_file = (
        root
        / "docs"
        / "source_backfills"
        / f"host-e2e-agentic-rag-validation-{parent_run_id}-{stamp}.txt"
    )
    env = os.environ.copy()
    for key in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ):
        env.pop(key, None)
    if not env.get("DATABASE_URL") and env.get("DATABASE_URL_TEST"):
        env["DATABASE_URL"] = env["DATABASE_URL_TEST"]
    if not env.get("HOST_E2E_BASE_URL") and env.get(
        "ADMIN_RETRIEVAL_VALIDATION_BASE_URL"
    ):
        env["HOST_E2E_BASE_URL"] = env["ADMIN_RETRIEVAL_VALIDATION_BASE_URL"]
    env["HOST_E2E_LOG_FILE"] = str(log_file)
    timeout = int(env.get("ADMIN_RETRIEVAL_VALIDATION_TIMEOUT_SECONDS", "1800"))

    try:
        result = subprocess.run(
            ["bash", str(script)],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "command": f"bash {script}",
            "returncode": 124,
            "result": "TIMEOUT",
            "failures": 1,
            "domain": domain,
            "parent_run_id": str(parent_run_id),
            "log_file": str(log_file),
            "stdout": stdout[-8000:],
            "stderr": stderr[-4000:],
            "gates": [],
        }

    log_text = log_file.read_text(encoding="utf-8") if log_file.exists() else result.stdout
    parsed = _parse_retrieval_validation_log(log_text)
    return {
        "command": f"bash {script}",
        "returncode": result.returncode,
        "domain": domain,
        "parent_run_id": str(parent_run_id),
        "log_file": str(log_file),
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-4000:],
        **parsed,
    }


async def _run_company_enrichment_batch_task(
    *,
    task_id: UUID,
    batch_id: UUID,
    parent_run_id: UUID | str | None,
    limit: int | None,
    chunk_size: int,
    stage_preset: CompanyEnrichmentStagePreset,
    include_failed: bool,
    skip_milvus: bool,
) -> None:
    try:
        summary = await asyncio.to_thread(
            _run_company_enrichment_batch_command,
            batch_id=batch_id,
            limit=limit,
            chunk_size=chunk_size,
            stage_preset=stage_preset,
            include_failed=include_failed,
            skip_milvus=skip_milvus,
        )
    except Exception as exc:
        logger.exception("Company enrichment batch task failed before command execution")
        _close_company_enrichment_batch_run(
            task_id,
            parent_run_id=parent_run_id,
            status="failed",
            items_processed=0,
            items_failed=1,
            result_summary={
                "domain": "company",
                "action": "company_enrichment_batch",
                "batch_id": str(batch_id),
                "company_enrichment_status": "failed",
                "error": str(exc),
            },
            error_summary={"message": str(exc)},
        )
        return

    report = summary.get("report") if isinstance(summary.get("report"), dict) else {}
    returncode = int(summary.get("returncode") or 0)
    report_status = str(report.get("status") or "")
    status = "succeeded" if returncode == 0 and report_status == "succeeded" else "partial"
    if returncode != 0:
        status = "failed"
    processed = _optional_int(report.get("companies_processed")) or _optional_int(
        report.get("companies_selected")
    ) or 0
    failed = 0 if status == "succeeded" else 1
    _close_company_enrichment_batch_run(
        task_id,
        parent_run_id=parent_run_id,
        status=status,
        items_processed=processed,
        items_failed=failed,
        result_summary={
            **summary,
            "domain": "company",
            "action": "company_enrichment_batch",
            "batch_id": str(batch_id),
            "company_enrichment_status": status,
        },
        error_summary=None
        if status == "succeeded"
        else {"message": str(summary.get("stderr") or "Company enrichment failed")},
    )


def _run_company_enrichment_batch_command(
    *,
    batch_id: UUID,
    limit: int | None,
    chunk_size: int,
    stage_preset: CompanyEnrichmentStagePreset,
    include_failed: bool,
    skip_milvus: bool,
) -> dict[str, Any]:
    agent_dir = _repo_root() / "apps" / "miroflow-agent"
    env = os.environ.copy()
    if not env.get("DATABASE_URL") and env.get("DATABASE_URL_TEST"):
        env["DATABASE_URL"] = env["DATABASE_URL_TEST"]
    timeout = int(env.get("ADMIN_COMPANY_ENRICHMENT_TIMEOUT_SECONDS", "7200"))
    command = [
        "uv",
        "run",
        "python",
        "scripts/run_company_upload_enrichment_batch.py",
        "--batch-id",
        str(batch_id),
        "--chunk-size",
        str(chunk_size),
        *_company_enrichment_stage_args(stage_preset),
    ]
    if limit is not None:
        command.extend(["--limit", str(limit)])
    if include_failed:
        command.append("--include-failed")
    if skip_milvus:
        command.append("--skip-milvus")
    try:
        result = subprocess.run(
            command,
            cwd=agent_dir,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "command": " ".join(command),
            "returncode": 124,
            "report": _parse_json_line(stdout),
            "stdout": stdout[-8000:],
            "stderr": stderr[-4000:],
        }
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "report": _parse_json_line(result.stdout),
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-4000:],
    }


def _company_enrichment_stage_args(
    stage_preset: CompanyEnrichmentStagePreset,
) -> list[str]:
    if stage_preset == "trusted_xlsx":
        return ["--skip-live-web"]
    if stage_preset == "high_trust_sources":
        return ["--skip-generic-serper"]
    return []


def _parse_json_line(stdout: str) -> dict[str, Any]:
    for line in reversed((stdout or "").strip().splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    return {}


def _parse_retrieval_validation_log(log_text: str) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    current_gate: dict[str, Any] | None = None
    result = "UNKNOWN"
    failures: int | None = None

    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            if current_gate is not None:
                gates.append(current_gate)
            current_gate = {"label": line.removeprefix("### ").strip()}
            continue
        if line.startswith("result="):
            result = line.split("=", 1)[1].strip()
            continue
        if line.startswith("failures="):
            failures = _optional_int(line.split("=", 1)[1].strip())
            continue
        if current_gate is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in {
            "http_status",
            "query_type",
            "answer_style",
            "citations_count",
        }:
            continue
        current_gate[key] = (
            _optional_int(value) if key == "citations_count" else value
        )

    if current_gate is not None:
        gates.append(current_gate)

    return {
        "result": result,
        "failures": failures,
        "gates": gates,
    }


def _close_milvus_backfill_run(
    task_id: UUID,
    *,
    status: str,
    items_processed: int,
    items_failed: int,
    result_summary: dict[str, Any],
    error_summary: dict[str, Any] | None = None,
) -> None:
    try:
        from psycopg.types.json import Jsonb
        from src.data_agents.storage.postgres.connection import connect

        with connect(_resolve_admin_dsn()) as conn:
            conn.execute(
                """
                UPDATE pipeline_run
                   SET run_scope = COALESCE(run_scope, '{}'::jsonb) || %s::jsonb
                 WHERE run_id = %s
                """,
                (Jsonb({"result_summary": result_summary}), task_id),
            )
            close_pipeline_run(
                conn,
                task_id,
                status=status,
                items_processed=items_processed,
                items_failed=items_failed,
                error_summary=error_summary,
            )
    except Exception:
        logger.exception("Failed to close Milvus backfill pipeline run %s", task_id)


def _close_retrieval_validation_run(
    task_id: UUID,
    *,
    parent_run_id: UUID,
    status: str,
    items_processed: int,
    items_failed: int,
    result_summary: dict[str, Any],
    error_summary: dict[str, Any] | None = None,
) -> None:
    try:
        from psycopg.types.json import Jsonb
        from src.data_agents.storage.postgres.connection import connect

        parent_report = {
            "run_id": str(task_id),
            "status": status,
            "result": result_summary.get("result"),
            "failures": result_summary.get("failures"),
            "log_file": result_summary.get("log_file"),
            "gates": result_summary.get("gates") or [],
        }
        with connect(_resolve_admin_dsn()) as conn:
            conn.execute(
                """
                UPDATE pipeline_run
                   SET run_scope = COALESCE(run_scope, '{}'::jsonb) || %s::jsonb
                 WHERE run_id = %s
                """,
                (Jsonb({"result_summary": result_summary}), task_id),
            )
            conn.execute(
                """
                UPDATE pipeline_run
                   SET run_scope = COALESCE(run_scope, '{}'::jsonb)
                       || jsonb_build_object(
                            'result_summary',
                            COALESCE(run_scope->'result_summary', '{}'::jsonb)
                            || jsonb_build_object(
                                 'retrieval_validation_report',
                                 %s::jsonb
                               )
                          )
                 WHERE run_id = %s
                """,
                (Jsonb(parent_report), parent_run_id),
            )
            close_pipeline_run(
                conn,
                task_id,
                status=status,
                items_processed=items_processed,
                items_failed=items_failed,
                error_summary=error_summary,
            )
    except Exception:
        logger.exception("Failed to close retrieval validation pipeline run %s", task_id)


def _close_company_enrichment_batch_run(
    task_id: UUID,
    *,
    parent_run_id: UUID | str | None,
    status: str,
    items_processed: int,
    items_failed: int,
    result_summary: dict[str, Any],
    error_summary: dict[str, Any] | None = None,
) -> None:
    try:
        from psycopg.types.json import Jsonb
        from src.data_agents.storage.postgres.connection import connect

        with connect(_resolve_admin_dsn()) as conn:
            conn.execute(
                """
                UPDATE pipeline_run
                   SET run_scope = COALESCE(run_scope, '{}'::jsonb) || %s::jsonb
                 WHERE run_id = %s
                """,
                (Jsonb({"result_summary": result_summary}), task_id),
            )
            if parent_run_id:
                conn.execute(
                    """
                    UPDATE pipeline_run
                       SET run_scope = COALESCE(run_scope, '{}'::jsonb)
                           || jsonb_build_object(
                                'result_summary',
                                COALESCE(run_scope->'result_summary', '{}'::jsonb)
                                || jsonb_build_object(
                                     'company_enrichment_batch_report',
                                     %s::jsonb
                                   )
                              )
                     WHERE run_id = %s
                    """,
                    (
                        Jsonb(
                            {
                                "run_id": str(task_id),
                                "status": status,
                                "batch_id": result_summary.get("batch_id"),
                                "report": result_summary.get("report") or {},
                            }
                        ),
                        parent_run_id,
                    ),
                )
            close_pipeline_run(
                conn,
                task_id,
                status=status,
                items_processed=items_processed,
                items_failed=items_failed,
                error_summary=error_summary,
            )
    except Exception:
        logger.exception("Failed to close company enrichment pipeline run %s", task_id)


def _resolve_admin_dsn() -> str:
    from src.data_agents.storage.postgres.connection import resolve_dsn

    raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    return resolve_dsn(raw)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _commit_if_supported(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _log_background_task_failure(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Unhandled pipeline action background task failure")
