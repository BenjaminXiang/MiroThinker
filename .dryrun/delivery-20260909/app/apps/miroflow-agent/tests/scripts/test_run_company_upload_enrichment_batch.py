from __future__ import annotations

from pathlib import Path
import sys
from uuid import UUID


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_upload_enrichment_batch.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_upload_enrichment_batch", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_stage_commands_scope_every_stage_to_company_ids(tmp_path) -> None:
    cli = _import_cli()
    batch_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    commands = cli._build_stage_commands(
        batch_id=batch_id,
        company_ids=["COMP-1", "COMP-2"],
        skip_milvus=False,
        sleep_seconds="0",
        source_product_limit=100,
        official_product_max_pages=2,
    )

    names = [name for name, _command in commands]
    assert names == [
        "xlsx_team_synthesis",
        "official_product_capture",
        "news_iyiou",
        "news_pitchhub",
        "generic_source_judgment",
        "signal_extract",
        "source_product_extract",
        "multi_source_narrative",
        "milvus_refresh",
    ]
    for name, command in commands:
        if name == "milvus_refresh":
            assert command.count("--company-id") == 2
        else:
            assert "--enrichment-batch-id" in command
            assert str(batch_id) in command
            assert command.count("--company-id") == 2
    assert "--enable-js-render" in dict(commands)["official_product_capture"]
    assert "--llm-structured-extract" in commands[6][1]
    assert "generic_web" in commands[6][1]
    assert "--skip-narrative" in commands[0][1]
    assert "--include-source-materials" in commands[7][1]
    assert "--skip-team" in commands[7][1]
    assert "--company-id" in commands[1][1]


def test_parse_args_accepts_dry_run_skip_flags() -> None:
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--dry-run",
            "--skip-live-web",
            "--skip-official-site",
            "--skip-yiou-pitchhub",
            "--skip-generic-serper",
            "--skip-persistence",
            "--skip-milvus",
            "--stage-concurrency",
            "4",
            "--llm-stage-concurrency",
            "3",
            "--web-stage-concurrency",
            "2",
            "--stage-subchunk-size",
            "2",
            "--stage-timeout-seconds",
            "123",
            "--stage-retry-budget",
            "2",
            "--retry-backoff-seconds",
            "0",
            "--child-llm-concurrency",
            "2",
            "--child-web-concurrency",
            "3",
            "--child-llm-timeout-seconds",
            "75",
            "--child-llm-retry-budget",
            "1",
            "--provider-llm-max-concurrency",
            "8",
            "--provider-serper-max-concurrency",
            "5",
            "--stale-after-minutes",
            "45",
            "--representative-sample-size",
            "200",
            "--company-id-file",
            "ids.txt",
            "--plan-only",
        ]
    )

    assert args.dry_run is True
    assert args.skip_live_web is True
    assert args.skip_official_site is True
    assert args.skip_yiou_pitchhub is True
    assert args.skip_generic_serper is True
    assert args.skip_persistence is True
    assert args.skip_milvus is True
    assert args.stage_concurrency == 4
    assert args.llm_stage_concurrency == 3
    assert args.web_stage_concurrency == 2
    assert args.stage_subchunk_size == 2
    assert args.stage_timeout_seconds == 123
    assert args.stage_retry_budget == 2
    assert args.retry_backoff_seconds == 0
    assert args.child_llm_concurrency == 2
    assert args.child_web_concurrency == 3
    assert args.child_llm_timeout_seconds == 75
    assert args.child_llm_retry_budget == 1
    assert args.provider_llm_max_concurrency == 8
    assert args.provider_serper_max_concurrency == 5
    assert args.stale_after_minutes == 45
    assert args.representative_sample_size == 200
    assert args.company_id_file == "ids.txt"
    assert args.plan_only is True


