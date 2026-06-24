from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
import types
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.data_agents.paper.canonical_writer import PaperUpsertReport
from src.data_agents.paper.title_resolver import ResolvedPaper

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_paper_title_enrichment_backfill.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_title_enrichment_backfill", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if " FROM paper p " in compact_sql and "professor_paper_link" in compact_sql:
            return FakeCursor(rows=self.rows)
        if compact_sql.startswith("INSERT INTO paper_merge_alias"):
            return FakeCursor(
                rows=[{"alias_id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}],
                rowcount=1,
            )
        if compact_sql.startswith("UPDATE paper"):
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO professor_paper_link"):
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("UPDATE professor_paper_link"):
            return FakeCursor(rowcount=1)
        return FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class NullCache:
    def get(self, _key: str):
        return None

    def set(self, _key: str, _value: ResolvedPaper) -> None:
        return None


def _row() -> dict[str, Any]:
    return {
        "paper_id": "PAPER-PAGEONLY",
        "title_clean": "Communication Efficient Federated Learning with Adaptive Quantization",
        "title_raw": None,
        "year": 2022,
        "authors_display": "Wenbo Ding et al.",
        "links": [
            {
                "link_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "professor_id": "PROF-DING",
                "canonical_name": "丁文伯",
                "evidence_source_type": "prof_homepage_tier2",
                "evidence_page_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "evidence_api_source": None,
                "match_reason": "official_homepage_publication",
                "author_name_match_score": "0.95",
                "topic_consistency_score": None,
                "institution_consistency_score": None,
                "is_officially_listed": True,
            }
        ],
    }


def _resolved() -> ResolvedPaper:
    return ResolvedPaper(
        title="Communication Efficient Federated Learning with Adaptive Quantization",
        doi="10.1145/3510587",
        openalex_id="W4294290817",
        arxiv_id=None,
        abstract="Federated learning abstract.",
        pdf_url=None,
        authors=("Wenbo Ding", "Yuzhu Mao"),
        year=2022,
        venue="ACM Transactions on Intelligent Systems and Technology",
        match_confidence=1.0,
        match_source="crossref",
    )


def _args(*, dry_run: bool) -> SimpleNamespace:
    return SimpleNamespace(
        plan_only=False,
        dry_run=dry_run,
        limit=1,
        worker_count=1,
        worker_index=0,
        seed_id=["8"],
        paper_id=[],
        paper_id_file=[],
        cache_only=False,
        min_confidence=0.85,
        reject_implausible=False,
        disable_openalex_title_search=False,
        disable_semantic_scholar_title_search=False,
        disable_dblp_title_search=False,
        disable_arxiv_title_search=True,
    )


def test_build_select_sql_scopes_seed_to_page_only_verified_links():
    cli = _import_cli()

    sql, params = cli._build_select_sql(
        limit=20,
        seed_ids=("8",),
        paper_ids=(),
    )

    compact_sql = " ".join(sql.split())
    assert "latest_seed_run AS (" in compact_sql
    assert "p.canonical_source = 'prof_page_only'" in compact_sql
    assert "ppl.link_status = 'verified'" in compact_sql
    assert "jsonb_agg" in compact_sql
    assert params == (["8"], 20)


def test_build_select_sql_can_shard_prof_page_only_candidates_by_worker():
    cli = _import_cli()

    sql, params = cli._build_select_sql(
        limit=20,
        seed_ids=(),
        paper_ids=(),
        worker_count=4,
        worker_index=2,
    )

    compact_sql = " ".join(sql.split())
    assert "mod(abs(hashtext(p.paper_id)::bigint), %s) = %s" in compact_sql
    assert params == (4, 2, 20)


def test_parse_args_validates_worker_shard_bounds():
    cli = _import_cli()

    args = cli._parse_args(["--worker-count", "4", "--worker-index", "3"])
    assert args.worker_count == 4
    assert args.worker_index == 3

    with pytest.raises(SystemExit):
        cli._parse_args(["--worker-count", "0"])
    with pytest.raises(SystemExit):
        cli._parse_args(["--worker-count", "4", "--worker-index", "4"])


def test_parse_args_can_scope_to_paper_ids_from_file(tmp_path):
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

    args = cli._parse_args(
        ["--paper-id", "PAPER-0", "--paper-id-file", str(paper_id_file)]
    )

    assert args.paper_id == ["PAPER-0", "PAPER-1", "PAPER-2"]


def test_parse_args_accepts_cache_only_mode():
    cli = _import_cli()

    args = cli._parse_args(["--cache-only", "--dry-run"])

    assert args.cache_only is True
    assert args.dry_run is True


def test_cli_loads_app_env_file_on_import(monkeypatch):
    calls: list[Path] = []
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda path: calls.append(Path(path)))
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    _import_cli()

    assert calls == [_SCRIPT_PATH.resolve().parents[1] / ".env"]


def test_build_select_sql_excludes_unsafe_professor_identity_and_title_pollution():
    cli = _import_cli()

    sql, _params = cli._build_select_sql(
        limit=20,
        seed_ids=("35",),
        paper_ids=(),
    )

    compact_sql = " ".join(sql.split()).lower()
    assert "prof.canonical_name" in compact_sql
    assert "面包屑" in compact_sql
    assert "highlighted news" in compact_sql
    assert "deep bit lab" in compact_sql
    assert "lab introduction" in compact_sql
    assert "professor_affiliation" in compact_sql
    assert "inventors" in compact_sql
    assert "us patent" in compact_sql


def test_process_rows_dry_run_resolves_without_writes():
    cli = _import_cli()
    conn = FakeConnection([_row()])

    report = cli._process_rows(
        conn,
        [_row()],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=True),
        resolve_title=lambda *_args, **_kwargs: _resolved(),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=True,
        ),
    )

    assert report["papers_processed"] == 1
    assert report["papers_resolved"] == 1
    assert report["paper_upserts"] == 0
    assert report["link_migrations"] == 0
    assert not any("INSERT INTO professor_paper_link" in sql for sql, _ in conn.statements)
    assert not any("UPDATE paper" in sql for sql, _ in conn.statements)


