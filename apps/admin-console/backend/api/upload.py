from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from dataclasses import asdict
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
    dry_run: bool = False


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


async def _handle_upload(
    *,
    domain: UploadDomain,
    file: UploadFile,
    conn: Any,
    dry_run: bool = False,
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
        run_kind="import_xlsx",
        run_scope={
            "source": "admin-console-upload",
            "domain": domain,
            "filename": file.filename,
            "file_content_hash": digest,
            "upload_path": str(upload_path),
            **({"dry_run": True} if dry_run else {}),
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
    from src.data_agents.company.import_xlsx import import_company_xlsx

    result = import_company_xlsx(upload_path)
    report = result.report
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
        "parse_report": asdict(report),
        **_milvus_backfill_hint("company"),
    }


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
    return {
        "status": "partial" if report.records_failed else "succeeded",
        "items_processed": report.records_parsed,
        "items_failed": report.records_failed,
        "imported": imported,
        "batch_id": str(report.batch_id),
        "team_members_inserted": report.team_members_inserted,
        "funding_events_inserted": report.funding_events_inserted,
        "lineage_rows": report.lineage_rows,
        **_milvus_backfill_hint("company"),
    }


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
