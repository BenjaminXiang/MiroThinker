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
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> Any:
    return module.SourceAssertion(
        assertion_id=assertion_id,
        source_record_id=f"record:{source_identity_id}",
        source_identity_id=source_identity_id,
        subject_entity_type=entity_type,
        field_path=field_path,
        value=value,
        observed_at=observed_at,
        valid_from=valid_from,
        valid_to=valid_to,
        assertion_run_id="assertion-run-1",
    )


def _field_group(
    module: Any,
    assertions: tuple[Any, ...],
    *,
    canonical_identity_id: str = "professor-c1",
    field_path: str = "employment.current_title",
    transition: str = "evaluate",
) -> Any:
    return module.FieldAssertionGroup(
        canonical_identity_id=canonical_identity_id,
        field_path=field_path,
        assertions=assertions,
        policy=_policy(module, "field_selection"),
        transition=transition,
    )


def _batch(
    module: Any,
    *,
    source_identities: tuple[Any, ...],
    canonical_identities: tuple[Any, ...],
    field_groups: tuple[Any, ...] = (),
    relationship_groups: tuple[Any, ...] = (),
    as_of: datetime = NOW,
    release_id: str = RELEASE_ID,
    decision_run_id: str = RUN_ID,
    human_review_resolutions: tuple[Any, ...] = (),
    previous_history: Any | None = None,
) -> Any:
    return module.DecisionBatchRequest(
        release_id=release_id,
        decision_run_id=decision_run_id,
        decision_method_version="canonical-decision-v1",
        as_of=as_of,
        source_identities=source_identities,
        canonical_identities=canonical_identities,
        field_groups=field_groups,
        relationship_groups=relationship_groups,
        human_review_resolutions=human_review_resolutions,
        previous_history=previous_history,
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
    assertions: tuple[Any, ...],
    *,
    decision_kind: str,
    subject_id: str,
    path: str,
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
    ordered_assertions = tuple(
        sorted(assertions, key=lambda assertion: assertion.assertion_id)
    )
    return module.RecordedAdjudication(
        input_evidence_ids=tuple(
            assertion.assertion_id for assertion in ordered_assertions
        ),
        input_evidence_sha256=module.canonical_adjudication_input_sha256(
            decision_kind=decision_kind,
            subject_id=subject_id,
            path=path,
            assertions=ordered_assertions,
        ),
        raw_output=raw_output,
        expected_output_sha256=hashlib.sha256(raw_output).hexdigest(),
    )


def _rehash_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _rebind_changed_group(
    payload: dict[str, Any],
    *,
    decision_collection: str,
    assertion_collection: str,
    decision_index: int = 0,
) -> None:
    decision = payload[decision_collection][decision_index]
    old_decision_id = decision["decision_id"]
    manifest = next(
        item
        for item in payload["decision_group_manifests"]
        if item["decision_id"] == old_decision_id
    )
    assertions_by_id = {
        assertion["assertion_id"]: assertion
        for assertion in payload[assertion_collection]
    }
    manifest_hash = hashlib.sha256(
        json.dumps(
            {
                "group_key": manifest["group_key"],
                "assertions": [
                    assertions_by_id[assertion_id]
                    for assertion_id in manifest["assertion_ids"]
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    new_decision_id = old_decision_id.replace(
        manifest["content_sha256"],
        manifest_hash,
        1,
    )
    assert new_decision_id != old_decision_id
    decision["decision_id"] = new_decision_id
    manifest["decision_id"] = new_decision_id
    manifest["content_sha256"] = manifest_hash
    for collection in (
        "constraint_outcomes",
        "current_fields",
        "current_relationships",
        "unresolved_conflicts",
    ):
        for item in payload[collection]:
            if item["decision_id"] == old_decision_id:
                item["decision_id"] = new_decision_id


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
        assertions,
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
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

    invented_value = result.model_dump(mode="json")
    invented_value["current_fields"][0]["value"] = "Invented title"
    with pytest.raises(ValueError, match="current.*value|selected.*value"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(invented_value)
        )

    invented_support = result.model_dump(mode="json")
    invented_support["current_fields"][0]["supporting_assertion_ids"] = [
        "title-official-a"
    ]
    with pytest.raises(ValueError, match="current.*support|support.*decision"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(invented_support)
        )

    trace_selection_mismatch = result.model_dump(mode="json")
    trace_selection_mismatch["canonical_decisions"][0]["selected_assertion_ids"] = [
        "title-historical"
    ]
    trace_selection_mismatch["canonical_decisions"][0]["conflicting_assertion_ids"] = [
        "title-official-a",
        "title-official-b",
    ]
    trace_selection_mismatch["current_fields"][0]["value"] = "Lecturer"
    trace_selection_mismatch["current_fields"][0]["supporting_assertion_ids"] = [
        "title-historical"
    ]
    trace_selection_mismatch["current_fields"][0]["conflicting_assertion_ids"] = [
        "title-official-a",
        "title-official-b",
    ]
    with pytest.raises(ValueError, match="trace.*selected|structured.*selected"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(trace_selection_mismatch)
        )

    trace_metadata_tamper = result.model_dump(mode="json")
    trace_metadata_tamper["canonical_decisions"][0]["llm_trace"]["prompt_version"] = (
        "tampered-semantic-neutral-prompt"
    )
    with pytest.raises(ValueError, match="decision.*seed|decision.*ID|seed.*hash"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(trace_metadata_tamper)
        )


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
        _field_assertion(
            module,
            "rejected-source-title",
            "rejected-source",
            "Dean",
            field_path="affiliation.city",
        ),
        _field_assertion(
            module,
            "wrong-identity-title",
            "foreign",
            "Lecturer",
            field_path="affiliation.city",
        ),
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
            field_path="affiliation.city",
            entity_type="company",
        ),
    )
    response = _recorded_response(
        module,
        assertions[:2],
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
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

    wrong_reason = result.model_dump(mode="json")
    for outcome in wrong_reason["constraint_outcomes"]:
        if outcome["assertion_id"] == "rejected-source-title":
            outcome["reason_codes"] = ["identity_mismatch"]
            break
    with pytest.raises(ValueError, match="deterministic.*outcome|outcome.*constraint"):
        module.DecisionBatchResult.model_validate(_rehash_result_payload(wrong_reason))


def test_field_assertion_cannot_be_rebound_to_wrong_canonical_owner() -> None:
    module = _module()
    professor_source = _source_identity(
        module,
        "professor-source",
        source_system="professor-source",
    )
    company_source = _source_identity(
        module,
        "company-source",
        source_system="company-source",
        entity_type="company",
    )
    assertion = _field_assertion(
        module,
        "owned-title",
        "professor-source",
        "Professor",
    )
    result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=(professor_source, company_source),
            canonical_identities=(
                _canonical_identity(module, "professor-c1", ("professor-source",)),
                _canonical_identity(
                    module,
                    "company-c1",
                    ("company-source",),
                    entity_type="company",
                ),
            ),
            field_groups=(_field_group(module, (assertion,)),),
        )
    )
    wrong_owner = result.model_dump(mode="json")
    wrong_owner["field_assertions"][0]["source_identity_id"] = "company-source"
    wrong_owner["field_assertions"][0]["source_record_id"] = "record:company-source"
    _rebind_changed_group(
        wrong_owner,
        decision_collection="canonical_decisions",
        assertion_collection="field_assertions",
    )

    with pytest.raises(ValueError, match="identity.*context|deterministic.*constraint"):
        module.DecisionBatchResult.model_validate(_rehash_result_payload(wrong_owner))


def test_decision_id_binds_complete_assertion_and_constraint_inputs() -> None:
    module = _module()
    source = _source_identity(module, "source-a", source_system="source-a")
    canonical = _canonical_identity(module, "professor-c1", ("source-a",))
    assertion = _field_assertion(module, "stable-id", "source-a", "Professor")

    def decide(assertion_value: Any, source_value: Any = source) -> Any:
        return module.create_ephemeral_canonical_decision_engine().decide(
            _batch(
                module,
                source_identities=(source_value,),
                canonical_identities=(canonical,),
                field_groups=(_field_group(module, (assertion_value,)),),
            )
        )

    baseline = decide(assertion).canonical_decisions[0].decision_id
    changed_value = (
        decide(assertion.model_copy(update={"value": "Chair Professor"}))
        .canonical_decisions[0]
        .decision_id
    )
    changed_provenance = (
        decide(
            assertion,
            source.model_copy(update={"source_system": "changed-source"}),
        )
        .canonical_decisions[0]
        .decision_id
    )

    assert len({baseline, changed_value, changed_provenance}) == 3


def test_rejected_outcome_remains_bound_to_its_owning_group() -> None:
    module = _module()
    sources = (
        _source_identity(module, "active-source", source_system="active"),
        _source_identity(
            module,
            "rejected-source",
            source_system="rejected",
            state="rejected",
        ),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        ("active-source", "rejected-source"),
    )
    title_assertions = (
        _field_assertion(module, "title-active", "active-source", "Professor"),
        _field_assertion(module, "title-rejected", "rejected-source", "Dean"),
    )
    city_assertions = (
        _field_assertion(
            module,
            "city-active",
            "active-source",
            "Shenzhen",
            field_path="affiliation.city",
        ),
        _field_assertion(
            module,
            "city-rejected",
            "rejected-source",
            "Hong Kong",
            field_path="affiliation.city",
        ),
    )
    result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(
                _field_group(module, title_assertions),
                _field_group(
                    module,
                    city_assertions,
                    field_path="affiliation.city",
                ),
            ),
        )
    )
    decisions = {
        decision.field_path: decision for decision in result.canonical_decisions
    }
    outcomes = {outcome.assertion_id: outcome for outcome in result.constraint_outcomes}
    manifests = {
        manifest.decision_id: manifest for manifest in result.decision_group_manifests
    }
    title_decision = decisions["employment.current_title"]
    title_manifest = manifests[title_decision.decision_id]
    assertion_by_id = {
        assertion.assertion_id: assertion for assertion in result.field_assertions
    }
    expected_manifest_hash = hashlib.sha256(
        json.dumps(
            {
                "group_key": title_manifest.group_key,
                "assertions": [
                    assertion_by_id[assertion_id].model_dump(mode="json")
                    for assertion_id in title_manifest.assertion_ids
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    assert outcomes["title-rejected"].group_key != outcomes["city-rejected"].group_key
    assert title_manifest.assertion_ids == ("title-active", "title-rejected")
    assert title_manifest.content_sha256 == expected_manifest_hash
    assert (
        f":manifest-sha256:{title_manifest.content_sha256}:seed-sha256:"
        in title_decision.decision_id
    )
    assert {
        assertion_id
        for manifest in result.decision_group_manifests
        for assertion_id in manifest.assertion_ids
    } == {assertion.assertion_id for assertion in result.field_assertions}

    relinked = result.model_dump(mode="json")
    for outcome in relinked["constraint_outcomes"]:
        if outcome["assertion_id"] == "title-rejected":
            outcome["decision_id"] = decisions["affiliation.city"].decision_id
            outcome["group_key"] = outcomes["city-rejected"].group_key
            break
    with pytest.raises(ValueError, match="manifest.*assertion|assertion.*manifest"):
        module.DecisionBatchResult.model_validate(_rehash_result_payload(relinked))

    partition_tamper = result.model_dump(mode="json")
    for manifest in partition_tamper["decision_group_manifests"]:
        if manifest["decision_id"] == title_decision.decision_id:
            manifest["assertion_ids"] = ["title-active"]
            break
    with pytest.raises(ValueError, match="manifest.*partition|partition.*manifest"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(partition_tamper)
        )

    content_tamper = result.model_dump(mode="json")
    for manifest in content_tamper["decision_group_manifests"]:
        if manifest["decision_id"] == title_decision.decision_id:
            manifest["content_sha256"] = "0" * 64
            break
    with pytest.raises(ValueError, match="decision.*manifest|manifest.*content"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(content_tamper)
        )


def test_adjudication_input_hash_rejects_duplicate_and_wrong_assertion_kind() -> None:
    module = _module()
    left = _field_assertion(module, "candidate-a", "source-a", "Professor")
    right = _field_assertion(module, "candidate-b", "source-b", "Chair Professor")

    with pytest.raises(module.DecisionBatchIntegrityError, match="duplicate"):
        module.canonical_adjudication_input_sha256(
            decision_kind="field",
            subject_id="professor-c1",
            path="employment.current_title",
            assertions=(left, left),
        )
    with pytest.raises(module.DecisionBatchIntegrityError, match="kind|relationship"):
        module.canonical_adjudication_input_sha256(
            decision_kind="relationship",
            subject_id="canonical-relation-1",
            path="professor_company_role",
            assertions=(left, right),
        )


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
    input_evidence_sha256 = module.canonical_adjudication_input_sha256(
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
        assertions=(left, right),
    )

    def request(assertions: tuple[Any, ...]) -> Any:
        return _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, assertions),),
        )

    response = module.RecordedAdjudication(
        input_evidence_ids=("ambiguous-a", "ambiguous-b"),
        input_evidence_sha256=input_evidence_sha256,
        raw_output=raw_output,
        expected_output_sha256=expected_output_sha256,
    )
    engine = module.create_ephemeral_canonical_decision_engine(
        adjudicator=_recorded_adjudicator(module, response)
    )

    def decide(assertions: tuple[Any, ...]) -> Any:
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
    assert first.canonical_decisions == reordered.canonical_decisions
    assert first.relationship_decisions == reordered.relationship_decisions
    assert first.current_fields == reordered.current_fields
    assert first.current_relationships == reordered.current_relationships
    assert first.constraint_outcomes == reordered.constraint_outcomes
    assert first.unresolved_conflicts == reordered.unresolved_conflicts
    assert first.content_sha256 == reordered.content_sha256

    with pytest.raises(
        module.AdjudicationIntegrityError,
        match="content|hash|bound|candidate",
    ):
        decide(
            (
                left,
                right.model_copy(update={"value": "Distinguished Professor"}),
            )
        )

    mismatched_response = module.RecordedAdjudication(
        input_evidence_ids=("ambiguous-a", "ambiguous-b"),
        input_evidence_sha256=input_evidence_sha256,
        raw_output=raw_output,
        expected_output_sha256="0" * 64,
    )
    with pytest.raises(module.AdjudicationIntegrityError, match="output hash"):
        module.create_ephemeral_canonical_decision_engine(
            adjudicator=_recorded_adjudicator(module, mismatched_response)
        ).decide(request((left, right)))


def test_recorded_adjudicator_rejects_duplicate_candidate_response_keys() -> None:
    module = _module()
    assertions = (
        _field_assertion(module, "candidate-a", "source-a", "Professor"),
        _field_assertion(module, "candidate-b", "source-b", "Chair Professor"),
    )
    response = _recorded_response(
        module,
        assertions,
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
        state="selected",
        selected_assertion_ids=("candidate-a",),
        conflicting_assertion_ids=("candidate-b",),
        confidence=0.8,
        rationale="One exact response may bind one ordered candidate key.",
        uncertainty="The other candidate remains retained as a conflict.",
    )

    with pytest.raises(module.AdjudicationIntegrityError, match="ambiguous|duplicate"):
        _recorded_adjudicator(module, response, response)


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
        assertions,
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
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
    assert len(result.review_cases) == 1
    review_case = result.review_cases[0]
    assert review_case.family.value == "field"
    assert review_case.release_id == RELEASE_ID
    assert review_case.decision_run_id == RUN_ID
    assert review_case.subject_id == "professor-c1"
    assert review_case.path == "employment.current_title"
    assert review_case.originating_record_id == decision.decision_id
    assert review_case.candidate_evidence_ids == ("conflict-a", "conflict-b")
    assert review_case.conflicting_evidence_ids == ("conflict-a", "conflict-b")
    assert review_case.source_identity_ids == ()
    assert review_case.confidence == 0.41
    assert review_case.uncertainty == "Both values remain materially plausible."
    assert review_case.trace_content_sha256 == decision.llm_trace.output_sha256
    assert (
        review_case.review_case_id == f"review-case:sha256:{review_case.content_sha256}"
    )
    assert {item.assertion_id for item in result.field_assertions} == {
        "conflict-a",
        "conflict-b",
    }

    tampered = result.model_dump(mode="json")
    tampered["review_cases"][0]["subject_id"] = "company-cross-wire"
    with pytest.raises(ValueError, match="review case|review.*subject|content hash"):
        module.DecisionBatchResult.model_validate(_rehash_result_payload(tampered))

    resolution = module.create_human_review_resolution(
        review_case=review_case,
        outcome="selected",
        selected_evidence_ids=("conflict-b",),
        reviewer_id="reviewer:canonical-operator-1",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="The official appointment evidence supports Chair Professor.",
        confidence=0.99,
    )
    reviewed_release = "candidate-s5-r2"
    reviewed_result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            release_id=reviewed_release,
            decision_run_id="decision-build-run-2",
            as_of=NOW + timedelta(hours=1),
            source_identities=sources,
            canonical_identities=(
                canonical.model_copy(update={"release_id": reviewed_release}),
            ),
            field_groups=(_field_group(module, assertions),),
            human_review_resolutions=(resolution,),
            previous_history=module.project_decision_history((result,), as_of=NOW),
        )
    )

    reviewed = reviewed_result.canonical_decisions[0]
    assert reviewed.release_id == reviewed_release
    assert reviewed.state.value == "selected"
    assert reviewed.method.value == "human_review"
    assert reviewed.selected_assertion_ids == ("conflict-b",)
    assert reviewed.conflicting_assertion_ids == ("conflict-a",)
    assert reviewed.supersedes_decision_id == decision.decision_id
    assert reviewed.human_review_resolution == resolution
    assert reviewed.llm_trace is None
    assert reviewed_result.review_cases == ()
    assert reviewed_result.current_fields[0].value == "Chair Professor"
    assert result.canonical_decisions[0] == decision
    assert result.review_cases == (review_case,)

    history = module.project_decision_history(
        (result, reviewed_result), as_of=NOW + timedelta(hours=1)
    )
    assert history.release_lineage == (RELEASE_ID, reviewed_release)
    assert history.canonical_decision_history == (decision, reviewed)
    assert history.relationship_decision_history == ()
    assert history.review_case_history == (review_case,)
    assert history.open_review_cases == ()
    assert history.current_fields == reviewed_result.current_fields
    assert history.current_relationships == ()
    assert history.content_sha256 == module.decision_history_projection_sha256(history)

    branched_release = "candidate-s5-r3-branch"
    with pytest.raises(ValueError, match="open case|previous history|human review"):
        _batch(
            module,
            release_id=branched_release,
            decision_run_id="decision-build-run-3-branch",
            as_of=NOW + timedelta(hours=2),
            source_identities=sources,
            canonical_identities=(
                canonical.model_copy(update={"release_id": branched_release}),
            ),
            field_groups=(_field_group(module, assertions),),
            human_review_resolutions=(resolution,),
            previous_history=history,
        )


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
            record_ids=("record:company-source",),
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
        assertions,
        decision_kind="relationship",
        subject_id="canonical-relation-1",
        path="professor_company_role",
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
        unresolved_assertions,
        decision_kind="relationship",
        subject_id="canonical-relation-2",
        path="professor_company_affiliation",
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
            unresolved_response,
            accepted_response,
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
    outcomes = {item.assertion_id: item for item in result.constraint_outcomes}
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
    assert len(result.review_cases) == 1
    relationship_case = result.review_cases[0]
    assert relationship_case.family.value == "relationship"
    assert relationship_case.subject_id == "canonical-relation-2"
    assert relationship_case.path == "professor_company_affiliation"
    assert relationship_case.originating_record_id == unresolved.decision_id
    assert relationship_case.candidate_evidence_ids == (
        "relation-contractor",
        "relation-employee",
    )
    assert relationship_case.conflicting_evidence_ids == (
        "relation-contractor",
        "relation-employee",
    )
    assert relationship_case.trace_content_sha256 == (
        unresolved.llm_trace.output_sha256
    )

    relationship_resolution = module.create_human_review_resolution(
        review_case=relationship_case,
        outcome="accepted",
        selected_evidence_ids=("relation-employee",),
        role_bindings={"source": "employee"},
        reviewer_id="reviewer:canonical-operator-2",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="The employment record establishes an employee relationship.",
        confidence=0.98,
    )
    reviewed_release = "candidate-s5-r2"
    reviewed_relationship_result = (
        module.create_ephemeral_canonical_decision_engine().decide(
            _batch(
                module,
                release_id=reviewed_release,
                decision_run_id="decision-build-run-2",
                as_of=NOW + timedelta(hours=1),
                source_identities=sources,
                canonical_identities=(
                    canonical_professor.model_copy(
                        update={"release_id": reviewed_release}
                    ),
                    canonical_company.model_copy(
                        update={"release_id": reviewed_release}
                    ),
                ),
                relationship_groups=(unresolved_group,),
                human_review_resolutions=(relationship_resolution,),
                previous_history=module.project_decision_history((result,), as_of=NOW),
            )
        )
    )
    reviewed_relationship = reviewed_relationship_result.relationship_decisions[0]
    assert reviewed_relationship.state.value == "accepted"
    assert reviewed_relationship.method.value == "human_review"
    assert reviewed_relationship.selected_assertion_ids == ("relation-employee",)
    assert reviewed_relationship.conflicting_assertion_ids == ("relation-contractor",)
    assert reviewed_relationship.role_bindings == {"source": "employee"}
    assert reviewed_relationship.supersedes_decision_id == unresolved.decision_id
    assert reviewed_relationship.human_review_resolution == relationship_resolution
    assert reviewed_relationship_result.review_cases == ()
    assert (
        reviewed_relationship_result.current_relationships[0].decision_id
        == reviewed_relationship.decision_id
    )
    assert not hasattr(current, "professor_projection")
    assert not hasattr(current, "company_projection")

    invented_roles = result.model_dump(mode="json")
    invented_roles["current_relationships"][0]["role_bindings"] = {"source": "advisor"}
    with pytest.raises(ValueError, match="current.*role|role.*decision"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(invented_roles)
        )

    trace_role_mismatch = result.model_dump(mode="json")
    trace_role_mismatch["relationship_decisions"][0]["role_bindings"] = {
        "source": "advisor"
    }
    trace_role_mismatch["current_relationships"][0]["role_bindings"] = {
        "source": "advisor"
    }
    with pytest.raises(ValueError, match="trace.*role|structured.*role"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(trace_role_mismatch)
        )

    relinked_outcome = result.model_dump(mode="json")
    unresolved_decision_id = unresolved.decision_id
    for outcome in relinked_outcome["constraint_outcomes"]:
        if outcome["assertion_id"] == "relation-founder":
            outcome["decision_id"] = unresolved_decision_id
            outcome["group_key"] = outcomes["relation-employee"].group_key
            break
    with pytest.raises(ValueError, match="manifest.*assertion|assertion.*manifest"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(relinked_outcome)
        )

    wrong_endpoint = result.model_dump(mode="json")
    for assertion in wrong_endpoint["relationship_assertions"]:
        if assertion["assertion_id"] == "relation-founder":
            assertion["source_endpoint"] = {
                "identity_id": "company-source",
                "identity_space": "source",
                "entity_type": "company",
            }
            assertion["target_endpoint"] = {
                "identity_id": "professor-source",
                "identity_space": "source",
                "entity_type": "professor",
            }
            break
    _rebind_changed_group(
        wrong_endpoint,
        decision_collection="relationship_decisions",
        assertion_collection="relationship_assertions",
    )
    with pytest.raises(ValueError, match="identity.*context|deterministic.*constraint"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(wrong_endpoint)
        )

    falsified_conflict = result.model_dump(mode="json")
    falsified_conflict["unresolved_conflicts"][0]["subject_id"] = "canonical-relation-1"
    falsified_conflict["unresolved_conflicts"][0]["path"] = "professor_company_role"
    with pytest.raises(ValueError, match="conflict.*subject|conflict.*path"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(falsified_conflict)
        )


