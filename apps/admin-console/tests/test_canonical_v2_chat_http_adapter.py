from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from importlib import import_module, util
import inspect
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable, TypedDict, cast

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest


RELEASE_ID = "candidate-s11a-release-bound-chat"
NOW = datetime(2026, 7, 20, 17, 45, tzinfo=UTC)
INITIAL_QUERY = "介绍 “Robotics Co” 并核实 2026 年当前营收"
SIMPLE_QUERY = "介绍 Robotics Co"
RELATIONSHIP_QUERY = "列出已展示 Robotics Co 作为申请人的代表性专利"
BLOCKING_QUERY = "介绍同名机器人公司"
RUNTIME_UNAVAILABLE = "canonical_v2_chat_runtime_unavailable"
INVALID_SELECTION = "canonical_v2_invalid_option"
RELEASE_MISMATCH = "canonical_v2_release_mismatch"
RAW_SELECTOR_DRAFT = "RAW_SELECTOR_DRAFT_DO_NOT_EXPOSE"
SECRET_SENTINEL = "sk-s11a-do-not-expose"
ACCEPTED_PHYSICAL_OWNER_SHA256 = (
    "708d2926670b739a5b388f489755c5ec43444a0ed6591c9a9c335857e22b91fa"
)
CHAT_SCHEMA_SHA256 = "04584086d12ca5c56e5fd28f702d2fe5f71a20038be84f0dbdcc45524edcbd94"
CHAT_MODEL_NAMES = (
    "ChatCitation",
    "CandidateOption",
    "ClarificationPayload",
    "ChatRequest",
    "ChatResponse",
    "ChatFeedbackRequest",
    "ChatFeedbackResponse",
    "ChatSessionResetResponse",
)

_CONTINUATION_PUBLIC_COPY = (
    ("broad_scope", "narrow_scope", "可进一步缩小当前结果范围", "缩小当前结果范围"),
    (
        "ambiguity",
        "switch_candidate",
        "可切换到其他有证据支持的候选实体",
        "切换候选实体",
    ),
    ("partial_coverage", "continue_coverage", "当前覆盖仍不完整", "继续补充覆盖"),
    (
        "evidence_gap",
        "targeted_evidence_search",
        "当前问题仍有证据缺口",
        "继续检索针对性证据",
    ),
    ("budget_exhausted", "resume_bounded_search", "本轮检索预算已用尽", "继续有界检索"),
    (
        "eligible_next_hop",
        "traverse_relationship",
        "可继续探索已验证的关联",
        "探索已验证关联",
    ),
)
_CONTINUATION_OPERATION_PUBLIC_LABEL = {
    operation: label for _, operation, _, label in _CONTINUATION_PUBLIC_COPY
}


class _MissingS11AChatAdapter(RuntimeError):
    """Exact S11A RED sentinel before fixture or runtime effects."""


class _FailureAdapterOverrides(TypedDict, total=False):
    plan_after: Callable[[Any], Any]
    read_after: Callable[[Any], Any]
    answer_after: Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class _S11ASeam:
    service_module: Any
    contracts_module: Any
    route_module: Any
    deps_module: Any
    legacy_module: Any
    app: Any
    adapter_type: type[Any]
    checkpoint_type: type[Any]


class _StageProbe:
    """Narrow real-stage delegate used only for counts and fault injection."""

    def __init__(
        self,
        delegate: Any,
        *,
        stage: str,
        effects: dict[str, int],
        before: Callable[[Any], Any] | None = None,
        after: Callable[[Any], Any] | None = None,
    ) -> None:
        self._delegate = delegate
        self._stage = stage
        self._effects = effects
        self._before = before
        self._after = after

    def __deepcopy__(self, memo: dict[int, Any]) -> _StageProbe:
        return _StageProbe(
            copy.deepcopy(self._delegate, memo),
            stage=self._stage,
            effects=self._effects,
            before=self._before,
            after=self._after,
        )

    def _invoke(self, method_name: str, value: Any) -> Any:
        self._effects[self._stage] += 1
        bound = self._before(value) if self._before is not None else value
        result = getattr(self._delegate, method_name)(bound)
        return self._after(result) if self._after is not None else result

    def plan(self, value: Any) -> Any:
        return self._invoke("plan", value)

    def execute(self, value: Any) -> Any:
        return self._invoke("execute", value)

    def answer(self, value: Any) -> Any:
        return self._invoke("answer", value)


def _required_attr(module: Any, name: str) -> Any:
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise _MissingS11AChatAdapter(
            f"exact S11A seam is absent: {module.__name__}.{name}"
        ) from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def test_public_citation_uses_official_homepage_without_internal_identity() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    answer = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    evidence = read.EvidenceItem(
        evidence_id="evidence:s12d:ding-homepage",
        object_id="professor-c-ding-wenbo",
        domain="professor",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:internal",
        snippet=json.dumps(
            {
                "name": "丁文伯",
                "homepage": "http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
            },
            ensure_ascii=False,
        ),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=read.EvidenceClaimBinding(
            subject_id="professor-c-ding-wenbo",
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    handle = read.CanonicalEntityHandle(
        canonical_id=evidence.object_id,
        domain="professor",
        display_name="丁文伯",
        evidence_ids=(evidence.evidence_id,),
    )
    turn_result = answer.TurnResult(
        session_id="session:s12d-public-source",
        turn_id="turn:s12d-public-source",
        release_id=RELEASE_ID,
        answer_text="丁文伯简介",
        citations=(
            answer.Citation(
                evidence_id=evidence.evidence_id,
                source_nature="local",
                source_locator=evidence.source_locator,
            ),
        ),
    )

    citations = service.CanonicalV2ChatAdapter._public_citations(
        turn_result=turn_result,
        handles_by_id={handle.canonical_id: handle},
        evidence_by_id={evidence.evidence_id: evidence},
    )

    assert len(citations) == 1
    assert citations[0].url == "http://www.sigs.tsinghua.edu.cn/dwb/main.htm"
    assert "professor-c-ding-wenbo" not in citations[0].id
    assert "/browse" not in citations[0].url


@pytest.mark.parametrize(
    "url",
    [
        "http://100.64.0.4:18188/browse",
        "http://localhost:18188/browse",
        "https://canonical-v2.internal/browse",
    ],
)
def test_public_source_url_rejects_private_or_internal_hosts(url: str) -> None:
    service = import_module("backend.services.canonical_v2_chat")

    assert service._public_url(url) is None


def test_public_chat_response_omits_internal_evidence_and_trace() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    answer = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    evidence = read.EvidenceItem(
        evidence_id="evidence:s12d:private",
        object_id="professor-c-ding-wenbo",
        domain="professor",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:private-locator",
        snippet=json.dumps(
            {
                "name": "丁文伯",
                "homepage": "http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
            },
            ensure_ascii=False,
        ),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=read.EvidenceClaimBinding(
            subject_id="professor-c-ding-wenbo",
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    handle = read.CanonicalEntityHandle(
        canonical_id=evidence.object_id,
        domain="professor",
        display_name="丁文伯",
        evidence_ids=(evidence.evidence_id,),
    )
    plan = read.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query="介绍清华的丁文伯",
        behavior_class="A",
        release_id=RELEASE_ID,
        domains=("professor",),
        protected_slots=(),
        lanes=("exact", "web"),
        max_candidates=5,
        web_required=True,
        web_policy=read.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1000,
            max_results=5,
        ),
    )
    evidence_set = read.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=plan.original_query,
        protected_slots=(),
        items=(evidence,),
        traces=(),
        limitations=(),
        entity_handles=(handle,),
    )
    turn_result = answer.TurnResult(
        session_id="session:s12d-public-envelope",
        turn_id="turn:s12d-public-envelope",
        release_id=RELEASE_ID,
        answer_text="丁文伯简介",
        citations=(
            answer.Citation(
                evidence_id=evidence.evidence_id,
                source_nature="local",
                source_locator=evidence.source_locator,
            ),
        ),
        render_mode="prose_renderer",
    )
    outcome = service._CanonicalV2ChatOutcome(
        query=plan.original_query,
        plan=plan,
        evidence_set=evidence_set,
        turn_result=turn_result,
    )
    adapter = object.__new__(service.CanonicalV2ChatAdapter)

    response = adapter._map_response(outcome)

    assert response.evidence == []
    assert response.structured_payload == {}
    serialized = json.dumps(response.model_dump(mode="json"), ensure_ascii=False)
    assert "canonical-v2-isolated" not in serialized
    assert RELEASE_ID not in serialized
    assert "professor-c-ding-wenbo" not in serialized


def test_isolated_read_integrity_error_is_a_stable_public_conflict() -> None:
    seam = _load_s11a_seam()
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read_isolated")

    class _FailingAdapter:
        def answer(self, **_: Any) -> Any:
            raise read_module.IsolatedKnowledgeReadIntegrityError(
                "private release-bound lookup detail"
            )

    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: _FailingAdapter()
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat",
            json={"query": "介绍一家机器人企业", "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    assert response.status_code == 409
    assert response.json() == {"detail": "canonical_v2_consumer_integrity_error"}
    assert "private release-bound lookup detail" not in response.text


def test_audit_only_candidate_evidence_does_not_break_retained_item_closure() -> None:
    consumer = import_module("backend.services.canonical_v2_admin")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    plan = read.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query="介绍目标公司",
        behavior_class="A",
        release_id=RELEASE_ID,
        domains=("company",),
        protected_slots=(),
        lanes=("exact",),
        max_candidates=1,
        web_required=False,
        supplemental_budget=read.SupplementalBudget(
            max_wall_time_ms=0,
            max_provider_calls=0,
            max_retries=0,
            max_cost_units=0.0,
        ),
    )
    evidence = read.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=plan.original_query,
        protected_slots=(),
        items=(),
        traces=(),
        limitations=(),
        candidate_traces=(
            read.CandidateTrace(
                raw_candidate_id="raw-candidate:dropped",
                query_view="view:original",
                lane="exact",
                attempt=1,
                release_id=RELEASE_ID,
                adapter_version="recorded-exact-v1",
                provider_version=None,
                raw_score=0.5,
                evidence_ids=("evidence:audit-only",),
                disposition="result_limit_rejected",
            ),
        ),
    )

    assert consumer._validated_evidence_set(evidence, plan=plan) == evidence

    live_reference = evidence.model_copy(
        update={
            "entity_handles": (
                read.CanonicalEntityHandle(
                    canonical_id="company:missing",
                    domain="company",
                    display_name="Missing Company",
                    evidence_ids=("evidence:missing-live-reference",),
                ),
            )
        }
    )
    with pytest.raises(
        consumer.CanonicalV2ConsumerIntegrityError,
        match="evidence metadata references an absent item",
    ):
        consumer._validated_evidence_set(live_reference, plan=plan)


