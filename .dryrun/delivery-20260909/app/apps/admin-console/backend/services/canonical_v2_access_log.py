"""SQLite-backed access log for Canonical V2 chat turns.

One independent database file so access history survives candidate knowledge
rebuilds (the candidate Postgres is disposable by design). Recording is
fail-open: a logging failure must never break a chat turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Literal

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "canonical-v2-access-log-v1"

AccessLogTurnStatus = Literal["completed", "error", "interrupted"]

_FIRST_QUERY_MAX = 200
_ERROR_DETAIL_MAX = 500


@dataclass(frozen=True, slots=True)
class AccessLogTurnRecord:
    """One recorded chat turn; every field comes from the public ChatResponse."""

    turn_id: str
    session_id: str
    turn_count: int
    query: str
    query_type: str
    answer_text: str
    answer_style: str
    citations: tuple[dict[str, Any], ...]
    suggested_followups: tuple[str, ...]
    status: AccessLogTurnStatus
    error_detail: str | None
    started_at: datetime
    finished_at: datetime
    latency_ms: int


@dataclass(frozen=True, slots=True)
class AccessLogSessionSummary:
    session_id: str
    started_at: str
    last_active_at: str
    turn_count: int
    first_query: str
    statuses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AccessLogTurnDetail:
    turn_id: str
    session_id: str
    turn_count: int
    query: str
    query_type: str
    answer_text: str
    answer_style: str
    citations: tuple[dict[str, Any], ...]
    suggested_followups: tuple[str, ...]
    status: str
    error_detail: str | None
    started_at: str
    finished_at: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class AccessLogSessionDetail:
    session: AccessLogSessionSummary
    turns: tuple[AccessLogTurnDetail, ...]


_DDL = """
CREATE TABLE IF NOT EXISTS workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    turn_count INTEGER NOT NULL,
    first_query TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_count INTEGER NOT NULL,
    query TEXT NOT NULL,
    query_type TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    answer_style TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    suggested_followups_json TEXT NOT NULL,
    status TEXT NOT NULL,
    error_detail TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session_turn_count
    ON turns (session_id, turn_count);