def test_zero_survivor_group_keeps_rejected_evidence_and_an_audit_decision() -> None:
    module = _module()
    sources = (
        _source_identity(
            module,
            "rejected-source",
            source_system="rejected_source",
            state="rejected",
        ),
        _source_identity(module, "foreign-source", source_system="foreign_source"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        ("rejected-source",),
    )
    assertions = (
        _field_assertion(
            module,
            "rejected-source-title",
            "rejected-source",
            "Dean",
        ),
        _field_assertion(
            module,
            "foreign-identity-title",
            "foreign-source",
            "Lecturer",
        ),
    )

    def decide(
        ordered_sources: tuple[Any, ...], ordered_assertions: tuple[Any, ...]
    ) -> Any:
        return module.create_ephemeral_canonical_decision_engine(
            adjudicator=_recorded_adjudicator(module)
        ).decide(
            _batch(
                module,
                source_identities=ordered_sources,
                canonical_identities=(canonical,),
                field_groups=(_field_group(module, ordered_assertions),),
            )
        )

    result = decide(sources, assertions)
    reordered = decide(tuple(reversed(sources)), tuple(reversed(assertions)))

    assert {item.assertion_id for item in result.field_assertions} == {
        item.assertion_id for item in assertions
    }
    assert len(result.field_assertions) == len(assertions)
    assert len(result.canonical_decisions) == 1
    decision = result.canonical_decisions[0]
    assert decision.release_id == RELEASE_ID
    assert decision.canonical_identity_id == "professor-c1"
    assert decision.field_path == "employment.current_title"
    assert decision.state.value == "unresolved"
    assert decision.method.value == "deterministic"
    assert decision.candidate_assertion_ids == ()
    assert decision.selected_assertion_ids == ()
    assert decision.conflicting_assertion_ids == ()
    assert decision.llm_trace is None
    assert result.current_fields == ()
    assert result.review_cases == ()

    outcomes = {outcome.assertion_id: outcome for outcome in result.constraint_outcomes}
    assert set(outcomes) == {
        "rejected-source-title",
        "foreign-identity-title",
    }
    assert all(not outcome.admitted for outcome in outcomes.values())
    assert outcomes["rejected-source-title"].reason_codes == (
        "source_identity_rejected",
    )
    assert outcomes["foreign-identity-title"].reason_codes == ("identity_mismatch",)
    assert {outcome.release_id for outcome in outcomes.values()} == {RELEASE_ID}
    assert {outcome.decision_id for outcome in outcomes.values()} == {
        decision.decision_id
    }
    assert {outcome.policy_version for outcome in outcomes.values()} == {"v1"}
    assert decision.model_dump(mode="json") == reordered.canonical_decisions[
        0
    ].model_dump(mode="json")
    assert result.constraint_outcomes == reordered.constraint_outcomes
    assert result.unresolved_conflicts == reordered.unresolved_conflicts
    assert result.review_cases == reordered.review_cases == ()
    assert result.current_fields == reordered.current_fields == ()
    assert result.current_relationships == reordered.current_relationships == ()
    assert result.content_sha256 == reordered.content_sha256

    duplicate_logical = result.model_dump(mode="json")
    duplicate_decision = dict(duplicate_logical["canonical_decisions"][0])
    duplicate_decision["decision_id"] = "duplicate-logical-decision"
    duplicate_logical["canonical_decisions"].append(duplicate_decision)
    with pytest.raises(
        ValueError,
        match="logical.*field|field.*logical|identity.*path",
    ):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(duplicate_logical)
        )

    wrong_run = result.model_dump(mode="json")
    wrong_run["canonical_decisions"][0]["decision_run_id"] = "wrong-run"
    with pytest.raises(ValueError, match="decision_run_id|batch.*run"):
        module.DecisionBatchResult.model_validate(_rehash_result_payload(wrong_run))

    wrong_as_of = result.model_dump(mode="json")
    wrong_as_of["canonical_decisions"][0]["decided_at"] = (
        NOW + timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ValueError, match="decided_at|as_of"):
        module.DecisionBatchResult.model_validate(_rehash_result_payload(wrong_as_of))


