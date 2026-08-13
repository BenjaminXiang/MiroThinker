"""Content-addressed runtime inputs for one isolated Canonical V2 Candidate."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from threading import Lock
import threading
from time import monotonic
from typing import Any, Literal, cast
from urllib.parse import urlparse, urlsplit, urlunsplit

from openai import OpenAI, OpenAIError
from pypinyin import lazy_pinyin
from pydantic import Field, ValidationInfo, field_validator, model_validator

from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.providers.bocha_search import BochaSearchProvider
from src.data_agents.providers.web_search import WebSearchProvider

from .contracts import ContractModel
from .followup_referents import (
    COMPANY_NAME_PATTERN,
    IDENTIFIER_PATTERN,
    _EXPLICIT_COMPANY_REJECT_MARKERS,
    _search_view,
    extract_institution_person_name,
    extract_leading_company_name,
    has_continuation_intent,
    has_explicit_named_subject,
    has_set_referent,
    has_singular_referent,
    strip_leading_pronoun,
)
from .knowledge_answer import (
    AnswerSelectionProposal,
    MaterialClaimProposal,
    ProseSynthesisResult,
    TurnRequest,
    claim_text_is_raw_dump,
    create_ephemeral_knowledge_answer,
)
from .knowledge_gap_feedback import create_ephemeral_knowledge_gap_feedback
from .knowledge_read import (
    AmbiguityPolicy,
    EvidenceClaimBinding,
    EvidenceItem,
    LaneRequest,
    MaterialPartProposal,
    MaterialQuestionPart,
    ProtectedSlot,
    QueryPlanningPolicy,
    QueryPlanningRequest,
    QueryViewProposal,
    RecallCandidate,
    RecordedPlanningProposal,
    RerankProposal,
    RerankRequest,
    RelationshipPathProposal,
    RetrievalLaneResult,
    SufficiencyDecisionRequest,
    SufficiencyProposal,
    SupplementalBudget,
    SupplementalLaneResult,
    SupplementalRequest,
    WebEvidenceSnapshot,
    WebSearchPolicy,
    WebSnapshotPayload,
    WebSnapshotPolicy,
    _extract_protected_slots,
    _explicit_organization_name,
    _retention_values,
)
from .knowledge_read_isolated import _NAMED_COMPANY_PATENT_PATTERN
from .llm_judgments import create_llm_judge


# Pinned to knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK.  The
# build module imports this one (load_recorded_serving_inputs), so importing
# the constant back would close an import cycle; a contract test asserts the
# two values stay equal.  Degraded professor fields carrying this placeholder
# must render as absent, not as literal source text.
_PROFESSOR_MISSING_FIELD_FALLBACK = "Not supplied by the historical source."
_ZERO_SHA256 = "0" * 64
_PUBLIC_DOMAINS = ("professor", "company", "paper", "patent")
_SERVING_AMBIGUITY_ENTITY_TYPE = "professor"
_SERVING_AMBIGUITY_POLICY_VERSION = "canonical-v2-serving-ambiguity-v1"
_SERVING_AMBIGUITY_MINIMUM_EVIDENCE_COUNT = 1
_SERVING_AMBIGUITY_CONFIDENCE_THRESHOLD = 0.5
_SERVING_AMBIGUITY_MINIMUM_LEAD_MARGIN = 0.25
_WEB_SEMANTIC_TRANSLATION = str.maketrans(
    {
        "總": "总",
        "註": "注",
        "冊": "册",
        "辦": "办",
        "處": "处",
        "門": "门",
        "開": "开",
        "電": "电",
    }
)
_CITY_NAMES = (
    "北京",
    "上海",
    "天津",
    "重庆",
    "深圳",
    "广州",
    "杭州",
    "南京",
    "苏州",
    "成都",
    "武汉",
    "西安",
    "长沙",
    "郑州",
    "青岛",
    "宁波",
    "厦门",
    "福州",
    "济南",
    "合肥",
    "南昌",
    "昆明",
    "贵阳",
    "南宁",
    "海口",
    "石家庄",
    "太原",
    "沈阳",
    "长春",
    "哈尔滨",
    "呼和浩特",
    "兰州",
    "西宁",
    "银川",
    "乌鲁木齐",
    "香港",
    "澳门",
)
_PROSE_RENDER_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="canonical-v2-prose",
)
_logger = logging.getLogger(__name__)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class RecordedServingBundle(ContractModel):
    """Secret-free runtime policy bound to one Candidate's physical artifacts."""

    schema_version: Literal["canonical-v2-serving-bundle-v1"]
    bundle_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    database_name: str = Field(min_length=1)
    database_target_kind: Literal["disposable"]
    index_target_id: str = Field(min_length=1)
    index_root: Path
    envelope_path: Path
    embedding_model_id: str = Field(min_length=1)
    planner_model_id: Literal["canonical-v2-deterministic-planner-v1"]
    answer_model_id: Literal["canonical-v2-deterministic-answer-v1"]
    web_provider: Literal["bocha-serper-v1"]
    bocha_api_key_env: Literal["BOCHA_API_KEY"]
    serper_api_key_env: Literal["SERPER_API_KEY"]
    max_candidates: int = Field(gt=0, le=100)
    max_web_results: int = Field(gt=0, le=20)
    web_timeout_ms: int = Field(gt=0, le=30_000)
    web_snapshot_max_bytes: int = Field(gt=0, le=1_000_000)
    content_sha256: str = Field(
        default=_ZERO_SHA256,
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("index_root", "envelope_path")
    @classmethod
    def require_absolute_paths(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("serving artifact paths must be absolute")
        return value

    @model_validator(mode="after")
    def bind_content(self, info: ValidationInfo) -> RecordedServingBundle:
        expected = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if info.context and info.context.get("external_content_addressed"):
            if self.content_sha256 == _ZERO_SHA256:
                raise ValueError("external serving bundle requires an explicit hash")
        if self.content_sha256 == _ZERO_SHA256:
            object.__setattr__(self, "content_sha256", expected)
        elif self.content_sha256 != expected:
            raise ValueError("serving bundle content hash differs")
        return self


@dataclass(frozen=True, slots=True)
class RecordedServingInputs:
    planning_policy: QueryPlanningPolicy
    proposal_provider: Callable[[QueryPlanningRequest], RecordedPlanningProposal]
    ambiguity_policy: AmbiguityPolicy | None
    universal_web_policy: WebSearchPolicy
    web_search: Callable[[LaneRequest], RetrievalLaneResult]
    web_snapshot_policy: WebSnapshotPolicy
    embedding_adapter: Any
    identity_fuser: None
    reranker: Callable[[RerankRequest], RerankProposal]
    sufficiency_decider: Callable[[SufficiencyDecisionRequest], Any]
    supplemental_search: Callable[[SupplementalRequest], Any]
    web_handle_resolver: None
    accepted_identity_lookup: None
    answer_factory: Callable[[], Any]
    answer_session_fork: Callable[[Any], Any]
    gap_operations: Any
    supplemental_budget: SupplementalBudget
    authority_sha256: str
    idle_keepwarm_cycle: Callable[[], None]


@dataclass(frozen=True, slots=True)
class _QuestionFrame:
    subject_scope: Literal["displayed_set", "explicit"]
    predicate: Literal[
        "headquarters_city",
        "registered_address",
        "office_city",
        "branch_city",
        "product_capability",
        "geography",
        "other",
    ]
    requested_values: tuple[str, ...]
    logic: Literal["all", "any"] = "all"


def _cities_in_text(value: str) -> tuple[str, ...]:
    return tuple(city for city in _CITY_NAMES if city in value)


def _question_frame(query: str) -> _QuestionFrame:
    scope = "displayed_set" if has_set_referent(query) else "explicit"
    cities = _cities_in_text(query)
    if "注册地址" in query or "工商地址" in query:
        return _QuestionFrame(scope, "registered_address", cities)
    if "总部" in query:
        return _QuestionFrame(scope, "headquarters_city", cities)
    if any(marker in query for marker in ("分公司", "分支机构")):
        return _QuestionFrame(scope, "branch_city", cities)
    if any(marker in query for marker in ("办公室", "办事处", "办公地")):
        return _QuestionFrame(scope, "office_city", cities)
    if "产品" in query and any(
        marker in query
        for marker in ("能力", "支持", "实现", "能够", "可以", "刷卡", "门禁", "开门", "机械臂")
    ):
        values: list[str] = []
        if "刷卡" in query or "门禁" in query:
            values.append("刷门禁")
        if "开门" in query:
            values.append("开门")
        if "机械臂" in query:
            values.append("机械臂")
        if "按电梯" in query or "电梯按钮" in query:
            values.append("按电梯")
        return _QuestionFrame(
            scope,
            "product_capability",
            tuple(dict.fromkeys(values)),
            "any" if any(marker in query for marker in ("或", "或者", "任一")) else "all",
        )
    if cities:
        return _QuestionFrame(scope, "geography", cities)
    return _QuestionFrame(scope, "other", ())


def _relation_clause(value: str, markers: tuple[str, ...]) -> str | None:
    clauses = re.split(r"[，,。；;！!]", value)
    return next(
        (clause for clause in clauses if any(marker in clause for marker in markers)),
        None,
    )


def _web_claim_semantics(
    *,
    frame: _QuestionFrame,
    title: str,
    snippet: str,
    fallback_value: str,
) -> tuple[str, str]:
    text = f"{title}。{snippet}".translate(_WEB_SEMANTIC_TRANSLATION)
    relation_markers = {
        "headquarters_city": ("总部",),
        "registered_address": ("注册地址", "工商地址"),
        "office_city": ("办公室", "办事处", "办公地"),
        "branch_city": ("分公司", "分支机构"),
    }
    markers = relation_markers.get(frame.predicate)
    if markers is not None:
        clause = _relation_clause(text, markers)
        if clause is not None and (cities := _cities_in_text(clause)):
            return frame.predicate, cities[0]
        return "current_web_result", fallback_value
    if frame.predicate == "geography":
        matched = next((city for city in frame.requested_values if city in text), None)
        if matched is not None:
            return "geography", matched
    if frame.predicate == "product_capability" and frame.requested_values:
        normalized = text.replace("刷卡", "刷门禁").replace("电梯按钮", "按电梯")
        matched = tuple(value for value in frame.requested_values if value in normalized)
        sufficient = (
            len(matched) == len(frame.requested_values)
            if frame.logic == "all"
            else bool(matched)
        )
        if sufficient:
            return "product_capability_evidence", " + ".join(matched)
    return "current_web_result", fallback_value


def _infer_domains(query: str) -> tuple[str, ...]:
    domains: set[str] = set()
    if _explicit_organization_name(query) is not None:
        domains.add("company")
    if extract_leading_company_name(query) is not None:
        domains.add("company")
    if any(
        marker in query
        for marker in (
            "教授",
            "老师",
            "学者",
            "研究方向",
            "任教",
            "导师",
            "课题组",
        )
    ):
        domains.add("professor")
    if any(
        marker in query
        for marker in (
            "公司",
            "企业",
            "融资",
            "产品",
            "工商",
            "供应商",
            "厂商",
            "创业",
            "创始人",
            "总部",
        )
    ):
        domains.add("company")
    normalized_query = query.casefold()
    if "打板" in query or any(marker in normalized_query for marker in ("pcb", "pcba")):
        domains.add("company")
    if any(marker in query for marker in ("论文", "文章", "发表", "期刊", "作者")):
        domains.add("paper")
    if any(
        marker in query for marker in ("专利", "申请号", "公开号", "发明人", "申请人")
    ):
        domains.add("patent")
    if extract_institution_person_name(query) is not None:
        domains.add("professor")
    return tuple(domain for domain in _PUBLIC_DOMAINS if domain in domains) or (
        _PUBLIC_DOMAINS
    )


def _contextual_web_search_view(query: str) -> str:
    frame = _question_frame(query)
    relation_term = {
        "headquarters_city": "总部",
        "registered_address": "注册地址",
        "office_city": "办公室",
        "branch_city": "分公司",
    }.get(frame.predicate)
    if relation_term is not None:
        return " ".join((relation_term, *frame.requested_values))
    if frame.predicate == "product_capability" and frame.requested_values:
        capability_terms = tuple(
            f"自主{value}" if value in {"刷门禁", "按电梯"} else value
            for value in frame.requested_values
        )
        return " ".join(("机器人", *capability_terms))
    value = _search_view(strip_leading_pronoun(query))
    product_scoped = "产品" in value
    value = re.sub(
        r"(?:上述|以上|这些|上面|其中)(?:的)?(?:企业|公司|主体)?"
        r"(?:里|中|内)?(?:的)?",
        " ",
        value,
    )
    value = re.sub(
        r"(?:产品)?(?:有)?哪些(?:可以|能够)?(?:实现|支持)?",
        " ",
        value,
    )
    value = re.sub(r"(?:分别)?(?:是)?谁$", " ", value)
    value = re.sub(r"(?:是|有)?什么$", " ", value)
    value = value.replace("送餐机器人", " 配送机器人 ")
    value = re.sub(r"(?:需要|能够|可以|使用)", " ", value)
    if "刷卡" in value and ("开门" in value or "门禁" in value):
        value = value.replace("自主刷卡", "刷门禁")
        value = value.replace("刷卡", "刷门禁")
        value = value.replace("和开门", " 开门")
    elif "刷卡" in value and "刷门禁" not in value:
        value = value.replace("刷卡", "刷卡 刷门禁")
    normalized = re.sub(r"[\s，,。！？?]+", " ", value).strip()
    if product_scoped and normalized:
        normalized = f"产品 {normalized}"
    return normalized or _search_view(query)


def _is_lawful_safety_guidance(query: str) -> bool:
    risk_markers = ("黄赌毒", "赌博", "毒品", "涉黄", "违法场所", "危险场所")
    avoidance_markers = (
        "避开",
        "避免",
        "不能去",
        "不要去",
        "如何防范",
        "安全",
        "举报",
    )
    return any(marker in query for marker in risk_markers) and any(
        marker in query for marker in avoidance_markers
    )


# Patent intent must follow the named company directly ("X的专利",
# "X有哪些专利") for a company→patent traversal; a company that merely names
# something else's possessor ("X的竞争对手有哪些专利") never anchors the path.
_NAMED_COMPANY_PATENT_OWNERSHIP_FOLLOW = re.compile(
    r"(?:的(?:相关)?专利|有(?:哪些|什么|多少)?(?:相关)?专利)"
)


def _has_named_company_patent_ownership_intent(
    query: str,
    displayed_entity_names: tuple[str, ...],
) -> bool:
    """Whether a company-name hit in the query owns the asked-about patents.

    Mirrors the possessive branch of
    :func:`knowledge_read_isolated._named_company_patent_names`: either the
    possessive pattern captures a real name ("普渡科技的专利有哪些"), or a
    company-suffixed extraction / displayed name is immediately followed by
    patent intent ("深圳市普渡科技有限公司有哪些专利", "普渡科技有哪些专利").
    Referent/quantifier lookalikes ("这些公司", "其他公司的专利有哪些") are
    rejected the same way as in :func:`followup_referents._has_explicit_company_name`.
    """
    for match in _NAMED_COMPANY_PATENT_PATTERN.finditer(query):
        name = match.group("name")
        if not any(marker in name for marker in _EXPLICIT_COMPANY_REJECT_MARKERS):
            return True
    extracted = [
        match.group(1)
        for match in COMPANY_NAME_PATTERN.finditer(query)
        if not any(
            marker in match.group(1)
            for marker in _EXPLICIT_COMPANY_REJECT_MARKERS
        )
    ]
    for name in dict.fromkeys((*extracted, *displayed_entity_names)):
        if not name:
            continue
        start = 0
        while True:
            index = query.find(name, start)
            if index < 0:
                break
            if _NAMED_COMPANY_PATENT_OWNERSHIP_FOLLOW.match(
                query[index + len(name) :]
            ):
                return True
            start = index + 1
    return False


def _relationship_path(
    request: QueryPlanningRequest,
) -> tuple[RelationshipPathProposal, ...]:
    if not request.displayed_entity_ids:
        return ()
    query = request.original_query
    displayed_id = request.displayed_entity_ids[0]
    if displayed_id.startswith(("professor-", "professor:")) and any(
        marker in query for marker in ("公司", "企业", "创业", "创办", "创立")
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="professor_company_role",
                direction="professor_to_company",
                source_type="professor",
                target_type="company",
            ),
        )
    if displayed_id.startswith(("company-", "company:")) and any(
        marker in query for marker in ("教授", "老师", "学者", "创始人", "联合创始人")
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="professor_company_role",
                direction="company_to_professor",
                source_type="company",
                target_type="professor",
            ),
        )
    if displayed_id.startswith(("professor-", "professor:")) and any(
        marker in query
        for marker in ("论文", "研究成果", "科研成果", "学术成果", "代表作", "发表")
    ) and (
        has_singular_referent(query)
        or "教授" in query
        or "老师" in query
        or has_continuation_intent(query)
        or any(
            name and name in query for name in request.displayed_entity_names
        )
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="professor_authored_paper",
                direction="professor_to_paper",
                source_type="professor",
                target_type="paper",
            ),
        )
    if displayed_id.startswith(("paper-", "paper:")) and any(
        marker in query for marker in ("作者", "教授", "老师")
    ) and any(
        marker in query for marker in ("这篇", "该论文", "论文")
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="professor_authored_paper",
                direction="paper_to_professor",
                source_type="paper",
                target_type="professor",
            ),
        )
    if (
        displayed_id.startswith(("company-", "company:"))
        and len(request.displayed_entity_ids) == 1
        and "专利" in query
        and (
            has_singular_referent(query)
            or has_set_referent(query)
            or has_continuation_intent(query)
            or any(marker in query for marker in ("它", "该公司", "这家"))
            or _has_named_company_patent_ownership_intent(
                query, request.displayed_entity_names
            )
        )
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="company_has_patent",
                direction="company_to_patent",
                source_type="company",
                target_type="patent",
            ),
        )
    if displayed_id.startswith(("patent-", "patent:")) and any(
        marker in query for marker in ("申请公司", "申请人", "哪个公司")
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="company_has_patent",
                direction="patent_to_company",
                source_type="patent",
                target_type="company",
            ),
        )
    return ()


def _proposal_provider(
    *,
    bundle: RecordedServingBundle,
    query_rewriter: Callable[[str], tuple[str, ...]] | None = None,
    view_store: _ServingQueryViewStore | None = None,
) -> Callable[[QueryPlanningRequest], RecordedPlanningProposal]:
    def provide(request: QueryPlanningRequest) -> RecordedPlanningProposal:
        if _is_lawful_safety_guidance(request.original_query):
            return RecordedPlanningProposal(
                proposal_id=f"planning-proposal:serving:{request.request_id}",
                request_sha256=request.content_sha256,
                schema_version="retrieval-plan-proposal-v1",
                model_id=bundle.planner_model_id,
                prompt_version="canonical-v2-serving-plan-v1",
                behavior_class="F",
                interaction_mode="safety_guidance",
                domains=(),
                lanes=(),
                max_candidates=0,
                max_provider_calls=0,
                web_mode="disabled",
                max_web_results=0,
            )
        relationship_paths = _relationship_path(request)
        if relationship_paths:
            path = relationship_paths[0]
            domains = (path.target_type,)
            lanes = ("relationship", "web")
        else:
            domains = _infer_domains(request.original_query)
            lanes = ("exact", "structured", "lexical", "vector", "web")
        search_text = (
            _contextual_web_search_view(request.original_query)
            if request.displayed_entity_names
            else _search_view(request.original_query)
        )
        if request.displayed_entity_names:
            if len(request.displayed_entity_names) == 1:
                entity_context = request.displayed_entity_names[0]
            else:
                entity_context = (
                    "("
                    + " OR ".join(
                        f'"{name}"' for name in request.displayed_entity_names
                    )
                    + ")"
                )
            search_text = f"{entity_context} {search_text}"
        protected_slots = _extract_protected_slots(request)
        retained_values = _retention_values(protected_slots)
        if any(
            slot.kind != "displayed_entity_set"
            and slot.raw_text
            and slot.raw_text not in search_text
            for slot in protected_slots
        ):
            search_text = request.original_query
        soft_context_subject = request.soft_context_subject
        if soft_context_subject is not None:
            # Same shape as the displayed-entity context prefix above: the
            # soft subject leads the web search text so an elaboration
            # follow-up stays about the prior web-only subject.
            if soft_context_subject not in search_text:
                search_text = f"{soft_context_subject} {search_text}"
            if soft_context_subject not in retained_values:
                retained_values = (*retained_values, soft_context_subject)
            # retained_values only records the value on each view; the
            # rewrite missing-append below consumes protected slot raw text,
            # so the soft subject rides a synthetic slot to be appended back
            # into any LLM rewrite view that dropped it.
            protected_slots = (
                *protected_slots,
                ProtectedSlot(
                    kind="soft_context_subject",
                    raw_text=soft_context_subject,
                ),
            )
        query_views = _serving_query_views(
            request=request,
            search_text=search_text,
            retained_values=retained_values,
            protected_slots=protected_slots,
            planner_model_id=bundle.planner_model_id,
            query_rewriter=query_rewriter,
        )
        if view_store is not None:
            view_store.record(
                request.original_query,
                tuple(view.text for view in query_views[1:]),
            )
        material_parts: tuple[MaterialQuestionPart, ...] = ()
        if not relationship_paths:
            if request.displayed_entity_ids:
                material_parts = _displayed_relation_material_parts(request)
            else:
                person_part = _person_criteria_material_part(request.original_query)
                if person_part is not None:
                    material_parts = (person_part,)
                else:
                    theme_part = _theme_material_part(request.original_query)
                    if theme_part is not None:
                        material_parts = (theme_part,)
        return RecordedPlanningProposal(
            proposal_id=f"planning-proposal:serving:{request.request_id}",
            request_sha256=request.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id=bundle.planner_model_id,
            prompt_version="canonical-v2-serving-plan-v1",
            behavior_class="A",
            interaction_mode="information_retrieval",
            domains=domains,
            lanes=lanes,
            query_views=query_views,
            relationship_paths=relationship_paths,
            material_parts=material_parts,
            # List-style questions need a wider recall window: relevant
            # suppliers routinely rank 10-25 in the vector lane, and the
            # default window cuts them before fusion ever sees them. The chat
            # layer only attaches enumeration_context on follow-up turns, so
            # fresh list queries are detected by their own markers.
            max_candidates=(
                max(
                    bundle.max_candidates + bundle.max_web_results,
                    _ENUMERATION_CANDIDATE_WINDOW,
                )
                if (
                    (
                        request.enumeration_context is not None
                        and request.enumeration_context.requested
                    )
                    or any(
                        marker in request.original_query
                        for marker in _ENUMERATION_QUERY_MARKERS
                    )
                )
                else bundle.max_candidates + bundle.max_web_results
            ),
            max_provider_calls=1,
            enumeration_mode=("representative" if relationship_paths else None),
            web_mode="universal",
            # List-style questions widen the web window as well as the
            # candidate window: supplier mentions in merged brand-list views
            # routinely rank 9-16, and the read side truncates web candidates
            # at this cap before theme probes ever see them.  The cap must
            # follow the enumeration candidate window so discovery-view tails
            # (九号 at merged rank 36-43) survive the read-side truncation.
            max_web_results=(
                max(bundle.max_web_results, _ENUMERATION_CANDIDATE_WINDOW)
                if (
                    (
                        request.enumeration_context is not None
                        and request.enumeration_context.requested
                    )
                    or any(
                        marker in request.original_query
                        for marker in _ENUMERATION_QUERY_MARKERS
                    )
                )
                else bundle.max_web_results
            ),
            professor_vector_view=(
                "both" if "professor" in domains and "vector" in lanes else None
            ),
        )

    return provide