def test_process_rows_skips_implausible_titles_before_resolver():
    cli = _import_cli()
    bad_row = {**_row(), "title_clean": "Meitong Dong, Wang"}
    calls: list[str] = []

    report = cli._process_rows(
        FakeConnection([bad_row]),
        [bad_row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=True),
        resolve_title=lambda title, **_kwargs: calls.append(title) or _resolved(),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_processed"] == 1
    assert report["papers_resolved"] == 0
    assert report["papers_unresolved"] == 1
    assert report["unresolved_samples"][0]["reason"] == "implausible_title"
    assert calls == []


def test_process_rows_skips_rows_with_only_unsafe_professor_links_before_resolver():
    cli = _import_cli()
    row = {
        **_row(),
        "links": [
            {
                **_row()["links"][0],
                "professor_id": "PROF-BREADCRUMB",
                "canonical_name": "面包屑",
            }
        ],
    }
    calls: list[str] = []

    conn = FakeConnection([row])

    report = cli._process_rows(
        conn,
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=True),
        resolve_title=lambda title, **_kwargs: calls.append(title) or _resolved(),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_processed"] == 1
    assert report["papers_resolved"] == 0
    assert report["papers_unresolved"] == 1
    assert report["unsafe_links_filtered"] == 1
    assert report["unresolved_samples"][0]["reason"] == "unsafe_professor_links"
    assert report["unsafe_link_samples"][0]["canonical_name"] == "面包屑"
    assert calls == []


def test_process_rows_migrates_only_safe_professor_links():
    cli = _import_cli()
    safe_link = _row()["links"][0]
    unsafe_link = {
        **safe_link,
        "link_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "professor_id": "PROF-BREADCRUMB",
        "canonical_name": "面包屑",
    }
    row = {**_row(), "links": [safe_link, unsafe_link]}
    migrated_professor_ids: list[str] = []

    def fake_upsert_link(conn, *, link, old_paper_id, resolved_paper_id, resolved, run_id):
        migrated_professor_ids.append(link["professor_id"])
        return 1

    original = cli._upsert_migrated_link
    cli._upsert_migrated_link = fake_upsert_link
    try:
        report = cli._process_rows(
            FakeConnection([row]),
            [row],
            cache=NullCache(),
            http_client=None,
            run_id=UUID("11111111-1111-1111-1111-111111111111"),
            args=_args(dry_run=False),
            resolve_title=lambda *_args, **_kwargs: _resolved(),
            upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
                paper_id="PAPER-RESOLVED",
                is_new=True,
            ),
        )
    finally:
        cli._upsert_migrated_link = original

    assert report["papers_resolved"] == 1
    assert report["unsafe_links_filtered"] == 1
    assert migrated_professor_ids == ["PROF-DING"]


