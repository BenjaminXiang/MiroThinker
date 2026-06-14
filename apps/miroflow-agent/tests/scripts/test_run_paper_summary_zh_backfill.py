from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.models import PaperAuthorMetadata

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
    assert "--seed-id" in captured.out
    assert "--paper-id-file" in captured.out
    assert "--worker-count" in captured.out
    assert "--worker-index" in captured.out


def test_cli_loads_app_env_file_on_import(monkeypatch):
    calls: list[Path] = []
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda path: calls.append(Path(path)))
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    _import_cli()

    assert calls == [_SCRIPT_PATH.resolve().parents[1] / ".env"]


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
    assert "LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id" in sql
    assert (
        "COALESCE(NULLIF(trim(p.abstract_clean), ''), "
        "NULLIF(trim(pft.abstract), ''), NULLIF(trim(pft.intro), ''))"
    ) in sql
    assert "p.summary_zh IS NULL" in sql
    assert params == (5,)


def test_build_select_sql_can_select_grounded_full_text_intro():
    cli = _import_cli()
    sql, _params = cli._build_select_sql(
        only_missing=True,
        limit=None,
        professor_ids=(),
        paper_ids=(),
        include_doi_enrichment=False,
    )

    assert "pft.intro AS full_text_intro" in sql
    assert "NULLIF(trim(pft.intro), '')" in sql


def test_build_select_sql_excludes_terminal_paper_states():
    cli = _import_cli()
    sql, _params = cli._build_select_sql(
        only_missing=True,
        limit=None,
        professor_ids=(),
        paper_ids=(),
        include_doi_enrichment=True,
    )

    compact_sql = " ".join(sql.split())
    assert "COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')" in compact_sql
    assert "COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'" in compact_sql


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
    assert "p.openalex_id IS NOT NULL" in sql
    assert "p.arxiv_id" in sql
    assert "p.openalex_id" in sql
    assert "ppl.professor_id = ANY(%s)" in sql
    assert "ppl.link_status = 'verified'" in sql
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
    assert "ppl.link_status = 'verified'" in compact_sql
    assert "pa.institution = ANY(%s)" in compact_sql
    assert "p.doi IS NOT NULL" in compact_sql
    assert params == (["清华大学深圳国际研究生院"], 25)


def test_build_select_sql_can_partition_work_by_worker_shard():
    cli = _import_cli()
    sql, params = cli._build_select_sql(
        only_missing=True,
        limit=25,
        professor_ids=(),
        paper_ids=(),
        institutions=("清华大学深圳国际研究生院",),
        worker_count=4,
        worker_index=2,
        include_doi_enrichment=True,
    )

    compact_sql = " ".join(sql.split())
    assert "mod(abs(hashtext(p.paper_id)), %s) = %s" in compact_sql
    assert params == (["清华大学深圳国际研究生院"], 4, 2, 25)


def test_parse_args_rejects_worker_index_outside_worker_count():
    cli = _import_cli()

    with pytest.raises(SystemExit):
        cli._parse_args(["--worker-count", "4", "--worker-index", "4"])


def test_build_select_sql_can_scope_to_latest_seed_run():
    cli = _import_cli()
    sql, params = cli._build_select_sql(
        only_missing=True,
        limit=10,
        professor_ids=(),
        paper_ids=(),
        institutions=(),
        seed_ids=("9",),
        include_doi_enrichment=False,
    )

    compact_sql = " ".join(sql.split())
    assert "latest_seed_run AS (" in compact_sql
    assert "pr.run_kind = 'roster_crawl'" in compact_sql
    assert "pr.run_scope->>'seed_id' = ANY(%s)" in compact_sql
    assert "(COALESCE(pr.run_scope->>'trigger_mode', '') = 'full') DESC" in compact_sql
    assert "JOIN seed_professors seed_scope ON seed_scope.professor_id = ppl.professor_id" in compact_sql
    assert "ppl.link_status = 'verified'" in compact_sql
    assert params == (["9"], 10)


