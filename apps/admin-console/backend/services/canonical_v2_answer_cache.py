"""Validated answer cache for fresh, standalone, local-only chat turns.

The cache is deliberately narrow: a hit may only replace a turn that would
have started from an empty session, named no referent, and answered from the
sealed pack (no web citation, no web handle whose id embeds a session). A
candidate must also pass the validation gate below before it is stored; a
stale entry misses on release or data-epoch changes and expires on TTL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

_logger = logging.getLogger(__name__)

_CACHE_ENV = "CANONICAL_V2_ANSWER_CACHE"
_TTL_ENV = "CANONICAL_V2_ANSWER_CACHE_TTL_SECONDS"
_DEFAULT_TTL_SECONDS = 86_400
_DISABLED_VALUES = frozenset({"0", "false", "off", "no"})

_REFERENT_MARKERS = (
    "他",
    "她",
    "它",
    "这家",
    "那家",
    "该",
    "上述",
    "其中",
    "这些",
    "那些",
)
_TIME_SENSITIVE_MARKERS = (
    "今天",
    "今日",
    "最新",
    "近",
    "目前",
    "现在",
    "本周",
    "本月",
    "今年",
    "实时",
    "新闻",
    "股价",
    "刚刚",
)
_MARKER_FRAGMENTS = ("<|canonical_v2", "</|canonical_v2", "DSML")
_MEMBER_COVERAGE_PREFIX = "此外，本次检索还召回以下相关本地企业"
_LOCAL_CITATION_TYPES = frozenset({"professor", "paper", "patent", "company"})
_LOCAL_CITATION_PREFIX = "local-source-"


def cache_enabled() -> bool:
    return os.environ.get(_CACHE_ENV, "1").strip().lower() not in _DISABLED_VALUES


def cache_ttl_seconds() -> int:
    raw = os.environ.get(_TTL_ENV, "").strip()
    if not raw:
        return _DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TTL_SECONDS
    return value if value > 0 else _DEFAULT_TTL_SECONDS


def eligible_query(query: str) -> tuple[bool, str]:
    """Whether a normalized query may be served from / written to the cache."""

    text = query.strip()
    if not 2 <= len(text) <= 120:
        return False, "length"
    if any(marker in text for marker in _REFERENT_MARKERS):
        return False, "referent"
    if any(marker in text for marker in _TIME_SENSITIVE_MARKERS):
        return False, "time_sensitive"
    return True, "ok"


def query_key(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()


def data_epoch() -> str:
    """Fingerprint of operator-owned local data that can change an answer."""

    manual_dir = Path(
        os.environ.get(
            "CANONICAL_V2_MANUAL_RECALL_DIR",
            "/root/deploy/fullstack-v2/var/manual-recall-v1",
        )
    )
    corrections = Path(
        os.environ.get(
            "CANONICAL_V2_CORRECTIONS_DB",
            "/root/deploy/fullstack-v2/var/corrections.sqlite3",
        )
    )
    parts: list[str] = []
    for path in (manual_dir / "manual-recall.json", corrections):
        try:
            stat = path.stat()
        except OSError:
            parts.append("missing")
            continue
        parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def validate_candidate(
    *,
    query: str,
    response: Any,
    turn_result: Any,
) -> tuple[bool, dict[str, Any]]:
    """The write gate: only a grounded, local, non-degraded answer may cache."""

    checks: dict[str, Any] = {}
    checks["eligible_query"] = eligible_query(query)[0]
    checks["response_mode"] = getattr(turn_result, "response_mode", None) == "answer"
    checks["render_mode"] = (
        getattr(turn_result, "render_mode", None) == "prose_renderer"
    )
    checks["no_fallback"] = getattr(turn_result, "fallback_sha256", None) is None
    citations = tuple(getattr(turn_result, "citations", ()) or ())
    checks["citations"] = bool(citations)
    checks["local_only"] = bool(citations) and all(
        getattr(citation, "type", None) in _LOCAL_CITATION_TYPES
        and str(getattr(citation, "id", "")).startswith(_LOCAL_CITATION_PREFIX)
        for citation in citations
    )
    citation_map = getattr(response, "citation_map", None) or {}
    # The HTTP envelope maps display index -> citation id ({"1": "local-source-…"}),
    # so both keys and values are valid resolution targets.
    mapped_ids = {str(key) for key in citation_map} | {
        str(value) for value in citation_map.values()
    }
    checks["citation_map"] = bool(citation_map) and all(
        str(getattr(citation, "id", "")) in mapped_ids for citation in citations
    )
    answer_text = str(getattr(turn_result, "answer_text", "") or "")
    checks["no_marker"] = not any(
        fragment in answer_text for fragment in _MARKER_FRAGMENTS
    )
    checks["no_member_wall"] = _MEMBER_COVERAGE_PREFIX not in answer_text
    checks["no_conflicts"] = not getattr(turn_result, "conflicts", ())
    checks["length"] = 40 <= len(answer_text) <= 1200
    return all(checks.values()), checks


class AnswerCache:
    """SQLite-backed exact-query cache with release/epoch/TTL checks."""

    def __init__(self, path: Path, *, ttl_seconds: int | None = None) -> None:
        self._path = Path(path)
        self._ttl_seconds = ttl_seconds or cache_ttl_seconds()
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS answer_cache (
                    query_key TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    release_id TEXT NOT NULL,
                    data_epoch TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.commit()

    def get(
        self, query: str, *, release_id: str, epoch: str
    ) -> dict[str, Any] | None:
        key = query_key(query)
        now = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT release_id, data_epoch, payload_json, expires_at "
                "FROM answer_cache WHERE query_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            stored_release, stored_epoch, payload_json, expires_at = row
            if stored_release != release_id or stored_epoch != epoch:
                return None
            try:
                expires = datetime.fromisoformat(expires_at)
            except ValueError:
                return None
            if expires <= now:
                return None
            connection.execute(
                "UPDATE answer_cache SET hit_count = hit_count + 1 "
                "WHERE query_key = ?",
                (key,),
            )
            connection.commit()
            try:
                payload = json.loads(payload_json)
            except ValueError:
                return None
            return payload if isinstance(payload, dict) else None

    def put(
        self,
        query: str,
        payload: dict[str, Any],
        *,
        release_id: str,
        epoch: str,
        validation: dict[str, Any],
    ) -> None:
        key = query_key(query)
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self._ttl_seconds)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO answer_cache (
                    query_key, query_text, release_id, data_epoch,
                    payload_json, validation_json, created_at, expires_at,
                    hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(query_key) DO UPDATE SET
                    query_text = excluded.query_text,
                    release_id = excluded.release_id,
                    data_epoch = excluded.data_epoch,
                    payload_json = excluded.payload_json,
                    validation_json = excluded.validation_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    key,
                    query.strip(),
                    release_id,
                    epoch,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(validation, ensure_ascii=False),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
            connection.commit()

    def purge_expired(self) -> int:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM answer_cache WHERE expires_at <= ?", (now,)
            )
            connection.commit()
            return cursor.rowcount
