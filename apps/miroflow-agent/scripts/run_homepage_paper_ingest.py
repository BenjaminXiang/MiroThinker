#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row

# Ensure imports work when running the script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.homepage_ingest import run_homepage_paper_ingest  # noqa: E402


def _default_resume_checkpoint_path() -> Path:
    return PROJECT_ROOT / "logs" / "data_agents" / "paper" / "homepage_ingest_runs.jsonl"


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run homepage paper ingest.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--institution")
    parser.add_argument("--prof-id")
    parser.add_argument("--resume", nargs="?", const="")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    log_level_name = str(args.log_level).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.stderr.write("DATABASE_URL is required for homepage paper ingest.\n")
        raise SystemExit(1)

    resume_checkpoint_path: Path | None = None
    if args.resume is not None:
        resume_checkpoint_path = (
            Path(args.resume) if args.resume else _default_resume_checkpoint_path()
        )

    conn = None
    try:
        conn = _open_database_connection(dsn)
        report = run_homepage_paper_ingest(
            conn,
            dry_run=args.dry_run,
            limit=args.limit,
            institution=args.institution,
            prof_id=args.prof_id,
            resume_checkpoint_path=resume_checkpoint_path,
        )
        payload = asdict(report)
        payload["run_id"] = str(report.run_id)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception:
        logging.exception("Homepage paper ingest failed")
        return 1
    finally:
        if conn is not None:
            close = getattr(conn, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
