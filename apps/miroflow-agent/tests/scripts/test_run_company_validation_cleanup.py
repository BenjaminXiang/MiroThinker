from __future__ import annotations

from pathlib import Path
import sys


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_validation_cleanup.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_validation_cleanup", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row: dict[str, int] | None = None) -> None:
        self._row = row or {"affected": 0}

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> _Result:
        sql = " ".join(query.split())
        self.calls.append((sql, params))
        if "FROM company_enrichment_search_audit" in sql:
            return _Result({"affected": 7})
        if "FROM company_enrichment_company_state" in sql:
            return _Result({"affected": 3})
        if "FROM company_enrichment_batch" in sql:
            return _Result({"affected": 1})
        return _Result({"affected": 0})


def test_cleanup_dry_run_reports_counts_without_mutation() -> None:
    cli = _import_cli()
    conn = _Conn()

    report = cli.cleanup_company_validation_batch(
        conn,
        batch_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        apply=False,
    )

    assert report["dry_run"] is True
    assert report["affected"] == {
        "company_enrichment_search_audit": 7,
        "company_enrichment_company_state": 3,
        "company_enrichment_batch": 1,
    }
    assert report["protected_tables_not_touched"] == [
        "company",
        "company_snapshot",
        "company_news_item",
        "company_signal_event",
        "company_product",
        "company_product_evidence",
        "company_application_scenario",
        "company_application_scenario_evidence",
        "milvus_company_profiles",
    ]
    mutating_sql = [
        sql
        for sql, _params in conn.calls
        if sql.startswith(("DELETE", "UPDATE", "TRUNCATE"))
    ]
    assert mutating_sql == []


def test_cleanup_apply_resets_only_batch_state_and_search_audit() -> None:
    cli = _import_cli()
    conn = _Conn()

    report = cli.cleanup_company_validation_batch(
        conn,
        batch_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        apply=True,
    )

    assert report["dry_run"] is False
    sql_text = "\n".join(sql for sql, _params in conn.calls)
    assert "DELETE FROM company_enrichment_search_audit" in sql_text
    assert "UPDATE company_enrichment_company_state" in sql_text
    assert "UPDATE company_enrichment_batch" in sql_text
    forbidden_fragments = (
        "DELETE FROM company_news_item",
        "DELETE FROM company_signal_event",
        "DELETE FROM company_product",
        "DELETE FROM company_application_scenario",
        "UPDATE company SET",
        "TRUNCATE",
    )
    assert not any(fragment in sql_text for fragment in forbidden_fragments)
