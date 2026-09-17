"""R6 — the console shell: `/main` login form vs dashboard, shared nav markers.

Fixture source: TestClient over the shell app with a scratch credential store.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.services.admin_auth import DB_PATH_ENV, KEY_PATH_ENV, AdminAuthStore
from backend.services.admin_session import SESSION_COOKIE, issue_session


_OPERATOR = "ops"
_PAGES = ("/admin", "/logs", "/browse", "/jobs", "/upload", "/seeds")
_QUICK_LINKS = ("/admin", "/logs", "/browse", "/jobs", "/upload", "/seeds", "/chat")


@pytest.fixture()
def auth_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[AdminAuthStore]:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "admin-auth.sqlite3"))
    monkeypatch.setenv(KEY_PATH_ENV, str(tmp_path / "admin-auth.key"))
    instance = AdminAuthStore(tmp_path / "admin-auth.sqlite3")
    instance.create_account(_OPERATOR, "scratch-password-one")
    yield instance
    instance.close()


def _client(signed_in: bool) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    if signed_in:
        client.cookies.set(
            SESSION_COOKIE, issue_session(_OPERATOR)[0], domain="testserver.local", path="/"
        )
    return client


def test_anonymous_main_shows_the_login_form_only(auth_state: AdminAuthStore) -> None:
    response = _client(False).get("/main")

    assert response.status_code == 200
    document = response.text
    assert 'id="login-form"' in document
    assert 'data-admin-user=""' in document
    assert 'action="/api/auth/login"' in document or 'id="login-submit"' in document
    assert _OPERATOR not in document
    assert "系统状态" in document


def test_authenticated_main_shows_the_dashboard_markers(auth_state: AdminAuthStore) -> None:
    response = _client(True).get("/main")

    assert response.status_code == 200
    document = response.text
    assert f'data-admin-user="{_OPERATOR}"' in document
    assert 'id="dashboard"' in document
    assert 'id="status-card"' in document
    assert 'id="account-area"' in document
    assert 'id="logout-button"' in document
    for link in _QUICK_LINKS:
        assert f'href="{link}"' in document


def test_main_assets_are_served_and_carry_the_session_calls() -> None:
    client = _client(False)

    script = client.get("/static/main.js")
    style = client.get("/static/main.css")

    assert script.status_code == 200
    assert "/api/auth/me" in script.text
    assert "/api/auth/login" in script.text
    assert "/api/auth/logout" in script.text
    assert "/api/auth/password" in script.text
    assert "/api/auth/accounts" in script.text
    assert "/api/canonical-v2/admin/system-status" in script.text
    assert style.status_code == 200
    assert ".topbar" in style.text


@pytest.mark.parametrize("page", _PAGES)
def test_every_admin_page_nav_carries_the_session_markers(
    page: str, auth_state: AdminAuthStore
) -> None:
    response = _client(True).get(page)

    assert response.status_code == 200
    document = response.text
    assert '<a href="/main"' in document
    assert 'id="admin-user"' in document
    assert 'id="logout-button"' in document
    assert '<script src="/static/nav_auth.js"' in document


def test_nav_script_fetches_the_identity_and_logs_out() -> None:
    response = _client(False).get("/static/nav_auth.js")

    assert response.status_code == 200
    assert "/api/auth/me" in response.text
    assert "/api/auth/logout" in response.text
    assert "admin-user" in response.text
