from __future__ import annotations

import importlib.util
import io
import os
import sys
import types
from pathlib import Path

from src.data_agents.professor.core_profile_paper_quality_audit import (
    DatasetClosureBucketRow,
    DatasetClosureBuckets,
)
from src.data_agents.professor.dataset_quality_closure import (
    ApiSampleEvidence,
    AffectedAuditEvidence,
    DatasetClosurePostWriteVerificationReport,
    DatasetClosureWriteReport,
    IndexRefreshEvidence,
    LaneWriteBatchSummary,
    QualityReevaluationEvidence,
    ResidualRiskCoverageReport,
    ResidualRiskIssueFilingReport,
    build_lane_dry_run_report,
    format_dataset_closure_dry_run_report,
)
from src.data_agents.professor.dataset_candidate_generation import (
    ProfileSummaryCandidate,
    build_candidate_generation_report,
    format_candidate_generation_report,
)


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_professor_dataset_quality_closure.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_dataset_quality_closure",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_import_loads_app_env(monkeypatch) -> None:
    calls: list[Path] = []
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda path: calls.append(Path(path))
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    _import_cli()

    assert calls == [_SCRIPT_PATH.parent.parent / ".env"]


def test_cli_run_outputs_lane_dry_run_report(monkeypatch) -> None:
    cli = _import_cli()

    def fake_load_buckets(conn, *, bucket_limit):
        assert conn == "CONN"
        assert bucket_limit == 2
        return DatasetClosureBuckets(
            bucket_limit=2,
            summary={
                "ready_summary_lt_200": {
                    "total": 441,
                    "sampled": 1,
                    "truncated": True,
                    "remediation_lane": "profile_summary_repair",
                }
            },
            rows=[
                DatasetClosureBucketRow(
                    blocker_type="ready_summary_lt_200",
                    entity_type="professor",
                    remediation_lane="profile_summary_repair",
                    professor_id="PROF-1",
                    automatic_eligibility=True,
                    evidence={"profile_summary_length": 180},
                )
            ],
        )

    monkeypatch.setattr(cli, "load_buckets", fake_load_buckets)
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=2,
        mode="dry-run",
        output=output,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert '"mode": "dry_run"' in rendered
    assert '"lane": "profile_summary_repair"' in rendered
    assert '"dataset_input_count": 441' in rendered
    assert '"proposed_write_count": 1' in rendered


def test_cli_candidate_dry_run_outputs_candidate_report(monkeypatch, tmp_path) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                automatic_eligibility=True,
            )
        ],
    )

    def fake_load_buckets(conn, *, bucket_limit):
        assert conn == "CONN"
        assert bucket_limit == 1
        return buckets

    def fake_candidate_report(**kwargs):
        assert kwargs["conn"] == "CONN"
        assert kwargs["buckets"] is buckets
        assert kwargs["lanes"] == ("profile_summary_repair",)
        return build_candidate_generation_report(
            buckets,
            lanes=("profile_summary_repair",),
        )

    monkeypatch.setattr(cli, "load_buckets", fake_load_buckets)
    monkeypatch.setattr(
        cli,
        "build_candidate_generation_report_for_buckets",
        fake_candidate_report,
    )
    output = io.StringIO()
    candidate_output = tmp_path / "candidate-dry-run.json"

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="candidate-dry-run",
        output=output,
        candidate_output=candidate_output,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert '"mode": "candidate_dry_run"' in rendered
    assert '"selection_hash"' in rendered
    assert '"closure_selection_hash"' in rendered
    assert candidate_output.read_text(encoding="utf-8") == rendered


