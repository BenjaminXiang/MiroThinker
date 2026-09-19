from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.main import app
from src.data_agents.canonical_v2.contracts import (
    GapClass,
    GapSeverity,
    GapStatus,
    KnowledgeGap,
    ReviewState,
)


class _MissingS10OOperationsAPI(RuntimeError):
    """Exact S10O admin RED sentinel."""


def _api_module():
    try:
        module = import_module("backend.api.canonical_v2_operations")
    except ModuleNotFoundError as exc:
        if exc.name == "backend.api.canonical_v2_operations":
            raise _MissingS10OOperationsAPI(
                "exact S10O Canonical V2 operations API is absent"
            ) from exc
        raise
    if not hasattr(module, "router"):
        raise _MissingS10OOperationsAPI("exact S10O operations router is absent")
    return module


def _gap() -> KnowledgeGap:
    now = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
    return KnowledgeGap(
        gap_id="gap:api:s10o",
        gap_class=GapClass.relationship,
        status=GapStatus.open,
        release_id="release:s10o:source",
        affected_domains=("professor", "paper"),
        affected_paths=("professor_attributed_to_paper",),
        query_trace_id="query:s10o",
        answer_trace_id="answer:s10o",
        observed_symptom="A relationship is missing.",
        evidence_ids=("web:s10o",),
        classification_confidence=0.9,
        review_state=ReviewState.unreviewed,
        proposed_owner="relationship_enrichment",
        proposed_remediation="collect_missing_relationship_evidence",
        demand_count=1,
        scenario_families=("query:relationship",),
        severity=GapSeverity.medium,
        created_at=now,
        updated_at=now,
    )


class _RecordedOperations:
    def __init__(self, module: Any) -> None:
        self.module = module
        self.queries: list[Any] = []
        self.failure: Exception | None = None

    def list_for_admin(self, query: Any) -> Any:
        self.queries.append(query)
        if self.failure is not None:
            raise self.failure
        return self.module.GapAdminPage(
            items=(_gap(),), total=1, limit=query.limit, offset=query.offset
        )

    def get_for_admin(self, gap_id: str) -> Any:
        if self.failure is not None:
            raise self.failure
        if gap_id == "missing":
            return None
        return self.module.GapAdminDetail(
            gap=_gap(),
            transitions=(),
            field_assertions=(),
            relationship_assertions=(),
            canonical_decisions=(),
            relationship_decisions=(),
            releases=(),
            provenance=(),
            unresolved_evidence_ids=("web:s10o",),
        )


