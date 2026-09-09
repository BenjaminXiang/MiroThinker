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

from src.data_agents.professor.pipeline_v3 import (  # noqa: E402
    PipelineV3Config,
    run_professor_pipeline_v3,
)
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)

_DEFAULT_LLM_PROFILE = "gemma4"
_DEFAULT_DATABASE_URL = "postgresql://miroflow:miroflow@localhost:15432/miroflow_real"


def _default_seed_doc() -> Path:
    return _REPO_ROOT / "docs" / "教授 URL.md"


def _default_output_dir() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "professor_v3"


def _ensure_metrics_database_url() -> str:
    if os.getenv("DATABASE_URL"):
        return "provided"
    database_url_test = os.getenv("DATABASE_URL_TEST")
    if database_url_test:
        os.environ["DATABASE_URL"] = database_url_test
        return "from_database_url_test"
    os.environ["DATABASE_URL"] = _DEFAULT_DATABASE_URL
    return "defaulted_host_real"


def _build_empty_report() -> dict:
    return {
        "stage1_discovery": {
            "seed_count": 0,
            "discovered_count": 0,
            "unique_count": 0,
        },
        "stage2_regex": {
            "structured": 0,
            "partial": 0,
            "non_stem_filtered": 0,
        },
        "stage2_1_direction_cleaning": {
            "cleaned_count": 0,
        },
        "stage3_homepage_crawl": {
            "crawled_count": 0,
            "fields_filled": 0,
        },
        "stage2b_papers": {
            "enriched": 0,
            "collected_total": 0,
            "staging_count": 0,
            "observability": {
                "observed": 0,
                "school_hit_count": 0,
                "fallback_count": 0,
                "name_disambiguation_conflict_count": 0,
                "school_hit_rate": 0.0,
                "fallback_rate": 0.0,
                "name_disambiguation_conflict_rate": 0.0,
                "source_breakdown": {},
            },
        },
        "stage2c_agent": {
            "triggered": 0,
            "local_success": 0,
            "online_escalation": 0,
            "failed": 0,
        },
        "stage5_web_search": {
            "search_count": 0,
            "identity_verified": 0,
            "low_signal_search_count": 0,
            "low_signal_skipped_count": 0,
            "low_signal_skipped_reasons": {},
        },
        "stage6_company_linking": {
            "links_confirmed": 0,
        },
        "stage7_summary": {
            "generated": 0,
            "fallback": 0,
        },
        "stage8_release": {
            "l1_blocked": 0,
            "released": 0,
            "quality_distribution": {},
            "vectorized": 0,
            "alerts": ["pipeline_failed"],
        },
    }


