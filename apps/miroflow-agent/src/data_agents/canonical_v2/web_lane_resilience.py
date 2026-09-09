"""Web-lane resilience: retry, view+day cache, circuit breaker, quota watermark.

Spec: openspec/changes/add-turn-trace-observability (task 1.3).

- Single retry with backoff per provider per view on transport/timeout errors
  only — auth/quota errors are not retried (pointless) and carry their reason.
- Web-result cache keyed by (provider, normalized view text, UTC day) — the
  day boundary is the TTL. SQLite, fail-open (any storage error degrades to
  no-cache behavior).
- Per-provider circuit breaker: OPEN after N consecutive failures, probe after
  a cooldown window, CLOSED on probe success. Replaces the process-lifetime
  sticky disable previously baked into the Serper provider.
- Per-provider per-day request counters against a quota watermark; above the
  watermark keepwarm traffic MUST NOT search (user turns still proceed).

All state lives beside the turn-trace journal root (env ``TURN_TRACE_DIR`` or
``var/turn-trace``); every resilience event is reported through the
turn-trace reporter (breaker states ride the web-outcome rows).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

DEFAULT_QUOTA_WATERMARK = 4000
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_COOLDOWN_SECONDS = 60.0
RETRY_BACKOFF_SECONDS = 0.25

_AUTH_MARKERS = ("401", "403", "unauthorized", "api key", "invalid key")
_QUOTA_MARKERS = ("credit", "quota", "余额", "配额")


def classify_search_error(exc: BaseException) -> tuple[bool, str]:
    """(retryable, breaker_reason) for a provider search failure."""
    message = str(exc).casefold()
    if any(marker in message for marker in _QUOTA_MARKERS):
        return False, "quota"
    if any(marker in message for marker in _AUTH_MARKERS):
        return False, "auth"
    return True, "transport"


def resilience_root() -> Path:
    import os

    env_dir = os.getenv("TURN_TRACE_DIR", "").strip()
    return Path(env_dir) if env_dir else Path("var") / "turn-trace"


def _utc_day(clock: Any) -> str:
    now = clock() if callable(clock) else datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        now = datetime.now(UTC)
    return now.astimezone(UTC).date().isoformat()


class WebLaneBreaker:
    """Per-provider consecutive-failure breaker with probe recovery."""

    def __init__(
        self,
        *,
        failure_threshold: int = BREAKER_FAILURE_THRESHOLD,
        cooldown_seconds: float = BREAKER_COOLDOWN_SECONDS,
        clock: Any = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._state: dict[str, str] = {}  # provider -> closed|open|probe
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, datetime] = {}
        self._reasons: dict[str, str] = {}

    def state(self, provider: str) -> str:
        with self._lock:
            return self._state.get(provider, "closed")

    def reason(self, provider: str) -> str | None:
        with self._lock:
            return self._reasons.get(provider)

    def attempt_allowed(self, provider: str) -> tuple[bool, str]:
        """May a real request be issued now? Returns (allowed, state_before)."""
        with self._lock:
            state = self._state.get(provider, "closed")
            if state != "open":
                return True, state
            opened_at = self._opened_at.get(provider)
            elapsed = (
                (self._clock() - opened_at).total_seconds()
                if opened_at is not None
                else 0.0
            )
            if elapsed >= self._cooldown_seconds:
                self._state[provider] = "probe"
                return True, "probe"
            return False, "open"

    def record(self, provider: str, ok: bool, reason: str | None = None) -> str:
        """Record one attempt outcome; returns the state after recording."""
        with self._lock:
            if ok:
                self._failures[provider] = 0
                self._state[provider] = "closed"
                self._reasons.pop(provider, None)
            else:
                failures = self._failures.get(provider, 0) + 1
                self._failures[provider] = failures
                if reason:
                    self._reasons[provider] = reason
                if failures >= self._failure_threshold:
                    self._state[provider] = "open"
                    self._opened_at[provider] = self._clock()
                elif self._state.get(provider) == "probe":
                    # A failed probe re-opens immediately with a fresh cooldown.
                    self._state[provider] = "open"
                    self._opened_at[provider] = self._clock()
            return self._state.get(provider, "closed")


class _WebLaneStore:
    """One SQLite file shared by the cache and quota counters (fail-open)."""

    _DDL = """
    CREATE TABLE IF NOT EXISTS web_cache (
        provider TEXT NOT NULL,
        view_key TEXT NOT NULL,
        day TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (provider, view_key, day)
    );
    CREATE TABLE IF NOT EXISTS web_quota (
        provider TEXT NOT NULL,
        day TEXT NOT NULL,
        request_count INTEGER NOT NULL,
        PRIMARY KEY (provider, day)
    );
    """

    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None
        try:
            root = resilience_root() if root is None else Path(root)
            root.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                root / "web_lane.sqlite3",
                check_same_thread=False,
                timeout=10.0,
            )
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(self._DDL)
            self._connection = connection
        except (OSError, sqlite3.Error):
            self._connection = None

    @property
    def available(self) -> bool:
        return self._connection is not None

    def cache_get(self, provider: str, view_key: str, day: str) -> list[dict[str, Any]] | None:
        if self._connection is None:
            return None
        try:
            with self._lock:
                row = self._connection.execute(
                    "SELECT payload_json FROM web_cache"
                    " WHERE provider = ? AND view_key = ? AND day = ?",
                    (provider, view_key, day),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        import json

        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError):
            return None
        return payload if isinstance(payload, list) else None

    def cache_put(
        self,
        provider: str,
        view_key: str,
        day: str,
        results: list[dict[str, Any]],
    ) -> None:
        if self._connection is None or not results:
            return
        import json

        try:
            payload = json.dumps(results, ensure_ascii=False)
            with self._lock:
                with self._connection:
                    self._connection.execute(
                        "INSERT OR REPLACE INTO web_cache"
                        " (provider, view_key, day, payload_json, fetched_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (
                            provider,
                            view_key,
                            day,
                            payload,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
        except (OSError, sqlite3.Error, ValueError):
            return

    def quota_incr(self, provider: str, day: str) -> int:
        if self._connection is None:
            return 0
        try:
            with self._lock:
                with self._connection:
                    self._connection.execute(
                        "INSERT INTO web_quota (provider, day, request_count)"
                        " VALUES (?, ?, 1)"
                        " ON CONFLICT (provider, day) DO UPDATE SET"
                        " request_count = request_count + 1",
                        (provider, day),
                    )
                    row = self._connection.execute(
                        "SELECT request_count FROM web_quota"
                        " WHERE provider = ? AND day = ?",
                        (provider, day),
                    ).fetchone()
            return int(row[0]) if row is not None else 0
        except sqlite3.Error:
            return 0

    def quota_count(self, provider: str, day: str) -> int:
        if self._connection is None:
            return 0
        try:
            with self._lock:
                row = self._connection.execute(
                    "SELECT request_count FROM web_quota"
                    " WHERE provider = ? AND day = ?",
                    (provider, day),
                ).fetchone()
            return int(row[0]) if row is not None else 0
        except sqlite3.Error:
            return 0


class NullWebLaneStore:
    """No-op storage: keeps resilience inert unless a store is explicitly
    injected (the serving composition wires one; direct-adapter tests stay
    hermetic — no cross-test cache/quota file sharing)."""

    available = False

    def cache_get(self, *_: Any) -> list[dict[str, Any]] | None:
        return None

    def cache_put(self, *_: Any) -> None: ...

    def quota_incr(self, *_: Any) -> int:
        return 0

    def quota_count(self, *_: Any) -> int:
        return 0


def view_cache_key(view: str) -> str:
    import hashlib

    return hashlib.sha256(view.encode("utf-8")).hexdigest()


def quota_watermark() -> int:
    import os

    raw = os.getenv("WEB_LANE_DAILY_QUOTA", "").strip()
    try:
        return int(raw) if raw else DEFAULT_QUOTA_WATERMARK
    except ValueError:
        return DEFAULT_QUOTA_WATERMARK


__all__ = [
    "BREAKER_COOLDOWN_SECONDS",
    "BREAKER_FAILURE_THRESHOLD",
    "RETRY_BACKOFF_SECONDS",
    "WebLaneBreaker",
    "_WebLaneStore",
    "NullWebLaneStore",
    "classify_search_error",
    "quota_watermark",
    "resilience_root",
    "_utc_day",
    "view_cache_key",
]
