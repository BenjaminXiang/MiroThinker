from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Callable, Sequence, TextIO

from .recollection_readiness import (
    SeedReadinessResult,
    build_readiness_matrix,
    load_readiness_inputs,
)
from .seed_runner import SingleSeedRunResult, run_single_seed
from ..storage.postgres.connection import connect

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FullRunCandidate:
    seed_id: int
    adapter_name: str
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class ExcludedSeed:
    seed_id: int
    adapter_name: str
    failure_class: str
    issue_outcome: str
    exclusion_reason: str


@dataclass(frozen=True, slots=True)
class FullRunPlan:
    selected: list[FullRunCandidate]
    excluded: list[ExcludedSeed]


@dataclass(frozen=True, slots=True)
class FullRunResult:
    seed_id: int
    adapter_name: str
    run_id: str
    terminal_status: str
    failure_class: str
    items_processed: int
    items_failed: int
    homepage_paper_bridge_status: str
    homepage_paper_bridge_papers_linked: int
    homepage_paper_bridge_error: str
    issue_outcome: str
    p8_ready: bool
    error: str


@dataclass(frozen=True, slots=True)
class FullRunMatrix:
    rows: list[FullRunResult]
    excluded: list[ExcludedSeed]


@dataclass(frozen=True, slots=True)
class HomepagePaperBridgeResult:
    status: str
    papers_linked_total: int
    profs_processed: int
    error: str = ""


FullRunner = Callable[[int], SingleSeedRunResult]
HomepagePaperBridgeRunner = Callable[[int], HomepagePaperBridgeResult]

_HEADER = (
    "row_type",
    "seed_id",
    "adapter_name",
    "run_id",
    "terminal_status",
    "failure_class",
    "items_processed",
    "items_failed",
    "homepage_paper_bridge_status",
    "homepage_paper_bridge_papers_linked",
    "issue_outcome",
    "p8_ready",
    "reason_or_error",
)


def _build_full_run_plan(
    readiness_rows: Sequence[SeedReadinessResult],
    *,
    selected_seed_ids: set[int] | None,
) -> FullRunPlan:
    selected: list[FullRunCandidate] = []
    excluded: list[ExcludedSeed] = []
    for row in sorted(readiness_rows, key=lambda item: item.seed_id):
        if selected_seed_ids is not None and row.seed_id not in selected_seed_ids:
            continue
        adapter_name = row.resolver_result or ""
        if row.recommended_next_mode == "full" and row.full_recollection_allowed:
            selected.append(
                FullRunCandidate(
                    seed_id=row.seed_id,
                    adapter_name=adapter_name,
                    evidence_reference=row.evidence_reference,
                )
            )
            continue
        excluded.append(
            ExcludedSeed(
                seed_id=row.seed_id,
                adapter_name=adapter_name,
                failure_class=row.latest_failure_class or row.recommended_next_mode,
                issue_outcome=row.evidence_reference,
                exclusion_reason=row.decision_reason,
            )
        )
    return FullRunPlan(selected=selected, excluded=excluded)


def build_full_run_plan(
    readiness_rows: Sequence[SeedReadinessResult],
    *,
    selected_seed_ids: set[int] | None = None,
) -> FullRunPlan:
    return _build_full_run_plan(readiness_rows, selected_seed_ids=selected_seed_ids)


def run_full_plan(
    plan: FullRunPlan,
    *,
    runner: FullRunner | None = None,
    bridge_runner: HomepagePaperBridgeRunner | None = None,
    run_homepage_paper_bridge: bool = True,
    database_url: str | None = None,
) -> FullRunMatrix:
    run_one = runner or _run_single_seed_full
    run_bridge = bridge_runner or (
        lambda seed_id: _run_homepage_paper_bridge_for_seed(
            seed_id,
            database_url=database_url,
        )
    )
    rows: list[FullRunResult] = []
    for candidate in plan.selected:
        try:
            result = run_one(candidate.seed_id)
            failure_class = result.failure_class
            terminal_status = result.status
            error = result.error or ""
            run_id = result.run_id or ""
            issue_outcome = "" if failure_class == "success" else failure_class
            bridge_result = _run_bridge_after_successful_full_recollection(
                candidate.seed_id,
                result,
                bridge_runner=run_bridge,
                enabled=run_homepage_paper_bridge,
            )
            rows.append(
                FullRunResult(
                    seed_id=candidate.seed_id,
                    adapter_name=result.adapter_name or candidate.adapter_name,
                    run_id=run_id,
                    terminal_status=terminal_status,
                    failure_class=failure_class,
                    items_processed=result.items_processed,
                    items_failed=result.items_failed,
                    homepage_paper_bridge_status=bridge_result.status,
                    homepage_paper_bridge_papers_linked=(
                        bridge_result.papers_linked_total
                    ),
                    homepage_paper_bridge_error=bridge_result.error,
                    issue_outcome=issue_outcome,
                    p8_ready=(
                        terminal_status == "success"
                        and failure_class == "success"
                        and bridge_result.status == "success"
                    ),
                    error=error,
                )
            )
        except Exception as exc:
            rows.append(
                FullRunResult(
                    seed_id=candidate.seed_id,
                    adapter_name=candidate.adapter_name,
                    run_id="",
                    terminal_status="exception",
                    failure_class=type(exc).__name__,
                    items_processed=0,
                    items_failed=1,
                    homepage_paper_bridge_status="not_applicable",
                    homepage_paper_bridge_papers_linked=0,
                    homepage_paper_bridge_error="",
                    issue_outcome=type(exc).__name__,
                    p8_ready=False,
                    error=str(exc),
                )
            )
    return FullRunMatrix(rows=rows, excluded=plan.excluded)


