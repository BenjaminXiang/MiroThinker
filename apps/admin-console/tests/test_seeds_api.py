"""Integration tests for /api/seeds — OpenSpec change prof-seed-admin-console.

Covers every Scenario in
`openspec/changes/prof-seed-admin-console/specs/professor-seed-management/spec.md`
that is reachable in Phase A (CRUD only; trigger / cron / pipeline-upsert /
adapter-missing scenarios are Phase B).
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.api import seeds as seeds_api

pytestmark = pytest.mark.usefixtures("postgres_data_ready")


def _wipe_seeds(dsn: str) -> None:
    pg_dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM professor_seed")
        conn.commit()


def _pg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def _set_seed_status(dsn: str, seed_id: int, status: str) -> None:
    with psycopg.connect(_pg_dsn(dsn)) as conn:
        conn.execute(
            "UPDATE professor_seed SET last_run_status=%s WHERE id=%s",
            (status, seed_id),
        )
        conn.commit()


def _seed_status(dsn: str, seed_id: int) -> tuple[str, bool]:
    with psycopg.connect(_pg_dsn(dsn)) as conn:
        row = conn.execute(
            """
            SELECT last_run_status, last_run_at IS NOT NULL
              FROM professor_seed
             WHERE id = %s
            """,
            (seed_id,),
        ).fetchone()
    assert row is not None
    return row[0], bool(row[1])


def _pipeline_run_status(dsn: str, run_id: str) -> tuple[str, str, dict[str, Any]]:
    with psycopg.connect(_pg_dsn(dsn)) as conn:
        row = conn.execute(
            """
            SELECT run_kind, status, run_scope
              FROM pipeline_run
             WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
    assert row is not None
    return row[0], row[1], row[2]


@pytest.fixture
def fresh_seeds(postgres_client: TestClient, postgres_data_ready: str) -> TestClient:
    _wipe_seeds(postgres_data_ready)
    return postgres_client


# --- Schema scenarios --------------------------------------------------------


def test_create_department_level_seed(fresh_seeds: TestClient) -> None:
    """Scenario: Department-level seed."""
    resp = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SZU",
            "department": "计算机与软件学院",
            "seed_url": "https://cse.szu.edu.cn/teachers",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["school"] == "SZU"
    assert body["department"] == "计算机与软件学院"
    assert body["seed_url"] == "https://cse.szu.edu.cn/teachers"
    assert body["last_run_status"] == "never_run"
    assert body["last_run_at"] is None


def test_create_school_wide_seed_normalizes_empty_department(
    fresh_seeds: TestClient,
) -> None:
    """Scenario: School-wide unified roster seed."""
    resp = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": "",
            "seed_url": "https://faculty.sustech.edu.cn",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["department"] is None


