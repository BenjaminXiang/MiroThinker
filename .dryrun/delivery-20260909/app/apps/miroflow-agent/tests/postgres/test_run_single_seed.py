from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from src.data_agents.professor import seed_runner as seed_runner_module
from src.data_agents.professor.discovery import (
    DiscoverySourceStatus,
)
from src.data_agents.professor.models import (
    EducationEntry,
    EnrichedProfessorProfile,
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
    WorkEntry,
)
from src.data_agents.professor.cross_domain import PaperLink, PaperStagingRecord
from src.data_agents.professor.publish_helpers import build_professor_id
from src.data_agents.professor.pipeline import (
    ProfessorPipelineReport,
    ProfessorPipelineResult,
)
from src.data_agents.professor.parser import parse_roster_seed_markdown
from src.data_agents.professor.seed_runner import (
    _default_pipeline_runner,
    _merged_to_enriched,
    run_single_seed,
    run_single_seed_with_conn,
)
from src.data_agents.storage.postgres.pipeline_run import open_pipeline_run


def _insert_seed(
    conn: psycopg.Connection,
    *,
    school: str = "SUSTech",
    department: str | None = None,
    seed_url: str | None = None,
    status: str = "never_run",
) -> int:
    seed_url = seed_url or f"https://faculty.sustech.edu.cn/{uuid4()}"
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
        SELECT status, items_processed, items_failed, error_summary, run_scope
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
        "run_scope": row[4],
    }


def _issue_rows(
    conn: psycopg.Connection,
    *,
    seed_id: int | None = None,
) -> list[tuple[str, str, dict[str, Any] | None]]:
    params: tuple[Any, ...] = ()
    seed_filter = ""
    if seed_id is not None:
        seed_filter = "AND evidence_snapshot->>'seed_id' = %s"
        params = (str(seed_id),)
    return conn.execute(
        f"""
        SELECT stage, description, evidence_snapshot
          FROM pipeline_issue
         WHERE reported_by = 'professor_seed_runner'
           {seed_filter}
         ORDER BY reported_at ASC
        """,
        params,
    ).fetchall()