def test_parse_args_uses_upload_enrichment_env_defaults(monkeypatch) -> None:
    cli = _import_cli()
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_STAGE_CONCURRENCY", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_LLM_STAGE_CONCURRENCY", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_WEB_STAGE_CONCURRENCY", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_STAGE_SUBCHUNK_SIZE", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_STAGE_TIMEOUT_SECONDS", "1200")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_STAGE_RETRY_BUDGET", "1")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_CHILD_LLM_CONCURRENCY", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_CHILD_WEB_CONCURRENCY", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_PROVIDER_LLM_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("COMPANY_UPLOAD_ENRICHMENT_PROVIDER_SERPER_MAX_CONCURRENCY", "8")

    args = cli._parse_args(["--batch-id", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"])

    assert args.stage_concurrency == 8
    assert args.llm_stage_concurrency == 8
    assert args.web_stage_concurrency == 8
    assert args.stage_subchunk_size == 8
    assert args.stage_timeout_seconds == 1200
    assert args.stage_retry_budget == 1
    assert args.child_llm_concurrency == 8
    assert args.child_web_concurrency == 8
    assert args.provider_llm_max_concurrency == 8
    assert args.provider_serper_max_concurrency == 8


def test_load_company_id_file_accepts_json_or_newline(tmp_path) -> None:
    cli = _import_cli()
    newline_file = tmp_path / "ids.txt"
    newline_file.write_text("COMP-2\n# comment\nCOMP-1\nCOMP-2\n", encoding="utf-8")
    json_file = tmp_path / "ids.json"
    json_file.write_text('["COMP-5", "COMP-6", "COMP-5"]', encoding="utf-8")

    assert cli._load_company_id_file(newline_file) == ["COMP-2", "COMP-1"]
    assert cli._load_company_id_file(json_file) == ["COMP-5", "COMP-6"]


def test_provider_rate_limit_overrides_feed_stage_policy(monkeypatch) -> None:
    cli = _import_cli()
    monkeypatch.delenv("COMPANY_DEEPSEEK_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("COMPANY_SERPER_MAX_CONCURRENCY", raising=False)

    overrides = cli._apply_provider_rate_limit_overrides(
        llm_max_concurrency=8,
        serper_max_concurrency=5,
    )

    assert overrides == {
        "deepseek_max_concurrency": 8,
        "serper_max_concurrency": 5,
    }
    assert (
        cli._effective_stage_policy(
            "source_product_extract",
            stage_concurrency=8,
            llm_stage_concurrency=8,
        ).max_concurrency
        == 8
    )
    assert (
        cli._effective_stage_policy(
            "news_iyiou",
            stage_concurrency=8,
            web_stage_concurrency=8,
        ).max_concurrency
        == 5
    )
    assert cli._provider_rate_limit_summary()["deepseek_max_concurrency"] == 8


def test_load_company_sample_prefers_explicit_company_ids() -> None:
    cli = _import_cli()

    sample = cli._load_company_sample(
        None,
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        limit=2,
        include_failed=False,
        representative_sample_size=200,
        explicit_company_ids=["COMP-3", "COMP-1", "COMP-9"],
    )

    assert sample.company_ids == ["COMP-3", "COMP-1"]
    assert sample.selection_criteria["strategy"] == "explicit_company_id_file"
    assert cli._validation_scope(
        representative_sample_size=200,
        company_count=2,
        explicit_company_ids=True,
    ) == {
        "scope": "explicit_company_ids",
        "companies_selected": 2,
        "full_population_attempted": False,
    }


def test_stage_policy_routes_llm_and_web_stages_without_credentials() -> None:
    cli = _import_cli()

    source_policy = cli._effective_stage_policy(
        "generic_source_judgment",
        stage_concurrency=8,
        llm_stage_concurrency=3,
        web_stage_concurrency=2,
        stage_timeout_seconds=321,
        stage_retry_budget=2,
        retry_backoff_seconds=0,
    )
    news_policy = cli._effective_stage_policy(
        "news_iyiou",
        stage_concurrency=8,
        llm_stage_concurrency=3,
        web_stage_concurrency=2,
        stage_timeout_seconds=321,
        stage_retry_budget=2,
        retry_backoff_seconds=0,
    )

    assert source_policy.effective_concurrency == 3
    assert source_policy.task_family == "llm"
    assert source_policy.rate_limit_key == "deepseek"
    assert source_policy.llm_task_type == "source_judgment"
    assert source_policy.llm_audit == {
        "task_type": "source_judgment",
        "llm_profile": "deepseek-v4-pro",
        "model": "deepseek-v4-pro",
        "cascade_strategy": "direct",
    }
    rendered_policy = str(source_policy.to_report_dict()).casefold()
    assert "api_key" not in rendered_policy
    assert "sk-" not in rendered_policy

    assert news_policy.effective_concurrency == 2
    assert news_policy.task_family == "web"
    assert news_policy.rate_limit_key == "serper"
    assert news_policy.llm_task_type == "search_hint_generation"
    assert news_policy.llm_audit["llm_profile"] == "deepseek-v4-lite"


def test_stage_subchunks_respect_concurrency_and_explicit_size() -> None:
    cli = _import_cli()

    assert cli._stage_subchunks(
        ["COMP-1", "COMP-2", "COMP-3", "COMP-4", "COMP-5"],
        stage_name="generic_source_judgment",
        stage_concurrency=3,
        stage_subchunk_size=2,
    ) == [["COMP-1", "COMP-2"], ["COMP-3", "COMP-4"], ["COMP-5"]]
    assert cli._stage_subchunks(
        ["COMP-1", "COMP-2", "COMP-3", "COMP-4", "COMP-5"],
        stage_name="generic_source_judgment",
        stage_concurrency=2,
        stage_subchunk_size=None,
    ) == [["COMP-1", "COMP-2", "COMP-3"], ["COMP-4", "COMP-5"]]
    assert cli._stage_subchunks(
        ["COMP-1", "COMP-2", "COMP-3"],
        stage_name="milvus_refresh",
        stage_concurrency=3,
        stage_subchunk_size=1,
    ) == [["COMP-1", "COMP-2", "COMP-3"]]


def test_run_stage_shards_yields_completed_shards_before_slow_siblings(
    monkeypatch,
) -> None:
    from datetime import datetime, timezone
    import threading
    import time

    cli = _import_cli()
    release_slow = threading.Event()

    def fake_run_stage_shard(**kwargs):
        company_ids = kwargs["company_ids"]
        if company_ids == ["COMP-SLOW"]:
            release_slow.wait(timeout=1)
        return (
            company_ids,
            datetime.now(timezone.utc),
            {"name": kwargs["stage_name"], "status": "succeeded", "report": {}},
        )

    monkeypatch.setattr(cli, "_run_stage_shard", fake_run_stage_shard)
    timer = threading.Timer(0.3, release_slow.set)
    timer.start()
    started = time.monotonic()
    try:
        shard_results = iter(
            cli._run_stage_shards(
                stage_name="generic_source_judgment",
                command_template=["python", "child.py"],
                company_id_shards=[["COMP-SLOW"], ["COMP-FAST"]],
                dsn="postgresql://fake/test",
                stage_concurrency=2,
                policy=cli._effective_stage_policy(
                    "generic_source_judgment",
                    stage_concurrency=2,
                ),
            )
        )
        first_company_ids, _started_at, first_report = next(shard_results)
    finally:
        release_slow.set()
        timer.cancel()

    assert first_company_ids == ["COMP-FAST"]
    assert first_report["status"] == "succeeded"
    assert time.monotonic() - started < 0.25


def test_build_stage_commands_respects_dry_run_and_skip_flags() -> None:
    cli = _import_cli()
    batch_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    commands = cli._build_stage_commands(
        batch_id=batch_id,
        company_ids=["COMP-1"],
        skip_milvus=True,
        sleep_seconds="0",
        source_product_limit=100,
        official_product_max_pages=1,
        dry_run=True,
        skip_live_web=True,
        skip_official_site=False,
        skip_yiou_pitchhub=False,
        skip_generic_serper=False,
        skip_persistence=True,
    )

    names = [name for name, _command in commands]
    assert names == [
        "xlsx_team_synthesis",
        "signal_extract",
        "source_product_extract",
        "multi_source_narrative",
    ]
    for _name, command in commands:
        assert "--dry-run" in command


def test_build_stage_commands_passes_child_concurrency_and_checkpoint_stage() -> None:
    cli = _import_cli()
    batch_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    commands = dict(
        cli._build_stage_commands(
            batch_id=batch_id,
            company_ids=["COMP-1"],
            skip_milvus=True,
            sleep_seconds="0",
            source_product_limit=100,
            official_product_max_pages=1,
            child_llm_concurrency=2,
            child_web_concurrency=3,
            child_llm_timeout_seconds=75,
            child_llm_retry_budget=1,
        )
    )

    xlsx = commands["xlsx_team_synthesis"]
    assert xlsx[xlsx.index("--checkpoint-stage") + 1] == "xlsx_team_synthesis"
    assert xlsx[xlsx.index("--concurrency") + 1] == "2"
    assert xlsx[xlsx.index("--llm-timeout-seconds") + 1] == "75"
    assert xlsx[xlsx.index("--llm-retry-budget") + 1] == "1"
    narrative = commands["multi_source_narrative"]
    assert narrative[narrative.index("--checkpoint-stage") + 1] == "multi_source_narrative"
    assert narrative[narrative.index("--concurrency") + 1] == "2"
    assert narrative[narrative.index("--llm-timeout-seconds") + 1] == "75"
    assert narrative[narrative.index("--llm-retry-budget") + 1] == "1"
    assert "--checkpoint-stage" in commands["generic_source_judgment"]
    assert "generic_source_judgment" in commands["generic_source_judgment"]
    generic = commands["generic_source_judgment"]
    assert generic[generic.index("--concurrency") + 1] == "2"
    assert generic[generic.index("--llm-timeout-seconds") + 1] == "75"
    assert generic[generic.index("--llm-retry-budget") + 1] == "1"
    signal = commands["signal_extract"]
    assert signal[signal.index("--llm-timeout-seconds") + 1] == "75"
    assert signal[signal.index("--llm-retry-budget") + 1] == "1"
    products = commands["source_product_extract"]
    assert products[products.index("--llm-timeout-seconds") + 1] == "75"
    assert products[products.index("--llm-retry-budget") + 1] == "1"
    news = commands["news_iyiou"]
    assert news[news.index("--concurrency") + 1] == "3"
    assert news[news.index("--llm-timeout-seconds") + 1] == "75"
    assert news[news.index("--llm-retry-budget") + 1] == "1"


def test_failed_stage_only_marks_companies_without_child_checkpoint(monkeypatch) -> None:
    cli = _import_cli()

    monkeypatch.setattr(
        cli,
        "load_stage_pending_company_ids",
        lambda _conn, *, batch_id, stage, company_ids: ["COMP-2"],
    )

    assert cli._company_ids_to_mark_for_stage_report(
        conn=object(),
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        stage_name="generic_source_judgment",
        company_ids=["COMP-1", "COMP-2"],
        stage_report={"status": "failed"},
    ) == ["COMP-2"]
    assert cli._company_ids_to_mark_for_stage_report(
        conn=object(),
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        stage_name="generic_source_judgment",
        company_ids=["COMP-1", "COMP-2"],
        stage_report={"status": "succeeded"},
    ) == ["COMP-1", "COMP-2"]


def test_process_batch_report_includes_scale_validation_metadata(monkeypatch) -> None:
    cli = _import_cli()

    class _Conn:
        def close(self):
            pass

    heartbeats: list[dict] = []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "close_stale_running_enrichment_batches",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        cli,
        "load_pending_company_ids",
        lambda *_args, **_kwargs: ["COMP-1", "COMP-2"],
    )
    monkeypatch.setattr(
        cli,
        "load_stage_pending_company_ids",
        lambda *_args, **kwargs: kwargs["company_ids"],
    )
    monkeypatch.setattr(cli, "mark_batch_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_finished", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "record_batch_heartbeat",
        lambda *_args, **kwargs: heartbeats.append(kwargs),
    )
    monkeypatch.setattr(cli, "mark_company_stage_running", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_company_stage_complete", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "record_baseline_readiness_stage",
        lambda *args, **kwargs: {
            "companies_checked": len(kwargs["company_ids"]),
            "baseline_ready": 1,
            "baseline_blocked": 1,
            "blockers": {"missing_meaningful_baseline_field": 1},
        },
    )
    monkeypatch.setattr(cli, "_build_stage_commands", lambda **_kwargs: [])

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        limit=2,
        chunk_size=2,
        skip_milvus=True,
        dry_run=True,
        skip_live_web=True,
        skip_persistence=True,
    )

    assert report["selected_company_ids"] == ["COMP-1", "COMP-2"]
    assert report["run_config"]["enabled_stages"] == [
        cli.BASELINE_READINESS_STAGE,
        "xlsx_team_synthesis",
        "signal_extract",
        "source_product_extract",
        "multi_source_narrative",
    ]
    assert report["run_config"]["skipped_stages"] == {
        "official_product_capture": "skip_live_web",
        "news_iyiou": "skip_live_web",
        "news_pitchhub": "skip_live_web",
        "generic_source_judgment": "skip_live_web",
        "persistence": "dry_run_or_skip_persistence",
        "milvus_refresh": "skip_milvus",
    }
    assert report["summary"]["source_adapter_counts"] == {}
    assert report["summary"]["miss_reason_counts"] == {"baseline_not_ready": 1}
    assert "vector_refresh_count" in report["summary"]
    assert report["rag_smoke"] == {
        "status": "not_run",
        "reason": "rag_smoke_is_post_batch_validation_gate",
    }
    assert "dry_run_no_persistence" in report["residual_risks"]
    assert "requires_5180_manual_inspection" in report["residual_risks"]
    assert heartbeats
    assert heartbeats[0]["current_stage"] == "started"
    assert heartbeats[-1]["current_stage"] == "succeeded"
    assert heartbeats[-1]["quality_report"]["headline"] == "2/2 companies processed"


def test_process_batch_plan_only_uses_representative_sample_without_writes(monkeypatch) -> None:
    cli = _import_cli()

    class _Conn:
        def __init__(self) -> None:
            self.closed = False

        def close(self):
            self.closed = True

    conn = _Conn()
    mutating_calls: list[str] = []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: conn)
    monkeypatch.setattr(
        cli,
        "load_representative_company_sample",
        lambda *_args, **_kwargs: cli.RepresentativeCompanySample(
            company_ids=["COMP-1", "COMP-2"],
            candidates_total=5,
            selected_count=2,
            selection_criteria={
                "strategy": "deterministic_stratified_round_robin",
                "bucket_fields": ["industry", "website_availability", "source_coverage"],
            },
            bucket_summary=[
                {
                    "bucket": {
                        "industry": "医疗AI",
                        "website_availability": "has_website",
                        "source_coverage": "no_external_sources",
                    },
                    "candidates": 3,
                    "selected": 1,
                },
                {
                    "bucket": {
                        "industry": "机器人",
                        "website_availability": "no_website",
                        "source_coverage": "has_external_sources",
                    },
                    "candidates": 2,
                    "selected": 1,
                },
            ],
        ),
    )
    for name in (
        "close_stale_running_enrichment_batches",
        "mark_batch_started",
        "mark_batch_finished",
        "mark_batch_progress",
        "mark_company_stage_running",
        "mark_company_stage_complete",
        "record_baseline_readiness_stage",
    ):
        monkeypatch.setattr(
            cli,
            name,
            lambda *args, _name=name, **kwargs: mutating_calls.append(_name),
        )

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        dry_run=True,
        plan_only=True,
        representative_sample_size=200,
        skip_live_web=True,
        skip_persistence=True,
        skip_milvus=True,
        stage_concurrency=4,
        llm_stage_concurrency=3,
        web_stage_concurrency=2,
    )

    assert mutating_calls == []
    assert report["status"] == "planned"
    assert report["plan_only"] is True
    assert report["selected_company_ids"] == ["COMP-1", "COMP-2"]
    assert report["selection"]["candidates_total"] == 5
    assert report["selection"]["sample_size_requested"] == 200
    assert report["validation_scope"]["scope"] == "representative_sample"
    assert report["run_config"]["stage_policies"]["generic_source_judgment"][
        "effective_concurrency"
    ] == 3
    assert report["expected_writes"]["domain_rows"] == {
        "company_news_item": 0,
        "company_signal_event": 0,
        "company_product": 0,
        "company_application_scenario": 0,
        "company_vector_upsert": 0,
    }
    assert "sample_underfilled" in report["blocked_prerequisites"]


