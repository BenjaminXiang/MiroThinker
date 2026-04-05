from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_professors_paginated(client: TestClient):
    resp = client.get("/api/professor?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["items"]) == 3


def test_list_professors_search(client: TestClient):
    resp = client.get("/api/professor?q=靳")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["display_name"] == "靳玉乐"


def test_list_professors_sort_desc(client: TestClient):
    resp = client.get("/api/professor?sort_by=display_name&sort_order=desc")
    assert resp.status_code == 200
    data = resp.json()
    names = [item["display_name"] for item in data["items"]]
    assert names == sorted(names, reverse=True)


def test_list_empty_page(client: TestClient):
    resp = client.get("/api/professor?page=999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 3


def test_invalid_domain_returns_422(client: TestClient):
    resp = client.get("/api/invalid_domain")
    assert resp.status_code == 422


def test_get_professor_detail(client: TestClient):
    resp = client.get("/api/professor/PROF-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "PROF-1"
    assert data["display_name"] == "靳玉乐"
    assert data["object_type"] == "professor"


def test_get_nonexistent_returns_404(client: TestClient):
    resp = client.get("/api/professor/NONEXISTENT")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Object not found"


def test_invalid_sort_by_returns_422(client: TestClient):
    resp = client.get("/api/professor?sort_by=payload_json")
    assert resp.status_code == 422
    assert "sort_by" in resp.json()["detail"].lower() or "Allowed" in resp.json()["detail"]


def test_health_endpoint(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
