"""R4 — the eight auth endpoints over the app: login, logout, me, password, accounts.

Fixture source: TestClient over a scratch credential store in ``tmp_path``.
Passwords are fixture-generated scratch values and are never printed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import secrets

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.services.admin_auth import (
    DB_PATH_ENV,
    KEY_PATH_ENV,
    AdminAuthStore,
    AdminLoginThrottle,
)
from backend.services.admin_session import SESSION_COOKIE, issue_session


_LOGIN = "/api/auth/login"
_LOGOUT = "/api/auth/logout"
_ME = "/api/auth/me"
_PASSWORD = "/api/auth/password"
_ACCOUNTS = "/api/auth/accounts"

_OPERATOR = "ops"


def _scratch_password() -> str:
    return secrets.token_urlsafe(12)


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[AdminAuthStore]:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "admin-auth.sqlite3"))
    monkeypatch.setenv(KEY_PATH_ENV, str(tmp_path / "admin-auth.key"))
    instance = AdminAuthStore(tmp_path / "admin-auth.sqlite3")
    yield instance
    instance.close()


@pytest.fixture()
def password() -> str:
    return _scratch_password()


@pytest.fixture()
def operator(store: AdminAuthStore, password: str) -> str:
    store.create_account(_OPERATOR, password)
    return _OPERATOR


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def fresh_login_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The login limiter is process-wide by design; each test needs its own."""

    from backend.api import admin_auth as admin_auth_api

    monkeypatch.setattr(admin_auth_api, "_LOGIN_LIMITER", AdminLoginThrottle())


def _login(client: TestClient, password: str, username: str = _OPERATOR):
    return client.post(_LOGIN, json={"username": username, "password": password})


def _logged_in(client: TestClient, password: str) -> None:
    response = _login(client, password)
    assert response.status_code == 200, response.text


def _actions(store: AdminAuthStore, action: str) -> list[str]:
    return [record.result for record in store.audit_records(action=action)]


