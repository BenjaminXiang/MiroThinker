# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Batch re-process existing professors through V3 pipeline.

Usage:
    # Re-process 5 SUSTech professors (quick test):
    uv run python scripts/run_batch_reprocess_v3.py --institution 南方科技大学 --limit 5 --skip-web-search

    # Re-process all professors, skip papers (homepage + agent only):
    uv run python scripts/run_batch_reprocess_v3.py --skip-papers --skip-web-search --skip-vectorize

    # Full re-process with all stages:
    uv run python scripts/run_batch_reprocess_v3.py

    # Re-process with specific store path:
    uv run python scripts/run_batch_reprocess_v3.py --store-db /path/to/released_objects.db
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "miroflow-agent"))

from src.data_agents.professor.batch_reprocess import (
    BatchReprocessConfig,
    run_batch_reprocess,
)
from src.data_agents.professor.llm_profiles import (
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)

_DEFAULT_LLM_PROFILE = "gemma4"


def _default_store_db() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "released_objects.db"


def _default_output_dir() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "batch_reprocess_v3"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch re-process existing professors through V3 pipeline."
    )
    parser.add_argument(
        "--store-db", type=Path, default=_default_store_db(),
        help="Path to SQLite released objects store.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_default_output_dir(),
        help="Output directory for batch artifacts.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N professors.",
    )
    parser.add_argument(
        "--institution", type=str, default=None,
        help="Only process professors from this institution.",
    )
    parser.add_argument(
        "--max-concurrent", type=int, default=8,
        help="Maximum concurrent professor processing.",
    )
    parser.add_argument(
        "--skip-vectorize", action="store_true",
        help="Skip Milvus vectorization.",
    )
    parser.add_argument(
        "--skip-web-search", action="store_true",
        help="Skip web search enrichment.",
    )
    parser.add_argument(
        "--skip-homepage", action="store_true",
        help="Skip homepage crawling.",
    )
    parser.add_argument(
        "--skip-papers", action="store_true",
        help="Skip paper collection.",
    )
    parser.add_argument(
        "--skip-agent", action="store_true",
        help="Skip agent enrichment.",
    )
    parser.add_argument(
        "--skip-summary", action="store_true",
        help="Skip summary generation.",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--llm-profile",
        type=str,
        default=None,
        help=(
            "LLM profile to use for local/online routing."
            " Supported aliases: gemma, gemma4, qwen, qwen35, miro, mirothinker, ark, volc, volces, doubao."
            f" Defaults to {_DEFAULT_LLM_PROFILE}."
        ),
    )
    args = parser.parse_args()

    # Clear proxy env vars before any HTTP calls
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        llm_settings = resolve_professor_llm_settings(
            profile_name=args.llm_profile,
            default_profile=_DEFAULT_LLM_PROFILE,
            strict=True,
            include_profile=True,
        )
    except ValueError as exc:
        parser.error(f"{exc} Available profiles: {render_professor_llm_profile_names()}")
    if "llm_profile" in llm_settings:
        logging.info("Using LLM profile: %s", llm_settings["llm_profile"])
    logging.info("LLM aliases available: %s", render_professor_llm_profile_names())

    if not args.store_db.exists():
        print(json.dumps({
            "error": f"store database not found: {args.store_db}",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, ensure_ascii=False))
        return 1

    config = BatchReprocessConfig(
        store_db_path=str(args.store_db),
        output_dir=args.output_dir,
        local_llm_base_url=llm_settings["local_llm_base_url"],
        local_llm_model=llm_settings["local_llm_model"],
        local_llm_api_key=llm_settings["local_llm_api_key"],
        online_llm_base_url=llm_settings["online_llm_base_url"],
        online_llm_model=llm_settings["online_llm_model"],
        online_llm_api_key=llm_settings["online_llm_api_key"],
        embedding_base_url="" if args.skip_vectorize else os.getenv(
            "EMBEDDING_BASE_URL",
            "http://100.64.0.27:18005/v1",
        ),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("API_KEY", "")),
        milvus_uri=str(args.output_dir / "milvus.db"),
        serper_api_key=os.getenv("SERPER_API_KEY", ""),
        max_concurrent=args.max_concurrent,
        crawl_timeout=args.timeout,
        limit=args.limit,
        institution_filter=args.institution,
        skip_web_search=args.skip_web_search,
        skip_vectorize=args.skip_vectorize,
        skip_homepage_crawl=args.skip_homepage,
        skip_papers=args.skip_papers,
        skip_agent_enrichment=args.skip_agent,
        skip_summary=args.skip_summary,
    )

    started_at = time.monotonic()
    result = asyncio.run(run_batch_reprocess(config))
    elapsed = time.monotonic() - started_at

    report_dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "llm_profile": llm_settings.get("llm_profile", _DEFAULT_LLM_PROFILE),
        "store_db": str(args.store_db),
        "output_directory": str(args.output_dir),
        "report": {
            "total_loaded": result.report.total_loaded,
            "processed": result.report.processed,
            "direction_cleaned": result.report.direction_cleaned,
            "homepage_crawled": result.report.homepage_crawled,
            "paper_enriched": result.report.paper_enriched,
            "agent_triggered": result.report.agent_triggered,
            "agent_success": result.report.agent_success,
            "web_searched": result.report.web_searched,
            "identity_verified": result.report.identity_verified,
            "company_links": result.report.company_links,
            "summary_generated": result.report.summary_generated,
            "failed": result.report.failed,
        },
    }

    print(json.dumps(report_dict, ensure_ascii=False, indent=2))

    # Save report
    report_path = args.output_dir / "batch_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nReport saved to: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
