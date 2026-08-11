from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest


ANSWER_TARGET = "src.data_agents.canonical_v2.knowledge_answer"
READ_TARGET = "src.data_agents.canonical_v2.knowledge_read"
NOW = datetime(2026, 7, 20, 11, 15, tzinfo=UTC)
RELEASE_ID = "candidate-s9i"


def _answer_module() -> Any:
    return import_module(ANSWER_TARGET)


def _read_module() -> Any:
    return import_module(READ_TARGET)


def _acknowledging_append(items: list[str]) -> Callable[[str], bool]:
    def append(text: str) -> bool:
        items.append(text)
        return True

    return append


def _snapshot(module: Any, token: str) -> Any:
    payload = f"Recorded bounded S9I snapshot:{token}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    return module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s9i:sha256:{digest}",
        content_sha256=digest,
        retrieved_at=NOW,
        byte_length=len(payload),
    )


def _item(
    module: Any,
    *,
    evidence_id: str,
    object_id: str,
    subject_id: str,
    predicate: str,
    value: str,
    snippet: str,
    status: str | None = None,
    domain: str = "company",
    lane: str = "exact",
    source_nature: str = "local",
    source_authority: str = "other",
    source_locator: str | None = None,
    web_snapshot: Any | None = None,
) -> Any:
    return module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=object_id,
        domain=domain,
        lane=lane,
        source_nature=source_nature,
        source_authority=source_authority,
        source_locator=source_locator or f"artifact:s9i#{evidence_id}",
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


def _evidence_set(
    module: Any,
    *,
    query: str,
    release_id: str = RELEASE_ID,
    items: tuple[Any, ...] = (),
    conflicts: tuple[Any, ...] = (),
    handles: tuple[Any, ...] = (),
    material_parts: tuple[Any, ...] = (),
    sufficiency_report: Any | None = None,
    continuation_candidates: tuple[Any, ...] = (),
) -> Any:
    return module.EvidenceSet(
        release_id=release_id,
        original_query=query,
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        material_conflicts=conflicts,
        entity_handles=handles,
        material_parts=material_parts,
        sufficiency_report=sufficiency_report,
        continuation_candidates=continuation_candidates,
    )


def _turn(
    module: Any,
    *,
    session_id: str,
    turn_id: str,
    evidence_set: Any,
    assessment_intent: Any | None = None,
    session_directive: Any | None = None,
    safety_guidance: Any | None = None,
) -> Any:
    values: dict[str, Any] = {
        "session_id": session_id,
        "turn_id": turn_id,
        "query": evidence_set.original_query,
        "release_id": evidence_set.release_id,
        "evidence_set": evidence_set,
    }
    if assessment_intent is not None:
        values["assessment_intent"] = assessment_intent
    if session_directive is not None:
        values["session_directive"] = session_directive
    if safety_guidance is not None:
        values["safety_guidance"] = safety_guidance
    return module.TurnRequest(**values)


def _claim(
    module: Any,
    *,
    claim_id: str,
    text: str,
    subject_id: str | None,
    predicate: str | None,
    value: str | None,
    evidence_ids: tuple[str, ...],
    status: str | None = None,
    outcome: str = "supported",
    confirmed: bool = True,
) -> Any:
    return module.MaterialClaimProposal(
        claim_id=claim_id,
        text=text,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        subject_handle_ids=(() if subject_id is None else (subject_id,)),
        evidence_ids=evidence_ids,
        outcome=outcome,
        confirmed=confirmed,
        uncertainty=("material retained conflict" if not confirmed else None),
        status=status,
    )


def _constructed_answer_proposal(
    module: Any,
    request: Any,
    *,
    claims: tuple[Any, ...] = (),
    answer_text: str = "NON_AUTHORITATIVE_RAW_DRAFT",
    displayed_handle_ids: tuple[str, ...] = (),
) -> Any:
    return module.AnswerSelectionProposal.model_construct(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id=f"answer-selection:{request.turn_id}",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id=f"answer-selector-run:{request.turn_id}",
        answer_text=answer_text,
        claims=claims,
        displayed_handle_ids=displayed_handle_ids,
        displayed_entity_ids=(),
        coverage_claim=None,
        continuation_candidate_ids=(),
    )


def _answer_proposal(
    module: Any,
    request: Any,
    *,
    claim: Any,
    selection_input_sha256: str | None = None,
    schema_version: str = "answer-selection-v1",
    answer_text: str = "NON_AUTHORITATIVE_RAW_DRAFT",
) -> Any:
    return module.AnswerSelectionProposal(
        selection_input_sha256=(
            request.content_sha256
            if selection_input_sha256 is None
            else selection_input_sha256
        ),
        schema_version=schema_version,
        decision_id=f"answer-selection:{request.turn_id}:recorded",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id=f"answer-selector-run:{request.turn_id}",
        answer_text=answer_text,
        claims=(claim,),
    )


def _assessment_binding(module: Any, item: Any) -> Any:
    binding = item.claim_binding
    assert binding is not None
    return module.AssessmentEvidenceBinding(
        evidence_id=item.evidence_id,
        subject_id=binding.subject_id,
        predicate=binding.predicate,
        value=binding.value,
        status=binding.status,
    )


def _assessment_proposal(
    module: Any,
    request: Any,
    *,
    dimensions: tuple[Any, ...],
    selection_input_sha256: str | None = None,
    schema_version: str = "assessment-selection-v1",
    synthesis: str = "POISONED_MODEL_AUTHORED_ASSESSMENT_SYNTHESIS",
) -> Any:
    return module.AssessmentSelectionProposal(
        selection_input_sha256=(
            request.content_sha256
            if selection_input_sha256 is None
            else selection_input_sha256
        ),
        schema_version=schema_version,
        decision_id=f"assessment-selection:{request.turn_id}",
        model_id="recorded-assessment-selector",
        prompt_version="assessment-selector-prompt-v1",
        decision_run_id=f"assessment-selector-run:{request.turn_id}",
        dimensions=dimensions,
        conditional_synthesis=synthesis,
    )


def _canonical_handle(
    module: Any,
    *,
    canonical_id: str,
    evidence_id: str,
) -> Any:
    return module.CanonicalEntityHandle(
        canonical_id=canonical_id,
        domain="company",
        display_name=canonical_id.rsplit(":", 1)[-1],
        evidence_ids=(evidence_id,),
    )


def _web_handle(
    module: Any,
    *,
    token: str,
    evidence_id: str,
    snapshot_id: str,
    session_id: str | None,
) -> Any:
    return module.WebEntityHandle(
        handle_id=f"web-handle:s9i:{token}",
        domain="company",
        display_name=f"Web Company {token}",
        evidence_snapshot_ids=(snapshot_id,),
        evidence_ids=(evidence_id,),
        resolution_state="unresolved",
        candidate_canonical_ids=(),
        originating_query=f"S9I Web handle {token}",
        origin_lane="web",
        origin_attempt=1,
        session_id=session_id,
        expires_at=NOW.replace(hour=12),
    )


def _web_policy(
    module: Any,
    mode: str,
    *,
    allowed_domains: tuple[str, ...] = (),
) -> Any:
    if mode == "disabled":
        return module.WebSearchPolicy(mode="disabled")
    return module.WebSearchPolicy(
        mode=mode,
        max_provider_calls=1,
        timeout_ms=1_500,
        max_results=3,
        allowed_domains=allowed_domains,
    )


def _plan(
    module: Any,
    *,
    query: str,
    interaction_mode: str,
    web_mode: str,
    release_id: str = RELEASE_ID,
) -> Any:
    information = interaction_mode == "information_retrieval"
    official = web_mode == "official_only"
    return module.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query=query,
        behavior_class=("A" if information else "F"),
        interaction_mode=interaction_mode,
        release_id=release_id,
        domains=("company",) if information else (),
        protected_slots=(),
        lanes=(("exact", "web") if information else ("web",) if official else ()),
        max_candidates=10,
        web_required=web_mode != "disabled",
        web_policy=_web_policy(
            module,
            web_mode,
            allowed_domains=("sz.gov.cn",) if official else (),
        ),
        freshness_material=web_mode != "disabled",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_material_claim_requires_complete_binding_and_filtered_draft_never_leaks() -> (
    None
):
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9i-alpha"
    exact = _item(
        read_module,
        evidence_id="evidence:s9i:exact-name",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="S9I Alpha Robotics",
        status="accepted",
        snippet="The accepted Company name is S9I Alpha Robotics.",
    )
    role_local = _item(
        read_module,
        evidence_id="evidence:s9i:role-local",
        object_id=company_id,
        subject_id=company_id,
        predicate="current_role",
        value="chief_scientist",
        status="accepted",
        snippet="The local release records a chief scientist role.",
    )
    role_web = _item(
        read_module,
        evidence_id="evidence:s9i:role-web",
        object_id=company_id,
        subject_id=company_id,
        predicate="current_role",
        value="external_advisor",
        status="reported",
        snippet="A current source reports an external adviser role.",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/s9i/alpha-role",
        web_snapshot=_snapshot(read_module, "alpha-role"),
    )
    conflict = read_module.EvidenceConflict(
        conflict_id="conflict:s9i:current-role",
        subject_id=company_id,
        predicate="current_role",
        evidence_ids=(role_local.evidence_id, role_web.evidence_id),
        material=True,
        fusion_decision_id=None,
    )
    unstructured = read_module.EvidenceItem(
        evidence_id="evidence:s9i:unstructured-inference",
        object_id=company_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator="artifact:s9i#unstructured-inference",
        snippet="An unstructured snippet cannot ground a material inference.",
        score=1.0,
        observed_at=NOW,
    )
    query = "确认公司名称并披露当前角色冲突"
    request = _turn(
        answer_module,
        session_id="session:s9i:claim-gate",
        turn_id="turn:s9i:claim-gate",
        evidence_set=_evidence_set(
            read_module,
            query=query,
            items=(exact, role_local, role_web, unstructured),
            conflicts=(conflict,),
        ),
    )
    valid = _claim(
        answer_module,
        claim_id="claim:s9i:valid-name",
        text="S9I Alpha Robotics is the accepted Company name.",
        subject_id=company_id,
        predicate="preferred_name",
        value="S9I Alpha Robotics",
        status="accepted",
        evidence_ids=(exact.evidence_id,),
    )
    valid_conflict = _claim(
        answer_module,
        claim_id="claim:s9i:valid-role-conflict",
        text="Retained sources materially disagree on the current role.",
        subject_id=company_id,
        predicate="current_role",
        value="conflicting",
        evidence_ids=conflict.evidence_ids,
        outcome="conflicting_evidence",
        confirmed=False,
    )
    poison_claims = (
        _claim(
            answer_module,
            claim_id="claim:s9i:missing-subject",
            text="POISON_MISSING_SUBJECT",
            subject_id=None,
            predicate="preferred_name",
            value="S9I Alpha Robotics",
            evidence_ids=(exact.evidence_id,),
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:missing-predicate",
            text="POISON_MISSING_PREDICATE",
            subject_id=company_id,
            predicate=None,
            value="S9I Alpha Robotics",
            evidence_ids=(exact.evidence_id,),
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:missing-value",
            text="POISON_MISSING_VALUE",
            subject_id=company_id,
            predicate="preferred_name",
            value=None,
            evidence_ids=(exact.evidence_id,),
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:mismatched-binding",
            text="POISON_MISMATCHED_BINDING",
            subject_id=company_id,
            predicate="preferred_name",
            value="Wrong Company",
            evidence_ids=(exact.evidence_id,),
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:unknown-evidence",
            text="POISON_UNKNOWN_EVIDENCE",
            subject_id=company_id,
            predicate="preferred_name",
            value="S9I Alpha Robotics",
            evidence_ids=("evidence:s9i:unknown",),
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:duplicate-evidence",
            text="POISON_DUPLICATE_EVIDENCE",
            subject_id=company_id,
            predicate="preferred_name",
            value="S9I Alpha Robotics",
            status="accepted",
            evidence_ids=(exact.evidence_id, exact.evidence_id),
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:partial-conflict",
            text="POISON_PARTIAL_CONFLICT",
            subject_id=company_id,
            predicate="current_role",
            value="conflicting",
            evidence_ids=(role_local.evidence_id,),
            outcome="conflicting_evidence",
            confirmed=False,
        ),
        answer_module.MaterialClaimProposal(
            claim_id="claim:s9i:unstructured-inference",
            claim_type="model_inference",
            text="POISON_UNSTRUCTURED_INFERENCE",
            subject_id=company_id,
            predicate="maturity_inference",
            value="mature",
            evidence_ids=(unstructured.evidence_id,),
            outcome="supported",
            synthesis=True,
            answer_scoped=True,
            confirmed=False,
            uncertainty="unsupported because the evidence has no structured binding",
        ),
        _claim(
            answer_module,
            claim_id="claim:s9i:arbitrary-outcome",
            text="POISON_ARBITRARY_OUTCOME",
            subject_id=company_id,
            predicate="preferred_name",
            value="S9I Alpha Robotics",
            status="accepted",
            evidence_ids=(exact.evidence_id,),
            outcome="selector_authored_unsupported",
        ),
    )
    raw_draft = "RAW_DRAFT " + " ".join(claim.text for claim in poison_claims)
    proposal = _constructed_answer_proposal(
        answer_module,
        request,
        claims=(valid, valid_conflict, *poison_claims),
        answer_text=raw_draft,
    )
    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda _: proposal
    ).answer(request)

    assert tuple(claim.claim_id for claim in result.claims) == (
        valid.claim_id,
        valid_conflict.claim_id,
    )
    assert all(
        claim.subject_id and claim.predicate and claim.value and claim.evidence_ids
        for claim in result.claims
    )
    assert tuple(mapping.claim_id for mapping in result.claim_evidence_map) == (
        valid.claim_id,
        valid_conflict.claim_id,
    )
    assert {citation.evidence_id for citation in result.citations} == {
        exact.evidence_id,
        role_local.evidence_id,
        role_web.evidence_id,
    }
    conflict_bindings = tuple(
        item.claim_binding
        for item in (role_local, role_web)
        if item.claim_binding is not None
    )
    assert {binding.subject_id for binding in conflict_bindings} == {company_id}
    assert {binding.predicate for binding in conflict_bindings} == {"current_role"}
    assert {binding.value for binding in conflict_bindings} == {
        "chief_scientist",
        "external_advisor",
    }
    assert {binding.status for binding in conflict_bindings} == {
        "accepted",
        "reported",
    }
    serialized = result.model_dump_json()
    assert raw_draft not in serialized
    for claim in poison_claims:
        assert claim.text not in serialized