def _scalar(conn: psycopg.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return row[0]


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


def _paper_staging(
    *,
    professor_id: str,
    professor_name: str = "李华",
) -> PaperStagingRecord:
    return PaperStagingRecord(
        title="Official Personal Homepage Paper",
        authors=[professor_name, "Alice Zhang"],
        year=2025,
        venue="NeurIPS",
        source_url="https://lihua.example.com/publications",
        source="official_publication_page",
        anchoring_professor_id=professor_id,
        anchoring_professor_name=professor_name,
        anchoring_institution="SUSTech",
    )


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


def test_default_pipeline_runner_temp_markdown_preserves_uestc_seed_context(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}
    seed = ProfessorRosterSeed(
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        roster_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404",
    )

    def fake_run_professor_pipeline(seed_doc: Any, **kwargs: Any) -> ProfessorPipelineResult:
        markdown = seed_doc.read_text(encoding="utf-8")
        captured["markdown"] = markdown
        captured["kwargs"] = kwargs
        return _pipeline_result(seed=seed, profiles=[])

    monkeypatch.setattr(
        seed_runner_module,
        "run_professor_pipeline",
        fake_run_professor_pipeline,
    )

    _default_pipeline_runner(seed, timeout=12.0)

    parsed = parse_roster_seed_markdown(captured["markdown"])
    assert parsed == [seed]
    assert "| 电子科技大学（深圳）高等研究院" not in captured["markdown"]


def test_default_pipeline_runner_temp_markdown_roundtrips_szu_csse_context(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )

    def fake_run_professor_pipeline(seed_doc: Any, **kwargs: Any) -> ProfessorPipelineResult:
        markdown = seed_doc.read_text(encoding="utf-8")
        captured["markdown"] = markdown
        captured["kwargs"] = kwargs
        return _pipeline_result(seed=seed, profiles=[])

    monkeypatch.setattr(
        seed_runner_module,
        "run_professor_pipeline",
        fake_run_professor_pipeline,
    )

    _default_pipeline_runner(seed, timeout=12.0)

    assert parse_roster_seed_markdown(captured["markdown"]) == [seed]
    assert captured["kwargs"]["skip_profile_fetch"] is False


def test_merged_to_enriched_builds_deterministic_profile_summary() -> None:
    profile = _profile(
        name="Ahmed Elazab",
        institution="清华大学深圳国际研究生院",
        title="助理教授，博士生导师",
        research_directions=("medical image analysis", "explainable AI"),
        education_structured=(
            EducationEntry(
                school="University of Chinese Academy of Sciences",
                degree="PhD",
                field="Pattern Recognition",
                start_year=2012,
                end_year=2017,
            ),
        ),
        work_experience=(
            WorkEntry(
                organization="Tsinghua SIGS",
                role="Assistant Professor",
                start_year=2025,
            ),
        ),
        awards=("Best paper award",),
        profile_raw_text=(
            "Ahmed Elazab is an assistant professor. His research focuses on "
            "trustworthy artificial intelligence for medical image analysis."
        ),
    )

    enriched = _merged_to_enriched(profile)

    assert len(enriched.profile_summary) >= 150
    assert "medical image analysis" in enriched.profile_summary
    assert "Best paper award" in enriched.profile_summary


def test_default_profile_writer_applies_llm_homepage_enrichment_before_write(
    pg_conn: psycopg.Connection,
    monkeypatch,
) -> None:
    profile = _profile(
        name="李华",
        homepage="https://faculty.sustech.edu.cn/lihua",
        profile_url="https://faculty.sustech.edu.cn/lihua",
        profile_raw_text="官网简介：李华研究机器学习。",
    )
    professor_id = build_professor_id(seed_runner_module._merged_to_enriched(profile))
    raw_text = (
        "官网简介：李华研究机器学习。\n\n"
        "Source: https://lihua.example.com\n"
        "李华个人维护主页：研究联邦学习与自适应量化。\n\n"
        "Source: https://lihua.example.com/publications\n"
        "Official Personal Homepage Paper"
    )

    def fake_enrich(
        merged: MergedProfessorProfileRecord,
        *,
        run_id: Any,
        timeout: float | None = None,
    ) -> tuple[EnrichedProfessorProfile, list[PaperStagingRecord]]:
        assert str(run_id)
        del timeout
        enriched = seed_runner_module._merged_to_enriched(merged).model_copy(
            update={
                "profile_raw_text": raw_text,
                "publication_evidence_urls": [
                    "https://lihua.example.com/publications"
                ],
                "official_top_papers": [
                    PaperLink(
                        title="Official Personal Homepage Paper",
                        year=2025,
                        venue="NeurIPS",
                        source="official_site",
                    )
                ],
            }
        )
        return enriched, [_paper_staging(professor_id=professor_id)]

    monkeypatch.setattr(
        seed_runner_module,
        "_enrich_profile_for_seed_write",
        fake_enrich,
        raising=False,
    )

    seed_runner_module._default_profile_writer(
        pg_conn,
        profile=profile,
        run_id="00000000-0000-0000-0000-000000000001",
    )

    assert (
        _scalar(
            pg_conn,
            "SELECT profile_raw_text FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == raw_text
    )
    assert (
        _scalar(
            pg_conn,
            "SELECT count(*) FROM paper WHERE title_clean = %s",
            ("Official Personal Homepage Paper",),
        )
        == 1
    )
    assert (
        _scalar(
            pg_conn,
            """
            SELECT ppl.evidence_source_type
              FROM professor_paper_link ppl
              JOIN paper p ON p.paper_id = ppl.paper_id
             WHERE ppl.professor_id = %s
               AND p.title_clean = %s
            """,
            (professor_id, "Official Personal Homepage Paper"),
        )
        == "official_publication_page"
    )


def test_default_profile_writer_passes_enriched_profile_and_staging_to_writer(
    monkeypatch,
) -> None:
    profile = _profile(
        name="李华",
        profile_raw_text="官网简介：李华研究机器学习。",
    )
    base_enriched = seed_runner_module._merged_to_enriched(profile)
    professor_id = build_professor_id(base_enriched)
    raw_text = (
        "官网简介：李华研究机器学习。\n\n"
        "Source: https://lihua.example.com\n"
        "李华个人维护主页：研究联邦学习与自适应量化。"
    )
    staging = [_paper_staging(professor_id=professor_id)]
    seen: dict[str, Any] = {}

    def fake_enrich(
        merged: MergedProfessorProfileRecord,
        *,
        run_id: Any,
        timeout: float | None = None,
    ) -> tuple[EnrichedProfessorProfile, list[PaperStagingRecord]]:
        del run_id, timeout
        return seed_runner_module._merged_to_enriched(merged).model_copy(
            update={"profile_raw_text": raw_text}
        ), staging

    def fake_upsert_source_page_for_url(*_args: Any, **_kwargs: Any) -> UUID:
        return UUID("00000000-0000-0000-0000-000000000002")

    def fake_write_professor_bundle(
        _conn: Any,
        *,
        enriched: EnrichedProfessorProfile,
        paper_staging: list[PaperStagingRecord] | None,
        official_profile_page_id: UUID,
        run_id: Any,
    ) -> None:
        seen.update(
            {
                "enriched": enriched,
                "paper_staging": paper_staging,
                "official_profile_page_id": official_profile_page_id,
                "run_id": run_id,
            }
        )

    monkeypatch.setattr(
        seed_runner_module,
        "_enrich_profile_for_seed_write",
        fake_enrich,
    )
    monkeypatch.setattr(
        seed_runner_module,
        "upsert_source_page_for_url",
        fake_upsert_source_page_for_url,
    )
    monkeypatch.setattr(
        seed_runner_module,
        "write_professor_bundle",
        fake_write_professor_bundle,
    )

    seed_runner_module._default_profile_writer(
        object(),
        profile=profile,
        run_id="00000000-0000-0000-0000-000000000001",
    )

    assert seen["enriched"].profile_raw_text == raw_text
    assert seen["paper_staging"] == staging
    assert seen["official_profile_page_id"] == UUID(
        "00000000-0000-0000-0000-000000000002"
    )
    assert seen["run_id"] == "00000000-0000-0000-0000-000000000001"


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
    assert result.failure_class == "adapter_missing"
    assert result.items_processed == 0
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "adapter_missing"
    assert _seed_row(pg_conn, seed_id)["last_run_at"] is not None
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "failed"
    issues = _issue_rows(pg_conn, seed_id=seed_id)
    assert len(issues) == 1
    assert issues[0][0] == "adapter_missing"
    assert issues[0][2]["seed_id"] == seed_id
    assert issues[0][2]["failure_class"] == "adapter_missing"
    assert _pipeline_run_row(pg_conn, run_id)["error_summary"]["failure_class"] == (
        "adapter_missing"
    )


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
    issues = _issue_rows(pg_conn, seed_id=seed_id)
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
    assert result.failure_class == "success"
    assert result.items_processed == 1
    assert [p.name for p in written] == ["李华"]
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "success"
    assert _seed_row(pg_conn, seed_id)["last_run_at"] is not None
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "succeeded"
    assert _issue_rows(pg_conn, seed_id=seed_id) == []


def test_run_single_seed_sample_writes_at_most_limit(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(pg_conn)
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "trigger_mode": "sample", "limit": 3},
        triggered_by="test",
    )
    written: list[str] = []

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(
            seed=seed,
            profiles=[
                _profile(name=f"教师{i}", profile_url=f"https://faculty.sustech.edu.cn/{i}")
                for i in range(5)
            ],
        )

    def profile_writer(
        _conn: psycopg.Connection,
        *,
        profile: MergedProfessorProfileRecord,
        run_id: Any,
    ) -> None:
        assert str(run_id)
        written.append(profile.name)

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        trigger_mode="sample",
        limit=3,
        adapter_resolver=lambda _seed: "sustech-roster",
        pipeline_runner=pipeline_runner,
        profile_writer=profile_writer,
    )

    assert result.status == "success"
    assert result.failure_class == "success"
    assert result.items_processed == 3
    assert written == ["教师0", "教师1", "教师2"]
    assert _pipeline_run_row(pg_conn, run_id)["items_processed"] == 3
    assert _issue_rows(pg_conn, seed_id=seed_id) == []


