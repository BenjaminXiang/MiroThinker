from __future__ import annotations

from fastapi import HTTPException
import pytest

from backend.api.batch import (
    BatchDeleteRequest,
    BatchQualityRequest,
    batch_delete,
    batch_update_quality,
)
from backend.api.domains import DomainEnum, get_domain_object
from tests.test_domains_postgres import _FakePostgresConn


def test_batch_quality_updates_existing_postgres_object() -> None:
    conn = _FakePostgresConn()

    response = batch_update_quality(
        BatchQualityRequest(ids=["PROF-TEST"], quality_status="needs_review"),
        conn=conn,
    )

    assert response.updated == 1
    assert conn.run_scopes[-1]["action"] == "batch_quality"
    assert conn.run_scopes[-1]["domain"] == "professor"
    assert conn.records["professor"]["identity_status"] == "needs_review"


def test_batch_quality_ignores_missing_ids() -> None:
    conn = _FakePostgresConn()

    response = batch_update_quality(
        BatchQualityRequest(ids=["MISSING-ID"], quality_status="needs_review"),
        conn=conn,
    )

    assert response.updated == 0
    assert conn.run_scopes == []


def test_batch_delete_soft_deletes_postgres_object() -> None:
    conn = _FakePostgresConn()

    response = batch_delete(BatchDeleteRequest(ids=["PROF-TEST"]), conn=conn)

    assert response.deleted == 1
    assert conn.run_scopes[-1]["action"] == "batch_delete"
    assert conn.run_scopes[-1]["domain"] == "professor"
    with pytest.raises(HTTPException) as exc:
        get_domain_object(DomainEnum.professor, "PROF-TEST", conn=conn)
    assert exc.value.status_code == 404


def test_batch_delete_ignores_missing_ids() -> None:
    conn = _FakePostgresConn()

    response = batch_delete(BatchDeleteRequest(ids=["MISSING-ID"]), conn=conn)

    assert response.deleted == 0
    assert conn.run_scopes == []