@pytest.mark.parametrize(
    ("outcome", "expected_code", "expected_sentence"),
    (
        (
            "missing",
            "material_evidence_missing",
            "目前公开信息较为有限，暂未能确认问题中的 2026 年当前营收。",
        ),
        (
            "conflicting",
            "material_evidence_conflicting",
            "目前公开信息对问题中的 2026 年当前营收存在不一致说法，暂未能确认。",
        ),
    ),
)
def test_material_sufficiency_gaps_are_typed_server_owned_and_deduplicated(
    outcome: str,
    expected_code: str,
    expected_sentence: str,
) -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j-robotics"
    profile = _item(
        read_module,
        evidence_id=f"evidence:s9j:profile:{outcome}",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
    )
    hostile_text = (
        "HOSTILE_PART_TEXT: Robotics Co had CNY 999 billion revenue; "
        "canonical:company:invented"
    )
    part = read_module.MaterialQuestionPart(
        part_id=f"material-part:s9j:current-revenue:{outcome}",
        text=hostile_text,
        subject_id=company_id,
        predicate="current_revenue",
        requested_value="2026",
    )
    rationale = f"Recorded S9J {outcome} rationale."
    report = read_module.SufficiencyReport(
        decision_input_sha256="a" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=part.part_id,
                outcome=outcome,
                evidence_ids=(() if outcome == "missing" else (profile.evidence_id,)),
                rationale=rationale,
                uncertainty="high",
                confidence=0.0,
                answer_scoped=False,
                canonical=True,
            ),
        ),
        complete=False,
    )
    request = _turn(
        answer_module,
        session_id=f"session:s9j:gap:{outcome}",
        turn_id=f"turn:s9j:gap:{outcome}",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co 并核实 2026 年当前营收",
            items=(profile,),
            material_parts=(part,),
            sufficiency_report=report,
        ),
    )
    semantic_claim = _claim(
        answer_module,
        claim_id=f"claim:s9j:profile:{outcome}",
        text="Robotics Co 由已接受的本地公司档案证据支持。",
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )
    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda value: _answer_proposal(
            answer_module, value, claim=semantic_claim
        )
    ).answer(request)

    matching = tuple(
        limitation
        for limitation in result.limitations
        if limitation.material_part_id == part.part_id
    )
    assert len(matching) == 1
    assert matching[0].model_dump(mode="json") == {
        "code": expected_code,
        "reason": rationale,
        "material": True,
        "stage": "sufficiency",
        "failure_kind": None,
        "material_part_id": part.part_id,
        "handle_id": None,
        "requested_path_id": None,
    }
    assert expected_sentence in result.answer_text
    assert result.answer_text.count(expected_sentence) == 1
    assert "HOSTILE_PART_TEXT" not in result.answer_text
    assert "CNY 999 billion" not in result.answer_text
    assert "canonical:company:invented" not in result.answer_text

    def timeout_selector(_: Any) -> Any:
        raise TimeoutError

    degraded = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=timeout_selector
    ).answer(request)
    degraded_matching = tuple(
        limitation
        for limitation in degraded.limitations
        if limitation.material_part_id == part.part_id
    )
    assert tuple(limitation.code for limitation in degraded_matching) == (
        expected_code,
    )
    assert expected_sentence in degraded.answer_text
    assert degraded.answer_text.count(expected_sentence) == 1
    assert hostile_text not in degraded.answer_text

    product_part = read_module.MaterialQuestionPart(
        part_id=f"material-part:s9j:product-capability:{outcome}",
        text="HOSTILE_PRODUCT_PART_TEXT",
        subject_id=company_id,
        predicate="capability",
        requested_value="autonomous_elevator_operation",
        answer_scoped=True,
    )
    product_report = read_module.SufficiencyReport(
        decision_input_sha256="b" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=product_part.part_id,
                outcome="missing",
                evidence_ids=(),
                rationale="No direct Product-bound status evidence is retained.",
                uncertainty="high",
                confidence=0.0,
                answer_scoped=True,
                canonical=False,
            ),
        ),
        complete=False,
    )
    product_request = _turn(
        answer_module,
        session_id=f"session:s9j:product-precedence:{outcome}",
        turn_id=f"turn:s9j:product-precedence:{outcome}",
        evidence_set=_evidence_set(
            read_module,
            query="Can the named Product operate an elevator?",
            items=(profile,),
            material_parts=(product_part,),
            sufficiency_report=product_report,
        ),
    )
    product_result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda value: _answer_proposal(
            answer_module, value, claim=semantic_claim
        )
    ).answer(product_request)
    product_limitations = tuple(
        limitation
        for limitation in product_result.limitations
        if limitation.material_part_id == product_part.part_id
    )
    assert tuple(limitation.code for limitation in product_limitations) == (
        "direct_product_capability_evidence_missing",
    )
    assert "HOSTILE_PRODUCT_PART_TEXT" not in product_result.answer_text


@pytest.mark.parametrize(
    ("predicate", "binding_value"),
    (
        ("canonical_projection", hashlib.sha256(b"lookup-projection").hexdigest()),
        ("semantic_recall", hashlib.sha256(b"semantic-projection").hexdigest()),
        ("company_has_patent", "canonical:patent:s9j-alpha"),
        ("professor_attributed_to_paper", "reference:paper:s9j-alpha"),
    ),
    ids=(
        "canonical-projection-digest",
        "semantic-recall-digest",
        "canonical-relationship-value",
        "reference-relationship-value",
    ),
)
def test_opaque_binding_values_never_become_public_claim_text(
    predicate: str,
    binding_value: str,
) -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j-opaque"
    item = _item(
        read_module,
        evidence_id=f"evidence:s9j:opaque:{predicate}",
        object_id=company_id,
        subject_id=company_id,
        predicate=predicate,
        value=binding_value,
        status="accepted",
        snippet="Trusted semantic evidence for Robotics Co.",
    )
    request = _turn(
        answer_module,
        session_id=f"session:s9j:opaque:{predicate}",
        turn_id=f"turn:s9j:opaque:{predicate}",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co",
            items=(item,),
        ),
    )
    safe_claim = _claim(
        answer_module,
        claim_id=f"claim:s9j:safe:{predicate}",
        text="Robotics Co 由已接受的本地证据支持。",
        subject_id=company_id,
        predicate=predicate,
        value=binding_value,
        evidence_ids=(item.evidence_id,),
        status="accepted",
    )
    unsafe_claim = _claim(
        answer_module,
        claim_id=f"claim:s9j:unsafe:{predicate}",
        text=f"Internal binding value {binding_value}.",
        subject_id=company_id,
        predicate=predicate,
        value=binding_value,
        evidence_ids=(item.evidence_id,),
        status="accepted",
    )
    proposal = _constructed_answer_proposal(
        answer_module,
        request,
        claims=(unsafe_claim, safe_claim),
    )
    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda _: proposal
    ).answer(request)

    assert tuple(claim.claim_id for claim in result.claims) == (safe_claim.claim_id,)
    assert result.claims[0].value == binding_value
    assert result.claim_evidence_map[0].value == binding_value
    assert binding_value not in result.claims[0].text
    assert binding_value not in result.answer_text


