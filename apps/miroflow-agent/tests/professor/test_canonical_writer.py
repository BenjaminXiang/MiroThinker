from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import socket
from unittest.mock import MagicMock
from uuid import UUID

from alembic import command
from alembic.config import Config
import psycopg
from psycopg.rows import dict_row
import pytest

from src.data_agents.professor.canonical_writer import (
    _professor_id_if_existing_name_matches,
    _resolve_professor_id_for_write,
    _upsert_professor_row,
    set_professor_lifecycle_state,
    upsert_source_page_for_url,
    write_professor_bundle,
)
from src.data_agents.professor.cross_domain import PaperStagingRecord
from src.data_agents.professor.models import (
    EducationEntry,
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
)
from src.data_agents.professor.publish_helpers import build_professor_id
from src.data_agents.storage.postgres import seed_loader


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
DATABASE_URL_SKIP_REASON = (
    "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping Postgres integration tests"
)
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)
_LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000001"


def _raw_database_url() -> str:
    # Prefer DATABASE_URL_TEST to keep real data isolated. See
    # docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md §4.
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip(DATABASE_URL_SKIP_REASON)
    if any(name in database_url for name in _REAL_DB_NAMES):
        pytest.fail(
            f"Refusing to run tests against a real-data database: {database_url!r}. "
            "Set DATABASE_URL_TEST to miroflow_test_mock (or similar)."
        )
    return database_url


def _psycopg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _ensure_socket_api_available() -> None:
    try:
        sock = socket.socket()
    except PermissionError:
        pytest.skip(NETWORK_SKIP_REASON)
    else:
        sock.close()


def _alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(APP_ROOT / "alembic"))
    return config


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    _ensure_socket_api_available()
    return _psycopg_dsn(_raw_database_url())


@pytest.fixture(scope="session")
def pg_migrated(pg_dsn: str):
    del pg_dsn
    config = _alembic_config()
    command.upgrade(config, "head")
    seed_loader.load_all()
    try:
        yield
    finally:
        command.downgrade(config, "base")


