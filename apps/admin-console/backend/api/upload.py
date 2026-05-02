from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.deps import get_pg_conn
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
)

router = APIRouter(prefix="/api/upload")
logger = logging.getLogger(__name__)

UploadDomain = Literal["company", "patent", "professor", "paper"]

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


@router.post("", response_model=UploadResponse)
async def upload_file(
    file: UploadFile,
    domain: UploadDomain = Query(...),
    conn: Any = Depends(get_pg_conn),
) -> UploadResponse:
    return await _handle_upload(domain=domain, file=file, conn=conn)


@router.post("/{domain}", response_model=UploadResponse)
async def upload_domain_file(
    domain: UploadDomain,
    file: UploadFile,
    conn: Any = Depends(get_pg_conn),
) -> UploadResponse:
    return await _handle_upload(domain=domain, file=file, conn=conn)


async def _handle_upload(
    *,
    domain: UploadDomain,
    file: UploadFile,
    conn: Any,
) -> UploadResponse:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    digest = hashlib.sha256(content).hexdigest()
    upload_path = _persist_upload_file(domain=domain, filename=file.filename, content=content, digest=digest)
    task_id = open_pipeline_run(
        conn,
        run_kind="backfill_real",
        run_scope={
            "source": "admin-console-upload",
            "domain": domain,
            "filename": file.filename,
            "file_content_hash": digest,
            "upload_path": str(upload_path),
        },
        triggered_by="admin-console",
    )
    source_page_id = _insert_upload_source_page(
        conn,
        domain=domain,
        filename=file.filename,
        digest=digest,
        upload_path=upload_path,
        task_id=task_id,
    )

    task = asyncio.create_task(
        _run_upload_pipeline_task(
            task_id=task_id,
            domain=domain,
            source_page_id=source_page_id,
            upload_path=upload_path,
        )
    )
    task.add_done_callback(_log_background_task_failure)

    return UploadResponse(
        imported=0,
        skipped=0,
        total_in_store=_count_domain(conn, domain),
        task_id=str(task_id),
        source_page_id=str(source_page_id),
    )


def _persist_upload_file(
    *,
    domain: str,
    filename: str,
    content: bytes,
    digest: str,
) -> Path:
    upload_dir = Path(tempfile.gettempdir()) / "mirothinker-admin-uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.xlsx"
    upload_path = upload_dir / f"{domain}-{digest[:16]}-{safe_name}"
    upload_path.write_bytes(content)
    return upload_path


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
            "url": f"admin-upload://{domain}/{digest}",
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
) -> None:
    try:
        await _dispatch_upload_pipeline(
            task_id=task_id,
            domain=domain,
            source_page_id=source_page_id,
            upload_path=upload_path,
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

    _close_background_run(task_id, status="succeeded")


async def _dispatch_upload_pipeline(
    *,
    task_id: UUID,
    domain: str,
    source_page_id: UUID,
    upload_path: Path,
) -> None:
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
        return

    logger.info(
        "Recorded admin upload pipeline handoff task_id=%s domain=%s source_page_id=%s upload_path=%s",
        task_id,
        domain,
        source_page_id,
        upload_path,
    )


def _close_background_run(
    task_id: UUID,
    *,
    status: str,
    error_summary: dict[str, Any] | None = None,
) -> None:
    try:
        from src.data_agents.storage.postgres.connection import connect

        with connect() as conn:
            close_pipeline_run(
                conn,
                task_id,
                status=status,
                items_processed=1 if status == "succeeded" else 0,
                items_failed=1 if status != "succeeded" else 0,
                error_summary=error_summary,
            )
    except Exception:
        logger.exception("Failed to close admin upload pipeline run %s", task_id)


def _log_background_task_failure(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Unhandled admin upload background task failure")
