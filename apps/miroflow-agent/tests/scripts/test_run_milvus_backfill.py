"""RED-phase tests for M3 Unit 3 — run_milvus_backfill.py CLI shell."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "run_milvus_backfill.py"


def _import_cli_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_milvus_backfill", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_exits_zero(capsys):
    with patch_argv(["run_milvus_backfill.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli_module()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--domain" in captured.out
    assert "--limit" in captured.out
    assert "--batch-size" in captured.out
    assert "--resume" in captured.out
    assert "--id" in captured.out
    assert "--paper-id" in captured.out
    assert "--paper-id-file" in captured.out
    assert "--changed-since" in captured.out


def test_cli_loads_app_env_file_on_import(monkeypatch):
    calls: list[Path | None] = []
    fake_dotenv = types.SimpleNamespace(
        load_dotenv=lambda path=None: calls.append(Path(path) if path else None)
    )
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    _import_cli_module()

    assert _SCRIPT_PATH.resolve().parents[1] / ".env" in calls


def test_cli_dispatches_paper_domain(monkeypatch, tmp_path):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_backfill(conn, milvus, embed, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(
            papers_total=0,
            papers_processed=0,
            papers_skipped=0,
            chunks_inserted=0,
            papers_with_errors=0,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_backfill)
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
            "paper",
            "--limit",
            "10",
            "--batch-size",
            "8",
            "--milvus-uri",
            ":memory:",
        ],
    )
    cli.main()
    assert called_kwargs.get("limit") == 10
    assert called_kwargs.get("batch_size") == 8


def test_cli_passes_paper_ids_and_changed_since_to_paper_backfill(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_backfill(conn, milvus, embed, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(
            papers_total=0,
            papers_processed=0,
            papers_skipped=0,
            chunks_inserted=0,
            papers_with_errors=0,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_backfill)
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
            "paper",
            "--paper-id",
            "PAPER-1",
            "--paper-id",
            "PAPER-2",
            "--changed-since",
            "2026-05-23T00:00:00Z",
            "--milvus-uri",
            ":memory:",
        ],
    )

    cli.main()

    assert called_kwargs["paper_ids"] == {"PAPER-1", "PAPER-2"}
    assert called_kwargs["changed_since"] == "2026-05-23T00:00:00Z"


def test_cli_passes_paper_ids_from_file_to_paper_backfill(monkeypatch, tmp_path):
    cli = _import_cli_module()
    paper_id_file = tmp_path / "paper-ids.jsonl"
    paper_id_file.write_text(
        "PAPER-TEXT\n"
        '{"paper_id": "PAPER-WRITTEN", "status": "written"}\n'
        '{"id": "PAPER-ID-FALLBACK"}\n'
        '{"paper_id": "PAPER-REJECTED", "status": "rejected"}\n'
        '{"paper_id": "PAPER-SKIPPED", "status": "skipped"}\n'
        '{"paper_id": "PAPER-ERROR", "status": "error"}\n'
        "\n"
    )
    called_kwargs: dict = {}

    def _fake_backfill(conn, milvus, embed, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(
            papers_total=0,
            papers_processed=0,
            papers_skipped=0,
            chunks_inserted=0,
            papers_with_errors=0,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_backfill)
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
            "paper",
            "--paper-id",
            "PAPER-CLI",
            "--paper-id-file",
            str(paper_id_file),
            "--milvus-uri",
            ":memory:",
        ],
    )

    cli.main()

    assert called_kwargs["paper_ids"] == {
        "PAPER-CLI",
        "PAPER-TEXT",
        "PAPER-WRITTEN",
        "PAPER-ID-FALLBACK",
    }


def test_cli_dispatches_professor_domain(monkeypatch):
    """--domain professor invokes professor backfill path (mocked)."""
    cli = _import_cli_module()
    # The professor backfill path is implementation-dependent. The test's contract
    # is merely that the CLI routes to a distinct handler for --domain professor
    # AND does not dispatch the paper backfill when domain=professor.
    paper_called = []

    def _fake_paper_backfill(*args, **kwargs):
        paper_called.append(1)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(0, 0, 0, 0, 0, 0.0)

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_paper_backfill)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    # Professor backfill dispatches to a function in the professor module;
    # patch a generic "_backfill_professor_domain" hook if present.
    if hasattr(cli, "_backfill_professor_domain"):
        prof_called = []

        def _fake_prof(*args, **kwargs):
            prof_called.append(1)
            from src.data_agents.paper.milvus_backfill import BackfillReport

            return BackfillReport(0, 0, 0, 0, 0, 0.0)

        monkeypatch.setattr(cli, "_backfill_professor_domain", _fake_prof)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_milvus_backfill.py",
            "--domain",
            "professor",
            "--milvus-uri",
            ":memory:",
        ],
    )
    cli.main()
    # Paper backfill must NOT have been called.
    assert paper_called == []


def test_cli_passes_professor_ids_to_professor_backfill(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_prof(*args, **kwargs):
        del args
        called_kwargs.update(kwargs)
        return {
            "profs_total": 0,
            "profs_processed": 0,
            "profs_skipped": 0,
            "profs_with_errors": 0,
            "duration_seconds": 0.0,
        }

    monkeypatch.setattr(cli, "_backfill_professor_domain", _fake_prof)
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
            "professor",
            "--id",
            "PROF-1",
            "--id",
            "PROF-2",
            "--milvus-uri",
            ":memory:",
        ],
    )

    cli.main()

    assert called_kwargs["include_ids"] == {"PROF-1", "PROF-2"}


def test_cli_domain_professor_defaults_to_split_collections(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_prof(*args, **kwargs):
        del args
        called_kwargs.update(kwargs)
        return {
            "profs_total": 0,
            "profs_processed": 0,
            "profs_skipped": 0,
            "profs_with_errors": 0,
            "collection_counts": {},
            "duration_seconds": 0.0,
        }

    monkeypatch.setattr(cli, "_backfill_professor_domain", _fake_prof)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_milvus_backfill.py", "--domain", "professor", "--milvus-uri", ":memory:"],
    )

    cli.main()

    assert called_kwargs["professor_collections"] == {
        "professor_identity_profiles",
        "professor_research_profiles",
    }


def test_cli_collection_can_select_professor_research_collection(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_prof(*args, **kwargs):
        del args
        called_kwargs.update(kwargs)
        return {
            "profs_total": 0,
            "profs_processed": 0,
            "profs_skipped": 0,
            "profs_with_errors": 0,
            "collection_counts": {},
            "duration_seconds": 0.0,
        }

    monkeypatch.setattr(cli, "_backfill_professor_domain", _fake_prof)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_milvus_backfill.py",
            "--collection",
            "professor_research_profiles",
            "--milvus-uri",
            ":memory:",
        ],
    )

    cli.main()

    assert called_kwargs["professor_collections"] == {"professor_research_profiles"}


def test_metric_int_normalizes_missing_values_for_milvus_lite():
    cli = _import_cli_module()

    assert cli._metric_int(None) == 0
    assert cli._metric_int(12) == 12


class _FakeRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[object]]] = []

    def execute(self, sql: str, params: list[object]):
        self.calls.append((sql, list(params)))
        return _FakeRows(self.rows)


class _FakeMilvus:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, object]] = []

    def has_collection(self, _collection_name: str) -> bool:
        return True

    def upsert(self, *, collection_name: str, data: list[dict[str, object]]) -> None:
        self.upsert_calls.append({"collection_name": collection_name, "data": data})


class _FakeEmbedding:
    def __init__(self) -> None:
        self.text_batches: list[list[str]] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.text_batches.append(list(texts))
        return [[0.1] * 4096 for _ in texts]


def _professor_row(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "professor_id": "PROF-1",
        "canonical_name": "张三",
        "canonical_name_en": "San Zhang",
        "institution": "南方科技大学",
        "department": "计算机系",
        "title": "教授",
        "profile_summary": "Focuses on embodied intelligence.",
        "profile_raw_text": "Raw profile text.",
        "research_directions": ["具身智能"],
        "paper_summary": "Papers study graph policies.",
        "patent_summary": "Patents cover force-control calibration.",
        "h_index": 12,
        "citation_count": 345,
        "paper_count": 34,
    }
    row.update(overrides)
    return row


def test_professor_backfill_can_write_identity_collection_only():
    cli = _import_cli_module()
    milvus = _FakeMilvus()
    embedding = _FakeEmbedding()

    report = cli._backfill_professor_domain(
        _FakeConn([_professor_row()]),
        milvus,
        embedding,
        batch_size=10,
        professor_collections={cli.PROFESSOR_IDENTITY_PROFILES_COLLECTION},
    )

    assert report["collection_counts"] == {
        "professor_identity_profiles": 1,
        "professor_research_profiles": 0,
        "professor_profiles": 0,
    }
    assert [call["collection_name"] for call in milvus.upsert_calls] == [
        "professor_identity_profiles"
    ]
    payload = milvus.upsert_calls[0]["data"][0]
    assert payload["identity_vector"] == [0.1] * 4096
    assert "张三" in payload["identity_text"]
    assert "Papers study graph policies" not in payload["identity_text"]


def test_professor_backfill_can_write_research_collection_only():
    cli = _import_cli_module()
    milvus = _FakeMilvus()
    embedding = _FakeEmbedding()

    report = cli._backfill_professor_domain(
        _FakeConn([_professor_row()]),
        milvus,
        embedding,
        batch_size=10,
        professor_collections={cli.PROFESSOR_RESEARCH_PROFILES_COLLECTION},
    )

    assert report["collection_counts"] == {
        "professor_identity_profiles": 0,
        "professor_research_profiles": 1,
        "professor_profiles": 0,
    }
    assert [call["collection_name"] for call in milvus.upsert_calls] == [
        "professor_research_profiles"
    ]
    payload = milvus.upsert_calls[0]["data"][0]
    assert payload["research_vector"] == [0.1] * 4096
    assert "Papers study graph policies" in payload["research_text"]
    assert "Patents cover force-control" in payload["research_text"]
    assert "南方科技大学" not in payload["research_text"]


def test_professor_backfill_selects_quality_status_for_split_payloads():
    cli = _import_cli_module()
    milvus = _FakeMilvus()
    embedding = _FakeEmbedding()
    conn = _FakeConn([_professor_row(quality_status="needs_enrichment")])

    cli._backfill_professor_domain(
        conn,
        milvus,
        embedding,
        batch_size=10,
        professor_collections={cli.PROFESSOR_IDENTITY_PROFILES_COLLECTION},
    )

    sql, _params = conn.calls[0]
    assert "p.quality_status" in sql
    payload = milvus.upsert_calls[0]["data"][0]
    assert payload["quality_status"] == "needs_enrichment"


def test_professor_backfill_dry_run_reports_collection_counts_without_writes():
    cli = _import_cli_module()
    milvus = _FakeMilvus()
    embedding = _FakeEmbedding()

    report = cli._backfill_professor_domain(
        _FakeConn([_professor_row()]),
        milvus,
        embedding,
        batch_size=10,
        dry_run=True,
        professor_collections={
            cli.PROFESSOR_IDENTITY_PROFILES_COLLECTION,
            cli.PROFESSOR_RESEARCH_PROFILES_COLLECTION,
        },
    )

    assert report["dry_run"] is True
    assert report["profs_total"] == 1
    assert report["profs_processed"] == 0
    assert report["collection_counts"] == {
        "professor_identity_profiles": 1,
        "professor_research_profiles": 1,
        "professor_profiles": 0,
    }
    assert milvus.upsert_calls == []
    assert embedding.text_batches == []


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_milvus_backfill.py", "--domain", "paper", "--milvus-uri", ":memory:"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0


def test_cli_resume_with_corrupt_line(monkeypatch, tmp_path):
    cli = _import_cli_module()
    ckpt = tmp_path / "resume.jsonl"
    ckpt.write_text(
        '{"paper_id": "p_ok"}\n'
        "not valid json\n"
        '{"paper_id": "p_ok2"}\n'
    )
    called_kwargs: dict = {}

    def _fake_backfill(conn, milvus, embed, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(0, 0, 0, 0, 0, 0.0)

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_backfill)
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
            "paper",
            "--milvus-uri",
            ":memory:",
            "--resume",
            str(ckpt),
        ],
    )
    cli.main()
    resume_ids = called_kwargs.get("resume_ids")
    assert resume_ids is not None
    assert "p_ok" in resume_ids
    assert "p_ok2" in resume_ids


class patch_argv:
    """Tiny context manager for setting sys.argv inside a `with` block."""

    def __init__(self, argv):
        self.argv = argv
        self._saved = None

    def __enter__(self):
        self._saved = sys.argv
        sys.argv = self.argv
        return self

    def __exit__(self, *exc):
        sys.argv = self._saved