def test_run_single_seed_sample_budgets_default_writer_enrichment(
    pg_conn: psycopg.Connection,
    monkeypatch,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="深圳大学",
        department="计算机与软件学院",
        seed_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "trigger_mode": "sample", "limit": 3},
        triggered_by="test",
    )
    observed_budgets: list[float] = []

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(
            seed=seed,
            profiles=[
                _profile(
                    name=f"教师{i}",
                    institution="深圳大学",
                    department="计算机与软件学院",
                    profile_url=f"https://csse.szu.edu.cn/pages/user/index?id={600 + i}",
                    homepage=f"https://csse.szu.edu.cn/pages/user/index?id={600 + i}",
                    roster_source=seed.roster_url,
                    evidence=(
                        seed.roster_url,
                        f"https://csse.szu.edu.cn/pages/user/index?id={600 + i}",
                    ),
                    source_urls=(seed.roster_url,),
                )
                for i in range(3)
            ],
        )

    def fake_default_writer(
        _conn: psycopg.Connection,
        *,
        profile: MergedProfessorProfileRecord,
        run_id: Any,
        enrichment_timeout: float,
    ) -> None:
        assert str(run_id)
        assert profile.name.startswith("教师")
        observed_budgets.append(enrichment_timeout)

    monkeypatch.setattr(
        seed_runner_module,
        "_attach_szu_csse_official_supplement_sources",
        lambda _seed, profiles, *, timeout: profiles,
    )
    monkeypatch.setattr(seed_runner_module, "_default_profile_writer", fake_default_writer)

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        timeout=9.0,
        trigger_mode="sample",
        limit=3,
        adapter_resolver=lambda _seed: "szu-csse-teacher-team",
        pipeline_runner=pipeline_runner,
    )

    assert result.status == "success"
    assert observed_budgets == pytest.approx([3.0, 3.0, 3.0], abs=0.25)
    assert _pipeline_run_row(pg_conn, run_id)["items_processed"] == 3


