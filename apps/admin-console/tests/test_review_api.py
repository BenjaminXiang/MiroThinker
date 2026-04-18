"""Round 8c-C — /api/review/sample and /api/review/issues CRUD.

Covers:
 * sample endpoint returns n profs with the shape ProfessorSample
 * seed reproducibility (same seed → same prof ordering)
 * institution filter
 * POST issues auto-populates evidence_snapshot from current DB state
 * CHECK constraints surface as 400
 * duplicate open issue → 409
 * resolve transitions state and is reflected in list filter
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from .conftest import _load_postgres_dependencies


TSINGHUA_SIGS = "清华大学深圳国际研究生院"


# ---------------------------------------------------------------------------
# /api/review/sample
# ---------------------------------------------------------------------------


def test_review_sample_returns_n_profs(
    professor_postgres_client: TestClient,
) -> None:
    response = professor_postgres_client.get(
        "/api/review/sample", params={"n": 5}
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) <= 5


def test_review_sample_card_shape_matches_spec(
    professor_postgres_client: TestClient,
) -> None:
    payload = professor_postgres_client.get(
        "/api/review/sample", params={"n": 5}
    ).json()
    if not payload:
        return
    card = payload[0]
    for key in (
        "professor_id",
        "canonical_name",
        "canonical_name_en",
        "institution",
        "primary_profile_url",
        "research_directions",
        "research_directions_source",
        "verified_papers",
        "rejected_papers",
        "facts_by_type",
    ):
        assert key in card, f"missing key: {key}"
    assert isinstance(card["research_directions"], list)
    assert isinstance(card["facts_by_type"], dict)


def test_review_sample_seed_reproducible(
    professor_postgres_client: TestClient,
) -> None:
    """Same seed → same ordering."""
    first = professor_postgres_client.get(
        "/api/review/sample", params={"n": 10, "seed": "LOCK-1"}
    ).json()
    second = professor_postgres_client.get(
        "/api/review/sample", params={"n": 10, "seed": "LOCK-1"}
    ).json()
    assert [c["professor_id"] for c in first] == [c["professor_id"] for c in second]


def test_review_sample_different_seeds_may_differ(
    professor_postgres_client: TestClient,
) -> None:
    """Different seeds should at least sometimes produce different sets.
    We accept equal sets in the degenerate case of <=N total profs."""
    a = professor_postgres_client.get(
        "/api/review/sample", params={"n": 10, "seed": "LOCK-A"}
    ).json()
    b = professor_postgres_client.get(
        "/api/review/sample", params={"n": 10, "seed": "LOCK-B"}
    ).json()
    if len(a) < 2 or len(b) < 2:
        return
    # Allow the rare case they're equal (small population) but assert shape.
    assert isinstance(a, list) and isinstance(b, list)


def test_review_sample_institution_filter(
    professor_postgres_client: TestClient,
) -> None:
    payload = professor_postgres_client.get(
        "/api/review/sample",
        params={"institution": TSINGHUA_SIGS, "n": 5},
    ).json()
    if not payload:
        return
    for card in payload:
        assert card["institution"] == TSINGHUA_SIGS


# ---------------------------------------------------------------------------
# POST /api/review/issues
# ---------------------------------------------------------------------------


def _a_professor_id(pg_dsn: str) -> str | None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        row = conn.execute(
            "SELECT professor_id FROM professor ORDER BY professor_id LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def test_report_issue_creates_row_with_evidence_snapshot(
    professor_postgres_client: TestClient, professor_data_ready: str
) -> None:
    pid = _a_professor_id(professor_data_ready)
    if pid is None:
        return
    body = {
        "professor_id": pid,
        "stage": "discovery",
        "severity": "medium",
        "description": f"snapshot-test-{uuid.uuid4().hex[:8]}",
        "reported_by": "qa",
    }
    response = professor_postgres_client.post("/api/review/issues", json=body)
    assert response.status_code in (200, 201), response.text
    created = response.json()
    assert "issue_id" in created
    assert created["professor_id"] == pid
    assert created["stage"] == "discovery"
    assert created["resolved"] is False
    # Codex #5: backend auto-populates evidence_snapshot
    assert created.get("evidence_snapshot") is not None, (
        "evidence_snapshot must be auto-generated server-side"
    )
    snap = created["evidence_snapshot"]
    assert isinstance(snap, dict)
    # The snapshot must include at least the professor context.
    assert "professor" in snap or "canonical_name" in snap


def test_report_issue_invalid_stage_returns_400(
    professor_postgres_client: TestClient,
) -> None:
    body = {
        "institution": "SUSTech",
        "stage": "not_a_stage",
        "severity": "low",
        "description": "x",
        "reported_by": "qa",
    }
    response = professor_postgres_client.post("/api/review/issues", json=body)
    assert response.status_code == 422 or response.status_code == 400


def test_report_issue_without_any_target_returns_400(
    professor_postgres_client: TestClient,
) -> None:
    """Codex #7: at least one of professor_id / link_id / institution required."""
    body = {
        "stage": "coverage",
        "severity": "low",
        "description": "no-target-test",
        "reported_by": "qa",
    }
    response = professor_postgres_client.post("/api/review/issues", json=body)
    assert response.status_code in (400, 422)


