from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import scripts.run_quality_promote as promote

# A canonical Chinese biography (200-300 chars, CJK-dominant) that satisfies the
# profile_summary contract so evaluate_professor returns "ready".
_ZH_PROFILE_SUMMARY = (
    "该教师长期从事人工智能与医学影像分析研究，聚焦脑疾病诊断、预后评估和多模态数据融合。"
    "其工作结合深度学习、可信人工智能和临床应用场景，形成了较稳定的研究方向。"
    "相关成果服务于智能医疗系统建设，并在人才培养和科研合作中持续积累影响。"
    "近年的研究强调算法可靠性、模型解释性和真实临床数据验证，能够为深圳高校的交叉学科布局提供支撑。"
    "团队也关注医学数据治理和跨院校协作，推动算法从实验室验证走向可审计的真实应用，并形成稳定成果。"
)


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
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_table = rows_by_table
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if " FROM professor " in compact_sql:
            return FakeCursor(rows=self.rows_by_table.get("professor", []))
        if " FROM company " in compact_sql:
            return FakeCursor(rows=self.rows_by_table.get("company", []))
        if " FROM paper " in compact_sql:
            return FakeCursor(rows=self.rows_by_table.get("paper", []))
        if compact_sql.startswith("UPDATE "):
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            return FakeCursor(rowcount=1)
        return FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _install_pipeline_run_mocks(monkeypatch: Any) -> list[tuple[UUID, dict[str, Any]]]:
    run_id = UUID("11111111-1111-1111-1111-111111111111")
    closed: list[tuple[UUID, dict[str, Any]]] = []
    monkeypatch.setattr(promote, "open_pipeline_run", lambda conn, **kwargs: run_id)
    monkeypatch.setattr(promote, "require_real_run_id", lambda value, **kwargs: value)
    monkeypatch.setattr(
        promote,
        "close_pipeline_run",
        lambda conn, value, **kwargs: closed.append((value, kwargs)),
    )
    return closed


def test_paper_select_defaults_identity_unverified_when_v020_missing() -> None:
    sql, params = promote._build_select_sql(
        promote.DOMAIN_CONFIGS["paper"],
        3,
        paper_identity_status_available=False,
    )

    assert "'unverified'::text AS identity_status" in sql
    assert "identity_status" not in sql.split(" FROM ")[0].replace(
        "'unverified'::text AS identity_status", ""
    )
    assert params == (3,)


def test_dry_run_summary_uses_no_writes(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    conn = FakeConnection(
        {
            "professor": [
                {
                    "professor_id": "p1",
                    "identity_status": "confirmed",
                    "profile_summary": _ZH_PROFILE_SUMMARY,
                }
            ],
            "company": [
                {
                    "company_id": "c1",
                    "profile_summary": "x" * 120,
                    "technology_route_summary": None,
                }
            ],
            "paper": [
                {
                    "paper_id": "pa1",
                    "summary_zh": None,
                    "abstract_clean": None,
                    "identity_status": "unverified",
                }
            ],
        }
    )
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://example/test")
    monkeypatch.setattr(promote, "_open_database_connection", lambda dsn: conn)

    promote.main(["--domain", "all", "--dry-run", "--limit", "10"])

    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["totals"]["scanned"] == 3
    assert report["totals"]["ready"] == 1
    assert report["totals"]["needs_review"] == 2
    assert report["totals"]["pipeline_issues"] == 1
    assert report["totals"]["updated"] == 0
    assert not any("UPDATE " in sql for sql, _params in conn.statements)
    assert not any(
        "INSERT INTO pipeline_issue" in sql for sql, _params in conn.statements
    )
    assert conn.closed is True


def test_actual_run_updates_ready_rows(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    conn = FakeConnection(
        {
            "professor": [
                {
                    "professor_id": "p1",
                    "identity_status": "confirmed",
                    "profile_summary": _ZH_PROFILE_SUMMARY,
                }
            ]
        }
    )
    closed = _install_pipeline_run_mocks(monkeypatch)
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://example/test")
    monkeypatch.setattr(promote, "_open_database_connection", lambda dsn: conn)

    promote.main(["--domain", "professor"])

    report = json.loads(capsys.readouterr().out)
    assert report["totals"]["updated"] == 1
    update_statements = [
        (sql, params) for sql, params in conn.statements if "UPDATE professor" in sql
    ]
    assert len(update_statements) == 1
    assert update_statements[0][1] == (
        "ready",
        UUID("11111111-1111-1111-1111-111111111111"),
        "p1",
    )
    assert closed[0][1]["status"] == "succeeded"
    assert conn.rollbacks == 0
    assert conn.closed is True


def test_actual_run_inserts_pipeline_issue(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    conn = FakeConnection(
        {
            "company": [
                {
                    "company_id": "c1",
                    "profile_summary": "x" * 120,
                    "technology_route_summary": None,
                }
            ]
        }
    )
    _install_pipeline_run_mocks(monkeypatch)
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://example/test")
    monkeypatch.setattr(promote, "_open_database_connection", lambda dsn: conn)

    promote.main(["--domain", "company"])

    report = json.loads(capsys.readouterr().out)
    assert report["totals"]["updated"] == 0
    assert report["totals"]["pipeline_issues"] == 1
    issue_statements = [
        (sql, params)
        for sql, params in conn.statements
        if "INSERT INTO pipeline_issue" in sql
    ]
    assert len(issue_statements) == 1
    assert issue_statements[0][1][0] is None
    assert issue_statements[0][1][1] == "company:c1"
    assert "company_partial_narrative" in issue_statements[0][1][2]
    snapshot = json.loads(issue_statements[0][1][3])
    assert snapshot["domain"] == "company"
    assert snapshot["record_id"] == "c1"
    assert snapshot["issue_code"] == "company_partial_narrative"
