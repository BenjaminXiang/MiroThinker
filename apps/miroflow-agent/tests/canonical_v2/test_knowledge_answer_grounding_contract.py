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


def _web_snapshot(module: Any, token: str) -> Any:
    snapshot_bytes = f"Recorded bounded Web snapshot:{token}".encode()
    content_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    return module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:sha256:{content_sha256}",
        content_sha256=content_sha256,
        retrieved_at=NOW,
        byte_length=len(snapshot_bytes),
    )


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
    status: str | None = None,
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
        source_locator=source_locator or f"artifact:s9g#{evidence_id}",
        snippet=snippet,
        score=1.0,
        observed_at=NOW,
        claim_binding=module.EvidenceClaimBinding(
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            status=status,
        ),
        web_snapshot=web_snapshot,
    )


def _coverage(
    module: Any,
    *,
    mode: str,
    scope: str,
    checked_ids: tuple[str, ...],
    displayed_ids: tuple[str, ...],
    unknown_scope: bool,
    continuation_state: str,
    required_member_outcomes: tuple[Any, ...] = (),
) -> Any:
    omitted_ids = tuple(
        member_id for member_id in checked_ids if member_id not in displayed_ids
    )
    unknown_ids = omitted_ids if not unknown_scope else ()
    return module.EnumerationCoverage(
        mode=mode,
        scope=scope,
        as_of=NOW,
        checked_ids=checked_ids,
        eligible_ids=checked_ids,
        retrieved_ids=checked_ids,
        displayed_ids=displayed_ids,
        omitted_ids=omitted_ids,
        unknown_ids=unknown_ids,
        unknown_scope=unknown_scope,
        checked_count=len(checked_ids),
        eligible_count=len(checked_ids),
        retrieved_count=len(checked_ids),
        displayed_count=len(displayed_ids),
        omitted_count=len(omitted_ids),
        unknown_count=(None if unknown_scope else len(unknown_ids)),
        exhaustive=False,
        accounting_complete=True,
        required_member_outcomes=required_member_outcomes,
        continuation_state=continuation_state,
        continuation_required=True,
    )


def _evidence_set(
    module: Any,
    *,
    query: str,
    items: tuple[Any, ...],
    material_conflicts: tuple[Any, ...] = (),
    material_parts: tuple[Any, ...] = (),
    enumeration_coverage: Any | None = None,
    industry_brief_intent: Any | None = None,
) -> Any:
    return module.EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        material_conflicts=material_conflicts,
        material_parts=material_parts,
        enumeration_coverage=enumeration_coverage,
        industry_brief_intent=industry_brief_intent,
    )


def _request(
    module: Any,
    *,
    turn_id: str,
    query: str,
    evidence_set: Any,
) -> Any:
    return module.TurnRequest(
        session_id=f"session:s9g:{turn_id}",
        turn_id=turn_id,
        query=query,
        release_id=RELEASE_ID,
        evidence_set=evidence_set,
    )


def _claim(
    module: Any,
    *,
    claim_id: str,
    claim_type: str,
    text: str,
    subject_id: str,
    predicate: str,
    value: str,
    evidence_ids: tuple[str, ...],
    outcome: str = "supported",
    source_natures: tuple[str, ...] = (),
    synthesis: bool = False,
    answer_scoped: bool = False,
    canonical: bool = False,
    confirmed: bool = True,
    uncertainty: str | None = None,
    status: str | None = None,
) -> Any:
    return module.MaterialClaimProposal(
        claim_id=claim_id,
        claim_type=claim_type,
        text=text,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        subject_handle_ids=(subject_id,),
        evidence_ids=evidence_ids,
        outcome=outcome,
        source_natures=source_natures,
        synthesis=synthesis,
        answer_scoped=answer_scoped,
        canonical=canonical,
        confirmed=confirmed,
        uncertainty=uncertainty,
        status=status,
    )


def _proposal(
    module: Any,
    request: Any,
    *,
    claims: tuple[Any, ...],
    answer_text: str = "Recorded answer draft.",
    displayed_entity_ids: tuple[str, ...] = (),
    coverage_claim: str | None = None,
) -> Any:
    return module.AnswerSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id=f"answer-selection:{request.turn_id}",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id=f"answer-selector-run:{request.turn_id}",
        answer_text=answer_text,
        claims=claims,
        displayed_handle_ids=(),
        displayed_entity_ids=displayed_entity_ids,
        coverage_claim=coverage_claim,
        continuation_candidate_ids=(),
    )


def _by_claim_id(result: Any) -> dict[str, Any]:
    return {claim.claim_id: claim for claim in result.claims}


def _mapping_by_claim_id(result: Any) -> dict[str, Any]:
    return {mapping.claim_id: mapping for mapping in result.claim_evidence_map}


def _citations_by_evidence(result: Any) -> dict[str, Any]:
    return {citation.evidence_id: citation for citation in result.citations}


def _mapping_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _mapping_keys(nested)
        }
    if isinstance(value, (list, tuple)):
        return {key for nested in value for key in _mapping_keys(nested)}
    return set()