def format_full_run_matrix(matrix: FullRunMatrix) -> list[str]:
    lines = ["\t".join(_HEADER)]
    for row in matrix.rows:
        lines.append(
            "\t".join(
                [
                    "executed",
                    str(row.seed_id),
                    row.adapter_name,
                    row.run_id,
                    row.terminal_status,
                    row.failure_class,
                    str(row.items_processed),
                    str(row.items_failed),
                    row.homepage_paper_bridge_status,
                    str(row.homepage_paper_bridge_papers_linked),
                    row.issue_outcome,
                    str(row.p8_ready),
                    row.error or row.homepage_paper_bridge_error,
                ]
            )
        )
    for row in matrix.excluded:
        lines.append(
            "\t".join(
                [
                    "excluded",
                    str(row.seed_id),
                    row.adapter_name,
                    "",
                    "blocked",
                    row.failure_class,
                    "0",
                    "0",
                    "not_applicable",
                    "0",
                    row.issue_outcome,
                    "False",
                    row.exclusion_reason,
                ]
            )
        )
    return lines


def print_full_run_matrix(matrix: FullRunMatrix, output: TextIO = sys.stdout) -> None:
    for line in format_full_run_matrix(matrix):
        print(line, file=output)


def run(
    *,
    database_url: str | None = None,
    selected_seed_ids: set[int] | None = None,
    run_homepage_paper_bridge: bool = True,
    output: TextIO = sys.stdout,
) -> int:
    with connect(database_url) as conn:
        readiness = build_readiness_matrix(load_readiness_inputs(conn))
    plan = build_full_run_plan(readiness, selected_seed_ids=selected_seed_ids)
    matrix = run_full_plan(
        plan,
        database_url=database_url,
        run_homepage_paper_bridge=run_homepage_paper_bridge,
    )
    print_full_run_matrix(matrix, output=output)
    return 1 if any(not row.p8_ready for row in matrix.rows) else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run controlled full recollection for full-ready Professor seeds."
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--seed-id",
        dest="seed_ids",
        action="append",
        type=int,
        default=None,
        help="Restrict execution to this seed id. May be provided multiple times.",
    )
    parser.add_argument(
        "--skip-homepage-paper-bridge",
        action="store_true",
        help=(
            "Explicitly skip the post-professor homepage paper bridge and "
            "record skipped_config in the output matrix."
        ),
    )
    args = parser.parse_args(argv)
    selected_seed_ids = set(args.seed_ids) if args.seed_ids else None
    return run(
        database_url=args.database_url,
        selected_seed_ids=selected_seed_ids,
        run_homepage_paper_bridge=not args.skip_homepage_paper_bridge,
    )


def _run_single_seed_full(seed_id: int) -> SingleSeedRunResult:
    return run_single_seed(seed_id, trigger_mode="full", timeout=45.0)


def _run_bridge_after_successful_full_recollection(
    seed_id: int,
    result: SingleSeedRunResult,
    *,
    bridge_runner: HomepagePaperBridgeRunner,
    enabled: bool,
) -> HomepagePaperBridgeResult:
    if not _successful_full_recollection_wrote_professors(result):
        return HomepagePaperBridgeResult(
            status="not_applicable",
            papers_linked_total=0,
            profs_processed=0,
        )
    if not enabled:
        return HomepagePaperBridgeResult(
            status="skipped_config",
            papers_linked_total=0,
            profs_processed=0,
            error="homepage paper bridge disabled by config",
        )
    try:
        return bridge_runner(seed_id)
    except Exception as exc:
        return HomepagePaperBridgeResult(
            status="failed",
            papers_linked_total=0,
            profs_processed=0,
            error=f"{type(exc).__name__}: {exc}",
        )


def _successful_full_recollection_wrote_professors(
    result: SingleSeedRunResult,
) -> bool:
    return (
        result.status == "success"
        and result.failure_class == "success"
        and result.items_processed > 0
    )


def _run_homepage_paper_bridge_for_seed(
    seed_id: int,
    *,
    database_url: str | None = None,
) -> HomepagePaperBridgeResult:
    from ..paper.homepage_ingest import run_homepage_paper_ingest

    with connect(database_url) as conn:
        report = run_homepage_paper_ingest(
            conn,
            seed_id=seed_id,
            publication_extractor=(
                _build_controlled_full_recollection_publication_extractor()
            ),
            include_owned_homepage_pages=True,
        )
        conn.commit()
    return HomepagePaperBridgeResult(
        status="success",
        papers_linked_total=report.papers_linked_total,
        profs_processed=report.profs_processed,
    )


def _build_controlled_full_recollection_publication_extractor():
    if _env_flag_disabled("CONTROLLED_FULL_RECOLLECTION_LLM_PUBLICATION_EXTRACTION"):
        return None

    from ..paper.llm_publication_extractor import build_llm_publication_extractor

    profile_name = os.environ.get(
        "CONTROLLED_FULL_RECOLLECTION_LLM_PUBLICATION_PROFILE",
        "gemma4",
    )
    force_llm = _env_flag_enabled(
        "CONTROLLED_FULL_RECOLLECTION_FORCE_LLM_PUBLICATION_EXTRACTION"
    )
    try:
        return build_llm_publication_extractor(profile_name, force_llm=force_llm)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM publication extractor unavailable for controlled full recollection; "
            "falling back to rule extraction (%s: %s)",
            exc.__class__.__name__,
            exc,
        )
        return None


def _env_flag_disabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"0", "false", "no", "off"}


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