def test_professor_affiliation_transition_keeps_history_and_projects_only_current() -> (
    None
):
    module = _module()
    professor_source = _source_identity(
        module,
        "professor-source-temporal",
        source_system="official_profile",
        record_ids=("record:affiliation-old", "record:affiliation-new"),
    )
    institution_a_source = _source_identity(
        module,
        "institution-a-source",
        source_system="institution_registry",
        entity_type="institution",
    )
    institution_b_source = _source_identity(
        module,
        "institution-b-source",
        source_system="institution_registry",
        entity_type="institution",
    )
    professor = _canonical_identity(
        module,
        "professor-temporal-c1",
        (professor_source.source_identity_id,),
    )
    institution_a = _canonical_identity(
        module,
        "institution-a-c1",
        (institution_a_source.source_identity_id,),
        entity_type="institution",
    )
    institution_b = _canonical_identity(
        module,
        "institution-b-c1",
        (institution_b_source.source_identity_id,),
        entity_type="institution",
    )

    transition = NOW
    old_start = NOW - timedelta(days=3650)
    new_start = transition
    old_assertion = module.RelationshipAssertion(
        assertion_id="affiliation-old-evidence",
        relationship_type_id="professor_affiliated_with_institution",
        relationship_type_version="v1",
        source_record_id="record:affiliation-old",
        source_endpoint=module.IdentityReference(
            identity_id=professor_source.source_identity_id,
            identity_space="source",
            entity_type="professor",
        ),
        target_endpoint=module.IdentityReference(
            identity_id=institution_a_source.source_identity_id,
            identity_space="source",
            entity_type="institution",
        ),
        attributes={"role": "faculty"},
        observed_at=NOW - timedelta(days=30),
        source_event_time=old_start,
        valid_from=old_start,
        valid_to=transition,
        assertion_run_id="temporal-assertion-run-1",
    )
    new_assertion = module.RelationshipAssertion(
        assertion_id="affiliation-new-evidence",
        relationship_type_id="professor_affiliated_with_institution",
        relationship_type_version="v1",
        source_record_id="record:affiliation-new",
        source_endpoint=module.IdentityReference(
            identity_id=professor_source.source_identity_id,
            identity_space="source",
            entity_type="professor",
        ),
        target_endpoint=module.IdentityReference(
            identity_id=institution_b_source.source_identity_id,
            identity_space="source",
            entity_type="institution",
        ),
        attributes={"role": "faculty"},
        observed_at=NOW - timedelta(days=7),
        source_event_time=new_start,
        valid_from=new_start,
        valid_to=None,
        assertion_run_id="temporal-assertion-run-1",
    )

    def relationship_group(
        canonical_relationship_id: str,
        target_canonical_identity_id: str,
        assertion: Any,
    ) -> Any:
        return module.RelationshipAssertionGroup(
            canonical_relationship_id=canonical_relationship_id,
            relationship_type_id=assertion.relationship_type_id,
            relationship_type_version=assertion.relationship_type_version,
            source_canonical_identity_id=professor.canonical_identity_id,
            target_canonical_identity_id=target_canonical_identity_id,
            assertions=(assertion,),
            policy=_policy(module, "relationship", "temporal-v1"),
        )

    request = _batch(
        module,
        source_identities=(
            institution_b_source,
            professor_source,
            institution_a_source,
        ),
        canonical_identities=(institution_b, professor, institution_a),
        relationship_groups=(
            relationship_group(
                "affiliation-episode-b",
                institution_b.canonical_identity_id,
                new_assertion,
            ),
            relationship_group(
                "affiliation-episode-a",
                institution_a.canonical_identity_id,
                old_assertion,
            ),
        ),
    )
    engine = module.create_ephemeral_canonical_decision_engine()
    result = engine.decide(request)

    decisions = {
        decision.canonical_relationship_id: decision
        for decision in result.relationship_decisions
    }
    assert set(decisions) == {"affiliation-episode-a", "affiliation-episode-b"}
    assert decisions["affiliation-episode-a"].valid_from == old_start
    assert decisions["affiliation-episode-a"].valid_to == transition
    assert decisions["affiliation-episode-b"].valid_from == new_start
    assert decisions["affiliation-episode-b"].valid_to is None

    assert tuple(
        selection.canonical_relationship_id
        for selection in result.current_relationships
    ) == ("affiliation-episode-b",)
    current = result.current_relationships[0]
    assert current.valid_from == new_start
    assert current.valid_to is None
    assert {
        assertion.assertion_id: assertion.source_event_time
        for assertion in result.relationship_assertions
    } == {
        "affiliation-new-evidence": new_start,
        "affiliation-old-evidence": old_start,
    }

    replay = engine.decide(
        request.model_copy(
            update={
                "source_identities": tuple(reversed(request.source_identities)),
                "canonical_identities": tuple(reversed(request.canonical_identities)),
                "relationship_groups": tuple(reversed(request.relationship_groups)),
            }
        )
    )
    assert replay == result

    missing_current = result.model_dump(mode="json")
    missing_current["current_relationships"] = []
    with pytest.raises(ValueError, match="accepted.*current|current.*accepted"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(missing_current)
        )

    changed_current_interval = result.model_dump(mode="json")
    changed_current_interval["current_relationships"][0]["valid_from"] = (
        new_start - timedelta(days=1)
    ).isoformat()
    with pytest.raises(ValueError, match="current.*validity|validity.*current"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(changed_current_interval)
        )

    changed_decision_interval = result.model_dump(mode="json")
    changed_decision_interval["relationship_decisions"][1]["valid_from"] = (
        new_start - timedelta(days=1)
    ).isoformat()
    changed_decision_interval["current_relationships"][0]["valid_from"] = (
        new_start - timedelta(days=1)
    ).isoformat()
    with pytest.raises(
        ValueError,
        match="validity|decision.*seed|decision.*ID",
    ):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(changed_decision_interval)
        )

    old_decision = decisions["affiliation-episode-a"]
    historical_as_current = result.model_dump(mode="json")
    historical_as_current["current_relationships"].append(
        {
            "release_id": RELEASE_ID,
            "canonical_relationship_id": "affiliation-episode-a",
            "relationship_type_id": old_decision.relationship_type_id,
            "relationship_type_version": old_decision.relationship_type_version,
            "source_canonical_identity_id": professor.canonical_identity_id,
            "target_canonical_identity_id": institution_a.canonical_identity_id,
            "role_bindings": {},
            "decision_id": old_decision.decision_id,
            "supporting_assertion_ids": [old_assertion.assertion_id],
            "conflicting_assertion_ids": [],
            "valid_from": old_start.isoformat(),
            "valid_to": transition.isoformat(),
        }
    )
    with pytest.raises(ValueError, match="accepted.*current|current.*accepted"):
        module.DecisionBatchResult.model_validate(
            _rehash_result_payload(historical_as_current)
        )


