# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.17 — wiring tests: name_identity_gate plumbed through write_professor_bundle.

Unlike the unit tests (fully mocked LLM), these tests exercise a real Postgres
fixture and inject a *fake* gate callable to catch wiring bugs:
  * Legacy path (gate=None) preserves existing name_en write behavior.
  * Rejected decision actually nulls the DB column (not just a local var).
  * Accepted decision persists candidate_name_en.
  * Gate is called with the *cleaned* canonical_name (not raw).
  * Contract: gate is sync-callable; an async gate is not allowed.
"""

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
from src.data_agents.professor.models import (
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
)
from src.data_agents.professor.name_identity_gate import (
    NameIdentityCandidate,
    NameIdentityDecision,
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
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip(DATABASE_URL_SKIP_REASON)
    if any(name in database_url for name in _REAL_DB_NAMES):
        pytest.fail(
            f"Refusing to run tests against a real-data database: {database_url!r}."
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


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    _ensure_socket_api_available()
    return _psycopg_dsn(_raw_database_url())


@pytest.fixture(scope="module")
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


def _enriched(name: str, name_en: str | None) -> EnrichedProfessorProfile:
    return EnrichedProfessorProfile(
        name=name,
        name_en=name_en,
        institution="深圳技术大学",
        department="材料学院",
        title="教授",
        email="test@sztu.edu.cn",
        homepage="https://cep.sztu.edu.cn/info/1053/1722.htm",
        research_directions=["二维材料"],
        profile_summary=f"{name}，深圳技术大学教授。",
        evidence_urls=["https://cep.sztu.edu.cn/info/1053/1722.htm"],
        profile_url="https://cep.sztu.edu.cn/info/1053/1722.htm",
        roster_source="https://cep.sztu.edu.cn/",
        extraction_status="structured",
        official_anchor_profile=OfficialAnchorProfile(
            source_url="https://cep.sztu.edu.cn/info/1053/1722.htm",
            bio_text=f"{name}，深圳技术大学教授。",
            research_topics=["二维材料"],
            sparse_anchor=False,
        ),
    )


def _page_id(conn: psycopg.Connection, url: str) -> UUID:
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


def _stored_name_en(conn: psycopg.Connection, professor_id: str) -> str | None:
    row = conn.execute(
        "SELECT canonical_name_en FROM professor WHERE professor_id = %s",
        (professor_id,),
    ).fetchone()
    assert row is not None
    return row[0]


# ---------------------------------------------------------------------------
# Wiring tests
# ---------------------------------------------------------------------------


def test_legacy_no_gate_leaves_name_en_unchanged(pg_conn: psycopg.Connection):
    """name_identity_gate defaults to None; must not disturb pre-existing behavior."""
    enriched = _enriched("张成萍", "Thomas Hardy")
    pid = build_professor_id(enriched)
    page_id = _page_id(pg_conn, enriched.profile_url)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        # name_identity_gate deliberately omitted
    )
    # Legacy path: junk name_en is preserved. The gate is a new opt-in.
    assert _stored_name_en(pg_conn, pid) == "Thomas Hardy"


def test_rejected_decision_nulls_db_column(pg_conn: psycopg.Connection):
    enriched = _enriched("张成萍", "Thomas Hardy")
    pid = build_professor_id(enriched)
    page_id = _page_id(pg_conn, enriched.profile_url)

    def fake_gate(candidate: NameIdentityCandidate) -> NameIdentityDecision:
        assert candidate.canonical_name == "张成萍"
        assert candidate.candidate_name_en == "Thomas Hardy"
        return NameIdentityDecision(
            accepted=False, confidence=0.05, reasoning="unrelated", error=None
        )

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        name_identity_gate=fake_gate,
    )
    assert _stored_name_en(pg_conn, pid) is None


def test_accepted_decision_persists_name_en(pg_conn: psycopg.Connection):
    enriched = _enriched("熊会元", "Huiyuan Xiong")
    pid = build_professor_id(enriched)
    page_id = _page_id(pg_conn, enriched.profile_url)

    def fake_gate(candidate: NameIdentityCandidate) -> NameIdentityDecision:
        return NameIdentityDecision(
            accepted=True, confidence=0.95, reasoning="standard pinyin", error=None
        )

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        name_identity_gate=fake_gate,
    )
    assert _stored_name_en(pg_conn, pid) == "Huiyuan Xiong"


def test_gate_skipped_when_name_en_empty(pg_conn: psycopg.Connection):
    """If name_en is empty, the gate must not be invoked (LLM call is wasted)."""
    enriched = _enriched("无英文名教授", None)
    pid = build_professor_id(enriched)
    page_id = _page_id(pg_conn, enriched.profile_url)

    called = {"n": 0}

    def fake_gate(candidate: NameIdentityCandidate) -> NameIdentityDecision:
        called["n"] += 1
        return NameIdentityDecision(True, 0.99, "", None)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        name_identity_gate=fake_gate,
    )
    assert called["n"] == 0
    assert _stored_name_en(pg_conn, pid) is None


def test_gate_called_with_cleaned_name(pg_conn: psycopg.Connection):
    """`_clean_text` strips whitespace; gate must see the cleaned version."""
    enriched = _enriched("  张三  ", "  Zhang San  ")
    pid = build_professor_id(enriched)
    page_id = _page_id(pg_conn, enriched.profile_url)

    captured = {}

    def fake_gate(candidate: NameIdentityCandidate) -> NameIdentityDecision:
        captured["name"] = candidate.canonical_name
        captured["candidate"] = candidate.candidate_name_en
        return NameIdentityDecision(True, 0.9, "", None)

    write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=page_id,
        name_identity_gate=fake_gate,
    )
    assert captured["name"] == "张三"  # cleaned
    assert captured["candidate"] == "Zhang San"  # cleaned
    assert _stored_name_en(pg_conn, pid) == "Zhang San"


def test_gate_callable_must_be_sync(pg_conn: psycopg.Connection):
    """Async gate would cause a coroutine object to reach the decision check.

    The wiring must detect an async callable and refuse it explicitly, rather
    than silently writing bogus data because the `if not decision.accepted`
    check on a coroutine is always truthy.
    """
    enriched = _enriched("李强", "Qiang Li")
    page_id = _page_id(pg_conn, enriched.profile_url)

    async def async_gate(candidate):  # pragma: no cover - should not be awaited
        return NameIdentityDecision(True, 1.0, "", None)

    with pytest.raises((TypeError, RuntimeError)):
        write_professor_bundle(
            pg_conn,
            enriched=enriched,
            official_profile_page_id=page_id,
            name_identity_gate=async_gate,  # type: ignore[arg-type]
        )
