#!/usr/bin/env python3
"""Run one admitted admin XLSX upload through the legacy import chain.

Spawned by the shared job gate as the declared task ``upload-<domain>-import``; it is the only place
that turns an admitted upload into domain rows. Everything it calls already existed — this script adds
the process boundary the gate needs and the ledger bookkeeping around it, nothing else.

It prints exactly one ``{"job_summary": …}`` line for the gate to record, then closes the ledger row.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID

ADMIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ADMIN_ROOT.parents[1]
sys.path.insert(0, str(ADMIN_ROOT))

from src.data_agents.canonical_v2.uploads import (  # noqa: E402
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    UPLOAD_DOMAINS,
    UploadStore,
    upload_root,
    uploads_database_path,
)
from src.data_agents.storage.postgres.pipeline_run import open_pipeline_run  # noqa: E402


def _ledger_store(environ: dict[str, str]) -> UploadStore:
    return UploadStore(uploads_database_path(environ))


def _validated_staged_path(record_path: str, environ: dict[str, str]) -> Path:
    root = upload_root(environ, repo_root=REPO_ROOT).resolve()
    resolved = Path(record_path).resolve()
    if root != resolved and root not in resolved.parents:
        raise SystemExit(f"staged path is outside the upload root: {resolved}")
    if not resolved.is_file():
        raise SystemExit(f"staged file is gone: {resolved}")
    return resolved


def _import_commit(*, task_id: UUID, domain: str, upload_path: Path) -> dict[str, object]:
    from backend.api.upload import (
        _dispatch_upload_pipeline,
        _insert_upload_source_page,
        _resolve_upload_dsn,
        _update_upload_run_path,
    )
    from src.data_agents.storage.postgres.connection import connect

    dsn = _resolve_upload_dsn()
    digest = _sha256(upload_path)
    with connect(dsn) as conn:
        run_id = open_pipeline_run(
            conn,
            run_kind="import_xlsx",
            run_scope={
                "source": "admin-console-upload",
                "domain": domain,
                "filename": upload_path.name,
                "file_content_hash": digest,
                "surface": "canonical-v2-admin-uploads",
            },
            triggered_by="admin-console",
        )
        _update_upload_run_path(conn, task_id=run_id, upload_path=upload_path)
        source_page_id = _insert_upload_source_page(
            conn,
            domain=domain,
            filename=upload_path.name,
            digest=digest,
            upload_path=upload_path,
            task_id=run_id,
        )
        conn.commit()
        summary = asyncio.run(
            _dispatch_upload_pipeline(
                task_id=run_id,
                domain=domain,
                source_page_id=source_page_id,
                upload_path=upload_path,
                dry_run=False,
            )
        )
    summary = dict(summary)
    summary["pipeline_run_id"] = str(run_id)
    return summary


def _import_dry_run(*, domain: str, upload_path: Path) -> dict[str, object]:
    from backend.api.upload import _dispatch_upload_pipeline

    summary = asyncio.run(
        _dispatch_upload_pipeline(
            task_id=UUID(int=0),
            domain=domain,
            source_page_id=UUID(int=0),
            upload_path=upload_path,
            dry_run=True,
        )
    )
    out = dict(summary)
    out["dry_run"] = True
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=list(UPLOAD_DOMAINS))
    parser.add_argument("--upload-id", required=True, dest="upload_id")
    args = parser.parse_args(argv)

    environ = dict(os.environ)
    store = _ledger_store(environ)
    record = store.get(args.upload_id)
    if record is None:
        raise SystemExit(f"unknown upload id: {args.upload_id}")
    if record.domain != args.domain:
        raise SystemExit(
            f"upload {args.upload_id} belongs to domain {record.domain}, not {args.domain}"
        )
    upload_path = _validated_staged_path(record.staged_path, environ)

    try:
        if record.dry_run:
            summary = _import_dry_run(domain=args.domain, upload_path=upload_path)
        else:
            summary = _import_commit(
                task_id=UUID(record.upload_id), domain=args.domain, upload_path=upload_path
            )
    except Exception as exc:  # noqa: BLE001 - the ledger must record the failure either way
        store.set_status(
            record.upload_id, status=STATUS_FAILED, summary={"error": f"{type(exc).__name__}: {exc}"}
        )
        raise
    else:
        status = str(summary.get("status") or STATUS_SUCCEEDED)
        summary["upload_status"] = status
        ledger_status = STATUS_SUCCEEDED if status in {"succeeded", "partial"} else STATUS_FAILED
        store.set_status(record.upload_id, status=ledger_status, summary=summary)
    finally:
        store.close()

    print(
        json.dumps(
            {
                "job_summary": {
                    "items_processed": int(summary.get("items_processed") or 0),
                    "items_failed": int(summary.get("items_failed") or 0),
                    "upload_id": record.upload_id,
                    "domain": record.domain,
                    "batch_id": summary.get("batch_id"),
                    "status": status,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0 if ledger_status == STATUS_SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