def test_equal_field_values_with_different_validity_do_not_auto_merge() -> None:
    module = _module()
    sources = (
        _source_identity(module, "temporal-field-a", source_system="official_a"),
        _source_identity(module, "temporal-field-b", source_system="official_b"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        tuple(source.source_identity_id for source in sources),
    )
    first = module.SourceAssertion(
        **{
            **_field_assertion(
                module,
                "institution-evidence-a",
                sources[0].source_identity_id,
                "Institution B",
                field_path="employment.institution",
            ).model_dump(mode="python"),
            "valid_from": NOW - timedelta(days=365),
            "valid_to": None,
        }
    )
    second = module.SourceAssertion(
        **{
            **_field_assertion(
                module,
                "institution-evidence-b",
                sources[1].source_identity_id,
                "Institution B",
                field_path="employment.institution",
            ).model_dump(mode="python"),
            "valid_from": NOW - timedelta(days=30),
            "valid_to": None,
        }
    )

    result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(
                _field_group(
                    module,
                    (second, first),
                    field_path="employment.institution",
                ),
            ),
        )
    )

    decision = result.canonical_decisions[0]
    assert decision.state.value == "unresolved"
    assert decision.selected_assertion_ids == ()
    assert decision.conflicting_assertion_ids == (
        "institution-evidence-a",
        "institution-evidence-b",
    )
    assert result.current_fields == ()
    assert {assertion.assertion_id for assertion in result.field_assertions} == {
        "institution-evidence-a",
        "institution-evidence-b",
    }

    response = _recorded_response(
        module,
        (first, second),
        decision_kind="field",
        subject_id=canonical.canonical_identity_id,
        path="employment.institution",
        state="selected",
        selected_assertion_ids=(first.assertion_id, second.assertion_id),
        conflicting_assertion_ids=(),
        confidence=0.9,
        rationale="The recorded fixture attempts to combine both intervals.",
        uncertainty="The evidence intervals differ.",
    )
    with pytest.raises(module.AdjudicationOutputError, match="validity|interval"):
        module.create_ephemeral_canonical_decision_engine(
            adjudicator=_recorded_adjudicator(module, response)
        ).decide(
            _batch(
                module,
                source_identities=sources,
                canonical_identities=(canonical,),
                field_groups=(
                    _field_group(
                        module,
                        (first, second),
                        field_path="employment.institution",
                    ),
                ),
            )
        )

    with pytest.raises(ValueError, match="validity|interval"):
        module._selected_validity(
            (first, second),
            (first.assertion_id, second.assertion_id),
        )