@pytest.mark.parametrize(
    ("leak_kind", "leaked_value"),
    (
        ("evidence_id", "evidence:review:selector-leak"),
        ("claim_id", "claim:review:selector-leak"),
        ("continuation_id", "continuation:review:selector-leak"),
        ("continuation_reason", "evidence_gap"),
        ("continuation_operation", "targeted_evidence_search"),
        ("chinese_adjacent_evidence_gap", "evidence_gap"),
        ("chinese_adjacent_broad_scope", "broad_scope"),
        ("chinese_adjacent_ambiguity", "ambiguity"),
        ("chinese_adjacent_narrow_scope", "narrow_scope"),
    ),
    ids=(
        "evidence-id",
        "claim-id",
        "continuation-id",
        "raw-continuation-reason",
        "raw-continuation-operation",
        "chinese-adjacent-evidence-gap",
        "chinese-adjacent-broad-scope",
        "chinese-adjacent-ambiguity",
        "chinese-adjacent-narrow-scope",
    ),
)
def test_selector_claim_text_cannot_copy_known_structured_values(
    leak_kind: str,
    leaked_value: str,
) -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j-selector-leak"
    profile = _item(
        read_module,
        evidence_id="evidence:review:selector-leak",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
    )
    candidate_reason, candidate_operation, target_kind = {
        "broad_scope": ("broad_scope", "narrow_scope", "current_result_set"),
        "ambiguity": ("ambiguity", "switch_candidate", "current_handle"),
        "narrow_scope": ("broad_scope", "narrow_scope", "current_result_set"),
    }.get(
        leaked_value,
        ("evidence_gap", "targeted_evidence_search", "current_handle"),
    )
    candidate = read_module.ContinuationCandidate(
        candidate_id="continuation:review:selector-leak",
        reason=candidate_reason,
        label="Search for targeted evidence",
        operation=candidate_operation,
        target_kind=target_kind,
        target_handle_ids=(company_id,) if target_kind == "current_handle" else (),
        constraint_pairs=(),
        relation_type=None,
        coverage_state=None,
        evidence_ids=(profile.evidence_id,),
        available=True,
    )
    request = _turn(
        answer_module,
        session_id=f"session:s9j:selector-leak:{leak_kind}",
        turn_id=f"turn:s9j:selector-leak:{leak_kind}",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co",
            items=(profile,),
            continuation_candidates=(candidate,),
        ),
    )
    unsafe_claim = _claim(
        answer_module,
        claim_id=(
            leaked_value
            if leak_kind == "claim_id"
            else f"claim:s9j:selector-leak:{leak_kind}"
        ),
        text=(
            f"Robotics Co 的内部状态为{leaked_value}。"
            if leak_kind.startswith("chinese_adjacent_")
            else f"Robotics Co is supported. Internal token: {leaked_value}."
        ),
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )
    safe_claim = _claim(
        answer_module,
        claim_id=f"claim:s9j:selector-safe:{leak_kind}",
        text="Robotics Co 由已接受的本地公司档案证据支持。",
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )
    proposal = _constructed_answer_proposal(
        answer_module,
        request,
        claims=(unsafe_claim, safe_claim),
    )
    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda _: proposal
    ).answer(request)

    assert tuple(claim.claim_id for claim in result.claims) == (safe_claim.claim_id,)
    assert result.claims[0].evidence_ids == (profile.evidence_id,)
    assert result.claim_evidence_map[0].evidence_ids == (profile.evidence_id,)
    assert result.citations[0].evidence_id == profile.evidence_id
    assert leaked_value not in result.answer_text


def test_opaque_only_rejection_preserves_material_gap() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j-opaque-only"
    digest = hashlib.sha256(b"s9j-opaque-only-projection").hexdigest()
    profile = _item(
        read_module,
        evidence_id="evidence:s9j:opaque-only-profile",
        object_id=company_id,
        subject_id=company_id,
        predicate="canonical_projection",
        value=digest,
        status="accepted",
        snippet="Trusted semantic profile for Robotics Co.",
    )
    part = read_module.MaterialQuestionPart(
        part_id="material-part:s9j:opaque-only-current-revenue",
        text="HOSTILE_OPAQUE_ONLY_PART_TEXT",
        subject_id=company_id,
        predicate="current_revenue",
        requested_value="2026",
    )
    rationale = "No retained evidence supports the requested current revenue."
    report = read_module.SufficiencyReport(
        decision_input_sha256="d" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=part.part_id,
                outcome="missing",
                evidence_ids=(),
                rationale=rationale,
                uncertainty="high",
                confidence=0.0,
                answer_scoped=False,
                canonical=True,
            ),
        ),
        complete=False,
    )
    request = _turn(
        answer_module,
        session_id="session:s9j:opaque-only-gap",
        turn_id="turn:s9j:opaque-only-gap",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co 并核实 2026 年当前营收",
            items=(profile,),
            material_parts=(part,),
            sufficiency_report=report,
        ),
    )
    opaque_claim = _claim(
        answer_module,
        claim_id="claim:s9j:opaque-only-profile",
        text=f"Internal canonical projection {digest}.",
        subject_id=company_id,
        predicate="canonical_projection",
        value=digest,
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )
    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda value: _answer_proposal(
            answer_module, value, claim=opaque_claim
        )
    ).answer(request)

    assert result.claims == ()
    assert result.claim_evidence_map == ()
    assert result.citations == ()
    assert result.render_mode == "deterministic_fallback"
    rejection = next(
        limitation
        for limitation in result.limitations
        if limitation.code == "answer_selection_rejected"
    )
    assert rejection.model_dump(mode="json") == {
        "code": "answer_selection_rejected",
        "reason": "unsupported_material_claim",
        "material": True,
        "stage": "answer_selection",
        "failure_kind": "unsupported_material_claim",
        "material_part_id": None,
        "handle_id": None,
        "requested_path_id": None,
    }
    gaps = tuple(
        limitation
        for limitation in result.limitations
        if limitation.material_part_id == part.part_id
    )
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.model_dump(mode="json") == {
        "code": "material_evidence_missing",
        "reason": rationale,
        "material": True,
        "stage": "sufficiency",
        "failure_kind": None,
        "material_part_id": part.part_id,
        "handle_id": None,
        "requested_path_id": None,
    }
    gap_sentence = "目前公开信息较为有限，暂未能确认问题中的 2026 年当前营收。"
    assert result.answer_text.count(gap_sentence) == 1
    assert digest not in result.answer_text
    assert profile.evidence_id not in result.answer_text
    assert "HOSTILE_OPAQUE_ONLY_PART_TEXT" not in result.answer_text


def test_prose_renderer_cannot_reintroduce_audit_values_or_omit_material_gap() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j-prose"
    digest = hashlib.sha256(b"s9j-prose-projection").hexdigest()
    profile = _item(
        read_module,
        evidence_id="evidence:s9j:prose-profile",
        object_id=company_id,
        subject_id=company_id,
        predicate="canonical_projection",
        value=digest,
        status="accepted",
        snippet="Trusted semantic profile for Robotics Co.",
    )
    part = read_module.MaterialQuestionPart(
        part_id="material-part:s9j:prose-current-revenue",
        text="HOSTILE_PROSE_PART_TEXT",
        subject_id=company_id,
        predicate="current_revenue",
        requested_value="2026",
    )
    report = read_module.SufficiencyReport(
        decision_input_sha256="c" * 64,
        parts=(
            read_module.SufficiencyPartDecision(
                part_id=part.part_id,
                outcome="missing",
                evidence_ids=(),
                rationale="No retained evidence supports the requested value.",
                uncertainty="high",
                confidence=0.0,
                answer_scoped=False,
                canonical=True,
            ),
        ),
        complete=False,
    )
    request = _turn(
        answer_module,
        session_id="session:s9j:prose",
        turn_id="turn:s9j:prose",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co 并核实 2026 年当前营收",
            items=(profile,),
            material_parts=(part,),
            sufficiency_report=report,
        ),
    )
    semantic_claim = _claim(
        answer_module,
        claim_id="claim:s9j:prose-profile",
        text="Robotics Co 由已接受的本地公司档案证据支持。",
        subject_id=company_id,
        predicate="canonical_projection",
        value=digest,
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )

    def selector(value: Any) -> Any:
        return _answer_proposal(answer_module, value, claim=semantic_claim)

    hostile = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=lambda _: (
            f"Hostile renderer exposed {digest} and {profile.evidence_id}."
        ),
    ).answer(request)
    gap_sentence = "目前公开信息较为有限，暂未能确认问题中的 2026 年当前营收。"
    assert digest not in hostile.answer_text
    assert profile.evidence_id not in hostile.answer_text
    # The hostile renderer's text is fully discarded, while the bounded
    # server-owned fallback keeps the already validated claim and material gap.
    assert hostile.answer_text.startswith(f"- {semantic_claim.text}")
    assert gap_sentence in hostile.answer_text
    assert "回答生成暂时不可用" not in hostile.answer_text
    assert hostile.render_mode == "deterministic_fallback"
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.material is True
        and limitation.stage == "prose"
        and limitation.failure_kind == "unsafe_output"
        for limitation in hostile.limitations
    )

    safe_prose = "Robotics Co 的已接受本地档案提供了公司简介证据。"
    safe = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=lambda _: safe_prose,
    ).answer(request)
    # The prose path owns insufficiency wording: the renderer's text is
    # returned verbatim and the deterministic gap sentence stays in the
    # deterministic/fallback modes only.
    assert safe.answer_text == safe_prose
    assert gap_sentence not in safe.answer_text
    assert safe.render_mode == "prose_renderer"


def test_prose_audit_value_matching_uses_token_boundaries_for_short_ids() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j-short-evidence-id"
    profile = _item(
        read_module,
        evidence_id="e",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
    )
    request = _turn(
        answer_module,
        session_id="session:s9j:short-evidence-id",
        turn_id="turn:s9j:short-evidence-id",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co",
            items=(profile,),
        ),
    )
    semantic_claim = _claim(
        answer_module,
        claim_id="claim:s9j:short-evidence-id",
        text="Evidence supports Robotics Co.",
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )

    def selector(value: Any) -> Any:
        return _answer_proposal(answer_module, value, claim=semantic_claim)

    safe_prose = semantic_claim.text
    safe = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=lambda _: safe_prose,
    ).answer(request)
    assert safe.answer_text == safe_prose
    assert safe.render_mode == "prose_renderer"
    assert all(
        limitation.code != "prose_synthesis_failed" for limitation in safe.limitations
    )

    exposed = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=lambda _: f"{safe_prose} Audit token: {profile.evidence_id}.",
    ).answer(request)
    assert exposed.render_mode == "deterministic_fallback"
    # The unsafe renderer text is discarded; the fallback comes only from the
    # already validated server-owned claim text.
    assert exposed.answer_text == f"- {semantic_claim.text}"
    assert "Audit token:" not in exposed.answer_text
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.failure_kind == "unsafe_output"
        for limitation in exposed.limitations
    )


