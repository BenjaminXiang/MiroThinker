"""Tests for the data recollection validation runbook CLI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_data_recollection_validation.py"
)


def _import_cli_module():
    spec = importlib.util.spec_from_file_location(
        "run_data_recollection_validation", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self):
        self.statements: list[tuple[str, tuple | None]] = []
        self.table_counts = {"paper": 7, "professor": 3}
        self.deleted_tables: list[str] = []

    def execute(self, sql, params=None):
        sql_text = str(sql)
        params_tuple = tuple(params or ())
        self.statements.append((sql_text, params_tuple))

        if "current_database()" in sql_text:
            return _FakeResult(
                {
                    "database_name": "unit_test_db",
                    "database_user": "tester",
                    "server_addr": "127.0.0.1",
                    "server_port": 5432,
                }
            )
        if "to_regclass" in sql_text:
            table = params_tuple[0].split(".")[-1]
            exists = table in self.table_counts or table == "alembic_version"
            return _FakeResult({"exists": f"public.{table}" if exists else None})
        if "FROM alembic_version" in sql_text:
            return _FakeResult({"version_num": "V027"})
        if "count(*) AS row_count" in sql_text:
            table = sql_text.split('"')[1]
            return _FakeResult({"row_count": self.table_counts.get(table, 0)})
        if sql_text.startswith('DELETE FROM public."'):
            self.deleted_tables.append(sql_text.split('"')[1])
            return _FakeResult({"deleted": 1})
        return _FakeResult({})


def test_cli_help_lists_safe_subcommands(capsys):
    cli = _import_cli_module()

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "init-workspace" in captured.out
    assert "cleanup-preview" in captured.out
    assert "plan-batch" in captured.out
    assert "generate-report" in captured.out


def test_init_workspace_creates_expected_audit_files(tmp_path):
    cli = _import_cli_module()

    workspace = cli.create_run_workspace(tmp_path, run_id="unit-run")

    assert workspace.path == tmp_path / "unit-run"
    for filename in [
        "environment.md",
        "cleanup-preview.json",
        "batch-plan.json",
        "validation-report.md",
        "verification.md",
    ]:
        assert (workspace.path / filename).exists()


def test_cleanup_preview_defaults_to_dry_run_and_does_not_delete():
    cli = _import_cli_module()
    conn = _FakeConn()

    preview = cli.build_cleanup_preview(conn, tables=("paper",), destructive=False)
    cli.execute_cleanup(conn, preview, destructive=False, confirm_database=None)

    payload = preview.to_dict()
    assert payload["dry_run"] is True
    assert payload["destructive"] is False
    assert payload["database"]["database_name"] == "unit_test_db"
    assert payload["alembic_revision"] == "V027"
    assert payload["tables"][0]["table"] == "paper"
    assert payload["tables"][0]["row_count"] == 7
    assert conn.deleted_tables == []


def test_destructive_cleanup_requires_matching_database_confirmation():
    cli = _import_cli_module()
    conn = _FakeConn()
    preview = cli.build_cleanup_preview(conn, tables=("paper",), destructive=True)

    with pytest.raises(cli.CleanupSafetyError, match="confirm-database"):
        cli.execute_cleanup(conn, preview, destructive=True, confirm_database=None)

    with pytest.raises(cli.CleanupSafetyError, match="unit_test_db"):
        cli.execute_cleanup(
            conn,
            preview,
            destructive=True,
            confirm_database="wrong_db",
        )


def test_destructive_cleanup_deletes_only_allowed_tables_with_confirmation():
    cli = _import_cli_module()
    conn = _FakeConn()
    preview = cli.build_cleanup_preview(conn, tables=("paper",), destructive=True)

    result = cli.execute_cleanup(
        conn,
        preview,
        destructive=True,
        confirm_database="unit_test_db",
    )

    assert result["deleted_tables"] == ["paper"]
    assert conn.deleted_tables == ["paper"]


def test_destructive_cleanup_uses_fk_safe_delete_order():
    cli = _import_cli_module()
    conn = _FakeConn()
    conn.table_counts = {table: 1 for table in cli.DEFAULT_CLEANUP_TABLES}
    preview = cli.build_cleanup_preview(conn, destructive=True)

    cli.execute_cleanup(
        conn,
        preview,
        destructive=True,
        confirm_database="unit_test_db",
    )

    assert conn.deleted_tables.index("pipeline_issue") < conn.deleted_tables.index(
        "professor"
    )
    assert conn.deleted_tables.index("pipeline_issue") < conn.deleted_tables.index(
        "professor_paper_link"
    )
    assert conn.deleted_tables.index(
        "professor_paper_link"
    ) < conn.deleted_tables.index("paper")


def test_protected_tables_are_not_in_cleanup_scope():
    cli = _import_cli_module()

    assert "professor_seed" not in cli.DEFAULT_CLEANUP_TABLES
    assert "alembic_version" not in cli.DEFAULT_CLEANUP_TABLES
    assert "source_backfill" not in cli.DEFAULT_CLEANUP_TABLES


def test_batch_plan_requires_bound_or_sample_evidence(tmp_path):
    cli = _import_cli_module()

    with pytest.raises(cli.BatchPlanError, match="sample-limit"):
        cli.build_batch_plan(seed_ids=[1], sample_limit=None, full_run=False)

    with pytest.raises(cli.BatchPlanError, match="sample evidence"):
        cli.build_batch_plan(
            seed_ids=[1],
            sample_limit=None,
            full_run=True,
            sample_evidence_path=tmp_path / "missing-report.md",
        )

    evidence = tmp_path / "sample-report.md"
    evidence.write_text("sample pass\n", encoding="utf-8")
    plan = cli.build_batch_plan(
        seed_ids=[1, 2],
        sample_limit=None,
        full_run=True,
        sample_evidence_path=evidence,
    )
    assert plan.full_run is True
    assert plan.seed_ids == [1, 2]
    assert plan.sample_evidence_path == evidence


def test_cli_plan_batch_writes_json(tmp_path):
    cli = _import_cli_module()

    cli.main(
        [
            "plan-batch",
            "--workspace",
            str(tmp_path),
            "--seed-id",
            "10",
            "--seed-id",
            "11",
            "--sample-limit",
            "3",
        ]
    )

    payload = json.loads((tmp_path / "batch-plan.json").read_text(encoding="utf-8"))
    assert payload["full_run"] is False
    assert payload["seed_ids"] == [10, 11]
    assert payload["sample_limit"] == 3
    assert payload["commands"]["professor_seed_trigger"][0].endswith(
        "run_data_recollection_validation.py"
    )
    assert "paper_homepage_ingest" in payload["commands"]
    assert "patent_homepage_ingest" in payload["commands"]
    assert "paper_summary_backfill" in payload["commands"]
    assert "milvus_refresh" in payload["commands"]


def test_validation_report_contains_required_sections_and_incomplete_verdict():
    cli = _import_cli_module()

    report = cli.render_validation_report(
        {
            "seed_status": [{"status": "success", "count": 2}],
            "pipeline_issue_taxonomy": [{"issue_type": "fetch_blocked", "count": 1}],
            "professor_quality": [{"quality_status": "ready", "count": 1}],
            "fact_coverage": {"with_facts": 0, "total": 1},
            "profile_summary_coverage": {"with_summary": 1, "total": 1},
            "admin_actions": [{"action": "mark_ready", "count": 1}],
            "manual_override_checks": {"manual_override_column": "not_present"},
            "paper_link_evidence": [
                {
                    "evidence_source_type": "homepage_tier1",
                    "match_reason": "official_profile",
                    "count": 4,
                }
            ],
            "patent_link_evidence": [{"evidence_source_type": "homepage", "count": 0}],
            "title_only_patent_rows": {"count": 0},
            "paper_summary_readiness": {
                "with_summary_zh": 3,
                "ready_count": 1,
                "boilerplate_rejections": 1,
                "summary_length_avg": 120,
                "total": 5,
            },
            "milvus_refresh": {"status": "not_run"},
            "retrieval_sanity": [],
        }
    )

    for heading in [
        "Seed Status",
        "Pipeline Issue Taxonomy",
        "Professor Quality And Facts",
        "Professor-Paper And Patent Links",
        "Paper Summary Readiness",
        "Milvus Refresh And Retrieval Sanity",
        "Final Verdict",
    ]:
        assert f"## {heading}" in report
    assert "admin_actions" in report
    assert "manual_override_checks" in report
    assert "homepage_tier1" in report
    assert "boilerplate_rejections" in report
    assert "Code-path verdict: pass" in report
    assert "Data-readiness verdict: incomplete evidence" in report


def test_default_validation_snapshot_has_milvus_and_retrieval_skip_fields():
    cli = _import_cli_module()

    snapshot = cli.collect_validation_snapshot()

    assert snapshot["milvus_refresh"]["status"] == "not_run"
    assert "target_paper_ids" in snapshot["milvus_refresh"]
    assert "chunks_inserted" in snapshot["milvus_refresh"]
    assert "chunks_refreshed" in snapshot["milvus_refresh"]
    assert snapshot["milvus_refresh"]["skipped_reason"]
    assert "sample_queries" in snapshot["retrieval_sanity"]
    assert "top_k_results" in snapshot["retrieval_sanity"]
    assert snapshot["retrieval_sanity"]["skipped_reason"]
