from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_admin_config import get_managed_settings_store
from backend.main import app
from tests.conftest import TEST_ADMIN_USERNAME, authorized_client
from src.data_agents.canonical_v2.contracts import (
    GapClass,
    GapSeverity,
    GapStatus,
    KnowledgeGap,
    ReviewState,
)
from src.data_agents.canonical_v2.knowledge_gap_postgres import GapAdminPage
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore


_AS_OF = datetime(2026, 9, 7, 15, 56, 13, tzinfo=UTC)
_SECRET_SENTINEL = "sk-super-secret-sentinel-4f8e21ab"
_STORE_STATE = "canonical_v2_managed_settings_store"


class _EphemeralGapOperations:
    """The exact pack-mode shape: record/remediation only, no admin listing."""

    def record(self, signal: Any) -> Any:  # pragma: no cover - capability marker
        raise NotImplementedError

    def apply_remediation(self, request: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class _AdminGapOperations:
    def list_for_admin(self, query: Any) -> GapAdminPage:
        now = _AS_OF
        return GapAdminPage(
            items=(
                KnowledgeGap(
                    gap_id="gap:w1:test",
                    gap_class=GapClass.relationship,
                    status=GapStatus.open,
                    release_id="candidate-v2-20260819-r1",
                    affected_domains=("professor", "paper"),
                    affected_paths=("professor_attributed_to_paper",),
                    query_trace_id="query:w1",
                    answer_trace_id="answer:w1",
                    observed_symptom="missing relationship",
                    evidence_ids=("web:w1",),
                    classification_confidence=0.5,
                    review_state=ReviewState.unreviewed,
                    proposed_owner="relationship_enrichment",
                    proposed_remediation="collect_missing_relationship_evidence",
                    demand_count=1,
                    scenario_families=("query:relationship",),
                    severity=GapSeverity.medium,
                    created_at=now,
                    updated_at=now,
                ),
            ),
            total=1,
            limit=query.limit,
            offset=query.offset,
        )


class _Manifest:
    manifest_version = "canonical-v2-build-manifest-v2"
    release_id = "candidate-v2-20260819-r1"
    build_run_id = "p4-build-20260819-v1"
    created_at = _AS_OF
    manifest_sha256 = "a" * 64


def _projections() -> list[SimpleNamespace]:
    rows: list[SimpleNamespace] = []
    for domain, count in (
        ("company", 2),
        ("paper", 3),
        ("patent", 1),
        ("professor", 4),
    ):
        for index in range(count):
            rows.append(
                SimpleNamespace(
                    entity_type=domain,
                    canonical_identity_id=f"{domain}-c-{index}",
                )
            )
    return rows


def _admin_runtime(*, gap_operations: Any) -> Any:
    from backend.services.canonical_v2_admin import CanonicalV2AdminRuntime

    projections = _projections()
    return CanonicalV2AdminRuntime(
        release_id="candidate-v2-20260819-r1",
        manifest=_Manifest(),
        candidate_projection=SimpleNamespace(
            as_of=_AS_OF, public_domain_projections=tuple(projections)
        ),
        relationship_authority=SimpleNamespace(current_relationships=()),
        planner=SimpleNamespace(),
        knowledge_read=SimpleNamespace(),
        chat_adapter=SimpleNamespace(),
        gap_operations=gap_operations,
    )


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ManagedSettingsStore]:
    scratch = tmp_path / "managed" / "settings.json"
    instance = ManagedSettingsStore(scratch, environ=dict(os.environ))
    had_prior = hasattr(app.state, _STORE_STATE)
    prior = getattr(app.state, _STORE_STATE, None)
    setattr(app.state, _STORE_STATE, instance)
    app.dependency_overrides[get_managed_settings_store] = lambda: instance
    try:
        yield instance
    finally:
        app.dependency_overrides.pop(get_managed_settings_store, None)
        if had_prior:
            setattr(app.state, _STORE_STATE, prior)
        elif hasattr(app.state, _STORE_STATE):
            delattr(app.state, _STORE_STATE)


def _client() -> TestClient:
    return authorized_client(raise_server_exceptions=False)