def test_run_single_seed_preview_runs_diagnostics_without_writes(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(pg_conn)
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "trigger_mode": "preview"},
        triggered_by="test",
    )

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(seed=seed, profiles=[_profile(), _profile(name="王明")])

    def profile_writer(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("preview mode must not write canonical professor rows")

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        trigger_mode="preview",
        adapter_resolver=lambda _seed: "sustech-roster",
        pipeline_runner=pipeline_runner,
        profile_writer=profile_writer,
    )

    assert result.status == "success"
    assert result.failure_class == "success"
    assert result.items_processed == 0
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "success"
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "succeeded"
    assert _pipeline_run_row(pg_conn, run_id)["items_processed"] == 0
    assert _issue_rows(pg_conn, seed_id=seed_id) == []


def test_run_single_seed_opened_run_records_mode_and_limit(
    pg_dsn: str,
) -> None:
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("BEGIN")
        seed_id = _insert_seed(conn)
        conn.commit()

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(seed=seed, profiles=[_profile()])

    result = run_single_seed(
        seed_id,
        dsn=pg_dsn,
        trigger_mode="sample",
        limit=1,
        adapter_resolver=lambda _seed: "sustech-roster",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    with psycopg.connect(pg_dsn) as conn:
        row = _pipeline_run_row(conn, result.run_id)
        conn.execute("DELETE FROM professor_seed WHERE id=%s", (seed_id,))
        conn.commit()

    assert row["run_scope"]["trigger_mode"] == "sample"
    assert row["run_scope"]["limit"] == 1


def test_run_single_seed_marks_failed_discovery_as_failure(
    pg_conn: psycopg.Connection,
    monkeypatch,
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

    monkeypatch.setattr(
        seed_runner_module,
        "_collect_szu_csse_official_supplement_profiles",
        lambda _seed, *, timeout: [],
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
    assert result.failure_class == "fetch_blocked"
    assert result.items_failed == 1
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "failure"
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "failed"
    issues = _issue_rows(pg_conn, seed_id=seed_id)
    assert len(issues) == 1
    assert issues[0][0] == "discovery"
    assert "fetch_failed" in issues[0][1]
    assert issues[0][2]["failure_class"] == "fetch_blocked"
    assert _pipeline_run_row(pg_conn, run_id)["error_summary"]["failure_class"] == (
        "fetch_blocked"
    )


def test_run_single_seed_rejects_szu_csse_out_of_scope_profiles(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="深圳大学",
        department="计算机与软件学院",
        seed_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )
    writer_calls: list[MergedProfessorProfileRecord] = []

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(
            seed=seed,
            profiles=[
                _profile(
                    name="文化建设",
                    institution="深圳大学",
                    department="计算机与软件学院",
                    homepage="https://aisc.szu.edu.cn/info/1054/1408.htm",
                    profile_url="https://aisc.szu.edu.cn/info/1054/1408.htm",
                    roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
                    evidence=("https://aisc.szu.edu.cn/info/1054/1408.htm",),
                    source_urls=("https://aisc.szu.edu.cn/AISC/Faculty.htm",),
                )
            ],
        )

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: "szu-teacher-family",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda _conn, *, profile, run_id: writer_calls.append(profile),
    )

    assert writer_calls == []
    assert result.status == "failure"
    assert result.failure_class == "parser_low_quality"
    assert "out-of-scope" in (result.error or "")
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "failure"
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "failed"
    assert _pipeline_run_row(pg_conn, run_id)["items_processed"] == 0
    issues = _issue_rows(pg_conn, seed_id=seed_id)
    assert len(issues) == 1
    evidence = issues[0][2]
    assert evidence["failure_class"] == "parser_low_quality"
    assert evidence["rejected_profile_urls"] == [
        "https://aisc.szu.edu.cn/info/1054/1408.htm"
    ]


def test_run_single_seed_writes_scoped_roster_only_profile_when_detail_fetch_fails(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="深圳大学",
        department="计算机与软件学院",
        seed_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )
    writer_calls: list[MergedProfessorProfileRecord] = []

    def pipeline_runner(seed: ProfessorRosterSeed, _timeout: float) -> ProfessorPipelineResult:
        return _pipeline_result(
            seed=seed,
            profiles=[
                _profile(
                    name="陈国良",
                    institution="深圳大学",
                    department="计算机与软件学院",
                    title=None,
                    homepage=None,
                    profile_url="https://csse.szu.edu.cn/pages/user/index?id=617",
                    roster_source="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
                    evidence=(
                        "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
                        "https://csse.szu.edu.cn/pages/user/index?id=617",
                    ),
                    source_urls=(
                        "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
                        "https://csse.szu.edu.cn/pages/user/index?id=617",
                    ),
                    research_directions=(),
                    extraction_status="failed",
                    error="RuntimeError: browser returned empty page",
                )
            ],
        )

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: "szu-csse-teacher-team",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda _conn, *, profile, run_id: writer_calls.append(profile),
    )

    assert result.status == "success"
    assert result.failure_class == "success"
    assert result.items_processed == 1
    assert [profile.name for profile in writer_calls] == ["陈国良"]
    assert writer_calls[0].extraction_status == "failed"
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "success"
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "succeeded"
    assert _issue_rows(pg_conn, seed_id=seed_id) == []


def test_szu_csse_seed_profile_scope_rejects_research_center_false_positive() -> None:
    seed = ProfessorRosterSeed(
        institution="深圳大学",
        department="计算机与软件学院",
        roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
    )

    assert (
        seed_runner_module._profile_matches_seed_scope(
            seed,
            _profile(
                name="文化建设",
                profile_url="https://aisc.szu.edu.cn/info/1054/1408.htm",
                roster_source="https://aisc.szu.edu.cn/AISC/Faculty.htm",
                evidence=("https://aisc.szu.edu.cn/info/1054/1408.htm",),
            ),
        )
        is False
    )
    assert (
        seed_runner_module._profile_matches_seed_scope(
            seed,
            _profile(
                name="张三",
                profile_url="https://csse.szu.edu.cn/pages/user/index?id=123",
                roster_source="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
                evidence=("https://csse.szu.edu.cn/pages/user/index?id=123",),
            ),
        )
        is True
    )
    assert (
        seed_runner_module._profile_matches_seed_scope(
            seed,
            _profile(
                name="赵六",
                profile_url="https://csse.szu.edu.cn/info/1010/3001.htm",
                roster_source="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
                evidence=("https://csse.szu.edu.cn/info/1010/3001.htm",),
            ),
        )
        is False
    )


def test_run_single_seed_classifies_parser_low_quality(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(pg_conn)
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: "sustech-roster",
        pipeline_runner=lambda seed, _timeout: _pipeline_result(
            seed=seed,
            profiles=[],
            status="resolved",
            reason="parser_empty",
        ),
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert result.status == "failure"
    assert result.failure_class == "parser_low_quality"
    issues = _issue_rows(pg_conn, seed_id=seed_id)
    assert len(issues) == 1
    assert issues[0][2]["failure_class"] == "parser_low_quality"


def test_run_single_seed_classifies_pipeline_exception(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(pg_conn)
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id},
        triggered_by="test",
    )

    def pipeline_runner(
        _seed: ProfessorRosterSeed,
        _timeout: float,
    ) -> ProfessorPipelineResult:
        raise RuntimeError("boom")

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        adapter_resolver=lambda _seed: "sustech-roster",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert result.status == "failure"
    assert result.failure_class == "pipeline_exception"
    issues = _issue_rows(pg_conn, seed_id=seed_id)
    assert len(issues) == 1
    assert issues[0][2]["failure_class"] == "pipeline_exception"


def test_sias_tokenized_202_page_builds_fetch_blocked_evidence() -> None:
    seed = ProfessorRosterSeed(
        institution="电子科技大学（深圳）高等研究院",
        department="电子信息",
        roster_url="https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm",
    )

    evidence = seed_runner_module._build_sias_fetch_blocked_evidence(
        seed,
        http_status=202,
        response_body=(
            "<!doctype html><html><head><script>"
            "window.$_ts={token:'abc'};"
            "</script></head><body></body></html>"
        ),
        fetch_method="direct_no_env",
        browser_diagnostic="net::ERR_CONNECTION_CLOSED",
    )

    assert evidence == {
        "failure_class": "fetch_blocked",
        "fetch_method": "direct_no_env",
        "http_status": 202,
        "response_char_count": 97,
        "response_chinese_char_count": 0,
        "response_anchor_count": 0,
        "response_shape": "tokenized_202_challenge",
        "browser_diagnostic": "net::ERR_CONNECTION_CLOSED",
    }


def test_run_single_seed_persists_fetch_blocked_for_uestc_sias_challenge(
    pg_conn: psycopg.Connection,
    monkeypatch,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="电子科技大学（深圳）高等研究院",
        department="电子信息",
        seed_url="https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "trigger_mode": "preview"},
        triggered_by="test",
    )
    monkeypatch.setattr(
        seed_runner_module,
        "_detect_known_fetch_blocked_seed",
        lambda seed, timeout: {
            "failure_class": "fetch_blocked",
            "fetch_method": "direct_no_env",
            "http_status": 202,
            "response_char_count": 93,
            "response_chinese_char_count": 0,
            "response_anchor_count": 0,
            "response_shape": "tokenized_202_challenge",
        },
    )

    pipeline_called = False

    def pipeline_runner(seed: ProfessorRosterSeed, timeout: float) -> ProfessorPipelineResult:
        nonlocal pipeline_called
        pipeline_called = True
        raise AssertionError(f"pipeline must not run for blocked seed {seed} / {timeout}")

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        trigger_mode="preview",
        adapter_resolver=lambda _seed: None,
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert pipeline_called is False
    assert result.status == "failure"
    assert result.failure_class == "fetch_blocked"
    assert result.error == "fetch_blocked: tokenized_202_challenge"
    assert _seed_row(pg_conn, seed_id)["last_run_status"] == "failure"
    assert _pipeline_run_row(pg_conn, run_id)["status"] == "failed"
    assert _pipeline_run_row(pg_conn, run_id)["error_summary"]["failure_class"] == "fetch_blocked"
    issues = _issue_rows(pg_conn, seed_id=seed_id)
    assert len(issues) == 1
    assert issues[0][0] == "discovery"
    evidence = issues[0][2]
    assert evidence["failure_class"] == "fetch_blocked"
    assert evidence["seed_id"] == seed_id
    assert evidence["school"] == "电子科技大学（深圳）高等研究院"
    assert evidence["department"] == "电子信息"
    assert evidence["seed_url"] == "https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm"
    assert evidence["trigger_mode"] == "preview"
    assert evidence["fetch_method"] == "direct_no_env"
    assert evidence["http_status"] == 202
    assert evidence["response_char_count"] == 93
    assert evidence["response_chinese_char_count"] == 0
    assert evidence["response_anchor_count"] == 0
    assert evidence["response_shape"] == "tokenized_202_challenge"


def test_resolves_uestc_sias_seed_to_official_yjsjy_replacement() -> None:
    cases = [
        (
            "电子信息",
            "https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm",
            "085400",
        ),
        (
            "计算机技术",
            "https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm",
            "085404",
        ),
        (
            "软件工程",
            "https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm",
            "085405",
        ),
        (
            "机械",
            "https://sias.uestc.edu.cn/rcpy/dsjs1/jx/gyhlwyznzz.htm",
            "085500",
        ),
    ]

    for department, roster_url, program_code in cases:
        seed = ProfessorRosterSeed(
            institution="电子科技大学（深圳）高等研究院",
            department=department,
            roster_url=roster_url,
        )

        replacement = seed_runner_module.resolve_uestc_yjsjy_replacement_seed(seed)

        assert replacement == ProfessorRosterSeed(
            institution="电子科技大学（深圳）高等研究院",
            department=department,
            roster_url=(
                "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc"
                f"?yxsh=28&zydm={program_code}"
            ),
        )


def test_resolves_uestc_sias_seed_to_official_yjsjy_replacement_by_department() -> None:
    cases = [
        ("电子信息", "085400"),
        ("计算机技术", "085404"),
        ("软件工程", "085405"),
        ("机械", "085500"),
    ]

    for department, program_code in cases:
        seed = ProfessorRosterSeed(
            institution="电子科技大学（深圳）高等研究院",
            department=department,
            roster_url="https://sias.uestc.edu.cn/rcpy/dsjs1/unknown.htm",
        )

        replacement = seed_runner_module.resolve_uestc_yjsjy_replacement_seed(seed)

        assert replacement == ProfessorRosterSeed(
            institution="电子科技大学（深圳）高等研究院",
            department=department,
            roster_url=(
                "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc"
                f"?yxsh=28&zydm={program_code}"
            ),
        )


def test_file_pipeline_issue_refreshes_existing_open_seed_issue_evidence() -> None:
    class FakeCursor:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self._row = row

        def fetchone(self) -> dict[str, Any] | None:
            return self._row

    class FakeConnection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[Any, ...]]] = []

        def execute(self, query: str, params: tuple[Any, ...]) -> FakeCursor:
            self.calls.append((query, params))
            if "SELECT issue_id" in query:
                return FakeCursor({"issue_id": "existing-issue"})
            return FakeCursor()

    conn = FakeConnection()

    seed_runner_module._file_pipeline_issue(
        conn,
        seed_id=5,
        seed=ProfessorRosterSeed(
            institution="深圳大学",
            department="计算机与软件学院",
            roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
        ),
        stage="discovery",
        severity="high",
        description="discovery failed: fetch_failed [seed_id=5]",
        evidence={
            "seed_id": 5,
            "run_id": "new-run",
            "failure_class": "fetch_blocked",
        },
    )

    update_calls = [
        (query, params) for query, params in conn.calls if "UPDATE pipeline_issue" in query
    ]

    assert len(update_calls) == 1
    assert "INSERT INTO pipeline_issue" not in "\n".join(query for query, _ in conn.calls)
    assert update_calls[0][1][0].obj["run_id"] == "new-run"
    assert update_calls[0][1][2] == "existing-issue"


