from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from importlib import import_module
from typing import Any, Callable


NOW = datetime(2026, 7, 20, 15, 10, tzinfo=UTC)
RELEASE_ID = "candidate-s8x-successor-handoff"


def _read_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_read")


def _answer_module() -> Any:
    return import_module("src.data_agents.canonical_v2.knowledge_answer")


def _web_policy(module: Any) -> Any:
    return module.WebSearchPolicy(
        mode="universal",
        max_provider_calls=1,
        timeout_ms=1_000,
        max_results=5,
    )


def _item(
    module: Any,
    *,
    token: str,
    object_id: str,
    value: str,
    lane: str = "exact",
    source_nature: str = "local",
    source_locator: str | None = None,
    web_snapshot: Any | None = None,
    claim_subject_id: str | None = None,
) -> Any:
    return module.EvidenceItem(
        evidence_id=f"evidence:s8x:{token}",
        object_id=object_id,
        domain="company",
        lane=lane,
        source_nature=source_nature,
        source_locator=source_locator or f"artifact:s8x#{token}",
        snippet=f"Retained evidence for {value}.",
        score=1.0,
        observed_at=NOW,
        claim_binding=module.EvidenceClaimBinding(
            subject_id=claim_subject_id or object_id,
            predicate="geography",
            value="深圳",
            status="accepted",
        ),
        web_snapshot=web_snapshot,
    )


def _candidate(
    module: Any,
    *,
    token: str,
    object_id: str,
    display_name: str,
    evidence: tuple[Any, ...],
    canonical_id: str | None = None,
    identity_kind: str = "canonical",
    resolution_state: str = "resolved",
) -> Any:
    return module.RecallCandidate(
        raw_candidate_id=f"raw-candidate:s8x:{token}",
        display_name=display_name,
        domain="company",
        identity_kind=identity_kind,
        canonical_id=(
            None
            if identity_kind == "web_only"
            else (object_id if canonical_id is None else canonical_id)
        ),
        resolution_state=resolution_state,
        query_view="view:original",
        lane=(evidence[0].lane if evidence else "exact"),
        attempt=1,
        release_id=RELEASE_ID,
        adapter_version=(
            f"recorded-s8x-{evidence[0].lane}-v1"
            if evidence
            else "recorded-s8x-exact-v1"
        ),
        provider_version=(
            "recorded-s8x-web-v1" if evidence and evidence[0].lane == "web" else None
        ),
        raw_score=1.0,
        evidence=evidence,
    )


def _part(module: Any, *, token: str, subject_id: str) -> Any:
    return module.MaterialQuestionPart(
        part_id=f"material-part:s8x:{token}",
        text=f"Verify missing evidence for {subject_id}",
        subject_id=subject_id,
        predicate="current_revenue",
        requested_value="2026",
    )


def _plan(
    module: Any,
    *,
    token: str,
    subject_ids: tuple[str, ...] = (),
    budget_calls: int | None = None,
    lanes: tuple[str, ...] = ("exact",),
    session_id: str | None = None,
) -> Any:
    return module.RetrievalPlan(
        plan_id=f"retrieval-plan:s8x:{token}",
        plan_version="retrieval-plan-v1",
        original_query=f"S8X query {token}",
        behavior_class="A",
        interaction_mode="information_retrieval",
        release_id=RELEASE_ID,
        as_of=NOW,
        domains=("company",),
        protected_slots=(
            module.ProtectedSlot(kind="geography", value="深圳", raw_text="深圳"),
        ),
        lanes=lanes,
        max_candidates=10,
        web_required="web" in lanes,
        web_policy=(
            _web_policy(module)
            if "web" in lanes
            else module.WebSearchPolicy(mode="disabled")
        ),
        material_parts=tuple(
            _part(module, token=f"{token}:{index}", subject_id=subject_id)
            for index, subject_id in enumerate(subject_ids, start=1)
        ),
        supplemental_budget=(
            None
            if budget_calls is None
            else module.SupplementalBudget(
                max_wall_time_ms=10_000,
                max_provider_calls=budget_calls,
                max_retries=1,
                max_cost_units=5.0,
            )
        ),
        session_id=session_id,
    )


