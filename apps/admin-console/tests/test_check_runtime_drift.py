"""Drift checker: the deployed customer tree must equal a git ref."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_runtime_drift.py"
_spec = importlib.util.spec_from_file_location("check_runtime_drift", _SCRIPT)
assert _spec and _spec.loader
drift = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = drift  # dataclasses resolves the module by name
_spec.loader.exec_module(drift)


def test_ignored_paths_cover_build_and_patch_residue() -> None:
    assert drift.is_ignored("apps/x/__pycache__/a.pyc")
    assert drift.is_ignored("apps/x/frontend/dist/index.html")
    assert drift.is_ignored("apps/x/backend/main.py.bak-answer-cache-20261025")
    assert drift.is_ignored("apps/x/serving_pack_loader.py.pre-aliasfoothold-20261015")
    assert drift.is_ignored(
        "apps/admin-console/.agents/runs/embedding-switch/report.json"
    )
    assert not drift.is_ignored("apps/x/backend/main.py")


def test_runtime_artifacts_are_reported_not_failed() -> None:
    assert drift.is_runtime_artifact("apps/miroflow-agent/.env")
    assert drift.is_runtime_artifact("apps/miroflow-agent/milvus.db")
    assert drift.is_runtime_artifact("apps/miroflow-agent/report.html")
    assert drift.is_ignored("apps/miroflow-agent/.env")  # never source drift
    assert not drift.is_runtime_artifact("apps/miroflow-agent/src/main.py")


def test_compare_reports_changed_missing_and_untracked() -> None:
    result = drift.compare(
        {"apps/a.py": "1", "apps/b.py": "2", "apps/c.py": "3"},
        {"apps/a.py": "1", "apps/b.py": "9", "apps/d.py": "4"},
    )
    assert result.changed == [("apps/b.py", "2", "9")]
    assert result.missing == ["apps/c.py"]
    assert result.untracked == ["apps/d.py"]
    assert result.total == 3
    assert "CHANGED  apps/b.py" in drift.format_report(result)


def test_compare_clean_tree_is_silent() -> None:
    result = drift.compare({"apps/a.py": "1"}, {"apps/a.py": "1"})
    assert result.total == 0
    assert "no drift" in drift.format_report(result)


def test_scan_local_skips_residue(tmp_path: Path) -> None:
    (tmp_path / "apps" / "svc").mkdir(parents=True)
    (tmp_path / "apps" / "svc" / "main.py").write_text("print('x')\n")
    (tmp_path / "apps" / "svc" / "main.py.bak-20261026").write_text("old\n")
    (tmp_path / "apps" / "svc" / ".env").write_text("SECRET=1\n")
    (tmp_path / "apps" / "svc" / "__pycache__").mkdir()
    (tmp_path / "apps" / "svc" / "__pycache__" / "main.cpython-312.pyc").write_bytes(
        b"x"
    )

    runtime: list[str] = []
    tree = drift.scan_local(tmp_path, runtime=runtime)

    assert list(tree) == ["apps/svc/main.py"]
    assert runtime == ["apps/svc/.env"]


def test_scan_git_reads_the_reference_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "apps" / "svc").mkdir(parents=True)
    (repo / "apps" / "svc" / "main.py").write_text("print('x')\n")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
        env={**env, "PATH": "/usr/bin:/bin"},
    )

    tree = drift.scan_git(repo, "HEAD")

    assert tree == drift.scan_local(repo)


def test_scan_local_rejects_missing_tree(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        drift.scan_local(tmp_path)
