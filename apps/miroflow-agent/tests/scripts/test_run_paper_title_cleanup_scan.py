from __future__ import annotations

import json
import os
from typing import Any

from scripts.run_paper_title_cleanup_scan import (
    _ScanRow,
    _scan_rows,
    _title_cleanup_enabled,
)


class _FakeCursor:
    def __init__(self, *, rows=None, rowcount=0):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConnection:
    """Minimal conn double covering the apply-identity-status-rejection path."""

    def __init__(self):
        self.paper: dict[str, dict[str, Any]] = {}
        self.link_target = {
            "paper_id": "PAPER-1",
            "link_id": "11111111-1111-1111-1111-111111111111",
            "professor_id": "PROF-1",
            "institution": "SUSTech",
        }
        self.issues: list[dict[str, Any]] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if "SELECT identity_status, quality_status FROM paper" in compact_sql:
            return _FakeCursor(rows=[self.paper[str(params[0])]])
        if "FROM pipeline_issue" in compact_sql and "resolved = false" in compact_sql:
            paper_id = str(params[0])
            stage_filter = params[1] if len(params) > 1 else None
            reported_by_filter = params[2] if len(params) > 2 else None
            rows = [
                issue
                for issue in self.issues
                if not issue["resolved"]
                and issue["evidence_snapshot"]["paper_id"] == paper_id
                and (stage_filter is None or issue["stage"] == stage_filter)
                and (
                    reported_by_filter is None
                    or issue["reported_by"] == reported_by_filter
                )
            ]
            return _FakeCursor(rows=rows[:1])
        if "FROM professor_paper_link" in compact_sql:
            return _FakeCursor(rows=[self.link_target])
        if compact_sql.startswith("UPDATE paper"):
            if "SET identity_status = 'rejected'" in compact_sql:
                run_id, paper_id = params
                paper = self.paper[str(paper_id)]
                if paper["identity_status"] == "rejected":
                    return _FakeCursor(rowcount=0)
                paper["identity_status"] = "rejected"
                paper["run_id"] = str(run_id)
                return _FakeCursor(rowcount=1)
            restored_status, paper_id = params
            paper = self.paper[str(paper_id)]
            if paper["identity_status"] != "rejected":
                return _FakeCursor(rowcount=0)
            paper["identity_status"] = str(restored_status)
            return _FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            stage = params[3]
            snapshot = json.loads(str(params[5]))
            if any(
                not issue["resolved"]
                and issue["stage"] == stage
                and issue["evidence_snapshot"]["paper_id"] == snapshot["paper_id"]
                for issue in self.issues
            ):
                return _FakeCursor(rowcount=0)
            self.issues.append(
                {
                    "issue_id": "ISSUE-1",
                    "professor_id": params[0],
                    "link_id": params[1],
                    "institution": params[2],
                    "stage": stage,
                    "severity": "medium",
                    "description": params[4],
                    "evidence_snapshot": snapshot,
                    "reported_by": params[6],
                    "resolved": False,
                }
            )
            return _FakeCursor(rowcount=1)
        return _FakeCursor()


def _conn_with(*paper_ids: str) -> _FakeConnection:
    conn = _FakeConnection()
    for pid in paper_ids:
        conn.paper[pid] = {
            "identity_status": "unverified",
            "quality_status": "needs_enrichment",
            "run_id": None,
        }
    return conn