def _missing_sufficiency(module: Any) -> Callable[[Any], Any]:
    def decide(request: Any) -> Any:
        return module.SufficiencyProposal(
            decision_input_sha256=request.content_sha256,
            schema_version="sufficiency-v1",
            decision_id=f"sufficiency:s8x:{request.plan_id}",
            parts=tuple(
                module.MaterialPartProposal(
                    part_id=part.part_id,
                    outcome="missing",
                    evidence_ids=(),
                    rationale="No retained evidence supports the requested value.",
                    uncertainty="high",
                    confidence=0.0,
                )
                for part in request.material_parts
            ),
        )

    return decide


def _read(
    module: Any,
    *,
    candidates: tuple[Any, ...],
    supplemental: Callable[[Any], Any] | None,
) -> Any:
    return module.create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": lambda _: module.RetrievalLaneResult(candidates=candidates),
            "web": lambda _: module.RetrievalLaneResult(),
        },
        universal_web_policy=_web_policy(module),
        sufficiency_decider=_missing_sufficiency(module),
        supplemental_search=supplemental,
        clock=lambda: NOW,
    )


def _empty_supplemental(module: Any) -> Callable[[Any], Any]:
    def search(_: Any) -> Any:
        return module.SupplementalLaneResult(
            items=(),
            elapsed_ms=0,
            cost_units=0.0,
            retryable=False,
        )

    return search


def _fixture(module: Any, *, token: str) -> tuple[str, Any, Any]:
    object_id = f"company:s8x-{token}"
    item = _item(
        module,
        token=token,
        object_id=object_id,
        value=f"S8X {token.title()} Robotics",
    )
    return (
        object_id,
        item,
        _candidate(
            module,
            token=token,
            object_id=object_id,
            display_name=f"S8X {token.title()} Robotics",
            evidence=(item,),
        ),
    )