def test_szu_csse_fetch_blocked_issue_includes_source_remediation_context() -> None:
    class FakeCursor:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self._row = row

        def fetchone(self) -> dict[str, Any] | None:
            return self._row

    class FakeConnection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[Any, ...]]] = []

        def execute(self, query: str, params: tuple[Any, ...]) -> FakeCursor:
            self.calls.append((query, params))
            return FakeCursor()

    conn = FakeConnection()

    result = seed_runner_module._mark_failure(
        conn,
        seed_id=5,
        seed=ProfessorRosterSeed(
            institution="深圳大学",
            department="计算机与软件学院",
            roster_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
        ),
        run_id=None,
        trigger_mode="preview",
        limit=2,
        failure_class="fetch_blocked",
        description="discovery failed: fetch_failed",
        evidence={"failed_fetch_urls": ["https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1"]},
        items_processed=0,
        items_failed=1,
    )

    insert_calls = [
        (query, params) for query, params in conn.calls if "INSERT INTO pipeline_issue" in query
    ]
    evidence = insert_calls[0][1][4].obj

    assert result.failure_class == "fetch_blocked"
    assert evidence["source_remediation"]["decision"] == "official_replacement_not_found"
    assert evidence["source_remediation"]["accepted_replacement_url"] is None
    assert "https://www.szu.edu.cn/szdw/jsjj.htm" in {
        candidate["url"] for candidate in evidence["source_remediation"]["rejected_candidates"]
    }