def test_multi_turn_planning_carries_only_the_explicit_referent_scope() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    displayed = ("professor:active", "professor:other")

    assert service._planning_displayed_ids(
        query="他是否有参与哪些企业的创立",
        displayed_ids=displayed,
        active_anchor_id="professor:active",
    ) == ("professor:active",)
    assert (
        service._planning_displayed_ids(
            query="上述教授发表过哪些论文",
            displayed_ids=displayed,
            active_anchor_id="professor:active",
        )
        == displayed
    )
    assert (
        service._planning_displayed_ids(
            query="专利 CN117873146A 的详细信息是什么",
            displayed_ids=displayed,
            active_anchor_id="professor:active",
        )
        == ()
    )


def test_independent_turn_declares_topic_switch_but_referential_turn_does_not() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    evidence_set = read.EvidenceSet(
        release_id=RELEASE_ID,
        original_query="专利 CN117873146A 的详细信息是什么",
        protected_slots=(),
        items=(),
        traces=(),
        limitations=(),
    )
    committed = cast(Any, object())

    independent = service.CanonicalV2ChatAdapter._session_directive(
        committed=committed,
        evidence_set=evidence_set,
        planning_displayed_ids=(),
        selection=None,
    )
    assert independent is not None
    assert independent.transition == "topic_switch"

    referential = service.CanonicalV2ChatAdapter._session_directive(
        committed=committed,
        evidence_set=evidence_set,
        planning_displayed_ids=("paper:active",),
        selection=None,
    )
    assert referential is None


def _load_s11a_seam() -> _S11ASeam:
    targets = (
        "backend.services.canonical_v2_chat",
        "backend.api.chat_contracts",
        "backend.api.canonical_v2_chat",
    )
    loaded: list[Any] = []
    for target in targets:
        try:
            loaded.append(import_module(target))
        except ModuleNotFoundError as exc:
            if exc.name != target:
                raise
            raise _MissingS11AChatAdapter(
                f"exact S11A seam module is absent: {target}"
            ) from exc

    service_module, contracts_module, route_module = loaded
    deps_module = import_module("backend.canonical_v2_deps")
    legacy_module = import_module("backend.api.chat")
    app = import_module("backend.main").app
    adapter_type = _required_attr(service_module, "CanonicalV2ChatAdapter")
    checkpoint_type = _required_attr(service_module, "ChatFeedbackCheckpoint")
    getter = _required_attr(deps_module, "get_canonical_v2_chat_adapter")
    _required_attr(route_module, "router")
    for model_name in CHAT_MODEL_NAMES:
        _required_attr(contracts_module, model_name)
        if _required_attr(legacy_module, model_name) is not _required_attr(
            contracts_module, model_name
        ):
            raise _MissingS11AChatAdapter(
                f"legacy chat does not identity re-export {model_name}"
            )
    schema_payload = {
        name: _required_attr(contracts_module, name).model_json_schema()
        for name in CHAT_MODEL_NAMES
    }
    if _canonical_sha256(schema_payload) != CHAT_SCHEMA_SHA256:
        raise _MissingS11AChatAdapter(
            "moved chat contracts do not preserve the frozen Pydantic schemas"
        )

    if tuple(inspect.signature(adapter_type).parameters) != (
        "release_id",
        "planner",
        "knowledge_read",
        "answer_factory",
        "answer_session_fork",
    ):
        raise _MissingS11AChatAdapter(
            "CanonicalV2ChatAdapter lacks the exact explicit release-bound constructor"
        )
    if tuple(inspect.signature(adapter_type.answer).parameters) != (
        "self",
        "query",
        "session_id",
        "option_id",
        "as_of",
    ):
        raise _MissingS11AChatAdapter(
            "CanonicalV2ChatAdapter.answer lacks the exact explicit input boundary"
        )
    expected_checkpoint_fields = (
        "session_id",
        "turn_id",
        "release_id",
        "query_trace_id",
        "answer_trace_id",
        "evidence_ids",
        "affected_domains",
        "affected_paths",
        "limitation_codes",
        "observed_at",
        "content_sha256",
    )
    if tuple(checkpoint_type.model_fields) != expected_checkpoint_fields:
        raise _MissingS11AChatAdapter(
            "ChatFeedbackCheckpoint lacks the exact immutable public evidence shape"
        )
    if getter.__module__ != "backend.canonical_v2_deps":
        raise _MissingS11AChatAdapter(
            "chat adapter dependency is not owned by the V2-only dependency seam"
        )

    post_chat = tuple(
        route
        for route in app.routes
        if route.path == "/api/chat" and "POST" in (route.methods or set())
    )
    if len(post_chat) != 1:
        raise _MissingS11AChatAdapter(
            "exactly one registered POST /api/chat route is required"
        )
    endpoint = post_chat[0].endpoint
    if endpoint is legacy_module.chat or endpoint.__module__ != route_module.__name__:
        raise _MissingS11AChatAdapter(
            "registered POST /api/chat is not the V2-only endpoint"
        )
    endpoint_parameters = inspect.signature(endpoint).parameters
    if "conn" in endpoint_parameters:
        raise _MissingS11AChatAdapter(
            "registered POST /api/chat still has a direct SQL dependency"
        )

    return _S11ASeam(
        service_module=service_module,
        contracts_module=contracts_module,
        route_module=route_module,
        deps_module=deps_module,
        legacy_module=legacy_module,
        app=app,
        adapter_type=adapter_type,
        checkpoint_type=checkpoint_type,
    )