def test_plan_only_reports_unsafe_professor_link_rows(capsys):
    cli = _import_cli()
    row = {
        **_row(),
        "links": [
            {
                **_row()["links"][0],
                "professor_id": "PROF-BREADCRUMB",
                "canonical_name": "面包屑",
            }
        ],
    }
    args = _args(dry_run=False)
    args.plan_only = True

    report = cli._build_plan_report([row], args=args)

    assert report["resolver_candidates"] == 0
    assert report["missing_title_or_links"] == 1
    assert report["unsafe_link_rows"] == 1
    assert report["unsafe_links_filtered"] == 1
    assert report["unsafe_link_samples"][0]["canonical_name"] == "面包屑"


def test_process_rows_resolves_with_reference_like_cleaned_title():
    cli = _import_cli()
    raw_title = (
        "Isolation and impartial aggregation: A paradigm of incremental learning "
        "without interference Yabin Wang #, Zhiheng Ma #, Zhiwu Huang, Yaowei "
        "Wang, Zhou Su, Xiaopeng Hong & Code"
    )
    row = {**_row(), "title_clean": raw_title}
    resolver_calls: list[str] = []

    def fake_resolve_title(title, **_kwargs):
        resolver_calls.append(title)
        return _resolved()

    report = cli._process_rows(
        FakeConnection([row]),
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=True),
        resolve_title=fake_resolve_title,
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert resolver_calls == [
        "Isolation and impartial aggregation: A paradigm of incremental "
        "learning without interference"
    ]
    assert report["resolved_samples"][0]["title"] == resolver_calls[0]


def test_process_rows_resolves_with_runtime_reference_tail_cleaned_title():
    cli = _import_cli()
    raw_title = (
        "Quantifying privacy vulnerability under linkage attack across "
        "multi-source individual mobility data. In 99th Transportation "
        "Research Board (TRB) Annual Meeting. [download]"
    )
    row = {**_row(), "title_clean": raw_title}
    resolver_calls: list[str] = []

    def fake_resolve_title(title, **_kwargs):
        resolver_calls.append(title)
        return _resolved()

    report = cli._process_rows(
        FakeConnection([row]),
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=True),
        resolve_title=fake_resolve_title,
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert resolver_calls == [
        "Quantifying privacy vulnerability under linkage attack across "
        "multi-source individual mobility data"
    ]
    assert report["resolved_samples"][0]["title"] == resolver_calls[0]


@pytest.mark.parametrize(
    "bad_title",
    [
        "Applied Catalysis B: Environmental",
        "Muhammad-Sadeeq (Jie Tang) Balogun",
    ],
)
def test_process_rows_skips_suat_venue_and_person_alias_noise(bad_title: str):
    cli = _import_cli()
    row = {**_row(), "title_clean": bad_title}
    calls: list[str] = []

    report = cli._process_rows(
        FakeConnection([row]),
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=True),
        resolve_title=lambda title, **_kwargs: calls.append(title) or _resolved(),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 0
    assert report["papers_unresolved"] == 1
    assert report["unresolved_samples"][0]["reason"] == "implausible_title"
    assert calls == []


