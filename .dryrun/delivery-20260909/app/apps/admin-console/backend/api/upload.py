from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from psycopg.types.json import Jsonb

from backend.deps import get_pg_conn
from src.data_agents.company.enrichment_batch import (
    create_enrichment_batch,
    record_batch_runner_started,
)
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
)

router = APIRouter(prefix="/api/upload")
logger = logging.getLogger(__name__)

UploadDomain = Literal["company", "patent", "professor", "paper"]
DEFAULT_ADMIN_UPLOAD_MAX_BYTES = 128 * 1024 * 1024
UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

_COUNT_SQL = {
    "professor": """
        SELECT count(*)::int AS total
        FROM professor
        WHERE identity_status = 'resolved'
    """,
    "company": """
        SELECT count(*)::int AS total
        FROM company
        WHERE identity_status != 'inactive'
    """,
    "paper": """
        SELECT count(*)::int AS total
        FROM paper p
        LEFT JOIN pipeline_run admin_run
               ON admin_run.run_id = p.run_id
              AND admin_run.triggered_by = 'admin-console'
        WHERE COALESCE(admin_run.run_scope->>'action', '') != 'delete'
    """,
    "patent": """
        SELECT count(*)::int AS total
        FROM patent
        WHERE COALESCE(status, '') != 'inactive'
    """,
}


class UploadResponse(BaseModel):
    imported: int
    skipped: int
    total_in_store: int
    task_id: str
    source_page_id: str
    dry_run: bool = False


class ActiveDuplicateUploadResponse(BaseModel):
    is_active_duplicate: bool
    file_content_hash: str
    active_task_id: str | None = None
    active_status: str | None = None
    active_batch_id: str | None = None
    active_batch_status: str | None = None
    filename: str | None = None
    message: str | None = None


@router.post("", response_model=UploadResponse)
async def upload_file(
    file: UploadFile,
    domain: UploadDomain = Query(...),
    dry_run: bool = False,
    conn: Any = Depends(get_pg_conn),
) -> UploadResponse:
    return await _handle_upload(domain=domain, file=file, conn=conn, dry_run=dry_run)


@router.post("/{domain}", response_model=UploadResponse)
async def upload_domain_file(
    domain: UploadDomain,
    file: UploadFile,
    dry_run: bool = False,
    conn: Any = Depends(get_pg_conn),
) -> UploadResponse:
    return await _handle_upload(domain=domain, file=file, conn=conn, dry_run=dry_run)


@router.get("/{domain}/active-duplicate", response_model=ActiveDuplicateUploadResponse)
def get_active_duplicate_upload(
    domain: UploadDomain,
    file_content_hash: str = Query(..., min_length=64, max_length=64),
    conn: Any = Depends(get_pg_conn),
) -> ActiveDuplicateUploadResponse:
    duplicate = _load_active_duplicate_upload(
        conn,
        domain=domain,
        file_content_hash=file_content_hash.lower(),
    )
    if not duplicate:
        return ActiveDuplicateUploadResponse(
            is_active_duplicate=False,
            file_content_hash=file_content_hash.lower(),
        )
    return ActiveDuplicateUploadResponse(
        is_active_duplicate=True,
        file_content_hash=file_content_hash.lower(),
        **duplicate,
    )


async def _handle_upload(
    *,
    domain: UploadDomain,
    file: UploadFile,
    conn: Any,
    dry_run: bool = False,
) -> UploadResponse:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")

    content = _read_upload_content(file)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    digest = hashlib.sha256(content).hexdigest()
    _acquire_upload_hash_lock(conn, domain=domain, file_content_hash=digest)
    duplicate = _load_active_duplicate_upload(
        conn,
        domain=domain,
        file_content_hash=digest,
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_upload_active",
                "file_content_hash": digest,
                **duplicate,
            },
        )

    task_id = open_pipeline_run(
        conn,
        run_kind="import_xlsx",
        run_scope={
            "source": "admin-console-upload",
            "domain": domain,
            "filename": file.filename,
            "file_content_hash": digest,
            **({"dry_run": True} if dry_run else {}),
        },
        triggered_by="admin-console",
    )
    upload_path = _persist_upload_file(
        domain=domain,
        filename=file.filename,
        content=content,
        digest=digest,
        task_id=task_id,
    )
    _update_upload_run_path(conn, task_id=task_id, upload_path=upload_path)
    _write_upload_file_manifest(
        domain=domain,
        filename=file.filename,
        digest=digest,
        upload_path=upload_path,
        task_id=task_id,
        content_size_bytes=len(content),
    )
    source_page_id = _insert_upload_source_page(
        conn,
        domain=domain,
        filename=file.filename,
        digest=digest,
        upload_path=upload_path,
        task_id=task_id,
    )
    _commit_if_supported(conn)

    task = asyncio.create_task(
        _run_upload_pipeline_task(
            task_id=task_id,
            domain=domain,
            source_page_id=source_page_id,
            upload_path=upload_path,
            dry_run=dry_run,
        )
    )
    task.add_done_callback(_log_background_task_failure)

    return UploadResponse(
        imported=0,
        skipped=0,
        total_in_store=_count_domain(conn, domain),
        task_id=str(task_id),
        source_page_id=str(source_page_id),
        dry_run=dry_run,
    )


