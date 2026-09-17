"""R2 — session codec: signing, expiry windows, epoch/account validity, key file.

Fixture source: constructed key + store, injected clock (no test sleeps).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import stat

from fastapi import Request
import pytest

from backend.services.admin_auth import (
    DB_PATH_ENV,
    KEY_PATH_ENV,
    AdminAuthStore,
)
from backend.services.admin_session import (
    ABSOLUTE_SESSION_SECONDS,
    IDLE_SESSION_SECONDS,
    SESSION_COOKIE,
    SessionCodec,
    authenticate,
    clear_session_cookie,
    request_is_https,
    render_session_cookie,
)


_PASSWORD = "scratch-password-one"
_START = datetime(2026, 9, 17, 8, 0, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _store(tmp_path: Path) -> AdminAuthStore:
    store = AdminAuthStore(tmp_path / "admin-auth.sqlite3")
    store.create_account("ops", _PASSWORD)
    return store


def _codec(clock: _Clock) -> SessionCodec:
    return SessionCodec(os.urandom(32), clock=clock)


def _request(headers: dict[str, str], *, scheme: str = "http") -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/main",
            "scheme": scheme,
            "headers": raw,
            "query_string": b"",
            "server": ("testserver", 80),
        }
    )


def test_issue_and_verify_round_trip() -> None:
    clock = _Clock(_START)
    codec = _codec(clock)

    token, expires_at = codec.issue("ops", password_epoch=1)

    assert SESSION_COOKIE == "cv2_admin_session"
    assert "." in token
    assert expires_at == _START + timedelta(seconds=IDLE_SESSION_SECONDS)
    ticket = codec.verify(token)
    assert ticket is not None
    assert ticket.username == "ops"
    assert ticket.password_epoch == 1
    assert ticket.issued_at == _START
    assert ticket.expires_at == expires_at


def test_tampered_payload_or_signature_is_rejected() -> None:
    clock = _Clock(_START)
    codec = _codec(clock)
    token, _ = codec.issue("ops", password_epoch=1)
    payload, signature = token.split(".", 1)

    flipped = "A" if payload[0] != "A" else "B"
    tampered_payload = f"{flipped}{payload[1:]}.{signature}"
    flipped_signature = "A" if signature[0] != "A" else "B"

    assert codec.verify(tampered_payload) is None
    assert codec.verify(f"{payload}.{flipped_signature}{signature[1:]}") is None
    assert codec.verify(f"{payload}.{signature}.extra") is None
    assert codec.verify("not-a-token") is None
    assert codec.verify("") is None


def test_idle_window_expires_and_refresh_extends_it() -> None:
    clock = _Clock(_START)
    codec = _codec(clock)
    token, _ = codec.issue("ops", password_epoch=1)

    clock.advance(IDLE_SESSION_SECONDS + 1)
    assert codec.verify(token) is None

    clock.now = _START + timedelta(seconds=IDLE_SESSION_SECONDS - 60)
    near_expiry = codec.verify(token)
    assert near_expiry is not None
    refreshed, refreshed_expiry = codec.refresh(near_expiry)

    assert refreshed != token
    assert refreshed_expiry == clock.now + timedelta(seconds=IDLE_SESSION_SECONDS)
    clock.advance(IDLE_SESSION_SECONDS - 1)
    assert codec.verify(token) is None
    assert codec.verify(refreshed) is not None


def test_absolute_window_caps_every_refresh() -> None:
    clock = _Clock(_START)
    codec = _codec(clock)
    token, expires_at = codec.issue("ops", password_epoch=1)
    assert expires_at == _START + timedelta(seconds=IDLE_SESSION_SECONDS)

    for _ in range(12):
        clock.advance(IDLE_SESSION_SECONDS - 2)
        ticket = codec.verify(token)
        assert ticket is not None
        token, expires_at = codec.refresh(ticket)

    assert expires_at == _START + timedelta(seconds=ABSOLUTE_SESSION_SECONDS)

    clock.now = _START + timedelta(seconds=ABSOLUTE_SESSION_SECONDS + 1)
    assert codec.verify(token) is None


def test_key_file_is_private_and_survives_a_reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_path = tmp_path / "state" / "admin-auth.key"
    key_path.parent.mkdir(parents=True)
    monkeypatch.setenv(KEY_PATH_ENV, str(key_path))
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "state" / "admin-auth.sqlite3"))
    clock = _Clock(_START)

    first = SessionCodec.from_environment(clock=clock)
    token, _ = first.issue("ops", password_epoch=1)

    assert key_path.is_file()
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert len(key_path.read_bytes()) == 32

    reloaded = SessionCodec.from_environment(clock=clock)
    assert reloaded.verify(token) is not None


def test_authentication_requires_an_existing_account_with_the_same_epoch(tmp_path: Path) -> None:
    clock = _Clock(_START)
    codec = _codec(clock)
    store = _store(tmp_path)

    live, _ = codec.issue("ops", password_epoch=store.account("ops").password_epoch)  # type: ignore[union-attr]
    stale, _ = codec.issue("ops", password_epoch=7)
    ghost, _ = codec.issue("ghost", password_epoch=1)

    assert authenticate(live, codec=codec, store=store) is not None
    assert authenticate(stale, codec=codec, store=store) is None
    assert authenticate(ghost, codec=codec, store=store) is None
    assert authenticate(None, codec=codec, store=store) is None

    store.set_password("ops", "another-scratch-password")
    assert authenticate(live, codec=codec, store=store) is None
    store.close()


def test_cookie_ranks_secure_only_behind_https() -> None:
    expires_at = _START + timedelta(seconds=IDLE_SESSION_SECONDS)

    plain = render_session_cookie("token.value", secure=False, expires_at=expires_at)
    secure = render_session_cookie("token.value", secure=True, expires_at=expires_at)

    assert plain.startswith(f"{SESSION_COOKIE}=token.value")
    assert "HttpOnly" in plain
    assert "SameSite=Lax" in plain
    assert "Path=/" in plain
    assert "Max-Age=" in plain
    assert "Secure" not in plain
    assert "Secure" in secure

    cleared = clear_session_cookie(secure=False)
    assert cleared.startswith(f"{SESSION_COOKIE}=")
    assert "Max-Age=0" in cleared


def test_request_is_https_follows_the_forwarded_proto() -> None:
    assert request_is_https(_request({})) is False
    assert request_is_https(_request({"X-Forwarded-Proto": "https"})) is True
    assert request_is_https(_request({"X-Forwarded-Proto": "http"})) is False
    assert request_is_https(_request({}, scheme="https")) is True