def test_process_rows_can_reject_implausible_titles_when_explicitly_enabled():
    cli = _import_cli()
    bad_row = {**_row(), "title_clean": "Meitong Dong, Wang"}
    args = _args(dry_run=False)
    args.reject_implausible = True
    conn = FakeConnection([bad_row])

    report = cli._process_rows(
        conn,
        [bad_row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        resolve_title=lambda *_args, **_kwargs: _resolved(),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_unresolved"] == 1
    assert report["implausible_papers_rejected"] == 1
    assert report["implausible_links_rejected"] == 1
    assert report["pipeline_issues_inserted"] == 1

    joined_sql = "\n".join(sql for sql, _ in conn.statements)
    assert "UPDATE professor_paper_link" in joined_sql
    assert "implausible_title" in joined_sql
    assert "UPDATE paper" in joined_sql
    assert "identity_status = 'rejected'" in joined_sql
    assert "INSERT INTO pipeline_issue" in joined_sql
    assert conn.commits == 1


def test_process_rows_migrates_links_and_marks_page_only_merged():
    cli = _import_cli()
    conn = FakeConnection([_row()])

    report = cli._process_rows(
        conn,
        [_row()],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=False),
        resolve_title=lambda *_args, **_kwargs: _resolved(),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_processed"] == 1
    assert report["papers_resolved"] == 1
    assert report["paper_upserts"] == 1
    assert report["link_migrations"] == 1
    assert report["page_only_papers_merged"] == 1
    assert report["merge_aliases_written"] == 1

    joined_sql = "\n".join(sql for sql, _ in conn.statements)
    assert "INSERT INTO paper_merge_alias" in joined_sql
    assert "INSERT INTO professor_paper_link" in joined_sql
    assert "ON CONFLICT (professor_id, paper_id) DO UPDATE" in joined_sql
    assert "UPDATE professor_paper_link" in joined_sql
    assert "UPDATE paper" in joined_sql

    merged_update = [
        params
        for sql, params in conn.statements
        if "UPDATE paper" in sql and "identity_status = 'merged'" in sql
    ][0]
    assert merged_update[1] == "PAPER-PAGEONLY"
    assert conn.commits == 1


@pytest.mark.parametrize(
    ("title", "year"),
    [
        (
            "Improved Alzheimer's disease diagnosis using multimodal sparse "
            "similarity feature selection and auxiliary data",
            2018,
        ),
        ("Graph Neural Networks for Materials Discovery", 2023),
    ],
)
def test_process_rows_records_merge_alias_for_duplicate_title_year_groups(
    title: str,
    year: int,
) -> None:
    cli = _import_cli()
    row = {**_row(), "title_clean": title, "title_raw": title, "year": year}
    conn = FakeConnection([row])

    report = cli._process_rows(
        conn,
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=False),
        resolve_title=lambda *_args, **_kwargs: ResolvedPaper(
            title=title,
            doi="10.1016/j.neucom.2018.01.001",
            openalex_id="WTEST",
            arxiv_id=None,
            abstract="Resolved duplicate abstract.",
            pdf_url=None,
            authors=("Ahmed Elazab", "Test Author"),
            year=year,
            venue="Neurocomputing",
            match_confidence=0.99,
            match_source="crossref",
        ),
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-CANON",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert report["link_migrations"] == 1
    assert report["merge_aliases_written"] == 1
    assert report["page_only_papers_merged"] == 1
    alias_params = [
        params
        for sql, params in conn.statements
        if "INSERT INTO paper_merge_alias" in sql
    ][0]
    assert alias_params["old_paper_id"] == "PAPER-PAGEONLY"
    assert alias_params["canonical_paper_id"] == "PAPER-CANON"


def test_process_rows_forwards_pfedgpa_arxiv_resolution_to_upsert() -> None:
    cli = _import_cli()
    title = (
        "pFedGPA: Diffusion-based Generative Parameter Aggregation for "
        "Personalized Federated Learning"
    )
    row = {**_row(), "title_clean": title, "title_raw": title, "year": 2024}
    upsert_kwargs: dict[str, Any] = {}

    def fake_upsert(*_args, **kwargs):
        upsert_kwargs.update(kwargs)
        return PaperUpsertReport(paper_id="PAPER-ARXIV-PFEDGPA", is_new=False)

    conn = FakeConnection([row])

    report = cli._process_rows(
        conn,
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=False),
        resolve_title=lambda *_args, **_kwargs: ResolvedPaper(
            title=title,
            doi=None,
            openalex_id=None,
            arxiv_id="2409.05701",
            abstract="Diffusion-based generative parameter aggregation.",
            pdf_url="http://arxiv.org/pdf/2409.05701v1",
            authors=("Test Author",),
            year=2024,
            venue="arXiv",
            match_confidence=0.99,
            match_source="arxiv",
        ),
        upsert_paper_fn=fake_upsert,
    )

    assert report["papers_resolved"] == 1
    assert report["resolved_samples"][0]["arxiv_id"] == "2409.05701"
    assert report["resolved_samples"][0]["pdf_url"] == "http://arxiv.org/pdf/2409.05701v1"
    assert report["full_text_pdf_upserts"] == 1
    assert upsert_kwargs["arxiv_id"] == "2409.05701"
    assert upsert_kwargs["canonical_source"] == "arxiv"
    assert upsert_kwargs["title_resolution_source"] == "arxiv"
    joined_sql = "\n".join(sql for sql, _ in conn.statements)
    assert "INSERT INTO paper_full_text" in joined_sql
    assert "http://arxiv.org/pdf/2409.05701v1" in repr(conn.statements)


def test_resolved_pdf_metadata_source_fits_database_limit() -> None:
    cli = _import_cli()
    conn = FakeConnection()

    count = cli._upsert_resolved_pdf_metadata(
        conn,
        resolved_paper_id="PAPER-SEMANTIC-SCHOLAR",
        resolved=ResolvedPaper(
            title="Discovery of the doubly charmed Tcc+ state",
            doi="10.1103/physrevd.105.l031505",
            openalex_id=None,
            arxiv_id="2108.00923",
            abstract="Source-backed abstract.",
            pdf_url="http://link.aps.org/pdf/10.1103/PhysRevD.105.L031505",
            authors=("Tian-Wei Wu",),
            year=2021,
            venue="Physical Review D",
            match_confidence=1.0,
            match_source="semantic_scholar",
        ),
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
    )

    assert count == 1
    source_param = [
        params[3]
        for sql, params in conn.statements
        if "INSERT INTO paper_full_text" in sql
    ][0]
    assert source_param == "title_res:semantic_scholar"
    assert len(source_param) <= 32


def test_process_rows_uses_existing_identifier_before_title_resolver_and_copies_summary():
    cli = _import_cli()
    row = {
        **_row(),
        "doi": "10.1111/1748-8583.12544",
        "venue": "Human Resource Management Journal",
        "abstract_clean": "This abstract was already enriched from DOI metadata.",
        "summary_zh": "这是一段已经生成的中文解读。",
        "quality_status": "ready",
    }
    conn = FakeConnection([row])
    resolve_calls: list[str] = []
    upsert_kwargs: dict[str, Any] = {}

    def fake_upsert(*_args, **kwargs):
        upsert_kwargs.update(kwargs)
        return PaperUpsertReport(paper_id="PAPER-DOI", is_new=False)

    report = cli._process_rows(
        conn,
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=False),
        resolve_title=lambda title, **_kwargs: resolve_calls.append(title) or _resolved(),
        upsert_paper_fn=fake_upsert,
    )

    assert resolve_calls == []
    assert report["papers_resolved"] == 1
    assert report["link_migrations"] == 1
    assert upsert_kwargs["doi"] == "10.1111/1748-8583.12544"
    assert upsert_kwargs["canonical_source"] == "crossref"
    assert upsert_kwargs["title_resolution_source"] == "doi_lookup"
    joined_sql = "\n".join(sql for sql, _ in conn.statements)
    assert "summary_zh = COALESCE(summary_zh, %s)" in joined_sql
    assert "quality_status = CASE" in joined_sql


