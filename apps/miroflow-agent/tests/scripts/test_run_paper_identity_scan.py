from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_paper_identity_scan.py"
_TEST_DSN = (
    "postgresql+psycopg://miroflow:secret-password@localhost:15432/"
    "miroflow_test_mock"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("run_paper_identity_scan", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(
        self,
        *,
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
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.papers = {
            row["paper_id"]: {
                "identity_status": row["identity_status"],
                "quality_status": row["quality_status"],
                "run_id": None,
            }
            for row in rows
        }
        self.link_statuses = {row["link_id"]: row["link_status"] for row in rows}
        self.issues: list[dict[str, Any]] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if "FROM paper p" in compact_sql and "JOIN professor_paper_link" in compact_sql:
            return FakeCursor(rows=self.rows)
        if "SELECT identity_status, quality_status FROM paper" in compact_sql:
            return FakeCursor(rows=[self.papers[str(params[0])]])
        if "FROM pipeline_issue" in compact_sql and "resolved = false" in compact_sql:
            paper_id = str(params[0])
            rows = [
                issue
                for issue in self.issues
                if not issue["resolved"]
                and issue["evidence_snapshot"]["paper_id"] == paper_id
            ]
            return FakeCursor(rows=rows[:1])
        if (
            "FROM professor_paper_link" in compact_sql
            and "JOIN professor" in compact_sql
        ):
            paper_id = str(params[0])
            row = next(row for row in self.rows if row["paper_id"] == paper_id)
            return FakeCursor(
                rows=[
                    {
                        "link_id": row["link_id"],
                        "professor_id": row["professor_id"],
                        "institution": row["institution"],
                    }
                ]
            )
        if compact_sql.startswith("UPDATE professor_paper_link"):
            link_id = str(params[-1])
            if "link_status='verified'" in compact_sql:
                self.link_statuses[link_id] = "verified"
            elif "link_status='rejected'" in compact_sql:
                self.link_statuses[link_id] = "rejected"
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("UPDATE paper"):
            if "identity_status = 'rejected'" in compact_sql:
                run_id, paper_id = params
                paper = self.papers[str(paper_id)]
                if paper["identity_status"] == "rejected":
                    return FakeCursor(rowcount=0)
                paper["identity_status"] = "rejected"
                paper["run_id"] = str(run_id)
                return FakeCursor(rowcount=1)
            restored_status, paper_id = params
            paper = self.papers[str(paper_id)]
            if paper["identity_status"] != "rejected":
                return FakeCursor(rowcount=0)
            paper["identity_status"] = str(restored_status)
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            snapshot = json.loads(str(params[4]))
            self.issues.append(
                {
                    "issue_id": f"ISSUE-{len(self.issues) + 1}",
                    "stage": "identity_gate",
                    "evidence_snapshot": snapshot,
                    "resolved": False,
                }
            )
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("UPDATE pipeline_issue"):
            issue_id = params[2]
            for issue in self.issues:
                if issue["issue_id"] == issue_id:
                    issue["resolved"] = True
                    return FakeCursor(rowcount=1)
            return FakeCursor(rowcount=0)
        return FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _row(
    *,
    paper_id: str,
    link_id: str,
    title: str,
    professor_id: str,
    link_status: str = "verified",
    identity_status: str = "unverified",
    quality_status: str = "ready",
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "title_clean": title,
        "authors_display": "Ada Lovelace, Grace Hopper",
        "year": 2024,
        "venue": "TestConf",
        "abstract_clean": "A deterministic test abstract.",
        "canonical_source": "prof_page_only",
        "identity_status": identity_status,
        "quality_status": quality_status,
        "link_id": link_id,
        "link_status": link_status,
        "professor_id": professor_id,
        "canonical_name": f"Professor {professor_id}",
        "institution": "SUSTech",
        "department": "Computer Science",
        "research_directions": ["AI"],
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _patch_runtime(
    module,
    monkeypatch: pytest.MonkeyPatch,
    *,
    conn: FakeConnection,
    gate_calls: list[int],
) -> None:
    monkeypatch.setattr(module, "resolve_dsn", lambda _url=None: _TEST_DSN)
    monkeypatch.setattr(
        module,
        "_build_llm_settings",
        lambda _profile, _online: (object(), "test-model"),
    )
    monkeypatch.setattr(module.psycopg, "connect", lambda *_a, **_kw: conn)
    monkeypatch.setattr(
        module,
        "open_pipeline_run",
        lambda *_a, **_kw: "33333333-3333-3333-3333-333333333333",
    )
    monkeypatch.setattr(module, "close_pipeline_run", lambda *_a, **_kw: None)

    async def fake_batch_verify_paper_identity(**kwargs):
        gate_calls.append(len(kwargs["candidates"]))
        out = []
        for candidate in kwargs["candidates"]:
            accepted = "keep" in candidate.title
            out.append(
                SimpleNamespace(
                    index=candidate.index,
                    accepted=accepted,
                    confidence=0.91 if accepted else 0.12,
                    reasoning="same person" if accepted else "same name, different person",
                    topic_consistency=0.8 if accepted else 0.1,
                    error=None,
                )
            )
        return out

    monkeypatch.setattr(module, "batch_verify_paper_identity", fake_batch_verify_paper_identity)


def _run_main(module, monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(module.sys, "argv", ["run_paper_identity_scan.py", *argv])
    return module.main()


def test_scan_dry_run_apply_and_flag_off(tmp_path, monkeypatch) -> None:
    module = _load_module()
    rows = [
        _row(
            paper_id="PAPER-REJECT",
            link_id="11111111-1111-1111-1111-111111111111",
            title="reject this attribution",
            professor_id="PROF-1",
        ),
        _row(
            paper_id="PAPER-KEEP",
            link_id="22222222-2222-2222-2222-222222222222",
            title="reject first attribution",
            professor_id="PROF-2",
        ),
        _row(
            paper_id="PAPER-KEEP",
            link_id="33333333-3333-3333-3333-333333333333",
            title="keep second attribution",
            professor_id="PROF-3",
        ),
    ]

    monkeypatch.setenv("PAPER_IDENTITY_GATE_ENABLED", "1")
    dry_conn = FakeConnection(rows)
    dry_gate_calls: list[int] = []
    _patch_runtime(module, monkeypatch, conn=dry_conn, gate_calls=dry_gate_calls)
    dry_output = tmp_path / "dry.jsonl"

    assert _run_main(
        module,
        monkeypatch,
        ["--database-url", _TEST_DSN, "--json-output", str(dry_output)],
    ) == 0

    assert dry_gate_calls
    assert dry_conn.papers["PAPER-REJECT"]["identity_status"] == "unverified"
    assert dry_conn.issues == []
    dry_records = _read_jsonl(dry_output)
    dry_summary = dry_records[-1]
    assert dry_summary["summary"] is True
    assert dry_summary["apply_mode"] is False
    assert dry_summary["examined"] == 2
    assert dry_summary["rejected"] == 1
    assert dry_summary["unchanged"] == 1
    assert {record["paper_id"]: record["action_taken"] for record in dry_records[:-1]} == {
        "PAPER-REJECT": "would_reject",
        "PAPER-KEEP": "none",
    }

    apply_conn = FakeConnection(rows)
    apply_gate_calls: list[int] = []
    _patch_runtime(module, monkeypatch, conn=apply_conn, gate_calls=apply_gate_calls)
    apply_output = tmp_path / "apply.jsonl"

    assert _run_main(
        module,
        monkeypatch,
        [
            "--database-url",
            _TEST_DSN,
            "--apply",
            "--json-output",
            str(apply_output),
        ],
    ) == 0

    assert apply_conn.papers["PAPER-REJECT"]["identity_status"] == "rejected"
    assert apply_conn.papers["PAPER-KEEP"]["identity_status"] == "unverified"
    assert len(apply_conn.issues) == 1
    assert apply_conn.issues[0]["evidence_snapshot"]["run_id"] == (
        "33333333-3333-3333-3333-333333333333"
    )
    apply_summary = _read_jsonl(apply_output)[-1]
    assert apply_summary["apply_mode"] is True
    assert apply_summary["rejected"] == 1
    assert apply_summary["unchanged"] == 1

    monkeypatch.setenv("PAPER_IDENTITY_GATE_ENABLED", "0")
    module = _load_module()
    monkeypatch.setattr(module, "resolve_dsn", lambda _url=None: _TEST_DSN)
    monkeypatch.setattr(
        module.psycopg,
        "connect",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("DB should not open")),
    )
    monkeypatch.setattr(
        module,
        "batch_verify_paper_identity",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("gate should not run")),
    )
    disabled_output = tmp_path / "disabled.jsonl"

    assert _run_main(
        module,
        monkeypatch,
        ["--database-url", _TEST_DSN, "--json-output", str(disabled_output)],
    ) == 0
    disabled_records = _read_jsonl(disabled_output)
    assert disabled_records == [{"summary": True, "disabled": True, "examined": 0}]