def test_material_claims_bind_exact_evidence_and_disclose_conflict_and_inference() -> (
    None
):
    module = _answer_module()
    read_module = _read_module()
    company_id = "company:example-robotics"
    professor_id = "professor:founder-1"
    founder = _item(
        read_module,
        evidence_id="evidence:founder",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="founded_by",
        value=professor_id,
        snippet="Example Robotics was founded by Professor One.",
    )
    role_local = _item(
        read_module,
        evidence_id="evidence:role-local",
        object_id=professor_id,
        domain="professor",
        subject_id=professor_id,
        predicate="current_role",
        value="chief_scientist",
        snippet="The accepted release lists the Professor as chief scientist.",
    )
    role_snapshot = _web_snapshot(read_module, "role-web")
    role_web = _item(
        read_module,
        evidence_id="evidence:role-web",
        object_id=professor_id,
        domain="professor",
        subject_id=professor_id,
        predicate="current_role",
        value="external_advisor",
        snippet="A current Web source lists the Professor as external adviser.",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/professors/founder-1",
        web_snapshot=role_snapshot,
    )
    deployment = _item(
        read_module,
        evidence_id="evidence:deployment",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="bounded_deployment_count",
        value="3",
        snippet="The retained evidence records three bounded deployments.",
    )
    unrelated = _item(
        read_module,
        evidence_id="evidence:unrelated-first",
        object_id="company:unrelated",
        domain="company",
        subject_id="company:unrelated",
        predicate="profile_summary",
        value="unrelated profile",
        snippet="This profile does not support any requested material claim.",
    )
    wrong_subject = _item(
        read_module,
        evidence_id="evidence:founder-wrong-subject",
        object_id="company:other-robotics",
        domain="company",
        subject_id="company:other-robotics",
        predicate="founded_by",
        value=professor_id,
        snippet="A different Company was founded by Professor One.",
    )
    wrong_predicate = _item(
        read_module,
        evidence_id="evidence:founder-wrong-predicate",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="advised_by",
        value=professor_id,
        snippet="Professor One advises Example Robotics.",
    )
    wrong_value = _item(
        read_module,
        evidence_id="evidence:founder-wrong-value",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="founded_by",
        value="professor:founder-2",
        snippet="Example Robotics was founded by Professor Two.",
    )
    conflict = read_module.EvidenceConflict(
        conflict_id="conflict:current-role",
        subject_id=professor_id,
        predicate="current_role",
        evidence_ids=(role_local.evidence_id, role_web.evidence_id),
        material=True,
        fusion_decision_id=None,
    )
    query = "这家公司的创始人是谁，他当前担任什么角色，并判断部署是否显示早期成熟？"
    request = _request(
        module,
        turn_id="turn:grounding:1",
        query=query,
        evidence_set=_evidence_set(
            read_module,
            query=query,
            items=(
                unrelated,
                wrong_subject,
                wrong_predicate,
                wrong_value,
                founder,
                role_local,
                role_web,
                deployment,
            ),
            material_conflicts=(conflict,),
        ),
    )
    valid_founder = _claim(
        module,
        claim_id="claim:founder",
        claim_type="relationship",
        text="Example Robotics was founded by Professor One.",
        subject_id=company_id,
        predicate="founded_by",
        value=professor_id,
        evidence_ids=(founder.evidence_id,),
        source_natures=("local",),
    )
    wrong_founder = _claim(
        module,
        claim_id="claim:wrong-founder",
        claim_type="relationship",
        text="The unrelated profile proves the founder relationship.",
        subject_id=company_id,
        predicate="founded_by",
        value=professor_id,
        evidence_ids=(unrelated.evidence_id,),
        source_natures=("local",),
    )
    wrong_subject_founder = _claim(
        module,
        claim_id="claim:founder-wrong-subject-binding",
        claim_type="relationship",
        text="The other Company's evidence proves this Company's founder.",
        subject_id=company_id,
        predicate="founded_by",
        value=professor_id,
        evidence_ids=(wrong_subject.evidence_id,),
        source_natures=("local",),
    )
    wrong_predicate_founder = _claim(
        module,
        claim_id="claim:founder-wrong-predicate-binding",
        claim_type="relationship",
        text="Adviser evidence proves the founder relationship.",
        subject_id=company_id,
        predicate="founded_by",
        value=professor_id,
        evidence_ids=(wrong_predicate.evidence_id,),
        source_natures=("local",),
    )
    wrong_value_founder = _claim(
        module,
        claim_id="claim:founder-wrong-value-binding",
        claim_type="relationship",
        text="Professor Two's evidence proves Professor One is the founder.",
        subject_id=company_id,
        predicate="founded_by",
        value=professor_id,
        evidence_ids=(wrong_value.evidence_id,),
        source_natures=("local",),
    )
    valid_conflict = _claim(
        module,
        claim_id="claim:role-conflict",
        claim_type="role",
        text="Current sources conflict on the Professor's role.",
        subject_id=professor_id,
        predicate="current_role",
        value="conflicting",
        evidence_ids=(role_local.evidence_id, role_web.evidence_id),
        outcome="conflicting_evidence",
        source_natures=("local", "current_web"),
        confirmed=False,
        uncertainty="material source conflict",
    )
    silent_role = _claim(
        module,
        claim_id="claim:silent-role",
        claim_type="role",
        text="The Professor is confirmed as chief scientist.",
        subject_id=professor_id,
        predicate="current_role",
        value="chief_scientist",
        evidence_ids=(role_local.evidence_id,),
        source_natures=("local",),
    )
    inference = _claim(
        module,
        claim_id="claim:deployment-inference",
        claim_type="model_inference",
        text="Three bounded deployments suggest early maturity.",
        subject_id=company_id,
        predicate="maturity_inference",
        value="early_maturity",
        evidence_ids=(deployment.evidence_id,),
        source_natures=("local",),
        synthesis=True,
        answer_scoped=True,
        confirmed=False,
        uncertainty="conditional on the retained deployment evidence",
    )
    fake_financing = _claim(
        module,
        claim_id="claim:model-memory-financing",
        claim_type="financing_event",
        text="The Company recently raised a Series C round.",
        subject_id=company_id,
        predicate="financing_round",
        value="Series C",
        evidence_ids=("model-memory:series-c",),
        confirmed=True,
    )

    def selector(value: Any) -> Any:
        return _proposal(
            module,
            value,
            claims=(
                valid_founder,
                wrong_founder,
                wrong_subject_founder,
                wrong_predicate_founder,
                wrong_value_founder,
                valid_conflict,
                silent_role,
                inference,
                fake_financing,
            ),
        )

    result = module.create_ephemeral_knowledge_answer(answer_selector=selector).answer(
        request
    )
    claims = _by_claim_id(result)
    mappings = _mapping_by_claim_id(result)
    citations = _citations_by_evidence(result)

    assert tuple(claims) == (
        "claim:founder",
        "claim:role-conflict",
        "claim:deployment-inference",
    )
    assert len(result.claims) == len(claims) == 3
    assert len(result.claim_evidence_map) == len(mappings) == 3
    assert set(mappings) == set(claims)
    for claim_id, claim in claims.items():
        mapping = mappings[claim_id]
        assert mapping.subject_id == claim.subject_id
        assert mapping.predicate == claim.predicate
        assert mapping.value == claim.value
        assert mapping.evidence_ids == claim.evidence_ids
        assert mapping.status == claim.status
    retained_evidence_ids = {
        evidence_id for claim in claims.values() for evidence_id in claim.evidence_ids
    }
    assert len(result.citations) == len(citations) == len(retained_evidence_ids)
    assert set(citations) == retained_evidence_ids
    assert claims["claim:founder"].evidence_ids == (founder.evidence_id,)
    assert mappings["claim:founder"].subject_id == company_id
    assert mappings["claim:founder"].predicate == "founded_by"
    assert mappings["claim:founder"].value == professor_id
    assert mappings["claim:founder"].evidence_ids == (founder.evidence_id,)
    assert claims["claim:role-conflict"].outcome == "conflicting_evidence"
    assert claims["claim:role-conflict"].confirmed is False
    assert claims["claim:role-conflict"].subject_id == professor_id
    assert claims["claim:role-conflict"].predicate == "current_role"
    assert claims["claim:role-conflict"].value == "conflicting"
    assert claims["claim:role-conflict"].status is None
    assert claims["claim:role-conflict"].evidence_ids == (
        role_local.evidence_id,
        role_web.evidence_id,
    )
    assert len(result.conflicts) == 1
    assert result.conflicts[0].conflict_id == conflict.conflict_id
    assert result.conflicts[0].evidence_ids == conflict.evidence_ids
    assert citations[founder.evidence_id].source_nature == "local"
    assert citations[founder.evidence_id].observed_at == NOW
    assert citations[role_local.evidence_id].source_nature == "local"
    assert citations[role_web.evidence_id].source_nature == "current_web"
    assert citations[role_web.evidence_id].web_snapshot_id == role_snapshot.snapshot_id
    assert citations[role_web.evidence_id].retrieved_at == NOW
    assert citations[role_web.evidence_id].source_locator == role_web.source_locator
    inferred = claims["claim:deployment-inference"]
    assert inferred.claim_type == "model_inference"
    assert inferred.synthesis is True
    assert inferred.answer_scoped is True
    assert inferred.canonical is False
    assert inferred.confirmed is False
    assert inferred.uncertainty
    assert inferred.subject_id == company_id
    assert inferred.predicate == "maturity_inference"
    assert inferred.value == "early_maturity"
    assert inferred.outcome == "supported"
    assert inferred.status is None
    assert inferred.evidence_ids == (deployment.evidence_id,)
    assert citations[deployment.evidence_id].source_nature == "local"
    assert citations[deployment.evidence_id].observed_at == NOW
    assert "claim:wrong-founder" not in claims
    assert "claim:founder-wrong-subject-binding" not in claims
    assert "claim:founder-wrong-predicate-binding" not in claims
    assert "claim:founder-wrong-value-binding" not in claims
    assert "claim:silent-role" not in claims
    assert "claim:model-memory-financing" not in claims
    assert "model-memory:series-c" not in {
        evidence_id for claim in claims.values() for evidence_id in claim.evidence_ids
    }