def test_process_rows_does_not_trust_polluted_existing_doi_identifier():
    cli = _import_cli()
    row = {
        **_row(),
        "doi": "10.1021/10.1002/poc.4450",
        "venue": None,
        "abstract_clean": None,
        "summary_zh": None,
        "quality_status": "needs_enrichment",
    }
    conn = FakeConnection([row])
    resolver_kwargs: dict[str, Any] = {}
    upsert_kwargs: dict[str, Any] = {}

    def fake_resolve_title(title, **kwargs):
        resolver_kwargs.update(kwargs)
        return _resolved()

    def fake_upsert(*_args, **kwargs):
        upsert_kwargs.update(kwargs)
        return PaperUpsertReport(paper_id="PAPER-RESOLVED", is_new=False)

    report = cli._process_rows(
        conn,
        [row],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=_args(dry_run=False),
        resolve_title=fake_resolve_title,
        upsert_paper_fn=fake_upsert,
    )

    assert resolver_kwargs
    assert report["bad_doi_identifiers"] == 1
    assert report["bad_doi_samples"] == [
        {
            "paper_id": "PAPER-PAGEONLY",
            "doi": "10.1021/10.1002/poc.4450",
            "reason": "nested_doi_prefix",
        }
    ]
    assert report["papers_resolved"] == 1
    assert upsert_kwargs["doi"] == "10.1145/3510587"
    assert upsert_kwargs["title_resolution_source"] == "crossref"


