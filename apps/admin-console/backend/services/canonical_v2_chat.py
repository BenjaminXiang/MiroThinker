"""Release-bound Canonical V2 chat orchestration behind the HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import ipaddress
import json
from threading import RLock
from typing import Any, Callable, Literal, Protocol, cast
from urllib.parse import urlparse, urlsplit, urlunsplit

from pydantic import Field, model_validator

from backend.api.chat_contracts import (
    CandidateOption,
    ChatCitation,
    ChatResponse,
    ClarificationPayload,
    TargetDomain,
)
from src.data_agents.canonical_v2.contracts import ContractModel
from src.data_agents.canonical_v2.followup_referents import (
    has_continuation_intent,
    has_explicit_named_subject,
    has_internal_set_antecedent,
    has_set_referent,
    has_singular_referent,
    referent_subject_domain,
)
from src.data_agents.canonical_v2.knowledge_answer import (
    ContinuationOffer,
    ContinuationSelection,
    ContextReceipt,
    KnowledgeAnswer,
    SafetyGuidanceDirective,
    SessionDirective,
    TurnRequest,
    TurnResult,
)
from src.data_agents.canonical_v2.knowledge_read import (
    CanonicalEntityHandle,
    EnumerationPlanningContext,
    EvidenceItem,
    EvidenceSet,
    QueryPlanningRequest,
    RetrievalPlan,
    WebEntityHandle,
)


_ZERO_SHA256 = "0" * 64
_PUBLIC_DOMAINS = frozenset({"professor", "company", "paper", "patent"})
_ENUMERATION_MARKERS = ("哪些", "谁", "多少", "几个", "列出", "所有", "分别")
_OFFICIAL_URL_FIELDS = {
    "professor": ("homepage",),
    "company": ("website",),
    "paper": ("url", "source_url", "publisher_url", "doi"),
    "patent": ("official_url", "source_url", "url"),
}
_PUBLIC_CONTINUATION_REASON = {
    "broad_scope": "可进一步缩小当前结果范围",
    "ambiguity": "可切换到其他有证据支持的候选实体",
    "partial_coverage": "当前覆盖仍不完整",
    "evidence_gap": "当前问题仍有证据缺口",
    "budget_exhausted": "本轮检索预算已用尽",
    "eligible_next_hop": "可继续探索已验证的关联",
}
_PUBLIC_CONTINUATION_OPERATION = {
    "narrow_scope": "缩小当前结果范围",
    "select_candidate": "选择候选实体",
    "switch_candidate": "切换候选实体",
    "continue_coverage": "继续补充覆盖",
    "targeted_evidence_search": "继续检索针对性证据",
    "resume_bounded_search": "继续有界检索",
    "traverse_relationship": "探索已验证关联",
}


class CanonicalV2InvalidOption(ValueError):
    """A caller supplied no exact active option for its cookie session."""


class CanonicalV2ReleaseMismatch(ValueError):
    """A validated stage crossed the adapter's explicit release boundary."""


class CanonicalV2MappingError(ValueError):
    """Validated stage output cannot be represented by the compatibility envelope."""


class _Planner(Protocol):
    def plan(self, request: QueryPlanningRequest) -> RetrievalPlan: ...


class _KnowledgeRead(Protocol):
    def execute(self, plan: RetrievalPlan) -> EvidenceSet: ...


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


def _validated_model(value: Any, model_type: type[Any]) -> Any:
    if isinstance(value, model_type):
        return model_type.model_validate(value.model_dump(mode="json"))
    return model_type.model_validate(value)


def _handle_id(handle: CanonicalEntityHandle | WebEntityHandle) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def _enumeration_context(
    *, query: str, displayed_ids: tuple[str, ...], as_of: datetime
) -> EnumerationPlanningContext | None:
    if not displayed_ids or not any(marker in query for marker in _ENUMERATION_MARKERS):
        return None
    return EnumerationPlanningContext(
        requested=True,
        scope=query,
        as_of=as_of,
        finite_universe=None,
    )


def _planning_displayed_ids(
    *,
    query: str,
    displayed_ids: tuple[str, ...],
    active_anchor_id: str | None,
    active_anchor_name: str | None = None,
    active_anchor_domain: str | None = None,
) -> tuple[str, ...]:
    if not displayed_ids:
        return ()
    # An explicitly named subject that is NOT the anchor always wins over
    # referent binding: "华力创科学这家公司…" asks about 华力创科学, not
    # about whatever the session happens to be anchored on.
    if has_explicit_named_subject(query) and not (
        active_anchor_name is not None and active_anchor_name in query
    ):
        return ()
    if has_singular_referent(query):
        if active_anchor_id is None:
            return ()
        # A typed referent (他/她 → person, 该公司 → company) must not bind an
        # anchor of another kind just because it is current; the miss falls
        # through to the referent history instead.
        subject_domain = referent_subject_domain(query)
        if (
            subject_domain is not None
            and active_anchor_domain is not None
            and subject_domain != active_anchor_domain
        ):
            return ()
        return (active_anchor_id,)
    if has_set_referent(query):
        return displayed_ids
    if has_continuation_intent(query):
        return (active_anchor_id,) if active_anchor_id is not None else ()
    if (
        active_anchor_id is not None
        and active_anchor_name is not None
        and active_anchor_name in query
    ):
        return (active_anchor_id,)
    return ()


