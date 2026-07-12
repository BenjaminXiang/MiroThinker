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
RED_REASON = "Task 5.3 RED: offline canonical identity resolution is not implemented"
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


def _request(
    module: Any,
    *,
    source_identities: tuple[Any, ...],
    identity_assertions: tuple[Any, ...],
    current_canonical_identities: tuple[Any, ...] = (),
    canonical_identity_history: tuple[Any, ...] = (),
    prior_identity_decisions: tuple[Any, ...] = (),
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
        canonical_identity_history=canonical_identity_history,
        prior_identity_decisions=prior_identity_decisions,
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
                current_canonical_identities=(),
                canonical_identity_history=(),
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


@pytest.mark.xfail(strict=True, raises=_MissingTargetModule, reason=RED_REASON)
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
    request = _request(
        module,
        source_identities=(source_url, source_label),
        identity_assertions=(assertion_url, assertion_label),
        current_canonical_identities=(canonical_url, canonical_label),
        prior_identity_decisions=(prior_url, prior_label),
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
        canonical_identity_history=tuple(reversed(request.canonical_identity_history)),
        prior_identity_decisions=tuple(reversed(request.prior_identity_decisions)),
    )
    assert engine.resolve(reversed_request) == result


@pytest.mark.xfail(strict=True, raises=_MissingTargetModule, reason=RED_REASON)
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


@pytest.mark.xfail(strict=True, raises=_MissingTargetModule, reason=RED_REASON)
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


@pytest.mark.xfail(strict=True, raises=_MissingTargetModule, reason=RED_REASON)
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
    request = _request(
        module,
        source_identities=(source_a, source_b),
        identity_assertions=assertions,
        current_canonical_identities=(wrong_combined,),
        canonical_identity_history=(prior_a, prior_b),
        prior_identity_decisions=(create_a, create_b, mistaken_merge),
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


@pytest.mark.xfail(strict=True, raises=_MissingTargetModule, reason=RED_REASON)
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
    request = _request(
        module,
        source_identities=(official, recovered),
        identity_assertions=assertions,
        current_canonical_identities=(official_current,),
        prior_identity_decisions=(prior_create,),
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
