from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn
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


class PipelineRunDetail(PipelineRunItem):
    source_pages: list[PipelineRunSourcePage] = Field(default_factory=list)


class PipelineRunActionResponse(BaseModel):
    task_id: str
    status: str
    domain: str
    parent_run_id: str


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


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_json_object(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


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
