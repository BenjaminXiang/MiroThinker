from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from importlib import import_module
from typing import Any


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_answer"
READ_TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
RELEASE_ID = "candidate-r1"
NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _answer_module() -> Any:
    return import_module(TARGET_MODULE)


def _read_module() -> Any:
    return import_module(READ_TARGET_MODULE)


def _slot(module: Any, kind: str, value: str) -> Any:
    return module.ProtectedSlot(kind=kind, value=value)


def _item(
    module: Any,
    *,
    evidence_id: str,
    object_id: str,
    domain: str,
    subject_id: str,
    predicate: str,
    value: str,
    snippet: str,
    lane: str = "exact",
    source_nature: str = "local",
    source_locator: str | None = None,
    web_snapshot: Any | None = None,
) -> Any:
    return module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=object_id,
        domain=domain,
        lane=lane,
        source_nature=source_nature,
        source_locator=source_locator or f"artifact:s9m#{evidence_id}",
        snippet=snippet,
        score=1.0,
        observed_at=NOW,
        claim_binding=module.EvidenceClaimBinding(
            subject_id=subject_id,
            predicate=predicate,
            value=value,
        ),
        web_snapshot=web_snapshot,
    )


def _canonical_handle(
    module: Any,
    *,
    canonical_id: str,
    domain: str,
    display_name: str,
    evidence_ids: tuple[str, ...],
) -> Any:
    return module.CanonicalEntityHandle(
        kind="canonical",
        canonical_id=canonical_id,
        domain=domain,
        display_name=display_name,
        evidence_ids=evidence_ids,
    )


def _web_fixture(module: Any, *, session_id: str) -> tuple[Any, Any]:
    snapshot_bytes = b"Recorded Web-only Company profile for S9M."
    content_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    snapshot = module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:sha256:{content_sha256}",
        content_sha256=content_sha256,
        retrieved_at=NOW,
        byte_length=len(snapshot_bytes),
    )
    item = _item(
        module,
        evidence_id="web:company-nova",
        object_id="web-object:company-nova",
        domain="company",
        subject_id="web-object:company-nova",
        predicate="display_identity",
        value="Nova Robotics",
        snippet="Nova Robotics is described in the retained bounded Web snapshot.",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/companies/nova",
        web_snapshot=snapshot,
    )
    handle = module.WebEntityHandle(
        kind="web",
        handle_id="web-handle:company-nova",
        domain="company",
        display_name="Nova Robotics",
        evidence_snapshot_ids=(snapshot.snapshot_id,),
        evidence_ids=(item.evidence_id,),
        resolution_state="unresolved",
        candidate_canonical_ids=(),
        originating_query="列出两家机器人公司",
        origin_lane="web",
        origin_attempt=1,
        session_id=session_id,
    )
    return item, handle


def _coverage(
    module: Any,
    *,
    scope: str,
    retrieved_ids: tuple[str, ...],
    displayed_ids: tuple[str, ...],
    continuation_state: str = "open_world",
) -> Any:
    omitted_ids = tuple(
        member_id for member_id in retrieved_ids if member_id not in displayed_ids
    )
    return module.EnumerationCoverage(
        mode="representative",
        scope=scope,
        as_of=NOW,
        checked_ids=retrieved_ids,
        eligible_ids=retrieved_ids,
        retrieved_ids=retrieved_ids,
        displayed_ids=displayed_ids,
        omitted_ids=omitted_ids,
        unknown_ids=(),
        unknown_scope=True,
        checked_count=len(retrieved_ids),
        eligible_count=len(retrieved_ids),
        retrieved_count=len(retrieved_ids),
        displayed_count=len(displayed_ids),
        omitted_count=len(omitted_ids),
        unknown_count=None,
        exhaustive=False,
        accounting_complete=True,
        required_member_outcomes=(),
        continuation_state=continuation_state,
        continuation_required=True,
    )


def _evidence_set(
    module: Any,
    *,
    query: str,
    items: tuple[Any, ...] = (),
    handles: tuple[Any, ...] = (),
    protected_slots: tuple[Any, ...] = (),
    coverage: Any | None = None,
    requested_traversal: Any | None = None,
    ambiguity_decision: Any | None = None,
    continuation_candidates: tuple[Any, ...] = (),
    material_parts: tuple[Any, ...] = (),
) -> Any:
    return module.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=protected_slots,
        items=items,
        traces=(),
        limitations=(),
        entity_handles=handles,
        enumeration_coverage=coverage,
        requested_traversal=requested_traversal,
        ambiguity_decision=ambiguity_decision,
        continuation_candidates=continuation_candidates,
        material_parts=material_parts,
    )


def _request(
    module: Any,
    *,
    session_id: str,
    turn_id: str,
    query: str,
    evidence_set: Any,
    continuation_selection: Any | None = None,
    session_directive: Any | None = None,
) -> Any:
    values: dict[str, Any] = {
        "session_id": session_id,
        "turn_id": turn_id,
        "query": query,
        "release_id": RELEASE_ID,
        "evidence_set": evidence_set,
    }
    if continuation_selection is not None:
        values["continuation_selection"] = continuation_selection
    if session_directive is not None:
        values["session_directive"] = session_directive
    return module.TurnRequest(**values)


def _proposal(
    module: Any,
    request: Any,
    *,
    displayed_handle_ids: tuple[str, ...] = (),
    claims: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (),
    continuation_candidate_ids: tuple[str, ...] = (),
) -> Any:
    evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
    claim_proposals = []
    for claim_id, text, subject_handle_ids, evidence_ids in claims:
        assert evidence_ids
        item = evidence_by_id.get(evidence_ids[0])
        binding = None if item is None else item.claim_binding
        subject_id = (
            binding.subject_id
            if binding is not None
            else subject_handle_ids[0]
            if subject_handle_ids
            else "unknown:subject"
        )
        claim_proposals.append(
            module.MaterialClaimProposal(
                claim_id=claim_id,
                text=text,
                subject_id=subject_id,
                predicate=(
                    binding.predicate
                    if binding is not None
                    else "retained_session_detail"
                ),
                value=binding.value if binding is not None else text,
                status=None if binding is None else binding.status,
                subject_handle_ids=subject_handle_ids,
                evidence_ids=evidence_ids,
            )
        )
    return module.AnswerSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id=f"answer-selection:{request.turn_id}",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id=f"answer-selector-run:{request.turn_id}",
        answer_text=f"Synthetic grounded answer for {request.turn_id}",
        claims=tuple(claim_proposals),
        displayed_handle_ids=displayed_handle_ids,
        continuation_candidate_ids=continuation_candidate_ids,
    )


def _handle_id(handle: Any) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def _constraint_pairs(receipt: Any) -> set[tuple[str, str]]:
    return {(slot.kind, slot.value) for slot in receipt.active_constraints}


def _values_for_key(value: Any, key: str) -> set[Any]:
    if isinstance(value, dict):
        found = (
            {value[key]} if key in value and not isinstance(value[key], dict) else set()
        )
        return found | {
            item for nested in value.values() for item in _values_for_key(nested, key)
        }
    if isinstance(value, (list, tuple)):
        return {item for nested in value for item in _values_for_key(nested, key)}
    return set()