def test_cli_candidate_dry_run_defaults_to_real_llm_provider(monkeypatch) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[],
    )
    providers = cli.CandidateLLMProviderBundle(
        provider_name="deepseek-v4-pro",
        profile_summary_provider=lambda _profile_input: "profile",
        research_translator=lambda _source_text: "research",
        paper_summary_provider=lambda _generation_input: "paper",
    )

    monkeypatch.setattr(cli, "load_buckets", lambda _conn, bucket_limit: buckets)
    monkeypatch.setattr(
        cli,
        "_build_candidate_llm_providers",
        lambda **kwargs: providers,
        raising=False,
    )

    def fake_candidate_report(**kwargs):
        assert kwargs["profile_summary_provider"] is providers.profile_summary_provider
        assert kwargs["research_translator"] is providers.research_translator
        assert kwargs["paper_summary_provider"] is providers.paper_summary_provider
        assert kwargs["provider_name"] == "deepseek-v4-pro"
        return build_candidate_generation_report(
            buckets,
            lanes=("profile_summary_repair",),
        )

    monkeypatch.setattr(
        cli,
        "build_candidate_generation_report_for_buckets",
        fake_candidate_report,
    )

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="candidate-dry-run",
        output=io.StringIO(),
    )

    assert exit_code == 0


def test_cli_candidate_dry_run_deterministic_mode_is_explicit(monkeypatch) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[],
    )
    monkeypatch.setattr(cli, "load_buckets", lambda _conn, bucket_limit: buckets)

    def fail_if_provider_built(**_kwargs):
        raise AssertionError("deterministic mode must not build real providers")

    monkeypatch.setattr(
        cli,
        "_build_candidate_llm_providers",
        fail_if_provider_built,
        raising=False,
    )

    def fake_candidate_report(**kwargs):
        assert kwargs["profile_summary_provider"] is None
        assert kwargs["research_translator"] is None
        assert kwargs["paper_summary_provider"] is None
        assert kwargs["provider_name"] == "deterministic"
        return build_candidate_generation_report(
            buckets,
            lanes=("profile_summary_repair",),
        )

    monkeypatch.setattr(
        cli,
        "build_candidate_generation_report_for_buckets",
        fake_candidate_report,
    )

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="candidate-dry-run",
        output=io.StringIO(),
        provider_mode="deterministic",
    )

    assert exit_code == 0


def test_cli_parse_args_defaults_candidate_provider_mode_to_real() -> None:
    cli = _import_cli()

    args = cli._parse_args(["--mode", "candidate-dry-run"])

    assert args.provider_mode == "real"


def test_cli_parse_args_accepts_parallel_candidate_and_provider_limiter_options() -> None:
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--mode",
            "candidate-dry-run",
            "--candidate-concurrency",
            "4",
            "--provider-max-concurrency",
            "3",
            "--provider-min-interval-seconds",
            "0.2",
        ]
    )

    assert args.candidate_concurrency == 4
    assert args.provider_max_concurrency == 3
    assert args.provider_min_interval_seconds == 0.2


