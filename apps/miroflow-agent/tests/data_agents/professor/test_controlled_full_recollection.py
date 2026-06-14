from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.data_agents.paper.homepage_ingest import IngestReport
from src.data_agents.professor.controlled_full_recollection import (
    FullRunResult,
    HomepagePaperBridgeResult,
    build_full_run_plan,
    format_full_run_matrix,
    run_full_plan,
)
from src.data_agents.professor.recollection_readiness import SeedReadinessResult
from src.data_agents.professor.seed_runner import SingleSeedRunResult


def _ready(seed_id: int, *, allowed: bool = True, mode: str = "full") -> SeedReadinessResult:
    return SeedReadinessResult(
        seed_id=seed_id,
        school=f"School {seed_id}",
        department=None,
        seed_url=f"https://example.edu/{seed_id}",
        last_run_status="success" if allowed else "failure",
        resolver_result=f"adapter-{seed_id}",
        coverage_state="resolver_covered",
        latest_run_id=f"run-{seed_id}",
        latest_run_status="succeeded" if allowed else "failed",
        latest_trigger_mode="sample" if allowed else "preview",
        latest_failure_class="success" if allowed else "fetch_blocked",
        latest_issue_id=None if allowed else f"issue-{seed_id}",
        recommended_next_mode=mode,
        full_recollection_allowed=allowed,
        decision_reason=(
            "latest_sample_success_allows_full"
            if allowed
            else "latest_run_fetch_blocked"
        ),
        evidence_reference=f"run:{seed_id}" if allowed else f"issue:{seed_id}",
    )


def test_full_run_plan_selects_only_full_ready_rows_in_seed_order() -> None:
    plan = build_full_run_plan([_ready(8), _ready(5, allowed=False, mode="blocked"), _ready(6)])

    assert [row.seed_id for row in plan.selected] == [6, 8]
    assert [row.seed_id for row in plan.excluded] == [5]
    assert plan.excluded[0].exclusion_reason == "latest_run_fetch_blocked"


def test_full_run_plan_can_filter_selected_seed_ids_without_selecting_blocked_rows() -> None:
    plan = build_full_run_plan(
        [_ready(8), _ready(5, allowed=False, mode="blocked"), _ready(6)],
        selected_seed_ids={5, 8},
    )

    assert [row.seed_id for row in plan.selected] == [8]
    assert [row.seed_id for row in plan.excluded] == [5]


def test_full_plan_runner_does_not_call_blocked_rows() -> None:
    plan = build_full_run_plan([_ready(6), _ready(5, allowed=False, mode="blocked")])
    called: list[int] = []

    def runner(seed_id: int) -> SingleSeedRunResult:
        called.append(seed_id)
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=f"full-{seed_id}",
            status="success",
            items_processed=4,
            items_failed=0,
            adapter_name=f"adapter-{seed_id}",
            failure_class="success",
        )

    result = run_full_plan(
        plan,
        runner=runner,
        bridge_runner=lambda _seed_id: HomepagePaperBridgeResult(
            status="success",
            papers_linked_total=7,
            profs_processed=1,
        ),
    )

    assert called == [6]
    assert result.rows == [
        FullRunResult(
            seed_id=6,
            adapter_name="adapter-6",
            run_id="full-6",
            terminal_status="success",
            failure_class="success",
            items_processed=4,
            items_failed=0,
            homepage_paper_bridge_status="success",
            homepage_paper_bridge_papers_linked=7,
            homepage_paper_bridge_error="",
            issue_outcome="",
            p8_ready=True,
            error="",
        )
    ]
    assert result.excluded[0].seed_id == 5


def test_full_plan_runs_homepage_paper_bridge_after_successful_full_run() -> None:
    plan = build_full_run_plan([_ready(6), _ready(7, allowed=False, mode="blocked")])
    bridged_seed_ids: list[int] = []

    def runner(seed_id: int) -> SingleSeedRunResult:
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=f"full-{seed_id}",
            status="success",
            items_processed=4,
            items_failed=0,
            adapter_name=f"adapter-{seed_id}",
            failure_class="success",
        )

    def bridge_runner(seed_id: int) -> HomepagePaperBridgeResult:
        bridged_seed_ids.append(seed_id)
        return HomepagePaperBridgeResult(
            status="success",
            papers_linked_total=63,
            profs_processed=2,
            error="",
        )

    result = run_full_plan(plan, runner=runner, bridge_runner=bridge_runner)

    assert bridged_seed_ids == [6]
    assert result.rows[0].homepage_paper_bridge_status == "success"
    assert result.rows[0].homepage_paper_bridge_papers_linked == 63