def test_create_normalizes_whitespace_department(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "HITSZ",
            "department": "   ",
            "seed_url": "https://eie.hitsz.edu.cn/teachers",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["department"] is None


def test_reject_invalid_url(fresh_seeds: TestClient) -> None:
    """Scenario: Reject invalid URL."""
    resp = fresh_seeds.post(
        "/api/seeds",
        json={"school": "SUSTech", "department": None, "seed_url": "not-a-url"},
    )
    assert resp.status_code == 422


def test_reject_blank_school(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.post(
        "/api/seeds",
        json={"school": "   ", "department": None, "seed_url": "https://example.com"},
    )
    assert resp.status_code == 422


# --- Listing -----------------------------------------------------------------


def test_list_returns_sorted(fresh_seeds: TestClient) -> None:
    seeds = [
        {"school": "SZU", "department": "数学学院", "seed_url": "https://math.szu.edu.cn/t"},
        {"school": "SZU", "department": "计算机与软件学院", "seed_url": "https://cse.szu.edu.cn/t"},
        {"school": "SZU", "department": None, "seed_url": "https://www.szu.edu.cn/all"},
        {"school": "SUSTech", "department": None, "seed_url": "https://faculty.sustech.edu.cn"},
    ]
    for body in seeds:
        resp = fresh_seeds.post("/api/seeds", json=body)
        assert resp.status_code == 201

    listed = fresh_seeds.get("/api/seeds").json()
    assert [(s["school"], s["department"]) for s in listed] == [
        ("SUSTech", None),
        ("SZU", None),
        ("SZU", "数学学院"),
        ("SZU", "计算机与软件学院"),
    ]


# --- Read --------------------------------------------------------------------


def test_get_single(fresh_seeds: TestClient) -> None:
    created = fresh_seeds.post(
        "/api/seeds",
        json={"school": "X", "department": None, "seed_url": "https://x.example.com"},
    ).json()
    resp = fresh_seeds.get(f"/api/seeds/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_404_on_missing(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.get("/api/seeds/999999")
    assert resp.status_code == 404


# --- Update ------------------------------------------------------------------


def test_update_school_and_department(fresh_seeds: TestClient) -> None:
    created = fresh_seeds.post(
        "/api/seeds",
        json={"school": "old-school", "department": "old-dept", "seed_url": "https://x.example.com"},
    ).json()
    resp = fresh_seeds.put(
        f"/api/seeds/{created['id']}",
        json={"school": "new-school", "department": "new-dept", "seed_url": "https://x.example.com"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["school"] == "new-school"
    assert body["department"] == "new-dept"
    assert body["id"] == created["id"]


def test_update_silently_ignores_run_status_in_body(
    fresh_seeds: TestClient,
) -> None:
    """Scenario: Admin cannot mutate run status."""
    created = fresh_seeds.post(
        "/api/seeds",
        json={"school": "X", "department": None, "seed_url": "https://x.example.com"},
    ).json()
    assert created["last_run_status"] == "never_run"

    resp = fresh_seeds.put(
        f"/api/seeds/{created['id']}",
        json={
            "school": "X",
            "department": None,
            "seed_url": "https://x.example.com",
            "last_run_status": "success",
            "last_run_at": "2050-01-01T00:00:00Z",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["last_run_status"] == "never_run", "status field must be ignored on PUT"
    assert body["last_run_at"] is None, "timestamp must be ignored on PUT"


def test_update_404_on_missing(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.put(
        "/api/seeds/999999",
        json={"school": "X", "department": None, "seed_url": "https://x.example.com"},
    )
    assert resp.status_code == 404


def test_update_rejects_duplicate_seed_url(fresh_seeds: TestClient) -> None:
    a = fresh_seeds.post(
        "/api/seeds",
        json={"school": "A", "department": None, "seed_url": "https://a.example.com"},
    ).json()
    fresh_seeds.post(
        "/api/seeds",
        json={"school": "B", "department": None, "seed_url": "https://b.example.com"},
    )

    # Try to update A's URL to B's existing URL → 409
    resp = fresh_seeds.put(
        f"/api/seeds/{a['id']}",
        json={"school": "A", "department": None, "seed_url": "https://b.example.com"},
    )
    assert resp.status_code == 409


# --- Delete ------------------------------------------------------------------


def test_delete_returns_204(fresh_seeds: TestClient) -> None:
    """Scenario: Hard delete."""
    created = fresh_seeds.post(
        "/api/seeds",
        json={"school": "X", "department": None, "seed_url": "https://x.example.com"},
    ).json()
    resp = fresh_seeds.delete(f"/api/seeds/{created['id']}")
    assert resp.status_code == 204
    assert resp.content == b""

    # Subsequent GET returns 404
    follow = fresh_seeds.get(f"/api/seeds/{created['id']}")
    assert follow.status_code == 404


def test_delete_404_on_missing(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.delete("/api/seeds/999999")
    assert resp.status_code == 404


# --- Uniqueness --------------------------------------------------------------


def test_create_rejects_duplicate_seed_url(fresh_seeds: TestClient) -> None:
    body: dict[str, Any] = {
        "school": "X",
        "department": None,
        "seed_url": "https://duplicate.example.com",
    }
    a = fresh_seeds.post("/api/seeds", json=body)
    assert a.status_code == 201

    b = fresh_seeds.post(
        "/api/seeds",
        json={**body, "school": "Y"},  # different school, same URL
    )
    assert b.status_code == 409
    assert b.json()["detail"]["error"] == "seed_url_already_exists"


# --- Trigger -----------------------------------------------------------------


def test_trigger_sets_in_progress_and_schedules_single_seed_run(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[tuple[int, str]] = []
    monkeypatch.setattr(
        seeds_api,
        "_schedule_seed_run",
        lambda seed_id, run_id: scheduled.append((seed_id, str(run_id))),
    )
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": "https://www.sustech.edu.cn/zh/letter/",
        },
    ).json()

    resp = fresh_seeds.post(f"/api/seeds/{created['id']}/trigger")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["seed_id"] == created["id"]
    assert body["status"] == "in_progress"
    assert scheduled == [(created["id"], body["run_id"])]
    assert _seed_status(postgres_data_ready, created["id"]) == ("in_progress", False)
    assert _pipeline_run_status(postgres_data_ready, body["run_id"]) == (
        "roster_crawl",
        "running",
        {
            "source": "admin-console",
            "domain": "professor",
            "action": "single_seed_trigger",
            "seed_id": created["id"],
            "school": "SUSTech",
            "department": None,
            "seed_url": created["seed_url"],
        },
    )


def test_trigger_returns_409_when_seed_already_in_progress(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[tuple[int, str]] = []
    monkeypatch.setattr(
        seeds_api,
        "_schedule_seed_run",
        lambda seed_id, run_id: scheduled.append((seed_id, str(run_id))),
    )
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": "https://faculty.sustech.edu.cn/again",
        },
    ).json()
    _set_seed_status(postgres_data_ready, created["id"], "in_progress")

    resp = fresh_seeds.post(f"/api/seeds/{created['id']}/trigger")

    assert resp.status_code == 409
    assert resp.json() == {"error": "already_in_progress", "seed_id": created["id"]}
    assert scheduled == []


def test_trigger_returns_422_when_adapter_missing(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[tuple[int, str]] = []
    monkeypatch.setattr(
        seeds_api,
        "_schedule_seed_run",
        lambda seed_id, run_id: scheduled.append((seed_id, str(run_id))),
    )
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "New School",
            "department": "New Department",
            "seed_url": "https://new.example.edu/faculty",
        },
    ).json()
    _set_seed_status(postgres_data_ready, created["id"], "adapter_missing")

    resp = fresh_seeds.post(f"/api/seeds/{created['id']}/trigger")

    assert resp.status_code == 422
    assert resp.json() == {
        "error": "adapter_missing",
        "seed_id": created["id"],
        "school": "New School",
        "department": "New Department",
    }
    assert scheduled == []


def test_trigger_accepts_adapter_missing_seed_after_adapter_is_registered(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[tuple[int, str]] = []
    monkeypatch.setattr(
        seeds_api,
        "_schedule_seed_run",
        lambda seed_id, run_id: scheduled.append((seed_id, str(run_id))),
    )
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": "https://www.sustech.edu.cn/zh/letter/",
        },
    ).json()
    _set_seed_status(postgres_data_ready, created["id"], "adapter_missing")

    resp = fresh_seeds.post(f"/api/seeds/{created['id']}/trigger")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["seed_id"] == created["id"]
    assert _seed_status(postgres_data_ready, created["id"]) == ("in_progress", False)
    assert scheduled == [(created["id"], body["run_id"])]


def test_trigger_returns_404_on_missing_seed(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.post("/api/seeds/999999/trigger")
    assert resp.status_code == 404