def _temporal_relationship_context(module: Any) -> tuple[Any, ...]:
    relationship_record = "record:temporal-relationship"
    professor_source = _source_identity(
        module,
        "temporal-professor-source",
        source_system="official_profile",
        record_ids=(relationship_record,),
    )
    company_source = _source_identity(
        module,
        "temporal-company-source",
        source_system="company_registry",
        record_ids=(relationship_record,),
        entity_type="company",
    )
    professor = _canonical_identity(
        module,
        "temporal-professor-c1",
        (professor_source.source_identity_id,),
    )
    company = _canonical_identity(
        module,
        "temporal-company-c1",
        (company_source.source_identity_id,),
        entity_type="company",
    )
    endpoints = {
        "source_endpoint": module.IdentityReference(
            identity_id=professor_source.source_identity_id,
            identity_space="source",
            entity_type="professor",
        ),
        "target_endpoint": module.IdentityReference(
            identity_id=company_source.source_identity_id,
            identity_space="source",
            entity_type="company",
        ),
    }
    return professor_source, company_source, professor, company, endpoints


def test_equal_temporal_instants_are_canonicalized_to_utc_before_hashing() -> None:
    module = _module()
    professor_source, company_source, professor, company, endpoints = (
        _temporal_relationship_context(module)
    )

    def decide_with(zone: timezone) -> Any:
        assertion = module.RelationshipAssertion(
            assertion_id="timezone-equivalent-evidence",
            relationship_type_id="professor_company_role",
            relationship_type_version="v1",
            source_record_id="record:temporal-relationship",
            attributes={"role": "founder"},
            observed_at=(NOW - timedelta(hours=1)).astimezone(zone),
            source_event_time=(NOW - timedelta(days=90)).astimezone(zone),
            valid_from=(NOW - timedelta(days=365)).astimezone(zone),
            valid_to=(NOW + timedelta(days=30)).astimezone(zone),
            assertion_run_id="temporal-assertion-run-1",
            **endpoints,
        )
        return module.create_ephemeral_canonical_decision_engine().decide(
            _batch(
                module,
                source_identities=(professor_source, company_source),
                canonical_identities=(professor, company),
                as_of=NOW.astimezone(zone),
                relationship_groups=(
                    module.RelationshipAssertionGroup(
                        canonical_relationship_id="timezone-relationship-c1",
                        relationship_type_id=assertion.relationship_type_id,
                        relationship_type_version=assertion.relationship_type_version,
                        source_canonical_identity_id=professor.canonical_identity_id,
                        target_canonical_identity_id=company.canonical_identity_id,
                        assertions=(assertion,),
                        policy=_policy(module, "relationship", "temporal-v1"),
                    ),
                ),
            )
        )

    utc_result = decide_with(timezone.utc)
    offset_result = decide_with(timezone(timedelta(hours=8)))

    assert offset_result == utc_result
    assert offset_result.as_of.utcoffset() == timedelta(0)
    assertion = offset_result.relationship_assertions[0]
    assert assertion.observed_at.utcoffset() == timedelta(0)
    assert assertion.source_event_time is not None
    assert assertion.source_event_time.utcoffset() == timedelta(0)
    assert assertion.valid_from is not None
    assert assertion.valid_from.utcoffset() == timedelta(0)
    assert assertion.valid_to is not None
    assert assertion.valid_to.utcoffset() == timedelta(0)
    serialized = assertion.model_dump_json()
    assert "+08:00" not in serialized


