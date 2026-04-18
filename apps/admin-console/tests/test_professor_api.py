from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import _load_postgres_dependencies


TSINGHUA_SIGS = "清华大学深圳国际研究生院"


def _find_professor_with_facts_and_papers(pg_dsn: str) -> tuple[str, str]:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        row = conn.execute(
            """
            SELECT p.professor_id, p.canonical_name
            FROM professor p
            WHERE EXISTS (
                SELECT 1
                FROM professor_fact pf
                WHERE pf.professor_id = p.professor_id
                  AND pf.fact_type = 'research_topic'
            )
              AND EXISTS (
                SELECT 1
                FROM professor_paper_link ppl
                WHERE ppl.professor_id = p.professor_id
            )
            ORDER BY
                (
                    SELECT count(*)
                    FROM professor_fact pf
                    WHERE pf.professor_id = p.professor_id
                      AND pf.fact_type = 'research_topic'
                ) DESC,
                (
                    SELECT count(*)
                    FROM professor_paper_link ppl
                    WHERE ppl.professor_id = p.professor_id
                ) DESC,
                p.canonical_name ASC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise AssertionError("No professor found with research topics and linked papers")
    return row[0], row[1]


def test_list_professors_returns_data(professor_postgres_client: TestClient) -> None:
    response = professor_postgres_client.get("/api/data/professors")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] > 0
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    assert 1 <= len(payload["items"]) <= 50

    first_item = payload["items"][0]
    assert "professor_id" in first_item
    assert "canonical_name" in first_item
    assert "verified_paper_count" in first_item


def test_filter_by_institution_tsinghua_sigs(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get(
        "/api/data/professors",
        params={"institution": TSINGHUA_SIGS},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] >= 1
    assert len(payload["items"]) >= 1
    assert all(item["institution"] == TSINGHUA_SIGS for item in payload["items"])


def test_filter_by_has_verified_papers(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get(
        "/api/data/professors",
        params={"has_verified_papers": "true"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] >= 1
    assert len(payload["items"]) >= 1
    assert all(item["verified_paper_count"] >= 1 for item in payload["items"])


def test_professor_detail_includes_facts_and_papers(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    professor_id, professor_name = _find_professor_with_facts_and_papers(
        professor_data_ready
    )

    response = professor_postgres_client.get(f"/api/data/professors/{professor_id}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["professor"]["professor_id"] == professor_id
    assert payload["professor"]["canonical_name"] == professor_name
    assert len(payload["affiliations"]) >= 1
    assert payload["facts_by_type"]["research_topic"]
    assert len(payload["verified_papers"]) <= 20
    assert len(payload["candidate_papers"]) <= 20
    assert payload["source_pages_used"] >= 1
    assert payload["affiliations"][0]["is_primary"] is True


def test_professor_detail_404(professor_postgres_client: TestClient) -> None:
    response = professor_postgres_client.get("/api/data/professors/PROF-does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Professor not found"


def test_professor_institution_facets_returns_data(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get("/api/data/facets/professor-institutions")
    assert response.status_code == 200

    payload = response.json()
    assert len(payload) >= 1
    assert payload[0]["count"] >= payload[-1]["count"]


def test_research_topic_facets_returns_data(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get("/api/data/facets/research-topics")
    assert response.status_code == 200

    payload = response.json()
    assert len(payload) >= 1
    assert payload[0]["count"] >= payload[-1]["count"]


# ---------------------------------------------------------------------------
# Round 8c-A: provenance + rejected-paper bucket + pagination
# ---------------------------------------------------------------------------


def test_professor_detail_exposes_primary_profile_url_and_directions_source(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    """8c-A: detail response must include the top-level provenance fields."""
    professor_id, _ = _find_professor_with_facts_and_papers(professor_data_ready)
    payload = professor_postgres_client.get(
        f"/api/data/professors/{professor_id}"
    ).json()
    prof = payload["professor"]
    # The key must exist even if value is None.
    assert "primary_profile_url" in prof
    assert "research_directions_source" in prof
    if prof["research_directions_source"] is not None:
        assert prof["research_directions_source"] in {
            "official_only",
            "paper_driven",
            "merged",
        }


def test_professor_detail_facts_carry_source_page_metadata(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    """8c-A: every ProfessorFactValue must expose source_page_url, role, fetched_at."""
    professor_id, _ = _find_professor_with_facts_and_papers(professor_data_ready)
    payload = professor_postgres_client.get(
        f"/api/data/professors/{professor_id}"
    ).json()
    facts = payload["facts_by_type"]["research_topic"]
    assert facts, "fixture must have at least one research_topic fact"
    for fact in facts:
        assert "source_page_url" in fact
        assert "source_page_role" in fact
        assert "source_page_fetched_at" in fact


def test_professor_detail_affiliations_carry_source_page_metadata(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    """8c-A: ProfessorAffiliation must expose source_page_url + role."""
    professor_id, _ = _find_professor_with_facts_and_papers(professor_data_ready)
    payload = professor_postgres_client.get(
        f"/api/data/professors/{professor_id}"
    ).json()
    for aff in payload["affiliations"]:
        assert "source_page_url" in aff
        assert "source_page_role" in aff


def test_professor_detail_verified_papers_carry_provenance(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    """8c-A: every PaperSummaryWithProvenance must carry link-level provenance."""
    professor_id, _ = _find_professor_with_facts_and_papers(professor_data_ready)
    payload = professor_postgres_client.get(
        f"/api/data/professors/{professor_id}"
    ).json()
    if not payload["verified_papers"]:
        return  # some random profs have no verified papers
    paper = payload["verified_papers"][0]
    for key in (
        "link_status",
        "match_reason",
        "rejected_reason",
        "verified_by",
        "verified_at",
        "evidence_api_source",
        "evidence_page_url",
        "is_officially_listed",
        "topic_consistency_score",
    ):
        assert key in paper, f"missing provenance key: {key}"
    assert paper["link_status"] == "verified"


def test_professor_detail_returns_rejected_papers_bucket(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    """8c-A: rejected_papers must be its own bucket, capped at 50 (CEO A1)."""
    # Pick any prof that has ≥1 rejected link.
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        row = conn.execute(
            """
            SELECT ppl.professor_id
              FROM professor_paper_link ppl
             WHERE ppl.link_status = 'rejected'
             GROUP BY ppl.professor_id
             ORDER BY COUNT(*) DESC
             LIMIT 1
            """
        ).fetchone()
    if row is None:
        return  # mock DB may lack rejections
    professor_id = row[0]
    payload = professor_postgres_client.get(
        f"/api/data/professors/{professor_id}"
    ).json()
    assert "rejected_papers" in payload
    assert "rejected_papers_total" in payload
    assert isinstance(payload["rejected_papers"], list)
    assert isinstance(payload["rejected_papers_total"], int)
    assert len(payload["rejected_papers"]) <= 50
    assert payload["rejected_papers_total"] >= len(payload["rejected_papers"])
    if payload["rejected_papers"]:
        first_rej = payload["rejected_papers"][0]
        assert first_rej["link_status"] == "rejected"
        assert "rejected_reason" in first_rej


def test_professor_detail_rejected_papers_ordered_by_rejected_at_desc(
    professor_postgres_client: TestClient,
    professor_data_ready: str,
) -> None:
    """8c-A: most recently rejected first."""
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        row = conn.execute(
            """
            SELECT ppl.professor_id
              FROM professor_paper_link ppl
             WHERE ppl.link_status = 'rejected'
             GROUP BY ppl.professor_id
            HAVING COUNT(*) >= 2
             LIMIT 1
            """
        ).fetchone()
    if row is None:
        return
    professor_id = row[0]
    rejected = professor_postgres_client.get(
        f"/api/data/professors/{professor_id}"
    ).json()["rejected_papers"]
    # Gather rejected_at timestamps server-side
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        rows = conn.execute(
            """
            SELECT p.paper_id, ppl.rejected_at
              FROM professor_paper_link ppl
              JOIN paper p ON p.paper_id = ppl.paper_id
             WHERE ppl.professor_id = %s AND ppl.link_status='rejected'
             ORDER BY ppl.rejected_at DESC NULLS LAST
            """,
            (professor_id,),
        ).fetchall()
    expected_order = [r[0] for r in rows][: len(rejected)]
    assert [p["paper_id"] for p in rejected] == expected_order
