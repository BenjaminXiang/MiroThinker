from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import (
    CanonicalDecision as SharedCanonicalDecision,
)
from src.data_agents.canonical_v2.contracts import (
    RelationshipAssertion as SharedRelationshipAssertion,
)
from src.data_agents.canonical_v2.contracts import (
    RelationshipDecision as SharedRelationshipDecision,
)
from src.data_agents.canonical_v2.contracts import (
    SourceAssertion as SharedSourceAssertion,
)


RED_REASON = "Task 5.1 RED: Canonical V2 canonical decision engine is not implemented"
RED = pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason=RED_REASON)
TARGET_MODULE = "src.data_agents.canonical_v2.canonical_decision_engine"
NOW = datetime(2026, 7, 11, 22, 40, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s5-r1"
RUN_ID = "decision-build-run-1"


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise


def _policy(module: Any, kind: str, version: str = "v1") -> Any:
    return module.PolicyReference(
        policy_id=f"{kind}-policy",
        policy_version=version,
        policy_kind=kind,
        content_sha256="1" * 64,
        effective_at=NOW - timedelta(days=1),
    )


def _source_identity(
    module: Any,
    source_identity_id: str,
    *,
    source_system: str,
    record_ids: tuple[str, ...] | None = None,
    entity_type: str = "professor",
    state: str = "active",
) -> Any:
    return module.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system=source_system,
        source_key=f"key:{source_identity_id}",
        entity_type=entity_type,
        source_record_ids=record_ids or (f"record:{source_identity_id}",),
        normalized_keys={"source_key": source_identity_id},
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW,
        state=state,
    )


def _canonical_identity(
    module: Any,
    canonical_identity_id: str,
    source_identity_ids: tuple[str, ...],
    *,
    entity_type: str = "professor",
) -> Any:
    return module.CanonicalIdentity(
        canonical_identity_id=canonical_identity_id,
        entity_type=entity_type,
        state="active",
        display_name=f"Display {canonical_identity_id}",
        source_identity_ids=source_identity_ids,
        identity_decision_id=f"identity-decision:{canonical_identity_id}",
        release_id=RELEASE_ID,
    )


def _field_assertion(
    module: Any,
    assertion_id: str,
    source_identity_id: str,
    value: Any,
    *,
    field_path: str = "employment.current_title",
    entity_type: str = "professor",
    observed_at: datetime = NOW - timedelta(hours=1),
) -> Any:
    return module.SourceAssertion(
        assertion_id=assertion_id,
        source_record_id=f"record:{source_identity_id}",
        source_identity_id=source_identity_id,
        subject_entity_type=entity_type,
        field_path=field_path,
        value=value,
        observed_at=observed_at,
        assertion_run_id="assertion-run-1",
    )


def _field_group(
    module: Any,
    assertions: tuple[Any, ...],
    *,
    canonical_identity_id: str = "professor-c1",
    field_path: str = "employment.current_title",
) -> Any:
    return module.FieldAssertionGroup(
        canonical_identity_id=canonical_identity_id,
        field_path=field_path,
        assertions=assertions,
        policy=_policy(module, "field_selection"),
    )


def _batch(
    module: Any,
    *,
    source_identities: tuple[Any, ...],
    canonical_identities: tuple[Any, ...],
    field_groups: tuple[Any, ...] = (),
    relationship_groups: tuple[Any, ...] = (),
) -> Any:
    return module.DecisionBatchRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        decision_method_version="canonical-decision-v1",
        as_of=NOW,
        source_identities=source_identities,
        canonical_identities=canonical_identities,
        field_groups=field_groups,
        relationship_groups=relationship_groups,
    )


def _recorded_adjudicator(module: Any, *responses: Any) -> Any:
    return module.create_recorded_structured_adjudicator(
        provider="recorded",
        model="canonical-judge-fixture-v1",
        prompt_version="canonical-assertion-adjudication-v1",
        schema_version="canonical-adjudication-output-v1",
        responses=responses,
    )