@pytest.mark.parametrize(
    ("valid_from", "valid_to", "source_event_time", "is_current"),
    (
        (
            NOW - timedelta(days=30),
            NOW + timedelta(days=30),
            NOW - timedelta(days=90),
            True,
        ),
        (
            NOW - timedelta(days=30),
            NOW,
            NOW - timedelta(days=90),
            False,
        ),
        (
            NOW + timedelta(days=1),
            None,
            NOW - timedelta(days=90),
            False,
        ),
        (None, None, NOW + timedelta(days=30), True),
    ),
    ids=("active", "ended-at-boundary", "future", "unknown"),
)
def test_relationship_current_projection_is_the_as_of_valid_subset(
    valid_from: datetime | None,
    valid_to: datetime | None,
    source_event_time: datetime,
    is_current: bool,
) -> None:
    module = _module()
    professor_source, company_source, professor, company, endpoints = (
        _temporal_relationship_context(module)
    )
    assertion = module.RelationshipAssertion(
        assertion_id="temporal-relationship-evidence",
        relationship_type_id="professor_company_role",
        relationship_type_version="v1",
        source_record_id="record:temporal-relationship",
        attributes={"role": "founder"},
        observed_at=NOW - timedelta(hours=1),
        source_event_time=source_event_time,
        valid_from=valid_from,
        valid_to=valid_to,
        assertion_run_id="temporal-assertion-run-1",
        **endpoints,
    )
    group = module.RelationshipAssertionGroup(
        canonical_relationship_id="temporal-relationship-c1",
        relationship_type_id=assertion.relationship_type_id,
        relationship_type_version=assertion.relationship_type_version,
        source_canonical_identity_id=professor.canonical_identity_id,
        target_canonical_identity_id=company.canonical_identity_id,
        assertions=(assertion,),
        policy=_policy(module, "relationship", "temporal-v1"),
    )

    result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=(professor_source, company_source),
            canonical_identities=(professor, company),
            relationship_groups=(group,),
        )
    )

    decision = result.relationship_decisions[0]
    assert decision.state.value == "accepted"
    assert decision.valid_from == valid_from
    assert decision.valid_to == valid_to
    assert result.relationship_assertions[0].source_event_time == source_event_time
    if valid_from is None and valid_to is None:
        assert decision.valid_from is None
        assert decision.valid_to is None
    if is_current:
        assert len(result.current_relationships) == 1
        assert result.current_relationships[0].valid_from == valid_from
        assert result.current_relationships[0].valid_to == valid_to
    else:
        assert result.current_relationships == ()


def test_equal_relationship_attributes_with_different_validity_do_not_auto_merge() -> (
    None
):
    module = _module()
    professor_source, company_source, professor, company, endpoints = (
        _temporal_relationship_context(module)
    )
    assertions = tuple(
        module.RelationshipAssertion(
            assertion_id=assertion_id,
            relationship_type_id="professor_company_role",
            relationship_type_version="v1",
            source_record_id="record:temporal-relationship",
            attributes={"role": "founder"},
            observed_at=NOW - timedelta(hours=1),
            valid_from=valid_from,
            valid_to=None,
            assertion_run_id="temporal-assertion-run-1",
            **endpoints,
        )
        for assertion_id, valid_from in (
            ("relationship-interval-old", NOW - timedelta(days=365)),
            ("relationship-interval-new", NOW - timedelta(days=30)),
        )
    )
    group = module.RelationshipAssertionGroup(
        canonical_relationship_id="temporal-relationship-c1",
        relationship_type_id="professor_company_role",
        relationship_type_version="v1",
        source_canonical_identity_id=professor.canonical_identity_id,
        target_canonical_identity_id=company.canonical_identity_id,
        assertions=tuple(reversed(assertions)),
        policy=_policy(module, "relationship", "temporal-v1"),
    )

    result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=(professor_source, company_source),
            canonical_identities=(professor, company),
            relationship_groups=(group,),
        )
    )

    decision = result.relationship_decisions[0]
    assert decision.state.value == "unresolved"
    assert decision.selected_assertion_ids == ()
    assert decision.conflicting_assertion_ids == (
        "relationship-interval-new",
        "relationship-interval-old",
    )
    assert decision.valid_from is None
    assert decision.valid_to is None
    assert result.current_relationships == ()
    assert result.unresolved_conflicts[0].assertion_ids == (
        "relationship-interval-new",
        "relationship-interval-old",
    )


