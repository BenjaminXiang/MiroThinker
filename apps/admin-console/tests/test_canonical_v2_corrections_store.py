from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from backend.services.canonical_v2_corrections import (
    SCHEMA_VERSION,
    CorrectionsStore,
    CorrectionsStoreError,
    FieldCorrectionRecord,
)

_BASE = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)


def _correction(
    *,
    domain: str = "company",
    canonical_object_id: str = "company-c-0026fc609d33f978c54872ce",
    field_path: str = "name",
    old_value: object = "旧名称",
    new_value: object = "新名称",
    reason: str = "名称登记变更",
    operator: str = "admin",
    minutes: int = 0,
) -> FieldCorrectionRecord:
    return FieldCorrectionRecord(
        domain=domain,
        canonical_object_id=canonical_object_id,
        field_path=field_path,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        operator=operator,
        created_at=_BASE + timedelta(minutes=minutes),
    )


def test_store_records_and_reads_back_one_correction(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    correction_id = store.record_correction(_correction())

    details = store.list_corrections()

    assert len(details) == 1
    detail = details[0]
    assert detail.correction_id == correction_id
    assert detail.domain == "company"
    assert detail.field_path == "name"
    assert detail.old_value == "旧名称"
    assert detail.new_value == "新名称"
    assert detail.reason == "名称登记变更"
    assert detail.operator == "admin"
    assert detail.status == "active"
    assert detail.created_at.startswith("2026-08-09T10:00:00")


def test_store_active_corrections_keeps_latest_per_field_path(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    store.record_correction(_correction(new_value="第一次", minutes=0))
    store.record_correction(_correction(new_value="第二次", minutes=1))
    store.record_correction(_correction(field_path="address", new_value="南山区", minutes=2))

    active = store.active_corrections(
        domain="company", canonical_object_id="company-c-0026fc609d33f978c54872ce"
    )

    by_path = {detail.field_path: detail.new_value for detail in active}
    assert by_path == {"name": "第二次", "address": "南山区"}


def test_store_revert_is_soft_and_excluded_from_active(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    correction_id = store.record_correction(_correction())

    assert store.revert_correction(correction_id) is True
    assert store.revert_correction(correction_id) is False  # already reverted
    assert store.revert_correction("correction-missing") is False

    assert store.active_corrections(
        domain="company", canonical_object_id="company-c-0026fc609d33f978c54872ce"
    ) == ()
    all_rows = store.list_corrections()
    assert len(all_rows) == 1
    assert all_rows[0].status == "reverted"


def test_store_rejects_empty_reason_and_operator(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    with pytest.raises(CorrectionsStoreError, match="reason"):
        store.record_correction(_correction(reason="  "))
    with pytest.raises(CorrectionsStoreError, match="operator"):
        store.record_correction(_correction(operator=""))
    with pytest.raises(CorrectionsStoreError, match="field_path"):
        store.record_correction(_correction(field_path=" "))
    with pytest.raises(CorrectionsStoreError, match="status"):
        store.list_corrections(status="archived")


def test_store_records_naive_timestamps_rejected(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    naive = FieldCorrectionRecord(
        domain="company",
        canonical_object_id="company-c-1",
        field_path="name",
        old_value=None,
        new_value="x",
        reason="r",
        operator="op",
        created_at=datetime(2026, 8, 9, 10, 0, 0),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        store.record_correction(naive)


def test_store_add_record_generates_manual_id_and_round_trips(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    payload = {"name": "手工录入企业", "industry": "集成电路", "city": "深圳"}

    detail = store.add_record(
        domain="company",
        payload=payload,
        reason="展会新发现的企业",
        operator="admin",
        created_at=_BASE,
    )

    assert detail.record_id.startswith("added-")
    assert detail.manual_object_id.startswith("company-manual-")
    assert detail.status == "active"
    fetched = store.get_added_record(detail.manual_object_id)
    assert fetched is not None
    assert fetched.payload == payload
    assert fetched.reason == "展会新发现的企业"

    listed = store.list_added_records(domain="company", status="active")
    assert [row.record_id for row in listed] == [detail.record_id]
    assert store.list_added_records(domain="paper", status="active") == ()


def test_store_revert_added_record_hides_it(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    detail = store.add_record(
        domain="professor",
        payload={"name": "手工教授"},
        reason="补录",
        operator="admin",
        created_at=_BASE,
    )

    assert store.revert_added_record(detail.record_id) is True
    assert store.revert_added_record(detail.record_id) is False
    assert store.get_added_record(detail.manual_object_id) is None
    reverted = store.list_added_records(status="reverted")
    assert [row.record_id for row in reverted] == [detail.record_id]


def test_store_add_record_validates_payload_and_audit(tmp_path: Path) -> None:
    store = CorrectionsStore(tmp_path / "corrections.sqlite3")
    with pytest.raises(CorrectionsStoreError, match="payload"):
        store.add_record(
            domain="company", payload={}, reason="r", operator="op", created_at=_BASE
        )
    with pytest.raises(CorrectionsStoreError, match="reason"):
        store.add_record(
            domain="company",
            payload={"name": "x"},
            reason=" ",
            operator="op",
            created_at=_BASE,
        )
    with pytest.raises(CorrectionsStoreError, match="status"):
        store.list_added_records(status="archived")


def test_store_file_permissions_and_schema_version(tmp_path: Path) -> None:
    database_path = tmp_path / "corrections.sqlite3"
    store = CorrectionsStore(database_path)
    assert (database_path.stat().st_mode & 0o777) == 0o600
    connection = sqlite3.connect(database_path)
    row = connection.execute(
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
    ).fetchone()
    connection.close()
    assert row[0] == SCHEMA_VERSION

    # reopening the same file keeps working (schema already initialized)
    reopened = CorrectionsStore(database_path)
    reopened.record_correction(_correction())
    assert len(store.list_corrections()) == 1