def test_cli_candidate_dry_run_parallel_uses_connection_factory_and_provider_limiter(
    monkeypatch,
) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=2,
        summary={
            "ready_summary_lt_200": {
                "total": 2,
                "sampled": 2,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[],
    )
    providers = cli.CandidateLLMProviderBundle(
        provider_name="deepseek-v4-pro",
        profile_summary_provider=lambda _profile_input: "profile",
        research_translator=lambda _source_text: "research",
        paper_summary_provider=lambda _generation_input: "paper",
    )

    monkeypatch.delenv("COMPANY_DEEPSEEK_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("COMPANY_DEEPSEEK_MIN_INTERVAL_SECONDS", raising=False)
    monkeypatch.setattr(cli, "load_buckets", lambda _conn, bucket_limit: buckets)
    monkeypatch.setattr(
        cli,
        "_build_candidate_llm_providers",
        lambda **_kwargs: providers,
        raising=False,
    )

    def fail_serial_builder(**_kwargs):
        raise AssertionError("parallel candidate dry-run must not use serial builder")

    def fake_parallel_builder(**kwargs):
        assert kwargs["connection_factory"] is connection_factory
        assert kwargs["buckets"] is buckets
        assert kwargs["lanes"] == ("profile_summary_repair",)
        assert kwargs["candidate_concurrency"] == 3
        provider_bundle = kwargs["providers_factory"]()
        assert provider_bundle.provider_name == "deepseek-v4-pro"
        assert provider_bundle.profile_summary_provider is providers.profile_summary_provider
        assert provider_bundle.research_translator is providers.research_translator
        assert provider_bundle.paper_summary_provider is providers.paper_summary_provider
        return build_candidate_generation_report(
            buckets,
            lanes=("profile_summary_repair",),
        )

    def connection_factory():
        return "WORKER-CONN"

    monkeypatch.setattr(
        cli,
        "build_candidate_generation_report_for_buckets",
        fail_serial_builder,
    )
    monkeypatch.setattr(
        cli,
        "build_candidate_generation_report_for_buckets_parallel",
        fake_parallel_builder,
        raising=False,
    )

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=2,
        mode="candidate-dry-run",
        output=io.StringIO(),
        candidate_concurrency=3,
        candidate_connection_factory=connection_factory,
        provider_max_concurrency=4,
        provider_min_interval_seconds=0.2,
    )

    assert exit_code == 0
    assert os.environ["COMPANY_DEEPSEEK_MAX_CONCURRENCY"] == "4"
    assert os.environ["COMPANY_DEEPSEEK_MIN_INTERVAL_SECONDS"] == "0.2"


def test_cli_write_mode_without_evidence_is_rejected() -> None:
    cli = _import_cli()
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=2,
        mode="write",
        output=output,
        dry_run_evidence=None,
    )

    assert exit_code == 2
    assert "missing_dry_run_evidence" in output.getvalue()


def test_cli_write_mode_loads_evidence_and_requires_run_id(
    monkeypatch,
    tmp_path,
) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                automatic_eligibility=True,
            )
        ],
    )
    evidence = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))
    evidence_path = tmp_path / "dry-run.json"
    evidence_path.write_text(
        format_dataset_closure_dry_run_report(evidence),
        encoding="utf-8",
    )

    def fake_load_buckets(conn, *, bucket_limit):
        assert conn == "CONN"
        assert bucket_limit == 1
        return buckets

    monkeypatch.setattr(cli, "load_buckets", fake_load_buckets)
    output = io.StringIO()

    missing_run_id_exit = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="write",
        output=output,
        dry_run_evidence=evidence_path,
    )

    assert missing_run_id_exit == 2
    assert "missing_run_id" in output.getvalue()

    output = io.StringIO()
    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="write",
        output=output,
        dry_run_evidence=evidence_path,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=1,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert '"mode": "write"' in rendered
    assert '"run_id": "11111111-1111-1111-1111-111111111111"' in rendered
    assert '"unresolved_issue_count": 1' in rendered