@dataclass(frozen=True, slots=True)
class _ReferentHistoryEntry:
    """A referent archived when a topic switch replaced the session that held it."""

    kind: Literal["anchor", "result_set"]
    domain: str | None
    canonical_ids: tuple[str, ...]
    display_names: tuple[str, ...]
    turn_count: int


_REFERENT_HISTORY_LIMIT = 4


def _history_displayed_ids(
    *,
    query: str,
    history: tuple[_ReferentHistoryEntry, ...],
) -> tuple[str, ...]:
    """Bind an explicit anaphora to the first compatible history entry.

    A clean new-topic query carries no anaphoric marker and binds nothing, so
    it stays a pure topic switch. With a marker, the walk is most-recent-first
    over kind-compatible entries; a typed referent (他/她 → person, 这些公司 →
    company) only binds an entry whose domain matches (a domain-less entry
    carries no type evidence and stays compatible), never a different domain.
    """
    if has_singular_referent(query):
        kind = "anchor"
    elif has_set_referent(query):
        kind = "result_set"
    elif has_continuation_intent(query):
        kind = "anchor"
    else:
        return ()
    subject_domain = referent_subject_domain(query)
    for entry in history:
        if entry.kind != kind:
            continue
        if (
            subject_domain is not None
            and entry.domain is not None
            and entry.domain != subject_domain
        ):
            continue
        return entry.canonical_ids
    return ()


def _next_referent_history(
    *,
    committed: _CommittedSession | None,
    directive: SessionDirective | None,
) -> tuple[_ReferentHistoryEntry, ...]:
    """Referent history for the next committed session.

    Non-switch commits carry the history through unchanged; a topic-switch
    commit archives the outgoing session's live referents ahead of it, bounded
    to the most recent entries.
    """
    if committed is None:
        return ()
    history = committed.referent_history
    if directive is None or directive.transition != "topic_switch":
        return history
    context = committed.context_receipt
    if context is None:
        return history
    archived: list[_ReferentHistoryEntry] = []
    if context.active_anchor is not None:
        archived.append(
            _ReferentHistoryEntry(
                kind="anchor",
                domain=context.active_anchor.domain,
                canonical_ids=(_handle_id(context.active_anchor),),
                display_names=(context.active_anchor.display_name,),
                turn_count=committed.turn_count,
            )
        )
    if context.displayed_result_set is not None:
        handles = tuple(
            handle
            for handle in context.displayed_result_set.handles
            if handle.kind == "canonical"
        )
        if handles:
            domains = {handle.domain for handle in handles}
            archived.append(
                _ReferentHistoryEntry(
                    kind="result_set",
                    domain=next(iter(domains)) if len(domains) == 1 else None,
                    canonical_ids=tuple(handle.canonical_id for handle in handles),
                    display_names=tuple(handle.display_name for handle in handles),
                    turn_count=committed.turn_count,
                )
            )
    return tuple(archived + list(history))[:_REFERENT_HISTORY_LIMIT]


def _referent_clarification_needed(
    *,
    query: str,
    committed: _CommittedSession | None,
) -> bool:
    """A referent with no resolvable target must clarify, never free-retrieve.

    Fires when the query carries a singular or set referent but neither the
    session nor its archived referent history has an anchor/displayed set to
    bind it to and the query itself names no explicit subject. Free retrieval
    in that state answers about an arbitrary entity.
    """
    context = None if committed is None else committed.context_receipt
    history: tuple[_ReferentHistoryEntry, ...] = (
        () if committed is None else getattr(committed, "referent_history", ())
    )
    if (has_singular_referent(query) or has_continuation_intent(query)) and (
        context is None or context.active_anchor is None
    ):
        return not has_explicit_named_subject(query) and not _history_displayed_ids(
            query=query, history=history
        )
    if has_set_referent(query) and (
        context is None or context.displayed_result_set is None
    ):
        # A set referent with an intra-query antecedent ("…厂商，他们…") is
        # self-resolving; it never needs the session or the history.
        return (
            not has_explicit_named_subject(query)
            and not has_internal_set_antecedent(query)
            and not _history_displayed_ids(query=query, history=history)
        )
    return False


_REFERENT_CLARIFICATION_PROMPT = (
    "您的问题里使用了指代词，但当前对话还没有可对应的主体。"
    "请先告诉我您想了解的对象（如教授姓名、公司名、论文标题或专利号），"
    "我再继续回答。"
)


def _referent_clarification_response(query: str) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "query": query,
            "query_type": "canonical_v2:G:clarification_only",
            "answer_text": _REFERENT_CLARIFICATION_PROMPT,
            "citations": [],
            "evidence": [],
            "clarification": ClarificationPayload(
                prompt=_REFERENT_CLARIFICATION_PROMPT,
                options=[],
                default_id="",
                omitted=0,
            ).model_dump(mode="json"),
            "structured_payload": {},
            "answer_style": "template",
            "citation_map": {},
            "suggested_followups": [],
        }
    )


