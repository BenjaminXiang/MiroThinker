"""Manual recall sidecar: lane contract, request filters, union, and wiring.

The sidecar store (operator uploads / manual records) is covered by the
admin-console tests; this file covers the agent-side union: manual points
become release-shaped vector candidates that pass the exact lane output
predicates ``_invoke_lane`` enforces, are exempted from release-bound
validation on their target marker, and disappear entirely when no provider
is configured.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.data_agents.canonical_v2 import knowledge_read as read_module
from src.data_agents.canonical_v2 import knowledge_read_isolated as isolated_read
from src.data_agents.canonical_v2 import manual_recall_points
from src.data_agents.canonical_v2.index_projection_isolated import (
    RecordedEmbeddingAdapter,
)
from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceSet,
    FusedCandidate,
    LaneQuery,
    RetrievalPlan,
    StructuredConstraints,
)


def _load_fast_boot_helpers() -> Any:
    """Load the sibling fast-boot fixture builders without a package import."""

    path = Path(__file__).resolve().with_name("test_fast_boot.py")
    spec = importlib.util.spec_from_file_location("fast_boot_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _load_runner_module() -> Any:
    runner_path = (
        Path(__file__).resolve().parents[4]
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py"
    )
    spec = importlib.util.spec_from_file_location(
        "complete_candidate_runner",
        runner_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


@dataclass
class _FakeManualPoint:
    point_id: str
    domain: str
    display_name: str
    canonical_ref: str
    embedded_content: str
    vector: tuple[float, ...]


class _FakeManualProvider:
    def __init__(self, points: tuple[_FakeManualPoint, ...]) -> None:
        self._points = points

    def active_points(self) -> tuple[_FakeManualPoint, ...]:
        return self._points


def _fake_point(
    *,
    point_id: str = "doc-0000000001:0",
    domain: str = "company",
    display_name: str = "Robotics Co (人工上传)",
    canonical_ref: str = "company-robotics",
    name: str = "Robotics Co",
    summary: str = "Operator uploaded robotics profile",
    vector: tuple[float, ...] | None = None,
) -> _FakeManualPoint:
    return _FakeManualPoint(
        point_id=point_id,
        domain=domain,
        display_name=display_name,
        canonical_ref=canonical_ref,
        embedded_content=json.dumps(
            {"name": name, "summary": summary},
            ensure_ascii=False,
        ),
        vector=vector if vector is not None else (0.0,) * 32,
    )


def test_manual_candidate_satisfies_lane_output_contract() -> None:
    fast_boot = _load_fast_boot_helpers()
    request = fast_boot._lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    point = _fake_point()
    candidate = manual_recall_points.manual_candidate_from_point(
        point=point,
        request=request,
        query_embedding_sha256="a" * 64,
        similarity_score=0.5,
        embedding_model=fast_boot.EMBEDDING_MODEL,
    )
    evidence = candidate.evidence[0]
    trace = evidence.local_projection_trace

    assert candidate.lane == request.lane == "vector"
    assert candidate.release_id == request.release_id
    assert candidate.query_view == request.query_view
    assert candidate.attempt == 1
    assert candidate.canonical_id == point.canonical_ref
    assert candidate.display_name == point.display_name
    assert candidate.raw_candidate_id == trace.raw_candidate_id
    assert candidate.raw_score == evidence.score == trace.similarity_score == 0.5
    assert evidence.evidence_id == trace.evidence_id
    assert evidence.object_id == point.canonical_ref
    assert evidence.source_nature == "local"
    assert (
        evidence.source_authority
        == manual_recall_points.MANUAL_RECALL_SOURCE_AUTHORITY
        == "manual_upload"
    )
    assert manual_recall_points.is_manual_vector_trace(trace)
    assert trace.target_id == manual_recall_points.MANUAL_RECALL_TARGET_ID
    assert trace.release_id == request.release_id
    # The exact predicates ``_invoke_lane`` enforces on lane output.
    assert read_module._valid_local_projection_item(evidence, request)
    assert read_module._valid_local_projection_candidate(candidate, request)


def test_manual_candidate_rejects_non_public_domain() -> None:
    fast_boot = _load_fast_boot_helpers()
    request = fast_boot._lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    point = _fake_point(domain="internal_reference")
    with pytest.raises(
        isolated_read.IsolatedKnowledgeReadIntegrityError,
        match="not a public domain",
    ):
        manual_recall_points.manual_candidate_from_point(
            point=point,
            request=request,
            query_embedding_sha256="a" * 64,
            similarity_score=0.5,
            embedding_model=fast_boot.EMBEDDING_MODEL,
        )


def test_manual_points_for_request_filters() -> None:
    fast_boot = _load_fast_boot_helpers()
    request = fast_boot._lane_request(lane="vector", query_text="Robotics Co [lane=vector]")
    corrupt = _fake_point(point_id="doc-0000000003:0")
    object.__setattr__(corrupt, "embedded_content", "{not json")
    provider = _FakeManualProvider(
        (
            _fake_point(point_id="doc-0000000001:0"),
            _fake_point(point_id="doc-0000000002:0", domain="paper"),
            corrupt,
        )
    )

    assert manual_recall_points.manual_points_for_request(
        provider=None,
        request=request,
    ) == ()
    matched = manual_recall_points.manual_points_for_request(
        provider=provider,
        request=request,
    )
    assert tuple(point.point_id for point in matched) == ("doc-0000000001:0",)

    displayed_request = request.model_copy(
        update={
            "structured_constraints": StructuredConstraints(
                displayed_entity_ids=("company-other",),
            )
        }
    )
    assert (
        manual_recall_points.manual_points_for_request(
            provider=provider,
            request=displayed_request,
        )
        == ()
    )

    excluded_request = request.model_copy(
        update={
            "structured_constraints": StructuredConstraints(
                excluded_terms=("robotics",),
            )
        }
    )
    assert (
        manual_recall_points.manual_points_for_request(
            provider=provider,
            request=excluded_request,
        )
        == ()
    )


def test_vector_lane_unions_manual_candidates_before_sort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast_boot = _load_fast_boot_helpers()
    fixture = fast_boot._build_fixture(tmp_path, monkeypatch)
    adapter = RecordedEmbeddingAdapter(model_id=fast_boot.EMBEDDING_MODEL, dimension=32)
    query_text = "Robotics Co [lane=vector]"
    query_topic = isolated_read._vector_query_topic(query_text)
    manual_vector = adapter.embed_batch((query_topic,))[0]
    provider = _FakeManualProvider((_fake_point(vector=manual_vector),))

    def _adapter(manual_provider: Any) -> Any:
        kwargs: dict[str, Any] = {}
        if manual_provider is not ...:
            kwargs["manual_recall_provider"] = manual_provider
        return isolated_read.create_isolated_vector_recall_adapter(
            release_bundle=fixture.bundle,
            published_release=fixture.published,
            embedding_adapter=adapter,
            reuse_audited_snapshot=True,
            vectorized_scoring=True,
            fast_boot=True,
            **kwargs,
        )

    request = fast_boot._lane_request(lane="vector", query_text=query_text)
    union_result = _adapter(provider)(request)
    assert len(union_result.candidates) == 4
    top = union_result.candidates[0]
    assert top.raw_score == pytest.approx(1.0)
    assert top.canonical_id == "company-robotics"
    assert top.display_name == "Robotics Co (人工上传)"
    assert manual_recall_points.is_manual_vector_trace(
        top.evidence[0].local_projection_trace
    )
    # Release points are unaffected by the union.
    release_candidates = [
        candidate
        for candidate in union_result.candidates
        if not manual_recall_points.is_manual_vector_trace(
            candidate.evidence[0].local_projection_trace
        )
    ]
    assert len(release_candidates) == 3

    # An empty/absent sidecar preserves the exact pre-existing lane output.
    empty_result = _adapter(_FakeManualProvider(()))(request)
    plain_result = _adapter(...)(request)
    assert empty_result == plain_result
    assert len(plain_result.candidates) == 3


def test_release_bound_vector_validator_exempts_manual_traces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast_boot = _load_fast_boot_helpers()
    fixture = fast_boot._build_fixture(tmp_path, monkeypatch)
    adapter = RecordedEmbeddingAdapter(model_id=fast_boot.EMBEDDING_MODEL, dimension=32)
    query_text = "Robotics Co [lane=vector]"
    manual_vector = adapter.embed_batch((query_text,))[0]
    provider = _FakeManualProvider((_fake_point(vector=manual_vector),))
    vector_adapter = isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=adapter,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
        fast_boot=True,
        manual_recall_provider=provider,
    )
    recall = vector_adapter(
        fast_boot._lane_request(lane="vector", query_text=query_text)
    )
    assert any(
        manual_recall_points.is_manual_vector_trace(
            candidate.evidence[0].local_projection_trace
        )
        for candidate in recall.candidates
    )

    items = tuple(candidate.evidence[0] for candidate in recall.candidates)
    fused_candidates = tuple(
        FusedCandidate(
            result_id=f"fused:test:{candidate.canonical_id}:{index}",
            canonical_id=candidate.canonical_id,
            display_name=candidate.display_name,
            domain=candidate.domain,
            raw_candidate_ids=(candidate.raw_candidate_id,),
            evidence_ids=(candidate.evidence[0].evidence_id,),
            evidence=(candidate.evidence[0],),
            quality_flags=(),
            raw_score=candidate.raw_score,
            identity_kind=candidate.identity_kind,
            resolution_state=candidate.resolution_state,
            origin_lane=candidate.lane,
            origin_attempt=candidate.attempt,
            adapter_versions=(candidate.adapter_version,),
            provider_versions=(
                (candidate.provider_version,)
                if candidate.provider_version is not None
                else ()
            ),
        )
        for index, candidate in enumerate(recall.candidates)
    )
    evidence_set = EvidenceSet(
        release_id=fast_boot.RELEASE_ID,
        original_query="Robotics Co",
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        fused_candidates=fused_candidates,
    )
    plan = RetrievalPlan(
        plan_version="manual-recall-test-v1",
        original_query="Robotics Co",
        behavior_class="A",
        release_id=fast_boot.RELEASE_ID,
        domains=("company",),
        protected_slots=(),
        lanes=("vector",),
        max_candidates=8,
        web_required=False,
        lane_queries=(
            LaneQuery(
                lane="vector",
                release_id=fast_boot.RELEASE_ID,
                catalog_sha256=fast_boot.CATALOG_CONTENT_SHA256,
                pure_topic_text="Robotics Co",
                query_text=query_text,
            ),
        ),
    )
    # Must not raise: manual traces are exempt on their target marker.
    isolated_read._validate_release_bound_vector_evidence(
        plan=plan,
        evidence_set=evidence_set,
        bundle=fixture.bundle,
        publication=fixture.published,
        embedding_adapter=adapter,
    )

    # Negative control: the same evidence with a release target marker is not
    # exempt and fails closed because its point is not in the audited bundle.
    manual_candidate = next(
        candidate
        for candidate in recall.candidates
        if manual_recall_points.is_manual_vector_trace(
            candidate.evidence[0].local_projection_trace
        )
    )
    tampered_trace = manual_candidate.evidence[0].local_projection_trace.model_copy(
        update={"target_id": fast_boot.TARGET_ID}
    )
    tampered_item = manual_candidate.evidence[0].model_copy(
        update={"local_projection_trace": tampered_trace}
    )
    tampered_set = evidence_set.model_copy(update={"items": (tampered_item,)})
    with pytest.raises(isolated_read.IsolatedKnowledgeReadIntegrityError):
        isolated_read._validate_release_bound_vector_evidence(
            plan=plan,
            evidence_set=tampered_set,
            bundle=fixture.bundle,
            publication=fixture.published,
            embedding_adapter=adapter,
        )


def _runner_serve_calls(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manual_recall_dir: str | None,
    fake_backend: Any | None,
) -> tuple[dict[str, Any], Any]:
    runner = _load_runner_module()
    fast_boot = _load_fast_boot_helpers()
    for name in (
        "CANONICAL_V2_ACCESS_LOG_DB",
        "CANONICAL_V2_CORRECTIONS_DB",
    ):
        monkeypatch.delenv(name, raising=False)
    if manual_recall_dir is None:
        monkeypatch.delenv("CANONICAL_V2_MANUAL_RECALL_DIR", raising=False)
    else:
        monkeypatch.setenv("CANONICAL_V2_MANUAL_RECALL_DIR", manual_recall_dir)
    if fake_backend is not None:
        monkeypatch.setitem(
            sys.modules, "backend.services.canonical_v2_manual_recall", fake_backend
        )

    create_read_calls: list[dict[str, Any]] = []
    app = SimpleNamespace(state=SimpleNamespace())
    recorded = SimpleNamespace(
        planning_policy=object(),
        proposal_provider=object(),
        ambiguity_policy=object(),
        universal_web_policy=object(),
        web_search=object(),
        web_snapshot_policy=object(),
        embedding_adapter=object(),
        identity_fuser=None,
        reranker=None,
        sufficiency_decider=None,
        supplemental_search=None,
        web_handle_resolver=None,
        accepted_identity_lookup=None,
        answer_factory=object(),
        answer_session_fork=object(),
        gap_operations=object(),
        supplemental_budget=object(),
        idle_keepwarm_cycle=object(),
    )
    dependencies = runner.RunnerDependencies(
        create_builder=lambda _config: object(),
        read_envelope=lambda _path: object(),
        validate_envelope=lambda value: value,
        load_recorded_serving_inputs=lambda _config: recorded,
        create_published_release=lambda **kwargs: SimpleNamespace(**kwargs),
        create_query_planner=lambda **kwargs: object(),
        create_knowledge_read=lambda **kwargs: create_read_calls.append(kwargs),
        compose_consumer_runtime=lambda **kwargs: object(),
        create_candidate_app=lambda **kwargs: app,
        uvicorn_run=lambda _app, **kwargs: None,
    )
    handoff = SimpleNamespace(
        release_verification=SimpleNamespace(
            evidence_ids=("release-verification:manual-recall",)
        ),
        release_bundle=object(),
        index_projection_request=object(),
        institution_catalog=object(),
    )
    runner._serve(
        config=fast_boot._runner_config(runner, tmp_path),
        handoff=handoff,
        dependencies=dependencies,
    )
    assert len(create_read_calls) == 1
    return create_read_calls[0], app


def test_runner_serve_composes_manual_recall_store_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(store_path=tmp_path / "manual-recall.json")
    fake_backend = SimpleNamespace(
        ManualRecallStore=lambda _path, _adapter: store,
    )
    call, app = _runner_serve_calls(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        manual_recall_dir=str(tmp_path),
        fake_backend=fake_backend,
    )
    assert call["manual_recall_provider"] is store
    assert app.state.canonical_v2_manual_recall_store is store


def test_runner_serve_defaults_to_no_manual_recall_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call, app = _runner_serve_calls(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        manual_recall_dir=None,
        fake_backend=None,
    )
    assert call["manual_recall_provider"] is None
    assert not hasattr(app.state, "canonical_v2_manual_recall_store")


def test_runner_serve_manual_recall_store_fails_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Env is set but the admin backend module is not importable here, so the
    # sidecar must degrade to None instead of failing the serving boot.
    call, app = _runner_serve_calls(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        manual_recall_dir=str(tmp_path),
        fake_backend=None,
    )
    assert call["manual_recall_provider"] is None
    assert not hasattr(app.state, "canonical_v2_manual_recall_store")