def test_main_returns_success_for_plan_only_report(monkeypatch, capsys) -> None:
    cli = _import_cli()

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        cli,
        "process_batch",
        lambda **_kwargs: {"status": "planned", "plan_only": True},
    )

    exit_code = cli.main(
        [
            "--batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--representative-sample-size",
            "200",
            "--plan-only",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert '"status": "planned"' in capsys.readouterr().out


def test_process_batch_live_representative_sample_stays_bounded(monkeypatch) -> None:
    cli = _import_cli()
    run_commands: list[list[str]] = []
    completed: list[dict] = []

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "load_representative_company_sample",
        lambda *_args, **_kwargs: cli.RepresentativeCompanySample(
            company_ids=["COMP-2", "COMP-5"],
            candidates_total=5,
            selected_count=2,
            selection_criteria={"strategy": "deterministic_stratified_round_robin"},
            bucket_summary=[],
        ),
    )
    monkeypatch.setattr(
        cli,
        "close_stale_running_enrichment_batches",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        cli,
        "load_stage_pending_company_ids",
        lambda *_args, **kwargs: kwargs["company_ids"],
    )
    monkeypatch.setattr(cli, "mark_batch_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_finished", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_company_stage_running", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "mark_company_stage_complete",
        lambda *args, **kwargs: completed.append(kwargs),
    )
    monkeypatch.setattr(
        cli,
        "record_baseline_readiness_stage",
        lambda *args, **kwargs: {
            "companies_checked": len(kwargs["company_ids"]),
            "baseline_ready": len(kwargs["company_ids"]),
            "baseline_blocked": 0,
            "blockers": {},
        },
    )

    def fake_run_command(name, command, dsn):
        run_commands.append(command)
        return {
            "name": name,
            "status": "succeeded",
            "report": {
                "companies_processed": command.count("--company-id"),
                "news_fetched": 0,
                "events_inserted": 0,
                "products_inserted": 0,
                "scenarios_inserted": 0,
            },
        }

    monkeypatch.setattr(cli, "_run_command", fake_run_command)
    monkeypatch.setattr(
        cli,
        "_stage_counters_by_company",
        lambda **kwargs: {
            company_id: cli._stage_counters(
                kwargs["stage_name"],
                kwargs["stage_report"],
            )
            for company_id in kwargs["company_ids"]
        },
    )

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        representative_sample_size=200,
        chunk_size=2,
        skip_milvus=False,
    )

    assert report["validation_scope"] == {
        "scope": "representative_sample",
        "sample_size_requested": 200,
        "companies_selected": 2,
        "full_population_attempted": False,
    }
    assert report["selected_company_ids"] == ["COMP-2", "COMP-5"]
    assert report["expected_writes"]["bounded_to_selected_company_ids"] is True
    assert report["expected_writes"]["domain_rows"]["company_vector_upsert"] == 2
    assert all("COMP-1" not in command for command in run_commands)
    assert all("COMP-3" not in command for command in run_commands)
    assert all(command.count("--company-id") == 2 for command in run_commands)
    assert {
        call["company_id"]
        for call in completed
        if call["stage"] == "milvus_refresh"
    } == {"COMP-2", "COMP-5"}


