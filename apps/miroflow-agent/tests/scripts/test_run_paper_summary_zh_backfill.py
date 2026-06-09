from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_paper_summary_zh_backfill.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_summary_zh_backfill", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_paper_summary_zh_backfill.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--only-missing" in captured.out
    assert "--all" in captured.out
    assert "--dry-run" in captured.out
    assert "--institution" in captured.out


def test_build_select_sql_only_missing_default():
    cli = _import_cli()
    args = cli._parse_args([])
    sql, params = cli._build_select_sql(
        only_missing=args.only_missing,
        limit=5,
        professor_ids=(),
        paper_ids=(),
        include_doi_enrichment=False,
    )

    assert args.only_missing is True
    assert "p.abstract_clean IS NOT NULL" in sql
    assert "p.summary_zh IS NULL" in sql
    assert params == (5,)


def test_build_select_sql_all_disables_summary_filter():
    cli = _import_cli()
    args = cli._parse_args(["--all"])
    sql, _params = cli._build_select_sql(
        only_missing=args.only_missing,
        limit=None,
        professor_ids=(),
        paper_ids=(),
        include_doi_enrichment=False,
    )

    assert "p.summary_zh IS NULL" not in sql


def test_build_select_sql_can_scope_to_professor_and_doi_enrichment():
    cli = _import_cli()
    sql, params = cli._build_select_sql(
        only_missing=True,
        limit=10,
        professor_ids=("PROF-1",),
        paper_ids=(),
        include_doi_enrichment=True,
    )

    assert "JOIN professor_paper_link ppl" in sql
    assert "p.doi IS NOT NULL" in sql
    assert "p.arxiv_id IS NOT NULL" in sql
    assert "p.arxiv_id" in sql
    assert "p.abstract_clean IS NOT NULL" in sql
    assert "ppl.professor_id = ANY(%s)" in sql
    assert params == (["PROF-1"], 10)


def test_build_select_sql_can_scope_to_institution():
    cli = _import_cli()
    sql, params = cli._build_select_sql(
        only_missing=True,
        limit=25,
        professor_ids=(),
        paper_ids=(),
        institutions=("清华大学深圳国际研究生院",),
        include_doi_enrichment=True,
    )

    compact_sql = " ".join(sql.split())
    assert "JOIN professor_paper_link ppl" in compact_sql
    assert "JOIN professor_affiliation pa ON pa.professor_id = ppl.professor_id" in compact_sql
    assert "pa.institution = ANY(%s)" in compact_sql
    assert "p.doi IS NOT NULL" in compact_sql
    assert params == (["清华大学深圳国际研究生院"], 25)


def test_build_select_sql_can_combine_institution_and_professor_ids():
    cli = _import_cli()
    sql, params = cli._build_select_sql(
        only_missing=True,
        limit=None,
        professor_ids=("PROF-1", "PROF-2"),
        paper_ids=(),
        institutions=("清华大学深圳国际研究生院",),
        include_doi_enrichment=False,
    )

    compact_sql = " ".join(sql.split())
    assert "JOIN professor_paper_link ppl" in compact_sql
    assert "JOIN professor_affiliation pa ON pa.professor_id = ppl.professor_id" in compact_sql
    assert "ppl.professor_id = ANY(%s)" in compact_sql
    assert "pa.institution = ANY(%s)" in compact_sql
    assert params == (["清华大学深圳国际研究生院"], ["PROF-1", "PROF-2"])


