from __future__ import annotations

from fastapi.testclient import TestClient


def test_export_csv_all(client: TestClient):
    resp = client.get("/api/export/professor?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "professor_export.csv" in resp.headers["content-disposition"]
    body = resp.content.decode("utf-8-sig")
    lines = body.strip().split("\n")
    # Header + 3 professor rows
    assert len(lines) == 4
    assert "姓名" in lines[0]


def test_export_csv_selected_ids(client: TestClient):
    resp = client.get("/api/export/professor?format=csv&ids=PROF-1,PROF-2")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")
    lines = body.strip().split("\n")
    # Header + 2 selected rows
    assert len(lines) == 3


def test_export_xlsx(client: TestClient):
    resp = client.get("/api/export/professor?format=xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_invalid_domain(client: TestClient):
    resp = client.get("/api/export/invalid_domain")
    assert resp.status_code == 422


def test_export_company_csv(client: TestClient):
    resp = client.get("/api/export/company?format=csv")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")
    lines = body.strip().split("\n")
    # Header + 1 company row
    assert len(lines) == 2
    assert "企业名称" in lines[0]
