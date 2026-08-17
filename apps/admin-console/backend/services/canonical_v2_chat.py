"""Release-bound Canonical V2 chat orchestration behind the HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from threading import RLock
from typing import Any, Callable, Protocol, cast

from pydantic import Field, model_validator

from backend.api.chat_contracts import (
    CandidateOption,
    ChatCitation,
    ChatResponse,
    ClarificationPayload,
    TargetDomain,
)
from src.data_agents.canonical_v2.contracts import ContractModel
from src.data_agents.canonical_v2.knowledge_answer import (
    ContinuationOffer,
    ContinuationSelection,
    ContextReceipt,
    KnowledgeAnswer,
    SessionDirective,
    TurnRequest,
    TurnResult,
)
from src.data_agents.canonical_v2.knowledge_read import (
    CanonicalEntityHandle,
    EvidenceSet,
    QueryPlanningRequest,
    RetrievalPlan,
    WebEntityHandle,
)


_ZERO_SHA256 = "0" * 64
_PUBLIC_DOMAINS = frozenset({"professor", "company", "paper", "patent"})
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
        self._lock = RLock()

    def get_feedback_checkpoint(self, session_id: str) -> ChatFeedbackCheckpoint | None:
        with self._lock:
            committed = self._sessions.get(session_id)
            return None if committed is None else committed.checkpoint

    def answer(
        self,
        *,
        query: str,
        session_id: str,
        option_id: str | None,
        as_of: datetime,
    ) -> ChatResponse:
        with self._lock:
            return self._answer_locked(
                query=query,
                session_id=session_id,
                option_id=option_id,
                as_of=as_of,
            )

    def _answer_locked(
        self,
        *,
        query: str,
        session_id: str,
        option_id: str | None,
        as_of: datetime,
    ) -> ChatResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be non-empty")
        if not session_id.strip():
            raise ValueError("session_id must be non-empty")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        observed_as_of = as_of.astimezone(UTC)

        committed = self._sessions.get(session_id)
        selection = self._selection(committed, option_id=option_id)
        turn_count = 1 if committed is None else committed.turn_count + 1
        turn_id = self._turn_id(
            session_id=session_id,
            turn_count=turn_count,
            query=normalized_query,
            option_id=option_id,
        )
        displayed_ids = () if committed is None else committed.displayed_ids
        planning_request = QueryPlanningRequest(
            request_id=f"query-request:chat:{turn_id}",
            release_id=self._release_id,
            original_query=normalized_query,
            as_of=observed_as_of,
            displayed_entity_ids=displayed_ids,
        )

        raw_plan = self._planner.plan(planning_request)
        self._require_release(raw_plan, stage="plan")
        plan = _validated_model(raw_plan, RetrievalPlan)
        self._require_release(plan, stage="plan")

        raw_evidence_set = self._knowledge_read.execute(plan)
        self._require_release(raw_evidence_set, stage="read")
        evidence_set = _validated_model(raw_evidence_set, EvidenceSet)
        self._require_release(evidence_set, stage="read")

        base_answer = self._answer_factory() if committed is None else committed.answer
        candidate_answer = self._answer_session_fork(base_answer)
        directive = self._session_directive(
            committed=committed,
            evidence_set=evidence_set,
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
        next_session = _CommittedSession(
            answer=candidate_answer,
            turn_count=turn_count,
            context_receipt=context_receipt,
            active_offer=turn_result.continuation_offer,
            displayed_ids=next_displayed_ids,
            checkpoint=checkpoint,
        )

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
    ) -> SessionDirective | None:
        if committed is None or evidence_set.requested_traversal is None:
            return None
        context = committed.context_receipt
        if context is not None and context.active_anchor is not None:
            return SessionDirective(referent="active_anchor")
        if context is not None and context.displayed_result_set is not None:
            return SessionDirective(referent="displayed_result_set")
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
        )
        clarification = self._clarification(
            turn_result=turn_result,
            handles_by_id=handles_by_id,
        )
        trace = self._trace(outcome)
        response_payload = {
            "query": outcome.query,
            "query_type": (
                f"canonical_v2:{outcome.plan.behavior_class}:"
                f"{turn_result.response_mode}"
            ),
            "answer_text": turn_result.answer_text,
            "citations": [item.model_dump(mode="json") for item in public_citations],
            "evidence": [item.model_dump(mode="json") for item in evidence_set.items],
            "clarification": (
                None if clarification is None else clarification.model_dump(mode="json")
            ),
            "structured_payload": {"canonical_v2": trace},
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
    ) -> tuple[ChatCitation, ...]:
        handle_by_evidence_id: dict[str, tuple[str, Any]] = {}
        for handle_id, handle in handles_by_id.items():
            if handle.domain not in _PUBLIC_DOMAINS:
                continue
            for evidence_id in handle.evidence_ids:
                handle_by_evidence_id.setdefault(evidence_id, (handle_id, handle))
        cards: list[ChatCitation] = []
        seen: set[str] = set()
        for citation in turn_result.citations:
            bound = handle_by_evidence_id.get(citation.evidence_id)
            if bound is None:
                continue
            handle_id, handle = bound
            if handle_id in seen:
                continue
            seen.add(handle_id)
            cards.append(
                ChatCitation(
                    type=handle.domain,
                    id=handle_id,
                    label=handle.display_name,
                    url=f"/browse#{handle.domain}/{handle_id}",
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
                        label=_PUBLIC_CONTINUATION_OPERATION.get(
                            option.operation, "继续当前问题"
                        ),
                        hint=_PUBLIC_CONTINUATION_OPERATION.get(
                            option.operation, "继续当前问题"
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
