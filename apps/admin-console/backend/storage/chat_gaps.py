"""SQLite ledger of the chat knowledge-gap feedback this console receives.

A filed feedback becomes a ``GapSignal`` and goes to whatever ``gap_operations``
the serving composition installs — the in-process ephemeral object in pack mode,
so the signal is gone at the next restart. The build-line read surface
(``/api/canonical-v2/operations/gaps``) needs the Postgres gap schemas this
deployment does not have, which left the demand-side signal write-only.

This ledger is the durable copy the console can actually read: one file next to
the console's other ledgers, no Postgres, no second deduplication rule — the
runtime derives ``signal_id`` from the feedback's content, so the same feedback
filed twice stays one row.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

DB_FILENAME = "chat-gaps.sqlite3"
DB_PATH_ENV = "CANONICAL_V2_CHAT_GAPS_DB"
JOBS_DB_ENV = "CANONICAL_V2_JOBS_DB"
ACCESS_LOG_DB_ENV = "CANONICAL_V2_ACCESS_LOG_DB"
# Local single-machine serving state directory, the same fallback the credential
# store uses (see backend/services/admin_auth.py); reached only when neither this
# ledger's own path nor a sibling ledger's is configured for this process.
DEFAULT_STATE_DIR = Path("/var/tmp/mirothinker-canonical-v2-s12f")

_DDL = """
CREATE TABLE IF NOT EXISTS chat_gap (
    signal_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    note TEXT,
    query_trace_id TEXT,
    answer_trace_id TEXT,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_gap_recorded_at ON chat_gap (recorded_at);
CREATE INDEX IF NOT EXISTS chat_gap_feedback_type ON chat_gap (feedback_type);
"""

_SELECT_COLUMNS = """
    signal_id, session_id, turn_id, release_id, feedback_type, note,
    query_trace_id, answer_trace_id, observed_at, recorded_at
"""


def chat_gaps_database_path(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the ledger path: the ledger directory the console already uses.

    An explicit path wins, the way every sibling ledger resolves its own
    (``CANONICAL_V2_ADMIN_AUTH_DB``, ``CANONICAL_V2_JOBS_DB``,
    ``CANONICAL_V2_UPLOADS_DB``) — and it is what keeps a test process from
    falling through to the serving deployment's own directory.

    Unlike the jobs and uploads ledgers this never fails — the read surface has
    to answer on a console where nothing is configured, and an unconfigured
    process should still get the deployment's default state directory rather
    than an error.
    """

    values = os.environ if environ is None else environ
    explicit = (values.get(DB_PATH_ENV) or "").strip()
    if explicit:
        return Path(explicit)
    for name in (JOBS_DB_ENV, ACCESS_LOG_DB_ENV):
        sibling = (values.get(name) or "").strip()
        if sibling:
            return Path(sibling).parent / DB_FILENAME
    return DEFAULT_STATE_DIR / DB_FILENAME


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        raise ValueError("chat gap timestamps must not be empty")
    return text


def _prepare_ledger_file(database_path: Path) -> Path:
    """Create the ledger 0600 if absent and refuse symlinked/hard-linked targets."""

    if not database_path.name:
        raise OSError("chat gap ledger path must name a file")
    parent = database_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.lstat(database_path)
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(database_path, flags, 0o600)
        os.close(descriptor)
    if database_path.is_symlink() or not database_path.is_file():
        raise OSError("chat gap ledger path must be a regular file")
    if os.lstat(database_path).st_nlink != 1:
        raise OSError("chat gap ledger path must not be hard-linked")
    os.chmod(database_path, 0o600, follow_symlinks=False)
    return database_path


class ChatGapStore:
    """Owns the one SQLite ledger of filed chat-gap signals."""

    def __init__(self, database_path: Path | str) -> None:
        self._database_path = _prepare_ledger_file(Path(database_path))
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self._database_path,
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
        with self._lock, self._connection:
            self._connection.executescript(_DDL)

    def record(self, entry: Mapping[str, Any]) -> bool:
        """Insert one signal; ``True`` only when a row was actually written.

        ``recorded_at`` defaults to now and may be supplied by a caller that
        needs a deterministic write order (tests).
        """

        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO chat_gap (
                    signal_id, session_id, turn_id, release_id, feedback_type,
                    note, query_trace_id, answer_trace_id, observed_at,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (signal_id) DO NOTHING
                """,
                (
                    entry["signal_id"],
                    entry["session_id"],
                    entry["turn_id"],
                    entry["release_id"],
                    entry["feedback_type"],
                    entry.get("note"),
                    entry.get("query_trace_id"),
                    entry.get("answer_trace_id"),
                    _timestamp(entry["observed_at"]),
                    _timestamp(entry.get("recorded_at") or datetime.now(UTC)),
                ),
            )
            return cursor.rowcount == 1

    def list_recent(
        self, limit: int = 50, feedback_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest rows first, optionally for one feedback type only."""

        clauses: list[str] = []
        params: list[Any] = []
        if feedback_type is not None:
            clauses.append("feedback_type = ?")
            params.append(feedback_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM chat_gap{where}
                ORDER BY recorded_at DESC, signal_id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def counts_by_type(self) -> dict[str, int]:
        """Count the whole ledger per feedback type, most frequent first."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT feedback_type, COUNT(*) AS rows
                FROM chat_gap GROUP BY feedback_type
                ORDER BY rows DESC, feedback_type ASC
                """
            ).fetchall()
        return {row["feedback_type"]: int(row["rows"]) for row in rows}

    def total(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS rows FROM chat_gap"
            ).fetchone()
        return int(row["rows"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()


def open_chat_gap_store(environ: Mapping[str, str] | None = None) -> ChatGapStore:
    """Open the ledger this process's environment resolves.

    Opening can fail (an unusable state directory); callers own that decision —
    the feedback path swallows it, the read surface reports it.
    """

    return ChatGapStore(chat_gaps_database_path(environ))


__all__ = [
    "ACCESS_LOG_DB_ENV",
    "DB_FILENAME",
    "DB_PATH_ENV",
    "DEFAULT_STATE_DIR",
    "JOBS_DB_ENV",
    "ChatGapStore",
    "chat_gaps_database_path",
    "open_chat_gap_store",
]
