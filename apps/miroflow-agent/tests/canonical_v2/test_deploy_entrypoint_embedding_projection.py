"""The site's key *file* must reach the candidate embedding slot too.

The sibling slice pins the page's half of this symmetry: one
``embedding.api_key`` field in ``/admin`` fills both authority slots
(``SGLANG_API_KEY`` for the recorded/self-hosted authority through
``load_local_api_key()``, ``CANONICAL_V2_EMBEDDING_API_KEY`` for the candidate
gateway authority — the slot its bundle's frozen ``api_key_source`` names).
This file pins the **deployment** half: a site that only drops the four key
files into ``secrets/`` (``CONFIG-GUIDE.md`` §2, ``README-FIRST.txt`` step ①)
must get the same two slots filled, because the file route is the way the
install-time flow provides credentials.

The projection lives at the container boundary (``deploy/docker/entrypoint.sh``)
because the candidate read side is deliberately closed: a bundle may only read
the slot it declared, so the file cannot be handed to it by the loader.

Precedence under test (high → low): explicit environment variable → managed
credential written by ``/admin`` → the key file.

Fixtures: the real ``entrypoint.sh`` over scratch paths, the real
``load_local_api_key`` reader. No network, no containers, no live state
directory; every value here is a locally generated fake (a real key never enters
a test or a log).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from src.data_agents.providers.local_api_key import load_local_api_key

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENTRYPOINT = _REPO_ROOT / "deploy" / "docker" / "entrypoint.sh"

_CANDIDATE_SLOT = "CANONICAL_V2_EMBEDDING_API_KEY"
_LOCAL_SLOTS = ("SGLANG_API_KEY", "OPENAI_API_KEY", "API_KEY")
_RECEIPT_MODE_ENV = "MIROTHINKER_ENTRYPOINT_ENV_RECEIPT"
_KEY_FILE_ENV = "MIROTHINKER_EMBEDDING_KEY_FILE"
# Locally generated fakes; nothing here is a real credential.
_FILE_KEY = "sk-fake-file-route-0000-1111-2222"
_ENV_KEY = "sk-fake-explicit-env-3333-4444-5555"
_MANAGED_KEY = "sk-fake-managed-page-6666-7777-8888"


def _write_key_file(directory: Path, value: str = _FILE_KEY) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    key_file = directory / ".sglang_api_key"
    key_file.write_text(value + "\n", encoding="utf-8")
    return key_file


def _write_managed_secrets(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"schema_version": 1, "secrets": {"embedding.api_key": "%s"}}' % value,
        encoding="utf-8",
    )
    return path


def _run_entrypoint(
    tmp_path: Path,
    *,
    key_file: Path | None,
    managed_secrets: Path | None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the shipped entrypoint in receipt mode over scratch paths.

    The entrypoint's frozen container paths do not exist here, and its real
    start script must never be reached from a test host — the receipt mode is
    what makes both true. A checkout whose entrypoint lacks that mode would
    fall through to ``exec``, so refuse to run instead of risking it.
    """

    if _RECEIPT_MODE_ENV not in _ENTRYPOINT.read_text(encoding="utf-8"):
        pytest.fail(
            f"{_ENTRYPOINT} has no {_RECEIPT_MODE_ENV} mode: this test refuses to run "
            "the start script (it would exec the live serving line on this host)"
        )

    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "MIROTHINKER_SKIP_PREFLIGHT": "1",
        _RECEIPT_MODE_ENV: "1",
        _KEY_FILE_ENV: str(key_file)
        if key_file
        else str(tmp_path / "absent" / ".sglang_api_key"),
        "CANONICAL_V2_MANAGED_SECRETS": str(
            managed_secrets
            if managed_secrets
            else tmp_path / "no-managed" / "secrets.json"
        ),
        **(extra_env or {}),
    }
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["bash", str(_ENTRYPOINT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _receipt_slot(output: str, name: str) -> str:
    match = re.search(rf"环境槽位\s+{name}=(\S+)", output)
    assert match, f"no receipt line for {name} in:\n{output}"
    return match.group(1)


def test_file_route_fills_both_authority_slots(tmp_path: Path) -> None:
    """只给文件：v1 槽位（读文件）与候选网关槽位（环境变量）都要有凭据。

    Chain: ``secrets/.sglang_api_key`` on disk → the shipped entrypoint → the
    child process it would exec (the receipt is printed *by* that child, so the
    value must really be exported). The v1 half is asserted with the real
    reader, ``load_local_api_key``, run against the same directory.
    """

    for name in _LOCAL_SLOTS:
        os.environ.pop(name, None)  # the local reader must fall through to the file
    key_dir = tmp_path / "secrets"
    key_file = _write_key_file(key_dir)

    result = _run_entrypoint(tmp_path, key_file=key_file, managed_secrets=None)

    assert result.returncode == 0, result.stderr
    assert _receipt_slot(result.stdout, _CANDIDATE_SLOT) == "已设置"
    assert load_local_api_key(key_dir) == _FILE_KEY  # v1 slot, file route, unchanged
    assert _FILE_KEY not in result.stdout and _FILE_KEY not in result.stderr


def test_explicit_environment_wins_over_the_key_file(tmp_path: Path) -> None:
    """显式设了环境变量就不许被文件覆盖（既有语义：service unit 是权威）。"""

    key_file = _write_key_file(tmp_path / "secrets")
    result = _run_entrypoint(
        tmp_path,
        key_file=key_file,
        managed_secrets=None,
        extra_env={_CANDIDATE_SLOT: _ENV_KEY},
    )

    assert result.returncode == 0, result.stderr
    assert _receipt_slot(result.stdout, _CANDIDATE_SLOT) == "已设置"
    assert "已显式设置" in result.stdout  # the explicit-env branch ran …
    assert "key 文件 →" not in result.stdout  # … so the file branch did not
    assert _ENV_KEY not in result.stdout and _FILE_KEY not in result.stdout


def test_managed_page_credential_owns_the_slot_over_the_key_file(
    tmp_path: Path,
) -> None:
    """页面写过 embedding key 时，投影留给服务启动时做（它会同时填两个槽位）。"""

    key_file = _write_key_file(tmp_path / "secrets")
    managed = _write_managed_secrets(
        tmp_path / "managed" / "secrets.json", _MANAGED_KEY
    )

    result = _run_entrypoint(tmp_path, key_file=key_file, managed_secrets=managed)

    assert result.returncode == 0, result.stderr
    assert _receipt_slot(result.stdout, _CANDIDATE_SLOT) == "空"
    assert "受管凭据" in result.stdout
    assert _MANAGED_KEY not in result.stdout and _FILE_KEY not in result.stdout


def test_absent_key_file_degrades_without_failing(tmp_path: Path) -> None:
    """没文件、没环境变量、没受管凭据 ⇒ 如实诊断、降级，不许 fail-closed。"""

    result = _run_entrypoint(tmp_path, key_file=None, managed_secrets=None)

    assert result.returncode == 0, result.stderr
    assert _receipt_slot(result.stdout, _CANDIDATE_SLOT) == "空"
    assert "没有可用的嵌入凭据" in result.stdout


def test_receipt_reports_the_v1_file_tier_without_printing_it(tmp_path: Path) -> None:
    """收据要能一眼看出"文件这一档在不在"，但只报名字与是否已设置。"""

    key_file = _write_key_file(tmp_path / "secrets")
    result = _run_entrypoint(tmp_path, key_file=key_file, managed_secrets=None)

    assert re.search(r"key 文件\s+\S*\.sglang_api_key=已设置", result.stdout), (
        result.stdout
    )
    assert _FILE_KEY not in result.stdout and _FILE_KEY not in result.stderr