def test_build_stage_commands_passes_local_milvus_uri_as_cli_arg() -> None:
    cli = _import_cli()
    batch_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    commands = cli._build_stage_commands(
        batch_id=batch_id,
        company_ids=["COMP-1"],
        skip_milvus=False,
        sleep_seconds="0",
        source_product_limit=100,
        official_product_max_pages=1,
        milvus_uri="/tmp/company-validation/milvus.db",
    )

    milvus_command = dict(commands)["milvus_refresh"]
    assert "--milvus-uri" in milvus_command
    assert "/tmp/company-validation/milvus.db" in milvus_command


def test_run_command_scrubs_local_milvus_uri_env_when_cli_arg_is_used(monkeypatch) -> None:
    cli = _import_cli()
    captured_env: dict[str, str] = {}

    class _Completed:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def _fake_run(_command, **kwargs):
        captured_env.update(kwargs["env"])
        return _Completed()

    monkeypatch.setenv("MILVUS_URI", "/tmp/company-validation/milvus.db")
    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    cli._run_command(
        "milvus_refresh",
        [
            "python",
            "run_milvus_backfill.py",
            "--milvus-uri",
            "/tmp/company-validation/milvus.db",
        ],
        "postgresql://fake/test",
    )

    assert "MILVUS_URI" not in captured_env


