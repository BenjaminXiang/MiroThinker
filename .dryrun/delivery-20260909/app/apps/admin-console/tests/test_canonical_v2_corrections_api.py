from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterator

from fastapi.testclient import TestClient
import pytest

from backend.canonical_v2_deps import get_canonical_v2_admin_runtime
from backend.main import app
from backend.services.canonical_v2_corrections import CorrectionsStore


_STATE_NAME = "canonical_v2_corrections_store"
_AS_OF = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)

_DETAIL: dict[str, Any] = {
    "release_id": "rel-test-1",
    "canonical_identity_id": "company-c-abc",
    "identity_decision_id": "identity-decision:x",
    "entity_type": "company",
    "quality_status": "partial",
    "name": "旧名称",
    "address": None,
    "profile_summary": "旧简介。",
}


class _FakeRuntime:
    @property
    def as_of(self) -> datetime:
        return _AS_OF

    def detail(self, *, domain: str, canonical_id: str) -> dict[str, Any] | None:
        if domain == "company" and canonical_id == "company-c-abc":
            return dict(_DETAIL)
        return None

    def list_domain(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "release_id": "rel-test-1",
            "domain": "company",
            "as_of": _AS_OF.isoformat(),
            "items": [dict(_DETAIL)],
            "total": 1,
            "limit": 25,
            "offset": 0,
            "sort_keys": [],
            "filter_receipt": None,
            "retrieval_traces": [],
            "limitations": [],
        }

    def export(self, *, domain: str, ids: list[str]) -> tuple[str, ...]:
        return tuple(json.dumps(dict(_DETAIL), ensure_ascii=False) for _ in ids)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[CorrectionsStore]:
    instance = CorrectionsStore(tmp_path / "corrections.sqlite3")
    had_prior = hasattr(app.state, _STATE_NAME)
    prior = getattr(app.state, _STATE_NAME, None)
    setattr(app.state, _STATE_NAME, instance)
    app.dependency_overrides[get_canonical_v2_admin_runtime] = lambda: _FakeRuntime()
    try:
        yield instance
    finally:
        app.dependency_overrides.pop(get_canonical_v2_admin_runtime, None)
        if had_prior:
            setattr(app.state, _STATE_NAME, prior)
        elif hasattr(app.state, _STATE_NAME):
            delattr(app.state, _STATE_NAME)
        instance.close()


@pytest.fixture()
def client(store: CorrectionsStore) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _correct(client: TestClient, **overrides: Any) -> Any:
    body = {"field_path": "name", "new_value": "新名称", "reason": "登记变更"}
    body.update(overrides)
    return client.post(
        "/api/canonical-v2/admin/domains/company/company-c-abc/corrections",
        json=body,
        headers={"X-Remote-User": "admin"},
    )


def test_create_correction_merges_into_detail(client, store) -> None:
    created = _correct(client)
    assert created.status_code == 201, created.text
    correction_id = created.json()["correction_id"]

    detail = client.get("/api/canonical-v2/admin/domains/company/company-c-abc")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["name"] == "新名称"
    assert payload["corrected_fields"] == ["name"]
    (correction,) = payload["corrections"]
    assert correction["correction_id"] == correction_id
    assert correction["old_value"] == "旧名称"
    assert correction["new_value"] == "新名称"
    assert correction["operator"] == "admin"
    assert correction["reason"] == "登记变更"
    # provenance fields untouched
    assert payload["identity_decision_id"] == "identity-decision:x"


def test_correction_field_whitelist_enforced(client) -> None:
    for field_path in ("identity_decision_id", "quality_status", "industry"):
        response = _correct(client, field_path=field_path, new_value="x")
        assert response.status_code == 422, (field_path, response.text)
    assert _correct(client, field_path="a.b", new_value="x").status_code == 422
    assert _correct(client, field_path="missing", new_value="x").status_code == 422
    assert _correct(client, field_path="name", new_value="旧名称").status_code == 422


def test_correction_unknown_object_404(client) -> None:
    response = client.post(
        "/api/canonical-v2/admin/domains/company/company-c-missing/corrections",
        json={"field_path": "name", "new_value": "x", "reason": "r"},
    )
    assert response.status_code == 404


def test_revert_restores_original_value(client) -> None:
    correction_id = _correct(client).json()["correction_id"]

    reverted = client.post(
        f"/api/canonical-v2/admin/corrections/{correction_id}/revert"
    )
    assert reverted.status_code == 200

    detail = client.get("/api/canonical-v2/admin/domains/company/company-c-abc")
    payload = detail.json()
    assert payload["name"] == "旧名称"
    assert "corrections" not in payload  # shape restored byte-identical
    assert (
        client.post("/api/canonical-v2/admin/corrections/correction-none/revert")
        .status_code
        == 404
    )


