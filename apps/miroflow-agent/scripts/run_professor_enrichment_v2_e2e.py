# LEGACY (Round 7.5): v2 pipeline runner. Canonical professor data should now
# come from pipeline_v3 + canonical_writer + run_real_e2e_professor_backfill.py.
# Kept for reference; do not use for new data collection.
#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""End-to-end professor enrichment pipeline v2.

Runs the full v2 pipeline against real university URLs, storing results
to JSONL and Milvus. Supports --limit for partial runs, --retry-failed
for re-processing failures, and --institution for single-university runs.

Usage:
    uv run python scripts/run_professor_enrichment_v2_e2e.py
    uv run python scripts/run_professor_enrichment_v2_e2e.py --limit 10
    uv run python scripts/run_professor_enrichment_v2_e2e.py --institution 南方科技大学
    uv run python scripts/run_professor_enrichment_v2_e2e.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure imports work when running the script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.pipeline_v2 import (
    PipelineV2Config,
    run_professor_pipeline_v2,
)
from src.data_agents.professor.llm_profiles import (
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)

_DEFAULT_LLM_PROFILE = "qwen35"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_seed_doc() -> Path:
    return _repo_root() / "docs" / "教授 URL.md"


def _default_output_dir() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run professor enrichment pipeline v2 end-to-end."
    )
    parser.add_argument(
        "--seed-doc",
        type=Path,
        default=_default_seed_doc(),
        help="Path to markdown document containing roster seed URLs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_output_dir(),
        help="Output directory for pipeline artifacts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N professors (for testing).",
    )
    parser.add_argument(
        "--institution",
        type=str,
        default=None,
        help="Only process professors from this institution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Stage 1 only and print discovery stats.",
    )
    parser.add_argument(
        "--skip-vectorize",
        action="store_true",
        help="Skip Milvus vectorization step.",
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
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds.",
    )
    args = parser.parse_args()

    try:
        llm_settings = resolve_professor_llm_settings(
            profile_name=args.llm_profile,
            default_profile=_DEFAULT_LLM_PROFILE,
            strict=True,
            include_profile=True,
        )
    except ValueError as exc:
        parser.error(f"{exc} Available profiles: {render_professor_llm_profile_names()}")

    if not args.seed_doc.exists():
        print(
            json.dumps(
                {
                    "error": f"seed document not found: {args.seed_doc}",
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
            )
        )
        return 1

    config = PipelineV2Config(
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
    )

    started_at = time.monotonic()
    result = asyncio.run(run_professor_pipeline_v2(config))
    elapsed = time.monotonic() - started_at

    report_dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "llm_profile": llm_settings.get("llm_profile", _DEFAULT_LLM_PROFILE),
        "seed_document": str(args.seed_doc),
        "output_directory": str(args.output_dir),
        "report": {
            "stage1": {
                "seed_count": result.report.seed_count,
                "discovered_count": result.report.discovered_count,
                "unique_count": result.report.unique_count,
            },
            "stage2a": {
                "regex_structured": result.report.regex_structured_count,
                "regex_partial": result.report.regex_partial_count,
            },
            "stage2b": {
                "paper_enriched": result.report.paper_enriched_count,
                "papers_collected_total": result.report.papers_collected_total,
                "paper_staging_count": result.report.paper_staging_count,
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
            "stage2c": {
                "agent_triggered": result.report.agent_triggered_count,
                "agent_local_success": result.report.agent_local_success_count,
                "agent_online_escalation": result.report.agent_online_escalation_count,
                "agent_failed": result.report.agent_failed_count,
            },
            "stage3": {
                "summary_generated": result.report.summary_generated_count,
                "summary_fallback": result.report.summary_fallback_count,
            },
            "stage4": {
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