def test_canonical_anchor_displayed_set_and_typed_traversal_stay_exact() -> None:
    module = _answer_module()
    read_module = _read_module()
    session_id = "session:s9m:canonical"
    professor_id = "professor:zhang-ming"
    paper_ids = ("paper:displayed-1", "paper:displayed-2")
    hidden_paper_id = "paper:retrieved-hidden"
    company_ids = ("professor:linked-1", "professor:linked-2")
    hidden_company_id = "professor:hidden-source-link"

    professor_item = _item(
        read_module,
        evidence_id="evidence:professor:zhang",
        object_id=professor_id,
        domain="professor",
        subject_id=professor_id,
        predicate="preferred_name",
        value="张明",
        snippet="The accepted release identifies 张明 at Southern Tech University.",
    )
    professor_handle = _canonical_handle(
        read_module,
        canonical_id=professor_id,
        domain="professor",
        display_name="张明教授",
        evidence_ids=(professor_item.evidence_id,),
    )
    paper_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{paper_id}",
            object_id=paper_id,
            domain="paper",
            subject_id=professor_id,
            predicate="professor_attributed_to_paper",
            value=paper_id,
            snippet=f"The retained relationship links 张明 to {paper_id} in 2024.",
        )
        for paper_id in (*paper_ids, hidden_paper_id)
    )
    paper_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=paper_id,
            domain="paper",
            display_name=paper_id,
            evidence_ids=(f"evidence:{paper_id}",),
        )
        for paper_id in (*paper_ids, hidden_paper_id)
    )
    company_bindings = (
        (hidden_paper_id, hidden_company_id),
        (paper_ids[0], company_ids[0]),
        (paper_ids[1], company_ids[1]),
    )
    company_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{source_id}:{target_id}",
            object_id=target_id,
            domain="professor",
            subject_id=target_id,
            predicate="professor_attributed_to_paper",
            value=source_id,
            snippet=f"{source_id} is evidence-linked to {target_id}.",
        )
        for source_id, target_id in company_bindings
    )
    company_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=target_id,
            domain="professor",
            display_name=target_id,
            evidence_ids=(f"evidence:{source_id}:{target_id}",),
        )
        for source_id, target_id in company_bindings
    )
    paper_coverage = _coverage(
        read_module,
        scope="张明教授在当前 release 中的 2024 年代表性论文",
        retrieved_ids=(*paper_ids, hidden_paper_id),
        displayed_ids=paper_ids,
    )
    partial_candidate = read_module.ContinuationCandidate(
        candidate_id="continuation:paper-coverage",
        reason="partial_coverage",
        label="继续查看其余论文",
        operation="continue_coverage",
        target_kind="current_result_set",
        target_handle_ids=(),
        constraint_pairs=(("year", "2024"),),
        relation_type=None,
        coverage_state="open_world",
        evidence_ids=tuple(f"evidence:{paper_id}" for paper_id in paper_ids),
        available=True,
    )
    requests = (
        _request(
            module,
            session_id=session_id,
            turn_id="turn:canonical:1",
            query="介绍南科大张明教授",
            evidence_set=_evidence_set(
                read_module,
                query="介绍南科大张明教授",
                items=(professor_item,),
                handles=(professor_handle,),
                protected_slots=(_slot(read_module, "institution", "南方科技大学"),),
            ),
        ),
        _request(
            module,
            session_id=session_id,
            turn_id="turn:canonical:2",
            query="列出他的 2024 年论文",
            evidence_set=_evidence_set(
                read_module,
                query="列出他的 2024 年论文",
                items=paper_items,
                handles=paper_handles,
                protected_slots=(_slot(read_module, "year", "2024"),),
                coverage=paper_coverage,
                requested_traversal=read_module.TypedTraversalRequest(
                    path_id="professor_to_paper",
                    source_domain="professor",
                    target_domain="paper",
                    relationship_type="professor_attributed_to_paper",
                    direction="forward",
                ),
                continuation_candidates=(partial_candidate,),
            ),
            session_directive=module.SessionDirective(referent="active_anchor"),
        ),
        _request(
            module,
            session_id=session_id,
            turn_id="turn:canonical:3",
            query="这些论文的作者中哪些是深圳教授",
            evidence_set=_evidence_set(
                read_module,
                query="这些论文的作者中哪些是深圳教授",
                items=company_items,
                handles=company_handles,
                protected_slots=(_slot(read_module, "geography", "深圳"),),
                requested_traversal=read_module.TypedTraversalRequest(
                    path_id="paper_to_professor",
                    source_domain="paper",
                    target_domain="professor",
                    relationship_type="professor_attributed_to_paper",
                    direction="inverse",
                ),
            ),
            session_directive=module.SessionDirective(referent="displayed_result_set"),
        ),
    )

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:canonical:1":
            return _proposal(
                module,
                request,
                displayed_handle_ids=(professor_id,),
                claims=(
                    (
                        "claim:professor",
                        "张明是当前聚焦的教授。",
                        (professor_id,),
                        (professor_item.evidence_id,),
                    ),
                ),
            )
        if request.turn_id == "turn:canonical:2":
            return _proposal(
                module,
                request,
                displayed_handle_ids=paper_ids,
                claims=tuple(
                    (
                        f"claim:{paper_id}",
                        f"展示论文 {paper_id}",
                        (paper_id,),
                        (f"evidence:{paper_id}",),
                    )
                    for paper_id in paper_ids
                ),
                continuation_candidate_ids=(partial_candidate.candidate_id,),
            )
        return _proposal(
            module,
            request,
            displayed_handle_ids=(hidden_company_id, *company_ids),
            claims=tuple(
                (
                    f"claim:{target_id}",
                    f"关联教授 {target_id}",
                    (target_id,),
                    (f"evidence:{source_id}:{target_id}",),
                )
                for source_id, target_id in company_bindings
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    first, papers, companies = tuple(answer.answer(request) for request in requests)

    assert first.context_receipt.active_anchor.kind == "canonical"
    assert first.context_receipt.active_anchor.canonical_id == professor_id
    assert (
        tuple(
            _handle_id(handle)
            for handle in papers.context_receipt.displayed_result_set.handles
        )
        == paper_ids
    )
    assert papers.context_receipt.active_anchor.canonical_id == professor_id
    assert papers.enumeration_coverage.mode == "representative"
    assert papers.enumeration_coverage.scope == paper_coverage.scope
    assert papers.enumeration_coverage.as_of == NOW
    assert papers.enumeration_coverage.displayed_ids == paper_ids
    assert papers.enumeration_coverage.continuation_state == "open_world"
    assert papers.continuation_offer.reasons == ("partial_coverage",)
    assert len(papers.continuation_offer.options) == 1
    assert (
        papers.continuation_offer.options[0].result_set_id
        == papers.context_receipt.displayed_result_set.result_set_id
    )
    assert papers.continuation_offer.options[0].constraint_pairs == (("year", "2024"),)

    traversal = companies.traversal_receipt
    assert companies.context_receipt.resolved_referent.kind == "result_set"
    assert companies.context_receipt.resolved_referent.handle_ids == paper_ids
    assert (
        companies.context_receipt.resolved_referent.result_set_id
        == papers.context_receipt.displayed_result_set.result_set_id
    )
    assert (
        companies.context_receipt.resolved_referent.enumeration_mode == "representative"
    )
    assert (
        companies.context_receipt.resolved_referent.continuation_state == "open_world"
    )
    assert traversal.path_id == "paper_to_professor"
    assert traversal.source_handle_ids == paper_ids
    assert traversal.target_handle_ids == company_ids
    assert (
        tuple(
            _handle_id(handle)
            for handle in companies.context_receipt.displayed_result_set.handles
        )
        == company_ids
    )
    assert hidden_paper_id not in traversal.source_handle_ids
    assert hidden_company_id not in traversal.target_handle_ids
    assert all(
        hidden_company_id not in claim.subject_handle_ids for claim in companies.claims
    )
    assert _constraint_pairs(companies.context_receipt) == {
        ("institution", "南方科技大学"),
        ("year", "2024"),
        ("geography", "深圳"),
    }
    assert companies.context_receipt.traversed_path_ids == (
        "professor_to_paper",
        "paper_to_professor",
    )
    assert companies.context_receipt.active_anchor.canonical_id == professor_id


def test_unresolved_web_handle_corefers_but_never_traverses_as_canonical() -> None:
    module = _answer_module()
    read_module = _read_module()
    session_id = "session:s9m:web-handle"
    canonical_id = "company:accepted-robotics"
    web_item, web_handle = _web_fixture(read_module, session_id=session_id)
    canonical_item = _item(
        read_module,
        evidence_id="evidence:company:accepted",
        object_id=canonical_id,
        domain="company",
        subject_id=canonical_id,
        predicate="preferred_name",
        value="Accepted Robotics",
        snippet="Accepted Robotics is present in the accepted release.",
    )
    canonical_handle = _canonical_handle(
        read_module,
        canonical_id=canonical_id,
        domain="company",
        display_name="Accepted Robotics",
        evidence_ids=(canonical_item.evidence_id,),
    )
    mixed_coverage = _coverage(
        read_module,
        scope="two displayed robotics Companies",
        retrieved_ids=(canonical_id, web_handle.handle_id),
        displayed_ids=(canonical_id, web_handle.handle_id),
    )
    list_request = _request(
        module,
        session_id=session_id,
        turn_id="turn:web:1",
        query="列出两家机器人公司",
        evidence_set=_evidence_set(
            read_module,
            query="列出两家机器人公司",
            items=(canonical_item, web_item),
            handles=(canonical_handle, web_handle),
            coverage=mixed_coverage,
        ),
    )
    detail_request = _request(
        module,
        session_id=session_id,
        turn_id="turn:web:2",
        query="第二家公司再讲详细些",
        evidence_set=_evidence_set(
            read_module,
            query="第二家公司再讲详细些",
        ),
        session_directive=module.SessionDirective(
            referent="displayed_member",
            displayed_ordinal=2,
        ),
    )
    raw_url = web_item.source_locator
    bad_patent_id = "patent:url-derived-bad"
    bad_patent_item = _item(
        read_module,
        evidence_id="evidence:bad-url-traversal",
        object_id=bad_patent_id,
        domain="patent",
        subject_id=bad_patent_id,
        predicate="patent_has_applicant",
        value=raw_url,
        snippet="This adversarial item incorrectly treats a URL as a Company identity.",
    )
    bad_patent_handle = _canonical_handle(
        read_module,
        canonical_id=bad_patent_id,
        domain="patent",
        display_name="URL-derived Patent",
        evidence_ids=(bad_patent_item.evidence_id,),
    )
    unresolved_revenue_part = read_module.MaterialQuestionPart(
        part_id="part:s9j:unresolved-web-current-revenue",
        text="HOSTILE_UNRESOLVED_WEB_PART_TEXT",
        subject_id=web_handle.handle_id,
        predicate="current_revenue",
        requested_value="2026",
    )
    unresolved_report = read_module.SufficiencyReport(
        decision_input_sha256="c" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=unresolved_revenue_part.part_id,
                outcome="missing",
                evidence_ids=(),
                rationale="No retained evidence supports current revenue.",
                uncertainty="high",
                confidence=0.0,
                answer_scoped=False,
                canonical=True,
            ),
        ),
        complete=False,
    )
    traversal_evidence = _evidence_set(
        read_module,
        query="它有哪些专利",
        items=(bad_patent_item,),
        handles=(bad_patent_handle,),
        requested_traversal=read_module.TypedTraversalRequest(
            path_id="company_to_patent",
            source_domain="company",
            target_domain="patent",
            relationship_type="patent_has_applicant",
            direction="inverse",
        ),
        material_parts=(unresolved_revenue_part,),
    ).model_copy(update={"sufficiency_report": unresolved_report})
    traversal_request = _request(
        module,
        session_id=session_id,
        turn_id="turn:web:3",
        query="它有哪些专利",
        evidence_set=traversal_evidence,
        session_directive=module.SessionDirective(referent="active_anchor"),
    )

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:web:1":
            return _proposal(
                module,
                request,
                displayed_handle_ids=(canonical_id, web_handle.handle_id),
            )
        if request.turn_id == "turn:web:2":
            return _proposal(
                module,
                request,
                displayed_handle_ids=(canonical_id,),
                claims=(
                    (
                        "claim:wrong-profile",
                        "A hostile proposal points back to the first Company.",
                        (canonical_id,),
                        (canonical_item.evidence_id,),
                    ),
                ),
            )
        return _proposal(
            module,
            request,
            displayed_handle_ids=(bad_patent_id,),
            claims=(
                (
                    "claim:bad-patent",
                    "The Web-only Company owns a Patent.",
                    (bad_patent_id,),
                    (bad_patent_item.evidence_id,),
                ),
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    listed = answer.answer(list_request)
    detailed = answer.answer(detail_request)
    blocked = answer.answer(traversal_request)

    listed_handles = listed.context_receipt.displayed_result_set.handles
    assert tuple(handle.kind for handle in listed_handles) == ("canonical", "web")
    assert tuple(_handle_id(handle) for handle in listed_handles) == (
        canonical_id,
        web_handle.handle_id,
    )
    assert listed_handles[1].evidence_snapshot_ids == web_handle.evidence_snapshot_ids
    assert listed_handles[1].resolution_state == "unresolved"
    assert raw_url != listed_handles[1].handle_id

    assert detailed.context_receipt.resolved_referent.kind == "displayed_member"
    assert detailed.context_receipt.resolved_referent.handle_ids == (
        web_handle.handle_id,
    )
    assert detailed.context_receipt.active_anchor.kind == "web"
    assert detailed.context_receipt.active_anchor.handle_id == web_handle.handle_id
    assert detailed.context_receipt.active_anchor.resolution_state == "unresolved"
    assert detailed.context_receipt.resolved_evidence_ids == (web_item.evidence_id,)
    assert all(
        canonical_id not in claim.subject_handle_ids for claim in detailed.claims
    )
    assert all(
        set(claim.evidence_ids) <= {web_item.evidence_id} for claim in detailed.claims
    )

    assert blocked.traversal_receipt is None
    assert blocked.claims == ()
    assert (
        blocked.context_receipt.performed_operation == "read_only_resolution_required"
    )
    assert blocked.context_receipt.active_anchor.kind == "web"
    assert blocked.context_receipt.active_anchor.handle_id == web_handle.handle_id
    assert blocked.context_receipt.active_anchor.evidence_snapshot_ids == (
        web_item.web_snapshot.snapshot_id,
    )
    assert any(
        limitation.code == "unresolved_web_handle_cannot_traverse"
        and limitation.handle_id == web_handle.handle_id
        and limitation.requested_path_id == "company_to_patent"
        for limitation in blocked.limitations
    )
    assert any(
        limitation.code == "material_evidence_missing"
        and limitation.material_part_id == unresolved_revenue_part.part_id
        for limitation in blocked.limitations
    )
    assert blocked.answer_text == (
        "The requested operation requires a resolved canonical handle.\n"
        "保留证据不足以支持问题中的 2026 年当前营收。"
    )
    assert "HOSTILE_UNRESOLVED_WEB_PART_TEXT" not in blocked.answer_text
    blocked_dump = blocked.model_dump(mode="python")
    assert raw_url not in _values_for_key(blocked_dump, "canonical_id")
    assert web_handle.handle_id not in _values_for_key(blocked_dump, "canonical_id")

    direct_patent_id = "patent:direct-web-traversal"
    direct_patent_item = _item(
        read_module,
        evidence_id="evidence:direct-web-traversal",
        object_id=direct_patent_id,
        domain="patent",
        subject_id=direct_patent_id,
        predicate="patent_has_applicant",
        value=web_handle.handle_id,
        snippet="A hostile current-turn edge treats an unresolved Web handle as Canonical.",
    )
    direct_patent_handle = _canonical_handle(
        read_module,
        canonical_id=direct_patent_id,
        domain="patent",
        display_name="Direct Web Traversal Patent",
        evidence_ids=(direct_patent_item.evidence_id,),
    )
    direct_session_id = "session:s9m:web-handle:direct"
    direct_web_handle = web_handle.model_copy(update={"session_id": direct_session_id})
    direct_request = _request(
        module,
        session_id=direct_session_id,
        turn_id="turn:web:direct",
        query="这家 Web 公司有哪些专利",
        evidence_set=_evidence_set(
            read_module,
            query="这家 Web 公司有哪些专利",
            items=(web_item, direct_patent_item),
            handles=(direct_web_handle, direct_patent_handle),
            requested_traversal=read_module.TypedTraversalRequest(
                path_id="company_to_patent",
                source_domain="company",
                target_domain="patent",
                relationship_type="patent_has_applicant",
                direction="inverse",
            ),
        ),
    )
    direct_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=lambda value: _proposal(
            module,
            value,
            displayed_handle_ids=(direct_patent_id,),
            claims=(
                (
                    "claim:direct-web-traversal",
                    "The unresolved Web Company owns this Patent.",
                    (direct_patent_id,),
                    (direct_patent_item.evidence_id,),
                ),
            ),
        )
    ).answer(direct_request)
    assert direct_answer.traversal_receipt is None
    assert direct_answer.claims == ()
    assert any(
        limitation.code == "unresolved_web_handle_cannot_traverse"
        and limitation.handle_id == web_handle.handle_id
        and limitation.requested_path_id == "company_to_patent"
        for limitation in direct_answer.limitations
    )


def _ambiguity_candidate(
    module: Any,
    *,
    handle_id: str,
    evidence_id: str,
    discriminator: str,
) -> Any:
    return module.AmbiguityCandidate(
        handle_id=handle_id,
        evidence_ids=(evidence_id,),
        discriminator=discriminator,
        viable=True,
        protected_constraint_conflict=False,
    )


def test_ambiguity_modes_and_selection_bind_the_exact_candidate() -> None:
    module = _answer_module()
    read_module = _read_module()
    candidate_ids = ("professor:li-wei-sustech", "professor:li-wei-szu")
    candidate_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{candidate_id}",
            object_id=candidate_id,
            domain="professor",
            subject_id=candidate_id,
            predicate="affiliation",
            value=affiliation,
            snippet=f"李伟 is affiliated with {affiliation}.",
        )
        for candidate_id, affiliation in zip(
            candidate_ids,
            ("南方科技大学", "深圳大学"),
            strict=True,
        )
    )
    candidate_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=candidate_id,
            domain="professor",
            display_name="李伟教授",
            evidence_ids=(item.evidence_id,),
        )
        for candidate_id, item in zip(candidate_ids, candidate_items, strict=True)
    )
    ambiguity_candidates = tuple(
        _ambiguity_candidate(
            read_module,
            handle_id=candidate_id,
            evidence_id=item.evidence_id,
            discriminator=affiliation,
        )
        for candidate_id, item, affiliation in zip(
            candidate_ids,
            candidate_items,
            ("南方科技大学", "深圳大学"),
            strict=True,
        )
    )
    web_snapshot_bytes = b"Recorded Web-only Professor candidate for ambiguity."
    web_snapshot_sha256 = hashlib.sha256(web_snapshot_bytes).hexdigest()
    web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:sha256:{web_snapshot_sha256}",
        content_sha256=web_snapshot_sha256,
        retrieved_at=NOW,
        byte_length=len(web_snapshot_bytes),
    )
    web_candidate_id = "web-handle:professor-li-wei-szu"
    web_candidate_item = _item(
        read_module,
        evidence_id="web:professor-li-wei-szu",
        object_id="web-object:professor-li-wei-szu",
        domain="professor",
        subject_id="web-object:professor-li-wei-szu",
        predicate="display_identity",
        value="李伟教授（深圳大学 Web 候选）",
        snippet="A bounded Web snapshot describes a same-name Professor at 深圳大学.",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/professors/li-wei-szu",
        web_snapshot=web_snapshot,
    )
    web_candidate_handle = read_module.WebEntityHandle(
        kind="web",
        handle_id=web_candidate_id,
        domain="professor",
        display_name="李伟教授（深圳大学 Web 候选）",
        evidence_snapshot_ids=(web_snapshot.snapshot_id,),
        evidence_ids=(web_candidate_item.evidence_id,),
        resolution_state="unresolved",
        candidate_canonical_ids=(),
        originating_query="介绍李伟教授",
        origin_lane="web",
        origin_attempt=1,
        session_id="session:s9m:ambiguity:blocking",
    )
    web_ambiguity_candidate = _ambiguity_candidate(
        read_module,
        handle_id=web_candidate_id,
        evidence_id=web_candidate_item.evidence_id,
        discriminator="深圳大学（Web snapshot）",
    )

    nonblocking_decision = read_module.AmbiguityDecision(
        decision_id="ambiguity:nonblocking",
        policy_version="ambiguity-policy-v1",
        outcome="selected",
        candidates=ambiguity_candidates,
        selected_handle_id=candidate_ids[0],
        viable_alternative_handle_ids=(candidate_ids[1],),
        decision_trace_id="trace:ambiguity:nonblocking",
    )
    nonblocking_request = _request(
        module,
        session_id="session:s9m:ambiguity:nonblocking",
        turn_id="turn:ambiguity:nb:1",
        query="介绍李伟教授",
        evidence_set=_evidence_set(
            read_module,
            query="介绍李伟教授",
            items=candidate_items,
            handles=candidate_handles,
            ambiguity_decision=nonblocking_decision,
        ),
    )

    def nonblocking_selector(request: Any) -> Any:
        selected_id = candidate_ids[0]
        selected_item = candidate_items[0]
        return _proposal(
            module,
            request,
            displayed_handle_ids=(selected_id,),
            claims=(
                (
                    f"claim:{selected_id}",
                    f"Answer for {selected_id}",
                    (selected_id,),
                    (selected_item.evidence_id,),
                ),
            ),
        )

    nonblocking_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=nonblocking_selector
    )
    interpreted = nonblocking_answer.answer(nonblocking_request)
    switch_options = tuple(
        option
        for option in interpreted.continuation_offer.options
        if option.operation == "switch_candidate"
    )
    assert interpreted.response_mode == "answer"
    assert interpreted.interpretation_notice.selected_handle_id == candidate_ids[0]
    assert interpreted.interpretation_notice.decision_trace_id == (
        nonblocking_decision.decision_trace_id
    )
    assert interpreted.continuation_offer.reasons == ("ambiguity",)
    assert len(switch_options) == 1
    assert switch_options[0].target_handle_ids == (candidate_ids[1],)
    assert all(
        candidate_ids[1] not in claim.subject_handle_ids for claim in interpreted.claims
    )

    switched = nonblocking_answer.answer(
        _request(
            module,
            session_id=nonblocking_request.session_id,
            turn_id="turn:ambiguity:nb:2",
            query="确认",
            evidence_set=_evidence_set(
                read_module,
                query="确认",
            ),
            continuation_selection=module.ContinuationSelection(
                offer_id=interpreted.continuation_offer.offer_id,
                option_id=switch_options[0].option_id,
            ),
        )
    )
    assert switched.context_receipt.transition_kind == "continuation_selection"
    assert switched.context_receipt.selected_option_id == switch_options[0].option_id
    assert switched.context_receipt.active_anchor.canonical_id == candidate_ids[1]
    assert switched.context_receipt.ambiguity_decision_trace_ids == (
        nonblocking_decision.decision_trace_id,
    )
    assert all(
        candidate_ids[0] not in claim.subject_handle_ids for claim in switched.claims
    )

    blocking_decision = read_module.AmbiguityDecision(
        decision_id="ambiguity:blocking",
        policy_version="ambiguity-policy-v1",
        outcome="blocked",
        candidates=(ambiguity_candidates[0], web_ambiguity_candidate),
        selected_handle_id=None,
        viable_alternative_handle_ids=(candidate_ids[0], web_candidate_id),
        decision_trace_id="trace:ambiguity:blocking",
    )
    blocked_product_part = read_module.MaterialQuestionPart(
        part_id="part:blocked-product-capability",
        text="Does a named Product have this capability?",
        subject_id="product:blocked",
        predicate="capability",
        requested_value="autonomous_navigation",
        answer_scoped=True,
    )
    blocking_revenue_part = read_module.MaterialQuestionPart(
        part_id="part:s9j:blocking-current-revenue",
        text="HOSTILE_BLOCKING_PART_TEXT",
        subject_id=candidate_ids[0],
        predicate="current_revenue",
        requested_value="2026",
    )
    blocking_report = read_module.SufficiencyReport(
        decision_input_sha256="a" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=blocking_revenue_part.part_id,
                outcome="missing",
                evidence_ids=(),
                rationale="No retained evidence supports current revenue.",
                uncertainty="high",
                confidence=0.0,
                answer_scoped=False,
                canonical=True,
            ),
        ),
        complete=False,
    )
    blocking_evidence = _evidence_set(
        read_module,
        query="介绍李伟教授",
        items=(candidate_items[0], web_candidate_item),
        handles=(candidate_handles[0], web_candidate_handle),
        ambiguity_decision=blocking_decision,
        material_parts=(blocked_product_part, blocking_revenue_part),
    ).model_copy(update={"sufficiency_report": blocking_report})
    blocking_request = _request(
        module,
        session_id="session:s9m:ambiguity:blocking",
        turn_id="turn:ambiguity:block:1",
        query="介绍李伟教授",
        evidence_set=blocking_evidence,
    )

    def hostile_blocking_selector(request: Any) -> Any:
        selected_id = candidate_ids[0]
        selected_item = candidate_items[0]
        return _proposal(
            module,
            request,
            displayed_handle_ids=(selected_id,),
            claims=(
                (
                    f"claim:{selected_id}",
                    "A primary answer that must be suppressed while ambiguity blocks.",
                    (selected_id,),
                    (selected_item.evidence_id,),
                ),
            ),
        )

    blocking_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=hostile_blocking_selector
    )
    clarification = blocking_answer.answer(blocking_request)
    assert clarification.response_mode == "clarification_only"
    assert clarification.claims == ()
    assert all(
        limitation.code != "direct_product_capability_evidence_missing"
        for limitation in clarification.limitations
    )
    assert any(
        limitation.code == "material_evidence_missing"
        and limitation.material_part_id == blocking_revenue_part.part_id
        for limitation in clarification.limitations
    )
    assert clarification.answer_text == (
        "Please select one of the evidenced candidates.\n"
        "保留证据不足以支持问题中的 2026 年当前营收。"
    )
    assert "HOSTILE_BLOCKING_PART_TEXT" not in clarification.answer_text
    assert (
        "Synthetic grounded answer for turn:ambiguity:block:1"
        not in clarification.answer_text
    )
    assert clarification.context_receipt.active_anchor is None
    assert clarification.continuation_offer.reasons == ("ambiguity",)
    assert len(clarification.continuation_offer.options) == 2
    assert tuple(
        option.target_handle_ids[0]
        for option in clarification.continuation_offer.options
    ) == (candidate_ids[0], web_candidate_id)
    assert tuple(
        option.discriminator for option in clarification.continuation_offer.options
    ) == ("南方科技大学", "深圳大学（Web snapshot）")
    assert all(
        option.evidence_ids for option in clarification.continuation_offer.options
    )

    selected_option = clarification.continuation_offer.options[1]
    selected = blocking_answer.answer(
        _request(
            module,
            session_id=blocking_request.session_id,
            turn_id="turn:ambiguity:block:2",
            query="确认",
            evidence_set=_evidence_set(read_module, query="确认"),
            continuation_selection=module.ContinuationSelection(
                offer_id=clarification.continuation_offer.offer_id,
                option_id=selected_option.option_id,
            ),
        )
    )
    assert selected.context_receipt.transition_kind == "clarification_selection"
    assert selected.context_receipt.selected_option_id == selected_option.option_id
    assert selected.context_receipt.active_anchor.kind == "web"
    assert selected.context_receipt.active_anchor.handle_id == web_candidate_id
    assert selected.context_receipt.active_anchor.evidence_snapshot_ids == (
        web_snapshot.snapshot_id,
    )
    assert selected.context_receipt.active_anchor.resolution_state == "unresolved"
    assert selected.context_receipt.ambiguity_decision_trace_ids == (
        blocking_decision.decision_trace_id,
    )
    assert all(
        candidate_ids[0] not in claim.subject_handle_ids for claim in selected.claims
    )


