#!/usr/bin/env python3
"""Run read-only Professor dataset quality closure dry-run reports."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Sequence, TextIO

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
load_dotenv(_APP_ROOT / ".env")

from src.data_agents.professor.core_profile_paper_quality_audit import (  # noqa: E402
    load_baseline_paper_metrics,
    load_baseline_professor_metrics,
    load_dataset_closure_buckets,
)
from src.data_agents.professor.dataset_candidate_generation import (  # noqa: E402
    CandidateGenerationProviders,
    build_candidate_generation_report_for_buckets,
    build_candidate_generation_report_for_buckets_parallel,
    enrich_buckets_with_candidate_write_evidence,
    format_candidate_generation_report,
)
from src.data_agents.professor.dataset_quality_closure import (  # noqa: E402
    ALL_CLOSURE_LANES,
    ClosureLaneName,
    DryRunEvidenceRequired,
    DryRunEvidenceMismatch,
    build_post_write_verification_report,
    build_lane_dry_run_report,
    build_residual_risk_coverage_report,
    default_dataset_closure_writers,
    default_post_write_verification_callbacks,
    file_residual_risk_issues_for_buckets,
    format_dataset_closure_dry_run_report,
    load_dry_run_evidence,
    require_dry_run_evidence_for_write,
    run_dataset_closure_write_batch,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)


@dataclass(frozen=True, slots=True)
class CandidateLLMProviderBundle:
    provider_name: str
    profile_summary_provider: object | None
    research_translator: object | None
    paper_summary_provider: object | None

    def to_generation_providers(self) -> CandidateGenerationProviders:
        return CandidateGenerationProviders(
            provider_name=self.provider_name,
            profile_summary_provider=self.profile_summary_provider,
            research_translator=self.research_translator,
            paper_summary_provider=self.paper_summary_provider,
        )


def load_buckets(conn, *, bucket_limit: int):
    professor_metrics = load_baseline_professor_metrics(conn)
    paper_metrics = load_baseline_paper_metrics(conn)
    return load_dataset_closure_buckets(
        conn,
        professor_metrics=professor_metrics,
        paper_metrics=paper_metrics,
        bucket_limit=bucket_limit,
    )


def run(
    *,
    conn,
    lanes: Sequence[ClosureLaneName],
    bucket_limit: int,
    mode: str,
    output: TextIO = sys.stdout,
    dry_run_evidence: str | Path | None = None,
    run_id: str | None = None,
    batch_size: int = 20,
    candidate_output: str | Path | None = None,
    provider_name: str | None = None,
    provider_mode: str = "real",
    llm_profile: str | None = None,
    provider_timeout_seconds: float | None = None,
    provider_retry_budget: int | None = None,
    candidate_concurrency: int = 1,
    candidate_connection_factory: Callable[[], Any] | None = None,
    provider_max_concurrency: int | None = None,
    provider_min_interval_seconds: float | None = None,
) -> int:
    if mode == "candidate-dry-run":
        buckets = load_buckets(conn, bucket_limit=bucket_limit)
        _apply_provider_rate_limit_overrides(
            provider_max_concurrency=provider_max_concurrency,
            provider_min_interval_seconds=provider_min_interval_seconds,
        )

        def build_provider_bundle() -> CandidateLLMProviderBundle:
            if provider_mode == "real":
                return _build_candidate_llm_providers(
                    provider_name=provider_name,
                    llm_profile=llm_profile,
                    timeout_seconds=provider_timeout_seconds,
                    retry_budget=provider_retry_budget,
                )
            return CandidateLLMProviderBundle(
                provider_name=provider_name or "deterministic",
                profile_summary_provider=None,
                research_translator=None,
                paper_summary_provider=None,
            )

        if candidate_concurrency > 1:
            if candidate_connection_factory is None:
                raise ValueError(
                    "candidate_connection_factory is required when "
                    "candidate_concurrency > 1"
                )
            report = build_candidate_generation_report_for_buckets_parallel(
                connection_factory=candidate_connection_factory,
                buckets=buckets,
                lanes=lanes,
                providers_factory=lambda: build_provider_bundle().to_generation_providers(),
                candidate_concurrency=candidate_concurrency,
            )
        else:
            provider_bundle = build_provider_bundle()
            report = build_candidate_generation_report_for_buckets(
                conn=conn,
                buckets=buckets,
                lanes=lanes,
                profile_summary_provider=provider_bundle.profile_summary_provider,
                research_translator=provider_bundle.research_translator,
                paper_summary_provider=provider_bundle.paper_summary_provider,
                provider_name=provider_bundle.provider_name,
            )
        rendered = format_candidate_generation_report(report)
        if candidate_output is not None:
            candidate_output_path = Path(candidate_output)
            candidate_output_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_output_path.write_text(rendered, encoding="utf-8")
        output.write(rendered)
        return 0

    if mode == "residual-risk":
        if not run_id:
            output.write(
                json.dumps(
                    {
                        "error": "missing_run_id",
                        "message": "residual-risk mode requires --run-id",
                        "mode": "residual-risk",
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            return 2
        try:
            buckets = load_buckets(conn, bucket_limit=bucket_limit)
            filing_report = file_residual_risk_issues_for_buckets(
                conn=conn,
                buckets=buckets,
                run_id=run_id,
                lanes=lanes,
            )
            coverage_report = build_residual_risk_coverage_report(
                conn=conn,
                buckets=buckets,
                lanes=lanes,
            )
        except ValueError as exc:
            output.write(
                json.dumps(
                    {
                        "error": "invalid_residual_risk_request",
                        "message": str(exc),
                        "mode": "residual-risk",
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            return 2
        output.write(
            json.dumps(
                {
                    "mode": "residual-risk",
                    "filing": asdict(filing_report),
                    "coverage": asdict(coverage_report),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return 0 if coverage_report.status == "complete" else 1

    if mode == "residual-risk-coverage":
        buckets = load_buckets(conn, bucket_limit=bucket_limit)
        coverage_report = build_residual_risk_coverage_report(
            conn=conn,
            buckets=buckets,
            lanes=lanes,
        )
        output.write(
            json.dumps(
                asdict(coverage_report),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return 0 if coverage_report.status == "complete" else 1

    if mode == "write":
        try:
            require_dry_run_evidence_for_write(
                lanes=lanes,
                evidence_path=dry_run_evidence,
            )
        except DryRunEvidenceRequired as exc:
            output.write(
                json.dumps(
                    {
                        "error": "missing_dry_run_evidence",
                        "message": str(exc),
                        "mode": "write",
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            return 2
        if run_id and not _pipeline_run_exists(conn, run_id):
            output.write(
                json.dumps(
                    {
                        "error": "missing_pipeline_run",
                        "message": (
                            "write mode requires --run-id to reference an "
                            "existing pipeline_run row"
                        ),
                        "mode": "write",
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            return 2
        try:
            buckets = load_buckets(conn, bucket_limit=bucket_limit)
            evidence, buckets = _load_write_mode_evidence_and_buckets(
                dry_run_evidence=dry_run_evidence,
                buckets=buckets,
                lanes=lanes,
            )
            opened_pipeline_run = False
            if not run_id:
                run_id = _open_write_mode_pipeline_run(
                    conn,
                    lanes=lanes,
                    bucket_limit=bucket_limit,
                    batch_size=batch_size,
                    dry_run_evidence=dry_run_evidence,
                )
                opened_pipeline_run = True
                _commit_if_supported(conn)
            report = run_dataset_closure_write_batch(
                conn=conn,
                buckets=buckets,
                lanes=lanes,
                dry_run_evidence=evidence,
                run_id=run_id,
                batch_size=batch_size,
                writers=default_dataset_closure_writers(),
            )
            post_write_report = build_post_write_verification_report(
                conn=conn,
                write_report=report,
                callbacks=default_post_write_verification_callbacks(),
            )
            if opened_pipeline_run:
                _close_opened_write_mode_pipeline_run(
                    conn,
                    run_id=run_id,
                    report=report,
                    post_write_report=post_write_report,
                )
        except (DryRunEvidenceMismatch, ValueError) as exc:
            output.write(
                json.dumps(
                    {
                        "error": "invalid_write_request",
                        "message": str(exc),
                        "mode": "write",
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            return 2
        payload = asdict(report)
        payload["post_write_verification"] = asdict(post_write_report)
        output.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if post_write_report.status == "failed" and (
            post_write_report.changed_professor_ids
            or post_write_report.changed_paper_ids
        ):
            return 1
        return 0

    buckets = load_buckets(conn, bucket_limit=bucket_limit)
    report = build_lane_dry_run_report(buckets, lanes=lanes)
    output.write(format_dataset_closure_dry_run_report(report))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = args.database_url or os.environ.get("DATABASE_URL") or os.environ.get(
        "DATABASE_URL_TEST"
    )
    if not dsn:
        sys.stderr.write("DATABASE_URL or --database-url is required.\n")
        return 2
    lanes = _resolve_lanes(args.lane)
    resolved_dsn = resolve_dsn(dsn)
    with psycopg.connect(resolved_dsn, row_factory=dict_row) as conn:
        return run(
            conn=conn,
            lanes=lanes,
            bucket_limit=args.bucket_limit,
            mode=args.mode,
            dry_run_evidence=args.dry_run_evidence,
            run_id=args.run_id,
            batch_size=args.batch_size,
            candidate_output=args.candidate_output,
            provider_name=args.provider_name,
            provider_mode=args.provider_mode,
            llm_profile=args.llm_profile,
            provider_timeout_seconds=args.provider_timeout_seconds,
            provider_retry_budget=args.provider_retry_budget,
            candidate_concurrency=args.candidate_concurrency,
            candidate_connection_factory=lambda: psycopg.connect(
                resolved_dsn,
                row_factory=dict_row,
            ),
            provider_max_concurrency=args.provider_max_concurrency,
            provider_min_interval_seconds=args.provider_min_interval_seconds,
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build read-only Professor dataset quality closure dry-run reports. "
            "Write mode only validates the dry-run evidence gate in this slice."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL, then DATABASE_URL_TEST.",
    )
    parser.add_argument(
        "--lane",
        action="append",
        choices=("all", *ALL_CLOSURE_LANES),
        default=["all"],
        help="Closure lane to include. Use repeatedly or 'all'.",
    )
    parser.add_argument(
        "--bucket-limit",
        type=int,
        default=20,
        help="Maximum bucket rows per blocker class.",
    )
    parser.add_argument(
        "--mode",
        choices=(
            "dry-run",
            "candidate-dry-run",
            "write",
            "residual-risk",
            "residual-risk-coverage",
        ),
        default="dry-run",
        help=(
            "Execution mode. Write mode refuses without dry-run evidence. "
            "Residual-risk mode only files pipeline_issue rows."
        ),
    )
    parser.add_argument(
        "--dry-run-evidence",
        default=None,
        help="Path to matching dry-run evidence required by write mode.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Concrete non-dry-run pipeline_run id required by write mode.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Maximum eligible rows to attempt per selected lane in write mode.",
    )
    parser.add_argument(
        "--candidate-output",
        default=None,
        help="Optional path to write candidate dry-run JSON evidence.",
    )
    parser.add_argument(
        "--provider-name",
        default=None,
        help="Provider label recorded in candidate dry-run failure metadata.",
    )
    parser.add_argument(
        "--provider-mode",
        choices=("real", "deterministic"),
        default="real",
        help=(
            "Candidate generation provider mode. Defaults to real LLM provider; "
            "use deterministic only for explicit debugging."
        ),
    )
    parser.add_argument(
        "--llm-profile",
        default=None,
        help="Professor LLM profile for real candidate generation.",
    )
    parser.add_argument(
        "--provider-timeout-seconds",
        type=float,
        default=None,
        help="Optional timeout override for real candidate LLM calls.",
    )
    parser.add_argument(
        "--provider-retry-budget",
        type=int,
        default=None,
        help="Optional retry budget override for real candidate LLM calls.",
    )
    parser.add_argument(
        "--candidate-concurrency",
        type=int,
        default=1,
        help="Candidate dry-run worker concurrency. Values above 1 use worker connections.",
    )
    parser.add_argument(
        "--provider-max-concurrency",
        type=int,
        default=None,
        help="Optional DeepSeek provider max concurrency override for candidate dry-run.",
    )
    parser.add_argument(
        "--provider-min-interval-seconds",
        type=float,
        default=None,
        help="Optional DeepSeek provider minimum interval override for candidate dry-run.",
    )
    return parser.parse_args(argv)


def _resolve_lanes(raw_lanes: Sequence[str]) -> tuple[ClosureLaneName, ...]:
    explicit = tuple(lane for lane in raw_lanes if lane != "all")
    if explicit:
        return explicit  # type: ignore[return-value]
    return ALL_CLOSURE_LANES


def _build_candidate_llm_providers(
    *,
    provider_name: str | None,
    llm_profile: str | None,
    timeout_seconds: float | None,
    retry_budget: int | None,
) -> CandidateLLMProviderBundle:
    from src.data_agents.professor.candidate_llm_provider import (
        open_professor_candidate_llm_provider,
    )

    profile_provider = open_professor_candidate_llm_provider(
        "profile_summary_synthesis",
        llm_profile=llm_profile,
        timeout_seconds=timeout_seconds,
        retry_budget=retry_budget,
    )
    research_provider = open_professor_candidate_llm_provider(
        "research_overview_translation",
        llm_profile=llm_profile,
        timeout_seconds=timeout_seconds,
        retry_budget=retry_budget,
    )
    paper_provider = open_professor_candidate_llm_provider(
        "paper_summary_synthesis",
        llm_profile=llm_profile,
        timeout_seconds=timeout_seconds,
        retry_budget=retry_budget,
    )
    resolved_provider_name = provider_name or profile_provider.provider_name
    return CandidateLLMProviderBundle(
        provider_name=resolved_provider_name,
        profile_summary_provider=profile_provider.generate_profile_summary,
        research_translator=research_provider.translate_research_overview,
        paper_summary_provider=paper_provider.generate_paper_summary,
    )


def _apply_provider_rate_limit_overrides(
    *,
    provider_max_concurrency: int | None = None,
    provider_min_interval_seconds: float | None = None,
) -> dict[str, int | float]:
    overrides: dict[str, int | float] = {}
    if provider_max_concurrency is not None:
        value = max(1, int(provider_max_concurrency))
        os.environ["COMPANY_DEEPSEEK_MAX_CONCURRENCY"] = str(value)
        overrides["deepseek_max_concurrency"] = value
    if provider_min_interval_seconds is not None:
        value = max(0.0, float(provider_min_interval_seconds))
        os.environ["COMPANY_DEEPSEEK_MIN_INTERVAL_SECONDS"] = str(value)
        overrides["deepseek_min_interval_seconds"] = value
    return overrides


def _pipeline_run_exists(conn, run_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM pipeline_run
         WHERE run_id = %s
         LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    return row is not None


def _open_write_mode_pipeline_run(
    conn,
    *,
    lanes: Sequence[ClosureLaneName],
    bucket_limit: int,
    batch_size: int,
    dry_run_evidence: str | Path | None,
) -> str:
    return str(
        open_pipeline_run(
            conn,
            run_kind="backfill_real",
            run_scope={
                "task": "professor_dataset_quality_closure",
                "mode": "write",
                "lanes": list(lanes),
                "bucket_limit": bucket_limit,
                "batch_size": batch_size,
                "dry_run_evidence": str(dry_run_evidence)
                if dry_run_evidence is not None
                else None,
            },
            triggered_by="run_professor_dataset_quality_closure",
        )
    )


def _close_opened_write_mode_pipeline_run(
    conn,
    *,
    run_id: str,
    report,
    post_write_report,
) -> None:
    failed_count = sum(lane.failed_count for lane in report.lanes)
    attempted_count = sum(lane.attempted_count for lane in report.lanes)
    if failed_count:
        status = "failed"
    elif post_write_report.completion_allowed:
        status = "succeeded"
    else:
        status = "partial"
    close_pipeline_run(
        conn,
        run_id=run_id,
        status=status,
        items_processed=attempted_count,
        items_failed=failed_count,
    )


def _commit_if_supported(conn) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _load_write_mode_evidence_and_buckets(
    *,
    dry_run_evidence: str | Path | None,
    buckets,
    lanes: Sequence[ClosureLaneName],
):
    path = Path(dry_run_evidence)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("mode") == "candidate_dry_run":
        closure_report = build_lane_dry_run_report(buckets, lanes=lanes)
        if payload.get("closure_selection_hash") != closure_report.selection_hash:
            raise DryRunEvidenceMismatch(
                "candidate dry-run closure_selection_hash does not match current bucket selection"
            )
        return (
            closure_report,
            enrich_buckets_with_candidate_write_evidence(
                buckets,
                candidate_payload=payload,
            ),
        )
    return load_dry_run_evidence(path), buckets


if __name__ == "__main__":
    raise SystemExit(main())
