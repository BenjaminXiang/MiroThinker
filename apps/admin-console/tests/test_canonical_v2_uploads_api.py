"""R4 — HTTP surface for the upload front door, plus page parity (R7).

Locks: admit (202 + upload id + run id), duplicate (409 naming the first upload), the refusal codes
(422 domain / 400 shape / 413 size), the 503 degradation when Postgres is unreachable, the ledger
list/detail payloads, the two new pages, and the shared navigation on every console page.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.main import _create_canonical_v2_route_shell
from src.data_agents.canonical_v2.jobs import JobRunStore, JobRuntime, JobTask
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.uploads import (
    UPLOAD_DOMAINS,
    UploadRuntime,
    UploadStore,
)


_PREFIX = "/api/canonical-v2/admin/uploads"
_PAGES = ("/browse", "/logs", "/admin", "/jobs", "/upload", "/seeds")
_NAV_TARGETS = ("chat", "browse", "logs", "admin", "jobs", "upload", "seeds")
WORKBOOK = b"PK\x03\x04synthetic-workbook-bytes"


class _StubProbe:
    def __init__(self, available: bool) -> None:
        self._available = available

    def available(self) -> bool:
        return self._available

    def describe(self) -> dict[str, Any]:
        return {"available": self._available, "source": None, "checked_at": None}


class _RecordingSpawn:
    def __call__(self, argv, *, cwd, env, timeout):  # noqa: ANN001
        class _Completed:
            returncode = 0
            stdout = '{"job_summary": {"items_processed": 1}}'
            stderr = ""

        return _Completed()


def _settings(path: Path) -> ManagedSettingsStore:
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    return ManagedSettingsStore(path=path, environ={})


def _resolver(store: UploadStore):
    def resolve(token: str) -> str:
        record = store.get(token)
        if record is None:
            raise ValueError(f"unknown upload id: {token}")
        return record.upload_id

    return resolve


def _client(tmp_path: Path, *, postgres: bool) -> tuple[TestClient, UploadRuntime, UploadStore]:
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    store = UploadStore(scratch / "uploads.sqlite3")
    tasks = [
        JobTask(
            task_id=f"upload-{domain}-import",
            label="stub",
            description="stub",
            domain=domain,
            argv_template=("python3", "-c", "print('stub')", "{upload_id}"),
            cwd_relative=".",
            timeout_seconds=15,
            collection_gated=True,
            quota="web_search",
            token_params={"upload_id": _resolver(store)},
        )
        for domain in UPLOAD_DOMAINS
    ]
    gate = JobRuntime(
        store=JobRunStore(scratch / "jobs.sqlite3"),
        settings_store=_settings(scratch / "settings.json"),
        tasks=tasks,
        lock_dir=scratch / "locks",
        repo_root=tmp_path,
        environ={"MIROTHINKER_ADMIN_UPLOAD_DIR": str(scratch / "stage")},
        spawn=_RecordingSpawn(),
        postgres_probe=_StubProbe(postgres),
    )
    runtime = UploadRuntime(
        store=store,
        gate=gate,
        repo_root=tmp_path,
        environ={"MIROTHINKER_ADMIN_UPLOAD_DIR": str(scratch / "stage")},
    )
    app = _create_canonical_v2_route_shell()
    app.state.canonical_v2_uploads_runtime = runtime
    # The seed surface shares the jobs database; give it one so the nav/segments stay consistent.
    app.state.canonical_v2_seed_gate = gate
    return TestClient(app), runtime, store


@pytest.fixture()
def client(tmp_path: Path):
    client, runtime, store = _client(tmp_path, postgres=True)
    yield client, runtime, store
    runtime.gate.close()
    store.close()


def _post(client: TestClient, domain: str, content: bytes = WORKBOOK, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{_PREFIX}/{domain}" + (f"?{query}" if query else "")
    return client.post(
        url,
        files={"file": ("sample.xlsx", io.BytesIO(content), "application/vnd.ms-excel")},
    )


def test_admit_returns_upload_and_run_identifiers(client) -> None:
    http, _, _ = client
    response = _post(http, "company")
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["outcome"] == "running"
    assert payload["upload"]["domain"] == "company"
    assert payload["upload"]["status"] == "running"
    assert payload["upload"]["content_sha256"]
    assert payload["upload"]["run_id"]


def test_duplicate_upload_is_refused_and_names_the_first(client) -> None:
    http, _, store = client
    first = _post(http, "company").json()
    response = _post(http, "company")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "duplicate_upload"
    assert detail["upload_id"] == first["upload"]["upload_id"]
    assert store.total() == 1


@pytest.mark.parametrize(
    "domain,expected",
    [("paper", 422), ("company", 400)],
)
def test_domain_white_list_and_file_shape(client, domain: str, expected: int) -> None:
    http, _, _ = client
    if domain == "paper":
        response = _post(http, domain)
    else:
        response = http.post(
            f"{_PREFIX}/{domain}",
            files={"file": ("sample.csv", io.BytesIO(WORKBOOK), "text/csv")},
        )
    assert response.status_code == expected


def test_oversized_upload_is_refused(client, monkeypatch) -> None:
    http, _, _ = client
    monkeypatch.setenv("MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES", "16")
    response = _post(http, "patent")
    assert response.status_code == 413
    assert response.json()["detail"] == "upload_too_large"


def test_list_and_detail_payloads(client) -> None:
    http, _, _ = client
    first = _post(http, "company").json()
    listed = http.get(_PREFIX)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert [item["upload_id"] for item in body["uploads"]] == [first["upload"]["upload_id"]]
    assert {item["domain"] for item in body["domains"]} == set(UPLOAD_DOMAINS)
    assert body["postgres"]["available"] is True

    detail = http.get(f"{_PREFIX}/{first['upload']['upload_id']}")
    assert detail.status_code == 200
    assert detail.json()["run"]["run_id"] == first["upload"]["run_id"]

    assert http.get(f"{_PREFIX}/does-not-exist").status_code == 404
    assert http.get(_PREFIX, params={"domain": "paper"}).status_code == 422


def test_unknown_domain_filter_is_refused(client) -> None:
    http, _, _ = client
    assert http.get(_PREFIX, params={"domain": "paper"}).status_code == 422


def test_degradation_without_postgres(tmp_path: Path) -> None:
    http, _, store = _client(tmp_path, postgres=False)
    try:
        response = _post(http, "company")
        assert response.status_code == 503
        assert response.json()["detail"] == "upload_requires_postgres"
        assert store.total() == 0
        assert http.get(_PREFIX).status_code == 200
        assert http.get("/api/health").status_code == 200
        dry_run = _post(http, "company", dry_run="true")
        assert dry_run.status_code == 202
        assert dry_run.json()["upload"]["dry_run"] is True
    finally:
        pass


def test_every_console_page_carries_the_shared_navigation(client) -> None:
    http, _, _ = client
    for page in _PAGES:
        response = http.get(page)
        assert response.status_code == 200, page
        body = response.text
        for target in _NAV_TARGETS:
            assert f'href="{target}"' in body, f"{page} is missing a link to {target}"


def test_new_pages_state_what_they_cannot_offer_without_postgres(tmp_path: Path) -> None:
    http, _, _ = _client(tmp_path, postgres=False)
    upload_page = http.get("/upload")
    assert upload_page.status_code == 200
    assert 'id="degrated"' in upload_page.text
    seeds_page = http.get("/seeds")
    assert seeds_page.status_code == 200
    assert 'id="degraded"' in seeds_page.text
