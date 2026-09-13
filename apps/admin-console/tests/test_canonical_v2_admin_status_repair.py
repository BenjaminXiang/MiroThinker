"""Regression for the live `GET /api/canonical-v2/admin/status` 500.

Live traceback (journalctl, unit `canonical-v2-backend`, 2026-09-13):

    AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'
      apps/admin-console/backend/services/canonical_v2_admin.py:631 status()
      apps/admin-console/backend/api/canonical_v2_consumers.py:109 _runtime_call()

The pack-mode composition installs the ephemeral in-process gap feedback, which
only implements `record`/`apply_remediation`. These tests construct exactly that
shape plus the operations-capable shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_consumers import router as consumers_router  # noqa: F401
from backend.canonical_v2_deps import get_canonical_v2_admin_runtime
from backend.main import app
from src.data_agents.canonical_v2.contracts import (
    GapClass,
    GapSeverity,
    GapStatus,
    KnowledgeGap,
    ReviewState,
)
from src.data_agents.canonical_v2.knowledge_gap_postgres import GapAdminPage


_AS_OF = datetime(2026, 9, 7, 15, 56, 13, tzinfo=UTC)


class _EphemeralKnowledgeGapFeedback:
    """Mirror of the runner's ephemeral object: no administrator listing."""

    def __init__(self) -> None:
        self.recorded: list[Any] = []

    def record(self, signal: Any) -> Any:
        self.recorded.append(signal)
        return signal

    def apply_remediation(self, request: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class _PostgresGapOperations:
    def list_for_admin(self, query: Any) -> GapAdminPage:
        return GapAdminPage(
            items=(
                KnowledgeGap(
                    gap_id="gap:status:test",
                    gap_class=GapClass.knowledge_coverage,
                    status=GapStatus.open,
                    release_id="candidate-v2-20260819-r1",
                    affected_domains=("company",),
                    affected_paths=("company_has_patent",),
                    query_trace_id="query:status",
                    answer_trace_id="answer:status",
                    observed_symptom="no result",
                    evidence_ids=("web:status",),
                    classification_confidence=0.5,
                    review_state=ReviewState.unreviewed,
                    proposed_owner="knowledge_coverage",
                    proposed_remediation="review_no_result",
                    demand_count=1,
                    scenario_families=("query:no_result",),
                    severity=GapSeverity.medium,
                    created_at=_AS_OF,
                    updated_at=_AS_OF,
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
    manifest_sha256 = "c" * 64


def _projections() -> tuple[SimpleNamespace, ...]:
    rows: list[SimpleNamespace] = []
    for domain, count in (
        ("company", 2),
        ("paper", 3),
        ("patent", 1),
        ("professor", 2),
    ):
        for index in range(count):
            rows.append(
                SimpleNamespace(
                    entity_type=domain,
                    canonical_identity_id=f"{domain}-c-{index}",
                )
            )
    return tuple(rows)


def _admin_runtime(*, gap_operations: Any) -> Any:
    from backend.services.canonical_v2_admin import CanonicalV2AdminRuntime

    return CanonicalV2AdminRuntime(
        release_id="candidate-v2-20260819-r1",
        manifest=_Manifest(),
        candidate_projection=SimpleNamespace(
            as_of=_AS_OF, public_domain_projections=_projections()
        ),
        relationship_authority=SimpleNamespace(current_relationships=()),
        planner=SimpleNamespace(),
        knowledge_read=SimpleNamespace(),
        chat_adapter=SimpleNamespace(),
        gap_operations=gap_operations,
    )


def _client_with(runtime: Any) -> TestClient:
    app.dependency_overrides[get_canonical_v2_admin_runtime] = lambda: runtime
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_override() -> Any:
    prior = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior)


def test_status_degrades_without_list_for_admin() -> None:
    runtime = _admin_runtime(gap_operations=_EphemeralKnowledgeGapFeedback())

    response = _client_with(runtime).get("/api/canonical-v2/admin/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "candidate-v2-20260819-r1"
    assert payload["manifest_version"] == "canonical-v2-build-manifest-v2"
    assert payload["manifest_sha256"] == "c" * 64
    assert payload["gap_summary"]["state"] == "unavailable"
    assert "administrator listing" in payload["gap_summary"]["reason"]
    counts = {item["domain"]: item["record_count"] for item in payload["domains"]}
    assert counts == {"company": 2, "paper": 3, "patent": 1, "professor": 2}


def test_status_keeps_page_when_capable() -> None:
    runtime = _admin_runtime(gap_operations=_PostgresGapOperations())

    response = _client_with(runtime).get("/api/canonical-v2/admin/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gap_summary"]["state"] == "available"
    assert payload["gap_summary"]["page"]["total"] == 1
    assert payload["gap_summary"]["page"]["items"][0]["gap_id"] == "gap:status:test"


def test_status_degrades_when_page_fails_exact_validation() -> None:
    class _HostileOperations:
        def list_for_admin(self, query: Any) -> Any:
            del query
            return SimpleNamespace(items=(), total=0, limit=10, offset=0)

    runtime = _admin_runtime(gap_operations=_HostileOperations())

    response = _client_with(runtime).get("/api/canonical-v2/admin/status")

    assert response.status_code == 200
    assert response.json()["gap_summary"]["state"] == "unavailable"
    assert "validation" in response.json()["gap_summary"]["reason"]


def test_status_propagates_capability_errors_as_500() -> None:
    class _ExplodingOperations:
        def list_for_admin(self, query: Any) -> Any:
            del query
            raise RuntimeError("storage exploded")

    runtime = _admin_runtime(gap_operations=_ExplodingOperations())

    response = _client_with(runtime).get("/api/canonical-v2/admin/status")

    # A real storage failure must stay visible; only a missing capability degrades.
    assert response.status_code == 500