def _recorded_response(
    module: Any,
    input_evidence_ids: tuple[str, ...],
    *,
    state: str,
    selected_assertion_ids: tuple[str, ...],
    conflicting_assertion_ids: tuple[str, ...],
    confidence: float,
    rationale: str,
    uncertainty: str,
    role_bindings: dict[str, str] | None = None,
) -> Any:
    validated_output: dict[str, Any] = {
        "state": state,
        "selected_assertion_ids": list(selected_assertion_ids),
        "conflicting_assertion_ids": list(conflicting_assertion_ids),
        "confidence": confidence,
        "rationale": rationale,
        "uncertainty": uncertainty,
    }
    if role_bindings is not None:
        validated_output["role_bindings"] = role_bindings
    raw_output = json.dumps(
        validated_output,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return module.RecordedAdjudication(
        input_evidence_ids=input_evidence_ids,
        raw_output=raw_output,
        expected_output_sha256=hashlib.sha256(raw_output).hexdigest(),
    )


@RED
def test_competing_field_assertions_are_retained_and_current_value_is_traceable() -> (
    None
):
    module = _module()
    assert module.SourceAssertion is SharedSourceAssertion
    assert module.CanonicalDecision is SharedCanonicalDecision
    sources = (
        _source_identity(module, "official-a", source_system="official_profile"),
        _source_identity(module, "official-b", source_system="official_profile"),
        _source_identity(module, "historical", source_system="historical_recovery"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        tuple(source.source_identity_id for source in sources),
    )
    assertions = (
        _field_assertion(
            module, "title-official-a", "official-a", "Associate Professor"
        ),
        _field_assertion(
            module, "title-official-b", "official-b", "Associate Professor"
        ),
        _field_assertion(module, "title-historical", "historical", "Lecturer"),
    )
    response = _recorded_response(
        module,
        ("title-historical", "title-official-a", "title-official-b"),
        state="selected",
        selected_assertion_ids=("title-official-a", "title-official-b"),
        conflicting_assertion_ids=("title-historical",),
        confidence=0.94,
        rationale="The recorded evidence supports the matching current official title.",
        uncertainty="The historical title remains retained as a conflict.",
    )
    result = module.create_ephemeral_canonical_decision_engine(
        adjudicator=_recorded_adjudicator(module, response)
    ).decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, assertions),),
        )
    )

    assert {item.assertion_id for item in result.field_assertions} == {
        "title-official-a",
        "title-official-b",
        "title-historical",
    }
    assert len(result.field_assertions) == 3
    assert len(result.canonical_decisions) == 1
    decision = result.canonical_decisions[0]
    assert decision.release_id == RELEASE_ID
    assert decision.state.value == "selected"
    assert decision.method.value == "structured_llm"
    assert decision.candidate_assertion_ids == (
        "title-historical",
        "title-official-a",
        "title-official-b",
    )
    assert decision.selected_assertion_ids == (
        "title-official-a",
        "title-official-b",
    )
    assert decision.conflicting_assertion_ids == ("title-historical",)
    assert set(decision.selected_assertion_ids).isdisjoint(
        decision.conflicting_assertion_ids
    )
    assert len(result.current_fields) == 1
    current = result.current_fields[0]
    assert current.release_id == RELEASE_ID
    assert current.canonical_identity_id == "professor-c1"
    assert current.field_path == "employment.current_title"
    assert current.value == "Associate Professor"
    assert current.decision_id == decision.decision_id
    assert current.supporting_assertion_ids == decision.selected_assertion_ids
    assert current.conflicting_assertion_ids == decision.conflicting_assertion_ids


