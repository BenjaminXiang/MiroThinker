from __future__ import annotations

import json
from typing import Any


class FakeCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self) -> None:
        self.paper = {
            "PAPER-1": {
                "identity_status": "unverified",
                "quality_status": "ready",
                "run_id": None,
            }
        }
        self.link_target = {
            "paper_id": "PAPER-1",
            "link_id": "11111111-1111-1111-1111-111111111111",
            "professor_id": "PROF-1",
            "institution": "SUSTech",
        }
        self.issues: list[dict[str, Any]] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if "SELECT identity_status, quality_status FROM paper" in compact_sql:
            paper_id = str(params[0])
            return FakeCursor(rows=[self.paper[paper_id]])
        if "FROM pipeline_issue" in compact_sql and "resolved = false" in compact_sql:
            paper_id = str(params[0])
            rows = [
                issue
                for issue in self.issues
                if not issue["resolved"]
                and issue["stage"] == "identity_gate"
                and issue["evidence_snapshot"]["paper_id"] == paper_id
            ]
            return FakeCursor(rows=rows[:1])
        if "FROM professor_paper_link" in compact_sql:
            return FakeCursor(rows=[self.link_target])
        if compact_sql.startswith("UPDATE paper"):
            if "SET identity_status = 'rejected'" in compact_sql:
                run_id, paper_id = params
                paper = self.paper[str(paper_id)]
                if paper["identity_status"] == "rejected":
                    return FakeCursor(rowcount=0)
                paper["identity_status"] = "rejected"
                paper["run_id"] = str(run_id)
                return FakeCursor(rowcount=1)
            restored_status, paper_id = params
            paper = self.paper[str(paper_id)]
            if paper["identity_status"] != "rejected":
                return FakeCursor(rowcount=0)
            paper["identity_status"] = str(restored_status)
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            snapshot = json.loads(str(params[4]))
            if any(
                not issue["resolved"]
                and issue["stage"] == "identity_gate"
                and issue["evidence_snapshot"]["paper_id"] == snapshot["paper_id"]
                for issue in self.issues
            ):
                return FakeCursor(rowcount=0)
            self.issues.append(
                {
                    "issue_id": "ISSUE-1",
                    "professor_id": params[0],
                    "link_id": params[1],
                    "institution": params[2],
                    "stage": "identity_gate",
                    "severity": "medium",
                    "description": params[3],
                    "evidence_snapshot": snapshot,
                    "reported_by": params[5],
                    "resolved": False,
                }
            )
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("UPDATE pipeline_issue"):
            issue_id = params[2]
            for issue in self.issues:
                if issue["issue_id"] == issue_id and not issue["resolved"]:
                    issue["resolved"] = True
                    issue["resolution_notes"] = params[0]
                    issue["resolution_round"] = params[1]
                    return FakeCursor(rowcount=1)
            return FakeCursor(rowcount=0)
        return FakeCursor()


def test_decide_reject_only_when_no_verified_link_and_prof_page_only() -> None:
    from src.data_agents.paper.identity_status_writer import (
        decide_identity_status_rejection,
    )

    plausible_title = "Deep Reinforcement Learning for Robotic Manipulation Tasks"

    # All three conditions met -> reject.
    assert (
        decide_identity_status_rejection(
            has_verified_link=False,
            canonical_source="prof_page_only",
            title_clean=plausible_title,
        ).action
        == "reject"
    )
    # A verified link remains -> no_change.
    assert (
        decide_identity_status_rejection(
            has_verified_link=True,
            canonical_source="prof_page_only",
            title_clean=plausible_title,
        ).action
        == "no_change"
    )
    # Not prof-page-only -> no_change.
    assert (
        decide_identity_status_rejection(
            has_verified_link=False,
            canonical_source="openalex",
            title_clean=plausible_title,
        ).action
        == "no_change"
    )


def test_decide_no_change_for_garbage_title() -> None:
    from src.data_agents.paper.identity_status_writer import (
        decide_identity_status_rejection,
    )

    # Parser-garbage title (root cause C2/C3): no verified link + prof_page_only,
    # but the title is implausible -> must NOT be mislabeled rejected; left unverified.
    for garbage in ("no.", "等。", "（ IF: 15.1 ）", ""):
        decision = decide_identity_status_rejection(
            has_verified_link=False,
            canonical_source="prof_page_only",
            title_clean=garbage,
        )
        assert decision.action == "no_change", garbage
        assert decision.reason == "implausible_title", garbage


def test_apply_rejection_sets_identity_status_and_files_issue_without_terminalizing_quality(
) -> None:
    from src.data_agents.paper.identity_status_writer import (
        apply_identity_status_rejection,
    )

    conn = FakeConnection()
    run_id = "22222222-2222-2222-2222-222222222222"
    evidence = {
        "confidence": 0.13,
        "reasoning": "same name but topic and coauthors do not match",
        "source_spans": [{"url": "https://example.edu/papers", "text": "paper row"}],
    }

    first = apply_identity_status_rejection(
        conn,
        paper_id="PAPER-1",
        run_id=run_id,
        evidence=evidence,
        prior_identity_status="unverified",
    )
    second = apply_identity_status_rejection(
        conn,
        paper_id="PAPER-1",
        run_id=run_id,
        evidence=evidence,
        prior_identity_status="rejected",
    )

    assert first.identity_updated is True
    assert first.issues_filed == 1
    assert second.identity_updated is False
    assert second.issues_filed == 0
    assert conn.paper["PAPER-1"]["identity_status"] == "rejected"
    assert conn.paper["PAPER-1"]["quality_status"] == "ready"
    assert len(conn.issues) == 1
    issue = conn.issues[0]
    assert issue["stage"] == "identity_gate"
    assert issue["evidence_snapshot"]["run_id"] == run_id
    assert issue["evidence_snapshot"]["paper_id"] == "PAPER-1"
    assert issue["evidence_snapshot"]["prior_identity_status"] == "unverified"
    assert issue["evidence_snapshot"]["gate_decision"] == evidence


def test_restore_returns_prior_identity_status_and_resolves_issue() -> None:
    from src.data_agents.paper.identity_status_writer import (
        apply_identity_status_rejection,
        restore_identity_status,
    )

    conn = FakeConnection()
    apply_identity_status_rejection(
        conn,
        paper_id="PAPER-1",
        run_id="22222222-2222-2222-2222-222222222222",
        evidence={"confidence": 0.1, "reasoning": "not same person"},
        prior_identity_status="unverified",
    )

    result = restore_identity_status(conn, paper_id="PAPER-1")

    assert result.restored is True
    assert result.prior_identity_status == "unverified"
    assert result.issues_resolved == 1
    assert conn.paper["PAPER-1"]["identity_status"] == "unverified"
    assert conn.paper["PAPER-1"]["quality_status"] == "ready"
    assert conn.issues[0]["resolved"] is True