def _continuation_candidate(
    module: Any,
    *,
    candidate_id: str,
    reason: str,
    operation: str,
    target_kind: str,
    target_handle_id: str,
    evidence_id: str,
    available: bool = True,
) -> Any:
    return module.ContinuationCandidate(
        candidate_id=candidate_id,
        reason=reason,
        label=f"Execute {operation}",
        operation=operation,
        target_kind=target_kind,
        target_handle_ids=(
            (target_handle_id,) if target_kind == "current_handle" else ()
        ),
        constraint_pairs=(("geography", "深圳"),),
        relation_type=(
            "patent_has_applicant" if reason == "eligible_next_hop" else None
        ),
        coverage_state=("open_world" if reason == "partial_coverage" else None),
        evidence_ids=(evidence_id,),
        available=available,
    )


def test_continuation_triggers_bind_options_and_topic_switch_replaces_active_state() -> (
    None
):
    module = _answer_module()
    read_module = _read_module()
    trigger_operations = (
        ("broad_scope", "narrow_scope", "current_result_set"),
        ("ambiguity", "switch_candidate", "current_handle"),
        ("partial_coverage", "continue_coverage", "current_result_set"),
        ("evidence_gap", "targeted_evidence_search", "current_handle"),
        ("budget_exhausted", "resume_bounded_search", "current_result_set"),
        ("eligible_next_hop", "traverse_relationship", "current_handle"),
    )
    company_id = "company:continuation-base"
    company_item = _item(
        read_module,
        evidence_id="evidence:continuation-company",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="preferred_name",
        value="Continuation Robotics",
        snippet="Continuation Robotics is in the accepted release.",
    )
    company_handle = _canonical_handle(
        read_module,
        canonical_id=company_id,
        domain="company",
        display_name="Continuation Robotics",
        evidence_ids=(company_item.evidence_id,),
    )
    alternative_company_id = "company:continuation-alternative"
    alternative_company_item = _item(
        read_module,
        evidence_id="evidence:continuation-alternative",
        object_id=alternative_company_id,
        domain="company",
        subject_id=alternative_company_id,
        predicate="preferred_name",
        value="Alternative Robotics",
        snippet="Alternative Robotics is a distinct viable ambiguity candidate.",
    )
    alternative_company_handle = _canonical_handle(
        read_module,
        canonical_id=alternative_company_id,
        domain="company",
        display_name="Alternative Robotics",
        evidence_ids=(alternative_company_item.evidence_id,),
    )

    for index, (reason, operation, target_kind) in enumerate(
        trigger_operations, start=1
    ):
        target_handle_id = (
            alternative_company_id if reason == "ambiguity" else company_id
        )
        target_evidence_id = (
            alternative_company_item.evidence_id
            if reason == "ambiguity"
            else company_item.evidence_id
        )
        candidates = tuple(
            _continuation_candidate(
                read_module,
                candidate_id=f"continuation:{reason}:{candidate_index}",
                reason=reason,
                operation=operation,
                target_kind=target_kind,
                target_handle_id=target_handle_id,
                evidence_id=target_evidence_id,
                available=not (reason == "broad_scope" and candidate_index == 2),
            )
            for candidate_index in range(1, (6 if reason == "broad_scope" else 2))
        )
        first_request = _request(
            module,
            session_id=f"session:s9m:continuation:{reason}",
            turn_id=f"turn:continuation:{index}:1",
            query=f"Continuation trigger {reason}",
            evidence_set=_evidence_set(
                read_module,
                query=f"Continuation trigger {reason}",
                items=(
                    (company_item, alternative_company_item)
                    if reason == "ambiguity"
                    else (company_item,)
                ),
                handles=(
                    (company_handle, alternative_company_handle)
                    if reason == "ambiguity"
                    else (company_handle,)
                ),
                protected_slots=(_slot(read_module, "geography", "深圳"),),
                continuation_candidates=candidates,
            ),
        )

        def selector(
            request: Any, *, current_candidates: tuple[Any, ...] = candidates
        ) -> Any:
            if not request.turn_id.endswith(":1"):
                return _proposal(module, request)
            return _proposal(
                module,
                request,
                displayed_handle_ids=(company_id,),
                claims=(
                    (
                        f"claim:{request.turn_id}",
                        "A grounded Company claim.",
                        (company_id,),
                        (company_item.evidence_id,),
                    ),
                ),
                continuation_candidate_ids=tuple(
                    candidate.candidate_id for candidate in current_candidates
                ),
            )

        answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
        first = answer.answer(first_request)
        offer = first.continuation_offer
        expected_candidates = tuple(
            candidate for candidate in candidates if candidate.available
        )[:3]

        assert offer.reasons == (reason,)
        assert len(offer.options) == len(expected_candidates)
        assert len(offer.options) <= 3
        assert tuple(option.operation for option in offer.options) == tuple(
            candidate.operation for candidate in expected_candidates
        )
        assert tuple(option.source_candidate_id for option in offer.options) == tuple(
            candidate.candidate_id for candidate in expected_candidates
        )
        if target_kind == "current_handle":
            assert all(
                option.target_handle_ids == (target_handle_id,)
                for option in offer.options
            )
            assert all(option.result_set_id is None for option in offer.options)
        else:
            assert all(option.target_handle_ids == () for option in offer.options)
            assert all(
                option.result_set_id
                == first.context_receipt.displayed_result_set.result_set_id
                for option in offer.options
            )
        assert all(
            option.constraint_pairs == (("geography", "深圳"),)
            for option in offer.options
        )
        assert all(
            option.evidence_ids == (target_evidence_id,) for option in offer.options
        )
        if reason == "eligible_next_hop":
            assert all(
                option.relation_type == "patent_has_applicant"
                for option in offer.options
            )

        selected_option = offer.options[0]
        selected = answer.answer(
            _request(
                module,
                session_id=first_request.session_id,
                turn_id=f"turn:continuation:{index}:2",
                query="继续",
                evidence_set=_evidence_set(
                    read_module,
                    query="继续",
                ),
                continuation_selection=module.ContinuationSelection(
                    offer_id=offer.offer_id,
                    option_id=selected_option.option_id,
                ),
            )
        )
        receipt = selected.context_receipt
        assert receipt.transition_kind == "continuation_selection"
        assert receipt.selected_option_id == selected_option.option_id
        assert receipt.selected_operation == operation
        assert receipt.resolved_referent.handle_ids == (target_handle_id,)
        assert _constraint_pairs(receipt) == {("geography", "深圳")}

    simple_request = _request(
        module,
        session_id="session:s9m:complete-simple",
        turn_id="turn:complete-simple:1",
        query="Continuation Robotics 的名称是什么",
        evidence_set=_evidence_set(
            read_module,
            query="Continuation Robotics 的名称是什么",
            items=(company_item,),
            handles=(company_handle,),
        ),
    )

    def simple_selector(request: Any) -> Any:
        return _proposal(
            module,
            request,
            displayed_handle_ids=(company_id,),
            claims=(
                (
                    "claim:complete-simple",
                    "The accepted name is Continuation Robotics.",
                    (company_id,),
                    (company_item.evidence_id,),
                ),
            ),
        )

    simple_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=simple_selector
    ).answer(simple_request)
    assert simple_answer.response_mode == "answer"
    assert simple_answer.continuation_offer is None

    patent_id = "patent:CN117873146A"
    professor_id = "professor:topic-old"
    paper_id = "paper:topic-old-result"
    professor_item = _item(
        read_module,
        evidence_id="evidence:topic-professor",
        object_id=professor_id,
        domain="professor",
        subject_id=professor_id,
        predicate="preferred_name",
        value="旧话题教授",
        snippet="The prior turn explicitly names the old Professor.",
    )
    paper_item = _item(
        read_module,
        evidence_id="evidence:topic-paper",
        object_id=paper_id,
        domain="paper",
        subject_id=professor_id,
        predicate="professor_attributed_to_paper",
        value=paper_id,
        snippet="The old Professor authored the old displayed Paper.",
    )
    professor_handle = _canonical_handle(
        read_module,
        canonical_id=professor_id,
        domain="professor",
        display_name="旧话题教授",
        evidence_ids=(professor_item.evidence_id,),
    )
    paper_handle = _canonical_handle(
        read_module,
        canonical_id=paper_id,
        domain="paper",
        display_name="旧话题论文",
        evidence_ids=(paper_item.evidence_id,),
    )
    patent_item = _item(
        read_module,
        evidence_id="evidence:topic-patent",
        object_id=patent_id,
        domain="patent",
        subject_id=patent_id,
        predicate="applicant",
        value="company:new-topic",
        snippet="CN117873146A names company:new-topic as applicant.",
    )
    patent_handle = _canonical_handle(
        read_module,
        canonical_id=patent_id,
        domain="patent",
        display_name="CN117873146A",
        evidence_ids=(patent_item.evidence_id,),
    )
    prior_request = _request(
        module,
        session_id="session:s9m:topic-switch",
        turn_id="turn:topic:1",
        query="列出旧话题教授的 2024 年论文",
        evidence_set=_evidence_set(
            read_module,
            query="列出旧话题教授的 2024 年论文",
            items=(professor_item, paper_item),
            handles=(professor_handle, paper_handle),
            protected_slots=(_slot(read_module, "year", "2024"),),
            requested_traversal=read_module.TypedTraversalRequest(
                path_id="professor_to_paper",
                source_domain="professor",
                target_domain="paper",
                relationship_type="professor_attributed_to_paper",
                direction="forward",
            ),
        ),
    )
    switch_request = _request(
        module,
        session_id=prior_request.session_id,
        turn_id="turn:topic:2",
        query="换个话题，CN117873146A 的申请人是谁",
        evidence_set=_evidence_set(
            read_module,
            query="换个话题，CN117873146A 的申请人是谁",
            items=(patent_item,),
            handles=(patent_handle,),
            protected_slots=(_slot(read_module, "exact_identifier", "CN117873146A"),),
        ),
        session_directive=module.SessionDirective(transition="topic_switch"),
    )

    def topic_selector(request: Any) -> Any:
        if request.turn_id == prior_request.turn_id:
            return _proposal(
                module,
                request,
                displayed_handle_ids=(paper_id,),
                claims=(
                    (
                        "claim:old-paper",
                        "The old Professor authored the old Paper.",
                        (professor_id, paper_id),
                        (paper_item.evidence_id,),
                    ),
                ),
            )
        return _proposal(
            module,
            request,
            displayed_handle_ids=(patent_id,),
            claims=(
                (
                    "claim:new-patent",
                    "The Patent applicant is company:new-topic.",
                    (patent_id,),
                    (patent_item.evidence_id,),
                ),
            ),
        )

    topic_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=topic_selector
    )
    prior = topic_answer.answer(prior_request)
    switched = topic_answer.answer(switch_request)

    assert prior.context_receipt.active_anchor.canonical_id == professor_id
    assert prior.context_receipt.displayed_result_set.handle_ids == (paper_id,)
    assert prior.context_receipt.traversed_path_ids == ("professor_to_paper",)
    assert _constraint_pairs(prior.context_receipt) == {("year", "2024")}
    assert switched.context_receipt.transition_kind == "topic_switch"
    assert switched.context_receipt.active_anchor.canonical_id == patent_id
    assert switched.context_receipt.displayed_result_set.handle_ids == (patent_id,)
    assert switched.context_receipt.traversed_path_ids == ()
    assert _constraint_pairs(switched.context_receipt) == {
        ("exact_identifier", "CN117873146A")
    }
    assert switched.context_receipt.resolved_referent.handle_ids == (patent_id,)
    assert professor_id not in switched.context_receipt.resolved_referent.handle_ids
    assert paper_id not in switched.context_receipt.displayed_result_set.handle_ids
    assert switched.continuation_offer is None