@RED
def test_deterministic_constraints_filter_llm_candidates_but_retain_evidence() -> None:
    module = _module()
    sources = (
        _source_identity(module, "valid-a", source_system="source_a"),
        _source_identity(module, "valid-b", source_system="source_b"),
        _source_identity(
            module,
            "rejected-source",
            source_system="rejected_source",
            state="rejected",
        ),
        _source_identity(module, "foreign", source_system="source_c"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        ("valid-a", "valid-b", "rejected-source"),
    )
    assertions = (
        _field_assertion(module, "valid-a-title", "valid-a", "Professor"),
        _field_assertion(module, "valid-b-title", "valid-b", "Chair Professor"),
        _field_assertion(module, "rejected-source-title", "rejected-source", "Dean"),
        _field_assertion(module, "wrong-identity-title", "foreign", "Lecturer"),
        _field_assertion(
            module,
            "future-title",
            "valid-a",
            "Future title",
            observed_at=NOW + timedelta(seconds=1),
        ),
        _field_assertion(
            module,
            "wrong-field",
            "valid-a",
            "Shenzhen",
            field_path="affiliation.city",
        ),
        _field_assertion(
            module,
            "wrong-entity",
            "valid-a",
            "Company title",
            entity_type="company",
        ),
    )
    response = _recorded_response(
        module,
        ("valid-a-title", "valid-b-title"),
        state="selected",
        selected_assertion_ids=("valid-b-title",),
        conflicting_assertion_ids=("valid-a-title",),
        confidence=0.82,
        rationale="Both sources survive hard constraints; the recorded evidence favors B.",
        uncertainty="Source A remains a material conflict.",
    )
    engine = module.create_ephemeral_canonical_decision_engine(
        adjudicator=_recorded_adjudicator(module, response)
    )
    result = engine.decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, assertions),),
        )
    )

    assert {item.assertion_id for item in result.field_assertions} == {
        assertion.assertion_id for assertion in assertions
    }
    decision = result.canonical_decisions[0]
    assert decision.candidate_assertion_ids == ("valid-a-title", "valid-b-title")
    assert decision.llm_trace.input_evidence_ids == (
        "valid-a-title",
        "valid-b-title",
    )
    rejected = {
        outcome.assertion_id: outcome
        for outcome in result.constraint_outcomes
        if not outcome.admitted
    }
    assert set(rejected) == {
        "rejected-source-title",
        "wrong-identity-title",
        "future-title",
        "wrong-field",
        "wrong-entity",
    }
    assert rejected["rejected-source-title"].reason_codes == (
        "source_identity_rejected",
    )
    assert rejected["wrong-identity-title"].reason_codes == ("identity_mismatch",)
    assert rejected["future-title"].reason_codes == ("observed_after_build",)
    assert rejected["wrong-field"].reason_codes == ("field_mismatch",)
    assert rejected["wrong-entity"].reason_codes == ("entity_type_mismatch",)
    assert all(outcome.policy_version == "v1" for outcome in rejected.values())


@RED
def test_structured_llm_decision_is_versioned_and_order_independent() -> None:
    module = _module()
    sources = (
        _source_identity(module, "source-a", source_system="peer_source"),
        _source_identity(module, "source-b", source_system="peer_source"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        ("source-a", "source-b"),
    )
    left = _field_assertion(module, "ambiguous-a", "source-a", "Professor")
    right = _field_assertion(module, "ambiguous-b", "source-b", "Chair Professor")
    validated_output = {
        "state": "selected",
        "selected_assertion_ids": ["ambiguous-b"],
        "conflicting_assertion_ids": ["ambiguous-a"],
        "confidence": 0.78,
        "rationale": "The recorded public evidence supports the more specific title.",
        "uncertainty": "The other source has no explicit end date.",
    }
    raw_output = json.dumps(
        validated_output,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    expected_output_sha256 = hashlib.sha256(raw_output).hexdigest()

    def request(assertions: tuple[Any, ...]) -> Any:
        return _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, assertions),),
        )

    def decide(assertions: tuple[Any, ...]) -> Any:
        response = module.RecordedAdjudication(
            input_evidence_ids=("ambiguous-a", "ambiguous-b"),
            raw_output=raw_output,
            expected_output_sha256=expected_output_sha256,
        )
        engine = module.create_ephemeral_canonical_decision_engine(
            adjudicator=_recorded_adjudicator(module, response)
        )
        return engine.decide(request(assertions))

    first = decide((left, right))
    reordered = decide((right, left))
    decision = first.canonical_decisions[0]
    trace = decision.llm_trace

    assert decision.release_id == RELEASE_ID
    assert decision.decision_run_id == RUN_ID
    assert decision.policy.policy_version == "v1"
    assert decision.method.value == "structured_llm"
    assert decision.method_version == "canonical-decision-v1"
    assert decision.confidence == 0.78
    assert decision.rationale == validated_output["rationale"]
    assert trace.provider == "recorded"
    assert trace.model == "canonical-judge-fixture-v1"
    assert trace.prompt_version == "canonical-assertion-adjudication-v1"
    assert trace.schema_version == "canonical-adjudication-output-v1"
    assert trace.input_evidence_ids == ("ambiguous-a", "ambiguous-b")
    assert trace.output_sha256 == expected_output_sha256
    assert trace.validated_output == validated_output
    assert decision.model_dump(mode="json") == reordered.canonical_decisions[
        0
    ].model_dump(mode="json")
    assert first.current_fields == reordered.current_fields
    assert first.content_sha256 == reordered.content_sha256

    mismatched_response = module.RecordedAdjudication(
        input_evidence_ids=("ambiguous-a", "ambiguous-b"),
        raw_output=raw_output,
        expected_output_sha256="0" * 64,
    )
    with pytest.raises(module.AdjudicationIntegrityError, match="output hash"):
        module.create_ephemeral_canonical_decision_engine(
            adjudicator=_recorded_adjudicator(module, mismatched_response)
        ).decide(request((left, right)))


