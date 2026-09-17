"""R5 — the gate: page 302 / API 401, public surface untouched, same-origin writes.

Fixture source: TestClient over the shell app with a scratch credential store.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_admin_config import get_managed_settings_store
from backend.main import app
from backend.services.admin_auth import DB_PATH_ENV, KEY_PATH_ENV, AdminAuthStore
from backend.services.admin_session import SESSION_COOKIE, issue_session
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore


_PAGES = ("/admin", "/logs", "/browse", "/jobs", "/upload", "/seeds")
_STATUS_API = "/api/canonical-v2/admin/system-status"
_CONFIG_API = "/api/canonical-v2/admin/config"
_OPERATOR = "ops"
_FORGED = "boss"


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[AdminAuthStore]:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "admin-auth.sqlite3"))
    monkeypatch.setenv(KEY_PATH_ENV, str(tmp_path / "admin-auth.key"))
    instance = AdminAuthStore(tmp_path / "admin-auth.sqlite3")
    instance.create_account(_OPERATOR, "scratch-password-one")
    yield instance
    instance.close()


@pytest.fixture()
def settings(tmp_path: Path) -> Iterator[ManagedSettingsStore]:
    instance = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    app.dependency_overrides[get_managed_settings_store] = lambda: instance
    try:
        yield instance
    finally:
        app.dependency_overrides.pop(get_managed_settings_store, None)


@pytest.fixture()
def anonymous() -> TestClient:
    return TestClient(app, raise_server_exceptions=False, follow_redirects=False)


@pytest.fixture()
def signed_in(store: AdminAuthStore) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    client.cookies.set(SESSION_COOKIE, issue_session(_OPERATOR)[0], domain="testserver.local", path="/")
    return client


@pytest.mark.parametrize("page", _PAGES)
def test_every_admin_page_redirects_an_anonymous_visitor(page: str, anonymous: TestClient) -> None:
    response = anonymous.get(page)

    assert response.status_code == 302
    assert response.headers["location"] == "/main"
    assert "<html" not in response.text


def test_gated_api_refuses_an_anonymous_caller() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(_STATUS_API)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
    assert "providers" not in response.text


def test_public_surface_stays_open(anonymous: TestClient) -> None:
    assert anonymous.get("/api/health").json() == {"status": "ok"}
    assert anonymous.get("/main").status_code == 200
    assert anonymous.get("/chat").status_code == 200
    assert anonymous.get("/static/assets/guoxian-logo.jpg").status_code == 200
    assert anonymous.get("/static/nav_auth.js").status_code == 200
    chat = anonymous.post("/api/chat", json={"query": "深圳有哪些机器人企业"})
    assert chat.status_code != 401
    assert "authentication_required" not in chat.text


def test_public_root_still_enters_chat(anonymous: TestClient) -> None:
    response = anonymous.get("/")

    assert response.status_code == 302
    assert response.headers["location"] == "/chat"


def test_a_session_reaches_the_pages_and_the_admin_api(signed_in: TestClient) -> None:
    assert signed_in.get("/logs").status_code == 200
    assert signed_in.get("/browse").status_code == 200
    assert signed_in.get("/admin").status_code == 200

    status = signed_in.get(_STATUS_API)
    assert status.status_code == 200
    assert "canonical_v2" in status.text or "release" in status.text


def test_cross_site_writes_are_refused(signed_in: TestClient, settings: ManagedSettingsStore) -> None:
    body = {"paths": {"access_log_retention_days": 30}}

    foreign_origin = signed_in.patch(_CONFIG_API, json=body, headers={"Origin": "https://evil.example"})
    cross_site = signed_in.patch(_CONFIG_API, json=body, headers={"Sec-Fetch-Site": "cross-site"})
    same_site = signed_in.patch(_CONFIG_API, json=body, headers={"Sec-Fetch-Site": "same-site"})

    assert foreign_origin.status_code == 403
    assert cross_site.status_code == 403
    assert same_site.status_code == 403
    assert list(settings.audit_records()) == []


def test_same_origin_and_headerless_writes_are_allowed(
    signed_in: TestClient, settings: ManagedSettingsStore
) -> None:
    same_origin = signed_in.patch(
        _CONFIG_API,
        json={"paths": {"access_log_retention_days": 31}},
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    )
    cli = signed_in.patch(_CONFIG_API, json={"paths": {"access_log_retention_days": 32}})

    assert same_origin.status_code == 200, same_origin.text
    assert cli.status_code == 200, cli.text


def test_cross_site_writes_are_refused_even_without_a_session(anonymous: TestClient) -> None:
    response = anonymous.post(
        "/api/auth/login",
        json={"username": _OPERATOR, "password": "scratch-password-one"},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


def test_a_forged_remote_user_header_cannot_impersonate(
    signed_in: TestClient, settings: ManagedSettingsStore
) -> None:
    response = signed_in.patch(
        _CONFIG_API,
        json={"paths": {"access_log_retention_days": 33}},
        headers={"X-Remote-User": _FORGED},
    )

    assert response.status_code == 200, response.text
    records = settings.audit_records()
    assert [record["operator"] for record in records] == [_OPERATOR]
    assert _FORGED not in json.dumps(records)


def test_chat_turns_are_logged_as_anonymous_on_the_public_path() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/chat/feedback",
        json={"session_id": "session:gate", "rating": "up"},
        headers={"X-Remote-User": _FORGED},
    )

    assert response.status_code != 401


def test_gate_reads_only_the_environment_named_store(
    store: AdminAuthStore, tmp_path: Path
) -> None:
    assert store.path == tmp_path / "admin-auth.sqlite3"
    assert os.environ[DB_PATH_ENV] == str(store.path)