def test_build_select_sql_can_scope_to_paper_ids_from_file(tmp_path):
    cli = _import_cli()
    paper_id_file = tmp_path / "paper-ids.txt"
    paper_id_file.write_text(
        "\n".join(
            [
                "PAPER-1",
                "  PAPER-2  ",
                "",
                "# comment",
                "PAPER-1",
            ]
        ),
        encoding="utf-8",
    )

    args = cli._parse_args(["--paper-id-file", str(paper_id_file)])

    assert args.paper_id == ["PAPER-1", "PAPER-2"]


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
    assert "ppl.link_status = 'verified'" in compact_sql
    assert "ppl.professor_id = ANY(%s)" in compact_sql
    assert "pa.institution = ANY(%s)" in compact_sql
    assert params == (["清华大学深圳国际研究生院"], ["PROF-1", "PROF-2"])


@pytest.mark.parametrize(
    "abstract",
    [
        (
            "With rapid advancements in single-cell RNA sequencing technologies, "
            "researchers can now map coordinated physiological processes across "
            "cell types and developmental stages with high resolution."
        ),
        (
            "To support air-ground integrated sensing and communication, this "
            "paper develops a network-level performance model and validates the "
            "analysis under realistic deployment assumptions."
        ),
        (
            "Based on foreign trade archives at the grassroots level, this "
            "article explains how market adaptation and containment shaped "
            "policy implementation during the 1960s and 1970s."
        ),
        (
            "For dual three-phase permanent magnet synchronous machines under "
            "open-phase fault, this study optimizes healthy phase currents and "
            "improves fault-tolerant control performance."
        ),
    ],
)
def test_usable_abstract_accepts_common_academic_opening_markers(abstract):
    cli = _import_cli()

    assert cli._is_usable_abstract(abstract)


@pytest.mark.parametrize(
    "fragment",
    [
        "and improves the model in later experiments",
        "or provides additional results without enough context",
        "but only after the missing previous clause is known",
    ],
)
def test_usable_abstract_rejects_short_leading_conjunction_fragments(fragment):
    cli = _import_cli()

    assert not cli._is_usable_abstract(fragment)


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


def test_abstract_for_summary_rejects_citation_metadata_and_uses_full_text():
    cli = _import_cli()
    row = {
        "abstract_clean": (
            "Xiaozhi Wang, Hao Peng, Yong Guan. Proceedings of the 62nd "
            "Annual Meeting of the Association for Computational Linguistics. 2024."
        ),
        "full_text_abstract": (
            "This paper introduces a concrete event extraction dataset with "
            "argument annotations, benchmark experiments, and detailed analysis "
            "of model performance across multiple event understanding tasks."
        ),
    }

    assert cli._abstract_for_summary(row) == (
        "This paper introduces a concrete event extraction dataset with "
        "argument annotations, benchmark experiments, and detailed analysis "
        "of model performance across multiple event understanding tasks."
    )
    assert row["abstract_for_summary_source"] == "paper_full_text.abstract"


def test_abstract_for_summary_rejects_venue_only_and_truncated_fragments():
    cli = _import_cli()

    assert (
        cli._abstract_for_summary(
            {
                "abstract_clean": (
                    "Optical Fiber Communication Conference 2018, San Diego, "
                    "California United States, 11-15 March 2018"
                ),
                "full_text_abstract": None,
            }
        )
        is None
    )
    assert (
        cli._abstract_for_summary(
            {
                "abstract_clean": (
                    "Subsea engineering structures are an evolutive system with "
                    "high diversity, e [...]"
                ),
                "full_text_abstract": None,
            }
        )
        is None
    )
    assert (
        cli._abstract_for_summary(
            {
                "abstract_clean": (
                    "and VOCs emissions reduction, to overcome the effects of "
                    "nonlinear photochemistry and aerosol chemical feedback."
                ),
                "full_text_abstract": None,
            }
        )
        is None
    )


def test_abstract_for_summary_rejects_author_affiliation_metadata():
    cli = _import_cli()
    row = {
        "abstract_clean": (
            "Jingfeng Huanga*, Daoyi Chenb & M. H. Coshc a Rosenstiel School "
            "of Marine and Atmospheric Science, University of Miami, Miami, FL "
            "33149-1031 b Department of Engineering, The University of Liverpool"
        ),
        "full_text_abstract": None,
    }

    assert cli._abstract_for_summary(row) is None


