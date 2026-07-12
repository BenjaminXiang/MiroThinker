from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import (
    CanonicalIdentity as SharedCanonicalIdentity,
)
from src.data_agents.canonical_v2.contracts import (
    IdentityDecision as SharedIdentityDecision,
)
from src.data_agents.canonical_v2.contracts import (
    PolicyReference as SharedPolicyReference,
)
from src.data_agents.canonical_v2.contracts import (
    SourceAssertion as SharedSourceAssertion,
)
from src.data_agents.canonical_v2.contracts import (
    SourceIdentity as SharedSourceIdentity,
)


TARGET_MODULE = "src.data_agents.canonical_v2.canonical_identity_resolution"
NOW = datetime(2026, 7, 12, 5, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s5-identity-r1"
RUN_ID = "identity-build-run-1"


class _MissingTargetModule(RuntimeError):
    """Exact Task 5.3 RED sentinel; nested missing dependencies fail normally."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingTargetModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _policy(module: Any) -> Any:
    return module.PolicyReference(
        policy_id="canonical-identity-policy",
        policy_version="identity-v1",
        policy_kind="identity",
        content_sha256="5" * 64,
        effective_at=NOW - timedelta(days=1),
    )


def _source_identity(
    module: Any,
    source_identity_id: str,
    *,
    source_system: str,
    source_key: str,
    entity_type: str,
    normalized_keys: dict[str, str],
    record_ids: tuple[str, ...] | None = None,
) -> Any:
    return module.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system=source_system,
        source_key=source_key,
        entity_type=entity_type,
        source_record_ids=record_ids or (f"record:{source_identity_id}",),
        normalized_keys=normalized_keys,
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW,
        state="active",
    )


def _identity_assertion(
    module: Any,
    assertion_id: str,
    source_identity: Any,
    *,
    field_path: str,
    value: Any,
    observed_at: datetime = NOW - timedelta(hours=1),
) -> Any:
    return module.SourceAssertion(
        assertion_id=assertion_id,
        source_record_id=source_identity.source_record_ids[0],
        source_identity_id=source_identity.source_identity_id,
        subject_entity_type=source_identity.entity_type,
        field_path=field_path,
        value=value,
        observed_at=observed_at,
        assertion_run_id="identity-assertion-run-1",
    )


def _canonical_identity(
    module: Any,
    canonical_identity_id: str,
    *,
    entity_type: str,
    source_identity_ids: tuple[str, ...],
    identity_decision_id: str,
    state: str = "active",
    predecessor_identity_ids: tuple[str, ...] = (),
    successor_identity_ids: tuple[str, ...] = (),
) -> Any:
    return module.CanonicalIdentity(
        canonical_identity_id=canonical_identity_id,
        entity_type=entity_type,
        state=state,
        display_name=f"Display {canonical_identity_id}",
        source_identity_ids=source_identity_ids,
        identity_decision_id=identity_decision_id,
        predecessor_identity_ids=predecessor_identity_ids,
        successor_identity_ids=successor_identity_ids,
        release_id=RELEASE_ID,
    )


def _prior_create_decision(
    module: Any,
    canonical_identity: Any,
    *,
    source_identities: tuple[Any, ...],
) -> Any:
    return module.IdentityDecision(
        decision_id=canonical_identity.identity_decision_id,
        action="create",
        source_identity_ids=tuple(
            source.source_identity_id for source in source_identities
        ),
        output_canonical_identity_ids=(canonical_identity.canonical_identity_id,),
        supporting_record_ids=tuple(
            record_id
            for source in source_identities
            for record_id in source.source_record_ids
        ),
        policy=_policy(module),
        method="deterministic",
        method_version="identity-v1",
        decision_run_id="prior-identity-build-run",
        confidence=1.0,
        rationale="Prior canonical identity creation retained for lineage.",
        decided_at=NOW - timedelta(days=2),
    )


def _prior_create_context(
    module: Any,
    decision: Any,
    canonical_identity: Any,
    *,
    source_identities: tuple[Any, ...],
    identity_assertions: tuple[Any, ...],
) -> Any:
    original_output = canonical_identity.model_copy(
        update={
            "state": module.CanonicalIdentityState.active,
            "identity_decision_id": decision.decision_id,
            "successor_identity_ids": (),
        }
    )
    source_ids = {source.source_identity_id for source in source_identities}
    return module.create_identity_decision_context(
        release_id=RELEASE_ID,
        decision=decision,
        candidate_verdict=None,
        source_identities=source_identities,
        identity_assertions=tuple(
            assertion
            for assertion in identity_assertions
            if assertion.source_identity_id in source_ids
        ),
        output_canonical_identities=(original_output,),
        output_allocations=(
            module.IdentityDecisionOutputAllocation(
                canonical_identity_id=original_output.canonical_identity_id,
                source_identity_ids=tuple(sorted(source_ids)),
            ),
        ),
    )


def _current_assignment(
    module: Any,
    *,
    source_identity_id: str,
    canonical_identity_id: str,
    identity_decision_id: str,
) -> Any:
    return module.SourceIdentityAssignment(
        release_id=RELEASE_ID,
        source_identity_id=source_identity_id,
        canonical_identity_id=canonical_identity_id,
        identity_decision_id=identity_decision_id,
    )


def _request(
    module: Any,
    *,
    source_identities: tuple[Any, ...],
    identity_assertions: tuple[Any, ...],
    current_canonical_identities: tuple[Any, ...] = (),
    current_source_identity_assignments: tuple[Any, ...] = (),
    canonical_identity_history: tuple[Any, ...] = (),
    prior_identity_decisions: tuple[Any, ...] = (),
    prior_decision_contexts: tuple[Any, ...] = (),
) -> Any:
    return module.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        identity_method_version="canonical-identity-resolution-v1",
        as_of=NOW,
        policy=_policy(module),
        source_identities=source_identities,
        identity_assertions=identity_assertions,
        current_canonical_identities=current_canonical_identities,
        current_source_identity_assignments=current_source_identity_assignments,
        canonical_identity_history=canonical_identity_history,
        prior_identity_decisions=prior_identity_decisions,
        prior_decision_contexts=prior_decision_contexts,
    )


def _recorded_identity_adjudication(
    module: Any,
    *,
    source_identities: tuple[Any, ...],
    identity_assertions: tuple[Any, ...],
    verdict: str,
    source_identity_groups: tuple[tuple[str, ...], ...],
    confidence: float,
    rationale: str,
    uncertainty: str,
    current_canonical_identities: tuple[Any, ...] = (),
    current_source_identity_assignments: tuple[Any, ...] = (),
    canonical_identity_history: tuple[Any, ...] = (),
    prior_identity_decisions: tuple[Any, ...] = (),
    prior_decision_contexts: tuple[Any, ...] = (),
) -> tuple[Any, bytes]:
    validated_output = {
        "verdict": verdict,
        "source_identity_groups": [list(group) for group in source_identity_groups],
        "confidence": confidence,
        "rationale": rationale,
        "uncertainty": uncertainty,
    }
    raw_output = json.dumps(
        validated_output,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        module.RecordedIdentityAdjudication(
            input_source_identity_ids=tuple(
                sorted(source.source_identity_id for source in source_identities)
            ),
            input_assertion_ids=tuple(
                sorted(assertion.assertion_id for assertion in identity_assertions)
            ),
            input_content_sha256=module.canonical_identity_adjudication_input_sha256(
                source_identities=source_identities,
                identity_assertions=identity_assertions,
                current_canonical_identities=current_canonical_identities,
                current_source_identity_assignments=(
                    current_source_identity_assignments
                ),
                canonical_identity_history=canonical_identity_history,
                prior_identity_decisions=prior_identity_decisions,
                prior_decision_contexts=prior_decision_contexts,
                policy=_policy(module),
            ),
            raw_output=raw_output,
            expected_output_sha256=hashlib.sha256(raw_output).hexdigest(),
        ),
        raw_output,
    )


def _recorded_identity_adjudicator(module: Any, response: Any) -> Any:
    return module.create_recorded_structured_identity_adjudicator(
        provider="recorded",
        model="canonical-identity-judge-fixture-v1",
        prompt_version="canonical-identity-adjudication-v1",
        schema_version="canonical-identity-verdict-v1",
        responses=(response,),
    )


def _assert_unique_current_assignments(
    result: Any, expected_source_identity_ids: set[str]
) -> dict[str, str]:
    current = result.current_canonical_identities
    current_by_id = {identity.canonical_identity_id: identity for identity in current}
    assert len(current_by_id) == len(current)
    assert all(identity.state.value == "active" for identity in current)

    current_memberships = [
        (source_identity_id, identity.canonical_identity_id)
        for identity in current
        for source_identity_id in identity.source_identity_ids
    ]
    current_source_ids = [source_id for source_id, _ in current_memberships]
    assert len(current_source_ids) == len(expected_source_identity_ids)
    assert set(current_source_ids) == expected_source_identity_ids
    assert len(set(current_source_ids)) == len(current_source_ids)

    assignments = result.source_identity_assignments
    assignment_source_ids = [
        assignment.source_identity_id for assignment in assignments
    ]
    assert len(assignments) == len(expected_source_identity_ids)
    assert set(assignment_source_ids) == expected_source_identity_ids
    assert len(set(assignment_source_ids)) == len(assignment_source_ids)
    for assignment in assignments:
        assert assignment.canonical_identity_id in current_by_id
        assert (
            assignment.source_identity_id
            in current_by_id[assignment.canonical_identity_id].source_identity_ids
        )

    assignment_map = {
        assignment.source_identity_id: assignment.canonical_identity_id
        for assignment in assignments
    }
    assert assignment_map == dict(current_memberships)
    return assignment_map


def test_identity_resolution_deep_module_exports_decision_context_contract() -> None:
    module = _module()

    assert {
        "IdentityDecisionContext",
        "IdentityDecisionOutputAllocation",
        "canonical_identity_applied_decision_id",
        "canonical_identity_component_id",
        "canonical_identity_rule_set_sha256",
        "create_identity_decision_context",
        "identity_decision_context_sha256",
    } <= set(module.__all__)


def _assert_decision_and_result_binding(
    module: Any,
    request: Any,
    result: Any,
    *,
    decision: Any,
    verdict: Any,
    source_identity_ids: set[str],
    supporting_assertion_ids: set[str],
    expected_assignment_decision_ids: dict[str, str],
) -> None:
    assert result.release_id == request.release_id
    assert result.decision_run_id == request.decision_run_id
    assert decision.policy == request.policy
    assert decision.method_version == request.identity_method_version
    assert decision.decision_run_id == request.decision_run_id
    if verdict.verdict == "same_entity":
        assert decision.method == verdict.method
        assert decision.confidence == verdict.confidence
        assert decision.rationale == verdict.rationale
        assert decision.llm_trace == verdict.llm_trace
        if decision.llm_trace is not None:
            assert decision.llm_trace.validated_output["uncertainty"] == (
                verdict.uncertainty
            )
    assert set(decision.source_identity_ids) == source_identity_ids
    assert source_identity_ids <= set(verdict.source_identity_ids)
    assert supporting_assertion_ids <= set(verdict.supporting_assertion_ids)
    decision_ids = [item.decision_id for item in result.identity_decisions]
    manifest_ids = [item.decision_id for item in result.decision_manifests]
    assert len(set(decision_ids)) == len(decision_ids)
    assert len(set(manifest_ids)) == len(manifest_ids)
    assert set(manifest_ids) == set(decision_ids)

    request_sources = {
        source.source_identity_id: source for source in request.source_identities
    }
    assert len(request_sources) == len(request.source_identities)
    expected_record_ids = {
        record_id
        for source_identity_id in source_identity_ids
        for record_id in request_sources[source_identity_id].source_record_ids
    }
    assert set(decision.supporting_record_ids) == expected_record_ids

    current_by_id = {
        identity.canonical_identity_id: identity
        for identity in result.current_canonical_identities
    }
    assert set(decision.output_canonical_identity_ids) <= set(current_by_id)
    assert all(
        current_by_id[output_id].identity_decision_id == decision.decision_id
        for output_id in decision.output_canonical_identity_ids
    )

    manifests = [
        manifest
        for manifest in result.decision_manifests
        if manifest.decision_id == decision.decision_id
    ]
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.release_id == request.release_id
    assert set(manifest.supporting_assertion_ids) == supporting_assertion_ids
    assert manifest.input_content_sha256 == (
        module.canonical_identity_decision_input_sha256(
            request=request,
            decision=decision,
            supporting_assertion_ids=tuple(sorted(supporting_assertion_ids)),
        )
    )
    changed_decision = decision.model_copy(
        update={"rationale": f"{decision.rationale} altered"}
    )
    assert (
        module.canonical_identity_decision_input_sha256(
            request=request,
            decision=changed_decision,
            supporting_assertion_ids=tuple(sorted(supporting_assertion_ids)),
        )
        != manifest.input_content_sha256
    )

    retained_sources = {
        source.source_identity_id: source.model_dump(mode="json")
        for source in result.source_identities
    }
    expected_sources = {
        source.source_identity_id: source.model_dump(mode="json")
        for source in request.source_identities
    }
    assert len(retained_sources) == len(result.source_identities)
    assert len(expected_sources) == len(request.source_identities)
    assert retained_sources == expected_sources

    retained_assertions = {
        assertion.assertion_id: assertion.model_dump(mode="json")
        for assertion in result.identity_assertions
    }
    expected_assertions = {
        assertion.assertion_id: assertion.model_dump(mode="json")
        for assertion in request.identity_assertions
    }
    assert len(retained_assertions) == len(result.identity_assertions)
    assert len(expected_assertions) == len(request.identity_assertions)
    assert retained_assertions == expected_assertions

    assignments_by_source = {
        assignment.source_identity_id: assignment
        for assignment in result.source_identity_assignments
    }
    assert len(assignments_by_source) == len(result.source_identity_assignments)
    assert {
        source_identity_id: assignments_by_source[
            source_identity_id
        ].identity_decision_id
        for source_identity_id in expected_assignment_decision_ids
    } == expected_assignment_decision_ids
    assert all(
        assignments_by_source[source_identity_id].canonical_identity_id
        in decision.output_canonical_identity_ids
        for source_identity_id in source_identity_ids
    )

    assert result.content_sha256 == module.canonical_identity_resolution_result_sha256(
        result
    )
    changed_result = result.model_copy(
        update={"decision_run_id": f"{result.decision_run_id}-altered"}
    )
    assert (
        module.canonical_identity_resolution_result_sha256(changed_result)
        != result.content_sha256
    )


def test_matching_strong_identifier_merges_prior_papers_order_independently() -> None:
    module = _module()
    assert module.SourceIdentity is SharedSourceIdentity
    assert module.SourceAssertion is SharedSourceAssertion
    assert module.CanonicalIdentity is SharedCanonicalIdentity
    assert module.IdentityDecision is SharedIdentityDecision
    assert module.PolicyReference is SharedPolicyReference

    source_url = _source_identity(
        module,
        "paper-doi-url",
        source_system="crossref-json",
        source_key="works/10.5555/CANONICAL.V2",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/canonical.v2"},
    )
    source_label = _source_identity(
        module,
        "paper-doi-label",
        source_system="professor-homepage",
        source_key="publication:17",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/canonical.v2"},
    )
    assertion_url = _identity_assertion(
        module,
        "assertion-paper-doi-url",
        source_url,
        field_path="identity.doi",
        value="https://doi.org/10.5555/CANONICAL.V2",
    )
    assertion_label = _identity_assertion(
        module,
        "assertion-paper-doi-label",
        source_label,
        field_path="identity.doi",
        value="DOI: 10.5555/canonical.v2",
    )
    canonical_url = _canonical_identity(
        module,
        "paper-prior-url",
        entity_type="paper",
        source_identity_ids=(source_url.source_identity_id,),
        identity_decision_id="identity-create-paper-url",
    )
    canonical_label = _canonical_identity(
        module,
        "paper-prior-label",
        entity_type="paper",
        source_identity_ids=(source_label.source_identity_id,),
        identity_decision_id="identity-create-paper-label",
    )
    prior_url = _prior_create_decision(
        module, canonical_url, source_identities=(source_url,)
    )
    prior_label = _prior_create_decision(
        module, canonical_label, source_identities=(source_label,)
    )
    prior_contexts = (
        _prior_create_context(
            module,
            prior_url,
            canonical_url,
            source_identities=(source_url,),
            identity_assertions=(assertion_url,),
        ),
        _prior_create_context(
            module,
            prior_label,
            canonical_label,
            source_identities=(source_label,),
            identity_assertions=(assertion_label,),
        ),
    )
    request = _request(
        module,
        source_identities=(source_url, source_label),
        identity_assertions=(assertion_url, assertion_label),
        current_canonical_identities=(canonical_url, canonical_label),
        current_source_identity_assignments=(
            _current_assignment(
                module,
                source_identity_id=source_url.source_identity_id,
                canonical_identity_id=canonical_url.canonical_identity_id,
                identity_decision_id=prior_url.decision_id,
            ),
            _current_assignment(
                module,
                source_identity_id=source_label.source_identity_id,
                canonical_identity_id=canonical_label.canonical_identity_id,
                identity_decision_id=prior_label.decision_id,
            ),
        ),
        prior_identity_decisions=(prior_url, prior_label),
        prior_decision_contexts=prior_contexts,
    )

    engine = module.create_ephemeral_canonical_identity_resolution_engine()
    result = engine.resolve(request)

    assert isinstance(result, module.IdentityResolutionResult)
    assert result.release_id == RELEASE_ID
    assert result.decision_run_id == RUN_ID
    assert len(result.candidate_verdicts) == 1
    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "same_entity"
    assert verdict.method == "deterministic"
    assert verdict.llm_trace is None
    assert set(verdict.source_identity_ids) == {
        source_url.source_identity_id,
        source_label.source_identity_id,
    }
    assert set(verdict.supporting_assertion_ids) == {
        assertion_url.assertion_id,
        assertion_label.assertion_id,
    }

    assert len(result.identity_decisions) == 1
    merge = result.identity_decisions[0]
    assert merge.action == "merge"
    assert merge.method == "deterministic"
    assert merge.llm_trace is None
    assert set(merge.input_canonical_identity_ids) == {
        canonical_url.canonical_identity_id,
        canonical_label.canonical_identity_id,
    }
    assert len(merge.output_canonical_identity_ids) == 1
    output_id = merge.output_canonical_identity_ids[0]

    assert len(result.current_canonical_identities) == 1
    assert result.current_canonical_identities[0].canonical_identity_id == output_id
    history = {
        identity.canonical_identity_id: identity
        for identity in result.canonical_identity_history
    }
    assert set(history) == {
        canonical_url.canonical_identity_id,
        canonical_label.canonical_identity_id,
    }
    assert all(identity.state.value != "active" for identity in history.values())
    identities = {
        **history,
        output_id: result.current_canonical_identities[0],
    }
    output = identities[output_id]
    assert output.state == "active"
    assert set(output.predecessor_identity_ids) == {
        canonical_url.canonical_identity_id,
        canonical_label.canonical_identity_id,
    }
    assert set(output.source_identity_ids) == {
        source_url.source_identity_id,
        source_label.source_identity_id,
    }
    for prior_id in merge.input_canonical_identity_ids:
        assert identities[prior_id].state == "merged"
        assert identities[prior_id].successor_identity_ids == (output_id,)

    assignment_map = _assert_unique_current_assignments(
        result,
        {source_url.source_identity_id, source_label.source_identity_id},
    )
    assert set(assignment_map.values()) == {output_id}
    assert all(
        assignment.identity_decision_id == merge.decision_id
        for assignment in result.source_identity_assignments
    )
    _assert_decision_and_result_binding(
        module,
        request,
        result,
        decision=merge,
        verdict=verdict,
        source_identity_ids={
            source_url.source_identity_id,
            source_label.source_identity_id,
        },
        supporting_assertion_ids={
            assertion_url.assertion_id,
            assertion_label.assertion_id,
        },
        expected_assignment_decision_ids={
            source_url.source_identity_id: merge.decision_id,
            source_label.source_identity_id: merge.decision_id,
        },
    )

    reversed_request = _request(
        module,
        source_identities=tuple(reversed(request.source_identities)),
        identity_assertions=tuple(reversed(request.identity_assertions)),
        current_canonical_identities=tuple(
            reversed(request.current_canonical_identities)
        ),
        current_source_identity_assignments=tuple(
            reversed(request.current_source_identity_assignments)
        ),
        canonical_identity_history=tuple(reversed(request.canonical_identity_history)),
        prior_identity_decisions=tuple(reversed(request.prior_identity_decisions)),
        prior_decision_contexts=tuple(reversed(request.prior_decision_contexts)),
    )
    assert engine.resolve(reversed_request) == result


def test_cross_format_professor_uses_content_bound_structured_llm_judgment() -> None:
    module = _module()
    source_zh = _source_identity(
        module,
        "professor-profile-zh",
        source_system="institution-profile-html",
        source_key="faculty/陈明",
        entity_type="professor",
        normalized_keys={
            "name_key": "chen ming",
            "institution_key": "southern university of science and technology",
        },
    )
    source_en = _source_identity(
        module,
        "professor-cv-en",
        source_system="historical-professor-xlsx",
        source_key="sheet:faculty,row:42",
        entity_type="professor",
        normalized_keys={
            "name_key": "chen ming",
            "institution_key": "southern university of science and technology",
        },
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-professor-name-zh",
            source_zh,
            field_path="identity.name",
            value="陈明",
        ),
        _identity_assertion(
            module,
            "assertion-professor-institution-zh",
            source_zh,
            field_path="identity.institution",
            value="南方科技大学",
        ),
        _identity_assertion(
            module,
            "assertion-professor-research-zh",
            source_zh,
            field_path="identity.research_context",
            value="机器人感知与自主系统",
        ),
        _identity_assertion(
            module,
            "assertion-professor-name-en",
            source_en,
            field_path="identity.name",
            value="Ming Chen",
        ),
        _identity_assertion(
            module,
            "assertion-professor-institution-en",
            source_en,
            field_path="identity.institution",
            value="Southern University of Science and Technology",
        ),
        _identity_assertion(
            module,
            "assertion-professor-research-en",
            source_en,
            field_path="identity.research_context",
            value="robot perception and autonomous systems",
        ),
    )
    sources = (source_zh, source_en)
    recorded, raw_output = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="same_entity",
        source_identity_groups=(
            (source_zh.source_identity_id, source_en.source_identity_id),
        ),
        confidence=0.91,
        rationale=(
            "Compatible bilingual name, institution, and research context support one "
            "Professor identity."
        ),
        uncertainty="No shared strong public identifier is present.",
    )
    request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
    )
    engine = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, recorded)
    )

    result = engine.resolve(request)

    assert len(result.candidate_verdicts) == 1
    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "same_entity"
    assert verdict.method == "structured_llm"
    assert verdict.confidence == 0.91
    assert verdict.rationale.startswith("Compatible bilingual")
    assert verdict.uncertainty == "No shared strong public identifier is present."
    assert set(verdict.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in assertions
    }
    assert verdict.llm_trace is not None
    assert verdict.llm_trace.provider == "recorded"
    assert verdict.llm_trace.model == "canonical-identity-judge-fixture-v1"
    assert verdict.llm_trace.prompt_version == "canonical-identity-adjudication-v1"
    assert verdict.llm_trace.schema_version == "canonical-identity-verdict-v1"
    assert verdict.llm_trace.output_sha256 == hashlib.sha256(raw_output).hexdigest()
    assert set(verdict.llm_trace.input_evidence_ids) == {
        assertion.assertion_id for assertion in assertions
    }

    assert len(result.identity_decisions) == 1
    decision = result.identity_decisions[0]
    assert decision.action == "create"
    assert decision.method == "structured_llm"
    assert decision.llm_trace == verdict.llm_trace
    assert decision.confidence == verdict.confidence
    assert decision.rationale == verdict.rationale
    assert decision.llm_trace.validated_output["uncertainty"] == verdict.uncertainty
    assert set(decision.source_identity_ids) == {
        source.source_identity_id for source in sources
    }
    assert set(decision.supporting_record_ids) == {
        record_id for source in sources for record_id in source.source_record_ids
    }
    assert len(decision.output_canonical_identity_ids) == 1
    output_id = decision.output_canonical_identity_ids[0]
    assignment_map = _assert_unique_current_assignments(
        result, {source.source_identity_id for source in sources}
    )
    assert set(assignment_map.values()) == {output_id}
    _assert_decision_and_result_binding(
        module,
        request,
        result,
        decision=decision,
        verdict=verdict,
        source_identity_ids={source.source_identity_id for source in sources},
        supporting_assertion_ids={assertion.assertion_id for assertion in assertions},
        expected_assignment_decision_ids={
            source.source_identity_id: decision.decision_id for source in sources
        },
    )
    assert engine.resolve(request) == result

    changed_assertions = (
        assertions[0].model_copy(update={"value": "陈铭"}),
        *assertions[1:],
    )
    changed_request = _request(
        module,
        source_identities=sources,
        identity_assertions=changed_assertions,
    )
    changed_engine = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, recorded)
    )
    with pytest.raises(
        module.IdentityAdjudicationIntegrityError, match="input|content"
    ):
        changed_engine.resolve(changed_request)


def test_same_name_professors_with_conflicting_strong_ids_remain_separate() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "professor-wang-a",
        source_system="institution-a-profile",
        source_key="faculty/wang-wei",
        entity_type="professor",
        normalized_keys={
            "name_key": "wang wei",
            "orcid": "0000-0001-1111-1111",
            "institution_key": "shenzhen-university",
        },
    )
    source_b = _source_identity(
        module,
        "professor-wang-b",
        source_system="institution-b-profile",
        source_key="faculty/wang-wei",
        entity_type="professor",
        normalized_keys={
            "name_key": "wang wei",
            "orcid": "0000-0002-2222-2222",
            "institution_key": "harbin-institute-of-technology-shenzhen",
        },
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-wang-a-name",
            source_a,
            field_path="identity.name",
            value="王伟",
        ),
        _identity_assertion(
            module,
            "assertion-wang-a-orcid",
            source_a,
            field_path="identity.orcid",
            value="https://orcid.org/0000-0001-1111-1111",
        ),
        _identity_assertion(
            module,
            "assertion-wang-a-institution",
            source_a,
            field_path="identity.institution",
            value="深圳大学",
        ),
        _identity_assertion(
            module,
            "assertion-wang-b-name",
            source_b,
            field_path="identity.name",
            value="王伟",
        ),
        _identity_assertion(
            module,
            "assertion-wang-b-orcid",
            source_b,
            field_path="identity.orcid",
            value="0000-0002-2222-2222",
        ),
        _identity_assertion(
            module,
            "assertion-wang-b-institution",
            source_b,
            field_path="identity.institution",
            value="哈尔滨工业大学（深圳）",
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )

    assert len(result.candidate_verdicts) == 1
    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "different_entities"
    assert verdict.method == "deterministic"
    assert verdict.llm_trace is None
    assert "conflicting_strong_identifier" in verdict.reason_codes
    assert set(verdict.source_identity_ids) == {
        source_a.source_identity_id,
        source_b.source_identity_id,
    }
    assert set(verdict.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in assertions
    }

    assert len(result.identity_decisions) == 2
    assert {decision.action.value for decision in result.identity_decisions} == {
        "create"
    }
    assert {decision.method.value for decision in result.identity_decisions} == {
        "deterministic"
    }
    assert all(decision.llm_trace is None for decision in result.identity_decisions)
    assert all(
        decision.action.value != "reject" for decision in result.identity_decisions
    )

    current = result.current_canonical_identities
    assert len(current) == 2
    assert all(identity.state.value == "active" for identity in current)
    assert {identity.source_identity_ids for identity in current} == {
        (source_a.source_identity_id,),
        (source_b.source_identity_id,),
    }
    assignments = _assert_unique_current_assignments(
        result, {source_a.source_identity_id, source_b.source_identity_id}
    )
    assert set(assignments) == {
        source_a.source_identity_id,
        source_b.source_identity_id,
    }
    assert len(set(assignments.values())) == 2
    assert all(source.state.value == "active" for source in result.source_identities)
    assertion_ids_by_source = {
        source.source_identity_id: {
            assertion.assertion_id
            for assertion in assertions
            if assertion.source_identity_id == source.source_identity_id
        }
        for source in (source_a, source_b)
    }
    for decision in result.identity_decisions:
        decision_source_ids = set(decision.source_identity_ids)
        assert len(decision_source_ids) == 1
        source_identity_id = next(iter(decision_source_ids))
        _assert_decision_and_result_binding(
            module,
            request,
            result,
            decision=decision,
            verdict=verdict,
            source_identity_ids=decision_source_ids,
            supporting_assertion_ids=assertion_ids_by_source[source_identity_id],
            expected_assignment_decision_ids={source_identity_id: decision.decision_id},
        )


def test_named_mistaken_merge_reversal_produces_exact_split_assignments() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "company-registry-a",
        source_system="company-registry-export",
        source_key="registry:91440300AAA000001A",
        entity_type="company",
        normalized_keys={
            "name_key": "pengcheng innovation technology",
            "unified_social_credit_code": "91440300AAA000001A",
        },
    )
    source_b = _source_identity(
        module,
        "company-registry-b",
        source_system="company-registry-export",
        source_key="registry:91440300BBB000002B",
        entity_type="company",
        normalized_keys={
            "name_key": "pengcheng innovation technology",
            "unified_social_credit_code": "91440300BBB000002B",
        },
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-company-uscc-a",
            source_a,
            field_path="identity.unified_social_credit_code",
            value="91440300AAA000001A",
        ),
        _identity_assertion(
            module,
            "assertion-company-uscc-b",
            source_b,
            field_path="identity.unified_social_credit_code",
            value="91440300BBB000002B",
        ),
    )
    prior_a = _canonical_identity(
        module,
        "company-prior-a",
        entity_type="company",
        source_identity_ids=(source_a.source_identity_id,),
        identity_decision_id="identity-create-company-a",
        state="merged",
        successor_identity_ids=("company-wrong-combined",),
    )
    prior_b = _canonical_identity(
        module,
        "company-prior-b",
        entity_type="company",
        source_identity_ids=(source_b.source_identity_id,),
        identity_decision_id="identity-create-company-b",
        state="merged",
        successor_identity_ids=("company-wrong-combined",),
    )
    wrong_combined = _canonical_identity(
        module,
        "company-wrong-combined",
        entity_type="company",
        source_identity_ids=(
            source_a.source_identity_id,
            source_b.source_identity_id,
        ),
        identity_decision_id="identity-merge-company-wrong",
        predecessor_identity_ids=(
            prior_a.canonical_identity_id,
            prior_b.canonical_identity_id,
        ),
    )
    create_a = _prior_create_decision(module, prior_a, source_identities=(source_a,))
    create_b = _prior_create_decision(module, prior_b, source_identities=(source_b,))
    mistaken_merge = module.IdentityDecision(
        decision_id=wrong_combined.identity_decision_id,
        action="merge",
        source_identity_ids=(
            source_a.source_identity_id,
            source_b.source_identity_id,
        ),
        input_canonical_identity_ids=(
            prior_a.canonical_identity_id,
            prior_b.canonical_identity_id,
        ),
        output_canonical_identity_ids=(wrong_combined.canonical_identity_id,),
        supporting_record_ids=(
            source_a.source_record_ids[0],
            source_b.source_record_ids[0],
        ),
        policy=_policy(module),
        method="human_review",
        method_version="identity-v0",
        decision_run_id="mistaken-merge-run",
        confidence=0.76,
        rationale="Historical review incorrectly treated the two registry rows as one Company.",
        decided_at=NOW - timedelta(days=2),
    )
    create_context_a = _prior_create_context(
        module,
        create_a,
        prior_a,
        source_identities=(source_a,),
        identity_assertions=assertions,
    )
    create_context_b = _prior_create_context(
        module,
        create_b,
        prior_b,
        source_identities=(source_b,),
        identity_assertions=assertions,
    )
    merge_context = module.create_identity_decision_context(
        release_id=RELEASE_ID,
        decision=mistaken_merge,
        candidate_verdict=None,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
        input_canonical_identities=(
            create_context_a.output_canonical_identities[0],
            create_context_b.output_canonical_identities[0],
        ),
        input_source_assignments=(
            _current_assignment(
                module,
                source_identity_id=source_a.source_identity_id,
                canonical_identity_id=prior_a.canonical_identity_id,
                identity_decision_id=create_a.decision_id,
            ),
            _current_assignment(
                module,
                source_identity_id=source_b.source_identity_id,
                canonical_identity_id=prior_b.canonical_identity_id,
                identity_decision_id=create_b.decision_id,
            ),
        ),
        referenced_prior_decision_ids=(create_a.decision_id, create_b.decision_id),
        output_canonical_identities=(wrong_combined,),
        output_allocations=(
            module.IdentityDecisionOutputAllocation(
                canonical_identity_id=wrong_combined.canonical_identity_id,
                source_identity_ids=(
                    source_a.source_identity_id,
                    source_b.source_identity_id,
                ),
            ),
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
        current_canonical_identities=(wrong_combined,),
        current_source_identity_assignments=(
            _current_assignment(
                module,
                source_identity_id=source_a.source_identity_id,
                canonical_identity_id=wrong_combined.canonical_identity_id,
                identity_decision_id=mistaken_merge.decision_id,
            ),
            _current_assignment(
                module,
                source_identity_id=source_b.source_identity_id,
                canonical_identity_id=wrong_combined.canonical_identity_id,
                identity_decision_id=mistaken_merge.decision_id,
            ),
        ),
        canonical_identity_history=(prior_a, prior_b),
        prior_identity_decisions=(create_a, create_b, mistaken_merge),
        prior_decision_contexts=(
            create_context_a,
            create_context_b,
            merge_context,
        ),
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )

    assert len(result.candidate_verdicts) == 1
    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "different_entities"
    assert verdict.method == "deterministic"
    assert "conflicting_strong_identifier" in verdict.reason_codes
    assert set(verdict.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in assertions
    }

    assert len(result.identity_decisions) == 1
    reversal = result.identity_decisions[0]
    assert reversal.action == "reverse"
    assert reversal.reversal_of_decision_id == mistaken_merge.decision_id
    assert reversal.input_canonical_identity_ids == (
        wrong_combined.canonical_identity_id,
    )
    assert len(reversal.output_canonical_identity_ids) == 2
    output_ids = set(reversal.output_canonical_identity_ids)

    current = {
        identity.canonical_identity_id: identity
        for identity in result.current_canonical_identities
    }
    assert set(current) == output_ids
    assert all(identity.state.value == "active" for identity in current.values())
    assert all(
        identity.predecessor_identity_ids == (wrong_combined.canonical_identity_id,)
        for identity in current.values()
    )
    assert {identity.source_identity_ids for identity in current.values()} == {
        (source_a.source_identity_id,),
        (source_b.source_identity_id,),
    }

    history = {
        identity.canonical_identity_id: identity
        for identity in result.canonical_identity_history
    }
    assert set(history).isdisjoint(current)
    assert all(identity.state.value != "active" for identity in history.values())
    corrected_predecessor = history[wrong_combined.canonical_identity_id]
    assert corrected_predecessor.state.value == "split"
    assert set(corrected_predecessor.successor_identity_ids) == output_ids
    assert history[prior_a.canonical_identity_id] == prior_a
    assert history[prior_b.canonical_identity_id] == prior_b

    assignment_map = _assert_unique_current_assignments(
        result, {source_a.source_identity_id, source_b.source_identity_id}
    )
    assert set(assignment_map.values()) == output_ids
    assert all(
        assignment.identity_decision_id == reversal.decision_id
        for assignment in result.source_identity_assignments
    )
    _assert_decision_and_result_binding(
        module,
        request,
        result,
        decision=reversal,
        verdict=verdict,
        source_identity_ids={
            source_a.source_identity_id,
            source_b.source_identity_id,
        },
        supporting_assertion_ids={assertion.assertion_id for assertion in assertions},
        expected_assignment_decision_ids={
            source_a.source_identity_id: reversal.decision_id,
            source_b.source_identity_id: reversal.decision_id,
        },
    )


def test_recovered_patent_keeps_source_and_record_lineage_without_id_compatibility() -> (
    None
):
    module = _module()
    official = _source_identity(
        module,
        "patent-cnipa-current",
        source_system="approved-cnipa-export",
        source_key="publication:CN117873146A",
        entity_type="patent",
        normalized_keys={"publication_number": "CN117873146A"},
        record_ids=("record:cnipa:CN117873146A",),
    )
    recovered = _source_identity(
        module,
        "patent-v042-recovered",
        source_system="wal-fpi-salvage",
        source_key="heap:block-812,offset-17",
        entity_type="patent",
        normalized_keys={
            "publication_number": "CN117873146A",
            "historical_identity_id": "v042:patent:8291",
        },
        record_ids=("record:wal-fpi:patent:block-812:offset-17",),
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-patent-publication-official",
            official,
            field_path="identity.publication_number",
            value="CN117873146A",
        ),
        _identity_assertion(
            module,
            "assertion-patent-publication-recovered",
            recovered,
            field_path="identity.publication_number",
            value="CN 117873146 A",
        ),
        _identity_assertion(
            module,
            "assertion-patent-historical-id",
            recovered,
            field_path="identity.historical_source_id",
            value="v042:patent:8291",
        ),
    )
    official_current = _canonical_identity(
        module,
        "patent-current-canonical",
        entity_type="patent",
        source_identity_ids=(official.source_identity_id,),
        identity_decision_id="identity-create-patent-current",
    )
    prior_create = _prior_create_decision(
        module, official_current, source_identities=(official,)
    )
    prior_context = _prior_create_context(
        module,
        prior_create,
        official_current,
        source_identities=(official,),
        identity_assertions=assertions,
    )
    request = _request(
        module,
        source_identities=(official, recovered),
        identity_assertions=assertions,
        current_canonical_identities=(official_current,),
        current_source_identity_assignments=(
            _current_assignment(
                module,
                source_identity_id=official.source_identity_id,
                canonical_identity_id=official_current.canonical_identity_id,
                identity_decision_id=prior_create.decision_id,
            ),
        ),
        prior_identity_decisions=(prior_create,),
        prior_decision_contexts=(prior_context,),
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )

    assert len(result.candidate_verdicts) == 1
    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "same_entity"
    assert verdict.method == "deterministic"
    assert set(verdict.supporting_assertion_ids) == {
        assertion.assertion_id for assertion in assertions
    }

    assert len(result.identity_decisions) == 1
    decision = result.identity_decisions[0]
    assert decision.action.value == "link"
    assert decision.method.value == "deterministic"
    assert decision.input_canonical_identity_ids == (
        official_current.canonical_identity_id,
    )
    assert decision.output_canonical_identity_ids == (
        official_current.canonical_identity_id,
    )
    assert set(decision.source_identity_ids) == {
        official.source_identity_id,
        recovered.source_identity_id,
    }
    assert set(decision.supporting_record_ids) == {
        official.source_record_ids[0],
        recovered.source_record_ids[0],
    }
    canonical_id = decision.output_canonical_identity_ids[0]
    assert canonical_id != recovered.normalized_keys["historical_identity_id"]

    assert len(result.current_canonical_identities) == 1
    current = result.current_canonical_identities[0]
    assert current.canonical_identity_id == canonical_id
    assert set(current.source_identity_ids) == {
        official.source_identity_id,
        recovered.source_identity_id,
    }
    assert _assert_unique_current_assignments(
        result, {official.source_identity_id, recovered.source_identity_id}
    ) == {
        official.source_identity_id: canonical_id,
        recovered.source_identity_id: canonical_id,
    }

    retained_sources = {
        source.source_identity_id: source for source in result.source_identities
    }
    retained_recovery = retained_sources[recovered.source_identity_id]
    assert retained_recovery.source_system == "wal-fpi-salvage"
    assert retained_recovery.source_key == "heap:block-812,offset-17"
    assert retained_recovery.source_record_ids == (
        "record:wal-fpi:patent:block-812:offset-17",
    )
    assert (
        retained_recovery.normalized_keys["historical_identity_id"]
        == "v042:patent:8291"
    )
    retained_assertions = {
        assertion.assertion_id: assertion for assertion in result.identity_assertions
    }
    assert (
        retained_assertions["assertion-patent-historical-id"].value
        == "v042:patent:8291"
    )
    assert retained_assertions["assertion-patent-historical-id"].source_record_id == (
        "record:wal-fpi:patent:block-812:offset-17"
    )
    _assert_decision_and_result_binding(
        module,
        request,
        result,
        decision=decision,
        verdict=verdict,
        source_identity_ids={
            official.source_identity_id,
            recovered.source_identity_id,
        },
        supporting_assertion_ids={assertion.assertion_id for assertion in assertions},
        expected_assignment_decision_ids={
            official.source_identity_id: prior_create.decision_id,
            recovered.source_identity_id: decision.decision_id,
        },
    )


def test_ambiguous_pair_without_adjudicator_stays_separate_and_unresolved() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "company-ambiguous-a",
        source_system="landing-a",
        source_key="company:ambiguous:a",
        entity_type="company",
        normalized_keys={"name_key": "星河科技"},
    )
    source_b = _source_identity(
        module,
        "company-ambiguous-b",
        source_system="landing-b",
        source_key="company:ambiguous:b",
        entity_type="company",
        normalized_keys={"name_key": "星河科技"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-company-ambiguous-a",
            source_a,
            field_path="identity.name",
            value="星河科技",
        ),
        _identity_assertion(
            module,
            "assertion-company-ambiguous-b",
            source_b,
            field_path="identity.name",
            value="星河科技",
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )

    assert len(result.candidate_verdicts) == 1
    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "unresolved"
    assert verdict.reason_codes == ("structured_adjudication_unavailable",)
    assert verdict.confidence == 0.0
    assert {decision.action.value for decision in result.identity_decisions} == {
        "create"
    }
    assert len(result.identity_decisions) == 2
    assert len(result.current_canonical_identities) == 2
    assert result.canonical_identity_history == ()
    assert all(
        decision.action.value != "reject" for decision in result.identity_decisions
    )
    _assert_unique_current_assignments(
        result, {source_a.source_identity_id, source_b.source_identity_id}
    )


def test_current_assignment_rejects_cross_wired_decision_provenance() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "professor-provenance-a",
        source_system="landing-a",
        source_key="professor:provenance:a",
        entity_type="professor",
        normalized_keys={"name_key": "王宁", "orcid": "0000-0001-0000-0001"},
    )
    source_b = _source_identity(
        module,
        "professor-provenance-b",
        source_system="landing-b",
        source_key="professor:provenance:b",
        entity_type="professor",
        normalized_keys={"name_key": "王宁", "orcid": "0000-0002-0000-0002"},
    )
    identity_a = _canonical_identity(
        module,
        "professor-current-a",
        entity_type="professor",
        source_identity_ids=(source_a.source_identity_id,),
        identity_decision_id="identity-create-provenance-a",
    )
    identity_b = _canonical_identity(
        module,
        "professor-current-b",
        entity_type="professor",
        source_identity_ids=(source_b.source_identity_id,),
        identity_decision_id="identity-create-provenance-b",
    )
    decision_a = _prior_create_decision(
        module, identity_a, source_identities=(source_a,)
    )
    decision_b = _prior_create_decision(
        module, identity_b, source_identities=(source_b,)
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-professor-provenance-a",
            source_a,
            field_path="identity.orcid",
            value="0000-0001-0000-0001",
        ),
        _identity_assertion(
            module,
            "assertion-professor-provenance-b",
            source_b,
            field_path="identity.orcid",
            value="0000-0002-0000-0002",
        ),
    )
    contexts = (
        _prior_create_context(
            module,
            decision_a,
            identity_a,
            source_identities=(source_a,),
            identity_assertions=assertions,
        ),
        _prior_create_context(
            module,
            decision_b,
            identity_b,
            source_identities=(source_b,),
            identity_assertions=assertions,
        ),
    )

    with pytest.raises(ValueError, match="assignment decision provenance"):
        _request(
            module,
            source_identities=(source_a, source_b),
            identity_assertions=assertions,
            current_canonical_identities=(identity_a, identity_b),
            current_source_identity_assignments=(
                _current_assignment(
                    module,
                    source_identity_id=source_a.source_identity_id,
                    canonical_identity_id=identity_a.canonical_identity_id,
                    identity_decision_id=decision_b.decision_id,
                ),
                _current_assignment(
                    module,
                    source_identity_id=source_b.source_identity_id,
                    canonical_identity_id=identity_b.canonical_identity_id,
                    identity_decision_id=decision_a.decision_id,
                ),
            ),
            prior_identity_decisions=(decision_a, decision_b),
            prior_decision_contexts=contexts,
        )


def test_result_rejects_cross_wired_current_assignment_provenance() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "professor-result-provenance-a",
        source_system="landing-a",
        source_key="professor:result-provenance:a",
        entity_type="professor",
        normalized_keys={"name_key": "陈晨", "orcid": "0000-0001-1111-1111"},
    )
    source_b = _source_identity(
        module,
        "professor-result-provenance-b",
        source_system="landing-b",
        source_key="professor:result-provenance:b",
        entity_type="professor",
        normalized_keys={"name_key": "陈晨", "orcid": "0000-0002-2222-2222"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-professor-result-provenance-a",
            source_a,
            field_path="identity.orcid",
            value="0000-0001-1111-1111",
        ),
        _identity_assertion(
            module,
            "assertion-professor-result-provenance-b",
            source_b,
            field_path="identity.orcid",
            value="0000-0002-2222-2222",
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    decision_by_source = {
        decision.source_identity_ids[0]: decision
        for decision in result.identity_decisions
    }
    assignments = list(result.source_identity_assignments)
    first = assignments[0]
    other_source_id = next(
        source_id
        for source_id in decision_by_source
        if source_id != first.source_identity_id
    )
    assignments[0] = first.model_copy(
        update={"identity_decision_id": decision_by_source[other_source_id].decision_id}
    )
    tampered = result.model_copy(
        update={"source_identity_assignments": tuple(assignments)}
    )
    tampered = tampered.model_copy(
        update={
            "content_sha256": module.canonical_identity_resolution_result_sha256(
                tampered
            )
        }
    )

    with pytest.raises(ValueError, match="assignment decision provenance"):
        module.IdentityResolutionResult.model_validate(
            tampered.model_dump(mode="python")
        )


def test_request_rejects_terminal_source_identity_before_resolution() -> None:
    module = _module()
    terminal_seed = _source_identity(
        module,
        "paper-terminal-source",
        source_system="landing-a",
        source_key="paper:terminal",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/terminal"},
    )
    terminal = module.SourceIdentity(
        **{**terminal_seed.model_dump(mode="python"), "state": "superseded"}
    )
    active = _source_identity(
        module,
        "paper-active-source",
        source_system="landing-b",
        source_key="paper:active",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/terminal"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-paper-terminal",
            terminal,
            field_path="identity.doi",
            value="10.5555/terminal",
        ),
        _identity_assertion(
            module,
            "assertion-paper-active",
            active,
            field_path="identity.doi",
            value="10.5555/terminal",
        ),
    )

    with pytest.raises(ValueError, match="source identities must be active"):
        _request(
            module,
            source_identities=(terminal, active),
            identity_assertions=assertions,
        )


def test_request_rejects_cross_entity_current_owner() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "paper-owner-type-a",
        source_system="landing-a",
        source_key="paper:owner-type:a",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/owner-type"},
    )
    source_b = _source_identity(
        module,
        "paper-owner-type-b",
        source_system="landing-b",
        source_key="paper:owner-type:b",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/owner-type"},
    )
    wrong_owner = _canonical_identity(
        module,
        "company-owner-for-paper",
        entity_type="company",
        source_identity_ids=(source_a.source_identity_id,),
        identity_decision_id="identity-create-wrong-owner-type",
    )
    prior_create = _prior_create_decision(
        module, wrong_owner, source_identities=(source_a,)
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-paper-owner-type-a",
            source_a,
            field_path="identity.doi",
            value="10.5555/owner-type",
        ),
        _identity_assertion(
            module,
            "assertion-paper-owner-type-b",
            source_b,
            field_path="identity.doi",
            value="10.5555/owner-type",
        ),
    )
    prior_context = _prior_create_context(
        module,
        prior_create,
        wrong_owner,
        source_identities=(source_a,),
        identity_assertions=assertions,
    )

    with pytest.raises(ValueError, match="canonical identity entity type"):
        _request(
            module,
            source_identities=(source_a, source_b),
            identity_assertions=assertions,
            current_canonical_identities=(wrong_owner,),
            current_source_identity_assignments=(
                _current_assignment(
                    module,
                    source_identity_id=source_a.source_identity_id,
                    canonical_identity_id=wrong_owner.canonical_identity_id,
                    identity_decision_id=prior_create.decision_id,
                ),
            ),
            prior_identity_decisions=(prior_create,),
            prior_decision_contexts=(prior_context,),
        )


def test_request_rejects_unknown_canonical_lineage_endpoint() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "paper-lineage-a",
        source_system="landing-a",
        source_key="paper:lineage:a",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/lineage-a"},
    )
    source_b = _source_identity(
        module,
        "paper-lineage-b",
        source_system="landing-b",
        source_key="paper:lineage:b",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/lineage-b"},
    )
    terminal = _canonical_identity(
        module,
        "paper-terminal-lineage",
        entity_type="paper",
        source_identity_ids=(source_a.source_identity_id,),
        identity_decision_id="identity-create-terminal-lineage",
        state="merged",
        successor_identity_ids=("paper-missing-successor",),
    )
    prior_create = _prior_create_decision(
        module, terminal, source_identities=(source_a,)
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-paper-lineage-a",
            source_a,
            field_path="identity.doi",
            value="10.5555/lineage-a",
        ),
        _identity_assertion(
            module,
            "assertion-paper-lineage-b",
            source_b,
            field_path="identity.doi",
            value="10.5555/lineage-b",
        ),
    )
    prior_context = _prior_create_context(
        module,
        prior_create,
        terminal,
        source_identities=(source_a,),
        identity_assertions=assertions,
    )

    with pytest.raises(ValueError, match="unknown canonical lineage"):
        _request(
            module,
            source_identities=(source_a, source_b),
            identity_assertions=assertions,
            canonical_identity_history=(terminal,),
            prior_identity_decisions=(prior_create,),
            prior_decision_contexts=(prior_context,),
        )


def test_request_rejects_prior_decision_without_exact_decision_time_context() -> None:
    module = _module()
    source = _source_identity(
        module,
        "prior-context-source",
        source_system="historical-landing",
        source_key="paper:prior-context",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/prior-context"},
    )
    assertion = _identity_assertion(
        module,
        "assertion-prior-context",
        source,
        field_path="identity.doi",
        value="10.5555/prior-context",
    )
    current = _canonical_identity(
        module,
        "paper-prior-context",
        entity_type="paper",
        source_identity_ids=(source.source_identity_id,),
        identity_decision_id="decision-prior-context",
    )
    prior = _prior_create_decision(
        module,
        current,
        source_identities=(source,),
    )
    assignment = _current_assignment(
        module,
        source_identity_id=source.source_identity_id,
        canonical_identity_id=current.canonical_identity_id,
        identity_decision_id=prior.decision_id,
    )

    with pytest.raises(
        ValueError, match="prior (?:identity )?decision.*context|context.*prior"
    ):
        _request(
            module,
            source_identities=(source,),
            identity_assertions=(assertion,),
            current_canonical_identities=(current,),
            current_source_identity_assignments=(assignment,),
            prior_identity_decisions=(prior,),
        )


def test_request_bound_validation_rejects_rehashed_manifest_tampering() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "company-manifest-a",
        source_system="landing-a",
        source_key="company:manifest:a",
        entity_type="company",
        normalized_keys={"name_key": "远航智能"},
    )
    source_b = _source_identity(
        module,
        "company-manifest-b",
        source_system="landing-b",
        source_key="company:manifest:b",
        entity_type="company",
        normalized_keys={"name_key": "远航智能"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-company-manifest-a",
            source_a,
            field_path="identity.name",
            value="远航智能",
        ),
        _identity_assertion(
            module,
            "assertion-company-manifest-b",
            source_b,
            field_path="identity.name",
            value="远航智能",
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    manifests = list(result.decision_manifests)
    manifests[0] = manifests[0].model_copy(update={"input_content_sha256": "f" * 64})
    tampered = result.model_copy(update={"decision_manifests": tuple(manifests)})
    tampered = tampered.model_copy(
        update={
            "content_sha256": module.canonical_identity_resolution_result_sha256(
                tampered
            )
        }
    )

    with pytest.raises(
        module.IdentityResolutionIntegrityError, match="manifest|content"
    ):
        module.validate_identity_resolution_result(request, tampered)


def test_request_bound_validation_rejects_rehashed_decision_tampering() -> None:
    module = _module()
    sources = (
        _source_identity(
            module,
            "decision-tamper-company-a",
            source_system="landing-a",
            source_key="company:decision-tamper:a",
            entity_type="company",
            normalized_keys={"name_key": "篡改测试"},
        ),
        _source_identity(
            module,
            "decision-tamper-company-b",
            source_system="landing-b",
            source_key="company:decision-tamper:b",
            entity_type="company",
            normalized_keys={"name_key": "篡改测试"},
        ),
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.company_name",
            value=source.source_key,
        )
        for source in sources
    )
    request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    decisions = list(result.identity_decisions)
    decisions[0] = decisions[0].model_copy(
        update={"rationale": "tampered rationale with internally consistent hashes"}
    )
    manifests = list(result.decision_manifests)
    manifest_index = next(
        index
        for index, manifest in enumerate(manifests)
        if manifest.decision_id == decisions[0].decision_id
    )
    manifests[manifest_index] = manifests[manifest_index].model_copy(
        update={
            "input_content_sha256": module.canonical_identity_decision_input_sha256(
                request=request,
                decision=decisions[0],
                supporting_assertion_ids=manifests[
                    manifest_index
                ].supporting_assertion_ids,
            )
        }
    )
    tampered = result.model_copy(
        update={
            "identity_decisions": tuple(decisions),
            "decision_manifests": tuple(manifests),
        }
    )
    tampered = tampered.model_copy(
        update={
            "content_sha256": module.canonical_identity_resolution_result_sha256(
                tampered
            )
        }
    )

    with pytest.raises(
        module.IdentityResolutionIntegrityError,
        match="decision.*content|content.*decision",
    ):
        module.validate_identity_resolution_result(request, tampered)


def test_request_bound_validation_rejects_rehashed_verdict_tampering() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "company-verdict-a",
        source_system="landing-a",
        source_key="company:verdict:a",
        entity_type="company",
        normalized_keys={"name_key": "启明数据"},
    )
    source_b = _source_identity(
        module,
        "company-verdict-b",
        source_system="landing-b",
        source_key="company:verdict:b",
        entity_type="company",
        normalized_keys={"name_key": "启明数据"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-company-verdict-a",
            source_a,
            field_path="identity.name",
            value="启明数据",
        ),
        _identity_assertion(
            module,
            "assertion-company-verdict-b",
            source_b,
            field_path="identity.name",
            value="启明数据",
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    verdict = result.candidate_verdicts[0].model_copy(
        update={"rationale": "tampered but internally rehashed rationale"}
    )
    tampered = result.model_copy(update={"candidate_verdicts": (verdict,)})
    tampered = tampered.model_copy(
        update={
            "content_sha256": module.canonical_identity_resolution_result_sha256(
                tampered
            )
        }
    )

    with pytest.raises(
        module.IdentityResolutionIntegrityError,
        match="verdict.*content|content.*verdict",
    ):
        module.validate_identity_resolution_result(request, tampered)


def test_adjudication_input_hash_binds_current_assignment_provenance() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "professor-adjudication-context-a",
        source_system="landing-a",
        source_key="professor:adjudication-context:a",
        entity_type="professor",
        normalized_keys={"name_key": "li ming"},
    )
    source_b = _source_identity(
        module,
        "professor-adjudication-context-b",
        source_system="landing-b",
        source_key="professor:adjudication-context:b",
        entity_type="professor",
        normalized_keys={"name_key": "li ming"},
    )
    current = _canonical_identity(
        module,
        "professor-adjudication-current",
        entity_type="professor",
        source_identity_ids=(source_a.source_identity_id,),
        identity_decision_id="identity-create-adjudication-current",
    )
    prior_create = _prior_create_decision(
        module, current, source_identities=(source_a,)
    )
    assignment = _current_assignment(
        module,
        source_identity_id=source_a.source_identity_id,
        canonical_identity_id=current.canonical_identity_id,
        identity_decision_id=prior_create.decision_id,
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-professor-adjudication-context-a",
            source_a,
            field_path="identity.name",
            value="李明",
        ),
        _identity_assertion(
            module,
            "assertion-professor-adjudication-context-b",
            source_b,
            field_path="identity.name",
            value="Li Ming",
        ),
    )
    common = {
        "source_identities": (source_a, source_b),
        "identity_assertions": assertions,
        "current_canonical_identities": (current,),
        "canonical_identity_history": (),
        "prior_identity_decisions": (prior_create,),
        "policy": _policy(module),
    }

    exact_hash = module.canonical_identity_adjudication_input_sha256(
        **common,
        current_source_identity_assignments=(assignment,),
    )
    changed_assignment = assignment.model_copy(
        update={"identity_decision_id": "identity-different-provenance"}
    )
    changed_hash = module.canonical_identity_adjudication_input_sha256(
        **common,
        current_source_identity_assignments=(changed_assignment,),
    )

    assert exact_hash != changed_hash


def test_request_bound_validation_rejects_cross_wired_output_decision() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "professor-output-a",
        source_system="landing-a",
        source_key="professor:output:a",
        entity_type="professor",
        normalized_keys={"name_key": "zhou lin", "orcid": "0000-0001-3333-3333"},
    )
    source_b = _source_identity(
        module,
        "professor-output-b",
        source_system="landing-b",
        source_key="professor:output:b",
        entity_type="professor",
        normalized_keys={"name_key": "zhou lin", "orcid": "0000-0002-4444-4444"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-professor-output-a",
            source_a,
            field_path="identity.orcid",
            value="0000-0001-3333-3333",
        ),
        _identity_assertion(
            module,
            "assertion-professor-output-b",
            source_b,
            field_path="identity.orcid",
            value="0000-0002-4444-4444",
        ),
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    identities = list(result.current_canonical_identities)
    other_decision_id = next(
        decision.decision_id
        for decision in result.identity_decisions
        if decision.decision_id != identities[0].identity_decision_id
    )
    identities[0] = identities[0].model_copy(
        update={"identity_decision_id": other_decision_id}
    )
    tampered = result.model_copy(
        update={"current_canonical_identities": tuple(identities)}
    )
    tampered = tampered.model_copy(
        update={
            "content_sha256": module.canonical_identity_resolution_result_sha256(
                tampered
            )
        }
    )

    with pytest.raises(
        module.IdentityResolutionIntegrityError,
        match="output.*decision|decision.*output",
    ):
        module.validate_identity_resolution_result(request, tampered)


def test_recorded_adjudication_rejects_raw_output_hash_tampering() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "company-raw-a",
        source_system="landing-a",
        source_key="company:raw:a",
        entity_type="company",
        normalized_keys={"name_key": "凌云科技"},
    )
    source_b = _source_identity(
        module,
        "company-raw-b",
        source_system="landing-b",
        source_key="company:raw:b",
        entity_type="company",
        normalized_keys={"name_key": "凌云科技"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-company-raw-a",
            source_a,
            field_path="identity.name",
            value="凌云科技",
        ),
        _identity_assertion(
            module,
            "assertion-company-raw-b",
            source_b,
            field_path="identity.name",
            value="凌云科技",
        ),
    )
    recorded, raw_output = _recorded_identity_adjudication(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
        verdict="same_entity",
        source_identity_groups=(
            (source_a.source_identity_id, source_b.source_identity_id),
        ),
        confidence=0.81,
        rationale="Recorded same-entity fixture.",
        uncertainty="No strong public identifier.",
    )
    tampered = recorded.model_copy(update={"raw_output": raw_output + b" "})
    engine = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, tampered)
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )

    with pytest.raises(module.IdentityAdjudicationIntegrityError, match="output hash"):
        engine.resolve(request)


def test_structured_different_entity_verdict_stays_separate() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "professor-llm-separate-a",
        source_system="landing-a",
        source_key="professor:llm-separate:a",
        entity_type="professor",
        normalized_keys={"name_key": "yang fan"},
    )
    source_b = _source_identity(
        module,
        "professor-llm-separate-b",
        source_system="landing-b",
        source_key="professor:llm-separate:b",
        entity_type="professor",
        normalized_keys={"name_key": "yang fan"},
    )
    assertions = (
        _identity_assertion(
            module,
            "assertion-professor-llm-separate-a",
            source_a,
            field_path="identity.institution",
            value="深圳大学",
        ),
        _identity_assertion(
            module,
            "assertion-professor-llm-separate-b",
            source_b,
            field_path="identity.institution",
            value="香港中文大学（深圳）",
        ),
    )
    recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
        verdict="different_entities",
        source_identity_groups=(
            (source_a.source_identity_id,),
            (source_b.source_identity_id,),
        ),
        confidence=0.93,
        rationale="Conflicting institution histories support distinct Professors.",
        uncertainty="No strong public identifier is available.",
    )
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, recorded)
    ).resolve(request)

    assert result.candidate_verdicts[0].verdict == "different_entities"
    assert result.candidate_verdicts[0].method == "structured_llm"
    assert len(result.current_canonical_identities) == 2
    assert {decision.action.value for decision in result.identity_decisions} == {
        "create"
    }
    assert all(
        decision.method.value == "composite" for decision in result.identity_decisions
    )
    assert all(decision.llm_trace is None for decision in result.identity_decisions)
    assert {
        manifest.candidate_verdict_id for manifest in result.decision_manifests
    } == {result.candidate_verdicts[0].verdict_id}
    assert all(
        decision.action.value != "reject" for decision in result.identity_decisions
    )


def test_release_batch_resolves_multiple_components_across_all_domains() -> None:
    module = _module()
    paper_crossref = _source_identity(
        module,
        "batch-paper-crossref",
        source_system="crossref-json",
        source_key="works/10.5555/BATCH.V2",
        entity_type="paper",
        normalized_keys={"doi": "https://doi.org/10.5555/BATCH.V2"},
    )
    paper_homepage = _source_identity(
        module,
        "batch-paper-homepage",
        source_system="professor-homepage",
        source_key="publication:batch-v2",
        entity_type="paper",
        normalized_keys={"doi": " doi:10.5555/batch.v2 "},
    )
    professor_roster = _source_identity(
        module,
        "batch-professor-roster",
        source_system="institution-roster",
        source_key="faculty/lin-yan",
        entity_type="professor",
        normalized_keys={
            "name_key": " Lin  Yan ",
            "institution_key": "Shenzhen University",
            "department_key": "Computer Science",
        },
    )
    professor_cv = _source_identity(
        module,
        "batch-professor-cv",
        source_system="historical-cv",
        source_key="cv/lin-yan",
        entity_type="professor",
        normalized_keys={
            "name_key": "lin yan",
            "institution_key": "shenzhen university",
            "department_key": " computer   science ",
        },
    )
    company = _source_identity(
        module,
        "batch-company-singleton",
        source_system="approved-company-batch",
        source_key="company/91440300BATCH0001",
        entity_type="company",
        normalized_keys={
            "name_key": "鹏程智能",
            "unified_social_credit_code": "91440300BATCH0001",
        },
    )
    patent = _source_identity(
        module,
        "batch-patent-singleton",
        source_system="approved-patent-export",
        source_key="patent/CN117873146A",
        entity_type="patent",
        normalized_keys={"publication_number": "CN-117873146-A"},
    )
    sources = (
        paper_crossref,
        paper_homepage,
        professor_roster,
        professor_cv,
        company,
        patent,
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.batch_anchor",
            value=source.source_key,
        )
        for source in sources
    )
    request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
    )

    engine = module.create_ephemeral_canonical_identity_resolution_engine()
    result = engine.resolve(request)

    assert len(result.candidate_verdicts) == 2
    assert {
        tuple(verdict.source_identity_ids): tuple(verdict.reason_codes)
        for verdict in result.candidate_verdicts
    } == {
        tuple(
            sorted(
                (paper_crossref.source_identity_id, paper_homepage.source_identity_id)
            )
        ): ("matching_strong_identifier",),
        tuple(
            sorted(
                (professor_roster.source_identity_id, professor_cv.source_identity_id)
            )
        ): ("matching_high_confidence_composite",),
    }
    current_memberships = {
        identity.entity_type: frozenset(identity.source_identity_ids)
        for identity in result.current_canonical_identities
    }
    assert current_memberships == {
        "paper": frozenset(
            (paper_crossref.source_identity_id, paper_homepage.source_identity_id)
        ),
        "professor": frozenset(
            (professor_roster.source_identity_id, professor_cv.source_identity_id)
        ),
        "company": frozenset((company.source_identity_id,)),
        "patent": frozenset((patent.source_identity_id,)),
    }
    _assert_unique_current_assignments(
        result, {source.source_identity_id for source in sources}
    )
    assert len(result.identity_decisions) == 4
    assert all(
        decision.action.value == "create" for decision in result.identity_decisions
    )

    reversed_request = _request(
        module,
        source_identities=tuple(reversed(sources)),
        identity_assertions=tuple(reversed(assertions)),
    )
    assert engine.resolve(reversed_request) == result


def test_engine_generated_create_merge_reverse_uses_new_successor_ids() -> None:
    module = _module()
    source_a = _source_identity(
        module,
        "lifecycle-company-a",
        source_system="historical-company-a",
        source_key="company:lifecycle:a",
        entity_type="company",
        normalized_keys={"name_key": "同名科技"},
    )
    source_b = _source_identity(
        module,
        "lifecycle-company-b",
        source_system="historical-company-b",
        source_key="company:lifecycle:b",
        entity_type="company",
        normalized_keys={"name_key": "同名科技"},
    )
    sources = (source_a, source_b)
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.company_name",
            value=source.source_key,
        )
        for source in sources
    )
    separate_recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="different_entities",
        source_identity_groups=(
            (source_a.source_identity_id,),
            (source_b.source_identity_id,),
        ),
        confidence=0.97,
        rationale="Independent evidence supports two Companies.",
        uncertainty="No material uncertainty remains.",
    )
    initial_request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
    )
    created = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, separate_recorded)
    ).resolve(initial_request)
    original_singleton_ids = {
        identity.canonical_identity_id
        for identity in created.current_canonical_identities
    }

    merge_request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        current_canonical_identities=created.current_canonical_identities,
        current_source_identity_assignments=created.source_identity_assignments,
        canonical_identity_history=created.canonical_identity_history,
        prior_identity_decisions=created.identity_decisions,
        prior_decision_contexts=created.decision_contexts,
    )
    merge_recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="same_entity",
        source_identity_groups=(
            (source_a.source_identity_id, source_b.source_identity_id),
        ),
        confidence=0.96,
        rationale="New corroborating evidence supports one Company.",
        uncertainty="No material uncertainty remains.",
        current_canonical_identities=merge_request.current_canonical_identities,
        current_source_identity_assignments=(
            merge_request.current_source_identity_assignments
        ),
        canonical_identity_history=merge_request.canonical_identity_history,
        prior_identity_decisions=merge_request.prior_identity_decisions,
        prior_decision_contexts=merge_request.prior_decision_contexts,
    )
    merged = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, merge_recorded)
    ).resolve(merge_request)

    reverse_request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        current_canonical_identities=merged.current_canonical_identities,
        current_source_identity_assignments=merged.source_identity_assignments,
        canonical_identity_history=merged.canonical_identity_history,
        prior_identity_decisions=(
            *created.identity_decisions,
            *merged.identity_decisions,
        ),
        prior_decision_contexts=(
            *created.decision_contexts,
            *merged.decision_contexts,
        ),
    )
    reverse_recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="different_entities",
        source_identity_groups=(
            (source_a.source_identity_id,),
            (source_b.source_identity_id,),
        ),
        confidence=0.98,
        rationale="Corrected evidence proves two distinct Companies.",
        uncertainty="No material uncertainty remains.",
        current_canonical_identities=reverse_request.current_canonical_identities,
        current_source_identity_assignments=(
            reverse_request.current_source_identity_assignments
        ),
        canonical_identity_history=reverse_request.canonical_identity_history,
        prior_identity_decisions=reverse_request.prior_identity_decisions,
        prior_decision_contexts=reverse_request.prior_decision_contexts,
    )

    reversed_result = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, reverse_recorded)
    ).resolve(reverse_request)

    current_ids = {
        identity.canonical_identity_id
        for identity in reversed_result.current_canonical_identities
    }
    history_ids = {
        identity.canonical_identity_id
        for identity in reversed_result.canonical_identity_history
    }
    assert current_ids.isdisjoint(history_ids)
    assert current_ids.isdisjoint(original_singleton_ids)
    assert {
        identity.source_identity_ids
        for identity in reversed_result.current_canonical_identities
    } == {(source_a.source_identity_id,), (source_b.source_identity_id,)}


@pytest.mark.parametrize("resolved_state", ("separate", "combined"))
def test_already_resolved_candidate_is_a_stable_noop(resolved_state: str) -> None:
    module = _module()
    if resolved_state == "separate":
        sources = (
            _source_identity(
                module,
                "noop-professor-a",
                source_system="institution-a",
                source_key="faculty/noop-a",
                entity_type="professor",
                normalized_keys={
                    "name_key": "same name",
                    "orcid": "0000-0001-0000-0001",
                },
            ),
            _source_identity(
                module,
                "noop-professor-b",
                source_system="institution-b",
                source_key="faculty/noop-b",
                entity_type="professor",
                normalized_keys={
                    "name_key": "same name",
                    "orcid": "0000-0002-0000-0002",
                },
            ),
        )
    else:
        sources = (
            _source_identity(
                module,
                "noop-paper-a",
                source_system="crossref",
                source_key="works/noop-a",
                entity_type="paper",
                normalized_keys={"doi": "10.5555/noop"},
            ),
            _source_identity(
                module,
                "noop-paper-b",
                source_system="homepage",
                source_key="publication/noop-b",
                entity_type="paper",
                normalized_keys={"doi": "https://doi.org/10.5555/NOOP"},
            ),
        )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.noop_anchor",
            value=source.source_key,
        )
        for source in sources
    )
    engine = module.create_ephemeral_canonical_identity_resolution_engine()
    initial = engine.resolve(
        _request(
            module,
            source_identities=sources,
            identity_assertions=assertions,
        )
    )
    replay_request = _request(
        module,
        source_identities=tuple(reversed(sources)),
        identity_assertions=tuple(reversed(assertions)),
        current_canonical_identities=tuple(
            reversed(initial.current_canonical_identities)
        ),
        current_source_identity_assignments=tuple(
            reversed(initial.source_identity_assignments)
        ),
        canonical_identity_history=tuple(reversed(initial.canonical_identity_history)),
        prior_identity_decisions=tuple(reversed(initial.identity_decisions)),
        prior_decision_contexts=tuple(reversed(initial.decision_contexts)),
    )

    replay = engine.resolve(replay_request)

    assert replay.identity_decisions == ()
    assert replay.decision_manifests == ()
    assert replay.current_canonical_identities == initial.current_canonical_identities
    assert replay.canonical_identity_history == initial.canonical_identity_history
    assert replay.source_identity_assignments == initial.source_identity_assignments
    assert len(replay.candidate_verdicts) == 1
    assert replay.candidate_verdicts[0].verdict == (
        "different_entities" if resolved_state == "separate" else "same_entity"
    )


def test_structured_different_entities_rejects_one_combined_group() -> None:
    module = _module()
    sources = (
        _source_identity(
            module,
            "contradictory-group-a",
            source_system="landing-a",
            source_key="company:contradictory:a",
            entity_type="company",
            normalized_keys={"name_key": "重叠科技"},
        ),
        _source_identity(
            module,
            "contradictory-group-b",
            source_system="landing-b",
            source_key="company:contradictory:b",
            entity_type="company",
            normalized_keys={"name_key": "重叠科技"},
        ),
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.company_name",
            value=source.source_key,
        )
        for source in sources
    )
    recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="different_entities",
        source_identity_groups=(
            (sources[0].source_identity_id, sources[1].source_identity_id),
        ),
        confidence=0.99,
        rationale="Contradictory fixture.",
        uncertainty="None.",
    )

    with pytest.raises(
        module.IdentityAdjudicationOutputError,
        match="different_entities|groups",
    ):
        module.create_ephemeral_canonical_identity_resolution_engine(
            adjudicator=_recorded_identity_adjudicator(module, recorded)
        ).resolve(
            _request(
                module,
                source_identities=sources,
                identity_assertions=assertions,
            )
        )


def test_low_confidence_llm_merge_degrades_to_unresolved_without_trace_relabeling() -> (
    None
):
    module = _module()
    sources = (
        _source_identity(
            module,
            "low-confidence-company-a",
            source_system="landing-a",
            source_key="company:low-confidence:a",
            entity_type="company",
            normalized_keys={"name_key": "候选科技"},
        ),
        _source_identity(
            module,
            "low-confidence-company-b",
            source_system="landing-b",
            source_key="company:low-confidence:b",
            entity_type="company",
            normalized_keys={"name_key": "候选科技"},
        ),
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.company_name",
            value=source.source_key,
        )
        for source in sources
    )
    recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="same_entity",
        source_identity_groups=(
            (sources[0].source_identity_id, sources[1].source_identity_id),
        ),
        confidence=0.41,
        rationale="The names may refer to one Company.",
        uncertainty="Identity evidence is weak and conflicting.",
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, recorded)
    ).resolve(
        _request(
            module,
            source_identities=sources,
            identity_assertions=assertions,
        )
    )

    verdict = result.candidate_verdicts[0]
    assert verdict.verdict == "unresolved"
    assert verdict.proposed_outcome == "same_entity"
    assert verdict.source_identity_groups == (
        (sources[0].source_identity_id, sources[1].source_identity_id),
    )
    assert "below_auto_action_threshold" in verdict.reason_codes
    assert verdict.llm_trace is not None
    assert len(result.current_canonical_identities) == 2
    assert {
        identity.source_identity_ids for identity in result.current_canonical_identities
    } == {(sources[0].source_identity_id,), (sources[1].source_identity_id,)}
    assert all(decision.llm_trace is None for decision in result.identity_decisions)
    assert all(
        decision.method.value == "composite" for decision in result.identity_decisions
    )
    manifests = {
        manifest.decision_id: manifest for manifest in result.decision_manifests
    }
    assertions_by_source = {
        source.source_identity_id: {
            assertion.assertion_id
            for assertion in assertions
            if assertion.source_identity_id == source.source_identity_id
        }
        for source in sources
    }
    for decision in result.identity_decisions:
        assert (
            manifests[decision.decision_id].candidate_verdict_id == verdict.verdict_id
        )
        assert (
            set(manifests[decision.decision_id].supporting_assertion_ids)
            == (assertions_by_source[decision.source_identity_ids[0]])
        )


def test_structured_component_partition_materializes_exact_source_groups() -> None:
    module = _module()
    sources = tuple(
        _source_identity(
            module,
            f"partition-company-{suffix}",
            source_system=f"landing-{suffix}",
            source_key=f"company:partition:{suffix}",
            entity_type="company",
            normalized_keys={"name_key": "分组科技"},
        )
        for suffix in ("a", "b", "c")
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.company_name",
            value=source.source_key,
        )
        for source in sources
    )
    expected_groups = (
        (sources[0].source_identity_id, sources[1].source_identity_id),
        (sources[2].source_identity_id,),
    )
    recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="different_entities",
        source_identity_groups=expected_groups,
        confidence=0.94,
        rationale="Two records co-refer while the third is a distinct Company.",
        uncertainty="No strong public identifier is available.",
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, recorded)
    ).resolve(
        _request(
            module,
            source_identities=sources,
            identity_assertions=assertions,
        )
    )

    assert result.candidate_verdicts[0].source_identity_groups == expected_groups
    assert {
        identity.source_identity_ids for identity in result.current_canonical_identities
    } == set(expected_groups)
    assert {
        decision.source_identity_ids for decision in result.identity_decisions
    } == set(expected_groups)
    assert len(result.identity_decisions) == 2


def test_conflicting_strong_identifiers_preserve_equal_identifier_groups() -> None:
    module = _module()
    sources = (
        _source_identity(
            module,
            "strong-group-professor-a1",
            source_system="roster-a",
            source_key="faculty/a1",
            entity_type="professor",
            normalized_keys={
                "name_key": "same professor",
                "orcid": "0000-0001-1111-1111",
            },
        ),
        _source_identity(
            module,
            "strong-group-professor-a2",
            source_system="cv-a",
            source_key="cv/a2",
            entity_type="professor",
            normalized_keys={
                "name_key": "same professor",
                "orcid": "https://orcid.org/0000-0001-1111-1111",
            },
        ),
        _source_identity(
            module,
            "strong-group-professor-b",
            source_system="roster-b",
            source_key="faculty/b",
            entity_type="professor",
            normalized_keys={
                "name_key": "same professor",
                "orcid": "0000-0002-2222-2222",
            },
        ),
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.orcid",
            value=source.normalized_keys["orcid"],
        )
        for source in sources
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        _request(
            module,
            source_identities=sources,
            identity_assertions=assertions,
        )
    )

    expected_groups = {
        (sources[0].source_identity_id, sources[1].source_identity_id),
        (sources[2].source_identity_id,),
    }
    assert {
        identity.source_identity_ids for identity in result.current_canonical_identities
    } == expected_groups
    assert set(result.candidate_verdicts[0].source_identity_groups) == expected_groups


def test_same_entity_component_merges_more_than_two_current_owners() -> None:
    module = _module()
    sources = tuple(
        _source_identity(
            module,
            f"many-owner-company-{suffix}",
            source_system=f"landing-{suffix}",
            source_key=f"company:many-owner:{suffix}",
            entity_type="company",
            normalized_keys={"name_key": "多源科技"},
        )
        for suffix in ("a", "b", "c")
    )
    assertions = tuple(
        _identity_assertion(
            module,
            f"assertion-{source.source_identity_id}",
            source,
            field_path="identity.company_name",
            value=source.source_key,
        )
        for source in sources
    )
    separate_recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="different_entities",
        source_identity_groups=tuple(
            (source.source_identity_id,) for source in sources
        ),
        confidence=0.96,
        rationale="Initial evidence supports three Companies.",
        uncertainty="No material uncertainty remains.",
    )
    initial = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, separate_recorded)
    ).resolve(
        _request(
            module,
            source_identities=sources,
            identity_assertions=assertions,
        )
    )
    merge_request = _request(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        current_canonical_identities=initial.current_canonical_identities,
        current_source_identity_assignments=initial.source_identity_assignments,
        prior_identity_decisions=initial.identity_decisions,
        prior_decision_contexts=initial.decision_contexts,
    )
    merge_recorded, _ = _recorded_identity_adjudication(
        module,
        source_identities=sources,
        identity_assertions=assertions,
        verdict="same_entity",
        source_identity_groups=(
            tuple(source.source_identity_id for source in sources),
        ),
        confidence=0.97,
        rationale="New corroborating evidence supports one Company.",
        uncertainty="No material uncertainty remains.",
        current_canonical_identities=merge_request.current_canonical_identities,
        current_source_identity_assignments=(
            merge_request.current_source_identity_assignments
        ),
        prior_identity_decisions=merge_request.prior_identity_decisions,
        prior_decision_contexts=merge_request.prior_decision_contexts,
    )

    result = module.create_ephemeral_canonical_identity_resolution_engine(
        adjudicator=_recorded_identity_adjudicator(module, merge_recorded)
    ).resolve(merge_request)

    assert len(result.current_canonical_identities) == 1
    assert result.identity_decisions[0].action.value == "merge"
    assert len(result.identity_decisions[0].input_canonical_identity_ids) == 3