CREATE INDEX IF NOT EXISTS turns_started_at ON turns (started_at);
CREATE INDEX IF NOT EXISTS turns_status ON turns (status);
"""


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("access log timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _prepare_database_file(database_path: Path) -> Path:
    """Create the database file with private permissions if missing."""

    if database_path.name in {"", ".", ".."} or not database_path.name:
        raise OSError("access log path must name a file")
    parent = database_path.parent
    if not parent.is_dir():
        raise OSError("access log parent directory does not exist")
    if parent.is_symlink():
        raise OSError("access log parent directory must not be a symlink")
    try:
        os.lstat(database_path)
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(database_path, flags, 0o600)
        os.close(descriptor)
    metadata = os.lstat(database_path)
    if database_path.is_symlink() or not database_path.is_file():
        raise OSError("access log path must be a regular file")
    if metadata.st_nlink != 1:
        raise OSError("access log path must not be hard-linked")
    os.chmod(database_path, 0o600, follow_symlinks=False)
    return database_path


class AccessLogStore:
    """Owns one SQLite database of recorded chat sessions and turns."""

    def __init__(self, database_path: Path) -> None:
        safe_path = _prepare_database_file(Path(database_path))
        self._database_path = safe_path
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            safe_path,
            check_same_thread=False,
            timeout=30.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._initialize_schema()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connection:
                self._connection.executescript(_DDL)
                row = self._connection.execute(
                    "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        "INSERT INTO workspace_meta (key, value) VALUES (?, ?)",
                        ("schema_version", SCHEMA_VERSION),
                    )
                elif row["value"] != SCHEMA_VERSION:
                    raise sqlite3.Error(
                        "access log schema version differs from "
                        f"{SCHEMA_VERSION}: {row['value']}"
                    )

    def record_turn(self, record: AccessLogTurnRecord) -> None:
        """Persist one turn; logging failures are logged, never raised.

        ``turn_count`` of zero means auto-assign the next ordinal for the
        session (``MAX(turn_count) + 1``), which keeps the HTTP layer free of
        per-session sequence bookkeeping.
        """

        try:
            started_at = _utc_iso(record.started_at)
            finished_at = _utc_iso(record.finished_at)
            first_query = record.query[:_FIRST_QUERY_MAX]
            with self._lock:
                with self._connection:
                    turn_count = record.turn_count
                    if turn_count <= 0:
                        row = self._connection.execute(
                            "SELECT MAX(turn_count) AS max_turn FROM turns"
                            " WHERE session_id = ?",
                            (record.session_id,),
                        ).fetchone()
                        turn_count = (
                            1
                            if row is None or row["max_turn"] is None
                            else int(row["max_turn"]) + 1
                        )
                    self._connection.execute(
                        """
                        INSERT INTO turns (
                            turn_id, session_id, turn_count, query, query_type,
                            answer_text, answer_style, citations_json,
                            suggested_followups_json, status, error_detail,
                            started_at, finished_at, latency_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (turn_id) DO NOTHING
                        """,
                        (
                            record.turn_id,
                            record.session_id,
                            turn_count,
                            record.query,
                            record.query_type,
                            record.answer_text,
                            record.answer_style,
                            json.dumps(record.citations, ensure_ascii=False),
                            json.dumps(
                                record.suggested_followups, ensure_ascii=False
                            ),
                            record.status,
                            (
                                None
                                if record.error_detail is None
                                else record.error_detail[:_ERROR_DETAIL_MAX]
                            ),
                            started_at,
                            finished_at,
                            record.latency_ms,
                        ),
                    )
                    self._connection.execute(
                        """
                        INSERT INTO sessions (
                            session_id, started_at, last_active_at,
                            turn_count, first_query
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT (session_id) DO UPDATE SET
                            last_active_at = excluded.last_active_at,
                            turn_count = MAX(sessions.turn_count, excluded.turn_count)
                        """,
                        (
                            record.session_id,
                            started_at,
                            finished_at,
                            turn_count,
                            first_query,
                        ),
                    )
        except (OSError, sqlite3.Error, ValueError) as exc:
            logger.warning(
                "Canonical V2 access log record failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    def list_sessions(
        self,
        *,
        query_text: str | None = None,
        status: AccessLogTurnStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[tuple[AccessLogSessionSummary, ...], int]:
        """List sessions ordered by most recent activity, with total count."""

        clauses: list[str] = []
        params: list[Any] = []
        if query_text:
            like = f"%{query_text}%"
            clauses.append(
                "(s.first_query LIKE ? OR EXISTS ("
                "SELECT 1 FROM turns t WHERE t.session_id = s.session_id"
                " AND t.query LIKE ?))"
            )
            params.extend([like, like])
        if status:
            clauses.append(
                "EXISTS (SELECT 1 FROM turns t WHERE t.session_id = s.session_id"
                " AND t.status = ?)"
            )
            params.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock:
            total_row = self._connection.execute(
                f"SELECT COUNT(*) AS total FROM sessions s{where}",
                params,
            ).fetchone()
            rows = self._connection.execute(
                f"""
                SELECT s.session_id, s.started_at, s.last_active_at,
                       s.turn_count, s.first_query
                FROM sessions s{where}
                ORDER BY s.last_active_at DESC, s.session_id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
            summaries: list[AccessLogSessionSummary] = []
            for row in rows:
                status_rows = self._connection.execute(
                    "SELECT DISTINCT status FROM turns WHERE session_id = ?",
                    (row["session_id"],),
                ).fetchall()
                summaries.append(
                    AccessLogSessionSummary(
                        session_id=row["session_id"],
                        started_at=row["started_at"],
                        last_active_at=row["last_active_at"],
                        turn_count=row["turn_count"],
                        first_query=row["first_query"],
                        statuses=tuple(
                            sorted(item["status"] for item in status_rows)
                        ),
                    )
                )
        return tuple(summaries), int(total_row["total"])

    def get_session(self, session_id: str) -> AccessLogSessionDetail | None:
        """Return one session with all its turns in turn order."""

        with self._lock:
            row = self._connection.execute(
                "SELECT session_id, started_at, last_active_at, turn_count,"
                " first_query FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            turn_rows = self._connection.execute(
                """
                SELECT turn_id, session_id, turn_count, query, query_type,
                       answer_text, answer_style, citations_json,
                       suggested_followups_json, status, error_detail,
                       started_at, finished_at, latency_ms
                FROM turns WHERE session_id = ?
                ORDER BY turn_count ASC, started_at ASC
                """,
                (session_id,),
            ).fetchall()
            status_rows = self._connection.execute(
                "SELECT DISTINCT status FROM turns WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        turns = tuple(
            AccessLogTurnDetail(
                turn_id=item["turn_id"],
                session_id=item["session_id"],
                turn_count=item["turn_count"],
                query=item["query"],
                query_type=item["query_type"],
                answer_text=item["answer_text"],
                answer_style=item["answer_style"],
                citations=tuple(json.loads(item["citations_json"])),
                suggested_followups=tuple(
                    json.loads(item["suggested_followups_json"])
                ),
                status=item["status"],
                error_detail=item["error_detail"],
                started_at=item["started_at"],
                finished_at=item["finished_at"],
                latency_ms=item["latency_ms"],
            )
            for item in turn_rows
        )
        return AccessLogSessionDetail(
            session=AccessLogSessionSummary(
                session_id=row["session_id"],
                started_at=row["started_at"],
                last_active_at=row["last_active_at"],
                turn_count=row["turn_count"],
                first_query=row["first_query"],
                statuses=tuple(sorted(item["status"] for item in status_rows)),
            ),
            turns=turns,
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "SCHEMA_VERSION",
    "AccessLogSessionDetail",
    "AccessLogSessionSummary",
    "AccessLogStore",
    "AccessLogTurnDetail",
    "AccessLogTurnRecord",
    "AccessLogTurnStatus",
]
