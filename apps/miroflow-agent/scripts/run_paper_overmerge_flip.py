"""Flip confirmed paper over-merges so the journal version is canonical."""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_APP_ROOT / ".env")
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.paper.dedup_merge import flip_paper_canonical  # noqa: E402
from src.data_agents.paper.milvus_backfill import backfill_paper_chunks  # noqa: E402
from src.data_agents.professor.vectorizer import EmbeddingClient  # noqa: E402
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

_RUN_KIND = "backfill_real"
_TRIGGERED_BY = "paper_overmerge_flip"
_REAL_DB_NAME = "miroflow_real"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flip selected paper over-merge groups to journal canonical.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="mode",
        action="store_const",
        const="dry-run",
        default="dry-run",
        help="Preview flip plans without writes (default).",
    )
    mode.add_argument(
        "--apply",
        dest="mode",
        action="store_const",
        const="apply",
        help="Apply flips and refresh paper Milvus chunks.",
    )
    parser.add_argument("--confirm-real-db", action="store_true")
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Conference canonical paper_id to demote. Repeatable.",
    )
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--milvus-uri", default="./milvus.db")
    args = parser.parse_args(argv)
    args.dry_run = args.mode == "dry-run"
    return args


def _open_database_connection(url: str | None):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_milvus_client(uri: str):
    _prepare_milvus_client_env(uri)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

    return MilvusClient(uri=uri)


def _prepare_milvus_client_env(uri: str) -> None:
    if uri.strip() == ":memory:":
        return
    os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")


def _open_embedding_client() -> EmbeddingClient:
    return EmbeddingClient(api_key=load_local_api_key())


def _resolve_group(conn: Any, old_canonical: str) -> str | None:
    row = conn.execute(
        """
        SELECT old_paper_id
          FROM paper_merge_alias
         WHERE canonical_paper_id = %s
           AND merge_reason = 'exact_title_dedup'
         ORDER BY updated_at DESC NULLS LAST, old_paper_id
         LIMIT 1
        """,
        (old_canonical,),
    ).fetchone()
    if row is None:
        return None
    return str(row["old_paper_id"] if isinstance(row, dict) else row[0])


