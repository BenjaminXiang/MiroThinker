# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from pathlib import Path
import subprocess


def _script_text(relative_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "scripts" / relative_path).read_text(encoding="utf-8")


def test_full_e2e_scripts_source_shared_env_loader():
    for script_name in ("run_full_e2e_parallel.sh", "run_full_e2e_all_schools.sh"):
        script_text = _script_text(script_name)

        assert "load_professor_e2e_env.sh" in script_text
        assert "source " in script_text or ". " in script_text


def test_full_e2e_scripts_do_not_hardcode_professor_api_keys():
    for script_name in ("run_full_e2e_parallel.sh", "run_full_e2e_all_schools.sh"):
        script_text = _script_text(script_name)

        assert "export API_KEY='" not in script_text
        assert 'export API_KEY="' not in script_text
        assert "export DASHSCOPE_API_KEY='" not in script_text
        assert 'export DASHSCOPE_API_KEY="' not in script_text
        assert "export SERPER_API_KEY='" not in script_text
        assert 'export SERPER_API_KEY="' not in script_text


def test_professor_e2e_env_loader_can_be_sourced_from_zsh():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "load_professor_e2e_env.sh"
    env = os.environ.copy()
    env["API_KEY"] = "test-api-key"

    result = subprocess.run(
        ["zsh", "-lc", f"source '{script_path}'"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_professor_e2e_env_loader_reads_repo_key_file_from_zsh():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "load_professor_e2e_env.sh"
    env = os.environ.copy()
    env.pop("API_KEY", None)

    result = subprocess.run(
        ["zsh", "-lc", f"source '{script_path}' && print -r -- \"$API_KEY\""],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "k8#pL2@mN9!qjfkew87@#$0204"