def _handle_id(handle: Any) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def _proposal(
    answer_module: Any,
    request: Any,
    *,
    displayed_handle_ids: tuple[str, ...],
    continuation_candidate_ids: tuple[str, ...] = (),
) -> Any:
    evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
    claims = ()
    if displayed_handle_ids and evidence_by_id:
        item = next(iter(evidence_by_id.values()))
        binding = item.claim_binding
        assert binding is not None
        claims = (
            answer_module.MaterialClaimProposal(
                claim_id=f"claim:s8x:{request.turn_id}",
                text=f"The accepted value is {binding.value}.",
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
        decision_id=f"answer-selection:s8x:{request.turn_id}",
        model_id="recorded-s8x-answer-selector",
        prompt_version="answer-selector-s8x-v1",
        decision_run_id=f"answer-selection-run:s8x:{request.turn_id}",
        answer_text="Untrusted selector draft.",
        claims=claims,
        displayed_handle_ids=displayed_handle_ids,
        continuation_candidate_ids=continuation_candidate_ids,
    )


def _turn(
    answer_module: Any,
    *,
    result: Any,
    session_id: str,
    turn_id: str,
    selection: Any | None = None,
) -> Any:
    return answer_module.TurnRequest(
        session_id=session_id,
        turn_id=turn_id,
        query=result.original_query,
        release_id=result.release_id,
        evidence_set=result,
        continuation_selection=selection,
    )


def _all_current_ids(result: Any) -> tuple[str, ...]:
    return tuple(_handle_id(handle) for handle in result.entity_handles)


def _all_successor_ids(result: Any) -> tuple[str, ...]:
    return tuple(candidate.candidate_id for candidate in result.continuation_candidates)


def test_evidence_gap_materializes_deterministic_current_handle_and_selects_next_turn() -> (
    None
):
    read_module = _read_module()
    answer_module = _answer_module()
    company_id, item, candidate = _fixture(read_module, token="alpha")
    read = _read(
        read_module,
        candidates=(candidate,),
        supplemental=_empty_supplemental(read_module),
    )
    plan = _plan(
        read_module,
        token="evidence-gap",
        subject_ids=(company_id, company_id),
        budget_calls=2,
    )

    result = read.execute(plan)
    repeated = read.execute(plan)

    assert result.continuation_reasons == ("evidence_gap",)
    assert result.continuation_candidates == repeated.continuation_candidates
    assert tuple(value.reason for value in result.continuation_candidates) == (
        "evidence_gap",
    )
    successor = result.continuation_candidates[0]
    assert successor.operation == "targeted_evidence_search"
    assert successor.target_kind == "current_handle"
    assert successor.target_handle_ids == (company_id,)
    assert successor.evidence_ids == (item.evidence_id,)
    assert successor.constraint_pairs == (("geography", "深圳"),)

    changed_item = _item(
        read_module,
        token="alpha-authority-change",
        object_id=company_id,
        value="S8X Alpha Robotics",
    )
    changed_candidate = _candidate(
        read_module,
        token="alpha",
        object_id=company_id,
        display_name="S8X Alpha Robotics",
        evidence=(changed_item,),
    )
    changed = _read(
        read_module,
        candidates=(changed_candidate,),
        supplemental=_empty_supplemental(read_module),
    ).execute(plan)
    assert changed.continuation_candidates[0].candidate_id != successor.candidate_id

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda request: _proposal(
            answer_module,
            request,
            displayed_handle_ids=(),
            continuation_candidate_ids=_all_successor_ids(request.evidence_set),
        )
    )
    first = answer.answer(
        _turn(
            answer_module,
            result=result,
            session_id="session:s8x:evidence-gap",
            turn_id="turn:s8x:evidence-gap:1",
        )
    )
    assert first.continuation_offer is not None
    assert first.context_receipt.displayed_result_set is None
    option = first.continuation_offer.options[0]
    assert option.operation == "targeted_evidence_search"
    assert option.target_handle_ids == (company_id,)
    assert option.evidence_ids == (item.evidence_id,)

    second_result = read.execute(_plan(read_module, token="evidence-gap-selection"))
    second = answer.answer(
        _turn(
            answer_module,
            result=second_result,
            session_id="session:s8x:evidence-gap",
            turn_id="turn:s8x:evidence-gap:2",
            selection=answer_module.ContinuationSelection(
                offer_id=first.continuation_offer.offer_id,
                option_id=option.option_id,
            ),
        )
    )
    receipt = second.context_receipt
    assert receipt is not None
    assert receipt.selected_option_id == option.option_id
    assert receipt.selected_operation == "targeted_evidence_search"
    assert receipt.active_anchor is not None
    assert _handle_id(receipt.active_anchor) == company_id
    assert receipt.resolved_referent is not None
    assert receipt.resolved_referent.kind == "continuation_option"
    assert receipt.resolved_referent.handle_ids == (company_id,)
    assert receipt.resolved_evidence_ids == (item.evidence_id,)
    assert tuple((slot.kind, slot.value) for slot in receipt.active_constraints) == (
        ("geography", "深圳"),
    )