def test_open_llm_client_disables_env_proxy(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, *, timeout, trust_env):
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["openai_kwargs"] = kwargs

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(Client=FakeHttpClient))
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(
        cli,
        "resolve_professor_llm_settings",
        lambda *_a, **_kw: {
            "local_llm_base_url": "http://127.0.0.1:1234/v1",
            "local_llm_api_key": "",
            "local_llm_model": "gemma-test",
        },
    )

    client, model, extra_body = cli._open_llm_client()

    assert isinstance(client, FakeOpenAI)
    assert model == "gemma-test"
    assert captured["trust_env"] is False
    assert captured["timeout"] == 90.0
    assert captured["openai_kwargs"]["api_key"] == "EMPTY"
    assert captured["openai_kwargs"]["http_client"] is not None
    assert extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_cli_dry_run_dispatches_without_paper_update(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "A paper",
            "title_raw": None,
            "abstract_clean": "This paper proposes a robust model for scientific discovery.",
            "summary_zh": None,
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any(isinstance(sql, str) and "UPDATE paper" in sql for sql in sqls)
    report = json.loads(capsys.readouterr().out)
    assert report["summaries_written"] == 1
    assert report["dry_run"] is True


def test_cli_boilerplate_summary_rejects_paper(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "A paper",
            "title_raw": None,
            "year": 2026,
            "venue": "NeurIPS",
            "authors_display": "A. Smith",
            "abstract_clean": "This paper proposes a robust model for discovery.",
            "summary_zh": None,
            "quality_status": "needs_enrichment",
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: True)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--limit", "1"]):
        cli.main()

    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 1
    sql, params = update_calls[0]
    assert "summary_zh = NULL" in " ".join(sql.split())
    assert "quality_status = %s" in sql
    assert params[0] == "rejected"
    report = json.loads(capsys.readouterr().out)
    assert report["summaries_rejected"] == 1
    assert report["summaries_written"] == 0


def test_cli_successful_summary_promotes_paper_status(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "A paper",
            "title_raw": None,
            "year": 2026,
            "venue": "NeurIPS",
            "authors_display": "A. Smith",
            "abstract_clean": "This paper proposes a robust model for discovery.",
            "summary_zh": None,
            "quality_status": "needs_enrichment",
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--limit", "1"]):
        cli.main()

    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 1
    sql, params = update_calls[0]
    assert "summary_zh = %s" in sql
    assert "quality_status = %s" in sql
    assert params[0] == "中" * 220
    assert params[1] == "ready"
    report = json.loads(capsys.readouterr().out)
    assert report["summaries_written"] == 1
    assert report["summaries_rejected"] == 0


def test_cli_enriches_doi_metadata_before_summary(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "A paper",
            "title_raw": None,
            "doi": "10.1234/example",
            "year": 2026,
            "venue": "NeurIPS",
            "authors_display": "A. Smith",
            "abstract_clean": None,
            "summary_zh": None,
            "quality_status": "needs_enrichment",
            "citation_count": None,
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        cli,
        "enrich_paper_with_hybrid_sources",
        lambda _doi, **_kwargs: cli.PaperMetadataEnrichment(
            abstract="Enriched abstract.",
            citation_count=12,
            enrichment_sources=("openalex",),
        ),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        [
            "run_paper_summary_zh_backfill.py",
            "--enrich-doi-metadata",
            "--professor-id",
            "PROF-1",
            "--limit",
            "1",
        ]
    ):
        cli.main()

    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE" in metadata_sql
    assert metadata_sql.count("citation_count = COALESCE") == 1
    assert metadata_params[0] == "Enriched abstract."
    assert metadata_params[3] == 12
    assert metadata_params[4] == "partial"
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "ready"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enrichment_attempted"] == 1
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 1


def test_cli_enriches_arxiv_metadata_before_summary(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-ARXIV",
            "title_clean": "An arXiv paper",
            "title_raw": None,
            "doi": None,
            "arxiv_id": "2401.00001",
            "year": 2026,
            "venue": None,
            "authors_display": "A. Smith",
            "abstract_clean": None,
            "summary_zh": None,
            "quality_status": "needs_enrichment",
            "citation_count": None,
        }
    ]
    conn.execute.return_value = select_cursor
    seen: dict[str, object] = {}

    def fake_enrich(doi: str | None, **kwargs):
        seen["doi"] = doi
        seen.update(kwargs)
        return cli.PaperMetadataEnrichment(
            abstract="Abstract from arXiv.",
            venue="arXiv",
            enrichment_sources=("arxiv",),
        )

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setattr(cli, "enrich_paper_with_hybrid_sources", fake_enrich)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        [
            "run_paper_summary_zh_backfill.py",
            "--enrich-doi-metadata",
            "--limit",
            "1",
        ]
    ):
        cli.main()

    assert seen == {"doi": None, "arxiv_id": "2401.00001"}
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE" in metadata_sql
    assert metadata_params[0] == "Abstract from arXiv."
    assert metadata_params[1] == "arXiv"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enrichment_attempted"] == 1
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 1


def test_cli_identifier_contradiction_files_issue_and_blocks_ready(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-CONFLICT",
            "title_clean": "Conflicting identifiers",
            "title_raw": None,
            "doi": "10.1234/canonical",
            "arxiv_id": "2401.00001",
            "year": 2026,
            "venue": "NeurIPS",
            "authors_display": "A. Smith",
            "abstract_clean": None,
            "summary_zh": None,
            "quality_status": "needs_enrichment",
            "citation_count": None,
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        cli,
        "enrich_paper_with_hybrid_sources",
        lambda _doi, **_kwargs: cli.PaperMetadataEnrichment(
            abstract="Enriched abstract.",
            enrichment_sources=("crossref",),
            identifier_contradictions=(
                cli.PaperIdentifierContradiction(
                    identifier_type="doi",
                    canonical_value="10.1234/canonical",
                    source_value="10.1234/conflicting",
                    source="crossref",
                ),
            ),
        ),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        [
            "run_paper_summary_zh_backfill.py",
            "--enrich-doi-metadata",
            "--limit",
            "1",
        ]
    ):
        cli.main()

    issue_calls = [
        call
        for call in conn.execute.call_args_list
        if call.args
        and isinstance(call.args[0], str)
        and "INSERT INTO pipeline_issue" in call.args[0]
    ]
    assert len(issue_calls) == 1
    assert "'paper_quality'" in issue_calls[0].args[0]
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "quality_status = %s" in metadata_sql
    assert metadata_params[4] == "needs_review"
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "needs_review"
    report = json.loads(capsys.readouterr().out)
    assert report["identifier_contradictions"] == 1
    assert report["summaries_written"] == 1


def test_cli_skips_already_chinese_abstract(monkeypatch, tmp_path):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "中文论文",
            "title_raw": None,
            "abstract_clean": "本文提出一种用于智能制造质量检测的深度学习方法，能够提升缺陷识别准确率。",
            "summary_zh": None,
        }
    ]
    conn.execute.return_value = select_cursor
    translator = MagicMock()
    checkpoint = tmp_path / "run.jsonl"

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: checkpoint
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", translator)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    translator.assert_not_called()
    rows = [
        json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [{"paper_id": "PAPER-1", "status": "skipped_already_zh"}]


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_paper_summary_zh_backfill.py", "--limit", "1"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code != 0


class _patch_argv:
    def __init__(self, argv):
        self.argv = argv
        self._saved = None

    def __enter__(self):
        self._saved = sys.argv
        sys.argv = self.argv
        return self

    def __exit__(self, *exc):
        sys.argv = self._saved
