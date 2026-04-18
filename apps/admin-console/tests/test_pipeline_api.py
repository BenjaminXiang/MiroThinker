"""Round 8c-B — Pipeline coverage + source-breakdown endpoints.

Post-Codex #2/#3/#11 amendments:
 * coverage-by-institution uses COUNT DISTINCT prof per primary+current
   affiliation (Codex #3) so a multi-affiliated prof is counted once.
 * source-breakdown replaces the misleading "funnel" framing (Codex #2)
   with three honest distributions over link-level counts.
 * anomaly_only=true filters in-place (Codex #11) — no separate endpoint.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import _load_postgres_dependencies


# ---------------------------------------------------------------------------
# coverage-by-institution
# ---------------------------------------------------------------------------


def test_coverage_by_institution_returns_nonempty_list(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get(
        "/api/pipeline/coverage-by-institution"
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1


def test_coverage_by_institution_shape_matches_spec(
    professor_postgres_client: TestClient,
) -> None:
    payload = professor_postgres_client.get(
        "/api/pipeline/coverage-by-institution"
    ).json()
    assert payload, "fixture should produce at least one institution"
    sample = payload[0]
    for key in (
        "institution",
        "professor_count",
        "with_verified_papers",
        "with_research_directions",
        "empty_authors_papers",
        "identity_gate_rejection_rate",
        "avg_topic_consistency_score",
        "anomaly_flags",
    ):
        assert key in sample, f"missing key: {key}"
    assert isinstance(sample["anomaly_flags"], list)
    assert isinstance(sample["professor_count"], int)
    assert sample["identity_gate_rejection_rate"] >= 0.0
    assert sample["identity_gate_rejection_rate"] <= 1.0


def test_coverage_by_institution_anomaly_only_subset(
    professor_postgres_client: TestClient,
) -> None:
    """anomaly_only=true must return a subset where anomaly_flags is non-empty."""
    all_items = professor_postgres_client.get(
        "/api/pipeline/coverage-by-institution"
    ).json()
    anomaly_items = professor_postgres_client.get(
        "/api/pipeline/coverage-by-institution",
        params={"anomaly_only": "true"},
    ).json()
    assert len(anomaly_items) <= len(all_items)
    for item in anomaly_items:
        assert item["anomaly_flags"], (
            f"anomaly_only=true returned an institution with empty flags: {item}"
        )


def test_coverage_by_institution_counts_primary_affiliation_only(
    professor_postgres_client: TestClient, professor_data_ready: str
) -> None:
    """Codex #3: a prof with multiple (is_primary=false) affiliations must NOT
    inflate other institutions' professor_count."""
    payload = professor_postgres_client.get(
        "/api/pipeline/coverage-by-institution"
    ).json()
    by_inst = {item["institution"]: item["professor_count"] for item in payload}
    total_reported = sum(by_inst.values())

    # Compute the ground truth: how many profs have exactly one is_primary+is_current row?
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        n_profs_with_primary = conn.execute(
            """
            SELECT COUNT(DISTINCT pa.professor_id)
              FROM professor_affiliation pa
             WHERE pa.is_primary = true AND pa.is_current = true
            """
        ).fetchone()[0]
    # The sum of per-institution counts MUST equal the distinct-prof count.
    # If it exceeds, a prof was double-counted (the very bug Codex #3 flagged).
    assert total_reported == n_profs_with_primary, (
        f"coverage sum {total_reported} != distinct-prof-with-primary {n_profs_with_primary}"
    )


def test_coverage_by_institution_rejection_rate_is_ratio(
    professor_postgres_client: TestClient,
) -> None:
    payload = professor_postgres_client.get(
        "/api/pipeline/coverage-by-institution"
    ).json()
    for item in payload:
        r = item["identity_gate_rejection_rate"]
        assert 0.0 <= r <= 1.0, f"rate out of range for {item['institution']}: {r}"


# ---------------------------------------------------------------------------
# source-breakdown
# ---------------------------------------------------------------------------


def test_source_breakdown_has_three_distributions(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get("/api/pipeline/source-breakdown")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "by_evidence_api_source",
        "by_verified_by",
        "by_link_status",
    }
    assert isinstance(payload["by_evidence_api_source"], dict)
    assert isinstance(payload["by_verified_by"], dict)
    assert isinstance(payload["by_link_status"], dict)


def test_source_breakdown_link_status_sum_equals_total(
    professor_postgres_client: TestClient, professor_data_ready: str
) -> None:
    """by_link_status must account for every professor_paper_link row (no
    rows dropped by an unknown status filter)."""
    payload = professor_postgres_client.get(
        "/api/pipeline/source-breakdown"
    ).json()
    reported = sum(payload["by_link_status"].values())
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        expected = conn.execute(
            "SELECT COUNT(*) FROM professor_paper_link"
        ).fetchone()[0]
    assert reported == expected, (
        f"by_link_status sum={reported}, expected={expected}"
    )


def test_source_breakdown_verified_by_never_empty_when_any_verified_exist(
    professor_postgres_client: TestClient, professor_data_ready: str
) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(professor_data_ready) as conn:
        n_verified = conn.execute(
            "SELECT COUNT(*) FROM professor_paper_link WHERE link_status='verified'"
        ).fetchone()[0]
    if n_verified == 0:
        return
    payload = professor_postgres_client.get(
        "/api/pipeline/source-breakdown"
    ).json()
    assert payload["by_verified_by"], (
        "fixture has verified links but by_verified_by is empty"
    )
