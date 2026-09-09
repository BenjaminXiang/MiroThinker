from __future__ import annotations

import json
from typing import Any

from scripts.run_paper_shell_residual_mark import (
    ResidualShellRow,
    mark_residual_shells,
)


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeResidualConnection:
    def __init__(self) -> None:
        self.paper_rows: list[dict[str, Any]] = [
            {
                "paper_id": "PAPER-UNRESOLVED-1",
                "title_clean": "Unresolved Shell One",
                "canonical_source": "prof_page_only",
                "abstract_clean": None,
                "quality_status": "needs_enrichment",
                "summary_zh": None,
                "identity_status": "unverified",
            },
            {
                "paper_id": "PAPER-UNRESOLVED-2",
                "title_clean": "Unresolved Shell Two",
                "canonical_source": "prof_page_only",
                "abstract_clean": "   ",
                "quality_status": "needs_review",
                "summary_zh": None,
                "identity_status": "unverified",
            },
            {
                "paper_id": "PAPER-RESOLVED",
                "title_clean": "Resolved Paper",
                "canonical_source": "prof_page_only",
                "abstract_clean": "Resolved abstract.",
                "quality_status": "ready",
                "summary_zh": "已有摘要",
                "identity_status": "resolved",
            },
            {
                "paper_id": "PAPER-CROSSREF",
                "title_clean": "Crossref Paper",
                "canonical_source": "crossref",
                "abstract_clean": None,
                "quality_status": "needs_enrichment",
                "summary_zh": None,
                "identity_status": "resolved",
            },
        ]
        self.links: list[dict[str, Any]] = [
            {"paper_id": "PAPER-UNRESOLVED-1", "professor_id": "PROF-A"},
            {"paper_id": "PAPER-UNRESOLVED-2", "professor_id": "PROF-B"},
            {"paper_id": "PAPER-RESOLVED", "professor_id": "PROF-C"},
            {"paper_id": "PAPER-CROSSREF", "professor_id": "PROF-D"},
        ]
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split()).lower()
        assert compact_sql.startswith("select ")
        assert "update paper" not in compact_sql
        assert "insert into pipeline_issue" not in compact_sql

        rows: list[dict[str, Any]] = []
        for paper in self.paper_rows:
            if paper["canonical_source"] != "prof_page_only":
                continue
            abstract = str(paper["abstract_clean"] or "").strip()
            if abstract:
                continue
            for link in self.links:
                if link["paper_id"] == paper["paper_id"]:
                    rows.append(
                        {
                            "paper_id": paper["paper_id"],
                            "title_clean": paper["title_clean"],
                            "professor_id": link["professor_id"],
                        }
                    )
        rows.sort(key=lambda row: (row["paper_id"], row["professor_id"]))
        if params:
            rows = rows[: int(params[0])]
        return _FakeCursor(rows)


def test_residual_marker_lists_only_unresolved_prof_page_shells(tmp_path) -> None:
    conn = _FakeResidualConnection()
    output = tmp_path / "residual.jsonl"

    stats = mark_residual_shells(
        conn,
        output_path=output,
        limit=10,
        run_id="stage-a-run",
    )

    assert stats.residual_count == 2
    assert output.read_text(encoding="utf-8").splitlines() == [
        json.dumps(
            {
                "paper_id": "PAPER-UNRESOLVED-1",
                "title_clean": "Unresolved Shell One",
                "professor_id": "PROF-A",
                "run_id": "stage-a-run",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "paper_id": "PAPER-UNRESOLVED-2",
                "title_clean": "Unresolved Shell Two",
                "professor_id": "PROF-B",
                "run_id": "stage-a-run",
            },
            ensure_ascii=False,
        ),
    ]


def test_residual_marker_is_bounded_and_does_not_mutate_quality_or_summary(
    tmp_path,
) -> None:
    conn = _FakeResidualConnection()
    before = [row.copy() for row in conn.paper_rows]
    output = tmp_path / "bounded.jsonl"

    stats = mark_residual_shells(
        conn,
        output_path=output,
        limit=1,
        run_id=None,
    )

    records = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert stats.residual_count == 1
    assert records == [
        {
            "paper_id": "PAPER-UNRESOLVED-1",
            "title_clean": "Unresolved Shell One",
            "professor_id": "PROF-A",
            "run_id": None,
        }
    ]
    assert conn.paper_rows == before
    assert all(
        not sql.lstrip().lower().startswith(("update", "insert", "delete"))
        for sql, _params in conn.statements
    )


def test_residual_shell_row_payload_preserves_required_fields() -> None:
    row = ResidualShellRow(
        paper_id="PAPER-X",
        title_clean="Residual Title",
        professor_id="PROF-X",
    )

    assert row.to_json_record(run_id="run-x") == {
        "paper_id": "PAPER-X",
        "title_clean": "Residual Title",
        "professor_id": "PROF-X",
        "run_id": "run-x",
    }
