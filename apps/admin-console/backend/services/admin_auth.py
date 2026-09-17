"""Administrator credential store, seeding, and login throttling.

One SQLite database in the serving state directory carries the console accounts
and their audit trail; a stored password is only ever a salted ``scrypt`` hash.
The database, its signing-key neighbour, and the first-boot password file are
private (0600) because a leaked store is a leaked console.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Any

SCHEMA_VERSION = "canonical-v2-admin-auth-v1"
DB_PATH_ENV = "CANONICAL_V2_ADMIN_AUTH_DB"
KEY_PATH_ENV = "CANONICAL_V2_ADMIN_AUTH_KEY"
INITIAL_PASSWORD_ENV = "CANONICAL_V2_ADMIN_INITIAL_PASSWORD"
ACCESS_LOG_PATH_ENV = "CANONICAL_V2_ACCESS_LOG_DB"

DB_FILENAME = "admin-auth.sqlite3"
KEY_FILENAME = "admin-auth.key"
PASSWORD_FILENAME = "admin-initial-password.txt"
# Local single-machine serving state directory (deploy/README.md); only reached
# when neither the auth nor the access-log path is configured for the process.
DEFAULT_STATE_DIR = Path("/var/tmp/mirothinker-canonical-v2-s12f")
DEFAULT_ADMIN_USERNAME = "admin"

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
GENERATED_PASSWORD_LENGTH = 16
USERNAME_MAX_LENGTH = 64

_SALT_BYTES = 16
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
# Ambiguous glyphs (l/1/I, o/0/O) are left out: these passwords get typed by hand.
_GENERATED_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_epoch INTEGER NOT NULL DEFAULT 1,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    source_ip TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class AdminAuthError(RuntimeError):
    """Raised for invalid credential-store operations."""


class DuplicateAccountError(AdminAuthError):
    """The username is already taken."""


class InvalidPasswordError(AdminAuthError):
    """The submitted password does not satisfy the console policy."""


class AccountNotFoundError(AdminAuthError):
    """No account carries that username."""


class LastAccountError(AdminAuthError):
    """Deleting this account would leave the console without an administrator."""


@dataclass(frozen=True, slots=True)
class Account:
    username: str
    role: str
    password_epoch: int
    created_at: str
    updated_at: str

    def as_public_dict(self) -> dict[str, Any]:
        """Account fields safe to hand to the page (never hash material)."""

        return {
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: int
    at: str
    actor: str
    action: str
    target: str
    source_ip: str
    result: str
    detail: str | None


def default_db_path(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the credential database path for one process environment."""

    values = os.environ if environ is None else environ
    override = (values.get(DB_PATH_ENV) or "").strip()
    if override:
        return Path(override)
    access_log = (values.get(ACCESS_LOG_PATH_ENV) or "").strip()
    if access_log:
        return Path(access_log).parent / DB_FILENAME
    return DEFAULT_STATE_DIR / DB_FILENAME


def default_key_path(
    environ: Mapping[str, str] | None = None, *, db_path: Path | None = None
) -> Path:
    """Resolve the session signing-key path (beside the database by default)."""

    values = os.environ if environ is None else environ
    override = (values.get(KEY_PATH_ENV) or "").strip()
    if override:
        return Path(override)
    return (db_path or default_db_path(values)).parent / KEY_FILENAME


def generate_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(_GENERATED_ALPHABET) for _ in range(length))


def hash_password(password: str, *, salt: bytes | None = None) -> tuple[str, str]:
    """Return ``(password_hash, password_salt)`` as lowercase hex."""

    _require_password(password)
    material = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=material,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return digest.hex(), material.hex()


def verify_password(password: str, *, password_hash: str, salt: str) -> bool:
    """Constant-time verification; a malformed stored hash never raises out."""

    if not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        material = bytes.fromhex(salt)
        expected = bytes.fromhex(password_hash)
    except ValueError:
        return False
    if not material or not expected:
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=material,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    # A stored digest of any other length is a corrupt row, not a match.
    return len(expected) == _SCRYPT_DKLEN and hmac.compare_digest(digest, expected)


def _require_password(password: str) -> str:
    if not isinstance(password, str) or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"password must be {MIN_PASSWORD_LENGTH}..{MAX_PASSWORD_LENGTH} characters"
        )
    return password


def _require_username(username: str) -> str:
    if not isinstance(username, str):
        raise AdminAuthError("username must be a string")
    cleaned = username.strip()
    if not cleaned or len(cleaned) > USERNAME_MAX_LENGTH or any(char.isspace() for char in cleaned):
        raise AdminAuthError(f"username must be 1..{USERNAME_MAX_LENGTH} non-space characters")
    return cleaned