def test_product_capability_requires_direct_named_product_binding_and_status() -> None:
    module = _answer_module()
    read_module = _read_module()
    product_id = "product:delivery-robot-x1"
    capability = "autonomous_elevator_button_operation"
    traps = (
        _item(
            read_module,
            evidence_id="evidence:company-general",
            object_id="company:example-robotics",
            domain="company",
            subject_id="company:example-robotics",
            predicate="capability",
            value=capability,
            snippet="The Company describes a general elevator integration capability.",
        ),
        _item(
            read_module,
            evidence_id="evidence:other-product",
            object_id="product:delivery-robot-x2",
            domain="company",
            subject_id="product:delivery-robot-x2",
            predicate="capability",
            value=capability,
            snippet="Another Product has the requested demonstrated capability.",
            status="demonstrated",
        ),
        _item(
            read_module,
            evidence_id="evidence:same-product-wrong-capability",
            object_id=product_id,
            domain="company",
            subject_id=product_id,
            predicate="capability",
            value="autonomous_door_opening",
            snippet="The named Product has a different capability.",
            status="demonstrated",
        ),
        _item(
            read_module,
            evidence_id="evidence:technology-route",
            object_id="technology_route:elevator-integration",
            domain="technology_route",
            subject_id="technology_route:elevator-integration",
            predicate="demonstrated_use",
            value=capability,
            snippet="A Technology route makes the capability plausible.",
            status="demonstrated",
        ),
    )
    direct = _item(
        read_module,
        evidence_id="evidence:direct-product-capability",
        object_id=product_id,
        domain="company",
        subject_id=product_id,
        predicate="capability",
        value=capability,
        snippet="The named Product is demonstrated operating elevator buttons.",
        status="demonstrated",
    )
    part = read_module.MaterialQuestionPart(
        part_id="part:product-capability",
        text="Can delivery-robot-x1 autonomously operate elevator buttons?",
        subject_id=product_id,
        predicate="capability",
        requested_value=capability,
        material=True,
        answer_scoped=True,
    )

    def run(items: tuple[Any, ...], turn_id: str) -> Any:
        query = "delivery-robot-x1 能自主按电梯按钮吗？"
        request = _request(
            module,
            turn_id=turn_id,
            query=query,
            evidence_set=_evidence_set(
                read_module,
                query=query,
                items=items,
                material_parts=(part,),
            ),
        )
        proposals = [
            _claim(
                module,
                claim_id=f"claim:product-capability-hostile:{index}",
                claim_type="product_capability",
                text=(
                    "delivery-robot-x1 demonstrates autonomous elevator operation."
                    if item.claim_binding.status == "demonstrated"
                    else "delivery-robot-x1 has autonomous elevator operation."
                ),
                subject_id=product_id,
                predicate="capability",
                value=capability,
                evidence_ids=(item.evidence_id,),
                outcome="supported",
                answer_scoped=True,
                confirmed=True,
                status=item.claim_binding.status,
            )
            for index, item in enumerate(items)
            if item.evidence_id != direct.evidence_id
        ]
        proposals.append(
            _claim(
                module,
                claim_id="claim:product-capability-model-memory",
                claim_type="product_capability",
                text="Model memory says delivery-robot-x1 has the capability.",
                subject_id=product_id,
                predicate="capability",
                value=capability,
                evidence_ids=("model-memory:product-capability",),
                outcome="supported",
                answer_scoped=True,
                confirmed=True,
                status="demonstrated",
            )
        )
        if any(item.evidence_id == direct.evidence_id for item in items):
            proposals.insert(
                0,
                _claim(
                    module,
                    claim_id="claim:product-capability",
                    claim_type="product_capability",
                    text="delivery-robot-x1 demonstrates autonomous elevator operation.",
                    subject_id=product_id,
                    predicate="capability",
                    value=capability,
                    evidence_ids=(direct.evidence_id,),
                    outcome="supported",
                    source_natures=("local",),
                    answer_scoped=True,
                    confirmed=True,
                    status="demonstrated",
                ),
            )
            proposals.append(
                _claim(
                    module,
                    claim_id="claim:product-capability-status-promotion",
                    claim_type="product_capability",
                    text=(
                        "delivery-robot-x1 is commercially available with autonomous "
                        "elevator operation."
                    ),
                    subject_id=product_id,
                    predicate="capability",
                    value=capability,
                    evidence_ids=(direct.evidence_id,),
                    outcome="supported",
                    source_natures=("local",),
                    answer_scoped=True,
                    confirmed=True,
                    status="commercially_available",
                )
            )

        def selector(value: Any) -> Any:
            return _proposal(module, value, claims=tuple(proposals))

        return module.create_ephemeral_knowledge_answer(
            answer_selector=selector
        ).answer(request)

    unsupported = run(traps, "turn:product:unsupported")
    unsupported_claims = tuple(
        claim
        for claim in unsupported.claims
        if claim.claim_type == "product_capability"
    )
    assert len(unsupported_claims) == 1
    unsupported_claim = unsupported_claims[0]
    assert unsupported_claim.subject_id == product_id
    assert unsupported_claim.predicate == "capability"
    assert unsupported_claim.value == capability
    assert unsupported_claim.outcome in {"unsupported", "qualified"}
    assert unsupported_claim.evidence_ids == ()
    assert unsupported_claim.confirmed is False
    assert unsupported_claim.answer_scoped is True
    assert unsupported_claim.canonical is False
    assert unsupported_claim.status in {None, "unknown"}
    assert all(
        not claim.claim_id.startswith("claim:product-capability-hostile:")
        for claim in unsupported.claims
    )
    assert "claim:product-capability-model-memory" not in _by_claim_id(unsupported)
    assert all(
        "model-memory:product-capability" not in claim.evidence_ids
        for claim in unsupported.claims
    )
    unsupported_mappings = _mapping_by_claim_id(unsupported)
    assert len(unsupported.claim_evidence_map) == len(unsupported_mappings) == 1
    assert set(unsupported_mappings) == {unsupported_claim.claim_id}
    unsupported_mapping = unsupported_mappings[unsupported_claim.claim_id]
    assert unsupported_mapping.subject_id == product_id
    assert unsupported_mapping.predicate == "capability"
    assert unsupported_mapping.value == capability
    assert unsupported_mapping.evidence_ids == ()
    assert unsupported_mapping.status == unsupported_claim.status
    assert unsupported.citations == ()
    assert "product_has_capability" not in _mapping_keys(
        unsupported.model_dump(mode="python")
    )
    assert any(
        limitation.code == "direct_product_capability_evidence_missing"
        and limitation.material_part_id == part.part_id
        for limitation in unsupported.limitations
    )

    supported = run((*traps, direct), "turn:product:supported")
    supported_claims = tuple(
        claim for claim in supported.claims if claim.claim_type == "product_capability"
    )
    assert len(supported_claims) == 1
    supported_claim = supported_claims[0]
    assert supported_claim.subject_id == product_id
    assert supported_claim.predicate == "capability"
    assert supported_claim.value == capability
    assert supported_claim.outcome == "supported"
    assert supported_claim.evidence_ids == (direct.evidence_id,)
    assert supported_claim.status == "demonstrated"
    assert supported_claim.status != "commercially_available"
    assert supported_claim.answer_scoped is True
    assert supported_claim.canonical is False
    supported_mappings = _mapping_by_claim_id(supported)
    assert len(supported.claim_evidence_map) == len(supported_mappings) == 1
    assert set(supported_mappings) == {supported_claim.claim_id}
    supported_mapping = supported_mappings[supported_claim.claim_id]
    assert supported_mapping.subject_id == product_id
    assert supported_mapping.predicate == "capability"
    assert supported_mapping.value == capability
    assert supported_mapping.evidence_ids == (direct.evidence_id,)
    assert supported_mapping.status == "demonstrated"
    supported_citations = _citations_by_evidence(supported)
    assert len(supported.citations) == len(supported_citations) == 1
    assert set(supported_citations) == {direct.evidence_id}
    supported_citation = supported_citations[direct.evidence_id]
    assert supported_citation.source_nature == "local"
    assert supported_citation.source_locator == direct.source_locator
    assert supported_citation.observed_at == NOW
    assert "claim:product-capability-status-promotion" not in _by_claim_id(supported)
    assert "claim:product-capability-model-memory" not in _by_claim_id(supported)
    assert all(
        not claim.claim_id.startswith("claim:product-capability-hostile:")
        for claim in supported.claims
    )
    assert "product_has_capability" not in _mapping_keys(
        supported.model_dump(mode="python")
    )