def test_run_command_converts_timeout_to_failed_stage_report(monkeypatch) -> None:
    cli = _import_cli()

    def _fake_run(command, **kwargs):
        raise cli.subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    report = cli._run_command(
        "generic_source_judgment",
        ["python", "run_company_generic_source_judgment.py"],
        "postgresql://fake/test",
        timeout_seconds=12,
    )

    assert report["status"] == "failed"
    assert report["returncode"] is None
    assert report["report"] == {}
    assert "timed out after 12" in report["stderr_tail"]
    assert "partial stderr" in report["stderr_tail"]


def test_process_batch_skips_completed_companies_and_records_stage_reports(
    monkeypatch,
) -> None:
    cli = _import_cli()
    calls: list[dict] = []
    baseline_calls: list[dict] = []

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "close_stale_running_enrichment_batches",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        cli,
        "load_pending_company_ids",
        lambda *_args, **_kwargs: ["COMP-1", "COMP-2"],
    )
    monkeypatch.setattr(
        cli,
        "load_stage_pending_company_ids",
        lambda *_args, **kwargs: kwargs["company_ids"],
    )
    monkeypatch.setattr(cli, "mark_batch_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_finished", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "mark_company_stage_running",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        cli,
        "mark_company_stage_complete",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(
        cli,
        "record_baseline_readiness_stage",
        lambda *args, **kwargs: baseline_calls.append(kwargs)
        or {
            "companies_checked": len(kwargs["company_ids"]),
            "baseline_ready": len(kwargs["company_ids"]),
            "baseline_blocked": 0,
            "blockers": {},
        },
    )
    monkeypatch.setattr(
        cli,
        "_run_command",
        lambda name, command, dsn: {
            "name": name,
            "status": "succeeded",
            "report": {
                "news_inserted": 1 if name.startswith("news_") else 0,
                "events_inserted": 1 if name == "signal_extract" else 0,
                "products_inserted": 1 if name.endswith("product_extract") else 0,
                "scenarios_inserted": 1 if name == "source_product_extract" else 0,
                "companies_with_errors": 0,
            },
        },
    )
    monkeypatch.setattr(
        cli,
        "_stage_counters_by_company",
        lambda **kwargs: {
            company_id: cli._stage_counters(
                kwargs["stage_name"],
                kwargs["stage_report"],
            )
            for company_id in kwargs["company_ids"]
        },
    )

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        limit=2,
        chunk_size=2,
        skip_milvus=True,
    )

    assert report["companies_selected"] == 2
    assert report["companies_processed"] == 2
    assert report["status"] == "succeeded"
    assert baseline_calls == [
        {
            "batch_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "company_ids": ["COMP-1", "COMP-2"],
        }
    ]
    assert report["stage_reports"][0]["name"] == "baseline_readiness"
    assert {call["stage"] for call in calls} == {
        "xlsx_team_synthesis",
        "news_iyiou",
        "news_pitchhub",
        "generic_source_judgment",
        "signal_extract",
        "source_product_extract",
        "official_product_capture",
        "multi_source_narrative",
        "batch_complete",
    }