def test_login_issues_a_session_cookie_and_audits_success(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    response = _login(client, password)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == _OPERATOR
    assert body["role"] == "admin"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" not in cookie
    assert password not in response.text
    assert _actions(store, "login") == ["ok"]


def test_login_over_https_adds_the_secure_flag(
    client: TestClient, operator: str, password: str
) -> None:
    response = client.post(
        _LOGIN,
        json={"username": _OPERATOR, "password": password},
        headers={"X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 200, response.text
    assert "Secure" in response.headers["set-cookie"]


def test_wrong_password_is_refused_and_audited(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    response = _login(client, password + "-wrong")

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"
    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")
    assert _actions(store, "login") == ["fail"]
    assert password not in response.text


def test_five_failures_lock_the_pair_even_for_the_right_password(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    for _ in range(5):
        assert _login(client, password + "-wrong").status_code == 401

    refused = _login(client, password)

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "60"
    assert refused.json()["detail"]["error"] == "locked"
    assert refused.json()["detail"]["retry_after_seconds"] == 60
    assert _actions(store, "login") == ["fail"] * 5 + ["locked"]


def test_me_reports_the_session_and_refuses_anonymous(
    client: TestClient, operator: str, password: str
) -> None:
    anonymous = client.get(_ME)
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "authentication_required"

    _logged_in(client, password)
    response = client.get(_ME)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == _OPERATOR
    assert body["role"] == "admin"
    assert body["expires_at"]


def test_logout_clears_the_cookie_and_audits(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)

    response = client.post(_LOGOUT)

    assert response.status_code == 200
    assert response.json()["username"] == _OPERATOR
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f"{SESSION_COOKIE}=") and "Max-Age=0" in cleared
    assert client.get(_ME).status_code == 401
    assert _actions(store, "logout") == ["ok"]


def test_password_change_kills_prior_sessions_and_keeps_the_caller(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)
    prior_cookie = client.cookies.get(SESSION_COOKIE)
    replacement = _scratch_password()

    response = client.post(_PASSWORD, json={"current_password": password, "new_password": replacement})

    assert response.status_code == 200, response.text
    assert password not in response.text
    assert replacement not in response.text
    assert store.account(_OPERATOR).password_epoch == 2  # type: ignore[union-attr]

    replayed = TestClient(app, raise_server_exceptions=False)
    replayed.cookies.set(SESSION_COOKIE, prior_cookie, domain="testserver.local", path="/")
    assert replayed.get(_ME).status_code == 401

    assert client.get(_ME).status_code == 200
    assert store.verify_credentials(_OPERATOR, replacement) is True
    assert _actions(store, "password_change") == ["ok"]


def test_password_change_requires_the_current_password_and_a_long_new_one(
    client: TestClient, operator: str, password: str
) -> None:
    _logged_in(client, password)
    replacement = _scratch_password()

    wrong = client.post(
        _PASSWORD, json={"current_password": password + "-wrong", "new_password": replacement}
    )
    too_short = client.post(_PASSWORD, json={"current_password": password, "new_password": "short"})

    assert wrong.status_code == 403
    assert too_short.status_code == 422
    assert client.get(_ME).status_code == 200


def test_account_listing_never_carries_password_material(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    store.create_account("ops2", _scratch_password())
    _logged_in(client, password)

    response = client.get(_ACCOUNTS)

    assert response.status_code == 200
    usernames = [entry["username"] for entry in response.json()["accounts"]]
    assert usernames == ["ops", "ops2"]
    assert all(entry["role"] == "admin" for entry in response.json()["accounts"])
    assert "password_hash" not in response.text
    assert "password_salt" not in response.text
    row = store.account(_OPERATOR)
    assert row is not None
    assert row.password_epoch == 1


def test_accounts_can_be_created_and_logged_in_with(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)

    created = client.post(_ACCOUNTS, json={"username": "ops2"})

    assert created.status_code == 201, created.text
    generated = created.json()["password"]
    assert isinstance(generated, str) and len(generated) == 16
    assert [entry["username"] for entry in client.get(_ACCOUNTS).json()["accounts"]] == [
        "ops",
        "ops2",
    ]

    newcomer = TestClient(app, raise_server_exceptions=False)
    assert newcomer.post(_LOGIN, json={"username": "ops2", "password": generated}).status_code == 200
    assert _actions(store, "account_create") == ["ok"]


def test_duplicate_account_and_weak_password_are_refused(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)

    duplicate = client.post(_ACCOUNTS, json={"username": _OPERATOR, "password": _scratch_password()})

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "account_exists"
    assert len(store.accounts()) == 1


def test_deleted_account_loses_access_and_the_last_account_is_guarded(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)
    store.create_account("ops2", _scratch_password())
    victim = TestClient(app, raise_server_exceptions=False)
    victim.cookies.set(
        SESSION_COOKIE, issue_session("ops2")[0], domain="testserver.local", path="/"
    )
    assert victim.get(_ME).status_code == 200

    deleted = client.delete(f"{_ACCOUNTS}/ops2")

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == "ops2"
    assert victim.get(_ME).status_code == 401
    assert victim.post(_LOGIN, json={"username": "ops2", "password": password}).status_code == 401
    assert [entry["username"] for entry in client.get(_ACCOUNTS).json()["accounts"]] == ["ops"]

    guarded = client.delete(f"{_ACCOUNTS}/ops")
    assert guarded.status_code == 409
    assert guarded.json()["detail"] == "last_account"
    assert _actions(store, "account_delete") == ["ok", "fail"]


def test_administrator_can_reset_another_password_and_the_reset_session_dies(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)
    member_password = _scratch_password()
    store.create_account("ops2", member_password)
    member = TestClient(app, raise_server_exceptions=False)
    assert member.post(_LOGIN, json={"username": "ops2", "password": member_password}).status_code == 200

    replacement = _scratch_password()
    reset = client.post(f"{_ACCOUNTS}/ops2/password", json={"password": replacement})

    assert reset.status_code == 200, reset.text
    assert reset.json()["password"] is None
    assert replacement not in reset.text
    assert member.get(_ME).status_code == 401
    assert store.verify_credentials("ops2", replacement) is True
    assert _actions(store, "password_reset") == ["ok"]


def test_generated_reset_password_is_returned_exactly_once(
    client: TestClient, store: AdminAuthStore, operator: str, password: str
) -> None:
    _logged_in(client, password)
    store.create_account("ops2", _scratch_password())

    reset = client.post(f"{_ACCOUNTS}/ops2/password", json={})

    assert reset.status_code == 200, reset.text
    generated = reset.json()["password"]
    assert isinstance(generated, str) and len(generated) == 16
    assert store.verify_credentials("ops2", generated) is True
    assert generated not in client.get(_ACCOUNTS).text


def test_account_endpoints_refuse_an_anonymous_caller(client: TestClient, store: AdminAuthStore) -> None:
    store.create_account(_OPERATOR, _scratch_password())

    assert client.get(_ACCOUNTS).status_code == 401
    assert client.post(_ACCOUNTS, json={"username": "ops2"}).status_code == 401
    assert client.delete(f"{_ACCOUNTS}/{_OPERATOR}").status_code == 401
    assert client.post(_PASSWORD, json={"new_password": "abcdefgh"}).status_code == 401
    assert store.accounts()[0].password_epoch == 1