def test_list_overlay_merges_correction_and_manual_records(client) -> None:
    _correct(client)
    client.post(
        "/api/canonical-v2/admin/domains/company/records",
        json={
            "payload": {"name": "手工企业", "industry_tags": ["机器人"]},
            "reason": "展会发现",
        },
        headers={"X-Remote-User": "admin"},
    )

    listed = client.get("/api/canonical-v2/admin/domains/company")
    payload = listed.json()
    assert payload["total"] == 2
    manual, corrected = payload["items"]
    assert manual["origin"] == "manual"
    assert manual["name"] == "手工企业"
    assert manual["canonical_identity_id"].startswith("company-manual-")
    assert corrected["name"] == "新名称"
    assert corrected["corrected_fields"] == ["name"]

    # manual rows only join the unfiltered first page
    filtered = client.get(
        "/api/canonical-v2/admin/domains/company?q=手工"
    ).json()
    assert all(item.get("origin") != "manual" for item in filtered["items"])
    paged = client.get("/api/canonical-v2/admin/domains/company?offset=1").json()
    assert all(item.get("origin") != "manual" for item in paged["items"])


def test_added_record_detail_revert_and_validation(client) -> None:
    missing_name = client.post(
        "/api/canonical-v2/admin/domains/company/records",
        json={"payload": {"industry_tags": ["x"]}, "reason": "r"},
    )
    assert missing_name.status_code == 422

    created = client.post(
        "/api/canonical-v2/admin/domains/paper/records",
        json={
            "payload": {
                "title": "手工论文",
                "content_sha256": "must-be-stripped",
                "year": 2026,
            },
            "reason": "补录",
        },
        headers={"X-Remote-User": "admin"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    manual_id = body["manual_object_id"]
    assert manual_id.startswith("paper-manual-")
    assert "content_sha256" not in body["detail"]

    detail = client.get(f"/api/canonical-v2/admin/domains/paper/{manual_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "手工论文"
    assert detail.json()["origin"] == "manual"

    reverted = client.post(
        f"/api/canonical-v2/admin/records/{body['record_id']}/revert"
    )
    assert reverted.status_code == 200
    assert (
        client.get(f"/api/canonical-v2/admin/domains/paper/{manual_id}").status_code
        == 404
    )


def test_corrections_list_and_export_endpoints(client) -> None:
    _correct(client)
    client.post(
        "/api/canonical-v2/admin/domains/company/records",
        json={"payload": {"name": "手工企业"}, "reason": "补录"},
    )

    listed = client.get("/api/canonical-v2/admin/corrections?domain=company")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["field_path"] == "name"

    exported = client.get("/api/canonical-v2/admin/corrections/export")
    assert exported.status_code == 200
    lines = [json.loads(line) for line in exported.text.strip().split("\n")]
    kinds = sorted(line["kind"] for line in lines)
    assert kinds == ["added_record", "field_correction"]
    correction_line = next(
        line for line in lines if line["kind"] == "field_correction"
    )
    assert correction_line["field_path"] == "name"
    assert correction_line["new_value"] == "新名称"


def test_domain_export_lines_carry_corrected_values(client) -> None:
    _correct(client, field_path="profile_summary", new_value="新简介。")

    exported = client.get(
        "/api/canonical-v2/admin/domains/company/export"
        "?format=jsonl&id=company-c-abc"
    )
    assert exported.status_code == 200
    (line,) = exported.text.strip().split("\n")
    payload = json.loads(line)
    assert payload["profile_summary"] == "新简介。"
    assert payload["corrected_fields"] == ["profile_summary"]


def test_read_paths_unchanged_without_store(tmp_path: Path) -> None:
    had_prior = hasattr(app.state, _STATE_NAME)
    if had_prior:
        delattr(app.state, _STATE_NAME)
    app.dependency_overrides[get_canonical_v2_admin_runtime] = lambda: _FakeRuntime()
    try:
        bare = TestClient(app, raise_server_exceptions=False)
        detail = bare.get("/api/canonical-v2/admin/domains/company/company-c-abc")
        assert detail.status_code == 200
        assert detail.json() == _DETAIL  # exact previous shape
        listed = bare.get("/api/canonical-v2/admin/domains/company")
        assert listed.json()["total"] == 1
        # corrections endpoints answer 503 without a store
        assert bare.get("/api/canonical-v2/admin/corrections").status_code == 503
        assert (
            bare.post(
                "/api/canonical-v2/admin/domains/company/records",
                json={"payload": {"name": "x"}, "reason": "r"},
            ).status_code
            == 503
        )
    finally:
        app.dependency_overrides.pop(get_canonical_v2_admin_runtime, None)
        if had_prior:
            setattr(app.state, _STATE_NAME, None)
