from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import _load_postgres_dependencies


def _find_paper_with_linked_professors(pg_dsn: str) -> tuple[str, int]:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        row = conn.execute(
            """
            SELECT p.paper_id, count(*)::int AS link_count
            FROM paper p
            JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id
            GROUP BY p.paper_id
            ORDER BY
                sum(CASE WHEN ppl.link_status = 'verified' THEN 1 ELSE 0 END) DESC,
                count(*) DESC,
                max(p.citation_count) DESC NULLS LAST,
                p.paper_id ASC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise AssertionError("No paper found with linked professors")
    return row[0], row[1]


def _verified_paper_ids(pg_dsn: str) -> set[str]:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT paper_id
            FROM professor_paper_link
            WHERE link_status = 'verified'
            """
        ).fetchall()
    return {row[0] for row in rows}


def test_paper_list_returns_data(professor_postgres_client: TestClient) -> None:
    response = professor_postgres_client.get("/api/data/papers")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] > 0
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    assert 1 <= len(payload["items"]) <= 50

    first_item = payload["items"][0]
    assert "paper_id" in first_item
    assert "title_clean" in first_item
    assert "linked_professor_count" in first_item


def test_paper_list_filters_verified_professors(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    verified_ids = _verified_paper_ids(professor_data_ready)

    response = professor_postgres_client.get(
        "/api/data/papers",
        params={"has_verified_professor": "true"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] >= 1
    assert len(payload["items"]) >= 1
    assert all(item["paper_id"] in verified_ids for item in payload["items"])


def test_paper_detail_linked_professors(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    paper_id, expected_link_count = _find_paper_with_linked_professors(
        professor_data_ready
    )

    response = professor_postgres_client.get(f"/api/data/papers/{paper_id}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["paper"]["paper_id"] == paper_id
    linked_professors = payload["linked_professors"]
    total_links = len(linked_professors["verified"]) + len(linked_professors["candidate"])
    assert total_links >= 1
    assert total_links == expected_link_count


def test_paper_404(professor_postgres_client: TestClient) -> None:
    response = professor_postgres_client.get("/api/data/papers/PAPER-does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Paper not found"


def test_patent_list_empty_ok(professor_postgres_client: TestClient) -> None:
    response = professor_postgres_client.get("/api/data/patents")
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_patent_detail_404(professor_postgres_client: TestClient) -> None:
    response = professor_postgres_client.get("/api/data/patents/PAT-does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Patent not found"


# ---------------------------------------------------------------------------
# Round 8c-A: paper detail must carry rejected-prof bucket + topic score
# ---------------------------------------------------------------------------


def test_paper_detail_exposes_rejected_professor_bucket(
    professor_postgres_client: TestClient, professor_data_ready: str
) -> None:
    """8c-A: paper-side view must show professors whose link was gate-rejected."""
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        row = conn.execute(
            """
            SELECT paper_id
              FROM professor_paper_link
             WHERE link_status = 'rejected'
             LIMIT 1
            """
        ).fetchone()
    if row is None:
        return
    paper_id = row[0]
    payload = professor_postgres_client.get(f"/api/data/papers/{paper_id}").json()
    profs = payload["linked_professors"]
    assert "rejected" in profs, "rejected bucket must exist on paper detail"
    assert isinstance(profs["rejected"], list)
    if profs["rejected"]:
        first = profs["rejected"][0]
        assert "professor_id" in first
        assert "rejected_reason" in first
        assert "topic_consistency_score" in first


def test_paper_detail_linked_professor_carries_topic_consistency_and_reason(
    professor_postgres_client: TestClient, professor_data_ready: str
) -> None:
    """8c-A: verified/candidate entries carry topic_consistency_score + match_reason."""
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        row = conn.execute(
            """
            SELECT paper_id
              FROM professor_paper_link
             WHERE link_status = 'verified'
               AND topic_consistency_score IS NOT NULL
             LIMIT 1
            """
        ).fetchone()
    if row is None:
        return
    paper_id = row[0]
    payload = professor_postgres_client.get(f"/api/data/papers/{paper_id}").json()
    verified = payload["linked_professors"]["verified"]
    assert verified
    first = verified[0]
    for key in ("topic_consistency_score", "match_reason", "verified_by"):
        assert key in first
