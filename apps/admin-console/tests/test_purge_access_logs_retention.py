"""Integration tests for the real cron purge script and its retention resolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess

from backend.services.canonical_v2_access_log import (
    AccessLogStore,
    AccessLogTurnRecord,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "deploy" / "purge-access-logs.sh"

_DEFAULT_RETENTION_DAYS = 90


def _turn(
    *, turn_id: str, session_id: str, age_days: int, query: str
) -> AccessLogTurnRecord:
    started = datetime.now(UTC) - timedelta(days=age_days)
    return AccessLogTurnRecord(
        turn_id=turn_id,
        session_id=session_id,
        turn_count=0,
        query=query,
        query_type="canonical_v2:A:answer",
        answer_text="回答。",
        answer_style="llm_synthesized",
        citations=(),
        suggested_followups=(),
        status="completed",
        error_detail=None,
        started_at=started,
        finished_at=started + timedelta(seconds=3),
        latency_ms=3000,
    )


def _database(path: Path) -> AccessLogStore:
    store = AccessLogStore(path)
    store.record_turn(
        _turn(
            turn_id="turn:old",
            session_id="session:chat:old",
            age_days=40,
            query="四十天前的提问",
        )
    )
    store.record_turn(
        _turn(
            turn_id="turn:recent",
            session_id="session:chat:recent",
            age_days=5,
            query="五天前的提问",
        )
    )
    return store


def _settings(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps({"schema_version": 1, "paths": {"access_log_retention_days": value}}),
        encoding="utf-8",
    )
    return path


def _run(
    *, db_path: Path, settings_path: Path | None, env_days: str | None = None, arg: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CANONICAL_V2_")}
    env["CANONICAL_V2_ACCESS_LOG_DB"] = str(db_path)
    if settings_path is not None:
        env["CANONICAL_V2_MANAGED_SETTINGS"] = str(settings_path)
    if env_days is not None:
        env["CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS"] = env_days
    command = ["bash", str(_SCRIPT)]
    if arg is not None:
        command.append(arg)
    return subprocess.run(command, capture_output=True, text=True, env=env, check=False)


def _surviving_turn_ids(db_path: Path) -> list[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT turn_id FROM turns ORDER BY turn_id").fetchall()
    finally:
        connection.close()
    return [row[0] for row in rows]


def test_managed_settings_file_drives_the_purge_window(tmp_path: Path) -> None:
    db_path = tmp_path / "access-logs.sqlite3"
    store = _database(db_path)
    store.close()
    settings = _settings(tmp_path / "settings.json", 30)

    result = _run(db_path=db_path, settings_path=settings)

    assert result.returncode == 0, result.stderr
    assert "source=file" in result.stdout
    assert "retention_days=30" in result.stdout
    assert _surviving_turn_ids(db_path) == ["turn:recent"]


def test_environment_outranks_the_settings_file(tmp_path: Path) -> None:
    db_path = tmp_path / "access-logs.sqlite3"
    store = _database(db_path)
    store.close()
    settings = _settings(tmp_path / "settings.json", 30)

    result = _run(db_path=db_path, settings_path=settings, env_days="60")

    assert result.returncode == 0, result.stderr
    assert "source=env" in result.stdout
    assert "retention_days=60" in result.stdout
    assert _surviving_turn_ids(db_path) == ["turn:old", "turn:recent"]


def test_positional_argument_outranks_everything(tmp_path: Path) -> None:
    db_path = tmp_path / "access-logs.sqlite3"
    store = _database(db_path)
    store.close()
    settings = _settings(tmp_path / "settings.json", 90)

    result = _run(db_path=db_path, settings_path=settings, env_days="90", arg="1")

    assert result.returncode == 0, result.stderr
    assert "source=argument" in result.stdout
    assert "retention_days=1" in result.stdout
    assert _surviving_turn_ids(db_path) == []


def test_missing_settings_file_falls_back_to_the_default(tmp_path: Path) -> None:
    db_path = tmp_path / "access-logs.sqlite3"
    store = _database(db_path)
    store.close()

    result = _run(db_path=db_path, settings_path=tmp_path / "absent" / "settings.json")

    assert result.returncode == 0, result.stderr
    assert "source=default" in result.stdout
    assert f"retention_days={_DEFAULT_RETENTION_DAYS}" in result.stdout
    assert _surviving_turn_ids(db_path) == ["turn:old", "turn:recent"]


def test_invalid_configured_values_warn_and_fall_back(tmp_path: Path) -> None:
    for index, value in enumerate(("abc", 0, 3651, "", None)):
        db_path = tmp_path / f"access-logs-{index}.sqlite3"
        store = _database(db_path)
        store.close()
        settings = _settings(tmp_path / f"settings-{index}.json", value)

        result = _run(db_path=db_path, settings_path=settings)

        assert result.returncode == 0, (value, result.stderr)
        assert f"retention_days={_DEFAULT_RETENTION_DAYS}" in result.stdout, value
        assert _surviving_turn_ids(db_path) == ["turn:old", "turn:recent"], value
    # An unreadable settings file is a warning, never a failure.
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    db_path = tmp_path / "access-logs-broken.sqlite3"
    store = _database(db_path)
    store.close()
    result = _run(db_path=db_path, settings_path=broken)
    assert result.returncode == 0, result.stderr
    assert "source=default" in result.stdout


def test_missing_database_is_skipped(tmp_path: Path) -> None:
    result = _run(db_path=tmp_path / "absent.sqlite3", settings_path=None)
    assert result.returncode == 0, result.stderr
    assert "skip" in result.stdout


def test_purge_also_removes_sessions_emptied_by_the_window(tmp_path: Path) -> None:
    db_path = tmp_path / "access-logs.sqlite3"
    store = _database(db_path)
    store.close()
    settings = _settings(tmp_path / "settings.json", 30)

    _run(db_path=db_path, settings_path=settings)

    connection = sqlite3.connect(db_path)
    try:
        sessions = [
            row[0] for row in connection.execute("SELECT session_id FROM sessions")
        ]
    finally:
        connection.close()
    assert sessions == ["session:chat:recent"]