def test_process_batch_uses_per_company_counters_and_updates_progress(
    monkeypatch,
) -> None:
    cli = _import_cli()
    completed_calls: list[dict] = []
    progress_calls: list[dict] = []

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "close_stale_running_enrichment_batches",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        cli,
        "load_pending_company_ids",
        lambda *_args, **_kwargs: ["COMP-1", "COMP-2"],
    )
    monkeypatch.setattr(
        cli,
        "load_stage_pending_company_ids",
        lambda *_args, **kwargs: kwargs["company_ids"],
    )
    monkeypatch.setattr(cli, "mark_batch_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_finished", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "mark_batch_progress",
        lambda *args, **kwargs: progress_calls.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(cli, "_build_stage_commands", lambda **_kwargs: [("news_iyiou", ["cmd"])])
    monkeypatch.setattr(cli, "mark_company_stage_running", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "mark_company_stage_complete",
        lambda *args, **kwargs: completed_calls.append(kwargs),
    )
    monkeypatch.setattr(
        cli,
        "_stage_counters_by_company",
        lambda **_kwargs: {
            "COMP-1": {"query_count": 1, "accepted_source_count": 1},
            "COMP-2": {"query_count": 2, "accepted_source_count": 0},
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_miss_reason_by_company",
        lambda **_kwargs: {"COMP-2": "no_results"},
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "record_baseline_readiness_stage",
        lambda *args, **kwargs: {
            "companies_checked": len(kwargs["company_ids"]),
            "baseline_ready": len(kwargs["company_ids"]),
            "baseline_blocked": 0,
            "blockers": {},
        },
    )
    monkeypatch.setattr(
        cli,
        "_run_command",
        lambda name, command, dsn: {
            "name": name,
            "status": "succeeded",
            "report": {"news_fetched": 1, "search_audit_rows": 3},
        },
    )

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        limit=2,
        chunk_size=2,
        skip_milvus=False,
    )

    counters_by_company = {
        call["company_id"]: call["counters"] for call in completed_calls
    }
    miss_by_company = {
        call["company_id"]: call["miss_reason"] for call in completed_calls
    }
    assert counters_by_company["COMP-1"]["query_count"] == 1
    assert counters_by_company["COMP-2"]["query_count"] == 2
    assert miss_by_company["COMP-1"] is None
    assert miss_by_company["COMP-2"] == "no_results"
    assert progress_calls[-1]["companies_processed"] == 2
    assert report["companies_processed"] == 2
    assert report["summary"]["miss_reason_counts"] == {"no_results": 1}
    assert report["selected_company_ids"] == ["COMP-1", "COMP-2"]


def test_process_batch_parallelizes_stage_subcommands_when_enabled(monkeypatch) -> None:
    cli = _import_cli()
    completed_calls: list[dict] = []
    run_commands: list[list[str]] = []

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "close_stale_running_enrichment_batches",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        cli,
        "load_pending_company_ids",
        lambda *_args, **_kwargs: ["COMP-1", "COMP-2", "COMP-3"],
    )
    monkeypatch.setattr(
        cli,
        "load_stage_pending_company_ids",
        lambda *_args, **kwargs: kwargs["company_ids"],
    )
    monkeypatch.setattr(cli, "mark_batch_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_finished", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_company_stage_running", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "mark_company_stage_complete",
        lambda *args, **kwargs: completed_calls.append(kwargs),
    )
    monkeypatch.setattr(
        cli,
        "record_baseline_readiness_stage",
        lambda *args, **kwargs: {
            "companies_checked": len(kwargs["company_ids"]),
            "baseline_ready": len(kwargs["company_ids"]),
            "baseline_blocked": 0,
            "blockers": {},
        },
    )
    monkeypatch.setattr(
        cli,
        "_build_stage_commands",
        lambda **_kwargs: [
            (
                "generic_source_judgment",
                ["python", "run_company_generic_source_judgment.py"],
            )
        ],
    )

    def fake_run_command(name, command, dsn):
        run_commands.append(command)
        return {
            "name": name,
            "status": "succeeded",
            "report": {"queries_run": 1, "accepted_sources": 1},
        }

    monkeypatch.setattr(cli, "_run_command", fake_run_command)
    monkeypatch.setattr(
        cli,
        "_stage_counters_by_company",
        lambda **kwargs: {
            company_id: {"accepted_source_count": 1}
            for company_id in kwargs["company_ids"]
        },
    )

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        limit=3,
        chunk_size=3,
        skip_milvus=True,
        stage_concurrency=2,
        stage_subchunk_size=1,
    )

    assert report["status"] == "succeeded"
    assert len(run_commands) == 3
    assert all(command.count("--company-id") == 1 for command in run_commands)
    assert {
        call["company_id"]
        for call in completed_calls
        if call["stage"] == "generic_source_judgment"
    } == {"COMP-1", "COMP-2", "COMP-3"}
    assert report["run_config"]["stage_policies"]["generic_source_judgment"][
        "effective_concurrency"
    ] == 2
    assert report["summary"]["stage_succeeded_count"] >= 1


def test_process_batch_uses_policy_concurrency_and_reports_checkpoint_skips(
    monkeypatch,
) -> None:
    cli = _import_cli()
    run_commands: list[list[str]] = []

    class _Conn:
        def close(self):
            pass

    def fake_stage_pending(*_args, **kwargs):
        if kwargs["stage"] == "generic_source_judgment":
            return ["COMP-2", "COMP-3"]
        return kwargs["company_ids"]

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        cli,
        "close_stale_running_enrichment_batches",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        cli,
        "load_pending_company_ids",
        lambda *_args, **_kwargs: ["COMP-1", "COMP-2", "COMP-3"],
    )
    monkeypatch.setattr(cli, "load_stage_pending_company_ids", fake_stage_pending)
    monkeypatch.setattr(cli, "mark_batch_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_finished", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_batch_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_company_stage_running", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "mark_company_stage_complete", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "record_baseline_readiness_stage",
        lambda *args, **kwargs: {
            "companies_checked": len(kwargs["company_ids"]),
            "baseline_ready": len(kwargs["company_ids"]),
            "baseline_blocked": 0,
            "blockers": {},
        },
    )
    monkeypatch.setattr(
        cli,
        "_build_stage_commands",
        lambda **_kwargs: [
            (
                "generic_source_judgment",
                ["python", "run_company_generic_source_judgment.py"],
            )
        ],
    )

    def fake_run_command(name, command, dsn):
        run_commands.append(command)
        return {
            "name": name,
            "status": "succeeded",
            "report": {"queries_run": 1, "accepted_sources": 1},
        }

    monkeypatch.setattr(cli, "_run_command", fake_run_command)
    monkeypatch.setattr(
        cli,
        "_stage_counters_by_company",
        lambda **kwargs: {
            company_id: {"accepted_source_count": 1}
            for company_id in kwargs["company_ids"]
        },
    )

    report = cli.process_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        limit=3,
        chunk_size=3,
        skip_milvus=True,
        stage_concurrency=8,
        llm_stage_concurrency=2,
        stage_subchunk_size=1,
    )

    assert len(run_commands) == 2
    assert all("COMP-1" not in command for command in run_commands)
    assert report["summary"]["companies_skipped_by_checkpoint"] == 1
    assert report["summary"]["stage_skipped_by_checkpoint"][
        "generic_source_judgment"
    ] == 1


