"""R3 — admission: white list, shape, hash identity, advisory lock, dry-run, gate dispatch.

Every case here uses a stub gate whose trigger is recorded, so the assertions are about *admission*
(the rules that run before any process exists) and about the fact that the only way out of admission
is the shared gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.data_agents.canonical_v2.jobs import (
    JobAlreadyRunningError,
    JobLock,
    JobParameterError,
    JobRunStore,
    JobRuntime,
    JobTask,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.uploads import (
    STATUS_REJECTED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    UPLOAD_DOMAINS,
    UploadDomainError,
    UploadDuplicateError,
    UploadFileTypeError,
    UploadInProgressError,
    UploadRequiresPostgresError,
    UploadRuntime,
    UploadStore,
    UploadTooLargeError,
    max_upload_bytes,
)


class _RecordingSpawn:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, *, cwd, env, timeout):  # noqa: ANN001 - mirrors _spawn_subprocess
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": dict(env), "timeout": timeout})

        class _Completed:
            returncode = 0
            stdout = '{"job_summary": {"items_processed": 1, "items_failed": 0}}'
            stderr = ""

        return _Completed()


def _upload_task(task_id: str, domain: str, resolver) -> JobTask:  # noqa: ANN001
    return JobTask(
        task_id=task_id,
        label=f"{domain} import",
        description="stub",
        group="import",
        operator_hint="桩上传任务，只出现在测试里。",
        domain=domain,
        argv_template=("python3", "-c", "print('stub')", "{upload_id}"),
        cwd_relative=".",
        timeout_seconds=30,
        collection_gated=True,
        quota="web_search",
        token_params={"upload_id": resolver},
    )


def _resolver(store: UploadStore):
    """The production resolver returns the record's id; an unknown token is a parameter error."""

    def resolve(token: str) -> str:
        record = store.get(token)
        if record is None:
            raise JobParameterError(f"unknown upload id: {token}")
        return record.upload_id

    return resolve


class _StubProbe:
    """A probe with a fixed answer: admission must not need a real database."""

    def __init__(self, available: bool) -> None:
        self._available = available

    def available(self) -> bool:
        return self._available

    def resolved_dsn(self) -> tuple[str | None, str | None]:
        return None, None

    def describe(self) -> dict[str, Any]:
        return {"available": self._available, "source": None, "checked_at": None}