def test_scan_apply_rejects_implausible_titles_and_leaves_plausible() -> None:
    conn = _conn_with("PAPER-GARBAGE", "PAPER-REAL")
    rows = [
        _ScanRow(
            "PAPER-GARBAGE",
            "Co-supervised PhD student",
            "prof_page_only",
            "unverified",
            "needs_enrichment",
        ),
        _ScanRow(
            "PAPER-REAL",
            "Deep Reinforcement Learning for Robotic Manipulation",
            "prof_page_only",
            "unverified",
            "needs_enrichment",
        ),
    ]

    stats = _scan_rows(
        conn,
        rows=rows,
        apply_mode=True,
        run_id="44444444-4444-4444-4444-444444444444",
        jsonl_handle=None,
        json_output_path=None,
        scan_started_at="2026-06-22T00:00:00Z",
    )

    assert stats.examined == 2
    assert stats.rejected == 1
    assert stats.unchanged == 1
    assert stats.identity_updates == 1
    assert stats.issues_filed == 1
    # garbage title -> rejected at title_cleanup stage; quality_status untouched
    assert conn.paper["PAPER-GARBAGE"]["identity_status"] == "rejected"
    assert conn.paper["PAPER-GARBAGE"]["quality_status"] == "needs_enrichment"
    # plausible title -> unchanged
    assert conn.paper["PAPER-REAL"]["identity_status"] == "unverified"
    # the filed issue is at the title_cleanup stage / reporter, distinct from W0b
    assert any(
        issue["stage"] == "identity_gate"
        and issue["reported_by"] == "paper_title_cleanup_scan"
        for issue in conn.issues
    )


def test_scan_dry_run_makes_no_writes() -> None:
    conn = _conn_with("PAPER-GARBAGE")
    rows = [
        _ScanRow(
            "PAPER-GARBAGE",
            "Not explicitly provided in text (Ref: Xu, W.; Arieno, M.; Low, H.)",
            "prof_page_only",
            "unverified",
            "needs_enrichment",
        )
    ]

    stats = _scan_rows(
        conn,
        rows=rows,
        apply_mode=False,
        run_id="dry-run-x",
        jsonl_handle=None,
        json_output_path=None,
        scan_started_at="2026-06-22T00:00:00Z",
    )

    assert stats.rejected == 1
    assert stats.identity_updates == 0
    assert stats.issues_filed == 0
    # dry-run writes nothing
    assert conn.paper["PAPER-GARBAGE"]["identity_status"] == "unverified"
    assert conn.issues == []


def test_scan_handles_empty_row_set() -> None:
    # _load_rows filters identity_status NOT IN ('rejected','merged'); an
    # already-rejected paper would not be loaded, so _scan_rows sees no rows.
    conn = _conn_with()

    stats = _scan_rows(
        conn,
        rows=[],
        apply_mode=True,
        run_id="r",
        jsonl_handle=None,
        json_output_path=None,
        scan_started_at="t",
    )

    assert stats.examined == 0
    assert stats.rejected == 0
    assert stats.issues_filed == 0


def test_title_cleanup_flag_defaults_off_and_toggles() -> None:
    os.environ.pop("PAPER_TITLE_CLEANUP_ENABLED", None)
    assert _title_cleanup_enabled() is False
    os.environ["PAPER_TITLE_CLEANUP_ENABLED"] = "1"
    try:
        assert _title_cleanup_enabled() is True
    finally:
        os.environ.pop("PAPER_TITLE_CLEANUP_ENABLED", None)


def test_is_clearly_garbage_paper_title_spares_real_and_catches_garbage() -> None:
    from src.data_agents.paper.title_quality import is_clearly_garbage_paper_title

    real_titles = [
        "Deep Reinforcement Learning for Robotic Manipulation Tasks",
        "Kinetic Modeling and Reaction Engineering",
        "Prototype filter design to minimize stopband energy with constraint on channel",
        "Communication-Efficient Distributed Covariance Sketch, with Application to Networks",
    ]
    for title in real_titles:
        assert is_clearly_garbage_paper_title(title) is False, title

    garbage_titles = [
        "Co-supervised PhD student",
        "Not explicitly provided in text (Ref: Xu, W.; Arieno, M.; Low, H.)",
        "Acta pharmaceutica Sinica B 2023;13:4840-4855. (IF=14.7)",
        "Nanoscale",
        "基于边缘重构的热红外行人检测方法、系统及存储介质",
        "Yufeng Song, Kaixi You, Yunxiang Chen, Jinlai Zhao",
    ]
    for title in garbage_titles:
        assert is_clearly_garbage_paper_title(title) is True, title
