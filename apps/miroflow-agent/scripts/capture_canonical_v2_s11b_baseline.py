"""Fail-closed producer for the two frozen S11B broad-test baseline partitions."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
from typing import Any, NoReturn, cast
import uuid
import xml.etree.ElementTree as ET

import dotenv
import psycopg
import pytest
from _pytest.junitxml import bin_xml_escape, mangle_test_address

from src.data_agents.canonical_v2.legacy_consumer_quarantine import (
    load_legacy_consumer_inventory,
)


SENSITIVE_ENV_NAMES = (
    "ALL_PROXY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "API_KEY",
    "BOCHA_API_KEY",
    "CANONICAL_V2_BACKUP_GATE_ROOT",
    "CANONICAL_V2_DATABASE_URL",
    "CANONICAL_V2_EXPECTED_DATABASE",
    "CANONICAL_V2_TARGET_KIND",
    "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    "CANONICAL_V2_TEST_DATABASE_URL",
    "CANONICAL_V2_TEST_EXPECTED_DATABASE",
    "CANONICAL_V2_TEST_TARGET_KIND",
    "CHAT_MILVUS_URI",
    "DASHSCOPE_API_KEY",
    "DATABASE_URL",
    "DATABASE_URL_TEST",
    "E2B_API_KEY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "JINA_API_KEY",
    "JINA_BASE_URL",
    "LOCAL_LLM_API_KEY",
    "LOCAL_LLM_BASE_URL",
    "MILVUS_URI",
    "NO_PROXY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENALEX_API_KEY",
    "OPENALEX_KEY",
    "REASONING_API_KEY",
    "REASONING_BASE_URL",
    "S2_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "SERPER_API_KEY",
    "SERPER_BASE_URL",
    "SGLANG_API_KEY",
    "SUMMARY_LLM_API_KEY",
    "SUMMARY_LLM_BASE_URL",
    "TENCENTCLOUD_SECRET_ID",
    "TENCENTCLOUD_SECRET_KEY",
    "VISION_API_KEY",
    "VISION_BASE_URL",
    "WHISPER_API_KEY",
    "WHISPER_BASE_URL",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)

_SIGNATURE_VERSION = "canonical-v2-s11b-baseline-signature-v3"
_ADMIN_MARKER = "not requires_classifier_llm"
_ADMIN_DESELECTED = ("tests/test_classifier_benchmark.py::test_classifier_benchmark",)
_INVENTORY_PATH = Path(
    "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/"
    "legacy-consumer-inventory-v1.json"
)
_PRODUCER_PATH = Path(
    "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py"
)
_RUN = subprocess.run


class BaselineCaptureError(RuntimeError):
    """A guard, partition, artifact, or atomic-promotion invariant failed."""


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_id: str
    cwd: str
    argv: tuple[str, ...]
    collection_argv: tuple[str, ...]


def _collection_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    values = [token for token in argv if not token.startswith("--junitxml=")]
    values.insert(len(values) - 1, "--collect-only")
    return tuple(values)


_CANONICAL_ARGV = (
    "uv",
    "run",
    "pytest",
    "-o",
    "addopts=",
    "-p",
    "no:cacheprovider",
    "-q",
    "--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/baseline/tmp/canonical-v2-no-external/pytest",
    "--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/baseline/junit/canonical-v2-no-external.xml",
    "tests/canonical_v2",
)
_ADMIN_ARGV = (
    "uv",
    "run",
    "pytest",
    "-o",
    "addopts=",
    "-p",
    "no:cacheprovider",
    "-q",
    "-m",
    _ADMIN_MARKER,
    "--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/baseline/tmp/admin-no-external/pytest",
    "--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/baseline/junit/admin-no-external.xml",
    "tests",
)
RUN_SPECS = (
    RunSpec(
        run_id="canonical-v2-no-external",
        cwd="apps/miroflow-agent",
        argv=_CANONICAL_ARGV,
        collection_argv=_collection_argv(_CANONICAL_ARGV),
    ),
    RunSpec(
        run_id="admin-no-external",
        cwd="apps/admin-console",
        argv=_ADMIN_ARGV,
        collection_argv=_collection_argv(_ADMIN_ARGV),
    ),
)


Runner = Callable[..., Any]


def _default_runner(*, argv: tuple[str, ...], cwd: Path, env: dict[str, str]) -> Any:
    return _RUN(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return (
            path.resolve(strict=True)
            .relative_to(repository_root.resolve(strict=True))
            .as_posix()
        )
    except ValueError:
        return path.resolve(strict=True).as_posix()


def _child_environment(
    *,
    repository_root: Path,
    mode: str,
    stage: Path,
    temp_root: Path,
    nodeids: Path,
    junit: Path,
    reports: Path,
    guard_receipt: Path,
    pytest_temp: Path,
) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTEST_CURRENT_TEST", None)
    for name in SENSITIVE_ENV_NAMES:
        environment[name] = ""
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    environment["PYTEST_PLUGINS"] = "scripts.capture_canonical_v2_s11b_baseline"
    python_paths = (
        repository_root / "apps/admin-console",
        repository_root / "apps/miroflow-agent",
    )
    inherited_python_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            *(str(path) for path in python_paths),
            *((inherited_python_path,) if inherited_python_path else ()),
        )
    )
    environment["CANONICAL_V2_S11B_MODE"] = mode
    environment["CANONICAL_V2_S11B_REPOSITORY_ROOT"] = str(repository_root)
    environment["CANONICAL_V2_S11B_STAGE"] = str(stage.resolve())
    environment["CANONICAL_V2_S11B_NODEIDS_STAGE"] = str(nodeids.resolve())
    environment["CANONICAL_V2_S11B_JUNIT_STAGE"] = str(junit.resolve())
    environment["CANONICAL_V2_S11B_REPORTS_STAGE"] = str(reports.resolve())
    environment["CANONICAL_V2_S11B_GUARD_RECEIPT"] = str(guard_receipt.resolve())
    environment["CANONICAL_V2_S11B_PYTEST_TEMP"] = str(pytest_temp.resolve())
    environment["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"] = str(temp_root.resolve())
    for name in ("TMPDIR", "TMP", "TEMP"):
        environment[name] = str((temp_root / name.lower()).resolve())
    return environment


def _validate_environment(environment: dict[str, str], temp_root: Path) -> None:
    if environment["PYTHON_DOTENV_DISABLED"] != "1":
        raise BaselineCaptureError("dotenv disabling guard is absent")
    if [name for name in SENSITIVE_ENV_NAMES if environment.get(name) != ""]:
        raise BaselineCaptureError("sensitive environment is not present-empty")
    exact_root = temp_root.resolve()
    for name in ("TMPDIR", "TMP", "TEMP"):
        try:
            Path(environment[name]).resolve().relative_to(exact_root)
        except ValueError as exc:
            raise BaselineCaptureError(
                "temporary environment escaped ownership"
            ) from exc
    try:
        Path(environment["CANONICAL_V2_S11B_PYTEST_TEMP"]).resolve().relative_to(
            exact_root
        )
    except ValueError as exc:
        raise BaselineCaptureError("pytest temporary root escaped ownership") from exc


_PROBE_NAMES = (
    "af_inet_connect_blocked",
    "af_inet_connect_ex_blocked",
    "af_inet_owned_loopback_allowed",
    "af_unix_inside_allowed",
    "af_unix_outside_blocked",
    "dotenv_mutation_restored",
    "dotenv_noop",
    "psycopg_async_class_blocked",
    "psycopg_class_blocked",
    "psycopg_top_level_blocked",
)
_SOCKET_POLICY_RECEIPT = {
    "af_inet_connect": "owned_live_loopback_listener_only",
    "af_inet_connect_ex": "blocked",
    "af_inet6_connect": "blocked",
    "af_unix_connect": "owned_root_only",
    "listener_requirements": {
        "destination_host": "127.0.0.1",
        "exact_destination_port": True,
        "listen_observed_after_guard_install": True,
        "live_socket_object": True,
        "same_process_socket_object": True,
        "so_acceptconn": True,
    },
}
_GUARD_VERSIONS_RECEIPT = {
    "socket": "stdlib-socket-guard-v2",
    "psycopg": "psycopg-sync-async-guard-v1",
    "dotenv": "dotenv-restore-guard-v1",
    "attempt_attribution": "pytest-current-test-report-v1",
}
_ALLOWED_LOOPBACK_ROW_KEYS = {
    "destination_host",
    "destination_port",
    "family",
    "listener_host",
    "listener_port",
    "operation",
}
_BLOCKED_ATTEMPT_ROW_KEYS = {"kind", "message", "nodeid", "phase"}
_BLOCKED_ATTEMPT_MESSAGES = {
    "af_inet_connect_blocked": {
        "AF_INET access is blocked",
        "AF_INET6 access is blocked",
    },
    "af_inet_connect_ex_blocked": {"network connect_ex is blocked"},
    "af_unix_outside_blocked": {
        "AF_UNIX address is invalid",
        "AF_UNIX address escaped the owned root",
    },
    "psycopg_top_level_blocked": {"psycopg connect is blocked"},
    "psycopg_class_blocked": {"sync psycopg connect is blocked"},
    "psycopg_async_class_blocked": {"async psycopg connect is blocked"},
}
_REPORT_OUTCOMES = {"passed", "failure", "error", "skipped"}


def _parse_guard_receipt(
    path: Path,
    *,
    environment: dict[str, str],
    mode: str,
) -> dict[str, Any]:
    if not path.is_file():
        raise BaselineCaptureError("child guard receipt is absent")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineCaptureError("child guard receipt is invalid") from exc
    if not isinstance(value, dict):
        raise BaselineCaptureError("child guard receipt must be an object")
    if (
        value.get("schema_version") != "canonical-v2-s11b-child-guard-v3"
        or value.get("mode") != mode
        or value.get("early_hook_installed") is not True
        or value.get("session_finished") is not True
        or value.get("unconfigured") is not True
        or value.get("present_empty_sensitive_env_names") != list(SENSITIVE_ENV_NAMES)
        or value.get("forbidden_attempts") != []
        or value.get("probes") != {name: True for name in _PROBE_NAMES}
        or value.get("socket_policy") != _SOCKET_POLICY_RECEIPT
        or value.get("guard_versions") != _GUARD_VERSIONS_RECEIPT
        or value.get("owned_temp_root")
        != environment["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"]
        or value.get("pytest_temp_root") != environment["CANONICAL_V2_S11B_PYTEST_TEMP"]
        or type(value.get("exitstatus")) is not int
    ):
        raise BaselineCaptureError("child guard receipt failed exact validation")
    blocked_attempts = value.get("blocked_test_attempts")
    if not isinstance(blocked_attempts, list):
        raise BaselineCaptureError("blocked-attempt receipt must be an array")
    if mode != "run" and blocked_attempts:
        raise BaselineCaptureError("collection emitted a blocked attempt")
    for row in blocked_attempts:
        if not isinstance(row, dict) or set(row) != _BLOCKED_ATTEMPT_ROW_KEYS:
            raise BaselineCaptureError("blocked-attempt receipt row is invalid")
        kind = row.get("kind")
        message = row.get("message")
        nodeid = row.get("nodeid")
        if (
            not isinstance(kind, str)
            or not isinstance(message, str)
            or message not in _BLOCKED_ATTEMPT_MESSAGES.get(kind, set())
            or not isinstance(nodeid, str)
            or "::" not in nodeid
            or row.get("phase") != "call"
        ):
            raise BaselineCaptureError("blocked-attempt receipt row is invalid")
    allowed_connects = value.get("allowed_owned_loopback_connects")
    if not isinstance(allowed_connects, list):
        raise BaselineCaptureError("owned loopback receipt must be an array")
    if mode != "run" and allowed_connects:
        raise BaselineCaptureError("collection emitted an owned loopback connect")
    for row in allowed_connects:
        if (
            not isinstance(row, dict)
            or set(row) != _ALLOWED_LOOPBACK_ROW_KEYS
            or row.get("destination_host") != "127.0.0.1"
            or row.get("listener_host") != "127.0.0.1"
            or row.get("family") != "AF_INET"
            or row.get("operation") != "connect"
            or type(row.get("destination_port")) is not int
            or type(row.get("listener_port")) is not int
            or not 1 <= row["destination_port"] <= 65_535
            or row["destination_port"] != row["listener_port"]
        ):
            raise BaselineCaptureError("owned loopback receipt row is invalid")
    deselected = value.get("deselected_nodeids")
    if not isinstance(deselected, list) or not all(
        isinstance(item, str) for item in deselected
    ):
        raise BaselineCaptureError("child deselection receipt is invalid")
    return value


def _correlate_blocked_test_attempts(
    guard: dict[str, Any],
    *,
    reports: tuple[dict[str, str], ...],
    nodeids: tuple[str, ...],
    run_id: str,
) -> list[dict[str, str]]:
    report_contexts: dict[tuple[str, str], list[dict[str, str]]] = {}
    for report in reports:
        report_contexts.setdefault((report["nodeid"], report["phase"]), []).append(
            report
        )
    collected = set(nodeids)
    correlated: list[dict[str, str]] = []
    for attempt in guard["blocked_test_attempts"]:
        context = (attempt["nodeid"], attempt["phase"])
        matching_reports = report_contexts.get(context, [])
        if attempt["nodeid"] not in collected or len(matching_reports) != 1:
            raise BaselineCaptureError(
                "blocked attempt is not bound to an executed test phase"
            )
        correlated.append(
            {
                "run_id": run_id,
                **attempt,
                "report_outcome": matching_reports[0]["outcome"],
            }
        )
    return correlated


def _parse_nodeids(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise BaselineCaptureError("collection did not emit a nodeid artifact")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BaselineCaptureError("nodeid artifact is not UTF-8") from exc
    nodeids = tuple(text.splitlines())
    if not nodeids or any(not item or "::" not in item for item in nodeids):
        raise BaselineCaptureError("nodeid artifact is empty or malformed")
    expected = tuple(sorted(set(nodeids)))
    if nodeids != expected or raw != ("\n".join(expected) + "\n").encode():
        raise BaselineCaptureError("nodeid artifact is not canonical")
    return nodeids


def _parse_reports(path: Path) -> tuple[dict[str, str], ...]:
    if not path.is_file():
        raise BaselineCaptureError("run did not emit report-hook evidence")
    reports: list[dict[str, str]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("report is not an object")
            required = {"nodeid", "phase", "outcome"}
            if set(value) != required or not all(
                isinstance(value[name], str) for name in required
            ):
                raise ValueError("report shape is not exact")
            if value["phase"] not in {"collection", "setup", "call", "teardown"}:
                raise ValueError("report phase is unknown")
            if value["outcome"] not in _REPORT_OUTCOMES:
                raise ValueError("report outcome is unknown")
            reports.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise BaselineCaptureError("report-hook evidence is malformed") from exc
    if not reports:
        raise BaselineCaptureError("report-hook evidence is empty")
    return tuple(reports)


def _junit_testcase_identity(nodeid: str) -> tuple[str, str]:
    names = mangle_test_address(nodeid)
    if len(names) < 2 or any(not name for name in names):
        raise BaselineCaptureError("JUnit failure nodeid is malformed")
    return ".".join(names[:-1]), bin_xml_escape(names[-1])


def _junit_failure_rows(
    path: Path,
    *,
    repository_root: Path,
    temp_root: Path,
) -> list[dict[str, str]]:
    if not path.is_file():
        raise BaselineCaptureError("run did not emit JUnit evidence")
    try:
        root = ET.fromstring(path.read_bytes())
    except ET.ParseError as exc:
        raise BaselineCaptureError("JUnit evidence is invalid") from exc
    rows: list[dict[str, str]] = []
    for testcase in root.findall(".//testcase"):
        testcase_identity = (
            testcase.get("classname", ""),
            testcase.get("name", ""),
        )
        for element in testcase:
            if element.tag not in {"failure", "error"}:
                continue
            row = {
                "nodeid": element.get("canonical_nodeid", ""),
                "phase": element.get("canonical_phase", ""),
                "outcome": element.get("canonical_outcome", ""),
                "normalized_failure_signature_sha256": element.get(
                    "canonical_signature", ""
                ),
            }
            if any(not value for value in row.values()):
                raise BaselineCaptureError("JUnit failure lacks exact hook identity")
            if _junit_testcase_identity(row["nodeid"]) != testcase_identity:
                raise BaselineCaptureError(
                    "JUnit failure testcase identity differs from canonical nodeid"
                )
            if row["outcome"] != element.tag:
                raise BaselineCaptureError(
                    "JUnit failure element differs from canonical outcome"
                )
            if row["normalized_failure_signature_sha256"] != _junit_failure_signature(
                element,
                repository_root=repository_root,
                temp_root=temp_root,
            ):
                raise BaselineCaptureError(
                    "JUnit failure signature is not independently recomputable"
                )
            rows.append(row)
    rows.sort(key=lambda item: (item["nodeid"], item["phase"], item["outcome"]))
    return rows


def _junit_terminal_outcomes(
    path: Path,
    *,
    nodeids: tuple[str, ...],
) -> dict[str, str]:
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        raise BaselineCaptureError("JUnit evidence is invalid") from exc
    nodeid_by_identity: dict[tuple[str, str], str] = {}
    for nodeid in nodeids:
        identity = _junit_testcase_identity(nodeid)
        if identity in nodeid_by_identity:
            raise BaselineCaptureError("collected JUnit testcase identity is ambiguous")
        nodeid_by_identity[identity] = nodeid
    outcomes: dict[str, str] = {}
    for testcase in root.findall(".//testcase"):
        identity = (testcase.get("classname", ""), testcase.get("name", ""))
        nodeid = nodeid_by_identity.get(identity)
        if nodeid is None or nodeid in outcomes:
            raise BaselineCaptureError(
                "JUnit testcase identity differs from collection"
            )
        terminal = [
            element.tag
            for element in testcase
            if element.tag in {"failure", "error", "skipped"}
        ]
        if len(terminal) > 1:
            raise BaselineCaptureError("JUnit testcase terminal outcome is ambiguous")
        outcomes[nodeid] = terminal[0] if terminal else "passed"
    if set(outcomes) != set(nodeids):
        raise BaselineCaptureError("JUnit testcase coverage differs from collection")
    return outcomes


def _report_terminal_outcomes(
    reports: tuple[dict[str, str], ...],
    *,
    nodeids: tuple[str, ...],
) -> dict[str, str]:
    collected = set(nodeids)
    phases_by_nodeid: dict[str, dict[str, str]] = {}
    for report in reports:
        nodeid = report["nodeid"]
        phase = report["phase"]
        if phase == "collection" or nodeid not in collected:
            raise BaselineCaptureError("run report identity differs from collection")
        phases = phases_by_nodeid.setdefault(nodeid, {})
        if phase in phases:
            raise BaselineCaptureError("run report phase is duplicated")
        phases[phase] = report["outcome"]
    if set(phases_by_nodeid) != collected:
        raise BaselineCaptureError("run report coverage differs from collection")

    outcomes: dict[str, str] = {}
    for nodeid, phases in phases_by_nodeid.items():
        setup = phases.get("setup")
        teardown = phases.get("teardown")
        call = phases.get("call")
        if (
            setup not in {"passed", "skipped", "error"}
            or teardown not in {"passed", "skipped", "error"}
            or (setup == "passed") != (call is not None)
            or call not in {None, "passed", "failure", "skipped"}
        ):
            raise BaselineCaptureError("run report lifecycle is incomplete")
        phase_outcomes = set(phases.values())
        if "error" in phase_outcomes:
            terminal = "error"
        elif "failure" in phase_outcomes:
            terminal = "failure"
        elif "skipped" in phase_outcomes:
            terminal = "skipped"
        else:
            terminal = "passed"
        outcomes[nodeid] = terminal
    return outcomes


def _validate_junit_report_bijection(
    path: Path,
    *,
    reports: tuple[dict[str, str], ...],
    nodeids: tuple[str, ...],
) -> None:
    if _junit_terminal_outcomes(path, nodeids=nodeids) != _report_terminal_outcomes(
        reports,
        nodeids=nodeids,
    ):
        raise BaselineCaptureError("JUnit and report-hook terminal outcomes disagree")


def _normalize(value: str, *, repository_root: Path, temp_root: Path) -> str:
    normalized = value.replace("\r\n", "\n")
    for root, token in (
        (temp_root, "<pytest-tmp>/"),
        (repository_root, "<repo>/"),
    ):
        exact = str(root.resolve())
        normalized = normalized.replace(exact + os.sep, token).replace(exact, token)
    return normalized


def _report_failure_identities(
    reports: tuple[dict[str, str], ...],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for report in reports:
        if report["outcome"] not in {"failure", "error"}:
            continue
        failures.append(
            {
                "nodeid": report["nodeid"],
                "phase": report["phase"],
                "outcome": report["outcome"],
            }
        )
    failures.sort(key=lambda item: (item["nodeid"], item["phase"], item["outcome"]))
    return failures


def _junit_failure_signature(
    element: ET.Element,
    *,
    repository_root: Path,
    temp_root: Path,
) -> str:
    message = _normalize(
        element.get("message", ""),
        repository_root=repository_root,
        temp_root=temp_root,
    )
    body = _normalize(
        element.text or "",
        repository_root=repository_root,
        temp_root=temp_root,
    )
    return hashlib.sha256(
        f"{element.tag}\n{message}\n{body}".encode("utf-8")
    ).hexdigest()


def _promote(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise BaselineCaptureError("baseline artifact already exists") from exc


def _preflight(temp_root: Path) -> bool:
    root = temp_root.resolve()
    inside = (root / "probe.sock").resolve()
    outside = (root.parent / "outside.sock").resolve()
    if len(os.fsencode(root / "guard-probe.sock")) > 107:
        return False
    try:
        inside.relative_to(root)
    except ValueError:
        return False
    try:
        outside.relative_to(root)
    except ValueError:
        return True
    return False


def capture_baseline(
    *,
    repository_root: Path,
    output_root: Path,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    """Capture both frozen partitions atomically into a new baseline row."""

    repository_root = repository_root.resolve(strict=True)
    inventory_path = repository_root / _INVENTORY_PATH
    inventory = load_legacy_consumer_inventory(
        inventory_path,
        repository_root=repository_root,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    row_path = output_root / "baseline-row.json"
    final_targets = [row_path]
    for spec in RUN_SPECS:
        final_targets.extend(
            (
                output_root / "collected" / f"{spec.run_id}.txt",
                output_root / "junit" / f"{spec.run_id}.xml",
            )
        )
    if any(path.exists() for path in final_targets):
        raise BaselineCaptureError("baseline target already exists")

    temp_root = Path(tempfile.mkdtemp(prefix="s11b-", dir="/tmp"))
    stage = output_root / f".stage-{uuid.uuid4().hex}"
    child_stage = temp_root / "child-stage"
    promoted: list[Path] = []
    run_rows: list[dict[str, Any]] = []
    child_guard_rows: list[dict[str, Any]] = []
    blocked_test_attempt_rows: list[dict[str, Any]] = []
    forbidden_attempt_rows: list[dict[str, Any]] = []
    pytest_temp_roots: dict[str, dict[str, str]] = {}
    try:
        try:
            stage.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise BaselineCaptureError("baseline stage already exists") from exc
        child_stage.mkdir(mode=0o700)
        for name in ("tmpdir", "tmp", "temp"):
            (temp_root / name).mkdir(mode=0o700)
        if not _preflight(temp_root):
            raise BaselineCaptureError("baseline guard self-probe failed")

        for spec in RUN_SPECS:
            run_stage = child_stage / spec.run_id
            run_stage.mkdir(mode=0o700)
            collect_nodeids_stage = run_stage / "collect-nodeids.txt"
            run_nodeids_stage = run_stage / "run-nodeids.txt"
            junit_stage = run_stage / "junit.xml"
            reports_stage = run_stage / "reports.jsonl"
            collect_guard_stage = run_stage / "collect-guard.json"
            run_guard_stage = run_stage / "run-guard.json"
            spec_temp = temp_root / spec.run_id
            spec_temp.mkdir(mode=0o700)
            collect_pytest_temp = spec_temp / "collect" / "pytest"
            run_pytest_temp = spec_temp / "run" / "pytest"
            collect_pytest_temp.parent.mkdir(mode=0o700)
            run_pytest_temp.parent.mkdir(mode=0o700)
            collect_environment = _child_environment(
                repository_root=repository_root,
                mode="collect",
                stage=run_stage,
                temp_root=temp_root,
                nodeids=collect_nodeids_stage,
                junit=junit_stage,
                reports=reports_stage,
                guard_receipt=collect_guard_stage,
                pytest_temp=collect_pytest_temp,
            )
            _validate_environment(collect_environment, temp_root)
            collected = runner(
                argv=spec.collection_argv,
                cwd=repository_root / spec.cwd,
                env=collect_environment,
            )
            if collected.returncode != 0:
                raise BaselineCaptureError("baseline collection failed")
            collect_guard = _parse_guard_receipt(
                collect_guard_stage,
                environment=collect_environment,
                mode="collect",
            )
            if collect_guard["exitstatus"] != int(collected.returncode):
                raise BaselineCaptureError(
                    "collection guard exit status disagrees with subprocess"
                )
            nodeids = _parse_nodeids(collect_nodeids_stage)
            expected_deselected = (
                list(_ADMIN_DESELECTED) if spec.run_id == "admin-no-external" else []
            )
            if collect_guard["deselected_nodeids"] != expected_deselected:
                raise BaselineCaptureError("collection deselection identity drifted")

            run_environment = _child_environment(
                repository_root=repository_root,
                mode="run",
                stage=run_stage,
                temp_root=temp_root,
                nodeids=run_nodeids_stage,
                junit=junit_stage,
                reports=reports_stage,
                guard_receipt=run_guard_stage,
                pytest_temp=run_pytest_temp,
            )
            _validate_environment(run_environment, temp_root)
            pytest_temp_roots[spec.run_id] = {
                "collect": collect_environment["CANONICAL_V2_S11B_PYTEST_TEMP"],
                "run": run_environment["CANONICAL_V2_S11B_PYTEST_TEMP"],
            }

            executed = runner(
                argv=spec.argv,
                cwd=repository_root / spec.cwd,
                env=run_environment,
            )
            run_guard = _parse_guard_receipt(
                run_guard_stage,
                environment=run_environment,
                mode="run",
            )
            if run_guard["exitstatus"] != int(executed.returncode):
                raise BaselineCaptureError(
                    "run guard exit status disagrees with subprocess"
                )
            if int(executed.returncode) not in {0, 1}:
                raise BaselineCaptureError(
                    "run did not reach a valid pytest terminal test outcome"
                )
            if run_guard["deselected_nodeids"] != expected_deselected:
                raise BaselineCaptureError("run deselection identity drifted")
            run_nodeids = _parse_nodeids(run_nodeids_stage)
            if run_nodeids != nodeids:
                raise BaselineCaptureError("collection and run nodeids disagree")
            reports = _parse_reports(reports_stage)
            correlated_attempts = _correlate_blocked_test_attempts(
                run_guard,
                reports=reports,
                nodeids=run_nodeids,
                run_id=spec.run_id,
            )
            report_failure_identities = _report_failure_identities(reports)
            failure_rows = _junit_failure_rows(
                junit_stage,
                repository_root=repository_root,
                temp_root=Path(run_environment["CANONICAL_V2_S11B_PYTEST_TEMP"]),
            )
            junit_failure_identities = [
                {
                    "nodeid": row["nodeid"],
                    "phase": row["phase"],
                    "outcome": row["outcome"],
                }
                for row in failure_rows
            ]
            if junit_failure_identities != report_failure_identities:
                raise BaselineCaptureError("JUnit and report-hook evidence disagree")
            _validate_junit_report_bijection(
                junit_stage,
                reports=reports,
                nodeids=nodeids,
            )
            child_guard_rows.extend((collect_guard, run_guard))
            blocked_test_attempt_rows.extend(correlated_attempts)
            for guard_receipt in (collect_guard, run_guard):
                forbidden_attempt_rows.extend(guard_receipt["forbidden_attempts"])

            final_nodeids = output_root / "collected" / f"{spec.run_id}.txt"
            final_junit = output_root / "junit" / f"{spec.run_id}.xml"
            promotion_stage = stage / spec.run_id
            promotion_stage.mkdir(mode=0o700)
            promotion_nodeids = promotion_stage / "collect-nodeids.txt"
            promotion_junit = promotion_stage / "junit.xml"
            shutil.copyfile(collect_nodeids_stage, promotion_nodeids)
            shutil.copyfile(junit_stage, promotion_junit)
            if _sha256(promotion_nodeids) != _sha256(collect_nodeids_stage) or _sha256(
                promotion_junit
            ) != _sha256(junit_stage):
                raise BaselineCaptureError(
                    "promotion-stage copy differs from validated evidence"
                )
            _promote(promotion_nodeids, final_nodeids)
            promoted.append(final_nodeids)
            _promote(promotion_junit, final_junit)
            promoted.append(final_junit)
            run_rows.append(
                {
                    "run_id": spec.run_id,
                    "cwd": spec.cwd,
                    "collection_argv": list(spec.collection_argv),
                    "argv": list(spec.argv),
                    "exit_code": int(executed.returncode),
                    "collected_nodeids_path": _display_path(
                        final_nodeids, repository_root
                    ),
                    "collected_nodeids_sha256": _sha256(final_nodeids),
                    "junit_xml_path": _display_path(final_junit, repository_root),
                    "junit_xml_sha256": _sha256(final_junit),
                    "failures": failure_rows,
                }
            )

        shutil.rmtree(stage)
        shutil.rmtree(temp_root)
        guard = {
            "python_dotenv_disabled": "1",
            "present_empty_sensitive_env_names": list(SENSITIVE_ENV_NAMES),
            "blocked_socket_families": ["AF_INET", "AF_INET6"],
            "blocked_socket_operations": ["connect", "connect_ex"],
            "psycopg_connect_blocked": True,
            "owned_temp_root": str(temp_root.resolve()),
            "temp_environment": {
                name: str((temp_root / name.lower()).resolve())
                for name in ("TMPDIR", "TMP", "TEMP")
            },
            "pytest_temp_roots": pytest_temp_roots,
            "allowed_af_unix_roots": [str(temp_root.resolve())],
            "admin_marker_expression": _ADMIN_MARKER,
            "admin_deselected_nodeids": list(_ADMIN_DESELECTED),
            "self_probes_passed": True,
            "cleanup": True,
            "blocked_test_attempt_count": len(blocked_test_attempt_rows),
            "blocked_test_attempts": blocked_test_attempt_rows,
            "forbidden_attempts": forbidden_attempt_rows,
            "child_receipts": child_guard_rows,
        }
        receipt = {
            "legacy_consumer_inventory": inventory.receipt,
            "broad_test_baseline": {
                "signature_schema_version": _SIGNATURE_VERSION,
                "producer_path": _PRODUCER_PATH.as_posix(),
                "producer_sha256": _sha256(repository_root / _PRODUCER_PATH),
                "guard_preflight": guard,
                "runs": run_rows,
            },
        }
        try:
            with row_path.open("xb") as stream:
                stream.write(_canonical_bytes(receipt))
        except FileExistsError as exc:
            raise BaselineCaptureError("baseline row already exists") from exc
        return receipt
    except BaseException:
        for path in reversed(promoted):
            path.unlink(missing_ok=True)
        row_path.unlink(missing_ok=True)
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


_ACTIVE_GUARD: dict[str, Any] | None = None


def _write_child_guard_receipt() -> None:
    guard_state = _ACTIVE_GUARD
    if guard_state is None:
        return
    with guard_state["receipt_lock"]:
        path = Path(guard_state["receipt_path"])
        value = {
            "schema_version": "canonical-v2-s11b-child-guard-v3",
            "mode": guard_state["mode"],
            "early_hook_installed": guard_state["early_hook_installed"],
            "present_empty_sensitive_env_names": [
                name for name in SENSITIVE_ENV_NAMES if os.environ.get(name) == ""
            ],
            "probes": dict(guard_state["probes"]),
            "blocked_test_attempts": list(guard_state["blocked_test_attempts"]),
            "forbidden_attempts": list(guard_state["forbidden_attempts"]),
            "socket_policy": _SOCKET_POLICY_RECEIPT,
            "allowed_owned_loopback_connects": list(
                guard_state["allowed_owned_loopback_connects"]
            ),
            "owned_temp_root": str(guard_state["allowed_root"]),
            "pytest_temp_root": guard_state["pytest_temp_root"],
            "deselected_nodeids": sorted(set(guard_state["deselected"])),
            "session_finished": guard_state["session_finished"],
            "unconfigured": guard_state["unconfigured"],
            "exitstatus": guard_state["exitstatus"],
            "guard_versions": _GUARD_VERSIONS_RECEIPT,
        }
        path.write_bytes(_canonical_bytes(value))


def _block_guard(kind: str, message: str) -> NoReturn:
    guard_state = _ACTIVE_GUARD
    if guard_state is None:
        raise BaselineCaptureError(message)
    with guard_state["receipt_lock"]:
        if guard_state.get("active_probe") == kind:
            guard_state["probes"][kind] = True
        else:
            current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
            suffix = " (call)"
            nodeid = (
                current_test[: -len(suffix)] if current_test.endswith(suffix) else ""
            )
            attributable = (
                guard_state["mode"] == "run"
                and "::" in nodeid
                and message in _BLOCKED_ATTEMPT_MESSAGES.get(kind, set())
            )
            if attributable:
                guard_state["blocked_test_attempts"].append(
                    {
                        "kind": kind,
                        "message": message,
                        "nodeid": nodeid,
                        "phase": "call",
                    }
                )
            else:
                guard_state["forbidden_attempts"].append(
                    {"kind": kind, "message": message}
                )
        _write_child_guard_receipt()
    raise BaselineCaptureError(message)


def _run_expected_probe(name: str, probe: Callable[[], Any]) -> None:
    guard_state = _ACTIVE_GUARD
    if guard_state is None:
        raise BaselineCaptureError("guard probe ran without an installed guard")
    with guard_state["receipt_lock"]:
        guard_state["active_probe"] = name
        try:
            probe()
        except BaselineCaptureError:
            pass
        finally:
            guard_state["active_probe"] = None
        if guard_state["probes"][name] is not True:
            raise BaselineCaptureError(f"guard probe did not block {name}")


def _run_guard_self_probes() -> None:
    if _ACTIVE_GUARD is None:
        raise BaselineCaptureError("guard self-probe ran before installation")
    allowed_root = cast(Path, _ACTIVE_GUARD["allowed_root"])
    inet_connect = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _run_expected_probe(
            "af_inet_connect_blocked",
            lambda: inet_connect.connect(("127.0.0.1", 9)),
        )
    finally:
        inet_connect.close()
    inet_connect_ex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _run_expected_probe(
            "af_inet_connect_ex_blocked",
            lambda: inet_connect_ex.connect_ex(("127.0.0.1", 9)),
        )
    finally:
        inet_connect_ex.close()

    owned_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    owned_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    accepted: socket.socket | None = None
    with _ACTIVE_GUARD["receipt_lock"]:
        allowed_rows_before = len(_ACTIVE_GUARD["allowed_owned_loopback_connects"])
    try:
        owned_server.bind(("127.0.0.1", 0))
        owned_server.listen(1)
        endpoint = owned_server.getsockname()
        with _ACTIVE_GUARD["receipt_lock"]:
            _ACTIVE_GUARD["active_probe"] = "af_inet_owned_loopback_allowed"
            try:
                owned_client.connect((endpoint[0], endpoint[1]))
                accepted, _ = owned_server.accept()
                _ACTIVE_GUARD["probes"]["af_inet_owned_loopback_allowed"] = True
            finally:
                _ACTIVE_GUARD["active_probe"] = None
    finally:
        if accepted is not None:
            accepted.close()
        owned_client.close()
        owned_server.close()
    with _ACTIVE_GUARD["receipt_lock"]:
        allowed_rows_after = len(_ACTIVE_GUARD["allowed_owned_loopback_connects"])
    if allowed_rows_after != allowed_rows_before:
        raise BaselineCaptureError("owned loopback self-probe leaked into receipt")

    server_path = allowed_root / "guard-probe.sock"
    server_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(server_path))
        server.listen(1)
        client.connect(str(server_path))
        with _ACTIVE_GUARD["receipt_lock"]:
            _ACTIVE_GUARD["probes"]["af_unix_inside_allowed"] = True
    finally:
        client.close()
        server.close()
        server_path.unlink(missing_ok=True)
    outside_client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        _run_expected_probe(
            "af_unix_outside_blocked",
            lambda: outside_client.connect(str(allowed_root.parent / "outside.sock")),
        )
    finally:
        outside_client.close()

    _run_expected_probe(
        "psycopg_top_level_blocked",
        lambda: psycopg.connect("postgresql://guard.invalid/db"),
    )
    _run_expected_probe(
        "psycopg_class_blocked",
        lambda: psycopg.Connection.connect("postgresql://guard.invalid/db"),
    )
    _run_expected_probe(
        "psycopg_async_class_blocked",
        lambda: psycopg.AsyncConnection.connect("postgresql://guard.invalid/db"),
    )

    noop_path = allowed_root / "missing-dotenv"
    dotenv.load_dotenv(dotenv_path=noop_path, override=True)
    with _ACTIVE_GUARD["receipt_lock"]:
        _ACTIVE_GUARD["probes"]["dotenv_noop"] = True
    mutation_path = allowed_root / "mutation.env"
    mutation_path.write_text("OPENAI_API_KEY=forbidden-probe\n", encoding="utf-8")
    _run_expected_probe(
        "dotenv_mutation_restored",
        lambda: dotenv.load_dotenv(dotenv_path=mutation_path, override=True),
    )
    mutation_path.unlink()
    if os.environ.get("OPENAI_API_KEY") != "":
        raise BaselineCaptureError("dotenv probe did not restore sensitive state")
    _write_child_guard_receipt()


def _install_pytest_guards(*, early: bool) -> None:
    global _ACTIVE_GUARD
    if _ACTIVE_GUARD is not None:
        if early:
            with _ACTIVE_GUARD["receipt_lock"]:
                _ACTIVE_GUARD["early_hook_installed"] = True
                _write_child_guard_receipt()
        return
    required = {
        name: os.environ.get(name)
        for name in (
            "CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT",
            "CANONICAL_V2_S11B_GUARD_RECEIPT",
            "CANONICAL_V2_S11B_MODE",
            "CANONICAL_V2_S11B_PYTEST_TEMP",
        )
    }
    if not all(required.values()):
        raise BaselineCaptureError("child guard configuration is incomplete")
    allowed_root = Path(
        cast(str, required["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"])
    ).resolve()
    original_connect = cast(Callable[[socket.socket, Any], Any], socket.socket.connect)
    original_connect_ex = cast(
        Callable[[socket.socket, Any], int], socket.socket.connect_ex
    )
    original_getsockname = cast(
        Callable[[socket.socket], Any], socket.socket.getsockname
    )
    original_listen = cast(Callable[[socket.socket, int], None], socket.socket.listen)
    original_dotenv = cast(Callable[..., Any], dotenv.load_dotenv)
    _ACTIVE_GUARD = {
        "allowed_root": allowed_root,
        "receipt_path": cast(str, required["CANONICAL_V2_S11B_GUARD_RECEIPT"]),
        "mode": cast(str, required["CANONICAL_V2_S11B_MODE"]),
        "pytest_temp_root": cast(str, required["CANONICAL_V2_S11B_PYTEST_TEMP"]),
        "early_hook_installed": early,
        "blocked_test_attempts": [],
        "forbidden_attempts": [],
        "allowed_owned_loopback_connects": [],
        "owned_loopback_listeners": [],
        "probes": {name: False for name in _PROBE_NAMES},
        "active_probe": None,
        "deselected": [],
        "session_finished": False,
        "unconfigured": False,
        "exitstatus": None,
        "receipt_lock": threading.RLock(),
    }
    guard_state = cast(dict[str, Any], _ACTIVE_GUARD)

    def exact_owned_loopback_endpoint(endpoint: object) -> tuple[str, int] | None:
        if type(endpoint) is not tuple or len(endpoint) != 2:
            return None
        host = endpoint[0]
        port = endpoint[1]
        if (
            type(host) is not str
            or host != "127.0.0.1"
            or type(port) is not int
            or not 1 <= port <= 65_535
        ):
            return None
        return host, port

    def guarded_listen(sock: socket.socket, backlog: int = 0) -> None:
        original_listen(sock, backlog)
        if sock.family != socket.AF_INET:
            return
        try:
            endpoint = exact_owned_loopback_endpoint(original_getsockname(sock))
        except OSError:
            return
        if endpoint is not None:
            with guard_state["receipt_lock"]:
                if all(
                    listener_row[0] is not sock
                    for listener_row in guard_state["owned_loopback_listeners"]
                ):
                    guard_state["owned_loopback_listeners"].append(
                        (sock, endpoint[0], endpoint[1])
                    )

    def owned_loopback_endpoints(
        address: object,
    ) -> tuple[tuple[str, int], tuple[str, int]] | None:
        destination = exact_owned_loopback_endpoint(address)
        if destination is None:
            return None
        destination_host, destination_port = destination
        with guard_state["receipt_lock"]:
            listeners = list(guard_state["owned_loopback_listeners"])
        for (
            listener,
            registered_host,
            registered_port,
        ) in listeners:
            try:
                listener_endpoint = exact_owned_loopback_endpoint(
                    original_getsockname(listener)
                )
                accepting = listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
            except OSError:
                continue
            if listener_endpoint is None:
                continue
            listener_host, listener_port = listener_endpoint
            if (
                listener.family == socket.AF_INET
                and listener.fileno() >= 0
                and accepting == 1
                and listener_host == registered_host
                and listener_port == registered_port
                and listener_host == destination_host
                and listener_port == destination_port
            ):
                return destination, listener_endpoint
        return None

    def require_address(sock: socket.socket, address: object) -> None:
        if sock.family == socket.AF_INET6:
            _block_guard("af_inet_connect_blocked", "AF_INET6 access is blocked")
        if sock.family == socket.AF_UNIX:
            if not isinstance(address, (str, bytes)):
                _block_guard("af_unix_outside_blocked", "AF_UNIX address is invalid")
            try:
                Path(os.fsdecode(address)).resolve(strict=False).relative_to(
                    allowed_root
                )
            except ValueError:
                _block_guard(
                    "af_unix_outside_blocked",
                    "AF_UNIX address escaped the owned root",
                )

    def guarded_connect(sock: socket.socket, address: object) -> Any:
        if sock.family == socket.AF_INET:
            endpoints = owned_loopback_endpoints(address)
            if endpoints is None:
                _block_guard("af_inet_connect_blocked", "AF_INET access is blocked")
            destination_endpoint, listener_endpoint = endpoints
            result = original_connect(sock, address)
            with guard_state["receipt_lock"]:
                if guard_state.get("active_probe") != "af_inet_owned_loopback_allowed":
                    guard_state["allowed_owned_loopback_connects"].append(
                        {
                            "destination_host": destination_endpoint[0],
                            "destination_port": destination_endpoint[1],
                            "family": "AF_INET",
                            "listener_host": listener_endpoint[0],
                            "listener_port": listener_endpoint[1],
                            "operation": "connect",
                        }
                    )
                    _write_child_guard_receipt()
            return result
        require_address(sock, address)
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object) -> int:
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            _block_guard("af_inet_connect_ex_blocked", "network connect_ex is blocked")
        require_address(sock, address)
        return original_connect_ex(sock, address)

    def blocked_top_level(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        _block_guard("psycopg_top_level_blocked", "psycopg connect is blocked")

    def blocked_connection(cls: object, *args: object, **kwargs: object) -> Any:
        del cls, args, kwargs
        _block_guard("psycopg_class_blocked", "sync psycopg connect is blocked")

    def blocked_async_connection(cls: object, *args: object, **kwargs: object) -> Any:
        del cls, args, kwargs
        _block_guard("psycopg_async_class_blocked", "async psycopg connect is blocked")

    def guarded_dotenv(*args: object, **kwargs: object) -> Any:
        with guard_state["receipt_lock"]:
            before = {name: os.environ.get(name) for name in SENSITIVE_ENV_NAMES}
            changed: list[str] = []
            try:
                if guard_state.get("active_probe") == "dotenv_mutation_restored":
                    os.environ["OPENAI_API_KEY"] = "forbidden-probe"
                    result = False
                else:
                    result = original_dotenv(*args, **kwargs)
                changed = [
                    name for name in SENSITIVE_ENV_NAMES if os.environ.get(name) != ""
                ]
            finally:
                for name in SENSITIVE_ENV_NAMES:
                    os.environ[name] = ""
            if any(value != "" for value in before.values()):
                _block_guard("dotenv_mutation_restored", "dotenv precondition drifted")
            if changed:
                _block_guard(
                    "dotenv_mutation_restored", "dotenv changed sensitive state"
                )
            return result

    socket.socket.listen = guarded_listen
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    psycopg.connect = blocked_top_level
    setattr(psycopg.Connection, "connect", classmethod(blocked_connection))
    setattr(
        psycopg.AsyncConnection,
        "connect",
        classmethod(blocked_async_connection),
    )
    dotenv.load_dotenv = guarded_dotenv
    _write_child_guard_receipt()
    _run_guard_self_probes()


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(
    early_config: Any,
    parser: Any,
    args: list[str],
) -> None:
    del early_config, parser, args
    _install_pytest_guards(early=True)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Any) -> None:
    if _ACTIVE_GUARD is None or not _ACTIVE_GUARD["early_hook_installed"]:
        raise BaselineCaptureError("guard was not installed before initial conftests")
    config.option.basetemp = _ACTIVE_GUARD["pytest_temp_root"]
    if _ACTIVE_GUARD["mode"] == "run":
        config.option.xmlpath = os.environ["CANONICAL_V2_S11B_JUNIT_STAGE"]
    else:
        config.option.xmlpath = None
    _write_child_guard_receipt()


def pytest_collection_finish(session: Any) -> None:
    target = os.environ.get("CANONICAL_V2_S11B_NODEIDS_STAGE")
    if target:
        nodeids = sorted({item.nodeid for item in session.items})
        Path(target).write_text("\n".join(nodeids) + "\n", encoding="utf-8")


def pytest_deselected(items: list[Any]) -> None:
    if _ACTIVE_GUARD is not None:
        with _ACTIVE_GUARD["receipt_lock"]:
            _ACTIVE_GUARD["deselected"].extend(item.nodeid for item in items)
            _write_child_guard_receipt()


def _append_report(value: dict[str, str]) -> None:
    target = os.environ.get("CANONICAL_V2_S11B_REPORTS_STAGE")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def pytest_runtest_logreport(report: Any) -> None:
    outcome = "passed"
    if report.failed:
        outcome = "failure" if report.when == "call" else "error"
    elif report.skipped:
        outcome = "skipped"
    _append_report(
        {
            "nodeid": report.nodeid,
            "phase": report.when,
            "outcome": outcome,
        }
    )


def pytest_collectreport(report: Any) -> None:
    if report.failed:
        _append_report(
            {
                "nodeid": report.nodeid,
                "phase": "collection",
                "outcome": "error",
            }
        )


def _annotate_junit_failures() -> None:
    if _ACTIVE_GUARD is None or _ACTIVE_GUARD["mode"] != "run":
        return
    junit_path = Path(os.environ["CANONICAL_V2_S11B_JUNIT_STAGE"])
    reports_path = Path(os.environ["CANONICAL_V2_S11B_REPORTS_STAGE"])
    if not junit_path.is_file() or not reports_path.is_file():
        raise BaselineCaptureError("terminal JUnit/report evidence is absent")
    repository_root = Path(os.environ["CANONICAL_V2_S11B_REPOSITORY_ROOT"])
    temp_root = Path(os.environ["CANONICAL_V2_S11B_PYTEST_TEMP"])
    failures = _report_failure_identities(_parse_reports(reports_path))
    tree = ET.parse(junit_path)
    testcases = [
        testcase
        for testcase in tree.findall(".//testcase")
        if any(element.tag in {"failure", "error"} for element in testcase)
    ]
    element_count = sum(
        element.tag in {"failure", "error"}
        for testcase in testcases
        for element in testcase
    )
    if element_count != len(failures):
        raise BaselineCaptureError("terminal JUnit/report count differs")
    testcases_by_identity: dict[tuple[str, str], ET.Element] = {}
    for testcase in testcases:
        identity = (testcase.get("classname", ""), testcase.get("name", ""))
        if not all(identity) or identity in testcases_by_identity:
            raise BaselineCaptureError("terminal JUnit testcase identity is ambiguous")
        testcases_by_identity[identity] = testcase
    failures_by_identity: dict[tuple[str, str], list[dict[str, str]]] = {}
    nodeid_by_identity: dict[tuple[str, str], str] = {}
    for failure in failures:
        identity = _junit_testcase_identity(failure["nodeid"])
        prior_nodeid = nodeid_by_identity.setdefault(identity, failure["nodeid"])
        if prior_nodeid != failure["nodeid"]:
            raise BaselineCaptureError("terminal report testcase identity is ambiguous")
        failures_by_identity.setdefault(identity, []).append(failure)
    if set(testcases_by_identity) != set(failures_by_identity):
        raise BaselineCaptureError("terminal JUnit/report testcase identity differs")
    for identity, testcase in testcases_by_identity.items():
        remaining = list(failures_by_identity[identity])
        elements = [
            element for element in testcase if element.tag in {"failure", "error"}
        ]
        if len(elements) != len(remaining):
            raise BaselineCaptureError("terminal JUnit/report testcase count differs")
        for element in elements:
            matches = [row for row in remaining if row["outcome"] == element.tag]
            if len(matches) != 1:
                raise BaselineCaptureError(
                    "terminal JUnit/report failure identity is ambiguous"
                )
            failure = matches[0]
            remaining.remove(failure)
            element.set("canonical_nodeid", failure["nodeid"])
            element.set("canonical_phase", failure["phase"])
            element.set("canonical_outcome", failure["outcome"])
            element.set(
                "canonical_signature",
                _junit_failure_signature(
                    element,
                    repository_root=repository_root,
                    temp_root=temp_root,
                ),
            )
    tree.write(junit_path, encoding="utf-8", xml_declaration=True)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    del session
    if _ACTIVE_GUARD is None:
        raise BaselineCaptureError("guard disappeared before session finish")
    _annotate_junit_failures()
    with _ACTIVE_GUARD["receipt_lock"]:
        for name in SENSITIVE_ENV_NAMES:
            os.environ[name] = ""
        _ACTIVE_GUARD["session_finished"] = True
        _ACTIVE_GUARD["exitstatus"] = int(exitstatus)
        _write_child_guard_receipt()


def pytest_unconfigure(config: Any) -> None:
    del config
    if _ACTIVE_GUARD is not None:
        with _ACTIVE_GUARD["receipt_lock"]:
            _ACTIVE_GUARD["unconfigured"] = True
            _write_child_guard_receipt()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture the frozen S11B baseline.")
    parser.add_argument("--output-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = Path(__file__).resolve().parents[3]
    expected = (
        repository_root
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline"
    )
    output_root = args.output_root.resolve() if args.output_root else expected
    if output_root != expected.resolve(strict=False):
        raise SystemExit("S11B baseline output root is fixed")
    try:
        receipt = capture_baseline(
            repository_root=repository_root,
            output_root=output_root,
        )
    except Exception:
        raise SystemExit("S11B baseline capture rejected") from None
    print(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
