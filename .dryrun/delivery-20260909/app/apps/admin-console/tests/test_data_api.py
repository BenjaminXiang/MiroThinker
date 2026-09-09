from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from backend.main import app
from .conftest import _load_postgres_dependencies


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeConn:
    def execute(
        self, query: str, params: dict[str, Any] | tuple[Any, ...] | None = None
    ) -> _FakeResult:
        del params
        sql = " ".join(query.split())
        # Match any industry-facet-style query: selects industry + count, groups by industry
        if (
            "industry" in sql.lower()
            and "count" in sql.lower()
            and "group by" in sql.lower()
        ):
            return _FakeResult(
                [
                    {"industry": "服务机器人", "count": 42},
                    {"industry": "VR/AR", "count": 7},
                ]
            )
        raise AssertionError(f"Unexpected SQL in fake connection: {sql}")


def _find_company_id(pg_dsn: str, patterns: list[str]) -> str:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        for pattern in patterns:
            row = conn.execute(
                """
                SELECT company_id
                FROM company
                WHERE canonical_name ILIKE %s
                ORDER BY canonical_name ASC
                LIMIT 1
                """,
                (pattern,),
            ).fetchone()
            if row is not None:
                return row[0]
    raise AssertionError(f"No company found for patterns={patterns}")


def test_facets_route_exists_with_dependency_override():
    from backend.deps import get_pg_conn

    app.dependency_overrides[get_pg_conn] = lambda: _FakeConn()
    try:
        with TestClient(app) as client:
            response = client.get("/api/data/facets/industries")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {"industry": "服务机器人", "count": 42},
        {"industry": "VR/AR", "count": 7},
    ]


def test_list_companies_returns_around_1024_default(
    postgres_client: TestClient,
) -> None:
    response = postgres_client.get("/api/data/companies")
    assert response.status_code == 200

    payload = response.json()
    assert 1020 <= payload["total"] <= 1030
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    assert len(payload["items"]) == 50


def test_filter_by_industry_vr_ar(postgres_client: TestClient) -> None:
    response = postgres_client.get("/api/data/companies", params={"industry": "VR/AR"})
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] >= 1
    assert any("极智视觉" in item["canonical_name"] for item in payload["items"])


def test_filter_by_q_jizhi(postgres_client: TestClient) -> None:
    # 极智视觉科技（深圳）is confirmed present in the test xlsx.
    response = postgres_client.get("/api/data/companies", params={"q": "极智视觉"})
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] >= 1
    assert any("极智视觉" in item["canonical_name"] for item in payload["items"])


def test_detail_endpoint_yunhe_or_旭宏(
    postgres_client: TestClient, postgres_data_ready: str
) -> None:
    company_id = _find_company_id(postgres_data_ready, ["%旭宏%", "%云合%", "%云河%"])

    response = postgres_client.get(f"/api/data/companies/{company_id}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["company"]["company_id"] == company_id
    assert payload["latest_snapshot"] is not None
    assert len(payload["all_snapshots"]) >= 1
    assert len(payload["team_members"]) >= 1
    assert len(payload["funding_events"]) >= 1


def test_pagination_page_size_10(postgres_client: TestClient) -> None:
    page_1 = postgres_client.get("/api/data/companies?page_size=10&page=1")
    page_2 = postgres_client.get("/api/data/companies?page_size=10&page=2")

    assert page_1.status_code == 200
    assert page_2.status_code == 200

    payload_1 = page_1.json()
    payload_2 = page_2.json()
    ids_1 = [item["company_id"] for item in payload_1["items"]]
    ids_2 = [item["company_id"] for item in payload_2["items"]]

    assert len(ids_1) == 10
    assert len(ids_2) == 10
    assert set(ids_1).isdisjoint(ids_2)


def test_facets_industries_returns_nonempty(postgres_client: TestClient) -> None:
    response = postgres_client.get("/api/data/facets/industries")
    assert response.status_code == 200

    payload = response.json()
    assert len(payload) >= 5


def test_detail_404(postgres_client: TestClient) -> None:
    response = postgres_client.get("/api/data/companies/COMP-does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Company not found"