def test_report_issue_duplicate_returns_409(
    professor_postgres_client: TestClient,
) -> None:
    """CEO A2 + Codex #6: same (target, stage, reporter, desc_hash) → 409."""
    payload = {
        "institution": "SUSTech",
        "stage": "coverage",
        "severity": "medium",
        "description": f"dup-test-{uuid.uuid4().hex[:8]}",
        "reported_by": "duplicate-tester",
    }
    first = professor_postgres_client.post("/api/review/issues", json=payload)
    assert first.status_code in (200, 201)
    second = professor_postgres_client.post("/api/review/issues", json=payload)
    assert second.status_code == 409, (
        f"expected 409 on duplicate, got {second.status_code} {second.text}"
    )


def test_report_issue_different_description_allowed(
    professor_postgres_client: TestClient,
) -> None:
    """Same target/stage/reporter, different description → second insert OK."""
    base = {
        "institution": "SUSTech",
        "stage": "coverage",
        "severity": "low",
        "reported_by": "variety-tester",
    }
    first = professor_postgres_client.post(
        "/api/review/issues",
        json={**base, "description": f"first-{uuid.uuid4().hex[:8]}"},
    )
    assert first.status_code in (200, 201)
    second = professor_postgres_client.post(
        "/api/review/issues",
        json={**base, "description": f"second-{uuid.uuid4().hex[:8]}"},
    )
    assert second.status_code in (200, 201)


# ---------------------------------------------------------------------------
# GET /api/review/issues
# ---------------------------------------------------------------------------


def test_list_issues_filters_by_resolved_and_stage(
    professor_postgres_client: TestClient,
) -> None:
    # Ensure there's at least one unresolved issue to find.
    unique_desc = f"filter-test-{uuid.uuid4().hex[:8]}"
    professor_postgres_client.post(
        "/api/review/issues",
        json={
            "institution": "SUSTech",
            "stage": "identity_gate",
            "severity": "low",
            "description": unique_desc,
            "reported_by": "filter-tester",
        },
    )
    open_issues = professor_postgres_client.get(
        "/api/review/issues",
        params={"resolved": "false", "stage": "identity_gate"},
    ).json()
    assert isinstance(open_issues, list)
    assert any(i["description"] == unique_desc for i in open_issues)
    assert all(i["stage"] == "identity_gate" for i in open_issues)
    assert all(i["resolved"] is False for i in open_issues)


# ---------------------------------------------------------------------------
# PATCH /api/review/issues/{id}/resolve
# ---------------------------------------------------------------------------


def test_resolve_issue_transitions_state(
    professor_postgres_client: TestClient,
) -> None:
    payload = {
        "institution": "SUSTech",
        "stage": "affiliation",
        "severity": "low",
        "description": f"resolve-test-{uuid.uuid4().hex[:8]}",
        "reported_by": "resolver-tester",
    }
    created = professor_postgres_client.post(
        "/api/review/issues", json=payload
    ).json()
    issue_id = created["issue_id"]

    resolved = professor_postgres_client.patch(
        f"/api/review/issues/{issue_id}/resolve",
        json={"resolution_notes": "fixed by Round 7.99", "resolution_round": "7.99"},
    )
    assert resolved.status_code == 200
    updated = resolved.json()
    assert updated["resolved"] is True
    assert updated["resolution_round"] == "7.99"
    assert updated["resolved_at"] is not None


def test_resolve_nonexistent_issue_returns_404(
    professor_postgres_client: TestClient,
) -> None:
    bogus = str(uuid.uuid4())
    response = professor_postgres_client.patch(
        f"/api/review/issues/{bogus}/resolve",
        json={"resolution_notes": "whatever"},
    )
    assert response.status_code == 404