def test_cli_write_mode_accepts_candidate_dry_run_handoff(
    monkeypatch,
    tmp_path,
) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                automatic_eligibility=True,
                evidence={"profile_summary_length": 180},
            )
        ],
    )
    candidate = ProfileSummaryCandidate(
        professor_id="PROF-1",
        candidate_profile_summary=_valid_candidate_profile_summary(),
        source_ids=("PAGE-1",),
        source_text_hashes=("a" * 64,),
        generation_method="llm_synthesis",
        input_facts=("research_topic:可信人工智能",),
    )
    candidate_report = build_candidate_generation_report(
        buckets,
        candidates=(candidate,),
        lanes=("profile_summary_repair",),
    )
    evidence_path = tmp_path / "candidate-dry-run.json"
    evidence_path.write_text(
        format_candidate_generation_report(candidate_report),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "load_buckets", lambda _conn, bucket_limit: buckets)

    def fake_write_batch(**kwargs):
        enriched_buckets = kwargs["buckets"]
        row = enriched_buckets.rows[0]
        assert row.evidence["candidate_profile_summary"] == (
            candidate.candidate_profile_summary
        )
        assert kwargs["dry_run_evidence"].selection_hash == (
            candidate_report.closure_selection_hash
        )
        return DatasetClosureWriteReport(
            mode="write",
            dry_run=False,
            write_allowed=True,
            run_id="11111111-1111-1111-1111-111111111111",
            bucket_limit=1,
            batch_size=1,
            dry_run_selection_hash=candidate_report.closure_selection_hash,
            lanes=(
                LaneWriteBatchSummary(
                    lane="profile_summary_repair",
                    blocker_type="ready_summary_lt_200",
                    input_count=1,
                    attempted_count=1,
                    written_count=1,
                    unchanged_count=0,
                    skipped_count=0,
                    failed_count=0,
                    unresolved_issue_count=0,
                    changed_professor_ids=("PROF-1",),
                    changed_paper_ids=(),
                    rollback_evidence=(),
                    issues=(),
                ),
            ),
        )

    post_write_report = DatasetClosurePostWriteVerificationReport(
        mode="post_write_verification",
        status="success",
        completion_allowed=True,
        run_id="11111111-1111-1111-1111-111111111111",
        changed_professor_ids=("PROF-1",),
        changed_paper_ids=(),
    )
    monkeypatch.setattr(cli, "run_dataset_closure_write_batch", fake_write_batch)
    monkeypatch.setattr(
        cli,
        "build_post_write_verification_report",
        lambda **_kwargs: post_write_report,
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="write",
        output=output,
        dry_run_evidence=evidence_path,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=1,
    )

    assert exit_code == 0
    assert '"mode": "write"' in output.getvalue()


