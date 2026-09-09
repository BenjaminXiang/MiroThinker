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


def _patent_row(**overrides) -> dict:
    defaults = {
        "patent_id": "PAT-001",
        "patent_number": "CN123",
        "title_clean": "Autonomous obstacle avoidance",
        "abstract_clean": "A method for drone navigation.",
        "technology_effect": "Improves navigation safety.",
        "patent_type": "invention",
        "ipc_codes": ["G05D", "B64U"],
    }
    defaults.update(overrides)
    return defaults


def test_backfill_patent_domain_writes_payload():
    cli = _import_cli_module()
    conn = _fake_pg_conn_returning([_patent_row()])
    milvus = MagicMock()
    milvus.has_collection.return_value = True
    embed = MagicMock()
    embed.embed_batch.side_effect = lambda texts: [[0.2] * 4096 for _ in texts]

    report = cli._backfill_patent_domain(conn, milvus, embed, batch_size=4)

    assert report["patents_total"] == 1
    assert report["patents_processed"] == 1
    assert report["patents_with_errors"] == 0
    payload = milvus.upsert.call_args.kwargs["data"][0]
    assert milvus.upsert.call_args.kwargs["collection_name"] == "patent_profiles"
    assert payload["id"] == "PAT-001"
    assert payload["ipc_codes"] == '["G05D", "B64U"]'
    assert payload["profile_vector"] == [0.2] * 4096


def test_backfill_patent_domain_skips_empty_semantic_text():
    cli = _import_cli_module()
    conn = _fake_pg_conn_returning(
        [_patent_row(title_clean="", abstract_clean="", technology_effect="")]
    )
    milvus = MagicMock()
    milvus.has_collection.return_value = True
    embed = MagicMock()

    report = cli._backfill_patent_domain(conn, milvus, embed)

    assert report["patents_total"] == 1
    assert report["patents_processed"] == 0
    assert report["patents_skipped"] == 1
    embed.embed_batch.assert_not_called()
    milvus.upsert.assert_not_called()


def test_cli_dispatches_patent_domain(monkeypatch):
    cli = _import_cli_module()
    called: list[dict] = []

    def _fake_patent(conn, milvus, embed, **kwargs):
        called.append(kwargs)
        return {"patents_total": 0, "patents_processed": 0}

    monkeypatch.setattr(cli, "_backfill_patent_domain", _fake_patent)
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
            "patent",
            "--limit",
            "3",
            "--batch-size",
            "2",
        ],
    )

    assert cli.main() == 0
    assert called[0]["limit"] == 3
    assert called[0]["batch_size"] == 2


def test_cli_patent_dry_run_outputs_expected_json(monkeypatch, capsys):
    cli = _import_cli_module()
    monkeypatch.setattr(sys, "argv", ["run_milvus_backfill.py", "--domain", "patent", "--dry-run"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["collection"] == "patent_profiles"
    assert "profile_vector" in payload["expected_fields"]
    assert "ipc_codes" in payload["missing_fields"]