def test_answer_selector_trace_binds_model_prompt_schema_run_and_visible_rejection() -> (
    None
):
    module = _answer_module()
    read_module = _read_module()
    item = _item(
        read_module,
        evidence_id="evidence:s9i:selector-name",
        object_id="company:s9i-selector",
        subject_id="company:s9i-selector",
        predicate="preferred_name",
        value="Selector Robotics",
        status="accepted",
        snippet="The accepted name is Selector Robotics.",
    )
    handle = _canonical_handle(
        read_module,
        canonical_id="company:s9i-selector",
        evidence_id=item.evidence_id,
    )
    request = _turn(
        module,
        session_id="session:s9i:answer-selector",
        turn_id="turn:s9i:answer-selector",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Selector Robotics",
            items=(item,),
            handles=(handle,),
        ),
    )
    valid_claim = _claim(
        module,
        claim_id="claim:s9i:selector-name",
        text="Selector Robotics is the accepted Company name.",
        subject_id="company:s9i-selector",
        predicate="preferred_name",
        value="Selector Robotics",
        status="accepted",
        evidence_ids=(item.evidence_id,),
    )
    accepted_proposal = _answer_proposal(
        module,
        request,
        claim=valid_claim,
    )
    accepted = module.create_ephemeral_knowledge_answer(
        answer_selector=lambda _: accepted_proposal
    ).answer(request)
    assert len(accepted.selector_traces) == 1
    accepted_trace = accepted.selector_traces[0]
    assert accepted_trace.stage == "answer_selection"
    assert accepted_trace.schema_version == accepted_proposal.schema_version
    assert accepted_trace.selection_input_sha256 == request.content_sha256
    assert accepted_trace.outcome == "accepted"
    assert accepted_trace.decision_id == accepted_proposal.decision_id
    assert accepted_trace.model_id == accepted_proposal.model_id
    assert accepted_trace.prompt_version == accepted_proposal.prompt_version
    assert accepted_trace.decision_run_id == accepted_proposal.decision_run_id
    assert accepted_trace.failure_kind is None
    assert accepted_proposal.answer_text not in accepted.model_dump_json()

    invalid_shape = module.AnswerSelectionProposal.model_construct(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id="answer-selection:s9i:invalid-shape",
        model_id="",
        prompt_version="POISON_UNTRUSTED_PROMPT",
        decision_run_id="POISON_UNTRUSTED_RUN",
        answer_text="POISON_UNTRUSTED_DRAFT",
        claims=(valid_claim,),
        displayed_handle_ids=(handle.canonical_id,),
        displayed_entity_ids=(),
        coverage_claim=None,
        continuation_candidate_ids=(),
    )
    hostile = (
        (
            _answer_proposal(
                module,
                request,
                claim=valid_claim,
                selection_input_sha256="f" * 64,
            ),
            "input_binding_mismatch",
        ),
        (
            _answer_proposal(
                module,
                request,
                claim=valid_claim,
                schema_version="answer-selection-v999",
            ),
            "schema_mismatch",
        ),
        (invalid_shape, "invalid_output"),
        (
            accepted_proposal.model_copy(update={"decision_id": ""}),
            "invalid_output",
        ),
    )
    for hostile_proposal, failure_kind in hostile:
        result = module.create_ephemeral_knowledge_answer(
            answer_selector=lambda _, value=hostile_proposal: value
        ).answer(request)
        assert result.claims == ()
        assert result.claim_evidence_map == ()
        assert result.citations == ()
        assert result.context_receipt is None
        assert len(result.selector_traces) == 1
        trace = result.selector_traces[0]
        assert trace.stage == "answer_selection"
        assert trace.outcome == "degraded"
        assert trace.failure_kind == failure_kind
        assert trace.decision_id is None
        assert trace.model_id is None
        assert trace.prompt_version is None
        assert trace.decision_run_id is None
        assert any(
            limitation.code == "answer_selection_rejected"
            and limitation.failure_kind == failure_kind
            for limitation in result.limitations
        )
        assert "POISON_UNTRUSTED" not in result.model_dump_json()

    def timed_out_selector(_: Any) -> Any:
        raise TimeoutError("recorded answer selector timeout")

    timed_out = module.create_ephemeral_knowledge_answer(
        answer_selector=timed_out_selector
    ).answer(request)
    assert timed_out.claims == ()
    assert timed_out.answer_text == (
        "关于该主体的公开信息目前较为有限，暂未能确认您问的具体内容。"
    )
    assert timed_out.render_mode == "deterministic_fallback"
    assert len(timed_out.selector_traces) == 1
    assert timed_out.selector_traces[0].outcome == "degraded"
    assert timed_out.selector_traces[0].failure_kind == "timeout"
    assert any(
        limitation.code == "answer_selection_rejected"
        and limitation.stage == "answer_selection"
        and limitation.failure_kind == "timeout"
        for limitation in timed_out.limitations
    )


def test_assessment_replays_evidence_relevance_and_degrades_visibly() -> None:
    module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9i-assessment"
    name_item = _item(
        read_module,
        evidence_id="evidence:s9i:assessment-name",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Assessment Robotics",
        status="accepted",
        snippet="The accepted name is Assessment Robotics.",
    )
    deployment = _item(
        read_module,
        evidence_id="evidence:s9i:deployment",
        object_id=company_id,
        subject_id=company_id,
        predicate="deployment_stage",
        value="production",
        status="accepted",
        snippet="One retained source records a production deployment.",
    )
    pilot = _item(
        read_module,
        evidence_id="evidence:s9i:pilot",
        object_id=company_id,
        subject_id=company_id,
        predicate="deployment_stage",
        value="pilot",
        status="reported",
        snippet="Another retained source records only a pilot.",
    )
    unrelated = _item(
        read_module,
        evidence_id="evidence:s9i:unrelated-profile",
        object_id=company_id,
        subject_id=company_id,
        predicate="profile_summary",
        value="unrelated profile",
        status="accepted",
        snippet="This profile does not establish production scale.",
    )
    conflict = read_module.EvidenceConflict(
        conflict_id="conflict:s9i:deployment-stage",
        subject_id=company_id,
        predicate="deployment_stage",
        evidence_ids=(deployment.evidence_id, pilot.evidence_id),
        material=True,
        fusion_decision_id=None,
    )
    query = "请按部署阶段和量产规模评估这家公司"
    evidence = _evidence_set(
        read_module,
        query=query,
        items=(name_item, deployment, pilot, unrelated),
        conflicts=(conflict,),
    )
    base_claim = _claim(
        module,
        claim_id="claim:s9i:assessment-name",
        text="Assessment Robotics is the accepted Company name.",
        subject_id=company_id,
        predicate="preferred_name",
        value="Assessment Robotics",
        status="accepted",
        evidence_ids=(name_item.evidence_id,),
    )

    def answer_selector(value: Any) -> Any:
        return _constructed_answer_proposal(
            module,
            value,
            claims=(base_claim,),
        )

    free_request = _turn(
        module,
        session_id="session:s9i:assessment",
        turn_id="turn:s9i:assessment:free",
        evidence_set=evidence,
        assessment_intent=module.AssessmentIntent(kind="technical_strength"),
    )
    explicit_request = _turn(
        module,
        session_id="session:s9i:assessment",
        turn_id="turn:s9i:assessment:explicit",
        evidence_set=evidence,
        assessment_intent=module.AssessmentIntent(
            kind="maturity",
            user_criteria=("部署阶段", "量产规模"),
        ),
    )

    def assessment_selector(value: Any) -> Any:
        if value.turn_id == free_request.turn_id:
            dimension = module.AssessmentDimensionProposal(
                name="本轮自选资料完整性",
                rationale="The dimension is selected only for this turn.",
                evidence_ids=(unrelated.evidence_id,),
                evidence_bindings=(_assessment_binding(module, unrelated),),
                outcome="supported",
                conclusion="The retained profile supports a bounded completeness finding.",
                uncertainty="medium",
            )
            return _assessment_proposal(
                module,
                value,
                dimensions=(dimension,),
            )
        conflicting = module.AssessmentDimensionProposal(
            name="部署阶段",
            rationale="Retained sources disagree on deployment stage.",
            evidence_ids=conflict.evidence_ids,
            evidence_bindings=(
                _assessment_binding(module, deployment),
                _assessment_binding(module, pilot),
            ),
            outcome="conflicting_evidence",
            conclusion="The stage conclusion is conditional because sources conflict.",
            uncertainty="high",
        )
        wrong_binding = module.AssessmentEvidenceBinding(
            evidence_id=unrelated.evidence_id,
            subject_id=company_id,
            predicate="production_scale",
            value="mass_production",
            status="accepted",
        )
        missing = module.AssessmentDimensionProposal(
            name="量产规模",
            rationale="A profile is not production-scale evidence.",
            evidence_ids=(unrelated.evidence_id,),
            evidence_bindings=(wrong_binding,),
            outcome="supported",
            conclusion="POISON_UNRELATED_SCALE_CONCLUSION",
            uncertainty="low",
        )
        unprescribed = module.AssessmentDimensionProposal(
            name="模型默认维度",
            rationale="This dimension was not requested.",
            evidence_ids=(deployment.evidence_id,),
            evidence_bindings=(_assessment_binding(module, deployment),),
            outcome="supported",
            conclusion="POISON_UNPRESCRIBED_CONCLUSION",
            uncertainty="low",
        )
        return _assessment_proposal(
            module,
            value,
            dimensions=(conflicting, missing, unprescribed),
        )

    answer = module.create_ephemeral_knowledge_answer(
        answer_selector=answer_selector,
        assessment_selector=assessment_selector,
    )
    free_result = answer.answer(free_request)
    assert free_result.assessment_frame is not None
    assert tuple(
        dimension.name for dimension in free_result.assessment_frame.dimensions
    ) == ("本轮自选资料完整性",)
    assert len(free_result.assessment_frame.dimensions) <= 3
    explicit_result = answer.answer(explicit_request)
    assert explicit_result.assessment_frame is not None
    dimensions = explicit_result.assessment_frame.dimensions
    assert tuple(dimension.name for dimension in dimensions) == (
        "部署阶段",
        "量产规模",
    )
    assert dimensions[0].outcome == "conflicting_evidence"
    assert dimensions[0].evidence_ids == conflict.evidence_ids
    assert dimensions[1].outcome == "insufficient_evidence"
    assert dimensions[1].evidence_ids == ()
    assert dimensions[1].conclusion is None
    assert "POISON_" not in explicit_result.model_dump_json()
    assert tuple(trace.stage for trace in explicit_result.selector_traces) == (
        "answer_selection",
        "assessment_selection",
    )
    assert explicit_result.selector_traces[0].outcome == "accepted"
    assert explicit_result.selector_traces[1].outcome == "degraded"
    assert any(
        limitation.code == "assessment_dimension_rejected"
        for limitation in explicit_result.limitations
    )

    valid_dimension = module.AssessmentDimensionProposal(
        name="部署证据",
        rationale="Bound to current-turn deployment evidence.",
        evidence_ids=(deployment.evidence_id,),
        evidence_bindings=(_assessment_binding(module, deployment),),
        outcome="supported",
        conclusion="A bounded deployment is evidenced.",
        uncertainty="medium",
    )
    invalid_shape = module.AssessmentSelectionProposal.model_construct(
        selection_input_sha256=free_request.content_sha256,
        schema_version="assessment-selection-v1",
        decision_id="assessment-selection:s9i:invalid-shape",
        model_id="",
        prompt_version="POISON_ASSESSMENT_PROMPT",
        decision_run_id="POISON_ASSESSMENT_RUN",
        dimensions=(valid_dimension,),
        conditional_synthesis="POISON_ASSESSMENT_SYNTHESIS",
    )
    hostile = (
        _assessment_proposal(
            module,
            free_request,
            dimensions=(valid_dimension,),
            selection_input_sha256="e" * 64,
        ),
        _assessment_proposal(
            module,
            free_request,
            dimensions=(valid_dimension,),
            schema_version="assessment-selection-v999",
        ),
        invalid_shape,
        _assessment_proposal(
            module,
            free_request,
            dimensions=(valid_dimension,),
        ).model_copy(update={"decision_id": ""}),
        _assessment_proposal(
            module,
            free_request,
            dimensions=(
                valid_dimension.model_copy(update={"name": "", "rationale": ""}),
            ),
        ),
    )
    for hostile_proposal in hostile:
        degraded = module.create_ephemeral_knowledge_answer(
            answer_selector=answer_selector,
            assessment_selector=lambda _, value=hostile_proposal: value,
        ).answer(free_request)
        assert tuple(claim.claim_id for claim in degraded.claims) == (
            base_claim.claim_id,
        )
        assert degraded.assessment_frame is None
        assert degraded.selector_traces[-1].stage == "assessment_selection"
        assert degraded.selector_traces[-1].outcome == "degraded"
        assert any(
            limitation.code == "assessment_selection_rejected"
            for limitation in degraded.limitations
        )
        assert "POISON_ASSESSMENT" not in degraded.model_dump_json()

    def timed_out_assessment(_: Any) -> Any:
        raise TimeoutError("recorded assessment selector timeout")

    timed_out = module.create_ephemeral_knowledge_answer(
        answer_selector=answer_selector,
        assessment_selector=timed_out_assessment,
    ).answer(free_request)
    assert tuple(claim.claim_id for claim in timed_out.claims) == (base_claim.claim_id,)
    assert timed_out.assessment_frame is None
    assert timed_out.selector_traces[-1].stage == "assessment_selection"
    assert timed_out.selector_traces[-1].outcome == "degraded"
    assert timed_out.selector_traces[-1].failure_kind == "timeout"
    assert any(
        limitation.code == "assessment_selection_rejected"
        and limitation.failure_kind == "timeout"
        for limitation in timed_out.limitations
    )