def _planning_displayed_names(
    *,
    context: ContextReceipt | None,
    displayed_ids: tuple[str, ...],
    history: tuple[_ReferentHistoryEntry, ...] = (),
) -> tuple[str, ...]:
    if not displayed_ids:
        return ()
    names_by_id: dict[str, str] = {}
    for entry in history:
        names_by_id.update(zip(entry.canonical_ids, entry.display_names))
    if context is not None:
        handles = []
        if context.active_anchor is not None:
            handles.append(context.active_anchor)
        if context.displayed_result_set is not None:
            handles.extend(context.displayed_result_set.handles)
        names_by_id.update(
            {_handle_id(handle): handle.display_name for handle in handles}
        )
    if any(entity_id not in names_by_id for entity_id in displayed_ids):
        return ()
    return tuple(names_by_id[entity_id] for entity_id in displayed_ids)


def _session_bound_plan(*, plan: RetrievalPlan, session_id: str) -> RetrievalPlan:
    return RetrievalPlan.model_validate(
        {
            **plan.model_dump(mode="json", exclude={"content_sha256"}),
            "session_id": session_id,
        }
    )


def _public_url(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.casefold().startswith("doi:"):
        text = f"https://doi.org/{text[4:].strip()}"
    elif text.startswith("10.") and "/" in text:
        text = f"https://doi.org/{text}"
    try:
        parsed = urlparse(text)
        hostname = (parsed.hostname or "").strip().casefold()
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or hostname == "localhost"
            or hostname.endswith((".localhost", ".local", ".internal"))
        ):
            return None
        try:
            if not ipaddress.ip_address(hostname).is_global:
                return None
        except ValueError:
            pass
        return parsed.geturl()
    except ValueError:
        return None


def _official_evidence_url(item: EvidenceItem) -> str | None:
    if item.source_nature == "current_web":
        if item.source_authority != "official":
            return None
        return _public_url(item.source_locator)
    try:
        payload = json.loads(item.snippet)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    for field in _OFFICIAL_URL_FIELDS.get(item.domain, ()):
        url = _public_url(payload.get(field))
        if url is not None:
            return url
    return None


def _official_host_scope(value: str) -> str | None:
    public_url = _public_url(value)
    if public_url is None:
        return None
    hostname = (urlparse(public_url).hostname or "").casefold()
    return hostname[4:] if hostname.startswith("www.") else hostname


def _current_web_url_for_official_hosts(
    item: EvidenceItem,
    *,
    official_hosts: frozenset[str],
) -> str | None:
    if item.source_nature != "current_web":
        return None
    public_url = _public_url(item.source_locator)
    if public_url is None:
        return None
    hostname = _official_host_scope(public_url)
    if hostname is None or not any(
        hostname == official_host or hostname.endswith(f".{official_host}")
        for official_host in official_hosts
    ):
        return None
    return public_url


class ChatFeedbackCheckpoint(ContractModel):
    session_id: str
    turn_id: str
    release_id: str
    query_trace_id: str
    answer_trace_id: str
    evidence_ids: tuple[str, ...]
    affected_domains: tuple[str, ...]
    affected_paths: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    observed_at: datetime
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bind_content(self) -> ChatFeedbackCheckpoint:
        expected = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected}:
            raise ValueError("content_sha256 must bind the complete checkpoint")
        object.__setattr__(self, "content_sha256", expected)
        return self


@dataclass(frozen=True, slots=True)
class _CanonicalV2ChatOutcome:
    query: str
    plan: RetrievalPlan
    evidence_set: EvidenceSet
    turn_result: TurnResult


@dataclass(frozen=True, slots=True)
class _CommittedSession:
    answer: KnowledgeAnswer
    turn_count: int
    context_receipt: ContextReceipt | None
    active_offer: ContinuationOffer | None
    displayed_ids: tuple[str, ...]
    checkpoint: ChatFeedbackCheckpoint
    prior_web_items: tuple[EvidenceItem, ...] = ()
    referent_history: tuple[_ReferentHistoryEntry, ...] = ()


_SESSION_WEB_CARRYOVER_LIMIT = 8


def _normalized_web_url(value: str) -> str:
    """URL identity used for session carry-over dedup.

    Mirrors ``knowledge_serving_isolated._normalized_web_url`` so carried items
    dedup exactly the way the web lane dedups its own results.
    """
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )


def _session_web_items(evidence_set: EvidenceSet) -> tuple[EvidenceItem, ...]:
    """Newest-first web lane items retained for bounded session carry-over."""
    seen: set[str] = set()
    retained: list[EvidenceItem] = []
    for item in evidence_set.items:
        if item.lane != "web":
            continue
        key = _normalized_web_url(item.source_locator)
        if key in seen:
            continue
        seen.add(key)
        retained.append(item)
        if len(retained) >= _SESSION_WEB_CARRYOVER_LIMIT:
            break
    return tuple(retained)