def test_non_enumeration_budget_materializes_current_result_set_and_selects_next_turn() -> (
    None
):
    read_module = _read_module()
    answer_module = _answer_module()
    company_id, item, candidate = _fixture(read_module, token="alpha")
    read = _read(
        read_module,
        candidates=(candidate,),
        supplemental=_empty_supplemental(read_module),
    )
    result = read.execute(
        _plan(
            read_module,
            token="budget-exhausted-non-enumeration",
            subject_ids=(company_id,),
            budget_calls=0,
        )
    )

    assert result.enumeration_coverage is None
    assert result.continuation_reasons == ("evidence_gap", "budget_exhausted")
    candidates_by_reason = {
        candidate.reason: candidate for candidate in result.continuation_candidates
    }
    assert tuple(candidates_by_reason) == ("evidence_gap", "budget_exhausted")
    successor = candidates_by_reason["budget_exhausted"]
    assert successor.operation == "resume_bounded_search"
    assert successor.target_kind == "current_result_set"
    assert successor.target_handle_ids == ()
    assert successor.evidence_ids == (item.evidence_id,)

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda request: _proposal(
            answer_module,
            request,
            displayed_handle_ids=_all_current_ids(request.evidence_set),
            continuation_candidate_ids=_all_successor_ids(request.evidence_set),
        )
    )
    first = answer.answer(
        _turn(
            answer_module,
            result=result,
            session_id="session:s8x:budget",
            turn_id="turn:s8x:budget:1",
        )
    )
    assert first.continuation_offer is not None
    assert first.context_receipt is not None
    displayed = first.context_receipt.displayed_result_set
    assert displayed is not None
    assert displayed.handle_ids == (company_id,)
    option = next(
        option
        for option in first.continuation_offer.options
        if option.operation == "resume_bounded_search"
    )
    assert option.result_set_id == displayed.result_set_id
    assert option.target_handle_ids == ()
    assert option.evidence_ids == (item.evidence_id,)

    second_result = read.execute(_plan(read_module, token="budget-selection"))
    second = answer.answer(
        _turn(
            answer_module,
            result=second_result,
            session_id="session:s8x:budget",
            turn_id="turn:s8x:budget:2",
            selection=answer_module.ContinuationSelection(
                offer_id=first.continuation_offer.offer_id,
                option_id=option.option_id,
            ),
        )
    )
    receipt = second.context_receipt
    assert receipt is not None
    assert receipt.selected_option_id == option.option_id
    assert receipt.selected_operation == "resume_bounded_search"
    assert receipt.active_anchor is not None
    assert _handle_id(receipt.active_anchor) == company_id
    assert receipt.resolved_referent is not None
    assert receipt.resolved_referent.kind == "result_set"
    assert receipt.resolved_referent.result_set_id == displayed.result_set_id
    assert receipt.resolved_referent.handle_ids == (company_id,)
    assert receipt.resolved_evidence_ids == (item.evidence_id,)


def test_canonical_object_id_cannot_authorize_another_handle() -> None:
    module = _read_module()
    supplemental = _empty_supplemental(module)
    crosswired_subject_id = "company:s8x-crosswired-subject"
    crosswired_handle_id = "company:s8x-crosswired-handle"
    crosswired_item = _item(
        module,
        token="canonical-object-crosswire",
        object_id=crosswired_subject_id,
        value="S8X Crosswired Handle",
        claim_subject_id=crosswired_handle_id,
    )
    result = _read(
        module,
        candidates=(
            _candidate(
                module,
                token="canonical-object-crosswire",
                object_id=crosswired_handle_id,
                display_name="S8X Crosswired Handle",
                evidence=(crosswired_item,),
            ),
        ),
        supplemental=supplemental,
    ).execute(
        _plan(
            module,
            token="canonical-object-crosswire",
            subject_ids=(crosswired_subject_id,),
            budget_calls=2,
        )
    )
    assert result.continuation_reasons == ("evidence_gap",)
    assert result.continuation_candidates == ()


