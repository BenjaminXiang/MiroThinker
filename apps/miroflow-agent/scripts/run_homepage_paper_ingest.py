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
from dotenv import load_dotenv
from psycopg.rows import dict_row

# Ensure imports work when running the script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.homepage_ingest import run_homepage_paper_ingest  # noqa: E402
from src.data_agents.paper.llm_publication_extractor import (  # noqa: E402
    LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES,
    LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS,
    LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS,
    build_llm_publication_extractor,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402

logger = logging.getLogger(__name__)
_LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS = (
    LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS
)
_LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS = (
    LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS
)
_LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES = (
    LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES
)


def _default_resume_checkpoint_path() -> Path:
    return PROJECT_ROOT / "logs" / "data_agents" / "paper" / "homepage_ingest_runs.jsonl"


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _build_llm_publication_extractor(profile_name: str, *, force_llm: bool = False):
    return build_llm_publication_extractor(
        profile_name,
        force_llm=force_llm,
        resolve_settings=resolve_professor_llm_settings,
        timeout_seconds=_LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS,
        retry_backoff_seconds=_LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS,
        max_consecutive_failures=_LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run homepage paper ingest.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--institution")
    parser.add_argument("--department")
    parser.add_argument("--seed-id")
    parser.add_argument("--prof-id")
    parser.add_argument("--resume", nargs="?", const="")
    parser.add_argument(
        "--include-owned-homepage-pages",
        action="store_true",
        default=True,
        help=(
            "Also ingest professor-owned source_page rows with publication, "
            "personal homepage, or lab homepage roles. This is the default; "
            "use --official-profile-pages-only to restrict to primary profiles."
        ),
    )
    parser.add_argument(
        "--official-profile-pages-only",
        action="store_false",
        dest="include_owned_homepage_pages",
        help="Restrict ingest to each professor's primary official profile page.",
    )
    parser.add_argument(
        "--llm-publication-extraction",
        action="store_true",
        help=(
            "Enable source-grounded LLM fallback for homepage publication sections "
            "when rule extraction emits suspicious titles or low-recall sections."
        ),
    )
    parser.add_argument(
        "--force-llm-publication-extraction",
        action="store_true",
        help=(
            "Force source-grounded LLM extraction for every detected homepage "
            "publication section. Implies --llm-publication-extraction."
        ),
    )
    parser.add_argument(
        "--llm-profile",
        default="gemma4",
        help="LLM profile for --llm-publication-extraction.",
    )
    parser.add_argument(
        "--external-resolution-max-per-professor",
        type=int,
        default=None,
        help=(
            "Maximum realtime external title-resolution attempts per professor. "
            "Use a small value such as 3-5 for bulk fast-mode seed reruns."
        ),
    )
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
    logging.getLogger("httpx").setLevel(logging.WARNING)

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.stderr.write("DATABASE_URL is required for homepage paper ingest.\n")
        raise SystemExit(1)

    resume_checkpoint_path: Path | None = None
    if args.resume is not None:
        resume_checkpoint_path = (
            Path(args.resume) if args.resume else _default_resume_checkpoint_path()
        )

    publication_extractor = (
        _build_llm_publication_extractor(
            args.llm_profile,
            force_llm=args.force_llm_publication_extraction,
        )
        if args.llm_publication_extraction
        or args.force_llm_publication_extraction
        else None
    )

    conn = None
    try:
        conn = _open_database_connection(dsn)
        report = run_homepage_paper_ingest(
            conn,
            dry_run=args.dry_run,
            limit=args.limit,
            institution=args.institution,
            department=args.department,
            seed_id=args.seed_id,
            prof_id=args.prof_id,
            resume_checkpoint_path=resume_checkpoint_path,
            publication_extractor=publication_extractor,
            include_owned_homepage_pages=args.include_owned_homepage_pages,
            external_resolution_max_per_professor=(
                args.external_resolution_max_per_professor
            ),
        )
        commit = getattr(conn, "commit", None)
        if callable(commit):
            commit()
        payload = asdict(report)
        payload["run_id"] = str(report.run_id)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception:
        if conn is not None:
            rollback = getattr(conn, "rollback", None)
            if callable(rollback):
                rollback()
        logging.exception("Homepage paper ingest failed")
        return 1
    finally:
        if conn is not None:
            close = getattr(conn, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
