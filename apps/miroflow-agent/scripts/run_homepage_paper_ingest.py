#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
import sys
import time

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# Ensure imports work when running the script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.homepage_ingest import run_homepage_paper_ingest  # noqa: E402
from src.data_agents.professor.homepage_publications import (  # noqa: E402
    build_llm_publication_extraction_messages,
    extract_publications_from_html_with_llm_fallback,
    parse_llm_publication_extraction_response,
)
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

logger = logging.getLogger(__name__)
_LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS = 20.0
_LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS = (1.0,)


def _default_resume_checkpoint_path() -> Path:
    return PROJECT_ROOT / "logs" / "data_agents" / "paper" / "homepage_ingest_runs.jsonl"


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _build_llm_publication_extractor(profile_name: str, *, force_llm: bool = False):
    import httpx
    from openai import OpenAI

    settings = resolve_professor_llm_settings(
        profile_name,
        include_profile=True,
        strict=True,
    )
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(
            timeout=_LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS,
            trust_env=False,
        ),
        timeout=_LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS,
        max_retries=0,
    )
    model = settings["local_llm_model"]
    extra_body = build_non_thinking_extra_body(model)

    def _extract_from_section(section_text: str, page_url: str):
        messages = build_llm_publication_extraction_messages(
            section_text=section_text,
            page_url=page_url,
        )
        response = _create_llm_publication_completion_with_retry(
            client,
            model=model,
            messages=messages,
            extra_body=extra_body,
        )
        content = response.choices[0].message.content or ""
        return parse_llm_publication_extraction_response(content)

    def _extract_from_html(html: str, *, page_url: str):
        return extract_publications_from_html_with_llm_fallback(
            html,
            page_url=page_url,
            llm_extractor=_extract_from_section,
            force_llm=force_llm,
        )

    return _extract_from_html


def _create_llm_publication_completion_with_retry(
    client,
    *,
    model: str,
    messages,
    extra_body: dict,
):
    backoff_seconds = _LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS
    max_attempts = len(backoff_seconds) + 1
    for attempt_index in range(max_attempts):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=8192,
                extra_body=extra_body,
            )
        except Exception as exc:
            if attempt_index >= len(backoff_seconds):
                raise
            sleep_seconds = backoff_seconds[attempt_index]
            logger.warning(
                "LLM publication extraction request failed on attempt %s/%s; "
                "retrying in %.1fs (%s)",
                attempt_index + 1,
                max_attempts,
                sleep_seconds,
                exc.__class__.__name__,
            )
            time.sleep(sleep_seconds)
    raise RuntimeError("unreachable LLM publication extraction retry state")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run homepage paper ingest.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--institution")
    parser.add_argument("--prof-id")
    parser.add_argument("--resume", nargs="?", const="")
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
            prof_id=args.prof_id,
            resume_checkpoint_path=resume_checkpoint_path,
            publication_extractor=publication_extractor,
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