@pytest.fixture()
def pg_conn(pg_migrated, pg_dsn: str):
    del pg_migrated
    seed_loader.load_all(pg_dsn)
    conn = psycopg.connect(pg_dsn)
    conn.execute("BEGIN")
    conn.execute(
        """
        TRUNCATE TABLE
            professor_paper_link,
            paper,
            professor_fact,
            professor_affiliation,
            professor,
            source_page
        RESTART IDENTITY CASCADE
        """
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture()
def pg_dict_conn(pg_migrated, pg_dsn: str):
    del pg_migrated
    seed_loader.load_all(pg_dsn)
    conn = psycopg.connect(pg_dsn, row_factory=dict_row)
    conn.execute("BEGIN")
    conn.execute(
        """
        TRUNCATE TABLE
            professor_paper_link,
            paper,
            professor_fact,
            professor_affiliation,
            professor,
            source_page
        RESTART IDENTITY CASCADE
        """
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _scalar(
    conn: psycopg.Connection, query: str, params: tuple[object, ...] = ()
) -> object:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _build_enriched(**overrides: object) -> EnrichedProfessorProfile:
    profile = EnrichedProfessorProfile(
        name="吴亚北",
        name_en="Yabei Wu",
        institution="南方科技大学",
        department="物理系",
        title="教授",
        email="wuyb3@sustech.edu.cn",
        homepage="https://faculty.sustech.edu.cn/wuyabei",
        research_directions=["二维材料"],
        education_structured=[
            EducationEntry(
                school="中国科学院大学",
                degree="博士",
                field="物理学",
                start_year=2005,
                end_year=2010,
            )
        ],
        awards=["国家杰出青年科学基金"],
        scholarly_profile_urls=["https://orcid.org/0000-0001-2345-6789"],
        profile_summary="吴亚北长期从事二维材料与电子结构研究。",
        evidence_urls=["https://www.sustech.edu.cn/zh/faculties/wuyabei.html"],
        profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        roster_source="https://www.sustech.edu.cn/zh/faculties/",
        extraction_status="structured",
        official_anchor_profile=OfficialAnchorProfile(
            source_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
            bio_text="吴亚北，南方科技大学物理系教授，研究方向包括二维材料与电子结构。",
            research_topics=["二维材料", "电子结构"],
            sparse_anchor=False,
        ),
    )
    return profile.model_copy(update=overrides)


def _build_paper_staging(**overrides: object) -> PaperStagingRecord:
    payload = {
        "title": "Twisted bilayer graphene and emergent phases",
        "authors": ["吴亚北", "张三"],
        "year": 2024,
        "venue": "Nature",
        "abstract": "A graphene paper.",
        "doi": "10.1038/example.2024.1",
        "citation_count": 42,
        "keywords": ["graphene", "moire"],
        "source_url": "https://www.sustech.edu.cn/publications/wuyabei",
        "source": "official_publication_page",
        "anchoring_professor_id": "PROF-WU",
        "anchoring_professor_name": "吴亚北",
        "anchoring_institution": "南方科技大学",
    }
    payload.update(overrides)
    record = PaperStagingRecord(**payload)
    extras = {
        key: value for key, value in payload.items() if key not in record.model_fields
    }
    record.__dict__.update(extras)
    return record


def _official_page_id(conn: psycopg.Connection, url: str) -> UUID:
    page_id = upsert_source_page_for_url(
        conn,
        url=url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-SEED",
        fetched_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        is_official_source=True,
        run_id=_LEGACY_RUN_ID,
    )
    assert isinstance(page_id, UUID)
    return page_id


def _insert_stale_professor_row_for_url(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    canonical_name: str,
    url: str,
) -> UUID:
    page_id = upsert_source_page_for_url(
        conn,
        url=url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref=professor_id,
        fetched_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        is_official_source=True,
        run_id=_LEGACY_RUN_ID,
    )
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            primary_official_profile_page_id,
            first_seen_at,
            last_refreshed_at,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            canonical_name,
            "interdisciplinary",
            page_id,
            now,
            now,
            _LEGACY_RUN_ID,
        ),
    )
    return page_id


def test_upsert_professor_row_rejects_placeholder_canonical_names():
    class FailOnSqlConn:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("placeholder names must be rejected before SQL")

    page_id = UUID("00000000-0000-0000-0000-000000000154")

    for placeholder in ("面包屑", "登录"):
        enriched = _build_enriched(
            name=placeholder,
            name_en=None,
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            title=None,
            evidence_urls=["https://sai.cuhk.edu.cn/teacher/154"],
            profile_url="https://sai.cuhk.edu.cn/teacher/154",
        )

        with pytest.raises(ValueError, match="non-person canonical name"):
            _upsert_professor_row(
                FailOnSqlConn(),
                professor_id=f"test-{placeholder}",
                enriched=enriched,
                primary_page_id=page_id,
                run_id=_LEGACY_RUN_ID,
            )


def test_professor_id_reuse_requires_existing_name_match_for_non_junk_names():
    assert (
        _professor_id_if_existing_name_matches(
            {"professor_id": "PROF-OLD", "canonical_name": "李志教授"},
            "李志",
        )
        == "PROF-OLD"
    )
    assert (
        _professor_id_if_existing_name_matches(
            {"professor_id": "PROF-OLD", "canonical_name": "赵展展"},
            "白志勇",
        )
        is None
    )


@pytest.mark.parametrize("stored_junk_name", ["友情链接", "教师学习"])
def test_professor_id_reuse_reclaims_same_url_row_with_stored_junk_name(
    stored_junk_name: str,
):
    assert (
        _professor_id_if_existing_name_matches(
            {"professor_id": "PROF-SYSU-JUNK", "canonical_name": stored_junk_name},
            "Loïc MARSOT",
        )
        == "PROF-SYSU-JUNK"
    )


