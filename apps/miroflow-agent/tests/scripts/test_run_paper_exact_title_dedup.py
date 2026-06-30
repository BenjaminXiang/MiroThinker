from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_paper_exact_title_dedup.py"
)
_RUN_ID = UUID("11111111-1111-1111-1111-111111111111")


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_exact_title_dedup", _SCRIPT_PATH
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
    def __init__(
        self,
        *,
        papers: list[dict[str, Any]] | None = None,
        links: list[dict[str, Any]] | None = None,
    ) -> None:
        self.papers = {row["paper_id"]: dict(row) for row in papers or []}
        self.links = [dict(row) for row in links or []]
        self.aliases: dict[str, str] = {}
        self.statements: list[tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql: str, params: Any = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if compact_sql.startswith("WITH g AS"):
            return FakeCursor(self._candidate_groups())
        if (
            compact_sql.startswith("SELECT p.paper_id")
            and "FROM paper p" in compact_sql
        ):
            paper_ids = list(params[0])
            rows = [self.papers[paper_id] for paper_id in paper_ids]
            return FakeCursor(rows)
        if compact_sql.startswith("SELECT paper_id") and "FROM paper" in compact_sql:
            paper_id = params[0]
            row = self.papers.get(paper_id)
            return FakeCursor([row] if row else [])
        if (
            compact_sql.startswith("SELECT")
            and "FROM professor_paper_link" in compact_sql
        ):
            paper_id = params[0]
            rows = [
                dict(link)
                for link in self.links
                if link["paper_id"] == paper_id and link["link_status"] != "rejected"
            ]
            return FakeCursor(rows)
        if compact_sql.startswith("INSERT INTO professor_paper_link"):
            return FakeCursor(rowcount=self._upsert_link(params))
        if compact_sql.startswith("INSERT INTO paper_merge_alias"):
            old_paper_id = params["old_paper_id"]
            self.aliases[old_paper_id] = params["canonical_paper_id"]
            return FakeCursor(
                rows=[{"alias_id": "dddddddd-dddd-dddd-dddd-dddddddddddd"}],
                rowcount=1,
            )
        if compact_sql.startswith("UPDATE professor_paper_link"):
            old_paper_id = params[2]
            count = 0
            for link in self.links:
                if (
                    link["paper_id"] == old_paper_id
                    and link["link_status"] != "rejected"
                ):
                    link["link_status"] = "rejected"
                    link["rejected_reason"] = params[0]
                    count += 1
            return FakeCursor(rowcount=count)
        if compact_sql.startswith("UPDATE paper"):
            old_paper_id = params[1]
            row = self.papers.get(old_paper_id)
            if row is None or row["paper_id"] == params[2]:
                return FakeCursor(rowcount=0)
            if row.get("identity_status") == "merged":
                return FakeCursor(rowcount=0)
            row["identity_status"] = "merged"
            row["quality_status"] = "rejected"
            row["run_id"] = params[0]
            return FakeCursor(rowcount=1)
        return FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def _candidate_groups(self) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in self.papers.values():
            title = str(row.get("title_clean") or "").strip().lower()
            if not title:
                continue
            if (row.get("identity_status") or "unverified") in {"rejected", "merged"}:
                continue
            groups.setdefault(title, []).append(row)
        result = []
        for title, rows in groups.items():
            authors = {
                str(row.get("authors_display") or "").strip().lower() for row in rows
            }
            if len(rows) > 1 and len(authors) == 1:
                result.append(
                    {
                        "t": title,
                        "pids": sorted(row["paper_id"] for row in rows),
                    }
                )
        return sorted(result, key=lambda row: row["t"])

    def _upsert_link(self, params: tuple[Any, ...]) -> int:
        professor_id = params[0]
        canonical_paper_id = params[1]
        existing = next(
            (
                link
                for link in self.links
                if link["professor_id"] == professor_id
                and link["paper_id"] == canonical_paper_id
            ),
            None,
        )
        if existing is None:
            self.links.append(
                {
                    "professor_id": professor_id,
                    "paper_id": canonical_paper_id,
                    "link_status": params[2],
                    "match_reason": params[6],
                }
            )
        else:
            existing["link_status"] = params[2]
            existing["match_reason"] = params[6]
        return 1


def _paper(paper_id: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "paper_id": paper_id,
        "title_clean": "Exact Duplicate Title",
        "title_raw": None,
        "authors_display": "Ada Lovelace, Grace Hopper",
        "doi": None,
        "arxiv_id": None,
        "openalex_id": None,
        "semantic_scholar_id": None,
        "abstract_clean": None,
        "summary_zh": None,
        "venue": None,
        "year": None,
        "identity_status": "unverified",
        "quality_status": "needs_enrichment",
        "canonical_source": "prof_page_only",
    }
    row.update(overrides)
    return row


def _link(paper_id: str, professor_id: str = "PROF-1") -> dict[str, Any]:
    return {
        "link_id": f"LINK-{paper_id}",
        "professor_id": professor_id,
        "paper_id": paper_id,
        "link_status": "verified",
        "evidence_source_type": "prof_homepage_tier2",
        "evidence_page_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "evidence_api_source": None,
        "match_reason": "official_homepage_publication",
        "author_name_match_score": "0.95",
        "topic_consistency_score": None,
        "institution_consistency_score": None,
        "is_officially_listed": True,
    }


def test_pick_canonical_prefers_identifier_bearing_member() -> None:
    cli = _import_cli()

    canonical = cli._pick_canonical_member(
        [
            _paper(
                "PAPER-RICH",
                abstract_clean="abstract",
                summary_zh="summary",
                venue="Journal",
                year=2025,
            ),
            _paper("PAPER-DOI", doi="10.1145/example"),
        ]
    )

    assert canonical["paper_id"] == "PAPER-DOI"


def test_pick_canonical_tie_breaks_by_richest_fields_then_lowest_id() -> None:
    cli = _import_cli()

    richest = cli._pick_canonical_member(
        [
            _paper("PAPER-2", abstract_clean="abstract"),
            _paper("PAPER-3", abstract_clean="abstract", venue="Journal"),
            _paper("PAPER-1"),
        ]
    )
    final_tie = cli._pick_canonical_member(
        [
            _paper("PAPER-2", abstract_clean="abstract"),
            _paper("PAPER-1", abstract_clean="abstract"),
        ]
    )

    assert richest["paper_id"] == "PAPER-3"
    assert final_tie["paper_id"] == "PAPER-1"


def test_candidate_query_excludes_merged_rows_from_groups() -> None:
    cli = _import_cli()
    conn = FakeConnection(
        papers=[
            _paper("PAPER-A"),
            _paper("PAPER-B", identity_status="merged"),
            _paper("PAPER-C"),
        ]
    )

    groups = cli._fetch_candidate_groups(conn, limit=None)

    compact_sql = " ".join(conn.statements[0][0].split())
    assert "NOT IN ('rejected','merged')" in compact_sql
    assert groups == [{"t": "exact duplicate title", "pids": ["PAPER-A", "PAPER-C"]}]


def test_dry_run_reports_planned_merges_without_write_statements() -> None:
    cli = _import_cli()
    conn = FakeConnection(
        papers=[
            _paper("PAPER-CANON", doi="10.1145/example"),
            _paper("PAPER-OLD"),
        ]
    )

    groups = cli._fetch_candidate_groups(conn, limit=50)
    report = cli._process_candidate_groups(
        conn,
        groups,
        dry_run=True,
        run_id="dry-run-test",
    )

    assert report["mode"] == "dry-run"
    assert report["groups_total"] == 1
    assert report["rows_total"] == 2
    assert report["groups_processed"] == 1
    assert report["members_merged"] == 1
    assert report["false_merge_count"] == 0
    assert not any(
        sql.lstrip().startswith(("INSERT", "UPDATE")) for sql, _ in conn.statements
    )


def test_merge_helper_migrates_links_before_rejecting_old_links() -> None:
    from src.data_agents.paper.dedup_merge import merge_paper_into_canonical

    conn = FakeConnection(
        papers=[_paper("PAPER-CANON"), _paper("PAPER-OLD")],
        links=[_link("PAPER-OLD", professor_id="PROF-OLD")],
    )

    result = merge_paper_into_canonical(
        conn,
        old_paper_id="PAPER-OLD",
        canonical_paper_id="PAPER-CANON",
        run_id=_RUN_ID,
    )

    migrate_index = next(
        index
        for index, (sql, _params) in enumerate(conn.statements)
        if "INSERT INTO professor_paper_link" in sql
    )
    reject_index = next(
        index
        for index, (sql, _params) in enumerate(conn.statements)
        if "UPDATE professor_paper_link" in sql
    )
    paper_update_sql = next(
        sql for sql, _params in conn.statements if "UPDATE paper" in sql
    )
    reject_params = conn.statements[reject_index][1]

    assert result == {
        "links_migrated": 1,
        "merge_aliases_written": 1,
        "old_links_rejected": 1,
        "papers_marked_merged": 1,
        "ready_degraded": 0,
    }
    assert migrate_index < reject_index
    assert reject_params[0] == "merged_into_canonical:PAPER-CANON"
    assert "canonical_source" not in paper_update_sql


def test_merge_helper_second_call_is_no_op_after_old_member_is_merged() -> None:
    from src.data_agents.paper.dedup_merge import merge_paper_into_canonical

    conn = FakeConnection(
        papers=[_paper("PAPER-CANON"), _paper("PAPER-OLD")],
        links=[_link("PAPER-OLD", professor_id="PROF-OLD")],
    )

    merge_paper_into_canonical(
        conn,
        old_paper_id="PAPER-OLD",
        canonical_paper_id="PAPER-CANON",
        run_id=_RUN_ID,
    )
    second = merge_paper_into_canonical(
        conn,
        old_paper_id="PAPER-OLD",
        canonical_paper_id="PAPER-CANON",
        run_id=_RUN_ID,
    )

    assert second == {
        "links_migrated": 0,
        "merge_aliases_written": 0,
        "old_links_rejected": 0,
        "papers_marked_merged": 0,
        "ready_degraded": 0,
    }
