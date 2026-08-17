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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.patent.homepage_ingest import run_homepage_patent_ingest  # noqa: E402


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run homepage patent ingest.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--institution")
    parser.add_argument("--prof-id")
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
        sys.stderr.write("DATABASE_URL is required for homepage patent ingest.\n")
        raise SystemExit(1)

    conn = None
    try:
        conn = _open_database_connection(dsn)
        report = run_homepage_patent_ingest(
            conn,
            dry_run=args.dry_run,
            limit=args.limit,
            institution=args.institution,
            prof_id=args.prof_id,
        )
        if not args.dry_run:
            conn.commit()
        payload = asdict(report)
        payload["run_id"] = str(report.run_id)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logging.exception("Homepage patent ingest failed")
        return 1
    finally:
        if conn is not None:
            close = getattr(conn, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
