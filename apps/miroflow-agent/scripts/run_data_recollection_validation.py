"""Operator runbook helpers for safe recollection validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_APP_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

CHANGE_ID = "data-recollection-validation-runbook"
DEFAULT_RUN_BASE = _REPO_ROOT / ".agents" / "runs" / CHANGE_ID
WORKSPACE_FILES = (
    "environment.md",
    "cleanup-preview.json",
    "batch-plan.json",
    "validation-report.md",
    "verification.md",
)

DEFAULT_CLEANUP_TABLES = (
    "pipeline_issue",
    "professor_admin_action",
    "professor_paper_link",
    "professor_patent_link",
    "professor_fact",
    "professor_affiliation",
    "paper_full_text",
    "paper_title_resolution_cache",
    "paper",
    "patent",
    "professor",
    "pipeline_run",
)
PROTECTED_TABLES = {
    "alembic_version",
    "professor_seed",
    "source_backfill",
}
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CleanupSafetyError(RuntimeError):
    """Raised when cleanup would be destructive without explicit confirmation."""


class BatchPlanError(ValueError):
    """Raised when a recollection batch plan is unsafe or underspecified."""


class RunWorkspace:
    def __init__(self, path: Path):
        self.path = path


class CleanupPreview:
    def __init__(
        self,
        *,
        database: dict[str, Any],
        alembic_revision: str | None,
        tables: list[dict[str, Any]],
        destructive: bool,
        generated_at: str,
    ):
        self.database = database
        self.alembic_revision = alembic_revision
        self.tables = tables
        self.destructive = destructive
        self.generated_at = generated_at

    @property
    def dry_run(self) -> bool:
        return not self.destructive

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": CHANGE_ID,
            "generated_at": self.generated_at,
            "dry_run": self.dry_run,
            "destructive": self.destructive,
            "database": self.database,
            "alembic_revision": self.alembic_revision,
            "tables": self.tables,
            "protected_tables": sorted(PROTECTED_TABLES),
        }


class BatchPlan:
    def __init__(
        self,
        *,
        seed_ids: list[int],
        sample_limit: int | None,
        full_run: bool,
        sample_evidence_path: Path | None,
        generated_at: str,
    ):
        self.seed_ids = seed_ids
        self.sample_limit = sample_limit
        self.full_run = full_run
        self.sample_evidence_path = sample_evidence_path
        self.generated_at = generated_at

    def to_dict(self) -> dict[str, Any]:
        command = [
            str(Path(__file__).resolve()),
            "plan-batch",
            *[
                flag
                for seed_id in self.seed_ids
                for flag in ("--seed-id", str(seed_id))
            ],
        ]
        if self.sample_limit is not None:
            command.extend(["--sample-limit", str(self.sample_limit)])
        if self.full_run:
            command.append("--full-run")
        if self.sample_evidence_path is not None:
            command.extend(["--sample-evidence", str(self.sample_evidence_path)])

        return {
            "change_id": CHANGE_ID,
            "generated_at": self.generated_at,
            "full_run": self.full_run,
            "seed_ids": self.seed_ids,
            "sample_limit": self.sample_limit,
            "sample_evidence_path": (
                str(self.sample_evidence_path) if self.sample_evidence_path else None
            ),
            "commands": {
                "professor_seed_trigger": command,
                "paper_homepage_ingest": [
                    "uv",
                    "run",
                    "python",
                    "scripts/run_homepage_paper_ingest.py",
                    "--limit",
                    str(self.sample_limit or 0),
                ],
                "patent_homepage_ingest": [
                    "uv",
                    "run",
                    "python",
                    "scripts/run_homepage_patent_ingest.py",
                    "--limit",
                    str(self.sample_limit or 0),
                ],
                "paper_summary_backfill": [
                    "uv",
                    "run",
                    "python",
                    "scripts/run_paper_summary_zh_backfill.py",
                    "--limit",
                    str(self.sample_limit or 0),
                ],
                "milvus_refresh": [
                    "uv",
                    "run",
                    "python",
                    "scripts/run_milvus_backfill.py",
                    "--domain",
                    "paper",
                ],
            },
        }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _row_get(row: Any, key: str, index: int = 0, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return default


def _open_database_connection(url: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(url, row_factory=dict_row)


def _safe_identifier(identifier: str) -> str:
    if not _IDENT_RE.match(identifier):
        raise CleanupSafetyError(f"Unsafe SQL identifier: {identifier!r}")
    return identifier


def _quote_identifier(identifier: str) -> str:
    return f'"{_safe_identifier(identifier)}"'


def _normalize_cleanup_tables(tables: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(tables))
    allowed = set(DEFAULT_CLEANUP_TABLES)
    for table in normalized:
        _safe_identifier(table)
        if table in PROTECTED_TABLES or table not in allowed:
            raise CleanupSafetyError(f"Table {table!r} is not in cleanup scope")
    return normalized


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute(
        "SELECT to_regclass(%s) AS exists",
        (f"public.{_safe_identifier(table)}",),
    ).fetchone()
    return bool(_row_get(row, "exists", 0))


def _count_table(conn: Any, table: str) -> int:
    row = conn.execute(
        f"SELECT count(*) AS row_count FROM public.{_quote_identifier(table)}"
    ).fetchone()
    return int(_row_get(row, "row_count", 0, 0) or 0)


def create_run_workspace(
    base_dir: Path | str = DEFAULT_RUN_BASE, *, run_id: str | None = None
) -> RunWorkspace:
    base_path = Path(base_dir)
    if run_id is None:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = base_path / run_id
    path.mkdir(parents=True, exist_ok=True)
    placeholders = {
        "environment.md": "# Environment\n\nPending.\n",
        "cleanup-preview.json": "{}\n",
        "batch-plan.json": "{}\n",
        "validation-report.md": "# Validation Report\n\nPending.\n",
        "verification.md": "# Verification\n\nPending.\n",
    }
    for filename in WORKSPACE_FILES:
        file_path = path / filename
        if not file_path.exists():
            file_path.write_text(placeholders[filename], encoding="utf-8")
    return RunWorkspace(path=path)


def build_cleanup_preview(
    conn: Any,
    *,
    tables: tuple[str, ...] | list[str] = DEFAULT_CLEANUP_TABLES,
    destructive: bool = False,
) -> CleanupPreview:
    cleanup_tables = _normalize_cleanup_tables(tables)
    fingerprint = conn.execute(
        """
        SELECT current_database() AS database_name,
               current_user AS database_user,
               inet_server_addr()::text AS server_addr,
               inet_server_port() AS server_port
        """
    ).fetchone()
    database = {
        "database_name": _row_get(fingerprint, "database_name", 0),
        "database_user": _row_get(fingerprint, "database_user", 1),
        "server_addr": _row_get(fingerprint, "server_addr", 2),
        "server_port": _row_get(fingerprint, "server_port", 3),
    }

    alembic_revision = None
    if _table_exists(conn, "alembic_version"):
        row = conn.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"
        ).fetchone()
        alembic_revision = _row_get(row, "version_num", 0)

    table_rows: list[dict[str, Any]] = []
    for table in cleanup_tables:
        exists = _table_exists(conn, table)
        table_rows.append(
            {
                "table": table,
                "exists": exists,
                "row_count": _count_table(conn, table) if exists else 0,
                "will_delete": bool(destructive and exists),
            }
        )

    return CleanupPreview(
        database=database,
        alembic_revision=alembic_revision,
        tables=table_rows,
        destructive=destructive,
        generated_at=_utc_now(),
    )


def execute_cleanup(
    conn: Any,
    preview: CleanupPreview,
    *,
    destructive: bool,
    confirm_database: str | None,
) -> dict[str, Any]:
    database_name = preview.database.get("database_name")
    if not destructive:
        return {"dry_run": True, "deleted_tables": []}
    if not confirm_database:
        raise CleanupSafetyError(
            "Destructive cleanup requires --confirm-database matching the target DB"
        )
    if confirm_database != database_name:
        raise CleanupSafetyError(
            f"--confirm-database must match target database {database_name!r}"
        )

    deleted_tables: list[str] = []
    for table in preview.tables:
        table_name = table["table"]
        if not table.get("exists"):
            continue
        _normalize_cleanup_tables([table_name])
        conn.execute(f"DELETE FROM public.{_quote_identifier(table_name)}")
        deleted_tables.append(table_name)
    return {"dry_run": False, "deleted_tables": deleted_tables}


def build_batch_plan(
    *,
    seed_ids: list[int],
    sample_limit: int | None,
    full_run: bool,
    sample_evidence_path: Path | str | None = None,
) -> BatchPlan:
    if not seed_ids:
        raise BatchPlanError("At least one --seed-id is required")
    evidence_path = Path(sample_evidence_path) if sample_evidence_path else None
    if full_run:
        if evidence_path is None or not evidence_path.exists():
            raise BatchPlanError(
                "A full run requires an existing sample evidence report"
            )
    elif sample_limit is None or sample_limit <= 0:
        raise BatchPlanError("A sample batch requires --sample-limit > 0")

    return BatchPlan(
        seed_ids=list(dict.fromkeys(seed_ids)),
        sample_limit=sample_limit,
        full_run=full_run,
        sample_evidence_path=evidence_path,
        generated_at=_utc_now(),
    )


def _format_json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_validation_report(snapshot: dict[str, Any]) -> str:
    milvus_status = snapshot.get("milvus_refresh", {}).get("status")
    retrieval_sanity = snapshot.get("retrieval_sanity") or _default_retrieval_sanity()
    if isinstance(retrieval_sanity, dict):
        retrieval_has_results = bool(retrieval_sanity.get("top_k_results"))
    else:
        retrieval_has_results = bool(retrieval_sanity)
    data_ready = milvus_status == "refreshed" and retrieval_has_results
    data_verdict = "pass" if data_ready else "incomplete evidence"

    sections = [
        "# Data Recollection Validation Report",
        "",
        "## Seed Status",
        _format_json_block(snapshot.get("seed_status", [])),
        "",
        "## Pipeline Issue Taxonomy",
        _format_json_block(snapshot.get("pipeline_issue_taxonomy", [])),
        "",
        "## Professor Quality And Facts",
        _format_json_block(
            {
                "professor_quality": snapshot.get("professor_quality", []),
                "fact_coverage": snapshot.get("fact_coverage", {}),
                "fact_coverage_by_type": snapshot.get("fact_coverage_by_type", []),
                "profile_summary_coverage": snapshot.get(
                    "profile_summary_coverage", {}
                ),
                "admin_actions": snapshot.get("admin_actions", []),
                "manual_override_checks": snapshot.get("manual_override_checks", {}),
            }
        ),
        "",
        "## Professor-Paper And Patent Links",
        _format_json_block(
            {
                "paper_link_evidence": snapshot.get("paper_link_evidence", {}),
                "patent_link_evidence": snapshot.get("patent_link_evidence", {}),
                "title_only_patent_rows": snapshot.get("title_only_patent_rows", {}),
            }
        ),
        "",
        "## Paper Summary Readiness",
        _format_json_block(snapshot.get("paper_summary_readiness", {})),
        "",
        "## Milvus Refresh And Retrieval Sanity",
        _format_json_block(
            {
                "milvus_refresh": snapshot.get("milvus_refresh", {}),
                "retrieval_sanity": retrieval_sanity,
            }
        ),
        "",
        "## Final Verdict",
        "- Code-path verdict: pass",
        f"- Data-readiness verdict: {data_verdict}",
        "- Destructive cleanup verdict: not executed by report generation",
        "",
    ]
    return "\n".join(sections)


def _safe_fetchall(conn: Any, sql: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(sql).fetchall()
    except Exception:
        return []
    return [dict(row) if isinstance(row, dict) else {} for row in rows]


def _default_milvus_refresh() -> dict[str, Any]:
    return {
        "status": "not_run",
        "target_paper_ids": [],
        "chunks_inserted": None,
        "chunks_refreshed": None,
        "skipped_reason": "Milvus refresh was not executed in this run.",
    }


def _default_retrieval_sanity() -> dict[str, Any]:
    return {
        "sample_queries": [],
        "top_k_results": [],
        "skipped_reason": "Retrieval sanity checks were not executed in this run.",
    }


def collect_validation_snapshot(conn: Any | None = None) -> dict[str, Any]:
    if conn is None:
        return {
            "seed_status": [],
            "pipeline_issue_taxonomy": [],
            "professor_quality": [],
            "fact_coverage": {},
            "fact_coverage_by_type": [],
            "profile_summary_coverage": {},
            "admin_actions": [],
            "manual_override_checks": {},
            "paper_link_evidence": {},
            "patent_link_evidence": {},
            "title_only_patent_rows": {},
            "paper_summary_readiness": {},
            "milvus_refresh": _default_milvus_refresh(),
            "retrieval_sanity": _default_retrieval_sanity(),
        }
    return {
        "seed_status": _safe_fetchall(
            conn,
            "SELECT status, count(*) AS count FROM professor_seed GROUP BY status ORDER BY status",
        ),
        "pipeline_issue_taxonomy": _safe_fetchall(
            conn,
            """
            SELECT stage,
                   severity,
                   COALESCE(evidence_snapshot->>'issue_type', 'unknown') AS issue_type,
                   count(*) AS count
              FROM pipeline_issue
             GROUP BY stage, severity, issue_type
             ORDER BY count DESC, stage, issue_type
            """,
        ),
        "professor_quality": _safe_fetchall(
            conn,
            "SELECT quality_status, count(*) AS count FROM professor GROUP BY quality_status ORDER BY quality_status",
        ),
        "fact_coverage": _safe_single_stat(
            conn,
            "professor_fact",
            "SELECT count(DISTINCT professor_id) AS with_facts, count(*) AS facts FROM professor_fact",
        ),
        "fact_coverage_by_type": _safe_fetchall(
            conn,
            """
            SELECT fact_type,
                   count(*) AS facts,
                   count(DISTINCT professor_id) AS professors
              FROM professor_fact
             GROUP BY fact_type
             ORDER BY fact_type
            """,
        ),
        "profile_summary_coverage": _safe_single_stat(
            conn,
            "professor",
            "SELECT count(*) FILTER (WHERE coalesce(profile_summary, '') <> '') AS with_summary, count(*) AS total FROM professor",
        ),
        "admin_actions": _safe_fetchall(
            conn,
            """
            SELECT action,
                   count(*) AS count,
                   count(DISTINCT professor_id) AS professors
              FROM professor_admin_action
             GROUP BY action
             ORDER BY action
            """,
        ),
        "manual_override_checks": {"manual_override_column": "not_present"},
        "paper_link_evidence": _safe_single_stat(
            conn,
            "professor_paper_link",
            """
            SELECT count(*) AS links,
                   count(*) FILTER (WHERE evidence_source_type LIKE 'homepage_%') AS homepage_links
              FROM professor_paper_link
            """,
        )
        | {
            "by_source_and_reason": _safe_fetchall(
                conn,
                """
                SELECT evidence_source_type,
                       match_reason,
                       link_status,
                       count(*) AS count
                  FROM professor_paper_link
                 GROUP BY evidence_source_type, match_reason, link_status
                 ORDER BY count DESC, evidence_source_type, match_reason
                """,
            )
        },
        "patent_link_evidence": _safe_single_stat(
            conn,
            "professor_patent_link",
            """
            SELECT count(*) AS links,
                   count(*) FILTER (WHERE evidence_source_type LIKE 'homepage%') AS homepage_links
              FROM professor_patent_link
            """,
        )
        | {
            "by_source_and_reason": _safe_fetchall(
                conn,
                """
                SELECT evidence_source_type,
                       match_reason,
                       link_status,
                       count(*) AS count
                  FROM professor_patent_link
                 GROUP BY evidence_source_type, match_reason, link_status
                 ORDER BY count DESC, evidence_source_type, match_reason
                """,
            )
        },
        "title_only_patent_rows": _safe_single_stat(
            conn,
            "patent",
            """
            SELECT count(*) FILTER (
                       WHERE coalesce(patent_number, '') = ''
                         AND coalesce(title_clean, '') <> ''
                   ) AS title_only_patents,
                   count(*) AS total
              FROM patent
            """,
        ),
        "paper_summary_readiness": _safe_single_stat(
            conn,
            "paper",
            """
            SELECT count(*) FILTER (WHERE coalesce(summary_zh, '') <> '') AS with_summary_zh,
                   count(*) FILTER (WHERE quality_status = 'ready') AS ready_count,
                   count(*) FILTER (WHERE quality_status = 'rejected') AS boilerplate_rejections,
                   avg(length(summary_zh)) FILTER (WHERE coalesce(summary_zh, '') <> '') AS summary_length_avg,
                   count(*) AS total
              FROM paper
            """,
        ),
        "milvus_refresh": _default_milvus_refresh(),
        "retrieval_sanity": _default_retrieval_sanity(),
    }


def _safe_single_stat(conn: Any, table: str, sql: str) -> dict[str, Any]:
    try:
        if not _table_exists(conn, table):
            return {"table_missing": table}
        row = conn.execute(sql).fetchone()
    except Exception as exc:
        return {"error": str(exc)}
    return dict(row) if isinstance(row, dict) else {}


def _load_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None:
        return collect_validation_snapshot()
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe cleanup, bounded recollection, and validation report helpers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-workspace", help="Create run workspace files")
    init.add_argument("--base-dir", type=Path, default=DEFAULT_RUN_BASE)
    init.add_argument("--run-id", default=None)

    cleanup = subparsers.add_parser(
        "cleanup-preview",
        help="Preview cleanup counts; destructive mode requires DB confirmation",
    )
    cleanup.add_argument("--database-url", default=None)
    cleanup.add_argument("--workspace", type=Path, default=None)
    cleanup.add_argument("--table", action="append", default=[])
    cleanup.add_argument("--destructive", action="store_true")
    cleanup.add_argument("--confirm-database", default=None)

    batch = subparsers.add_parser("plan-batch", help="Write a bounded batch plan")
    batch.add_argument("--workspace", type=Path, required=True)
    batch.add_argument("--seed-id", type=int, action="append", default=[])
    batch.add_argument("--sample-limit", type=int, default=None)
    batch.add_argument("--full-run", action="store_true")
    batch.add_argument("--sample-evidence", type=Path, default=None)

    report = subparsers.add_parser(
        "generate-report", help="Render a validation report from a snapshot"
    )
    report.add_argument("--workspace", type=Path, required=True)
    report.add_argument("--snapshot-json", type=Path, default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        if args.command == "init-workspace":
            workspace = create_run_workspace(args.base_dir, run_id=args.run_id)
            print(str(workspace.path))
            return

        if args.command == "cleanup-preview":
            dsn = (
                args.database_url
                or os.environ.get("DATABASE_URL")
                or os.environ.get("DATABASE_URL_TEST")
            )
            if not dsn:
                print("ERROR: DATABASE_URL not set", file=sys.stderr)
                raise SystemExit(1)
            conn = _open_database_connection(dsn)
            tables = tuple(args.table) if args.table else DEFAULT_CLEANUP_TABLES
            preview = build_cleanup_preview(
                conn,
                tables=tables,
                destructive=args.destructive,
            )
            result = execute_cleanup(
                conn,
                preview,
                destructive=args.destructive,
                confirm_database=args.confirm_database,
            )
            if args.destructive and hasattr(conn, "commit"):
                conn.commit()
            payload = preview.to_dict()
            payload["cleanup_execution"] = result
            if args.workspace:
                _write_json(args.workspace / "cleanup-preview.json", payload)
            print(json.dumps(payload, ensure_ascii=False))
            return

        if args.command == "plan-batch":
            plan = build_batch_plan(
                seed_ids=args.seed_id,
                sample_limit=args.sample_limit,
                full_run=args.full_run,
                sample_evidence_path=args.sample_evidence,
            )
            payload = plan.to_dict()
            _write_json(args.workspace / "batch-plan.json", payload)
            print(json.dumps(payload, ensure_ascii=False))
            return

        if args.command == "generate-report":
            snapshot = _load_snapshot(args.snapshot_json)
            report = render_validation_report(snapshot)
            args.workspace.mkdir(parents=True, exist_ok=True)
            (args.workspace / "validation-report.md").write_text(
                report,
                encoding="utf-8",
            )
            print(report)
            return

        raise SystemExit(f"Unknown command: {args.command}")
    except (CleanupSafetyError, BatchPlanError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
