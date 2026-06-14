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


def _insert_failed_seed_run(
    dsn: str,
    *,
    seed_id: int,
    failure_class: str,
) -> None:
    with psycopg.connect(_pg_dsn(dsn)) as conn:
        conn.execute(
            """
            INSERT INTO pipeline_run (
                run_kind, run_scope, started_at, finished_at, status,
                triggered_by, error_summary
            )
            VALUES (
                'roster_crawl',
                jsonb_build_object(
                    'source', 'admin-console',
                    'domain', 'professor',
                    'action', 'single_seed_trigger',
                    'seed_id', %s
                ),
                now(),
                now(),
                'failed',
                'test',
                jsonb_build_object('failure_class', %s::text)
            )
            """,
            (seed_id, failure_class),
        )
        conn.commit()


def _capture_scheduled() -> tuple[list[dict[str, Any]], Any]:
    scheduled: list[dict[str, Any]] = []

    def schedule_seed_run(**kwargs: Any) -> None:
        scheduled.append(
            {
                **kwargs,
                "run_id": str(kwargs["run_id"]),
            }
        )

    return scheduled, schedule_seed_run


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


def test_list_seeds_surfaces_latest_failure_class(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
) -> None:
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": "https://faculty.sustech.edu.cn/failure-class",
        },
    ).json()
    _set_seed_status(postgres_data_ready, created["id"], "success")
    _insert_failed_seed_run(
        postgres_data_ready,
        seed_id=created["id"],
        failure_class="fetch_blocked",
    )

    resp = fresh_seeds.get("/api/seeds")

    assert resp.status_code == 200, resp.text
    row = next(seed for seed in resp.json() if seed["id"] == created["id"])
    assert row["failure_class"] == "fetch_blocked"


def test_list_seeds_allows_manual_interruption_failure_class(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
) -> None:
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SZU",
            "department": "计算机与软件学院",
            "seed_url": "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
        },
    ).json()
    _set_seed_status(postgres_data_ready, created["id"], "success")
    _insert_failed_seed_run(
        postgres_data_ready,
        seed_id=created["id"],
        failure_class="manual_interruption",
    )

    resp = fresh_seeds.get("/api/seeds")
    single = fresh_seeds.get(f"/api/seeds/{created['id']}")

    assert resp.status_code == 200, resp.text
    assert single.status_code == 200, single.text
    row = next(seed for seed in resp.json() if seed["id"] == created["id"])
    assert row["last_run_status"] == "failure"
    assert row["failure_class"] == "manual_interruption"
    assert single.json()["last_run_status"] == "failure"
    assert single.json()["failure_class"] == "manual_interruption"


# --- Trigger -----------------------------------------------------------------


def test_trigger_sets_in_progress_and_schedules_single_seed_run(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
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
    assert scheduled == [
        {
            "seed_id": created["id"],
            "run_id": body["run_id"],
            "trigger_mode": "full",
            "limit": None,
        }
    ]
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
            "trigger_mode": "full",
            "limit": None,
        },
    )


def test_trigger_sample_records_limit_and_schedules_bounded_run(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": "https://faculty.sustech.edu.cn/sample",
        },
    ).json()

    resp = fresh_seeds.post(
        f"/api/seeds/{created['id']}/trigger",
        json={"mode": "sample", "limit": 3},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert scheduled == [
        {
            "seed_id": created["id"],
            "run_id": body["run_id"],
            "trigger_mode": "sample",
            "limit": 3,
        }
    ]
    assert _pipeline_run_status(postgres_data_ready, body["run_id"])[2] == {
        "source": "admin-console",
        "domain": "professor",
        "action": "single_seed_trigger",
        "seed_id": created["id"],
        "school": "SUSTech",
        "department": None,
        "seed_url": created["seed_url"],
        "trigger_mode": "sample",
        "limit": 3,
    }


def test_trigger_preview_schedules_non_writing_run(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": "https://faculty.sustech.edu.cn/preview",
        },
    ).json()

    resp = fresh_seeds.post(
        f"/api/seeds/{created['id']}/trigger",
        json={"mode": "preview"},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert scheduled == [
        {
            "seed_id": created["id"],
            "run_id": body["run_id"],
            "trigger_mode": "preview",
            "limit": None,
        }
    ]
    assert _pipeline_run_status(postgres_data_ready, body["run_id"])[2][
        "trigger_mode"
    ] == "preview"


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "sample"},
        {"mode": "sample", "limit": 0},
        {"mode": "sample", "limit": -1},
        {"mode": "sample", "limit": 1001},
    ],
)
def test_trigger_rejects_invalid_sample_limits(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
    created = fresh_seeds.post(
        "/api/seeds",
        json={
            "school": "SUSTech",
            "department": None,
            "seed_url": f"https://faculty.sustech.edu.cn/invalid-{payload.get('limit', 'missing')}",
        },
    ).json()

    resp = fresh_seeds.post(f"/api/seeds/{created['id']}/trigger", json=payload)

    assert resp.status_code == 422
    assert scheduled == []
    assert _seed_status(postgres_data_ready, created["id"]) == ("never_run", False)


def test_trigger_returns_409_when_seed_already_in_progress(
    fresh_seeds: TestClient,
    postgres_data_ready: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
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
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
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
    scheduled, schedule_seed_run = _capture_scheduled()
    monkeypatch.setattr(seeds_api, "_schedule_seed_run", schedule_seed_run)
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
    assert scheduled == [
        {
            "seed_id": created["id"],
            "run_id": body["run_id"],
            "trigger_mode": "full",
            "limit": None,
        }
    ]


def test_trigger_returns_404_on_missing_seed(fresh_seeds: TestClient) -> None:
    resp = fresh_seeds.post("/api/seeds/999999/trigger")
    assert resp.status_code == 404
