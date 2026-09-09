"""Capture the missing S11C execution provenance without replacing prior evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


_S11C_RELATIVE = Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c")
_S11B_RECEIPT_RELATIVE = Path(
    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/verification-receipt.json"
)
_GUARDED_RUN_IDS = frozenset({"admin-no-external", "canonical-v2-predecessors"})
_PREDECESSOR_COMMAND_POINTERS = {
    "s11b-focused-agent-owners": "/verification/focused_agent_owners/command",
    "s11b-focused-admin-owners": ("/verification/focused_admin_s11b_owners/command"),
    "s11a-predecessor-owner": "/verification/s11a_predecessor_owner/command",
    "s10o-predecessor-owner": "/verification/s10o_predecessor_owner/command",
}
_DERIVATION = "pytest-junit-testsuite-timestamp-plus-duration-v1"

Runner = Callable[..., subprocess.CompletedProcess[bytes]]
Clock = Callable[[], datetime]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return raw, value


def _json_pointer(document: dict[str, Any], pointer: str) -> Any:
    current: Any = document
    for raw_token in pointer.removeprefix("/").split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError("Accepted predecessor command pointer is missing")
        current = current[token]
    return current


def _canonical_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("execution time must be timezone-aware")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _junit_execution_window(raw: bytes) -> dict[str, str]:
    root = ET.fromstring(raw)
    suites = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "testsuite"
    ]
    if len(suites) != 1:
        raise ValueError("guarded JUnit must contain exactly one testsuite")
    timestamp = suites[0].attrib.get("timestamp")
    duration_text = suites[0].attrib.get("time")
    if not timestamp or duration_text is None:
        raise ValueError("guarded JUnit lacks timestamp or duration")
    try:
        started = datetime.fromisoformat(timestamp)
        duration = Decimal(duration_text)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("guarded JUnit timestamp or duration is invalid") from exc
    if (
        started.tzinfo is None
        or started.utcoffset() != timedelta(0)
        or not duration.is_finite()
        or duration < 0
    ):
        raise ValueError("guarded JUnit execution window is not finite UTC")
    microseconds = duration * Decimal(1_000_000)
    if microseconds != microseconds.to_integral_value():
        raise ValueError("guarded JUnit duration exceeds microsecond precision")
    finished = started + timedelta(microseconds=int(microseconds))
    return {
        "junit_testsuite_duration_seconds": duration_text,
        "junit_testsuite_timestamp": timestamp,
        "derived_started_at_utc": _canonical_utc(started),
        "derived_finished_at_utc": _canonical_utc(finished),
    }


def _repository_artifact(
    repository_root: Path, declaration: Any, *, label: str
) -> Path:
    if not isinstance(declaration, str) or not declaration:
        raise ValueError(f"{label} path is missing")
    path = Path(declaration)
    if path.is_absolute():
        raise ValueError(f"{label} path must be repository-relative")
    resolved = (repository_root / path).resolve()
    try:
        resolved.relative_to(repository_root)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes repository root") from exc
    return resolved


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def capture_guarded_execution_provenance(
    repository_root: Path,
) -> dict[str, Any]:
    """Derive immutable UTC windows from the two existing broad JUnit files."""

    repository_root = repository_root.resolve()
    evidence_root = repository_root / _S11C_RELATIVE
    output = evidence_root / "guarded-execution-provenance-v1.json"
    if output.exists():
        raise FileExistsError(output)
    ledger_path = evidence_root / "retired-failure-ledger-v1.json"
    guard_path = evidence_root / "guarded-partitions-receipt.json"
    ledger_raw, ledger = _read_json(ledger_path, label="retired failure ledger")
    guard_raw, guard = _read_json(guard_path, label="guarded partitions receipt")
    ledger_runs = ledger.get("runs")
    guard_runs = guard.get("runs")
    if not isinstance(ledger_runs, list) or not isinstance(guard_runs, list):
        raise ValueError("guarded execution source run sets are missing")
    ledger_by_id = {
        row.get("run_id"): row
        for row in ledger_runs
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    guard_by_id = {
        row.get("run_id"): row
        for row in guard_runs
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    if set(guard_by_id) != _GUARDED_RUN_IDS or not _GUARDED_RUN_IDS.issubset(
        ledger_by_id
    ):
        raise ValueError("guarded execution source run set mismatch")

    provenance_runs: list[dict[str, Any]] = []
    for run_id in sorted(_GUARDED_RUN_IDS):
        ledger_run = ledger_by_id[run_id]
        guard_run = guard_by_id[run_id]
        cwd = ledger_run.get("cwd")
        guard_cwd = guard_run.get("cwd")
        if (
            not isinstance(cwd, str)
            or not Path(cwd).is_absolute()
            or not isinstance(guard_cwd, str)
            or (repository_root / guard_cwd).resolve() != Path(cwd).resolve()
            or ledger_run.get("command") != guard_run.get("argv")
            or ledger_run.get("junit_xml_path") != guard_run.get("junit_xml_path")
            or ledger_run.get("junit_xml_sha256") != guard_run.get("junit_xml_sha256")
        ):
            raise ValueError("guarded execution ledger/guard binding mismatch")
        junit_path = _repository_artifact(
            repository_root,
            ledger_run.get("junit_xml_path"),
            label="guarded JUnit",
        )
        junit_raw = junit_path.read_bytes()
        junit_sha256 = _sha256(junit_raw)
        if junit_sha256 != ledger_run.get("junit_xml_sha256"):
            raise ValueError("guarded execution JUnit source hash mismatch")
        provenance_runs.append(
            {
                "argv": ledger_run["command"],
                "cwd": cwd,
                "derivation": _DERIVATION,
                **_junit_execution_window(junit_raw),
                "junit_xml_path": ledger_run["junit_xml_path"],
                "junit_xml_sha256": junit_sha256,
                "run_id": run_id,
            }
        )
    receipt = {
        "runs": provenance_runs,
        "schema_version": "canonical-v2-s11c-guarded-execution-provenance-v1",
        "source_artifacts": {
            "guarded_partitions_receipt": {
                "path": (_S11C_RELATIVE / guard_path.name).as_posix(),
                "sha256": _sha256(guard_raw),
            },
            "retired_failure_ledger": {
                "path": (_S11C_RELATIVE / ledger_path.name).as_posix(),
                "sha256": _sha256(ledger_raw),
            },
        },
    }
    _write_new_json(output, receipt)
    return receipt


def _run_command(
    argv: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def capture_predecessor_reruns_v2(
    repository_root: Path,
    *,
    runner: Runner = _run_command,
    clock: Clock = _now,
) -> dict[str, Any]:
    """Rerun all four unchanged Accepted commands from the exact repository cwd."""

    repository_root = repository_root.resolve()
    evidence_root = repository_root / _S11C_RELATIVE
    output = evidence_root / "predecessor-reruns-v2.json"
    if output.exists():
        raise FileExistsError(output)
    accepted_path = repository_root / _S11B_RECEIPT_RELATIVE
    v1_path = evidence_root / "predecessor-reruns-v1.json"
    accepted_raw, accepted = _read_json(accepted_path, label="Accepted S11B receipt")
    v1_raw, v1 = _read_json(v1_path, label="predecessor reruns v1")
    if v1.get("schema_version") != "canonical-v2-s11c-predecessor-reruns-v1" or v1.get(
        "accepted_s11b_receipt_sha256"
    ) != _sha256(accepted_raw):
        raise ValueError("predecessor v1 Accepted authority mismatch")
    v1_runs = v1.get("runs")
    if not isinstance(v1_runs, list):
        raise ValueError("predecessor v1 run set is missing")
    v1_by_id = {
        row.get("run_id"): row
        for row in v1_runs
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    if set(v1_by_id) != set(_PREDECESSOR_COMMAND_POINTERS) or len(v1_by_id) != len(
        v1_runs
    ):
        raise ValueError("predecessor v1 must contain exact four runs")

    child_env = dict(os.environ)
    child_env.pop("HF_TOKEN", None)
    captured_runs: list[dict[str, Any]] = []
    for run_id, pointer in _PREDECESSOR_COMMAND_POINTERS.items():
        v1_row = v1_by_id[run_id]
        command = _json_pointer(accepted, pointer)
        if (
            not isinstance(command, str)
            or not command
            or v1_row.get("accepted_command_json_pointer") != pointer
            or v1_row.get("accepted_command") != command
            or v1_row.get("accepted_command_sha256") != _sha256(command.encode())
            or v1_row.get("exit_code") != 0
            or not isinstance(v1_row.get("cross_links"), list)
        ):
            raise ValueError("predecessor v1 command authority mismatch")
        started = clock()
        argv = ["/bin/bash", "-lc", command]
        result = runner(argv, cwd=repository_root, env=dict(child_env))
        finished = clock()
        if started.tzinfo is None or finished.tzinfo is None or finished < started:
            raise ValueError("predecessor rerun UTC window is invalid")
        if (
            not isinstance(result.stdout, bytes)
            or not isinstance(result.stderr, bytes)
            or isinstance(result.returncode, bool)
            or not isinstance(result.returncode, int)
        ):
            raise ValueError("predecessor runner result is not raw-byte exact")
        if result.returncode != 0:
            raise RuntimeError(
                f"Accepted predecessor command regressed: {run_id} exit "
                f"{result.returncode}"
            )
        captured_runs.append(
            {
                "accepted_command": command,
                "accepted_command_json_pointer": pointer,
                "accepted_command_sha256": _sha256(command.encode()),
                "cross_links": v1_row["cross_links"],
                "cwd": str(repository_root),
                "exit_code": result.returncode,
                "finished_at": _canonical_utc(finished),
                "launcher_argv": argv,
                "run_id": run_id,
                "sanitized_env_unset": ["HF_TOKEN"],
                "started_at": _canonical_utc(started),
                "stderr_sha256": _sha256(result.stderr),
                "stdout_sha256": _sha256(result.stdout),
            }
        )
    receipt = {
        "accepted_s11b_receipt_path": _S11B_RECEIPT_RELATIVE.as_posix(),
        "accepted_s11b_receipt_sha256": _sha256(accepted_raw),
        "runs": captured_runs,
        "schema_version": "canonical-v2-s11c-predecessor-reruns-v2",
        "supersedes": {
            "path": (_S11C_RELATIVE / v1_path.name).as_posix(),
            "sha256": _sha256(v1_raw),
        },
    }
    _write_new_json(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument(
        "--capture",
        choices=("guarded-provenance", "predecessor-v2", "both"),
        default="both",
    )
    args = parser.parse_args()
    if args.capture in {"guarded-provenance", "both"}:
        capture_guarded_execution_provenance(args.repository_root)
    if args.capture in {"predecessor-v2", "both"}:
        capture_predecessor_reruns_v2(args.repository_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