def prepare_private_file(path: Path) -> Path:
    """Create the file 0600 if absent and refuse symlinked/hard-linked targets."""

    if not path.name:
        raise OSError("credential path must name a file")
    parent = path.parent
    if not parent.is_dir():
        raise OSError("credential parent directory does not exist")
    try:
        os.lstat(path)
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)
    if path.is_symlink() or not path.is_file():
        raise OSError("credential path must be a regular file")
    if os.lstat(path).st_nlink != 1:
        raise OSError("credential path must not be hard-linked")
    os.chmod(path, 0o600, follow_symlinks=False)
    return path


class AdminAuthStore:
    """Owns one SQLite database of console accounts and their audit trail."""

    def __init__(
        self,
        path: str | Path,
        *,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = prepare_private_file(Path(path))
        self._environ = os.environ if environ is None else environ
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self._path, check_same_thread=False, timeout=30.0
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._initialize_schema()

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(_DDL)
            row = self._connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?)",
                    ("schema_version", SCHEMA_VERSION),
                )
            elif row["value"] != SCHEMA_VERSION:
                raise sqlite3.Error(
                    f"admin-auth schema version differs from {SCHEMA_VERSION}: {row['value']}"
                )

    # -- accounts ---------------------------------------------------------

    def accounts(self) -> list[Account]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT username, role, password_epoch, created_at, updated_at"
                " FROM accounts ORDER BY username"
            ).fetchall()
        return [self._account(row) for row in rows]

    def account(self, username: str) -> Account | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT username, role, password_epoch, created_at, updated_at"
                " FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
        return None if row is None else self._account(row)

    @staticmethod
    def _account(row: sqlite3.Row) -> Account:
        return Account(
            username=row["username"],
            role=row["role"],
            password_epoch=row["password_epoch"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_account(self, username: str, password: str, *, role: str = "admin") -> Account:
        cleaned = _require_username(username)
        _require_password(password)
        password_hash, salt = hash_password(password)
        now = self._now()
        with self._lock, self._connection:
            if (
                self._connection.execute(
                    "SELECT 1 FROM accounts WHERE username = ?", (cleaned,)
                ).fetchone()
                is not None
            ):
                raise DuplicateAccountError(f"account already exists: {cleaned}")
            self._connection.execute(
                "INSERT INTO accounts"
                " (username, password_hash, password_salt, password_epoch, role,"
                "  created_at, updated_at)"
                " VALUES (?, ?, ?, 1, ?, ?, ?)",
                (cleaned, password_hash, salt, role, now, now),
            )
        created = self.account(cleaned)
        assert created is not None
        return created

    def delete_account(self, username: str) -> Account:
        cleaned = _require_username(username)
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT username, role, password_epoch, created_at, updated_at"
                " FROM accounts WHERE username = ?",
                (cleaned,),
            ).fetchone()
            if row is None:
                raise AccountNotFoundError(f"account not found: {cleaned}")
            if (
                self._connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] < 2
            ):
                raise LastAccountError("the last administrator account cannot be deleted")
            self._connection.execute("DELETE FROM accounts WHERE username = ?", (cleaned,))
        return self._account(row)

    def set_password(self, username: str, password: str) -> Account:
        cleaned = _require_username(username)
        _require_password(password)
        password_hash, salt = hash_password(password)
        now = self._now()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT password_epoch FROM accounts WHERE username = ?", (cleaned,)
            ).fetchone()
            if row is None:
                raise AccountNotFoundError(f"account not found: {cleaned}")
            self._connection.execute(
                "UPDATE accounts SET password_hash = ?, password_salt = ?,"
                " password_epoch = password_epoch + 1, updated_at = ? WHERE username = ?",
                (password_hash, salt, now, cleaned),
            )
        updated = self.account(cleaned)
        assert updated is not None
        return updated

    def verify_credentials(self, username: str, password: str) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT password_hash, password_salt FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return False
        return verify_password(
            password, password_hash=row["password_hash"], salt=row["password_salt"]
        )

    # -- audit ------------------------------------------------------------

    def append_audit(
        self,
        *,
        actor: str,
        action: str,
        target: str = "",
        source_ip: str = "",
        result: str = "ok",
        detail: str | None = None,
    ) -> AuditRecord:
        at = self._now()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO audit (at, actor, action, target, source_ip, result, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (at, actor, action, target, source_ip, result, detail),
            )
            audit_id = int(cursor.lastrowid or 0)
        return AuditRecord(
            id=audit_id,
            at=at,
            actor=actor,
            action=action,
            target=target,
            source_ip=source_ip,
            result=result,
            detail=detail,
        )

    def audit_records(
        self, *, action: str | None = None, limit: int | None = None
    ) -> list[AuditRecord]:
        sql = (
            "SELECT id, at, actor, action, target, source_ip, result, detail FROM audit"
        )
        params: list[Any] = []
        if action is not None:
            sql += " WHERE action = ?"
            params.append(action)
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._lock:
            rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [
            AuditRecord(
                id=row["id"],
                at=row["at"],
                actor=row["actor"],
                action=row["action"],
                target=row["target"],
                source_ip=row["source_ip"],
                result=row["result"],
                detail=row["detail"],
            )
            for row in rows
        ]

    # -- first boot -------------------------------------------------------

    def seed_initial_admin(
        self,
        *,
        password: str | None = None,
        username: str = DEFAULT_ADMIN_USERNAME,
        announce: Callable[[str], None] | None = None,
    ) -> str | None:
        """Seed exactly one administrator on an empty store; idempotent afterwards.

        The password is announced once (stdout by default) and written once to a
        0600 file next to the database, because the operator has to be able to
        read it after the first boot.
        """

        if self.accounts():
            return None
        initial = password or (self._environ.get(INITIAL_PASSWORD_ENV) or "").strip()
        seeded = initial or generate_password()
        self.create_account(username, seeded)
        announce = print if announce is None else announce
        announce(
            f"[admin-auth] first-boot administrator '{username}' password: {seeded}"
        )
        password_file = self._path.parent / PASSWORD_FILENAME
        prepare_private_file(password_file)
        password_file.write_text(seeded + "\n", encoding="utf-8")
        os.chmod(password_file, 0o600)
        return seeded

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()


