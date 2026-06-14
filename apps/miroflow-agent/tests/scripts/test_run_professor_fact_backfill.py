from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.data_agents.professor.fact_backfill import (
    ExtractedProfessorFact,
    ProfessorFactExtractionResult,
    ProfessorFactPersistenceReport,
)
from src.data_agents.professor.summary_reinforcement import ReinforcementResult

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_professor_fact_backfill.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_fact_backfill", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeConn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def execute(self, *_args, **_kwargs):
        cursor = MagicMock()
        cursor.fetchall.return_value = self.rows
        return cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _args(**overrides):
    defaults = {
        "database_url": "postgresql://fake/test",
        "limit": 10,
        "professor_id": None,
        "dry_run": False,
        "skip_re_eval": False,
        "min_summary_length": 150,
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _row(professor_id: str, *, raw_text: str, summary: str | None = None):
    return {
        "professor_id": professor_id,
        "canonical_name": f"{professor_id} Name",
        "institution": "深圳大学",
        "research_directions": ["机器人"],
        "profile_summary": summary,
        "profile_raw_text": raw_text,
        "primary_official_profile_page_id": "11111111-1111-1111-1111-111111111111",
    }


def _fact(professor_id: str) -> ExtractedProfessorFact:
    return ExtractedProfessorFact(
        professor_id=professor_id,
        fact_type="education",
        value_raw="清华大学博士",
        value_normalized="清华大学博士",
        evidence_span="清华大学博士",
        confidence=0.91,
        source_profile_raw_text_len=42,
    )


def test_build_select_sql_uses_non_empty_profile_raw_text_filter() -> None:
    cli = _import_cli()

    sql, params = cli._build_select_sql(limit=5, professor_ids=("PROF-1",))

    assert "p.profile_raw_text IS NOT NULL" in sql
    assert "length(trim(p.profile_raw_text)) > 0" in sql
    assert "p.professor_id = ANY(%s)" in sql
    assert params == (["PROF-1"], 5)


def test_run_backfill_processes_facts_summary_and_re_eval(monkeypatch) -> None:
    cli = _import_cli()
    conn = FakeConn([_row("PROF-1", raw_text="同一段 profile raw text")])
    extract = MagicMock(
        return_value=ProfessorFactExtractionResult(facts=(_fact("PROF-1"),))
    )
    persist = MagicMock(
        return_value=ProfessorFactPersistenceReport(facts_written=1, facts_updated=0)
    )
    summary = MagicMock(
        return_value=ReinforcementResult(
            summary="教授围绕机器人开展研究。" * 10,
            source_paper_count=0,
            error=None,
        )
    )
    persist_summary = MagicMock()
    re_eval = MagicMock(return_value={"evaluated": 1, "written": 1})

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "RUN-1")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli,
        "compute_fact_backfill_preflight",
        lambda _conn: SimpleNamespace(skipped_no_profile_raw_text_count=2),
    )
    monkeypatch.setattr(cli, "extract_professor_facts", extract)
    monkeypatch.setattr(cli, "persist_extracted_professor_facts", persist)
    monkeypatch.setattr(cli, "generate_reinforced_profile_summary", summary)
    monkeypatch.setattr(cli, "_persist_summary", persist_summary)
    monkeypatch.setattr(cli, "run_re_eval", re_eval)

    report = cli.run_backfill(_args())

    assert report["processed"] == 1
    assert report["skipped"] == 2
    assert report["failed"] == 0
    assert report["facts_written"] == 1
    assert report["summaries_written"] == 1
    assert report["re_evaluated"] == 1
    extract_kwargs = extract.call_args.kwargs
    summary_kwargs = summary.call_args.kwargs
    assert extract_kwargs["profile_raw_text"] == "同一段 profile raw text"
    assert summary_kwargs["bio"] == "同一段 profile raw text"
    persist.assert_called_once()
    persist_summary.assert_called_once()
    re_eval.assert_called_once()


def test_run_backfill_isolates_per_professor_failures(monkeypatch) -> None:
    cli = _import_cli()
    conn = FakeConn(
        [
            _row("PROF-ERR", raw_text="bad raw"),
            _row("PROF-OK", raw_text="good raw"),
        ]
    )

    def extract_side_effect(**kwargs):
        if kwargs["professor_id"] == "PROF-ERR":
            raise RuntimeError("extract down")
        return ProfessorFactExtractionResult(facts=(_fact("PROF-OK"),))

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "RUN-1")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli,
        "compute_fact_backfill_preflight",
        lambda _conn: SimpleNamespace(skipped_no_profile_raw_text_count=0),
    )
    monkeypatch.setattr(cli, "extract_professor_facts", MagicMock(side_effect=extract_side_effect))
    monkeypatch.setattr(
        cli,
        "persist_extracted_professor_facts",
        MagicMock(return_value=ProfessorFactPersistenceReport(facts_written=1)),
    )
    monkeypatch.setattr(
        cli,
        "generate_reinforced_profile_summary",
        MagicMock(return_value=ReinforcementResult(summary="", source_paper_count=0, error=None)),
    )
    monkeypatch.setattr(cli, "run_re_eval", MagicMock(return_value={"evaluated": 1}))

    report = cli.run_backfill(_args())

    assert report["processed"] == 2
    assert report["failed"] == 1
    assert report["facts_written"] == 1
    assert conn.rollbacks == 1


def test_main_prints_json_report(monkeypatch, capsys) -> None:
    cli = _import_cli()
    monkeypatch.setattr(
        cli,
        "run_backfill",
        lambda _args: {"processed": 1, "facts_written": 1},
    )

    cli.main(["--dry-run", "--limit", "1"])

    assert json.loads(capsys.readouterr().out) == {
        "processed": 1,
        "facts_written": 1,
    }