def test_continuation_authority_defaults_deny_for_canonical_and_web_matrix() -> None:
    module = _read_module()
    alpha_id, _, alpha = _fixture(module, token="alpha")
    other_id, _, other = _fixture(module, token="other")
    supplemental = _empty_supplemental(module)

    canonical_cases = (
        _read(module, candidates=(other,), supplemental=supplemental).execute(
            _plan(
                module,
                token="canonical-crosswire",
                subject_ids=(alpha_id,),
                budget_calls=2,
            )
        ),
        _read(module, candidates=(alpha, other), supplemental=supplemental).execute(
            _plan(
                module,
                token="canonical-multiple-subjects",
                subject_ids=(alpha_id, other_id),
                budget_calls=2,
            )
        ),
        _read(
            module,
            candidates=(
                _candidate(
                    module,
                    token="missing-evidence",
                    object_id="company:s8x-missing-evidence",
                    display_name="S8X Missing Evidence",
                    evidence=(),
                ),
            ),
            supplemental=supplemental,
        ).execute(
            _plan(
                module,
                token="canonical-missing-evidence",
                subject_ids=("company:s8x-missing-evidence",),
                budget_calls=2,
            )
        ),
    )
    for case in canonical_cases:
        assert case.continuation_reasons == ("evidence_gap",)
        assert (
            tuple(
                value
                for value in case.continuation_candidates
                if value.reason == "evidence_gap"
            )
            == ()
        )

    subject_id = "web-object:s8x-shared"

    def web_fixture(token: str, *, object_id: str = subject_id) -> tuple[Any, Any]:
        payload = f"Recorded current Web authority for {token}.".encode()
        content_sha256 = hashlib.sha256(payload).hexdigest()
        snapshot = module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:s8x:{token}:sha256:{content_sha256}",
            content_sha256=content_sha256,
            retrieved_at=NOW,
            byte_length=len(payload),
        )
        item = _item(
            module,
            token=f"web-{token}",
            object_id=object_id,
            value=f"S8X Web {token.title()}",
            lane="web",
            source_nature="current_web",
            source_locator=f"https://current.example/{token}",
            web_snapshot=snapshot,
        )
        candidate = _candidate(
            module,
            token=f"web-{token}",
            object_id=object_id,
            display_name=f"S8X Web {token.title()}",
            evidence=(item,),
            identity_kind="web_only",
            resolution_state="unresolved",
        )
        return (
            candidate,
            module.WebSnapshotPayload(
                snapshot_id=snapshot.snapshot_id,
                content=payload,
            ),
        )

    def execute_web(
        token: str,
        *,
        candidates: tuple[Any, ...],
        payloads: tuple[Any, ...],
        subject: str = subject_id,
        session_id: str | None = "session:s8x:web",
        ttl: timedelta = timedelta(hours=1),
    ) -> Any:
        read = module.create_ephemeral_knowledge_read(
            lane_adapters={
                "web": lambda _: module.RetrievalLaneResult(
                    candidates=candidates,
                    web_snapshot_payloads=payloads,
                )
            },
            universal_web_policy=_web_policy(module),
            sufficiency_decider=_missing_sufficiency(module),
            supplemental_search=supplemental,
            clock=lambda: NOW,
            web_handle_ttl=ttl,
            web_snapshot_policy=module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8x",
                policy_version="web-snapshot-policy-v1",
                max_bytes=10_000,
            ),
        )
        return read.execute(
            _plan(
                module,
                token=token,
                subject_ids=(subject,),
                budget_calls=2,
                lanes=("web",),
                session_id=session_id,
            )
        )

    valid_candidate, valid_payload = web_fixture("valid")
    valid = execute_web(
        "web-valid",
        candidates=(valid_candidate,),
        payloads=(valid_payload,),
    )
    assert len(valid.entity_handles) == 1
    valid_handle = valid.entity_handles[0]
    assert valid_handle.kind == "web"
    valid_gap = tuple(
        value
        for value in valid.continuation_candidates
        if value.reason == "evidence_gap"
    )
    assert len(valid_gap) == 1
    assert valid_gap[0].target_handle_ids == (valid_handle.handle_id,)
    assert valid_gap[0].evidence_ids == valid_handle.evidence_ids

    mixed_a, mixed_payload_a = web_fixture("mixed-a")
    mixed_b, mixed_payload_b = web_fixture(
        "mixed-b",
        object_id="web-object:s8x-mixed-other",
    )
    mixed_object_candidate = _candidate(
        module,
        token="web-mixed-object",
        object_id=subject_id,
        display_name="S8X Web Mixed Object",
        evidence=(*mixed_a.evidence, *mixed_b.evidence),
        identity_kind="web_only",
        resolution_state="unresolved",
    )
    mixed_object = execute_web(
        "web-mixed-object",
        candidates=(mixed_object_candidate,),
        payloads=(mixed_payload_a, mixed_payload_b),
    )
    assert len(mixed_object.entity_handles) == 1
    assert mixed_object.continuation_reasons == ("evidence_gap",)
    assert mixed_object.continuation_candidates == ()

    duplicate_a, duplicate_payload_a = web_fixture("duplicate-a")
    duplicate_b, duplicate_payload_b = web_fixture("duplicate-b")
    crosswired, crosswired_payload = web_fixture(
        "crosswired",
        object_id="web-object:s8x-other",
    )
    snapshotless_item = _item(
        module,
        token="web-snapshotless",
        object_id=subject_id,
        value="S8X Web Snapshotless",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/snapshotless",
    )
    snapshotless = _candidate(
        module,
        token="web-snapshotless",
        object_id=subject_id,
        display_name="S8X Web Snapshotless",
        evidence=(snapshotless_item,),
        identity_kind="web_only",
        resolution_state="unresolved",
    )
    denied = (
        execute_web(
            "web-expired",
            candidates=(valid_candidate,),
            payloads=(valid_payload,),
            ttl=timedelta(0),
        ),
        execute_web(
            "web-sessionless",
            candidates=(valid_candidate,),
            payloads=(valid_payload,),
            session_id=None,
        ),
        execute_web(
            "web-snapshotless",
            candidates=(snapshotless,),
            payloads=(),
        ),
        execute_web(
            "web-duplicate",
            candidates=(duplicate_a, duplicate_b),
            payloads=(duplicate_payload_a, duplicate_payload_b),
        ),
        execute_web(
            "web-crosswired",
            candidates=(crosswired,),
            payloads=(crosswired_payload,),
        ),
    )
    for case in denied:
        assert case.continuation_reasons == ("evidence_gap",)
        assert (
            tuple(
                value
                for value in case.continuation_candidates
                if value.reason == "evidence_gap"
            )
            == ()
        )