@RED
def test_materially_ambiguous_field_remains_unresolved_without_current_fact() -> None:
    module = _module()
    sources = (
        _source_identity(module, "source-a", source_system="peer_source"),
        _source_identity(module, "source-b", source_system="peer_source"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        ("source-a", "source-b"),
    )
    assertions = (
        _field_assertion(module, "conflict-a", "source-a", "Professor"),
        _field_assertion(module, "conflict-b", "source-b", "Chair Professor"),
    )
    response = _recorded_response(
        module,
        ("conflict-a", "conflict-b"),
        state="unresolved",
        selected_assertion_ids=(),
        conflicting_assertion_ids=("conflict-a", "conflict-b"),
        confidence=0.41,
        rationale="Neither source establishes which title is current.",
        uncertainty="Both values remain materially plausible.",
    )
    result = module.create_ephemeral_canonical_decision_engine(
        adjudicator=_recorded_adjudicator(module, response)
    ).decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, assertions),),
        )
    )

    decision = result.canonical_decisions[0]
    assert decision.state.value == "unresolved"
    assert decision.selected_assertion_ids == ()
    assert decision.conflicting_assertion_ids == ("conflict-a", "conflict-b")
    assert result.current_fields == ()
    assert len(result.unresolved_conflicts) == 1
    conflict = result.unresolved_conflicts[0]
    assert conflict.release_id == RELEASE_ID
    assert conflict.subject_id == "professor-c1"
    assert conflict.path == "employment.current_title"
    assert conflict.assertion_ids == decision.conflicting_assertion_ids
    assert {item.assertion_id for item in result.field_assertions} == {
        "conflict-a",
        "conflict-b",
    }


