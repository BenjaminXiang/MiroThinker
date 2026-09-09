from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from src.data_agents.paper.dedup_merge import flip_paper_canonical

_EXACT_TITLE_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_paper_exact_title_dedup.py"
)
_RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
_CONF = "PAPER-3E13FAE7D789"
_JOURNAL = "PAPER-64D7A39FC25B"


def _import_exact_title_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_exact_title_dedup_for_overmerge_test",
        _EXACT_TITLE_SCRIPT_PATH,
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


class FlipFakeConnection:
    def __init__(
        self,
        *,
        papers: list[dict[str, Any]] | None = None,
        links: list[dict[str, Any]] | None = None,
        aliases: dict[str, str] | None = None,
    ) -> None:
        self.papers = {row["paper_id"]: dict(row) for row in papers or []}
        self.links = [dict(row) for row in links or []]
        self.aliases = dict(aliases or {})
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if (
            compact_sql.startswith("SELECT paper_id, identity_status")
            and "FROM paper" in compact_sql
        ):
            row = self.papers.get(params[0])
            return FakeCursor([row] if row else [])
        if (
            compact_sql.startswith("SELECT 1")
            and "FROM paper_merge_alias" in compact_sql
        ):
            old_paper_id, canonical_paper_id = params
            if self.aliases.get(old_paper_id) == canonical_paper_id:
                return FakeCursor([{"exists": 1}])
            return FakeCursor()
        if compact_sql.startswith("DELETE FROM paper_merge_alias"):
            old_paper_id, canonical_paper_id = params
            if self.aliases.get(old_paper_id) == canonical_paper_id:
                del self.aliases[old_paper_id]
                return FakeCursor(rowcount=1)
            return FakeCursor(rowcount=0)
        if compact_sql.startswith("INSERT INTO paper_merge_alias"):
            self.aliases[params["old_paper_id"]] = params["canonical_paper_id"]
            return FakeCursor(
                rows=[{"alias_id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}],
                rowcount=1,
            )
        if compact_sql.startswith("UPDATE paper"):
            paper_id = params[1]
            row = self.papers.get(paper_id)
            if row is None:
                return FakeCursor(rowcount=0)
            if "identity_status = 'confirmed'" in compact_sql:
                row["identity_status"] = "confirmed"
                row["quality_status"] = "ready"
            elif "identity_status = 'merged'" in compact_sql:
                row["identity_status"] = "merged"
                row["quality_status"] = "rejected"
            row["run_id"] = params[0]
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("UPDATE professor_paper_link"):
            if "link_status = 'verified'" in compact_sql:
                paper_id = params[1]
                count = 0
                for link in self.links:
                    if (
                        link["paper_id"] == paper_id
                        and link["link_status"] == "rejected"
                    ):
                        link["link_status"] = "verified"
                        link["rejected_at"] = None
                        link["rejected_reason"] = None
                        link["run_id"] = params[0]
                        count += 1
                return FakeCursor(rowcount=count)
            if "link_status = 'rejected'" in compact_sql:
                paper_id = params[2]
                count = 0
                for link in self.links:
                    if (
                        link["paper_id"] == paper_id
                        and link["link_status"] != "rejected"
                    ):
                        link["link_status"] = "rejected"
                        link["rejected_reason"] = params[0]
                        link["run_id"] = params[1]
                        count += 1
                return FakeCursor(rowcount=count)
        return FakeCursor()


class CandidateFakeConnection:
    def __init__(self, papers: list[dict[str, Any]]) -> None:
        self.papers = {row["paper_id"]: dict(row) for row in papers}
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if compact_sql.startswith("WITH g AS"):
            return FakeCursor(self._candidate_groups())
        return FakeCursor()

    def _candidate_groups(self) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in self.papers.values():
            title = str(row.get("title_clean") or "").strip().lower()
            if not title:
                continue
            if (row.get("identity_status") or "unverified") in {"rejected", "merged"}:
                continue
            groups.setdefault(title, []).append(row)

        result: list[dict[str, Any]] = []
        for title, rows in groups.items():
            authors = {
                str(row.get("authors_display") or "").strip().lower() for row in rows
            }
            publisher_dois = {
                doi
                for row in rows
                if (doi := _publisher_doi(row.get("doi"))) is not None
            }
            if len(rows) > 1 and len(authors) == 1 and len(publisher_dois) <= 1:
                result.append(
                    {
                        "t": title,
                        "pids": sorted(row["paper_id"] for row in rows),
                    }
                )
        return sorted(result, key=lambda row: row["t"])


def _publisher_doi(value: object) -> str | None:
    if value is None:
        return None
    doi = str(value).strip()
    if not doi:
        return None
    lowered = doi.lower()
    if lowered.startswith(("10.48550/arxiv.", "10.2139/ssrn.", "10.5194/egusphere-")):
        return None
    return doi


def _paper(paper_id: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "paper_id": paper_id,
        "title_clean": "Exact Duplicate Title",
        "authors_display": "Ada Lovelace, Grace Hopper",
        "doi": None,
        "identity_status": "unverified",
        "quality_status": "needs_enrichment",
    }
    row.update(overrides)
    return row


def _link(
    paper_id: str,
    *,
    link_status: str,
    match_reason: str,
) -> dict[str, Any]:
    return {
        "professor_id": "PROF-ADE0D71E527F",
        "paper_id": paper_id,
        "link_status": link_status,
        "match_reason": match_reason,
        "rejected_at": "2026-06-29T00:00:00Z" if link_status == "rejected" else None,
        "rejected_reason": "merged_into_canonical"
        if link_status == "rejected"
        else None,
    }


def _preflip_conn() -> FlipFakeConnection:
    return FlipFakeConnection(
        papers=[
            _paper(_CONF, identity_status="confirmed", quality_status="ready"),
            _paper(_JOURNAL, identity_status="merged", quality_status="rejected"),
        ],
        links=[
            _link(
                _CONF,
                link_status="verified",
                match_reason=f"homepage_title_resolution; exact_title_dedup:{_JOURNAL}",
            ),
            _link(
                _JOURNAL,
                link_status="rejected",
                match_reason="homepage_title_resolution",
            ),
        ],
        aliases={_JOURNAL: _CONF},
    )


def test_flip_reverses_alias_before_writing_corrected_alias() -> None:
    conn = _preflip_conn()

    result = flip_paper_canonical(
        conn,
        old_canonical=_CONF,
        new_canonical=_JOURNAL,
        run_id=_RUN_ID,
    )

    delete_index = next(
        index
        for index, (sql, _params) in enumerate(conn.statements)
        if "DELETE FROM paper_merge_alias" in sql
    )
    upsert_index = next(
        index
        for index, (sql, _params) in enumerate(conn.statements)
        if "INSERT INTO paper_merge_alias" in sql
    )
    delete_params = conn.statements[delete_index][1]
    upsert_params = conn.statements[upsert_index][1]

    assert delete_index < upsert_index
    assert delete_params == (_JOURNAL, _CONF)
    assert upsert_params["old_paper_id"] == _CONF
    assert upsert_params["canonical_paper_id"] == _JOURNAL
    assert conn.aliases == {_CONF: _JOURNAL}
    assert result["aliases_deleted"] == 1
    assert result["aliases_written"] == 1


def test_flip_restores_journal_link_without_changing_clean_match_reason() -> None:
    conn = _preflip_conn()

    result = flip_paper_canonical(
        conn,
        old_canonical=_CONF,
        new_canonical=_JOURNAL,
        run_id=_RUN_ID,
    )

    journal_link = _find_link(conn, _JOURNAL)
    journal_update_sql = next(
        sql
        for sql, params in conn.statements
        if "UPDATE professor_paper_link" in sql and params[-1] == _JOURNAL
    )
    assert "link_status = 'verified'" in journal_update_sql
    assert journal_link["link_status"] == "verified"
    assert journal_link["match_reason"] == "homepage_title_resolution"
    assert result["links_restored"] == 1


def test_flip_rejects_conference_link_and_keeps_contamination_hidden() -> None:
    conn = _preflip_conn()

    result = flip_paper_canonical(
        conn,
        old_canonical=_CONF,
        new_canonical=_JOURNAL,
        run_id=_RUN_ID,
    )

    conf_link = _find_link(conn, _CONF)
    journal_link = _find_link(conn, _JOURNAL)
    conf_update_params = next(
        params
        for sql, params in conn.statements
        if "UPDATE professor_paper_link" in sql and params[-1] == _CONF
    )
    assert conf_link["link_status"] == "rejected"
    assert conf_link["rejected_reason"] == f"merged_into_canonical:{_JOURNAL}"
    assert conf_link["match_reason"].endswith(f"; exact_title_dedup:{_JOURNAL}")
    assert f"exact_title_dedup:{_JOURNAL}" not in journal_link["match_reason"]
    assert conf_update_params[0] == f"merged_into_canonical:{_JOURNAL}"
    assert result["links_rejected"] == 1


def test_flip_swaps_paper_statuses() -> None:
    conn = _preflip_conn()

    result = flip_paper_canonical(
        conn,
        old_canonical=_CONF,
        new_canonical=_JOURNAL,
        run_id=_RUN_ID,
    )

    assert conn.papers[_JOURNAL]["identity_status"] == "confirmed"
    assert conn.papers[_JOURNAL]["quality_status"] == "ready"
    assert conn.papers[_CONF]["identity_status"] == "merged"
    assert conn.papers[_CONF]["quality_status"] == "rejected"
    assert result["papers_promoted"] == 1
    assert result["papers_demoted"] == 1


def test_flip_is_noop_when_conference_is_already_merged_to_journal() -> None:
    conn = FlipFakeConnection(
        papers=[
            _paper(_CONF, identity_status="merged", quality_status="rejected"),
            _paper(_JOURNAL, identity_status="confirmed", quality_status="ready"),
        ],
        links=[],
        aliases={_CONF: _JOURNAL},
    )

    result = flip_paper_canonical(
        conn,
        old_canonical=_CONF,
        new_canonical=_JOURNAL,
        run_id=_RUN_ID,
    )

    assert result == {
        "aliases_deleted": 0,
        "aliases_written": 0,
        "papers_promoted": 0,
        "papers_demoted": 0,
        "links_restored": 0,
        "links_rejected": 0,
    }
    assert not any(
        sql.lstrip().startswith(("DELETE", "INSERT", "UPDATE"))
        for sql, _params in conn.statements
    )


def test_flip_rejects_identical_paper_ids() -> None:
    with pytest.raises(
        ValueError, match="old_canonical must differ from new_canonical"
    ):
        flip_paper_canonical(
            FlipFakeConnection(),
            old_canonical=_CONF,
            new_canonical=_CONF,
            run_id=_RUN_ID,
        )


def test_candidate_sql_excludes_publisher_doi_conflict_group() -> None:
    cli = _import_exact_title_cli()
    conn = CandidateFakeConnection(
        [
            _paper("PAPER-CONF", doi="10.1007/978-3-030-17184-1_10"),
            _paper("PAPER-JOURNAL", doi="10.1016/j.jlamp.2021.100678"),
        ]
    )

    groups = cli._fetch_candidate_groups(conn, limit=None)

    compact_sql = " ".join(conn.statements[0][0].split()).lower()
    assert "count(distinct nullif(p.doi,''))" in compact_sql
    assert "10.48550/arxiv.%" in compact_sql
    assert groups == []


def test_candidate_sql_keeps_preprint_published_pair_eligible() -> None:
    cli = _import_exact_title_cli()
    conn = CandidateFakeConnection(
        [
            _paper("PAPER-ARXIV", doi="10.48550/arxiv.1805.10073"),
            _paper("PAPER-PUBLISHED", doi="10.1016/j.jlamp.2021.100678"),
        ]
    )

    groups = cli._fetch_candidate_groups(conn, limit=None)

    assert groups == [
        {"t": "exact duplicate title", "pids": ["PAPER-ARXIV", "PAPER-PUBLISHED"]}
    ]


def _find_link(conn: FlipFakeConnection, paper_id: str) -> dict[str, Any]:
    return next(link for link in conn.links if link["paper_id"] == paper_id)