def test_process_rows_forwards_openalex_disable_flag_to_title_resolver():
    cli = _import_cli()
    conn = FakeConnection([_row()])
    args = _args(dry_run=True)
    args.disable_openalex_title_search = True
    resolver_kwargs: dict[str, Any] = {}

    def fake_resolve_title(_title, **kwargs):
        resolver_kwargs.update(kwargs)
        return _resolved()

    report = cli._process_rows(
        conn,
        [_row()],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        resolve_title=fake_resolve_title,
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert resolver_kwargs["enable_openalex_title_search"] is False


def test_process_rows_forwards_dblp_disable_flag_to_title_resolver():
    cli = _import_cli()
    conn = FakeConnection([_row()])
    args = _args(dry_run=True)
    args.disable_dblp_title_search = True
    resolver_kwargs: dict[str, Any] = {}

    def fake_resolve_title(_title, **kwargs):
        resolver_kwargs.update(kwargs)
        return _resolved()

    report = cli._process_rows(
        conn,
        [_row()],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        resolve_title=fake_resolve_title,
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert resolver_kwargs["enable_dblp_title_search"] is False


def test_process_rows_forwards_semantic_scholar_disable_flag_to_title_resolver():
    cli = _import_cli()
    conn = FakeConnection([_row()])
    args = _args(dry_run=True)
    args.disable_semantic_scholar_title_search = True
    resolver_kwargs: dict[str, Any] = {}

    def fake_resolve_title(_title, **kwargs):
        resolver_kwargs.update(kwargs)
        return _resolved()

    report = cli._process_rows(
        conn,
        [_row()],
        cache=NullCache(),
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        resolve_title=fake_resolve_title,
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert resolver_kwargs["enable_semantic_scholar_title_search"] is False


def test_process_rows_forwards_cache_only_and_keeps_cache_in_dry_run():
    cli = _import_cli()
    conn = FakeConnection([_row()])
    args = _args(dry_run=True)
    args.cache_only = True
    cache = NullCache()
    resolver_kwargs: dict[str, Any] = {}

    def fake_resolve_title(_title, **kwargs):
        resolver_kwargs.update(kwargs)
        return _resolved()

    report = cli._process_rows(
        conn,
        [_row()],
        cache=cache,
        http_client=None,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        resolve_title=fake_resolve_title,
        upsert_paper_fn=lambda *_args, **_kwargs: PaperUpsertReport(
            paper_id="PAPER-RESOLVED",
            is_new=False,
        ),
    )

    assert report["papers_resolved"] == 1
    assert report["cache_only"] is True
    assert resolver_kwargs["cache_only"] is True
    assert resolver_kwargs["cache"] is cache


def test_empty_report_records_dblp_title_search_switch():
    cli = _import_cli()
    args = _args(dry_run=True)
    args.disable_dblp_title_search = True

    report = cli._empty_report(
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        rows_total=0,
    )

    assert report["dblp_title_search_enabled"] is False


def test_empty_report_records_semantic_scholar_title_search_switch():
    cli = _import_cli()
    args = _args(dry_run=True)
    args.disable_semantic_scholar_title_search = True

    report = cli._empty_report(
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        rows_total=0,
    )

    assert report["semantic_scholar_title_search_enabled"] is False


def test_empty_report_truncates_large_paper_id_scope():
    cli = _import_cli()
    args = _args(dry_run=True)
    args.paper_id = [f"PAPER-{index:04d}" for index in range(105)]

    report = cli._empty_report(
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        args=args,
        rows_total=0,
    )

    assert report["paper_id_count"] == 105
    assert report["paper_id_truncated"] is True
    assert report["paper_id"] == [f"PAPER-{index:04d}" for index in range(100)]


def test_main_plan_only_is_read_only_and_does_not_open_pipeline_run(monkeypatch, capsys):
    cli = _import_cli()
    conn = FakeConnection([_row()])
    open_run = MagicMock()
    open_http = MagicMock()

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", open_run)
    monkeypatch.setattr(cli, "_open_http_client", open_http)

    cli.main(["--plan-only", "--seed-id", "35", "--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["plan_only"] is True
    assert report["papers_total"] == 1
    assert report["resolver_candidates"] == 1
    assert report["implausible_titles"] == 0
    assert conn.commits == 0
    open_run.assert_not_called()
    open_http.assert_not_called()


def test_main_dry_run_does_not_open_pipeline_run(monkeypatch, capsys):
    cli = _import_cli()
    conn = FakeConnection([_row()])
    open_run = MagicMock()
    close_run = MagicMock()
    http_client = MagicMock()

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", open_run)
    monkeypatch.setattr(cli, "close_pipeline_run", close_run)
    monkeypatch.setattr(cli, "_open_http_client", lambda: http_client)
    monkeypatch.setattr(cli, "PostgresTitleResolutionCache", lambda _conn: NullCache())
    monkeypatch.setattr(cli, "resolve_paper_by_title", lambda *_a, **_kw: _resolved())

    cli.main(["--dry-run", "--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert conn.commits == 0
    open_run.assert_not_called()
    close_run.assert_not_called()


def test_cli_help_lists_safe_scoping_flags(capsys):
    cli = _import_cli()

    try:
        cli.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "--plan-only" in captured.out
    assert "--dry-run" in captured.out
    assert "--seed-id" in captured.out
    assert "--paper-id" in captured.out
    assert "--reject-implausible" in captured.out
    assert "--disable-openalex-title-search" in captured.out
    assert "--disable-semantic-scholar-title-search" in captured.out
    assert "--disable-dblp-title-search" in captured.out
    assert "--disable-arxiv-title-search" in captured.out