def test_continuation_candidates_require_server_owned_executable_contract() -> None:
    module = _answer_module()
    read_module = _read_module()
    company_id = "company:continuation-policy"
    company_item = _item(
        read_module,
        evidence_id="evidence:continuation-policy",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="preferred_name",
        value="Policy Robotics",
        snippet="Policy Robotics is in the accepted release.",
    )
    company_handle = _canonical_handle(
        read_module,
        canonical_id=company_id,
        domain="company",
        display_name="Policy Robotics",
        evidence_ids=(company_item.evidence_id,),
    )
    invalid_operation = _continuation_candidate(
        read_module,
        candidate_id="continuation:invalid-operation",
        reason="broad_scope",
        operation="delete_data",
        target_kind="current_result_set",
        target_handle_id=company_id,
        evidence_id=company_item.evidence_id,
    )
    invalid_target = _continuation_candidate(
        read_module,
        candidate_id="continuation:invalid-target",
        reason="evidence_gap",
        operation="targeted_evidence_search",
        target_kind="current_result_set",
        target_handle_id=company_id,
        evidence_id=company_item.evidence_id,
    )
    missing_relation = _continuation_candidate(
        read_module,
        candidate_id="continuation:missing-relation",
        reason="eligible_next_hop",
        operation="traverse_relationship",
        target_kind="current_handle",
        target_handle_id=company_id,
        evidence_id=company_item.evidence_id,
    ).model_copy(update={"relation_type": None})
    stray_relation = _continuation_candidate(
        read_module,
        candidate_id="continuation:stray-relation",
        reason="broad_scope",
        operation="narrow_scope",
        target_kind="current_result_set",
        target_handle_id=company_id,
        evidence_id=company_item.evidence_id,
    ).model_copy(update={"relation_type": "company_committed_crimes"})
    poisoned_label = _continuation_candidate(
        read_module,
        candidate_id="continuation:poisoned-label",
        reason="partial_coverage",
        operation="continue_coverage",
        target_kind="current_result_set",
        target_handle_id=company_id,
        evidence_id=company_item.evidence_id,
    ).model_copy(update={"label": "This Company committed crimes."})
    valid = _continuation_candidate(
        read_module,
        candidate_id="continuation:valid-next-hop",
        reason="eligible_next_hop",
        operation="traverse_relationship",
        target_kind="current_handle",
        target_handle_id=company_id,
        evidence_id=company_item.evidence_id,
    )
    candidates = (
        invalid_operation,
        invalid_target,
        missing_relation,
        stray_relation,
        poisoned_label,
        valid,
    )
    first_request = _request(
        module,
        session_id="session:s9c1:continuation-policy",
        turn_id="turn:s9c1:continuation-policy:1",
        query="Show a safe continuation offer",
        evidence_set=_evidence_set(
            read_module,
            query="Show a safe continuation offer",
            items=(company_item,),
            handles=(company_handle,),
            protected_slots=(_slot(read_module, "geography", "深圳"),),
            continuation_candidates=candidates,
        ),
    )

    def selector(request: Any) -> Any:
        if request.turn_id != first_request.turn_id:
            return _proposal(module, request)
        return _proposal(
            module,
            request,
            displayed_handle_ids=(company_id,),
            claims=(
                (
                    "claim:continuation-policy",
                    "Policy Robotics is in the accepted release.",
                    (company_id,),
                    (company_item.evidence_id,),
                ),
            ),
            continuation_candidate_ids=tuple(
                candidate.candidate_id for candidate in candidates
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    first = answer.answer(first_request)
    offer = first.continuation_offer
    assert offer is not None
    assert tuple(option.source_candidate_id for option in offer.options) == (
        poisoned_label.candidate_id,
        valid.candidate_id,
    )
    assert tuple(option.label for option in offer.options) == (
        "Continue coverage",
        "Explore the available relationship",
    )
    assert offer.reasons == ("partial_coverage", "eligible_next_hop")
    assert len(offer.options) <= 3
    serialized_offer = offer.model_dump_json()
    assert poisoned_label.label not in serialized_offer
    assert invalid_operation.operation not in serialized_offer
    assert stray_relation.relation_type not in serialized_offer

    selected_option = offer.options[1]
    assert selected_option.target_handle_ids == (company_id,)
    assert selected_option.result_set_id is None
    assert selected_option.constraint_pairs == (("geography", "深圳"),)
    assert selected_option.evidence_ids == (company_item.evidence_id,)
    assert selected_option.relation_type == "patent_has_applicant"
    selected = answer.answer(
        _request(
            module,
            session_id=first_request.session_id,
            turn_id="turn:s9c1:continuation-policy:2",
            query="继续",
            evidence_set=_evidence_set(read_module, query="继续"),
            continuation_selection=module.ContinuationSelection(
                offer_id=offer.offer_id,
                option_id=selected_option.option_id,
            ),
        )
    )
    assert selected.context_receipt.transition_kind == "continuation_selection"
    assert selected.context_receipt.selected_option_id == selected_option.option_id
    assert selected.context_receipt.selected_operation == "traverse_relationship"
    assert selected.context_receipt.resolved_referent.handle_ids == (company_id,)
    assert selected.context_receipt.resolved_evidence_ids == (company_item.evidence_id,)
    assert _constraint_pairs(selected.context_receipt) == {("geography", "深圳")}

    invalid_query = "Reject every invalid continuation"
    invalid_request = _request(
        module,
        session_id="session:s9c1:continuation-invalid-only",
        turn_id="turn:s9c1:continuation-invalid-only:1",
        query=invalid_query,
        evidence_set=_evidence_set(
            read_module,
            query=invalid_query,
            items=(company_item,),
            handles=(company_handle,),
            continuation_candidates=(
                invalid_operation,
                invalid_target,
                missing_relation,
                stray_relation,
            ),
        ),
    )
    invalid_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=lambda request: _proposal(
            module,
            request,
            displayed_handle_ids=(company_id,),
            claims=(
                (
                    "claim:continuation-invalid-only",
                    "Policy Robotics is in the accepted release.",
                    (company_id,),
                    (company_item.evidence_id,),
                ),
            ),
            continuation_candidate_ids=(
                invalid_operation.candidate_id,
                invalid_target.candidate_id,
                missing_relation.candidate_id,
                stray_relation.candidate_id,
            ),
        )
    ).answer(invalid_request)
    assert invalid_answer.continuation_offer is None


def test_person_criteria_aggregate_claim_survives_displayed_set_scope() -> None:
    """Question-scoped person-criteria claims stay inside the turn scope.

    Serving mints one aggregate evidence item for person-criteria probes
    (founder/graduated-from over the displayed companies) whose subject is a
    synthetic question-scoped id, not a displayed handle. Handle binding must
    keep such claims within the displayed-set scope instead of dropping them,
    or founder findings gathered by the supplemental probes never reach the
    answer even though the evidence was retained and grounded.
    """
    module = _answer_module()
    read_module = _read_module()
    session_id = "session:s9m:person-criteria"
    company_ids = ("company:c-alpha", "company:c-beta")
    company_names = ("阿尔法机器人", "贝塔智能")
    company_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{company_id}",
            object_id=company_id,
            domain="company",
            subject_id=company_id,
            predicate="preferred_name",
            value=name,
            snippet=f"{name} 是一家深圳机器人企业。",
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    company_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=company_id,
            domain="company",
            display_name=name,
            evidence_ids=(f"evidence:{company_id}",),
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )

    part_subject = "serving-person-criteria:founder"
    snapshot_bytes = b"Recorded founder findings for the displayed companies."
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    aggregate_item = _item(
        read_module,
        evidence_id="web-evidence:sha256:person-aggregate",
        object_id=part_subject,
        domain="company",
        subject_id=part_subject,
        predicate="person_criteria",
        value="创始人",
        snippet=(
            '{"name": "阿尔法机器人、贝塔智能",'
            ' "profile_summary": "阿尔法机器人：创始人王甲；贝塔智能：创始人李乙"}'
        ),
        lane="supplemental",
        source_nature="supplemental_web",
        source_locator="https://example.test/founders",
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
            content_sha256=snapshot_sha256,
            retrieved_at=NOW,
            byte_length=len(snapshot_bytes),
        ),
    )

    first_request = _request(
        module,
        session_id=session_id,
        turn_id="turn:person-criteria:1",
        query="列出两家机器人公司",
        evidence_set=_evidence_set(
            read_module,
            query="列出两家机器人公司",
            items=company_items,
            handles=company_handles,
        ),
    )
    second_request = _request(
        module,
        session_id=session_id,
        turn_id="turn:person-criteria:2",
        query="这些公司的创始人都有谁",
        evidence_set=_evidence_set(
            read_module,
            query="这些公司的创始人都有谁",
            items=(aggregate_item,),
            handles=(),
        ),
        session_directive=module.SessionDirective(referent="displayed_result_set"),
    )

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:person-criteria:1":
            return _proposal(
                module,
                request,
                displayed_handle_ids=company_ids,
                claims=tuple(
                    (
                        f"claim:{company_id}",
                        f"展示公司 {company_id}",
                        (company_id,),
                        (f"evidence:{company_id}",),
                    )
                    for company_id in company_ids
                ),
            )
        return _proposal(
            module,
            request,
            claims=(
                (
                    "claim:founders",
                    "阿尔法机器人的创始人是王甲，贝塔智能的创始人是李乙。",
                    (),
                    (aggregate_item.evidence_id,),
                ),
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    first, second = (
        answer.answer(request) for request in (first_request, second_request)
    )

    assert (
        tuple(
            _handle_id(handle)
            for handle in first.context_receipt.displayed_result_set.handles
        )
        == company_ids
    )
    founder_claims = [
        claim for claim in second.claims if claim.subject_id == part_subject
    ]
    assert len(founder_claims) == 1
    assert set(founder_claims[0].subject_handle_ids) == set(company_ids)
    assert second.response_mode == "answer"


def test_question_scoped_subject_prefix_matches_serving_mint() -> None:
    """The answer layer's question-scoped prefix pin tracks the serving mint."""
    module = _answer_module()
    serving = import_module("src.data_agents.canonical_v2.knowledge_serving_isolated")
    assert module._QUESTION_SCOPED_SUBJECT_PREFIXES == (
        serving._PERSON_CRITERIA_PART_PREFIX,
    )


def test_prose_path_suppresses_deterministic_gap_jargon() -> None:
    """Prose owns insufficiency wording; the gap sentence stays in fallback.

    Live-derived: a prose answer that fully covered the question still ended
    with "保留证据不足以支持问题中的 关键部分。" whenever a sufficiency part
    stayed missing, contradicting the answer itself. The prose path now keeps
    the renderer's wording only; deterministic fallback keeps the honest gap
    sentence.
    """
    module = _answer_module()
    read_module = _read_module()
    session_id = "session:s9m:prose-gap"
    company_id = "company:gap-target"
    company_item = _item(
        read_module,
        evidence_id="evidence:gap-target",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="preferred_name",
        value="间隙科技",
        snippet="间隙科技是一家机器人企业。",
    )
    company_handle = _canonical_handle(
        read_module,
        canonical_id=company_id,
        domain="company",
        display_name="间隙科技",
        evidence_ids=(company_item.evidence_id,),
    )
    missing_part = read_module.MaterialQuestionPart(
        part_id="part:s9m:missing-revenue",
        text="2026 年营收",
        subject_id=company_id,
        predicate="current_revenue",
        requested_value="2026",
    )
    missing_report = read_module.SufficiencyReport(
        decision_input_sha256="d" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=missing_part.part_id,
                outcome="missing",
                evidence_ids=(),
                rationale="No retained evidence supports current revenue.",
                uncertainty="high",
                confidence=0.0,
                answer_scoped=False,
                canonical=True,
            ),
        ),
        complete=False,
    )
    evidence_set = _evidence_set(
        read_module,
        query="间隙科技怎么样，2026 年营收多少",
        items=(company_item,),
        handles=(company_handle,),
        material_parts=(missing_part,),
    ).model_copy(update={"sufficiency_report": missing_report})
    request = _request(
        module,
        session_id=session_id,
        turn_id="turn:prose-gap:1",
        query="间隙科技怎么样，2026 年营收多少",
        evidence_set=evidence_set,
    )

    def selector(inner: Any) -> Any:
        return _proposal(
            module,
            inner,
            displayed_handle_ids=(company_id,),
            claims=(
                (
                    "claim:gap-target",
                    "间隙科技是一家机器人企业。",
                    (company_id,),
                    (company_item.evidence_id,),
                ),
            ),
        )

    prose_text = "间隙科技是一家机器人企业，其2026年营收信息暂无法确认。"
    prose_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=lambda result: prose_text,
    )
    prose_result = prose_answer.answer(request)
    assert prose_result.render_mode == "prose_renderer"
    assert prose_result.answer_text == prose_text
    assert "保留证据不足以支持" not in prose_result.answer_text
    assert any(
        limitation.code == "material_evidence_missing"
        for limitation in prose_result.limitations
    )

    def timeout_renderer(result: Any) -> str:
        raise TimeoutError("renderer unavailable")

    fallback_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=timeout_renderer,
    )
    fallback_result = fallback_answer.answer(request)
    assert fallback_result.render_mode == "deterministic_fallback"
    assert "保留证据不足以支持问题中的 2026 年当前营收。" in (
        fallback_result.answer_text
    )