def test_miss_reason_by_company_covers_non_search_stage_failures() -> None:
    cli = _import_cli()

    assert cli._miss_reason_by_company(
        stage_name="signal_extract",
        stage_report={"status": "succeeded", "report": {}},
        counters_by_company={"COMP-1": {"event_count": 0}},
        company_ids=["COMP-1"],
    ) == {"COMP-1": "llm_rejected"}
    assert cli._miss_reason_by_company(
        stage_name="source_product_extract",
        stage_report={"status": "succeeded", "report": {}},
        counters_by_company={"COMP-1": {"product_count": 0, "scenario_count": 0}},
        company_ids=["COMP-1"],
    ) == {"COMP-1": "synthesis_no_facts"}
    assert cli._miss_reason_by_company(
        stage_name="source_product_extract",
        stage_report={"status": "failed", "stderr_tail": "insert persist failed"},
        counters_by_company={},
        company_ids=["COMP-1"],
    ) == {"COMP-1": "persist_failed"}
    assert cli._miss_reason_by_company(
        stage_name="news_iyiou",
        stage_report={"status": "failed", "stderr_tail": "timeout"},
        counters_by_company={},
        company_ids=["COMP-1"],
    ) == {"COMP-1": "fetch_failed"}
    assert cli._miss_reason_by_company(
        stage_name="source_product_extract",
        stage_report={"status": "failed", "stderr_tail": "JSON parse failed"},
        counters_by_company={},
        company_ids=["COMP-1"],
    ) == {"COMP-1": "llm_structured_output_failed"}


def test_run_stage_shard_retries_transient_failure_and_preserves_attempt_audit(
    monkeypatch,
) -> None:
    cli = _import_cli()
    attempts: list[tuple[str, list[str]]] = []

    reports = [
        {
            "name": "generic_source_judgment",
            "status": "failed",
            "returncode": 1,
            "stderr_tail": "temporary timeout from provider",
            "report": {},
        },
        {
            "name": "generic_source_judgment",
            "status": "succeeded",
            "returncode": 0,
            "report": {"queries_run": 1, "accepted_sources": 1},
        },
    ]

    def fake_run_command(name, command, dsn):
        attempts.append((name, command))
        return reports.pop(0)

    monkeypatch.setattr(cli, "_run_command", fake_run_command)

    policy = cli._effective_stage_policy(
        "generic_source_judgment",
        stage_retry_budget=1,
        retry_backoff_seconds=0,
    )
    company_ids, _started_at, stage_report = cli._run_stage_shard(
        stage_name="generic_source_judgment",
        command_template=["python", "run_company_generic_source_judgment.py"],
        company_ids=["COMP-1"],
        dsn="postgresql://fake/test",
        shard_index=0,
        shard_count=1,
        policy=policy,
    )

    assert company_ids == ["COMP-1"]
    assert len(attempts) == 2
    assert stage_report["status"] == "succeeded"
    assert stage_report["attempts"] == 2
    assert stage_report["attempt_reports"][0]["failure_reason"] == "fetch_failed"
    assert stage_report["execution_policy"]["retry_budget"] == 1
    assert stage_report["execution_policy"]["llm_audit"]["task_type"] == "source_judgment"


def test_run_stage_shard_does_not_retry_non_retryable_json_failure(monkeypatch) -> None:
    cli = _import_cli()
    attempts: list[list[str]] = []

    def fake_run_command(name, command, dsn):
        attempts.append(command)
        return {
            "name": name,
            "status": "failed",
            "returncode": 1,
            "stderr_tail": "JSON parse failed in structured output",
            "report": {},
        }

    monkeypatch.setattr(cli, "_run_command", fake_run_command)

    policy = cli._effective_stage_policy(
        "source_product_extract",
        stage_retry_budget=3,
        retry_backoff_seconds=0,
    )
    _company_ids, _started_at, stage_report = cli._run_stage_shard(
        stage_name="source_product_extract",
        command_template=["python", "run_company_source_product_extract.py"],
        company_ids=["COMP-1"],
        dsn="postgresql://fake/test",
        shard_index=0,
        shard_count=1,
        policy=policy,
    )

    assert len(attempts) == 1
    assert stage_report["status"] == "failed"
    assert stage_report["attempts"] == 1
    assert stage_report["final_failure_reason"] == "llm_structured_output_failed"


def test_xlsx_stage_counters_include_baseline_product_synthesis() -> None:
    cli = _import_cli()

    counters = cli._stage_counters(
        "xlsx_team_synthesis",
        {
            "report": {
                "narratives_written": 0,
                "team_members_written": 0,
                "products_written": 2,
                "scenarios_written": 1,
            }
        },
    )

    assert counters["product_count"] == 2
    assert counters["scenario_count"] == 1
    assert (
        cli._non_search_stage_miss_reason(
            stage_name="xlsx_team_synthesis",
            counters=counters,
        )
        is None
    )