def test_homepage_paper_bridge_passes_llm_publication_extractor_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.data_agents.paper import homepage_ingest as homepage_ingest_module
    from src.data_agents.paper import llm_publication_extractor
    from src.data_agents.professor import controlled_full_recollection as full_run

    class _ConnectContext:
        def __enter__(self) -> object:
            return conn

        def __exit__(self, *_args: Any) -> None:
            return None

    class _Connection:
        def commit(self) -> None:
            return None

    conn = _Connection()
    sentinel_extractor = object()
    called_kwargs: dict[str, Any] = {}
    monkeypatch.delenv(
        "CONTROLLED_FULL_RECOLLECTION_LLM_PUBLICATION_EXTRACTION",
        raising=False,
    )

    def fake_run_homepage_paper_ingest(
        conn_arg: object,
        **kwargs: Any,
    ) -> IngestReport:
        assert conn_arg is conn
        called_kwargs.update(kwargs)
        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=1,
            profs_processed=1,
            profs_skipped=0,
            papers_linked_total=3,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(
        full_run,
        "connect",
        lambda _database_url=None: _ConnectContext(),
    )
    monkeypatch.setattr(
        homepage_ingest_module,
        "run_homepage_paper_ingest",
        fake_run_homepage_paper_ingest,
    )
    monkeypatch.setattr(
        llm_publication_extractor,
        "build_llm_publication_extractor",
        lambda profile_name, **kwargs: sentinel_extractor,
    )

    result = full_run._run_homepage_paper_bridge_for_seed(
        25,
        database_url="postgresql://example/db",
    )

    assert result.status == "success"
    assert result.papers_linked_total == 3
    assert called_kwargs["seed_id"] == 25
    assert called_kwargs["include_owned_homepage_pages"] is True
    assert called_kwargs["publication_extractor"] is sentinel_extractor


def test_full_plan_records_explicit_homepage_paper_bridge_skip() -> None:
    plan = build_full_run_plan([_ready(6)])

    def bridge_runner(_seed_id: int) -> HomepagePaperBridgeResult:
        raise AssertionError("configured bridge skip must not call bridge runner")

    result = run_full_plan(
        plan,
        runner=lambda seed_id: SingleSeedRunResult(
            seed_id=seed_id,
            run_id=f"full-{seed_id}",
            status="success",
            items_processed=4,
            items_failed=0,
            adapter_name=f"adapter-{seed_id}",
            failure_class="success",
        ),
        bridge_runner=bridge_runner,
        run_homepage_paper_bridge=False,
    )

    assert result.rows[0].homepage_paper_bridge_status == "skipped_config"
    assert result.rows[0].p8_ready is False


def test_full_run_matrix_includes_executed_and_excluded_rows() -> None:
    plan = build_full_run_plan([_ready(6), _ready(5, allowed=False, mode="blocked")])
    result = run_full_plan(
        plan,
        runner=lambda seed_id: SingleSeedRunResult(
            seed_id=seed_id,
            run_id=f"full-{seed_id}",
            status="success",
            items_processed=4,
            items_failed=0,
            adapter_name=f"adapter-{seed_id}",
            failure_class="success",
        ),
        bridge_runner=lambda _seed_id: HomepagePaperBridgeResult(
            status="success",
            papers_linked_total=0,
            profs_processed=1,
        ),
    )

    lines = format_full_run_matrix(result)

    assert lines[0].split("\t") == [
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
    ]
    assert "executed\t6\tadapter-6\tfull-6\tsuccess\tsuccess\t4\t0\tsuccess\t0\t\tTrue\t" in lines
    assert "excluded\t5\tadapter-5\t\tblocked\tfetch_blocked\t0\t0\tnot_applicable\t0\tissue:5\tFalse\tlatest_run_fetch_blocked" in lines