def test_answer_rejects_prior_result_set_for_budget_but_keeps_current_handle_offer() -> (
    None
):
    read_module = _read_module()
    answer_module = _answer_module()
    alpha_id, alpha_item, alpha = _fixture(read_module, token="alpha")
    other_id, _, other = _fixture(read_module, token="other")
    supplemental = _empty_supplemental(read_module)
    read_alpha = _read(
        read_module,
        candidates=(alpha,),
        supplemental=supplemental,
    )
    current = read_alpha.execute(
        _plan(
            read_module,
            token="poison-current",
            subject_ids=(alpha_id,),
            budget_calls=0,
        )
    )
    prior = _read(
        read_module,
        candidates=(other,),
        supplemental=None,
    ).execute(_plan(read_module, token="poison-prior"))

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda request: _proposal(
            answer_module,
            request,
            displayed_handle_ids=(
                (other_id,) if request.turn_id == "turn:s8x:poison:1" else ()
            ),
            continuation_candidate_ids=_all_successor_ids(request.evidence_set),
        )
    )
    prior_answer = answer.answer(
        _turn(
            answer_module,
            result=prior,
            session_id="session:s8x:poison",
            turn_id="turn:s8x:poison:1",
        )
    )
    assert prior_answer.context_receipt is not None
    prior_result_set = prior_answer.context_receipt.displayed_result_set
    assert prior_result_set is not None
    assert prior_result_set.handle_ids == (other_id,)

    poisoned = answer.answer(
        _turn(
            answer_module,
            result=current,
            session_id="session:s8x:poison",
            turn_id="turn:s8x:poison:2",
        )
    )
    assert poisoned.context_receipt is not None
    assert poisoned.context_receipt.displayed_result_set == prior_result_set
    assert poisoned.continuation_offer is not None
    options = poisoned.continuation_offer.options
    targeted = tuple(
        option for option in options if option.operation == "targeted_evidence_search"
    )
    assert len(targeted) == 1
    assert targeted[0].target_handle_ids == (alpha_id,)
    assert targeted[0].evidence_ids == (alpha_item.evidence_id,)
    assert all(option.operation != "resume_bounded_search" for option in options)
    assert all(
        option.result_set_id != prior_result_set.result_set_id for option in options
    )


