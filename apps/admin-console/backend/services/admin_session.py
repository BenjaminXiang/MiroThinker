"""Signed-cookie sessions for the admin console, and the request identity.

The cookie carries username / issued-at / expiry / password epoch and is signed
with an HMAC-SHA256 key kept in a 0600 file beside the credential database, so
sessions survive a restart while a password change or account deletion kills
every cookie that accounts still holds.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
import hashlib
import hmac
import json
import os
import secrets

from fastapi import Request

from backend.services.admin_auth import (
    AccountNotFoundError,
    AdminAuthStore,
    default_key_path,
    prepare_private_file,
    store_from_environment,
)

SESSION_COOKIE = "cv2_admin_session"
IDLE_SESSION_SECONDS = 3600
ABSOLUTE_SESSION_SECONDS = 12 * 3600
SESSION_KEY_BYTES = 32

_PAYLOAD_KEYS = ("u", "iat", "exp", "ep")


@dataclass(frozen=True, slots=True)
class SessionTicket:
    """One verified session as it arrived on a request."""

    username: str
    password_epoch: int
    issued_at: datetime
    expires_at: datetime


class SessionCodec:
    """Signs and verifies the session cookie for one signing key."""

    def __init__(self, key: bytes, *, clock: Callable[[], datetime] | None = None) -> None:
        if len(key) < SESSION_KEY_BYTES:
            raise ValueError("session signing key must be at least 32 bytes")
        self._key = key
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> SessionCodec:
        return cls(load_signing_key(environ), clock=clock)

    def issue(self, username: str, *, password_epoch: int) -> tuple[str, datetime]:
        issued_at = self._now()
        expires_at = self._expiry(issued_at, issued_at)
        return self._sign(username, issued_at, expires_at, password_epoch), expires_at

    def refresh(self, ticket: SessionTicket) -> tuple[str, datetime]:
        now = self._now()
        expires_at = self._expiry(ticket.issued_at, now)
        return self._sign(ticket.username, ticket.issued_at, expires_at, ticket.password_epoch), expires_at

    def verify(self, token: str | None) -> SessionTicket | None:
        if not isinstance(token, str) or token.count(".") != 1:
            return None
        payload_part, signature_part = token.split(".")
        payload = _b64decode(payload_part)
        signature = _b64decode(signature_part)
        if payload is None or signature is None:
            return None
        if not hmac.compare_digest(signature, self._signature(payload)):
            return None
        try:
            fields = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        if not isinstance(fields, dict) or any(key not in fields for key in _PAYLOAD_KEYS):
            return None
        try:
            issued_at = datetime.fromisoformat(str(fields["iat"]))
            expires_at = datetime.fromisoformat(str(fields["exp"]))
            password_epoch = int(fields["ep"])
            username = str(fields["u"])
        except (TypeError, ValueError):
            return None
        if issued_at.tzinfo is None or expires_at.tzinfo is None:
            return None
        if not username or password_epoch < 0:
            return None
        if expires_at <= self._now():
            return None
        return SessionTicket(
            username=username,
            password_epoch=password_epoch,
            issued_at=issued_at.astimezone(UTC),
            expires_at=expires_at.astimezone(UTC),
        )

    def _expiry(self, issued_at: datetime, now: datetime) -> datetime:
        return min(
            now + timedelta(seconds=IDLE_SESSION_SECONDS),
            issued_at + timedelta(seconds=ABSOLUTE_SESSION_SECONDS),
        )

    def _sign(self, username: str, issued_at: datetime, expires_at: datetime, password_epoch: int) -> str:
        payload = json.dumps(
            {
                "u": username,
                "iat": issued_at.isoformat(),
                "exp": expires_at.isoformat(),
                "ep": password_epoch,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"{_b64encode(payload)}.{_b64encode(self._signature(payload))}"

    def _signature(self, payload: bytes) -> bytes:
        return hmac.new(self._key, payload, hashlib.sha256).digest()

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)


def load_signing_key(environ: Mapping[str, str] | None = None) -> bytes:
    """Read the signing key beside the credential database, creating it once."""

    path = default_key_path(environ)
    if not path.exists():
        prepare_private_file(path)
        path.write_bytes(secrets.token_bytes(SESSION_KEY_BYTES))
        os.chmod(path, 0o600)
    key = path.read_bytes()
    if len(key) < SESSION_KEY_BYTES:
        raise OSError("admin session signing key is too short")
    return key


def _b64encode(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes | None:
    try:
        return urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        return None


def authenticate(
    token: str | None, *, codec: SessionCodec, store: AdminAuthStore
) -> SessionTicket | None:
    """Verify the signature, the window, the account, and the password epoch."""

    ticket = codec.verify(token)
    if ticket is None:
        return None
    account = store.account(ticket.username)
    if account is None or account.password_epoch != ticket.password_epoch:
        return None
    return ticket


def issue_session(
    username: str,
    *,
    environ: Mapping[str, str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[str, datetime]:
    """Mint a session cookie value for one existing account (login's core step)."""

    store = store_from_environment(environ)
    account = store.account(username)
    if account is None:
        raise AccountNotFoundError(f"account not found: {username}")
    codec = SessionCodec.from_environment(environ, clock=clock)
    return codec.issue(username, password_epoch=account.password_epoch)


def session_ticket(
    request: Request, *, environ: Mapping[str, str] | None = None
) -> SessionTicket | None:
    """Resolve the caller's session, or None when it is absent or not valid."""

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        codec = SessionCodec.from_environment(environ)
    except OSError:
        return None
    return authenticate(token, codec=codec, store=store_from_environment(environ))


def current_operator(request: Request) -> str:
    """The acting identity of a request: the session username, else anonymous."""

    username = getattr(request.state, "admin_user", None)
    if isinstance(username, str) and username:
        return username
    return "anonymous"


def request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if forwarded:
        return forwarded == "https"
    return request.url.scheme == "https"


def request_origin(request: Request) -> str:
    """The origin this request was addressed to, for same-origin comparisons."""

    scheme = "https" if request_is_https(request) else "http"
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}".rstrip("/")


def render_session_cookie(
    token: str,
    *,
    secure: bool,
    expires_at: datetime,
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(UTC)
    max_age = max(0, int((expires_at - moment).total_seconds()))
    attributes = [
        f"{SESSION_COOKIE}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={max_age}",
        f"Expires={format_datetime(expires_at.astimezone(UTC), usegmt=True)}",
    ]
    if secure:
        attributes.append("Secure")
    return "; ".join(attributes)


def clear_session_cookie(*, secure: bool = False) -> str:
    attributes = [
        f"{SESSION_COOKIE}=",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
    ]
    if secure:
        attributes.append("Secure")
    return "; ".join(attributes)


__all__ = [
    "ABSOLUTE_SESSION_SECONDS",
    "IDLE_SESSION_SECONDS",
    "SESSION_COOKIE",
    "SESSION_KEY_BYTES",
    "SessionCodec",
    "SessionTicket",
    "authenticate",
    "clear_session_cookie",
    "current_operator",
    "issue_session",
    "load_signing_key",
    "render_session_cookie",
    "request_is_https",
    "request_origin",
    "session_ticket",
]
