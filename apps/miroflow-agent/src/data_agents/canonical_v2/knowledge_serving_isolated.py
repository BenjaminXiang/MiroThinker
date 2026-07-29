"""Content-addressed runtime inputs for one isolated Canonical V2 Candidate."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any, Literal, cast
from urllib.parse import urlparse, urlsplit, urlunsplit

from openai import OpenAI, OpenAIError
from pydantic import Field, ValidationInfo, field_validator, model_validator

from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.providers.bocha_search import BochaSearchProvider
from src.data_agents.providers.web_search import WebSearchProvider

from .contracts import ContractModel
from .knowledge_answer import (
    AnswerSelectionProposal,
    MaterialClaimProposal,
    TurnRequest,
    create_ephemeral_knowledge_answer,
)
from .knowledge_gap_feedback import create_ephemeral_knowledge_gap_feedback
from .knowledge_read import (
    EvidenceClaimBinding,
    EvidenceItem,
    LaneRequest,
    QueryPlanningPolicy,
    QueryPlanningRequest,
    QueryViewProposal,
    RecallCandidate,
    RecordedPlanningProposal,
    RerankProposal,
    RerankRequest,
    RelationshipPathProposal,
    RetrievalLaneResult,
    SupplementalBudget,
    WebEvidenceSnapshot,
    WebSearchPolicy,
    WebSnapshotPayload,
    WebSnapshotPolicy,
    _extract_protected_slots,
    _explicit_organization_name,
    _retention_values,
)


_ZERO_SHA256 = "0" * 64
_PUBLIC_DOMAINS = ("professor", "company", "paper", "patent")
_PROSE_RENDER_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="canonical-v2-prose",
)


def _institution_person_name(query: str) -> str | None:
    institution = r"(?:清华|北大|[\u4e00-\u9fff]{2,20}(?:大学|学院|研究院))"
    for pattern in (
        institution
        + r"(?:的)?(?P<name>[\u4e00-\u9fff·]{2,4})(?:教授|老师)?[？?。！!]?\Z",
        institution + r"(?:的)?(?P<name>[\u4e00-\u9fff·]{2,4}?)(?:教授|老师)?(?:的)?"
        r"(?=(?:评价|简介|信息|情况|研究方向|论文|专利))",
    ):
        match = re.search(pattern, query.strip())
        if match is not None:
            return match.group("name")
    return None


def _leading_company_name(query: str) -> str | None:
    match = re.match(
        r"^(?P<name>[\u4e00-\u9fffA-Za-z0-9（）()·-]{2,40}?)"
        r"(?=这家公司|(?:公司|企业)(?:情况|信息|简介))",
        query.strip(),
    )
    if match is None:
        return None
    name = match.group("name").strip()
    if any(marker in name for marker in ("哪些", "什么", "如何", "上述")):
        return None
    return name


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
    ambiguity_policy: None
    universal_web_policy: WebSearchPolicy
    web_search: Callable[[LaneRequest], RetrievalLaneResult]
    web_snapshot_policy: WebSnapshotPolicy
    embedding_adapter: Any
    identity_fuser: None
    reranker: Callable[[RerankRequest], RerankProposal]
    sufficiency_decider: None
    supplemental_search: None
    web_handle_resolver: None
    accepted_identity_lookup: None
    answer_factory: Callable[[], Any]
    answer_session_fork: Callable[[Any], Any]
    gap_operations: Any
    supplemental_budget: SupplementalBudget
    authority_sha256: str
    idle_keepwarm_cycle: Callable[[], None]


def _infer_domains(query: str) -> tuple[str, ...]:
    domains: set[str] = set()
    if _explicit_organization_name(query) is not None:
        domains.add("company")
    if _leading_company_name(query) is not None:
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
    if _institution_person_name(query) is not None:
        domains.add("professor")
    return tuple(domain for domain in _PUBLIC_DOMAINS if domain in domains) or (
        _PUBLIC_DOMAINS
    )


def _without_introduction_prefix(value: str) -> str:
    return re.sub(
        r"^(?:我关注的是|我说的是|我指的是|这里指的是|"
        r"(?:请问|请|麻烦|帮我)(?:介绍一下|介绍|了解一下|了解|查一下|查询|查)?|"
        r"介绍一下|介绍|我想了解|帮我查一下|帮我查)\s*",
        "",
        value,
    )


def _without_information_suffix(value: str) -> str:
    return re.sub(
        r"(?:的)?(?:相关)?(?:信息|资料|情况|介绍)\s*$",
        "",
        value,
    ).strip()


def _search_view(query: str) -> str:
    value = query.strip()
    if any(marker in value for marker in ("不要", "不包括", "排除", "除外")):
        return value
    identifier = re.search(r"\b(?:CN|WO|US|EP)[A-Z0-9.-]{5,}\b", value, re.I)
    if identifier is not None:
        return identifier.group(0)
    search_value = _without_information_suffix(_without_introduction_prefix(value))
    leading_company_name = _leading_company_name(search_value)
    if leading_company_name is not None:
        return leading_company_name
    company = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9（）()·-]{2,80}"
        r"(?:有限责任公司|股份有限公司|有限公司|公司))",
        search_value,
    )
    if company is not None:
        return company.group(1)
    professor = re.match(
        r"^(?:请问|请介绍|介绍一下|我想了解|帮我查(?:一下)?)?\s*"
        r"(?P<name>[\u4e00-\u9fffA-Za-z·]{2,40}?)(?:教授|老师)"
        r"(?:的)?(?:研究方向|简介|信息|论文|专利|公司|情况|资料).*$",
        value,
    )
    if professor is not None:
        return professor.group("name")
    institution_person_name = _institution_person_name(search_value)
    if institution_person_name is not None:
        return institution_person_name
    if re.fullmatch(r"[\u4e00-\u9fff·]{2,4}[？?。！!]?", search_value):
        return search_value.rstrip("？?。！!")
    return search_value.rstrip("？?。！!")


def _contextual_web_search_view(query: str) -> str:
    value = _search_view(query)
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
    if "刷卡" in value and "刷门禁" not in value:
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
    if "论文" in query and any(
        marker in query for marker in ("他", "她", "教授", "老师")
    ):
        return (
            RelationshipPathProposal(
                relationship_type_id="professor_authored_paper",
                direction="professor_to_paper",
                source_type="professor",
                target_type="paper",
            ),
        )
    if any(marker in query for marker in ("作者", "教授", "老师")) and any(
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
    if "专利" in query and any(marker in query for marker in ("它", "该公司", "这家")):
        return (
            RelationshipPathProposal(
                relationship_type_id="company_has_patent",
                direction="company_to_patent",
                source_type="company",
                target_type="patent",
            ),
        )
    if any(marker in query for marker in ("申请公司", "申请人", "哪个公司")):
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
            query_views=(
                QueryViewProposal(
                    view_id=f"view:serving:{request.request_id}",
                    kind="serving_search",
                    text=search_text,
                    original_query_sha256=request.original_query_sha256,
                    retained_protected_values=retained_values,
                    producer_kind="deterministic",
                    producer_version=bundle.planner_model_id,
                    bound_entity_ids=request.displayed_entity_ids,
                    bound_entity_names=request.displayed_entity_names,
                ),
            ),
            relationship_paths=relationship_paths,
            max_candidates=bundle.max_candidates + bundle.max_web_results,
            max_provider_calls=1,
            enumeration_mode=("representative" if relationship_paths else None),
            web_mode="universal",
            max_web_results=bundle.max_web_results,
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


def _normalized_web_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )


def _relaxed_serper_query(query: str) -> str:
    if query.startswith("("):
        _, separator, capability_query = query.partition(") ")
        if separator and capability_query:
            return capability_query
    entity_name, separator, remainder = query.partition(" ")
    if not separator:
        return query
    search_name = re.sub(r"(?:股份)?有限公司$", "", entity_name)
    if search_name == entity_name:
        return query
    search_name = re.sub(r"^[\u4e00-\u9fff]{2,4}市", "", search_name, count=1)
    search_name = re.sub(
        r"(?:(?:智能)?科技|(?:科学)?技术|自动化|机器人)$",
        "",
        search_name,
    )
    if len(search_name) < 2:
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
    ) -> None:
        self._timeout_ms = timeout_ms
        self._max_snapshot_bytes = max_snapshot_bytes
        self._clock = clock
        provider_attempt_timeout = max(0.1, self._timeout_ms * 0.00045)
        self._bocha = bocha or BochaSearchProvider(timeout=provider_attempt_timeout)
        self._serper = serper or WebSearchProvider(timeout=provider_attempt_timeout)
        self._executor = ThreadPoolExecutor(
            max_workers=2,
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
        return tuple(ordered)

    def __call__(self, request: LaneRequest) -> RetrievalLaneResult:
        query_text = re.sub(
            r"\s*\[lane=web\]\s*$",
            "",
            request.query_text,
        ).strip()
        organic = self._merged_results(query_text)
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
            )
            canonical_id = matched_entity[0] if matched_entity is not None else None
            display_name = matched_entity[1] if matched_entity is not None else title
            geography = next(
                (
                    slot.value
                    for slot in request.protected_slots
                    if slot.kind == "geography"
                    and slot.value
                    and slot.value in f"{title} {snippet}"
                ),
                None,
            )
            evidence_identity = {
                "request": request.content_sha256,
                "locator": locator,
                "snapshot": snapshot_id,
            }
            evidence_id = f"web-evidence:sha256:{_canonical_sha256(evidence_identity)}"
            observed_at = self._clock().astimezone(timezone.utc)
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
                    predicate=(
                        "geography" if geography is not None else "current_web_result"
                    ),
                    value=geography or snapshot_sha256,
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


def _normalized_web_identity(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def _web_identity_forms(value: str) -> tuple[str, ...]:
    normalized = _normalized_web_identity(value)
    forms = [normalized]
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "公司"):
        normalized_suffix = _normalized_web_identity(suffix)
        if normalized.endswith(normalized_suffix):
            shortened = normalized[: -len(normalized_suffix)]
            if len(shortened) >= 4:
                forms.append(shortened)
            break
    return tuple(dict.fromkeys(form for form in forms if form))


def _matched_bound_entity(
    *,
    request: LaneRequest,
    title: str,
    snippet: str,
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
        and any(form in searchable for form in _web_identity_forms(entity_name))
    )
    return matches[0] if len(matches) == 1 else None


def _serving_reranker(request: RerankRequest) -> RerankProposal:
    def candidate_key(candidate: Any) -> tuple[float, str]:
        return (-candidate.raw_score, candidate.result_id)

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
            in {"exact", "structured", "lexical", "relationship", "internal_reference"}
            for item in candidate.evidence
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


def _list_names(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names = [
        str(item.get("name") or "").strip()
        for item in value
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    return "、".join(names[:6])


def _semantic_text(item: EvidenceItem, display_name: str) -> str:
    if item.source_nature == "current_web":
        return f"{item.snippet}；来源：{item.source_locator}"
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
                return f"{relation_text} 公司简介：{profile.strip()}"
            return relation_text
    parts: list[str] = [name]
    if item.domain == "professor":
        for label, field in (
            ("机构", "institution"),
            ("职称", "title"),
            ("简介", "profile_summary"),
        ):
            value = payload.get(field)
            if isinstance(value, str) and value.strip() and value.strip() != name:
                parts.append(f"{label}：{value.strip()}")
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
                parts.append(f"{label}：{value.strip()}")
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


class _OpenAIProseRenderer:
    def __init__(self, *, client: Any, model: str, extra_body: dict[str, Any]) -> None:
        self._client = client
        self._model = model
        self._extra_body = extra_body

    def __call__(self, result: Any) -> str:
        context = getattr(result, "context_receipt", None)
        active_anchor = getattr(context, "active_anchor", None)
        displayed_set = getattr(context, "displayed_result_set", None)
        citation_by_evidence_id = {
            citation.evidence_id: citation
            for citation in getattr(result, "citations", ())
        }
        payload = {
            "prompt_version": "canonical-v2-prose-v3",
            "user_question": getattr(result, "original_query", None),
            "active_entity": (
                None
                if active_anchor is None
                else {
                    "name": active_anchor.display_name,
                    "domain": active_anchor.domain,
                }
            ),
            "displayed_entities": [
                {"name": handle.display_name, "domain": handle.domain}
                for handle in (() if displayed_set is None else displayed_set.handles)
            ],
            "relationship_paths": list(
                () if context is None else context.traversed_path_ids
            ),
            "supported_claims": [
                {
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
                for claim in result.claims
            ],
        }
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=1200,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是深圳科创信息助手。输入中的主张是有证据约束的候选材料，不代表每条都与"
                        "问题相关；先判断相关性，再只使用相关材料围绕用户问题回答。先直接给出结论，"
                        "再按主体或关系组织必要补充；综合本地与网页材料，合并同义和重复信息，不要"
                        "复制原始字段或搜索摘要，不要逐字段复述，不要输出“简介”“技术路线”等数据"
                        "字段标签。关系问题必须明确写出"
                        "人物、关系角色和目标实体。产品能力只有在同一材料明确绑定具体产品与具体能力"
                        "时才能确认；公司通用能力、其他产品或外围系统集成不能替代，并应区分机器人"
                        "直接操作物理控件与通过楼宇或物联网接口集成。专利或公司技术不是产品名称；"
                        "用户问‘哪些产品’时必须给出材料中与该能力直接绑定的具体产品名，否则明确"
                        "说明只确认到公司或技术层。总部地点必须有材料明确写出总部关系，不能从"
                        "公司名称、分支机构或服务地点推断总部。对“上述/这些”集合问题，说明"
                        "哪些主体有直接支持，并对其余主体作简短限定。不要输出内部ID、检索流程、证据"
                        "元数据或输入中未提供的事实。评估全部相关材料后仍不足时再明确说明，不要猜测。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            extra_body=self._extra_body,
        )
        choices = getattr(response, "choices", ())
        content = (
            None
            if not choices
            else getattr(getattr(choices[0], "message", None), "content", None)
        )
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM prose response is empty")
        rendered = content.strip()
        founder_supported = any(
            claim.predicate == "professor_company_role" and "参与创立" in claim.text
            for claim in result.claims
        )
        if founder_supported and "参与创立" not in rendered:
            handles = (() if active_anchor is None else (active_anchor,)) + (
                () if displayed_set is None else displayed_set.handles
            )
            professor_name = next(
                (
                    handle.display_name
                    for handle in handles
                    if handle.domain == "professor"
                ),
                None,
            )
            company_name = next(
                (
                    handle.display_name
                    for handle in handles
                    if handle.domain == "company"
                ),
                None,
            )
            if professor_name is not None and company_name is not None:
                rendered = f"{professor_name}参与创立了{company_name}。\n\n{rendered}"
        return rendered

    def warm(self) -> None:
        self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
            extra_body=self._extra_body,
        )


class _EnvironmentProseRenderer:
    def __init__(self) -> None:
        self._renderer: _OpenAIProseRenderer | None = None
        self._renderer_lock = Lock()

    def _configured_renderer(self) -> _OpenAIProseRenderer:
        with self._renderer_lock:
            if self._renderer is not None:
                return self._renderer
            profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
            settings = resolve_professor_llm_settings(profile)
            api_key = settings.get("local_llm_api_key")
            if not api_key:
                raise ValueError("configured chat LLM API key is unavailable")
            model = str(settings["local_llm_model"])
            timeout = max(
                5.0,
                float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "12")),
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
            )
            return self._renderer

    def __call__(self, result: Any) -> str:
        try:
            timeout = max(
                5.0,
                float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "12")),
            )
            renderer = self._configured_renderer()
            future = _PROSE_RENDER_EXECUTOR.submit(renderer, result)
            return future.result(timeout=timeout)
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

    def __deepcopy__(self, memo: dict[int, Any]) -> _EnvironmentProseRenderer:
        # The provider client is process-scoped; only answer session state is forked.
        memo[id(self)] = self
        return self

    def warm(self) -> None:
        self._configured_renderer().warm()


def _warm_environment_llm() -> None:
    profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
    settings = resolve_professor_llm_settings(profile)
    api_key = settings.get("local_llm_api_key")
    if not api_key:
        raise ValueError("configured chat LLM API key is unavailable")
    model = str(settings["local_llm_model"])
    timeout = max(5.0, float(os.getenv("CHAT_LLM_TIMEOUT_SECONDS", "12")))
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
            eligible_items = tuple(
                item
                for item in request.evidence_set.items
                if item.source_nature == "current_web"
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
            bundle.max_candidates if enumeration else min(bundle.max_candidates, 3)
        )
        web_claim_limit = bundle.max_web_results
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
                    text=_semantic_text(item, display_name),
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
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    llm_keepwarm: Callable[[], None] | None = None,
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
        max_candidates=bundle.max_candidates + bundle.max_web_results,
        max_provider_calls=2,
        max_planning_attempts=1,
    )
    provider_attempt_timeout = max(0.1, bundle.web_timeout_ms * 0.00045)
    web_search = _DualWebLaneAdapter(
        timeout_ms=bundle.web_timeout_ms,
        max_snapshot_bytes=bundle.web_snapshot_max_bytes,
        clock=clock,
    )
    keepwarm_bocha = BochaSearchProvider(timeout=provider_attempt_timeout)
    keepwarm_serper = WebSearchProvider(timeout=provider_attempt_timeout)
    environment_renderer = _EnvironmentProseRenderer()
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

    idle_keepwarm_cycle = _provider_keepwarm_cycle(
        operations=(
            warm_bocha,
            warm_serper,
            warm_embedding,
            selected_llm_keepwarm,
        )
    )
    return RecordedServingInputs(
        planning_policy=planning_policy,
        proposal_provider=_proposal_provider(bundle=bundle),
        ambiguity_policy=None,
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
        sufficiency_decider=None,
        supplemental_search=None,
        web_handle_resolver=None,
        accepted_identity_lookup=None,
        answer_factory=lambda: create_ephemeral_knowledge_answer(
            answer_selector=_answer_selector(bundle=bundle),
            prose_renderer=selected_prose_renderer,
        ),
        answer_session_fork=deepcopy,
        gap_operations=create_ephemeral_knowledge_gap_feedback(clock=clock),
        supplemental_budget=SupplementalBudget(
            max_wall_time_ms=bundle.web_timeout_ms,
            max_provider_calls=2,
            max_retries=0,
            max_cost_units=2.0,
        ),
        authority_sha256=cast(str, bundle.content_sha256),
        idle_keepwarm_cycle=idle_keepwarm_cycle,
    )


__all__ = [
    "RecordedServingBundle",
    "RecordedServingInputs",
    "load_recorded_serving_inputs",
]