def _load_accepted_logical_fixture_owner() -> Any:
    owner_path = (
        Path(__file__).resolve().parents[3]
        / "apps/miroflow-agent/tests/canonical_v2"
        / "test_internal_reference_projection_contract.py"
    )
    assert hashlib.sha256(owner_path.read_bytes()).hexdigest() == (
        ACCEPTED_PHYSICAL_OWNER_SHA256
    )
    spec = util.spec_from_file_location("_s11a_accepted_physical_owner", owner_path)
    if spec is None or spec.loader is None:
        raise AssertionError("accepted S8X physical owner cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _materialize_release_bound_scenario(
    *,
    scenario: dict[str, Any],
    tmp_path: Path,
) -> dict[str, Any]:
    """Rebuild the accepted logical fixture onto a fresh guarded physical target."""

    isolated_index_module = import_module(
        "src.data_agents.canonical_v2.index_projection_isolated"
    )
    release_module = import_module(
        "src.data_agents.canonical_v2.release_publication_isolated"
    )
    repository_root = Path(__file__).resolve().parents[3]
    backup_gate_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_milvus_sha256 = (
        hashlib.sha256(original_milvus.read_bytes()).hexdigest()
        if original_milvus.is_file()
        else None
    )
    target = isolated_index_module.prepare_isolated_index_target(
        root=(tmp_path / "canonical-v2-s11a-index").resolve(strict=False),
        target_id="canonical-v2-s11a-index",
        release_id=scenario["bundle"].release_id,
        backup_gate_root=backup_gate_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    physical_result = isolated_index_module.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=backup_gate_root,
        embedding_adapter=isolated_index_module.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        clock=lambda: NOW,
    ).build(scenario["index_request"])
    assert physical_result == scenario["bundle"].index_result
    physical_bundle = release_module.IsolatedReleaseBundle(
        manifest=scenario["bundle"].manifest,
        index_result=physical_result,
        index_target=target,
        relationship_projection_request=(
            scenario["bundle"].relationship_projection_request
        ),
        relationship_projection_result=(
            scenario["bundle"].relationship_projection_result
        ),
    )
    if original_milvus_sha256 is not None:
        assert hashlib.sha256(original_milvus.read_bytes()).hexdigest() == (
            original_milvus_sha256
        )
    return {
        **scenario,
        "bundle": physical_bundle,
        "original_milvus": original_milvus,
        "original_milvus_sha256": original_milvus_sha256,
    }


def _handle_id(handle: Any) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def _semantic_claim_text(request: Any, item: Any, binding: Any) -> str:
    handle_by_id = {
        _handle_id(handle): handle for handle in request.evidence_set.entity_handles
    }
    handle = handle_by_id.get(item.object_id) or handle_by_id.get(binding.subject_id)
    display_name = None if handle is None else handle.display_name
    projection: dict[str, Any] = {}
    if isinstance(item.snippet, str):
        try:
            loaded = json.loads(item.snippet)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            projection = loaded
    if display_name is None:
        for key in ("name", "title", "display_name"):
            value = projection.get(key)
            if isinstance(value, str) and value.strip():
                display_name = value.strip()
                break
    display_name = display_name or "所展示实体"
    if binding.predicate in {"canonical_projection", "semantic_recall"}:
        summary = projection.get("profile_summary")
        if isinstance(summary, str) and summary.strip():
            return f"{display_name}：{summary.strip()}"
        domain_label = {
            "company": "公司",
            "paper": "论文",
            "patent": "专利",
            "professor": "教授",
        }.get(item.domain, "实体")
        return f"{display_name} 由已接受的本地{domain_label}档案证据支持。"
    if binding.predicate == "patent_has_applicant":
        applicant_name = projection.get("name")
        if isinstance(applicant_name, str) and applicant_name.strip():
            return f"{display_name} 的申请人为 {applicant_name.strip()}。"
        return f"{display_name} 具有已接受的专利申请人关系证据。"
    if binding.predicate in {
        "professor_attributed_to_paper",
        "company_has_patent",
    }:
        return f"已接受的类型化关系证据支持与 {display_name} 相关的当前结果。"
    return f"{display_name} 由已接受的类型化证据支持。"


def _answer_proposal(answer_module: Any, request: Any) -> Any:
    handle_ids = tuple(
        _handle_id(handle) for handle in request.evidence_set.entity_handles
    )
    evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
    claims: tuple[Any, ...] = ()
    if handle_ids and evidence_by_id:
        item = next(iter(evidence_by_id.values()))
        binding = item.claim_binding
        assert binding is not None
        claims = (
            answer_module.MaterialClaimProposal(
                claim_id=f"claim:s11a:{request.turn_id}",
                text=_semantic_claim_text(request, item, binding),
                subject_id=binding.subject_id,
                predicate=binding.predicate,
                value=binding.value,
                evidence_ids=(item.evidence_id,),
                status=binding.status,
            ),
        )
    return answer_module.AnswerSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id=f"answer-selection:s11a:{request.turn_id}",
        model_id="recorded-s11a-answer-selector",
        prompt_version="answer-selector-s11a-v1",
        decision_run_id=f"answer-selection-run:s11a:{request.turn_id}",
        answer_text=f"{RAW_SELECTOR_DRAFT} {SECRET_SENTINEL}",
        claims=claims,
        displayed_handle_ids=handle_ids,
        continuation_candidate_ids=tuple(
            candidate.candidate_id
            for candidate in request.evidence_set.continuation_candidates
        ),
    )