@pytest.mark.parametrize(
    ("valid_from", "valid_to", "is_current"),
    (
        (NOW - timedelta(days=30), NOW + timedelta(days=30), True),
        (NOW - timedelta(days=30), NOW, False),
        (NOW + timedelta(days=1), None, False),
        (None, None, True),
    ),
    ids=("active", "ended-at-boundary", "future", "unknown"),
)
def test_field_current_projection_is_the_as_of_valid_subset(
    valid_from: datetime | None,
    valid_to: datetime | None,
    is_current: bool,
) -> None:
    module = _module()
    source = _source_identity(
        module,
        "temporal-field-source",
        source_system="official_profile",
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        (source.source_identity_id,),
    )
    assertion = module.SourceAssertion(
        **{
            **_field_assertion(
                module,
                "temporal-title-evidence",
                source.source_identity_id,
                "Professor",
            ).model_dump(mode="python"),
            "source_event_time": NOW - timedelta(days=90),
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
    )

    result = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=(source,),
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, (assertion,)),),
        )
    )

    assert result.canonical_decisions[0].state.value == "selected"
    assert result.field_assertions == (assertion,)
    assert result.field_assertions[0].source_event_time == NOW - timedelta(days=90)
    if is_current:
        assert len(result.current_fields) == 1
        assert result.current_fields[0].valid_from == valid_from
        assert result.current_fields[0].valid_to == valid_to

        missing_current = result.model_dump(mode="json")
        missing_current["current_fields"] = []
        with pytest.raises(ValueError, match="selected.*current|current.*selected"):
            module.DecisionBatchResult.model_validate(
                _rehash_result_payload(missing_current)
            )

        changed_current = result.model_dump(mode="json")
        changed_current["current_fields"][0]["valid_from"] = (
            NOW - timedelta(days=29)
        ).isoformat()
        with pytest.raises(ValueError, match="current.*validity|validity.*current"):
            module.DecisionBatchResult.model_validate(
                _rehash_result_payload(changed_current)
            )
    else:
        assert result.current_fields == ()

        injected_current = result.model_dump(mode="json")
        decision = result.canonical_decisions[0]
        injected_current["current_fields"] = [
            {
                "release_id": RELEASE_ID,
                "canonical_identity_id": canonical.canonical_identity_id,
                "field_path": decision.field_path,
                "value": assertion.value,
                "decision_id": decision.decision_id,
                "supporting_assertion_ids": list(decision.selected_assertion_ids),
                "conflicting_assertion_ids": list(decision.conflicting_assertion_ids),
                "valid_from": (None if valid_from is None else valid_from.isoformat()),
                "valid_to": None if valid_to is None else valid_to.isoformat(),
            }
        ]
        with pytest.raises(ValueError, match="selected.*current|current.*selected"):
            module.DecisionBatchResult.model_validate(
                _rehash_result_payload(injected_current)
            )


def test_engine_derives_field_replacement_and_withdrawal_from_validated_history() -> (
    None
):
    module = _module()
    source = _source_identity(
        module,
        "field-history-source",
        source_system="official_profile",
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        (source.source_identity_id,),
    )
    first_assertion = _field_assertion(
        module,
        "field-history-r1",
        source.source_identity_id,
        "Professor",
    )
    engine = module.create_ephemeral_canonical_decision_engine()
    first = engine.decide(
        _batch(
            module,
            source_identities=(source,),
            canonical_identities=(canonical,),
            field_groups=(_field_group(module, (first_assertion,)),),
        )
    )
    first_history = module.project_decision_history((first,), as_of=NOW)

    second_release = "candidate-s5-r2-ordinary-replacement"
    second_assertion = _field_assertion(
        module,
        "field-history-r2",
        source.source_identity_id,
        "Chair Professor",
    )
    second = engine.decide(
        _batch(
            module,
            release_id=second_release,
            decision_run_id="decision-build-run-r2-replacement",
            as_of=NOW + timedelta(hours=1),
            source_identities=(source,),
            canonical_identities=(
                canonical.model_copy(update={"release_id": second_release}),
            ),
            field_groups=(_field_group(module, (second_assertion,)),),
            previous_history=first_history,
        )
    )
    assert (
        second.canonical_decisions[0].supersedes_decision_id
        == first.canonical_decisions[0].decision_id
    )
    assert second.current_fields[0].value == "Chair Professor"
    second_history = module.project_decision_history(
        (first, second),
        as_of=NOW + timedelta(hours=1),
    )
    assert second_history.current_fields == second.current_fields

    third_release = "candidate-s5-r3-withdrawal"
    withdrawn = engine.decide(
        _batch(
            module,
            release_id=third_release,
            decision_run_id="decision-build-run-r3-withdrawal",
            as_of=NOW + timedelta(hours=2),
            source_identities=(source,),
            canonical_identities=(
                canonical.model_copy(update={"release_id": third_release}),
            ),
            field_groups=(
                _field_group(
                    module,
                    (second_assertion,),
                    transition="withdraw",
                ),
            ),
            previous_history=second_history,
        )
    )
    withdrawal = withdrawn.canonical_decisions[0]
    assert withdrawal.state.value == "superseded"
    assert withdrawal.method.value == "composite"
    assert (
        withdrawal.supersedes_decision_id == second.canonical_decisions[0].decision_id
    )
    assert withdrawal.selected_assertion_ids == ()
    assert withdrawal.conflicting_assertion_ids == ()
    assert withdrawal.human_review_resolution is None
    assert withdrawal.llm_trace is None
    assert withdrawn.current_fields == ()
    assert withdrawn.unresolved_conflicts == ()
    assert withdrawn.review_cases == ()
    final_history = module.project_decision_history(
        (first, second, withdrawn),
        as_of=NOW + timedelta(hours=2),
    )
    assert final_history.current_fields == ()
    assert final_history.canonical_decision_history == (
        first.canonical_decisions[0],
        second.canonical_decisions[0],
        withdrawal,
    )


@pytest.mark.parametrize(
    ("valid_from", "valid_to"),
    (
        (NOW + timedelta(days=1), None),
        (NOW - timedelta(days=10), NOW),
    ),
    ids=("future-head", "ended-head"),
)
def test_engine_supersedes_the_lineage_head_even_when_it_is_not_current(
    valid_from: datetime | None,
    valid_to: datetime | None,
) -> None:
    module = _module()
    source = _source_identity(
        module,
        "noncurrent-head-source",
        source_system="official_profile",
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        (source.source_identity_id,),
    )
    first = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            source_identities=(source,),
            canonical_identities=(canonical,),
            field_groups=(
                _field_group(
                    module,
                    (
                        _field_assertion(
                            module,
                            "noncurrent-head-r1",
                            source.source_identity_id,
                            "Professor",
                            valid_from=valid_from,
                            valid_to=valid_to,
                        ),
                    ),
                ),
            ),
        )
    )
    assert first.current_fields == ()
    history = module.project_decision_history((first,), as_of=NOW)
    second_release = "candidate-s5-r2-after-noncurrent-head"
    second = module.create_ephemeral_canonical_decision_engine().decide(
        _batch(
            module,
            release_id=second_release,
            decision_run_id="decision-build-run-after-noncurrent-head",
            as_of=NOW + timedelta(hours=1),
            source_identities=(source,),
            canonical_identities=(
                canonical.model_copy(update={"release_id": second_release}),
            ),
            field_groups=(
                _field_group(
                    module,
                    (
                        _field_assertion(
                            module,
                            "noncurrent-head-r2",
                            source.source_identity_id,
                            "Chair Professor",
                        ),
                    ),
                ),
            ),
            previous_history=history,
        )
    )
    assert (
        second.canonical_decisions[0].supersedes_decision_id
        == first.canonical_decisions[0].decision_id
    )
    assert second.current_fields[0].value == "Chair Professor"


