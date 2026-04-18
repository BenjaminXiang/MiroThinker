from __future__ import annotations

import json

from fastapi.testclient import TestClient


# --- PATCH update tests ---

def test_update_core_facts(client: TestClient):
    resp = client.patch(
        "/api/professor/PROF-1",
        json={"core_facts": {"title": "教授", "department": "教育学院"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["core_facts"]["title"] == "教授"
    assert data["core_facts"]["department"] == "教育学院"
    # Original fields should be preserved (merge, not replace)
    assert data["core_facts"]["name"] == "靳玉乐"


def test_update_quality_status(client: TestClient):
    resp = client.patch(
        "/api/professor/PROF-1",
        json={"quality_status": "low_confidence"},
    )
    assert resp.status_code == 200
    assert resp.json()["quality_status"] == "low_confidence"


def test_update_quality_status_to_needs_enrichment(client: TestClient):
    resp = client.patch(
        "/api/professor/PROF-1",
        json={"quality_status": "needs_enrichment"},
    )
    assert resp.status_code == 200
    assert resp.json()["quality_status"] == "needs_enrichment"


def test_update_summary_fields(client: TestClient):
    resp = client.patch(
        "/api/professor/PROF-1",
        json={"summary_fields": {"profile_summary": "Updated summary."}},
    )
    assert resp.status_code == 200
    assert resp.json()["summary_fields"]["profile_summary"] == "Updated summary."


def test_update_display_name_via_core_facts_name(client: TestClient):
    """When core_facts.name is changed, display_name should update."""
    resp = client.patch(
        "/api/professor/PROF-1",
        json={"core_facts": {"name": "靳教授"}},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "靳教授"


def test_update_nonexistent_returns_404(client: TestClient):
    resp = client.patch(
        "/api/professor/NONEXISTENT",
        json={"quality_status": "ready"},
    )
    assert resp.status_code == 404


def test_update_no_changes(client: TestClient):
    resp = client.patch("/api/professor/PROF-1", json={})
    assert resp.status_code == 200
    assert resp.json()["id"] == "PROF-1"


# --- DELETE tests ---

def test_delete_object(client: TestClient):
    resp = client.delete("/api/professor/PROF-1")
    assert resp.status_code == 204
    # Verify it's gone
    assert client.get("/api/professor/PROF-1").status_code == 404


def test_delete_nonexistent_returns_404(client: TestClient):
    resp = client.delete("/api/professor/NONEXISTENT")
    assert resp.status_code == 404


# --- Filter tests ---

def test_list_with_quality_filter(client: TestClient):
    filters = json.dumps({"quality_status": "needs_review"})
    resp = client.get(f"/api/professor?filters={filters}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["display_name"] == "王芳"


def test_list_with_needs_enrichment_filter(client: TestClient):
    filters = json.dumps({"quality_status": "needs_enrichment"})
    resp = client.get(f"/api/professor?filters={filters}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


def test_list_with_invalid_filters_json(client: TestClient):
    resp = client.get("/api/professor?filters=not_json")
    assert resp.status_code == 422


def test_list_search_and_filter_combined(client: TestClient):
    filters = json.dumps({"quality_status": "ready"})
    resp = client.get(f"/api/professor?q=李&filters={filters}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["display_name"] == "李明"


# --- Filter options endpoint ---

def test_get_filter_options(client: TestClient):
    resp = client.get("/api/professor/filters/quality_status")
    assert resp.status_code == 200
    data = resp.json()
    options = data["options"]
    assert "ready" in options
    assert "needs_review" in options


# --- Dashboard ---

def test_dashboard_has_last_updated(client: TestClient):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    professor_domain = next(d for d in data["domains"] if d["name"] == "professor")
    assert professor_domain["count"] == 3
    assert professor_domain["last_updated"] is not None


def test_dashboard_empty_domain(client: TestClient):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    paper_domain = next(d for d in data["domains"] if d["name"] == "paper")
    assert paper_domain["count"] == 0
    assert paper_domain["last_updated"] is None