@lru_cache(maxsize=8)
def _cached_store(path: str) -> AdminAuthStore:
    return AdminAuthStore(path)


def store_from_environment(environ: Mapping[str, str] | None = None) -> AdminAuthStore:
    """Return the process-wide store for the environment-named database."""

    return _cached_store(str(default_db_path(environ)))


@dataclass(frozen=True, slots=True)
class LoginDecision:
    """What the next login attempt for one username+client pair may do."""

    allowed: bool
    retry_after_seconds: int
    remaining_attempts: int


class AdminLoginThrottle:
    """Per-key login lockout: 5 failures lock 60 s, doubling up to 30 minutes."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        lock_seconds: float = 60.0,
        max_lock_seconds: float = 1800.0,
        clock: Callable[[], float] | None = None,
        max_keys: int = 2048,
    ) -> None:
        self.max_failures = int(max_failures)
        self.lock_seconds = float(lock_seconds)
        self.max_lock_seconds = float(max_lock_seconds)
        self._clock = clock or time.monotonic
        self._max_keys = int(max_keys)
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._lockouts: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def check(self, key: str) -> LoginDecision:
        now = self._clock()
        with self._lock:
            return self._decision(key, now)

    def _expire(self, key: str, now: float) -> bool:
        """Drop a finished lockout; report whether the key is locked right now."""

        locked_until = self._locked_until.get(key, 0.0)
        if locked_until > now:
            return True
        if locked_until:
            self._locked_until.pop(key, None)
            self._failures.pop(key, None)
        return False

    def _decision(self, key: str, now: float) -> LoginDecision:
        if self._expire(key, now):
            locked_until = self._locked_until[key]
            return LoginDecision(
                allowed=False,
                retry_after_seconds=max(1, int(locked_until - now + 0.999)),
                remaining_attempts=0,
            )
        failures = self._failures.get(key, 0)
        return LoginDecision(
            allowed=True,
            retry_after_seconds=0,
            remaining_attempts=max(0, self.max_failures - failures),
        )

    def record_failure(self, key: str) -> LoginDecision:
        """Record one failed attempt and report what the next attempt may do."""

        now = self._clock()
        with self._lock:
            if self._expire(key, now):
                return self._decision(key, now)
            if len(self._failures) > self._max_keys:
                self._failures.clear()
                self._lockouts.clear()
                self._locked_until.clear()
            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            if failures < self.max_failures:
                return self._decision(key, now)
            lockouts = self._lockouts.get(key, 0)
            duration = min(self.lock_seconds * (2**lockouts), self.max_lock_seconds)
            self._lockouts[key] = lockouts + 1
            self._locked_until[key] = now + duration
            self._failures[key] = 0
            return self._decision(key, now)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


__all__ = [
    "Account",
    "AccountNotFoundError",
    "AdminAuthError",
    "AdminAuthStore",
    "AdminLoginThrottle",
    "AuditRecord",
    "DB_PATH_ENV",
    "DEFAULT_ADMIN_USERNAME",
    "DuplicateAccountError",
    "INITIAL_PASSWORD_ENV",
    "InvalidPasswordError",
    "KEY_PATH_ENV",
    "LastAccountError",
    "LoginDecision",
    "PASSWORD_FILENAME",
    "prepare_private_file",
    "SCHEMA_VERSION",
    "default_db_path",
    "default_key_path",
    "generate_password",
    "hash_password",
    "store_from_environment",
    "verify_password",
]