def _fetch_link_rows(
    conn: Any,
    *,
    old_canonical: str,
    new_canonical: str,
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT professor_id,
                   paper_id,
                   link_status,
                   match_reason
              FROM professor_paper_link
             WHERE paper_id = ANY(%s)
             ORDER BY professor_id, paper_id
            """,
            ([old_canonical, new_canonical],),
        ).fetchall()
    ]


def _build_link_disposition(
    *,
    old_canonical: str,
    new_canonical: str,
    link_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    dispositions: list[dict[str, Any]] = []
    false_action_count = 0
    for row in link_rows:
        paper_id = _required_str(row.get("paper_id"), "paper_id")
        current_status = _required_str(row.get("link_status"), "link_status")
        if paper_id == new_canonical:
            next_status = "verified"
            expected_current = "rejected"
        elif paper_id == old_canonical:
            next_status = "rejected"
            expected_current = "non-rejected"
        else:
            continue
        if (
            paper_id == new_canonical
            and current_status != "rejected"
            or paper_id == old_canonical
            and current_status == "rejected"
        ):
            false_action_count += 1
        dispositions.append(
            {
                "professor_id": _required_str(row.get("professor_id"), "professor_id"),
                "paper_id": paper_id,
                "current_link_status": current_status,
                "new_link_status": next_status,
                "expected_current": expected_current,
                "match_reason": row.get("match_reason"),
            }
        )
    return dispositions, false_action_count


def _process_groups(
    conn: Any,
    *,
    groups: list[str],
    dry_run: bool,
    run_id: UUID | str,
    milvus_client: Any | None = None,
    embedding_client: Any | None = None,
) -> dict[str, Any]:
    report = _empty_report(
        run_id=run_id,
        mode="dry-run" if dry_run else "apply",
        groups_total=len(groups),
    )
    for old_canonical in groups:
        new_canonical = _resolve_group(conn, old_canonical)
        if new_canonical is None:
            report["groups"].append(
                {
                    "old_canonical": old_canonical,
                    "new_canonical": None,
                    "status": "skipped",
                    "reason": "exact_title_dedup_alias_not_found",
                }
            )
            continue

        link_rows = _fetch_link_rows(
            conn,
            old_canonical=old_canonical,
            new_canonical=new_canonical,
        )
        link_disposition, false_action_count = _build_link_disposition(
            old_canonical=old_canonical,
            new_canonical=new_canonical,
            link_rows=link_rows,
        )
        group_report = {
            "old_canonical": old_canonical,
            "new_canonical": new_canonical,
            "status": "planned" if dry_run else "applied",
            "plan": _flip_plan(
                old_canonical=old_canonical,
                new_canonical=new_canonical,
            ),
            "link_disposition": link_disposition,
            "false_action_count": false_action_count,
        }
        report["groups"].append(group_report)
        report["groups_processed"] += 1
        report["false_action_count"] += false_action_count

        if dry_run:
            continue

        counts = flip_paper_canonical(
            conn,
            old_canonical=old_canonical,
            new_canonical=new_canonical,
            run_id=run_id,
        )
        for key in (
            "aliases_deleted",
            "aliases_written",
            "papers_promoted",
            "papers_demoted",
            "links_restored",
            "links_rejected",
        ):
            report[key] += counts[key]
        conn.commit()
        if milvus_client is None or embedding_client is None:
            raise ValueError(
                "milvus_client and embedding_client are required for apply"
            )
        milvus_report = backfill_paper_chunks(
            conn,
            milvus_client,
            embedding_client,
            paper_ids={old_canonical, new_canonical},
        )
        group_report["milvus_report"] = _jsonable_report(milvus_report)
        report["milvus_refreshed"] += 1
    return report


def _flip_plan(*, old_canonical: str, new_canonical: str) -> list[dict[str, str]]:
    return [
        {
            "step": "reverse_alias",
            "delete_alias": f"{new_canonical}->{old_canonical}",
            "write_alias": f"{old_canonical}->{new_canonical}",
        },
        {
            "step": "paper_status",
            "promote": f"{new_canonical}: confirmed/ready",
            "demote": f"{old_canonical}: merged/rejected",
        },
        {
            "step": "links",
            "restore": f"{new_canonical}: rejected->verified",
            "reject": f"{old_canonical}: non-rejected->rejected",
        },
        {
            "step": "milvus_refresh",
            "paper_ids": f"{old_canonical},{new_canonical}",
        },
    ]


def _empty_report(
    *,
    run_id: UUID | str,
    mode: str,
    groups_total: int,
) -> dict[str, Any]:
    return {
        "groups_total": groups_total,
        "groups_processed": 0,
        "aliases_deleted": 0,
        "aliases_written": 0,
        "papers_promoted": 0,
        "papers_demoted": 0,
        "links_restored": 0,
        "links_rejected": 0,
        "milvus_refreshed": 0,
        "false_action_count": 0,
        "run_id": run_id,
        "mode": mode,
        "groups": [],
    }


def _jsonable_report(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return dict(report)
    return {"value": report}


def _required_str(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _print_report(report: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, default=str))
        return
    print(f"mode: {report['mode']}")
    print(f"run_id: {report['run_id']}")
    print(f"groups_total: {report['groups_total']}")
    print(f"groups_processed: {report['groups_processed']}")
    print(f"aliases_deleted: {report['aliases_deleted']}")
    print(f"aliases_written: {report['aliases_written']}")
    print(f"papers_promoted: {report['papers_promoted']}")
    print(f"papers_demoted: {report['papers_demoted']}")
    print(f"links_restored: {report['links_restored']}")
    print(f"links_rejected: {report['links_rejected']}")
    print(f"milvus_refreshed: {report['milvus_refreshed']}")
    print(f"false_action_count: {report['false_action_count']}")
    for group in report["groups"]:
        print(json.dumps(group, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print("Refusing miroflow_real without --confirm-real-db.", file=sys.stderr)
        return 2

    conn = _open_database_connection(args.database_url)
    run_id: UUID | str | None = None
    try:
        if args.dry_run:
            run_id = f"dry-run-{uuid4()}"
            milvus_client = None
            embedding_client = None
        else:
            run_id = open_pipeline_run(
                conn,
                run_kind=_RUN_KIND,
                run_scope={
                    "task": "paper_overmerge_flip",
                    "groups": args.group,
                    "mode": args.mode,
                },
                triggered_by=_TRIGGERED_BY,
            )
            run_id = require_real_run_id(
                run_id,
                writer_name="run_paper_overmerge_flip",
            )
            conn.commit()
            milvus_client = _open_milvus_client(args.milvus_uri)
            embedding_client = _open_embedding_client()

        report = _process_groups(
            conn,
            groups=args.group,
            dry_run=args.dry_run,
            run_id=run_id,
            milvus_client=milvus_client,
            embedding_client=embedding_client,
        )
        if not args.dry_run:
            close_pipeline_run(
                conn,
                run_id,
                status="partial" if report["false_action_count"] else "succeeded",
                items_processed=report["groups_processed"],
                items_failed=report["false_action_count"],
            )
            conn.commit()
        _print_report(report, json_output=args.json_output)
        return 0
    except Exception as exc:
        if run_id is not None and not args.dry_run:
            conn.rollback()
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            conn.commit()
        raise
    finally:
        close_conn = getattr(conn, "close", None)
        if callable(close_conn):
            close_conn()


if __name__ == "__main__":
    raise SystemExit(main())