def _merge_prior_web_evidence(
    *,
    committed: _CommittedSession | None,
    evidence_set: EvidenceSet,
    directive: SessionDirective | None,
) -> EvidenceSet:
    """Carry prior session web evidence into a continuing follow-up turn.

    The fresh read keeps precedence: carried items whose normalized URL already
    appears in the current items are dropped, so fresh content always wins a
    URL conflict. Carry-over is skipped on topic switches (a new topic must not
    inherit stale web evidence) and bounded by the retention cap, so the merged
    set exceeds the read's own candidate window by at most the carried items.
    All carried items keep their original provenance (locator, authority,
    snapshot), and the TurnRequest content hash is rebound by its own model
    validator when the adapter builds the request.
    """
    if (
        committed is None
        or not committed.prior_web_items
        or (directive is not None and directive.transition == "topic_switch")
    ):
        return evidence_set
    current_urls = {
        _normalized_web_url(item.source_locator) for item in evidence_set.items
    }
    carried = tuple(
        item
        for item in committed.prior_web_items
        if _normalized_web_url(item.source_locator) not in current_urls
    )
    if not carried:
        return evidence_set
    merged = evidence_set.model_copy(
        update={"items": evidence_set.items + carried}
    )
    return _validated_model(merged, EvidenceSet)


