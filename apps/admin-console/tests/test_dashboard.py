from __future__ import annotations

from fastapi.testclient import TestClient


def test_dashboard_returns_domain_counts_and_quality(client: TestClient):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    domains = {d["name"]: d for d in data["domains"]}

    assert domains["professor"]["count"] == 3
    assert domains["professor"]["quality"]["ready"] == 2
    assert domains["professor"]["quality"]["needs_review"] == 1

    assert domains["company"]["count"] == 1
    assert domains["company"]["quality"]["ready"] == 1

    assert domains["paper"]["count"] == 0
    assert domains["patent"]["count"] == 0


def test_dashboard_empty_db(client: TestClient, store, tmp_path):
    from backend.deps import get_store
    from backend.main import app
    from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

    empty_store = SqliteReleasedObjectStore(tmp_path / "empty.db")
    app.dependency_overrides[get_store] = lambda: empty_store
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    for d in data["domains"]:
        assert d["count"] == 0


def test_dashboard_response_matches_schema(client: TestClient):
    resp = client.get("/api/dashboard")
    data = resp.json()
    assert "domains" in data
    for d in data["domains"]:
        assert "name" in d
        assert "count" in d
        assert "quality" in d
        assert isinstance(d["quality"], dict)
