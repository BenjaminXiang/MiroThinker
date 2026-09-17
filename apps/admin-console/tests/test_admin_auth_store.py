"""R1 — credential store: scrypt hashes, account CRUD, epoch bump, audit, seeding.

Fixture source: constructed store on ``tmp_path``; every password here is a
fabricated constant of the test, never a real credential.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import stat

import pytest

from backend.services.admin_auth import (
    DB_PATH_ENV,
    INITIAL_PASSWORD_ENV,
    PASSWORD_FILENAME,
    SCHEMA_VERSION,
    AccountNotFoundError,
    AdminAuthError,
    AdminAuthStore,
    DuplicateAccountError,
    InvalidPasswordError,
    LastAccountError,
    default_db_path,
    hash_password,
    verify_password,
)


_PASSWORD = "scratch-password-one"
_OTHER = "scratch-password-two"


def _store(tmp_path: Path) -> AdminAuthStore:
    return AdminAuthStore(tmp_path / "admin-auth.sqlite3")


def _rows(path: Path, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return list(connection.execute(sql, params).fetchall())
    finally:
        connection.close()


def _hashed(password: str) -> tuple[str, str]:
    return hash_password(password)


def test_default_path_follows_the_environment_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "scratch" / "admin-auth.sqlite3"
    monkeypatch.setenv(DB_PATH_ENV, str(target))

    assert default_db_path() == target


def test_store_path_is_exactly_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = default_db_path({})
    existed_before = fallback.exists()
    target = tmp_path / "scratch" / "admin-auth.sqlite3"
    target.parent.mkdir()
    monkeypatch.setenv(DB_PATH_ENV, str(target))

    store = AdminAuthStore(default_db_path())
    store.create_account("ops", _PASSWORD)
    store.close()

    assert target.is_file()
    assert fallback.exists() is existed_before


def test_created_account_stores_a_hash_and_salt_but_no_plaintext(tmp_path: Path) -> None:
    store = _store(tmp_path)
    account = store.create_account("ops", _PASSWORD)

    assert account == store.account("ops")
    assert account is not None
    assert account.role == "admin"
    assert account.password_epoch == 1
    rows = _rows(
        store.path,
        "SELECT username, password_hash, password_salt, role FROM accounts",
    )
    assert len(rows) == 1
    username, password_hash, password_salt, role = (str(value) for value in rows[0])
    assert username == "ops"
    assert password_hash and password_salt
    assert _PASSWORD not in password_hash
    assert _PASSWORD not in password_salt
    assert role == "admin"
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert _rows(store.path, "SELECT value FROM meta WHERE key = 'schema_version'") == [
        (SCHEMA_VERSION,)
    ]
    store.close()


def test_every_account_gets_its_own_salt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account("ops", _PASSWORD)
    store.create_account("ops2", _PASSWORD)

    rows = _rows(store.path, "SELECT password_hash, password_salt FROM accounts ORDER BY username")

    assert rows[0][0] != rows[1][0]
    assert rows[0][1] != rows[1][1]
    store.close()


def test_verify_password_is_constant_time_and_rejects_wrong_input() -> None:
    password_hash, salt = _hashed(_PASSWORD)

    assert verify_password(_PASSWORD, password_hash=password_hash, salt=salt) is True
    assert verify_password(_PASSWORD + "x", password_hash=password_hash, salt=salt) is False
    assert verify_password(_PASSWORD, password_hash=password_hash[:16], salt=salt) is False


def test_credentials_verify_only_against_the_stored_hash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account("ops", _PASSWORD)

    assert store.verify_credentials("ops", _PASSWORD) is True
    assert store.verify_credentials("ops", _OTHER) is False
    assert store.verify_credentials("ghost", _PASSWORD) is False
    store.close()


def test_duplicate_and_weak_passwords_are_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account("ops", _PASSWORD)

    with pytest.raises(DuplicateAccountError):
        store.create_account("ops", _OTHER)
    with pytest.raises(InvalidPasswordError):
        store.create_account("ops2", "short")
    with pytest.raises(AdminAuthError):
        store.create_account("  ", _PASSWORD)
    assert [account.username for account in store.accounts()] == ["ops"]
    store.close()


def test_set_password_bumps_the_epoch_and_keeps_the_other_accounts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account("ops", _PASSWORD)
    store.create_account("ops2", _PASSWORD)

    updated = store.set_password("ops", _OTHER)

    assert updated.password_epoch == 2
    assert store.account("ops2") is not None
    assert store.account("ops2").password_epoch == 1  # type: ignore[union-attr]
    assert store.verify_credentials("ops", _OTHER) is True
    assert store.verify_credentials("ops", _PASSWORD) is False
    with pytest.raises(AccountNotFoundError):
        store.set_password("ghost", _OTHER)
    store.close()


def test_delete_account_and_last_account_guard(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account("ops", _PASSWORD)

    with pytest.raises(LastAccountError):
        store.delete_account("ops")

    store.create_account("ops2", _OTHER)
    deleted = store.delete_account("ops")

    assert deleted.username == "ops"
    assert [account.username for account in store.accounts()] == ["ops2"]
    with pytest.raises(AccountNotFoundError):
        store.delete_account("ops")
    store.close()


def test_audit_rows_are_appended_in_order(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.append_audit(
        actor="ops",
        action="login",
        target="ops",
        source_ip="10.0.0.7",
        result="fail",
        detail="invalid_credentials",
    )
    store.append_audit(actor="ops", action="login", target="ops", source_ip="10.0.0.7", result="ok")

    records = store.audit_records(action="login")
    assert [record.result for record in records] == ["fail", "ok"]
    first = records[0]
    assert (first.actor, first.action, first.target, first.source_ip) == (
        "ops",
        "login",
        "ops",
        "10.0.0.7",
    )
    assert first.detail == "invalid_credentials"
    assert first.at.endswith("+00:00") or first.at.endswith("Z")
    assert store.audit_records(action="logout") == []
    store.close()


def test_seeding_is_idempotent_and_writes_a_private_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INITIAL_PASSWORD_ENV, _PASSWORD)
    store = _store(tmp_path)
    announced: list[str] = []

    first = store.seed_initial_admin(announce=announced.append)

    assert first == _PASSWORD
    assert len(announced) == 1
    assert _PASSWORD in announced[0]
    password_file = store.path.parent / PASSWORD_FILENAME
    assert password_file.read_text(encoding="utf-8").strip() == _PASSWORD
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600
    assert store.verify_credentials("admin", _PASSWORD) is True

    second = store.seed_initial_admin(announce=announced.append)

    assert second is None
    assert len(announced) == 1
    assert [account.username for account in store.accounts()] == ["admin"]
    store.close()


def test_seeding_without_an_override_generates_sixteen_characters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(INITIAL_PASSWORD_ENV, raising=False)
    store = _store(tmp_path)
    announced: list[str] = []

    seeded = store.seed_initial_admin(announce=announced.append)

    assert seeded is not None
    assert len(seeded) == 16
    assert store.verify_credentials("admin", seeded) is True
    store.close()


def test_seeding_respects_an_existing_account(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_account("chief", _PASSWORD)
    announced: list[str] = []

    assert store.seed_initial_admin(announce=announced.append) is None
    assert announced == []
    assert not (store.path.parent / PASSWORD_FILENAME).exists()
    store.close()