def test_merge_pipeline_run_scope_accepts_uestc_fallback_audit_fields() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[Any, ...]]] = []

        def execute(self, query: str, params: tuple[Any, ...]) -> None:
            self.calls.append((query, params))

    conn = FakeConnection()

    seed_runner_module._merge_pipeline_run_scope(
        conn,
        run_id="00000000-0000-0000-0000-000000000001",
        trigger_mode="preview",
        limit=None,
        failure_class="success",
        fallback_audit_fields={
            "effective_seed_url": (
                "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405"
            ),
            "effective_department": "软件工程",
            "fallback_adapter": "uestc-yjsjy-mentor-roster",
            "fallback_source_url": "https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm",
            "fallback_program_code": "085405",
        },
    )

    patch = conn.calls[0][1][0].obj
    assert patch["effective_seed_url"] == (
        "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405"
    )
    assert patch["effective_department"] == "软件工程"
    assert patch["fallback_adapter"] == "uestc-yjsjy-mentor-roster"
    assert patch["fallback_source_url"] == "https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm"
    assert patch["fallback_program_code"] == "085405"


def test_run_single_seed_uses_official_yjsjy_replacement_for_uestc_sias_seed(
    pg_conn: psycopg.Connection,
) -> None:
    seed_id = _insert_seed(
        pg_conn,
        school="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        seed_url="https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm",
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={"seed_id": seed_id, "trigger_mode": "preview"},
        triggered_by="test",
    )
    captured_seed: ProfessorRosterSeed | None = None

    def pipeline_runner(seed: ProfessorRosterSeed, timeout: float) -> ProfessorPipelineResult:
        nonlocal captured_seed
        captured_seed = seed
        return _pipeline_result(seed=seed, profiles=[_profile(roster_source=seed.roster_url)])

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        trigger_mode="preview",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    assert captured_seed == ProfessorRosterSeed(
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        roster_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404",
    )
    assert result.status == "success"
    assert result.adapter_name == "uestc-yjsjy-mentor-roster"
    assert result.failure_class == "success"