def test_blocking_planner_materializes_blocked_candidates_without_continuation() -> None:
    read_module = _read_module()
    answer_module = _answer_module()
    company_id, item, _ = _fixture(read_module, token="alpha")
    other_id, other_item, _ = _fixture(read_module, token="other")
    policy = read_module.QueryPlanningPolicy(
        policy_id="query-planning-policy:s8x",
        policy_version="query-planning-policy-v1",
        public_domains=("professor", "company", "paper", "patent"),
        supported_lanes=("exact", "web"),
        supported_relationship_paths=(),
        max_candidates=10,
        max_provider_calls=1,
        max_planning_attempts=1,
    )
    catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8x",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(),
    )
    ambiguity_policy = read_module.AmbiguityPolicy(
        policy_id="ambiguity-policy:s8x",
        policy_version="ambiguity-policy-v1",
        entity_type="company",
        minimum_evidence_count=1,
        confidence_threshold=0.7,
        minimum_lead_margin=0.2,
    )
    ambiguity_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8x:blocking",
        release_id=RELEASE_ID,
        original_query="介绍同名机器人公司",
        as_of=NOW,
        ambiguity_candidates=(
            read_module.AmbiguityCandidate(
                candidate_id="candidate:s8x:blocking:alpha",
                entity_type="company",
                canonical_id=company_id,
                display_name="同名机器人公司",
                evidence_ids=(item.evidence_id,),
                evidence_confidence=0.9,
                model_confidence=0.9,
                discriminators=(
                    read_module.CandidateDiscriminator(
                        kind="district",
                        value="南山",
                        evidence_ids=(item.evidence_id,),
                    ),
                ),
            ),
            read_module.AmbiguityCandidate(
                candidate_id="candidate:s8x:blocking:other",
                entity_type="company",
                canonical_id=other_id,
                display_name="同名机器人公司",
                evidence_ids=(other_item.evidence_id,),
                evidence_confidence=0.8,
                model_confidence=0.8,
                discriminators=(
                    read_module.CandidateDiscriminator(
                        kind="district",
                        value="宝安",
                        evidence_ids=(other_item.evidence_id,),
                    ),
                ),
            ),
        ),
    )
    planner = read_module.create_ephemeral_query_planner(
        planning_policy=policy,
        institution_catalog=catalog,
        ambiguity_policy=ambiguity_policy,
        proposal_provider=lambda request: read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8x:blocking",
            request_sha256=request.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-s8x-planner",
            prompt_version="query-plan-prompt-v1",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("company",),
            lanes=("exact", "web"),
            max_candidates=10,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=5,
        ),
    )
    plan = planner.plan(ambiguity_request)
    assert plan.interaction_mode == "blocking_clarification"
    assert plan.lanes == ()

    read = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=_web_policy(read_module)
    )
    result = read.execute(plan)
    repeated = read.execute(plan)

    assert result.items == ()
    # Successor handoff registers the blocked candidates as handles so the
    # clarification can offer evidenced discriminators and a later selection
    # turn can resolve its target; no continuation option is materialized.
    assert {handle.canonical_id for handle in result.entity_handles} == {
        company_id,
        other_id,
    }
    assert result.continuation_candidates == ()
    decision = result.ambiguity_decision
    assert decision is not None
    assert decision.outcome == "blocked"
    assert {candidate.handle_id for candidate in decision.candidates} == {
        company_id,
        other_id,
    }
    assert decision.selected_handle_id is None
    assert set(decision.viable_alternative_handle_ids) == {company_id, other_id}
    assert decision.decision_id == repeated.ambiguity_decision.decision_id
    assert decision.decision_trace_id == repeated.ambiguity_decision.decision_trace_id
    assert decision.decision_id.startswith("ambiguity-decision:sha256:")
    assert decision.decision_trace_id.startswith("ambiguity-trace:sha256:")

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda request: _proposal(
            answer_module,
            request,
            displayed_handle_ids=(),
        )
    ).answer(
        _turn(
            answer_module,
            result=result,
            session_id="session:s8x:blocking",
            turn_id="turn:s8x:blocking:1",
        )
    )
    assert answer.response_mode == "clarification_only"
    assert answer.claims == ()
    # The successor handoff turns the blocked candidates into an executable
    # clarification offer (selection_kind clarification_selection) with the
    # evidenced discriminators, so the user can resolve the ambiguity by
    # choosing instead of typing a distinguishing detail.
    offer = answer.continuation_offer
    assert offer is not None
    assert offer.selection_kind == "clarification_selection"
    assert {option.target_handle_ids for option in offer.options} == {
        (company_id,),
        (other_id,),
    }
    assert all(option.discriminator for option in offer.options)
    assert "evidenced candidates" in answer.answer_text.lower()