def test_resolve_professor_id_does_not_reuse_source_page_owner_for_different_name():
    class Rows:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class Conn:
        def __init__(self):
            self.rows = [
                None,
                {"professor_id": "PROF-ZHAO", "canonical_name": "赵展展"},
            ]

        def execute(self, *_args, **_kwargs):
            return Rows(self.rows.pop(0))

    enriched = _build_enriched(
        name="王五",
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        profile_url="https://sai.cuhk.edu.cn/teacher/154",
        evidence_urls=["https://sai.cuhk.edu.cn/teacher/154"],
    )

    assert (
        _resolve_professor_id_for_write(
            Conn(),
            enriched=enriched,
            fallback_professor_id="PROF-WANG",
        )
        == "PROF-WANG"
    )


def test_source_page_owner_reuse_requires_same_teacher_name(pg_conn: psycopg.Connection):
    shared_url = "https://sai.cuhk.edu.cn/teacher/154"
    first = _build_enriched(
        name="赵展展",
        name_en=None,
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        profile_url=shared_url,
        evidence_urls=[shared_url],
        roster_source="https://sai.cuhk.edu.cn/teacher-search",
    )
    second = _build_enriched(
        name="王五",
        name_en=None,
        institution="香港中文大学（深圳）",
        department="人工智能学院",
        profile_url=shared_url,
        evidence_urls=[shared_url],
        roster_source="https://sai.cuhk.edu.cn/teacher-search",
    )

    first_report = write_professor_bundle(
        pg_conn,
        enriched=first,
        official_profile_page_id=None,
        run_id=_LEGACY_RUN_ID,
    )
    second_report = write_professor_bundle(
        pg_conn,
        enriched=second,
        official_profile_page_id=None,
        run_id=_LEGACY_RUN_ID,
    )

    assert first_report.professor_id == build_professor_id(first)
    assert second_report.professor_id == build_professor_id(second)
    assert second_report.professor_id != first_report.professor_id
    assert _scalar(pg_conn, "SELECT count(*) FROM professor") == 2
    assert (
        _scalar(
            pg_conn,
            "SELECT owner_scope_ref FROM source_page WHERE url = %s",
            (shared_url,),
        )
        == first_report.professor_id
    )