def test_typed_session_directive_owns_referents_topic_switch_and_release_boundary() -> (
    None
):
    module = _answer_module()
    read_module = _read_module()
    session_id = "session:s9i:typed-directive"

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:s9i:session:member":
            first_item, second_item = request.evidence_set.items
            first_binding = first_item.claim_binding
            second_binding = second_item.claim_binding
            assert first_binding is not None
            assert second_binding is not None
            correct = module.MaterialClaimProposal(
                claim_id="claim:s9i:member-correct",
                text="The selected second member is Session Company 2.",
                subject_id=second_binding.subject_id,
                predicate=second_binding.predicate,
                value=second_binding.value,
                evidence_ids=(second_item.evidence_id,),
                subject_handle_ids=(),
            )
            wrong_empty = module.MaterialClaimProposal(
                claim_id="claim:s9i:member-wrong-empty",
                text="POISON_WRONG_MEMBER_EMPTY_HANDLES",
                subject_id=first_binding.subject_id,
                predicate=first_binding.predicate,
                value=first_binding.value,
                evidence_ids=(first_item.evidence_id,),
                subject_handle_ids=(),
            )
            forged_allowed = module.MaterialClaimProposal(
                claim_id="claim:s9i:member-forged-allowed",
                text="POISON_WRONG_MEMBER_FORGED_HANDLE",
                subject_id=first_binding.subject_id,
                predicate=first_binding.predicate,
                value=first_binding.value,
                evidence_ids=(first_item.evidence_id,),
                subject_handle_ids=(second_binding.subject_id,),
            )
            return _constructed_answer_proposal(
                module,
                request,
                claims=(correct, wrong_empty, forged_allowed),
            )
        return _constructed_answer_proposal(
            module,
            request,
            displayed_handle_ids=tuple(
                handle.canonical_id if handle.kind == "canonical" else handle.handle_id
                for handle in request.evidence_set.entity_handles
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    seed_items = tuple(
        _item(
            read_module,
            evidence_id=f"evidence:s9i:session:{index}",
            object_id=f"company:s9i:{index}",
            subject_id=f"company:s9i:{index}",
            predicate="preferred_name",
            value=f"Session Company {index}",
            snippet=f"Session Company {index} is retained.",
        )
        for index in (1, 2)
    )
    seed_handles = tuple(
        _canonical_handle(
            read_module,
            canonical_id=f"company:s9i:{index}",
            evidence_id=seed_items[index - 1].evidence_id,
        )
        for index in (1, 2)
    )
    seed = _turn(
        module,
        session_id=session_id,
        turn_id="turn:s9i:session:seed",
        evidence_set=_evidence_set(
            read_module,
            query="opaque seed",
            items=seed_items,
            handles=seed_handles,
        ),
        session_directive=module.SessionDirective(),
    )
    seeded = answer.answer(seed)
    assert seeded.context_receipt is not None
    assert seeded.context_receipt.displayed_result_set is not None
    assert seeded.context_receipt.displayed_result_set.handle_ids == tuple(
        handle.canonical_id for handle in seed_handles
    )

    def empty_turn(
        turn_id: str, query: str, directive: Any, *, release: str = RELEASE_ID
    ) -> Any:
        return _turn(
            module,
            session_id=session_id,
            turn_id=turn_id,
            evidence_set=_evidence_set(
                read_module,
                query=query,
                release_id=release,
            ),
            session_directive=directive,
        )

    member = answer.answer(
        _turn(
            module,
            session_id=session_id,
            turn_id="turn:s9i:session:member",
            evidence_set=_evidence_set(
                read_module,
                query="opaque member request",
                items=seed_items,
            ),
            session_directive=module.SessionDirective(
                referent="displayed_member",
                displayed_ordinal=2,
            ),
        )
    )
    assert member.context_receipt.resolved_referent.handle_ids == (
        seed_handles[1].canonical_id,
    )
    assert tuple(claim.claim_id for claim in member.claims) == (
        "claim:s9i:member-correct",
    )
    assert member.claims[0].subject_handle_ids == (seed_handles[1].canonical_id,)
    assert "POISON_WRONG_MEMBER" not in member.model_dump_json()
    result_set = answer.answer(
        empty_turn(
            "turn:s9i:session:set",
            "opaque set request",
            module.SessionDirective(referent="displayed_result_set"),
        )
    )
    assert result_set.context_receipt.resolved_referent.handle_ids == tuple(
        handle.canonical_id for handle in seed_handles
    )
    active = answer.answer(
        empty_turn(
            "turn:s9i:session:anchor",
            "opaque anchor request",
            module.SessionDirective(referent="active_anchor"),
        )
    )
    assert active.context_receipt.resolved_referent.handle_ids == (
        seed_handles[1].canonical_id,
    )
    wording_trap = answer.answer(
        empty_turn(
            "turn:s9i:session:wording-trap",
            "第二家 这些 它 换个话题",
            module.SessionDirective(),
        )
    )
    assert wording_trap.context_receipt.resolved_referent is None
    assert wording_trap.context_receipt.transition_kind == "turn"
    assert wording_trap.context_receipt.active_anchor.canonical_id == (
        seed_handles[1].canonical_id
    )

    invalid_directives = (
        {"referent": "displayed_member"},
        {"referent": "none", "displayed_ordinal": 1},
        {"referent": "active_anchor", "displayed_ordinal": 1},
        {"referent": "displayed_result_set", "displayed_ordinal": 1},
    )
    for values in invalid_directives:
        with pytest.raises(ValueError):
            module.SessionDirective(**values)

    switched_item = _item(
        read_module,
        evidence_id="evidence:s9i:session:switched",
        object_id="company:s9i:switched",
        subject_id="company:s9i:switched",
        predicate="preferred_name",
        value="Switched Company",
        snippet="Switched Company is retained.",
    )
    switched_handle = _canonical_handle(
        read_module,
        canonical_id="company:s9i:switched",
        evidence_id=switched_item.evidence_id,
    )
    switched = answer.answer(
        _turn(
            module,
            session_id=session_id,
            turn_id="turn:s9i:session:topic-switch",
            evidence_set=_evidence_set(
                read_module,
                query="opaque typed transition",
                items=(switched_item,),
                handles=(switched_handle,),
            ),
            session_directive=module.SessionDirective(transition="topic_switch"),
        )
    )
    assert switched.context_receipt.transition_kind == "topic_switch"
    assert switched.context_receipt.active_anchor.canonical_id == (
        switched_handle.canonical_id
    )
    assert switched.context_receipt.displayed_result_set.handle_ids == (
        switched_handle.canonical_id,
    )

    mismatch = answer.answer(
        empty_turn(
            "turn:s9i:session:release-mismatch",
            "opaque cross-release continuation",
            module.SessionDirective(),
            release="candidate-s9i-r2",
        )
    )
    assert mismatch.claims == ()
    assert mismatch.context_receipt is None
    assert any(
        limitation.code == "session_release_mismatch"
        for limitation in mismatch.limitations
    )

    rebound_item = _item(
        read_module,
        evidence_id="evidence:s9i:session:rebound",
        object_id="company:s9i:rebound",
        subject_id="company:s9i:rebound",
        predicate="preferred_name",
        value="Rebound Company",
        snippet="Rebound Company is retained in release two.",
    )
    rebound_handle = _canonical_handle(
        read_module,
        canonical_id="company:s9i:rebound",
        evidence_id=rebound_item.evidence_id,
    )
    rebound = answer.answer(
        _turn(
            module,
            session_id=session_id,
            turn_id="turn:s9i:session:release-rebind",
            evidence_set=_evidence_set(
                read_module,
                query="opaque release rebind",
                release_id="candidate-s9i-r2",
                items=(rebound_item,),
                handles=(rebound_handle,),
            ),
            session_directive=module.SessionDirective(transition="topic_switch"),
        )
    )
    assert rebound.context_receipt.transition_kind == "topic_switch"
    assert rebound.context_receipt.active_anchor.canonical_id == (
        rebound_handle.canonical_id
    )

    for index, bad_session in enumerate((None, "session:s9i:other"), start=1):
        snapshot = _snapshot(read_module, f"bad-session-{index}")
        web_item = _item(
            read_module,
            evidence_id=f"evidence:s9i:web-session:{index}",
            object_id=f"web-object:s9i:{index}",
            subject_id=f"web-object:s9i:{index}",
            predicate="display_identity",
            value=f"Wrong Session Web Company {index}",
            snippet="A wrong-session Web handle must not enter state.",
            lane="web",
            source_nature="current_web",
            source_locator=f"https://current.example/s9i/wrong-session-{index}",
            web_snapshot=snapshot,
        )
        web_handle = _web_handle(
            read_module,
            token=str(index),
            evidence_id=web_item.evidence_id,
            snapshot_id=snapshot.snapshot_id,
            session_id=bad_session,
        )
        rejected = answer.answer(
            _turn(
                module,
                session_id=session_id,
                turn_id=f"turn:s9i:session:web-reject:{index}",
                evidence_set=_evidence_set(
                    read_module,
                    query=f"opaque Web handle {index}",
                    release_id="candidate-s9i-r2",
                    items=(web_item,),
                    handles=(web_handle,),
                ),
                session_directive=module.SessionDirective(),
            )
        )
        assert rejected.context_receipt is not None
        assert web_handle.handle_id not in {
            handle.handle_id
            for handle in rejected.context_receipt.displayed_result_set.handles
            if handle.kind == "web"
        }
        assert any(
            limitation.code == "web_handle_session_mismatch"
            and limitation.handle_id == web_handle.handle_id
            for limitation in rejected.limitations
        )


def test_safety_guidance_is_server_owned_bounded_and_official_snapshot_grounded() -> (
    None
):
    answer_module = _answer_module()
    read_module = _read_module()
    web_calls: list[Any] = []

    def fail_on_web(value: Any) -> Any:
        web_calls.append(value)
        raise AssertionError("static safety guidance invoked Web")

    static_read = read_module.create_ephemeral_knowledge_read(
        local_search=lambda _: read_module.RetrievalLaneResult(),
        web_search=fail_on_web,
        universal_web_policy=_web_policy(read_module, "universal"),
    )
    static_evidence = static_read.execute(
        _plan(
            read_module,
            query="请给出简短合法安全提醒",
            interaction_mode="safety_guidance",
            web_mode="disabled",
        )
    )
    assert static_evidence.items == ()
    assert all(trace.lane != "web" for trace in static_evidence.traces)
    hostile_selector_calls: list[str] = []

    def hostile_selector(value: Any) -> Any:
        hostile_selector_calls.append(value.turn_id)
        raise AssertionError("safety rendering invoked the answer selector")

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=hostile_selector
    )
    static_request = _turn(
        answer_module,
        session_id="session:s9i:safety",
        turn_id="turn:s9i:safety:static",
        evidence_set=static_evidence,
        safety_guidance=answer_module.SafetyGuidanceDirective(mode="static"),
    )
    static_result = answer.answer(static_request)
    assert static_result.response_mode == "safety_guidance"
    assert static_result.claims == ()
    assert static_result.claim_evidence_map == ()
    assert static_result.citations == ()
    assert static_result.continuation_offer is None
    assert len(static_result.answer_text) <= 300
    assert "官方" in static_result.answer_text
    assert "venue" not in static_result.answer_text.lower()
    assert "district" not in static_result.answer_text.lower()
    assert "evasion" not in static_result.answer_text.lower()
    assert web_calls == []

    official = _item(
        read_module,
        evidence_id="evidence:s9i:official-contact",
        object_id="official-resource:s9i",
        subject_id="official-resource:s9i",
        predicate="official_help_contact",
        value="12345",
        status="current",
        snippet="POISON_OFFICIAL_SNIPPET_WITH_VENUE_ALLEGATION",
        lane="web",
        source_nature="current_web",
        source_authority="official",
        source_locator="https://www.sz.gov.cn/s9i/help",
        web_snapshot=_snapshot(read_module, "official-help"),
    )
    wrong_predicate = _item(
        read_module,
        evidence_id="evidence:s9i:official-wrong-predicate",
        object_id="official-resource:s9i:wrong",
        subject_id="official-resource:s9i:wrong",
        predicate="suspected_venue",
        value="POISON_DISTRICT_VENUE",
        status="current",
        snippet="POISON_EVASION_INSTRUCTION",
        lane="web",
        source_nature="current_web",
        source_authority="official",
        source_locator="https://www.sz.gov.cn/s9i/wrong",
        web_snapshot=_snapshot(read_module, "official-wrong"),
    )
    unverified = _item(
        read_module,
        evidence_id="evidence:s9i:unverified-help",
        object_id="web-object:s9i:unverified",
        subject_id="web-object:s9i:unverified",
        predicate="official_help_contact",
        value="POISON_UNVERIFIED_CONTACT",
        snippet="POISON_UNVERIFIED_SNIPPET",
        lane="web",
        source_nature="current_web",
        source_authority="other",
        source_locator="https://unverified.example/s9i/help",
        web_snapshot=_snapshot(read_module, "unverified-help"),
    )
    poisoned_contact_value = "Venue X; evade enforcement; " + "P" * 400
    poisoned_contact = _item(
        read_module,
        evidence_id="evidence:s9i:official-poison-contact",
        object_id="official-resource:s9i:poison-contact",
        subject_id="official-resource:s9i:poison-contact",
        predicate="official_help_contact",
        value=poisoned_contact_value,
        status="current",
        snippet="POISON_WHITELISTED_PREDICATE_SNIPPET",
        lane="web",
        source_nature="current_web",
        source_authority="official",
        source_locator="https://www.sz.gov.cn/s9i/poison-contact",
        web_snapshot=_snapshot(read_module, "official-poison-contact"),
    )

    def official_web_search(_: Any) -> Any:
        return read_module.RetrievalLaneResult(
            items=(official, wrong_predicate, poisoned_contact, unverified)
        )

    official_read = read_module.create_ephemeral_knowledge_read(
        local_search=lambda _: read_module.RetrievalLaneResult(),
        web_search=official_web_search,
        universal_web_policy=_web_policy(read_module, "universal"),
    )
    official_evidence = official_read.execute(
        _plan(
            read_module,
            query="请查询当前官方求助联系方式",
            interaction_mode="safety_guidance",
            web_mode="official_only",
        )
    )
    assert tuple(item.evidence_id for item in official_evidence.items) == (
        official.evidence_id,
        wrong_predicate.evidence_id,
        poisoned_contact.evidence_id,
    )
    assert all(item.web_snapshot is not None for item in official_evidence.items)
    official_request = _turn(
        answer_module,
        session_id="session:s9i:safety",
        turn_id="turn:s9i:safety:official",
        evidence_set=official_evidence,
        safety_guidance=answer_module.SafetyGuidanceDirective(
            mode="official_snapshot",
            official_evidence_ids=tuple(
                item.evidence_id for item in official_evidence.items
            ),
        ),
    )
    official_result = answer.answer(official_request)
    assert official_result.response_mode == "safety_guidance"
    assert tuple(
        mapping.evidence_ids for mapping in official_result.claim_evidence_map
    ) == ((official.evidence_id,),)
    assert tuple(citation.evidence_id for citation in official_result.citations) == (
        official.evidence_id,
    )
    assert "12345" in official_result.answer_text
    assert len(official_result.answer_text) <= 300
    serialized = official_result.model_dump_json()
    for poison in (
        official.snippet,
        wrong_predicate.snippet,
        "POISON_DISTRICT_VENUE",
        "POISON_UNVERIFIED_CONTACT",
        poisoned_contact_value,
        poisoned_contact.snippet,
        "unverified.example",
    ):
        assert poison not in serialized
    assert official_result.continuation_offer is None
    assert hostile_selector_calls == []

    with pytest.raises(ValueError):
        answer_module.SafetyGuidanceDirective(
            mode="static",
            official_evidence_ids=(official.evidence_id,),
        )
    with pytest.raises(ValueError):
        answer_module.SafetyGuidanceDirective(
            mode="official_snapshot",
            official_evidence_ids=("e1", "e2", "e3", "e4"),
        )


def test_real_knowledge_read_result_flows_to_grounded_answer_and_assessment() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_milvus_before = _file_sha256(original_milvus)
    company_id = "company:s9i-vertical"
    local_item = _item(
        read_module,
        evidence_id="evidence:s9i:vertical-local",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Vertical Robotics",
        status="accepted",
        snippet="The accepted local name is Vertical Robotics.",
    )
    web_item = _item(
        read_module,
        evidence_id="evidence:s9i:vertical-web",
        object_id=company_id,
        subject_id=company_id,
        predicate="deployment_stage",
        value="production",
        status="reported",
        snippet="A bounded current source reports a production deployment.",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/s9i/vertical",
        web_snapshot=_snapshot(read_module, "vertical-web"),
    )
    read_calls: list[str] = []

    def local_search(value: Any) -> Any:
        read_calls.append(value.lane)
        return read_module.RetrievalLaneResult(items=(local_item,))

    def web_search(value: Any) -> Any:
        read_calls.append(value.lane)
        return read_module.RetrievalLaneResult(items=(web_item,))

    query = "核实 Vertical Robotics 的部署证据并做本轮评估"
    plan = _plan(
        read_module,
        query=query,
        interaction_mode="information_retrieval",
        web_mode="universal",
    )
    read = read_module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=web_search,
        universal_web_policy=_web_policy(read_module, "universal"),
    )
    evidence_set = read.execute(plan)
    assert isinstance(evidence_set, read_module.EvidenceSet)
    assert {trace.lane for trace in evidence_set.traces} == {"exact", "web"}
    assert all(trace.status == "succeeded" for trace in evidence_set.traces)
    assert tuple(item.evidence_id for item in evidence_set.items) == (
        local_item.evidence_id,
        web_item.evidence_id,
    )
    assert evidence_set.items[1].web_snapshot == web_item.web_snapshot
    assert sorted(read_calls) == ["exact", "web"]
    request = _turn(
        answer_module,
        session_id="session:s9i:vertical",
        turn_id="turn:s9i:vertical",
        evidence_set=evidence_set,
        assessment_intent=answer_module.AssessmentIntent(kind="technical_strength"),
    )
    claim = _claim(
        answer_module,
        claim_id="claim:s9i:vertical-deployment",
        text="A bounded current source reports a production deployment.",
        subject_id=company_id,
        predicate="deployment_stage",
        value="production",
        status="reported",
        evidence_ids=(web_item.evidence_id,),
    )

    def answer_selector(value: Any) -> Any:
        return _answer_proposal(answer_module, value, claim=claim)

    def assessment_selector(value: Any) -> Any:
        dimension = answer_module.AssessmentDimensionProposal(
            name="本轮自由部署维度",
            rationale="The dimension is bound to the real current-Web evidence.",
            evidence_ids=(web_item.evidence_id,),
            evidence_bindings=(_assessment_binding(answer_module, web_item),),
            outcome="supported",
            conclusion="The retained evidence supports one bounded deployment finding.",
            uncertainty="medium",
        )
        return _assessment_proposal(
            answer_module,
            value,
            dimensions=(dimension,),
        )

    result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=answer_selector,
        assessment_selector=assessment_selector,
    ).answer(request)
    assert tuple(trace.stage for trace in result.selector_traces) == (
        "answer_selection",
        "assessment_selection",
    )
    assert all(
        trace.selection_input_sha256 == request.content_sha256
        for trace in result.selector_traces
    )
    assert result.claims[0].evidence_ids == (web_item.evidence_id,)
    assert result.claim_evidence_map[0].evidence_ids == result.claims[0].evidence_ids
    assert result.citations[0].evidence_id == result.claims[0].evidence_ids[0]
    assert result.assessment_frame is not None
    assert result.assessment_frame.dimensions[0].evidence_ids == (web_item.evidence_id,)
    assert result.citations[0].web_snapshot_id == web_item.web_snapshot.snapshot_id
    assert _file_sha256(original_milvus) == original_milvus_before


