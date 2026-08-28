from __future__ import annotations

import asyncio
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
import threading
from types import SimpleNamespace
from typing import Any, Callable, TypedDict, cast

from fastapi import Request, Response
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
    "3ae8b81597997b237e19017c8606d6e683f5b780a377e574916faa16abc3d98c"
)
CHAT_SCHEMA_SHA256 = "04f4bb9e7be272f5b508e22360759ed6b0b32c59a3ffc18fb2cb9cf057b8f91c"
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
    ("web_url", "expected"),
    (
        ("https://www.pudurobotics.com/en/products/flashbot-arm", True),
        ("https://products.pudurobotics.com/flashbot-arm", True),
        ("https://robot-news.example/pudu-flashbot-arm", False),
    ),
)
def test_public_web_citation_requires_same_entity_official_host(
    web_url: str,
    expected: bool,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    answer = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    company_id = "company-c-pudu"
    local = read.EvidenceItem(
        evidence_id="evidence:s12d:pudu-local",
        object_id=company_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:pudu",
        snippet=json.dumps(
            {
                "name": "深圳市普渡科技有限公司",
                "website": "https://www.pudurobotics.com/",
            },
            ensure_ascii=False,
        ),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=read.EvidenceClaimBinding(
            subject_id=company_id,
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    web = read.EvidenceItem(
        evidence_id="evidence:s12d:pudu-web-product",
        object_id="web-object:s12d:pudu-flashbot-arm",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator=web_url,
        snippet="FlashBot Arm 配备机械手，可直接按下电梯按钮。",
        score=1.0,
        source_authority="web_search",
        claim_binding=read.EvidenceClaimBinding(
            subject_id=company_id,
            predicate="current_web_result",
            value="b" * 64,
            status="observed",
        ),
    )
    handle = read.CanonicalEntityHandle(
        canonical_id=company_id,
        domain="company",
        display_name="深圳市普渡科技有限公司",
        evidence_ids=(local.evidence_id, web.evidence_id),
    )
    turn_result = answer.TurnResult(
        session_id="session:s12d-pudu-official-web",
        turn_id="turn:s12d-pudu-official-web",
        release_id=RELEASE_ID,
        answer_text="FlashBot Arm 可通过机械手直接按下电梯按钮。",
        citations=(
            answer.Citation(
                evidence_id=web.evidence_id,
                source_nature="current_web",
                source_locator=web.source_locator,
            ),
        ),
    )

    citations = service.CanonicalV2ChatAdapter._public_citations(
        turn_result=turn_result,
        handles_by_id={handle.canonical_id: handle},
        evidence_by_id={local.evidence_id: local, web.evidence_id: web},
    )

    # Contract change (fix-web-citations): non-official web evidence now
    # emits a web-type source card (user rule 尽量能指出处) instead of no
    # card at all; official-host matches keep their company card.
    if expected:
        assert citations and citations[0].type == "company"
    else:
        assert citations and citations[0].type == "web"
        assert citations[0].url == web_url
    if expected:
        assert citations[0].url == web_url


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
    canonical_id = "professor-c-0123456789abcdef01234567"
    internal_id = "PROF-8000C9F994C3"
    evidence = read.EvidenceItem(
        evidence_id="evidence:s12d:private",
        object_id=canonical_id,
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
            subject_id=canonical_id,
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
        answer_text=f"丁文伯公开简介。{internal_id}；后续公开结论保留。",
        citations=(
            answer.Citation(
                evidence_id=evidence.evidence_id,
                source_nature="local",
                source_locator=evidence.source_locator,
            ),
        ),
        response_mode="clarification_only",
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
    assert response.answer_text == "丁文伯公开简介。；后续公开结论保留。"
    assert response.clarification is not None
    assert response.clarification.prompt == response.answer_text
    serialized = json.dumps(response.model_dump(mode="json"), ensure_ascii=False)
    assert "canonical-v2-isolated" not in serialized
    assert RELEASE_ID not in serialized
    assert canonical_id not in serialized
    assert internal_id not in serialized


_REFUSAL_ANCHOR_NAME = "国际先进技术应用推进中心（深圳）"


def _refusal_outcome(
    service: Any,
    *,
    answer_text: str,
    response_mode: str = "answer",
    anchored: bool = True,
) -> Any:
    answer = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    handle = read.CanonicalEntityHandle(
        canonical_id="company-c-refusal-anchor",
        domain="company",
        display_name=_REFUSAL_ANCHOR_NAME,
        evidence_ids=(),
    )
    plan = read.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query=f"介绍{_REFUSAL_ANCHOR_NAME}",
        behavior_class="A",
        release_id=RELEASE_ID,
        domains=("company",),
        protected_slots=(),
        lanes=("exact",),
        max_candidates=5,
        web_required=False,
    )
    evidence_set = read.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=plan.original_query,
        protected_slots=(),
        items=(),
        traces=(),
        limitations=(),
        entity_handles=(handle,),
    )
    turn_result = answer.TurnResult(
        session_id="session:s12d-refusal",
        turn_id="turn:s12d-refusal",
        release_id=RELEASE_ID,
        answer_text=answer_text,
        response_mode=response_mode,
        render_mode="deterministic_fallback",
        context_receipt=(
            answer.ContextReceipt(active_anchor=handle) if anchored else None
        ),
    )
    return service._CanonicalV2ChatOutcome(
        query=plan.original_query,
        plan=plan,
        evidence_set=evidence_set,
        turn_result=turn_result,
    )


@pytest.mark.parametrize(
    "refusal_text",
    (
        "暂无可直接确认的公开信息要点。",
        "No supported material claims are available.",
        "未提供具体的主体信息。",
    ),
)
def test_public_chat_response_softens_short_refusal_with_anchor(
    refusal_text: str,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    adapter = object.__new__(service.CanonicalV2ChatAdapter)

    response = adapter._map_response(
        _refusal_outcome(service, answer_text=refusal_text)
    )

    # Never-refuse contract (enforce-never-refuse-contracts): subject-first,
    # confirmed-identity statement, named coverage gap, actionable next step.
    assert response.answer_text.startswith(
        f"已确认您关注的是{_REFUSAL_ANCHOR_NAME}。"
    )
    assert "暂未能确认您问的具体内容" not in response.answer_text
    assert "换个角度" not in response.answer_text
    assert refusal_text not in response.answer_text
    assert "请提供" not in response.answer_text


def test_public_chat_response_softens_short_refusal_without_anchor() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    adapter = object.__new__(service.CanonicalV2ChatAdapter)

    response = adapter._map_response(
        _refusal_outcome(
            service,
            answer_text="暂无可直接确认的公开信息要点。",
            anchored=False,
        )
    )

    # No anchor: still contract-formed — actionable, no brush-off refusal.
    assert response.answer_text.startswith("已收到您的问题。")
    assert "暂未能确认您问的具体内容" not in response.answer_text
    assert "换个角度" not in response.answer_text
    assert "暂无可" not in response.answer_text


def test_public_chat_response_keeps_long_answer_with_refusal_fragment() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    adapter = object.__new__(service.CanonicalV2ChatAdapter)
    long_answer = "国际先进技术应用推进中心（深圳）是位于深圳的共性技术服务平台。" * 4 + "暂无可直接确认的公开信息要点。"

    response = adapter._map_response(
        _refusal_outcome(service, answer_text=long_answer)
    )

    assert response.answer_text == long_answer


def test_public_chat_response_keeps_clarification_only_text() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    adapter = object.__new__(service.CanonicalV2ChatAdapter)
    clarification_text = "Please provide one distinguishing detail so I can resolve the ambiguity."

    response = adapter._map_response(
        _refusal_outcome(
            service,
            answer_text=clarification_text,
            response_mode="clarification_only",
        )
    )

    assert response.answer_text == clarification_text


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


def test_pronoun_follow_up_binds_the_active_anchor() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    displayed = ("professor:active", "professor:other")

    for query in (
        "他有哪些代表性研究成果",
        "他的代表性论文有哪些",
        "那他还主持过哪些项目",
        "她有哪些专利",
        "那它支持哪些产品能力",
        "该学者的工作有哪些",
        "这位老师的研究方向是什么",
        "这个人创办过哪些公司",
    ):
        assert service._planning_displayed_ids(
            query=query,
            displayed_ids=displayed,
            active_anchor_id="professor:active",
        ) == ("professor:active",), query

    # Pronoun-like compounds and pronoun-less turns must not hijack the anchor.
    for query in (
        "其他公司有哪些",
        "其它专利有哪些",
        "吉他品牌有哪些",
        "专利 CN117873146A 的详细信息是什么",
    ):
        assert (
            service._planning_displayed_ids(
                query=query,
                displayed_ids=displayed,
                active_anchor_id="professor:active",
            )
            == ()
        ), query

    # A pronoun without an anchor binds nothing instead of crashing.
    assert (
        service._planning_displayed_ids(
            query="他有哪些代表性研究成果",
            displayed_ids=displayed,
            active_anchor_id=None,
        )
        == ()
    )


def test_set_follow_up_binds_the_displayed_result_set() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    displayed = ("professor:active", "professor:other")

    for query in (
        "上述企业里总部在深圳的有哪些",
        "它们分别是什么",
        "他们有哪些专利",
        "这几家企业哪家更强",
        "这两篇论文的区别是什么",
        "这两位教授谁更适合",
        "已展示的专利有哪些",
    ):
        assert (
            service._planning_displayed_ids(
                query=query,
                displayed_ids=displayed,
                active_anchor_id="professor:active",
            )
            == displayed
        ), query

    # Expansion requests ask beyond the displayed set; they bind neither the
    # anchor nor the set until a real expansion operation exists.
    for query in (
        "还有哪些企业",
        "其他的呢",
    ):
        assert (
            service._planning_displayed_ids(
                query=query,
                displayed_ids=displayed,
                active_anchor_id="professor:active",
            )
            == ()
        ), query


def test_continuation_follow_up_binds_the_active_anchor() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    displayed = ("professor:active", "professor:other")

    for query in (
        # The reported live case: "介绍X" first turn, this follow-up second.
        "有没有更详细的信息",
        "还有更多信息吗",
        "能再详细点吗",
        "详细说说",
        "再展开讲讲",
    ):
        assert service._planning_displayed_ids(
            query=query,
            displayed_ids=displayed,
            active_anchor_id="professor:active",
        ) == ("professor:active",), query

    # Without an anchor an elaboration follow-up binds nothing instead of
    # hijacking the displayed set.
    assert (
        service._planning_displayed_ids(
            query="有没有更详细的信息",
            displayed_ids=displayed,
            active_anchor_id=None,
        )
        == ()
    )

    # Expansion phrasings that merely share the 还有/有没有 opening are not
    # continuations and must keep binding nothing.
    for query in (
        "还有哪些企业",
        "有没有类似的",
    ):
        assert (
            service._planning_displayed_ids(
                query=query,
                displayed_ids=displayed,
                active_anchor_id="professor:active",
            )
            == ()
        ), query


def _soft_anchor_web_turn() -> tuple[Any, Any, Any]:
    """One web-lane item plus its single web entity handle (web-only turn)."""
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    item = read.EvidenceItem(
        evidence_id="evidence:soft:ubtech-web",
        object_id="web-object:soft:ubtech",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://www.ubt-robotics.example/about",
        snippet="优必选科技是一家深圳人形机器人公司。",
        score=1.0,
        source_authority="web_search",
        claim_binding=read.EvidenceClaimBinding(
            subject_id="web-object:soft:ubtech",
            predicate="current_web_result",
            value="c" * 64,
            status="observed",
        ),
    )
    handle = read.WebEntityHandle(
        handle_id="web-handle:soft:ubtech",
        domain="company",
        display_name="优必选",
        evidence_snapshot_ids=("snapshot:soft:ubtech",),
        evidence_ids=(item.evidence_id,),
        resolution_state="unresolved",
        candidate_canonical_ids=(),
        originating_query="优必选公司怎么样",
        origin_lane="web",
        origin_attempt=1,
    )
    return read, item, handle


class _SoftAnchorPlanner:
    """One trivial plan per turn, recording every planning request."""

    def __init__(self, captured: list[Any]) -> None:
        self._captured = captured

    def plan(self, request: Any) -> Any:
        self._captured.append(request)
        read = import_module("src.data_agents.canonical_v2.knowledge_read")
        return read.RetrievalPlan(
            plan_version="retrieval-plan-v1",
            original_query=request.original_query,
            behavior_class="A",
            release_id=RELEASE_ID,
            domains=("company",),
            protected_slots=(),
            lanes=("web",),
            max_candidates=5,
            web_required=False,
        )


class _SoftAnchorRead:
    """Scripted per-turn evidence, one entry per planned turn."""

    def __init__(self, script: list[tuple[tuple[Any, ...], tuple[Any, ...]]]) -> None:
        self._script = script

    def execute(self, plan: Any) -> Any:
        read = import_module("src.data_agents.canonical_v2.knowledge_read")
        items, handles = self._script.pop(0)
        return read.EvidenceSet(
            release_id=RELEASE_ID,
            original_query=plan.original_query,
            protected_slots=(),
            items=items,
            traces=(),
            limitations=(),
            entity_handles=handles,
        )


class _SoftAnchorAnswer:
    """Records turn requests; returns receipt-less grounded turn results."""

    def __init__(self, captured: list[Any]) -> None:
        self._captured = captured

    def answer(self, request: Any) -> Any:
        self._captured.append(request)
        answer = import_module("src.data_agents.canonical_v2.knowledge_answer")
        return answer.TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text=f"web answer for {request.query}",
            citations=(),
        )


def _soft_anchor_adapter(
    *,
    read_script: list[tuple[tuple[Any, ...], tuple[Any, ...]]],
    planning_requests: list[Any],
    answer_requests: list[Any],
) -> Any:
    service = import_module("backend.services.canonical_v2_chat")
    answer = _SoftAnchorAnswer(answer_requests)
    return service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_SoftAnchorPlanner(planning_requests),
        knowledge_read=_SoftAnchorRead(read_script),
        answer_factory=lambda: answer,
        answer_session_fork=lambda value: value,
    )


def test_web_only_elaboration_binds_the_soft_subject_anchor() -> None:
    """A web-only first answer leaves a soft subject anchor; an elaboration
    follow-up binds it into planning instead of clarifying, and the turn
    continues the session so prior web evidence carries over."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[
            ((web_item,), (web_handle,)),
            ((), ()),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-elaboration"

    first = adapter.answer(
        query="优必选公司怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.query_type != "canonical_v2:G:clarification_only"

    second = adapter.answer(
        query="有没有更详细的信息",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    # The soft anchor lets the elaboration through instead of clarifying, ...
    assert second.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 2
    # ... carries the prior subject name into planning, ...
    assert getattr(planning_requests[1], "soft_context_subject", None) == "优必选公司"
    # ... keeps the turn a continuation (no topic switch), ...
    assert answer_requests[1].session_directive is None
    # ... and therefore merges the prior web evidence into the follow-up read.
    assert web_item.evidence_id in {
        item.evidence_id for item in answer_requests[1].evidence_set.items
    }
    # The elaboration chain keeps the soft anchor for later turns.
    assert adapter._sessions[session_id].soft_subject_name == "优必选公司"


def test_web_only_expansion_follow_up_never_binds_the_soft_subject() -> None:
    """Expansion requests ("还有哪些类似的") ask beyond the current subject:
    binding the soft anchor would narrow instead of expand, so it stays out."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[
            ((web_item,), (web_handle,)),
            ((), ()),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-expansion"
    adapter.answer(
        query="优必选公司怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    second = adapter.answer(
        query="还有哪些类似的",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 2
    assert getattr(planning_requests[1], "soft_context_subject", None) is None


def test_explicit_named_follow_up_overrides_the_soft_subject() -> None:
    """A follow-up naming its own subject never borrows the soft anchor: the
    turn anchors on the subject derived from its own query instead."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[
            ((web_item,), (web_handle,)),
            ((), ()),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-explicit-override"
    adapter.answer(
        query="优必选公司怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    second = adapter.answer(
        query="大疆创新科技有限公司怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 2
    # Intentional behavior change (Task 10): the stored "优必选公司" anchor is
    # still never injected on an explicit-subject turn, but the turn now
    # anchors on the subject derived from its own query.
    assert (
        getattr(planning_requests[1], "soft_context_subject", None)
        == "大疆创新科技有限公司"
    )


def test_fresh_turn_org_query_soft_subject_derivation() -> None:
    """A fresh-turn web-only org query anchors THIS turn: the subject derived
    from the query itself is injected into planning and the answer request,
    instead of only taking effect from the next continuation turn."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,))],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-fresh-org"

    response = adapter.answer(
        query="介绍一下国际先进技术应用推进中心",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert response.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 1
    assert (
        getattr(planning_requests[0], "soft_context_subject", None)
        == "国际先进技术应用推进中心"
    )
    # The same anchor reaches the answer session on this turn, ...
    assert answer_requests[0].soft_context_subject == "国际先进技术应用推进中心"
    # ... and it is exactly the anchor the commit path stores for later turns.
    assert (
        adapter._sessions[session_id].soft_subject_name == "国际先进技术应用推进中心"
    )


def test_fresh_turn_qualified_org_query_soft_subject_derivation() -> None:
    """A branch-qualified org name keeps its qualifier: the derived subject
    matches the pinned commit-path extraction verbatim."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,))],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-fresh-qualified-org"

    response = adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert response.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 1
    assert (
        getattr(planning_requests[0], "soft_context_subject", None)
        == "国际先进技术应用推进中心（深圳）"
    )
    assert (
        answer_requests[0].soft_context_subject == "国际先进技术应用推进中心（深圳）"
    )


def test_continuation_anchor_still_wins_over_derivation() -> None:
    """A stored continuation anchor always wins over derivation: the
    elaboration follow-up would derive "有没有更详细" from its own query if
    the new branch overrode the anchor, so carrying the STORED name pins the
    priority explicitly."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[
            ((web_item,), (web_handle,)),
            ((), ()),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-continuation-priority"

    adapter.answer(
        query="优必选公司怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    second = adapter.answer(
        query="有没有更详细的信息",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 2
    assert getattr(planning_requests[1], "soft_context_subject", None) == "优必选公司"
    assert answer_requests[1].soft_context_subject == "优必选公司"


def test_explicit_subject_turn_keeps_topic_switch_directive() -> None:
    """Mid-session explicit org switch with no stored anchor: the request
    carries the derived subject, but _session_directive sees the
    continuation-only value, so the topic_switch decision is identical to
    pre-change behavior."""
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[
            # No web handle on the set turn: the commit-path handle fallback
            # must not store an anchor either.
            ((), ()),
            ((), ()),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:soft-anchor-explicit-topic-switch"

    # A set question stores no soft anchor and displays no canonical ids.
    adapter.answer(
        query="深圳有哪些机器人公司",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert adapter._sessions[session_id].soft_subject_name is None

    second = adapter.answer(
        query="介绍大疆创新科技有限公司",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert len(planning_requests) == 2
    # The derived current-query subject anchors this turn's planning/answer, ...
    assert (
        getattr(planning_requests[1], "soft_context_subject", None)
        == "大疆创新科技有限公司"
    )
    assert answer_requests[1].soft_context_subject == "大疆创新科技有限公司"
    # ... but session-transition semantics stay continuation-only: the turn
    # still declares a topic switch exactly as before.
    directive = answer_requests[1].session_directive
    assert directive is not None
    assert directive.transition == "topic_switch"


def test_question_echo_and_negation_queries_do_not_derive_soft_subject() -> None:
    """The garbage guards self-gate derivation: a whole-query echo and a
    negation query both anchor nothing on a fresh turn."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[
            ((web_item,), (web_handle,)),
            ((web_item,), (web_handle,)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    for index, query in enumerate(
        (
            # The search view is the whole query: the echo guard rejects it.
            "国际先进技术应用推进中心怎么样",
            # Negation markers return the query unchanged, also an echo.
            "不包括国际先进技术应用推进中心的介绍",
        )
    ):
        response = adapter.answer(
            query=query,
            session_id=f"session:soft-anchor-guard-{index}",
            option_id=None,
            as_of=NOW,
        )
        assert response.query_type != "canonical_v2:G:clarification_only", query

    assert len(planning_requests) == 2
    assert getattr(planning_requests[0], "soft_context_subject", None) is None
    assert getattr(planning_requests[1], "soft_context_subject", None) is None
    assert answer_requests[0].soft_context_subject is None
    assert answer_requests[1].soft_context_subject is None


def test_soft_subject_name_prefers_the_query_search_view_subject() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    read, web_item, web_handle = _soft_anchor_web_turn()

    def evidence_set(*handles: Any) -> Any:
        return read.EvidenceSet(
            release_id=RELEASE_ID,
            original_query="优必选公司怎么样",
            protected_slots=(),
            items=(web_item,),
            traces=(),
            limitations=(),
            entity_handles=handles,
        )

    def handle_with_name(name: str, token: str) -> Any:
        return read.WebEntityHandle(
            handle_id=f"web-handle:soft:{token}",
            domain="company",
            display_name=name,
            evidence_snapshot_ids=(f"snapshot:soft:{token}",),
            evidence_ids=(web_item.evidence_id,),
            resolution_state="unresolved",
            candidate_canonical_ids=(),
            originating_query="fixture",
            origin_lane="web",
            origin_attempt=1,
        )

    other_handle = handle_with_name("猎户星空", "orion")

    # The user's own query names the most reliable subject: it wins over any
    # handle display name and survives multi-handle evidence.
    assert (
        service._soft_subject_name(
            query="优必选公司怎么样",
            evidence_set=evidence_set(web_handle),
        )
        == "优必选公司"
    )
    assert (
        service._soft_subject_name(
            query="优必选公司怎么样",
            evidence_set=evidence_set(web_handle, other_handle),
        )
        == "优必选公司"
    )
    # Multi-handle evidence with an unextractable query anchors nothing.
    assert (
        service._soft_subject_name(
            query="深圳有哪些机器人公司",
            evidence_set=evidence_set(web_handle, other_handle),
        )
        is None
    )
    # A news-headline display name never binds: the query subject wins when
    # extractable, and the headline itself is rejected when it is not.
    headline_handle = handle_with_name(
        "河套数学与交叉学科研究院、国际先进技术应用推进中心（深圳）揭牌",
        "headline",
    )
    assert (
        service._soft_subject_name(
            query="介绍一下 国际先进技术应用推进中心（深圳）",
            evidence_set=evidence_set(headline_handle),
        )
        == "国际先进技术应用推进中心（深圳）"
    )
    assert (
        service._soft_subject_name(
            query="再介绍下",
            evidence_set=evidence_set(headline_handle),
        )
        is None
    )
    # Headline shapes: an enumerating 、 or an event-verb suffix disqualifies.
    assert (
        service._soft_subject_name(
            query="再介绍下",
            evidence_set=evidence_set(handle_with_name("优必选、大疆创新", "pair")),
        )
        is None
    )
    assert (
        service._soft_subject_name(
            query="再介绍下",
            evidence_set=evidence_set(handle_with_name("优必选科技发布", "verb")),
        )
        is None
    )
    # A clean single display name is the fallback when the query has none.
    assert (
        service._soft_subject_name(
            query="再介绍下",
            evidence_set=evidence_set(web_handle),
        )
        == "优必选"
    )
    # Garbage guards: question words never bind; whole-query echoes are only
    # rejected for QUESTION shapes — a bare entity-name query IS its own
    # subject (Phase 3.1, P3 relaxation: bare-name openings must establish
    # the soft subject instead of starving the follow-up into clarification).
    assert (
        service._soft_subject_name(
            query="深圳有哪些机器人公司",
            evidence_set=evidence_set(),
        )
        is None
    )
    assert (
        service._soft_subject_name(
            query="优必选",
            evidence_set=evidence_set(),
        )
        == "优必选"
    )


def test_soft_bound_continuation_is_not_a_topic_switch() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    evidence_set = read.EvidenceSet(
        release_id=RELEASE_ID,
        original_query="有没有更详细的信息",
        protected_slots=(),
        items=(),
        traces=(),
        limitations=(),
    )

    directive = service.CanonicalV2ChatAdapter._session_directive(
        committed=cast(Any, object()),
        evidence_set=evidence_set,
        planning_displayed_ids=(),
        selection=None,
        soft_context_subject="优必选",
    )

    assert directive is None


def test_continuation_with_soft_subject_skips_clarification() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    committed = SimpleNamespace(
        context_receipt=None,
        referent_history=(),
        soft_subject_name="优必选",
    )
    assert (
        service._referent_clarification_needed(
            query="有没有更详细的信息",
            committed=cast(Any, committed),
        )
        is False
    )
    # Without the soft anchor the same elaboration must still clarify.
    committed_without_soft = SimpleNamespace(
        context_receipt=None,
        referent_history=(),
    )
    assert (
        service._referent_clarification_needed(
            query="有没有更详细的信息",
            committed=cast(Any, committed_without_soft),
        )
        is True
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


@pytest.mark.parametrize(
    ("query", "has_anchor", "has_set", "expected"),
    (
        ("他有哪些代表性研究成果", False, False, True),
        ("这论文的链接是什么", False, False, True),
        ("该公司的专利有哪些", False, False, True),
        ("上述企业有哪些是深圳的", False, False, True),
        ("他们有哪些专利", False, False, True),
        ("他有哪些代表性研究成果", True, True, False),
        ("这论文的链接是什么", True, True, False),
        ("上述企业有哪些是深圳的", False, True, False),
        ("他有哪些代表性研究成果", False, True, True),
        ("介绍清华的丁文伯，他的论文有哪些", False, False, False),
        ("华力创这家公司相关信息，他的产量特点是什么", False, False, False),
        ("专利 CN117873146A 的详细信息是什么，它的申请公司", False, False, False),
        (
            "pFedGPA: Diffusion-based Generative Parameter Aggregation for "
            "Personalized Federated Learning 这篇论文的详细信息",
            False,
            False,
            False,
        ),
        ("他的论文有哪些", False, False, True),
        # An elaboration follow-up with no anchor anywhere must clarify,
        # never fall through to free retrieval; with an anchor it must not.
        ("有没有更详细的信息", False, False, True),
        ("有没有更详细的信息", True, True, False),
    ),
)
def test_referent_clarification_matrix(
    query: str,
    has_anchor: bool,
    has_set: bool,
    expected: bool,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    # G3 pronoun x anchor-type guard (513858e): the anchor's domain now
    # matters for personal pronouns. The historical rows mean "a person
    # anchor binds the referent", so the dummy anchor is professor-typed.
    context = SimpleNamespace(
        active_anchor=(
            SimpleNamespace(domain="professor") if has_anchor else None
        ),
        displayed_result_set=object() if has_set else None,
    )
    committed = (
        None
        if not (has_anchor or has_set)
        else SimpleNamespace(context_receipt=context)
    )

    assert (
        service._referent_clarification_needed(query=query, committed=committed)
        is expected
    )


@pytest.mark.parametrize(
    ("anchor_domain", "expected"),
    (
        ("professor", False),
        ("company", True),
        ("paper", True),
        ("patent", True),
    ),
)
def test_referent_clarification_personal_pronoun_anchor_domain_matrix(
    anchor_domain: str,
    expected: bool,
) -> None:
    """G3: a personal pronoun only binds a person anchor; organization /
    paper / patent anchors must clarify instead of free-retrieving."""
    service = import_module("backend.services.canonical_v2_chat")
    committed = SimpleNamespace(
        context_receipt=SimpleNamespace(
            active_anchor=SimpleNamespace(domain=anchor_domain),
            displayed_result_set=object(),
        ),
    )

    assert (
        service._referent_clarification_needed(
            query="他有哪些代表性研究成果", committed=committed
        )
        is expected
    )


def test_unbound_pronoun_turn_clarifies_without_retrieval_or_session_write() -> None:
    service = import_module("backend.services.canonical_v2_chat")

    def forbidden_planner(value: Any) -> Any:
        raise AssertionError("unbound referent must not reach planning")

    def forbidden_read(value: Any) -> Any:
        raise AssertionError("unbound referent must not reach retrieval")

    adapter = service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=forbidden_planner,
        knowledge_read=forbidden_read,
        answer_factory=lambda: None,
        answer_session_fork=lambda value: value,
    )

    response = adapter.answer(
        query="他有哪些代表性研究成果",
        session_id="session:unbound-pronoun",
        option_id=None,
        as_of=NOW,
    )

    assert response.query_type == "canonical_v2:G:clarification_only"
    assert response.clarification is not None
    assert "指代" in response.answer_text
    assert response.citations == []
    assert adapter._sessions == {}


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
    assert "暂未能确认问题中的" in first.answer_text
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
    assert len(blocking.clarification.options) == 2
    assert {option.domain for option in blocking.clarification.options} == {"company"}
    assert {option.label for option in blocking.clarification.options} == {
        "南山",
        "宝安",
    }
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


def test_s11a_post_chat_stream_emits_stage_and_answer_events() -> None:
    """The SSE stream route emits stage/plan_done/retrieval_done then a full
    answer event and a terminal done event."""
    seam = _load_s11a_seam()
    getter = seam.deps_module.get_canonical_v2_chat_adapter

    class _StreamingAdapter:
        def answer_stream(
            self,
            *,
            query: str,
            session_id: str,
            option_id: str | None,
            as_of: datetime,
            progress: Callable[[str, dict[str, Any]], None] | None = None,
            **_: Any,
        ) -> Any:
            if progress is not None:
                progress("stage", {"name": "planning"})
                progress(
                    "plan_done",
                    {
                        "lanes": ["exact"],
                        "domains": ["company"],
                        "views": ["Robotics Co"],
                    },
                )
                progress("stage", {"name": "retrieval"})
                progress(
                    "retrieval_done",
                    {
                        "lanes": [
                            {"lane": "exact", "status": "succeeded", "candidates": 1}
                        ]
                    },
                )
                progress("stage", {"name": "synthesis"})
            return seam.contracts_module.ChatResponse(
                query=query,
                query_type="canonical_v2:A:answer",
                answer_text="示例回答",
                citations=[],
                evidence=[],
                clarification=None,
                structured_payload={},
                answer_style="template",
                citation_map={},
                suggested_followups=[],
            )

    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: _StreamingAdapter()
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    # A fresh stream turn must carry the session cookie on the stream itself
    # (the injected Response's cookies are dropped for StreamingResponse).
    assert "miroflow_chat_session=" in response.headers.get("set-cookie", "")
    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    names = [name for name, _ in events]
    assert names == [
        "stage",
        "plan_done",
        "stage",
        "retrieval_done",
        "stage",
        "answer",
        "done",
    ]
    stages = [data["name"] for name, data in events if name == "stage"]
    assert stages == ["planning", "retrieval", "synthesis"]
    plan_done = next(data for name, data in events if name == "plan_done")
    assert plan_done["lanes"] == ["exact"]
    retrieval_done = next(data for name, data in events if name == "retrieval_done")
    assert retrieval_done["lanes"][0]["candidates"] == 1
    answer_payload = next(data for name, data in events if name == "answer")
    assert answer_payload["query"] == SIMPLE_QUERY
    assert answer_payload["answer_text"] == "示例回答"
    assert set(answer_payload) >= {
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


def test_s11a_chat_stream_emits_answer_chunk_events() -> None:
    """The route publishes safe chunks before the adapter returns."""
    seam = _load_s11a_seam()
    getter = seam.deps_module.get_canonical_v2_chat_adapter

    chunks = ["深圳", "科创", "助手", "开始回答"]
    first_chunk_published_before_return = threading.Event()

    class _ChunkStreamingAdapter:
        def answer_stream(
            self,
            *,
            query: str,
            session_id: str,
            option_id: str | None,
            as_of: datetime,
            progress: Callable[[str, dict[str, Any]], bool | None] | None = None,
            **_: Any,
        ) -> Any:
            if progress is not None:
                progress("stage", {"name": "planning"})
                progress("plan_done", {"lanes": ["exact"], "domains": [], "views": []})
                progress("stage", {"name": "retrieval"})
                progress("retrieval_done", {"lanes": []})
                progress("stage", {"name": "synthesis"})
                for index, text in enumerate(chunks):
                    published = progress("answer_chunk", {"text": text})
                    if index == 0:
                        assert published is True
                        first_chunk_published_before_return.set()
            return seam.contracts_module.ChatResponse(
                query=query,
                query_type="canonical_v2:A:answer",
                answer_text="".join(chunks),
                citations=[],
                evidence=[],
                clarification=None,
                structured_payload={},
                answer_style="template",
                citation_map={},
                suggested_followups=[],
            )

    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: _ChunkStreamingAdapter()
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    assert first_chunk_published_before_return.is_set()
    assert response.status_code == 200
    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    names = [name for name, _ in events]
    assert names[:5] == [
        "stage",
        "plan_done",
        "stage",
        "retrieval_done",
        "stage",
    ]
    assert names[-2:] == ["answer", "done"]
    assert names[5:-2] and set(names[5:-2]) == {"answer_chunk"}
    chunk_events = [data for name, data in events if name == "answer_chunk"]
    assert "".join(chunk["text"] for chunk in chunk_events) == "".join(chunks)
    answer_payload = next(data for name, data in events if name == "answer")
    assert answer_payload["answer_text"] == "".join(chunks)


@pytest.mark.parametrize(
    "marker",
    (
        "PROF-8000C9F994C3",
        "COMP-012345abcdef",
        "company-c-0123456789abcdef01234567",
        "professor-c-0123456789abcdef01234567",
        "paper-c-0123456789abcdef01234567",
        "patent-c-0123456789abcdef01234567",
        "web-object:sha256:" + ("a" * 64),
        "web-handle:sha256:" + ("b" * 64),
        "web-object:s12g-private",
        "source_nature=current_web",
    ),
)
def test_s12g_public_text_sanitizer_removes_only_producer_backed_markers(
    marker: str,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    source = f"公开前文。{marker}；公开后文。"
    expected = "公开前文。；公开后文。"

    assert service._sanitize_public_text(source) == expected

    split = len(marker) // 2
    sanitizer = service._PublicTextStreamSanitizer()
    streamed = (
        sanitizer.feed(f"公开前文。{marker[:split]}")
        + sanitizer.feed(f"{marker[split:]}；公开后文。")
        + sanitizer.flush()
    )
    assert streamed == expected


def test_s12g_public_text_sanitizer_releases_short_safe_text_immediately() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    sanitizer = service._PublicTextStreamSanitizer()

    assert sanitizer.feed("普通短回答。") == "普通短回答。"
    assert sanitizer.flush() == ""


def test_s12g_public_projection_is_idempotent_across_stream_and_final_response() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    raw_markdown = (
        "# 深圳科创\n\n"
        "普通文本保持。web-object:s12g-privateCOMP-012345abcdef；结尾公开。"
    )
    expected = "# 深圳科创\n\n普通文本保持。；结尾公开。"

    assert service._sanitize_public_text("普通文本保持。") == "普通文本保持。"

    batch = service._sanitize_public_text(raw_markdown)
    assert service._sanitize_public_text(batch) == batch

    response = service.ChatResponse(
        query=SIMPLE_QUERY,
        query_type="canonical_v2:A:answer",
        answer_text=raw_markdown,
        citations=[],
        evidence=[],
        clarification=None,
        structured_payload={},
        answer_style="template",
        citation_map={},
        suggested_followups=[],
    )
    final_answer = service._sanitize_public_response(response).answer_text

    sanitizer = service._PublicTextStreamSanitizer()
    streamed = (
        sanitizer.feed(
            "# 深圳科创\n\n普通文本保持。web-object:s12g-private"
        )
        + sanitizer.feed("COMP-012345abcdef；结尾公开。")
        + sanitizer.flush()
    )

    assert batch == streamed == final_answer == expected


@pytest.mark.parametrize(
    "failed_attempt",
    (
        "web-obje",
        "source_nature=current_",
    ),
)
def test_s12g_public_text_sanitizer_abort_discards_attempt_state(
    failed_attempt: str,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    sanitizer = service._PublicTextStreamSanitizer()

    assert sanitizer.feed(failed_attempt) == ""
    assert hasattr(sanitizer, "abort")
    sanitizer.abort()

    assert sanitizer.feed("新的公开回答") == "新的公开回答"
    assert sanitizer.flush() == ""


def test_s12g_public_text_sanitizer_abort_resets_left_boundary_state() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    sanitizer = service._PublicTextStreamSanitizer()

    assert sanitizer.feed("web-object:s12g-private") == ""
    sanitizer.abort()

    streamed = sanitizer.feed("COMP-012345abcdef；") + sanitizer.flush()
    assert streamed == "；"


@pytest.mark.parametrize(
    "public_text",
    (
        "source:github",
        "paper:arxiv",
        "query:python",
        "paper-based",
        "https://example.test/company:overview?ref=public",
        "a" * 64,
        "PROF-DING-WENBO",
        "evidence:sha256:" + ("b" * 64),
        "current_web",
        "Source_nature=current_web",
        "source_nature = current_web",
    ),
)
def test_s12g_public_text_sanitizer_preserves_normal_text_verbatim(
    public_text: str,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")

    assert service._sanitize_public_text(public_text) == public_text

    sanitizer = service._PublicTextStreamSanitizer()
    split = max(1, len(public_text) // 2)
    streamed = (
        sanitizer.feed(public_text[:split])
        + sanitizer.feed(public_text[split:])
        + sanitizer.flush()
    )
    assert streamed == public_text


@pytest.mark.parametrize(
    ("candidate", "is_internal"),
    (
        ("COMP-012345abcdef", True),
        ("COMP-3B95F48EB687", True),
        ("COMP-012345aBcDeF", True),
        ("COMP-012345abcde", False),
        ("COMP-012345abcdef0", False),
        ("COMP-012345abcdeg", False),
    ),
)
def test_s12g_comp_marker_requires_exact_twelve_hex_digits(
    candidate: str,
    is_internal: bool,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    source = f"公开前文。{candidate}；公开后文。"
    expected = "公开前文。；公开后文。" if is_internal else source

    assert service._sanitize_public_text(source) == expected

    sanitizer = service._PublicTextStreamSanitizer()
    single_feed = sanitizer.feed(source) + sanitizer.flush()
    assert single_feed == expected

    for split in range(1, len(source)):
        sanitizer = service._PublicTextStreamSanitizer()
        streamed = (
            sanitizer.feed(source[:split])
            + sanitizer.feed(source[split:])
            + sanitizer.flush()
        )
        assert streamed == expected, split


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "Xcompany-c-0123456789abcdef01234567。。。",
            "Xcompany-c-0123456789abcdef01234567。。。",
        ),
        (
            "web-object:s12g-privateCOMP-012345abcdef；",
            "；",
        ),
    ),
)
def test_s12g_public_text_stream_preserves_original_left_boundary_for_every_split(
    source: str,
    expected: str,
) -> None:
    service = import_module("backend.services.canonical_v2_chat")
    batch = service._sanitize_public_text(source)
    assert batch == expected

    sanitizer = service._PublicTextStreamSanitizer()
    single_feed = sanitizer.feed(source) + sanitizer.flush()
    assert single_feed == batch

    for split in range(1, len(source)):
        sanitizer = service._PublicTextStreamSanitizer()
        streamed = (
            sanitizer.feed(source[:split])
            + sanitizer.feed(source[split:])
            + sanitizer.flush()
        )
        assert streamed == batch, split


def test_s12g_public_text_stream_matches_batch_for_every_web_namespace_split() -> None:
    service = import_module("backend.services.canonical_v2_chat")
    marker = "web-object:s12g-private"
    source = f"公开前文。{marker}；公开后文。"
    expected = "公开前文。；公开后文。"
    assert service._sanitize_public_text(source) == expected

    for split in range(1, len(marker)):
        sanitizer = service._PublicTextStreamSanitizer()
        streamed = (
            sanitizer.feed(f"公开前文。{marker[:split]}")
            + sanitizer.feed(f"{marker[split:]}；公开后文。")
            + sanitizer.flush()
        )
        assert streamed == expected, split


def test_s12g_chat_stream_sanitizes_split_internal_markers_without_losing_public_text() -> (
    None
):
    seam = _load_s11a_seam()
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    safe_markdown = (
        "# 深圳科创\n\n"
        "这是 **公开回答**，详情见 [官网](https://example.com/product?q=robot)。\n\n"
        "- 第一项\n- 第二项\n\n"
    )
    long_text = "长正文：" + ("深圳科创持续创新。" * 64)
    internal_markers = (
        "PROF-8000C9F994C3",
        "web-object:s12g-private",
        "source_nature=current_web",
    )
    chunks = (
        "PROF-8000",
        "C9F994C3",
        safe_markdown,
        "中段前文 web-object:s12g-",
        "private 后文继续公开。\n\n",
        long_text,
        "\n\n结尾公开说明：source_",
        "nature=current_web",
    )
    expected_public_text = "".join(chunks)
    for marker in internal_markers:
        expected_public_text = expected_public_text.replace(marker, "")

    class _UnsafeChunkStreamingAdapter:
        def answer_stream(
            self,
            *,
            query: str,
            progress: Callable[[str, dict[str, Any]], None] | None = None,
            **_: Any,
        ) -> Any:
            if progress is not None:
                progress("stage", {"name": "planning"})
                progress("plan_done", {"lanes": ["exact"], "domains": [], "views": []})
                progress("stage", {"name": "retrieval"})
                progress("retrieval_done", {"lanes": []})
                progress("stage", {"name": "synthesis"})
                for text in chunks:
                    progress("answer_chunk", {"text": text})
            return seam.contracts_module.ChatResponse(
                query=query,
                query_type="canonical_v2:A:answer",
                answer_text=expected_public_text,
                citations=[],
                evidence=[],
                clarification=None,
                structured_payload={},
                answer_style="template",
                citation_map={},
                suggested_followups=[],
            )

    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: _UnsafeChunkStreamingAdapter()
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    assert response.status_code == 200
    for unsafe_fragment in internal_markers:
        assert unsafe_fragment not in response.text

    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))

    assert [name for name, _ in events if name != "answer_chunk"] == [
        "stage",
        "plan_done",
        "stage",
        "retrieval_done",
        "stage",
        "answer",
        "done",
    ]
    chunk_payloads = [data for name, data in events if name == "answer_chunk"]
    assert all(
        set(payload) == {"text"} and payload["text"] for payload in chunk_payloads
    )
    streamed_public_text = "".join(payload["text"] for payload in chunk_payloads)
    answer_payload = next(data for name, data in events if name == "answer")
    assert set(answer_payload) == set(seam.contracts_module.ChatResponse.model_fields)
    assert streamed_public_text == answer_payload["answer_text"] == expected_public_text
    assert safe_markdown in streamed_public_text
    assert "https://example.com/product?q=robot" in streamed_public_text
    assert long_text in streamed_public_text


def test_s12g_real_adapter_sse_sanitizes_answer_and_clarification() -> None:
    seam = _load_s11a_seam()
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    marker = "PROF-8000C9F994C3"
    unsafe_answer = f"公开说明保留 source:github。{marker}"
    expected_answer = "公开说明保留 source:github。"

    class _Planner:
        def plan(self, request: Any) -> Any:
            return read_module.RetrievalPlan(
                plan_version="retrieval-plan-v1",
                original_query=request.original_query,
                behavior_class="A",
                release_id=RELEASE_ID,
                domains=(),
                protected_slots=(),
                lanes=(),
                max_candidates=0,
                web_required=False,
            )

    class _Read:
        def execute(self, plan: Any) -> Any:
            return read_module.EvidenceSet(
                release_id=RELEASE_ID,
                original_query=plan.original_query,
                protected_slots=(),
                items=(),
                traces=(),
                limitations=(),
            )

    class _Answer:
        prose_progress: Callable[[str], None] | None = None

        def answer(self, turn: Any) -> Any:
            return answer_module.TurnResult(
                session_id=turn.session_id,
                turn_id=turn.turn_id,
                release_id=turn.release_id,
                answer_text=unsafe_answer,
                response_mode="clarification_only",
            )

    adapter = seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_Planner(),
        knowledge_read=_Read(),
        answer_factory=_Answer,
        answer_session_fork=lambda _: _Answer(),
    )
    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: adapter
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    events = [
        (
            block.split("\n", 1)[0].removeprefix("event: "),
            json.loads(block.split("data: ", 1)[1]),
        )
        for block in response.text.strip().split("\n\n")
    ]
    answer_payload = next(data for name, data in events if name == "answer")
    assert answer_payload["answer_text"] == expected_answer
    assert answer_payload["clarification"]["prompt"] == expected_answer
    assert marker not in json.dumps(answer_payload, ensure_ascii=False)


def _web_items_evidence_item(
    read_module: Any,
    *,
    index: int,
    locator: str,
    snippet: str,
    lane: str = "web",
) -> Any:
    return read_module.EvidenceItem(
        evidence_id=f"evidence:web-items:{index}",
        object_id=f"web-object:web-items:{index}",
        domain="company",
        lane=lane,
        source_nature="current_web" if lane == "web" else "local",
        source_locator=locator,
        snippet=snippet,
        score=1.0,
        source_authority="web_search",
    )


class _WebItemsPlanner:
    def plan(self, request: Any) -> Any:
        read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
        return read_module.RetrievalPlan(
            plan_version="retrieval-plan-v1",
            original_query=request.original_query,
            behavior_class="A",
            release_id=RELEASE_ID,
            domains=("company",),
            protected_slots=(),
            lanes=("web",),
            max_candidates=5,
            web_required=False,
        )


class _WebItemsRead:
    def __init__(self, items: tuple[Any, ...]) -> None:
        self._items = items

    def execute(self, plan: Any) -> Any:
        read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
        return read_module.EvidenceSet(
            release_id=RELEASE_ID,
            original_query=plan.original_query,
            protected_slots=(),
            items=self._items,
            traces=(),
            limitations=(),
        )


class _WebItemsAnswer:
    prose_progress: Callable[[str], None] | None = None

    def answer(self, turn: Any) -> Any:
        answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
        return answer_module.TurnResult(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            release_id=turn.release_id,
            answer_text=f"公开回答：{turn.query}",
        )


def _web_items_adapter(items: tuple[Any, ...]) -> Any:
    service = import_module("backend.services.canonical_v2_chat")
    return service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_WebItemsPlanner(),
        knowledge_read=_WebItemsRead(items),
        answer_factory=_WebItemsAnswer,
        answer_session_fork=lambda _: _WebItemsAnswer(),
    )


def _streamed_progress_events(
    adapter: Any,
    session_id: str,
) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    adapter.answer_stream(
        query=SIMPLE_QUERY,
        session_id=session_id,
        option_id=None,
        as_of=NOW,
        progress=lambda name, data: events.append((name, data)),
    )
    return events


def test_real_adapter_retrieval_done_lists_public_web_items() -> None:
    """``retrieval_done`` carries up to 10 sanitized web lane results: the
    title is split from the packed ``title：snippet`` form, the URL passes the
    public-URL sanitizer, and the source host rides along. Non-web items,
    non-public locators, and duplicate URLs never reach the event."""
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    items = [
        _web_items_evidence_item(
            read_module,
            index=0,
            locator="https://www.example.com/news/a",
            snippet="甲公司发布新机器人：完整新闻摘要",
        ),
        _web_items_evidence_item(
            read_module,
            index=1,
            locator="https://news.example.org/b",
            snippet="只有标题没有摘要",
        ),
        # Non-public locators are dropped by the public-URL sanitizer.
        _web_items_evidence_item(
            read_module,
            index=2,
            locator="https://intranet.local/secret",
            snippet="内部页面：不应出现",
        ),
        # Trailing-slash duplicate of the first item's normalized URL: dropped.
        _web_items_evidence_item(
            read_module,
            index=3,
            locator="https://www.example.com/news/a/",
            snippet="重复条目：不应出现",
        ),
        # Non-web lanes never leak into the web list.
        _web_items_evidence_item(
            read_module,
            index=4,
            lane="exact",
            locator="local://company-c-0123456789abcdef01234567",
            snippet='{"name": "本地条目"}',
        ),
        *[
            _web_items_evidence_item(
                read_module,
                index=10 + extra,
                locator=f"https://extra.example.net/{extra}",
                snippet=f"补充标题 {extra}",
            )
            for extra in range(10)
        ],
    ]
    adapter = _web_items_adapter(tuple(items))

    events = _streamed_progress_events(adapter, "session:retrieval-done-web-items")

    retrieval_done = next(data for name, data in events if name == "retrieval_done")
    # The lane contract stays intact and web_items is a pure addition.
    assert "lanes" in retrieval_done
    # 2 kept head items + 8 extras: internal, duplicate, and non-web items
    # were filtered before the 10-item cap applies.
    assert retrieval_done["web_items"] == [
        {
            "title": "甲公司发布新机器人",
            "url": "https://www.example.com/news/a",
            "source": "www.example.com",
        },
        {
            "title": "只有标题没有摘要",
            "url": "https://news.example.org/b",
            "source": "news.example.org",
        },
        *[
            {
                "title": f"补充标题 {extra}",
                "url": f"https://extra.example.net/{extra}",
                "source": "extra.example.net",
            }
            for extra in range(8)
        ],
    ]


def test_real_adapter_retrieval_done_web_items_empty_without_web_results() -> None:
    """Without web lane items the field is present and empty — a backwards-
    compatible addition older clients can simply ignore."""
    adapter = _web_items_adapter(())

    events = _streamed_progress_events(adapter, "session:retrieval-done-no-web")

    retrieval_done = next(data for name, data in events if name == "retrieval_done")
    assert retrieval_done["web_items"] == []


def test_s11a_chat_stream_integrity_error_emits_error_event() -> None:
    """A knowledge-read integrity failure surfaces as an SSE error event with
    the stable public detail (never the private message)."""
    seam = _load_s11a_seam()
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read_isolated")

    class _FailingStreamAdapter:
        def answer_stream(self, **_: Any) -> Any:
            raise read_module.IsolatedKnowledgeReadIntegrityError(
                "private release-bound lookup detail"
            )

    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: _FailingStreamAdapter()
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: error" in response.text
    assert RELEASE_MISMATCH in response.text
    assert "private release-bound lookup detail" not in response.text


class _S12GStageProbe:
    def __init__(self, *, blocked_stage: str | None, blocked_query: str) -> None:
        self.blocked_stage = blocked_stage
        self.blocked_query = blocked_query
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = {"plan": 0, "read": 0, "answer": 0}

    def visit(self, stage: str, query: str) -> None:
        self.calls[stage] += 1
        if stage != self.blocked_stage or query != self.blocked_query:
            return
        self.entered.set()
        if not self.release.wait(2.0):
            raise TimeoutError(f"timed out waiting to release {stage}")


class _S12GHistoryAnswer:
    prose_progress: Callable[[str], None] | None = None

    def __init__(
        self,
        *,
        probe: _S12GStageProbe,
        answer_module: Any,
        history: tuple[str, ...] = (),
    ) -> None:
        self.probe = probe
        self.answer_module = answer_module
        self.history = list(history)

    def answer(self, turn: Any) -> Any:
        self.probe.visit("answer", turn.query)
        if self.prose_progress is not None:
            self.prose_progress(f"公开分片：{turn.query}")
        self.history.append(turn.query)
        return self.answer_module.TurnResult(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            release_id=turn.release_id,
            answer_text="｜".join(self.history),
        )


def _s12g_real_adapter(seam: _S11ASeam, probe: _S12GStageProbe) -> Any:
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")

    class _Planner:
        def plan(self, request: Any) -> Any:
            probe.visit("plan", request.original_query)
            return read_module.RetrievalPlan(
                plan_version="retrieval-plan-v1",
                original_query=request.original_query,
                behavior_class="A",
                release_id=RELEASE_ID,
                domains=(),
                protected_slots=(),
                lanes=(),
                max_candidates=0,
                web_required=False,
            )

    class _Read:
        def execute(self, plan: Any) -> Any:
            probe.visit("read", plan.original_query)
            return read_module.EvidenceSet(
                release_id=RELEASE_ID,
                original_query=plan.original_query,
                protected_slots=(),
                items=(),
                traces=(),
                limitations=(),
            )

    return seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_Planner(),
        knowledge_read=_Read(),
        answer_factory=lambda: _S12GHistoryAnswer(
            probe=probe,
            answer_module=answer_module,
        ),
        answer_session_fork=lambda base: _S12GHistoryAnswer(
            probe=probe,
            answer_module=answer_module,
            history=tuple(base.history),
        ),
    )


@pytest.mark.parametrize(
    ("cancel_first", "expected_third_answer"),
    (
        (True, "第一轮公开问题｜第三轮公开问题"),
        (False, "第一轮公开问题｜第二轮公开问题｜第三轮公开问题"),
    ),
)
def test_s12g_turn_gate_linearizes_cancellation_and_session_commit(
    cancel_first: bool,
    expected_third_answer: str,
) -> None:
    seam = _load_s11a_seam()
    second_query = "第二轮公开问题"
    probe = _S12GStageProbe(blocked_stage="answer", blocked_query=second_query)
    adapter = _s12g_real_adapter(seam, probe)
    turn_gate = seam.service_module._TurnCommitGate()
    session_id = f"session:s12g-linearized-{cancel_first}"
    outcome: dict[str, Any] = {}
    completed = threading.Event()

    first = adapter.answer(
        query="第一轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.answer_text == "第一轮公开问题"

    def run_second_turn() -> None:
        try:
            outcome["response"] = adapter.answer_stream(
                query=second_query,
                session_id=session_id,
                option_id=None,
                as_of=NOW,
                turn_gate=turn_gate,
            )
        except BaseException as exc:  # noqa: BLE001 - asserted through public outcome
            outcome["error"] = exc
        finally:
            completed.set()

    worker = threading.Thread(target=run_second_turn, daemon=True)
    worker.start()
    assert probe.entered.wait(1.5)
    if cancel_first:
        turn_gate.cancel()
        probe.release.set()
    else:
        probe.release.set()
        assert completed.wait(1.5)
        turn_gate.cancel()
    assert completed.wait(1.5)
    worker.join(0.1)
    assert not worker.is_alive()
    if cancel_first:
        assert "response" not in outcome
    else:
        assert outcome["response"].answer_text == "第一轮公开问题｜第二轮公开问题"

    third = adapter.answer(
        query="第三轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert third.answer_text == expected_third_answer


@pytest.mark.parametrize(
    ("blocked_stage", "expected_calls", "forbidden_event"),
    (
        ("plan", {"plan": 1, "read": 0, "answer": 0}, "plan_done"),
        ("read", {"plan": 1, "read": 1, "answer": 0}, "retrieval_done"),
        ("answer", {"plan": 1, "read": 1, "answer": 1}, "answer_chunk"),
    ),
)
def test_s12g_cancelled_turn_exits_at_the_next_stage_boundary(
    blocked_stage: str,
    expected_calls: dict[str, int],
    forbidden_event: str,
) -> None:
    seam = _load_s11a_seam()
    cancelled_query = "需取消的公开问题"
    probe = _S12GStageProbe(
        blocked_stage=blocked_stage,
        blocked_query=cancelled_query,
    )
    adapter = _s12g_real_adapter(seam, probe)
    turn_gate = seam.service_module._TurnCommitGate()
    progress_names: list[str] = []
    outcome: dict[str, Any] = {}

    def run_cancelled_turn() -> None:
        try:
            outcome["response"] = adapter.answer_stream(
                query=cancelled_query,
                session_id=f"session:s12g-stage-{blocked_stage}",
                option_id=None,
                as_of=NOW,
                progress=lambda name, _: progress_names.append(name),
                turn_gate=turn_gate,
            )
        except BaseException as exc:  # noqa: BLE001 - asserted through public outcome
            outcome["error"] = exc

    worker = threading.Thread(target=run_cancelled_turn, daemon=True)
    worker.start()
    assert probe.entered.wait(1.5)
    turn_gate.cancel()
    probe.release.set()
    worker.join(1.5)

    assert not worker.is_alive()
    assert "response" not in outcome
    assert probe.calls == expected_calls
    assert forbidden_event not in progress_names
    recovered = adapter.answer(
        query="恢复后的公开问题",
        session_id=f"session:s12g-stage-{blocked_stage}",
        option_id=None,
        as_of=NOW,
    )
    assert recovered.answer_text == "恢复后的公开问题"


class _S12GFinishingProxy:
    def __init__(self, adapter: Any, worker_finished: threading.Event) -> None:
        self.adapter = adapter
        self.worker_finished = worker_finished

    def answer_stream(self, **kwargs: Any) -> Any:
        try:
            return self.adapter.answer_stream(**kwargs)
        finally:
            self.worker_finished.set()


def test_s12g_chat_stream_aclose_cancels_before_real_adapter_commit() -> None:
    seam = _load_s11a_seam()
    query = "停止当前流"
    probe = _S12GStageProbe(blocked_stage="plan", blocked_query=query)
    worker_finished = threading.Event()
    adapter = _S12GFinishingProxy(
        _s12g_real_adapter(seam, probe),
        worker_finished,
    )

    class _Request:
        app = SimpleNamespace(state=SimpleNamespace())

        async def is_disconnected(self) -> bool:
            return False

    async def stop_after_first_event() -> str:
        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(query=query, entity_id_hint=None),
            Response(),
            _Request(),
            miroflow_chat_session="session:s12g-stop",
            adapter=adapter,
        )
        iterator = cast(Any, stream.body_iterator)
        first_event = await iterator.__anext__()
        assert await asyncio.to_thread(probe.entered.wait, 1.5)
        await iterator.aclose()
        return str(first_event)

    first_event = asyncio.run(stop_after_first_event())
    probe.release.set()
    assert worker_finished.wait(1.5)
    assert probe.calls == {"plan": 1, "read": 0, "answer": 0}
    assert "event: stage" in first_event
    assert all(
        f"event: {name}" not in first_event for name in ("answer", "done", "error")
    )


def test_s12g_chat_stream_disconnect_cancels_before_real_adapter_commit() -> None:
    seam = _load_s11a_seam()
    query = "断开当前流"
    probe = _S12GStageProbe(blocked_stage="plan", blocked_query=query)
    worker_finished = threading.Event()
    disconnect_observed = threading.Event()
    adapter = _S12GFinishingProxy(
        _s12g_real_adapter(seam, probe),
        worker_finished,
    )

    class _DisconnectedRequest:
        app = SimpleNamespace(state=SimpleNamespace())

        async def is_disconnected(self) -> bool:
            if not await asyncio.to_thread(probe.entered.wait, 1.5):
                raise TimeoutError("planner did not reach the disconnect boundary")
            disconnect_observed.set()
            return True

    async def consume_until_disconnect() -> list[Any]:
        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(query=query, entity_id_hint=None),
            Response(),
            _DisconnectedRequest(),
            miroflow_chat_session="session:s12g-disconnect",
            adapter=adapter,
        )
        return [chunk async for chunk in stream.body_iterator]

    chunks = asyncio.run(consume_until_disconnect())
    assert disconnect_observed.is_set()
    probe.release.set()
    assert worker_finished.wait(1.5)
    assert probe.calls == {"plan": 1, "read": 0, "answer": 0}
    assert all(
        f"event: {name}" not in str(chunk)
        for chunk in chunks
        for name in ("answer", "done", "error")
    )


@pytest.mark.parametrize("outcome", ("normal", "error", "disconnect"))
def test_s12g_chat_stream_terminal_race_is_fifo_ordered(
    outcome: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seam = _load_s11a_seam()
    real_queue = import_module("queue")
    adapter_entered = threading.Event()
    release_adapter = threading.Event()
    worker_exited = threading.Event()

    class _TerminalAdapter:
        def answer_stream(self, **kwargs: Any) -> Any:
            adapter_entered.set()
            if not release_adapter.wait(1.5):
                raise TimeoutError("test did not release terminal adapter")
            if outcome == "error":
                raise RuntimeError("test-owned terminal failure")
            return seam.contracts_module.ChatResponse(
                query=kwargs["query"],
                query_type="canonical_v2:A:answer",
                answer_text="终态回答",
                citations=[],
                evidence=[],
                clarification=None,
                structured_payload={},
                answer_style="template",
                citation_map={},
                suggested_followups=[],
            )

    class _ControlledQueue(real_queue.Queue):
        def __init__(self) -> None:
            super().__init__()
            self.first_poll = True

        def get_nowait(self) -> Any:
            if self.first_poll:
                self.first_poll = False
                assert adapter_entered.wait(1.5)
                release_adapter.set()
                assert worker_exited.wait(1.5)
                raise real_queue.Empty
            return super().get_nowait()

    class _ObservedThread(threading.Thread):
        def __init__(self, *, target: Callable[[], None], daemon: bool) -> None:
            def observed_target() -> None:
                try:
                    target()
                finally:
                    worker_exited.set()

            super().__init__(target=observed_target, daemon=daemon)

    monkeypatch.setattr(
        seam.route_module,
        "queue",
        SimpleNamespace(Queue=_ControlledQueue, Empty=real_queue.Empty),
    )
    monkeypatch.setattr(
        seam.route_module,
        "threading",
        SimpleNamespace(Thread=_ObservedThread, Event=threading.Event),
    )

    class _Request:
        app = SimpleNamespace(state=SimpleNamespace())

        def __init__(self) -> None:
            self.disconnect_polls = 0

        async def is_disconnected(self) -> bool:
            self.disconnect_polls += 1
            return outcome == "disconnect" and self.disconnect_polls >= 2

    controlled_request = _Request()

    async def consume() -> str:
        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(query=SIMPLE_QUERY, entity_id_hint=None),
            Response(),
            controlled_request,
            miroflow_chat_session=f"session:s12g-terminal-race:{outcome}",
            adapter=_TerminalAdapter(),
        )
        parts = [chunk async for chunk in stream.body_iterator]
        return "".join(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
            for chunk in parts
        )

    body = asyncio.run(consume())
    names = re.findall(r"^event: ([^\n]+)$", body, flags=re.MULTILINE)

    assert worker_exited.is_set()
    if outcome == "normal":
        assert names == ["answer", "done"]
    elif outcome == "error":
        assert names == ["error"]
    else:
        assert controlled_request.disconnect_polls == 2
        assert names == []


def test_s12g_real_http_stream_blocks_split_dynamic_structured_value() -> None:
    seam = _load_s11a_seam()
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    marker = "evidence:s12g:http-dynamic:" + ("x" * 64)
    claim_id = "claim:s12g:http-dynamic:" + ("y" * 64)
    continuation_id = "continuation:s12g:http-dynamic:" + ("z" * 64)
    company_id = "company:s12g:http-dynamic"
    safe_prefix = "这是可公开的安全前缀。" * 12
    safe_suffix = "这段后缀不得越过动态值安全边界。" * 8
    split = len(marker) // 2
    evidence = read_module.EvidenceItem(
        evidence_id=marker,
        object_id=company_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_authority="canonical_release",
        source_locator="canonical-v2-isolated:s12g-http-dynamic",
        snippet="The accepted Company name is Robotics Co.",
        score=1.0,
        observed_at=NOW,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id=company_id,
            predicate="preferred_name",
            value="Robotics Co",
            status="accepted",
        ),
    )
    candidate = read_module.ContinuationCandidate(
        candidate_id=continuation_id,
        reason="evidence_gap",
        label="Search for targeted evidence",
        operation="targeted_evidence_search",
        target_kind="current_handle",
        target_handle_ids=(company_id,),
        constraint_pairs=(),
        relation_type=None,
        coverage_state=None,
        evidence_ids=(marker,),
        available=True,
    )
    evidence_set = read_module.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=SIMPLE_QUERY,
        protected_slots=(),
        items=(evidence,),
        traces=(),
        limitations=(),
        continuation_candidates=(candidate,),
    )

    class _Planner:
        def plan(self, request: Any) -> Any:
            return read_module.RetrievalPlan(
                plan_version="retrieval-plan-v1",
                original_query=request.original_query,
                behavior_class="A",
                release_id=RELEASE_ID,
                domains=("company",),
                protected_slots=(),
                lanes=("exact",),
                max_candidates=1,
                web_required=False,
            )

    class _Read:
        def execute(self, plan: Any) -> Any:
            assert plan.original_query == SIMPLE_QUERY
            return evidence_set

    def answer_selector(turn: Any) -> Any:
        claim = answer_module.MaterialClaimProposal(
            claim_id=claim_id,
            text="Robotics Co 由已接受的本地公司档案证据支持。",
            subject_id=company_id,
            predicate="preferred_name",
            value="Robotics Co",
            subject_handle_ids=(company_id,),
            evidence_ids=(marker,),
            outcome="supported",
            confirmed=True,
            status="accepted",
        )
        return answer_module.AnswerSelectionProposal(
            selection_input_sha256=turn.content_sha256,
            schema_version="answer-selection-v1",
            decision_id=f"answer-selection:{turn.turn_id}:http-dynamic",
            model_id="recorded-answer-selector",
            prompt_version="answer-selector-prompt-v1",
            decision_run_id=f"answer-selector-run:{turn.turn_id}:http-dynamic",
            answer_text="NON_AUTHORITATIVE_RAW_DRAFT",
            claims=(claim,),
        )

    class _UnsafeRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            chunks = (
                safe_prefix + marker[:split],
                marker[split:] + safe_suffix,
            )
            for chunk in chunks:
                on_chunk(chunk)
            return "".join(chunks)

    renderer = _UnsafeRenderer()

    def answer_factory() -> Any:
        return answer_module.create_ephemeral_knowledge_answer(
            answer_selector=answer_selector,
            prose_renderer=renderer,
        )

    adapter = seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_Planner(),
        knowledge_read=_Read(),
        answer_factory=answer_factory,
        answer_session_fork=lambda _: answer_factory(),
    )
    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: adapter
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        lines = block.split("\n")
        name = next(
            (
                line.removeprefix("event: ")
                for line in lines
                if line.startswith("event: ")
            ),
            "message",
        )
        data = "\n".join(
            line.removeprefix("data: ") for line in lines if line.startswith("data: ")
        )
        if data:
            events.append((name, json.loads(data)))

    names = [name for name, _ in events]
    streamed_text = "".join(
        data["text"] for name, data in events if name == "answer_chunk"
    )
    assert response.status_code == 200
    assert marker not in response.text
    assert streamed_text and safe_prefix.startswith(streamed_text)
    assert names[-1:] == ["error"]
    assert "answer" not in names
    assert "done" not in names
    assert renderer.calls == 1


def test_s12g_real_http_pre_output_retry_discards_pending_marker_tail() -> None:
    seam = _load_s11a_seam()
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    failed_text = "web-obje"
    successful_text = "第二次成功短尾"

    class _Planner:
        def plan(self, request: Any) -> Any:
            return read_module.RetrievalPlan(
                plan_version="retrieval-plan-v1",
                original_query=request.original_query,
                behavior_class="A",
                release_id=RELEASE_ID,
                domains=(),
                protected_slots=(),
                lanes=(),
                max_candidates=0,
                web_required=False,
            )

    class _Read:
        def execute(self, plan: Any) -> Any:
            return read_module.EvidenceSet(
                release_id=RELEASE_ID,
                original_query=plan.original_query,
                protected_slots=(),
                items=(),
                traces=(),
                limitations=(),
            )

    class _RetryingRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            text = failed_text if self.calls == 1 else successful_text
            on_chunk(text)
            if self.calls == 1:
                raise TimeoutError("first attempt failed before public output")
            return text

    renderer = _RetryingRenderer()

    def answer_factory() -> Any:
        return answer_module.create_ephemeral_knowledge_answer(
            prose_renderer=renderer,
        )

    adapter = seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_Planner(),
        knowledge_read=_Read(),
        answer_factory=answer_factory,
        answer_session_fork=lambda _: answer_factory(),
    )
    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: adapter
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        lines = block.split("\n")
        name = next(
            (
                line.removeprefix("event: ")
                for line in lines
                if line.startswith("event: ")
            ),
            "message",
        )
        data = "\n".join(
            line.removeprefix("data: ") for line in lines if line.startswith("data: ")
        )
        if data:
            events.append((name, json.loads(data)))

    names = [name for name, _ in events]
    streamed_text = "".join(
        data["text"] for name, data in events if name == "answer_chunk"
    )
    assert response.status_code == 200
    assert renderer.calls == 2
    answer_payload = next(data for name, data in events if name == "answer")
    assert failed_text not in response.text
    assert streamed_text == successful_text
    assert answer_payload["answer_text"] == successful_text
    assert names[-2:] == ["answer", "done"]
    assert "error" not in names


def test_s12g_real_http_stream_correction_supersedes_drifted_draft() -> None:
    """Off-anchor drift on the SSE stream path, corrected in the FINAL answer.

    The renderer streams a draft that never names the anchor, then one bounded
    non-stream retry produces an on-anchor correction marked
    ``supersedes_streamed_draft``. The knowledge_answer stream guard exempts
    that one legitimate mismatch: the SSE answer event carries the CORRECTED
    text (chat.html re-renders over the drifted draft), a done event follows,
    no error event fires, and the session commits instead of rolling back.
    Completions scripting reuses the Task-4 ``_StreamThenSyncProseCompletions``
    pattern from the renderer tests.
    """
    seam = _load_s11a_seam()
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    serving_module = import_module(
        "src.data_agents.canonical_v2.knowledge_serving_isolated"
    )
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    session_id = "session:s12g:http-stream-correction"
    company_id = "company:s12g:http-stream-correction"
    evidence_id = "evidence:s12g:http-stream-correction"
    drifted_answer = "这份漂移草稿把同名主体的公开背景张冠李戴，全篇未正面作答。"
    corrected_answer = "Robotics Co 由已接受的本地公司档案证据支持，聚焦机器人业务。"

    def wire(answer: str) -> str:
        return (
            "<|canonical_v2_selection_v1|>\n"
            '{"selected_claim_indexes":[1],"selected_entity_indexes":[1]}\n'
            "<|canonical_v2_answer_v1|>\n" + answer
        )

    class _Completions:
        def __init__(self) -> None:
            self.stream_create_calls = 0
            self.sync_create_calls = 0

        def create(self, **kwargs: object) -> object:
            if kwargs.get("stream"):
                self.stream_create_calls += 1
                content = wire(drifted_answer)

                def completion() -> object:
                    for index in range(0, len(content), 7):
                        yield SimpleNamespace(
                            choices=(
                                SimpleNamespace(
                                    delta=SimpleNamespace(
                                        content=content[index : index + 7]
                                    ),
                                    finish_reason=None,
                                ),
                            )
                        )
                    yield SimpleNamespace(
                        choices=(
                            SimpleNamespace(
                                delta=SimpleNamespace(content=None),
                                finish_reason="stop",
                            ),
                        )
                    )

                return completion()
            self.sync_create_calls += 1
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        message=SimpleNamespace(content=wire(corrected_answer)),
                        finish_reason="stop",
                    ),
                )
            )

    completions = _Completions()
    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )
    evidence = read_module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=company_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_authority="canonical_release",
        source_locator="canonical-v2-isolated:s12g-http-stream-correction",
        snippet="The accepted Company name is Robotics Co.",
        score=1.0,
        observed_at=NOW,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id=company_id,
            predicate="preferred_name",
            value="Robotics Co",
            status="accepted",
        ),
    )
    handle = read_module.CanonicalEntityHandle(
        canonical_id=company_id,
        domain="company",
        display_name="Robotics Co",
        evidence_ids=(evidence_id,),
    )
    evidence_set = read_module.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=SIMPLE_QUERY,
        protected_slots=(),
        items=(evidence,),
        traces=(),
        limitations=(),
        entity_handles=(handle,),
    )

    class _Planner:
        def plan(self, request: Any) -> Any:
            return read_module.RetrievalPlan(
                plan_version="retrieval-plan-v1",
                original_query=request.original_query,
                behavior_class="A",
                release_id=RELEASE_ID,
                domains=("company",),
                protected_slots=(),
                lanes=("exact",),
                max_candidates=1,
                web_required=False,
            )

    class _Read:
        def execute(self, plan: Any) -> Any:
            assert plan.original_query == SIMPLE_QUERY
            return evidence_set

    def answer_selector(turn: Any) -> Any:
        claim = answer_module.MaterialClaimProposal(
            claim_id="claim:s12g:http-stream-correction",
            text="Robotics Co 由已接受的本地公司档案证据支持。",
            subject_id=company_id,
            predicate="preferred_name",
            value="Robotics Co",
            subject_handle_ids=(company_id,),
            evidence_ids=(evidence_id,),
            outcome="supported",
            confirmed=True,
            status="accepted",
        )
        return answer_module.AnswerSelectionProposal(
            selection_input_sha256=turn.content_sha256,
            schema_version="answer-selection-v1",
            decision_id=f"answer-selection:{turn.turn_id}:http-stream-correction",
            model_id="recorded-answer-selector",
            prompt_version="answer-selector-prompt-v1",
            decision_run_id=f"answer-selector-run:{turn.turn_id}:http-correction",
            answer_text="NON_AUTHORITATIVE_RAW_DRAFT",
            claims=(claim,),
            displayed_handle_ids=(company_id,),
        )

    def answer_factory() -> Any:
        return answer_module.create_ephemeral_knowledge_answer(
            answer_selector=answer_selector,
            prose_renderer=renderer,
        )

    adapter = seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_Planner(),
        knowledge_read=_Read(),
        answer_factory=answer_factory,
        answer_session_fork=lambda _: answer_factory(),
    )
    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: adapter
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": SIMPLE_QUERY, "entity_id_hint": None},
            headers={"cookie": f"miroflow_chat_session={session_id}"},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        lines = block.split("\n")
        name = next(
            (
                line.removeprefix("event: ")
                for line in lines
                if line.startswith("event: ")
            ),
            "message",
        )
        data = "\n".join(
            line.removeprefix("data: ") for line in lines if line.startswith("data: ")
        )
        if data:
            events.append((name, json.loads(data)))

    names = [name for name, _ in events]
    streamed_text = "".join(
        data["text"] for name, data in events if name == "answer_chunk"
    )
    assert response.status_code == 200
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 1  # one bounded corrective retry
    # The drifted draft was already published and stays visible in the chunks.
    assert streamed_text == drifted_answer
    answer_payload = next(data for name, data in events if name == "answer")
    assert answer_payload["answer_text"] == corrected_answer
    assert names[-2:] == ["answer", "done"]
    assert "error" not in names
    # The turn committed its session instead of rolling back on the mismatch.
    assert session_id in adapter._sessions


def test_s12g_real_http_stream_blocks_traversed_path_value() -> None:
    seam = _load_s11a_seam()
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    getter = seam.deps_module.get_canonical_v2_chat_adapter
    session_id = "session:s12g:http-traversed-path"
    marker = "professor_to_company"
    safe_prefix = "这是可公开的 traversal 回答前缀。" * 12
    split = len(marker) // 2

    class _Planner:
        def plan(self, request: Any) -> Any:
            return read_module.RetrievalPlan(
                plan_version="retrieval-plan-v1",
                original_query=request.original_query,
                behavior_class="A",
                release_id=RELEASE_ID,
                domains=(),
                protected_slots=(),
                lanes=(),
                max_candidates=0,
                web_required=False,
            )

    class _Read:
        def execute(self, plan: Any) -> Any:
            return read_module.EvidenceSet(
                release_id=RELEASE_ID,
                original_query=plan.original_query,
                protected_slots=(),
                items=(),
                traces=(),
                limitations=(),
            )

    class _PathEchoRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            assert value.context_receipt.traversed_path_ids == (marker,)
            chunks = (safe_prefix + marker[:split], marker[split:])
            for chunk in chunks:
                on_chunk(chunk)
            return "".join(chunks)

    renderer = _PathEchoRenderer()

    def answer_factory() -> Any:
        answer = answer_module.create_ephemeral_knowledge_answer(
            prose_renderer=renderer,
        )
        answer._sessions[session_id] = answer_module._SessionState(
            release_id=RELEASE_ID,
            traversed_path_ids=(marker,),
        )
        return answer

    adapter = seam.adapter_type(
        release_id=RELEASE_ID,
        planner=_Planner(),
        knowledge_read=_Read(),
        answer_factory=answer_factory,
        answer_session_fork=lambda _: answer_factory(),
    )
    prior = seam.app.dependency_overrides.get(getter)
    seam.app.dependency_overrides[getter] = lambda: adapter
    try:
        response = TestClient(seam.app, raise_server_exceptions=False).post(
            "/api/chat/stream",
            json={"query": "张教授参与创立了哪些企业？", "entity_id_hint": None},
            headers={"cookie": f"miroflow_chat_session={session_id}"},
        )
    finally:
        if prior is None:
            seam.app.dependency_overrides.pop(getter, None)
        else:
            seam.app.dependency_overrides[getter] = prior

    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.split("\n\n"):
        lines = block.split("\n")
        name = next(
            (
                line.removeprefix("event: ")
                for line in lines
                if line.startswith("event: ")
            ),
            "message",
        )
        data = "\n".join(
            line.removeprefix("data: ") for line in lines if line.startswith("data: ")
        )
        if data:
            events.append((name, json.loads(data)))

    names = [name for name, _ in events]
    streamed_text = "".join(
        data["text"] for name, data in events if name == "answer_chunk"
    )
    assert response.status_code == 200
    assert marker not in response.text
    assert streamed_text and safe_prefix.startswith(streamed_text)
    assert names[-1:] == ["error"]
    assert "answer" not in names
    assert "done" not in names
    assert renderer.calls == 1
    assert adapter._sessions == {}


def test_s12g_disconnect_observation_linearizes_before_session_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seam = _load_s11a_seam()
    second_query = "第二轮断开问题"
    probe = _S12GStageProbe(blocked_stage="answer", blocked_query=second_query)
    adapter = _s12g_real_adapter(seam, probe)
    worker_finished = threading.Event()
    disconnect_observed = threading.Event()
    cancel_entered = threading.Event()

    class _DelayedCancelGate(seam.service_module._TurnCommitGate):
        def cancel(self) -> None:
            cancel_entered.set()
            assert disconnect_observed.is_set()
            probe.release.set()
            if not worker_finished.wait(1.5):
                raise TimeoutError("adapter did not finish in disconnect window")
            super().cancel()

    monkeypatch.setattr(seam.route_module, "_TurnCommitGate", _DelayedCancelGate)
    session_id = "session:s12g-disconnect-linearization"
    first = adapter.answer(
        query="第一轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.answer_text == "第一轮公开问题"

    class _DisconnectedRequest:
        app = SimpleNamespace(state=SimpleNamespace())

        async def is_disconnected(self) -> bool:
            if not await asyncio.to_thread(probe.entered.wait, 1.5):
                raise TimeoutError("answer did not reach the disconnect boundary")
            disconnect_observed.set()
            return True

    async def consume_until_disconnect() -> list[Any]:
        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(
                query=second_query,
                entity_id_hint=None,
            ),
            Response(),
            _DisconnectedRequest(),
            miroflow_chat_session=session_id,
            adapter=_S12GFinishingProxy(adapter, worker_finished),
        )
        return [chunk async for chunk in stream.body_iterator]

    chunks = asyncio.run(consume_until_disconnect())
    assert disconnect_observed.is_set()
    assert cancel_entered.is_set()
    assert worker_finished.is_set()
    assert all(
        f"event: {name}" not in str(chunk)
        for chunk in chunks
        for name in ("answer", "done", "error")
    )

    third = adapter.answer(
        query="第三轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert third.answer_text == "第一轮公开问题｜第三轮公开问题"


def test_s12g_pending_disconnect_observation_blocks_overlapping_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seam = _load_s11a_seam()
    second_query = "第二轮重叠断开问题"
    probe = _S12GStageProbe(blocked_stage="answer", blocked_query=second_query)
    adapter = _s12g_real_adapter(seam, probe)
    worker_finished = threading.Event()
    observation_entered = threading.Event()
    commit_attempted = threading.Event()
    barrier_waiting = threading.Event()
    overlap_verified = threading.Event()

    class _ObservedCondition(threading.Condition):
        def wait(self, timeout: float | None = None) -> bool:
            barrier_waiting.set()
            return super().wait(timeout)

    class _ObservedGate(seam.service_module._TurnCommitGate):
        def __init__(self) -> None:
            super().__init__()
            self._condition = _ObservedCondition()

        def commit(self) -> Any:
            commit_attempted.set()
            return super().commit()

    monkeypatch.setattr(seam.route_module, "_TurnCommitGate", _ObservedGate)
    session_id = "session:s12g-pending-observation-overlap"
    first = adapter.answer(
        query="第一轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.answer_text == "第一轮公开问题"

    class _OverlappingDisconnectRequest:
        app = SimpleNamespace(state=SimpleNamespace())

        async def is_disconnected(self) -> bool:
            if not await asyncio.to_thread(probe.entered.wait, 1.5):
                raise TimeoutError(
                    "answer did not reach pending disconnect observation"
                )
            observation_entered.set()
            probe.release.set()
            if not await asyncio.to_thread(commit_attempted.wait, 1.5):
                raise TimeoutError("adapter did not attempt overlapping session commit")
            if not await asyncio.to_thread(barrier_waiting.wait, 1.5):
                raise TimeoutError("overlapping commit did not wait for observation")
            assert not worker_finished.is_set()
            overlap_verified.set()
            return True

    async def consume_overlapping_disconnect() -> list[Any]:
        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(
                query=second_query,
                entity_id_hint=None,
            ),
            Response(),
            _OverlappingDisconnectRequest(),
            miroflow_chat_session=session_id,
            adapter=_S12GFinishingProxy(adapter, worker_finished),
        )
        return [chunk async for chunk in stream.body_iterator]

    chunks = asyncio.run(consume_overlapping_disconnect())
    assert observation_entered.is_set()
    assert commit_attempted.is_set()
    assert barrier_waiting.is_set()
    assert overlap_verified.is_set()
    assert worker_finished.wait(1.5)
    assert all(
        f"event: {name}" not in str(chunk)
        for chunk in chunks
        for name in ("answer", "done", "error")
    )

    third = adapter.answer(
        query="第三轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert third.answer_text == "第一轮公开问题｜第三轮公开问题"


def test_s12g_commit_before_disconnect_observation_remains_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seam = _load_s11a_seam()
    second_query = "第二轮先提交问题"
    probe = _S12GStageProbe(blocked_stage=None, blocked_query=second_query)
    adapter = _s12g_real_adapter(seam, probe)
    worker_finished = threading.Event()

    class _CommitFirstGate(seam.service_module._TurnCommitGate):
        def begin_transport_observation(self) -> None:
            if not worker_finished.wait(1.5):
                raise TimeoutError("adapter did not commit before disconnect probe")
            super().begin_transport_observation()

    monkeypatch.setattr(seam.route_module, "_TurnCommitGate", _CommitFirstGate)
    session_id = "session:s12g-commit-first-linearization"
    first = adapter.answer(
        query="第一轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.answer_text == "第一轮公开问题"

    class _LateDisconnectedRequest:
        app = SimpleNamespace(state=SimpleNamespace())

        async def is_disconnected(self) -> bool:
            if not await asyncio.to_thread(worker_finished.wait, 1.5):
                raise TimeoutError("adapter did not finish before late disconnect")
            return True

    async def consume_after_commit() -> list[Any]:
        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(
                query=second_query,
                entity_id_hint=None,
            ),
            Response(),
            _LateDisconnectedRequest(),
            miroflow_chat_session=session_id,
            adapter=_S12GFinishingProxy(adapter, worker_finished),
        )
        return [chunk async for chunk in stream.body_iterator]

    asyncio.run(consume_after_commit())
    assert worker_finished.is_set()

    third = adapter.answer(
        query="第三轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert third.answer_text == ("第一轮公开问题｜第二轮先提交问题｜第三轮公开问题")


def _s12g_asgi_http_scope(*, spec_version: str) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/chat/stream",
        "raw_path": b"/api/chat/stream",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
        "app": SimpleNamespace(state=SimpleNamespace()),
    }


@pytest.mark.parametrize(
    ("spec_version", "transport_failure"),
    (
        pytest.param(
            "2.3",
            "receive_disconnect",
            id="asgi-2.3-receive-disconnect",
        ),
        pytest.param(
            "2.4",
            "send_oserror",
            id="asgi-2.4-send-oserror",
        ),
    ),
)
def test_s12g_full_asgi_transport_disconnect_cancels_before_session_commit(
    spec_version: str,
    transport_failure: str,
) -> None:
    seam = _load_s11a_seam()
    second_query = f"第二轮完整 ASGI 断开问题 {spec_version}"
    probe = _S12GStageProbe(blocked_stage="answer", blocked_query=second_query)
    adapter = _s12g_real_adapter(seam, probe)
    worker_finished = threading.Event()
    stream_adapter = _S12GFinishingProxy(adapter, worker_finished)
    session_id = f"session:s12g-full-asgi-disconnect:{spec_version}"

    first = adapter.answer(
        query="第一轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.answer_text == "第一轮公开问题"

    async def exercise_transport_failure() -> list[dict[str, Any]]:
        scope = _s12g_asgi_http_scope(spec_version=spec_version)
        inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        body_send_entered = asyncio.Event()
        hold_body_send = asyncio.Event()
        transport_observed = asyncio.Event()
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            message = await inbound.get()
            if message["type"] == "http.disconnect":
                transport_observed.set()
            return message

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)
            if message["type"] != "http.response.body" or not message.get("more_body"):
                return
            body_send_entered.set()
            if transport_failure == "send_oserror":
                if not await asyncio.to_thread(probe.entered.wait, 1.5):
                    raise TimeoutError("answer did not reach the send failure boundary")
                transport_observed.set()
                raise OSError("test-owned ASGI transport failure")
            await hold_body_send.wait()

        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(
                query=second_query,
                entity_id_hint=None,
            ),
            Response(),
            Request(scope, receive),
            miroflow_chat_session=session_id,
            adapter=stream_adapter,
        )
        response_task = asyncio.create_task(stream(scope, receive, send))
        try:
            if transport_failure == "receive_disconnect":
                await asyncio.wait_for(body_send_entered.wait(), 1.5)
                if not await asyncio.to_thread(probe.entered.wait, 1.5):
                    raise TimeoutError(
                        "answer did not reach the receive disconnect boundary"
                    )
                await inbound.put({"type": "http.disconnect"})
                await asyncio.wait_for(response_task, 1.5)
            else:
                client_disconnect = import_module("starlette.requests").ClientDisconnect
                with pytest.raises(client_disconnect):
                    await asyncio.wait_for(response_task, 1.5)
            assert transport_observed.is_set()
        finally:
            hold_body_send.set()
            if not response_task.done():
                response_task.cancel()
                await asyncio.gather(response_task, return_exceptions=True)
            probe.release.set()
            assert await asyncio.to_thread(worker_finished.wait, 1.5)
        return sent

    sent = asyncio.run(exercise_transport_failure())
    assert [message["type"] for message in sent[:2]] == [
        "http.response.start",
        "http.response.body",
    ]

    third = adapter.answer(
        query="第三轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert third.answer_text == "第一轮公开问题｜第三轮公开问题"


def test_s12g_full_asgi_late_disconnect_preserves_prior_session_commit() -> None:
    seam = _load_s11a_seam()
    second_query = "第二轮完整 ASGI 先提交问题"
    probe = _S12GStageProbe(blocked_stage=None, blocked_query=second_query)
    adapter = _s12g_real_adapter(seam, probe)
    worker_finished = threading.Event()
    session_id = "session:s12g-full-asgi-commit-first"

    first = adapter.answer(
        query="第一轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.answer_text == "第一轮公开问题"

    async def disconnect_after_commit() -> list[dict[str, Any]]:
        scope = _s12g_asgi_http_scope(spec_version="2.3")
        inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        body_send_entered = asyncio.Event()
        hold_body_send = asyncio.Event()
        disconnect_observed = asyncio.Event()
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            message = await inbound.get()
            if message["type"] == "http.disconnect":
                disconnect_observed.set()
            return message

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("more_body"):
                body_send_entered.set()
                await hold_body_send.wait()

        stream = seam.route_module.chat_stream(
            seam.contracts_module.ChatRequest(
                query=second_query,
                entity_id_hint=None,
            ),
            Response(),
            Request(scope, receive),
            miroflow_chat_session=session_id,
            adapter=_S12GFinishingProxy(adapter, worker_finished),
        )
        response_task = asyncio.create_task(stream(scope, receive, send))
        try:
            await asyncio.wait_for(body_send_entered.wait(), 1.5)
            assert await asyncio.to_thread(worker_finished.wait, 1.5)
            await inbound.put({"type": "http.disconnect"})
            await asyncio.wait_for(response_task, 1.5)
            assert disconnect_observed.is_set()
        finally:
            hold_body_send.set()
            if not response_task.done():
                response_task.cancel()
                await asyncio.gather(response_task, return_exceptions=True)
        return sent

    sent = asyncio.run(disconnect_after_commit())
    assert [message["type"] for message in sent[:2]] == [
        "http.response.start",
        "http.response.body",
    ]

    third = adapter.answer(
        query="第三轮公开问题",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert third.answer_text == (
        "第一轮公开问题｜第二轮完整 ASGI 先提交问题｜第三轮公开问题"
    )


class _ReceiptAnchorAnswer:
    """Records turn requests; returns grounded results with a scripted
    ContextReceipt whose active_anchor is one scripted handle per turn."""

    def __init__(self, captured: list[Any], anchors: list[Any]) -> None:
        self._captured = captured
        self._anchors = anchors

    def answer(self, request: Any) -> Any:
        self._captured.append(request)
        answer = import_module("src.data_agents.canonical_v2.knowledge_answer")
        anchor = self._anchors.pop(0) if self._anchors else None
        return answer.TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text=f"web answer for {request.query}",
            citations=(),
            context_receipt=answer.ContextReceipt(active_anchor=anchor),
        )


def _receipt_anchor_adapter(
    *,
    read_script: list[tuple[tuple[Any, ...], tuple[Any, ...]]],
    planning_requests: list[Any],
    answer_requests: list[Any],
    anchors: list[Any],
) -> Any:
    service = import_module("backend.services.canonical_v2_chat")
    answer = _ReceiptAnchorAnswer(answer_requests, anchors)
    return service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_SoftAnchorPlanner(planning_requests),
        knowledge_read=_SoftAnchorRead(read_script),
        answer_factory=lambda: answer,
        answer_session_fork=lambda value: value,
    )


def _canonical_handle(canonical_id: str, domain: str, display_name: str) -> Any:
    read = import_module("src.data_agents.canonical_v2.knowledge_read")
    return read.CanonicalEntityHandle(
        canonical_id=canonical_id,
        domain=domain,
        display_name=display_name,
        evidence_ids=(),
    )


def test_deepening_reference_carries_soft_subject_into_planning() -> None:
    """Register §1 trigger B: a referential deepening turn keeps the org
    subject in planning instead of degrading to unpinned topic views."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,)), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:deepening-carryover"

    first = adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    assert first.query_type != "canonical_v2:G:clarification_only"

    second = adapter.answer(
        query="这个中心的企业培育情况怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert (
        planning_requests[1].soft_context_subject
        == "国际先进技术应用推进中心（深圳）"
    )


def test_deepening_reference_keeps_soft_subject_after_commit() -> None:
    """The commit path keeps the stored soft subject across a deepening turn
    instead of re-deriving garbage from the referential query (and losing
    the anchor for every later turn)."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,)), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:deepening-keep"

    adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    adapter.answer(
        query="这个中心的企业培育情况怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert (
        adapter._sessions[session_id].soft_subject_name
        == "国际先进技术应用推进中心（深圳）"
    )


def test_bare_pronoun_deepening_answers_about_soft_subject() -> None:
    """Register §1 trigger A: after the badcase pair, a bare-它 deepening
    answers about the carried subject instead of clarifying (and instead of
    binding whatever record the vector lane leaked)."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,)), ((), ()), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:pronoun-deepening"

    adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    adapter.answer(
        query="有没有更详细的信息",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    third = adapter.answer(
        query="它有哪些布局和进展",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert third.query_type != "canonical_v2:G:clarification_only"
    assert (
        planning_requests[2].soft_context_subject
        == "国际先进技术应用推进中心（深圳）"
    )
    assert planning_requests[2].displayed_entity_ids == ()


def test_anaphoric_reference_binds_canonical_anchor() -> None:
    """With a legitimate canonical anchor active, a generic referential
    institution noun binds it into planning like a typed singular referent."""
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _receipt_anchor_adapter(
        read_script=[((), ()), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
        anchors=[_canonical_handle("company:hualichuang", "company", "华力创科学")],
    )
    session_id = "session:anaphoric-canonical"

    adapter.answer(
        query="介绍一下华力创科学",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    second = adapter.answer(
        query="该机构的发展情况怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert planning_requests[1].displayed_entity_ids == ("company:hualichuang",)


def test_person_pronoun_over_org_soft_subject_still_clarifies() -> None:
    """A person-typed pronoun over an organization-level soft subject is a
    genuine mismatch and must keep yielding the referent clarification."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,))],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:person-pronoun-guard"

    adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    second = adapter.answer(
        query="他有哪些论文",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type == "canonical_v2:G:clarification_only"


def test_explicit_subject_deepening_does_not_carry_soft_anchor() -> None:
    """An explicit named subject on the deepening turn wins over the stored
    soft anchor; the org subject must not leak into that planning request."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _soft_anchor_adapter(
        read_script=[((web_item,), (web_handle,)), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )
    session_id = "session:explicit-subject-guard"

    adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    adapter.answer(
        query="华力创科学这家公司的情况怎么样",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert (
        planning_requests[1].soft_context_subject
        != "国际先进技术应用推进中心（深圳）"
    )


def test_leaked_canonical_anchor_dropped_on_soft_turn() -> None:
    """Register §1 root cause 3: a vector-lane canonical record that captured
    the answer receipt on a web-only turn must not become the session anchor
    nor bind the next referential turn."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _receipt_anchor_adapter(
        read_script=[((web_item,), (web_handle,)), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
        anchors=[_canonical_handle("professor:hit-sz:zhangty", "professor", "张天尧")],
    )
    session_id = "session:leak-guard"

    adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    committed_receipt = adapter._sessions[session_id].context_receipt
    assert committed_receipt is None or committed_receipt.active_anchor is None

    second = adapter.answer(
        query="它有哪些布局和进展",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    assert second.query_type != "canonical_v2:G:clarification_only"
    assert planning_requests[1].displayed_entity_ids == ()
    assert (
        planning_requests[1].soft_context_subject
        == "国际先进技术应用推进中心（深圳）"
    )


def test_matching_canonical_anchor_kept_on_soft_turn() -> None:
    """A canonical anchor whose name matches the turn's subject survives the
    commit sanitize (legitimate canonical capture on a soft-anchored turn)."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _receipt_anchor_adapter(
        read_script=[((web_item,), (web_handle,))],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
        anchors=[_canonical_handle("company:ubtech", "company", "优必选科技")],
    )
    session_id = "session:matching-anchor"

    adapter.answer(
        query="介绍一下优必选",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    receipt = adapter._sessions[session_id].context_receipt
    assert receipt is not None
    assert receipt.active_anchor is not None
    assert receipt.active_anchor.display_name == "优必选科技"


def test_web_handle_anchor_kept_on_soft_turn() -> None:
    """Web handles are the soft subject's own anchor shape and are never
    dropped by the commit sanitize."""
    _, web_item, web_handle = _soft_anchor_web_turn()
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _receipt_anchor_adapter(
        read_script=[((web_item,), (web_handle,))],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
        anchors=[web_handle],
    )
    session_id = "session:web-handle-anchor"

    adapter.answer(
        query="介绍一下 国际先进技术应用推进中心（深圳）",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    receipt = adapter._sessions[session_id].context_receipt
    assert receipt is not None
    assert receipt.active_anchor is web_handle or (
        receipt.active_anchor is not None
        and receipt.active_anchor.kind == "web"
    )


def test_planned_canonical_ids_never_sanitized() -> None:
    """Turns that planned canonical displayed ids (real referent/entity
    turns) keep the receipt anchor untouched even when the names mismatch."""
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    adapter = _receipt_anchor_adapter(
        read_script=[((), ()), ((), ())],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
        anchors=[
            _canonical_handle("company:hualichuang", "company", "华力创科学"),
            _canonical_handle("company:hualichuang", "company", "华力创科学"),
        ],
    )
    session_id = "session:planned-ids-guard"

    adapter.answer(
        query="介绍一下华力创科学",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )
    adapter.answer(
        query="该公司的专利有哪些",
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )

    receipt = adapter._sessions[session_id].context_receipt
    assert receipt is not None
    assert receipt.active_anchor is not None
    assert receipt.active_anchor.display_name == "华力创科学"
