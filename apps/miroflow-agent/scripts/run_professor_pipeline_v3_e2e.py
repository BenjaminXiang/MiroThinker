# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""E2E runner for Professor Pipeline V3.

Usage:
    # Process 2 professors per institution (quick validation):
    uv run python scripts/run_professor_pipeline_v3_e2e.py --limit 2 --skip-vectorize

    # Process only SUSTech:
    uv run python scripts/run_professor_pipeline_v3_e2e.py --institution 南方科技大学 --limit 5

    # Full run without web search:
    uv run python scripts/run_professor_pipeline_v3_e2e.py --skip-web-search --skip-vectorize

    # Full run with all layers:
    uv run python scripts/run_professor_pipeline_v3_e2e.py
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

from src.data_agents.professor.pipeline_v3 import (
    PipelineV3Config,
    run_professor_pipeline_v3,
)
from src.data_agents.professor.llm_profiles import (
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)

_DEFAULT_LLM_PROFILE = "gemma4"


def _default_seed_doc() -> Path:
    return _REPO_ROOT / "docs" / "教授 URL.md"


def _default_output_dir() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "professor_v3"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run professor enrichment pipeline V3 end-to-end."
    )
    parser.add_argument(
        "--seed-doc", type=Path, default=_default_seed_doc(),
        help="Path to markdown document containing roster seed URLs.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_default_output_dir(),
        help="Output directory for pipeline artifacts.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N professors (for testing).",
    )
    parser.add_argument(
        "--institution", type=str, default=None,
        help="Only process professors from this institution.",
    )
    parser.add_argument(
        "--skip-vectorize", action="store_true",
        help="Skip Milvus vectorization step.",
    )
    parser.add_argument(
        "--skip-web-search", action="store_true",
        help="Skip Layer 3 web search entirely.",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--store-db", type=str, default=None,
        help="Path to shared SQLite store for cross-domain writes.",
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
            f" Defaults to {_DEFAULT_LLM_PROFILE}.")
        ,
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
        return 1
    if "llm_profile" in llm_settings:
        logging.info("Using LLM profile: %s", llm_settings["llm_profile"])
    logging.info("LLM aliases available: %s", render_professor_llm_profile_names())

    if not args.seed_doc.exists():
        print(json.dumps({
            "error": f"seed document not found: {args.seed_doc}",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, ensure_ascii=False))
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    store_db = args.store_db or str(
        _REPO_ROOT / "logs" / "data_agents" / "released_objects.db"
    )

    config = PipelineV3Config(
        seed_doc=args.seed_doc,
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
        crawl_timeout=args.timeout,
        limit=args.limit,
        institution_filter=args.institution,
        skip_web_search=args.skip_web_search,
        skip_vectorize=args.skip_vectorize,
        store_db_path=store_db,
    )

    started_at = time.monotonic()
    result = asyncio.run(run_professor_pipeline_v3(config))
    elapsed = time.monotonic() - started_at

    report_dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "llm_profile": llm_settings.get("llm_profile", _DEFAULT_LLM_PROFILE),
        "seed_document": str(args.seed_doc),
        "output_directory": str(args.output_dir),
        "report": {
            "stage1_discovery": {
                "seed_count": result.report.seed_count,
                "discovered_count": result.report.discovered_count,
                "unique_count": result.report.unique_count,
            },
            "stage2_regex": {
                "structured": result.report.regex_structured_count,
                "partial": result.report.regex_partial_count,
            },
            "stage2_1_direction_cleaning": {
                "cleaned_count": result.report.direction_cleaned_count,
            },
            "stage3_homepage_crawl": {
                "crawled_count": result.report.homepage_crawled_count,
                "fields_filled": result.report.homepage_fields_filled,
            },
            "stage2b_papers": {
                "enriched": result.report.paper_enriched_count,
                "collected_total": result.report.papers_collected_total,
                "staging_count": result.report.paper_staging_count,
                "observability": {
                    "observed": result.report.paper_observation_count,
                    "school_hit_count": result.report.paper_school_hit_count,
                    "fallback_count": result.report.paper_fallback_count,
                    "name_disambiguation_conflict_count": result.report.paper_name_disambiguation_conflict_count,
                    "school_hit_rate": (
                        result.report.paper_school_hit_count / result.report.paper_observation_count
                        if result.report.paper_observation_count
                        else 0.0
                    ),
                    "fallback_rate": (
                        result.report.paper_fallback_count / result.report.paper_observation_count
                        if result.report.paper_observation_count
                        else 0.0
                    ),
                    "name_disambiguation_conflict_rate": (
                        result.report.paper_name_disambiguation_conflict_count
                        / result.report.paper_observation_count
                        if result.report.paper_observation_count
                        else 0.0
                    ),
                    "source_breakdown": result.report.paper_source_breakdown,
                },
            },
            "stage2c_agent": {
                "triggered": result.report.agent_triggered_count,
                "local_success": result.report.agent_local_success_count,
                "online_escalation": result.report.agent_online_escalation_count,
                "failed": result.report.agent_failed_count,
            },
            "stage5_web_search": {
                "search_count": result.report.web_search_count,
                "identity_verified": result.report.identity_verified_count,
            },
            "stage6_company_linking": {
                "links_confirmed": result.report.company_links_confirmed,
            },
            "stage7_summary": {
                "generated": result.report.summary_generated_count,
                "fallback": result.report.summary_fallback_count,
            },
            "stage8_release": {
                "l1_blocked": result.report.l1_blocked_count,
                "released": result.report.released_count,
                "quality_distribution": result.report.quality_distribution,
                "vectorized": result.report.vectorized_count,
                "alerts": result.report.alerts,
            },
        },
        "output_files": {k: str(v) for k, v in result.output_files.items()},
    }

    print(json.dumps(report_dict, ensure_ascii=False, indent=2))

    # Save report
    report_path = args.output_dir / "e2e_report.json"
    report_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nReport saved to: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