def test_prose_renderer_stream_is_duck_typed_only_when_progress_is_set() -> None:
    """A renderer exposing ``stream`` is used only when ``prose_progress`` is
    set; plain callable renderers keep the synchronous path, and the stream
    path preserves the timeout-retry/fallback failure semantics."""
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s9j:stream"
    profile = _item(
        read_module,
        evidence_id="evidence:s9j:stream",
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
    )
    request = _turn(
        answer_module,
        session_id="session:s9j:stream",
        turn_id="turn:s9j:stream",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co",
            items=(profile,),
        ),
    )
    semantic_claim = _claim(
        answer_module,
        claim_id="claim:s9j:stream",
        text="Evidence supports Robotics Co.",
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(profile.evidence_id,),
        status="accepted",
    )

    def selector(value: Any) -> Any:
        return _answer_proposal(answer_module, value, claim=semantic_claim)

    class _StreamingRenderer:
        def __init__(self) -> None:
            self.stream_calls: list[str] = []

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.stream_calls.append("stream")
            for chunk in ("深圳", "科创", "助手"):
                on_chunk(chunk)
            return "深圳科创助手"

    # Without a progress sink the duck-typed stream method is ignored and the
    # synchronous callable path runs (existing injected renderers stay valid).
    sync_renderer = _StreamingRenderer()
    plain = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=sync_renderer,
    ).answer(request)
    assert plain.render_mode == "prose_renderer"
    assert plain.answer_text == "SYNC_RENDERED"
    assert sync_renderer.stream_calls == []

    # With a progress sink the stream method runs: deltas are forwarded in
    # order and the accumulated full text becomes the answer.
    stream_renderer = _StreamingRenderer()
    forwarded: list[str] = []
    stream_module = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=stream_renderer,
    )
    stream_module.prose_progress = _acknowledging_append(forwarded)
    streamed = stream_module.answer(request)
    assert stream_renderer.stream_calls == ["stream"]
    assert forwarded == ["深圳", "科创", "助手"]
    assert streamed.render_mode == "prose_renderer"
    assert streamed.answer_text == "深圳科创助手"

    # The stream path keeps the retry-once semantics: when both attempts time
    # out before publication, it returns the bounded grounded fallback.
    class _TimingOutStreamRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            raise TimeoutError("test-owned stream timeout")

    failing_renderer = _TimingOutStreamRenderer()
    failed_module = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=failing_renderer,
    )
    failed_module.prose_progress = lambda _text: None
    degraded = failed_module.answer(request)
    assert failing_renderer.calls == 2
    assert degraded.render_mode == "deterministic_fallback"
    assert degraded.answer_text == f"- {semantic_claim.text}"
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.failure_kind == "timeout"
        for limitation in degraded.limitations
    )