def test_industry_brief_preserves_scope_routes_semantics_and_representative_coverage() -> (
    None
):
    module = _answer_module()
    read_module = _read_module()
    route_ids = ("technology_route:visual-servo", "technology_route:marker-nav")
    route_definitions = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:{route_id}:definition",
            object_id=route_id,
            domain="technology_route",
            subject_id=route_id,
            predicate="definition",
            value=definition,
            snippet=definition,
        )
        for route_id, definition in zip(
            route_ids,
            (
                "Visual servoing uses observed visual feedback for motion control.",
                "Marker navigation uses detected markers as bounded localization references.",
            ),
            strict=True,
        )
    )
    hidden_company = "company:hidden-first"
    displayed_companies = (
        "company:discussion",
        "company:demonstrated",
        "company:claimed",
        "company:conflicting",
    )
    hidden = _item(
        read_module,
        evidence_id="evidence:hidden-first",
        object_id=hidden_company,
        domain="company",
        subject_id=hidden_company,
        predicate="technology_discussion_or_mention",
        value=route_ids[0],
        snippet="This retrieved Company is intentionally not displayed.",
        status="discussion_or_mention",
    )
    discussion = _item(
        read_module,
        evidence_id="evidence:discussion",
        object_id=displayed_companies[0],
        domain="company",
        subject_id=displayed_companies[0],
        predicate="technology_discussion_or_mention",
        value=route_ids[0],
        snippet="The Company discusses the route but does not claim adoption.",
        status="discussion_or_mention",
    )
    demonstrated = _item(
        read_module,
        evidence_id="evidence:demonstrated",
        object_id=displayed_companies[1],
        domain="company",
        subject_id=displayed_companies[1],
        predicate="technology_demonstrated_use",
        value=route_ids[0],
        snippet="The retained evidence demonstrates use of the route.",
        status="demonstrated_use",
    )
    claimed = _item(
        read_module,
        evidence_id="evidence:claimed-adoption",
        object_id=displayed_companies[2],
        domain="company",
        subject_id=displayed_companies[2],
        predicate="technology_claimed_adoption",
        value=route_ids[1],
        snippet="The Company claims adoption of marker navigation.",
        status="claimed_adoption",
    )
    conflict_local = _item(
        read_module,
        evidence_id="evidence:route-conflict-local",
        object_id=displayed_companies[3],
        domain="company",
        subject_id=displayed_companies[3],
        predicate="technology_route_state",
        value=route_ids[1],
        snippet="The accepted local evidence records only discussion.",
        status="discussion_or_mention",
    )
    adoption_snapshot = _web_snapshot(read_module, "route-adoption")
    conflict_web = _item(
        read_module,
        evidence_id="evidence:route-conflict-web",
        object_id=displayed_companies[3],
        domain="company",
        subject_id=displayed_companies[3],
        predicate="technology_route_state",
        value=route_ids[1],
        snippet="A current Web source claims adoption of the route.",
        status="claimed_adoption",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/companies/conflicting-route",
        web_snapshot=adoption_snapshot,
    )
    checked_ids = (hidden_company, *displayed_companies)
    coverage = _coverage(
        read_module,
        mode="representative",
        scope="Shenzhen route landscape",
        checked_ids=checked_ids,
        displayed_ids=displayed_companies,
        unknown_scope=True,
        continuation_state="open_world",
    )
    conflict = read_module.EvidenceConflict(
        conflict_id="conflict:route-state",
        subject_id=displayed_companies[3],
        predicate="technology_route_state",
        evidence_ids=(conflict_local.evidence_id, conflict_web.evidence_id),
        material=True,
        fusion_decision_id=None,
    )
    intent = read_module.IndustryBriefIntent(
        release_id=RELEASE_ID,
        scope="Shenzhen route landscape",
        as_of=NOW,
        route_ids=route_ids,
        enumeration_mode="representative",
    )
    query = "比较视觉伺服和标记导航路线，并给出深圳代表性公司"
    request = _request(
        module,
        turn_id="turn:industry-brief:1",
        query=query,
        evidence_set=_evidence_set(
            read_module,
            query=query,
            items=(
                hidden,
                *route_definitions,
                discussion,
                demonstrated,
                claimed,
                conflict_local,
                conflict_web,
            ),
            material_conflicts=(conflict,),
            enumeration_coverage=coverage,
            industry_brief_intent=intent,
        ),
    )
    proposals = (
        *tuple(
            _claim(
                module,
                claim_id=f"claim:{route_id}:definition",
                claim_type="technology_route_definition",
                text=item.snippet,
                subject_id=route_id,
                predicate="definition",
                value=item.claim_binding.value,
                evidence_ids=(item.evidence_id,),
                source_natures=("local",),
            )
            for route_id, item in zip(route_ids, route_definitions, strict=True)
        ),
        _claim(
            module,
            claim_id="claim:discussion",
            claim_type="technology_relationship",
            text="The first Company discusses but does not adopt visual servoing.",
            subject_id=displayed_companies[0],
            predicate="technology_discussion_or_mention",
            value=route_ids[0],
            evidence_ids=(discussion.evidence_id,),
            status="discussion_or_mention",
        ),
        _claim(
            module,
            claim_id="claim:demonstrated",
            claim_type="technology_relationship",
            text="The second Company demonstrates use of visual servoing.",
            subject_id=displayed_companies[1],
            predicate="technology_demonstrated_use",
            value=route_ids[0],
            evidence_ids=(demonstrated.evidence_id,),
            status="demonstrated_use",
        ),
        _claim(
            module,
            claim_id="claim:route-conflict",
            claim_type="technology_relationship",
            text="Local and Web evidence conflict on the third Company's route state.",
            subject_id=displayed_companies[3],
            predicate="technology_route_state",
            value="conflicting",
            evidence_ids=(conflict_local.evidence_id, conflict_web.evidence_id),
            outcome="conflicting_evidence",
            source_natures=("local", "current_web"),
            confirmed=False,
            uncertainty="local discussion versus current-Web claimed adoption",
        ),
        _claim(
            module,
            claim_id="claim:claimed-adoption",
            claim_type="technology_relationship",
            text="The third Company claims adoption of marker navigation.",
            subject_id=displayed_companies[2],
            predicate="technology_claimed_adoption",
            value=route_ids[1],
            evidence_ids=(claimed.evidence_id,),
            status="claimed_adoption",
        ),
        _claim(
            module,
            claim_id="claim:discussion-promoted-to-adoption",
            claim_type="technology_relationship",
            text="The first displayed Company adopted visual servoing.",
            subject_id=displayed_companies[0],
            predicate="technology_claimed_adoption",
            value=route_ids[0],
            evidence_ids=(discussion.evidence_id,),
            status="claimed_adoption",
        ),
        _claim(
            module,
            claim_id="claim:hidden-adoption",
            claim_type="technology_relationship",
            text="The hidden first Company adopted the route.",
            subject_id=hidden_company,
            predicate="technology_claimed_adoption",
            value=route_ids[0],
            evidence_ids=(hidden.evidence_id,),
            status="claimed_adoption",
        ),
        _claim(
            module,
            claim_id="claim:unsupported-product-capability",
            claim_type="product_capability",
            text="A Product on this route has the requested capability.",
            subject_id="product:unsupported",
            predicate="capability",
            value="autonomous_elevator_button_operation",
            evidence_ids=(discussion.evidence_id,),
            answer_scoped=True,
        ),
    )

    def selector(value: Any) -> Any:
        return _proposal(
            module,
            value,
            claims=proposals,
            displayed_entity_ids=(hidden_company, *displayed_companies),
            coverage_claim="all Shenzhen Companies",
        )

    result = module.create_ephemeral_knowledge_answer(answer_selector=selector).answer(
        request
    )
    brief = result.industry_brief
    brief_claims = {claim.claim_id: claim for claim in brief.claims}
    brief_mappings = {mapping.claim_id: mapping for mapping in brief.claim_evidence_map}
    brief_citations = {citation.evidence_id: citation for citation in brief.citations}

    assert result.claims == brief.claims
    assert result.claim_evidence_map == brief.claim_evidence_map
    assert result.citations == brief.citations
    assert result.conflicts == brief.conflicts
    assert result.enumeration_coverage == brief.enumeration_coverage == coverage
    assert {limitation.code for limitation in brief.limitations} <= {
        limitation.code for limitation in result.limitations
    }
    assert any(
        limitation.code == "open_world_scope_unknown"
        for limitation in result.limitations
    )
    assert brief.release_id == RELEASE_ID
    assert brief.scope == intent.scope
    assert brief.as_of == NOW
    assert brief.route_ids == route_ids
    assert tuple(summary.route_id for summary in brief.route_summaries) == route_ids
    assert tuple(summary.definition for summary in brief.route_summaries) == tuple(
        item.claim_binding.value for item in route_definitions
    )
    findings_by_subject = {
        finding.subject_id: finding for finding in brief.relationship_findings
    }
    assert len(brief.relationship_findings) == len(findings_by_subject) == 4
    assert set(findings_by_subject) == set(displayed_companies)
    expected_findings = {
        displayed_companies[0]: (
            route_ids[0],
            "discussion_or_mention",
            (discussion.evidence_id,),
        ),
        displayed_companies[1]: (
            route_ids[0],
            "demonstrated_use",
            (demonstrated.evidence_id,),
        ),
        displayed_companies[2]: (
            route_ids[1],
            "claimed_adoption",
            (claimed.evidence_id,),
        ),
        displayed_companies[3]: (
            route_ids[1],
            "conflicting",
            (conflict_local.evidence_id, conflict_web.evidence_id),
        ),
    }
    for subject_id, (route_id, status, evidence_ids) in expected_findings.items():
        finding = findings_by_subject[subject_id]
        assert finding.route_id == route_id
        assert finding.status == status
        assert finding.evidence_ids == evidence_ids
    assert brief.displayed_entity_ids == displayed_companies
    assert hidden_company not in brief.displayed_entity_ids
    assert brief.enumeration_coverage == coverage
    assert brief.coverage_claim == "representative"
    assert any(
        limitation.code == "open_world_scope_unknown"
        for limitation in brief.limitations
    )
    assert "claim:hidden-adoption" not in brief_claims
    assert "claim:discussion-promoted-to-adoption" not in brief_claims
    assert "claim:unsupported-product-capability" not in brief_claims
    assert all(claim.evidence_ids for claim in brief.claims)
    assert set(brief_claims) == {
        f"claim:{route_ids[0]}:definition",
        f"claim:{route_ids[1]}:definition",
        "claim:discussion",
        "claim:demonstrated",
        "claim:claimed-adoption",
        "claim:route-conflict",
    }
    expected_claim_bindings = {
        f"claim:{route_ids[0]}:definition": (
            route_ids[0],
            "definition",
            route_definitions[0].claim_binding.value,
            (route_definitions[0].evidence_id,),
            None,
            "supported",
        ),
        f"claim:{route_ids[1]}:definition": (
            route_ids[1],
            "definition",
            route_definitions[1].claim_binding.value,
            (route_definitions[1].evidence_id,),
            None,
            "supported",
        ),
        "claim:discussion": (
            displayed_companies[0],
            "technology_discussion_or_mention",
            route_ids[0],
            (discussion.evidence_id,),
            "discussion_or_mention",
            "supported",
        ),
        "claim:demonstrated": (
            displayed_companies[1],
            "technology_demonstrated_use",
            route_ids[0],
            (demonstrated.evidence_id,),
            "demonstrated_use",
            "supported",
        ),
        "claim:claimed-adoption": (
            displayed_companies[2],
            "technology_claimed_adoption",
            route_ids[1],
            (claimed.evidence_id,),
            "claimed_adoption",
            "supported",
        ),
        "claim:route-conflict": (
            displayed_companies[3],
            "technology_route_state",
            "conflicting",
            (conflict_local.evidence_id, conflict_web.evidence_id),
            None,
            "conflicting_evidence",
        ),
    }
    for claim_id, expected_binding in expected_claim_bindings.items():
        claim = brief_claims[claim_id]
        assert (
            claim.subject_id,
            claim.predicate,
            claim.value,
            claim.evidence_ids,
            claim.status,
            claim.outcome,
        ) == expected_binding
    assert len(brief.claims) == len(brief_claims) == 6
    assert len(brief.claim_evidence_map) == len(brief_mappings) == 6
    assert set(brief_mappings) == set(brief_claims)
    for claim_id, claim in brief_claims.items():
        mapping = brief_mappings[claim_id]
        assert mapping.subject_id == claim.subject_id
        assert mapping.predicate == claim.predicate
        assert mapping.value == claim.value
        assert mapping.evidence_ids == claim.evidence_ids
        assert mapping.status == claim.status
    retained_brief_evidence_ids = {
        evidence_id
        for claim in brief_claims.values()
        for evidence_id in claim.evidence_ids
    }
    assert (
        len(brief.citations) == len(brief_citations) == len(retained_brief_evidence_ids)
    )
    assert set(brief_citations) == retained_brief_evidence_ids
    assert len(brief.conflicts) == 1
    assert brief.conflicts[0].conflict_id == conflict.conflict_id
    assert brief.conflicts[0].evidence_ids == conflict.evidence_ids
    for item in (*route_definitions, discussion, demonstrated, claimed, conflict_local):
        citation = brief_citations[item.evidence_id]
        assert citation.source_nature == "local"
        assert citation.source_locator == item.source_locator
        assert citation.observed_at == NOW
    assert brief_citations[conflict_web.evidence_id].source_nature == "current_web"
    assert brief_citations[conflict_web.evidence_id].source_locator == (
        conflict_web.source_locator
    )
    assert brief_citations[conflict_web.evidence_id].web_snapshot_id == (
        adoption_snapshot.snapshot_id
    )
    assert brief_citations[conflict_web.evidence_id].retrieved_at == NOW
    assert brief.derived is True
    assert brief.canonical is False
    assert set(brief.public_domains) == {"professor", "company", "paper", "patent"}
    assert "technology_route" in brief.internal_reference_types
    assert "product_has_capability" not in _mapping_keys(
        result.model_dump(mode="python")
    )
    serialized_result = result.model_dump_json()
    assert "claim:hidden-adoption" not in serialized_result
    assert "claim:discussion-promoted-to-adoption" not in serialized_result
    assert "claim:unsupported-product-capability" not in serialized_result