def test_cli_write_mode_outputs_post_write_verification(monkeypatch, tmp_path) -> None:
    cli = _import_cli()
    evidence_path = tmp_path / "dry-run.json"
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                automatic_eligibility=True,
            )
        ],
    )
    evidence_path.write_text(
        format_dataset_closure_dry_run_report(
            build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))
        ),
        encoding="utf-8",
    )
    write_report = DatasetClosureWriteReport(
        mode="write",
        dry_run=False,
        write_allowed=True,
        run_id="11111111-1111-1111-1111-111111111111",
        bucket_limit=1,
        batch_size=1,
        dry_run_selection_hash="hash",
        lanes=(
            LaneWriteBatchSummary(
                lane="profile_summary_repair",
                blocker_type="ready_summary_lt_200",
                input_count=1,
                attempted_count=1,
                written_count=1,
                unchanged_count=0,
                skipped_count=0,
                failed_count=0,
                unresolved_issue_count=0,
                changed_professor_ids=("PROF-1",),
                changed_paper_ids=(),
                rollback_evidence=(),
                issues=(),
            ),
        ),
    )
    post_write_report = DatasetClosurePostWriteVerificationReport(
        mode="post_write_verification",
        status="success",
        completion_allowed=True,
        run_id="11111111-1111-1111-1111-111111111111",
        changed_professor_ids=("PROF-1",),
        changed_paper_ids=(),
        quality_re_evaluation=QualityReevaluationEvidence(
            evaluated_professor_ids=("PROF-1",),
            before_distribution={"needs_enrichment": 1},
            after_distribution={"ready": 1},
        ),
        affected_audit=AffectedAuditEvidence(
            checked_professor_ids=("PROF-1",),
            checked_paper_ids=(),
            remaining_blocker_counts={},
        ),
        admin_professor_detail_samples=ApiSampleEvidence(sampled_ids=("PROF-1",)),
        paper_detail_samples=ApiSampleEvidence(sampled_ids=()),
        index_refresh_selection=IndexRefreshEvidence(
            professor_ids=("PROF-1",),
            paper_ids=(),
        ),
    )

    monkeypatch.setattr(cli, "load_buckets", lambda _conn, bucket_limit: buckets)
    monkeypatch.setattr(cli, "run_dataset_closure_write_batch", lambda **_kwargs: write_report)
    monkeypatch.setattr(
        cli,
        "build_post_write_verification_report",
        lambda **_kwargs: post_write_report,
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="write",
        output=output,
        dry_run_evidence=evidence_path,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=1,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert '"post_write_verification"' in rendered
    assert '"completion_allowed": true' in rendered


def test_cli_residual_risk_mode_requires_run_id(monkeypatch) -> None:
    cli = _import_cli()
    monkeypatch.setattr(
        cli,
        "load_buckets",
        lambda _conn, bucket_limit: DatasetClosureBuckets(
            bucket_limit=0,
            summary={},
            rows=[],
        ),
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=10,
        mode="residual-risk",
        output=output,
    )

    assert exit_code == 2
    assert "missing_run_id" in output.getvalue()


def test_cli_residual_risk_mode_outputs_filing_and_coverage(monkeypatch) -> None:
    cli = _import_cli()
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                automatic_eligibility=True,
            )
        ],
    )
    monkeypatch.setattr(cli, "load_buckets", lambda _conn, bucket_limit: buckets)
    monkeypatch.setattr(
        cli,
        "file_residual_risk_issues_for_buckets",
        lambda **_kwargs: ResidualRiskIssueFilingReport(
            mode="residual_risk_issue_filing",
            run_id="11111111-1111-1111-1111-111111111111",
            input_count=1,
            inserted_count=1,
            updated_count=0,
            by_blocker={"ready_summary_lt_200": 1},
        ),
    )
    monkeypatch.setattr(
        cli,
        "build_residual_risk_coverage_report",
        lambda **_kwargs: ResidualRiskCoverageReport(
            mode="residual_risk_coverage",
            status="complete",
            input_count=1,
            covered_count=1,
            unclassified_count=0,
            covered_by_blocker={"ready_summary_lt_200": 1},
        ),
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="residual-risk",
        output=output,
        run_id="11111111-1111-1111-1111-111111111111",
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert '"residual_risk_issue_filing"' in rendered
    assert '"residual_risk_coverage"' in rendered
    assert '"unclassified_count": 0' in rendered


def test_cli_residual_risk_coverage_returns_nonzero_when_incomplete(monkeypatch) -> None:
    cli = _import_cli()
    monkeypatch.setattr(
        cli,
        "load_buckets",
        lambda _conn, bucket_limit: DatasetClosureBuckets(
            bucket_limit=1,
            summary={},
            rows=[],
        ),
    )
    monkeypatch.setattr(
        cli,
        "build_residual_risk_coverage_report",
        lambda **_kwargs: ResidualRiskCoverageReport(
            mode="residual_risk_coverage",
            status="incomplete",
            input_count=1,
            covered_count=0,
            unclassified_count=1,
            covered_by_blocker={},
            unclassified_samples=({"professor_id": "PROF-1"},),
        ),
    )
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        lanes=("profile_summary_repair",),
        bucket_limit=1,
        mode="residual-risk-coverage",
        output=output,
    )

    assert exit_code == 1
    assert '"status": "incomplete"' in output.getvalue()


def test_cli_lane_resolution_drops_default_all_when_specific_lane_is_given() -> None:
    cli = _import_cli()

    assert cli._resolve_lanes(["all"]) == cli.ALL_CLOSURE_LANES
    assert cli._resolve_lanes(["all", "profile_summary_repair"]) == (
        "profile_summary_repair",
    )
    assert cli._resolve_lanes(
        ["profile_summary_repair", "duplicate_paper_merge"]
    ) == ("profile_summary_repair", "duplicate_paper_merge")


def _valid_candidate_profile_summary() -> str:
    summary = (
        "Ahmed Elazab现任清华大学深圳国际研究生院助理教授、博士生导师，研究聚焦可信人工智能、"
        "医学影像分析和脑疾病诊断预后。他结合机器学习、深度学习与多模态神经影像融合，构建稳健的"
        "计算机辅助检测与诊断系统，并通过模式识别和神经信息学发现疾病特异性生物标志物。其工作强调"
        "可解释人工智能和临床可解释性，目标是形成可融入医疗流程的可靠决策支持工具。相关成果可支撑"
        "教师画像中的研究领域、论文摘要和后续可追溯检索。"
    )
    assert 200 <= len(summary) <= 300
    return summary