def test_prose_stream_retries_once_before_any_output() -> None:
    answer_module = _answer_module()
    request = _turn(
        answer_module,
        session_id="session:s12g:retry-before-output",
        turn_id="turn:s12g:retry-before-output",
        evidence_set=_evidence_set(_read_module(), query="介绍深圳科创"),
    )

    class _RetryingRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("failed before output")
            on_chunk("第二次尝试")
            return "第二次尝试"

    renderer = _RetryingRenderer()
    forwarded: list[str] = []
    stream_module = answer_module.create_ephemeral_knowledge_answer(
        prose_renderer=renderer,
    )
    stream_module.prose_progress = _acknowledging_append(forwarded)

    result = stream_module.answer(request)

    assert renderer.calls == 2
    assert forwarded == ["第二次尝试"]
    assert result.render_mode == "prose_renderer"
    assert result.answer_text == "第二次尝试"


def test_unacknowledged_stream_mismatch_rolls_back_session() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    session_id = "session:s12g:unacknowledged-stream-mismatch"
    failed_handle = _canonical_handle(
        read_module,
        canonical_id="company:s12g:unacknowledged-stream-mismatch",
        evidence_id="evidence:s12g:unacknowledged-stream-mismatch",
    )
    request = _turn(
        answer_module,
        session_id=session_id,
        turn_id="turn:s12g:unacknowledged-stream-mismatch",
        evidence_set=_evidence_set(
            read_module,
            query="介绍失败后不应保留的企业",
            handles=(failed_handle,),
        ),
    )
    proposal = _constructed_answer_proposal(
        answer_module,
        request,
        displayed_handle_ids=(failed_handle.canonical_id,),
    )

    class _MismatchedRenderer:
        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            on_chunk("x")
            return "y"

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda _: proposal,
        prose_renderer=_MismatchedRenderer(),
    )
    answer.prose_progress = lambda _text: False
    answer._sessions[session_id] = answer_module._SessionState(release_id=RELEASE_ID)

    with pytest.raises(ValueError, match="prose stream differs from its final answer"):
        answer.answer(request)

    restored = answer._sessions[session_id]
    assert restored.handles == {}
    assert restored.active_anchor is None
    assert restored.displayed_result_set is None
    assert restored.result_sets == {}


@pytest.mark.parametrize(
    "progress_result",
    (
        pytest.param(False, id="false"),
        pytest.param(1, id="integer_one"),
    ),
)
def test_prose_stream_aborts_each_unacknowledged_timeout_attempt(
    progress_result: object,
) -> None:
    answer_module = _answer_module()
    request = _turn(
        answer_module,
        session_id="session:s12g:unacknowledged-timeouts",
        turn_id="turn:s12g:unacknowledged-timeouts",
        evidence_set=_evidence_set(_read_module(), query="介绍深圳科创"),
    )

    class _UnacknowledgedRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            on_chunk(f"attempt-{self.calls}")
            raise TimeoutError(f"attempt {self.calls} timed out")

    renderer = _UnacknowledgedRenderer()
    forwarded: list[str] = []
    aborts: list[str] = []
    stream_module = answer_module.create_ephemeral_knowledge_answer(
        prose_renderer=renderer,
    )

    def progress(text: str) -> object:
        forwarded.append(text)
        return progress_result

    stream_module.prose_progress = progress
    stream_module.prose_progress_abort = lambda: aborts.append("abort")

    result = stream_module.answer(request)

    assert renderer.calls == 2
    assert forwarded == ["attempt-1", "attempt-2"]
    assert aborts == ["abort", "abort"]
    assert result.render_mode == "deterministic_fallback"
    assert "attempt-1" not in result.answer_text
    assert "attempt-2" not in result.answer_text


@pytest.mark.parametrize(
    ("failure_type", "callback_fails"),
    (
        pytest.param(TimeoutError, False, id="provider-timeout"),
        pytest.param(ValueError, False, id="final-parse"),
        pytest.param(ValueError, True, id="progress-callback"),
        pytest.param(TimeoutError, True, id="progress-callback-timeout"),
    ),
)
def test_visible_prose_stream_failure_is_not_retried_or_committed(
    failure_type: type[Exception],
    callback_fails: bool,
) -> None:
    answer_module = _answer_module()
    request = _turn(
        answer_module,
        session_id=f"session:s12g:visible-failure:{failure_type.__name__}:{callback_fails}",
        turn_id=f"turn:s12g:visible-failure:{failure_type.__name__}:{callback_fails}",
        evidence_set=_evidence_set(_read_module(), query="介绍深圳科创"),
    )

    class _VisibleFailingRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            on_chunk(f"attempt-{self.calls}")
            if not callback_fails:
                raise failure_type("failed after output")
            return "UNREACHABLE"

    renderer = _VisibleFailingRenderer()
    forwarded: list[str] = []
    stream_module = answer_module.create_ephemeral_knowledge_answer(
        prose_renderer=renderer,
    )

    def progress(text: str) -> bool:
        forwarded.append(text)
        if callback_fails:
            raise failure_type("progress stopped")
        return True

    stream_module.prose_progress = progress

    with pytest.raises(failure_type):
        stream_module.answer(request)

    assert renderer.calls == 1
    assert forwarded == ["attempt-1"]
    assert request.session_id not in stream_module._sessions


def test_environment_prose_stream_invalid_output_is_not_retried_as_timeout() -> None:
    answer_module = _answer_module()
    serving_module = import_module(
        "src.data_agents.canonical_v2.knowledge_serving_isolated"
    )
    calls: list[dict[str, object]] = []
    published: list[str] = []
    malformed_shell = (
        '{"selected_claim_indexes":[],"selected_entity_indexes":[]}'
    )

    class _Completions:
        def create(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return (
                SimpleNamespace(
                    choices=(
                        SimpleNamespace(
                            delta=SimpleNamespace(content=malformed_shell),
                        ),
                    )
                ),
            )

    openai_renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions()),
        ),
        model="recorded-chat-model",
        extra_body={},
    )
    environment_renderer = serving_module._EnvironmentProseRenderer()
    environment_renderer._renderer = openai_renderer
    answer = answer_module.create_ephemeral_knowledge_answer(
        prose_renderer=environment_renderer,
    )
    answer.prose_progress = _acknowledging_append(published)
    request = _turn(
        answer_module,
        session_id="session:s12g:malformed-environment-stream",
        turn_id="turn:s12g:malformed-environment-stream",
        evidence_set=_evidence_set(_read_module(), query="介绍深圳科创"),
    )

    result = answer.answer(request)

    assert len(calls) == 1
    assert published == []
    assert result.render_mode == "deterministic_fallback"
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.stage == "prose"
        and limitation.failure_kind == "invalid_output"
        for limitation in result.limitations
    )


def test_environment_prose_sync_invalid_output_is_not_retried_as_timeout() -> None:
    answer_module = _answer_module()
    serving_module = import_module(
        "src.data_agents.canonical_v2.knowledge_serving_isolated"
    )
    calls: list[dict[str, object]] = []
    malformed_wire = (
        "<|canonical_v2_selection_v1|>\n"
        '{"selected_claim_indexes":[]}\n'
        "<|canonical_v2_answer_v1|>\n不得公开"
    )

    class _Completions:
        def create(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        message=SimpleNamespace(content=malformed_wire),
                    ),
                )
            )

    openai_renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions()),
        ),
        model="recorded-chat-model",
        extra_body={},
    )
    environment_renderer = serving_module._EnvironmentProseRenderer()
    environment_renderer._renderer = openai_renderer
    answer = answer_module.create_ephemeral_knowledge_answer(
        prose_renderer=environment_renderer,
    )
    request = _turn(
        answer_module,
        session_id="session:s12g:malformed-environment-sync",
        turn_id="turn:s12g:malformed-environment-sync",
        evidence_set=_evidence_set(_read_module(), query="介绍深圳科创"),
    )

    result = answer.answer(request)

    assert len(calls) == 1
    assert result.render_mode == "deterministic_fallback"
    assert any(
        limitation.code == "prose_synthesis_failed"
        and limitation.stage == "prose"
        and limitation.failure_kind == "invalid_output"
        for limitation in result.limitations
    )


@pytest.mark.parametrize(
    ("marker_kind", "marker"),
    (
        ("evidence-id", "evidence:s12g:dynamic-stream-guard"),
        ("claim-id", "claim:s12g:dynamic-stream-guard"),
        ("continuation-id", "continuation:s12g:dynamic-stream-guard"),
        ("continuation-reason", "evidence_gap"),
        ("continuation-operation", "targeted_evidence_search"),
    ),
)
def test_structured_only_stream_guard_rejects_every_dynamic_marker_split(
    marker_kind: str,
    marker: str,
) -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    company_id = "company:s12g:dynamic-stream-guard"
    evidence_id = "evidence:s12g:dynamic-stream-guard"
    claim_id = "claim:s12g:dynamic-stream-guard"
    continuation_id = "continuation:s12g:dynamic-stream-guard"
    profile = _item(
        read_module,
        evidence_id=evidence_id,
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
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
        evidence_ids=(evidence_id,),
        available=True,
    )
    safe_prefix = "公开回答已经开始，以下内容可安全展示。"

    for split in range(len(marker) + 1):
        request = _turn(
            answer_module,
            session_id=f"session:s12g:stream-guard:{marker_kind}:{split}",
            turn_id=f"turn:s12g:stream-guard:{marker_kind}:{split}",
            evidence_set=_evidence_set(
                read_module,
                query="介绍 Robotics Co",
                items=(profile,),
                continuation_candidates=(candidate,),
            ),
        )
        semantic_claim = _claim(
            answer_module,
            claim_id=claim_id,
            text="Robotics Co 由已接受的本地公司档案证据支持。",
            subject_id=company_id,
            predicate="preferred_name",
            value="Robotics Co",
            evidence_ids=(evidence_id,),
            status="accepted",
        )

        class _UnsafeStreamingRenderer:
            def __init__(self) -> None:
                self.calls = 0
                self.chunks = (
                    safe_prefix + marker[:split],
                    marker[split:],
                )

            def __call__(self, value: Any) -> str:
                return "SYNC_RENDERED"

            def stream(self, value: Any, *, on_chunk: Any) -> str:
                self.calls += 1
                for chunk in self.chunks:
                    on_chunk(chunk)
                return "".join(self.chunks)

        renderer = _UnsafeStreamingRenderer()
        published: list[str] = []
        stream_module = answer_module.create_ephemeral_knowledge_answer(
            answer_selector=lambda value: _answer_proposal(
                answer_module,
                value,
                claim=semantic_claim,
            ),
            prose_renderer=renderer,
        )
        stream_module.prose_progress = _acknowledging_append(published)

        with pytest.raises(ValueError):
            stream_module.answer(request)

        assert renderer.calls == 1, split
        assert "".join(published) == safe_prefix, split
        assert request.session_id not in stream_module._sessions, split


