from __future__ import annotations

from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "close_stale_pipeline_runs.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("close_stale_pipeline_runs", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_stale_run_update_sql_filters_age_kind_and_trigger() -> None:
    cli = _import_cli()

    sql, params = cli._build_stale_run_update_sql(
        older_than_minutes=30,
        run_kind="news_refresh",
        triggered_by="run_company_signal_extract",
        status="failed",
        dry_run=False,
    )

    assert "status = 'running'" in sql
    assert "started_at < now() - (%(older_than_minutes)s::text || ' minutes')::interval" in sql
    assert "run_kind = %(run_kind)s" in sql
    assert "triggered_by = %(triggered_by)s" in sql
    assert "UPDATE pipeline_run" in sql
    assert params["older_than_minutes"] == 30
    assert params["run_kind"] == "news_refresh"
    assert params["triggered_by"] == "run_company_signal_extract"
    assert params["status"] == "failed"


def test_build_stale_run_update_sql_dry_run_selects_without_update() -> None:
    cli = _import_cli()

    sql, _params = cli._build_stale_run_update_sql(
        older_than_minutes=10,
        run_kind=None,
        triggered_by=None,
        status="failed",
        dry_run=True,
    )

    assert sql.lstrip().startswith("SELECT")
    assert "UPDATE pipeline_run" not in sql