def test_write_professor_bundle_reclaims_stale_junk_name_for_same_primary_url(
    pg_conn: psycopg.Connection,
):
    profile_url = "https://science.sysu.edu.cn/teacher/loic-marsot"
    stale_professor_id = "PROF-SYSU-STALE-LINKS"
    _insert_stale_professor_row_for_url(
        pg_conn,
        professor_id=stale_professor_id,
        canonical_name="友情链接",
        url=profile_url,
    )
    corrected = _build_enriched(
        name="Loïc MARSOT",
        name_en=None,
        institution="中山大学",
        department="理学院",
        title="副教授",
        email=None,
        homepage=None,
        scholarly_profile_urls=[],
        profile_url=profile_url,
        evidence_urls=[profile_url],
        roster_source="https://science.sysu.edu.cn/teacher",
        research_directions=["数学物理"],
        profile_summary="Loïc MARSOT 从事数学物理研究。",
        official_anchor_profile=OfficialAnchorProfile(
            source_url=profile_url,
            bio_text="Loïc MARSOT，中山大学理学院副教授，从事数学物理研究。",
            research_topics=["数学物理"],
            sparse_anchor=False,
        ),
    )

    report = write_professor_bundle(
        pg_conn,
        enriched=corrected,
        official_profile_page_id=None,
        run_id=_LEGACY_RUN_ID,
    )

    assert build_professor_id(corrected) != stale_professor_id
    assert report.professor_id == stale_professor_id
    assert report.is_new_professor is False
    assert _scalar(pg_conn, "SELECT count(*) FROM professor") == 1
    row = pg_conn.execute(
        """
        SELECT p.canonical_name,
               p.primary_official_profile_page_id,
               sp.owner_scope_ref
          FROM professor p
          JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.professor_id = %s
        """,
        (stale_professor_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "Loïc MARSOT"
    assert row[1] is not None
    assert row[2] == stale_professor_id


def test_write_new_professor_and_one_affiliation(pg_conn: psycopg.Connection):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    report = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert report.professor_id == professor_id
    assert report.is_new_professor is True
    assert (
        _scalar(
            pg_conn,
            "SELECT count(*) FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == 1
    )
    assert (
        _scalar(
            pg_conn,
            "SELECT count(*) FROM professor_affiliation WHERE professor_id = %s",
            (professor_id,),
        )
        == 1
    )
    assert (
        _scalar(
            pg_conn,
            "SELECT count(*) FROM professor_fact WHERE professor_id = %s",
            (professor_id,),
        )
        >= 1
    )


def test_write_new_professor_defaults_lifecycle_to_active(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert (
        _scalar(
            pg_conn,
            "SELECT lifecycle_state FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == "active"
    )


def test_set_professor_lifecycle_state_updates_state_and_audit(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)
    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    result = set_professor_lifecycle_state(
        pg_conn,
        professor_id=professor_id,
        lifecycle_state="archived",
        actor="ops",
        note="No longer listed on current school roster.",
    )

    assert result.professor_id == professor_id
    assert result.previous_lifecycle_state == "active"
    assert result.lifecycle_state == "archived"
    assert result.lifecycle_merged_into_id is None
    assert (
        _scalar(
            pg_conn,
            "SELECT lifecycle_state FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == "archived"
    )
    audit_row = pg_conn.execute(
        """
        SELECT action, actor, note
          FROM professor_admin_action
         WHERE professor_id = %s
         ORDER BY created_at DESC
         LIMIT 1
        """,
        (professor_id,),
    ).fetchone()
    assert audit_row == (
        "set_lifecycle_state",
        "ops",
        "lifecycle_state active -> archived; No longer listed on current school roster.",
    )


def test_normal_professor_refresh_preserves_explicit_archived_lifecycle(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)
    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )
    set_professor_lifecycle_state(
        pg_conn,
        professor_id=professor_id,
        lifecycle_state="archived",
        actor="ops",
        note="Archived by lifecycle review.",
    )

    refreshed = enriched.model_copy(
        update={
            "profile_summary": "吴亚北继续从事二维材料与电子结构研究，历史资料保持可信。",
        }
    )
    write_professor_bundle(
        pg_conn,
        enriched=refreshed,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    row = pg_conn.execute(
        """
        SELECT lifecycle_state, profile_summary
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()

    assert row == (
        "archived",
        "吴亚北继续从事二维材料与电子结构研究，历史资料保持可信。",
    )


def test_write_professor_bundle_sets_incomplete_official_quality_status(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched(
        research_directions=[],
        profile_summary=None,
    )
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert (
        _scalar(
            pg_conn,
            "SELECT quality_status FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == "needs_enrichment"
    )
    assert (
        _scalar(
            pg_conn,
            """
            SELECT count(*)
              FROM pipeline_issue
             WHERE professor_id = %s
               AND reported_by = 'professor_quality_gate'
               AND resolved = false
            """,
            (professor_id,),
        )
        >= 1
    )


def test_write_professor_persists_profile_raw_text(pg_conn: psycopg.Connection):
    enriched = _build_enriched(
        profile_summary="吴亚北现任南方科技大学物理系教授，长期从事二维材料与电子结构研究。",
        profile_raw_text="个人简介：吴亚北长期从事二维材料与电子结构研究。教育背景：中国科学院大学博士。",
    )
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert (
        _scalar(
            pg_conn,
            "SELECT profile_raw_text FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == "个人简介：吴亚北长期从事二维材料与电子结构研究。教育背景：中国科学院大学博士。"
    )
    assert (
        _scalar(
            pg_conn,
            "SELECT profile_summary FROM professor WHERE professor_id = %s",
            (professor_id,),
        )
        == "吴亚北现任南方科技大学物理系教授，长期从事二维材料与电子结构研究。"
    )


def test_write_professor_bundle_strips_nul_bytes_from_text_fields(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched(
        profile_summary="吴亚北\x00长期从事二维材料研究。",
        profile_raw_text="个人简介：吴亚北\x00长期从事二维材料与电子结构研究。",
        research_directions=["二维\x00材料"],
    )
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    row = pg_conn.execute(
        """
        SELECT p.profile_summary,
               p.profile_raw_text,
               pf.value_raw
          FROM professor p
          JOIN professor_fact pf
            ON pf.professor_id = p.professor_id
         WHERE p.professor_id = %s
           AND pf.fact_type = 'research_topic'
        """,
        (professor_id,),
    ).fetchone()
    assert row is not None
    assert "\x00" not in row[0]
    assert "\x00" not in row[1]
    assert "\x00" not in row[2]
    assert row[2] == "二维材料"


def test_idempotent_on_repeat_upsert(pg_conn: psycopg.Connection):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )
    second = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert second.professor_id == professor_id
    assert second.is_new_professor is False
    assert _scalar(pg_conn, "SELECT count(*) FROM professor") == 1
    assert _scalar(pg_conn, "SELECT count(*) FROM professor_affiliation") == 1


def test_reuses_existing_professor_id_when_profile_url_key_gains_department(
    pg_conn: psycopg.Connection,
):
    initial = _build_enriched(department=None, title=None)
    existing_id = build_professor_id(initial)
    page_id = _official_page_id(pg_conn, initial.profile_url)

    first = write_professor_bundle(
        pg_conn,
        enriched=initial,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )
    enriched = initial.model_copy(
        update={
            "department": "物理系",
            "title": "教授",
            "profile_raw_text": "吴亚北，南方科技大学物理系教授。",
        }
    )
    changed_key_id = build_professor_id(enriched)

    second = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert changed_key_id != existing_id
    assert first.professor_id == existing_id
    assert second.professor_id == existing_id
    assert _scalar(pg_conn, "SELECT count(*) FROM professor") == 1
    assert (
        _scalar(
            pg_conn,
            "SELECT profile_raw_text FROM professor WHERE professor_id = %s",
            (existing_id,),
        )
        == "吴亚北，南方科技大学物理系教授。"
    )
    affiliation_rows = pg_conn.execute(
        """
        SELECT department, title, is_primary
        FROM professor_affiliation
        WHERE professor_id = %s
        ORDER BY department NULLS FIRST
        """,
        (existing_id,),
    ).fetchall()
    assert len(affiliation_rows) == 2
    assert sum(1 for row in affiliation_rows if row[2]) == 1
    assert any(
        row[0] == "物理系" and row[1] == "教授" and row[2]
        for row in affiliation_rows
    )
    assert any(row[0] is None and row[2] is False for row in affiliation_rows)


def test_corrected_primary_affiliation_supersedes_stale_current_title_variant(
    pg_conn: psycopg.Connection,
):
    source_url = "https://sds.cuhk.edu.cn/teacher/2238"
    contaminated_title = (
        "BRESAR, Miha | 香港中文大学（深圳）数据科学学院 URL Source: "
        "https://sds.cuhk.edu.cn/teacher/2238 Markdown Content: ## BRESAR, Miha "
        "助理教授 教育背景 博士，统计学，华威大学"
    )
    initial = _build_enriched(
        name="BRESAR, Miha",
        name_en=None,
        institution="香港中文大学（深圳）",
        department="数据科学学院",
        title=contaminated_title,
        email="mihabresar@cuhk.edu.cn",
        homepage="https://sites.google.com/view/mihabresar",
        profile_url=source_url,
        roster_source="https://sds.cuhk.edu.cn/teacher-search",
        evidence_urls=[source_url],
        research_directions=["概率论"],
        official_anchor_profile=OfficialAnchorProfile(
            source_url=source_url,
            bio_text="BRESAR, Miha 助理教授，研究领域包括概率论。",
            research_topics=["概率论"],
            sparse_anchor=False,
        ),
    )
    page_id = _official_page_id(pg_conn, source_url)

    first = write_professor_bundle(
        pg_conn,
        enriched=initial,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )
    corrected = initial.model_copy(update={"title": "助理教授"})
    second = write_professor_bundle(
        pg_conn,
        enriched=corrected,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert second.professor_id == first.professor_id
    affiliation_rows = pg_conn.execute(
        """
        SELECT title, is_primary, is_current
        FROM professor_affiliation
        WHERE professor_id = %s
        ORDER BY is_current DESC, is_primary DESC, title
        """,
        (first.professor_id,),
    ).fetchall()

    assert len(affiliation_rows) == 2
    assert [row for row in affiliation_rows if row[2]] == [("助理教授", True, True)]
    assert any(
        row[0] == contaminated_title and row[1] is False and row[2] is False
        for row in affiliation_rows
    )


def test_research_topics_become_facts(pg_conn: psycopg.Connection):
    enriched = _build_enriched(
        research_directions=["人工智能", "机器学习", "计算机视觉"]
    )
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert (
        _scalar(
            pg_conn,
            """
        SELECT count(*)
        FROM professor_fact
        WHERE professor_id = %s
          AND fact_type = 'research_topic'
        """,
            (build_professor_id(enriched),),
        )
        == 3
    )


def test_academic_positions_become_facts(pg_conn: psycopg.Connection):
    enriched = _build_enriched(academic_positions=["IEEE Fellow", "ACM Fellow"])
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    rows = pg_conn.execute(
        """
        SELECT value_raw, source_page_id, evidence_span, status, run_id
          FROM professor_fact
         WHERE professor_id = %s
           AND fact_type = 'academic_position'
         ORDER BY value_raw
        """,
        (build_professor_id(enriched),),
    ).fetchall()
    assert [(row[0], row[1], row[3], row[4]) for row in rows] == [
        ("ACM Fellow", page_id, "active", UUID(_LEGACY_RUN_ID)),
        ("IEEE Fellow", page_id, "active", UUID(_LEGACY_RUN_ID)),
    ]
    assert all(row[2] for row in rows)


def test_paper_staging_produces_verified_link_when_official(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched()
    page_id = _official_page_id(pg_conn, enriched.profile_url)
    staging = _build_paper_staging(disambiguation_confidence=0.95)

    report = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        paper_staging=[staging],
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert report.papers_written == 1
    assert report.professor_paper_links_written == 1
    assert report.professor_paper_links_verified == 1
    assert (
        _scalar(
            pg_conn,
            "SELECT count(*) FROM paper",
        )
        == 1
    )
    assert (
        _scalar(
            pg_conn,
            """
        SELECT count(*)
        FROM professor_paper_link
        WHERE link_status = 'verified'
        """,
        )
        == 1
    )


def test_paper_staging_produces_candidate_link_when_api_only(
    pg_conn: psycopg.Connection,
):
    enriched = _build_enriched()
    page_id = _official_page_id(pg_conn, enriched.profile_url)
    staging = _build_paper_staging(
        source="academic_api_with_affiliation_match",
        source_url="https://openalex.org/W1234567890",
        disambiguation_confidence=0.95,
        institution_consistency_score=0.20,
        topic_consistency_score=0.95,
        doi="10.48550/example.2024.2",
    )

    report = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        paper_staging=[staging],
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert report.professor_paper_links_written == 1
    assert report.professor_paper_links_verified == 0
    row = pg_conn.execute(
        """
        SELECT link_status, evidence_api_source, evidence_page_id
        FROM professor_paper_link
        """
    ).fetchone()
    assert row == ("candidate", "academic_api_with_affiliation_match", None)


@pytest.mark.parametrize("source", ["dblp", "arxiv"])
def test_api_paper_staging_preserves_supported_canonical_source(
    pg_conn: psycopg.Connection,
    source: str,
):
    enriched = _build_enriched()
    page_id = _official_page_id(pg_conn, enriched.profile_url)
    staging = _build_paper_staging(
        source=source,
        source_url=f"https://example.org/{source}/paper-1",
        disambiguation_confidence=0.95,
        institution_consistency_score=0.20,
        topic_consistency_score=0.95,
        doi=f"10.48550/{source}.2024.2",
    )

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        paper_staging=[staging],
        official_profile_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert (
        _scalar(
            pg_conn,
            "SELECT canonical_source FROM paper WHERE doi = %s",
            (f"10.48550/{source}.2024.2",),
        )
        == source
    )


def test_upsert_source_page_returns_stable_page_id(pg_conn: psycopg.Connection):
    url = "https://www.sustech.edu.cn/zh/faculties/wuyabei.html"

    first = upsert_source_page_for_url(
        pg_conn,
        url=url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-001",
        fetched_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        is_official_source=True,
        run_id=_LEGACY_RUN_ID,
    )
    second = upsert_source_page_for_url(
        pg_conn,
        url=url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-001",
        fetched_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        is_official_source=True,
        run_id=_LEGACY_RUN_ID,
    )

    assert first == second
    assert (
        _scalar(
            pg_conn,
            "SELECT count(*) FROM source_page WHERE url = %s",
            (url,),
        )
        == 1
    )


def test_upsert_source_page_conflict_sql_preserves_official_profile_role():
    conn = MagicMock()
    page_id = UUID("11111111-1111-1111-1111-111111111111")
    conn.execute.return_value.fetchone.return_value = {"page_id": page_id}

    returned = upsert_source_page_for_url(
        conn,
        url="https://example.edu/prof",
        page_role="personal_homepage",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-001",
        fetched_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        is_official_source=False,
        run_id=_LEGACY_RUN_ID,
    )

    assert returned == page_id
    sql = conn.execute.call_args.args[0]
    assert "WHEN source_page.page_role IN ('official_profile', 'official_publication_page')" in sql
    assert "AND EXCLUDED.page_role IN ('personal_homepage', 'lab_homepage')" in sql
    assert "THEN source_page.page_role" in sql


def test_upsert_professor_row_refreshes_primary_official_profile_page_sql():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"exists": 1}
    page_id = UUID("11111111-1111-1111-1111-111111111111")

    is_new = _upsert_professor_row(
        conn,
        professor_id="PROF-001",
        enriched=_build_enriched(),
        primary_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert is_new is False
    sql = conn.execute.call_args_list[-1].args[0]
    assert (
        "primary_official_profile_page_id  = EXCLUDED.primary_official_profile_page_id"
        in sql
    )
    assert (
        "primary_official_profile_page_id  = COALESCE("
        not in sql
    )


def test_canonical_writer_accepts_default_dict_rows(pg_dict_conn: psycopg.Connection):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)

    first = write_professor_bundle(
        pg_dict_conn,
        enriched=enriched,
        official_profile_page_id=None,
        run_id=_LEGACY_RUN_ID,
    )
    second = write_professor_bundle(
        pg_dict_conn,
        enriched=enriched,
        official_profile_page_id=None,
        run_id=_LEGACY_RUN_ID,
    )

    assert first.professor_id == professor_id
    assert second.is_new_professor is False
    assert first.affiliations_written == 1
    assert second.affiliations_written == 1
    row = pg_dict_conn.execute(
        """
        SELECT p.professor_id, sp.page_id
        FROM professor p
        JOIN source_page sp
          ON sp.page_id = p.primary_official_profile_page_id
        WHERE p.professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    assert row is not None
    assert row["professor_id"] == professor_id
    assert isinstance(row["page_id"], UUID)