def test_stream_guard_preserves_safe_markdown_url_and_immediate_progress() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    evidence_id = "evidence:s12g:safe-stream-guard"
    company_id = "company:s12g:safe-stream-guard"
    profile = _item(
        read_module,
        evidence_id=evidence_id,
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
    )
    candidate = read_module.ContinuationCandidate(
        candidate_id="continuation:s12g:safe-stream-guard",
        reason="evidence_gap",
        label="Search for targeted evidence",
        operation="targeted_evidence_search",
        target_kind="current_handle",
        target_handle_ids=(company_id,),
        constraint_pairs=(),
        relation_type=None,
        coverage_state=None,
        evidence_ids=(evidence_id,),
        available=True,
    )
    request = _turn(
        answer_module,
        session_id="session:s12g:safe-stream-guard",
        turn_id="turn:s12g:safe-stream-guard",
        evidence_set=_evidence_set(
            read_module,
            query="介绍 Robotics Co",
            items=(profile,),
            continuation_candidates=(candidate,),
        ),
    )
    semantic_claim = _claim(
        answer_module,
        claim_id="claim:s12g:safe-stream-guard",
        text="Robotics Co 由已接受的本地公司档案证据支持。",
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(evidence_id,),
        status="accepted",
    )
    chunks = (
        "# 深圳科创\n\n这是 **公开回答**，详情见 "
        "[官网](https://example.test/product?q=robot)。",
        "\n\n- 第一项\n- 第二项\n",
        "结尾保留普通文本 evidence_ga",
    )
    published: list[str] = []

    class _SafeStreamingRenderer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: Any) -> str:
            return "SYNC_RENDERED"

        def stream(self, value: Any, *, on_chunk: Any) -> str:
            self.calls += 1
            on_chunk(chunks[0])
            assert "".join(published) == chunks[0]
            for chunk in chunks[1:]:
                on_chunk(chunk)
            return "".join(chunks)

    renderer = _SafeStreamingRenderer()
    stream_module = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=lambda value: _answer_proposal(
            answer_module,
            value,
            claim=semantic_claim,
        ),
        prose_renderer=renderer,
    )
    stream_module.prose_progress = _acknowledging_append(published)

    result = stream_module.answer(request)

    assert renderer.calls == 1
    assert "".join(published) == "".join(chunks)
    assert result.answer_text == "".join(chunks)
    assert result.render_mode == "prose_renderer"


def test_stream_guard_rechecks_artificial_eos_before_fatal_marker_splits() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    short_marker = "ambiguity"
    long_marker = "evidence:s12g:adjacent-fatal:" + ("x" * 32)
    company_id = "company:s12g:adjacent-fatal"
    profile = _item(
        read_module,
        evidence_id=long_marker,
        object_id=company_id,
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        status="accepted",
        snippet="The accepted Company name is Robotics Co.",
    )
    candidate = read_module.ContinuationCandidate(
        candidate_id="continuation:s12g:adjacent-fatal",
        reason=short_marker,
        label="Switch candidate",
        operation="switch_candidate",
        target_kind="current_handle",
        target_handle_ids=(),
        constraint_pairs=(),
        relation_type=None,
        coverage_state=None,
        evidence_ids=(long_marker,),
        available=True,
    )
    claim = _claim(
        answer_module,
        claim_id="claim:s12g:adjacent-fatal",
        text="Robotics Co 由已接受的本地公司档案证据支持。",
        subject_id=company_id,
        predicate="preferred_name",
        value="Robotics Co",
        evidence_ids=(long_marker,),
        status="accepted",
    )
    safe_prefix = "这是可公开的安全前缀。"
    unsafe_suffix = short_marker + long_marker

    for split in range(len(unsafe_suffix) + 1):
        request = _turn(
            answer_module,
            session_id=f"session:s12g:adjacent-fatal:{split}",
            turn_id=f"turn:s12g:adjacent-fatal:{split}",
            evidence_set=_evidence_set(
                read_module,
                query="介绍 Robotics Co",
                items=(profile,),
                continuation_candidates=(candidate,),
            ),
        )

        class _AdjacentUnsafeRenderer:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, value: Any) -> str:
                return "SYNC_RENDERED"

            def stream(self, value: Any, *, on_chunk: Any) -> str:
                self.calls += 1
                chunks = (
                    safe_prefix + unsafe_suffix[:split],
                    unsafe_suffix[split:],
                )
                for chunk in chunks:
                    on_chunk(chunk)
                return "".join(chunks)

        renderer = _AdjacentUnsafeRenderer()
        published: list[str] = []
        answer = answer_module.create_ephemeral_knowledge_answer(
            answer_selector=lambda value: _answer_proposal(
                answer_module,
                value,
                claim=claim,
            ),
            prose_renderer=renderer,
        )
        answer.prose_progress = _acknowledging_append(published)

        with pytest.raises(ValueError):
            answer.answer(request)

        assert renderer.calls == 1, split
        assert "".join(published) == safe_prefix, split
        assert request.session_id not in answer._sessions, split


def test_stream_guard_retains_revalidated_pending_suffix_until_resolution() -> None:
    answer_module = _answer_module()
    guard_type = answer_module._StructuredOnlyProseStreamGuard
    short_marker = "ambiguity"
    long_marker = "evidence:s12g:pending-adjacent:" + ("x" * 32)
    marker_prefix = long_marker[:20]
    safe_prefix = "公开前缀。"
    first_chunk = safe_prefix + short_marker + marker_prefix

    fatal_guard = guard_type(frozenset((short_marker, long_marker)))
    fatal_published: list[str] = []
    fatal_guard.feed(first_chunk, publish=fatal_published.append)
    assert "".join(fatal_published) == safe_prefix
    with pytest.raises(ValueError):
        fatal_guard.feed(
            long_marker[len(marker_prefix) :],
            publish=fatal_published.append,
        )
    assert "".join(fatal_published) == safe_prefix

    safe_guard = guard_type(frozenset((short_marker, long_marker)))
    safe_published: list[str] = []
    safe_guard.feed(first_chunk, publish=safe_published.append)
    assert "".join(safe_published) == safe_prefix
    divergent_suffix = "X，随后是普通公开文本。"
    safe_guard.feed(divergent_suffix, publish=safe_published.append)
    safe_guard.flush(publish=safe_published.append)
    assert "".join(safe_published) == first_chunk + divergent_suffix


def test_stream_guard_rechecks_true_eos_and_preserves_safe_adjacency() -> None:
    answer_module = _answer_module()
    guard_type = answer_module._StructuredOnlyProseStreamGuard
    short_marker = "ambiguity"
    long_marker = "evidence:s12g:flush-adjacent:" + ("x" * 32)
    marker_prefix = long_marker[:20]
    safe_prefix = "公开前缀。"

    fatal_guard = guard_type(frozenset((short_marker, long_marker)))
    fatal_published: list[str] = []
    fatal_guard.feed(
        safe_prefix + short_marker,
        publish=fatal_published.append,
    )
    assert "".join(fatal_published) == safe_prefix
    with pytest.raises(ValueError):
        fatal_guard.flush(publish=fatal_published.append)
    assert "".join(fatal_published) == safe_prefix

    safe_guard = guard_type(frozenset((short_marker, long_marker)))
    safe_published: list[str] = []
    safe_text = safe_prefix + short_marker + marker_prefix
    safe_guard.feed(safe_text, publish=safe_published.append)
    assert "".join(safe_published) == safe_prefix
    safe_guard.flush(publish=safe_published.append)
    assert "".join(safe_published) == safe_text


def test_traversed_path_marker_is_guarded_for_every_stream_split() -> None:
    answer_module = _answer_module()
    read_module = _read_module()
    marker = "professor_to_company"
    safe_prefix = "这是可公开的 traversal 回答前缀。"

    for split in range(len(marker) + 1):
        session_id = f"session:s12g:traversed-path:{split}"
        request = _turn(
            answer_module,
            session_id=session_id,
            turn_id=f"turn:s12g:traversed-path:{split}",
            evidence_set=_evidence_set(
                read_module,
                query="他参与创立了哪些企业？",
            ),
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
        published: list[str] = []
        answer = answer_module.create_ephemeral_knowledge_answer(
            prose_renderer=renderer,
        )
        answer._sessions[session_id] = answer_module._SessionState(
            release_id=RELEASE_ID,
            traversed_path_ids=(marker,),
        )
        answer.prose_progress = _acknowledging_append(published)

        with pytest.raises(ValueError):
            answer.answer(request)

        assert renderer.calls == 1, split
        assert "".join(published) == safe_prefix, split
        restored = answer._sessions[session_id]
        assert restored.traversed_path_ids == (marker,), split
        assert restored.evidence_by_id == {}, split
        assert restored.result_sets == {}, split


def test_deterministic_fallback_renders_readable_points_not_raw_dumps() -> None:
    """Deterministic/fallback rendering must never publish raw search dumps:
    source-locator tails are stripped (except for link-seeking renders),
    document-mill page text is dropped, and each grounded point is capped.
    Regression for T15 光基多维力传感 raw-dump answers (2026-08-06)."""
    module = _answer_module()
    junk_claim = module.MaterialClaim(
        claim_id="claim:s12g:t15-taodocs",
        text=(
            "光学传感器涉及的光学原理、效应.ppt_淘豆网：淘豆网 首页 分类 我的"
            "日阅读TOP20 热门文档；来源：https://www.taodocs.com/p-123879375.html"
        ),
        evidence_ids=("evidence:s12g:t15-taodocs",),
        source_natures=("current_web",),
        synthesis=False,
    )
    web_claim = module.MaterialClaim(
        claim_id="claim:s12g:t15-web",
        text="王学谦：清华大学自动化系教师主页；来源：https://example.test/wang-xueqian",
        evidence_ids=("evidence:s12g:t15-web",),
        source_natures=("current_web",),
        synthesis=False,
    )
    long_claim = module.MaterialClaim(
        claim_id="claim:s12g:t15-long",
        text="摘要：" + "长" * 200,
        evidence_ids=("evidence:s12g:t15-long",),
        source_natures=("local",),
        synthesis=False,
    )

    assert (
        module._clean_deterministic_claim_text(
            junk_claim.text, keep_source_tails=False
        )
        is None
    )
    login_wall_claim = module.MaterialClaim(
        claim_id="claim:s12g:t15-login-wall",
        text=(
            "具身智能技术科普之数据采集技术路线：请您登录后查看更多专业优质内容。"
            "登录知乎 · 意见反馈"
        ),
        evidence_ids=("evidence:s12g:t15-login-wall",),
        source_natures=("current_web",),
        synthesis=False,
    )
    assert module.claim_text_is_raw_dump(login_wall_claim.text)
    assert (
        module._clean_deterministic_claim_text(
            login_wall_claim.text, keep_source_tails=False
        )
        is None
    )
    assert not module.claim_text_is_raw_dump(web_claim.text)
    assert module._clean_deterministic_claim_text(
        web_claim.text, keep_source_tails=False
    ) == "王学谦：清华大学自动化系教师主页"
    assert module._clean_deterministic_claim_text(
        web_claim.text, keep_source_tails=True
    ) == web_claim.text
    long_cleaned = module._clean_deterministic_claim_text(
        long_claim.text, keep_source_tails=False
    )
    assert long_cleaned is not None
    assert len(long_cleaned) <= module._DETERMINISTIC_CLAIM_TEXT_LIMIT + len("……")

    answer = module._deterministic_answer_text(
        (junk_claim, web_claim, long_claim),
        required_sentences=("补充说明。",),
    )
    assert "来源：" not in answer
    assert "淘豆网" not in answer
    assert "- 王学谦：清华大学自动化系教师主页" in answer
    assert answer.endswith("补充说明。")

    link_answer = module._deterministic_answer_text(
        (web_claim,),
        keep_source_tails=True,
    )
    assert "https://example.test/wang-xueqian" in link_answer

    all_junk = module._deterministic_answer_text((junk_claim,))
    assert (
        "关于该主体的公开信息目前较为有限，暂未能确认您问的具体内容。" in all_junk
    )

    empty = module._deterministic_answer_text(())
    assert empty == "关于该主体的公开信息目前较为有限，暂未能确认您问的具体内容。"