@RED
def test_relationship_assertions_follow_retention_and_current_selection_rules() -> None:
    module = _module()
    assert module.RelationshipAssertion is SharedRelationshipAssertion
    assert module.RelationshipDecision is SharedRelationshipDecision
    relation_record = "record:professor-company"
    sources = (
        _source_identity(
            module,
            "professor-source",
            source_system="official_profile",
            record_ids=(relation_record,),
        ),
        _source_identity(
            module,
            "company-source",
            source_system="company_registry",
            record_ids=(relation_record,),
            entity_type="company",
        ),
    )
    canonical_professor = _canonical_identity(
        module,
        "professor-c1",
        ("professor-source",),
    )
    canonical_company = _canonical_identity(
        module,
        "company-c1",
        ("company-source",),
        entity_type="company",
    )
    endpoints = {
        "source_endpoint": module.IdentityReference(
            identity_id="professor-source",
            identity_space="source",
            entity_type="professor",
        ),
        "target_endpoint": module.IdentityReference(
            identity_id="company-source",
            identity_space="source",
            entity_type="company",
        ),
    }
    assertions = tuple(
        module.RelationshipAssertion.model_validate(
            {
                "assertion_id": assertion_id,
                "relationship_type_id": "professor_company_role",
                "relationship_type_version": "v1",
                "source_record_id": relation_record,
                "attributes": {"role": role},
                "observed_at": observed_at,
                "assertion_run_id": "relationship-assertion-run-1",
                **endpoints,
            }
        )
        for assertion_id, role, observed_at in (
            ("relation-founder", "founder", NOW - timedelta(hours=2)),
            ("relation-advisor", "advisor", NOW - timedelta(hours=1)),
        )
    )
    unresolved_assertions = tuple(
        module.RelationshipAssertion.model_validate(
            {
                "assertion_id": assertion_id,
                "relationship_type_id": "professor_company_affiliation",
                "relationship_type_version": "v1",
                "source_record_id": relation_record,
                "attributes": {"role": role},
                "observed_at": NOW - timedelta(minutes=30),
                "assertion_run_id": "relationship-assertion-run-1",
                **endpoints,
            }
        )
        for assertion_id, role in (
            ("relation-employee", "employee"),
            ("relation-contractor", "contractor"),
        )
    )
    accepted_response = _recorded_response(
        module,
        ("relation-advisor", "relation-founder"),
        state="selected",
        selected_assertion_ids=("relation-founder",),
        conflicting_assertion_ids=("relation-advisor",),
        confidence=0.91,
        rationale="The recorded evidence supports the founder role.",
        uncertainty="The advisor assertion remains retained as a conflict.",
        role_bindings={"source": "founder"},
    )
    unresolved_response = _recorded_response(
        module,
        ("relation-contractor", "relation-employee"),
        state="unresolved",
        selected_assertion_ids=(),
        conflicting_assertion_ids=("relation-contractor", "relation-employee"),
        confidence=0.44,
        rationale="The recorded evidence cannot distinguish employment from contracting.",
        uncertainty="Both relationship roles remain materially plausible.",
    )
    accepted_group = module.RelationshipAssertionGroup(
        canonical_relationship_id="canonical-relation-1",
        relationship_type_id="professor_company_role",
        relationship_type_version="v1",
        source_canonical_identity_id="professor-c1",
        target_canonical_identity_id="company-c1",
        assertions=assertions,
        policy=_policy(module, "relationship"),
    )
    unresolved_group = module.RelationshipAssertionGroup(
        canonical_relationship_id="canonical-relation-2",
        relationship_type_id="professor_company_affiliation",
        relationship_type_version="v1",
        source_canonical_identity_id="professor-c1",
        target_canonical_identity_id="company-c1",
        assertions=unresolved_assertions,
        policy=_policy(module, "relationship"),
    )
    result = module.create_ephemeral_canonical_decision_engine(
        adjudicator=_recorded_adjudicator(
            module,
            accepted_response,
            unresolved_response,
        )
    ).decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical_professor, canonical_company),
            relationship_groups=(accepted_group, unresolved_group),
        )
    )

    assert {item.assertion_id for item in result.relationship_assertions} == {
        "relation-founder",
        "relation-advisor",
        "relation-employee",
        "relation-contractor",
    }
    decisions = {
        item.canonical_relationship_id: item for item in result.relationship_decisions
    }
    decision = decisions["canonical-relation-1"]
    assert decision.release_id == RELEASE_ID
    assert decision.relationship_type_version == "v1"
    assert decision.state.value == "accepted"
    assert decision.selected_assertion_ids == ("relation-founder",)
    assert decision.conflicting_assertion_ids == ("relation-advisor",)
    assert set(decision.selected_assertion_ids).isdisjoint(
        decision.conflicting_assertion_ids
    )
    unresolved = decisions["canonical-relation-2"]
    assert unresolved.state.value == "unresolved"
    assert unresolved.selected_assertion_ids == ()
    assert unresolved.conflicting_assertion_ids == (
        "relation-contractor",
        "relation-employee",
    )
    assert len(result.current_relationships) == 1
    current = result.current_relationships[0]
    assert current.release_id == RELEASE_ID
    assert current.canonical_relationship_id == "canonical-relation-1"
    assert current.relationship_type_id == "professor_company_role"
    assert current.relationship_type_version == "v1"
    assert current.source_canonical_identity_id == "professor-c1"
    assert current.target_canonical_identity_id == "company-c1"
    assert current.role_bindings == {"source": "founder"}
    assert current.decision_id == decision.decision_id
    assert current.supporting_assertion_ids == ("relation-founder",)
    assert current.conflicting_assertion_ids == ("relation-advisor",)
    assert {conflict.subject_id for conflict in result.unresolved_conflicts} == {
        "canonical-relation-2"
    }
    assert not hasattr(current, "professor_projection")
    assert not hasattr(current, "company_projection")