def test_rejected_review_supersedes_unresolved_head_without_restoring_old_current() -> (
    None
):
    module = _module()
    sources = (
        _source_identity(module, "review-chain-a", source_system="official-a"),
        _source_identity(module, "review-chain-b", source_system="official-b"),
    )
    canonical = _canonical_identity(
        module,
        "professor-c1",
        tuple(source.source_identity_id for source in sources),
    )
    engine = module.create_ephemeral_canonical_decision_engine()
    first = engine.decide(
        _batch(
            module,
            source_identities=sources,
            canonical_identities=(canonical,),
            field_groups=(
                _field_group(
                    module,
                    (
                        _field_assertion(
                            module, "review-chain-r1", "review-chain-a", "Professor"
                        ),
                    ),
                ),
            ),
        )
    )
    second_release = "candidate-s5-r2-unresolved-head"
    conflicting = (
        _field_assertion(module, "review-chain-r2-a", "review-chain-a", "Professor"),
        _field_assertion(
            module, "review-chain-r2-b", "review-chain-b", "Chair Professor"
        ),
    )
    second = engine.decide(
        _batch(
            module,
            release_id=second_release,
            decision_run_id="decision-build-run-r2-unresolved-head",
            as_of=NOW + timedelta(hours=1),
            source_identities=sources,
            canonical_identities=(
                canonical.model_copy(update={"release_id": second_release}),
            ),
            field_groups=(_field_group(module, conflicting),),
            previous_history=module.project_decision_history((first,), as_of=NOW),
        )
    )
    unresolved = second.canonical_decisions[0]
    assert unresolved.state.value == "unresolved"
    assert unresolved.supersedes_decision_id == first.canonical_decisions[0].decision_id
    second_history = module.project_decision_history(
        (first, second), as_of=NOW + timedelta(hours=1)
    )
    assert second_history.current_fields == ()
    resolution = module.create_human_review_resolution(
        review_case=second.review_cases[0],
        outcome="rejected",
        reviewer_id="reviewer:reject-conflicting-field",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=2),
        rationale="Neither retained assertion is safe to publish as canonical.",
        confidence=0.99,
    )
    third_release = "candidate-s5-r3-rejected-head"
    third = engine.decide(
        _batch(
            module,
            release_id=third_release,
            decision_run_id="decision-build-run-r3-rejected-head",
            as_of=NOW + timedelta(hours=2),
            source_identities=sources,
            canonical_identities=(
                canonical.model_copy(update={"release_id": third_release}),
            ),
            field_groups=(_field_group(module, conflicting),),
            human_review_resolutions=(resolution,),
            previous_history=second_history,
        )
    )
    rejected = third.canonical_decisions[0]
    assert rejected.state.value == "rejected"
    assert rejected.supersedes_decision_id == unresolved.decision_id
    final_history = module.project_decision_history(
        (first, second, third), as_of=NOW + timedelta(hours=2)
    )
    assert final_history.current_fields == ()
    assert final_history.open_review_cases == ()


def test_engine_derives_relationship_replacement_and_withdrawal_from_history() -> None:
    module = _module()
    professor_source = _source_identity(
        module,
        "relationship-history-professor",
        source_system="official_profile",
        record_ids=("record:relationship-history",),
    )
    company_source = _source_identity(
        module,
        "relationship-history-company",
        source_system="company_registry",
        entity_type="company",
    )
    professor = _canonical_identity(
        module,
        "relationship-history-professor-c1",
        (professor_source.source_identity_id,),
    )
    company = _canonical_identity(
        module,
        "relationship-history-company-c1",
        (company_source.source_identity_id,),
        entity_type="company",
    )

    def assertion(assertion_id: str, role: str) -> Any:
        return module.RelationshipAssertion(
            assertion_id=assertion_id,
            relationship_type_id="professor_company_role",
            relationship_type_version="v1",
            source_record_id="record:relationship-history",
            source_endpoint=module.IdentityReference(
                identity_id=professor_source.source_identity_id,
                identity_space="source",
                entity_type="professor",
            ),
            target_endpoint=module.IdentityReference(
                identity_id=company_source.source_identity_id,
                identity_space="source",
                entity_type="company",
            ),
            attributes={"role": role},
            observed_at=NOW - timedelta(hours=1),
            assertion_run_id="relationship-history-assertion-run",
        )

    def group(item: Any, *, transition: str = "evaluate") -> Any:
        return module.RelationshipAssertionGroup(
            canonical_relationship_id="relationship-history-c1",
            relationship_type_id="professor_company_role",
            relationship_type_version="v1",
            source_canonical_identity_id=professor.canonical_identity_id,
            target_canonical_identity_id=company.canonical_identity_id,
            assertions=(item,),
            policy=_policy(module, "relationship"),
            transition=transition,
        )

    engine = module.create_ephemeral_canonical_decision_engine()
    first_assertion = assertion("relationship-history-r1", "advisor")
    first = engine.decide(
        _batch(
            module,
            source_identities=(professor_source, company_source),
            canonical_identities=(professor, company),
            relationship_groups=(group(first_assertion),),
        )
    )
    second_release = "candidate-s5-r2-relationship-replacement"
    second_assertion = assertion("relationship-history-r2", "founder")
    second = engine.decide(
        _batch(
            module,
            release_id=second_release,
            decision_run_id="decision-build-run-r2-relationship-replacement",
            as_of=NOW + timedelta(hours=1),
            source_identities=(professor_source, company_source),
            canonical_identities=(
                professor.model_copy(update={"release_id": second_release}),
                company.model_copy(update={"release_id": second_release}),
            ),
            relationship_groups=(group(second_assertion),),
            previous_history=module.project_decision_history((first,), as_of=NOW),
        )
    )
    assert (
        second.relationship_decisions[0].supersedes_decision_id
        == first.relationship_decisions[0].decision_id
    )
    second_history = module.project_decision_history(
        (first, second), as_of=NOW + timedelta(hours=1)
    )
    third_release = "candidate-s5-r3-relationship-withdrawal"
    third = engine.decide(
        _batch(
            module,
            release_id=third_release,
            decision_run_id="decision-build-run-r3-relationship-withdrawal",
            as_of=NOW + timedelta(hours=2),
            source_identities=(professor_source, company_source),
            canonical_identities=(
                professor.model_copy(update={"release_id": third_release}),
                company.model_copy(update={"release_id": third_release}),
            ),
            relationship_groups=(group(second_assertion, transition="withdraw"),),
            previous_history=second_history,
        )
    )
    withdrawal = third.relationship_decisions[0]
    assert withdrawal.state.value == "superseded"
    assert withdrawal.method.value == "composite"
    assert (
        withdrawal.supersedes_decision_id
        == second.relationship_decisions[0].decision_id
    )
    assert withdrawal.selected_assertion_ids == ()
    assert withdrawal.conflicting_assertion_ids == ()
    assert withdrawal.role_bindings == {}
    assert withdrawal.valid_from is None
    assert withdrawal.valid_to is None
    assert third.current_relationships == ()
    assert (
        module.project_decision_history(
            (first, second, third), as_of=NOW + timedelta(hours=2)
        ).current_relationships
        == ()
    )
