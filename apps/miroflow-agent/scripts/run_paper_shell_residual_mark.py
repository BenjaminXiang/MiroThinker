# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Emit bounded JSONL for unresolved prof-page-only paper shells.

This is the Stage D marker for ``recover-paper-shells-via-realtime-resolution``.
It is intentionally read-only: residual shells stay not-ready and no
``quality_status``, ``summary_zh``, or ``identity_status`` fields are mutated.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402

_DEFAULT_LIMIT = 1000


@dataclass(frozen=True, slots=True)
class ResidualShellRow:
    paper_id: str
    title_clean: str
    professor_id: str

    def to_json_record(self, *, run_id: str | None) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "title_clean": self.title_clean,
            "professor_id": self.professor_id,
            "run_id": run_id,
        }


@dataclass(frozen=True, slots=True)
class ResidualMarkStats:
    residual_count: int
    output_path: Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write unresolved prof_page_only paper shells with linked professor_id "
            "as bounded JSONL."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL from the environment.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="JSONL output path for residual shell records.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Maximum residual rows to emit. Default: {_DEFAULT_LIMIT}.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional Stage A run_id to carry into each JSONL record.",
    )
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    return args


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def load_residual_shells(conn: Any, *, limit: int) -> list[ResidualShellRow]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if limit == 0:
        return []

    rows = conn.execute(
        """
        SELECT p.paper_id,
               p.title_clean,
               ppl.professor_id
          FROM paper AS p
          JOIN professor_paper_link AS ppl
            ON ppl.paper_id = p.paper_id
         WHERE p.canonical_source = 'prof_page_only'
           AND NULLIF(BTRIM(COALESCE(p.abstract_clean, '')), '') IS NULL
         ORDER BY p.paper_id, ppl.professor_id
         LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_residual_shell_row(row) for row in rows]


def _residual_shell_row(row: Any) -> ResidualShellRow:
    return ResidualShellRow(
        paper_id=str(row["paper_id"]),
        title_clean=str(row.get("title_clean") or ""),
        professor_id=str(row["professor_id"]),
    )


def write_residual_jsonl(
    rows: list[ResidualShellRow],
    *,
    output_path: Path,
    run_id: str | None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_json_record(run_id=run_id), ensure_ascii=False))
            handle.write("\n")


def mark_residual_shells(
    conn: Any,
    *,
    output_path: Path,
    limit: int,
    run_id: str | None,
) -> ResidualMarkStats:
    rows = load_residual_shells(conn, limit=limit)
    write_residual_jsonl(rows, output_path=output_path, run_id=run_id)
    return ResidualMarkStats(residual_count=len(rows), output_path=output_path)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = resolve_dsn(args.database_url)
    conn = _open_database_connection(dsn)
    try:
        stats = mark_residual_shells(
            conn,
            output_path=args.output,
            limit=args.limit,
            run_id=args.run_id,
        )
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()

    print(
        json.dumps(
            {
                "residual_count": stats.residual_count,
                "output_path": str(stats.output_path),
                "read_only": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