def test_get_config_reports_defaults_and_sources(store: ManagedSettingsStore) -> None:
    response = _client().get("/api/canonical-v2/admin/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == str(store.path)
    assert payload["exists"] is False
    assert payload["settings"]["paths"]["access_log_retention_days"] == 90
    by_path = {field["path"]: field for field in payload["fields"]}
    assert by_path["paths.access_log_retention_days"]["source"] == "default"
    assert by_path["collection.enabled.company"]["editable"] is True
    assert "api_key" not in json.dumps(payload).casefold()


def test_get_patch_get_round_trip(store: ManagedSettingsStore) -> None:
    client = _client()

    patched = client.patch(
        "/api/canonical-v2/admin/config",
        json={
            "collection": {
                "enabled": {"company": False},
                "max_llm_calls_per_run": 640,
            },
            "paths": {"access_log_retention_days": 30},
        },
        headers={"X-Remote-User": "operator-li"},
    )
    assert patched.status_code == 200
    assert patched.json()["changed"] == [
        "collection.enabled.company",
        "collection.max_llm_calls_per_run",
        "paths.access_log_retention_days",
    ]

    reread = client.get("/api/canonical-v2/admin/config")
    assert reread.status_code == 200
    body = reread.json()
    assert body["exists"] is True
    assert body["settings"]["collection"]["max_llm_calls_per_run"] == 640
    assert body["settings"]["collection"]["enabled"]["company"] is False
    assert body["settings"]["paths"]["access_log_retention_days"] == 30

    records = store.audit_records()
    assert len(records) == 1
    # The identity is the signed-in operator, never the X-Remote-User header.
    assert records[0]["operator"] == TEST_ADMIN_USERNAME
    assert "operator-li" not in json.dumps(records)

    restarted = ManagedSettingsStore(store.path)
    document, _ = restarted.effective()
    assert document.collection.max_llm_calls_per_run == 640


def test_patch_without_a_session_is_refused(store: ManagedSettingsStore) -> None:
    response = TestClient(app, raise_server_exceptions=False).patch(
        "/api/canonical-v2/admin/config",
        json={"paths": {"access_log_retention_days": 44}},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
    assert store.audit_records() == ()


@pytest.mark.parametrize(
    ("body", "marker"),
    [
        ({"unknown_group": {"x": 1}}, "whitelist"),
        ({"collection": {"api_key": _SECRET_SENTINEL}}, "credential"),
        ({"collection": {"max_web_searches_per_run": "many"}}, "validation"),
        ({"collection": {"window_end_hour_utc": 3}}, "window"),
        ({}, "non-empty"),
    ],
)
def test_patch_rejects_unknown_secret_and_ill_typed_fields(
    store: ManagedSettingsStore, body: dict, marker: str
) -> None:
    response = _client().patch("/api/canonical-v2/admin/config", json=body)

    assert response.status_code == 422
    assert _SECRET_SENTINEL not in response.text
    assert marker in response.text or marker == "validation"
    assert store.exists() is False
    assert store.audit_records() == ()


def test_system_status_reports_degradable_blocks(
    store: ManagedSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANONICAL_V2_CORRECTIONS_DB", "/nonexistent/corrections.sqlite3")
    monkeypatch.delenv("CANONICAL_V2_SERVING_PACK", raising=False)
    monkeypatch.delenv("CANONICAL_V2_INDEX_ROOT", raising=False)
    monkeypatch.delenv("CANONICAL_V2_DATABASE_URL", raising=False)
    # The freshness block reads the console database (DATABASE_URL) now; a locally
    # set test name would defeat the unconfigured case this test locks.
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)

    response = _client().get("/api/canonical-v2/admin/system-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ok"
    assert payload["config"]["state"] == "ok"
    assert payload["pack"]["state"] == "unavailable"
    assert "CANONICAL_V2_SERVING_PACK" in payload["pack"]["reason"]
    assert payload["operations"]["corrections"]["state"] == "unavailable"
    assert payload["freshness"]["state"] == "ok"
    assert payload["freshness"]["collection_history"]["state"] == "unavailable"
    assert "pipeline_run" in payload["freshness"]["collection_history"]["reason"]
    assert payload["disk"]["state"] == "ok"
    for domain in ("company", "paper", "patent", "professor"):
        assert domain in payload["freshness"]["per_domain"]


def test_system_status_uses_runtime_manifest_when_installed(
    store: ManagedSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CANONICAL_V2_SERVING_PACK", raising=False)
    runtime = SimpleNamespace(
        admin_runtime=SimpleNamespace(
            manifest=SimpleNamespace(
                release_id="candidate-v2-20260819-r1",
                manifest_version="canonical-v2-build-manifest-v2",
                build_run_id="p4-build-20260819-v1",
                created_at=_AS_OF,
                manifest_sha256="b" * 64,
                published_projections=(
                    SimpleNamespace(projection_id="published:company", record_count=7089),
                    SimpleNamespace(projection_id="published:paper", record_count=24520),
                    SimpleNamespace(projection_id="published:patent", record_count=11504),
                    SimpleNamespace(projection_id="published:professor", record_count=3958),
                ),
            ),
            as_of=_AS_OF,
        )
    )
    had_prior = hasattr(app.state, "canonical_v2_consumer_runtime")
    prior = getattr(app.state, "canonical_v2_consumer_runtime", None)
    app.state.canonical_v2_consumer_runtime = runtime
    try:
        response = _client().get("/api/canonical-v2/admin/system-status")
    finally:
        if had_prior:
            app.state.canonical_v2_consumer_runtime = prior
        else:
            delattr(app.state, "canonical_v2_consumer_runtime")

    assert response.status_code == 200
    pack = response.json()["pack"]
    assert pack["state"] == "ok"
    assert pack["manifest_sha256"] == "b" * 64
    assert pack["record_counts"]["published:company"] == 7089
    assert response.json()["freshness"]["per_domain"]["professor"]["record_count"] == 3958


def test_health_check_never_echoes_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOCHA_API_KEY", _SECRET_SENTINEL)
    monkeypatch.setenv("SERPER_API_KEY", "serper-sentinel-value-9911")

    seen: list[str] = []

    def _probe(url: str, key: str) -> tuple[bool, str]:
        seen.append(url)
        if _SECRET_SENTINEL in url or "serper-sentinel" in url:
            raise AssertionError("credential material must not reach the probe URL")
        return True, "probe ok"

    import backend.api.canonical_v2_admin_config as module

    monkeypatch.setattr(module, "probe_http", _probe)

    response = _client().post("/api/canonical-v2/admin/providers/health-check")

    assert response.status_code == 200
    body = response.json()
    assert seen, "the health check must actually probe configured providers"
    assert _SECRET_SENTINEL not in response.text
    assert "serper-sentinel" not in response.text
    by_key = {item["key"]: item for item in body["providers"]}
    assert by_key["bocha"]["configured"] is True
    assert by_key["bocha"]["suffix4"] == _SECRET_SENTINEL[-4:]
    assert by_key["bocha"]["origin"] == "env:BOCHA_API_KEY"
    assert len(by_key["bocha"]["suffix4"]) == 4
    assert len(_SECRET_SENTINEL) > 4


def test_health_check_reports_unconfigured_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "BOCHA_API_KEY",
        "SERPER_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "API_KEY",
        "LOCAL_LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    import backend.services.canonical_v2_admin_status as module

    monkeypatch.setattr(module, "_key_file_roots", lambda environ: ())

    response = _client().post("/api/canonical-v2/admin/providers/health-check")

    assert response.status_code == 200
    assert all(item["configured"] is False for item in response.json()["providers"])
    assert all(item["suffix4"] is None for item in response.json()["providers"])


def test_admin_page_is_served() -> None:
    """The shell links the shared nav and its own assets; the API calls moved to `admin.js`."""

    response = _client().get("/admin")

    assert response.status_code == 200
    body = response.text
    assert "管理配置中心" in body
    assert 'href="logs"' in body
    assert '<script src="/static/admin.js"' in body
    assert '<link rel="stylesheet" href="/static/admin.css"' in body
    assert 'id="card-collection"' in body
    assert "立即检查" not in body  # the global health button moved into the connection cards


def test_logs_page_links_to_admin() -> None:
    response = _client().get("/logs")

    assert response.status_code == 200
    assert 'href="admin"' in response.text


def test_config_endpoint_reports_env_override_source(
    store: ManagedSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_LANE_DAILY_QUOTA", "55")
    instance = ManagedSettingsStore(store.path, environ=dict(os.environ))
    app.dependency_overrides[get_managed_settings_store] = lambda: instance

    response = _client().get("/api/canonical-v2/admin/config")

    assert response.status_code == 200
    by_path = {field["path"]: field for field in response.json()["fields"]}
    entry = by_path["collection.max_web_searches_per_run"]
    assert entry["value"] == 55
    assert entry["source"] == "env"
    assert entry["editable"] is False