def _checkpoint_bytes(checkpoint: Any) -> bytes:
    return json.dumps(
        checkpoint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@pytest.mark.parametrize(
    ("reason", "operation", "expected_prompt", "expected_label"),
    _CONTINUATION_PUBLIC_COPY,
)
def test_s9j_chat_adapter_maps_continuation_execution_to_public_copy(
    reason: str,
    operation: str,
    expected_prompt: str,
    expected_label: str,
) -> None:
    seam = _load_s11a_seam()
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    company_id = "company:s9j-public-copy"
    evidence_id = "evidence:s9j:public-copy"
    handle = read_module.CanonicalEntityHandle(
        canonical_id=company_id,
        domain="company",
        display_name="Robotics Co",
        evidence_ids=(evidence_id,),
    )
    option = answer_module.ContinuationOption(
        option_id=f"continuation-option:s9j:{operation}",
        label=f"POISON {reason} {operation}",
        operation=operation,
        target_handle_ids=(company_id,),
        evidence_ids=(evidence_id,),
    )
    turn_result = answer_module.TurnResult(
        session_id=f"session:s9j:{operation}",
        turn_id=f"turn:s9j:{operation}",
        release_id=RELEASE_ID,
        answer_text="Safe grounded answer.",
        continuation_offer=answer_module.ContinuationOffer(
            offer_id=f"continuation-offer:s9j:{operation}",
            reasons=(reason,),
            options=(option,),
        ),
    )

    public = seam.adapter_type._clarification(
        turn_result=turn_result,
        handles_by_id={company_id: handle},
    )

    assert public is not None
    assert public.prompt == expected_prompt
    assert len(public.options) == 1
    assert public.options[0].label == expected_label
    assert public.options[0].hint == expected_label
    public_copy = (
        public.prompt,
        public.options[0].label,
        public.options[0].hint,
    )
    assert all(reason not in value for value in public_copy)
    assert all(operation not in value for value in public_copy)
    assert all("POISON" not in value for value in public_copy)


def _assert_checkpoint_matches(
    checkpoint: Any,
    *,
    session_id: str,
    evidence_set: Any,
    turn_result: Any,
    observed_at: datetime,
) -> None:
    expected_evidence_ids = tuple(item.evidence_id for item in evidence_set.items)
    expected_domains = tuple(sorted({item.domain for item in evidence_set.items}))
    expected_paths = (
        ()
        if turn_result.traversal_receipt is None
        else (turn_result.traversal_receipt.path_id,)
    )
    expected_limitation_codes = tuple(
        limitation.code for limitation in turn_result.limitations
    )
    assert checkpoint.session_id == session_id == turn_result.session_id
    assert checkpoint.turn_id == turn_result.turn_id
    assert checkpoint.release_id == evidence_set.release_id == turn_result.release_id
    assert checkpoint.query_trace_id == (
        f"evidence-set:sha256:{_canonical_sha256(evidence_set.model_dump(mode='json'))}"
    )
    assert checkpoint.answer_trace_id == (
        f"turn-result:sha256:{_canonical_sha256(turn_result.model_dump(mode='json'))}"
    )
    assert checkpoint.evidence_ids == expected_evidence_ids
    assert checkpoint.affected_domains == expected_domains
    assert checkpoint.affected_paths == expected_paths
    assert checkpoint.limitation_codes == expected_limitation_codes
    assert checkpoint.observed_at == observed_at
    assert checkpoint.content_sha256 == _canonical_sha256(
        checkpoint.model_dump(mode="json", exclude={"content_sha256"})
    )


def test_s11a_post_chat_uses_release_bound_canonical_v2_without_legacy_sql(
    request: pytest.FixtureRequest,
) -> None:
    seam = _load_s11a_seam()

    # The seam check above is intentionally before every fixture, client, SQL,
    # provider, release, or answer-session effect.
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    monkeypatch.setattr(seam.route_module, "_utc_now", lambda: NOW)
    fixture_owner = _load_accepted_logical_fixture_owner()
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_read_module = import_module(
        "src.data_agents.canonical_v2.knowledge_read_isolated"
    )
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")

    scenario = _materialize_release_bound_scenario(
        scenario=fixture_owner._s8r2_scenario(
            tmp_path=tmp_path,
            release_id=RELEASE_ID,
        ),
        tmp_path=tmp_path,
    )
    bundle = scenario["bundle"]
    published = scenario["published"]
    index_request = scenario["index_request"]
    institution_catalog = scenario["catalog"]
    assert bundle.release_id == published.release_id == RELEASE_ID

    planning_policy = read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s11a-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=("professor", "company", "paper", "patent"),
        supported_lanes=("exact", "relationship", "web"),
        supported_relationship_paths=(("company_has_patent", "company_to_patent"),),
        max_candidates=20,
        max_provider_calls=1,
        max_planning_attempts=1,
    )
    revenue_part = read_module.MaterialQuestionPart(
        part_id="material-part:s11a-current-revenue",
        text="核实 Robotics Co 的 2026 年当前营收",
        subject_id="company-robotics",
        predicate="current_revenue",
        requested_value="2026",
    )

    def proposal_provider(value: Any) -> Any:
        if value.original_query == RELATIONSHIP_QUERY:
            return read_module.RecordedPlanningProposal(
                proposal_id=f"planning-proposal:s11a:relationship:{value.request_id}",
                request_sha256=value.content_sha256,
                schema_version="retrieval-plan-proposal-v1",
                model_id="recorded-s11a-planner",
                prompt_version="query-plan-prompt-v1",
                behavior_class="E",
                interaction_mode="information_retrieval",
                domains=("patent",),
                lanes=("relationship", "web"),
                relationship_paths=(
                    read_module.RelationshipPathProposal(
                        relationship_type_id="company_has_patent",
                        direction="company_to_patent",
                        source_type="company",
                        target_type="patent",
                    ),
                ),
                max_candidates=20,
                max_provider_calls=1,
                enumeration_mode="representative",
                web_mode="universal",
                max_web_results=5,
            )
        return read_module.RecordedPlanningProposal(
            proposal_id=f"planning-proposal:s11a:exact:{value.request_id}",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-s11a-planner",
            prompt_version="query-plan-prompt-v1",
            behavior_class="A",
            interaction_mode="information_retrieval",
            domains=("company",),
            lanes=("exact", "web"),
            material_parts=(
                (revenue_part,) if value.original_query == INITIAL_QUERY else ()
            ),
            max_candidates=20,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=5,
        )

    release_planner = isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
    )

    supplemental_budget = read_module.SupplementalBudget(
        max_wall_time_ms=1_000,
        max_provider_calls=2,
        max_retries=1,
        max_cost_units=5.0,
    )

    def bind_server_owned_plan_controls(value: Any) -> Any:
        """Apply Accepted S8C/S8R2 caller-owned controls to one real plan."""

        updates: dict[str, Any] = {
            "supplemental_budget": supplemental_budget.model_dump(mode="json")
        }
        if (
            value.enumeration_policy is None
            and len(value.relationship_paths) == 1
            and (
                value.relationship_paths[0].relationship_type_id,
                value.relationship_paths[0].direction,
            )
            in set(planning_policy.supported_relationship_paths)
            and value.relationship_paths[0].source_type
            in set(planning_policy.public_domains)
            and value.relationship_paths[0].target_type
            in set(planning_policy.public_domains)
            and value.structured_constraints.displayed_entity_ids
        ):
            updates["enumeration_policy"] = read_module.EnumerationPolicy(
                mode="representative",
                scope=fixture_owner.S8R2_SCOPE,
                as_of=value.as_of,
                exhaustive=False,
                continuation_state="available",
            ).model_dump(mode="json")
        return read_module.RetrievalPlan.model_validate(
            {
                **value.model_dump(mode="json", exclude={"content_sha256"}),
                **updates,
            }
        )

    provider_effects = {"web": 0, "supplemental": 0}

    def web_search(_: Any) -> Any:
        provider_effects["web"] += 1
        return read_module.RetrievalLaneResult()

    def missing_sufficiency(value: Any) -> Any:
        return read_module.SufficiencyProposal(
            decision_input_sha256=value.content_sha256,
            schema_version="sufficiency-v1",
            decision_id=f"sufficiency:s11a:{value.plan_id}",
            parts=tuple(
                read_module.MaterialPartProposal(
                    part_id=part.part_id,
                    outcome="missing",
                    evidence_ids=(),
                    rationale="No retained evidence supports the requested value.",
                    uncertainty="high",
                    confidence=0.0,
                )
                for part in value.material_parts
            ),
        )

    def supplemental_search(_: Any) -> Any:
        provider_effects["supplemental"] += 1
        return read_module.SupplementalLaneResult(
            items=(),
            elapsed_ms=1,
            cost_units=0.0,
            retryable=False,
        )

    release_read = isolated_read_module.create_isolated_release_knowledge_read(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=5,
        ),
        web_search=web_search,
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s11a",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        sufficiency_decider=missing_sufficiency,
        supplemental_search=supplemental_search,
        web_handle_ttl=timedelta(hours=1),
        clock=lambda: NOW,
    )

    def real_answer_factory() -> Any:
        return answer_module.create_ephemeral_knowledge_answer(
            answer_selector=lambda value: _answer_proposal(answer_module, value)
        )

    def make_adapter(
        *,
        planner: Any = release_planner,
        knowledge_read: Any = release_read,
        plan_after: Callable[[Any], Any] | None = None,
        read_after: Callable[[Any], Any] | None = None,
        answer_after: Callable[[Any], Any] | None = None,
        answer_factory_builder: Callable[[], Any] = real_answer_factory,
        captured: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, int]]:
        effects = {"plan": 0, "read": 0, "answer": 0}

        def observed_after(
            stage: str,
            delegate: Callable[[Any], Any] | None,
        ) -> Callable[[Any], Any]:
            def observe(value: Any) -> Any:
                bound = (
                    bind_server_owned_plan_controls(value) if stage == "plan" else value
                )
                if delegate is not None:
                    bound = delegate(bound)
                if captured is not None:
                    captured[stage] = bound
                return bound

            return observe

        def answer_factory() -> Any:
            return _StageProbe(
                answer_factory_builder(),
                stage="answer",
                effects=effects,
                after=observed_after("answer", answer_after),
            )

        adapter = seam.adapter_type(
            release_id=RELEASE_ID,
            planner=_StageProbe(
                planner,
                stage="plan",
                effects=effects,
                before=(
                    lambda value: (
                        (captured.__setitem__("plan_request", value) or value)
                        if captured is not None
                        else value
                    )
                ),
                after=observed_after("plan", plan_after),
            ),
            knowledge_read=_StageProbe(
                knowledge_read,
                stage="read",
                effects=effects,
                before=(
                    lambda value: (
                        (captured.__setitem__("read_request", value) or value)
                        if captured is not None
                        else value
                    )
                ),
                after=observed_after("read", read_after),
            ),
            answer_factory=answer_factory,
            answer_session_fork=copy.deepcopy,
        )
        return adapter, effects

    app = seam.app
    prior_runtime = getattr(app.state, "canonical_v2_chat_adapter", None)
    had_runtime = hasattr(app.state, "canonical_v2_chat_adapter")
    prior_dependency_overrides = dict(app.dependency_overrides)
    legacy_effects = {"chat": 0, "sql": 0, "operations": 0}

    def forbidden_effect(kind: str) -> Callable[..., Any]:
        def fail(*_: Any, **__: Any) -> Any:
            legacy_effects[kind] += 1
            raise AssertionError(f"forbidden S11A effect reached: {kind}")

        return fail

    original_legacy_dependency = seam.legacy_module.get_pg_conn
    app.dependency_overrides[original_legacy_dependency] = forbidden_effect("sql")
    monkeypatch.setattr(seam.legacy_module, "chat", forbidden_effect("chat"))
    monkeypatch.setattr(seam.legacy_module, "get_pg_conn", forbidden_effect("sql"))
    monkeypatch.setattr(
        seam.deps_module,
        "_compose_operations",
        forbidden_effect("operations"),
    )

    def cleanup() -> None:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior_dependency_overrides)
        if had_runtime:
            app.state.canonical_v2_chat_adapter = prior_runtime
        elif hasattr(app.state, "canonical_v2_chat_adapter"):
            delattr(app.state, "canonical_v2_chat_adapter")

    request.addfinalizer(cleanup)

    if hasattr(app.state, "canonical_v2_chat_adapter"):
        delattr(app.state, "canonical_v2_chat_adapter")
    no_runtime_client = TestClient(app, raise_server_exceptions=False)
    missing_runtime = no_runtime_client.post(
        "/api/chat", json={"query": SIMPLE_QUERY, "entity_id_hint": None}
    )
    assert missing_runtime.status_code == 503
    assert missing_runtime.json()["detail"] == RUNTIME_UNAVAILABLE
    assert legacy_effects == {"chat": 0, "sql": 0, "operations": 0}
    assert provider_effects == {"web": 0, "supplemental": 0}

    app.state.canonical_v2_chat_adapter = object()
    wrong_runtime = no_runtime_client.post(
        "/api/chat", json={"query": SIMPLE_QUERY, "entity_id_hint": None}
    )
    assert wrong_runtime.status_code == 503
    assert wrong_runtime.json()["detail"] == RUNTIME_UNAVAILABLE
    assert legacy_effects == {"chat": 0, "sql": 0, "operations": 0}
    assert provider_effects == {"web": 0, "supplemental": 0}

    captured: dict[str, Any] = {}
    adapter, effects = make_adapter(captured=captured)
    app.state.canonical_v2_chat_adapter = adapter
    client = TestClient(app, raise_server_exceptions=False)
    first_http = client.post(
        "/api/chat", json={"query": INITIAL_QUERY, "entity_id_hint": None}
    )
    assert first_http.status_code == 200
    first = seam.contracts_module.ChatResponse.model_validate(first_http.json())
    assert first.query == INITIAL_QUERY
    assert first.query_type.startswith("canonical_v2:")
    assert first.answer_text
    assert first.answer_style == "template"
    assert set(type(first).model_fields) == {
        "query",
        "query_type",
        "answer_text",
        "citations",
        "evidence",
        "clarification",
        "structured_payload",
        "answer_style",
        "citation_map",
        "suggested_followups",
    }
    first_cookie = first_http.headers["set-cookie"]
    first_cookie_lower = first_cookie.casefold()
    assert f"miroflow_chat_session={client.cookies.get('miroflow_chat_session')}" in (
        first_cookie
    )
    assert "path=/" in first_cookie_lower
    assert "max-age=1800" in first_cookie_lower
    assert "httponly" in first_cookie_lower
    assert "samesite=lax" in first_cookie_lower
    serialized_first = json.dumps(first.model_dump(mode="json"), ensure_ascii=False)
    assert RAW_SELECTOR_DRAFT not in serialized_first
    assert SECRET_SENTINEL not in serialized_first
    assert all(
        citation.type in {"professor", "company", "paper", "patent"}
        for citation in first.citations
    )
    assert all("/browse" not in citation.url for citation in first.citations)
    assert first.citation_map == {
        str(index): citation.id
        for index, citation in enumerate(first.citations, start=1)
    }
    first_plan = captured["plan"]
    first_evidence_set = captured["read"]
    first_turn_result = captured["answer"]
    assert first.evidence == []
    assert first.structured_payload == {}
    trace = adapter._trace(  # noqa: SLF001 - server-side trace stays private
        SimpleNamespace(
            plan=first_plan,
            evidence_set=first_evidence_set,
            turn_result=first_turn_result,
        )
    )
    assert trace["release_id"] == RELEASE_ID
    assert trace["plan_id"] == first_plan.plan_id
    assert trace["plan_version"] == first_plan.plan_version
    assert trace["behavior_class"] == first_plan.behavior_class == "A"
    assert trace["interaction_mode"] == first_plan.interaction_mode
    assert trace["lanes"] == list(first_plan.lanes) == ["exact", "web"]
    assert trace["retrieval_traces"] == [
        item.model_dump(mode="json") for item in first_evidence_set.traces
    ]
    assert trace["sufficiency_report"] == (
        None
        if first_evidence_set.sufficiency_report is None
        else first_evidence_set.sufficiency_report.model_dump(mode="json")
    )
    assert trace["enumeration_coverage"] == (
        None
        if first_turn_result.enumeration_coverage is None
        else first_turn_result.enumeration_coverage.model_dump(mode="json")
    )
    assert trace["evidence_ids"] == [
        item.evidence_id for item in first_evidence_set.items
    ]
    assert trace["evidence_source_natures"] == [
        item.source_nature for item in first_evidence_set.items
    ]
    assert trace["entity_handles"] == [
        handle.model_dump(mode="json") for handle in first_evidence_set.entity_handles
    ]
    assert trace["claims"] == [
        claim.model_dump(mode="json") for claim in first_turn_result.claims
    ]
    assert trace["claim_evidence_mappings"] == [
        mapping.model_dump(mode="json")
        for mapping in first_turn_result.claim_evidence_map
    ]
    assert trace["limitations"] == [
        limitation.model_dump(mode="json")
        for limitation in first_turn_result.limitations
    ]
    assert trace["conflicts"] == [
        conflict.model_dump(mode="json") for conflict in first_turn_result.conflicts
    ]
    assert trace["selector_traces"] == [
        selector.model_dump(mode="json")
        for selector in first_turn_result.selector_traces
    ]
    assert trace["context_receipt"] == (
        None
        if first_turn_result.context_receipt is None
        else first_turn_result.context_receipt.model_dump(mode="json")
    )
    assert trace["traversal_receipt"] == (
        None
        if first_turn_result.traversal_receipt is None
        else first_turn_result.traversal_receipt.model_dump(mode="json")
    )
    assert trace["interpretation_notice"] == (
        None
        if first_turn_result.interpretation_notice is None
        else first_turn_result.interpretation_notice.model_dump(mode="json")
    )
    assert trace["continuation_offer"] == (
        None
        if first_turn_result.continuation_offer is None
        else first_turn_result.continuation_offer.model_dump(mode="json")
    )
    retained_evidence_ids = {item.evidence_id for item in first_evidence_set.items}
    handle_ids = {_handle_id(handle) for handle in first_evidence_set.entity_handles}
    allowed_subject_ids = handle_ids | {
        f"canonical:{handle.domain}:{_handle_id(handle)}"
        for handle in first_evidence_set.entity_handles
        if handle.kind == "canonical"
    }
    assert all(
        set(claim.evidence_ids) <= retained_evidence_ids
        and claim.subject_id in allowed_subject_ids
        for claim in first_turn_result.claims
    )
    assert all(
        set(mapping.evidence_ids) <= retained_evidence_ids
        and mapping.subject_id in allowed_subject_ids
        for mapping in first_turn_result.claim_evidence_map
    )
    assert all(
        citation.evidence_id in retained_evidence_ids
        for citation in first_turn_result.citations
    )
    assert all(citation.id in handle_ids for citation in first.citations)
    assert "selector_draft" not in trace
    assert "release_manifest" not in trace
    assert first.clarification is not None
    assert 0 < len(first.clarification.options) <= 3
    option = first.clarification.options[0]
    assert first_turn_result.continuation_offer is not None
    answer_options = first_turn_result.continuation_offer.options
    assert [candidate.id for candidate in first.clarification.options] == [
        candidate.option_id for candidate in answer_options
    ]
    assert [candidate.label for candidate in first.clarification.options] == [
        _CONTINUATION_OPERATION_PUBLIC_LABEL[candidate.operation]
        for candidate in answer_options
    ]
    assert all(
        set(candidate.target_handle_ids) <= handle_ids for candidate in answer_options
    )
    handle_domain_by_id = {
        _handle_id(handle): handle.domain
        for handle in first_evidence_set.entity_handles
    }
    for compatibility_option, answer_option in zip(
        first.clarification.options,
        answer_options,
        strict=True,
    ):
        target_domains = {
            handle_domain_by_id[handle_id]
            for handle_id in answer_option.target_handle_ids
        }
        assert len(target_domains) == 1
        assert compatibility_option.domain == next(iter(target_domains))
    assert first.clarification.default_id == ""
    assert first.suggested_followups == [
        candidate.label for candidate in first.clarification.options
    ]
    first_binding = first_evidence_set.items[0].claim_binding
    assert first_binding is not None
    assert any(
        claim["subject_id"] == first_binding.subject_id
        and claim["predicate"] == first_binding.predicate
        and claim["value"] == first_binding.value
        and claim["status"] == first_binding.status
        for claim in trace["claims"]
    )
    sufficiency = trace["sufficiency_report"]
    assert sufficiency is not None and sufficiency["complete"] is False
    assert any(
        part["part_id"] == "material-part:s11a-current-revenue"
        and part["outcome"] == "missing"
        for part in sufficiency["parts"]
    )
    continuation = trace["continuation_offer"]
    assert continuation is not None
    assert continuation["options"][0]["operation"] == "targeted_evidence_search"

    public_strings = [
        first.answer_text,
        first.clarification.prompt,
        *(candidate.label for candidate in first.clarification.options),
        *(candidate.hint for candidate in first.clarification.options),
        *first.suggested_followups,
    ]
    assert "Robotics Co" in first.answer_text
    assert "Robotics company." in first.answer_text
    assert "2026 年当前营收" in first.answer_text
    assert "保留证据不足以支持" in first.answer_text
    assert all(re.search(r"[0-9a-f]{64}", value) is None for value in public_strings)
    assert all(
        marker not in value
        for value in public_strings
        for marker in (
            "canonical:",
            "reference:",
            "evidence:",
            "continuation-option:",
            "continuation-candidate:",
            "evidence_gap",
            "targeted_evidence_search",
        )
    )
    session_id = client.cookies.get("miroflow_chat_session")
    assert session_id
    assert captured["read_request"].session_id == session_id
    checkpoint = adapter.get_feedback_checkpoint(session_id)
    assert checkpoint is not None
    assert type(checkpoint) is seam.checkpoint_type
    _assert_checkpoint_matches(
        checkpoint,
        session_id=session_id,
        evidence_set=first_evidence_set,
        turn_result=first_turn_result,
        observed_at=NOW,
    )
    assert adapter.get_feedback_checkpoint("session:s11a:unknown") is None
    with pytest.raises((ValidationError, AttributeError), match="frozen|attribute"):
        checkpoint.session_id = "forbidden"  # type: ignore[misc]
    assert not hasattr(adapter, "set_feedback_checkpoint")
    assert not hasattr(adapter, "prepare")
    assert not hasattr(adapter, "commit")
    assert not hasattr(adapter, "rollback")

    before_invalid = (dict(effects), dict(provider_effects))
    unknown_option = client.post(
        "/api/chat",
        json={"query": INITIAL_QUERY, "entity_id_hint": "option:s11a:unknown"},
    )
    assert unknown_option.status_code == 400
    assert unknown_option.json()["detail"] == INVALID_SELECTION
    assert (effects, provider_effects) == before_invalid

    for surrogate in (option.label, INITIAL_QUERY):
        surrogate_selection = client.post(
            "/api/chat",
            json={"query": INITIAL_QUERY, "entity_id_hint": surrogate},
        )
        assert surrogate_selection.status_code == 400
        assert surrogate_selection.json()["detail"] == INVALID_SELECTION
        assert (effects, provider_effects) == before_invalid

    cross_session_client = TestClient(app, raise_server_exceptions=False)
    cross_session = cross_session_client.post(
        "/api/chat",
        json={"query": INITIAL_QUERY, "entity_id_hint": option.id},
    )
    assert cross_session.status_code == 400
    assert cross_session.json()["detail"] == INVALID_SELECTION
    assert (effects, provider_effects) == before_invalid

    second_http = client.post(
        "/api/chat",
        json={"query": INITIAL_QUERY, "entity_id_hint": option.id},
    )
    assert second_http.status_code == 200
    second = seam.contracts_module.ChatResponse.model_validate(second_http.json())
    assert second.evidence == []
    assert second.structured_payload == {}
    second_trace = adapter._trace(  # noqa: SLF001
        SimpleNamespace(
            plan=captured["plan"],
            evidence_set=captured["read"],
            turn_result=captured["answer"],
        )
    )
    assert captured["answer"].context_receipt is not None
    assert second_trace["context_receipt"] == captured[
        "answer"
    ].context_receipt.model_dump(mode="json")
    assert second_trace["context_receipt"]["selected_option_id"] == option.id
    assert second_trace["context_receipt"]["selected_operation"] == (
        "targeted_evidence_search"
    )
    assert option.id in json.dumps(second_trace, ensure_ascii=False)

    consumed_effects = (dict(effects), dict(provider_effects))
    consumed = client.post(
        "/api/chat",
        json={"query": INITIAL_QUERY, "entity_id_hint": option.id},
    )
    assert consumed.status_code == 400
    assert consumed.json()["detail"] == INVALID_SELECTION
    assert (effects, provider_effects) == consumed_effects

    third_http = client.post(
        "/api/chat", json={"query": RELATIONSHIP_QUERY, "entity_id_hint": None}
    )
    assert third_http.status_code == 200
    third = seam.contracts_module.ChatResponse.model_validate(third_http.json())
    third_evidence_set = captured["read"]
    third_turn_result = captured["answer"]
    assert third.evidence == []
    assert third.structured_payload == {}
    third_trace = adapter._trace(  # noqa: SLF001
        SimpleNamespace(
            plan=captured["plan"],
            evidence_set=third_evidence_set,
            turn_result=third_turn_result,
        )
    )
    third_planning_request = captured["plan_request"]
    assert third_planning_request.enumeration_context is not None
    assert third_planning_request.enumeration_context.requested is True
    assert third_planning_request.enumeration_context.scope == RELATIONSHIP_QUERY
    assert third_planning_request.enumeration_context.as_of == NOW
    assert third_planning_request.displayed_entity_names == ("Robotics Co",)
    assert third_trace["release_id"] == RELEASE_ID
    assert third_trace["lanes"] == ["relationship", "web"]
    assert third_trace["evidence_ids"] == [
        item.evidence_id for item in third_evidence_set.items
    ]
    assert third_trace["sufficiency_report"] == (
        None
        if third_evidence_set.sufficiency_report is None
        else third_evidence_set.sufficiency_report.model_dump(mode="json")
    )
    assert third_trace["enumeration_coverage"] == (
        None
        if third_turn_result.enumeration_coverage is None
        else third_turn_result.enumeration_coverage.model_dump(mode="json")
    )
    assert third_trace["entity_handles"] == [
        handle.model_dump(mode="json") for handle in third_evidence_set.entity_handles
    ]
    assert third_trace["claims"] == [
        claim.model_dump(mode="json") for claim in third_turn_result.claims
    ]
    assert third_trace["claim_evidence_mappings"] == [
        mapping.model_dump(mode="json")
        for mapping in third_turn_result.claim_evidence_map
    ]
    assert third_trace["limitations"] == [
        limitation.model_dump(mode="json")
        for limitation in third_turn_result.limitations
    ]
    assert third_turn_result.traversal_receipt is not None
    assert third_turn_result.context_receipt is not None
    assert third_trace["context_receipt"] == (
        third_turn_result.context_receipt.model_dump(mode="json")
    )
    assert third_trace["traversal_receipt"] == (
        third_turn_result.traversal_receipt.model_dump(mode="json")
    )
    third_retained_evidence_ids = {
        item.evidence_id for item in third_evidence_set.items
    }
    assert all(
        set(claim.evidence_ids) <= third_retained_evidence_ids
        for claim in third_turn_result.claims
    )
    traversal = third_trace["traversal_receipt"]
    assert traversal["path_id"] == "company_to_patent"
    assert traversal["source_handle_ids"] == ["company-robotics"]
    assert traversal["target_handle_ids"] == ["patent-ada"]
    assert "Robot control system" in third.answer_text
    assert "Robotics Co" in third.answer_text
    assert effects["plan"] == effects["read"] == effects["answer"] == 3
    assert legacy_effects == {"chat": 0, "sql": 0, "operations": 0}
    third_checkpoint = adapter.get_feedback_checkpoint(session_id)
    assert third_checkpoint is not None
    assert third_checkpoint != checkpoint
    _assert_checkpoint_matches(
        third_checkpoint,
        session_id=session_id,
        evidence_set=captured["read"],
        turn_result=captured["answer"],
        observed_at=NOW,
    )

    reset_http = client.post("/api/chat/session/reset")
    assert reset_http.status_code == 200
    assert set(reset_http.json()) == {"session_id"}
    reset_session_id = reset_http.json()["session_id"]
    assert reset_session_id
    assert reset_session_id != session_id
    assert client.cookies.get("miroflow_chat_session") == reset_session_id
    reset_cookie = reset_http.headers["set-cookie"]
    reset_cookie_lower = reset_cookie.casefold()
    assert f"miroflow_chat_session={reset_session_id}" in reset_cookie
    assert "path=/" in reset_cookie_lower
    assert "max-age=1800" in reset_cookie_lower
    assert "httponly" in reset_cookie_lower
    assert "samesite=lax" in reset_cookie_lower
    assert adapter.get_feedback_checkpoint(reset_session_id) is None
    assert adapter.get_feedback_checkpoint(session_id) == third_checkpoint
    reset_fresh_http = client.post(
        "/api/chat", json={"query": SIMPLE_QUERY, "entity_id_hint": None}
    )
    assert reset_fresh_http.status_code == 200
    reset_fresh = seam.contracts_module.ChatResponse.model_validate(
        reset_fresh_http.json()
    )
    assert reset_fresh.evidence == []
    assert reset_fresh.structured_payload == {}
    reset_context = captured["answer"].context_receipt
    assert reset_context is None or (
        reset_context.selected_option_id is None
        and reset_context.selected_operation is None
    )
    reset_checkpoint = adapter.get_feedback_checkpoint(reset_session_id)
    assert reset_checkpoint is not None
    _assert_checkpoint_matches(
        reset_checkpoint,
        session_id=reset_session_id,
        evidence_set=captured["read"],
        turn_result=captured["answer"],
        observed_at=NOW,
    )

    stale_adapter, stale_effects = make_adapter()
    app.state.canonical_v2_chat_adapter = stale_adapter
    stale_client = TestClient(app, raise_server_exceptions=False)
    stale_first_http = stale_client.post(
        "/api/chat", json={"query": INITIAL_QUERY, "entity_id_hint": None}
    )
    assert stale_first_http.status_code == 200
    stale_first = seam.contracts_module.ChatResponse.model_validate(
        stale_first_http.json()
    )
    assert stale_first.clarification is not None
    stale_option_id = stale_first.clarification.options[0].id
    stale_replacement = stale_client.post(
        "/api/chat", json={"query": SIMPLE_QUERY, "entity_id_hint": None}
    )
    assert stale_replacement.status_code == 200
    stale_before = (dict(stale_effects), dict(provider_effects))
    stale_selection = stale_client.post(
        "/api/chat",
        json={"query": INITIAL_QUERY, "entity_id_hint": stale_option_id},
    )
    assert stale_selection.status_code == 400
    assert stale_selection.json()["detail"] == INVALID_SELECTION
    assert (stale_effects, provider_effects) == stale_before

    for wording_kind in ("option_label", "option_bearing_original_query"):
        wording_captured: dict[str, Any] = {}
        wording_adapter, _ = make_adapter(captured=wording_captured)
        app.state.canonical_v2_chat_adapter = wording_adapter
        wording_client = TestClient(app, raise_server_exceptions=False)
        wording_first_http = wording_client.post(
            "/api/chat", json={"query": INITIAL_QUERY, "entity_id_hint": None}
        )
        assert wording_first_http.status_code == 200
        wording_first = seam.contracts_module.ChatResponse.model_validate(
            wording_first_http.json()
        )
        assert wording_first.clarification is not None
        ordinary_query_wording = (
            wording_first.clarification.options[0].label
            if wording_kind == "option_label"
            else wording_first.query
        )
        wording_http = wording_client.post(
            "/api/chat",
            json={"query": ordinary_query_wording, "entity_id_hint": None},
        )
        assert wording_http.status_code == 200
        wording = seam.contracts_module.ChatResponse.model_validate(wording_http.json())
        assert wording.structured_payload == {}
        wording_context = wording_captured["answer"].context_receipt
        assert wording_context is None or (
            wording_context.selected_option_id is None
            and wording_context.selected_operation is None
        )

    simple_adapter, _ = make_adapter()
    app.state.canonical_v2_chat_adapter = simple_adapter
    simple_client = TestClient(app, raise_server_exceptions=False)
    simple_http = simple_client.post(
        "/api/chat", json={"query": SIMPLE_QUERY, "entity_id_hint": None}
    )
    assert simple_http.status_code == 200
    simple = seam.contracts_module.ChatResponse.model_validate(simple_http.json())
    assert simple.clarification is None
    assert simple.suggested_followups == []
    assert simple.evidence == []
    assert simple.structured_payload == {}

    def timed_out_renderer(_: Any) -> Any:
        raise TimeoutError("recorded S11A prose renderer timeout")

    def degraded_answer_factory() -> Any:
        return answer_module.create_ephemeral_knowledge_answer(
            answer_selector=lambda value: _answer_proposal(answer_module, value),
            prose_renderer=timed_out_renderer,
        )

    degraded_captured: dict[str, Any] = {}
    degraded_adapter, _ = make_adapter(
        answer_factory_builder=degraded_answer_factory,
        captured=degraded_captured,
    )
    app.state.canonical_v2_chat_adapter = degraded_adapter
    degraded_client = TestClient(app, raise_server_exceptions=False)
    degraded_http = degraded_client.post(
        "/api/chat", json={"query": INITIAL_QUERY, "entity_id_hint": None}
    )
    assert degraded_http.status_code == 200
    degraded = seam.contracts_module.ChatResponse.model_validate(degraded_http.json())
    degraded_turn = degraded_captured["answer"]
    assert degraded.answer_style == "template"
    assert degraded_turn.render_mode == "deterministic_fallback"
    assert degraded_turn.claims
    assert degraded_turn.citations
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.stage == "prose"
        and limitation.failure_kind == "timeout"
        for limitation in degraded_turn.limitations
    )
    assert degraded.evidence == []
    assert degraded.structured_payload == {}
    degraded_trace = degraded_adapter._trace(  # noqa: SLF001
        SimpleNamespace(
            plan=degraded_captured["plan"],
            evidence_set=degraded_captured["read"],
            turn_result=degraded_turn,
        )
    )
    assert degraded_trace["claims"] == [
        claim.model_dump(mode="json") for claim in degraded_turn.claims
    ]
    assert degraded_trace["limitations"] == [
        limitation.model_dump(mode="json") for limitation in degraded_turn.limitations
    ]
    assert RAW_SELECTOR_DRAFT not in degraded.model_dump_json()
    assert SECRET_SENTINEL not in degraded.model_dump_json()
    degraded_session = degraded_client.cookies.get("miroflow_chat_session")
    assert degraded_session
    degraded_checkpoint = degraded_adapter.get_feedback_checkpoint(degraded_session)
    assert degraded_checkpoint is not None
    _assert_checkpoint_matches(
        degraded_checkpoint,
        session_id=degraded_session,
        evidence_set=degraded_captured["read"],
        turn_result=degraded_turn,
        observed_at=NOW,
    )
    assert "prose_synthesis_failed" in degraded_checkpoint.limitation_codes

    ambiguity_policy = read_module.AmbiguityPolicy(
        policy_id="ambiguity-policy:s11a",
        policy_version="ambiguity-policy-v1",
        entity_type="company",
        minimum_evidence_count=1,
        confidence_threshold=0.7,
        minimum_lead_margin=0.2,
    )
    blocking_planner = isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
        ambiguity_policy=ambiguity_policy,
    )

    def add_blocking_candidates(value: Any) -> Any:
        if value.original_query != BLOCKING_QUERY:
            return value
        candidates = (
            read_module.AmbiguityCandidate(
                candidate_id="candidate:s11a:blocking:nanshan",
                entity_type="company",
                canonical_id="company-robotics",
                display_name="同名机器人公司",
                evidence_ids=("evidence:s11a:blocking:nanshan",),
                evidence_confidence=0.9,
                model_confidence=0.9,
                discriminators=(
                    read_module.CandidateDiscriminator(
                        kind="district",
                        value="南山",
                        evidence_ids=("evidence:s11a:blocking:nanshan",),
                    ),
                ),
            ),
            read_module.AmbiguityCandidate(
                candidate_id="candidate:s11a:blocking:baoan",
                entity_type="company",
                canonical_id="company-s11a-other",
                display_name="同名机器人公司",
                evidence_ids=("evidence:s11a:blocking:baoan",),
                evidence_confidence=0.8,
                model_confidence=0.8,
                discriminators=(
                    read_module.CandidateDiscriminator(
                        kind="district",
                        value="宝安",
                        evidence_ids=("evidence:s11a:blocking:baoan",),
                    ),
                ),
            ),
        )
        payload = value.model_dump(
            mode="json",
            exclude={
                "content_sha256",
                "original_query_sha256",
                "ambiguity_candidate_manifest_sha256",
            },
        )
        payload["ambiguity_candidates"] = [
            candidate.model_dump(mode="json") for candidate in candidates
        ]
        return read_module.QueryPlanningRequest.model_validate(payload)

    blocking_effects = {"plan": 0, "read": 0, "answer": 0}

    def blocking_answer_factory() -> Any:
        return _StageProbe(
            real_answer_factory(),
            stage="answer",
            effects=blocking_effects,
        )

    blocking_adapter = seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_StageProbe(
            blocking_planner,
            stage="plan",
            effects=blocking_effects,
            before=add_blocking_candidates,
            after=bind_server_owned_plan_controls,
        ),
        knowledge_read=_StageProbe(
            release_read,
            stage="read",
            effects=blocking_effects,
        ),
        answer_factory=blocking_answer_factory,
        answer_session_fork=copy.deepcopy,
    )
    app.state.canonical_v2_chat_adapter = blocking_adapter
    blocking_client = TestClient(app, raise_server_exceptions=False)
    blocking_http = blocking_client.post(
        "/api/chat", json={"query": BLOCKING_QUERY, "entity_id_hint": None}
    )
    assert blocking_http.status_code == 200
    blocking = seam.contracts_module.ChatResponse.model_validate(blocking_http.json())
    assert blocking.answer_text
    assert blocking.clarification is not None
    assert blocking.clarification.options == []
    assert blocking.clarification.default_id == ""
    assert blocking.evidence == []
    assert blocking.structured_payload == {}
    assert blocking_effects == {"plan": 1, "read": 1, "answer": 1}

    def once_after_success(
        transform: Callable[[Any], Any],
    ) -> Callable[[Any], Any]:
        invocation_count = 0

        def invoke(value: Any) -> Any:
            nonlocal invocation_count
            invocation_count += 1
            return transform(value) if invocation_count == 2 else value

        return invoke

    def stage_exception(stage: str) -> Callable[[Any], Any]:
        def fail(_: Any) -> Any:
            raise RuntimeError(f"forced S11A {stage} exception")

        return fail

    def wrong_release(value: Any) -> Any:
        return value.model_copy(update={"release_id": "candidate-s11a-wrong-release"})

    def hostile_mapper_input(value: Any) -> Any:
        assert value.claims
        assert value.claim_evidence_map
        poisoned_evidence_id = "evidence:s11a:undisplayed-mapper-input"
        poisoned_claim = value.claims[0].model_copy(
            update={"evidence_ids": (poisoned_evidence_id,)}
        )
        poisoned_mapping = value.claim_evidence_map[0].model_copy(
            update={"evidence_ids": (poisoned_evidence_id,)}
        )
        return value.model_copy(
            update={
                "claims": (poisoned_claim,),
                "claim_evidence_map": (poisoned_mapping,),
            }
        )

    failure_cases: tuple[tuple[str, str, _FailureAdapterOverrides, int], ...] = (
        (
            "planner_exception",
            "plan",
            {"plan_after": once_after_success(stage_exception("planner"))},
            500,
        ),
        (
            "read_exception",
            "read",
            {"read_after": once_after_success(stage_exception("read"))},
            500,
        ),
        (
            "answer_exception",
            "answer",
            {"answer_after": once_after_success(stage_exception("answer"))},
            500,
        ),
        (
            "plan_release_mismatch",
            "plan",
            {"plan_after": once_after_success(wrong_release)},
            409,
        ),
        (
            "read_release_mismatch",
            "read",
            {"read_after": once_after_success(wrong_release)},
            409,
        ),
        (
            "answer_release_mismatch",
            "answer",
            {"answer_after": once_after_success(wrong_release)},
            409,
        ),
        (
            "compatibility_mapping_failure",
            "answer",
            {"answer_after": once_after_success(hostile_mapper_input)},
            500,
        ),
    )

    def establish_state(target_adapter: Any) -> tuple[Any, str, Any, bytes]:
        app.state.canonical_v2_chat_adapter = target_adapter
        target_client = TestClient(app, raise_server_exceptions=False)
        established_http = target_client.post(
            "/api/chat", json={"query": INITIAL_QUERY, "entity_id_hint": None}
        )
        assert established_http.status_code == 200
        established = seam.contracts_module.ChatResponse.model_validate(
            established_http.json()
        )
        assert established.clarification is not None
        established_option = established.clarification.options[0]
        established_session = target_client.cookies.get("miroflow_chat_session")
        assert established_session
        established_checkpoint = target_adapter.get_feedback_checkpoint(
            established_session
        )
        assert established_checkpoint is not None
        return (
            target_client,
            established_session,
            established_option,
            _checkpoint_bytes(established_checkpoint),
        )

    for case_id, failed_stage, kwargs, expected_status in failure_cases:
        failing_captured: dict[str, Any] = {}
        failing_adapter, failing_effects = make_adapter(
            plan_after=kwargs.get("plan_after"),
            read_after=kwargs.get("read_after"),
            answer_after=kwargs.get("answer_after"),
            captured=failing_captured,
        )
        (
            failing_client,
            failing_session,
            failing_option,
            checkpoint_before_failure,
        ) = establish_state(failing_adapter)
        effects_before_failure = dict(failing_effects)
        failed_http = failing_client.post(
            "/api/chat",
            json={"query": INITIAL_QUERY, "entity_id_hint": failing_option.id},
        )
        assert failed_http.status_code == expected_status, case_id
        if expected_status == 409:
            assert failed_http.json()["detail"] == RELEASE_MISMATCH
        assert RAW_SELECTOR_DRAFT not in failed_http.text
        assert SECRET_SENTINEL not in failed_http.text
        if failed_stage == "plan":
            assert failing_effects["read"] == effects_before_failure["read"]
            assert failing_effects["answer"] == effects_before_failure["answer"]
        elif failed_stage == "read":
            assert failing_effects["answer"] == effects_before_failure["answer"]
        checkpoint_after_failure = failing_adapter.get_feedback_checkpoint(
            failing_session
        )
        assert checkpoint_after_failure is not None
        assert _checkpoint_bytes(checkpoint_after_failure) == (
            checkpoint_before_failure
        )
        retry_http = failing_client.post(
            "/api/chat",
            json={"query": INITIAL_QUERY, "entity_id_hint": failing_option.id},
        )
        assert retry_http.status_code == 200, case_id
        retry = seam.contracts_module.ChatResponse.model_validate(retry_http.json())
        assert retry.structured_payload == {}
        retry_context = failing_captured["answer"].context_receipt
        assert retry_context is not None
        assert retry_context.selected_option_id == failing_option.id
        assert retry_context.selected_operation == "targeted_evidence_search"

    validation_captured: dict[str, Any] = {}
    validation_adapter, _ = make_adapter(captured=validation_captured)
    (
        validation_client,
        validation_session,
        validation_option,
        checkpoint_before_validation,
    ) = establish_state(validation_adapter)

    def reject_response(
        cls: type[Any],
        value: Any,
        *_: Any,
        **__: Any,
    ) -> Any:
        raise ValueError("forced S11A ChatResponse validation failure")

    with monkeypatch.context() as response_failure:
        response_failure.setattr(
            seam.contracts_module.ChatResponse,
            "model_validate",
            classmethod(reject_response),
        )
        validation_failure = validation_client.post(
            "/api/chat",
            json={"query": INITIAL_QUERY, "entity_id_hint": validation_option.id},
        )
    assert validation_failure.status_code == 500
    checkpoint_after_validation = validation_adapter.get_feedback_checkpoint(
        validation_session
    )
    assert checkpoint_after_validation is not None
    assert _checkpoint_bytes(checkpoint_after_validation) == (
        checkpoint_before_validation
    )
    validation_retry_http = validation_client.post(
        "/api/chat",
        json={"query": INITIAL_QUERY, "entity_id_hint": validation_option.id},
    )
    assert validation_retry_http.status_code == 200
    validation_retry = seam.contracts_module.ChatResponse.model_validate(
        validation_retry_http.json()
    )
    assert validation_retry.structured_payload == {}
    validation_context = validation_captured["answer"].context_receipt
    assert validation_context is not None
    assert validation_context.selected_option_id == validation_option.id
    assert validation_context.selected_operation == "targeted_evidence_search"

    public_adapter_names = {name for name in dir(adapter) if not name.startswith("_")}
    assert public_adapter_names >= {"answer", "get_feedback_checkpoint"}
    assert not public_adapter_names & {
        "set_feedback_checkpoint",
        "prepare",
        "commit",
        "rollback",
        "sessions",
        "checkpoints",
    }

    quarantine_script = """
import sys
for name in (
    'backend.api.chat',
    'backend.deps',
    'backend.api.chat_contracts',
    'backend.api.canonical_v2_chat',
    'backend.canonical_v2_deps',
    'backend.services.canonical_v2_chat',
):
    sys.modules.pop(name, None)
import backend.api.chat_contracts
import backend.api.canonical_v2_chat
import backend.canonical_v2_deps
import backend.services.canonical_v2_chat
forbidden_prefixes = (
    'backend.api.chat',
    'backend.deps',
    'backend.storage',
    'src.data_agents.providers',
    'src.data_agents.canonical',
    'src.data_agents.publish',
    'src.data_agents.quality',
    'src.data_agents.service.retrieval',
    'src.data_agents.service.search_service',
    'src.data_agents.paper.milvus_backfill',
    'src.data_agents.storage.milvus_collections',
    'src.data_agents.storage.milvus_store',
    'pymilvus',
)
writer_fragments = (
    '.canonical_import',
    '.canonical_writer',
    '.identity_status_writer',
    '.quality_promotion',
    '.release',
    '.vectorizer',
)
forbidden = sorted(
    name for name in sys.modules
    if name == 'src.data_agents.canonical'
    or any(
        name == prefix or name.startswith(prefix + '.')
        for prefix in forbidden_prefixes
    )
    or any(fragment in name for fragment in writer_fragments)
)
if forbidden:
    raise SystemExit('forbidden imports: ' + ','.join(forbidden))
"""
    quarantine = subprocess.run(
        [sys.executable, "-c", quarantine_script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert quarantine.returncode == 0, quarantine.stdout + quarantine.stderr
    assert legacy_effects == {"chat": 0, "sql": 0, "operations": 0}
    if scenario["original_milvus_sha256"] is not None:
        assert (
            hashlib.sha256(scenario["original_milvus"].read_bytes()).hexdigest()
            == (scenario["original_milvus_sha256"])
        )
