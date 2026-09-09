"""Focused owner for the S11C configurable guarded-partition wrapper."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
import xml.etree.ElementTree as ET

import pytest


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_WRAPPER_PATH = Path(__file__).with_name("capture_guarded_partitions.py")
_MISSING_SENTINEL = "_MissingS11CGuardedPartitionWrapper"


class _MissingS11CGuardedPartitionWrapper(RuntimeError):
    """The pre-Ready wrapper has not reached GREEN yet."""


def _load_wrapper() -> ModuleType:
    if not _WRAPPER_PATH.is_file():
        pytest.xfail(_MISSING_SENTINEL)
        raise _MissingS11CGuardedPartitionWrapper(_MISSING_SENTINEL)
    spec = importlib.util.spec_from_file_location(
        "s11c_capture_guarded_partitions_owner_target",
        _WRAPPER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_mutable_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wrapper: ModuleType,
) -> tuple[Path, Path, Path, bytes]:
    repository_root = tmp_path / "mutable-authority"
    receipt_path = repository_root / wrapper._ACCEPTED_RECEIPT_PATH
    producer_path = repository_root / wrapper._ACCEPTED_PRODUCER_PATH
    owner_path = repository_root / wrapper._ACCEPTED_OWNER_PATH
    sensitive_names = tuple(f"SENSITIVE_{index:02d}" for index in range(49))

    def producer_bytes(label: str) -> bytes:
        return (
            "from dataclasses import dataclass\n"
            f"SENSITIVE_ENV_NAMES = {sensitive_names!r}\n"
            "_SIGNATURE_VERSION = 'canonical-v2-s11b-baseline-signature-v3'\n"
            "_ADMIN_MARKER = 'not requires_classifier_llm'\n"
            "_ADMIN_DESELECTED = "
            "('tests/test_classifier_benchmark.py::test_classifier_benchmark',)\n"
            "@dataclass(frozen=True)\n"
            "class Probe:\n"
            f"    value: str = {label!r}\n"
            "EXECUTED_SOURCE = Probe().value\n"
        ).encode()

    original_producer = producer_bytes("original")
    owner_bytes = b"temporary producer owner\n"
    producer_path.parent.mkdir(parents=True, exist_ok=True)
    owner_path.parent.mkdir(parents=True, exist_ok=True)
    producer_path.write_bytes(original_producer)
    owner_path.write_bytes(owner_bytes)
    receipt = {
        "status": "Accepted",
        "slice_id": "S11B",
        "implementation_artifacts": {
            wrapper._ACCEPTED_PRODUCER_PATH.as_posix(): hashlib.sha256(
                original_producer
            ).hexdigest(),
            wrapper._ACCEPTED_OWNER_PATH.as_posix(): hashlib.sha256(
                owner_bytes
            ).hexdigest(),
        },
    }
    receipt_bytes = json.dumps(receipt, sort_keys=True).encode()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(receipt_bytes)
    monkeypatch.setattr(
        wrapper,
        "_ACCEPTED_RECEIPT_SHA256",
        hashlib.sha256(receipt_bytes).hexdigest(),
    )
    monkeypatch.setattr(
        wrapper,
        "_ACCEPTED_PRODUCER_SHA256",
        hashlib.sha256(original_producer).hexdigest(),
    )
    monkeypatch.setattr(
        wrapper,
        "_ACCEPTED_OWNER_SHA256",
        hashlib.sha256(owner_bytes).hexdigest(),
    )
    return (
        repository_root,
        receipt_path,
        producer_path,
        producer_bytes("tampered"),
    )


def _terminal_guard_receipt(
    producer: ModuleType,
    *,
    environment: dict[str, str],
    mode: str,
    exitstatus: int,
    deselected_nodeids: list[str],
    terminal: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "canonical-v2-s11b-child-guard-v3",
        "mode": mode,
        "early_hook_installed": True,
        "present_empty_sensitive_env_names": list(producer.SENSITIVE_ENV_NAMES),
        "probes": {name: True for name in producer._PROBE_NAMES},
        "blocked_test_attempts": [],
        "forbidden_attempts": [],
        "socket_policy": producer._SOCKET_POLICY_RECEIPT,
        "allowed_owned_loopback_connects": [],
        "owned_temp_root": environment["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"],
        "pytest_temp_root": environment["CANONICAL_V2_S11B_PYTEST_TEMP"],
        "deselected_nodeids": deselected_nodeids,
        "session_finished": terminal,
        "unconfigured": terminal,
        "exitstatus": exitstatus,
        "guard_versions": producer._GUARD_VERSIONS_RECEIPT,
    }


def _write_synthetic_junit_and_reports(
    producer: ModuleType,
    *,
    environment: dict[str, str],
    nodeid: str,
    exitstatus: int,
) -> None:
    classname, name = producer._junit_testcase_identity(nodeid)
    testcase = ET.Element("testcase", {"classname": classname, "name": name})
    call_outcome = "passed"
    if exitstatus == 1:
        call_outcome = "failure"
        failure = ET.SubElement(
            testcase,
            "failure",
            {
                "message": "synthetic bounded failure",
                "canonical_nodeid": nodeid,
                "canonical_phase": "call",
                "canonical_outcome": "failure",
            },
        )
        failure.text = "synthetic bounded body"
        failure.set(
            "canonical_signature",
            producer._junit_failure_signature(
                failure,
                repository_root=_REPOSITORY_ROOT,
                temp_root=Path(environment["CANONICAL_V2_S11B_PYTEST_TEMP"]),
            ),
        )
    suite = ET.Element("testsuite")
    suite.append(testcase)
    suites = ET.Element("testsuites")
    suites.append(suite)
    ET.ElementTree(suites).write(
        environment["CANONICAL_V2_S11B_JUNIT_STAGE"],
        encoding="utf-8",
        xml_declaration=True,
    )
    reports = [
        {"nodeid": nodeid, "phase": "setup", "outcome": "passed"},
        {"nodeid": nodeid, "phase": "call", "outcome": call_outcome},
        {"nodeid": nodeid, "phase": "teardown", "outcome": "passed"},
    ]
    Path(environment["CANONICAL_V2_S11B_REPORTS_STAGE"]).write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in reports),
        encoding="utf-8",
    )


def test_authority_parses_the_same_receipt_bytes_that_were_hashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = _load_wrapper()
    repository_root, receipt_path, _, _ = _write_mutable_authority(
        tmp_path,
        monkeypatch,
        wrapper,
    )
    original_read_bytes = Path.read_bytes
    receipt_reads = 0

    def mutating_read_bytes(path: Path) -> bytes:
        nonlocal receipt_reads
        raw = original_read_bytes(path)
        if path.resolve() == receipt_path.resolve():
            receipt_reads += 1
            if receipt_reads == 1:
                receipt_path.write_bytes(b"{invalid-after-hash")
        return raw

    monkeypatch.setattr(Path, "read_bytes", mutating_read_bytes)
    authority = wrapper.verify_accepted_s11b_authority(repository_root)

    assert receipt_reads == 1
    assert authority.producer.EXECUTED_SOURCE == "original"


def test_authority_executes_the_same_producer_bytes_that_were_hashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = _load_wrapper()
    repository_root, _, producer_path, tampered_producer = _write_mutable_authority(
        tmp_path,
        monkeypatch,
        wrapper,
    )
    original_read_bytes = Path.read_bytes
    producer_reads = 0
    module_name = "_s11c_exact_accepted_s11b_guard"
    prior_module = sys.modules.get(module_name)
    temporary_agent_root = str(repository_root / "apps/miroflow-agent")

    def mutating_read_bytes(path: Path) -> bytes:
        nonlocal producer_reads
        raw = original_read_bytes(path)
        if path.resolve() == producer_path.resolve():
            producer_reads += 1
            if producer_reads == 1:
                producer_path.write_bytes(tampered_producer)
        return raw

    monkeypatch.setattr(Path, "read_bytes", mutating_read_bytes)
    authority = wrapper.verify_accepted_s11b_authority(repository_root)

    assert producer_reads == 1
    assert authority.producer.EXECUTED_SOURCE == "original"
    assert authority.producer.Probe("dataclass-ok").value == "dataclass-ok"
    assert temporary_agent_root not in sys.path
    assert sys.modules.get(module_name) is prior_module


def test_real_capture_exposes_only_the_frozen_task5_partition_set() -> None:
    wrapper = _load_wrapper()

    assert tuple(inspect.signature(wrapper.capture_guarded_partitions).parameters) == (
        "repository_root",
    )
    assert not hasattr(wrapper, "PartitionSpec")
    assert tuple(
        (spec.run_id, spec.cwd, spec.pytest_args) for spec in wrapper._TASK5_PARTITIONS
    ) == (
        (
            "admin-no-external",
            "apps/admin-console",
            ("-m", "not requires_classifier_llm", "tests"),
        ),
        (
            "canonical-v2-predecessors",
            "apps/miroflow-agent",
            (
                "tests/canonical_v2",
                "--ignore=tests/canonical_v2/test_consumer_acceptance_contract.py",
            ),
        ),
    )


def test_real_capture_rejects_nonlocal_output_before_runner(
    tmp_path: Path,
) -> None:
    wrapper = _load_wrapper()
    calls = 0

    def runner(**kwargs: object) -> SimpleNamespace:
        nonlocal calls
        del kwargs
        calls += 1
        return SimpleNamespace(returncode=0)

    with pytest.raises(
        wrapper.GuardedPartitionCaptureError,
        match="exact S11C evidence root",
    ):
        wrapper._capture_guarded_partitions(
            repository_root=_REPOSITORY_ROOT,
            output_root=tmp_path / "outside-s11c",
            runner=runner,
            capture_mode="real_subprocess",
        )
    assert calls == 0
    exact_root = (
        _REPOSITORY_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c"
    )
    with pytest.raises(
        wrapper.GuardedPartitionCaptureError,
        match="Accepted default subprocess runner",
    ):
        wrapper._capture_guarded_partitions(
            repository_root=_REPOSITORY_ROOT,
            output_root=exact_root,
            runner=runner,
            capture_mode="real_subprocess",
        )
    assert calls == 0


def test_synthetic_capture_preserves_preexisting_bytes_before_runner(
    tmp_path: Path,
) -> None:
    wrapper = _load_wrapper()
    output_root = tmp_path / "preexisting"
    paths = {
        output_root / "baseline-row.json": b"preexisting baseline\n",
        output_root / "guarded-partitions-receipt.json": b"preexisting receipt\n",
        output_root / "collected" / "admin-no-external.txt": b"nodeids\n",
        output_root / "junit" / "admin-no-external.xml": b"<preexisting />\n",
        output_root / ".guarded-receipt-racing": b"preexisting stage\n",
    }
    for path, raw in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    calls = 0

    def runner(**kwargs: object) -> SimpleNamespace:
        nonlocal calls
        del kwargs
        calls += 1
        return SimpleNamespace(returncode=0)

    with pytest.raises(
        wrapper.GuardedPartitionCaptureError,
        match="target already exists",
    ):
        wrapper._capture_guarded_partitions_for_test(
            repository_root=_REPOSITORY_ROOT,
            output_root=output_root,
            runner=runner,
        )
    assert calls == 0
    assert {path: path.read_bytes() for path in paths} == paths


def test_guarded_wrapper_reuses_accepted_s11b_guard_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = _load_wrapper()
    authority = wrapper.verify_accepted_s11b_authority(_REPOSITORY_ROOT)
    producer = authority.producer

    assert authority.receipt_sha256 == (
        "cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945"
    )
    assert authority.producer_sha256 == (
        "75fd8ea49cf6cab552c0eec1d196c9a41430543e10beb361bde14dd5e4638efa"
    )
    assert authority.owner_sha256 == (
        "47c060bb589bac6ae5c593eea2dfebf3272dd23b12e690662cd3e7322f95e1b3"
    )
    assert len(producer.SENSITIVE_ENV_NAMES) == 49
    assert tuple(sorted(producer.SENSITIVE_ENV_NAMES)) == producer.SENSITIVE_ENV_NAMES
    assert producer._SIGNATURE_VERSION == ("canonical-v2-s11b-baseline-signature-v3")
    assert producer._ADMIN_MARKER == "not requires_classifier_llm"
    assert producer._ADMIN_DESELECTED == (
        "tests/test_classifier_benchmark.py::test_classifier_benchmark",
    )

    calls: list[dict[str, Any]] = []
    observed_temp_roots: set[Path] = set()

    def make_runner(
        *,
        terminal: bool = True,
        invalid_exit: bool = False,
        race_path: Path | None = None,
    ) -> Any:
        def runner(
            *, argv: tuple[str, ...], cwd: Path, env: dict[str, str]
        ) -> SimpleNamespace:
            mode = env["CANONICAL_V2_S11B_MODE"]
            is_admin = cwd.name == "admin-console"
            exitstatus = (
                2 if invalid_exit and mode == "run" else int(is_admin and mode == "run")
            )
            calls.append(
                {
                    "argv": argv,
                    "cwd": cwd,
                    "env": dict(env),
                    "mode": mode,
                    "returned": True,
                }
            )
            assert env["PYTHON_DOTENV_DISABLED"] == "1"
            assert env["PYTEST_PLUGINS"] == (
                "scripts.capture_canonical_v2_s11b_baseline"
            )
            assert "PYTEST_CURRENT_TEST" not in env
            assert all(env[name] == "" for name in producer.SENSITIVE_ENV_NAMES)
            owned_root = Path(env["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"])
            assert owned_root.parent == Path("/tmp")
            assert owned_root.name.startswith("s11b-")
            observed_temp_roots.add(owned_root)
            if is_admin:
                nodeid = "tests/test_admin.py::test_admin"
            else:
                nodeid = "tests/canonical_v2/test_predecessor.py::test_predecessor"
            Path(env["CANONICAL_V2_S11B_NODEIDS_STAGE"]).write_text(
                nodeid + "\n",
                encoding="utf-8",
            )
            guard = _terminal_guard_receipt(
                producer,
                environment=env,
                mode=mode,
                exitstatus=exitstatus,
                deselected_nodeids=(
                    list(producer._ADMIN_DESELECTED) if is_admin else []
                ),
                terminal=(terminal or mode == "collect"),
            )
            Path(env["CANONICAL_V2_S11B_GUARD_RECEIPT"]).write_text(
                json.dumps(guard, sort_keys=True),
                encoding="utf-8",
            )
            if mode == "run":
                _write_synthetic_junit_and_reports(
                    producer,
                    environment=env,
                    nodeid=nodeid,
                    exitstatus=exitstatus,
                )
                if race_path is not None and not is_admin:
                    race_path.parent.mkdir(parents=True, exist_ok=True)
                    race_path.write_bytes(b"racing artifact\n")
            return SimpleNamespace(returncode=exitstatus, stdout="", stderr="")

        return runner

    output_root = tmp_path / "accepted"
    result = wrapper._capture_guarded_partitions_for_test(
        repository_root=_REPOSITORY_ROOT,
        output_root=output_root,
        runner=make_runner(),
    )
    receipt = result.receipt

    assert result.capture_mode == "synthetic_test_only"
    assert receipt["capture_mode"] == "synthetic_test_only"
    assert receipt["schema_version"] == (
        "canonical-v2-s11c-guarded-partitions-receipt-v1"
    )
    assert receipt["signature_schema_version"] == producer._SIGNATURE_VERSION
    assert receipt["accepted_s11b"] == {
        "owner_path": (
            "apps/miroflow-agent/tests/scripts/"
            "test_capture_canonical_v2_s11b_baseline.py"
        ),
        "owner_sha256": authority.owner_sha256,
        "producer_path": (
            "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py"
        ),
        "producer_sha256": authority.producer_sha256,
        "receipt_path": (
            ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
            "s11b/verification-receipt.json"
        ),
        "receipt_sha256": authority.receipt_sha256,
    }
    assert [row["run_id"] for row in receipt["runs"]] == [
        "admin-no-external",
        "canonical-v2-predecessors",
    ]
    assert [row["exit_code"] for row in receipt["runs"]] == [1, 0]
    assert receipt["guard_preflight"]["admin_marker_expression"] == (
        "not requires_classifier_llm"
    )
    assert receipt["guard_preflight"]["admin_deselected_nodeids"] == list(
        producer._ADMIN_DESELECTED
    )
    assert receipt["guard_preflight"]["cleanup"] is True
    assert (
        receipt["guard_preflight"]["terminal_receipts_captured_after_process_exit"]
        is False
    )
    assert len(receipt["guard_preflight"]["child_receipts"]) == 4
    assert all(
        row["session_finished"] is True and row["unconfigured"] is True
        for row in receipt["guard_preflight"]["child_receipts"]
    )
    assert len(calls) == 4
    for run_id, collect_call, run_call in zip(
        (row["run_id"] for row in receipt["runs"]),
        calls[::2],
        calls[1::2],
        strict=True,
    ):
        collect_argv = collect_call["argv"]
        run_argv = run_call["argv"]
        assert "--collect-only" in collect_argv
        assert "--collect-only" not in run_argv
        assert not any(token.startswith("--junitxml=") for token in collect_argv)
        assert sum(token.startswith("--junitxml=") for token in run_argv) == 1
        collect_basetemp = next(
            token for token in collect_argv if token.startswith("--basetemp=")
        )
        run_basetemp = next(
            token for token in run_argv if token.startswith("--basetemp=")
        )
        assert collect_basetemp != run_basetemp
        assert (
            collect_call["cwd"] / collect_basetemp.removeprefix("--basetemp=")
        ).resolve() == (output_root / "tmp" / run_id / "collect" / "pytest").resolve()
        assert (
            run_call["cwd"] / run_basetemp.removeprefix("--basetemp=")
        ).resolve() == (output_root / "tmp" / run_id / "pytest").resolve()
        assert (
            collect_call["env"]["CANONICAL_V2_S11B_PYTEST_TEMP"]
            != run_call["env"]["CANONICAL_V2_S11B_PYTEST_TEMP"]
        )
    assert all(not root.exists() for root in observed_temp_roots)
    assert not list(output_root.glob(".guarded-receipt-*"))
    assert not (output_root / "guarded-partitions-receipt.json").exists()
    assert len(list((output_root / "collected").glob("*.txt"))) == 2
    assert len(list((output_root / "junit").glob("*.xml"))) == 2
    assert result.receipt_bytes == producer._canonical_bytes(receipt)
    assert result.receipt_sha256 == hashlib.sha256(result.receipt_bytes).hexdigest()

    with monkeypatch.context() as patch:
        patch.setattr(wrapper, "_ACCEPTED_PRODUCER_SHA256", "0" * 64)
        with pytest.raises(
            wrapper.GuardedPartitionCaptureError,
            match="Accepted S11B producer hash drifted",
        ):
            wrapper.verify_accepted_s11b_authority(_REPOSITORY_ROOT)

    for name, runner, message in (
        ("nonterminal", make_runner(terminal=False), "child guard receipt"),
        ("exit-two", make_runner(invalid_exit=True), "terminal test outcome"),
    ):
        rejected = tmp_path / name
        with pytest.raises(wrapper.GuardedPartitionCaptureError, match=message):
            wrapper._capture_guarded_partitions_for_test(
                repository_root=_REPOSITORY_ROOT,
                output_root=rejected,
                runner=runner,
            )
        assert not (rejected / "guarded-partitions-receipt.json").exists()
        assert not list((rejected / "collected").glob("*.txt"))
        assert not list((rejected / "junit").glob("*.xml"))
        assert not list(rejected.glob(".guarded-receipt-*"))

    raced = tmp_path / "raced"
    racing_path = raced / "collected" / "admin-no-external.txt"
    with pytest.raises(
        wrapper.GuardedPartitionCaptureError,
        match="artifact appeared during promotion",
    ):
        wrapper._capture_guarded_partitions_for_test(
            repository_root=_REPOSITORY_ROOT,
            output_root=raced,
            runner=make_runner(race_path=racing_path),
        )
    assert racing_path.read_bytes() == b"racing artifact\n"
    assert not (raced / "guarded-partitions-receipt.json").exists()
    assert not list((raced / "junit").glob("*.xml"))
    assert not list(raced.glob(".guarded-receipt-*"))

    aba_root = tmp_path / "post-link-aba"
    first_destination: Path | None = None
    original_promote = wrapper._link_without_overwrite
    link_calls = 0

    def replace_after_first_link(source: Path, destination: Path) -> Any:
        nonlocal first_destination, link_calls
        link_calls += 1
        if link_calls == 1:
            owned = original_promote(source, destination)
            first_destination = destination
            return owned
        assert first_destination is not None
        first_destination.unlink()
        first_destination.write_bytes(b"foreign post-link replacement\n")
        raise wrapper.GuardedPartitionCaptureError("artifact appeared during promotion")

    with monkeypatch.context() as patch:
        patch.setattr(wrapper, "_link_without_overwrite", replace_after_first_link)
        with pytest.raises(
            wrapper.GuardedPartitionCaptureError,
            match="artifact appeared during promotion",
        ):
            wrapper._capture_guarded_partitions_for_test(
                repository_root=_REPOSITORY_ROOT,
                output_root=aba_root,
                runner=make_runner(),
            )
    assert first_destination is not None
    assert first_destination.read_bytes() == b"foreign post-link replacement\n"
    assert not (aba_root / "guarded-partitions-receipt.json").exists()
    assert not list(aba_root.glob(".guarded-receipt-*"))
    assert all(not root.exists() for root in observed_temp_roots)