def test_summary_text_uses_full_text_intro_without_treating_it_as_abstract():
    cli = _import_cli()
    row = {
        "title_clean": "A source grounded paper",
        "year": 2024,
        "venue": "NeurIPS",
        "authors_display": "A. Smith",
        "abstract_clean": None,
        "full_text_abstract": None,
        "full_text_intro": (
            "This introduction motivates a source grounded research problem, "
            "summarizes the proposed method, outlines the experimental setup, "
            "and explains why the results matter for downstream applications."
        ),
    }

    assert cli._abstract_for_summary(row) == row["full_text_intro"]
    assert row["abstract_for_summary_source"] == "paper_full_text.intro"

    signals = cli._paper_enrichment_signals(
        row,
        summary_zh="这是一段中文解读。" * 30,
        summary_zh_boilerplate_rejected=False,
    )
    assert signals.has_summary_zh is True
    assert signals.has_abstract is False


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
    open_pipeline_run = MagicMock(return_value="11111111-1111-1111-1111-111111111111")
    close_pipeline_run = MagicMock()
    monkeypatch.setattr(cli, "open_pipeline_run", open_pipeline_run)
    monkeypatch.setattr(cli, "close_pipeline_run", close_pipeline_run)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any(isinstance(sql, str) and "UPDATE paper" in sql for sql in sqls)
    open_pipeline_run.assert_not_called()
    close_pipeline_run.assert_not_called()
    report = json.loads(capsys.readouterr().out)
    assert report["summaries_written"] == 1
    assert report["dry_run"] is True


def test_cli_boilerplate_summary_rejects_summary_without_rejecting_paper(
    monkeypatch,
    tmp_path,
    capsys,
):
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
    assert params[0] == "partial"
    report = json.loads(capsys.readouterr().out)
    assert report["summaries_rejected"] == 1
    assert report["summaries_written"] == 0


def test_cli_invalid_generated_summary_rejects_summary_without_rejecting_paper(
    monkeypatch,
    tmp_path,
    capsys,
):
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
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: None)
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
    assert params[0] == "partial"
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