def test_run_single_seed_records_uestc_yjsjy_replacement_audit_scope(
    pg_conn: psycopg.Connection,
) -> None:
    original_url = "https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm"
    effective_url = (
        "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405"
    )
    seed_id = _insert_seed(
        pg_conn,
        school="电子科技大学（深圳）高等研究院",
        department="软件工程",
        seed_url=original_url,
    )
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="roster_crawl",
        run_scope={
            "seed_id": seed_id,
            "seed_url": original_url,
            "department": "软件工程",
            "trigger_mode": "preview",
        },
        triggered_by="test",
    )

    def pipeline_runner(seed: ProfessorRosterSeed, timeout: float) -> ProfessorPipelineResult:
        assert seed.roster_url == effective_url
        return _pipeline_result(seed=seed, profiles=[_profile(roster_source=seed.roster_url)])

    result = run_single_seed_with_conn(
        pg_conn,
        seed_id=seed_id,
        run_id=run_id,
        trigger_mode="preview",
        pipeline_runner=pipeline_runner,
        profile_writer=lambda *_args, **_kwargs: None,
    )

    run_scope = _pipeline_run_row(pg_conn, run_id)["run_scope"]
    assert result.status == "success"
    assert run_scope["seed_url"] == original_url
    assert run_scope["department"] == "软件工程"
    assert run_scope["effective_seed_url"] == effective_url
    assert run_scope["effective_department"] == "软件工程"
    assert run_scope["fallback_adapter"] == "uestc-yjsjy-mentor-roster"
    assert run_scope["fallback_source_url"] == original_url
    assert run_scope["fallback_program_code"] == "085405"