def test_zero_bound_claims_fails_open_with_attributed_web_evidence() -> None:
    """All proposal claims dropped by scope must not hard-degrade when
    bindable web evidence exists: answer from attributed evidence instead."""
    module = _answer_module()
    read_module = _read_module()
    snapshot_bytes = b"Recorded hotel delivery page for Ninebot."
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    web_item = _item(
        read_module,
        evidence_id="web-evidence:ninebot-hotel",
        object_id="web-object:sha256:ninebot",
        domain="company",
        subject_id="web-object:sha256:ninebot",
        predicate="display_identity",
        value="九号机器人酒店配送",
        snippet="九号机器人酒店配送方案：面向酒店客房送餐与楼宇配送场景。",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/ninebot-hotel",
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
            content_sha256=snapshot_sha256,
            retrieved_at=NOW,
            byte_length=len(snapshot_bytes),
        ),
    )
    company_ids = ("company:fail-open-alpha", "company:fail-open-beta")
    company_names = ("阿尔法机器人", "贝塔智能")
    company_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{company_id}",
            object_id=company_id,
            domain="company",
            subject_id=company_id,
            predicate="preferred_name",
            value=name,
            snippet=f"{name} 是一家深圳机器人企业。",
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    company_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=company_id,
            domain="company",
            display_name=name,
            evidence_ids=(f"evidence:{company_id}",),
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    first_request = _request(
        module,
        session_id="session:s9m:fail-open",
        turn_id="turn:fail-open:1",
        query="列出两家机器人公司",
        evidence_set=_evidence_set(
            read_module,
            query="列出两家机器人公司",
            items=company_items,
            handles=company_handles,
        ),
    )
    second_request = _request(
        module,
        session_id="session:s9m:fail-open",
        turn_id="turn:fail-open:2",
        query="这些公司的酒店配送能力如何",
        evidence_set=_evidence_set(
            read_module,
            query="这些公司的酒店配送能力如何",
            items=(web_item,),
        ),
    )

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:fail-open:1":
            return _proposal(
                module,
                request,
                displayed_handle_ids=company_ids,
            )
        return _proposal(
            module,
            request,
            displayed_handle_ids=(),
            claims=(
                (
                    "claim:out-of-scope",
                    "一家不在展示集内的公司。",
                    ("company:elsewhere",),
                    (web_item.evidence_id,),
                ),
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    answer.answer(first_request)
    result = answer.answer(second_request)
    assert result.response_mode == "answer"
    assert "九号机器人酒店配送" in result.answer_text
    assert any(
        limitation.code == "attributed_evidence_fallback"
        for limitation in result.limitations
    )
    assert result.claims[0].evidence_ids == (web_item.evidence_id,)
    assert tuple(mapping.claim_id for mapping in result.claim_evidence_map) == tuple(
        claim.claim_id for claim in result.claims
    )
    assert result.citations


def test_first_turn_attributed_fallback_keeps_session_for_prose_scope() -> None:
    """First-turn fail-open must keep the session state the turn created.

    The fallback branch restores the session snapshot before knowing whether
    attributed evidence can answer; on a first turn that pops the session
    ``_advance_session`` just created, and a prose renderer selecting a
    displayed entity then dies with a KeyError in ``_commit_prose_scope``.
    The restore belongs to the degrade path only: a successful fallback keeps
    the turn's session state and the prose scope commit works.
    """
    module = _answer_module()
    read_module = _read_module()
    snapshot_bytes = b"Recorded hotel delivery page for Ninebot."
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    web_item = _item(
        read_module,
        evidence_id="web-evidence:ninebot-hotel",
        object_id="web-object:sha256:ninebot",
        domain="company",
        subject_id="web-object:sha256:ninebot",
        predicate="display_identity",
        value="九号机器人酒店配送",
        snippet="九号机器人酒店配送方案：面向酒店客房送餐与楼宇配送场景。",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/ninebot-hotel",
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
            content_sha256=snapshot_sha256,
            retrieved_at=NOW,
            byte_length=len(snapshot_bytes),
        ),
    )
    company_ids = ("company:prose-scope-alpha", "company:prose-scope-beta")
    company_names = ("阿尔法机器人", "贝塔智能")
    company_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{company_id}",
            object_id=company_id,
            domain="company",
            subject_id=company_id,
            predicate="preferred_name",
            value=name,
            snippet=f"{name} 是一家深圳机器人企业。",
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    company_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=company_id,
            domain="company",
            display_name=name,
            evidence_ids=(f"evidence:{company_id}",),
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    request = _request(
        module,
        session_id="session:s9m:fail-open-prose",
        turn_id="turn:fail-open-prose:1",
        query="列出两家机器人公司并说明酒店配送能力",
        evidence_set=_evidence_set(
            read_module,
            query="列出两家机器人公司并说明酒店配送能力",
            items=(*company_items, web_item),
            handles=company_handles,
        ),
    )

    def selector(value: Any) -> Any:
        return _proposal(
            module,
            value,
            displayed_handle_ids=company_ids,
            claims=(
                (
                    "claim:out-of-scope",
                    "一家不在展示集内的公司。",
                    ("company:elsewhere",),
                    (web_item.evidence_id,),
                ),
            ),
        )

    def prose(result: Any) -> Any:
        return module.ProseSynthesisResult(
            answer_text=f"根据留存快照：{result.claims[0].text}",
            selected_claim_ids=tuple(claim.claim_id for claim in result.claims),
            selected_handle_ids=(company_ids[0],),
        )

    answer = module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=prose,
    )
    result = answer.answer(request)
    assert result.render_mode == "prose_renderer"
    assert "九号机器人酒店配送" in result.answer_text
    assert any(
        limitation.code == "attributed_evidence_fallback"
        for limitation in result.limitations
    )


