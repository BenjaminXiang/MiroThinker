"""R1 — the declared W3 tasks stay closed: fixed argv, closed sets, server-resolved tokens.

Locks: every upload/seed task the W3 surface can reach exists in the shared table with a fixed argv
whose script is present in the repo; an out-of-set value, an undeclared parameter, a malformed token
and an unknown token are each refused before any argv exists; a token never carries path text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_agents.canonical_v2.jobs import (
    JOB_TASKS_BY_ID,
    JobParameterError,
    JobsConfigurationError,
    JobTask,
)
from src.data_agents.canonical_v2.uploads import (
    UPLOAD_DOMAINS,
    UPLOAD_TASK_BY_DOMAIN,
    resolve_upload_token,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
W3_TASK_IDS = (
    "upload-company-import",
    "upload-patent-import",
    "upload-professor-import",
    "admin-seed-refresh",
    "admin-seed-refresh-sample",
)


@pytest.mark.parametrize("task_id", W3_TASK_IDS)
def test_declared_task_exists_with_fixed_argv_and_existing_script(task_id: str) -> None:
    task = JOB_TASKS_BY_ID[task_id]
    assert task.script_relative is not None, "a declared task must point at a script"
    script = (REPO_ROOT / task.cwd_relative / task.script_relative).resolve()
    assert script.is_file(), f"{task_id} declares a script that does not exist: {script}"
    assert task.argv_template[0] == "uv"
    assert task.collection_gated is True
    assert task.timeout_seconds > 0


def test_upload_tasks_cover_exactly_the_white_listed_domains() -> None:
    assert set(UPLOAD_TASK_BY_DOMAIN) == set(UPLOAD_DOMAINS)
    for domain, task_id in UPLOAD_TASK_BY_DOMAIN.items():
        task = JOB_TASKS_BY_ID[task_id]
        assert task.domain == domain
        assert set(task.token_params) == {"upload_id"}
        assert task.params == {}, "an upload task takes no caller-spelled value"


def test_upload_id_token_is_the_only_caller_value_and_must_be_registered() -> None:
    task = JOB_TASKS_BY_ID["upload-company-import"]
    with pytest.raises(JobParameterError):
        task.argv_for({"upload_id": "8f14e45f-ceea-467a-9d0b-1b1c1c1c1c1c/../../etc/passwd"})
    with pytest.raises(JobParameterError):
        task.argv_for({"upload_id": "no-such-upload-id"})
    with pytest.raises(JobParameterError):
        task.argv_for({"upload_id": "ok" * 40})
    with pytest.raises(JobParameterError):
        task.argv_for({"upload_id": "a" * 65})
    with pytest.raises(JobParameterError):
        task.argv_for({"upload_id": "8f14e45f", "domain": "paper"})


def test_seed_task_keeps_mode_and_limit_closed() -> None:
    refresh = JOB_TASKS_BY_ID["admin-seed-refresh"]
    assert refresh.params == {"mode": ("preview", "full")}
    assert dict(refresh.token_params) == {"seed_id": refresh.token_params["seed_id"]}
    argv = refresh.argv_for({"seed_id": "42", "mode": "preview"})
    assert argv == (
        "uv",
        "run",
        "python",
        "scripts/run_admin_seed_refresh.py",
        "--seed-id",
        "42",
        "--trigger-mode",
        "preview",
    )
    with pytest.raises(JobParameterError):
        refresh.argv_for({"seed_id": "42", "mode": "sample"})
    with pytest.raises(JobParameterError):
        refresh.argv_for({"seed_id": "42; rm -rf /", "mode": "preview"})
    with pytest.raises(JobParameterError):
        refresh.argv_for({"seed_id": "0", "mode": "preview"})
    with pytest.raises(JobParameterError):
        refresh.argv_for({"seed_id": "42", "mode": "preview", "limit": "5"})

    sample = JOB_TASKS_BY_ID["admin-seed-refresh-sample"]
    assert sample.params == {"limit": ("5", "20", "50", "100")}
    assert sample.argv_for({"seed_id": "7", "limit": "20"})[-2:] == ("--limit", "20")
    with pytest.raises(JobParameterError):
        sample.argv_for({"seed_id": "7", "limit": "1000"})


def test_token_shape_rejects_shell_and_path_text() -> None:
    task = JOB_TASKS_BY_ID["admin-seed-refresh"]
    for token in ("42 43", "42;ls", "-42", "42/43", "42\n43", "", "4" * 65):
        with pytest.raises(JobParameterError):
            task.argv_for({"seed_id": token, "mode": "preview"})


def test_a_parameter_declared_twice_is_a_configuration_error() -> None:
    task = JobTask(
        task_id="bad-task",
        label="bad",
        description="bad",
        group="ops",
        operator_hint="桩任务，只出现在测试里。",
        domain="company",
        argv_template=("echo", "{value}"),
        cwd_relative=".",
        timeout_seconds=5,
        params={"value": ("a",)},
        token_params={"value": lambda token: token},
    )
    with pytest.raises(JobsConfigurationError):
        task.argv_for({"value": "a"})


def test_resolving_a_token_without_a_ledger_entry_is_refused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CANONICAL_V2_UPLOADS_DB", str(tmp_path / "uploads.sqlite3"))
    with pytest.raises(JobParameterError):
        resolve_upload_token("not-registered")