def test_prose_failure_returns_the_same_deterministic_grounded_fallback() -> None:
    module = _answer_module()
    read_module = _read_module()
    company_id = "company:fallback"
    evidence = _item(
        read_module,
        evidence_id="evidence:fallback-company",
        object_id=company_id,
        domain="company",
        subject_id=company_id,
        predicate="preferred_name",
        value="Fallback Robotics",
        snippet="The accepted Company name is Fallback Robotics.",
    )
    coverage = _coverage(
        read_module,
        mode="representative",
        scope="one bounded displayed Company",
        checked_ids=(company_id,),
        displayed_ids=(company_id,),
        unknown_scope=True,
        continuation_state="open_world",
    )
    query = "介绍 Fallback Robotics"
    request = _request(
        module,
        turn_id="turn:fallback:1",
        query=query,
        evidence_set=_evidence_set(
            read_module,
            query=query,
            items=(evidence,),
            enumeration_coverage=coverage,
        ),
    )
    grounded_claim = _claim(
        module,
        claim_id="claim:fallback-name",
        claim_type="identity",
        text="The accepted Company name is Fallback Robotics.",
        subject_id=company_id,
        predicate="preferred_name",
        value="Fallback Robotics",
        evidence_ids=(evidence.evidence_id,),
        source_natures=("local",),
    )
    poison = "POISONED_UNSUPPORTED_SERIES_C_FACT"

    def selector(value: Any) -> Any:
        return _proposal(
            module,
            value,
            claims=(grounded_claim,),
            answer_text=poison,
        )

    def timed_out_renderer(_: Any) -> Any:
        raise TimeoutError("recorded prose renderer timeout")

    def execute() -> Any:
        return module.create_ephemeral_knowledge_answer(
            answer_selector=selector,
            prose_renderer=timed_out_renderer,
        ).answer(request)

    first = execute()
    second = execute()
    assert first.render_mode == "deterministic_fallback"
    assert len(first.claims) == 1
    assert len(first.claim_evidence_map) == 1
    assert len(first.citations) == 1
    assert first.claims == second.claims
    assert first.claim_evidence_map == second.claim_evidence_map
    assert first.citations == second.citations
    assert first.enumeration_coverage == second.enumeration_coverage == coverage
    assert first.answer_text == second.answer_text
    assert first.fallback_sha256 == second.fallback_sha256
    fallback_claim = first.claims[0]
    assert fallback_claim.claim_id == grounded_claim.claim_id
    assert fallback_claim.claim_type == grounded_claim.claim_type
    assert fallback_claim.text == grounded_claim.text
    assert fallback_claim.subject_id == company_id
    assert fallback_claim.predicate == "preferred_name"
    assert fallback_claim.value == "Fallback Robotics"
    assert fallback_claim.outcome == "supported"
    assert fallback_claim.evidence_ids == (evidence.evidence_id,)
    assert fallback_claim.confirmed is True
    assert fallback_claim.canonical is False
    fallback_mapping = first.claim_evidence_map[0]
    assert fallback_mapping.claim_id == grounded_claim.claim_id
    assert fallback_mapping.subject_id == company_id
    assert fallback_mapping.predicate == "preferred_name"
    assert fallback_mapping.value == "Fallback Robotics"
    assert fallback_mapping.evidence_ids == (evidence.evidence_id,)
    assert fallback_mapping.status is None
    fallback_citation = first.citations[0]
    assert fallback_citation.evidence_id == evidence.evidence_id
    assert fallback_citation.source_nature == "local"
    assert fallback_citation.source_locator == evidence.source_locator
    assert fallback_citation.observed_at == NOW
    assert first.answer_text
    assert poison not in first.answer_text
    assert all(poison not in claim.text for claim in first.claims)
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.stage == "prose"
        and limitation.failure_kind == "timeout"
        for limitation in first.limitations
    )
