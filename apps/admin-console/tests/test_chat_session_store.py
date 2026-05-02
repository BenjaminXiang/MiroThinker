from __future__ import annotations

import os
from pathlib import Path
import socket
from typing import Any

import pytest

from backend.api.chat import SessionEntity
from backend.storage import chat_session as chat_session_module
from backend.storage.chat_session import SessionStore

_SESSION_PREFIX = "test-chat-session-"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIROFLOW_AGENT_ROOT = _REPO_ROOT / "apps" / "miroflow-agent"
_ALEMBIC_INI = _MIROFLOW_AGENT_ROOT / "alembic.ini"
_DATABASE_URL_SKIP_REASON = (
    "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping Postgres integration tests"
)
_NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"


def _raw_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip(_DATABASE_URL_SKIP_REASON)
    if "miroflow_real" in database_url:
        pytest.fail(
            f"Refusing to run tests against a real-data database: {database_url!r}. "
            "Set DATABASE_URL_TEST to a dedicated test database."
        )
    return database_url


def _psycopg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _ensure_socket_api_available() -> None:
    try:
        sock = socket.socket()
    except PermissionError:
        pytest.skip(_NETWORK_SKIP_REASON)
    else:
        sock.close()


def _load_alembic() -> tuple[Any, type[Any]]:
    try:
        from alembic import command as alembic_command
        from alembic.config import Config
    except ImportError as exc:
        pytest.skip(f"Alembic not importable in this environment: {exc}")
    return alembic_command, Config


def _load_postgres_dependencies() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        pytest.skip(f"Postgres dependencies not importable in this environment: {exc}")
    return psycopg, dict_row


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    _ensure_socket_api_available()
    database_url = _raw_database_url()
    alembic_command, Config = _load_alembic()
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_MIROFLOW_AGENT_ROOT / "alembic"))
    try:
        alembic_command.upgrade(config, "head")
    except Exception as exc:
        pytest.skip(f"{_NETWORK_SKIP_REASON}: {exc}")
    return _psycopg_dsn(database_url)


@pytest.fixture()
def clean_chat_sessions(pg_dsn: str) -> None:
    psycopg, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            "DELETE FROM chat_session WHERE session_id LIKE %s",
            (_SESSION_PREFIX + "%",),
        )
        conn.commit()
    yield
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            "DELETE FROM chat_session WHERE session_id LIKE %s",
            (_SESSION_PREFIX + "%",),
        )
        conn.commit()


def _row(pg_dsn: str, session_id: str) -> dict[str, Any] | None:
    psycopg, dict_row = _load_postgres_dependencies()

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        return conn.execute(
            """
            SELECT session_id, entities, turns, last_seen_at
              FROM chat_session
             WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()


def test_get_or_create_creates_row_and_round_trips_jsonb(
    pg_dsn: str, clean_chat_sessions: None
) -> None:
    del clean_chat_sessions
    session_id = _SESSION_PREFIX + "roundtrip"
    store = SessionStore(pg_dsn)

    ctx = store.get_or_create(session_id)
    ctx.push_entity(SessionEntity(kind="professor", id="PROF-001", label="丁文伯"))
    ctx.push_turn("介绍丁文伯", "A_prof_profile", "丁文伯是教授。")
    store.persist(ctx)

    stored = _row(pg_dsn, session_id)
    assert stored is not None
    assert stored["entities"] == [
        {"kind": "professor", "id": "PROF-001", "label": "丁文伯"}
    ]
    assert stored["turns"][0]["query_type"] == "A_prof_profile"

    reloaded = SessionStore(pg_dsn).get_or_create(session_id)
    assert reloaded.latest_professor().label == "丁文伯"
    assert reloaded.turns[0]["answer_text"] == "丁文伯是教授。"


def test_get_or_create_treats_expired_row_as_new_session(
    pg_dsn: str, clean_chat_sessions: None
) -> None:
    del clean_chat_sessions
    session_id = _SESSION_PREFIX + "expired"
    psycopg, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            """
            INSERT INTO chat_session (session_id, entities, turns, last_seen_at)
            VALUES (%s, %s::jsonb, %s::jsonb, now() - interval '25 hours')
            """,
            (
                session_id,
                '[{"kind":"professor","id":"PROF-OLD","label":"旧教授"}]',
                '[{"query":"旧问题"}]',
            ),
        )
        conn.commit()

    ctx = SessionStore(pg_dsn).get_or_create(session_id)

    assert ctx.session_id == session_id
    assert ctx.entities == []
    assert ctx.turns == []
    stored = _row(pg_dsn, session_id)
    assert stored is not None
    assert stored["entities"] == []


def test_gc_expired_deletes_only_stale_rows(
    pg_dsn: str, clean_chat_sessions: None
) -> None:
    del clean_chat_sessions
    stale_id = _SESSION_PREFIX + "gc-stale"
    fresh_id = _SESSION_PREFIX + "gc-fresh"
    psycopg, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            """
            INSERT INTO chat_session (session_id, entities, turns, last_seen_at)
            VALUES
                (%s, '[]'::jsonb, '[]'::jsonb, now() - interval '25 hours'),
                (%s, '[]'::jsonb, '[]'::jsonb, now())
            """,
            (stale_id, fresh_id),
        )
        conn.commit()

    deleted = SessionStore(pg_dsn).gc_expired()

    assert deleted == 1
    assert _row(pg_dsn, stale_id) is None
    assert _row(pg_dsn, fresh_id) is not None


def test_postgres_unavailable_falls_back_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> Any:
        raise OSError("database unavailable")

    monkeypatch.setattr(chat_session_module.psycopg, "connect", fail_connect)
    store = SessionStore("postgresql://miroflow:miroflow@localhost:15432/missing")
    session_id = _SESSION_PREFIX + "fallback"

    ctx = store.get_or_create(session_id)
    ctx.push_entity(SessionEntity(kind="professor", id="PROF-001", label="丁文伯"))
    store.persist(ctx)
    reloaded = store.get_or_create(session_id)

    assert reloaded.latest_professor().label == "丁文伯"
    assert reloaded.session_id == session_id
