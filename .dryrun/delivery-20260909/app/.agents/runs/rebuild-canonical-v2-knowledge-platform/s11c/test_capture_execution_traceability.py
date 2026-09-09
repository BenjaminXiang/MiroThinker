"""Fail-closed owner for the S11C execution-traceability supplement."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


_MODULE_PATH = Path(__file__).with_name("capture_execution_traceability.py")
_S11C_RELATIVE = Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c")
_S11B_RECEIPT_RELATIVE = Path(
    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/verification-receipt.json"
)
_POINTERS = {
    "s11b-focused-agent-owners": "/verification/focused_agent_owners/command",
    "s11b-focused-admin-owners": ("/verification/focused_admin_s11b_owners/command"),
    "s11a-predecessor-owner": "/verification/s11a_predecessor_owner/command",
    "s10o-predecessor-owner": "/verification/s10o_predecessor_owner/command",
}


def _load_module() -> ModuleType:
    assert _MODULE_PATH.is_file(), "execution-traceability capture helper is missing"
    spec = importlib.util.spec_from_file_location(
        "s11c_capture_execution_traceability", _MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _guarded_fixture(repository_root: Path) -> tuple[Path, bytes, bytes]:
    evidence_root = repository_root / _S11C_RELATIVE
    junit_by_run = {
        "admin-no-external": (
            b'<testsuites><testsuite timestamp="2026-07-21T17:58:13.490872+00:00" '
            b'time="40.550"><testcase name="a" /></testsuite></testsuites>'
        ),
        "canonical-v2-predecessors": (
            b'<testsuites><testsuite timestamp="2026-07-21T17:58:58.245407+00:00" '
            b'time="216.806"><testcase name="b" /></testsuite></testsuites>'
        ),
    }
    runs = []
    guard_runs = []
    for run_id, raw in junit_by_run.items():
        junit_path = _S11C_RELATIVE / "junit" / f"{run_id}.xml"
        _write(repository_root / junit_path, raw)
        argv = ["pytest", f"--junitxml={junit_path.as_posix()}"]
        cwd = repository_root / (
            "apps/admin-console"
            if run_id == "admin-no-external"
            else "apps/miroflow-agent"
        )
        runs.append(
            {
                "command": argv,
                "cwd": str(cwd),
                "junit_xml_path": junit_path.as_posix(),
                "junit_xml_sha256": hashlib.sha256(raw).hexdigest(),
                "run_id": run_id,
            }
        )
        guard_runs.append(
            {
                "argv": argv,
                "cwd": cwd.relative_to(repository_root).as_posix(),
                "junit_xml_path": junit_path.as_posix(),
                "junit_xml_sha256": hashlib.sha256(raw).hexdigest(),
                "run_id": run_id,
            }
        )
    ledger_raw = _json_bytes(
        {
            "runs": runs,
            "schema_version": "canonical-v2-s11c-retired-failure-ledger-v1",
        }
    )
    guard_raw = _json_bytes(
        {
            "runs": guard_runs,
            "schema_version": "canonical-v2-s11c-guarded-partitions-receipt-v1",
        }
    )
    _write(evidence_root / "retired-failure-ledger-v1.json", ledger_raw)
    _write(evidence_root / "guarded-partitions-receipt.json", guard_raw)
    return evidence_root, ledger_raw, guard_raw


def test_guarded_provenance_derives_exact_utc_window_and_binds_sources(
    tmp_path: Path,
) -> None:
    module = _load_module()
    evidence_root, ledger_raw, guard_raw = _guarded_fixture(tmp_path)

    receipt = module.capture_guarded_execution_provenance(tmp_path)

    assert receipt["schema_version"] == (
        "canonical-v2-s11c-guarded-execution-provenance-v1"
    )
    assert receipt["source_artifacts"]["retired_failure_ledger"]["sha256"] == (
        hashlib.sha256(ledger_raw).hexdigest()
    )
    assert (
        receipt["source_artifacts"]["guarded_partitions_receipt"]["sha256"]
        == hashlib.sha256(guard_raw).hexdigest()
    )
    rows = {row["run_id"]: row for row in receipt["runs"]}
    assert rows["admin-no-external"]["derived_started_at_utc"] == (
        "2026-07-21T17:58:13.490872Z"
    )
    assert rows["admin-no-external"]["derived_finished_at_utc"] == (
        "2026-07-21T17:58:54.040872Z"
    )
    assert rows["canonical-v2-predecessors"]["derived_finished_at_utc"] == (
        "2026-07-21T18:02:35.051407Z"
    )
    output = evidence_root / "guarded-execution-provenance-v1.json"
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        module.capture_guarded_execution_provenance(tmp_path)
    assert output.read_bytes() == original


def _predecessor_fixture(repository_root: Path) -> tuple[Path, bytes]:
    commands = {run_id: f"printf '%s\\n' {run_id}" for run_id in _POINTERS}
    receipt = {
        "verification": {
            pointer.split("/")[2]: {"command": commands[run_id]}
            for run_id, pointer in _POINTERS.items()
        }
    }
    receipt_raw = _json_bytes(receipt)
    _write(repository_root / _S11B_RECEIPT_RELATIVE, receipt_raw)
    v1 = {
        "accepted_s11b_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "runs": [
            {
                "accepted_command": commands[run_id],
                "accepted_command_json_pointer": pointer,
                "accepted_command_sha256": hashlib.sha256(
                    commands[run_id].encode()
                ).hexdigest(),
                "cross_links": [],
                "exit_code": 0,
                "run_id": run_id,
                "stderr_sha256": "0" * 64,
                "stdout_sha256": "1" * 64,
            }
            for run_id, pointer in _POINTERS.items()
        ],
        "schema_version": "canonical-v2-s11c-predecessor-reruns-v1",
    }
    v1_raw = _json_bytes(v1)
    v1_path = repository_root / _S11C_RELATIVE / "predecessor-reruns-v1.json"
    _write(v1_path, v1_raw)
    return v1_path, v1_raw


def test_predecessor_v2_reruns_unchanged_commands_from_exact_repository_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    v1_path, v1_raw = _predecessor_fixture(tmp_path)
    calls: list[dict[str, Any]] = []

    def runner(
        argv: list[str], *, cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append({"argv": argv, "cwd": cwd, "env": env})
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=f"stdout-{len(calls)}".encode(),
            stderr=f"stderr-{len(calls)}".encode(),
        )

    moments = iter(
        datetime(2026, 7, 21, 19, 0, second, tzinfo=timezone.utc) for second in range(8)
    )
    monkeypatch.setenv("HF_TOKEN", "must-not-reach-child")

    receipt = module.capture_predecessor_reruns_v2(
        tmp_path,
        runner=runner,
        clock=lambda: next(moments),
    )

    assert len(calls) == 4
    assert all(call["cwd"] == tmp_path.resolve() for call in calls)
    assert all("HF_TOKEN" not in call["env"] for call in calls)
    assert all(
        call["argv"] == ["/bin/bash", "-lc", row["accepted_command"]]
        for call, row in zip(calls, receipt["runs"], strict=True)
    )
    assert all(row["cwd"] == str(tmp_path.resolve()) for row in receipt["runs"])
    assert receipt["supersedes"]["sha256"] == hashlib.sha256(v1_raw).hexdigest()
    assert v1_path.read_bytes() == v1_raw
    v2_path = tmp_path / _S11C_RELATIVE / "predecessor-reruns-v2.json"
    original = v2_path.read_bytes()
    with pytest.raises(FileExistsError):
        module.capture_predecessor_reruns_v2(
            tmp_path,
            runner=runner,
            clock=lambda: next(moments),
        )
    assert len(calls) == 4
    assert v2_path.read_bytes() == original