def test_sias_fetch_blocked_issue_is_persisted_per_seed(
    pg_conn: psycopg.Connection,
    monkeypatch,
) -> None:
    first_seed_id = _insert_seed(
        pg_conn,
        school="电子科技大学（深圳）高等研究院",
        department="电子信息",
        seed_url="https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm",
    )
    second_seed_id = _insert_seed(
        pg_conn,
        school="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        seed_url="https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm",
    )
    monkeypatch.setattr(
        seed_runner_module,
        "_detect_known_fetch_blocked_seed",
        lambda seed, timeout: {
            "failure_class": "fetch_blocked",
            "fetch_method": "direct_no_env",
            "http_status": 202,
            "response_char_count": 2437,
            "response_chinese_char_count": 0,
            "response_anchor_count": 0,
            "response_shape": "tokenized_202_challenge",
        },
    )

    for seed_id in (first_seed_id, second_seed_id):
        run_id = open_pipeline_run(
            pg_conn,
            run_kind="roster_crawl",
            run_scope={"seed_id": seed_id, "trigger_mode": "preview"},
            triggered_by="test",
        )
        result = run_single_seed_with_conn(
            pg_conn,
            seed_id=seed_id,
            run_id=run_id,
            trigger_mode="preview",
            adapter_resolver=lambda _seed: None,
            pipeline_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("pipeline must not run for blocked seed")
            ),
            profile_writer=lambda *_args, **_kwargs: None,
        )
        assert result.failure_class == "fetch_blocked"

    first_issues = _issue_rows(pg_conn, seed_id=first_seed_id)
    second_issues = _issue_rows(pg_conn, seed_id=second_seed_id)

    assert len(first_issues) == 1
    assert len(second_issues) == 1
    assert first_issues[0][2]["seed_id"] == first_seed_id
    assert second_issues[0][2]["seed_id"] == second_seed_id
    assert first_issues[0][1] != second_issues[0][1]
