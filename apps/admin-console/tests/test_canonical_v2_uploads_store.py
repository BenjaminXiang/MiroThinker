"""R2 — the serving-side upload ledger: identity, ordering, terminal state, hygiene."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_agents.canonical_v2.uploads import (
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    SCHEMA_VERSION,
    UploadStore,
    uploads_database_path,
)


def _store(tmp_path: Path) -> UploadStore:
    return UploadStore(tmp_path / "uploads.sqlite3")


def _create(store: UploadStore, *, upload_id: str, domain: str = "company", digest: str = "a" * 64):
    return store.create(
        upload_id=upload_id,
        domain=domain,
        filename="sample.xlsx",
        content_sha256=digest,
        size_bytes=1024,
        staged_path=f"/tmp/staging/{upload_id}/sample.xlsx",
        dry_run=False,
        operator="tester",
    )


def test_admit_list_and_read_back(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = _create(store, upload_id="u-1")
    assert record.status == STATUS_QUEUED
    assert record.run_id is None
    assert store.get("u-1") == record
    assert store.total() == 1
    assert store.schema_version() == SCHEMA_VERSION
    store.close()


def test_listing_is_newest_first_and_filters_by_domain(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store, upload_id="u-1", domain="company")
    _create(store, upload_id="u-2", domain="patent", digest="b" * 64)
    _create(store, upload_id="u-3", domain="company", digest="c" * 64)
    company = store.list(domain="company")
    assert [record.upload_id for record in company] == ["u-3", "u-1"]
    assert store.total(domain="patent") == 1
    assert len(store.list()) == 3
    store.close()


def test_duplicate_lookup_ignores_failed_attempts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store, upload_id="u-1")
    assert store.find_active(domain="company", content_sha256="a" * 64) is not None
    store.set_status("u-1", status=STATUS_FAILED, summary={"error": "boom"})
    assert store.find_active(domain="company", content_sha256="a" * 64) is None
    assert store.find_active(domain="patent", content_sha256="a" * 64) is None
    store.close()


def test_status_transitions_and_bounded_summary(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store, upload_id="u-1")
    store.set_status("u-1", status=STATUS_RUNNING, run_id="run-1", summary={"task_id": "t"})
    record = store.set_status("u-1", status=STATUS_SUCCEEDED, summary={"rows": 2})
    assert record is not None
    assert record.status == STATUS_SUCCEEDED
    assert record.run_id == "run-1"
    assert record.summary == {"rows": 2}
    store.close()


def test_large_summaries_are_truncated_and_redacted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store, upload_id="u-1")
    record = store.set_status(
        "u-1",
        status=STATUS_SUCCEEDED,
        summary={"stdout": "api_key=sk-live-abcdef123456 " + "x" * 8000},
    )
    assert record is not None
    assert record.summary is not None
    assert record.summary["truncated"] is True
    assert "sk-live-abcdef123456" not in record.summary["excerpt"]
    store.close()


def test_schema_opens_idempotently_and_stores_no_content(tmp_path: Path) -> None:
    path = tmp_path / "uploads.sqlite3"
    UploadStore(path).close()
    store = UploadStore(path)
    _create(store, upload_id="u-1")
    raw = path.read_bytes()
    assert b"PK\x03\x04" not in raw, "the ledger must never carry the workbook itself"
    store.close()


def test_database_path_resolution(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        uploads_database_path({})
    assert uploads_database_path({"CANONICAL_V2_UPLOADS_DB": str(tmp_path / "u.sqlite3")}) == (
        tmp_path / "u.sqlite3"
    )
    assert uploads_database_path(
        {"CANONICAL_V2_ACCESS_LOG_DB": str(tmp_path / "access-logs.sqlite3")}
    ) == (tmp_path / "uploads.sqlite3")