class CanonicalV2ChatAdapter:
    """One explicit release with copy-on-write answer-session commits."""

    def __init__(
        self,
        *,
        release_id: str,
        planner: _Planner,
        knowledge_read: _KnowledgeRead,
        answer_factory: Callable[[], KnowledgeAnswer],
        answer_session_fork: Callable[[KnowledgeAnswer], KnowledgeAnswer],
    ) -> None:
        if not release_id.strip():
            raise ValueError("release_id must be explicit")
        self._release_id = release_id
        self._planner = planner
        self._knowledge_read = knowledge_read
        self._answer_factory = answer_factory
        self._answer_session_fork = answer_session_fork
        self._sessions: dict[str, _CommittedSession] = {}
        self._session_locks: dict[str, RLock] = {}
        self._lock = RLock()

    def get_feedback_checkpoint(self, session_id: str) -> ChatFeedbackCheckpoint | None:
        with self._session_lock(session_id):
            with self._lock:
                committed = self._sessions.get(session_id)
                return None if committed is None else committed.checkpoint

    def _session_lock(self, session_id: str) -> RLock:
        with self._lock:
            return self._session_locks.setdefault(session_id, RLock())

    def answer(
        self,
        *,
        query: str,
        session_id: str,
        option_id: str | None,
        as_of: datetime,
    ) -> ChatResponse:
        with self._session_lock(session_id):
            return self._answer_locked(
                query=query,
                session_id=session_id,
                option_id=option_id,
                as_of=as_of,
                progress=None,
            )

    def answer_stream(
        self,
        *,
        query: str,
        session_id: str,
        option_id: str | None,
        as_of: datetime,
        progress: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ChatResponse:
        """One turn with an optional per-call progress callback.

        Kept separate from ``answer`` so the frozen S11A input boundary stays
        exact; the callback is per-call state, never shared instance state.
        """
        with self._session_lock(session_id):
            return self._answer_locked(
                query=query,
                session_id=session_id,
                option_id=option_id,
                as_of=as_of,
                progress=progress,
            )

    def _answer_locked(
        self,
        *,
        query: str,
        session_id: str,
        option_id: str | None,
        as_of: datetime,
        progress: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ChatResponse:
        def emit(name: str, payload: dict[str, Any]) -> None:
            if progress is not None:
                progress(name, payload)

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be non-empty")
        if not session_id.strip():
            raise ValueError("session_id must be non-empty")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        observed_as_of = as_of.astimezone(UTC)

        with self._lock:
            committed = self._sessions.get(session_id)
        selection = self._selection(committed, option_id=option_id)
        if selection is None and _referent_clarification_needed(
            query=normalized_query,
            committed=committed,
        ):
            return _referent_clarification_response(normalized_query)
        turn_count = 1 if committed is None else committed.turn_count + 1
        turn_id = self._turn_id(
            session_id=session_id,
            turn_count=turn_count,
            query=normalized_query,
            option_id=option_id,
        )
        prior_displayed_ids = () if committed is None else committed.displayed_ids
        prior_context = None if committed is None else committed.context_receipt
        active_anchor_id = (
            None
            if prior_context is None or prior_context.active_anchor is None
            else _handle_id(prior_context.active_anchor)
        )
        selection_target_ids = self._selection_target_ids(committed, selection)
        ids_from_history = False
        if selection_target_ids:
            # A continuation selection replaces (never narrows) the anchor: bind
            # the option's canonical targets into planning so retrieval fetches
            # their evidence and the answer session registers their handles
            # before the selection executes. This is what lets a same-name
            # switch_candidate target that was never displayed actually re-anchor.
            displayed_ids = selection_target_ids
        else:
            displayed_ids = _planning_displayed_ids(
                query=normalized_query,
                displayed_ids=prior_displayed_ids,
                active_anchor_id=active_anchor_id,
                active_anchor_name=(
                    None
                    if prior_context is None or prior_context.active_anchor is None
                    else prior_context.active_anchor.display_name
                ),
                active_anchor_domain=(
                    None
                    if prior_context is None or prior_context.active_anchor is None
                    else prior_context.active_anchor.domain
                ),
            )
            if not displayed_ids and committed is not None:
                # A topic switch replaced the session the anaphora refers to:
                # bind the archived referent history instead of free-retrieving.
                # Never when the query names its own subject — its referent
                # words are cataphoric, not session references.
                explicit_new_subject = has_explicit_named_subject(
                    normalized_query
                ) and not (
                    prior_context is not None
                    and prior_context.active_anchor is not None
                    and prior_context.active_anchor.display_name in normalized_query
                )
                if not explicit_new_subject:
                    history_ids = _history_displayed_ids(
                        query=normalized_query,
                        history=committed.referent_history,
                    )
                    if history_ids:
                        displayed_ids = history_ids
                        ids_from_history = True
        displayed_names = _planning_displayed_names(
            context=prior_context,
            displayed_ids=displayed_ids,
            history=() if committed is None else committed.referent_history,
        )
        planning_request = QueryPlanningRequest(
            request_id=f"query-request:chat:{turn_id}",
            release_id=self._release_id,
            original_query=normalized_query,
            as_of=observed_as_of,
            displayed_entity_ids=displayed_ids,
            displayed_entity_names=displayed_names,
            enumeration_context=_enumeration_context(
                query=normalized_query,
                displayed_ids=displayed_ids,
                as_of=observed_as_of,
            ),
        )

        emit("stage", {"name": "planning"})
        raw_plan = self._planner.plan(planning_request)
        self._require_release(raw_plan, stage="plan")
        plan = _validated_model(raw_plan, RetrievalPlan)
        self._require_release(plan, stage="plan")
        plan = _session_bound_plan(plan=plan, session_id=session_id)
        emit(
            "plan_done",
            {
                "lanes": list(plan.lanes),
                "domains": list(plan.domains),
                "views": [
                    view.text
                    for view in plan.query_views
                    if isinstance(getattr(view, "text", None), str)
                ],
            },
        )
        emit("stage", {"name": "retrieval"})

        raw_evidence_set = self._knowledge_read.execute(plan)
        self._require_release(raw_evidence_set, stage="read")
        evidence_set = _validated_model(raw_evidence_set, EvidenceSet)
        self._require_release(evidence_set, stage="read")
        emit(
            "retrieval_done",
            {
                "lanes": [
                    {
                        "lane": trace.lane,
                        "status": trace.status,
                        "candidates": trace.candidate_count,
                    }
                    for trace in evidence_set.traces
                    if isinstance(getattr(trace, "lane", None), str)
                ]
            },
        )
        emit("stage", {"name": "synthesis"})

        base_answer = self._answer_factory() if committed is None else committed.answer
        candidate_answer = self._answer_session_fork(base_answer)
        if progress is not None:
            # Token-level stream sink: the answer module duck-types renderers
            # exposing ``stream(result, *, on_chunk)`` and forwards each delta
            # as an ``answer_chunk`` event. Set on the forked instance that
            # actually answers and cleared before the session commit, so a
            # later synchronous turn can never stream into a stale callback.
            candidate_answer.prose_progress = lambda text: progress(
                "answer_chunk", {"text": text}
            )
        directive = self._session_directive(
            committed=committed,
            evidence_set=evidence_set,
            planning_displayed_ids=displayed_ids,
            selection=selection,
            from_history=ids_from_history,
        )
        evidence_set = _merge_prior_web_evidence(
            committed=committed,
            evidence_set=evidence_set,
            directive=directive,
        )
        turn_request = TurnRequest(
            session_id=session_id,
            turn_id=turn_id,
            query=normalized_query,
            release_id=self._release_id,
            evidence_set=evidence_set,
            assessment_intent=plan.assessment_intent,
            continuation_selection=selection,
            session_directive=directive,
            safety_guidance=(
                SafetyGuidanceDirective(mode="static")
                if plan.interaction_mode == "safety_guidance"
                else None
            ),
        )
        raw_turn_result = candidate_answer.answer(turn_request)
        self._require_release(raw_turn_result, stage="answer")
        turn_result = _validated_model(raw_turn_result, TurnResult)
        self._require_release(turn_result, stage="answer")
        if turn_result.session_id != session_id or turn_result.turn_id != turn_id:
            raise CanonicalV2MappingError(
                "answer result does not bind the requested session turn"
            )

        outcome = _CanonicalV2ChatOutcome(
            query=normalized_query,
            plan=plan,
            evidence_set=evidence_set,
            turn_result=turn_result,
        )
        response = self._map_response(outcome)
        checkpoint = self._checkpoint(
            session_id=session_id,
            evidence_set=evidence_set,
            turn_result=turn_result,
            fallback_observed_at=observed_as_of,
        )
        context_receipt = turn_result.context_receipt
        next_displayed_ids = self._displayed_ids(
            context_receipt,
            fallback=displayed_ids,
        )
        # Per-turn stream sink must not outlive this turn on the committed
        # session instance (the commit is the terminal statement, and any
        # earlier failure discards the fork, so no try/finally is needed).
        candidate_answer.prose_progress = None
        next_session = _CommittedSession(
            answer=candidate_answer,
            turn_count=turn_count,
            context_receipt=context_receipt,
            active_offer=turn_result.continuation_offer,
            displayed_ids=next_displayed_ids,
            checkpoint=checkpoint,
            prior_web_items=_session_web_items(evidence_set),
            referent_history=_next_referent_history(
                committed=committed,
                directive=directive,
            ),
        )

        with self._lock:
            self._sessions[session_id] = next_session
        return response

    def _selection(
        self,
        committed: _CommittedSession | None,
        *,
        option_id: str | None,
    ) -> ContinuationSelection | None:
        if option_id is None:
            return None
        offer = None if committed is None else committed.active_offer
        if offer is None or all(
            option.option_id != option_id for option in offer.options
        ):
            raise CanonicalV2InvalidOption(
                "option_id must bind one exact active continuation option"
            )
        return ContinuationSelection(
            offer_id=offer.offer_id,
            option_id=option_id,
        )

    @staticmethod
    def _selection_target_ids(
        committed: _CommittedSession | None,
        selection: ContinuationSelection | None,
    ) -> tuple[str, ...]:
        """Canonical target ids the selected option must bind into planning.

        Only explicit canonical targets qualify: result-set options resolve
        handles the session already registered, and session-scoped web handles
        are not retrievable recall targets.
        """
        if committed is None or selection is None:
            return ()
        offer = committed.active_offer
        if offer is None or offer.offer_id != selection.offer_id:
            return ()
        option = next(
            (
                value
                for value in offer.options
                if value.option_id == selection.option_id
            ),
            None,
        )
        if option is None or option.result_set_id is not None:
            return ()
        return tuple(
            handle_id
            for handle_id in option.target_handle_ids
            if handle_id and not handle_id.startswith("web-handle:")
        )

    def _require_release(self, value: Any, *, stage: str) -> None:
        if getattr(value, "release_id", None) != self._release_id:
            raise CanonicalV2ReleaseMismatch(
                f"{stage} result does not match the adapter release"
            )

    @staticmethod
    def _session_directive(
        *,
        committed: _CommittedSession | None,
        evidence_set: EvidenceSet,
        planning_displayed_ids: tuple[str, ...],
        selection: ContinuationSelection | None,
        from_history: bool = False,
    ) -> SessionDirective | None:
        if committed is None:
            return None
        if from_history:
            # A history-bound referent leaves the current topic for an earlier
            # one: the answer session must wipe and rebuild around the fresh
            # evidence, exactly like a fresh named-entity turn.
            return SessionDirective(transition="topic_switch")
        if evidence_set.requested_traversal is not None:
            context = committed.context_receipt
            if context is not None and context.active_anchor is not None:
                return SessionDirective(referent="active_anchor")
            if context is not None and context.displayed_result_set is not None:
                return SessionDirective(referent="displayed_result_set")
            return None
        if selection is None and not planning_displayed_ids:
            return SessionDirective(transition="topic_switch")
        return None

    @staticmethod
    def _turn_id(
        *,
        session_id: str,
        turn_count: int,
        query: str,
        option_id: str | None,
    ) -> str:
        digest = _canonical_sha256(
            {
                "session_id": session_id,
                "turn_count": turn_count,
                "query": query,
                "option_id": option_id,
            }
        )
        return f"turn:chat:sha256:{digest}"

    @staticmethod
    def _displayed_ids(
        context_receipt: ContextReceipt | None,
        *,
        fallback: tuple[str, ...],
    ) -> tuple[str, ...]:
        if (
            context_receipt is not None
            and context_receipt.displayed_result_set is not None
        ):
            return tuple(
                handle.canonical_id
                for handle in context_receipt.displayed_result_set.handles
                if handle.kind == "canonical"
            )
        return fallback

    def _map_response(self, outcome: _CanonicalV2ChatOutcome) -> ChatResponse:
        evidence_set = outcome.evidence_set
        turn_result = outcome.turn_result
        evidence_by_id = {item.evidence_id: item for item in evidence_set.items}
        retained_evidence_ids = tuple(evidence_by_id)
        retained_evidence_id_set = set(retained_evidence_ids)
        handles_by_id = {
            _handle_id(handle): handle for handle in evidence_set.entity_handles
        }

        claim_ids = {claim.claim_id for claim in turn_result.claims}
        if len(claim_ids) != len(turn_result.claims):
            raise CanonicalV2MappingError("answer contains duplicate claim IDs")
        mappings_by_id = {
            mapping.claim_id: mapping for mapping in turn_result.claim_evidence_map
        }
        if (
            len(mappings_by_id) != len(turn_result.claim_evidence_map)
            or set(mappings_by_id) != claim_ids
        ):
            raise CanonicalV2MappingError(
                "claim-evidence mappings do not close one-to-one over admitted claims"
            )
        for claim in turn_result.claims:
            if not set(claim.evidence_ids) <= retained_evidence_id_set:
                raise CanonicalV2MappingError(
                    "claim references evidence absent from KnowledgeRead"
                )
            mapping = mappings_by_id[claim.claim_id]
            if (
                mapping.subject_id,
                mapping.predicate,
                mapping.value,
                mapping.evidence_ids,
                mapping.status,
            ) != (
                claim.subject_id,
                claim.predicate,
                claim.value,
                claim.evidence_ids,
                claim.status,
            ):
                raise CanonicalV2MappingError(
                    "claim-evidence mapping differs from its admitted claim"
                )
            if not claim.evidence_ids:
                if not (
                    claim.claim_type == "product_capability"
                    and claim.outcome == "unsupported"
                    and claim.answer_scoped
                    and not claim.confirmed
                    and claim.subject_id is not None
                    and claim.subject_handle_ids == (claim.subject_id,)
                ):
                    raise CanonicalV2MappingError(
                        "evidence-free claim is not the typed unsupported Product claim"
                    )
                continue
            claim_evidence = tuple(
                evidence_by_id[evidence_id] for evidence_id in claim.evidence_ids
            )
            bindings = tuple(item.claim_binding for item in claim_evidence)
            if any(binding is None for binding in bindings):
                raise CanonicalV2MappingError(
                    "admitted claim evidence lacks a typed claim binding"
                )
            if claim.claim_type == "model_inference":
                continue
            if claim.outcome == "conflicting_evidence":
                if any(
                    binding is None
                    or binding.subject_id != claim.subject_id
                    or binding.predicate != claim.predicate
                    for binding in bindings
                ):
                    raise CanonicalV2MappingError(
                        "conflicting claim lacks matching typed lineage"
                    )
                continue
            if any(
                binding is None
                or (
                    binding.subject_id,
                    binding.predicate,
                    binding.value,
                    binding.status,
                )
                != (
                    claim.subject_id,
                    claim.predicate,
                    claim.value,
                    claim.status,
                )
                for binding in bindings
            ):
                raise CanonicalV2MappingError(
                    "claim differs from its admitted evidence binding"
                )
        if any(
            citation.evidence_id not in retained_evidence_id_set
            for citation in turn_result.citations
        ):
            raise CanonicalV2MappingError(
                "citation references evidence absent from KnowledgeRead"
            )

        public_citations = self._public_citations(
            turn_result=turn_result,
            handles_by_id=handles_by_id,
            evidence_by_id=evidence_by_id,
        )
        clarification = self._clarification(
            turn_result=turn_result,
            handles_by_id=handles_by_id,
        )
        response_payload = {
            "query": outcome.query,
            "query_type": (
                f"canonical_v2:{outcome.plan.behavior_class}:"
                f"{turn_result.response_mode}"
            ),
            "answer_text": turn_result.answer_text,
            "citations": [item.model_dump(mode="json") for item in public_citations],
            "evidence": [],
            "clarification": (
                None if clarification is None else clarification.model_dump(mode="json")
            ),
            "structured_payload": {},
            "answer_style": (
                "llm_synthesized"
                if turn_result.render_mode == "prose_renderer"
                else "template"
            ),
            "citation_map": {
                str(index): citation.id
                for index, citation in enumerate(public_citations, start=1)
            },
            "suggested_followups": (
                []
                if clarification is None
                else [option.label for option in clarification.options]
            ),
        }
        return ChatResponse.model_validate(response_payload)

    @staticmethod
    def _public_citations(
        *,
        turn_result: TurnResult,
        handles_by_id: dict[str, CanonicalEntityHandle | WebEntityHandle],
        evidence_by_id: dict[str, EvidenceItem],
    ) -> tuple[ChatCitation, ...]:
        handle_by_evidence_id: dict[str, tuple[str, Any]] = {}
        for handle_id, handle in handles_by_id.items():
            if handle.domain not in _PUBLIC_DOMAINS:
                continue
            for evidence_id in handle.evidence_ids:
                handle_by_evidence_id.setdefault(evidence_id, (handle_id, handle))
        cards: list[ChatCitation] = []
        seen: set[str] = set()
        official_hosts_by_handle_id: dict[str, frozenset[str]] = {}
        for citation in turn_result.citations:
            bound = handle_by_evidence_id.get(citation.evidence_id)
            evidence = evidence_by_id.get(citation.evidence_id)
            if bound is None or evidence is None:
                continue
            handle_id, handle = bound
            official_url = _official_evidence_url(evidence)
            if official_url is None and evidence.source_nature == "current_web":
                official_hosts = official_hosts_by_handle_id.get(handle_id)
                if official_hosts is None:
                    official_hosts = frozenset(
                        host
                        for evidence_id in handle.evidence_ids
                        if (bound_evidence := evidence_by_id.get(evidence_id)) is not None
                        and bound_evidence.source_nature != "current_web"
                        and (
                            local_official_url := _official_evidence_url(bound_evidence)
                        )
                        is not None
                        and (host := _official_host_scope(local_official_url))
                        is not None
                    )
                    official_hosts_by_handle_id[handle_id] = official_hosts
                official_url = _current_web_url_for_official_hosts(
                    evidence,
                    official_hosts=official_hosts,
                )
            if official_url is None or official_url in seen:
                continue
            seen.add(official_url)
            public_id = hashlib.sha256(official_url.encode("utf-8")).hexdigest()[:16]
            cards.append(
                ChatCitation(
                    type=handle.domain,
                    id=f"official-source-{public_id}",
                    label=handle.display_name,
                    url=official_url,
                )
            )
        return tuple(cards)

    @staticmethod
    def _clarification(
        *,
        turn_result: TurnResult,
        handles_by_id: dict[str, CanonicalEntityHandle | WebEntityHandle],
    ) -> ClarificationPayload | None:
        offer = turn_result.continuation_offer
        options: list[CandidateOption] = []
        omitted = 0
        if offer is not None:
            for option in offer.options[:3]:
                target_handles = tuple(
                    handles_by_id.get(handle_id)
                    for handle_id in option.target_handle_ids
                )
                domains = {
                    handle.domain
                    for handle in target_handles
                    if handle is not None and handle.domain in _PUBLIC_DOMAINS
                }
                if (
                    not option.target_handle_ids
                    or any(handle is None for handle in target_handles)
                    or len(domains) != 1
                ):
                    omitted += 1
                    continue
                options.append(
                    CandidateOption(
                        id=option.option_id,
                        domain=cast(TargetDomain, next(iter(domains))),
                        label=(
                            option.discriminator
                            or _PUBLIC_CONTINUATION_OPERATION.get(
                                option.operation, "继续当前问题"
                            )
                        ),
                        hint=(
                            option.discriminator
                            or _PUBLIC_CONTINUATION_OPERATION.get(
                                option.operation, "继续当前问题"
                            )
                        ),
                    )
                )
            omitted += max(0, len(offer.options) - 3)
        if not options and turn_result.response_mode != "clarification_only":
            return None
        prompt = (
            turn_result.answer_text
            if offer is None or not offer.reasons
            else " / ".join(
                _PUBLIC_CONTINUATION_REASON.get(reason, "可继续当前问题")
                for reason in offer.reasons
            )
        )
        return ClarificationPayload(
            prompt=prompt,
            options=options,
            default_id="",
            omitted=omitted,
        )

    @staticmethod
    def _trace(outcome: _CanonicalV2ChatOutcome) -> dict[str, Any]:
        evidence_set = outcome.evidence_set
        turn_result = outcome.turn_result

        def dumped(value: Any | None) -> Any:
            return None if value is None else value.model_dump(mode="json")

        return {
            "release_id": outcome.plan.release_id,
            "plan_id": outcome.plan.plan_id,
            "plan_version": outcome.plan.plan_version,
            "behavior_class": outcome.plan.behavior_class,
            "interaction_mode": outcome.plan.interaction_mode,
            "lanes": list(outcome.plan.lanes),
            "retrieval_traces": [
                item.model_dump(mode="json") for item in evidence_set.traces
            ],
            "constraint_receipts": [
                item.model_dump(mode="json")
                for item in evidence_set.constraint_receipts
            ],
            "fusion_receipt": dumped(evidence_set.fusion_receipt),
            "rerank_receipt": dumped(evidence_set.rerank_receipt),
            "sufficiency_report": dumped(evidence_set.sufficiency_report),
            "supplemental_budget_receipt": dumped(
                evidence_set.supplemental_budget_receipt
            ),
            "enumeration_coverage": dumped(turn_result.enumeration_coverage),
            "evidence_ids": [item.evidence_id for item in evidence_set.items],
            "evidence_source_natures": [
                item.source_nature for item in evidence_set.items
            ],
            "entity_handles": [
                handle.model_dump(mode="json") for handle in evidence_set.entity_handles
            ],
            "citations": [
                citation.model_dump(mode="json") for citation in turn_result.citations
            ],
            "claims": [claim.model_dump(mode="json") for claim in turn_result.claims],
            "claim_evidence_mappings": [
                mapping.model_dump(mode="json")
                for mapping in turn_result.claim_evidence_map
            ],
            "limitations": [
                limitation.model_dump(mode="json")
                for limitation in turn_result.limitations
            ],
            "conflicts": [
                conflict.model_dump(mode="json") for conflict in turn_result.conflicts
            ],
            "selector_traces": [
                trace.model_dump(mode="json") for trace in turn_result.selector_traces
            ],
            "context_receipt": dumped(turn_result.context_receipt),
            "traversal_receipt": dumped(turn_result.traversal_receipt),
            "interpretation_notice": dumped(turn_result.interpretation_notice),
            "continuation_offer": dumped(turn_result.continuation_offer),
            "assessment_frame": dumped(turn_result.assessment_frame),
            "industry_brief": dumped(turn_result.industry_brief),
            "response_mode": turn_result.response_mode,
            "render_mode": turn_result.render_mode,
        }

    @staticmethod
    def _checkpoint(
        *,
        session_id: str,
        evidence_set: EvidenceSet,
        turn_result: TurnResult,
        fallback_observed_at: datetime,
    ) -> ChatFeedbackCheckpoint:
        return ChatFeedbackCheckpoint(
            session_id=session_id,
            turn_id=turn_result.turn_id,
            release_id=turn_result.release_id,
            query_trace_id=(
                "evidence-set:sha256:"
                + _canonical_sha256(evidence_set.model_dump(mode="json"))
            ),
            answer_trace_id=(
                "turn-result:sha256:"
                + _canonical_sha256(turn_result.model_dump(mode="json"))
            ),
            evidence_ids=tuple(item.evidence_id for item in evidence_set.items),
            affected_domains=tuple(
                sorted({item.domain for item in evidence_set.items})
            ),
            affected_paths=(
                ()
                if turn_result.traversal_receipt is None
                else (turn_result.traversal_receipt.path_id,)
            ),
            limitation_codes=tuple(
                limitation.code for limitation in turn_result.limitations
            ),
            observed_at=fallback_observed_at,
        )


__all__ = ["CanonicalV2ChatAdapter", "ChatFeedbackCheckpoint"]
