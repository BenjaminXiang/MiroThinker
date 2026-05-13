from __future__ import annotations

from typing import Any

import psycopg

from src.data_agents.professor.discovery import (
    DiscoverySourceStatus,
)
from src.data_agents.professor.models import (
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
)
from src.data_agents.professor.pipeline import (
    ProfessorPipelineReport,
    ProfessorPipelineResult,
)
from src.data_agents.professor.seed_runner import run_single_seed_with_conn
from src.data_agents.storage.postgres.pipeline_run import open_pipeline_run


def _insert_seed(
    conn: psycopg.Connection,
    *,
    school: str = "SUSTech",
    department: str | None = None,
    seed_url: str = "https://faculty.sustech.edu.cn",
    status: str = "never_run",
) -> int:
    row = conn.execute(
        """
        INSERT INTO professor_seed (school, department, seed_url, last_run_status)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (school, department, seed_url, status),
    ).fetchone()
    return int(row[0])


def _seed_row(conn: psycopg.Connection, seed_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT last_run_status, last_run_at
          FROM professor_seed
         WHERE id = %s
        """,
        (seed_id,),
    ).fetchone()
    assert row is not None
    return {"last_run_status": row[0], "last_run_at": row[1]}


def _pipeline_run_row(conn: psycopg.Connection, run_id: Any) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT status, items_processed, items_failed, error_summary
          FROM pipeline_run
         WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    assert row is not None
    return {
        "status": row[0],
        "items_processed": row[1],
        "items_failed": row[2],
        "error_summary": row[3],
    }


def _issue_rows(conn: psycopg.Connection) -> list[tuple[str, str, dict[str, Any] | None]]:
    return conn.execute(
        """
        SELECT stage, description, evidence_snapshot
          FROM pipeline_issue
         WHERE reported_by = 'professor_seed_runner'
         ORDER BY reported_at ASC
        """
    ).fetchall()


def _profile(**overrides: Any) -> MergedProfessorProfileRecord:
    defaults = dict(
        name="李华",
        institution="SUSTech",
        department="CSE",
        title="教授",
        email=None,
        office=None,
        homepage="https://faculty.sustech.edu.cn/lihua",
        profile_url="https://faculty.sustech.edu.cn/lihua",
        source_urls=("https://faculty.sustech.edu.cn",),
        evidence=("https://faculty.sustech.edu.cn/lihua",),
        research_directions=("AI",),
        extraction_status="structured",
        skip_reason=None,
        error=None,
        roster_source="https://faculty.sustech.edu.cn",
    )
    defaults.update(overrides)
    return MergedProfessorProfileRecord(**defaults)


def _pipeline_result(
    *,
    seed: ProfessorRosterSeed,
    profiles: list[MergedProfessorProfileRecord],
    status: str = "resolved",
    reason: str = "fixture",
    error: str | None = None,
) -> ProfessorPipelineResult:
    report = ProfessorPipelineReport(
        seed_url_count=1,
        discovered_professor_count=len(profiles),
        unique_professor_count=len(profiles),
        duplicate_professor_count=0,
        failed_roster_fetch_count=1 if status == "failed" else 0,
        unresolved_seed_source_count=1 if status != "resolved" else 0,
        official_profile_candidate_count=len(profiles),
        profile_fetch_success_count=len(profiles),
        profile_fetch_failed_count=0,
        skipped_external_profile_count=0,
        structured_profile_count=len(profiles),
        partial_profile_count=0,
    )
    return ProfessorPipelineResult(
        profiles=profiles,
        source_statuses=[
            DiscoverySourceStatus(
                seed_url=seed.roster_url,
                institution=seed.institution or "UNKNOWN",
                department=seed.department,
                status=status,
                reason=reason,
                error=error,
                visited_urls=[seed.roster_url],
                discovered_professor_count=len(profiles),
            )
        ],
        failed_fetch_urls=[seed.roster_url] if status == "failed" else [],
        report=report,
    )


def test_run_single_seed_marks_adapter_missing_without_running_pipeline(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="New School",
        seed_url="https://new.example.edu/faculty",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )
    called = False

    def pipeline_runner(seed: ProfessorRosterSeed, timeout: float) -> ProfessorPipelineResult:
        nonlocal called
        called = True
        raise AssertionError(f"pipeline must not run for {seed} / {timeout}")

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: None,
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert called is False
    assert result.status == "adapter_missing"
    assert result.items_processed == 0
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "adapter_missing"
    assert _seed_row(pg_conn, seed_id)["last_run_at"] is not None
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "failed"
    issues = _issue_rows(pg_conn)
    assert len(issues) == 1
    assert issues[0][0] == "adapter_missing"
    assert issues[0][2]["seed_id"] == seed_id


def test_run_single_seed_deduplicates_repeated_open_adapter_missing_issue(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="New School",
        seed_url="https://new.example.edu/faculty",
    )
    first_run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "attempt": 1},
        triggered_by="test",
    )
    second_run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "attempt": 2},
        triggered_by="test",
    )

    first = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=first_run_id,
        adapter_resolver=lambda _seed: None,
        pipeline_runner=lambda *_args, **_kwargs: None,
        profile_writer=lambda *_args, **_kwargs: None,
    )
    second = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=second_run_id,
        adapter_resolver=lambda _seed: None,
        pipeline_runner=lambda *_args, **_kwargs: None,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert first.status == "adapter_missing"
    assert second.status == "adapter_missing"
    assert _pipeline_run_row(pg_conn, first_run_id)["status"] == "failed"
    assert _pipeline_run_row(pg_conn, second_run_id)["status"] == "failed"
    issues = _issue_rows(pg_conn)
    assert len(issues) == 1
    assert issues[0][0] == "adapter_missing"


def test_run_single_seed_writes_success_status_after_supported_pipeline(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(pg_conn)
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )
    written: list[MergedProfessorProfileRecord] = []

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        profile = _profile(
            institution=seed.institution,
            department=seed.department,
            roster_source=seed.roster_url,
        )
        return _pipeline_result(seed=seed, profiles=[profile])

    def profile_writer(
        _conn: psycopg.Connection,
        *,
        profile: MergedProfessorProfileRecord,
        run_id: Any,
    ) -> None:
        assert str(run_id)
        written.append(profile)

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: "sustech-roster",
        pipeline_runner=pipeline_runner,
        profile_writer=profile_writer,
    )

    assert result.status == "success"
    assert result.items_processed == 1
    assert [p.name for p in written] == ["李华"]
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "success"
    assert _seed_row(pg_conn, seed_id)["last_run_at"] is not None
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "succeeded"
    assert _issue_rows(pg_conn) == []


def test_run_single_seed_marks_failed_discovery_as_failure(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="SZU",
        department="计算机与软件学院",
        seed_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(
            seed=seed,
            profiles=[],
            status="failed",
            reason="fetch_failed",
            error="HTTP 412 JS challenge",
        )

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: "szu-teacher-family",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert result.status == "failure"
    assert result.items_failed == 1
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "failure"
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "failed"
    issues = _issue_rows(pg_conn)
    assert len(issues) == 1
    assert issues[0][0] == "discovery"
    assert "fetch_failed" in issues[0][1]
