from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "run_milvus_backfill.py"


def _import_cli_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_milvus_backfill", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_pg_conn_returning(rows: list[dict]):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn.execute.return_value = cursor
    return conn


def _company_row(**overrides) -> dict:
    defaults = {
        "company_id": "COMP-001",
        "canonical_name": "Example Robotics",
        "industry": "AI",
        "hq_city": "Shenzhen",
        "description": "Builds autonomy systems for drones.",
        "profile_summary": None,
        "technology_route_summary": None,
    }
    defaults.update(overrides)
    return defaults


def test_backfill_company_domain_writes_payload():
    cli = _import_cli_module()
    conn = _fake_pg_conn_returning([_company_row()])
    milvus = MagicMock()
    milvus.has_collection.return_value = True
    embed = MagicMock()
    embed.embed_batch.side_effect = lambda texts: [[0.1] * 4096 for _ in texts]

    report = cli._backfill_company_domain(conn, milvus, embed, batch_size=4)

    assert report["companies_total"] == 1
    assert report["companies_processed"] == 1
    assert report["companies_with_errors"] == 0
    payload = milvus.upsert.call_args.kwargs["data"][0]
    assert milvus.upsert.call_args.kwargs["collection_name"] == "company_profiles"
    assert payload["id"] == "COMP-001"
    assert payload["description"] == "Builds autonomy systems for drones."
    assert payload["profile_vector"] == [0.1] * 4096


def test_backfill_company_domain_uses_latest_snapshot_join_and_inactive_filter():
    cli = _import_cli_module()
    conn = _fake_pg_conn_returning([])
    milvus = MagicMock()
    milvus.has_collection.return_value = True
    embed = MagicMock()

    cli._backfill_company_domain(
        conn,
        milvus,
        embed,
        limit=5,
        resume_ids={"COMP-skip"},
    )

    sql = conn.execute.call_args.args[0]
    params = conn.execute.call_args.args[1]
    assert "company_snapshot" in sql
    assert "identity_status != 'inactive'" in sql
    assert "company_id NOT IN" in sql
    assert params == ["COMP-skip", 5]


def test_backfill_company_domain_counts_embedding_errors():
    cli = _import_cli_module()
    conn = _fake_pg_conn_returning([_company_row(), _company_row(company_id="COMP-002")])
    milvus = MagicMock()
    milvus.has_collection.return_value = True
    embed = MagicMock()
    embed.embed_batch.side_effect = RuntimeError("embedding down")

    report = cli._backfill_company_domain(conn, milvus, embed)

    assert report["companies_processed"] == 0
    assert report["companies_with_errors"] == 2
    milvus.upsert.assert_not_called()


def test_cli_dispatches_company_domain(monkeypatch):
    cli = _import_cli_module()
    called: list[dict] = []

    def _fake_company(conn, milvus, embed, **kwargs):
        called.append(kwargs)
        return {"companies_total": 0, "companies_processed": 0}

    monkeypatch.setattr(cli, "_backfill_company_domain", _fake_company)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_milvus_backfill.py",
            "--domain",
            "company",
            "--limit",
            "2",
            "--batch-size",
            "1",
        ],
    )

    assert cli.main() == 0
    assert called[0]["limit"] == 2
    assert called[0]["batch_size"] == 1


def test_cli_company_dry_run_outputs_expected_json(monkeypatch, capsys):
    cli = _import_cli_module()
    monkeypatch.setattr(sys, "argv", ["run_milvus_backfill.py", "--domain", "company", "--dry-run"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["collection"] == "company_profiles"
    assert "profile_vector" in payload["expected_fields"]
    assert "technology_route_summary" in payload["missing_fields"]