def _web_domain(request: LaneRequest) -> str:
    return request.domains[0] if request.domains else "company"


@dataclass(frozen=True, slots=True)
class _NormalizedWebResult:
    title: str
    url: str
    snippet: str
    summary: str
    primary_provider_version: str
    corroborating_provider_versions: tuple[str, ...]


def _prioritize_relation_evidence(
    *,
    results: tuple[_NormalizedWebResult, ...],
    frame: _QuestionFrame,
    request: LaneRequest,
) -> tuple[_NormalizedWebResult, ...]:
    expected_predicate = (
        "product_capability_evidence"
        if frame.predicate == "product_capability"
        else frame.predicate
    )
    if expected_predicate == "other":
        return results

    def relation_evidence_tier(result: _NormalizedWebResult) -> int:
        predicate, _ = _web_claim_semantics(
            frame=frame,
            title=result.title,
            snippet=result.snippet,
            fallback_value="",
        )
        if predicate != expected_predicate:
            return 2
        matched_entity = _matched_bound_entity(
            request=request,
            title=result.title,
            snippet=result.snippet,
            locator=result.url,
        )
        return 0 if matched_entity is not None else 1

    return tuple(
        result
        for _, result in sorted(
            enumerate(results),
            key=lambda indexed: (
                relation_evidence_tier(indexed[1]),
                indexed[0],
            ),
        )
    )


# Subject-consistency floor: with bound anchors, off-subject single-channel
# results may only backfill the lane up to this many survivors; corroborated
# results and subject hits always outrank them.
_WEB_SUBJECT_CONSISTENCY_FLOOR = 3


def _apply_web_subject_consistency(
    *,
    results: tuple[_NormalizedWebResult, ...],
    request: LaneRequest,
) -> tuple[_NormalizedWebResult, ...]:
    bound_entity_names = request.bound_entity_names
    if (
        request.soft_context_subject is not None
        and request.soft_context_subject not in bound_entity_names
    ):
        # Web-only sessions bind no canonical entities: the soft subject rides
        # its own LaneRequest field and enters only this gate, never
        # _matched_bound_entity (no entity id exists to anchor on, so the
        # names/ids alignment contract stays untouched).
        bound_entity_names = (*bound_entity_names, request.soft_context_subject)
    if not bound_entity_names:
        return results
    anchor_qualifier = next(
        (
            qualifier
            for name in bound_entity_names
            if (
                qualifier := _anchor_location_qualifier(
                    name, str(getattr(request, "original_query", "") or "")
                )
            )
            is not None
        ),
        None,
    )
    tiered = [
        (
            _web_result_relevance_tier(
                result=result,
                bound_entity_names=bound_entity_names,
                anchor_qualifier=anchor_qualifier,
            ),
            index,
            result,
        )
        for index, result in enumerate(results)
    ]
    kept = [entry for entry in tiered if entry[0] in (0, 1)]
    # Tier order decides among the non-kept channels (T2 before T3 before T4
    # before T5); within a tier the original result order stays stable.
    related = sorted(
        (entry for entry in tiered if entry[0] in (2, 3)),
        key=lambda entry: entry[0],
    )
    suspect = [entry for entry in tiered if entry[0] == 4]
    missed = [entry for entry in tiered if entry[0] == 5]

    def unwrap(entries):
        return [result for _, _, result in entries]

    if len(kept) >= _WEB_SUBJECT_CONSISTENCY_FLOOR:
        # T4/T5 are the wrong-organization channels and drop out; T2/T3 are
        # same-organization background and stay, ordered after the anchor hits.
        return tuple(unwrap(kept) + unwrap(related))
    # Demotion first, filtering second: below the floor the demoted results
    # backfill in tier order so obscure single-channel subjects keep evidence
    # and the lane never empties into the unavailable branch.
    pool = unwrap(related) + unwrap(suspect) + unwrap(missed)
    return tuple(unwrap(kept) + pool[: _WEB_SUBJECT_CONSISTENCY_FLOOR - len(kept)])


def _normalized_web_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )


def _compact_company_alias(entity_name: str) -> str:
    search_name = entity_name.strip().strip('"')
    # Parenthesized segments (（深圳）) never belong to the brand.
    search_name = re.sub(r"（[^）]*）|\([^)]*\)", "", search_name)
    search_name = re.sub(r"(?:股份)?有限公司$", "", search_name)
    search_name = re.sub(r"^[\u4e00-\u9fff]{2,4}市", "", search_name, count=1)
    search_name = re.sub(
        r"(?:(?:智能)?科技|(?:科学)?技术|自动化|机器人)$",
        "",
        search_name,
    )
    # The distinctive brand is the leading run before the first industry word
    # (帕西尼感知科技 -> 帕西尼, 全世萝卜机器人应用科技 -> 全世萝卜); only take it
    # when it actually shortens the alias.
    brand = re.split(
        r"(?:科技|技术|机器人|自动化|智能|感知|电子|实业|控股|集团|工业|医疗|生物|信息)",
        search_name,
        maxsplit=1,
    )[0]
    if 2 <= len(brand) < len(search_name):
        return brand
    return search_name if len(search_name) >= 2 else entity_name


def _relaxed_serper_query(query: str) -> str:
    displayed_set = re.match(r'^\((?P<entities>.+)\)\s+(?P<remainder>.+)$', query)
    if displayed_set is not None:
        names = re.findall(r'"([^"]+)"', displayed_set.group("entities"))
        aliases = tuple(dict.fromkeys(_compact_company_alias(name) for name in names))
        if aliases:
            return f"({' OR '.join(aliases)}) {displayed_set.group('remainder')}"
    entity_name, separator, remainder = query.partition(" ")
    if not separator:
        return query
    search_name = _compact_company_alias(entity_name)
    if search_name == entity_name:
        return query
    return f"{search_name} {remainder}"


class _DualWebLaneAdapter:
    def __init__(
        self,
        *,
        timeout_ms: int,
        max_snapshot_bytes: int,
        clock: Callable[[], datetime],
        bocha: Any | None = None,
        serper: Any | None = None,
        page_fetcher: Callable[[str], str | None] | None = None,
        extra_view_queries: Callable[[str], tuple[str, ...]] | None = None,
        gap_judge: Any | None = None,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._max_snapshot_bytes = max_snapshot_bytes
        self._clock = clock
        provider_attempt_timeout = max(0.1, self._timeout_ms * 0.00045)
        self._bocha = bocha or BochaSearchProvider(timeout=provider_attempt_timeout)
        self._serper = serper or WebSearchProvider(timeout=provider_attempt_timeout)
        self._page_fetcher = page_fetcher
        self._page_fetch_timeout = max(2.0, provider_attempt_timeout)
        self._extra_view_queries = extra_view_queries
        self._gap_judge = gap_judge
        self._executor = ThreadPoolExecutor(
            # 4 plan query views x 2 providers run concurrently per Web lane;
            # a smaller pool would serialize later views past their deadline.
            max_workers=8,
            thread_name_prefix="canonical-v2-web",
        )

    @staticmethod
    def _search_provider(provider: Any, query: str) -> list[dict[str, Any]]:
        try:
            payload = provider.search(query)
        except Exception:  # noqa: BLE001 - each provider degrades independently
            return []
        organic = payload.get("organic", ()) if isinstance(payload, dict) else ()
        if not isinstance(organic, list):
            return []
        return [item for item in organic if isinstance(item, dict)]

    @staticmethod
    def _normalize_results(
        *,
        provider_version: str,
        results: list[dict[str, Any]],
    ) -> list[_NormalizedWebResult]:
        normalized: list[_NormalizedWebResult] = []
        for raw in results:
            title = str(raw.get("title") or "").strip()
            locator = str(raw.get("link") or raw.get("url") or "").strip()
            parsed = urlparse(locator)
            if not title or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            normalized.append(
                _NormalizedWebResult(
                    title=title,
                    url=locator,
                    snippet=str(raw.get("snippet") or "").strip(),
                    summary=str(raw.get("summary") or "").strip(),
                    primary_provider_version=provider_version,
                    corroborating_provider_versions=(provider_version,),
                )
            )
        return normalized

    def _merged_results(self, query: str) -> tuple[_NormalizedWebResult, ...]:
        futures = {
            "bocha-v1": self._executor.submit(
                self._search_provider,
                self._bocha,
                query,
            ),
            "serper-v1": self._executor.submit(
                self._search_provider,
                self._serper,
                _relaxed_serper_query(query),
            ),
        }
        timeout_seconds = self._timeout_ms / 1000
        provider_results: dict[str, list[dict[str, Any]]] = {}
        for provider_version, future in futures.items():
            try:
                provider_results[provider_version] = future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                provider_results[provider_version] = []
        return self._normalize_and_order_results(provider_results=provider_results)

    def _normalize_and_order_results(
        self,
        *,
        provider_results: dict[str, list[dict[str, Any]]],
    ) -> tuple[_NormalizedWebResult, ...]:
        normalized_by_provider = {
            provider_version: self._normalize_results(
                provider_version=provider_version,
                results=provider_results[provider_version],
            )
            for provider_version in ("bocha-v1", "serper-v1")
        }
        merged_by_url: dict[str, _NormalizedWebResult] = {}
        for provider_version in ("bocha-v1", "serper-v1"):
            for item in normalized_by_provider[provider_version]:
                normalized_url = _normalized_web_url(item.url)
                previous = merged_by_url.get(normalized_url)
                if previous is None:
                    merged_by_url[normalized_url] = item
                    continue
                merged_by_url[normalized_url] = _NormalizedWebResult(
                    title=previous.title,
                    url=previous.url,
                    snippet=previous.snippet,
                    summary=previous.summary,
                    primary_provider_version=previous.primary_provider_version,
                    corroborating_provider_versions=tuple(
                        dict.fromkeys(
                            previous.corroborating_provider_versions
                            + item.corroborating_provider_versions
                        )
                    ),
                )
        ordered: list[_NormalizedWebResult] = []
        retained_urls: set[str] = set()
        provider_order = ("bocha-v1", "serper-v1")
        max_provider_results = max(
            (len(normalized_by_provider[provider]) for provider in provider_order),
            default=0,
        )
        for rank in range(max_provider_results):
            for provider_version in provider_order:
                results = normalized_by_provider[provider_version]
                if rank >= len(results):
                    continue
                normalized_url = _normalized_web_url(results[rank].url)
                if normalized_url in retained_urls:
                    continue
                retained_urls.add(normalized_url)
                ordered.append(merged_by_url[normalized_url])
        # Dual-channel corroboration outranks provider rotation: a result both
        # providers returned is a stronger subject signal than Bocha's raw rank
        # (production badcase: Bocha filled top ranks with a similarly named
        # wrong institution while Serper stayed on-topic). Relative order is
        # preserved inside the corroborated and single-channel groups.
        corroborated = [
            item for item in ordered if len(item.corroborating_provider_versions) >= 2
        ]
        single_channel = [
            item for item in ordered if len(item.corroborating_provider_versions) < 2
        ]
        return tuple(corroborated + single_channel)

    def _request_view_queries(
        self,
        request: LaneRequest,
        query_text: str,
    ) -> tuple[str, ...]:
        if self._extra_view_queries is None:
            return (query_text,)
        extras = tuple(
            text
            for text in dict.fromkeys(self._extra_view_queries(request.original_query))
            if isinstance(text, str) and text and text != query_text
        )
        if not extras:
            return (query_text,)
        return (query_text, *_enumeration_ordered_view_queries(
            original_query=request.original_query,
            extras=extras,
        ))[:_SERVING_WEB_MAX_QUERY_VIEWS]

    def _merged_results_for_views(
        self,
        queries: tuple[str, ...],
    ) -> tuple[_NormalizedWebResult, ...]:
        if len(queries) <= 1:
            return self._merged_results(queries[0] if queries else "")
        timeout_seconds = self._timeout_ms / 1000
        futures: dict[tuple[int, str], Any] = {}
        for index, query in enumerate(queries):
            futures[(index, "bocha-v1")] = self._executor.submit(
                self._search_provider,
                self._bocha,
                query,
            )
            futures[(index, "serper-v1")] = self._executor.submit(
                self._search_provider,
                self._serper,
                _relaxed_serper_query(query),
            )
        per_view: list[tuple[_NormalizedWebResult, ...]] = []
        for index in range(len(queries)):
            provider_results: dict[str, list[dict[str, Any]]] = {}
            for provider_version in ("bocha-v1", "serper-v1"):
                try:
                    provider_results[provider_version] = futures[
                        (index, provider_version)
                    ].result(timeout=timeout_seconds)
                except FutureTimeoutError:
                    provider_results[provider_version] = []
            per_view.append(
                self._normalize_and_order_results(provider_results=provider_results)
            )
        discovery_indexes = tuple(
            index
            for index, query in enumerate(queries[1:], start=1)
            if _is_brand_discovery_view(query)
        )
        return _discovery_front_merge(per_view, discovery_indexes)

    def _enrich_with_page_text(
        self,
        results: tuple[_NormalizedWebResult, ...],
        *,
        depth: int = 2,
    ) -> tuple[_NormalizedWebResult, ...]:
        if self._page_fetcher is None:
            return results
        targets = tuple(
            result
            for result in results[:depth]
            if not result.url.casefold().endswith(".pdf")
        )
        if not targets:
            return results
        fetched_by_url: dict[str, str] = {}
        futures = {
            self._executor.submit(self._page_fetcher, result.url): result.url
            for result in targets
        }
        for future, url in futures.items():
            try:
                text = future.result(timeout=self._page_fetch_timeout)
            except Exception:  # noqa: BLE001 - a failed fetch keeps the snippet
                text = None
            if text:
                fetched_by_url[url] = text
        if not fetched_by_url:
            return results
        return tuple(
            _NormalizedWebResult(
                title=result.title,
                url=result.url,
                snippet=fetched_by_url[result.url][:1200],
                summary=fetched_by_url[result.url],
                primary_provider_version=result.primary_provider_version,
                corroborating_provider_versions=result.corroborating_provider_versions,
            )
            if result.url in fetched_by_url
            else result
            for result in results
        )

    def __call__(self, request: LaneRequest) -> RetrievalLaneResult:
        query_text = re.sub(
            r"\s*\[lane=web\]\s*$",
            "",
            request.query_text,
        ).strip()
        question_frame = _question_frame(request.original_query)
        organic = _prioritize_relation_evidence(
            results=_apply_web_subject_consistency(
                results=self._merged_results_for_views(
                    self._request_view_queries(request, query_text)
                ),
                request=request,
            ),
            frame=question_frame,
            request=request,
        )
        # List-style questions get deeper page fetches: company/theme mentions
        # that bind recall (开普勒/九号 in brand listicles) sit below the
        # snippet cut, so two fetches miss them.
        fetch_depth = (
            5
            if any(
                marker in request.original_query
                for marker in _ENUMERATION_QUERY_MARKERS
            )
            else 2
        )
        organic = self._enrich_with_page_text(organic, depth=fetch_depth)
        if self._gap_judge is not None and _should_rewrite_serving_query(
            request.original_query
        ):
            digest = "\n".join(
                f"- {item.title}：{item.snippet[:120]}" for item in organic[:8]
            )
            try:
                gap_results = self._gap_judge.judge_batch(
                    "gap_check",
                    request.original_query,
                    {"gap": digest},
                )
                gap = gap_results[0] if gap_results else None
            except Exception:  # noqa: BLE001 - gap loop never breaks the lane
                gap = None
            if gap is not None and not gap.covered and gap.followup_queries:
                followup_results = self._merged_results_for_views(
                    tuple(gap.followup_queries[:2])
                )
                if followup_results:
                    organic = _merge_web_results_across_views(
                        [organic, followup_results]
                    )
        if not organic:
            raise ConnectionError("Bocha and Serper Web search are unavailable")
        candidates: list[RecallCandidate] = []
        snapshots: list[WebSnapshotPayload] = []
        domain = _web_domain(request)
        for rank, raw in enumerate(organic[: request.max_candidates], start=1):
            title = raw.title
            locator = raw.url
            snippet = raw.snippet
            snapshot_content = json.dumps(
                {
                    "title": title,
                    "link": locator,
                    "snippet": snippet,
                    "summary": raw.summary,
                    "primary_provider_version": raw.primary_provider_version,
                    "corroborating_provider_versions": list(
                        raw.corroborating_provider_versions
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")[: self._max_snapshot_bytes]
            snapshot_sha256 = hashlib.sha256(snapshot_content).hexdigest()
            snapshot_id = f"web-snapshot:sha256:{snapshot_sha256}"
            object_id = (
                f"web-object:sha256:{hashlib.sha256(locator.encode()).hexdigest()}"
            )
            matched_entity = _matched_bound_entity(
                request=request,
                title=title,
                snippet=snippet,
                locator=locator,
            )
            canonical_id = matched_entity[0] if matched_entity is not None else None
            display_name = matched_entity[1] if matched_entity is not None else title
            evidence_identity = {
                "request": request.content_sha256,
                "locator": locator,
                "snapshot": snapshot_id,
            }
            evidence_id = f"web-evidence:sha256:{_canonical_sha256(evidence_identity)}"
            observed_at = self._clock().astimezone(timezone.utc)
            predicate, claim_value = _web_claim_semantics(
                frame=question_frame,
                title=title,
                snippet=snippet,
                fallback_value=snapshot_sha256,
            )
            evidence = EvidenceItem(
                evidence_id=evidence_id,
                object_id=object_id,
                domain=domain,
                lane="web",
                source_nature="current_web",
                source_locator=locator,
                snippet=(f"{title}：{snippet}" if snippet else title),
                score=max(0.0, 1.0 - ((rank - 1) * 0.05)),
                source_authority=(
                    "official"
                    if any(
                        (urlparse(locator).hostname or "").endswith(host)
                        for host in request.web_policy.allowed_domains
                    )
                    else "web_search"
                ),
                observed_at=observed_at,
                claim_binding=EvidenceClaimBinding(
                    subject_id=canonical_id or object_id,
                    predicate=predicate,
                    value=claim_value,
                    status="observed",
                ),
                web_snapshot=WebEvidenceSnapshot(
                    snapshot_id=snapshot_id,
                    content_sha256=snapshot_sha256,
                    retrieved_at=observed_at,
                    byte_length=len(snapshot_content),
                ),
            )
            candidate_id = (
                f"web-candidate:sha256:{_canonical_sha256(evidence_identity)}"
            )
            candidates.append(
                RecallCandidate(
                    raw_candidate_id=candidate_id,
                    display_name=display_name,
                    domain=domain,
                    identity_kind=("web_candidate" if canonical_id else "web_only"),
                    canonical_id=canonical_id,
                    resolution_state=("resolved" if canonical_id else "unresolved"),
                    query_view=request.query_view,
                    lane="web",
                    attempt=1,
                    release_id=request.release_id,
                    adapter_version="canonical-v2-dual-web-lane-v1",
                    provider_version=raw.primary_provider_version,
                    raw_score=evidence.score,
                    evidence=(evidence,),
                )
            )
            snapshots.append(
                WebSnapshotPayload(snapshot_id=snapshot_id, content=snapshot_content)
            )
        return RetrievalLaneResult(
            candidates=tuple(candidates),
            web_snapshot_payloads=tuple(snapshots),
        )


# --- LLM query rewriting for serving recall widening (multi-view Web lane) ---

_SERVING_WEB_MAX_QUERY_VIEWS = 4
_SERVING_QUERY_REWRITE_MAX_QUERIES = 3
_SERVING_QUERY_REWRITER_VERSION = "canonical-v2-llm-query-rewrite-v1"
_QUERY_REWRITE_TIMEOUT_SECONDS = 2.0
_QUERY_REWRITE_MAX_TOKENS = 150
_QUERY_REWRITE_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="canonical-v2-query-rewrite",
)
_QUERY_REWRITE_SYSTEM_PROMPT = (
    "你是搜索查询改写助手，帮助检索系统查全相关公开信息。"
    "理解用户问题的真实意图，只输出一个JSON对象："
    '{"queries": ["...", "..."]}，包含1到3条简短的中文关键词式搜索查询。'
    "规则：多意图问题按意图逐条拆分；"
    "主题类/概念类问题（问方法、路线、方式、差异、原理、厂商等）："
    "围绕主题补充该领域常见子方向与行业术语作为搜索词"
    "（例如“具身智能数据采集”可补充“遥操作、动作捕捉、真机采集、仿真合成”），"
    "以便检索到相关行业内容；"
    "严格限于用户问题涉及的主题范围，不得编造具体公司、论文、专利、人名等"
    "实体名称，不得编造事实与数字；"
    "每条不超过30个字；不要输出JSON之外的任何内容。"
)
_QUERY_REWRITE_ENUMERATION_MARKERS = (
    "哪些",
    "推荐",
    "分别",
    "几种",
    "多少",
    "列出",
    "所有",
)
_QUERY_REWRITE_INTENT_CONNECTORS = ("以及", "还有", "同时", "并且")
_QUERY_REWRITE_CONJUNCTION_PATTERN = re.compile(
    r"(?<!以)及|和[^，,。；;？?！!]*(?:情况|信息|评价|特点|竞争力)"
)
_QUERY_REWRITE_PROFILE_PATTERN = re.compile(r"介绍|是谁|的详细信息")
# "X 的 Y" attribute follow-ups (创始人/教育背景/产量/竞争力/评价/总部...):
# the deterministic web view carries only the entity name, so the attribute
# dimension must reach the rewrite views or the web lane never searches it.
_QUERY_REWRITE_ATTRIBUTE_PATTERN = re.compile(
    r"的(创始人|创始团队|联合创始人|CEO|董事长|总经理|教育背景|学历|背景|"
    r"产量|产能|竞争力|评价|总部|核心团队|团队|融资|股东|产品|业务|布局|"
    r"营收|利润|专利|历史|发展|现状|规模|排名|荣誉|奖项|技术|研究方向|论文|"
    r"代表作|代表作品|市场|客户|合作|联系方式|地址)"
)
_ARXIV_IDENTIFIER_PATTERN = re.compile(
    r"(?:arxiv:)?\b\d{4}\.\d{4,5}(?:v\d+)?(?!\d)",
    re.IGNORECASE,
)

# Rewrite views that explicitly ask for a brand/name list ("国内成熟酒店配送
# 机器人品牌", "酒店服务机器人头部企业名单") are discovery queries: their
# results routinely carry supplier mentions (九号/开普勒 in brand listicles)
# that the plain-view results bury below the candidate cut.  On enumeration
# turns those views are merged before the other rewrite views so their
# mentions reach the theme probes.
_BRAND_DISCOVERY_VIEW_MARKERS = (
    "品牌",
    "名单",
    "排名",
    "排行",
    "头部",
    "汇总",
    "厂商",
    "厂家",
)

# Deterministic term-expansion views for data-theme concept questions.  The
# LLM rewrite sometimes drifts (e.g. "数据采集路线规划方法" pulls traffic/GIS
# content) or omits the domain vocabulary that the thematic articles actually
# use (动作捕捉/物理仿真引擎...).  When the query names a data theme, append
# one term view so recall covers the industry terminology; it replaces the
# last LLM rewrite when the view budget is already full.
_CONCEPT_TERM_VIEW_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("数据采集", "数据路线", "数据需求"),
        "具身智能 机器人 数据采集 遥操作 动作捕捉 真机 仿真 方法",
    ),
    (
        ("合成数据",),
        "具身智能 合成数据 物理仿真引擎 生成式模型 规则 方法 厂商",
    ),
)


def _concept_term_view_text(query: str) -> str | None:
    for markers, text in _CONCEPT_TERM_VIEW_RULES:
        if any(marker in query for marker in markers):
            return text
    return None


# Answer-side relevance guard for data-theme concept questions.  The LLM
# rewrite sometimes drifts to adjacent domains (traffic surveys, web
# crawlers, crowdsourcing), and the prose prompt's relevance instruction is
# not enough — the drifted claims reached the answer anyway (T19).  Claims
# carrying these off-theme terms are dropped before they reach either the
# prose prompt or the deterministic fallback.  A query that names an
# alternate data domain itself (网页/交通/网络/地图… data collection) keeps
# its own claims: the guard only fires for the embodied-AI data themes.
_CONCEPT_QUERY_MARKERS = ("数据采集", "数据路线", "数据需求", "合成数据")
_CONCEPT_QUERY_ALTERNATE_ANCHOR_MARKERS = (
    "网页",
    "网站",
    "页面",
    "网络",
    "交通",
    "地图",
    "GIS",
    "GPS",
    "爬虫",
)
_CONCEPT_OFF_TOPIC_CLAIM_MARKERS = (
    "交通",
    "感应环",
    "路调",
    "点调",
    "测绘",
    "网约车",
    "爬虫",
    "众包",
    "GIS",
    "GPS",
    "网页抓取",
    "网络爬虫",
)


def _concept_theme_filter_active(query: str) -> bool:
    if not any(marker in query for marker in _CONCEPT_QUERY_MARKERS):
        return False
    return not any(
        marker in query for marker in _CONCEPT_QUERY_ALTERNATE_ANCHOR_MARKERS
    )


def _concept_off_topic_claim(text: str) -> bool:
    return any(marker in text for marker in _CONCEPT_OFF_TOPIC_CLAIM_MARKERS)


def _enumeration_ordered_view_queries(
    *,
    original_query: str,
    extras: tuple[str, ...],
) -> tuple[str, ...]:
    """Order rewrite views for an enumeration turn: discovery views first."""
    if not any(marker in original_query for marker in _ENUMERATION_QUERY_MARKERS):
        return extras
    discovery = tuple(
        text
        for text in extras
        if any(marker in text for marker in _BRAND_DISCOVERY_VIEW_MARKERS)
    )
    if not discovery:
        return extras
    return (
        *discovery,
        *(text for text in extras if text not in discovery),
    )


def _intent_connector_count(query: str) -> int:
    return sum(
        query.count(connector) for connector in _QUERY_REWRITE_INTENT_CONNECTORS
    ) + len(_QUERY_REWRITE_CONJUNCTION_PATTERN.findall(query))


def _should_rewrite_serving_query(query: str) -> bool:
    """Deterministic fast-path gate for LLM query rewriting.

    Rewriting fires only for multi-intent questions (enumeration markers or
    at least two intent connectors) and thematic/conceptual questions with no
    explicit named subject. It never fires for identifier queries (patent
    numbers, arXiv ids), single named-entity profile queries, or
    safety-guidance queries.
    """
    text = query.strip()
    if not text:
        return False
    if _is_lawful_safety_guidance(text):
        return False
    if IDENTIFIER_PATTERN.search(text) is not None:
        return False
    if _ARXIV_IDENTIFIER_PATTERN.search(text) is not None:
        return False
    enumeration = any(marker in text for marker in _QUERY_REWRITE_ENUMERATION_MARKERS)
    multi_intent = _intent_connector_count(text) >= 2
    attribute_question = _QUERY_REWRITE_ATTRIBUTE_PATTERN.search(text) is not None
    if _QUERY_REWRITE_PROFILE_PATTERN.search(text) is not None and not (
        enumeration or multi_intent or attribute_question
    ):
        return False
    return (
        enumeration
        or multi_intent
        or attribute_question
        or not has_explicit_named_subject(text)
    )


def _parse_rewritten_queries(content: str) -> tuple[str, ...]:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced is not None:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ()
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, dict):
        return ()
    queries = payload.get("queries")
    if not isinstance(queries, list):
        return ()
    cleaned: list[str] = []
    for item in queries:
        if not isinstance(item, str):
            continue
        value = " ".join(item.split())
        if value and value not in cleaned:
            cleaned.append(value)
    return tuple(cleaned[:_SERVING_QUERY_REWRITE_MAX_QUERIES])


