from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import socket
from uuid import UUID

from alembic import command
from alembic.config import Config
import psycopg
import pytest

from src.data_agents.professor.canonical_writer import (
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
    )
    assert isinstance(page_id, UUID)
    return page_id


def test_write_new_professor_and_one_affiliation(pg_conn: psycopg.Connection):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    report = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
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


def test_idempotent_on_repeat_upsert(pg_conn: psycopg.Connection):
    enriched = _build_enriched()
    professor_id = build_professor_id(enriched)
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
    )
    second = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
    )

    assert second.professor_id == professor_id
    assert second.is_new_professor is False
    assert _scalar(pg_conn, "SELECT count(*) FROM professor") == 1
    assert _scalar(pg_conn, "SELECT count(*) FROM professor_affiliation") == 1


def test_research_topics_become_facts(pg_conn: psycopg.Connection):
    enriched = _build_enriched(
        research_directions=["人工智能", "机器学习", "计算机视觉"]
    )
    page_id = _official_page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
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
    )
    second = upsert_source_page_for_url(
        pg_conn,
        url=url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-001",
        fetched_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        is_official_source=True,
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
