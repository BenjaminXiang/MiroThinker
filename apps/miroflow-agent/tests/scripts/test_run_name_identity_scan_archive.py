from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_name_identity_scan.py"
_TEST_DSN = (
    "postgresql+psycopg://miroflow:secret-password@localhost:15432/"
    "miroflow_test_mock"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("run_name_identity_scan", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.rollbacks = 0
        self.execute_calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def execute(self, sql: str, _params=None):
        self.execute_calls.append(sql)
        if "SELECT p.professor_id" in sql:
            return _FakeCursor(rows=self.rows)
        if "INSERT INTO pipeline_issue" in sql:
            return _FakeCursor(rowcount=1)
        if "UPDATE professor" in sql:
            return _FakeCursor(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")

    def rollback(self) -> None:
        self.rollbacks += 1


def _row(
    professor_id: str,
    *,
    canonical_name: str = "张三",
    canonical_name_en: str = "Zhang San",
    institution: str | None = "南方科技大学",
    source_url: str | None = "https://example.edu/profile",
) -> dict[str, object]:
    return {
        "professor_id": professor_id,
        "canonical_name": canonical_name,
        "canonical_name_en": canonical_name_en,
        "institution": institution,
        "source_url": source_url,
    }


def _decision(
    *,
    accepted: bool,
    confidence: float,
    reasoning: str = "",
    error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        accepted=accepted,
        confidence=confidence,
        reasoning=reasoning,
        error=error,
    )


def _patch_runtime(
    module,
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: list[dict[str, object]],
    decisions: list[SimpleNamespace],
    dsn: str = _TEST_DSN,
) -> _FakeConn:
    conn = _FakeConn(rows)
    monkeypatch.setattr(module, "resolve_dsn", lambda _url: dsn)
    monkeypatch.setattr(module, "_build_llm_settings", lambda: (object(), "test-model"))
    monkeypatch.setattr(module.psycopg, "connect", lambda *_a, **_kw: conn)
    monkeypatch.setattr(
        module,
        "batch_verify_name_identity",
        lambda _candidates, **_kw: decisions,
    )
    return conn


def _run_main(module, monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(module.sys, "argv", ["run_name_identity_scan.py", *argv])
    return module.main()


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_json_output_writes_per_professor_format(tmp_path, monkeypatch):
    module = _load_module()
    output = tmp_path / "scan.jsonl"
    _patch_runtime(
        module,
        monkeypatch,
        rows=[
            _row("PROF-1", canonical_name="张三", canonical_name_en="Zhang San"),
            _row("PROF-2", canonical_name="李四", canonical_name_en="Wang Wu"),
        ],
        decisions=[
            _decision(accepted=True, confidence=0.93, reasoning="拼音匹配"),
            _decision(accepted=False, confidence=0.12, reasoning="姓名不一致"),
        ],
    )

    code = _run_main(
        module,
        monkeypatch,
        [
            "--database-url",
            _TEST_DSN,
            "--apply",
            "--auto-clear-threshold",
            "0.5",
            "--json-output",
            str(output),
        ],
    )

    assert code == 0
    accepted, rejected, summary = _read_jsonl(output)
    assert accepted == {
        "professor_id": "PROF-1",
        "canonical_name": "张三",
        "canonical_name_en_before": "Zhang San",
        "institution": "南方科技大学",
        "source_url": "https://example.edu/profile",
        "decision": "accepted",
        "confidence": 0.93,
        "reason": "",
        "action_taken": "none",
        "apply_mode": True,
        "scan_started_at": accepted["scan_started_at"],
        "examined_index": 1,
    }
    assert accepted["scan_started_at"].endswith("Z")
    assert rejected["professor_id"] == "PROF-2"
    assert rejected["canonical_name_en_before"] == "Wang Wu"
    assert rejected["decision"] == "rejected"
    assert rejected["reason"] == "姓名不一致"
    assert rejected["action_taken"] == "issue_filed_and_name_en_cleared"
    assert rejected["apply_mode"] is True
    assert rejected["examined_index"] == 2
    assert summary["summary"] is True


def test_archive_uses_utc_filename_format(tmp_path, monkeypatch, capsys):
    module = _load_module()
    monkeypatch.setattr(module, "_ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(module, "_utc_date_slug", lambda: "2026-05-02")
    _patch_runtime(module, monkeypatch, rows=[], decisions=[])

    code = _run_main(module, monkeypatch, ["--database-url", _TEST_DSN, "--archive"])

    archive = tmp_path / "round-7-17-name-identity-clear-2026-05-02.jsonl"
    assert code == 0
    assert archive.exists()
    assert _read_jsonl(archive)[-1]["summary"] is True
    assert f"archived to {archive}" in capsys.readouterr().err


def test_archive_and_json_output_are_mutually_exclusive(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "run_name_identity_scan.py",
            "--archive",
            "--json-output",
            str(tmp_path / "scan.jsonl"),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        module._parse_args()

    assert exc.value.code == 2


def test_summary_line_format(tmp_path, monkeypatch):
    module = _load_module()
    output = tmp_path / "summary.jsonl"
    _patch_runtime(
        module,
        monkeypatch,
        rows=[_row("PROF-1"), _row("PROF-2")],
        decisions=[
            _decision(accepted=False, confidence=0.6, reasoning="低置信"),
            _decision(accepted=False, confidence=0.2, reasoning="姓名不一致"),
        ],
    )

    code = _run_main(
        module,
        monkeypatch,
        [
            "--database-url",
            _TEST_DSN,
            "--institution",
            "南方科技大学",
            "--auto-clear-threshold",
            "0.5",
            "--json-output",
            str(output),
        ],
    )

    summary = _read_jsonl(output)[-1]
    assert code == 0
    assert summary["summary"] is True
    assert summary["scan_started_at"].endswith("Z")
    assert summary["scan_finished_at"].endswith("Z")
    assert isinstance(summary["duration_seconds"], int)
    assert summary["institution_filter"] == "南方科技大学"
    assert summary["apply_mode"] is False
    assert summary["examined"] == 2
    assert summary["rejected"] == 2
    assert summary["issues_inserted"] == 0
    assert summary["clear_updates"] == 0
    assert summary["would_clear"] == 1
    assert summary["auto_clear_threshold"] == 0.5
    assert summary["database_dsn_host"] == "localhost:15432"
    assert summary["database_name"] == "miroflow_test_mock"


def test_json_output_appends_to_existing_file(tmp_path, monkeypatch):
    module = _load_module()
    output = tmp_path / "append.jsonl"
    output.write_text('{"previous": true}\n', encoding="utf-8")
    _patch_runtime(
        module,
        monkeypatch,
        rows=[_row("PROF-1")],
        decisions=[_decision(accepted=True, confidence=0.91, reasoning="ok")],
    )

    assert _run_main(
        module,
        monkeypatch,
        ["--database-url", _TEST_DSN, "--json-output", str(output)],
    ) == 0
    assert _run_main(
        module,
        monkeypatch,
        ["--database-url", _TEST_DSN, "--json-output", str(output)],
    ) == 0

    records = _read_jsonl(output)
    assert records[0] == {"previous": True}
    assert len(records) == 5
    assert [record.get("summary") for record in records].count(True) == 2


def test_json_output_does_not_expose_dsn_password(tmp_path, monkeypatch):
    module = _load_module()
    output = tmp_path / "redacted.jsonl"
    _patch_runtime(
        module,
        monkeypatch,
        rows=[_row("PROF-1")],
        decisions=[_decision(accepted=False, confidence=0.2, reasoning="姓名不一致")],
        dsn=_TEST_DSN,
    )

    assert _run_main(
        module,
        monkeypatch,
        ["--database-url", _TEST_DSN, "--json-output", str(output)],
    ) == 0

    text = output.read_text(encoding="utf-8")
    summary = _read_jsonl(output)[-1]
    assert "secret-password" not in text
    assert "miroflow:secret-password" not in text
    assert summary["database_dsn_host"] == "localhost:15432"
    assert summary["database_name"] == "miroflow_test_mock"