def test_cli_enriches_missing_venue_even_when_abstract_is_present(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-MISSING-VENUE",
            "title_clean": "Adversarial Training Methods for Network Embedding",
            "title_raw": None,
            "doi": "10.1234/missing-venue",
            "arxiv_id": None,
            "openalex_id": "W123",
            "year": 2019,
            "venue": None,
            "authors_display": "A. Smith, B. Li",
            "abstract_clean": (
                "This paper studies adversarial training methods for network "
                "embedding, presents a robust optimization formulation, and "
                "evaluates the method on graph representation benchmarks."
            ),
            "summary_zh": None,
            "quality_status": "partial",
            "citation_count": None,
        }
    ]
    conn.execute.return_value = select_cursor
    seen: dict[str, object] = {}

    def fake_enrich(doi: str | None, **kwargs):
        seen["doi"] = doi
        seen.update(kwargs)
        return cli.PaperMetadataEnrichment(
            venue="ACM Transactions on Knowledge Discovery from Data",
            citation_count=21,
            enrichment_sources=("crossref",),
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

    assert seen == {
        "doi": "10.1234/missing-venue",
        "arxiv_id": None,
        "openalex_id": "W123",
    }
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "venue = COALESCE(venue, %s)" in metadata_sql
    assert metadata_params[1] == "ACM Transactions on Knowledge Discovery from Data"
    assert metadata_params[3] == 21
    assert metadata_params[5] == "partial"
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "ready"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enrichment_attempted"] == 1
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 1


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
            abstract=(
                "This enriched abstract describes a robust scientific model, "
                "reports benchmark results, and explains its downstream use cases."
            ),
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
    assert metadata_params[0] == (
        "This enriched abstract describes a robust scientific model, "
        "reports benchmark results, and explains its downstream use cases."
    )
    assert metadata_params[3] == 12
    assert metadata_params[4] is None
    assert metadata_params[5] == "partial"
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "ready"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enrichment_attempted"] == 1
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 1


def test_cli_does_not_persist_unusable_provider_abstract(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-BAD-ABSTRACT",
            "title_clean": "A paper with bad provider abstract",
            "title_raw": None,
            "doi": "10.1234/bad-abstract",
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
            abstract=",",
            citation_count=7,
            enrichment_sources=("openalex",),
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

    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 1
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE" in metadata_sql
    assert metadata_params[0] is None
    assert metadata_params[3] == 7
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 0
    assert report["papers_skipped"] == 1


def test_cli_enriches_missing_authors_from_metadata(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-AUTHORS",
            "title_clean": "A paper with missing authors",
            "title_raw": None,
            "doi": "10.1234/authors",
            "year": 2026,
            "venue": "NeurIPS",
            "authors_display": None,
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
            abstract=(
                "This enriched abstract describes a robust scientific model, "
                "reports benchmark results, and explains its downstream use cases."
            ),
            authors=(
                PaperAuthorMetadata(display_name="Alice Smith", source="crossref"),
                PaperAuthorMetadata(display_name="Bob Li", source="crossref"),
            ),
            enrichment_sources=("crossref",),
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

    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    metadata_sql, metadata_params = update_calls[0]
    assert "authors_display = COALESCE(authors_display" in metadata_sql
    assert metadata_params[4] == "Alice Smith, Bob Li"
    assert metadata_params[5] == "partial"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 1


def test_cli_enriches_doi_metadata_when_existing_abstract_is_citation_metadata(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-CITATION",
            "title_clean": "MAVEN-ARG",
            "title_raw": None,
            "doi": "10.18653/v1/2024.acl-long.224",
            "year": 2024,
            "venue": "ACL",
            "authors_display": "Xiaozhi Wang",
            "abstract_clean": (
                "Xiaozhi Wang, Hao Peng, Yong Guan. Proceedings of the 62nd "
                "Annual Meeting of the Association for Computational Linguistics. 2024."
            ),
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
            abstract=(
                "This paper introduces a large event argument annotation dataset, "
                "describes its construction protocol, and evaluates multiple "
                "baseline models on event understanding tasks."
            ),
            enrichment_sources=("crossref",),
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

    assert seen["doi"] == "10.18653/v1/2024.acl-long.224"
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE(%s, abstract_clean)" in metadata_sql
    assert metadata_params[0] == (
        "This paper introduces a large event argument annotation dataset, "
        "describes its construction protocol, and evaluates multiple "
        "baseline models on event understanding tasks."
    )
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
            abstract=(
                "This arXiv abstract describes a technical method, its experimental "
                "setup, and quantitative findings across benchmark datasets."
            ),
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

    assert seen == {"doi": None, "arxiv_id": "2401.00001", "openalex_id": None}
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE" in metadata_sql
    assert metadata_params[0] == (
        "This arXiv abstract describes a technical method, its experimental "
        "setup, and quantitative findings across benchmark datasets."
    )
    assert metadata_params[1] == "arXiv"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enrichment_attempted"] == 1
    assert report["metadata_enriched"] == 1
    assert report["summaries_written"] == 1


def test_cli_uses_enriched_pdf_url_when_metadata_has_no_abstract(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-PDF",
            "title_clean": "A DOI paper with an open PDF",
            "title_raw": None,
            "doi": "10.1234/pdf",
            "arxiv_id": None,
            "openalex_id": None,
            "year": 2026,
            "venue": "Example Journal",
            "authors_display": "A. Smith",
            "abstract_clean": None,
            "full_text_abstract": None,
            "summary_zh": None,
            "quality_status": "needs_enrichment",
            "citation_count": None,
        }
    ]
    conn.execute.return_value = select_cursor
    fetched: dict[str, object] = {}
    upserts: list[FullTextExtract] = []

    def fake_fetch_pdf_url_full_text(
        pdf_url: str,
        *,
        paper_id: str,
        source: str,
    ) -> FullTextExtract:
        fetched.update({"pdf_url": pdf_url, "paper_id": paper_id, "source": source})
        return FullTextExtract(
            paper_id=paper_id,
            abstract=(
                "This PDF abstract describes the research question,\x00 interaction "
                "design method, evaluation setup, and implications for mobile "
                "communication systems.\x1f"
            ),
            intro=None,
            pdf_url=pdf_url,
            pdf_sha256="abc123",
            source=source,
            fetch_error=None,
            pdf_byte_size=123,
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
    monkeypatch.setattr(
        cli,
        "enrich_paper_with_hybrid_sources",
        lambda _doi, **_kwargs: cli.PaperMetadataEnrichment(
            pdf_url="https://example.org/open.pdf",
            enrichment_sources=("semantic_scholar",),
        ),
    )
    monkeypatch.setattr(cli, "fetch_pdf_url_full_text", fake_fetch_pdf_url_full_text)
    monkeypatch.setattr(
        cli,
        "upsert_paper_full_text",
        lambda _conn, *, paper_id, extract, run_id: upserts.append(extract),
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

    assert fetched == {
        "pdf_url": "https://example.org/open.pdf",
        "paper_id": "PAPER-PDF",
        "source": "doi_pdf:semantic_scholar",
    }
    assert len(upserts) == 1
    assert upserts[0].abstract.startswith("This PDF abstract describes")
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE(%s, abstract_clean)" in metadata_sql
    assert metadata_params[0].startswith("This PDF abstract describes")
    assert "\x00" not in metadata_params[0]
    assert "\x1f" not in metadata_params[0]
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "ready"
    report = json.loads(capsys.readouterr().out)
    assert report["metadata_enrichment_attempted"] == 1
    assert report["metadata_enriched"] == 1
    assert report["full_text_enrichment_attempted"] == 1
    assert report["full_text_enriched"] == 1
    assert report["summaries_written"] == 1


def test_cli_uses_same_run_pdf_intro_without_persisting_as_abstract(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-PDF-INTRO",
            "title_clean": "A DOI paper with a useful PDF introduction",
            "title_raw": None,
            "doi": "10.1234/pdf-intro",
            "arxiv_id": None,
            "openalex_id": None,
            "year": 1980,
            "venue": "Example Journal",
            "authors_display": "A. Smith",
            "abstract_clean": None,
            "full_text_abstract": None,
            "full_text_intro": None,
            "summary_zh": None,
            "quality_status": "partial",
            "citation_count": None,
        }
    ]
    conn.execute.return_value = select_cursor
    checkpoint_path = tmp_path / "run.jsonl"
    translated: dict[str, str] = {}
    upserts: list[FullTextExtract] = []
    intro = (
        "This introduction motivates an elliptic equation problem, explains the "
        "maximum principle argument, reviews related boundary value results, "
        "and outlines how symmetry properties are proved in the paper."
    )

    def fake_fetch_pdf_url_full_text(
        pdf_url: str,
        *,
        paper_id: str,
        source: str,
    ) -> FullTextExtract:
        return FullTextExtract(
            paper_id=paper_id,
            abstract=None,
            intro=intro,
            pdf_url=pdf_url,
            pdf_sha256="intro123",
            source=source,
            fetch_error=None,
            pdf_byte_size=456,
        )

    def fake_translate(abstract: str, **_kwargs):
        translated["source_text"] = abstract
        return "中" * 220

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "_resolve_checkpoint_path", lambda _resume, _run_id: checkpoint_path)
    monkeypatch.setattr(cli, "translate_abstract_to_zh", fake_translate)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        cli,
        "enrich_paper_with_hybrid_sources",
        lambda _doi, **_kwargs: cli.PaperMetadataEnrichment(
            pdf_url="https://example.org/intro.pdf",
            enrichment_sources=("openalex",),
        ),
    )
    monkeypatch.setattr(cli, "fetch_pdf_url_full_text", fake_fetch_pdf_url_full_text)
    monkeypatch.setattr(
        cli,
        "upsert_paper_full_text",
        lambda _conn, *, paper_id, extract, run_id: upserts.append(extract),
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

    assert translated["source_text"] == intro
    assert len(upserts) == 1
    assert upserts[0].intro == intro
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 1
    summary_sql, summary_params = update_calls[0]
    assert "summary_zh = %s" in summary_sql
    assert "abstract_clean" not in summary_sql
    assert summary_params[1] == "partial"
    report = json.loads(capsys.readouterr().out)
    assert report["full_text_enrichment_attempted"] == 1
    assert report["full_text_enriched"] == 1
    assert report["abstract_clean_backfilled_from_full_text"] == 0
    assert report["summaries_written"] == 1
    checkpoint_rows = [
        json.loads(line)
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert checkpoint_rows[-1]["abstract_source"] == "paper_full_text.intro"


def test_cli_backfills_abstract_clean_from_existing_full_text_abstract(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-FT",
            "title_clean": "Full text abstract paper",
            "title_raw": None,
            "year": 2026,
            "venue": "ICLR",
            "authors_display": "A. Smith",
            "abstract_clean": None,
            "full_text_abstract": "This full text abstract has useful technical details.",
            "summary_zh": None,
            "quality_status": "needs_enrichment",
        }
    ]
    conn.execute.return_value = select_cursor
    seen: dict[str, str] = {}

    def fake_translate(abstract: str, **_kwargs):
        seen["abstract"] = abstract
        return "中" * 220

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
    monkeypatch.setattr(cli, "translate_abstract_to_zh", fake_translate)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--limit", "1"]):
        cli.main()

    assert seen["abstract"] == "This full text abstract has useful technical details."
    update_calls = [
        (call.args[0], call.args[1])
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert len(update_calls) == 2
    metadata_sql, metadata_params = update_calls[0]
    assert "abstract_clean = COALESCE(%s, abstract_clean)" in metadata_sql
    assert metadata_params[0] == "This full text abstract has useful technical details."
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "ready"
    report = json.loads(capsys.readouterr().out)
    assert report["abstract_clean_backfilled_from_full_text"] == 1


def test_cli_enriches_openalex_metadata_before_summary(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-OA",
            "title_clean": "An OpenAlex paper",
            "title_raw": None,
            "doi": None,
            "arxiv_id": None,
            "openalex_id": "W123",
            "year": None,
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
            abstract=(
                "This OpenAlex abstract describes the research problem, proposed "
                "method, empirical evaluation, and reported scientific findings."
            ),
            venue="OpenAlex Venue",
            publication_date="2026-01-02",
            citation_count=7,
            enrichment_sources=("openalex",),
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

    assert seen == {"doi": None, "arxiv_id": None, "openalex_id": "W123"}
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
                abstract=(
                    "This enriched abstract describes the canonical paper content, "
                    "including the method, evaluation, and relevant findings."
                ),
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
    assert metadata_params[5] == "needs_review"
    summary_sql, summary_params = update_calls[1]
    assert "summary_zh = %s" in summary_sql
    assert summary_params[1] == "needs_review"
    report = json.loads(capsys.readouterr().out)
    assert report["identifier_contradictions"] == 1
    assert report["summaries_written"] == 1


def test_cli_summarizes_already_chinese_abstract(monkeypatch, tmp_path):
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
    translator = MagicMock(return_value="中" * 220)
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

    translator.assert_called_once()
    rows = [
        json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [
        {
            "paper_id": "PAPER-1",
            "status": "dry_run_success",
            "chars": 220,
            "abstract_source": "paper.abstract_clean",
        }
    ]


def test_cli_writes_checkpoint_to_explicit_resume_path(monkeypatch, tmp_path):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "A paper",
            "title_raw": None,
            "abstract_clean": "This paper proposes a robust model for discovery.",
            "summary_zh": None,
            "quality_status": "needs_enrichment",
        }
    ]
    conn.execute.return_value = select_cursor
    explicit_checkpoint = tmp_path / "explicit.jsonl"
    default_checkpoint = tmp_path / "default.jsonl"

    def fake_resolve_checkpoint_path(resume_arg, _run_id):
        return explicit_checkpoint if resume_arg else default_checkpoint

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "_resolve_checkpoint_path", fake_resolve_checkpoint_path)
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_a, **_kw: False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        [
            "run_paper_summary_zh_backfill.py",
            "--resume",
            str(explicit_checkpoint),
            "--limit",
            "1",
        ]
    ):
        cli.main()

    assert explicit_checkpoint.exists()
    assert not default_checkpoint.exists()
    rows = [
        json.loads(line)
        for line in explicit_checkpoint.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [
        {
            "paper_id": "PAPER-1",
            "status": "written",
            "chars": 220,
            "abstract_source": "paper.abstract_clean",
        }
    ]


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
