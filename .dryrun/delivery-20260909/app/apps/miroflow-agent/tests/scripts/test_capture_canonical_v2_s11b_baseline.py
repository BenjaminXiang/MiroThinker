"""Focused deterministic owner for the guarded S11B baseline producer."""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import xml.etree.ElementTree as ET

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]


def _assert_short_owned_temp_root(
    environment: dict[str, str],
    observed_roots: set[Path],
) -> None:
    owned_root = Path(environment["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"])
    assert len(os.fsencode(owned_root / "guard-probe.sock")) <= 107
    assert owned_root.parent == Path("/tmp")
    assert owned_root.name.startswith("s11b-")
    assert owned_root.stat().st_mode & 0o777 == 0o700
    for name in (
        "TMPDIR",
        "TMP",
        "TEMP",
        "CANONICAL_V2_S11B_STAGE",
        "CANONICAL_V2_S11B_NODEIDS_STAGE",
        "CANONICAL_V2_S11B_JUNIT_STAGE",
        "CANONICAL_V2_S11B_REPORTS_STAGE",
        "CANONICAL_V2_S11B_GUARD_RECEIPT",
        "CANONICAL_V2_S11B_PYTEST_TEMP",
    ):
        Path(environment[name]).relative_to(owned_root)
    observed_roots.add(owned_root)