def _read_upload_content(file: UploadFile) -> bytes:
    max_bytes = _admin_upload_max_bytes()
    content = bytearray()
    while True:
        chunk = file.file.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "upload_too_large",
                    "message": "Uploaded file exceeds the configured size limit.",
                    "filename": file.filename,
                    "max_bytes": max_bytes,
                    "max_mib": round(max_bytes / 1024 / 1024, 2),
                },
            )
    return bytes(content)


def _admin_upload_max_bytes() -> int:
    raw = os.environ.get("MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES", "").strip()
    if not raw:
        return DEFAULT_ADMIN_UPLOAD_MAX_BYTES
    try:
        parsed = int(raw)
    except ValueError:
        logger.warning(
            "Invalid MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES=%r; using default %s",
            raw,
            DEFAULT_ADMIN_UPLOAD_MAX_BYTES,
        )
        return DEFAULT_ADMIN_UPLOAD_MAX_BYTES
    return parsed if parsed > 0 else DEFAULT_ADMIN_UPLOAD_MAX_BYTES


def _persist_upload_file(
    *,
    domain: str,
    filename: str,
    content: bytes,
    digest: str,
    task_id: UUID,
) -> Path:
    upload_dir = _admin_upload_root() / domain / digest[:16] / str(task_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.xlsx"
    upload_path = upload_dir / safe_name
    upload_path.write_bytes(content)
    return upload_path


def _admin_upload_root() -> Path:
    configured = os.environ.get("MIROTHINKER_ADMIN_UPLOAD_DIR", "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / "data" / "admin_uploads"


def _update_upload_run_path(conn: Any, *, task_id: UUID, upload_path: Path) -> None:
    conn.execute(
        """
        UPDATE pipeline_run
           SET run_scope = COALESCE(run_scope, '{}'::jsonb)
               || %(upload_scope)s::jsonb
         WHERE run_id = %(task_id)s
        """,
        {
            "task_id": task_id,
            "upload_scope": Jsonb({"upload_path": str(upload_path)}),
        },
    )


def _write_upload_file_manifest(
    *,
    domain: str,
    filename: str,
    digest: str,
    upload_path: Path,
    task_id: UUID,
    content_size_bytes: int,
) -> None:
    manifest_path = upload_path.with_suffix(upload_path.suffix + ".summary.json")
    manifest_path.write_text(
        json.dumps(
            {
                "source": "admin-console-upload",
                "domain": domain,
                "filename": filename,
                "file_content_hash": digest,
                "task_id": str(task_id),
                "upload_path": str(upload_path),
                "content_size_bytes": int(content_size_bytes),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _acquire_upload_hash_lock(
    conn: Any,
    *,
    domain: str,
    file_content_hash: str,
) -> None:
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%(lock_key)s))",
        {"lock_key": f"admin-upload:{domain}:{file_content_hash.lower()}"},
    )


def _load_active_duplicate_upload(
    conn: Any,
    *,
    domain: str,
    file_content_hash: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            pr.run_id,
            pr.status,
            pr.run_scope->>'filename' AS filename,
            b.batch_id AS active_batch_id,
            b.status AS active_batch_status
          FROM pipeline_run pr
          LEFT JOIN company_enrichment_batch b
                 ON b.upload_task_id = pr.run_id
                AND b.status IN ('queued', 'running')
         WHERE pr.triggered_by = 'admin-console'
           AND pr.run_kind = 'import_xlsx'
           AND pr.run_scope->>'source' = 'admin-console-upload'
           AND pr.run_scope->>'domain' = %(domain)s
           AND lower(pr.run_scope->>'file_content_hash') = %(file_content_hash)s
           AND (
                 pr.status = 'running'
                 OR b.batch_id IS NOT NULL
           )
         ORDER BY pr.started_at DESC NULLS LAST
         LIMIT 1
        """,
        {
            "domain": domain,
            "file_content_hash": file_content_hash.lower(),
        },
    ).fetchone()
    if not row:
        return None
    task_id = _row_value(row, "run_id", 0)
    status = _row_value(row, "status", 1)
    filename = _row_value(row, "filename", 2)
    batch_id = _row_value(row, "active_batch_id", 3)
    batch_status = _row_value(row, "active_batch_status", 4)
    message = (
        "同一个 Excel 文件正在后台处理中，已拒绝重复上传。"
        "请在现有任务完成后再重新上传，或打开现有任务查看进度。"
    )
    return {
        "active_task_id": str(task_id) if task_id else None,
        "active_status": str(status) if status else None,
        "active_batch_id": str(batch_id) if batch_id else None,
        "active_batch_status": str(batch_status) if batch_status else None,
        "filename": str(filename) if filename else None,
        "message": message,
    }


def _insert_upload_source_page(
    conn: Any,
    *,
    domain: str,
    filename: str,
    digest: str,
    upload_path: Path,
    task_id: UUID,
) -> UUID:
    row = conn.execute(
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            http_status,
            content_hash,
            title,
            clean_text_path,
            is_official_source,
            fetch_run_id,
            run_id
        )
        VALUES (
            %(url)s,
            'unknown',
            'global',
            %(domain)s,
            now(),
            200,
            %(digest)s,
            %(filename)s,
            %(upload_path)s,
            false,
            %(task_id)s,
            %(task_id)s
        )
        ON CONFLICT (url) DO UPDATE
           SET fetched_at = EXCLUDED.fetched_at,
               content_hash = EXCLUDED.content_hash,
               title = EXCLUDED.title,
               clean_text_path = EXCLUDED.clean_text_path,
               fetch_run_id = EXCLUDED.fetch_run_id,
               run_id = EXCLUDED.run_id
        RETURNING page_id
        """,
        {
            "url": f"admin-upload://{domain}/{task_id}/{digest}",
            "domain": domain,
            "digest": digest,
            "filename": filename,
            "upload_path": str(upload_path),
            "task_id": task_id,
        },
    ).fetchone()
    if row is None:
        raise RuntimeError("source_page INSERT did not return a row")
    return row["page_id"] if isinstance(row, dict) else row[0]


def _count_domain(conn: Any, domain: str) -> int:
    row = conn.execute(_COUNT_SQL[domain]).fetchone()
    if row is None:
        return 0
    return int(row["total"] if isinstance(row, dict) else row[0])


async def _run_upload_pipeline_task(
    *,
    task_id: UUID,
    domain: str,
    source_page_id: UUID,
    upload_path: Path,
    dry_run: bool = False,
) -> None:
    try:
        summary = await _dispatch_upload_pipeline(
            task_id=task_id,
            domain=domain,
            source_page_id=source_page_id,
            upload_path=upload_path,
            dry_run=dry_run,
        )
    except Exception as exc:
        logger.exception(
            "Admin upload pipeline task failed for %s source_page=%s",
            domain,
            source_page_id,
        )
        _close_background_run(
            task_id,
            status="failed",
            error_summary={"message": str(exc)},
        )
        return

    _close_background_run(
        task_id,
        status=str(summary.get("status") or "succeeded"),
        items_processed=_optional_int(summary.get("items_processed")),
        items_failed=_optional_int(summary.get("items_failed")),
        result_summary=_result_summary_payload(summary),
    )


async def _dispatch_upload_pipeline(
    *,
    task_id: UUID,
    domain: str,
    source_page_id: UUID,
    upload_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        if domain == "company":
            return await asyncio.to_thread(
                _run_company_upload_dry_run,
                upload_path=upload_path,
            )

        if domain == "patent":
            return await asyncio.to_thread(
                _run_patent_upload_dry_run,
                upload_path=upload_path,
            )

        return {
            "status": "succeeded",
            "items_processed": 0,
            "items_failed": 0,
            "dry_run": True,
        }

    if domain == "professor":
        from src.data_agents.professor.pipeline_v3 import (
            PipelineV3Config,
            run_professor_pipeline_v3,
        )

        output_dir = upload_path.parent / f"{upload_path.stem}-pipeline-v3"
        await run_professor_pipeline_v3(
            PipelineV3Config(
                seed_doc=upload_path,
                output_dir=output_dir,
                skip_vectorize=True,
                store_db_path=None,
            )
        )
        return {"status": "succeeded", "items_processed": 1, "items_failed": 0}

    if domain == "company":
        return await asyncio.to_thread(
            _run_company_upload_pipeline,
            task_id=task_id,
            upload_path=upload_path,
        )

    if domain == "patent":
        return await asyncio.to_thread(
            _run_patent_upload_pipeline,
            task_id=task_id,
            upload_path=upload_path,
        )

    logger.info(
        "Recorded admin upload pipeline handoff task_id=%s domain=%s source_page_id=%s upload_path=%s",
        task_id,
        domain,
        source_page_id,
        upload_path,
    )
    return {"status": "succeeded", "items_processed": 1, "items_failed": 0}


def _run_company_upload_dry_run(*, upload_path: Path) -> dict[str, Any]:
    from src.data_agents.company.canonical_import import build_company_import_preflight
    from src.data_agents.company.import_xlsx import import_company_xlsx

    result = import_company_xlsx(upload_path)
    report = result.report
    file_content_hash = hashlib.sha256(upload_path.read_bytes()).hexdigest()
    existing_companies = _load_existing_company_lookup_for_preflight()
    existing_ids = (
        set(existing_companies)
        if existing_companies is not None
        else _load_existing_company_ids_for_preflight()
    )
    canonical_preflight = build_company_import_preflight(
        upload_path,
        existing_company_ids=existing_ids,
        existing_companies=existing_companies,
    )
    parse_issue_count = (
        report.rows_missing_company_name + report.orphan_continuation_rows
    )
    return {
        "status": "partial" if parse_issue_count else "succeeded",
        "items_processed": report.deduped_records,
        "items_failed": parse_issue_count,
        "dry_run": True,
        "domain": "company",
        "imported": 0,
        "rows_read": report.rows_read,
        "records_parsed": report.company_rows_parsed,
        "deduped_records": report.deduped_records,
        "duplicate_groups": report.duplicate_groups,
        "duplicate_records_discarded": report.duplicate_records_discarded,
        "data_quality_issues": _company_dry_run_quality_issues(report),
        "canonical_preflight": canonical_preflight,
        "duplicate_upload_preflight": _load_duplicate_upload_preflight(
            file_content_hash
        ),
        "parse_report": asdict(report),
        **_milvus_backfill_hint("company"),
    }


def _load_duplicate_upload_preflight(file_content_hash: str) -> dict[str, Any]:
    try:
        dsn = _resolve_upload_dsn()
    except Exception as exc:  # noqa: BLE001
        logger.info("Company upload duplicate preflight skipped lookup: %s", exc)
        return {"duplicate_lookup": "not_run", "is_duplicate_upload": False}

    try:
        from src.data_agents.storage.postgres.connection import connect

        with connect(dsn) as conn:
            row = conn.execute(
                """
                SELECT
                    (
                        SELECT count(*)::int
                          FROM import_batch
                         WHERE file_content_hash = %(file_content_hash)s
                    ) AS prior_import_batches,
                    (
                        SELECT count(*)::int
                          FROM pipeline_run
                         WHERE triggered_by = 'admin-console'
                           AND run_scope->>'domain' = 'company'
                           AND run_scope->>'file_content_hash' = %(file_content_hash)s
                    ) AS prior_admin_upload_runs
                """,
                {"file_content_hash": file_content_hash},
            ).fetchone()
        prior_imports = int(_row_value(row, "prior_import_batches", 0) or 0)
        prior_uploads = int(_row_value(row, "prior_admin_upload_runs", 1) or 0)
        return {
            "duplicate_lookup": "available",
            "is_duplicate_upload": prior_imports > 0 or prior_uploads > 1,
            "prior_import_batches": prior_imports,
            "prior_admin_upload_runs": prior_uploads,
            "recommended_action": (
                "Review existing import before applying; use a deliberate re-import path if needed."
                if prior_imports > 0 or prior_uploads > 1
                else None
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Company upload duplicate preflight lookup failed: %s", exc)
        return {"duplicate_lookup": "failed", "is_duplicate_upload": False}


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


def _load_existing_company_ids_for_preflight() -> set[str] | None:
    try:
        dsn = _resolve_upload_dsn()
    except Exception as exc:  # noqa: BLE001
        logger.info("Company upload preflight skipped existing lookup: %s", exc)
        return None

    try:
        from src.data_agents.storage.postgres.connection import connect

        with connect(dsn) as conn:
            rows = conn.execute(
                """
                SELECT company_id
                FROM company
                WHERE identity_status != 'inactive'
                """
            ).fetchall()
        return {
            str(row["company_id"] if isinstance(row, dict) else row[0])
            for row in rows
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Company upload preflight existing lookup failed: %s", exc)
        return None


def _load_existing_company_lookup_for_preflight() -> dict[str, dict[str, Any]] | None:
    try:
        dsn = _resolve_upload_dsn()
    except Exception as exc:  # noqa: BLE001
        logger.info("Company upload preflight skipped existing diff lookup: %s", exc)
        return None

    try:
        from src.data_agents.storage.postgres.connection import connect

        with connect(dsn) as conn:
            rows = conn.execute(
                """
                SELECT company_id, canonical_name, registered_name, website, quality_status
                FROM company
                WHERE identity_status != 'inactive'
                """
            ).fetchall()
        return {
            str(row["company_id"] if isinstance(row, dict) else row[0]): {
                "canonical_name": row["canonical_name"] if isinstance(row, dict) else row[1],
                "registered_name": row["registered_name"] if isinstance(row, dict) else row[2],
                "website": row["website"] if isinstance(row, dict) else row[3],
                "quality_status": row["quality_status"] if isinstance(row, dict) else row[4],
            }
            for row in rows
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Company upload preflight existing diff lookup failed: %s", exc)
        return None


def _run_patent_upload_dry_run(*, upload_path: Path) -> dict[str, Any]:
    from src.data_agents.patent.import_xlsx import import_patent_xlsx

    result = import_patent_xlsx(upload_path)
    report = result.report
    return {
        "status": "partial" if report.skipped_rows else "succeeded",
        "items_processed": report.records_parsed,
        "items_failed": report.skipped_rows,
        "dry_run": True,
        "domain": "patent",
        "imported": 0,
        "rows_read": report.rows_read,
        "records_parsed": report.records_parsed,
        "skipped_rows": report.skipped_rows,
        "skip_reasons": report.skip_reasons,
        "parse_report": asdict(report),
        **_milvus_backfill_hint("patent"),
    }


def _company_dry_run_quality_issues(report: Any) -> list[dict[str, Any]]:
    source_rows = [int(row) for row in getattr(report, "missing_company_name_rows", ())]
    if not source_rows:
        return []
    count = len(source_rows)
    return [
        {
            "issue_type": "missing_company_name",
            "source_rows": source_rows,
            "severity": "medium",
            "description": f"{count} company rows are missing company_name",
            "recommended_action": "Fill company_name in the source Excel rows before import.",
        }
    ]


def _run_company_upload_pipeline(
    *,
    task_id: UUID,
    upload_path: Path,
) -> dict[str, Any]:
    from src.data_agents.company.canonical_import import (
        import_company_xlsx_to_postgres,
    )

    dsn = _resolve_upload_dsn()
    seed_id = f"admin-upload-company-{task_id}"
    _ensure_admin_upload_seed(
        dsn=dsn,
        seed_id=seed_id,
        seed_kind="company_xlsx",
        domain="company",
        upload_path=upload_path,
        task_id=task_id,
    )
    report = import_company_xlsx_to_postgres(
        upload_path,
        dsn=dsn,
        seed_id=seed_id,
        triggered_by="admin-console",
    )
    imported = report.records_new_company + report.records_updated_company
    company_ids = _load_company_ids_for_import_batch(dsn=dsn, batch_id=report.batch_id)
    enrichment = _enqueue_company_upload_enrichment(
        dsn=dsn,
        task_id=task_id,
        import_batch_id=report.batch_id,
        company_ids=company_ids,
    )
    return {
        "status": (
            "partial"
            if report.records_failed or enrichment.get("status") == "partial"
            else "succeeded"
        ),
        "items_processed": report.records_parsed,
        "items_failed": report.records_failed,
        "imported": imported,
        "batch_id": str(report.batch_id),
        "company_ids_for_enrichment": len(company_ids),
        "enrichment": enrichment,
        "team_members_inserted": report.team_members_inserted,
        "funding_events_inserted": report.funding_events_inserted,
        "lineage_rows": report.lineage_rows,
        **_milvus_backfill_hint("company"),
    }


def _open_enrichment_connection(dsn: str):
    from src.data_agents.storage.postgres.connection import connect

    return connect(dsn)


def _enqueue_company_upload_enrichment(
    *,
    dsn: str,
    task_id: UUID,
    import_batch_id: UUID,
    company_ids: list[str],
) -> dict[str, Any]:
    conn_or_context = _open_enrichment_connection(dsn)

    def _create(conn: Any):
        batch = create_enrichment_batch(
            conn,
            upload_task_id=task_id,
            import_batch_id=import_batch_id,
            company_ids=company_ids,
            run_scope={
                "source": "admin-console-upload",
                "domain": "company",
                "import_batch_id": str(import_batch_id),
            },
            triggered_by="admin-console",
        )
        _commit_if_supported(conn)
        return batch

    enter = getattr(conn_or_context, "__enter__", None)
    if callable(enter):
        with conn_or_context as conn:
            batch = _create(conn)
    else:
        conn = conn_or_context
        try:
            batch = _create(conn)
        finally:
            close = getattr(conn, "close", None)
            if callable(close):
                close()
    _schedule_company_enrichment_batch(dsn=dsn, batch_id=batch.batch_id)
    return {
        "status": "queued",
        "batch_id": str(batch.batch_id),
        "companies_total": batch.companies_total,
        "companies_selected": batch.companies_selected,
    }


def _schedule_company_enrichment_batch(*, dsn: str, batch_id: UUID) -> None:
    if os.environ.get("COMPANY_UPLOAD_ENRICHMENT_DISABLE_AUTORUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    command = [
        sys.executable,
        str(_miroflow_agent_root() / "scripts" / "run_company_upload_enrichment_batch.py"),
        "--batch-id",
        str(batch_id),
    ]
    limit = os.environ.get("COMPANY_UPLOAD_ENRICHMENT_LIMIT", "").strip()
    if limit:
        command.extend(["--limit", limit])
    chunk_size = os.environ.get("COMPANY_UPLOAD_ENRICHMENT_CHUNK_SIZE", "").strip()
    if chunk_size:
        command.extend(["--chunk-size", chunk_size])
    if os.environ.get("COMPANY_UPLOAD_ENRICHMENT_SKIP_MILVUS", "").strip() in {
        "1",
        "true",
        "True",
    }:
        command.append("--skip-milvus")
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    log_path = _company_enrichment_log_path(batch_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    try:
        proc = subprocess.Popen(  # noqa: S603 - command is internal Python script with fixed args.
            command,
            cwd=_miroflow_agent_root(),
            env=env,
            text=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception:
        log_handle.close()
        raise
    else:
        try:
            _record_company_enrichment_runner(
                dsn=dsn,
                batch_id=batch_id,
                runner_pid=getattr(proc, "pid", None),
                runner_log_path=log_path,
            )
        finally:
            log_handle.close()


def _company_enrichment_log_path(batch_id: UUID) -> Path:
    configured = os.environ.get("MIROTHINKER_COMPANY_ENRICHMENT_LOG_DIR", "").strip()
    root = Path(configured) if configured else _repo_root() / "data" / "company_enrichment_logs"
    return root / f"{batch_id}.log"


def _record_company_enrichment_runner(
    *,
    dsn: str,
    batch_id: UUID,
    runner_pid: int | None,
    runner_log_path: Path,
) -> None:
    conn_or_context = _open_enrichment_connection(dsn)

    def _record(conn: Any) -> None:
        record_batch_runner_started(
            conn,
            batch_id=batch_id,
            runner_pid=runner_pid,
            runner_log_path=str(runner_log_path),
        )
        _commit_if_supported(conn)

    enter = getattr(conn_or_context, "__enter__", None)
    if callable(enter):
        with conn_or_context as conn:
            _record(conn)
        return
    conn = conn_or_context
    try:
        _record(conn)
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()


def _load_company_ids_for_import_batch(*, dsn: str, batch_id: UUID) -> list[str]:
    from src.data_agents.storage.postgres.connection import connect

    with connect(dsn) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT company_id
            FROM company_snapshot
            WHERE import_batch_id = %s
            ORDER BY company_id
            """,
            (batch_id,),
        ).fetchall()
    return [str(row["company_id"] if isinstance(row, dict) else row[0]) for row in rows]


def _run_company_upload_enrichment(
    *,
    dsn: str,
    task_id: UUID,
    company_ids: list[str],
) -> dict[str, Any]:
    selected_company_ids = _bounded_company_ids_for_upload_enrichment(company_ids)
    if not selected_company_ids:
        return {
            "status": "skipped",
            "reason": "no companies imported",
            "companies_total": len(company_ids),
            "companies_selected": 0,
        }

    sleep_seconds = os.environ.get("COMPANY_UPLOAD_ENRICHMENT_SLEEP_SECONDS", "0.2")
    commands: list[tuple[str, list[str]]] = []
    for connector in ("iyiou", "pitchhub"):
        command = [
            sys.executable,
            str(_miroflow_agent_root() / "scripts" / "run_company_news_ingest.py"),
            "--connector",
            connector,
            "--priority",
            "all",
            "--since",
            "2000-01-01",
            "--sleep-seconds",
            sleep_seconds,
            "--serper-article-max-chars",
            "4000",
            "--llm-search-hints",
        ]
        if connector == "iyiou":
            command.append("--serper-fetch-article-text")
        command.extend(_company_id_args(selected_company_ids))
        commands.append((f"news_{connector}", command))

    source_adapters = [
        "--source-adapter",
        "iyiou",
        "--source-adapter",
        "pitchhub_36kr",
    ]
    commands.append(
        (
            "signal_extract",
            [
                sys.executable,
                str(_miroflow_agent_root() / "scripts" / "run_company_signal_extract.py"),
                "--since",
                "2000-01-01",
                *source_adapters,
                *_company_id_args(selected_company_ids),
            ],
        )
    )
    commands.append(
        (
            "source_product_extract",
            [
                sys.executable,
                str(
                    _miroflow_agent_root()
                    / "scripts"
                    / "run_company_source_product_extract.py"
                ),
                "--limit",
                str(max(1000, len(selected_company_ids) * 20)),
                *source_adapters,
                *_company_id_args(selected_company_ids),
            ],
        )
    )

    command_reports: list[dict[str, Any]] = []
    status = "succeeded"
    for name, command in commands:
        report = _run_company_enrichment_command(
            name=name,
            command=command,
            dsn=dsn,
            task_id=task_id,
        )
        command_reports.append(report)
        if report.get("status") != "succeeded":
            status = "partial"

    return {
        "status": status,
        "companies_total": len(company_ids),
        "companies_selected": len(selected_company_ids),
        "enrichment_limit": _company_upload_enrichment_limit(),
        "commands": command_reports,
        "news_inserted": sum(_int_from_report(r, "news_inserted") for r in command_reports),
        "events_inserted": sum(_int_from_report(r, "events_inserted") for r in command_reports),
        "products_inserted": sum(_int_from_report(r, "products_inserted") for r in command_reports),
        "scenarios_inserted": sum(_int_from_report(r, "scenarios_inserted") for r in command_reports),
    }


def _bounded_company_ids_for_upload_enrichment(company_ids: list[str]) -> list[str]:
    limit = _company_upload_enrichment_limit()
    if limit is None:
        return list(company_ids)
    return list(company_ids[:limit])


def _company_upload_enrichment_limit() -> int | None:
    raw = os.environ.get("COMPANY_UPLOAD_ENRICHMENT_LIMIT", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _company_id_args(company_ids: list[str]) -> list[str]:
    args: list[str] = []
    for company_id in company_ids:
        args.extend(["--company-id", company_id])
    return args


def _run_company_enrichment_command(
    *,
    name: str,
    command: list[str],
    dsn: str,
    task_id: UUID,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    env["COMPANY_UPLOAD_TASK_ID"] = str(task_id)
    try:
        completed = subprocess.run(
            command,
            cwd=_miroflow_agent_root(),
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=float(os.environ.get("COMPANY_UPLOAD_ENRICHMENT_TIMEOUT_SECONDS", "900")),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "status": "failed",
            "error": str(exc),
        }

    payload = _parse_command_json_output(completed.stdout)
    if completed.returncode != 0:
        return {
            "name": name,
            "status": "failed",
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-1000:],
            "stdout_tail": completed.stdout[-1000:],
            "report": payload,
        }
    return {
        "name": name,
        "status": "succeeded",
        "returncode": completed.returncode,
        "report": payload,
    }


def _parse_command_json_output(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    return {}


def _int_from_report(command_report: dict[str, Any], key: str) -> int:
    report = command_report.get("report")
    if not isinstance(report, dict):
        return 0
    try:
        return int(report.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _miroflow_agent_root() -> Path:
    return _repo_root() / "apps" / "miroflow-agent"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _run_patent_upload_pipeline(
    *,
    task_id: UUID,
    upload_path: Path,
) -> dict[str, Any]:
    from src.data_agents.patent.canonical_writer import (
        upsert_company_patent_link,
        upsert_patent,
    )
    from src.data_agents.patent.exact_backfill import build_patent_release_from_sources
    from src.data_agents.patent.import_xlsx import import_patent_xlsx
    from src.data_agents.patent.linkage import link_company_ids
    from src.data_agents.patent.release import publish_patent_release
    from src.data_agents.storage.postgres.connection import connect

    dsn = _resolve_upload_dsn()
    import_report = import_patent_xlsx(upload_path).report
    with connect(dsn) as conn:
        company_name_to_id, company_aliases_map = _load_company_lookup(conn)
        release_result = build_patent_release_from_sources(
            workbook_paths=[upload_path],
            company_name_to_id=company_name_to_id,
            company_aliases_map=company_aliases_map,
            llm_client=None,
        )
        output_dir = upload_path.parent / f"{upload_path.stem}-patent-release"
        publish_patent_release(
            release_result,
            patent_records_path=output_dir / "patent_records.jsonl",
            released_objects_path=output_dir / "released_objects.jsonl",
        )

        patents_written = 0
        link_candidates = 0
        links_written = 0
        link_errors = 0
        for record in release_result.patent_records:
            with conn.transaction():
                upsert_patent(conn, record=record, run_id=task_id)
            patents_written += 1
            for company_id, evidence_source_type, match_reason in link_company_ids(
                record.applicants,
                company_name_to_id,
                company_aliases_map=company_aliases_map,
            ):
                link_candidates += 1
                try:
                    with conn.transaction():
                        upsert_company_patent_link(
                            patent_id=record.id,
                            company_id=company_id,
                            link_role="applicant",
                            evidence_source_type=evidence_source_type,
                            match_reason=match_reason,
                            conn=conn,
                        )
                except Exception:  # noqa: BLE001 - keep patent rows even if one link fails
                    link_errors += 1
                    logger.exception(
                        "Admin patent upload link failed patent=%s company=%s",
                        record.id,
                        company_id,
                    )
                    continue
                links_written += 1

    return {
        "status": (
            "partial" if (import_report.skipped_rows or link_errors) else "succeeded"
        ),
        "items_processed": patents_written,
        "items_failed": import_report.skipped_rows + link_errors,
        "imported": patents_written,
        "rows_read": import_report.rows_read,
        "records_parsed": import_report.records_parsed,
        "skipped_rows": import_report.skipped_rows,
        "skip_reasons": import_report.skip_reasons,
        "released_record_count": release_result.report.released_record_count,
        "company_patent_link_candidates": link_candidates,
        "company_patent_links_written": links_written,
        "company_patent_link_errors": link_errors,
        "artifact_dir": str(output_dir),
        **_milvus_backfill_hint("patent"),
    }


def _resolve_upload_dsn() -> str:
    from src.data_agents.storage.postgres.connection import resolve_dsn

    raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    return resolve_dsn(raw)


def _ensure_admin_upload_seed(
    *,
    dsn: str,
    seed_id: str,
    seed_kind: str,
    domain: str,
    upload_path: Path,
    task_id: UUID,
) -> None:
    from psycopg.types.json import Jsonb
    from src.data_agents.storage.postgres.connection import connect

    with connect(dsn) as conn:
        conn.execute(
            """
            INSERT INTO seed_registry (
                seed_id,
                seed_kind,
                scope_key,
                source_uri,
                priority,
                refresh_policy,
                status,
                config
            )
            VALUES (%s, %s, %s, %s, 100, 'manual', 'active', %s)
            ON CONFLICT (seed_id) DO UPDATE
               SET source_uri = EXCLUDED.source_uri,
                   config = EXCLUDED.config,
                   updated_at = now()
            """,
            (
                seed_id,
                seed_kind,
                f"admin-console:{domain}:{task_id}",
                f"file://{upload_path}",
                Jsonb(
                    {
                        "source": "admin-console-upload",
                        "domain": domain,
                        "task_id": str(task_id),
                    }
                ),
            ),
        )


def _load_company_lookup(conn: Any) -> tuple[dict[str, str], dict[str, str]]:
    rows = conn.execute(
        "SELECT company_id, canonical_name, registered_name, aliases FROM company"
    ).fetchall()
    company_name_to_id: dict[str, str] = {}
    company_aliases_map: dict[str, str] = {}
    for row in rows:
        company_id = row["company_id"] if isinstance(row, dict) else row[0]
        canonical_name = row["canonical_name"] if isinstance(row, dict) else row[1]
        registered_name = row["registered_name"] if isinstance(row, dict) else row[2]
        aliases = row["aliases"] if isinstance(row, dict) else row[3]
        if canonical_name:
            company_name_to_id.setdefault(str(canonical_name), str(company_id))
        if registered_name:
            company_name_to_id.setdefault(str(registered_name), str(company_id))
        for alias in _iter_aliases(aliases):
            company_aliases_map.setdefault(alias, str(company_id))
    return company_name_to_id, company_aliases_map


def _iter_aliases(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _commit_if_supported(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _close_background_run(
    task_id: UUID,
    *,
    status: str,
    items_processed: int | None = None,
    items_failed: int | None = None,
    error_summary: dict[str, Any] | None = None,
    result_summary: dict[str, Any] | None = None,
) -> None:
    try:
        from psycopg.types.json import Jsonb
        from src.data_agents.storage.postgres.connection import connect

        with connect(_resolve_upload_dsn()) as conn:
            if result_summary:
                conn.execute(
                    """
                    UPDATE pipeline_run
                       SET run_scope = COALESCE(run_scope, '{}'::jsonb) || %s::jsonb
                     WHERE run_id = %s
                    """,
                    (Jsonb({"result_summary": result_summary}), task_id),
                )
                try:
                    _file_upload_pipeline_issues(
                        conn,
                        task_id=task_id,
                        domain=str(result_summary.get("domain") or "upload"),
                        result_summary=result_summary,
                    )
                except Exception:
                    logger.exception(
                        "Failed to file admin upload pipeline issues for %s", task_id
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
        logger.exception("Failed to close admin upload pipeline run %s", task_id)


def _file_upload_pipeline_issues(
    conn: Any,
    *,
    task_id: UUID,
    domain: str,
    result_summary: dict[str, Any],
) -> None:
    issues = result_summary.get("data_quality_issues")
    if not isinstance(issues, list) or not issues:
        return

    from psycopg.types.json import Jsonb

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "low")
        if severity not in {"low", "medium", "high"}:
            severity = "low"
        description = str(issue.get("description") or "Admin upload data quality issue")
        evidence = {
            "domain": domain,
            "task_id": str(task_id),
            **issue,
        }
        conn.execute(
            """
            INSERT INTO pipeline_issue (
                institution,
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
                f"admin-upload:{domain}:{task_id}",
                "data_quality_flag",
                severity,
                description,
                Jsonb(evidence),
                "admin_upload_dry_run",
            ),
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    reserved = {"status", "items_processed", "items_failed"}
    return {
        key: value
        for key, value in summary.items()
        if key not in reserved and value is not None
    }


def _milvus_backfill_hint(domain: str) -> dict[str, str | bool]:
    return {
        "milvus_backfill_required": True,
        "milvus_backfill_status": "not_triggered",
        "milvus_backfill_command": (
            "cd apps/miroflow-agent && "
            f"uv run python scripts/run_milvus_backfill.py --domain {domain} "
            "--milvus-uri \"${CHAT_MILVUS_URI:-./milvus.db}\""
        ),
    }


def _log_background_task_failure(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Unhandled admin upload background task failure")