def _build_report_dict(
    *,
    args: argparse.Namespace,
    llm_settings: dict[str, str],
    elapsed_seconds: float,
    result: object | None = None,
    error: str | None = None,
) -> dict:
    if result is None:
        report = _build_empty_report()
    else:
        report = {
            "stage1_discovery": {
                "seed_count": getattr(result.report, "seed_count", 0),
                "discovered_count": getattr(result.report, "discovered_count", 0),
                "unique_count": getattr(result.report, "unique_count", 0),
            },
            "stage2_regex": {
                "structured": getattr(result.report, "regex_structured_count", 0),
                "partial": getattr(result.report, "regex_partial_count", 0),
                "non_stem_filtered": getattr(result.report, "non_stem_filtered_count", 0),
            },
            "stage2_1_direction_cleaning": {
                "cleaned_count": getattr(result.report, "direction_cleaned_count", 0),
            },
            "stage3_homepage_crawl": {
                "crawled_count": getattr(result.report, "homepage_crawled_count", 0),
                "fields_filled": getattr(result.report, "homepage_fields_filled", 0),
            },
            "stage2b_papers": {
                "enriched": getattr(result.report, "paper_enriched_count", 0),
                "collected_total": getattr(result.report, "papers_collected_total", 0),
                "staging_count": getattr(result.report, "paper_staging_count", 0),
                "observability": {
                    "observed": getattr(result.report, "paper_observation_count", 0),
                    "school_hit_count": getattr(result.report, "paper_school_hit_count", 0),
                    "fallback_count": getattr(result.report, "paper_fallback_count", 0),
                    "name_disambiguation_conflict_count": getattr(
                        result.report, "paper_name_disambiguation_conflict_count", 0
                    ),
                    "school_hit_rate": (
                        getattr(result.report, "paper_school_hit_count", 0)
                        / getattr(result.report, "paper_observation_count", 1)
                        if getattr(result.report, "paper_observation_count", 0)
                        else 0.0
                    ),
                    "fallback_rate": (
                        getattr(result.report, "paper_fallback_count", 0)
                        / getattr(result.report, "paper_observation_count", 1)
                        if getattr(result.report, "paper_observation_count", 0)
                        else 0.0
                    ),
                    "name_disambiguation_conflict_rate": (
                        getattr(result.report, "paper_name_disambiguation_conflict_count", 0)
                        / getattr(result.report, "paper_observation_count", 1)
                        if getattr(result.report, "paper_observation_count", 0)
                        else 0.0
                    ),
                    "source_breakdown": getattr(result.report, "paper_source_breakdown", {}),
                },
            },
            "stage2c_agent": {
                "triggered": getattr(result.report, "agent_triggered_count", 0),
                "local_success": getattr(result.report, "agent_local_success_count", 0),
                "online_escalation": getattr(result.report, "agent_online_escalation_count", 0),
                "failed": getattr(result.report, "agent_failed_count", 0),
            },
            "stage5_web_search": {
                "search_count": getattr(result.report, "web_search_count", 0),
                "identity_verified": getattr(result.report, "identity_verified_count", 0),
                "low_signal_search_count": getattr(result.report, "low_signal_web_search_count", 0),
                "low_signal_skipped_count": getattr(
                    result.report, "low_signal_web_search_skipped_count", 0
                ),
                "low_signal_skipped_reasons": getattr(
                    result.report, "low_signal_web_search_skipped_reasons", {}
                ),
            },
            "stage6_company_linking": {
                "links_confirmed": getattr(result.report, "company_links_confirmed", 0),
            },
            "stage7_summary": {
                "generated": getattr(result.report, "summary_generated_count", 0),
                "fallback": getattr(result.report, "summary_fallback_count", 0),
            },
            "stage8_release": {
                "l1_blocked": getattr(result.report, "l1_blocked_count", 0),
                "released": getattr(result.report, "released_count", 0),
                "quality_distribution": getattr(result.report, "quality_distribution", {}),
                "vectorized": getattr(result.report, "vectorized_count", 0),
                "alerts": list(getattr(result.report, "alerts", [])),
            },
        }

    output_files = {
        "enriched": str(args.output_dir / "enriched_v3.jsonl"),
        "paper_staging": str(args.output_dir / "paper_staging.jsonl"),
        "quality_report": str(args.output_dir / "quality_report.json"),
    }
    if result is not None and getattr(result, "output_files", None):
        output_files = {k: str(v) for k, v in result.output_files.items()}

    report_dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "llm_profile": llm_settings.get("llm_profile", _DEFAULT_LLM_PROFILE),
        "seed_document": str(args.seed_doc),
        "output_directory": str(args.output_dir),
        "report": report,
        "output_files": output_files,
    }
    if error is not None:
        report_dict["error"] = error
    return report_dict


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
        "--stem-only",
        action="store_true",
        help="Exclude clearly non-STEM professor records from output/release.",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=8,
        help="Maximum professors processed concurrently.",
    )
    parser.add_argument(
        "--homepage-timeout",
        type=float,
        default=180.0,
        help="Whole homepage enrichment timeout per professor in seconds.",
    )
    parser.add_argument(
        "--paper-timeout",
        type=float,
        default=180.0,
        help="Whole paper collection timeout per professor in seconds.",
    )
    parser.add_argument(
        "--summary-timeout",
        type=float,
        default=90.0,
        help="Whole summary generation timeout per professor in seconds.",
    )
    parser.add_argument(
        "--agent-timeout",
        type=float,
        default=300.0,
        help="Agent enrichment timeout budget in seconds.",
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
    metrics_database_url_source = _ensure_metrics_database_url()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logging.info("Metrics DATABASE_URL source: %s", metrics_database_url_source)

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
        max_concurrent=args.max_concurrent,
        crawl_timeout=args.timeout,
        homepage_timeout=args.homepage_timeout,
        paper_collection_timeout=args.paper_timeout,
        agent_timeout=args.agent_timeout,
        summary_timeout=args.summary_timeout,
        limit=args.limit,
        institution_filter=args.institution,
        skip_web_search=args.skip_web_search,
        skip_vectorize=args.skip_vectorize,
        exclude_non_stem=args.stem_only,
        store_db_path=store_db,
    )

    started_at = time.monotonic()
    result = None
    try:
        result = asyncio.run(run_professor_pipeline_v3(config))
        elapsed = time.monotonic() - started_at
        report_dict = _build_report_dict(
            args=args,
            llm_settings=llm_settings,
            elapsed_seconds=elapsed,
            result=result,
        )
        print(json.dumps(report_dict, ensure_ascii=False, indent=2))
        status_code = 0
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started_at
        report_dict = _build_report_dict(
            args=args,
            llm_settings=llm_settings,
            elapsed_seconds=elapsed,
            result=result,
            error=str(exc),
        )
        logging.exception("Professor V3 E2E run failed")
        print(json.dumps(report_dict, ensure_ascii=False, indent=2))
        status_code = 1

    # Save report
    report_path = args.output_dir / "e2e_report.json"
    report_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nReport saved to: {report_path}")
    return status_code


if __name__ == "__main__":
    sys.exit(main())