@pytest.fixture()
def runtime(tmp_path: Path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    settings_path = scratch / "settings.json"
    settings_path.write_text('{"schema_version": 1}', encoding="utf-8")
    store = UploadStore(scratch / "uploads.sqlite3")
    spawn = _RecordingSpawn()
    tasks = [
        _upload_task(f"upload-{domain}-import", domain, _resolver(store)) for domain in UPLOAD_DOMAINS
    ]
    gate = JobRuntime(
        store=JobRunStore(scratch / "jobs.sqlite3"),
        settings_store=ManagedSettingsStore(path=settings_path, environ={}),
        tasks=tasks,
        lock_dir=scratch / "locks",
        repo_root=tmp_path,
        environ={"DATABASE_URL": "postgresql://probe/available"},
        spawn=spawn,
        postgres_probe=_StubProbe(True),
    )
    environ = {"MIROTHINKER_ADMIN_UPLOAD_DIR": str(scratch / "stage")}
    uploads = UploadRuntime(
        store=store,
        gate=gate,
        repo_root=tmp_path,
        environ=environ,
        preflight=None,
        batch_reader=None,
    )
    yield uploads, store, spawn, gate
    gate.close()
    store.close()


def _register(runtime: UploadRuntime, content: bytes = b"PK\x03\x04fake-workbook", **kwargs):
    payload = {
        "domain": "company",
        "filename": "sample.xlsx",
        "content": content,
        "operator": "tester",
    }
    payload.update(kwargs)
    return runtime.register(**payload)


def test_unknown_domain_is_refused_before_anything_is_staged(runtime) -> None:
    uploads, store, spawn, _ = runtime
    with pytest.raises(UploadDomainError):
        _register(uploads, domain="paper")
    assert store.total() == 0
    assert spawn.calls == []


@pytest.mark.parametrize("filename", ["sample.csv", "sample.xls", "sample", "sample.xlsx.txt"])
def test_non_workbook_payload_is_refused(runtime, filename: str) -> None:
    uploads, store, spawn, _ = runtime
    with pytest.raises(UploadFileTypeError):
        _register(uploads, filename=filename)
    assert store.total() == 0
    assert spawn.calls == []


def test_empty_payload_is_refused(runtime) -> None:
    uploads, _, _, _ = runtime
    with pytest.raises(UploadFileTypeError):
        _register(uploads, content=b"")


def test_oversized_payload_is_refused_without_staging(runtime) -> None:
    uploads, store, _, _ = runtime
    uploads._environ["MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES"] = "16"  # noqa: SLF001 - sized for the test
    with pytest.raises(UploadTooLargeError):
        _register(uploads, content=b"x" * 64)
    assert store.total() == 0
    assert not (uploads.upload_root).exists()
    assert max_upload_bytes({"MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES": "16"}) == 16


def test_admission_stages_the_file_and_dispatches_through_the_gate(runtime) -> None:
    uploads, store, spawn, gate = runtime
    result = _register(uploads)
    assert result.outcome == "running"
    assert result.record.status == STATUS_RUNNING
    assert result.record.run_id
    staged = Path(result.record.staged_path)
    assert staged.is_file()
    assert staged.read_bytes() == b"PK\x03\x04fake-workbook"
    assert uploads.upload_root in staged.parents
    assert len(spawn.calls) == 1
    assert result.record.upload_id in spawn.calls[0]["argv"]
    run = gate.run_detail(result.record.run_id)
    assert run is not None
    assert run["operator"] == "tester"
    assert run["task_id"] == "upload-company-import"


def test_same_content_is_deduplicated_and_names_the_first_upload(runtime) -> None:
    uploads, store, spawn, _ = runtime
    first = _register(uploads)
    with pytest.raises(UploadDuplicateError) as excinfo:
        _register(uploads)
    assert excinfo.value.record is not None
    assert excinfo.value.record.upload_id == first.record.upload_id
    assert store.total() == 1
    assert len(spawn.calls) == 1


def test_same_content_for_another_domain_is_a_distinct_upload(runtime) -> None:
    uploads, store, _, _ = runtime
    _register(uploads, domain="company")
    _register(uploads, domain="patent")
    assert store.total() == 2


def test_a_failed_upload_does_not_poison_the_hash(runtime) -> None:
    uploads, store, spawn, _ = runtime
    first = _register(uploads)
    store.set_status(first.record.upload_id, status="failed", summary={"error": "boom"})
    again = _register(uploads)
    assert again.record.upload_id != first.record.upload_id
    assert len(spawn.calls) == 2


def test_a_held_advisory_lock_excludes_a_second_admission(runtime) -> None:
    uploads, store, spawn, gate = runtime
    digest = __import__("hashlib").sha256(b"PK\x03\x04fake-workbook").hexdigest()
    lock_dir = Path(gate.store.database_path).parent / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with JobLock.try_acquire(lock_dir / f"upload-company-{digest[:16]}.lock"):
        with pytest.raises(UploadInProgressError):
            _register(uploads)
    assert store.total() == 0
    assert spawn.calls == []


def test_committing_without_postgres_is_refused_but_dry_run_is_allowed(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    settings_path = scratch / "settings.json"
    settings_path.write_text('{"schema_version": 1}', encoding="utf-8")
    store = UploadStore(scratch / "uploads.sqlite3")
    spawn = _RecordingSpawn()
    gate = JobRuntime(
        store=JobRunStore(scratch / "jobs.sqlite3"),
        settings_store=ManagedSettingsStore(path=settings_path, environ={}),
        tasks=[_upload_task("upload-company-import", "company", _resolver(store))],
        lock_dir=scratch / "locks",
        repo_root=tmp_path,
        environ={},
        spawn=spawn,
        postgres_probe=_StubProbe(False),
    )
    uploads = UploadRuntime(
        store=store,
        gate=gate,
        repo_root=tmp_path,
        environ={"MIROTHINKER_ADMIN_UPLOAD_DIR": str(scratch / "stage")},
    )
    with pytest.raises(UploadRequiresPostgresError):
        _register(uploads)
    dry = _register(uploads, dry_run=True, content=b"PK\x03\x04dry")
    assert dry.record.dry_run is True
    gate.close()
    store.close()


def test_a_dry_run_is_refused_for_a_domain_without_a_dry_run_parser(runtime) -> None:
    uploads, _, _, _ = runtime
    with pytest.raises(UploadFileTypeError):
        _register(uploads, domain="professor", dry_run=True)


def test_gate_suppression_is_recorded_on_the_upload(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    settings_path = scratch / "settings.json"
    settings_path.write_text(
        '{"schema_version": 1, "collection": {"enabled": {"company": false}}}', encoding="utf-8"
    )
    store = UploadStore(scratch / "uploads.sqlite3")
    spawn = _RecordingSpawn()
    gate = JobRuntime(
        store=JobRunStore(scratch / "jobs.sqlite3"),
        settings_store=ManagedSettingsStore(path=settings_path, environ={}),
        tasks=[_upload_task("upload-company-import", "company", _resolver(store))],
        lock_dir=scratch / "locks",
        repo_root=tmp_path,
        environ={"DATABASE_URL": "postgresql://probe/available"},
        spawn=spawn,
        postgres_probe=_StubProbe(True),
    )
    uploads = UploadRuntime(
        store=store,
        gate=gate,
        repo_root=tmp_path,
        environ={"MIROTHINKER_ADMIN_UPLOAD_DIR": str(scratch / "stage")},
    )
    result = _register(uploads)
    assert result.outcome == "skipped"
    assert result.skip_reason == "switch_off"
    assert result.record.status == STATUS_SKIPPED
    assert spawn.calls == []
    gate.close()
    store.close()


def test_gate_refusal_is_recorded_on_the_upload(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    settings_path = scratch / "settings.json"
    settings_path.write_text('{"schema_version": 1}', encoding="utf-8")
    store = UploadStore(scratch / "uploads.sqlite3")
    gate = JobRuntime(
        store=JobRunStore(scratch / "jobs.sqlite3"),
        settings_store=ManagedSettingsStore(path=settings_path, environ={}),
        tasks=[_upload_task("upload-company-import", "company", _resolver(store))],
        lock_dir=scratch / "locks",
        repo_root=tmp_path,
        environ={"DATABASE_URL": "postgresql://probe/available"},
        spawn=_RecordingSpawn(),
        postgres_probe=_StubProbe(True),
    )
    gate.trigger = _raise_already_running  # type: ignore[assignment]
    uploads = UploadRuntime(
        store=store,
        gate=gate,
        repo_root=tmp_path,
        environ={"MIROTHINKER_ADMIN_UPLOAD_DIR": str(scratch / "stage")},
    )
    with pytest.raises(UploadInProgressError):
        _register(uploads)
    record = store.list()[0]
    assert record.status == STATUS_REJECTED
    assert record.summary == {"code": "job_already_running"}
    gate.close()
    store.close()


def _raise_already_running(*args: Any, **kwargs: Any):
    raise JobAlreadyRunningError("already running", active_run_id="run-x")


def test_detail_reports_the_run_and_tolerates_a_missing_batch(runtime) -> None:
    uploads, _, _, _ = runtime
    result = _register(uploads)
    detail = uploads.detail(result.record.upload_id)
    assert detail["upload"]["upload_id"] == result.record.upload_id
    assert detail["run"]["run_id"] == result.record.run_id
    assert detail["batch"] is None


def test_resolve_token_requires_a_staged_file(runtime) -> None:
    uploads, store, _, _ = runtime
    result = _register(uploads)
    Path(result.record.staged_path).unlink()
    with pytest.raises(Exception):
        uploads.resolve_token(result.record.upload_id)


def test_quota_limits_reach_the_child_environment(runtime) -> None:
    uploads, _, spawn, _ = runtime
    _register(uploads)
    env = spawn.calls[0]["env"]
    assert env["MIROTHINKER_MAX_WEB_SEARCHES_PER_RUN"] == "200"
    assert env["MIROTHINKER_JOB_TASK_ID"] == "upload-company-import"
    assert "DB_PASSWORD" not in env
