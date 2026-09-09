"""Postgres-backed chat session persistence with in-memory fallback."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

_SQLALCHEMY_PREFIX = "postgresql+psycopg://"
_PG_PREFIX = "postgresql://"
_DEFAULT_TTL_SECONDS = 30 * 60
_DEFAULT_MAX_CACHE_SIZE = 512


def _normalize_dsn(dsn: str) -> str:
    if dsn.startswith(_SQLALCHEMY_PREFIX):
        return _PG_PREFIX + dsn[len(_SQLALCHEMY_PREFIX) :]
    return dsn


def _context_cls() -> type[Any]:
    from backend.api.chat import SessionContext

    return SessionContext


def _new_context(session_id: str) -> Any:
    return _context_cls()(session_id=session_id)


def _coerce_epoch(value: Any) -> float:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    try:
        return float(value)
    except (TypeError, ValueError):
        return time.time()


class SessionStore:
    def __init__(self, dsn: str | None, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._dsn = _normalize_dsn(dsn) if dsn else None
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}
        self._postgres_available = bool(self._dsn)

    def get_or_create(self, session_id: str | None) -> Any:
        now = time.time()
        self._gc_memory(now=now)
        if self._postgres_available and self._dsn:
            try:
                self._delete_expired_postgres(self._ttl_seconds)
            except Exception as exc:
                self._mark_postgres_unavailable(exc)

        if session_id:
            cached = self._get_cached(session_id, now=now)
            if cached is not None:
                cached.last_seen_at = now
                return cached

        if self._postgres_available and self._dsn and session_id:
            try:
                row = self._fetch(session_id)
            except Exception as exc:
                self._mark_postgres_unavailable(exc)
            else:
                if row is not None:
                    ctx = self._context_from_row(row)
                    self._put_cached(ctx)
                    return ctx

        new_id = session_id or uuid.uuid4().hex
        ctx = _new_context(new_id)
        ctx.last_seen_at = now
        self._put_cached(ctx)
        if self._postgres_available and self._dsn:
            try:
                self._upsert(ctx)
            except Exception as exc:
                self._mark_postgres_unavailable(exc)
        return ctx

    def persist(self, ctx: Any) -> None:
        ctx.last_seen_at = time.time()
        self._put_cached(ctx)
        if not self._postgres_available or not self._dsn:
            return
        try:
            self._upsert(ctx)
        except Exception as exc:
            self._mark_postgres_unavailable(exc)

    def gc_expired(self, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> int:
        now = time.time()
        with self._lock:
            stale = [
                session_id
                for session_id, ctx in self._cache.items()
                if now - _coerce_epoch(getattr(ctx, "last_seen_at", 0.0)) > ttl_seconds
            ]
            for session_id in stale:
                self._cache.pop(session_id, None)
        deleted = len(stale)

        if not self._postgres_available or not self._dsn:
            return deleted
        try:
            return self._delete_expired_postgres(ttl_seconds)
        except Exception as exc:
            self._mark_postgres_unavailable(exc)
            return deleted

    def _fetch(self, session_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT session_id,
                       user_id,
                       entities,
                       turns,
                       last_result_set,
                       last_seen_at
                  FROM chat_session
                 WHERE session_id = %s
                   AND last_seen_at > now() - (%s * interval '1 second')
                """,
                (session_id, self._ttl_seconds),
            ).fetchone()

    def _upsert(self, ctx: Any) -> None:
        payload = self._payload(ctx)
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            conn.execute(
                """
                INSERT INTO chat_session (
                    session_id,
                    user_id,
                    entities,
                    turns,
                    last_result_set,
                    last_seen_at
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, to_timestamp(%s))
                ON CONFLICT (session_id) DO UPDATE
                   SET user_id = EXCLUDED.user_id,
                       entities = EXCLUDED.entities,
                       turns = EXCLUDED.turns,
                       last_result_set = EXCLUDED.last_result_set,
                       last_seen_at = EXCLUDED.last_seen_at
                """,
                (
                    payload["session_id"],
                    payload.get("user_id"),
                    json.dumps(payload["entities"], ensure_ascii=False),
                    json.dumps(payload["turns"], ensure_ascii=False),
                    json.dumps(payload["last_result_set"], ensure_ascii=False),
                    payload["last_seen_at"],
                ),
            )
            conn.commit()

    def _delete_expired_postgres(self, ttl_seconds: int) -> int:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            result = conn.execute(
                """
                DELETE FROM chat_session
                 WHERE last_seen_at < now() - (%s * interval '1 second')
                """,
                (ttl_seconds,),
            )
            conn.commit()
            return int(result.rowcount or 0)

    def _payload(self, ctx: Any) -> dict[str, Any]:
        if hasattr(ctx, "model_dump"):
            data = ctx.model_dump(mode="json")
        else:
            data = {
                "session_id": ctx.session_id,
                "entities": [
                    e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                    for e in ctx.entities
                ],
                "turns": list(ctx.turns),
                "last_result_set": dict(getattr(ctx, "last_result_set", {}) or {}),
                "last_seen_at": ctx.last_seen_at,
            }
        return {
            "session_id": data["session_id"],
            "user_id": data.get("user_id"),
            "entities": data.get("entities") or [],
            "turns": data.get("turns") or [],
            "last_result_set": data.get("last_result_set") or {},
            "last_seen_at": _coerce_epoch(data.get("last_seen_at")),
        }

    def _context_from_row(self, row: dict[str, Any]) -> Any:
        cls = _context_cls()
        entities = self._json_payload(row.get("entities"), fallback=[])
        turns = self._json_payload(row.get("turns"), fallback=[])
        last_result_set = self._json_payload(row.get("last_result_set"), fallback={})
        try:
            return cls(
                session_id=row["session_id"],
                user_id=row.get("user_id"),
                entities=entities,
                turns=turns,
                last_result_set=last_result_set,
                last_seen_at=_coerce_epoch(row.get("last_seen_at")),
            )
        except Exception as exc:
            logger.warning(
                "Invalid chat_session payload for session_id=%s; returning empty context: %s",
                row.get("session_id"),
                exc,
            )
            return cls(
                session_id=row["session_id"],
                user_id=row.get("user_id"),
                last_seen_at=_coerce_epoch(row.get("last_seen_at")),
            )

    def _json_payload(self, value: Any, *, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning("Invalid chat_session JSON payload; using fallback")
                return fallback
        return value

    def _get_cached(self, session_id: str, *, now: float) -> Any | None:
        with self._lock:
            ctx = self._cache.get(session_id)
            if ctx is None:
                return None
            if now - _coerce_epoch(getattr(ctx, "last_seen_at", 0.0)) > self._ttl_seconds:
                self._cache.pop(session_id, None)
                return None
            return ctx

    def _put_cached(self, ctx: Any) -> None:
        with self._lock:
            self._cache[ctx.session_id] = ctx
            if len(self._cache) <= _DEFAULT_MAX_CACHE_SIZE:
                return
            oldest = min(
                self._cache.items(),
                key=lambda item: _coerce_epoch(getattr(item[1], "last_seen_at", 0.0)),
            )[0]
            self._cache.pop(oldest, None)

    def _gc_memory(self, *, now: float) -> None:
        with self._lock:
            stale = [
                session_id
                for session_id, ctx in self._cache.items()
                if now - _coerce_epoch(getattr(ctx, "last_seen_at", 0.0))
                > self._ttl_seconds
            ]
            for session_id in stale:
                self._cache.pop(session_id, None)

    def _mark_postgres_unavailable(self, exc: Exception) -> None:
        if self._postgres_available:
            logger.warning(
                "Postgres chat_session store unavailable; falling back to in-memory sessions: %s",
                exc,
            )
        self._postgres_available = False
