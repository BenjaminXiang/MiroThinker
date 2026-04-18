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
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_get_professor_related_papers_uses_relation_objects(client: TestClient, populated_store):
    from src.data_agents.contracts import ReleasedObject
    from .conftest import _evidence, TIMESTAMP

    paper = ReleasedObject(
        id="PAPER-1",
        object_type="paper",
        display_name="On the Analytical Engine",
        core_facts={"title": "On the Analytical Engine", "professor_ids": []},
        summary_fields={"summary_text": "A paper."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status="ready",
    )
    link = ReleasedObject(
        id="PPLINK-1",
        object_type="professor_paper_link",
        display_name="靳玉乐 -> On the Analytical Engine",
        core_facts={
            "professor_id": "PROF-1",
            "paper_id": "PAPER-1",
            "link_status": "verified",
            "professor_name": "靳玉乐",
            "paper_title": "On the Analytical Engine",
            "evidence_source": "official_linked_google_scholar",
            "evidence_url": "https://scholar.google.com/citations?user=abc",
            "verified_by": "pipeline_v3",
        },
        summary_fields={"match_reason": "Verified via official scholar profile."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status="ready",
    )
    populated_store.upsert_released_objects([paper, link])

    resp = client.get('/api/professor/PROF-1/related')
    assert resp.status_code == 200
    data = resp.json()
    assert [item['id'] for item in data['papers']] == ['PAPER-1']


def test_get_paper_related_professors_does_not_fallback_to_legacy_professor_ids(client: TestClient, populated_store):
    from src.data_agents.contracts import ReleasedObject
    from .conftest import _evidence, TIMESTAMP

    paper = ReleasedObject(
        id="PAPER-1",
        object_type="paper",
        display_name="On the Analytical Engine",
        core_facts={"title": "On the Analytical Engine", "professor_ids": ["PROF-1"]},
        summary_fields={"summary_text": "A paper."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status="ready",
    )
    populated_store.upsert_released_objects([paper])

    resp = client.get('/api/paper/PAPER-1/related')
    assert resp.status_code == 200
    data = resp.json()
    assert data['papers'] == []