def test_baseline_producer_freezes_partitions_environment_and_atomic_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    assert len(producer.SENSITIVE_ENV_NAMES) == 49
    assert tuple(sorted(producer.SENSITIVE_ENV_NAMES)) == producer.SENSITIVE_ENV_NAMES
    assert producer._SIGNATURE_VERSION == "canonical-v2-s11b-baseline-signature-v3"
    assert (
        producer._GUARD_VERSIONS_RECEIPT["attempt_attribution"]
        == "pytest-current-test-report-v1"
    )
    assert [spec.run_id for spec in producer.RUN_SPECS] == [
        "canonical-v2-no-external",
        "admin-no-external",
    ]
    assert all("-k" not in spec.argv for spec in producer.RUN_SPECS)
    assert (
        producer.RUN_SPECS[1].argv[producer.RUN_SPECS[1].argv.index("-m") + 1]
        == "not requires_classifier_llm"
    )

    calls: list[dict[str, Any]] = []
    observed_roots: set[Path] = set()

    def runner(
        *, argv: tuple[str, ...], cwd: Path, env: dict[str, str]
    ) -> SimpleNamespace:
        calls.append({"argv": argv, "cwd": cwd, "env": dict(env)})
        assert env["PYTHON_DOTENV_DISABLED"] == "1"
        assert "PYTEST_CURRENT_TEST" not in env
        assert all(env[name] == "" for name in producer.SENSITIVE_ENV_NAMES)
        _assert_short_owned_temp_root(env, observed_roots)
        Path(env["CANONICAL_V2_S11B_NODEIDS_STAGE"]).write_text(
            "tests/example.py::test_example\n", encoding="utf-8"
        )
        mode = env["CANONICAL_V2_S11B_MODE"]
        deselected = (
            ["tests/test_classifier_benchmark.py::test_classifier_benchmark"]
            if cwd.name == "admin-console"
            else []
        )
        guard = {
            "schema_version": "canonical-v2-s11b-child-guard-v3",
            "mode": mode,
            "early_hook_installed": True,
            "present_empty_sensitive_env_names": list(producer.SENSITIVE_ENV_NAMES),
            "probes": {name: True for name in producer._PROBE_NAMES},
            "blocked_test_attempts": (
                [
                    {
                        "kind": "af_inet_connect_blocked",
                        "message": "AF_INET access is blocked",
                        "nodeid": "tests/example.py::test_example",
                        "phase": "call",
                    }
                ]
                if mode == "run" and cwd.name == "admin-console"
                else []
            ),
            "forbidden_attempts": [],
            "socket_policy": producer._SOCKET_POLICY_RECEIPT,
            "allowed_owned_loopback_connects": [],
            "owned_temp_root": env["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"],
            "pytest_temp_root": env["CANONICAL_V2_S11B_PYTEST_TEMP"],
            "deselected_nodeids": deselected,
            "session_finished": True,
            "unconfigured": True,
            "exitstatus": 0,
            "guard_versions": producer._GUARD_VERSIONS_RECEIPT,
        }
        Path(env["CANONICAL_V2_S11B_GUARD_RECEIPT"]).write_text(
            json.dumps(guard), encoding="utf-8"
        )
        if mode == "run":
            Path(env["CANONICAL_V2_S11B_JUNIT_STAGE"]).write_text(
                '<testsuites tests="1" failures="0" errors="0">'
                '<testsuite tests="1" failures="0" errors="0">'
                '<testcase classname="tests.example" name="test_example" />'
                "</testsuite></testsuites>",
                encoding="utf-8",
            )
            Path(env["CANONICAL_V2_S11B_REPORTS_STAGE"]).write_text(
                "".join(
                    json.dumps(
                        {
                            "nodeid": "tests/example.py::test_example",
                            "phase": phase,
                            "outcome": "passed",
                        }
                    )
                    + "\n"
                    for phase in ("setup", "call", "teardown")
                ),
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    output_root = (
        tmp_path
        / ("artificially-deep-output-root-" + "x" * 80)
        / ("nested-baseline-root-" + "y" * 80)
        / "baseline"
    )
    original_link = producer.os.link

    def cross_device_link_guard(source: Any, destination: Any) -> None:
        source_path = Path(os.fsdecode(source))
        if any(source_path.is_relative_to(root) for root in observed_roots):
            raise OSError(errno.EXDEV, "forced cross-device producer boundary")
        original_link(source, destination)

    monkeypatch.setattr(producer.os, "link", cross_device_link_guard)
    receipt = producer.capture_baseline(
        repository_root=_REPO_ROOT,
        output_root=output_root,
        runner=runner,
    )
    baseline = receipt["broad_test_baseline"]
    assert baseline["guard_preflight"]["present_empty_sensitive_env_names"] == list(
        producer.SENSITIVE_ENV_NAMES
    )
    assert baseline["guard_preflight"]["cleanup"] is True
    assert baseline["guard_preflight"]["pytest_temp_roots"] == {
        spec.run_id: {
            "collect": calls[index * 2]["env"]["CANONICAL_V2_S11B_PYTEST_TEMP"],
            "run": calls[index * 2 + 1]["env"]["CANONICAL_V2_S11B_PYTEST_TEMP"],
        }
        for index, spec in enumerate(producer.RUN_SPECS)
    }
    assert "pytest_temp_root" not in baseline["guard_preflight"]
    assert baseline["guard_preflight"]["blocked_test_attempt_count"] == 1
    assert baseline["guard_preflight"]["blocked_test_attempts"] == [
        {
            "kind": "af_inet_connect_blocked",
            "message": "AF_INET access is blocked",
            "nodeid": "tests/example.py::test_example",
            "phase": "call",
            "report_outcome": "passed",
            "run_id": "admin-no-external",
        }
    ]
    assert baseline["guard_preflight"]["forbidden_attempts"] == []
    assert len(baseline["runs"]) == 2
    assert len(calls) == 4
    assert len(observed_roots) == 1
    assert all(not root.exists() for root in observed_roots)
    assert all(
        Path(row["collected_nodeids_path"]).name.endswith(".txt")
        for row in baseline["runs"]
    )
    assert all(
        Path(row["junit_xml_path"]).name.endswith(".xml") for row in baseline["runs"]
    )

    with pytest.raises(producer.BaselineCaptureError):
        producer.capture_baseline(
            repository_root=_REPO_ROOT,
            output_root=output_root,
            runner=runner,
        )


@pytest.mark.parametrize(
    "tamper",
    (
        "forbidden",
        "attempt-nodeid-drift",
        "attempt-report-duplicate",
        "collect-attempt",
        "collect-owned-loopback",
        "exitstatus-drift",
        "nodeid-drift",
        "partial",
        "junit-mismatch",
        "missing-call",
        "junit-outcome-drift",
        "terminal-exit-code",
        "interrupt",
    ),
)
def test_baseline_producer_rejects_partial_guarded_output_atomically(
    tmp_path: Path,
    tamper: str,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    observed_roots: set[Path] = set()

    def runner(
        *, argv: tuple[str, ...], cwd: Path, env: dict[str, str]
    ) -> SimpleNamespace:
        del argv
        _assert_short_owned_temp_root(env, observed_roots)
        mode = env["CANONICAL_V2_S11B_MODE"]
        if tamper == "interrupt" and mode == "run":
            raise KeyboardInterrupt
        nodeid = (
            "tests/drift.py::test_drift"
            if tamper == "nodeid-drift" and mode == "run"
            else "tests/example.py::test_example"
        )
        Path(env["CANONICAL_V2_S11B_NODEIDS_STAGE"]).write_text(
            nodeid + "\n", encoding="utf-8"
        )
        guard = {
            "schema_version": "canonical-v2-s11b-child-guard-v3",
            "mode": mode,
            "early_hook_installed": True,
            "present_empty_sensitive_env_names": list(producer.SENSITIVE_ENV_NAMES),
            "probes": {name: True for name in producer._PROBE_NAMES},
            "blocked_test_attempts": (
                [
                    {
                        "kind": "af_inet_connect_blocked",
                        "message": "AF_INET access is blocked",
                        "nodeid": "tests/other.py::test_other",
                        "phase": "call",
                    }
                ]
                if tamper == "attempt-nodeid-drift" and mode == "run"
                else [
                    {
                        "kind": "af_inet_connect_blocked",
                        "message": "AF_INET access is blocked",
                        "nodeid": "tests/example.py::test_example",
                        "phase": "call",
                    }
                ]
                if tamper == "attempt-report-duplicate" and mode == "run"
                else [
                    {
                        "kind": "af_inet_connect_blocked",
                        "message": "AF_INET access is blocked",
                        "nodeid": "tests/example.py::test_example",
                        "phase": "call",
                    }
                ]
                if tamper == "collect-attempt" and mode == "collect"
                else []
            ),
            "forbidden_attempts": (
                [{"kind": "network", "message": "blocked"}]
                if tamper == "forbidden"
                else []
            ),
            "socket_policy": producer._SOCKET_POLICY_RECEIPT,
            "allowed_owned_loopback_connects": (
                [
                    {
                        "destination_host": "127.0.0.1",
                        "destination_port": 49152,
                        "family": "AF_INET",
                        "listener_host": "127.0.0.1",
                        "listener_port": 49152,
                        "operation": "connect",
                    }
                ]
                if tamper == "collect-owned-loopback" and mode == "collect"
                else []
            ),
            "owned_temp_root": env["CANONICAL_V2_S11B_ALLOWED_UNIX_ROOT"],
            "pytest_temp_root": env["CANONICAL_V2_S11B_PYTEST_TEMP"],
            "deselected_nodeids": (
                ["tests/test_classifier_benchmark.py::test_classifier_benchmark"]
                if cwd.name == "admin-console"
                else []
            ),
            "session_finished": True,
            "unconfigured": True,
            "exitstatus": (
                3
                if tamper == "exitstatus-drift" and mode == "run"
                else 2
                if tamper == "terminal-exit-code" and mode == "run"
                else 0
            ),
            "guard_versions": producer._GUARD_VERSIONS_RECEIPT,
        }
        Path(env["CANONICAL_V2_S11B_GUARD_RECEIPT"]).write_text(
            json.dumps(guard), encoding="utf-8"
        )
        if mode == "run":
            if tamper == "junit-mismatch":
                terminal = "<failure />"
            elif tamper == "junit-outcome-drift":
                terminal = "<skipped />"
            else:
                terminal = ""
            junit = (
                '<testsuites><testsuite><testcase classname="tests.example" '
                f'name="test_example">{terminal}</testcase></testsuite></testsuites>'
            )
            Path(env["CANONICAL_V2_S11B_JUNIT_STAGE"]).write_text(
                junit, encoding="utf-8"
            )
            if tamper != "partial":
                rows = [
                    {
                        "nodeid": nodeid,
                        "phase": phase,
                        "outcome": "passed",
                    }
                    for phase in ("setup", "call", "teardown")
                    if not (tamper == "missing-call" and phase == "call")
                ]
                if tamper == "attempt-report-duplicate":
                    rows.append(dict(rows[1]))
                Path(env["CANONICAL_V2_S11B_REPORTS_STAGE"]).write_text(
                    "".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8",
                )
        return SimpleNamespace(
            returncode=(2 if tamper == "terminal-exit-code" and mode == "run" else 0),
            stdout="",
            stderr="",
        )

    output_root = tmp_path / "baseline"
    expected = (
        KeyboardInterrupt if tamper == "interrupt" else producer.BaselineCaptureError
    )
    with pytest.raises(expected):
        producer.capture_baseline(
            repository_root=_REPO_ROOT,
            output_root=output_root,
            runner=runner,
        )
    assert not (output_root / "baseline-row.json").exists()
    assert not list((output_root / "collected").glob("*.txt"))
    assert not list((output_root / "junit").glob("*.xml"))
    assert not list(output_root.glob(".stage-*"))
    assert observed_roots
    assert all(not root.exists() for root in observed_roots)


def test_real_child_allows_owned_loopback_http_and_receipts_exact_connect(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    project = tmp_path / "project"
    project.mkdir()
    result_path = project / "result.json"
    (project / "test_owned_http.py").write_text(
        "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
        "import json\n"
        "from threading import Thread\n"
        "from urllib.request import urlopen\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        body = b'owned-loopback-ok'\n"
        "        self.send_response(200)\n"
        "        self.send_header('content-length', str(len(body)))\n"
        "        self.end_headers()\n"
        "        self.wfile.write(body)\n"
        "    def log_message(self, format, *args):\n"
        "        pass\n"
        "def test_owned_loopback_http():\n"
        "    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)\n"
        "    thread = Thread(target=server.serve_forever, daemon=True)\n"
        "    thread.start()\n"
        "    try:\n"
        "        with urlopen("  # noqa: S310 - exact guarded numeric loopback.
        "f'http://127.0.0.1:{server.server_port}/health', timeout=5) as response:\n"
        "            body = response.read().decode()\n"
        "            assert response.status == 200\n"
        "            assert body == 'owned-loopback-ok'\n"
        f"        with open({str(result_path)!r}, 'w', encoding='utf-8') as stream:\n"
        "            json.dump({'body': body, 'port': server.server_port, "
        "'status': response.status}, stream, sort_keys=True)\n"
        "    finally:\n"
        "        server.shutdown()\n"
        "        thread.join(timeout=5)\n"
        "        server.server_close()\n",
        encoding="utf-8",
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    owned_temp = Path(tempfile.mkdtemp(prefix="s11b-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(owned_temp, ignore_errors=True))
    for name in ("tmpdir", "tmp", "temp"):
        (owned_temp / name).mkdir()
    nodeids = stage / "nodeids.txt"
    junit = stage / "junit.xml"
    reports = stage / "reports.jsonl"
    guard = stage / "guard.json"
    pytest_temp = owned_temp / "pytest"
    environment = producer._child_environment(
        repository_root=_REPO_ROOT,
        mode="run",
        stage=stage,
        temp_root=owned_temp,
        nodeids=nodeids,
        junit=junit,
        reports=reports,
        guard_receipt=guard,
        pytest_temp=pytest_temp,
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-q",
            "test_owned_http.py",
        ],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(result_path.read_text())
    assert result["status"] == 200
    assert result["body"] == "owned-loopback-ok"
    receipt = producer._parse_guard_receipt(
        guard,
        environment=environment,
        mode="run",
    )
    assert receipt["blocked_test_attempts"] == []
    assert receipt["forbidden_attempts"] == []
    assert receipt["socket_policy"] == producer._SOCKET_POLICY_RECEIPT
    assert receipt["allowed_owned_loopback_connects"] == [
        {
            "destination_host": "127.0.0.1",
            "destination_port": result["port"],
            "family": "AF_INET",
            "listener_host": "127.0.0.1",
            "listener_port": result["port"],
            "operation": "connect",
        }
    ]


def test_real_child_rejects_listener_side_getsockname_spoof(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    unowned = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unowned.bind(("127.0.0.1", 0))
    unowned.listen(1)
    unowned_port = unowned.getsockname()[1]
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_hostile_listener.py").write_text(
        "import socket\n"
        "from scripts.capture_canonical_v2_s11b_baseline import BaselineCaptureError\n"
        "class EqualEndpoint(tuple):\n"
        "    def __eq__(self, other):\n"
        "        return True\n"
        "class HostileListener(socket.socket):\n"
        "    hostile = False\n"
        "    def getsockname(self):\n"
        "        endpoint = super().getsockname()\n"
        "        return EqualEndpoint(endpoint) if self.hostile else endpoint\n"
        "def test_listener_spoof_cannot_authorize_unowned_port():\n"
        "    listener = HostileListener(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    try:\n"
        "        listener.bind(('127.0.0.1', 0))\n"
        "        listener.listen(1)\n"
        "        owned_port = socket.socket.getsockname(listener)[1]\n"
        f"        assert owned_port != {unowned_port}\n"
        "        listener.hostile = True\n"
        "        try:\n"
        f"            client.connect(('127.0.0.1', {unowned_port}))\n"
        "        except BaselineCaptureError:\n"
        "            pass\n"
        "        else:\n"
        "            raise AssertionError(\n"
        "                'hostile listener authorized unowned pre-guard port'\n"
        "            )\n"
        "    finally:\n"
        "        client.close()\n"
        "        listener.close()\n",
        encoding="utf-8",
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    owned_temp = Path(tempfile.mkdtemp(prefix="s11b-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(owned_temp, ignore_errors=True))
    for name in ("tmpdir", "tmp", "temp"):
        (owned_temp / name).mkdir()
    nodeids = stage / "nodeids.txt"
    junit = stage / "junit.xml"
    reports = stage / "reports.jsonl"
    guard = stage / "guard.json"
    pytest_temp = owned_temp / "pytest"
    environment = producer._child_environment(
        repository_root=_REPO_ROOT,
        mode="run",
        stage=stage,
        temp_root=owned_temp,
        nodeids=nodeids,
        junit=junit,
        reports=reports,
        guard_receipt=guard,
        pytest_temp=pytest_temp,
    )
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
                "-q",
                "test_hostile_listener.py",
            ],
            cwd=project,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        unowned.close()
    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt = json.loads(guard.read_text())
    assert receipt["schema_version"] == "canonical-v2-s11b-child-guard-v3"
    assert receipt["blocked_test_attempts"] == [
        {
            "kind": "af_inet_connect_blocked",
            "message": "AF_INET access is blocked",
            "nodeid": "test_hostile_listener.py::test_listener_spoof_cannot_authorize_unowned_port",
            "phase": "call",
        }
    ]
    assert receipt["forbidden_attempts"] == []
    assert receipt["allowed_owned_loopback_connects"] == []


def test_real_child_installs_guard_before_conftest_and_restores_dotenv(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    project = tmp_path / "project"
    project.mkdir()
    dotenv_path = project / "mutation.env"
    dotenv_path.write_text("OPENAI_API_KEY=forbidden-child\n", encoding="utf-8")
    (project / "conftest.py").write_text(
        "import os\n"
        "import socket\n"
        "import dotenv\n"
        "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "try:\n"
        "    sock.connect(('127.0.0.1', 9))\n"
        "except Exception:\n"
        "    pass\n"
        "finally:\n"
        "    sock.close()\n"
        f"try:\n    dotenv.load_dotenv({str(dotenv_path)!r}, override=True)\n"
        "except Exception:\n    pass\n"
        "assert os.environ['OPENAI_API_KEY'] == ''\n",
        encoding="utf-8",
    )
    (project / "test_safe.py").write_text(
        "import os\n"
        "import socket\n"
        "from pathlib import Path\n"
        "from threading import Thread\n"
        "from scripts.capture_canonical_v2_s11b_baseline import BaselineCaptureError\n"
        "class SpoofHost(str):\n"
        "    def __eq__(self, other):\n"
        "        return other == '127.0.0.1'\n"
        "    def __ne__(self, other):\n"
        "        return False\n"
        "class SpoofAddress(tuple):\n"
        "    def __getitem__(self, index):\n"
        "        if index == 0:\n"
        "            return '127.0.0.1'\n"
        "        return super().__getitem__(index)\n"
        "def assert_guard_blocked(address):\n"
        "    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    try:\n"
        "        client.connect(address)\n"
        "    except BaselineCaptureError:\n"
        "        pass\n"
        "    except ConnectionRefusedError as exc:\n"
        "        raise AssertionError('hostile address bypassed socket guard') from exc\n"
        "    else:\n"
        "        raise AssertionError('hostile address unexpectedly connected')\n"
        "    finally:\n"
        "        client.close()\n"
        "def test_safe(tmp_path):\n"
        "    tmp_path.relative_to(Path(os.environ['CANONICAL_V2_S11B_PYTEST_TEMP']))\n"
        "    closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    closed.bind(('127.0.0.1', 0))\n"
        "    closed.listen(1)\n"
        "    closed_endpoint = closed.getsockname()\n"
        "    closed.close()\n"
        "    assert_guard_blocked(closed_endpoint)\n"
        "    worker = Thread(target=assert_guard_blocked, args=(closed_endpoint,))\n"
        "    worker.start()\n"
        "    worker.join(timeout=5)\n"
        "    assert not worker.is_alive()\n"
        "    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    try:\n"
        "        listener.bind(('127.0.0.1', 0))\n"
        "        listener.listen(1)\n"
        "        port = listener.getsockname()[1]\n"
        "        assert_guard_blocked((SpoofHost('127.0.0.2'), port))\n"
        "        assert_guard_blocked(SpoofAddress(('127.0.0.2', port)))\n"
        "    finally:\n"
        "        listener.close()\n"
        "    os.environ.pop('HTTP_PROXY', None)\n",
        encoding="utf-8",
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    owned_temp = Path(tempfile.mkdtemp(prefix="s11b-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(owned_temp, ignore_errors=True))
    for name in ("tmpdir", "tmp", "temp"):
        (owned_temp / name).mkdir()
    nodeids = stage / "nodeids.txt"
    junit = stage / "junit.xml"
    reports = stage / "reports.jsonl"
    guard = stage / "guard.json"
    pytest_temp = owned_temp / "pytest"
    environment = producer._child_environment(
        repository_root=_REPO_ROOT,
        mode="run",
        stage=stage,
        temp_root=owned_temp,
        nodeids=nodeids,
        junit=junit,
        reports=reports,
        guard_receipt=guard,
        pytest_temp=pytest_temp,
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-q",
            "test_safe.py",
        ],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt = json.loads(guard.read_text())
    assert receipt["early_hook_installed"] is True
    assert receipt["probes"] == {name: True for name in producer._PROBE_NAMES}
    assert len(receipt["blocked_test_attempts"]) == 4
    assert {item["nodeid"] for item in receipt["blocked_test_attempts"]} == {
        "test_safe.py::test_safe"
    }
    assert {item["phase"] for item in receipt["blocked_test_attempts"]} == {"call"}
    assert {item["kind"] for item in receipt["forbidden_attempts"]} == {
        "af_inet_connect_blocked",
        "dotenv_mutation_restored",
    }
    assert [item["kind"] for item in receipt["forbidden_attempts"]].count(
        "af_inet_connect_blocked"
    ) == 1
    assert receipt["present_empty_sensitive_env_names"] == list(
        producer.SENSITIVE_ENV_NAMES
    )
    assert receipt["allowed_owned_loopback_connects"] == []
    assert receipt["session_finished"] is True
    assert receipt["unconfigured"] is True
    assert pytest_temp.is_dir()


def test_real_child_keeps_guard_through_concurrent_atexit_workers(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()
    worker_count = 24
    project = tmp_path / "project"
    project.mkdir()
    result_path = project / "late-result.json"
    (project / "test_late_guard.py").write_text(
        "import atexit\n"
        "import json\n"
        "import socket\n"
        "from threading import Barrier, Lock, Thread\n"
        "from scripts.capture_canonical_v2_s11b_baseline import BaselineCaptureError\n"
        f"WORKER_COUNT = {worker_count}\n"
        f"CLOSED_PORT = {closed_port}\n"
        f"RESULT_PATH = {str(result_path)!r}\n"
        "def late_probe():\n"
        "    barrier = Barrier(WORKER_COUNT + 1)\n"
        "    lock = Lock()\n"
        "    outcomes = []\n"
        "    def worker():\n"
        "        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "        barrier.wait()\n"
        "        try:\n"
        "            client.connect(('127.0.0.1', CLOSED_PORT))\n"
        "        except BaselineCaptureError:\n"
        "            outcome = 'blocked'\n"
        "        except OSError:\n"
        "            outcome = 'escaped-guard'\n"
        "        else:\n"
        "            outcome = 'connected'\n"
        "        finally:\n"
        "            client.close()\n"
        "        with lock:\n"
        "            outcomes.append(outcome)\n"
        "    workers = [Thread(target=worker) for _ in range(WORKER_COUNT)]\n"
        "    for thread in workers:\n"
        "        thread.start()\n"
        "    barrier.wait()\n"
        "    for thread in workers:\n"
        "        thread.join(timeout=5)\n"
        "    assert all(not thread.is_alive() for thread in workers)\n"
        "    with open(RESULT_PATH, 'w', encoding='utf-8') as stream:\n"
        "        json.dump(sorted(outcomes), stream)\n"
        "atexit.register(late_probe)\n"
        "def test_registers_late_probe():\n"
        "    pass\n",
        encoding="utf-8",
    )
    stage = tmp_path / "stage-late"
    stage.mkdir()
    owned_temp = Path(tempfile.mkdtemp(prefix="s11b-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(owned_temp, ignore_errors=True))
    for name in ("tmpdir", "tmp", "temp"):
        (owned_temp / name).mkdir()
    environment = producer._child_environment(
        repository_root=_REPO_ROOT,
        mode="run",
        stage=stage,
        temp_root=owned_temp,
        nodeids=stage / "nodeids.txt",
        junit=stage / "junit.xml",
        reports=stage / "reports.jsonl",
        guard_receipt=stage / "guard.json",
        pytest_temp=owned_temp / "pytest",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-q",
            "test_late_guard.py",
        ],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(result_path.read_text()) == ["blocked"] * worker_count
    receipt = json.loads((stage / "guard.json").read_text())
    assert receipt["unconfigured"] is True
    assert receipt["blocked_test_attempts"] == []
    assert (
        receipt["forbidden_attempts"]
        == [{"kind": "af_inet_connect_blocked", "message": "AF_INET access is blocked"}]
        * worker_count
    )


def test_junit_failure_rows_rejects_canonical_identity_on_wrong_testcase(
    tmp_path: Path,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    junit = tmp_path / "wrong-testcase.xml"
    signature = "a" * 64
    junit.write_text(
        '<testsuites><testsuite><testcase classname="tests.alpha" name="test_alpha">'
        '<failure canonical_nodeid="tests/beta.py::test_beta" '
        'canonical_phase="call" canonical_outcome="failure" '
        f'canonical_signature="{signature}" />'
        "</testcase></testsuite></testsuites>",
        encoding="utf-8",
    )

    with pytest.raises(
        producer.BaselineCaptureError,
        match="JUnit failure testcase identity differs",
    ):
        producer._junit_failure_rows(
            junit,
            repository_root=tmp_path / "repository",
            temp_root=tmp_path / "pytest-root",
        )


def test_failure_normalization_uses_frozen_recomputable_tokens(
    tmp_path: Path,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    repository_root = tmp_path / "repository"
    pytest_root = repository_root / ".agents" / "pytest-root"
    value = (
        f"{repository_root}/apps/example.py\r\n"
        f"{pytest_root}/case/output.txt\n"
        f"{repository_root}"
    )

    assert (
        producer._normalize(
            value,
            repository_root=repository_root,
            temp_root=pytest_root,
        )
        == "<repo>/apps/example.py\n<pytest-tmp>/case/output.txt\n<repo>/"
    )


def test_junit_failure_rows_rejects_nonrecomputable_embedded_signature(
    tmp_path: Path,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    junit = tmp_path / "tampered-signature.xml"
    signature = "a" * 64
    junit.write_text(
        '<testsuites><testsuite><testcase classname="tests.alpha" name="test_alpha">'
        '<failure message="exact failure" '
        'canonical_nodeid="tests/alpha.py::test_alpha" '
        'canonical_phase="call" canonical_outcome="failure" '
        f'canonical_signature="{signature}">exact body</failure>'
        "</testcase></testsuite></testsuites>",
        encoding="utf-8",
    )

    with pytest.raises(
        producer.BaselineCaptureError,
        match="JUnit failure signature is not independently recomputable",
    ):
        producer._junit_failure_rows(
            junit,
            repository_root=tmp_path / "repository",
            temp_root=tmp_path / "pytest-root",
        )


def test_real_child_binds_sorted_failure_rows_to_exact_junit_testcase(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    from scripts import capture_canonical_v2_s11b_baseline as producer

    project = tmp_path / "project-junit-binding"
    project.mkdir()
    (project / "test_failure_binding.py").write_text(
        "def test_z_collected_first(tmp_path):\n"
        "    assert False, f'z failure belongs to z testcase: {tmp_path}'\n"
        "def test_a_collected_second(tmp_path):\n"
        "    assert False, f'a failure belongs to a testcase: {tmp_path}'\n",
        encoding="utf-8",
    )
    stage = tmp_path / "stage-junit-binding"
    stage.mkdir()
    owned_temp = Path(tempfile.mkdtemp(prefix="s11b-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(owned_temp, ignore_errors=True))
    for name in ("tmpdir", "tmp", "temp"):
        (owned_temp / name).mkdir()
    environment = producer._child_environment(
        repository_root=_REPO_ROOT,
        mode="run",
        stage=stage,
        temp_root=owned_temp,
        nodeids=stage / "nodeids.txt",
        junit=stage / "junit.xml",
        reports=stage / "reports.jsonl",
        guard_receipt=stage / "guard.json",
        pytest_temp=owned_temp / "pytest",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-q",
            "test_failure_binding.py",
        ],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    tree = ET.parse(stage / "junit.xml")
    observed: dict[str, str] = {}
    for testcase in tree.findall(".//testcase"):
        failure = testcase.find("failure")
        assert failure is not None
        observed[testcase.get("name", "")] = failure.get("canonical_nodeid", "")
        message = producer._normalize(
            failure.get("message", ""),
            repository_root=_REPO_ROOT,
            temp_root=owned_temp / "pytest",
        )
        body = producer._normalize(
            failure.text or "",
            repository_root=_REPO_ROOT,
            temp_root=owned_temp / "pytest",
        )
        assert "<pytest-tmp>/" in body
        expected_signature = hashlib.sha256(
            f"failure\n{message}\n{body}".encode("utf-8")
        ).hexdigest()
        assert failure.get("canonical_signature") == expected_signature
    assert observed == {
        "test_a_collected_second": "test_failure_binding.py::test_a_collected_second",
        "test_z_collected_first": "test_failure_binding.py::test_z_collected_first",
    }
