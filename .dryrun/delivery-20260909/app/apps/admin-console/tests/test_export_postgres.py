from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api.export import _extract_field, _load_export_objects, export_domain
from tests.test_domains_postgres import _FakePostgresConn


def test_export_loads_all_objects_from_postgres() -> None:
    conn = _FakePostgresConn()

    objects = _load_export_objects(conn, "professor")

    assert len(objects) == 1
    assert objects[0]["id"] == "PROF-TEST"
    assert objects[0]["object_type"] == "professor"
    assert objects[0]["core_facts"]["institution"] == "Test University"
    assert any("FROM professor p" in call[0] for call in conn.calls)


def test_export_loads_selected_ids_from_postgres() -> None:
    conn = _FakePostgresConn()

    objects = _load_export_objects(conn, "company", ids="COMP-TEST,MISSING")

    assert [obj["id"] for obj in objects] == ["COMP-TEST"]


def test_export_field_extraction_keeps_released_object_shape() -> None:
    conn = _FakePostgresConn()
    obj = _load_export_objects(conn, "paper", ids="PAPER-TEST")[0]

    assert _extract_field(obj, "display_name") == "Notes on the Analytical Engine"
    assert _extract_field(obj, "year") == "2026"
    assert _extract_field(obj, "summary_zh") == "A test paper."


def test_export_rejects_unknown_domain() -> None:
    conn = _FakePostgresConn()

    with pytest.raises(HTTPException) as exc:
        export_domain("invalid", conn=conn)

    assert exc.value.status_code == 422