def test_canonical_v2_operations_api_is_bounded_read_only_and_quarantined(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _api_module()
    routes = {
        (method, route.path)
        for route in module.router.routes
        for method in route.methods
    }
    assert routes == {
        ("GET", "/api/canonical-v2/operations/gaps"),
        ("GET", "/api/canonical-v2/operations/gaps/{gap_id}"),
    }
    assert module.get_knowledge_gap_operations.__module__ == "backend.canonical_v2_deps"
    operations_module = import_module(
        "src.data_agents.canonical_v2.knowledge_gap_postgres"
    )
    recorded = _RecordedOperations(operations_module)
    app.dependency_overrides[module.get_knowledge_gap_operations] = lambda: recorded

    response = client.get(
        "/api/canonical-v2/operations/gaps",
        params={
            "statuses": "open",
            "gap_classes": "relationship",
            "severities": "medium",
            "domain": "professor",
            "path": "professor_attributed_to_paper",
            "release_id": "release:s10o:source",
            "limit": 1,
            "offset": 0,
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["gap_id"] == "gap:api:s10o"
    query = recorded.queries[-1]
    assert query.model_dump(mode="json") == {
        "statuses": ["open"],
        "gap_classes": ["relationship"],
        "severities": ["medium"],
        "domain": "professor",
        "path": "professor_attributed_to_paper",
        "release_id": "release:s10o:source",
        "limit": 1,
        "offset": 0,
    }
    assert client.get("/api/canonical-v2/operations/gaps/missing").status_code == 404
    assert (
        client.get("/api/canonical-v2/operations/gaps/gap:api:s10o").status_code == 200
    )
    assert (
        client.get(
            "/api/canonical-v2/operations/gaps", params={"limit": 201}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/canonical-v2/operations/gaps", params={"statuses": "poison"}
        ).status_code
        == 422
    )
    for failure, expected_status, expected_detail in (
        (
            operations_module.KnowledgeGapPersistenceError(
                "postgresql://operator:PERSIST_LEAK_SENTINEL@example.invalid/private SQL"
            ),
            503,
            "Canonical V2 operations are unavailable",
        ),
        (
            operations_module.KnowledgeGapConfigurationError(
                "postgresql://operator:CONFIG_LEAK_SENTINEL@example.invalid/revoked gate"
            ),
            503,
            "Canonical V2 operations are unavailable",
        ),
        (
            operations_module.KnowledgeGapIntegrityError(
                "INTEGRITY_LEAK_SENTINEL payload"
            ),
            500,
            "Canonical V2 gap data failed validation",
        ),
    ):
        recorded.failure = failure
        for path in (
            "/api/canonical-v2/operations/gaps",
            "/api/canonical-v2/operations/gaps/gap:api:s10o",
        ):
            unavailable = client.get(path)
            assert unavailable.status_code == expected_status
            assert unavailable.json() == {"detail": expected_detail}
            assert "LEAK_SENTINEL" not in unavailable.text
    recorded.failure = None

    assert operations_module.__file__ is not None
    assert module.__file__ is not None
    agent_source = Path(operations_module.__file__).read_text(encoding="utf-8")
    deps_module = import_module("backend.canonical_v2_deps")
    assert deps_module.__file__ is not None
    assert "MilvusClient" not in agent_source
    quarantine = textwrap.dedent(
        """
        import importlib.abc
        import json
        import sys

        forbidden = (
            "backend.deps",
            "backend.api.chat",
            "backend.api.review",
            "backend.api.pipeline_issues",
            "src.data_agents.providers",
            "src.data_agents.retrieval",
            "pymilvus",
        )

        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
                    raise ImportError(f"forbidden import attempted: {fullname}")
                return None

        sys.meta_path.insert(0, Blocker())
        import backend.canonical_v2_deps
        from backend.api import canonical_v2_operations

        routes = sorted(
            (method, route.path)
            for route in canonical_v2_operations.router.routes
            for method in route.methods
        )
        assert routes == [
            ("GET", "/api/canonical-v2/operations/gaps"),
            ("GET", "/api/canonical-v2/operations/gaps/{gap_id}"),
        ]
        print(json.dumps(routes))
        """
    )
    admin_root = Path(__file__).resolve().parents[1]
    agent_src = admin_root.parent / "miroflow-agent"
    quarantine_env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(admin_root), str(agent_src))),
    }
    quarantined = subprocess.run(
        [sys.executable, "-c", quarantine],
        cwd=admin_root,
        env=quarantine_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert quarantined.returncode == 0, quarantined.stderr
    assert "backend.deps" not in quarantined.stdout
    deps_module._compose_operations.cache_clear()
    for name in (
        "CANONICAL_V2_DATABASE_URL",
        "CANONICAL_V2_EXPECTED_DATABASE",
        "CANONICAL_V2_TARGET_KIND",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://operator:GENERIC_LEAK_SENTINEL@example.invalid/wrong",
    )
    monkeypatch.setenv("MILVUS_URI", "https://GENERIC_MILVUS_LEAK_SENTINEL.invalid")
    with pytest.raises(HTTPException) as unconfigured:
        deps_module.get_knowledge_gap_operations()
    assert unconfigured.value.status_code == 503
    assert unconfigured.value.detail == "Canonical V2 operations are not configured"
    assert "LEAK_SENTINEL" not in str(unconfigured.value.detail)
    page = client.get("/browse")
    assert page.status_code == 200
    assert "V2 Gaps" in page.text
    # The 知识缺口 tab reads the feedback ledger; the build-line surface stays quarantined
    # behind its own router and is never called from the page.
    assert 'const gapsPath = "api/canonical-v2/admin/chat-gaps";' in page.text
    assert "operations/gaps" not in page.text
    assert "esc(JSON.stringify" in page.text


def test_the_static_pages_only_call_their_own_v2_surfaces() -> None:
    """A live guard where the s11b quarantine helper no longer runs.

    ``test_canonical_v2_consumer_migration._assert_static_and_import_quarantine``
    carries the same intent, but it sits behind a stale factory-arity assertion
    (``:735``) that has failed since the factory gained an optional second
    parameter, and four of its page pins have rotted since. A guard that never
    runs is not a guard, so this one is reachable: it locks what the two pages the
    public actually loads may call.
    """

    static_dir = Path(__file__).resolve().parents[1] / "backend" / "static"
    expected = {
        "browse.html": {
            "api/canonical-v2/admin/status",
            "api/canonical-v2/admin/domains/",
            "api/canonical-v2/admin/chat-gaps",
            "api/canonical-v2/admin/corrections",
            "api/canonical-v2/admin/company-documents",
        },
        "chat.html": {"api/chat/stream", "api/chat/feedback"},
    }
    for name, literals in expected.items():
        page = (static_dir / name).read_text(encoding="utf-8")
        found = set(re.findall(r'"(/?api/[A-Za-z0-9_{}./:-]+)"', page))
        assert found == literals, (name, sorted(found))

    legacy = (
        "/api/data/",
        "/api/seeds/",
        "/api/pipeline",
        "/api/upload",
        "/api/review",
        "/api/batch",
        "/api/admin_professor",
        "canonical_writer",
        "Milvus",
    )
    for name in (*expected, "main.html", "admin.html", "seeds.html", "jobs.html", "logs.html"):
        page = (static_dir / name).read_text(encoding="utf-8")
        for forbidden in legacy:
            assert forbidden not in page, (name, forbidden)
    # chat.html mentions innerHTML only in comments that say it is not used, so the
    # blanket check stays on the page the fossil applied it to.
    browse = (static_dir / "browse.html").read_text(encoding="utf-8")
    assert re.search(r"(?:inner|outer)\s*HTML", browse, re.IGNORECASE) is None
