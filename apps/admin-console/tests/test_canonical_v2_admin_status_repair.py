"""Regression for the live `GET /api/canonical-v2/admin/status` 500.

Live traceback (journalctl, unit `canonical-v2-backend`, 2026-09-13):

    AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'
      apps/admin-console/backend/services/canonical_v2_admin.py:631 status()
      apps/admin-console/backend/api/canonical_v2_consumers.py:109 _runtime_call()

The pack-mode composition installs the ephemeral in-process gap feedback, which
only implements `record`/`apply_remediation`. These tests construct exactly that
shape plus the operations-capable shape.

The same object is injected as both the admin runtime's `gap_operations` and the
`/api/canonical-v2/operations/*` dependency (`main.py:248-250`). The first repair
covered only the status surface, so the same defect returned one week later on the
two operations endpoints (live, 2026-09-19 23:34):

    AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'
      apps/admin-console/backend/api/canonical_v2_operations.py:47 list_knowledge_gaps

Both surfaces are now covered here.
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
from tests.conftest import authorized_client
from src.data_agents.canonical_v2.contracts import (
    GapClass,
    GapSeverity,
    GapStatus,
    KnowledgeGap,
    ReviewState,
)
from src.data_agents.canonical_v2.knowledge_gap_postgres import (
    GapAdminDetail,
    GapAdminPage,
)


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
            items=(_gap(),),
            total=1,
            limit=query.limit,
            offset=query.offset,
        )

    def get_for_admin(self, gap_id: str) -> GapAdminDetail | None:
        if gap_id != "gap:status:test":
            return None
        return GapAdminDetail(
            gap=_gap(),
            transitions=(),
            field_assertions=(),
            relationship_assertions=(),
            canonical_decisions=(),
            relationship_decisions=(),
            releases=(),
            provenance=(),
            unresolved_evidence_ids=("web:status",),
        )


def _gap() -> KnowledgeGap:
    return KnowledgeGap(
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


def _admin_runtime(*, gap_operations: Any, chat_adapter: Any = None) -> Any:
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
        chat_adapter=SimpleNamespace() if chat_adapter is None else chat_adapter,
        gap_operations=gap_operations,
    )


def _client_with(runtime: Any) -> TestClient:
    app.dependency_overrides[get_canonical_v2_admin_runtime] = lambda: runtime
    return authorized_client(raise_server_exceptions=False)


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


def _operations_client(operations: Any) -> TestClient:
    from backend.api import canonical_v2_operations

    app.dependency_overrides[canonical_v2_operations.get_knowledge_gap_operations] = (
        lambda: operations
    )
    return authorized_client(raise_server_exceptions=False)


_GAPS_PATHS = (
    "/api/canonical-v2/operations/gaps",
    "/api/canonical-v2/operations/gaps/gap:status:test",
)


@pytest.mark.parametrize("path", _GAPS_PATHS)
def test_gaps_degrade_without_administrator_capability(path: str) -> None:
    client = _operations_client(_EphemeralKnowledgeGapFeedback())

    response = client.get(path)

    assert response.status_code == 503
    assert response.json() == {"detail": "Canonical V2 operations are unavailable"}


def test_gaps_keep_pages_and_404_when_capable() -> None:
    client = _operations_client(_PostgresGapOperations())

    page = client.get("/api/canonical-v2/operations/gaps")
    assert page.status_code == 200
    assert page.json()["items"][0]["gap_id"] == "gap:status:test"

    detail = client.get("/api/canonical-v2/operations/gaps/gap:status:test")
    assert detail.status_code == 200
    assert detail.json()["gap"]["gap_id"] == "gap:status:test"

    absent = client.get("/api/canonical-v2/operations/gaps/gap:absent:test")
    assert absent.status_code == 404
    assert absent.json() == {"detail": "Canonical V2 gap not found"}


@pytest.mark.parametrize("path", _GAPS_PATHS)
def test_gaps_keep_capable_object_errors_visible(path: str) -> None:
    class _ExplodingOperations:
        def list_for_admin(self, query: Any) -> Any:
            del query
            raise RuntimeError("storage exploded")

        def get_for_admin(self, gap_id: str) -> Any:
            del gap_id
            raise RuntimeError("storage exploded")

    client = _operations_client(_ExplodingOperations())

    # The capability guard must not swallow a capable object's real failures.
    assert client.get(path).status_code == 500


@pytest.mark.parametrize("path", _GAPS_PATHS)
def test_gaps_degrade_through_the_candidate_aggregate_wiring(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live path: `main.py` injects the aggregate's own `gap_operations` member."""

    from backend.api.canonical_v2_operations import get_knowledge_gap_operations
    from backend.canonical_v2_deps import get_canonical_v2_gap_operations
    from backend.services.canonical_v2_admin import CanonicalV2ConsumerRuntime
    from backend.services.canonical_v2_chat import CanonicalV2ChatAdapter

    chat_adapter = CanonicalV2ChatAdapter(
        release_id="candidate-v2-20260819-r1",
        planner=SimpleNamespace(),
        knowledge_read=SimpleNamespace(),
        answer_factory=lambda: None,
        answer_session_fork=lambda answer: answer,
    )
    ephemeral = _EphemeralKnowledgeGapFeedback()
    monkeypatch.setattr(
        app.state,
        "canonical_v2_consumer_runtime",
        CanonicalV2ConsumerRuntime(
            release_id="candidate-v2-20260819-r1",
            admin_runtime=_admin_runtime(
                gap_operations=ephemeral, chat_adapter=chat_adapter
            ),
            chat_adapter=chat_adapter,
            gap_operations=ephemeral,
        ),
        raising=False,
    )
    app.dependency_overrides[get_knowledge_gap_operations] = (
        get_canonical_v2_gap_operations
    )

    response = authorized_client(raise_server_exceptions=False).get(path)

    assert response.status_code == 503
    assert response.json() == {"detail": "Canonical V2 operations are unavailable"}