class _ServingQueryRewriter:
    """Environment-LLM query rewriter for recall widening.

    Mirrors _EnvironmentProseRenderer's construction and isolation pattern:
    the OpenAI-compatible client is built lazily from the configured chat LLM
    profile, the call runs on a bounded executor under a hard timeout, and
    any failure degrades to no rewrites so the deterministic view stays the
    only view (zero regression on the serving path).
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = _QUERY_REWRITE_TIMEOUT_SECONDS,
        max_tokens: int = _QUERY_REWRITE_MAX_TOKENS,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._client: Any | None = None
        self._model = ""
        self._extra_body: dict[str, Any] = {}
        self._client_lock = Lock()

    def _configured_client(self) -> tuple[Any, str, dict[str, Any]]:
        with self._client_lock:
            if self._client is not None:
                return self._client, self._model, self._extra_body
            profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
            settings = resolve_professor_llm_settings(
                profile,
                apply_endpoint_env_overrides=False,
            )
            api_key = settings.get("local_llm_api_key")
            if not api_key:
                raise ValueError("configured chat LLM API key is unavailable")
            model = str(settings["local_llm_model"])
            self._client = OpenAI(
                base_url=settings["local_llm_base_url"],
                api_key=api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
            self._model = model
            self._extra_body = build_non_thinking_extra_body(model)
            return self._client, self._model, self._extra_body

    @property
    def producer_version(self) -> str:
        try:
            return str(self._configured_client()[1])
        except (
            ConnectionError,
            OpenAIError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return _SERVING_QUERY_REWRITER_VERSION

    def _chat_completion(self, query: str) -> str:
        client, model, extra_body = self._configured_client()
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": _QUERY_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            extra_body=extra_body,
        )
        choices = getattr(response, "choices", ())
        content = (
            None
            if not choices
            else getattr(getattr(choices[0], "message", None), "content", None)
        )
        if not isinstance(content, str):
            raise ValueError("LLM query rewrite response is not text")
        return content

    def __call__(self, query: str) -> tuple[str, ...]:
        try:
            future = _QUERY_REWRITE_EXECUTOR.submit(self._chat_completion, query)
            content = future.result(timeout=self._timeout_seconds)
        except (
            ConnectionError,
            FutureTimeoutError,
            OpenAIError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return ()
        return _parse_rewritten_queries(content)


class _ServingQueryViewStore:
    """Hands plan-level rewrite views to the serving Web lane.

    LaneRequest does not carry the plan's query views, so the serving
    composition shares them through this store, keyed by the exact original
    query text (LaneRequest.original_query always equals the planned
    QueryPlanningRequest.original_query). The planner records on every plan,
    so a later deterministic-only plan for the same text clears earlier
    rewrites; entries are bounded FIFO.
    """

    _CAPACITY = 256

    def __init__(self) -> None:
        self._lock = Lock()
        self._view_texts_by_query: dict[str, tuple[str, ...]] = {}

    def record(self, original_query: str, view_texts: tuple[str, ...]) -> None:
        with self._lock:
            if not view_texts:
                self._view_texts_by_query.pop(original_query, None)
                return
            if original_query in self._view_texts_by_query:
                del self._view_texts_by_query[original_query]
            while len(self._view_texts_by_query) >= self._CAPACITY:
                self._view_texts_by_query.pop(next(iter(self._view_texts_by_query)))
            self._view_texts_by_query[original_query] = view_texts

    def views_for(self, original_query: str) -> tuple[str, ...]:
        with self._lock:
            return self._view_texts_by_query.get(original_query, ())


def _merge_web_results_across_views(
    per_view: list[tuple[_NormalizedWebResult, ...]],
) -> tuple[_NormalizedWebResult, ...]:
    """URL-dedup merge across views.

    The earliest view/rank wins the slot (deterministic view first); provider
    provenance unions through corroborating_provider_versions exactly like
    the per-view dual-provider merge.
    """
    merged_by_url: dict[str, _NormalizedWebResult] = {}
    ordered_urls: list[str] = []
    for results in per_view:
        for item in results:
            normalized_url = _normalized_web_url(item.url)
            previous = merged_by_url.get(normalized_url)
            if previous is None:
                merged_by_url[normalized_url] = item
                ordered_urls.append(normalized_url)
                continue
            merged_by_url[normalized_url] = _NormalizedWebResult(
                title=previous.title,
                url=previous.url,
                snippet=previous.snippet,
                summary=previous.summary,
                primary_provider_version=previous.primary_provider_version,
                corroborating_provider_versions=tuple(
                    dict.fromkeys(
                        previous.corroborating_provider_versions
                        + item.corroborating_provider_versions
                    )
                ),
            )
    return tuple(merged_by_url[url] for url in ordered_urls)


def _is_brand_discovery_view(text: str) -> bool:
    """True for rewrite views aimed at supplier/brand listicles."""
    return any(marker in text for marker in _BRAND_DISCOVERY_VIEW_MARKERS)


def _discovery_front_merge(
    per_view: list[tuple[_NormalizedWebResult, ...]],
    discovery_view_indexes: tuple[int, ...],
    *,
    plain_head_limit: int = 10,
    front_limit: int = 14,
) -> tuple[_NormalizedWebResult, ...]:
    """Merge views with brand-discovery results promoted ahead of the rest.

    Brand-list views carry supplier mentions (九号/开普勒 in brand listicles)
    at ranks 9-16 of their own view; the literal-query view's 20+ results
    otherwise bury them below the candidate cut.  The literal view keeps its
    head (``plain_head_limit``), then the first ``front_limit`` discovery
    results follow, then the tail of every view.  When no discovery view is
    present the merge degenerates to the plain earliest-view-wins merge.
    """
    if not discovery_view_indexes:
        return _merge_web_results_across_views(per_view)
    discovery = tuple(
        item
        for index in discovery_view_indexes
        for item in per_view[index]
    )
    other = tuple(
        item
        for index, view in enumerate(per_view)
        if index != 0 and index not in discovery_view_indexes
        for item in view
    )
    return _merge_web_results_across_views(
        [
            per_view[0][:plain_head_limit],
            discovery[:front_limit],
            per_view[0][plain_head_limit:],
            other,
            discovery[front_limit:],
        ]
    )


def _authority_seeking_view_texts(
    *,
    request: QueryPlanningRequest,
    original_query: str,
) -> tuple[str, ...]:
    """Authority-seeking view texts for org-level anchors (spec §2c).

    The qualifying anchor is the first displayed entity name, then the soft
    context subject, whose ``_anchor_location_qualifier`` is None — i.e. an
    org-level anchor where the user named no city.  A city-qualified anchor
    keeps the phase-1 view set (pin, don't broaden), so no texts are
    produced; likewise when no anchor exists at all.
    """
    candidates = (
        *request.displayed_entity_names,
        *((request.soft_context_subject,) if request.soft_context_subject else ()),
    )
    for name in candidates:
        if not isinstance(name, str) or not name.strip():
            continue
        if _anchor_location_qualifier(name, original_query) is not None:
            continue
        stripped = name.strip()
        return (f"{stripped} 百度百科", f"{stripped} 官网")
    return ()


def _append_authority_seeking_views(
    views: list[QueryViewProposal],
    *,
    request: QueryPlanningRequest,
    retained_values: tuple[str, ...],
    required_raw_texts: tuple[str, ...],
) -> tuple[QueryViewProposal, ...]:
    """Append authority-seeking views last, deduplicated by exact text.

    Appending last means the extra recall never displaces the deterministic,
    rewrite, or term views; the web lane's per-view concurrency treats them
    as extra views.  Like the rewrite views, any protected raw text the
    authority text dropped is appended back so the plan-level
    lost_protected_slot invariant holds on every view.
    """
    seen_texts = {view.text for view in views}
    for text in _authority_seeking_view_texts(
        request=request, original_query=request.original_query,
    ):
        missing = tuple(raw for raw in required_raw_texts if raw not in text)
        view_text = " ".join((text, *missing)) if missing else text
        if view_text in seen_texts:
            continue
        seen_texts.add(view_text)
        views.append(
            QueryViewProposal(
                view_id=f"view:serving:{request.request_id}:authority:{len(views)}",
                kind="serving_search",
                text=view_text,
                original_query_sha256=request.original_query_sha256,
                retained_protected_values=retained_values,
                producer_kind="authority_seeking",
                producer_version=_SERVING_QUERY_REWRITER_VERSION,
                bound_entity_ids=request.displayed_entity_ids,
                bound_entity_names=request.displayed_entity_names,
                soft_context_subject=request.soft_context_subject,
            )
        )
    return tuple(views)


def _serving_query_views(
    *,
    request: QueryPlanningRequest,
    search_text: str,
    retained_values: tuple[str, ...],
    protected_slots: tuple[ProtectedSlot, ...],
    planner_model_id: str,
    query_rewriter: Callable[[str], tuple[str, ...]] | None,
) -> tuple[QueryViewProposal, ...]:
    """Deterministic view first, then up to three LLM rewrite views, then
    authority-seeking views for org-level anchors.

    Rewrite views keep the retained protected values of the turn; any
    protected raw text the rewrite dropped (geography, year, quoted name,
    identifier, negation term) is appended back so the plan-level
    lost_protected_slot invariant holds on every view.  Authority-seeking
    views are appended last on every return path so they never displace the
    phase-1 views; they get the same missing-raw-text append.
    """
    deterministic = QueryViewProposal(
        view_id=f"view:serving:{request.request_id}",
        kind="serving_search",
        text=search_text,
        original_query_sha256=request.original_query_sha256,
        retained_protected_values=retained_values,
        producer_kind="deterministic",
        producer_version=planner_model_id,
        bound_entity_ids=request.displayed_entity_ids,
        bound_entity_names=request.displayed_entity_names,
        soft_context_subject=request.soft_context_subject,
    )
    required_raw_texts = tuple(
        slot.raw_text
        for slot in protected_slots
        if slot.kind != "displayed_entity_set" and slot.raw_text
    )
    if query_rewriter is None or not _should_rewrite_serving_query(
        request.original_query
    ):
        return _append_authority_seeking_views(
            [deterministic],
            request=request,
            retained_values=retained_values,
            required_raw_texts=required_raw_texts,
        )
    try:
        rewritten = query_rewriter(request.original_query)
        candidates = tuple(dict.fromkeys(rewritten))
        producer_version = str(
            getattr(
                query_rewriter,
                "producer_version",
                _SERVING_QUERY_REWRITER_VERSION,
            )
        )
    except Exception:  # noqa: BLE001 - recall widening must never break planning
        return _append_authority_seeking_views(
            [deterministic],
            request=request,
            retained_values=retained_values,
            required_raw_texts=required_raw_texts,
        )
    views = [deterministic]
    for text in candidates:
        if not isinstance(text, str) or not text or text == search_text:
            continue
        missing = tuple(raw for raw in required_raw_texts if raw not in text)
        views.append(
            QueryViewProposal(
                view_id=f"view:serving:{request.request_id}:rewrite:{len(views)}",
                kind="serving_search",
                text=" ".join((text, *missing)) if missing else text,
                original_query_sha256=request.original_query_sha256,
                retained_protected_values=retained_values,
                producer_kind="llm_rewrite",
                producer_version=producer_version,
                bound_entity_ids=request.displayed_entity_ids,
                bound_entity_names=request.displayed_entity_names,
        soft_context_subject=request.soft_context_subject,
            )
        )
        if len(views) >= _SERVING_WEB_MAX_QUERY_VIEWS:
            break
    term_view_text = _concept_term_view_text(request.original_query)
    existing_texts = {view.text for view in views}
    if term_view_text is not None and term_view_text not in existing_texts:
        if len(views) >= _SERVING_WEB_MAX_QUERY_VIEWS:
            views = views[:-1]
        # Promote the term view directly after the deterministic view: the
        # merge is earliest-view-wins, so a term view appended last was
        # drowned below the candidate cut by the rewrite views (T19 lost
        # 动作捕捉 content that only the term view recalls).
        views.insert(
            1,
            QueryViewProposal(
                view_id=f"view:serving:{request.request_id}:term:0",
                kind="serving_search",
                text=term_view_text,
                original_query_sha256=request.original_query_sha256,
                retained_protected_values=retained_values,
                producer_kind="term_expansion",
                producer_version=_SERVING_QUERY_REWRITER_VERSION,
                bound_entity_ids=request.displayed_entity_ids,
                bound_entity_names=request.displayed_entity_names,
        soft_context_subject=request.soft_context_subject,
            ),
        )
    return _append_authority_seeking_views(
        views,
        request=request,
        retained_values=retained_values,
        required_raw_texts=required_raw_texts,
    )


def _normalized_web_identity(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


_ANCHOR_LOCATION_LEXICON = frozenset({
    "北京", "上海", "广州", "深圳", "合肥", "南沙", "杭州", "苏州", "南京",
    "武汉", "成都", "重庆", "西安", "天津", "青岛", "宁波", "无锡", "长沙",
    "郑州", "佛山", "东莞", "珠海", "厦门", "福州", "济南", "大连", "沈阳",
    "哈尔滨", "长春", "昆明", "贵阳", "南昌", "太原", "石家庄", "兰州",
    "乌鲁木齐", "呼和浩特", "南宁", "海口", "银川", "西宁", "拉萨", "香港",
    "澳门", "台北", "雄安", "大湾区",
})

_PAREN_QUALIFIER_RE = re.compile(r"[（(]([^（）()]{1,8})[）)]")


def _parenthesized_qualifier(value: str) -> str | None:
    match = _PAREN_QUALIFIER_RE.search(value)
    if match is None:
        return None
    qualifier = _normalized_web_identity(match.group(1))
    return qualifier or None


def _org_name_stem(value: str) -> str:
    return _normalized_web_identity(_PAREN_QUALIFIER_RE.sub("", value))


def _anchor_location_qualifier(anchor_name: str, query: str) -> str | None:
    qualifier = _parenthesized_qualifier(anchor_name)
    if qualifier is not None:
        return qualifier if qualifier in _ANCHOR_LOCATION_LEXICON else None
    stem = _org_name_stem(anchor_name)
    if not stem:
        return None
    normalized_query = _normalized_web_identity(query)
    if stem not in normalized_query:
        return None
    for location in _ANCHOR_LOCATION_LEXICON:
        if location in normalized_query:
            return location
    return None


def _web_identity_full_name_forms(value: str) -> tuple[str, ...]:
    normalized = _normalized_web_identity(value)
    forms = [normalized]
    stem = _org_name_stem(value)
    if stem and stem != normalized:
        forms.append(stem)
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "公司"):
        normalized_suffix = _normalized_web_identity(suffix)
        if normalized.endswith(normalized_suffix):
            shortened = normalized[: -len(normalized_suffix)]
            if len(shortened) >= 4:
                forms.append(shortened)
                without_city = re.sub(
                    r"^[\u3400-\u9fff]{2,4}市", "", shortened, count=1,
                )
                if len(without_city) >= 4:
                    forms.append(without_city)
            break
    return tuple(dict.fromkeys(form for form in forms if form))


def _web_identity_compact_aliases(value: str) -> tuple[str, ...]:
    compact_alias = _normalized_web_identity(_compact_company_alias(value))
    full = set(_web_identity_full_name_forms(value))
    if len(compact_alias) >= 2 and compact_alias not in full:
        return (compact_alias,)
    return ()


def _web_identity_forms(value: str) -> tuple[str, ...]:  # re-implemented, same output
    return (*_web_identity_full_name_forms(value), *_web_identity_compact_aliases(value))


_SHORT_BRAND_CONTEXT_MARKERS = (
    "机器人",
    "科技",
    "智能",
    "公司",
    "集团",
    "品牌",
    "官方",
    "产品",
    "產品",
)
_BRAND_DOMAIN_SUFFIXES = (
    "",
    "ai",
    "china",
    "group",
    "robot",
    "robots",
    "robotics",
    "tech",
    "technology",
)


def _web_identity_text_matches(form: str, searchable: str) -> bool:
    if len(form) >= 4:
        return form in searchable
    return len(form) >= 2 and any(
        f"{form}{marker}" in searchable or f"{marker}{form}" in searchable
        for marker in _SHORT_BRAND_CONTEXT_MARKERS
    )


def _evidence_branch_qualifiers(
    *, org_stem: str, texts: tuple[str, ...], anchor_qualifier: str | None
) -> tuple[str, ...]:
    if not org_stem:
        return ()
    found: list[str] = []
    pattern = re.compile(
        r"[（(]([^（）()]{1,8})[）)]"
    )
    for text in texts:
        if org_stem not in _normalized_web_identity(text):
            continue
        for match in pattern.finditer(text):
            qualifier = _normalized_web_identity(match.group(1))
            if (
                qualifier in _ANCHOR_LOCATION_LEXICON
                and qualifier != anchor_qualifier
                and qualifier not in found
            ):
                found.append(qualifier)
    return tuple(found)


def _web_result_relevance_tier(
    *,
    result: _NormalizedWebResult,
    bound_entity_names: tuple[str, ...],
    anchor_qualifier: str | None,
) -> int:
    if len(result.corroborating_provider_versions) >= 2:
        return 0
    searchable = _normalized_web_identity(f"{result.title} {result.snippet}")
    best = 5
    for entity_name in bound_entity_names:
        stem = _org_name_stem(entity_name)
        full_hit = any(
            _web_identity_text_matches(form, searchable)
            for form in _web_identity_full_name_forms(entity_name)
        )
        if full_hit:
            if anchor_qualifier is not None and stem and stem in searchable:
                if anchor_qualifier in searchable:
                    return 1  # best possible, stop early
                other_branches = _evidence_branch_qualifiers(
                    org_stem=stem,
                    texts=(f"{result.title} {result.snippet}",),
                    anchor_qualifier=anchor_qualifier,
                )
                best = min(best, 3 if other_branches else 2)
            else:
                best = min(best, 2)
            continue
        if any(
            _web_identity_text_matches(form, searchable)
            for form in _web_identity_compact_aliases(entity_name)
        ):
            best = min(best, 4)
    return best


def _web_identity_domain_matches(entity_name: str, locator: str) -> bool:
    alias = _compact_company_alias(entity_name)
    if re.fullmatch(r"[\u3400-\u9fff]{2,8}", alias) is None:
        return False
    brand = "".join(lazy_pinyin(alias)).casefold()
    if len(brand) < 4:
        return False
    hostname = urlparse(locator).hostname or ""
    labels = tuple(
        _normalized_web_identity(label)
        for label in hostname.casefold().split(".")
        if label and label.casefold() != "www"
    )
    allowed_labels = {f"{brand}{suffix}" for suffix in _BRAND_DOMAIN_SUFFIXES}
    return bool(set(labels) & allowed_labels)


def _web_result_hits_bound_entity(
    *,
    bound_entity_names: tuple[str, ...],
    title: str,
    snippet: str,
) -> bool:
    # Only complete identity forms count: shared core fragments (e.g. 先进技术
    # across 中国科学院深圳先进技术研究院 vs the anchor) must not score as a
    # subject hit, so matching reuses the full _web_identity_forms output.
    searchable = _normalized_web_identity(f"{title} {snippet}")
    return any(
        _web_identity_text_matches(form, searchable)
        for entity_name in bound_entity_names
        for form in _web_identity_forms(entity_name)
    )


def _matched_bound_entity(
    *,
    request: LaneRequest,
    title: str,
    snippet: str,
    locator: str = "",
) -> tuple[str, str] | None:
    if not request.bound_entity_names:
        return None
    searchable = _normalized_web_identity(f"{title} {snippet}")
    matches = tuple(
        (entity_id, entity_name)
        for entity_id, entity_name in zip(
            request.bound_entity_ids,
            request.bound_entity_names,
            strict=True,
        )
        if not entity_id.startswith("web-handle:")
        and (
            any(
                _web_identity_text_matches(form, searchable)
                for form in _web_identity_forms(entity_name)
            )
            or _web_identity_domain_matches(entity_name, locator)
        )
    )
    return matches[0] if len(matches) == 1 else None


def _serving_reranker(request: RerankRequest) -> RerankProposal:
    def candidate_key(candidate: Any) -> tuple[float, str]:
        return (-candidate.raw_score, candidate.result_id)

    # List-style questions are recall-driven: the vector lane is the primary
    # local witness (exact/lexical lanes rarely fire for theme questions), so
    # its canonical candidates must stay in the same balanced lane as the Web
    # gap candidates instead of being pushed to the tail as mere neighbors.
    # Entity questions keep the conservative order: a Web gap that names the
    # target explicitly outranks a vector neighbor that merely resembles it.
    enumeration = any(
        marker in request.original_query
        for marker in _ENUMERATION_QUERY_MARKERS
    )

    mixed: list[Any] = []
    local: list[Any] = []
    web: list[Any] = []
    other: list[Any] = []
    for candidate in request.eligible_candidates:
        has_web = any(
            item.source_nature == "current_web" for item in candidate.evidence
        )
        has_strong_local = any(
            item.source_nature == "local"
            and item.lane
            in {
                "exact",
                "structured",
                "lexical",
                "relationship",
                "internal_reference",
            }
            for item in candidate.evidence
        ) or (
            enumeration
            and any(
                item.source_nature == "local" and item.lane == "vector"
                for item in candidate.evidence
            )
        )
        if has_web and has_strong_local:
            mixed.append(candidate)
        elif has_strong_local:
            local.append(candidate)
        elif has_web:
            web.append(candidate)
        else:
            other.append(candidate)

    mixed.sort(key=candidate_key)
    local.sort(key=candidate_key)
    web.sort(key=candidate_key)
    other.sort(key=candidate_key)
    balanced: list[Any] = []
    for index in range(max(len(local), len(web))):
        if index < len(local):
            balanced.append(local[index])
        if index < len(web):
            balanced.append(web[index])

    ordered = tuple(
        candidate.result_id
        for candidate in (*mixed, *balanced, *other)
    )
    return RerankProposal(
        decision_input_sha256=request.content_sha256,
        schema_version="canonical-v2-serving-rerank-v1",
        model_id="canonical-v2-deterministic-reranker-v1",
        prompt_version="canonical-v2-serving-rerank-v1",
        ordered_result_ids=ordered,
        rationale=(
            "Deterministic late selection preserves bounded local and current-Web recall."
        ),
    )


# --- Serving sufficiency + supplemental retrieval for person-criteria queries ---
#
# A person-criteria question (毕业于X 的企业家/创始人/…是谁) asks for PEOPLE, but
# the local release often holds only the companies (no founder/education fields)
# and one generic Web query returns industry news instead of the people. The
# ephemeral read already owns the sufficiency/supplemental machinery
# (knowledge_read._build_sufficiency/_run_supplemental); this region supplies the
# two serving callables that plug into it:
#
# * the sufficiency decider marks the planner-minted person part missing only
#   when no retained local/first-pass-Web evidence already covers the person
#   criteria, and hands per-turn context (covering items or company candidates)
#   to the supplemental search through a bounded plan-keyed store;
# * the supplemental search either re-binds covering evidence to the part (no
#   provider calls) or runs BOUNDED per-candidate dual-Web probes and returns
#   one aggregated evidence item, always inside SupplementalBudget so the budget
#   receipt validates downstream.
#
# Binding note: the read framework only accepts a "supported" part when the
# cited evidence claim bindings match the part's subject/predicate/requested
# value exactly, and `_apply_direct_item_constraints` requires a geography
# observation (predicate "geography", subject == object_id) whenever the query
# carries a protected city slot. A single claim binding satisfies both by
# anchoring the part on a question-scoped subject, mirroring the object_id, and
# using predicate "geography" with the city as requested value when a protected
# city is present.

_PERSON_CRITERIA_PART_PREFIX = "serving-person-criteria:"
_DISPLAYED_RELATION_PART_PREFIX = "serving-displayed-relation:"
_THEME_PART_PREFIX = "serving-theme:"
# Company-enumeration asks (供应商/厂商/企业/公司/厂家/品牌) whose retained
# candidates often lack direct theme evidence in their profiles
# (开普勒/安赛步 rank fine but say 人形机器人). One bounded per-candidate
# probe fetches the missing theme binding deterministically.
_THEME_COMPANY_ASK_MARKERS = ("供应商", "厂商", "企业", "公司", "厂家", "品牌", "推荐")
_THEME_SCAFFOLD_TOKENS = (
    "供应商",
    "厂商",
    "企业",
    "公司",
    "厂家",
    "品牌",
    "中国",
    "全国",
    "成熟",
    "推荐",
    "我想找",
    "我想",
    "目前",
    "哪些",
    "的",
    "我",
    "找",
    "一下",
    "有",
    "深圳",
    "广州",
    "上海",
    "北京",
)
_THEME_PROBE_MAX_CANDIDATES = 16
_THEME_COVERAGE_THRESHOLD = 0.5


def _theme_core(query: str) -> str | None:
    """The theme noun phrase of a company-enumeration question."""
    head = re.split(r"[，,。；;！!？?\n]", query, maxsplit=1)[0]
    core = head
    for token in _THEME_SCAFFOLD_TOKENS:
        core = core.replace(token, " ")
    core = " ".join(core.split())
    if len(core) < 2:
        return None
    return core


def _theme_bigram_coverage(core: str, text: str) -> float:
    normalized_core = _normalized_web_identity(core)
    if len(normalized_core) < 2:
        return 0.0
    normalized_text = _normalized_web_identity(text)
    bigrams = {
        normalized_core[index : index + 2]
        for index in range(len(normalized_core) - 1)
    }
    if not bigrams:
        return 0.0
    hits = sum(1 for bigram in bigrams if bigram in normalized_text)
    return hits / len(bigrams)


def _theme_material_part(query: str) -> MaterialQuestionPart | None:
    if not any(marker in query for marker in _ENUMERATION_QUERY_MARKERS):
        return None
    if not any(marker in query for marker in _THEME_COMPANY_ASK_MARKERS):
        return None
    core = _theme_core(query)
    if core is None:
        return None
    part_key = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    subject_id = f"{_THEME_PART_PREFIX}{part_key}"
    return MaterialQuestionPart(
        part_id=subject_id,
        text=query,
        subject_id=subject_id,
        predicate="theme_relevance",
        requested_value=core,
        material=True,
        answer_scoped=False,
    )


def _theme_evidence_covers(core: str, text: str) -> bool:
    return _theme_bigram_coverage(core, text) >= _THEME_COVERAGE_THRESHOLD
_PERSON_ROLE_MARKERS = ("创始人", "联合创始人", "创办人", "企业家")
_PROFESSOR_ROLE_MARKERS = ("教授", "老师")
# Industry nouns that sharpen a constraint-seeded discovery query
# ("早稻田 深圳 机器人 创始人" beats "早稻田 深圳 创始人" by pages); only the
# first term found in the question is appended, verification stays per-company.
_DISCOVERY_SCOPE_TERMS = (
    "具身智能",
    "机器人",
    "无人机",
    "传感器",
    "半导体",
    "芯片",
    "激光",
    "新能源",
    "汽车",
    "医疗",
    "生物",
    "材料",
    "人工智能",
    "软件",
)
# Founding teams are described with many wordings (创始人/创始团队/由…创立/
# 联合创办); the acceptance family must cover the whole expression class, not
# just the literal 创始人 marker.
_FOUNDER_TEXT_MARKERS = (
    "创始人",
    "联合创始人",
    "创办人",
    "创始团队",
    "联合创始",
    "参与创立",
    "联合创办",
    "创立",
    "创办",
    "企业家",
)
# Displayed-set relation follow-ups whose generic Web pass can leave displayed
# companies unbound; each maps to a bounded per-company probe.
_RELATION_FRAME_PREDICATES = (
    "headquarters_city",
    "registered_address",
    "office_city",
    "branch_city",
    "product_capability",
)
_DISPLAYED_COMPANY_ID_PREFIXES = ("company:", "company-", "web-handle:")
# Mirror the protected-slot geography cities in knowledge_read so the part's
# geography binding observes exactly what the slot will require.
_SUPPLEMENTAL_GEOGRAPHY_CITIES = ("深圳", "广州", "上海", "北京")
_SUPPLEMENTAL_WEB_SOURCE_NATURE = "supplemental_web"
# Candidate window for enumeration (list-style) queries; wide enough to keep
# vector ranks 10-25 inside the fused retention.
_ENUMERATION_CANDIDATE_WINDOW = 48
# List-style markers mirroring the answer selector's enumeration family; a
# fresh list query carries no enumeration_context, so the planner keys on the
# query text itself.
_ENUMERATION_QUERY_MARKERS = (
    "哪些",
    "谁",
    "多少",
    "几个",
    "几种",
    "列出",
    "所有",
    "分别",
    "推荐",
    "厂商",
    "供应商",
)
# Probes cover the whole typical displayed set (the answer usually shows six
# or fewer members); a smaller cap starves later members of the set even when
# the provider holds their evidence.
_SUPPLEMENTAL_PROBE_MAX_COMPANIES = 6
_SUPPLEMENTAL_PROBE_COST_UNITS = 0.5
_SUPPLEMENTAL_CONTEXT_CAPACITY = 256
_EDUCATION_PATTERN = re.compile(r"毕业于\s*([一-鿿A-Za-z·]{2,20})")
_EDUCATION_TRAILING_STOPWORDS = (
    "，",
    "。",
    "；",
    "、",
    "且",
    "而",
    "在",
    "的",
    "是",
    "有",
)
_ALUMNI_PATTERN = re.compile(
    r"([一-鿿A-Za-z·]{2,12}?(?:大学|学院|研究院|研究所))(?=\s*(?:毕业|校友))"
)


@dataclass(frozen=True, slots=True)
class _PersonCriteria:
    constraint: str | None
    founder_role: bool
    professor_role: bool


@dataclass(frozen=True, slots=True)
class _RelationProbeSpec:
    part: MaterialQuestionPart
    entity_name: str
    frame: _QuestionFrame
    term: str


@dataclass(frozen=True, slots=True)
class _ThemeProbeSpec:
    canonical_id: str
    entity_name: str
    theme_core: str


@dataclass(frozen=True, slots=True)
class _ServingSupplementalContext:
    question: str
    coverage_items: tuple[EvidenceItem, ...]
    person_part: MaterialQuestionPart | None
    person_constraint: str | None
    person_probe_companies: tuple[str, ...]
    person_role_word: str
    person_geography: str | None
    person_scope_term: str | None
    relation_probes: tuple[_RelationProbeSpec, ...]
    theme_part: MaterialQuestionPart | None
    theme_probes: tuple[_ThemeProbeSpec, ...]


def _education_constraint(query: str) -> str | None:
    match = _EDUCATION_PATTERN.search(query)
    if match is not None:
        value = match.group(1)
        cut = min(
            (
                index
                for token in _EDUCATION_TRAILING_STOPWORDS
                if (index := value.find(token)) > 0
            ),
            default=len(value),
        )
        value = value[:cut]
        if len(value) >= 2:
            return value
    alumni = _ALUMNI_PATTERN.search(query)
    if alumni is not None:
        return alumni.group(1)
    return None


def _person_criteria(query: str) -> _PersonCriteria | None:
    founder_role = any(marker in query for marker in _PERSON_ROLE_MARKERS)
    constraint = _education_constraint(query)
    # Only a role or an education constraint gives the probes something to
    # search for; a bare "是谁/有谁" asks about a named or bound subject and is
    # served by the ordinary named/profile path, not by per-company probes.
    if not (founder_role or constraint is not None):
        return None
    professor_role = not founder_role and any(
        marker in query for marker in _PROFESSOR_ROLE_MARKERS
    )
    return _PersonCriteria(
        constraint=constraint,
        founder_role=founder_role,
        professor_role=professor_role,
    )


def _supplemental_geography_value(query: str) -> str | None:
    organization_name = _explicit_organization_name(query)
    return next(
        (
            city
            for city in _SUPPLEMENTAL_GEOGRAPHY_CITIES
            if city in query
            and not (organization_name is not None and city in organization_name)
        ),
        None,
    )


def _person_criteria_material_part(query: str) -> MaterialQuestionPart | None:
    criteria = _person_criteria(query)
    if criteria is None:
        return None
    part_key = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    subject_id = f"{_PERSON_CRITERIA_PART_PREFIX}{part_key}"
    city = _supplemental_geography_value(query)
    if city is not None:
        predicate = "geography"
        requested_value = city
    elif criteria.constraint is not None:
        predicate = "person_criteria"
        requested_value = criteria.constraint
    else:
        predicate = "person_criteria"
        requested_value = "founder"
    return MaterialQuestionPart(
        part_id=subject_id,
        text=query,
        subject_id=subject_id,
        predicate=predicate,
        requested_value=requested_value,
        material=True,
        answer_scoped=False,
    )


def _displayed_relation_material_parts(
    request: QueryPlanningRequest,
) -> tuple[MaterialQuestionPart, ...]:
    """One material part per displayed company for relation follow-ups.

    City-bound relation predicates (总部/注册地址/分公司/办公室) use the
    geography binding form so one claim binding satisfies both the sufficiency
    direct-binding rule and the protected geography slot; product-capability
    queries carry no protected city slot and bind the capability value instead.
    """
    frame = _question_frame(request.original_query)
    if frame.predicate not in _RELATION_FRAME_PREDICATES:
        return ()
    if frame.predicate == "product_capability":
        if frame.logic != "all" or not frame.requested_values:
            return ()
        predicate = "product_capability_evidence"
        requested_value = " + ".join(frame.requested_values)
    else:
        if not frame.requested_values:
            return ()
        predicate = "geography"
        requested_value = frame.requested_values[0]
    parts: list[MaterialQuestionPart] = []
    for entity_id, entity_name in zip(
        request.displayed_entity_ids,
        request.displayed_entity_names,
        strict=True,
    ):
        if not entity_id.startswith(_DISPLAYED_COMPANY_ID_PREFIXES):
            continue
        normalized_name = entity_name.strip()
        if not normalized_name:
            continue
        part_key = hashlib.sha256(
            f"{request.original_query}|{entity_id}".encode("utf-8")
        ).hexdigest()[:16]
        parts.append(
            MaterialQuestionPart(
                part_id=f"{_DISPLAYED_RELATION_PART_PREFIX}{part_key}",
                text=normalized_name,
                subject_id=entity_id,
                predicate=predicate,
                requested_value=requested_value,
                material=True,
                answer_scoped=False,
            )
        )
    return tuple(parts[:_SUPPLEMENTAL_PROBE_MAX_COMPANIES])


def _relation_probe_term(frame: _QuestionFrame) -> str:
    if frame.predicate == "product_capability":
        return " ".join(frame.requested_values)
    return {
        "headquarters_city": "总部",
        "registered_address": "注册地址",
        "office_city": "办公室",
        "branch_city": "分公司",
    }[frame.predicate]


def _part_bound_evidence(item: EvidenceItem, part: MaterialQuestionPart) -> bool:
    binding = item.claim_binding
    return (
        binding is not None
        and binding.subject_id == part.subject_id
        and binding.predicate == part.predicate
        and (
            binding.value == part.requested_value
            or binding.value.startswith(f"{part.requested_value}:")
        )
    )


def _has_founder_relationship(item: EvidenceItem) -> bool:
    try:
        payload = json.loads(item.snippet)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    relationship = payload.get("_relationship")
    if not isinstance(relationship, dict):
        return False
    if str(relationship.get("relationship_type") or "") != "professor_company_role":
        return False
    return any(
        str(role).strip().casefold() == "founder"
        for role in relationship.get("roles", ())
    )


def _payload_display_names(item: EvidenceItem) -> tuple[str, ...]:
    try:
        payload = json.loads(item.snippet)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    return tuple(
        value.strip()
        for key in ("name", "canonical_name_zh", "title")
        if isinstance((value := payload.get(key)), str) and value.strip()
    )


def _covers_person_criteria(
    item: EvidenceItem,
    *,
    criteria: _PersonCriteria,
    query: str,
) -> bool:
    text = item.snippet
    constraint_met = criteria.constraint is None or criteria.constraint in text
    if criteria.founder_role:
        return constraint_met and (
            _has_founder_relationship(item)
            or any(marker in text for marker in _FOUNDER_TEXT_MARKERS)
        )
    if criteria.professor_role:
        return constraint_met and (
            item.domain == "professor"
            or any(marker in text for marker in _PROFESSOR_ROLE_MARKERS)
        )
    if criteria.constraint is not None:
        return constraint_met and (
            item.domain == "professor"
            or _has_founder_relationship(item)
            or any(marker in text for marker in _FOUNDER_TEXT_MARKERS)
        )
    return any(
        len(name) >= 2 and name in query for name in _payload_display_names(item)
    )


def _company_name_from_item(item: EvidenceItem) -> str | None:
    for name in _payload_display_names(item):
        if len(name) >= 4:
            return name
    match = COMPANY_NAME_PATTERN.search(item.snippet)
    if match is not None:
        return match.group(1)
    return None


def _company_probe_candidates(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    local_names: list[str] = []
    web_names: list[str] = []
    for item in items:
        if item.domain != "company":
            continue
        name = _company_name_from_item(item)
        if name is None:
            continue
        bucket = local_names if item.source_nature != "current_web" else web_names
        if name not in local_names and name not in web_names:
            bucket.append(name)
    return tuple((*local_names, *web_names))


def _company_names_from_web_text(text: str) -> tuple[str, ...]:
    """Legal company names mentioned in raw web text.

    The name regex greedily rides over leading verbs/particles in Han runs
    ("走进位于深圳南山智园的优必选科技股份有限公司"), so captures are cut at
    the last scaffolding separator before acceptance.
    """
    names: list[str] = []
    for match in COMPANY_NAME_PATTERN.finditer(text):
        name = match.group(1)
        for separator in ("的", "位于", "走进", "来自", "由", "是", "在", "与", "创立"):
            if separator in name:
                name = name.rsplit(separator, 1)[-1]
        if len(name) >= 4 and name not in names:
            names.append(name)
    return tuple(names)


class _SupplementalContextStore:
    """Bounded plan-keyed handoff from the sufficiency decider to the search."""

    def __init__(self, capacity: int = _SUPPLEMENTAL_CONTEXT_CAPACITY) -> None:
        self._capacity = capacity
        self._lock = Lock()
        self._entries: dict[str, list[_ServingSupplementalContext]] = {}

    def record(self, plan_id: str, context: _ServingSupplementalContext) -> None:
        with self._lock:
            entries = self._entries.setdefault(plan_id, [])
            entries.append(context)
            while len(self._entries) > self._capacity:
                oldest = next(iter(self._entries))
                self._entries.pop(oldest, None)

    def pop(self, plan_id: str) -> _ServingSupplementalContext | None:
        with self._lock:
            entries = self._entries.get(plan_id)
            if not entries:
                self._entries.pop(plan_id, None)
                return None
            context = entries.pop(0)
            if not entries:
                self._entries.pop(plan_id, None)
            return context


def _serving_sufficiency_decider(
    *,
    context_store: _SupplementalContextStore,
) -> Callable[[SufficiencyDecisionRequest], SufficiencyProposal | None]:
    def decide(request: SufficiencyDecisionRequest) -> SufficiencyProposal | None:
        person_parts = tuple(
            part
            for part in request.material_parts
            if part.part_id.startswith(_PERSON_CRITERIA_PART_PREFIX)
        )
        relation_parts = tuple(
            part
            for part in request.material_parts
            if part.part_id.startswith(_DISPLAYED_RELATION_PART_PREFIX)
        )
        theme_parts = tuple(
            part
            for part in request.material_parts
            if part.part_id.startswith(_THEME_PART_PREFIX)
        )
        if not person_parts and not relation_parts and not theme_parts:
            return None
        proposals: list[MaterialPartProposal] = []
        coverage_items: tuple[EvidenceItem, ...] = ()
        person_probe_companies: tuple[str, ...] = ()
        person_constraint: str | None = None
        relation_probes: list[_RelationProbeSpec] = []
        theme_probes: list[_ThemeProbeSpec] = []
        relation_frame = (
            _question_frame(request.original_query) if relation_parts else None
        )
        for part in (*person_parts, *relation_parts, *theme_parts):
            bound = tuple(
                item.evidence_id
                for item in request.evidence
                if _part_bound_evidence(item, part)
            )
            if bound:
                proposals.append(
                    MaterialPartProposal(
                        part_id=part.part_id,
                        outcome="supported",
                        evidence_ids=bound,
                        rationale=(
                            "Directly bound evidence is present in the retained result."
                        ),
                        uncertainty="low",
                        confidence=0.9,
                    )
                )
                continue
            if part in person_parts:
                criteria = _person_criteria(request.original_query) or _PersonCriteria(
                    constraint=None,
                    founder_role=True,
                    professor_role=False,
                )
                person_constraint = criteria.constraint
                covering = tuple(
                    item
                    for item in request.evidence
                    if _covers_person_criteria(
                        item,
                        criteria=criteria,
                        query=request.original_query,
                    )
                )
                if covering:
                    coverage_items = covering[:_SUPPLEMENTAL_PROBE_MAX_COMPANIES]
                    rationale = (
                        "Retained evidence already names the person subject; it is "
                        "being rebound to the person-criteria part."
                    )
                else:
                    person_probe_companies = _company_probe_candidates(
                        request.evidence
                    )[:_SUPPLEMENTAL_PROBE_MAX_COMPANIES]
                    rationale = (
                        "No retained evidence names a person matching the question."
                    )
                proposals.append(
                    MaterialPartProposal(
                        part_id=part.part_id,
                        outcome="missing",
                        evidence_ids=(),
                        rationale=rationale,
                        uncertainty="high",
                        confidence=0.2,
                    )
                )
            elif part in relation_parts:
                frame = cast(_QuestionFrame, relation_frame)
                relation_probes.append(
                    _RelationProbeSpec(
                        part=part,
                        entity_name=part.text,
                        frame=frame,
                        term=_relation_probe_term(frame),
                    )
                )
                proposals.append(
                    MaterialPartProposal(
                        part_id=part.part_id,
                        outcome="missing",
                        evidence_ids=(),
                        rationale=(
                            "No retained evidence directly binds this displayed "
                            "company to the requested relation."
                        ),
                        uncertainty="high",
                        confidence=0.2,
                    )
                )
            else:
                core = part.requested_value
                company_candidates: list[tuple[str, str, str]] = []
                seen_candidate_ids: set[str] = set()
                seen_web_names: set[str] = set()
                covered_ids: set[str] = set()
                for item in request.evidence:
                    if item.domain != "company":
                        continue
                    object_id = item.object_id
                    if (
                        not object_id.startswith(("company:", "company-"))
                        or object_id in seen_candidate_ids
                    ):
                        continue
                    seen_candidate_ids.add(object_id)
                    names = _payload_display_names(item)
                    entity_name = names[0] if names else object_id
                    seen_web_names.add(entity_name)
                    company_candidates.append((object_id, entity_name, item.snippet))
                    if _theme_evidence_covers(
                        core, f"{entity_name} {item.snippet}"
                    ):
                        covered_ids.add(object_id)
                # Web-only suppliers (九号 in brand listicles, 深南 in a
                # top-100 ranking) never reach the probes through local
                # object ids; extract company names from current-web
                # evidence so they can be verified individually too.
                for item in request.evidence:
                    if (
                        item.domain != "company"
                        or item.source_nature != "current_web"
                    ):
                        continue
                    for name in _company_names_from_web_text(item.snippet):
                        if name in seen_web_names:
                            continue
                        seen_web_names.add(name)
                        candidate_id = f"web-name:{name}"
                        company_candidates.append(
                            (candidate_id, name, item.snippet)
                        )
                        if _theme_evidence_covers(
                            core, f"{name} {item.snippet}"
                        ):
                            covered_ids.add(candidate_id)
                uncovered_candidates = [
                    (object_id, entity_name, snippet)
                    for object_id, entity_name, snippet in company_candidates
                    if not (
                        object_id.startswith(("company:", "company-"))
                        and object_id in covered_ids
                    )
                ]
                # Theme-partial candidates verify first so unrelated names
                # cannot consume the probe ceiling (stable within a tier);
                # web-extracted names always probe (their snippet can only
                # mention, not bind, the company to the theme).
                uncovered_candidates.sort(
                    key=lambda candidate: -_theme_bigram_coverage(
                        core, f"{candidate[1]} {candidate[2]}"
                    )
                )
                if not uncovered_candidates:
                    covering_id = next(
                        (
                            object_id
                            for object_id, _, _ in company_candidates
                            if object_id in covered_ids
                        ),
                        None,
                    )
                    coverage_items = tuple(
                        item
                        for item in request.evidence
                        if covering_id is not None and item.object_id == covering_id
                    )[:_SUPPLEMENTAL_PROBE_MAX_COMPANIES]
                    rationale = (
                        "Retained evidence already binds candidates to the theme; "
                        "one is being rebound to the theme part."
                    )
                else:
                    # Verify each uncovered candidate individually: one covered
                    # company must not shield the rest from verification.
                    theme_probes.extend(
                        _ThemeProbeSpec(
                            canonical_id=object_id,
                            entity_name=entity_name,
                            theme_core=core,
                        )
                        for object_id, entity_name, _ in uncovered_candidates[
                            :_THEME_PROBE_MAX_CANDIDATES
                        ]
                    )
                    rationale = (
                        "Some enumeration candidates lack direct theme evidence."
                    )
                proposals.append(
                    MaterialPartProposal(
                        part_id=part.part_id,
                        # The read framework only accepts "supported" for
                        # part-shaped bindings, so coverage re-binds in the
                        # supplemental pass; the decider always marks missing.
                        outcome="missing",
                        evidence_ids=(),
                        rationale=rationale,
                        uncertainty="high" if uncovered_candidates else "low",
                        confidence=0.2 if uncovered_candidates else 0.9,
                    )
                )
        person_role_word = "企业家"
        if person_parts:
            person_criteria = _person_criteria(request.original_query)
            if person_criteria is None or person_criteria.founder_role:
                person_role_word = "创始人"
            elif person_criteria.professor_role:
                person_role_word = "教授"
        context_store.record(
            request.plan_id,
            _ServingSupplementalContext(
                question=request.original_query,
                coverage_items=coverage_items,
                person_part=person_parts[0] if person_parts else None,
                person_constraint=person_constraint,
                person_probe_companies=person_probe_companies,
                person_role_word=person_role_word,
                person_geography=(
                    person_parts[0].requested_value
                    if person_parts and person_parts[0].predicate == "geography"
                    else None
                ),
                person_scope_term=next(
                    (
                        term
                        for term in _DISCOVERY_SCOPE_TERMS
                        if term in request.original_query
                    ),
                    None,
                ),
                relation_probes=tuple(
                    relation_probes[:_SUPPLEMENTAL_PROBE_MAX_COMPANIES]
                ),
                theme_part=theme_parts[0] if theme_parts else None,
                theme_probes=tuple(theme_probes),
            ),
        )
        return SufficiencyProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="canonical-v2-serving-sufficiency-v1",
            decision_id=f"sufficiency:serving:{request.plan_id}",
            parts=tuple(proposals),
        )

    return decide


def _rebind_person_evidence(
    item: EvidenceItem,
    part: MaterialQuestionPart,
) -> EvidenceItem:
    web_derived = item.source_nature == "current_web"
    snippet = item.snippet
    if web_derived:
        title, _, remainder = item.snippet.partition("：")
        snippet = json.dumps(
            {
                "name": title.strip() or item.source_locator,
                "profile_summary": (remainder or item.snippet).strip(),
            },
            ensure_ascii=False,
        )
    return EvidenceItem(
        evidence_id=(
            f"{part.part_id}:rebind:"
            f"{hashlib.sha256(item.evidence_id.encode()).hexdigest()[:16]}"
        ),
        object_id=part.subject_id,
        domain=item.domain if item.domain in _PUBLIC_DOMAINS else "company",
        lane="supplemental",
        source_nature=(
            _SUPPLEMENTAL_WEB_SOURCE_NATURE if web_derived else item.source_nature
        ),
        source_locator=item.source_locator,
        snippet=snippet,
        score=item.score,
        source_authority=item.source_authority,
        observed_at=item.observed_at,
        claim_binding=EvidenceClaimBinding(
            subject_id=part.subject_id,
            predicate=part.predicate,
            value=part.requested_value,
            status="observed",
        ),
        web_snapshot=item.web_snapshot,
    )


def _person_evidence_match(
    result: _NormalizedWebResult,
    *,
    company: str,
    constraint: str | None,
) -> bool:
    text = f"{result.title} {result.snippet}"
    searchable = _normalized_web_identity(text)
    # Person-name matching is plain containment: the brand-context marker
    # rule (_web_identity_text_matches) is tuned for company names and
    # misses person bios where the name stands alone (T13).
    if not any(form in searchable for form in _web_identity_forms(company)):
        return False
    if constraint is not None:
        # Education-constrained person queries: the person name and the
        # education constraint co-occurring in the same hit is enough.
        # Requiring a founder marker in the same snippet misses pages that
        # state the school without the role word (T13 早稻田企业家 returned
        # "未找到" for exactly this reason); the LLM probe judge backstops
        # any relaxed accept.
        return constraint in text
    return any(marker in text for marker in _FOUNDER_TEXT_MARKERS)


def _person_probe_evidence_item(
    *,
    part: MaterialQuestionPart,
    findings: tuple[tuple[str, _NormalizedWebResult], ...],
    clock: Callable[[], datetime],
    max_snapshot_bytes: int,
) -> EvidenceItem:
    observed_at = clock().astimezone(timezone.utc)
    name = "、".join(company for company, _ in findings)
    summary = "；".join(
        f"{company}：{(hit.snippet or hit.title).strip()[:160]}"
        for company, hit in findings
    )
    snippet = json.dumps(
        {"name": name, "profile_summary": summary},
        ensure_ascii=False,
    )
    first_hit = findings[0][1]
    snapshot_content = json.dumps(
        {
            "title": name,
            "link": first_hit.url,
            "snippet": summary,
            "summary": summary,
            "primary_provider_version": first_hit.primary_provider_version,
            "corroborating_provider_versions": sorted(
                {
                    version
                    for _, hit in findings
                    for version in hit.corroborating_provider_versions
                }
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")[:max_snapshot_bytes]
    snapshot_sha256 = hashlib.sha256(snapshot_content).hexdigest()
    snapshot_id = f"web-snapshot:sha256:{snapshot_sha256}"
    evidence_identity = {
        "part": part.part_id,
        "locators": tuple(hit.url for _, hit in findings),
        "snapshot": snapshot_id,
    }
    return EvidenceItem(
        evidence_id=f"web-evidence:sha256:{_canonical_sha256(evidence_identity)}",
        object_id=part.subject_id,
        domain="company",
        lane="supplemental",
        source_nature=_SUPPLEMENTAL_WEB_SOURCE_NATURE,
        source_locator=first_hit.url,
        snippet=snippet,
        score=1.0,
        source_authority="web_search",
        observed_at=observed_at,
        claim_binding=EvidenceClaimBinding(
            subject_id=part.subject_id,
            predicate=part.predicate,
            value=part.requested_value,
            status="observed",
        ),
        web_snapshot=WebEvidenceSnapshot(
            snapshot_id=snapshot_id,
            content_sha256=snapshot_sha256,
            retrieved_at=observed_at,
            byte_length=len(snapshot_content),
        ),
    )


def _relation_evidence_match(
    result: _NormalizedWebResult,
    *,
    spec: _RelationProbeSpec,
) -> bool:
    text = f"{result.title} {result.snippet}"
    searchable = _normalized_web_identity(text)
    if not any(
        _web_identity_text_matches(form, searchable)
        for form in _web_identity_forms(spec.entity_name)
    ):
        return False
    expected_predicate = (
        "product_capability_evidence"
        if spec.frame.predicate == "product_capability"
        else spec.frame.predicate
    )
    predicate, value = _web_claim_semantics(
        frame=spec.frame,
        title=result.title,
        snippet=result.snippet,
        fallback_value="",
    )
    return predicate == expected_predicate and value == spec.part.requested_value


def _theme_evidence_match(
    result: _NormalizedWebResult,
    *,
    company: str,
    core: str,
) -> bool:
    text = f"{result.title} {result.snippet}"
    searchable = _normalized_web_identity(text)
    if not any(
        _web_identity_text_matches(form, searchable)
        for form in _web_identity_forms(company)
    ):
        return False
    return _theme_evidence_covers(core, text)


def _probe_rule_hit(
    *,
    kind: Literal["person", "relation", "theme"],
    entity_name: str,
    semantics: Mapping[str, Any],
    result: _NormalizedWebResult,
) -> bool:
    """The deterministic zero-cost pre-filter for one probe result."""
    if kind == "person":
        return _person_evidence_match(
            result,
            company=entity_name,
            constraint=cast("str | None", semantics.get("constraint")),
        )
    if kind == "relation":
        return _relation_evidence_match(
            result,
            spec=cast(_RelationProbeSpec, semantics["spec"]),
        )
    return _theme_evidence_match(
        result,
        company=entity_name,
        core=cast(str, semantics["core"]),
    )


def _render_probe_hit(
    *,
    entity_name: str,
    semantics: Mapping[str, Any],
    result: _NormalizedWebResult,
) -> str:
    # ``default=str`` keeps the relation spec dataclass renderable.
    return (
        f"实体：{entity_name}\n"
        f"语义：{json.dumps(semantics, ensure_ascii=False, default=str)}\n"
        f"标题：{result.title}\n"
        f"摘要：{result.snippet}"
    )


def _judge_failed(judge: Any) -> bool:
    """True when the judge's latest batch degraded to fail-open defaults."""
    outcome = getattr(judge, "last_outcome", "ok")
    return isinstance(outcome, str) and "fail_open" in outcome


def _accept_probe_hit(
    *,
    judge: Any | None,
    kind: Literal["person", "relation", "theme"],
    question: str,
    entity_name: str,
    semantics: Mapping[str, Any],
    result: _NormalizedWebResult,
) -> bool:
    """Rule-first probe acceptance with an LLM rescue for rule misses.

    A rule hit short-circuits without any LLM call, and without a judge the
    rule result stands. A rule miss is judged by the LLM, but only a
    successful ("ok") judgment can recover it: when the judge degraded to
    fail-open defaults (``last_outcome`` marked ``*_fail_open``), the rule
    result is kept, because the harness's fail-open defaults accept
    everything and would admit exactly the noise the rules rejected.
    """
    rule_hit = _probe_rule_hit(
        kind=kind,
        entity_name=entity_name,
        semantics=semantics,
        result=result,
    )
    if rule_hit or judge is None:
        return rule_hit
    judgments = judge.judge_batch(
        kind="probe_accept",
        question=question,
        items={
            "hit-1": _render_probe_hit(
                entity_name=entity_name,
                semantics=semantics,
                result=result,
            )
        },
    )
    if _judge_failed(judge):
        return rule_hit
    if not judgments:
        return False
    return bool(getattr(judgments[0], "accept", False))


def _select_probe_hit(
    *,
    judge: Any | None,
    kind: Literal["person", "relation", "theme"],
    question: str,
    entity_name: str,
    semantics: Mapping[str, Any],
    results: tuple[_NormalizedWebResult, ...],
) -> _NormalizedWebResult | None:
    """Pick one job's accepted probe result: batch-then-pick.

    The first rule hit in result order wins outright and never spends an
    LLM call. Only when no result rule-matches are the misses rendered and
    judged in ONE batched ``judge_batch`` call; the first accepted entry in
    original result order wins. A failed batch (``*_fail_open``) accepts
    nothing, keeping the deterministic rule outcome.
    """
    misses: list[_NormalizedWebResult] = []
    for result in results:
        if _probe_rule_hit(
            kind=kind,
            entity_name=entity_name,
            semantics=semantics,
            result=result,
        ):
            return result
        misses.append(result)
    if judge is None or not misses:
        return None
    item_ids = tuple(f"hit-{index}" for index in range(1, len(misses) + 1))
    judgments = judge.judge_batch(
        kind="probe_accept",
        question=question,
        items={
            item_id: _render_probe_hit(
                entity_name=entity_name,
                semantics=semantics,
                result=result,
            )
            for item_id, result in zip(item_ids, misses, strict=True)
        },
    )
    if _judge_failed(judge):
        return None
    accepted_ids = {
        str(getattr(judgment, "item_id", ""))
        for judgment in judgments
        if bool(getattr(judgment, "accept", False))
    }
    for item_id, result in zip(item_ids, misses, strict=True):
        if item_id in accepted_ids:
            return result
    return None


def _theme_probe_entity_form(entity_name: str) -> str:
    """The probe-query form of a candidate name.

    Deliberately NOT the aggressive brand split: "九号" collides with Ninebot
    while "九号机器人" pins the right company, so only the legal suffix and
    city prefix come off.
    """
    name = re.sub(r"（[^）]*）|\([^)]*\)", "", entity_name.strip().strip('"'))
    name = re.sub(r"(?:股份)?有限公司$", "", name)
    name = re.sub(r"^[\u4e00-\u9fff]{2,4}市", "", name, count=1)
    return name if len(name) >= 2 else entity_name


def _theme_probe_evidence_item(
    *,
    spec: _ThemeProbeSpec,
    hit: _NormalizedWebResult,
    clock: Callable[[], datetime],
    max_snapshot_bytes: int,
) -> EvidenceItem:
    """The fetched theme binding for one enumeration candidate.

    The item's subject is the candidate's canonical id, so the candidate's
    claim gains the theme relevance its profile lacked (this is what lets
    开普勒-style companies survive relevance filtering).
    """
    observed_at = clock().astimezone(timezone.utc)
    snippet = json.dumps(
        {
            "name": spec.entity_name,
            "profile_summary": (hit.snippet or hit.title).strip()[:240],
        },
        ensure_ascii=False,
    )
    snapshot_content = json.dumps(
        {
            "title": hit.title,
            "link": hit.url,
            "snippet": hit.snippet,
            "summary": hit.summary,
            "primary_provider_version": hit.primary_provider_version,
            "corroborating_provider_versions": list(
                hit.corroborating_provider_versions
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")[:max_snapshot_bytes]
    snapshot_sha256 = hashlib.sha256(snapshot_content).hexdigest()
    snapshot_id = f"web-snapshot:sha256:{snapshot_sha256}"
    evidence_identity = {
        "theme": spec.theme_core,
        "candidate": spec.canonical_id,
        "locator": hit.url,
        "snapshot": snapshot_id,
    }
    return EvidenceItem(
        evidence_id=f"web-evidence:sha256:{_canonical_sha256(evidence_identity)}",
        object_id=spec.canonical_id,
        domain="company",
        lane="supplemental",
        source_nature=_SUPPLEMENTAL_WEB_SOURCE_NATURE,
        source_locator=hit.url,
        snippet=snippet,
        score=1.0,
        source_authority="web_search",
        observed_at=observed_at,
        claim_binding=EvidenceClaimBinding(
            subject_id=spec.canonical_id,
            predicate="theme_relevance",
            value=spec.theme_core,
            status="observed",
        ),
        web_snapshot=WebEvidenceSnapshot(
            snapshot_id=snapshot_id,
            content_sha256=snapshot_sha256,
            retrieved_at=observed_at,
            byte_length=len(snapshot_content),
        ),
    )


def _relation_probe_evidence_item(
    *,
    spec: _RelationProbeSpec,
    hit: _NormalizedWebResult,
    clock: Callable[[], datetime],
    max_snapshot_bytes: int,
) -> EvidenceItem:
    observed_at = clock().astimezone(timezone.utc)
    snippet = json.dumps(
        {
            "name": spec.entity_name,
            "profile_summary": (hit.snippet or hit.title).strip()[:240],
        },
        ensure_ascii=False,
    )
    snapshot_content = json.dumps(
        {
            "title": hit.title,
            "link": hit.url,
            "snippet": hit.snippet,
            "summary": hit.summary,
            "primary_provider_version": hit.primary_provider_version,
            "corroborating_provider_versions": list(
                hit.corroborating_provider_versions
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")[:max_snapshot_bytes]
    snapshot_sha256 = hashlib.sha256(snapshot_content).hexdigest()
    snapshot_id = f"web-snapshot:sha256:{snapshot_sha256}"
    evidence_identity = {
        "part": spec.part.part_id,
        "locator": hit.url,
        "snapshot": snapshot_id,
    }
    return EvidenceItem(
        evidence_id=f"web-evidence:sha256:{_canonical_sha256(evidence_identity)}",
        object_id=spec.part.subject_id,
        domain="company",
        lane="supplemental",
        source_nature=_SUPPLEMENTAL_WEB_SOURCE_NATURE,
        source_locator=hit.url,
        snippet=snippet,
        score=1.0,
        source_authority="web_search",
        observed_at=observed_at,
        claim_binding=EvidenceClaimBinding(
            subject_id=spec.part.subject_id,
            predicate=spec.part.predicate,
            value=spec.part.requested_value,
            status="observed",
        ),
        web_snapshot=WebEvidenceSnapshot(
            snapshot_id=snapshot_id,
            content_sha256=snapshot_sha256,
            retrieved_at=observed_at,
            byte_length=len(snapshot_content),
        ),
    )


def _serving_supplemental_search(
    *,
    context_store: _SupplementalContextStore,
    probe: Callable[[str], tuple[_NormalizedWebResult, ...]],
    budget: SupplementalBudget,
    clock: Callable[[], datetime],
    max_snapshot_bytes: int,
    judge: Any | None = None,
) -> Callable[[SupplementalRequest], SupplementalLaneResult]:
    def search(request: SupplementalRequest) -> SupplementalLaneResult:
        started_at = monotonic()
        context = context_store.pop(request.plan_id)
        if context is None:
            return SupplementalLaneResult(
                items=(), elapsed_ms=0, cost_units=0.0, retryable=False
            )
        coverage_part = (
            context.person_part
            if context.person_part is not None
            else context.theme_part
        )
        if context.coverage_items and coverage_part is not None:
            rebound_items = tuple(
                _rebind_person_evidence(item, coverage_part)
                for item in context.coverage_items
            )
            return SupplementalLaneResult(
                items=rebound_items,
                elapsed_ms=int((monotonic() - started_at) * 1_000),
                cost_units=0.0,
                retryable=False,
            )
        person_findings: list[tuple[str, _NormalizedWebResult]] = []
        relation_findings: list[tuple[_RelationProbeSpec, _NormalizedWebResult]] = []
        theme_findings: list[tuple[_ThemeProbeSpec, _NormalizedWebResult]] = []
        discovery_cost = 0.0
        discovery_names: tuple[str, ...] = ()
        if (
            context.person_part is not None
            and context.person_constraint is not None
        ):
            # Constraint-seeded discovery: the retained candidates (local lanes
            # and the generic first-pass Web) often miss the companies that
            # actually carry the constraint, so one criteria-shaped query
            # ("早稻田 深圳 创始人") seeds them. Hits whose text already binds
            # a company to the founder/education criteria become findings
            # immediately; the rest join the per-company verification probes.
            discovery_query = " ".join(
                value
                for value in (
                    context.person_constraint,
                    context.person_geography,
                    context.person_scope_term,
                    context.person_role_word,
                )
                if value
            )
            discovery_cost = _SUPPLEMENTAL_PROBE_COST_UNITS
            try:
                discovery_results = probe(discovery_query)
            except Exception:  # noqa: BLE001 - discovery degrades like probes
                discovery_results = ()
            ordered_names: list[str] = []
            for result in discovery_results:
                for name in _company_names_from_web_text(
                    f"{result.title} {result.snippet}"
                ):
                    if name in ordered_names:
                        continue
                    ordered_names.append(name)
                    if _person_evidence_match(
                        result,
                        company=name,
                        constraint=context.person_constraint,
                    ):
                        person_findings.append((name, result))
            discovery_names = tuple(ordered_names)
        finding_names = {name for name, _ in person_findings}
        person_jobs = tuple(
            name
            for name in dict.fromkeys(
                (*discovery_names, *context.person_probe_companies)
            )
            if name not in finding_names
        )[:_SUPPLEMENTAL_PROBE_MAX_COMPANIES]
        relation_jobs = context.relation_probes[
            : _SUPPLEMENTAL_PROBE_MAX_COMPANIES - len(person_jobs)
        ]
        query_by_job: dict[tuple[str, int], str] = {}
        for index, company in enumerate(person_jobs):
            query_by_job[("person", index)] = (
                f"{company} {context.person_constraint}"
                if context.person_constraint is not None
                else f"{company} 创始人"
            )
        for index, spec in enumerate(relation_jobs):
            query_by_job[("relation", index)] = f"{spec.entity_name} {spec.term}"
        theme_jobs = context.theme_probes[:_THEME_PROBE_MAX_CANDIDATES]
        for index, spec in enumerate(theme_jobs):
            query_by_job[("theme", index)] = (
                f"{_theme_probe_entity_form(spec.entity_name)} {spec.theme_core}"
            )
        if not query_by_job and not person_findings:
            return SupplementalLaneResult(
                items=(), elapsed_ms=0, cost_units=0.0, retryable=False
            )
        max_wall_seconds = max(0.2, (budget.max_wall_time_ms / 1_000) * 0.9)
        # 16 concurrent web probes (two providers each) routinely trip the
        # providers' rate limits and randomly drop jobs (深南's probe was
        # among the dropped); 8 workers keep the batch within the limits
        # while adding at most one extra probe round.
        with ThreadPoolExecutor(
            max_workers=min(8, len(query_by_job)),
            thread_name_prefix="canonical-v2-serving-probe",
        ) as pool:
            future_by_job = {
                pool.submit(probe, query): job for job, query in query_by_job.items()
            }
            for future, job in future_by_job.items():
                remaining = max_wall_seconds - (monotonic() - started_at)
                try:
                    results = future.result(timeout=max(0.05, remaining))
                except Exception:  # noqa: BLE001 - each probe degrades independently
                    continue
                if job[0] == "person":
                    company = person_jobs[job[1]]
                    hit = _select_probe_hit(
                        judge=judge,
                        kind="person",
                        question=context.question,
                        entity_name=company,
                        semantics={"constraint": context.person_constraint},
                        results=results,
                    )
                    if hit is not None:
                        person_findings.append((company, hit))
                elif job[0] == "theme":
                    spec = theme_jobs[job[1]]
                    hit = _select_probe_hit(
                        judge=judge,
                        kind="theme",
                        question=context.question,
                        entity_name=spec.entity_name,
                        semantics={"core": spec.theme_core},
                        results=results,
                    )
                    if hit is not None:
                        theme_findings.append((spec, hit))
                else:
                    spec = relation_jobs[job[1]]
                    hit = _select_probe_hit(
                        judge=judge,
                        kind="relation",
                        question=context.question,
                        entity_name=spec.entity_name,
                        semantics={"spec": spec},
                        results=results,
                    )
                    if hit is not None:
                        relation_findings.append((spec, hit))
        cost_units = (
            _SUPPLEMENTAL_PROBE_COST_UNITS * len(query_by_job)
        ) + discovery_cost
        elapsed_ms = int((monotonic() - started_at) * 1_000)
        items: list[EvidenceItem] = [
            _relation_probe_evidence_item(
                spec=spec,
                hit=hit,
                clock=clock,
                max_snapshot_bytes=max_snapshot_bytes,
            )
            for spec, hit in relation_findings
        ]
        items.extend(
            _theme_probe_evidence_item(
                spec=spec,
                hit=hit,
                clock=clock,
                max_snapshot_bytes=max_snapshot_bytes,
            )
            for spec, hit in theme_findings
        )
        if person_findings and context.person_part is not None:
            items.append(
                _person_probe_evidence_item(
                    part=context.person_part,
                    findings=tuple(person_findings),
                    clock=clock,
                    max_snapshot_bytes=max_snapshot_bytes,
                )
            )
        if theme_findings and context.theme_part is not None:
            items.append(
                _person_probe_evidence_item(
                    part=context.theme_part,
                    findings=tuple(
                        (spec.entity_name, hit) for spec, hit in theme_findings
                    ),
                    clock=clock,
                    max_snapshot_bytes=max_snapshot_bytes,
                )
            )
        return SupplementalLaneResult(
            items=tuple(items),
            elapsed_ms=elapsed_ms,
            cost_units=cost_units,
            retryable=False,
        )

    return search


def _create_serving_person_criteria_sufficiency_supplemental(
    *,
    web_lane: _DualWebLaneAdapter,
    budget: SupplementalBudget,
    clock: Callable[[], datetime],
    max_snapshot_bytes: int,
    judge: Any | None = None,
) -> tuple[
    Callable[[SufficiencyDecisionRequest], SufficiencyProposal | None],
    Callable[[SupplementalRequest], SupplementalLaneResult],
]:
    """Create the paired serving sufficiency decider and supplemental search."""
    context_store = _SupplementalContextStore()
    # Each probe provider gets up to 3s: Serper needs ~2s from typical
    # networks and a tighter deadline silently drops it, leaving only the
    # weaker provider and systematically empty probes.
    probe_adapter = _DualWebLaneAdapter(
        timeout_ms=max(200, min(3_000, (budget.max_wall_time_ms * 2) // 3)),
        max_snapshot_bytes=max_snapshot_bytes,
        clock=clock,
        bocha=web_lane._bocha,
        serper=web_lane._serper,
        # Person probes need full pages: founder names (许晋诚/陈功) rarely
        # survive a 160-char snippet cut. Enrich each probe's top-2 results
        # with fetched page text, same as the main lane.
        page_fetcher=web_lane._page_fetcher,
    )
    return (
        _serving_sufficiency_decider(context_store=context_store),
        _serving_supplemental_search(
            context_store=context_store,
            probe=probe_adapter._merged_results,
            budget=budget,
            clock=clock,
            max_snapshot_bytes=max_snapshot_bytes,
            judge=judge,
        ),
    )


def _list_names(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names = [
        str(
            item.get("company_name")
            or item.get("name")
            or ""
        ).strip()
        for item in value
        if isinstance(item, dict)
        and str(
            item.get("company_name") or item.get("name") or ""
        ).strip()
    ]
    return "、".join(names[:6])


_WEB_CLAIM_SNIPPET_LIMIT = 240
_LOCAL_CLAIM_FIELD_LIMIT = 160


def _semantic_text(item: EvidenceItem, display_name: str) -> str:
    if item.source_nature == "current_web":
        # Cap the claim text: fetched page bodies (up to 1200 chars per
        # item) times the 48-claim enumeration window made the prose prompt
        # enormous and the model started copying raw listings instead of
        # answering.  The first 240 chars keep the title and the binding
        # sentence.
        return f"{item.snippet[:_WEB_CLAIM_SNIPPET_LIMIT]}；来源：{item.source_locator}"
    try:
        payload = json.loads(item.snippet)
    except (TypeError, json.JSONDecodeError):
        return f"{display_name}：{item.snippet}"
    if not isinstance(payload, dict):
        return display_name
    name = str(
        payload.get("name")
        or payload.get("canonical_name_zh")
        or payload.get("title")
        or display_name
    ).strip()
    relationship = payload.get("_relationship")
    if isinstance(relationship, dict):
        relationship_type = str(relationship.get("relationship_type") or "")
        roles = {
            str(role).strip().casefold()
            for role in relationship.get("roles", ())
            if str(role).strip()
        }
        if relationship_type == "professor_company_role" and "founder" in roles:
            if item.domain == "company":
                relation_text = f"该教授参与创立了{name}，角色为创始人。"
            else:
                relation_text = f"{name}参与创立了该公司，角色为创始人。"
            profile = payload.get("profile_summary")
            if isinstance(profile, str) and profile.strip():
                return f"{relation_text} 公司简介：{profile.strip()[:_LOCAL_CLAIM_FIELD_LIMIT]}"
            return relation_text
    parts: list[str] = [name]
    if item.domain == "professor":
        for label, field in (
            ("机构", "institution"),
            ("职称", "title"),
            ("简介", "profile_summary"),
        ):
            value = payload.get(field)
            if (
                isinstance(value, str)
                and value.strip()
                and value.strip() != name
                and value.strip() != _PROFESSOR_MISSING_FIELD_FALLBACK
            ):
                parts.append(f"{label}：{value.strip()[:_LOCAL_CLAIM_FIELD_LIMIT]}")
        directions = _list_names(payload.get("research_directions"))
        if directions:
            parts.append(f"研究方向：{directions}")
    elif item.domain == "company":
        for label, field in (
            ("简介", "profile_summary"),
            ("技术路线", "technology_route_summary"),
        ):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                text = value.strip()[:_LOCAL_CLAIM_FIELD_LIMIT]
                # Aggregated probe summaries already open with the company
                # name ("帕西尼公司：从创始团队…"); don't print it twice.
                if text.startswith(f"{name}："):
                    text = text[len(f"{name}：") :]
                if text:
                    parts.append(f"{label}：{text}")
    elif item.domain == "paper":
        authors = _list_names(payload.get("authors"))
        if authors:
            parts.append(f"作者：{authors}")
        venue = payload.get("venue")
        if isinstance(venue, dict) and str(venue.get("name") or "").strip():
            parts.append(f"发表 venue：{str(venue['name']).strip()}")
        if payload.get("year") is not None:
            parts.append(f"年份：{payload['year']}")
        summary = payload.get("summary_text")
        if isinstance(summary, str) and summary.strip():
            parts.append(f"摘要：{summary.strip()}")
    elif item.domain == "patent":
        number = payload.get("patent_number")
        if isinstance(number, str) and number.strip():
            parts.append(f"专利号：{number.strip()}")
        applicants = _list_names(payload.get("applicants"))
        if applicants:
            parts.append(f"申请人：{applicants}")
        inventors = _list_names(payload.get("inventors"))
        if inventors:
            parts.append(f"发明人：{inventors}")
        summary = payload.get("summary_text")
        if isinstance(summary, str) and summary.strip():
            parts.append(f"摘要：{summary.strip()}")
    return "；".join(parts) + "。"


_PROSE_SELECTION_MARKER = "<|canonical_v2_selection_v1|>"
_PROSE_ANSWER_MARKER = "<|canonical_v2_answer_v1|>"
_PROSE_PRIVATE_MARKERS = (_PROSE_SELECTION_MARKER, _PROSE_ANSWER_MARKER)
_PROSE_SELECTION_KEYS = frozenset(
    {"selected_claim_indexes", "selected_entity_indexes"}
)
_PROSE_CLASSIFICATION_PREFIX_LIMIT = len(_PROSE_SELECTION_MARKER) + 64
_PROSE_SELECTION_HEADER_LIMIT = 4096


def _decode_prose_selection_header(header: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, value in pairs:
            if key in decoded:
                raise ValueError("LLM prose selection header contains a duplicate key")
            decoded[key] = value
        return decoded

    try:
        selected = json.loads(header, object_pairs_hook=unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM prose selection header is invalid JSON") from exc
    if not isinstance(selected, dict) or set(selected) != _PROSE_SELECTION_KEYS:
        raise ValueError(
            "LLM prose selection header must contain exactly "
            "selected_claim_indexes and selected_entity_indexes"
        )

    decoded_indexes: list[tuple[int, ...]] = []
    for key in ("selected_claim_indexes", "selected_entity_indexes"):
        indexes = selected[key]
        if not isinstance(indexes, list) or any(
            not isinstance(index, int) or isinstance(index, bool) for index in indexes
        ):
            raise ValueError(f"{key} must be integer indexes")
        if len(indexes) != len(set(indexes)):
            raise ValueError(f"{key} are duplicated")
        decoded_indexes.append(tuple(indexes))
    return decoded_indexes[0], decoded_indexes[1]


class _ProseWireDecoder:
    """Incrementally separate a validated selection header from plain prose."""

    def __init__(self) -> None:
        self._state: Literal["classifying", "header", "answer", "plain"] = (
            "classifying"
        )
        self._buffer = ""
        self._header_search_from = 0
        self._selection: tuple[tuple[int, ...], tuple[int, ...]] | None = None
        self._marker_candidate = ""

    @property
    def selection(self) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
        return self._selection

    def _filter_private_markers(self, text: str, *, finish: bool = False) -> str:
        safe_parts: list[str] = []
        for char in text:
            if not self._marker_candidate:
                if char == "<":
                    self._marker_candidate = char
                else:
                    safe_parts.append(char)
                continue

            candidate = self._marker_candidate + char
            if any(marker.startswith(candidate) for marker in _PROSE_PRIVATE_MARKERS):
                self._marker_candidate = candidate
                if candidate in _PROSE_PRIVATE_MARKERS:
                    self._marker_candidate = ""
                    raise ValueError("LLM prose response contains a private marker")
                continue

            safe_parts.append(self._marker_candidate)
            self._marker_candidate = "<" if char == "<" else ""
            if char != "<":
                safe_parts.append(char)

        if finish and self._marker_candidate:
            safe_parts.append(self._marker_candidate)
            self._marker_candidate = ""
        return "".join(safe_parts)

    def _publish_plain(self) -> str:
        self._state = "plain"
        text = self._buffer
        self._buffer = ""
        return self._filter_private_markers(text)

    @staticmethod
    def _structured_object_kind(text: str) -> Literal["pending", "json", "plain"]:
        body = text[1:].lstrip()
        if not body:
            return "pending"
        return "json" if body[0] in {'"', "}"} else "plain"

    def _consume_classification(self) -> str:
        if self._buffer.startswith(_PROSE_SELECTION_MARKER):
            self._buffer = self._buffer[len(_PROSE_SELECTION_MARKER) :]
            self._state = "header"
            self._header_search_from = 0
            return self._consume_header()
        if _PROSE_SELECTION_MARKER.startswith(self._buffer):
            return ""

        if self._buffer.startswith("{"):
            object_kind = self._structured_object_kind(self._buffer)
            if object_kind == "json":
                raise ValueError(
                    "LLM prose response uses an unsupported legacy JSON object"
                )
            if object_kind == "plain":
                return self._publish_plain()
        elif self._buffer.startswith("`"):
            if "```".startswith(self._buffer):
                return ""
            if not self._buffer.startswith("```"):
                return self._publish_plain()
            fence_body = self._buffer[3:]
            if "json".startswith(fence_body):
                if fence_body == "json":
                    raise ValueError(
                        "LLM prose response uses an unsupported legacy JSON fence"
                    )
                return ""
            if fence_body.startswith("json"):
                raise ValueError(
                    "LLM prose response uses an unsupported legacy JSON fence"
                )
            if fence_body and fence_body[0].isspace():
                fenced_text = fence_body.lstrip()
                if not fenced_text:
                    return ""
                if fenced_text.startswith("{"):
                    object_kind = self._structured_object_kind(fenced_text)
                    if object_kind == "json":
                        raise ValueError(
                            "LLM prose response uses an unsupported legacy JSON fence"
                        )
                    if object_kind == "pending":
                        return ""
                return self._publish_plain()
            return self._publish_plain()
        else:
            return self._publish_plain()

        if len(self._buffer) > _PROSE_CLASSIFICATION_PREFIX_LIMIT:
            raise ValueError("LLM prose response has an incomplete structured prefix")
        return ""

    def _consume_header(self) -> str:
        marker_index = self._buffer.find(
            _PROSE_ANSWER_MARKER, self._header_search_from
        )
        if marker_index < 0:
            confirmed_header_length = max(
                0, len(self._buffer) - len(_PROSE_ANSWER_MARKER) + 1
            )
            if confirmed_header_length > _PROSE_SELECTION_HEADER_LIMIT:
                raise ValueError("LLM prose selection header exceeds the size limit")
            self._header_search_from = confirmed_header_length
            return ""
        if marker_index > _PROSE_SELECTION_HEADER_LIMIT:
            raise ValueError("LLM prose selection header exceeds the size limit")

        selection = _decode_prose_selection_header(
            self._buffer[:marker_index].strip()
        )
        answer_start = marker_index + len(_PROSE_ANSWER_MARKER)
        answer = self._buffer[answer_start:]
        self._buffer = ""
        self._header_search_from = 0
        self._selection = selection
        self._state = "answer"
        return self._filter_private_markers(answer)

    def feed(self, text: str) -> str:
        if not text:
            return ""
        if self._state in {"answer", "plain"}:
            return self._filter_private_markers(text)
        if self._state == "classifying" and not self._buffer:
            text = text.lstrip()
            if not text:
                return ""
        self._buffer += text
        if self._state == "classifying":
            return self._consume_classification()
        return self._consume_header()

    def finish(self) -> str:
        if self._state == "classifying":
            if (
                0 < len(self._buffer) < len(_PROSE_SELECTION_MARKER)
                and _PROSE_SELECTION_MARKER.startswith(self._buffer)
            ):
                answer = self._publish_plain()
            elif not self._buffer.strip():
                answer = self._publish_plain()
            else:
                answer = self._consume_classification()
            if self._state == "classifying":
                raise ValueError("LLM prose response has an incomplete structured prefix")
            if self._state == "header":
                raise ValueError("LLM prose response is missing the answer marker")
            return answer + self._filter_private_markers("", finish=True)
        if self._state == "header":
            raise ValueError("LLM prose response is missing the answer marker")
        return self._filter_private_markers("", finish=True)


class _ProseTextNormalizer:
    """Publish only text that survives deterministic final normalization."""

    _SENTENCE_ENDINGS = frozenset(".!?。！？")
    _LINE_PREFIX_LIMIT = 16
    _ROMAN_LIST_MARKER_CHARS = frozenset("IVXLCDMivxlcdm")

    def __init__(
        self,
        *,
        founder_prefix: str | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> None:
        self._founder_prefix = founder_prefix or None
        self._on_chunk = on_chunk
        self._parts: list[str] = []
        self._pending_whitespace: list[str] = []
        self._founder_duplicate_candidate: list[str] = []
        self._founder_prefix_added = False
        self._founder_boundary_safe = True
        self._line_prefix: list[str] = []
        self._line_prefix_truncated = False
        self._model_text_started = False
        self._started = False

    def _emit(self, text: str) -> None:
        if not text:
            return
        self._parts.append(text)
        if self._on_chunk is not None:
            self._on_chunk(text)

    def _period_follows_list_marker(self) -> bool:
        if self._line_prefix_truncated:
            return False
        marker = "".join(self._line_prefix).strip()
        if not marker:
            return False
        numeric_parts = marker.split(".")
        if all(part.isdigit() for part in numeric_parts):
            return True
        if len(marker) == 1 and marker.isascii() and marker.isalpha():
            return True
        return len(marker) <= 6 and all(
            char in self._ROMAN_LIST_MARKER_CHARS for char in marker
        )

    def _record_line_char(self, char: str) -> None:
        if char in "\r\n":
            self._line_prefix.clear()
            self._line_prefix_truncated = False
        elif not self._line_prefix_truncated:
            if len(self._line_prefix) < self._LINE_PREFIX_LIMIT:
                self._line_prefix.append(char)
            else:
                self._line_prefix_truncated = True

    def _update_founder_boundary(self, char: str) -> None:
        if char in "\r\n":
            self._founder_boundary_safe = True
        elif char.isspace():
            pass
        elif char in self._SENTENCE_ENDINGS:
            self._founder_boundary_safe = not (
                char == "." and self._period_follows_list_marker()
            )
        else:
            self._founder_boundary_safe = False
        self._record_line_char(char)

    def _feed_stable_char(self, char: str) -> None:
        if char.isspace():
            self._pending_whitespace.append(char)
            self._update_founder_boundary(char)
            return
        if not self._model_text_started:
            self._pending_whitespace.clear()
            if self._founder_prefix_added:
                self._emit("\n\n")
            self._model_text_started = True
        elif self._pending_whitespace:
            self._emit("".join(self._pending_whitespace))
            self._pending_whitespace.clear()
        self._emit(char)
        self._update_founder_boundary(char)

    def _flush_founder_candidate(self) -> None:
        candidate = tuple(self._founder_duplicate_candidate)
        self._founder_duplicate_candidate.clear()
        for candidate_char in candidate:
            self._feed_stable_char(candidate_char)

    def _feed_founder_char(self, char: str) -> None:
        founder_prefix = self._founder_prefix
        if founder_prefix is None:
            self._feed_stable_char(char)
            return
        if not self._founder_duplicate_candidate:
            if not (
                self._founder_boundary_safe and char == founder_prefix[0]
            ):
                self._feed_stable_char(char)
                return
        self._founder_duplicate_candidate.append(char)
        candidate = "".join(self._founder_duplicate_candidate)
        if not founder_prefix.startswith(candidate):
            self._flush_founder_candidate()
        elif candidate == founder_prefix:
            self._founder_duplicate_candidate.clear()
            self._founder_boundary_safe = True

    def feed(self, text: str) -> None:
        for char in text:
            if "\ud800" <= char <= "\udfff":
                raise ValueError(
                    "LLM prose response has an unpaired UTF-16 surrogate"
                )
            if not self._started:
                if char.isspace():
                    continue
                self._started = True
                if self._founder_prefix is not None:
                    self._founder_prefix_added = True
                    self._emit(self._founder_prefix)
            self._feed_founder_char(char)

    def finish(self) -> str:
        self._flush_founder_candidate()
        self._pending_whitespace.clear()
        return "".join(self._parts)


def _founder_prefix(result: Any, active_anchor: Any, displayed_set: Any) -> str | None:
    founder_claims = tuple(
        claim
        for claim in getattr(result, "claims", ())
        if getattr(claim, "predicate", None) == "professor_company_role"
        and "参与创立" in str(getattr(claim, "text", ""))
    )
    if len(founder_claims) != 1:
        return None

    handles = (() if active_anchor is None else (active_anchor,)) + (
        () if displayed_set is None else tuple(displayed_set.handles)
    )
    handle_by_id: dict[str, Any] = {}
    for handle in handles:
        handle_id = getattr(handle, "canonical_id", None) or getattr(
            handle, "handle_id", None
        )
        if isinstance(handle_id, str) and handle_id:
            handle_by_id.setdefault(handle_id, handle)

    bound_handles = tuple(
        handle_by_id[handle_id]
        for handle_id in dict.fromkeys(
            getattr(founder_claims[0], "subject_handle_ids", ())
        )
        if handle_id in handle_by_id
    )
    professors = tuple(
        handle for handle in bound_handles if handle.domain == "professor"
    )
    companies = tuple(handle for handle in bound_handles if handle.domain == "company")
    if len(professors) != 1 or len(companies) != 1:
        return None
    professor_name = getattr(professors[0], "display_name", None)
    company_name = getattr(companies[0], "display_name", None)
    if not isinstance(professor_name, str) or not professor_name:
        return None
    if not isinstance(company_name, str) or not company_name:
        return None
    return f"{professor_name}参与创立了{company_name}。"


def _rendered_prose_answer_text(rendered: str | ProseSynthesisResult) -> str:
    return rendered if isinstance(rendered, str) else rendered.answer_text


def _anchor_correction_name(result: Any, active_anchor: Any) -> str | None:
    """Anchor the synchronous answer must stay on, or None to skip the check.

    A web-only soft context subject outranks the session anchor: the vector
    lane can mis-anchor the session onto a look-alike canonical entity, and
    judging the answer against that wrong anchor lets drifted answers pass.
    Otherwise mirrors the ``_matched_bound_entity`` skip for web-handle
    anchors: their display names come from unattributed Web text, so an
    answer cannot be judged against them. Clarification-only turns are never
    corrected.
    """
    if str(getattr(result, "response_mode", "answer") or "answer") != "answer":
        return None
    context = getattr(result, "context_receipt", None)
    soft_subject = getattr(context, "soft_context_subject", None)
    if (
        isinstance(soft_subject, str)
        and soft_subject.strip()
        and _normalized_web_identity(soft_subject)
    ):
        return soft_subject
    if active_anchor is None:
        return None
    entity_id = getattr(active_anchor, "canonical_id", None) or getattr(
        active_anchor, "handle_id", None
    )
    if (
        not isinstance(entity_id, str)
        or not entity_id
        or entity_id.startswith("web-handle:")
    ):
        return None
    display_name = getattr(active_anchor, "display_name", None)
    if (
        not isinstance(display_name, str)
        or not display_name.strip()
        or not _normalized_web_identity(display_name)
    ):
        return None
    return display_name


_ANSWER_LEAD_SENTENCE_RE = re.compile(r"[。！？!?]")


def _answer_lead_mentions_stem(answer_text: str, org_stem: str) -> bool:
    """Whether the answer's opening sentence names the organization."""
    if not org_stem:
        return False
    head = _ANSWER_LEAD_SENTENCE_RE.split(answer_text, maxsplit=1)[0]
    return org_stem in _normalized_web_identity(head)


def _answer_mentions_anchor(
    answer_text: str, anchor_name: str, *, location_qualifier: str | None = None
) -> bool:
    searchable = _normalized_web_identity(answer_text)
    if location_qualifier is not None:
        stem = _org_name_stem(anchor_name)
        if not (stem and stem in searchable and location_qualifier in searchable):
            return False
        # A lookalike-organized answer can still name-drop the anchor once;
        # require the anchor to lead the answer or recur in it.
        return _answer_lead_mentions_stem(answer_text, stem) or searchable.count(stem) >= 2
    for form in _web_identity_forms(anchor_name):
        # The Web-lane marker rule for short forms targets noisy search
        # snippets; on the answer side a bare 3+ char name (丁文伯是…) is a
        # legitimate anchor mention, so plain substring wins from len 3 up.
        if len(form) >= 3:
            if form in searchable:
                return True
        elif _web_identity_text_matches(form, searchable):
            return True
    return False


def _anchor_correction_message(
    anchor_name: str,
    *,
    location_qualifier: str | None = None,
    reference_material: str | None = None,
) -> str:
    if location_qualifier is not None:
        instruction = (
            f"上一轮答案没有聚焦“{anchor_name}”作答，请重新回答："
            f"围绕“{anchor_name}”组织答案；该分部的公开信息不足时，"
            "基于已确认的信息概括作答，涉及其他分部的内容须明确归属，"
            "不得把其他分部的事实写入该分部；不得反问用户，不得要求用户补充信息；"
            "保持既定的返回格式不变。"
        )
    else:
        instruction = (
            f"上一轮答案没有围绕主体“{anchor_name}”作答，请重新回答："
            f"仅依据与“{anchor_name}”直接相关的输入信息组织答案；"
            "没有直接信息时，基于该主体可确认的信息概括作答。"
            "不得反问用户，不得要求用户补充信息；保持既定的返回格式不变。"
        )
    if reference_material:
        return (
            f"{instruction}\n以下是与该主体直接相关的补充材料，"
            f"优先采用其中与“{anchor_name}”直接相关的事实：\n{reference_material}"
        )
    return instruction


def _anchor_location_qualifier_for_result(result: Any, anchor_name: str) -> str | None:
    return _anchor_location_qualifier(
        anchor_name, str(getattr(result, "original_query", "") or "")
    )


def _multi_branch_guidance_block(
    *, anchor_name: str, branch_qualifiers: tuple[str, ...],
) -> str:
    branches = "、".join(branch_qualifiers)
    return (
        f"情境说明：用户问的是机构级名称“{anchor_name}”，未指明城市。"
        f"输入信息显示该机构在以下地区设有分部：{branches}。"
        "要求：先完整回答用户的问题，总部及各分部的内容都是合法素材，"
        "但涉及具体分部的事实时必须明确归属（不得把一个分部的事实写成另一个分部的）；"
        "任何情况下不得拒答、不得反问。"
        "如果用户的需求可能特指某一分部，请在答案中自然地说明该机构在上述城市设有分部，"
        "并顺势引导用户在提问中注明想了解的城市——引导要与答案内容融为一体，"
        "不要使用模板式附录句；如果对话上下文已经表明用户聚焦某一分部，"
        "则直接按该分部作答，不再引导。"
    )


def _multi_branch_context_for_result(result: Any) -> str | None:
    context = getattr(result, "context_receipt", None)
    soft_subject = getattr(context, "soft_context_subject", None)
    anchor = getattr(context, "active_anchor", None)
    anchor_name = (
        soft_subject
        if isinstance(soft_subject, str) and soft_subject.strip()
        else getattr(anchor, "display_name", None)
    )
    if not isinstance(anchor_name, str) or not anchor_name.strip():
        return None
    original_query = str(getattr(result, "original_query", "") or "")
    if _anchor_location_qualifier(anchor_name, original_query) is not None:
        return None
    stem = _org_name_stem(anchor_name)
    if not stem:
        return None
    claim_texts = tuple(
        str(getattr(claim, "text", "") or "")
        for claim in getattr(result, "claims", ())
    )
    branches = _evidence_branch_qualifiers(
        org_stem=stem, texts=claim_texts, anchor_qualifier=None,
    )
    if not branches:
        return None
    return _multi_branch_guidance_block(
        anchor_name=anchor_name, branch_qualifiers=branches,
    )


def _reject_truncated_prose_finish_reason(choice: Any) -> None:
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason in {"length", "content_filter"}:
        raise ValueError(
            f"LLM prose response rejected provider finish_reason={finish_reason}"
        )


class _OpenAIProseRenderer:
    def __init__(
        self,
        *,
        client: Any,
        model: str,
        extra_body: dict[str, Any],
        page_fetcher: Callable[[str], str | None] | None = None,
        fetch_timeout_seconds: float = 10.0,
    ) -> None:
        self._client = client
        self._model = model
        self._extra_body = extra_body
        self._page_fetcher = page_fetcher
        # Advisory only: the reference fetch is a direct call guarded by
        # try/except (see _fetch_anchor_reference_material). This layer owns
        # no executor to enforce a separate deadline, so the tiered fetcher's
        # internal timeouts (page_fetch tier0 5s) are the effective bound.
        self._fetch_timeout_seconds = fetch_timeout_seconds

    def _fetch_anchor_reference_material(
        self, *, result: Any, anchor_name: str,
    ) -> str | None:
        """Fetch at most one anchor-relevant page for the correction retry.

        Candidate: the first ``current_web`` citation locator whose domain
        matches the anchor brand, else the first whose title/snippet head
        names the anchor. The anti-echo guard drops fetched pages that never
        mention the anchor stem, so a wrong-subject page is never injected.
        Fail-open: any error yields None (a bare correction message).
        """
        if self._page_fetcher is None:
            return None
        citations = tuple(
            citation
            for citation in getattr(result, "citations", ())
            if getattr(citation, "source_nature", None) == "current_web"
        )
        if not citations:
            return None

        def locator(citation: Any) -> str:
            return str(getattr(citation, "source_locator", "") or "")

        chosen = next(
            (
                citation
                for citation in citations
                if _web_identity_domain_matches(anchor_name, locator(citation))
            ),
            None,
        )
        if chosen is None:
            forms = _web_identity_forms(anchor_name)

            def title_hits(citation: Any) -> bool:
                raw = str(
                    getattr(citation, "title", "")
                    or getattr(citation, "snippet", "")
                    or ""
                )
                head = raw.partition("：")[0]
                searchable = _normalized_web_identity(head)
                return any(
                    _web_identity_text_matches(form, searchable) for form in forms
                )

            chosen = next((c for c in citations if title_hits(c)), None)
        if chosen is None:
            return None
        try:
            text = self._page_fetcher(locator(chosen))
        except Exception:
            _logger.info("anchor reference fetch failed", exc_info=True)
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        stem = _org_name_stem(anchor_name)
        if not stem or stem not in _normalized_web_identity(text):
            return None
        return text.strip()[:1200]

    def _chat_request(
        self, result: Any
    ) -> tuple[
        tuple[dict[str, Any], ...],
        tuple[Any, ...],
        list[Any],
        list[str | None],
        Any,
        Any,
    ]:
        """Build the shared prose request: chat messages plus analysis locals.

        ``__call__`` and ``stream`` share one payload construction so the
        token-level streaming path keeps the exact prompt version, system
        instructions, and request shape of the synchronous path.
        """
        context = getattr(result, "context_receipt", None)
        active_anchor = getattr(context, "active_anchor", None)
        displayed_set = getattr(context, "displayed_result_set", None)
        candidate_handles: list[Any] = []
        seen_handles: set[tuple[str, str]] = set()
        for handle in (
            *(() if displayed_set is None else displayed_set.handles),
            *(() if active_anchor is None else (active_anchor,)),
        ):
            key = (str(handle.domain), str(handle.display_name))
            if key not in seen_handles:
                seen_handles.add(key)
                candidate_handles.append(handle)

        def handle_id(handle: Any) -> str | None:
            value = getattr(handle, "canonical_id", None) or getattr(
                handle, "handle_id", None
            )
            return value if isinstance(value, str) and value else None

        handle_ids = tuple(handle_id(handle) for handle in candidate_handles)
        citation_by_evidence_id: dict[str, Any] = {
            citation.evidence_id: citation
            for citation in getattr(result, "citations", ())
        }
        claims = cast(tuple[Any, ...], tuple(getattr(result, "claims", ())))
        claim_entity_indexes: list[tuple[int, ...]] = []
        for claim in claims:
            evidence_ids = set(getattr(claim, "evidence_ids", ()))
            subject_handle_ids = set(getattr(claim, "subject_handle_ids", ()))
            subject_id = getattr(claim, "subject_id", None)
            indexes = tuple(
                index
                for index, (candidate, candidate_id) in enumerate(
                    zip(candidate_handles, handle_ids, strict=True),
                    start=1,
                )
                if (
                    (candidate_id is not None and candidate_id == subject_id)
                    or (candidate_id is not None and candidate_id in subject_handle_ids)
                    or bool(evidence_ids.intersection(getattr(candidate, "evidence_ids", ())))
                )
            )
            claim_entity_indexes.append(indexes)
        frame = _question_frame(str(getattr(result, "original_query", "") or ""))
        coverage = getattr(result, "enumeration_coverage", None)
        coverage_payload: dict[str, Any] | None = None
        if coverage is not None:
            display_name_by_id = {
                candidate_id: handle.display_name
                for handle, candidate_id in zip(
                    candidate_handles, handle_ids, strict=True
                )
                if candidate_id is not None
            }
            coverage_payload = {
                "mode": coverage.mode,
                "scope": coverage.scope,
                "as_of": coverage.as_of.isoformat(),
                "checked_count": coverage.checked_count,
                "eligible_count": coverage.eligible_count,
                "retrieved_count": coverage.retrieved_count,
                "displayed_count": coverage.displayed_count,
                "omitted_count": coverage.omitted_count,
                **(
                    {"unknown_count": coverage.unknown_count}
                    if coverage.unknown_count is not None
                    else {}
                ),
                "unknown_scope": coverage.unknown_scope,
                "exhaustive": coverage.exhaustive,
                "omitted_members": [
                    display_name_by_id[member_id]
                    for member_id in coverage.omitted_ids
                    if member_id in display_name_by_id
                ],
            }
        payload = {
            "prompt_version": "canonical-v2-prose-v16",
            "user_question": getattr(result, "original_query", None),
            "question_frame": {
                "subject_scope": frame.subject_scope,
                "predicate": frame.predicate,
                "requested_values": list(frame.requested_values),
                "logic": frame.logic,
            },
            "active_entity": (
                None
                if active_anchor is None
                else {
                    "name": active_anchor.display_name,
                    "domain": active_anchor.domain,
                }
            ),
            "displayed_entities": [
                {
                    "entity_index": index,
                    "name": handle.display_name,
                    "domain": handle.domain,
                }
                for index, handle in enumerate(candidate_handles, start=1)
            ],
            "relationship_paths": list(
                () if context is None else context.traversed_path_ids
            ),
            "supported_claims": [
                {
                    "claim_index": index,
                    "subject_entity_indexes": list(claim_entity_indexes[index - 1]),
                    "text": claim.text,
                    "predicate": claim.predicate,
                    "status": claim.status,
                    "source_types": list(claim.source_natures),
                    "source_urls": [
                        citation.source_locator
                        for evidence_id in claim.evidence_ids
                        if (
                            (citation := citation_by_evidence_id.get(evidence_id))
                            is not None
                            and citation.source_nature == "current_web"
                        )
                    ],
                }
                for index, claim in enumerate(claims, start=1)
            ],
            "enumeration_coverage": coverage_payload,
        }
        guidance = _multi_branch_context_for_result(result)
        messages = [
            {
                "role": "system",
                "content": (
                        "你是深圳科创信息助手。输入是带证据约束的候选信息，不代表每条都与问题相关；"
                        "先判断相关性，再只采用相关内容回答用户。"
                        "行文风格：像熟悉领域的专业助手一样直接作答——先给结论，再按主体或关系组织"
                        "必要细节，叙述自然流畅；禁止出现“材料”“提供的材料”“根据材料”“材料显示”"
                        "“候选材料”“检索到”“检索结果”“证据显示”“有证据表明”这类元叙述措辞；"
                        "可以自然使用“公开信息显示”“官网介绍”等表述；合并同义与重复信息；"
                        "不要复制原始字段或搜索摘要，不要逐字段复述，不要输出“简介”“技术路线”等"
                        "数据字段标签。"
                        "内部纪律（遵守但不在行文中强调）：关系问题明确写出人物、关系角色和目标实体。"
                        "产品能力确认看语义覆盖而非逐字匹配：公司文档化的主营业务或产品定位明确覆盖"
                        "所问能力即可确认（如“印制电路板”覆盖“PCB打板”、“配送机器人”覆盖“酒店送餐”），"
                        "不要求与问法措辞逐字一致；但具体功能点类问题（如“机械臂按电梯”“刷门禁”）"
                        "只有在同一信息直接绑定具体产品与具体功能时才能确认；公司通用能力、"
                        "其他产品或外围系统集成不能替代；区分机器人直接操作物理控件与通过楼宇或"
                        "物联网接口集成。专利或公司技术不是产品名称；用户问‘哪些产品’时必须给出"
                        "直接绑定该能力的具体产品名，否则说明只能确认到公司或技术层。"
                        "总部地点必须有信息明确写出总部关系，不能从公司名称、分支机构或服务地点"
                        "推断总部。"
                        "不要输出内部ID、检索流程；不得编造具体公司、人名、数字、日期等事实；"
                        "但问题直接问及的普遍背景（如行业规模、常见做法、一般性分类）"
                        "允许基于公开常识作概括性说明，明确区别于输入中可直接确认的信息。"
                        "人名、公司名、论文标题、专利号等专有名称必须与输入中的写法逐字一致"
                        "（例如“丁文伯”不可写成“丁文波”），不得自行改写、简写或音译。"
                        "回答降级策略（按优先级执行，任何情况下不得只回答“未找到/无法回答”）："
                        "① 有直接依据时，直接回答并给出关键细节；"
                        "② 所问的具体属性无直接依据时，充分利用该主体相关的其他可确认信息作答"
                        "（如主体概况、相关人物、公开背景、行业情况），最后说明该具体属性公开"
                        "信息未披露即可；不要生硬套模板，也不要为凑内容编造；"
                        "③ 主体本身无任何公开信息时，先说明公开信息中未找到该主体，"
                        "再给出问题主题相关的概括性背景（行业常见情况、同类典型做法）"
                        "直接作答；不得反问用户，不得要求用户补充信息；"
                        "④ 概括性内容基于公开常识，不得编造具体公司、人名、数字、日期等事实。"
                        "对依据不足或未入选的主体不要逐条解释、不要逐一列名。"
                        "列表与集合类问题必须求全：凡是有直接依据确认的主体都要列出，按相关度"
                        "从高到低排序，宁多勿漏——不得因为篇幅或知名度只挑少数几家；每个主体"
                        "用一两句给出其关键事实即可，确需取舍时按 enumeration_coverage 如实交代。"
                        "对“上述/这些”集合问题，只回答有直接依据的主体，其余主体不列名、不解释，"
                        "用覆盖度一句带过。"
                        "对“方法/路线/方式/差异/原理”类概念问题：按行业常见分类分条组织答案，"
                        "覆盖输入信息中出现的各主要方向——例如数据采集类（遥操作、动作捕捉/动捕、"
                        "真机/全模态采集、仿真合成、视频学习等）、生成类（物理仿真引擎、生成式模型、"
                        "规则/程序化生成等）——确保不遗漏有依据的方向；只组织输入中有依据的内容，"
                        "不得为凑分类而编造。"
                        "输入中的 enumeration_coverage 是列表类问题的枚举核算；当其 mode 为 "
                        "representative 时，用自然语言交代覆盖度（如“共找到 N 个相关结果，"
                        "以上为其中有代表性的 M 个”），严禁暗示已穷尽全部结果。"
                        "严格按以下 wire 格式返回：\n<|canonical_v2_selection_v1|>\n"
                        "一个恰好只含 selected_claim_indexes 和 selected_entity_indexes 两个字段的"
                        "JSON对象\n<|canonical_v2_answer_v1|>\n最终中文答案。"
                        "selected_claim_indexes列出答案实际使用的全部claim_index（包括用于排除候选的"
                        "反证）；selected_entity_indexes只列出答案最终确认或推荐的主体entity_index，"
                        "不要列入被排除或仅作为背景的主体。答案 marker 后是未经JSON编码的纯文本，"
                        "可以多行。禁止Markdown代码围栏、旧版JSON答案外壳、marker之外的附加文本。"
                        + ("" if guidance is None else f"\n{guidance}")
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ]
        return (
            messages,
            claims,
            candidate_handles,
            handle_ids,
            active_anchor,
            displayed_set,
        )

    @staticmethod
    def _selection_ids(
        *,
        selection: tuple[tuple[int, ...], tuple[int, ...]],
        claims: tuple[Any, ...],
        candidate_handles: list[Any],
        handle_ids: list[str | None],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        claim_indexes, entity_indexes = selection
        if len(claim_indexes) != len(set(claim_indexes)) or any(
            index < 1 or index > len(claims) for index in claim_indexes
        ):
            raise ValueError("selected_claim_indexes are out of range or duplicated")
        if len(entity_indexes) != len(set(entity_indexes)) or any(
            index < 1
            or index > len(candidate_handles)
            or handle_ids[index - 1] is None
            for index in entity_indexes
        ):
            raise ValueError("selected_entity_indexes are out of range or duplicated")
        return (
            tuple(cast(str, claims[index - 1].claim_id) for index in claim_indexes),
            tuple(cast(str, handle_ids[index - 1]) for index in entity_indexes),
        )

    @classmethod
    def _finalize_response(
        cls,
        *,
        answer_text: str,
        selection: tuple[tuple[int, ...], tuple[int, ...]] | None,
        claims: tuple[Any, ...],
        candidate_handles: list[Any],
        handle_ids: list[str | None],
    ) -> str | ProseSynthesisResult:
        if not answer_text:
            raise ValueError("LLM prose response is empty")
        if selection is None:
            return answer_text
        selected_claim_ids, selected_handle_ids = cls._selection_ids(
            selection=selection,
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
        )
        return ProseSynthesisResult(
            answer_text=answer_text,
            selected_claim_ids=selected_claim_ids,
            selected_handle_ids=selected_handle_ids,
        )

    def _parse_response(
        self,
        result: Any,
        *,
        content: Any,
        claims: tuple[Any, ...],
        candidate_handles: list[Any],
        handle_ids: list[str | None],
        active_anchor: Any,
        displayed_set: Any,
    ) -> str | ProseSynthesisResult:
        """Decode and normalize one synchronous provider response."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM prose response is empty")
        decoder = _ProseWireDecoder()
        normalizer = _ProseTextNormalizer(
            founder_prefix=_founder_prefix(result, active_anchor, displayed_set)
        )
        normalizer.feed(decoder.feed(content))
        normalizer.feed(decoder.finish())
        return self._finalize_response(
            answer_text=normalizer.finish(),
            selection=decoder.selection,
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
        )

    def _synthesize_once(
        self,
        *,
        result: Any,
        request_messages: list[dict[str, Any]],
        claims: tuple[Any, ...],
        candidate_handles: list[Any],
        handle_ids: list[str | None],
        active_anchor: Any,
        displayed_set: Any,
    ) -> str | ProseSynthesisResult:
        """Run one non-stream synthesis round-trip and parse the response.

        Shared by the synchronous ``__call__`` (initial render plus its one
        correction retry) and the stream path's final-answer correction.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            # 3000 tokens lifts the old 1200 ceiling that silently truncated
            # long answers; streaming and sync synthesis share the same bound.
            max_tokens=3000,
            messages=request_messages,
            extra_body=self._extra_body,
        )
        choices = getattr(response, "choices", ())
        choice = None if not choices else choices[0]
        _reject_truncated_prose_finish_reason(choice)
        content = (
            None
            if choice is None
            else getattr(getattr(choice, "message", None), "content", None)
        )
        return self._parse_response(
            result,
            content=content,
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
            active_anchor=active_anchor,
            displayed_set=displayed_set,
        )

    def __call__(self, result: Any) -> str | ProseSynthesisResult:
        (
            messages,
            claims,
            candidate_handles,
            handle_ids,
            active_anchor,
            displayed_set,
        ) = self._chat_request(result)

        rendered = self._synthesize_once(
            result=result,
            request_messages=messages,
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
            active_anchor=active_anchor,
            displayed_set=displayed_set,
        )
        anchor_name = _anchor_correction_name(result, active_anchor)
        qualifier = (
            None
            if anchor_name is None
            else _anchor_location_qualifier_for_result(result, anchor_name)
        )
        if anchor_name is None or _answer_mentions_anchor(
            _rendered_prose_answer_text(rendered), anchor_name,
            location_qualifier=qualifier,
        ):
            return rendered
        # One bounded correction retry: an answer that never names the anchor
        # entity is presumed to have drifted onto a look-alike subject. A
        # correct pronoun-only answer pays one extra call; when the retry
        # still misses, the caller's deterministic fallback answers instead.
        reference = self._fetch_anchor_reference_material(
            result=result, anchor_name=anchor_name,
        )
        corrected = self._synthesize_once(
            result=result,
            request_messages=[
                *messages,
                {
                    "role": "user",
                    "content": _anchor_correction_message(
                        anchor_name,
                        location_qualifier=qualifier,
                        reference_material=reference,
                    ),
                },
            ],
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
            active_anchor=active_anchor,
            displayed_set=displayed_set,
        )
        if not _answer_mentions_anchor(
            _rendered_prose_answer_text(corrected), anchor_name,
            location_qualifier=qualifier,
        ):
            raise ValueError("answer off-anchor")
        return corrected

    def stream(
        self, result: Any, *, on_chunk: Callable[[str], None]
    ) -> str | ProseSynthesisResult:
        """Incrementally decode the selection header and publish plain answer text.

        Answer chunks are published as they arrive and cannot be revoked, so
        the stream keeps its single streaming provider call. When the finished
        answer has drifted off the correction anchor, the FINAL answer is
        corrected with one bounded non-stream retry; the returned result then
        differs from the streamed draft and the SSE answer event triggers the
        frontend re-render. Correction failure is fail-open: the original
        streamed result stands.
        """
        (
            messages,
            claims,
            candidate_handles,
            handle_ids,
            active_anchor,
            displayed_set,
        ) = self._chat_request(result)
        completion = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=3000,
            messages=messages,
            extra_body=self._extra_body,
            stream=True,
        )
        decoder = _ProseWireDecoder()
        normalizer = _ProseTextNormalizer(
            founder_prefix=_founder_prefix(result, active_anchor, displayed_set),
            on_chunk=on_chunk,
        )
        selection_validated = False
        for chunk in completion:
            choices = getattr(chunk, "choices", ())
            if not choices:
                continue
            choice = choices[0]
            _reject_truncated_prose_finish_reason(choice)
            delta = getattr(choice, "delta", None)
            text = None if delta is None else getattr(delta, "content", None)
            if not isinstance(text, str) or not text:
                continue
            answer_chunk = decoder.feed(text)
            if decoder.selection is not None and not selection_validated:
                self._selection_ids(
                    selection=decoder.selection,
                    claims=claims,
                    candidate_handles=candidate_handles,
                    handle_ids=handle_ids,
                )
                selection_validated = True
            normalizer.feed(answer_chunk)

        final_chunk = decoder.finish()
        if decoder.selection is not None and not selection_validated:
            self._selection_ids(
                selection=decoder.selection,
                claims=claims,
                candidate_handles=candidate_handles,
                handle_ids=handle_ids,
            )
        normalizer.feed(final_chunk)
        finalized = self._finalize_response(
            answer_text=normalizer.finish(),
            selection=decoder.selection,
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
        )
        anchor_name = _anchor_correction_name(result, active_anchor)
        if anchor_name is None:
            return finalized
        qualifier = _anchor_location_qualifier_for_result(result, anchor_name)
        if _answer_mentions_anchor(
            _rendered_prose_answer_text(finalized), anchor_name,
            location_qualifier=qualifier,
        ):
            return finalized
        # Chunks are already published and irrevocable; correct the FINAL
        # answer with one non-stream retry. The SSE answer event then differs
        # from the streamed draft and the frontend re-renders (see
        # chat.html answer-event mismatch fallback). Failure is fail-open:
        # the original streamed result stands, matching phase-1 behavior.
        try:
            reference = self._fetch_anchor_reference_material(
                result=result, anchor_name=anchor_name,
            )
            corrected = self._synthesize_once(
                result=result,
                request_messages=[
                    *messages,
                    {
                        "role": "user",
                        "content": _anchor_correction_message(
                            anchor_name,
                            location_qualifier=qualifier,
                            reference_material=reference,
                        ),
                    },
                ],
                claims=claims,
                candidate_handles=candidate_handles,
                handle_ids=handle_ids,
                active_anchor=active_anchor,
                displayed_set=displayed_set,
            )
        except Exception:  # provider/parse failure mid-correction: keep original
            _logger.info("stream off-anchor correction failed; keeping streamed answer")
            return finalized
        if _answer_mentions_anchor(
            _rendered_prose_answer_text(corrected), anchor_name,
            location_qualifier=qualifier,
        ):
            if isinstance(corrected, ProseSynthesisResult):
                # The corrected FINAL answer supersedes the already-published
                # drifted chunks; the mark lets the knowledge_answer stream
                # guard exempt this one legitimate mismatch.
                return corrected.model_copy(
                    update={"supersedes_streamed_draft": True}
                )
            return corrected
        _logger.info("stream off-anchor correction missed; keeping streamed answer")
        return finalized

    def warm(self) -> None:
        self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
            extra_body=self._extra_body,
        )


class _EnvironmentProseRenderer:
    def __init__(
        self, *, page_fetcher: Callable[[str], str | None] | None = None,
    ) -> None:
        self._renderer: _OpenAIProseRenderer | None = None
        self._renderer_lock = Lock()
        self._page_fetcher = page_fetcher

    def _configured_renderer(self) -> _OpenAIProseRenderer:
        with self._renderer_lock:
            if self._renderer is not None:
                return self._renderer
            profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
            settings = resolve_professor_llm_settings(
                profile,
                apply_endpoint_env_overrides=False,
            )
            api_key = settings.get("local_llm_api_key")
            if not api_key:
                raise ValueError("configured chat LLM API key is unavailable")
            model = str(settings["local_llm_model"])
            timeout = max(
                5.0,
                float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "30")),
            )
            self._renderer = _OpenAIProseRenderer(
                client=OpenAI(
                    base_url=settings["local_llm_base_url"],
                    api_key=api_key,
                    timeout=timeout,
                    max_retries=0,
                ),
                model=model,
                extra_body=build_non_thinking_extra_body(model),
                page_fetcher=self._page_fetcher,
            )
            return self._renderer

    def __call__(self, result: Any) -> str | ProseSynthesisResult:
        try:
            timeout = max(
                5.0,
                float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "30")),
            )
            renderer = self._configured_renderer()
        except (
            ConnectionError,
            FutureTimeoutError,
            OpenAIError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise TimeoutError("LLM prose synthesis is unavailable") from exc

        try:
            future = _PROSE_RENDER_EXECUTOR.submit(renderer, result)
            return future.result(timeout=timeout)
        except (
            ConnectionError,
            FutureTimeoutError,
            OpenAIError,
            OSError,
            RuntimeError,
        ) as exc:
            raise TimeoutError("LLM prose synthesis is unavailable") from exc

    def stream(
        self, result: Any, *, on_chunk: Callable[[str], None]
    ) -> str | ProseSynthesisResult:
        try:
            renderer = self._configured_renderer()
        except (
            ConnectionError,
            FutureTimeoutError,
            OpenAIError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise TimeoutError("LLM prose synthesis is unavailable") from exc

        try:
            # The stream runs on the caller thread instead of the executor:
            # only the provider client's per-read timeout applies, so a stream
            # with continuous output is never cut by a whole-answer deadline.
            # A stalled first token still surfaces as TimeoutError (via the
            # client timeout), which the answer retry loop handles once.
            return renderer.stream(result, on_chunk=on_chunk)
        except (
            ConnectionError,
            FutureTimeoutError,
            OpenAIError,
            OSError,
            RuntimeError,
        ) as exc:
            raise TimeoutError("LLM prose synthesis is unavailable") from exc

    def __deepcopy__(self, memo: dict[int, Any]) -> _EnvironmentProseRenderer:
        # The provider client is process-scoped; only answer session state is forked.
        memo[id(self)] = self
        return self

    def warm(self) -> None:
        self._configured_renderer().warm()


def _warm_environment_llm() -> None:
    profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
    settings = resolve_professor_llm_settings(
        profile,
        apply_endpoint_env_overrides=False,
    )
    api_key = settings.get("local_llm_api_key")
    if not api_key:
        raise ValueError("configured chat LLM API key is unavailable")
    model = str(settings["local_llm_model"])
    timeout = max(5.0, float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "30")))
    OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=api_key,
        timeout=timeout,
        max_retries=0,
    ).chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=1,
        messages=[{"role": "user", "content": "ping"}],
        extra_body=build_non_thinking_extra_body(model),
    )


def _provider_keepwarm_cycle(
    *,
    operations: tuple[Callable[[], None], ...],
) -> Callable[[], None]:
    executor = ThreadPoolExecutor(
        max_workers=len(operations),
        thread_name_prefix="canonical-v2-provider-keepwarm",
    )

    def cycle() -> None:
        futures = tuple(executor.submit(operation) for operation in operations)
        for future in futures:
            try:
                future.result()
            except Exception:  # noqa: BLE001 - each warm path is best-effort
                continue

    return cycle


def _relationship_trace_anchor_id(trace: Any) -> str | None:
    """Displayed-anchor id proven by a relationship projection trace.

    The isolated read runtime writes exactly one displayed anchor onto each
    relationship trace (``displayed_entity_id`` /
    ``displayed_company_id`` / per-domain variants); ``displayed_entity_ids``
    is the common fallback for trace shapes without a single-name anchor.
    """
    for field_name in (
        "displayed_entity_id",
        "displayed_company_id",
        "displayed_patent_id",
        "displayed_professor_id",
        "displayed_paper_id",
    ):
        anchor_id = getattr(trace, field_name, None)
        if isinstance(anchor_id, str) and anchor_id:
            return anchor_id
    entity_ids = getattr(trace, "displayed_entity_ids", ())
    if isinstance(entity_ids, tuple):
        for entity_id in entity_ids:
            if isinstance(entity_id, str) and entity_id:
                return entity_id
    return None


def _answer_selector(
    *,
    bundle: RecordedServingBundle,
) -> Callable[[TurnRequest], AnswerSelectionProposal]:
    def select(request: TurnRequest) -> AnswerSelectionProposal:
        handles = request.evidence_set.entity_handles
        handle_by_evidence = {
            evidence_id: handle
            for handle in handles
            for evidence_id in handle.evidence_ids
        }
        enumeration = any(
            marker in request.query
            for marker in (
                "哪些",
                "谁",
                "多少",
                "几个",
                "几种",
                "列出",
                "所有",
                "分别",
                "推荐",
                "厂商",
                "供应商",
            )
        )
        preferred_objects = {
            item.object_id
            for item in request.evidence_set.items
            if item.lane in {"exact", "structured", "lexical"}
        }
        normalized_query = " ".join(request.query.casefold().split())
        search_view = _search_view(request.query)
        normalized_search_view = " ".join(search_view.casefold().split())
        exact_named_objects = {
            handle.canonical_id
            for handle in handles
            if handle.kind == "canonical"
            and (
                (normalized_name := " ".join(handle.display_name.casefold().split()))
                and (
                    normalized_name == normalized_search_view
                    or (
                        len(normalized_name) >= 8
                        and normalized_name in normalized_query
                    )
                )
            )
        }
        preferred_objects.update(exact_named_objects)
        focused_entity = search_view != request.query.strip().rstrip("？?。！!")
        if focused_entity and not preferred_objects:
            displayed_anchor_ids = frozenset(
                entity_id
                for slot in request.evidence_set.protected_slots
                if slot.kind == "displayed_entity_set"
                for entity_id in slot.entity_ids
            )
            eligible_items = tuple(
                item
                for item in request.evidence_set.items
                if item.source_nature == "current_web"
                # A named-entity traversal turn also has a focused search view
                # and no exact-lane hits; its release-bound relationship
                # claims are the answer itself, never focus noise — but only
                # when the item's trace proves it is bound to the turn's
                # displayed anchor, so cross-pool or untraceable relationship
                # candidates cannot answer.
                or (
                    item.lane == "relationship"
                    and displayed_anchor_ids
                    and _relationship_trace_anchor_id(item.local_projection_trace)
                    in displayed_anchor_ids
                )
            )
        else:
            eligible_items = tuple(
                item
                for item in request.evidence_set.items
                if item.source_nature == "current_web"
                or enumeration
                or not preferred_objects
                or item.object_id in preferred_objects
            )
        local_items = tuple(
            item for item in eligible_items if item.source_nature != "current_web"
        )
        web_items = tuple(
            item for item in eligible_items if item.source_nature == "current_web"
        )
        balanced_items: list[EvidenceItem] = []
        for index in range(max(len(local_items), len(web_items))):
            if index < len(local_items):
                balanced_items.append(local_items[index])
            if index < len(web_items):
                balanced_items.append(web_items[index])
        local_claim_limit = (
            # Enumeration answers may show a representative sixteen (the
            # coverage sentence discloses the rest); non-enumeration stays
            # tight.
            max(bundle.max_candidates, 16)
            if enumeration
            else min(bundle.max_candidates, 3)
        )
        web_claim_limit = (
            # Enumeration turns widen the web candidate window to cover the
            # discovery-view tails (九号 sits at merged rank 36-43); the
            # claim limit must follow the window or those web-only suppliers
            # never reach the prose model.
            _ENUMERATION_CANDIDATE_WINDOW
            if enumeration
            else bundle.max_web_results
        )
        claim_limit = local_claim_limit + web_claim_limit
        claims: list[MaterialClaimProposal] = []
        seen_objects: set[tuple[str, str]] = set()
        local_claim_count = 0
        web_claim_count = 0
        displayed_handle_ids: list[str] = []
        for item in balanced_items:
            binding = item.claim_binding
            source_group = (
                "current_web"
                if item.source_nature == "current_web"
                else "local"
            )
            seen_key = (item.object_id, source_group)
            if binding is None or seen_key in seen_objects:
                continue
            if source_group == "current_web":
                if web_claim_count >= web_claim_limit:
                    continue
                web_claim_count += 1
            else:
                if local_claim_count >= local_claim_limit:
                    continue
                local_claim_count += 1
            seen_objects.add(seen_key)
            handle = handle_by_evidence.get(item.evidence_id)
            display_name = handle.display_name if handle is not None else item.object_id
            claim_text = _semantic_text(item, display_name)
            # Content-farm/login-wall dumps are never answer content: dropping
            # them here keeps both the prose prompt small (large prompts made
            # the renderer fail its wire protocol) and the deterministic
            # fallback readable.
            if claim_text_is_raw_dump(claim_text):
                continue
            if _concept_theme_filter_active(
                request.query
            ) and _concept_off_topic_claim(claim_text):
                continue
            if handle is not None:
                handle_id = (
                    handle.canonical_id
                    if handle.kind == "canonical"
                    else handle.handle_id
                )
                if handle_id not in displayed_handle_ids:
                    displayed_handle_ids.append(handle_id)
            claims.append(
                MaterialClaimProposal(
                    claim_id=(
                        f"claim:serving:{request.turn_id}:"
                        f"{hashlib.sha256(item.evidence_id.encode()).hexdigest()[:16]}"
                    ),
                    text=claim_text,
                    subject_id=binding.subject_id,
                    predicate=binding.predicate,
                    value=binding.value,
                    evidence_ids=(item.evidence_id,),
                    status=binding.status,
                )
            )
            if len(claims) >= claim_limit:
                break
        return AnswerSelectionProposal(
            selection_input_sha256=request.content_sha256,
            schema_version="answer-selection-v1",
            decision_id=f"answer-selection:serving:{request.turn_id}",
            model_id=bundle.answer_model_id,
            prompt_version="canonical-v2-serving-answer-v1",
            decision_run_id=f"answer-selection-run:serving:{request.turn_id}",
            answer_text="Evidence-bound deterministic answer.",
            claims=tuple(claims),
            displayed_handle_ids=tuple(displayed_handle_ids),
            continuation_candidate_ids=tuple(
                candidate.candidate_id
                for candidate in request.evidence_set.continuation_candidates
            ),
        )

    return select


def _read_bundle(path: Path) -> RecordedServingBundle:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("serving bundle must be an explicit regular file")
    if path.stat().st_nlink != 1:
        raise ValueError("serving bundle must not be hard linked")
    try:
        return RecordedServingBundle.model_validate_json(
            path.read_bytes(),
            context={"external_content_addressed": True},
        )
    except (OSError, ValueError) as exc:
        raise ValueError("serving bundle is unreadable or has an invalid hash") from exc


def load_recorded_serving_inputs(
    *,
    path: Path,
    expected_content_sha256: str,
    expected_release_id: str,
    expected_database: str,
    expected_index_root: Path,
    expected_envelope_path: Path,
    embedding_adapter: Any,
    prose_renderer: Callable[[Any], Any] | None = None,
    page_fetcher: Callable[[str], str | None] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    llm_keepwarm: Callable[[], None] | None = None,
    query_rewriter: Callable[[str], tuple[str, ...]] | None = None,
) -> RecordedServingInputs:
    """Load one secret-free serving authority and bind it to runner-owned paths."""

    bundle = _read_bundle(path)
    if bundle.content_sha256 != expected_content_sha256:
        raise ValueError("serving bundle declared hash differs")
    if bundle.release_id != expected_release_id:
        raise ValueError("serving bundle release differs")
    if (
        bundle.database_name != expected_database
        or bundle.database_target_kind != "disposable"
    ):
        raise ValueError("serving bundle database differs")
    if (
        bundle.index_target_id != f"index:{expected_release_id}"
        or bundle.index_root != expected_index_root
    ):
        raise ValueError("serving bundle index target differs")
    if bundle.envelope_path != expected_envelope_path:
        raise ValueError("serving bundle envelope differs")
    if getattr(embedding_adapter, "model_id", None) != bundle.embedding_model_id:
        raise ValueError("serving bundle embedding model differs")

    supported_relationship_paths = (
        ("company_has_patent", "company_to_patent"),
        ("company_has_patent", "patent_to_company"),
        ("professor_authored_paper", "professor_to_paper"),
        ("professor_authored_paper", "paper_to_professor"),
        ("professor_company_role", "professor_to_company"),
        ("professor_company_role", "company_to_professor"),
    )
    planning_policy = QueryPlanningPolicy(
        policy_id=f"query-planning-policy:{bundle.release_id}",
        policy_version="canonical-v2-serving-planning-v1",
        public_domains=_PUBLIC_DOMAINS,
        supported_lanes=(
            "exact",
            "structured",
            "lexical",
            "vector",
            "relationship",
            "internal_reference",
            "web",
        ),
        supported_relationship_paths=supported_relationship_paths,
        # The ceiling must admit the enumeration window; ordinary proposals
        # still request the default bundle window.
        max_candidates=max(
            bundle.max_candidates + bundle.max_web_results,
            _ENUMERATION_CANDIDATE_WINDOW,
        ),
        max_provider_calls=2,
        max_planning_attempts=1,
    )
    provider_attempt_timeout = max(0.1, bundle.web_timeout_ms * 0.00045)
    query_view_store = _ServingQueryViewStore()
    selected_query_rewriter = (
        _ServingQueryRewriter() if query_rewriter is None else query_rewriter
    )
    web_search = _DualWebLaneAdapter(
        timeout_ms=bundle.web_timeout_ms,
        max_snapshot_bytes=bundle.web_snapshot_max_bytes,
        clock=clock,
        page_fetcher=page_fetcher,
        extra_view_queries=query_view_store.views_for,
        gap_judge=create_llm_judge(),
    )
    keepwarm_bocha = BochaSearchProvider(timeout=provider_attempt_timeout)
    keepwarm_serper = WebSearchProvider(timeout=provider_attempt_timeout)
    # The correction retry fetches reference pages through the same tiered
    # fetcher the web lane uses — one shared object, never a second fetcher.
    environment_renderer = _EnvironmentProseRenderer(page_fetcher=page_fetcher)
    selected_prose_renderer = prose_renderer or environment_renderer
    selected_llm_keepwarm = llm_keepwarm or (
        environment_renderer.warm
        if prose_renderer is None
        else _warm_environment_llm
    )

    def warm_bocha() -> None:
        keepwarm_bocha.search("深圳科技创新")

    def warm_serper() -> None:
        keepwarm_serper.search("深圳科技创新")

    def warm_embedding() -> None:
        embedding_adapter.embed_batch(
            (
                "canonical-v2-provider-keepwarm:"
                f"{int(clock().timestamp() // 300)}",
            )
        )

    warm_fetcher = getattr(page_fetcher, "warm", None)

    def warm_fetch() -> None:
        if warm_fetcher is not None:
            warm_fetcher()

    idle_keepwarm_cycle = _provider_keepwarm_cycle(
        operations=(
            warm_bocha,
            warm_serper,
            warm_embedding,
            warm_fetch,
            selected_llm_keepwarm,
        )
    )
    supplemental_budget = SupplementalBudget(
        # Wide enumerations run the full probe+fetch+judgment pipeline
        # (gap check ~2s + up to 24 concurrent probes ~3s + per-job judgment
        # batches + serial headless fetches ~5-10s), which needs ~30s worst
        # case; 10s produced receipt-exhausted integrity failures (409-class)
        # on exactly those turns. 30s is the serving-policy ceiling for that
        # pipeline, not a per-turn target.
        max_wall_time_ms=max(bundle.web_timeout_ms, 30_000),
        max_provider_calls=2,
        max_retries=0,
        # Room for the widest probe family: theme-verification probes across
        # the enumeration candidate window (16 x 0.5 cost units) plus the
        # person (discovery + 6) and relation (6) families at once (28 total
        # x 0.5 = 14.0); the receipt is checked against this ceiling by the
        # server-owned plan control, so it must bound the real worst case.
        max_cost_units=16.0,
    )
    sufficiency_decider, supplemental_search = (
        _create_serving_person_criteria_sufficiency_supplemental(
            web_lane=web_search,
            budget=supplemental_budget,
            clock=clock,
            max_snapshot_bytes=bundle.web_snapshot_max_bytes,
            judge=create_llm_judge(),
        )
    )
    warm_fetcher = getattr(page_fetcher, "warm", None)
    if warm_fetcher is not None:
        threading.Thread(
            target=warm_fetcher,
            name="canonical-v2-fetch-warm",
            daemon=True,
        ).start()
    return RecordedServingInputs(
        planning_policy=planning_policy,
        proposal_provider=_proposal_provider(
            bundle=bundle,
            query_rewriter=selected_query_rewriter,
            view_store=query_view_store,
        ),
        ambiguity_policy=AmbiguityPolicy(
            policy_id=f"ambiguity-policy:serving:{bundle.release_id}",
            policy_version=_SERVING_AMBIGUITY_POLICY_VERSION,
            entity_type=_SERVING_AMBIGUITY_ENTITY_TYPE,
            minimum_evidence_count=_SERVING_AMBIGUITY_MINIMUM_EVIDENCE_COUNT,
            confidence_threshold=_SERVING_AMBIGUITY_CONFIDENCE_THRESHOLD,
            minimum_lead_margin=_SERVING_AMBIGUITY_MINIMUM_LEAD_MARGIN,
        ),
        universal_web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=bundle.web_timeout_ms,
            max_results=bundle.max_web_results,
        ),
        web_search=web_search,
        web_snapshot_policy=WebSnapshotPolicy(
            policy_id=f"web-snapshot-policy:{bundle.release_id}",
            policy_version="canonical-v2-serving-web-snapshot-v1",
            max_bytes=bundle.web_snapshot_max_bytes,
        ),
        embedding_adapter=embedding_adapter,
        identity_fuser=None,
        reranker=_serving_reranker,
        sufficiency_decider=sufficiency_decider,
        supplemental_search=supplemental_search,
        web_handle_resolver=None,
        accepted_identity_lookup=None,
        answer_factory=lambda: create_ephemeral_knowledge_answer(
            answer_selector=_answer_selector(bundle=bundle),
            prose_renderer=selected_prose_renderer,
        ),
        answer_session_fork=deepcopy,
        gap_operations=create_ephemeral_knowledge_gap_feedback(clock=clock),
        supplemental_budget=supplemental_budget,
        authority_sha256=cast(str, bundle.content_sha256),
        idle_keepwarm_cycle=idle_keepwarm_cycle,
    )


__all__ = [
    "RecordedServingBundle",
    "RecordedServingInputs",
    "load_recorded_serving_inputs",
]