def test_stage_details_capture_synthesis_and_persistence_audit() -> None:
    cli = _import_cli()

    details = cli._stage_details(
        stage_name="source_product_extract",
        stage_report={
            "status": "succeeded",
            "returncode": 0,
            "report": {
                "source_adapters": ["iyiou", "pitchhub_36kr"],
                "news_processed": 3,
                "products_inserted": 2,
                "scenarios_inserted": 1,
                "llm_fallback_failed": 1,
                "dry_run": False,
            },
        },
    )

    assert details == {
        "synthesis_inputs": {
            "source_adapters": ["iyiou", "pitchhub_36kr"],
            "news_processed": 3,
        },
        "produced_facts": {
            "products": 2,
            "scenarios": 1,
        },
        "rejected_facts": {
            "llm_rejected_or_empty": 1,
        },
        "persistence_outcome": {
            "dry_run": False,
            "status": "succeeded",
            "returncode": 0,
        },
    }


def test_stage_details_capture_source_product_rejection_reasons() -> None:
    cli = _import_cli()

    details = cli._stage_details(
        stage_name="source_product_extract",
        stage_report={
            "status": "succeeded",
            "returncode": 0,
            "report": {
                "source_adapters": ["pitchhub_36kr"],
                "news_processed": 1,
                "products_inserted": 0,
                "scenarios_inserted": 0,
                "llm_fallback_failed": 0,
                "source_candidate_gate_rejected": 1,
                "rejected_candidate_reasons": {
                    "candidate belongs to another company": 1
                },
                "rejected_candidates": [
                    {
                        "news_id": "11111111-1111-1111-1111-111111111111",
                        "company_id": "COMP-QIDUO",
                        "source_adapter": "pitchhub_36kr",
                        "source_url": "https://pitchhub.36kr.com/project/1",
                        "gate": "product_candidate_attribution_gate",
                        "reason": "candidate belongs to another company",
                        "rejected_count": 1,
                    }
                ],
                "dry_run": False,
            },
        },
    )

    assert details["rejected_facts"] == {
        "llm_rejected_or_empty": 0,
        "candidate_gate_rejected": 1,
        "rejected_candidate_reasons": {
            "candidate belongs to another company": 1
        },
        "rejected_candidate_samples": [
            {
                "company_id": "COMP-QIDUO",
                "source_adapter": "pitchhub_36kr",
                "source_url": "https://pitchhub.36kr.com/project/1",
                "gate": "product_candidate_attribution_gate",
                "reason": "candidate belongs to another company",
                "rejected_count": 1,
            }
        ],
    }


def test_batch_summary_accumulates_source_product_rejection_reasons() -> None:
    cli = _import_cli()
    report: dict = {}

    cli._accumulate_stage_report(
        report,
        {
            "name": "source_product_extract",
            "status": "succeeded",
            "report": {
                "rejected_candidate_reasons": {
                    "candidate belongs to another company": 2,
                    "工商注册经营范围，不是具体产品或解决方案材料": 1,
                },
                "rejected_candidates": [
                    {
                        "reason": "candidate belongs to another company",
                        "rejected_count": 2,
                    },
                    {
                        "reason": "工商注册经营范围，不是具体产品或解决方案材料",
                        "rejected_count": 1,
                    },
                ],
            },
        },
    )

    assert report["summary"]["rejected_candidate_count"] == 3
    assert report["summary"]["rejected_candidate_reasons"] == {
        "candidate belongs to another company": 2,
        "工商注册经营范围，不是具体产品或解决方案材料": 1,
    }


def test_stage_details_capture_generic_react_audit() -> None:
    cli = _import_cli()

    details = cli._stage_details(
        stage_name="generic_source_judgment",
        stage_report={
            "status": "succeeded",
            "returncode": 0,
            "report": {
                "queries_run": 2,
                "results_seen": 5,
                "snippet_judgments": 5,
                "fetch_count": 2,
                "source_judgments": 7,
                "accepted_sources": 1,
                "rejected_sources": 4,
                "needs_review_sources": 1,
                "search_audit_rows": 2,
                "dry_run": False,
            },
        },
    )

    assert details["source_discovery"] == {
        "query_count": 2,
        "result_count": 5,
        "snippet_judgments": 5,
        "fetch_attempts": 2,
        "source_judgments": 7,
        "accepted_source_material": 1,
        "rejected_source_material": 4,
        "needs_review_source_material": 1,
        "search_audit_rows": 2,
    }
    assert details["persistence_outcome"] == {
        "dry_run": False,
        "status": "succeeded",
        "returncode": 0,
    }


def test_stage_details_include_policy_and_llm_outcome_without_secrets() -> None:
    cli = _import_cli()
    policy = cli._effective_stage_policy("source_product_extract")

    details = cli._stage_details(
        stage_name="source_product_extract",
        stage_report={
            "status": "failed",
            "returncode": 1,
            "stderr_tail": "JSON parse failed",
            "attempts": 1,
            "final_failure_reason": "llm_structured_output_failed",
            "execution_policy": policy.to_report_dict(),
            "report": {
                "source_adapters": ["generic_web"],
                "news_processed": 1,
                "llm_fallback_failed": 1,
            },
        },
    )

    assert details["execution_policy"]["llm_audit"] == {
        "task_type": "generic_product_admission",
        "llm_profile": "deepseek-v4-pro",
        "model": "deepseek-v4-pro",
        "cascade_strategy": "direct",
    }
    assert details["llm_task_outcome"] == {
        "task_type": "generic_product_admission",
        "llm_profile": "deepseek-v4-pro",
        "model": "deepseek-v4-pro",
        "attempts": 1,
        "json_repair_retry": True,
        "failure_reason": "llm_structured_output_failed",
        "structured_output_failures": 1,
    }
    rendered = str(details).casefold()
    assert "api_key" not in rendered
    assert "sk-" not in rendered
