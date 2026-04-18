from __future__ import annotations

from fastapi.testclient import TestClient


def test_batch_update_quality(client: TestClient):
    resp = client.patch(
        "/api/batch/quality",
        json={"ids": ["PROF-1", "PROF-2"], "quality_status": "low_confidence"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    # Verify the change persisted
    detail = client.get("/api/professor/PROF-1").json()
    assert detail["quality_status"] == "low_confidence"


def test_batch_update_quality_partial(client: TestClient):
    """Some IDs exist, some don't — should only count existing ones."""
    resp = client.patch(
        "/api/batch/quality",
        json={"ids": ["PROF-1", "NONEXISTENT"], "quality_status": "needs_review"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1


def test_batch_update_quality_needs_enrichment(client: TestClient):
    resp = client.patch(
        "/api/batch/quality",
        json={"ids": ["PROF-1"], "quality_status": "needs_enrichment"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1

    detail = client.get("/api/professor/PROF-1").json()
    assert detail["quality_status"] == "needs_enrichment"


def test_batch_update_quality_empty_ids(client: TestClient):
    resp = client.patch(
        "/api/batch/quality",
        json={"ids": [], "quality_status": "ready"},
    )
    assert resp.status_code == 422


def test_batch_delete(client: TestClient):
    resp = client.post(
        "/api/batch/delete",
        json={"ids": ["PROF-1", "PROF-2"]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    # Verify they are gone
    assert client.get("/api/professor/PROF-1").status_code == 404
    assert client.get("/api/professor/PROF-2").status_code == 404


def test_batch_delete_nonexistent(client: TestClient):
    resp = client.post(
        "/api/batch/delete",
        json={"ids": ["NONEXISTENT-1"]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


def test_batch_delete_empty_ids(client: TestClient):
    resp = client.post(
        "/api/batch/delete",
        json={"ids": []},
    )
    assert resp.status_code == 422