def test_attributed_items_failing_grounding_keep_the_degrade() -> None:
    """Attributed fallback candidates must clear the same grounding guardrails
    as selector claims. Here the web item's snippet leaks its own evidence id
    (a structured-only value), so ``_ground_claim`` rejects the fallback claim
    and the turn keeps the original ``unsupported_material_claim`` degrade
    instead of answering from unsafe text."""
    module = _answer_module()
    read_module = _read_module()
    snapshot_bytes = b"Recorded hotel delivery page for Ninebot."
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    leaky_web_item = _item(
        read_module,
        evidence_id="web-evidence:ninebot-hotel-leaky",
        object_id="web-object:sha256:ninebot",
        domain="company",
        subject_id="web-object:sha256:ninebot",
        predicate="display_identity",
        value="九号机器人酒店配送",
        snippet=(
            "九号机器人酒店配送方案详情见 "
            "web-evidence:ninebot-hotel-leaky 快照页。"
        ),
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/ninebot-hotel",
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
            content_sha256=snapshot_sha256,
            retrieved_at=NOW,
            byte_length=len(snapshot_bytes),
        ),
    )
    company_ids = ("company:degrade-alpha", "company:degrade-beta")
    company_names = ("阿尔法机器人", "贝塔智能")
    company_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{company_id}",
            object_id=company_id,
            domain="company",
            subject_id=company_id,
            predicate="preferred_name",
            value=name,
            snippet=f"{name} 是一家深圳机器人企业。",
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    company_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=company_id,
            domain="company",
            display_name=name,
            evidence_ids=(f"evidence:{company_id}",),
        )
        for company_id, name in zip(company_ids, company_names, strict=True)
    )
    first_request = _request(
        module,
        session_id="session:s9m:fail-open-degrade",
        turn_id="turn:fail-open-degrade:1",
        query="列出两家机器人公司",
        evidence_set=_evidence_set(
            read_module,
            query="列出两家机器人公司",
            items=company_items,
            handles=company_handles,
        ),
    )
    second_request = _request(
        module,
        session_id="session:s9m:fail-open-degrade",
        turn_id="turn:fail-open-degrade:2",
        query="这些公司的酒店配送能力如何",
        evidence_set=_evidence_set(
            read_module,
            query="这些公司的酒店配送能力如何",
            items=(leaky_web_item,),
        ),
    )

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:fail-open-degrade:1":
            return _proposal(
                module,
                request,
                displayed_handle_ids=company_ids,
            )
        return _proposal(
            module,
            request,
            displayed_handle_ids=(),
            claims=(
                (
                    "claim:out-of-scope",
                    "一家不在展示集内的公司。",
                    ("company:elsewhere",),
                    (leaky_web_item.evidence_id,),
                ),
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    answer.answer(first_request)
    result = answer.answer(second_request)
    assert result.claims == ()
    assert result.render_mode == "deterministic_fallback"
    assert result.answer_text == "No supported material claims are available."
    assert any(
        limitation.code == "answer_selection_rejected"
        and limitation.reason == "unsupported_material_claim"
        for limitation in result.limitations
    )
    assert all(
        limitation.code != "attributed_evidence_fallback"
        for limitation in result.limitations
    )
