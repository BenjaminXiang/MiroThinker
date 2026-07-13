from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from importlib import import_module
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue

from src.data_agents.canonical_v2.contracts import (
    PolicyReference as SharedPolicyReference,
)
from src.data_agents.canonical_v2.contracts import (
    RelationshipAssertion as SharedRelationshipAssertion,
)
from src.data_agents.canonical_v2.contracts import (
    RelationshipDecision as SharedRelationshipDecision,
)
from src.data_agents.canonical_v2.contracts import (
    RelationshipType as SharedRelationshipType,
)
from src.data_agents.canonical_v2.contracts import TemporalComparisonContext
from src.data_agents.canonical_v2 import domain_projection_models as domain_models
from src.data_agents.canonical_v2.domain_catalog import (
    CATALOG_CONTENT_SHA256 as INSTALLED_CATALOG_CONTENT_SHA256,
)
from src.data_agents.canonical_v2.domain_catalog import (
    CATALOG_SCHEMA_VERSION as INSTALLED_CATALOG_SCHEMA_VERSION,
)
from src.data_agents.canonical_v2.domain_catalog import (
    CATALOG_VERSION as INSTALLED_CATALOG_VERSION,
)


TARGET_MODULE = "src.data_agents.canonical_v2.relationship_projection"
REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = (
    REPO_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s6/"
    "domain-catalog-v1.json"
)
CATALOG_SCHEMA_VERSION = "canonical-v2-domain-catalog-v1"
CATALOG_VERSION = "canonical-v2-prd-catalog-2026-07-12"
CATALOG_CONTENT_SHA256 = (
    "8ad9e719579b834f51128788f49d091913c0c90e3b047aac9b2f83cc794441d7"
)
CATALOG_FILE_SHA256 = "b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0"
NOW = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)


def _canonical_sha256(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _content_bound_model(model: Any, values: dict[str, Any], hash_field: str) -> Any:
    provisional = model.model_validate(
        {**values, hash_field: "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    payload = provisional.model_dump(mode="json", exclude={hash_field})
    return model.model_validate(
        {
            **provisional.model_dump(mode="python"),
            hash_field: _canonical_sha256(payload),
        }
    )


def _typed_company_subobject(endpoint: Any) -> Any:
    parent_id = endpoint.parent_canonical_identity_ref.rsplit(":", maxsplit=1)[-1]
    base = {
        "subobject_id": endpoint.stable_reference,
        "parent_canonical_identity_id": parent_id,
        "supporting_assertion_ids": (f"projection-assertion:{parent_id}",),
        "decision_ids": (f"projection-decision:{parent_id}",),
        "observed_at": NOW,
        "valid_from": None,
        "valid_to": None,
    }
    definitions = {
        "business_scenario": (
            domain_models.CompanyBusinessScenario,
            {"name": "Scenario", "description": "Typed scenario fixture"},
        ),
        "capability": (
            domain_models.CompanyCapability,
            {"name": "Capability", "description": "Typed capability fixture"},
        ),
        "financing_event": (
            domain_models.CompanyFinancingEvent,
            {"round": "Series A"},
        ),
        "product": (
            domain_models.CompanyProduct,
            {"name": "Product"},
        ),
        "public_update": (
            domain_models.CompanyPublicUpdate,
            {
                "headline": "Public update",
                "source_url": "https://example.com/update",
            },
        ),
    }
    model, members = definitions[endpoint.endpoint_type]
    return _content_bound_model(
        model,
        {**base, **members},
        "projection_content_sha256",
    )


def _typed_domain_projection(
    *,
    entity_type: str,
    canonical_identity_id: str,
    company_subobjects: tuple[Any, ...] = (),
) -> Any:
    assertion_id = f"projection-assertion:{canonical_identity_id}"
    decision_id = f"projection-decision:{canonical_identity_id}"
    field_path = {
        "company": "name",
        "paper": "title",
        "patent": "title",
        "professor": "name",
    }[entity_type]
    common = {
        "release_id": "candidate-s6d-r1",
        "canonical_identity_id": canonical_identity_id,
        "identity_decision_id": f"identity-decision:{canonical_identity_id}",
        "inclusion_decision_id": f"inclusion:{canonical_identity_id}",
        "projection_version": "domain-projection-v1",
        "catalog_schema_version": INSTALLED_CATALOG_SCHEMA_VERSION,
        "catalog_version": INSTALLED_CATALOG_VERSION,
        "catalog_content_sha256": INSTALLED_CATALOG_CONTENT_SHA256,
        "as_of": NOW,
        "field_lineage": (
            domain_models.FieldProjectionLineage(
                field_path=field_path,
                decision_id=decision_id,
                supporting_assertion_ids=(assertion_id,),
            ),
        ),
        "evidence": (
            domain_models.ProjectionEvidenceReference(
                assertion_id=assertion_id,
                decision_id=decision_id,
                field_path=field_path,
            ),
        ),
        "id": canonical_identity_id,
        "last_updated": NOW,
        "quality_status": "partial",
        "run_id": "relationship-projection-domain-fixture",
    }
    if entity_type == "company":
        attributes = {
            attribute: tuple(
                item
                for item in company_subobjects
                if item.__class__
                is domain_models.DOMAIN_SUBOBJECT_MODELS["company"][subobject_type]
            )
            for subobject_type, attribute in domain_models.DOMAIN_SUBOBJECT_ATTRIBUTES[
                "company"
            ].items()
        }
        return _content_bound_model(
            domain_models.CompanyProjection,
            {
                **common,
                "name": f"Company {canonical_identity_id}",
                "normalized_name": canonical_identity_id,
                "profile_summary": "Typed Company endpoint fixture.",
                "technology_route_summary": "Typed technology route.",
                **attributes,
            },
            "content_sha256",
        )
    if entity_type == "paper":
        return _content_bound_model(
            domain_models.PaperProjection,
            {
                **common,
                "authors": (),
                "title": f"Paper {canonical_identity_id}",
                "venue": domain_models.NamedReference(
                    reference_id="venue:fixture",
                    name="Fixture Venue",
                ),
                "year": 2026,
            },
            "content_sha256",
        )
    if entity_type == "patent":
        return _content_bound_model(
            domain_models.PatentProjection,
            {
                **common,
                "applicants": (),
                "summary_text": "Typed Patent endpoint fixture.",
                "title": f"Patent {canonical_identity_id}",
            },
            "content_sha256",
        )
    if entity_type == "professor":
        return _content_bound_model(
            domain_models.ProfessorProjection,
            {
                **common,
                "canonical_name_zh": canonical_identity_id,
                "company_roles": (),
                "department": domain_models.NamedReference(
                    reference_id="department:fixture",
                    name="Fixture Department",
                ),
                "email": "fixture@example.edu",
                "homepage": "https://example.edu/fixture",
                "institution": "Fixture Institution",
                "name": canonical_identity_id,
                "paper_summary": "Typed paper summary.",
                "patent_ids": (),
                "patent_summary": "Typed patent summary.",
                "profile_summary": "Typed Professor endpoint fixture.",
                "research_directions": (),
                "title": "Professor",
            },
            "content_sha256",
        )
    raise AssertionError(f"unsupported domain projection fixture: {entity_type}")


def _domain_projection_registry(
    candidates: tuple[Any, ...],
    direction_probes: tuple[Any, ...],
) -> tuple[Any, ...]:
    canonical_endpoints: dict[tuple[str, str], Any] = {}
    typed_endpoints: dict[str, Any] = {}
    for item in (*candidates, *direction_probes):
        item_id = getattr(item, "candidate_id", getattr(item, "probe_id", ""))
        skip_dangling = item_id.startswith("invalid:dangling-domain-endpoint")
        for endpoint in (item.source_endpoint, item.target_endpoint):
            if endpoint.reference_kind == "canonical_identity" and not skip_dangling:
                canonical_endpoints[
                    (endpoint.endpoint_type, endpoint.canonical_identity_id)
                ] = endpoint
            elif endpoint.reference_kind == "typed_subobject" and not skip_dangling:
                typed_endpoints[endpoint.stable_reference] = endpoint
                parent_id = endpoint.parent_canonical_identity_ref.rsplit(
                    ":", maxsplit=1
                )[-1]
                canonical_endpoints[("company", parent_id)] = endpoint
    subobjects_by_parent: dict[str, list[Any]] = {}
    for endpoint in typed_endpoints.values():
        parent_id = endpoint.parent_canonical_identity_ref.rsplit(":", maxsplit=1)[-1]
        subobjects_by_parent.setdefault(parent_id, []).append(
            _typed_company_subobject(endpoint)
        )
    return tuple(
        _typed_domain_projection(
            entity_type=entity_type,
            canonical_identity_id=canonical_identity_id,
            company_subobjects=tuple(
                sorted(
                    subobjects_by_parent.get(canonical_identity_id, ()),
                    key=lambda item: item.subobject_id,
                )
            ),
        )
        for entity_type, canonical_identity_id in sorted(canonical_endpoints)
    )


class _MissingTargetModule(RuntimeError):
    """Exact Task 6.4 RED sentinel; nested missing dependencies fail normally."""


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


def _catalog() -> dict[str, Any]:
    payload = CATALOG_PATH.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == CATALOG_FILE_SHA256
    catalog = json.loads(payload)
    assert catalog["schema_version"] == CATALOG_SCHEMA_VERSION
    assert catalog["catalog_version"] == CATALOG_VERSION
    assert catalog["content_sha256"] == CATALOG_CONTENT_SHA256
    assert len(catalog["relationships"]) == 34
    return catalog


def _relationship(catalog: dict[str, Any], relationship_type_id: str) -> dict[str, Any]:
    return next(
        relationship
        for relationship in catalog["relationships"]
        if relationship["relationship_type_id"] == relationship_type_id
    )


def _catalog_reference(module: Any) -> Any:
    return module.RelationshipCatalogIdentity(
        schema_version=CATALOG_SCHEMA_VERSION,
        catalog_version=CATALOG_VERSION,
        content_sha256=CATALOG_CONTENT_SHA256,
    )


def _canonical_endpoint(module: Any, endpoint_type: str, endpoint_id: str) -> Any:
    return module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type=endpoint_type,
        stable_reference=f"canonical:{endpoint_type}:{endpoint_id}",
        canonical_identity_id=endpoint_id,
        parent_canonical_identity_ref=None,
    )


def _registry_endpoint(module: Any, endpoint_type: str, endpoint_id: str) -> Any:
    return module.RelationshipEndpointReference(
        reference_kind="registry_entity",
        endpoint_type=endpoint_type,
        stable_reference=f"registry:{endpoint_type}:{endpoint_id}",
        canonical_identity_id=None,
        parent_canonical_identity_ref=None,
    )


def _subobject_endpoint(
    module: Any,
    endpoint_type: str,
    endpoint_id: str,
    *,
    parent_canonical_identity_ref: str,
) -> Any:
    return module.RelationshipEndpointReference(
        reference_kind="typed_subobject",
        endpoint_type=endpoint_type,
        stable_reference=f"subobject:{endpoint_type}:{endpoint_id}",
        canonical_identity_id=None,
        parent_canonical_identity_ref=parent_canonical_identity_ref,
    )


def _lineage_endpoint(
    module: Any,
    endpoint_type: str,
    endpoint_id: str,
    *,
    lineage_family: str | None = None,
    subject_reference: str | None = None,
    subject_entity_type: str | None = None,
) -> Any:
    return module.RelationshipEndpointReference(
        reference_kind="lineage_record",
        endpoint_type=endpoint_type,
        stable_reference=f"lineage:{endpoint_type}:{endpoint_id}",
        canonical_identity_id=None,
        parent_canonical_identity_ref=None,
        lineage_family=lineage_family,
        subject_reference=subject_reference,
        subject_entity_type=subject_entity_type,
    )


def _retained_evidence(
    module: Any,
    prefix: str,
    evidence_kinds: tuple[str, ...] | list[str],
) -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]:
    artifact = module.RetainedArtifactReference(
        reference_id=f"artifact:{prefix}",
        artifact_id=prefix,
        content_sha256="a" * 64,
    )
    assertions = tuple(
        module.RetainedAssertionReference(
            reference_id=f"assertion:{prefix}:{index}",
            assertion_id=f"{prefix}:{index}",
            source_record_ref=f"source-record:{prefix}:{index}",
            artifact_refs=(artifact.reference_id,),
        )
        for index, _ in enumerate(evidence_kinds)
    )
    bindings = tuple(
        module.RetainedEvidenceBinding(
            evidence_kind=evidence_kind,
            assertion_refs=(assertions[index].reference_id,),
            artifact_refs=(artifact.reference_id,),
        )
        for index, evidence_kind in enumerate(evidence_kinds)
    )
    return assertions, (artifact,), bindings


def _outcome(result: Any, candidate_id: str) -> Any:
    matches = tuple(
        outcome
        for outcome in result.candidate_outcomes
        if outcome.candidate_id == candidate_id
    )
    assert len(matches) == 1, (
        f"expected one outcome for {candidate_id}, got {len(matches)}"
    )
    return matches[0]


def _relationship_policy() -> SharedPolicyReference:
    return SharedPolicyReference.model_validate(
        {
            "policy_id": "relationship-projection-policy",
            "policy_version": "relationship-v1",
            "policy_kind": "relationship",
            "content_sha256": "b" * 64,
            "effective_at": NOW,
        }
    )


def _bound_projection_inputs(
    module: Any,
    candidates: tuple[Any, ...],
    policy: SharedPolicyReference,
) -> tuple[
    tuple[Any, ...], tuple[Any, ...], tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]
]:
    bound_candidates = []
    shared_assertions = []
    typed_assertions = []
    assignments = []
    decision_inputs = []
    for candidate in candidates:
        assertion_id = f"relationship-assertion:{candidate.candidate_id}"
        decision_input_id = f"relationship-decision-input:{candidate.candidate_id}"
        source_record_id = f"source-record:{candidate.candidate_id}"
        evidence_refs = tuple(
            sorted(
                {
                    reference
                    for binding in candidate.evidence_bindings
                    for reference in (*binding.assertion_refs, *binding.artifact_refs)
                }
            )
        )
        if (
            candidate.source_endpoint.reference_kind == "canonical_identity"
            and candidate.target_endpoint.reference_kind == "canonical_identity"
        ):
            source_identity_id = f"source-identity:{candidate.candidate_id}:source"
            target_identity_id = f"source-identity:{candidate.candidate_id}:target"
            assertion = SharedRelationshipAssertion.model_validate(
                {
                    "assertion_id": assertion_id,
                    "relationship_type_id": candidate.relationship_type_id,
                    "relationship_type_version": candidate.relationship_type_version,
                    "source_record_id": source_record_id,
                    "source_endpoint": {
                        "identity_id": source_identity_id,
                        "identity_space": "source",
                        "entity_type": candidate.source_endpoint.endpoint_type,
                    },
                    "target_endpoint": {
                        "identity_id": target_identity_id,
                        "identity_space": "source",
                        "entity_type": candidate.target_endpoint.endpoint_type,
                    },
                    "attributes": {
                        "candidate_id": candidate.candidate_id,
                        "evidence_refs": list(evidence_refs),
                        "evidence_metadata": json.loads(
                            json.dumps(candidate.evidence_metadata)
                        ),
                        "role_bindings": dict(candidate.role_bindings),
                    },
                    "observed_at": candidate.observed_at,
                    "source_event_time": candidate.source_event_time,
                    "valid_from": candidate.valid_from,
                    "valid_to": candidate.valid_to,
                    "assertion_run_id": "relationship-projection-input-run",
                }
            )
            shared_assertions.append(assertion)
            assignments.extend(
                (
                    module.SourceCanonicalAssignment(
                        assignment_id=f"assignment:{candidate.candidate_id}:source",
                        source_identity_id=source_identity_id,
                        canonical_identity_id=candidate.source_endpoint.canonical_identity_id,
                        entity_type=candidate.source_endpoint.endpoint_type,
                        source_record_refs=(source_record_id,),
                    ),
                    module.SourceCanonicalAssignment(
                        assignment_id=f"assignment:{candidate.candidate_id}:target",
                        source_identity_id=target_identity_id,
                        canonical_identity_id=candidate.target_endpoint.canonical_identity_id,
                        entity_type=candidate.target_endpoint.endpoint_type,
                        source_record_refs=(source_record_id,),
                    ),
                )
            )
            assertion_input_kind = "shared_source_relationship_assertion"
        else:
            typed_assertions.append(
                module.TypedRelationshipAssertionInput(
                    assertion_id=assertion_id,
                    relationship_type_id=candidate.relationship_type_id,
                    relationship_type_version=candidate.relationship_type_version,
                    source_record_ref=source_record_id,
                    source_endpoint=candidate.source_endpoint,
                    target_endpoint=candidate.target_endpoint,
                    attributes={
                        "candidate_id": candidate.candidate_id,
                        "evidence_metadata": candidate.evidence_metadata,
                        "role_bindings": candidate.role_bindings,
                    },
                    evidence_bindings=candidate.evidence_bindings,
                    observed_at=candidate.observed_at,
                    source_event_time=candidate.source_event_time,
                    valid_from=candidate.valid_from,
                    valid_to=candidate.valid_to,
                    assertion_run_id="relationship-projection-input-run",
                )
            )
            assertion_input_kind = "typed_relationship_assertion"
        decision_state = (
            "rejected" if candidate.candidate_id.startswith("rejected:") else "accepted"
        )
        decision_inputs.append(
            module.RelationshipDecisionInput(
                decision_input_id=decision_input_id,
                decision_id=f"relationship-decision:{candidate.candidate_id}",
                canonical_relationship_id=(
                    f"canonical-relationship:{candidate.candidate_id}"
                ),
                state=decision_state,
                candidate_assertion_ids=(assertion_id,),
                selected_assertion_ids=(assertion_id,)
                if decision_state == "accepted"
                else (),
                conflicting_assertion_ids=(),
                role_bindings=candidate.role_bindings,
                selected_evidence_refs=evidence_refs
                if decision_state == "accepted"
                else (),
                policy=policy,
                method="deterministic",
                method_version="relationship-v1",
                confidence=1.0,
                rationale="Task 6.4 retained decision input",
            )
        )
        bound_candidates.append(
            module.RelationshipProjectionCandidate.model_validate(
                {
                    **candidate.model_dump(mode="python"),
                    "assertion_input_id": assertion_id,
                    "assertion_input_kind": assertion_input_kind,
                    "decision_input_id": decision_input_id,
                }
            )
        )
    return (
        tuple(bound_candidates),
        tuple(shared_assertions),
        tuple(typed_assertions),
        tuple(assignments),
        tuple(decision_inputs),
    )


def _projection_request(
    module: Any,
    *,
    run_id: str,
    candidates: tuple[Any, ...],
    retained_assertions: tuple[Any, ...],
    retained_artifacts: tuple[Any, ...],
    direction_probes: tuple[Any, ...] = (),
    layer_probes: tuple[Any, ...] = (),
    temporal_comparison_context: TemporalComparisonContext | None = None,
) -> Any:
    policy = _relationship_policy()
    (
        bound_candidates,
        shared_assertions,
        typed_assertions,
        assignments,
        decision_inputs,
    ) = _bound_projection_inputs(module, candidates, policy)
    values = {
        "catalog": _catalog_reference(module),
        "release_id": "candidate-s6d-r1",
        "projection_run_id": run_id,
        "as_of": NOW,
        "decision_policy": policy,
        "domain_projections": _domain_projection_registry(
            bound_candidates,
            direction_probes,
        ),
        "candidates": bound_candidates,
        "relationship_assertions": shared_assertions,
        "typed_relationship_assertions": typed_assertions,
        "source_canonical_assignments": assignments,
        "decision_inputs": decision_inputs,
        "direction_probes": direction_probes,
        "layer_probes": layer_probes,
        "retained_assertions": retained_assertions,
        "retained_artifacts": retained_artifacts,
    }
    if temporal_comparison_context is not None:
        values["temporal_comparison_context"] = temporal_comparison_context
    return module.RelationshipProjectionRequest.model_validate(values)


def _assert_canonical_decision_layers(
    request: Any, result: Any, candidate_id: str
) -> None:
    outcome = _outcome(result, candidate_id)
    candidate = next(
        candidate
        for candidate in request.candidates
        if candidate.candidate_id == candidate_id
    )
    input_assertion = next(
        assertion
        for assertion in request.relationship_assertions
        if assertion.assertion_id == candidate.assertion_input_id
    )
    decision_input = next(
        decision_input
        for decision_input in request.decision_inputs
        if decision_input.decision_input_id == candidate.decision_input_id
    )
    assertions = tuple(
        assertion
        for assertion in result.retained_relationship_assertions
        if assertion.assertion_id == outcome.retained_assertion_id
    )
    decisions = tuple(
        decision
        for decision in result.relationship_decisions
        if decision.decision_id == outcome.decision_id
    )
    currents = tuple(
        current
        for current in result.current_relationships
        if current.canonical_relationship_id == outcome.projected_relationship_id
    )
    assert len(assertions) == len(decisions) == len(currents) == 1
    assertion = assertions[0]
    decision = decisions[0]
    assert isinstance(assertion, SharedRelationshipAssertion)
    assert isinstance(decision, SharedRelationshipDecision)
    assert assertion.model_dump(mode="json") == input_assertion.model_dump(mode="json")
    assert assertion.source_endpoint.identity_space.value == "source"
    assert assertion.target_endpoint.identity_space.value == "source"
    assert assertion.source_record_id in {
        source_record_ref
        for assignment in request.source_canonical_assignments
        for source_record_ref in assignment.source_record_refs
    }
    assignment_by_source = {
        assignment.source_identity_id: assignment
        for assignment in request.source_canonical_assignments
    }
    source_assignment = assignment_by_source[assertion.source_endpoint.identity_id]
    target_assignment = assignment_by_source[assertion.target_endpoint.identity_id]
    assert source_assignment.entity_type == assertion.source_endpoint.entity_type
    assert target_assignment.entity_type == assertion.target_endpoint.entity_type
    assert (
        decision.source_canonical_identity_id == source_assignment.canonical_identity_id
    )
    assert (
        decision.target_canonical_identity_id == target_assignment.canonical_identity_id
    )
    assert decision.state.value == decision_input.state
    assert decision.decision_id == decision_input.decision_id
    assert (
        decision.canonical_relationship_id == decision_input.canonical_relationship_id
    )
    assert decision.candidate_assertion_ids == decision_input.candidate_assertion_ids
    assert (
        decision.selected_assertion_ids
        == decision_input.selected_assertion_ids
        == (assertion.assertion_id,)
    )
    assert decision.role_bindings == candidate.role_bindings
    assert decision.policy.model_dump(
        mode="json"
    ) == request.decision_policy.model_dump(mode="json")
    assert currents[0].decision_id == decision.decision_id


def _assert_typed_decision_layers(request: Any, result: Any, candidate_id: str) -> None:
    outcome = _outcome(result, candidate_id)
    candidate = next(
        candidate
        for candidate in request.candidates
        if candidate.candidate_id == candidate_id
    )
    input_assertion = next(
        assertion
        for assertion in request.typed_relationship_assertions
        if assertion.assertion_id == candidate.assertion_input_id
    )
    decision_input = next(
        decision_input
        for decision_input in request.decision_inputs
        if decision_input.decision_input_id == candidate.decision_input_id
    )
    assertions = tuple(
        assertion
        for assertion in result.typed_relationship_assertions
        if assertion.assertion_id == outcome.retained_assertion_id
    )
    decisions = tuple(
        decision
        for decision in result.typed_relationship_decisions
        if decision.decision_id == outcome.decision_id
    )
    assert len(assertions) == len(decisions) == 1
    assertion = assertions[0]
    decision = decisions[0]
    assert assertion.model_dump(mode="json") == input_assertion.model_dump(mode="json")
    assert decision.state == decision_input.state
    assert decision.candidate_assertion_ids == decision_input.candidate_assertion_ids
    assert (
        decision.selected_assertion_ids
        == decision_input.selected_assertion_ids
        == (assertion.assertion_id,)
    )
    assert (
        decision.selected_evidence_refs
        == decision_input.selected_evidence_refs
        == outcome.selected_evidence_refs
    )
    assert decision.selected_evidence_refs
    assert decision.policy.model_dump(
        mode="json"
    ) == request.decision_policy.model_dump(mode="json")


def test_identity_lifecycle_requires_same_domain_typed_lineage() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "identity_lifecycle"
    )
    assert len(relationships) == 5
    relationship_by_id = {
        relationship["relationship_type_id"]: relationship
        for relationship in relationships
    }
    module = _module()
    assert module.RelationshipType is SharedRelationshipType
    assert module.RelationshipAssertion is SharedRelationshipAssertion
    assert module.RelationshipDecision is SharedRelationshipDecision

    registries = {
        relationship_id: _retained_evidence(
            module,
            relationship_id,
            relationship["required_evidence_kinds"],
        )
        for relationship_id, relationship in relationship_by_id.items()
    }
    paper_old = _canonical_endpoint(module, "paper", "paper-old")
    paper_survivor = _canonical_endpoint(module, "paper", "paper-survivor")
    identity_decision_1 = _lineage_endpoint(
        module,
        "identity_decision",
        "identity-decision-1",
        lineage_family="identity",
        subject_reference="canonical:paper:paper-old",
        subject_entity_type="paper",
    )
    identity_decision_2 = _lineage_endpoint(
        module,
        "identity_decision",
        "identity-decision-2",
        lineage_family="identity",
        subject_reference="canonical:paper:paper-old",
        subject_entity_type="paper",
    )
    candidates = [
        module.RelationshipProjectionCandidate(
            candidate_id="valid:canonical_identity_merged_into",
            relationship_type_id="canonical_identity_merged_into",
            relationship_type_version=relationship_by_id[
                "canonical_identity_merged_into"
            ]["version"],
            source_endpoint=paper_old,
            target_endpoint=paper_survivor,
            role_bindings={},
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries["canonical_identity_merged_into"][2],
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:canonical_identity_split_from",
            relationship_type_id="canonical_identity_split_from",
            relationship_type_version=relationship_by_id[
                "canonical_identity_split_from"
            ]["version"],
            source_endpoint=paper_old,
            target_endpoint=paper_survivor,
            role_bindings={},
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries["canonical_identity_split_from"][2],
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:source_identity_resolves_to_canonical_identity",
            relationship_type_id="source_identity_resolves_to_canonical_identity",
            relationship_type_version=relationship_by_id[
                "source_identity_resolves_to_canonical_identity"
            ]["version"],
            source_endpoint=_lineage_endpoint(
                module,
                "source_identity",
                "source-paper-1",
                lineage_family="identity",
                subject_reference="canonical:paper:paper-survivor",
                subject_entity_type="paper",
            ),
            target_endpoint=paper_survivor,
            role_bindings={},
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries[
                "source_identity_resolves_to_canonical_identity"
            ][2],
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:identity_decision_supersedes_identity_decision",
            relationship_type_id="identity_decision_supersedes_identity_decision",
            relationship_type_version=relationship_by_id[
                "identity_decision_supersedes_identity_decision"
            ]["version"],
            source_endpoint=identity_decision_2,
            target_endpoint=identity_decision_1,
            role_bindings={},
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries[
                "identity_decision_supersedes_identity_decision"
            ][2],
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:identity_decision_reverses_identity_decision",
            relationship_type_id="identity_decision_reverses_identity_decision",
            relationship_type_version=relationship_by_id[
                "identity_decision_reverses_identity_decision"
            ]["version"],
            source_endpoint=identity_decision_2,
            target_endpoint=identity_decision_1,
            role_bindings={},
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries[
                "identity_decision_reverses_identity_decision"
            ][2],
        ),
    ]
    merge = relationship_by_id["canonical_identity_merged_into"]
    merge_evidence = registries["canonical_identity_merged_into"][2]
    candidates.extend(
        (
            module.RelationshipProjectionCandidate(
                candidate_id="invalid:paper-merge-cross-domain",
                relationship_type_id=merge["relationship_type_id"],
                relationship_type_version=merge["version"],
                source_endpoint=paper_old,
                target_endpoint=_canonical_endpoint(module, "professor", "professor-1"),
                role_bindings={},
                observed_at=NOW,
                source_event_time=NOW,
                valid_from=None,
                valid_to=None,
                evidence_bindings=merge_evidence,
            ),
            module.RelationshipProjectionCandidate(
                candidate_id="invalid:missing-one-required-evidence-kind",
                relationship_type_id=merge["relationship_type_id"],
                relationship_type_version=merge["version"],
                source_endpoint=paper_old,
                target_endpoint=paper_survivor,
                role_bindings={},
                observed_at=NOW,
                source_event_time=NOW,
                valid_from=None,
                valid_to=None,
                evidence_bindings=merge_evidence[:1],
            ),
            module.RelationshipProjectionCandidate(
                candidate_id="invalid:dangling-evidence-references",
                relationship_type_id=merge["relationship_type_id"],
                relationship_type_version=merge["version"],
                source_endpoint=paper_old,
                target_endpoint=paper_survivor,
                role_bindings={},
                observed_at=NOW,
                source_event_time=NOW,
                valid_from=None,
                valid_to=None,
                evidence_bindings=tuple(
                    module.RetainedEvidenceBinding(
                        evidence_kind=evidence_kind,
                        assertion_refs=(f"assertion:missing:{index}",),
                        artifact_refs=("artifact:missing",),
                    )
                    for index, evidence_kind in enumerate(
                        merge["required_evidence_kinds"]
                    )
                ),
            ),
            module.RelationshipProjectionCandidate(
                candidate_id="invalid:unknown-relationship-version",
                relationship_type_id=merge["relationship_type_id"],
                relationship_type_version="unknown-version",
                source_endpoint=paper_old,
                target_endpoint=paper_survivor,
                role_bindings={},
                observed_at=NOW,
                source_event_time=NOW,
                valid_from=None,
                valid_to=None,
                evidence_bindings=merge_evidence,
            ),
            module.RelationshipProjectionCandidate(
                candidate_id="invalid:dangling-domain-endpoint",
                relationship_type_id=merge["relationship_type_id"],
                relationship_type_version=merge["version"],
                source_endpoint=paper_old,
                target_endpoint=_canonical_endpoint(
                    module, "paper", "paper-not-projected"
                ),
                role_bindings={},
                observed_at=NOW,
                source_event_time=NOW,
                valid_from=None,
                valid_to=None,
                evidence_bindings=merge_evidence,
            ),
        )
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-1",
        candidates=tuple(candidates),
        retained_assertions=tuple(
            assertion
            for assertions, _, _ in registries.values()
            for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact
            for _, artifacts, _ in registries.values()
            for artifact in artifacts
        ),
    )
    assert set(request.catalog.model_dump()) == {
        "schema_version",
        "catalog_version",
        "content_sha256",
    }
    assert ".agents" not in json.dumps(request.catalog.model_dump(), sort_keys=True)
    assert all(
        "decision_state" not in candidate.model_dump()
        for candidate in request.candidates
    )

    result = module.create_ephemeral_relationship_projection().project(request)
    replayed = module.create_ephemeral_relationship_projection().project(request)

    assert replayed == result
    assert len(result.content_sha256) == 64
    first_decision, second_decision, *remaining_decisions = request.decision_inputs
    for identity_field in ("decision_id", "canonical_relationship_id"):
        duplicated = second_decision.model_copy(
            update={identity_field: getattr(first_decision, identity_field)}
        )
        tampered = request.model_copy(
            update={
                "decision_inputs": (
                    first_decision,
                    duplicated,
                    *remaining_decisions,
                )
            }
        )
        with pytest.raises(
            module.RelationshipProjectionIntegrityError,
            match="duplicate (relationship decision ID|canonical relationship ID)",
        ):
            module.create_ephemeral_relationship_projection().project(tampered)

    valid_outcomes = tuple(
        _outcome(result, f"valid:{relationship_id}")
        for relationship_id in relationship_by_id
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == set(
        relationship_by_id
    )
    assert all(outcome.admitted is True for outcome in valid_outcomes)
    assert all(outcome.decision_id for outcome in valid_outcomes)
    rejected = _outcome(result, "invalid:paper-merge-cross-domain")
    assert rejected.admitted is False
    assert rejected.decision_state is None
    assert "source_and_target_entity_types_must_match" in rejected.reason_codes
    assert rejected.projected_relationship_id is None
    missing_kind = _outcome(result, "invalid:missing-one-required-evidence-kind")
    dangling = _outcome(result, "invalid:dangling-evidence-references")
    unknown_version = _outcome(result, "invalid:unknown-relationship-version")
    dangling_endpoint = _outcome(result, "invalid:dangling-domain-endpoint")
    assert missing_kind.admitted is False
    assert "missing_required_evidence_kind" in missing_kind.reason_codes
    assert dangling.admitted is False
    assert "unresolved_retained_evidence_reference" in dangling.reason_codes
    assert unknown_version.admitted is False
    assert "relationship_type_version_not_registered" in unknown_version.reason_codes
    assert dangling_endpoint.admitted is False
    assert "canonical_endpoint_not_in_domain_projection" in (
        dangling_endpoint.reason_codes
    )
    assert set(result.retained_assertion_refs) == {
        assertion.reference_id
        for assertions, _, _ in registries.values()
        for assertion in assertions
    }
    assert set(result.retained_artifact_refs) == {
        artifact.reference_id
        for _, artifacts, _ in registries.values()
        for artifact in artifacts
    }


def test_organization_roles_enforce_vocabulary_and_role_ownership() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "organization_role"
    )
    assert len(relationships) == 6
    relationship_by_id = {
        relationship["relationship_type_id"]: relationship
        for relationship in relationships
    }
    professor_company = _relationship(catalog, "professor_company_role")
    non_company_role = _relationship(
        catalog, "professor_held_role_at_non_company_organization"
    )
    team_member = _relationship(catalog, "company_has_team_member")
    module = _module()

    professor = _canonical_endpoint(module, "professor", "professor-1")
    company = _canonical_endpoint(module, "company", "company-1")
    institution = _registry_endpoint(module, "institution", "institution-1")
    team_professor = _canonical_endpoint(module, "professor", "professor-2")

    registries = {
        relationship_id: _retained_evidence(
            module,
            relationship_id,
            relationship["required_evidence_kinds"],
        )
        for relationship_id, relationship in relationship_by_id.items()
    }
    professor_company_evidence = registries["professor_company_role"][2]
    non_company_evidence = registries[
        "professor_held_role_at_non_company_organization"
    ][2]
    team_evidence = registries["company_has_team_member"][2]
    candidates = [
        module.RelationshipProjectionCandidate(
            candidate_id="valid:professor_company_role",
            relationship_type_id=professor_company["relationship_type_id"],
            relationship_type_version=professor_company["version"],
            source_endpoint=professor,
            target_endpoint=company,
            role_bindings={"founder": professor.stable_reference},
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=professor_company_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:generic-company-association",
            relationship_type_id=professor_company["relationship_type_id"],
            relationship_type_version=professor_company["version"],
            source_endpoint=professor,
            target_endpoint=company,
            role_bindings={"associate": professor.stable_reference},
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=professor_company_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:founder-role-bound-to-company",
            relationship_type_id=professor_company["relationship_type_id"],
            relationship_type_version=professor_company["version"],
            source_endpoint=professor,
            target_endpoint=company,
            role_bindings={"founder": company.stable_reference},
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=professor_company_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:professor_held_role_at_non_company_organization",
            relationship_type_id=non_company_role["relationship_type_id"],
            relationship_type_version=non_company_role["version"],
            source_endpoint=professor,
            target_endpoint=institution,
            role_bindings={"position_title": professor.stable_reference},
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=non_company_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:non-company-position-targets-company",
            relationship_type_id=non_company_role["relationship_type_id"],
            relationship_type_version=non_company_role["version"],
            source_endpoint=professor,
            target_endpoint=company,
            role_bindings={"position_title": professor.stable_reference},
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=non_company_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:company_has_team_member",
            relationship_type_id=team_member["relationship_type_id"],
            relationship_type_version=team_member["version"],
            source_endpoint=company,
            target_endpoint=team_professor,
            role_bindings={"team_role": team_professor.stable_reference},
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=team_evidence,
        ),
    ]
    for relationship_id, target_type in (
        ("professor_affiliated_with_institution", "institution"),
        ("professor_educated_at_institution", "institution"),
        ("professor_member_of_department", "department"),
    ):
        relationship = relationship_by_id[relationship_id]
        candidates.append(
            module.RelationshipProjectionCandidate(
                candidate_id=f"valid:{relationship_id}",
                relationship_type_id=relationship_id,
                relationship_type_version=relationship["version"],
                source_endpoint=professor,
                target_endpoint=_registry_endpoint(
                    module, target_type, f"{target_type}-1"
                ),
                role_bindings={},
                observed_at=NOW,
                source_event_time=None,
                valid_from=NOW,
                valid_to=None,
                evidence_bindings=registries[relationship_id][2],
            )
        )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-organization",
        candidates=tuple(candidates),
        retained_assertions=tuple(
            assertion
            for assertions, _, _ in registries.values()
            for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact
            for _, artifacts, _ in registries.values()
            for artifact in artifacts
        ),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    valid_outcomes = tuple(
        _outcome(result, f"valid:{relationship_id}")
        for relationship_id in relationship_by_id
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == set(
        relationship_by_id
    )
    assert all(outcome.admitted is True for outcome in valid_outcomes)
    _assert_canonical_decision_layers(request, result, "valid:professor_company_role")
    _assert_canonical_decision_layers(request, result, "valid:company_has_team_member")
    _assert_typed_decision_layers(
        request,
        result,
        "valid:professor_held_role_at_non_company_organization",
    )
    generic = _outcome(result, "invalid:generic-company-association")
    wrong_owner = _outcome(result, "invalid:founder-role-bound-to-company")
    wrong_target = _outcome(result, "invalid:non-company-position-targets-company")
    assert generic.admitted is False
    assert (
        "generic_association_without_a_supported_role_is_not_accepted"
        in generic.reason_codes
    )
    assert wrong_owner.admitted is False
    assert "role_ownership_mismatch" in wrong_owner.reason_codes
    assert wrong_target.admitted is False
    assert "company_targets_require_professor_company_role" in wrong_target.reason_codes

    tampered_assertion = next(
        assertion
        for assertion in request.relationship_assertions
        if assertion.assertion_id
        == "relationship-assertion:valid:professor_company_role"
    )
    tampered_assertion = tampered_assertion.model_copy(
        update={
            "attributes": {
                **tampered_assertion.attributes,
                "role_bindings": {"investor": professor.stable_reference},
            }
        }
    )
    tampered_request = request.model_copy(
        update={
            "relationship_assertions": tuple(
                tampered_assertion
                if assertion.assertion_id == tampered_assertion.assertion_id
                else assertion
                for assertion in request.relationship_assertions
            )
        }
    )
    tampered_result = module.create_ephemeral_relationship_projection().project(
        tampered_request
    )
    tampered = _outcome(tampered_result, "valid:professor_company_role")
    assert tampered.admitted is False
    assert "source_relationship_assertion_continuity_mismatch" in (
        tampered.reason_codes
    )


def test_scholarly_output_keeps_attribution_evidence_separate_from_identity() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "scholarly_output"
    )
    assert len(relationships) == 4
    relationship_by_id = {
        relationship["relationship_type_id"]: relationship
        for relationship in relationships
    }
    attribution = _relationship(catalog, "professor_attributed_to_paper")
    authorship = _relationship(catalog, "paper_has_author")
    module = _module()

    professor = _canonical_endpoint(module, "professor", "professor-1")
    paper = _canonical_endpoint(module, "paper", "paper-1")
    person = _registry_endpoint(module, "person", "author-1")
    registries = {
        relationship_id: _retained_evidence(
            module,
            relationship_id,
            relationship["required_evidence_kinds"],
        )
        for relationship_id, relationship in relationship_by_id.items()
    }
    attribution_evidence = registries["professor_attributed_to_paper"][2]
    author_evidence = registries["paper_has_author"][2]
    candidates = [
        module.RelationshipProjectionCandidate(
            candidate_id="valid:professor_attributed_to_paper",
            relationship_type_id=attribution["relationship_type_id"],
            relationship_type_version=attribution["version"],
            source_endpoint=professor,
            target_endpoint=paper,
            role_bindings={},
            evidence_metadata={
                "attribution_basis": (
                    "professor_page_declaration",
                    "verified_author_attribution",
                )
            },
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=attribution_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:attribution-basis-as-business-role",
            relationship_type_id=attribution["relationship_type_id"],
            relationship_type_version=attribution["version"],
            source_endpoint=professor,
            target_endpoint=paper,
            role_bindings={"page_declaration": professor.stable_reference},
            evidence_metadata={},
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=attribution_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="rejected:professor_attributed_to_paper",
            relationship_type_id=attribution["relationship_type_id"],
            relationship_type_version=attribution["version"],
            source_endpoint=professor,
            target_endpoint=paper,
            role_bindings={},
            evidence_metadata={"attribution_basis": ("professor_page_declaration",)},
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=attribution_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:paper_has_author",
            relationship_type_id=authorship["relationship_type_id"],
            relationship_type_version=authorship["version"],
            source_endpoint=paper,
            target_endpoint=person,
            role_bindings={"author": person.stable_reference},
            evidence_metadata={},
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=author_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:paper_published_in_venue",
            relationship_type_id="paper_published_in_venue",
            relationship_type_version=relationship_by_id["paper_published_in_venue"][
                "version"
            ],
            source_endpoint=paper,
            target_endpoint=_registry_endpoint(module, "venue", "venue-1"),
            role_bindings={},
            evidence_metadata={},
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries["paper_published_in_venue"][2],
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="valid:paper_references_paper",
            relationship_type_id="paper_references_paper",
            relationship_type_version=relationship_by_id["paper_references_paper"][
                "version"
            ],
            source_endpoint=paper,
            target_endpoint=_canonical_endpoint(module, "paper", "paper-2"),
            role_bindings={},
            evidence_metadata={},
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=registries["paper_references_paper"][2],
        ),
    ]
    request = _projection_request(
        module,
        run_id="relationship-projection-run-scholarly",
        candidates=tuple(candidates),
        retained_assertions=tuple(
            assertion
            for assertions, _, _ in registries.values()
            for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact
            for _, artifacts, _ in registries.values()
            for artifact in artifacts
        ),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    valid_outcomes = tuple(
        _outcome(result, f"valid:{relationship_id}")
        for relationship_id in relationship_by_id
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == set(
        relationship_by_id
    )
    assert all(outcome.admitted is True for outcome in valid_outcomes)
    _assert_canonical_decision_layers(
        request, result, "valid:professor_attributed_to_paper"
    )
    _assert_typed_decision_layers(request, result, "valid:paper_published_in_venue")
    role_conflation = _outcome(result, "invalid:attribution-basis-as-business-role")
    assert role_conflation.admitted is False
    assert (
        "attribution_basis_is_evidence_metadata_not_business_role"
        in role_conflation.reason_codes
    )
    rejected = _outcome(result, "rejected:professor_attributed_to_paper")
    assert rejected.admitted is True
    assert rejected.decision_state == "rejected"
    assert rejected.projected_relationship_id is None
    assert result.identity_state_changes == ()


def test_intellectual_property_preserves_applicant_and_inventor_semantics() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "intellectual_property"
    )
    assert len(relationships) == 3
    applicant = _relationship(catalog, "patent_has_applicant")
    inventor = _relationship(catalog, "patent_has_inventor")
    page_listing = _relationship(catalog, "professor_page_lists_patent")
    module = _module()

    patent = _canonical_endpoint(module, "patent", "patent-1")
    company = _canonical_endpoint(module, "company", "company-1")
    organization = _registry_endpoint(module, "organization", "organization-1")
    professor = _canonical_endpoint(module, "professor", "professor-1")
    person = _registry_endpoint(module, "person", "person-1")
    registries = [
        _retained_evidence(
            module, "patent-applicant", applicant["required_evidence_kinds"]
        ),
        _retained_evidence(
            module, "patent-inventor", inventor["required_evidence_kinds"]
        ),
        _retained_evidence(
            module, "professor-page-patent", page_listing["required_evidence_kinds"]
        ),
    ]
    applicant_evidence = registries[0][2]
    inventor_evidence = registries[1][2]
    page_evidence = registries[2][2]
    candidates = (
        module.RelationshipProjectionCandidate(
            candidate_id="company-is-patent-applicant",
            relationship_type_id=applicant["relationship_type_id"],
            relationship_type_version=applicant["version"],
            source_endpoint=patent,
            target_endpoint=company,
            role_bindings={"applicant": company.stable_reference},
            evidence_metadata={},
            requested_paths=("company_to_patent", "patent_to_company"),
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=applicant_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="applicant-relabeled-owner",
            relationship_type_id=applicant["relationship_type_id"],
            relationship_type_version=applicant["version"],
            source_endpoint=patent,
            target_endpoint=company,
            role_bindings={"owner": company.stable_reference},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=applicant_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="organization-on-company-path",
            relationship_type_id=applicant["relationship_type_id"],
            relationship_type_version=applicant["version"],
            source_endpoint=patent,
            target_endpoint=organization,
            role_bindings={"applicant": organization.stable_reference},
            evidence_metadata={},
            requested_paths=("company_to_patent",),
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=applicant_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="professor-is-patent-inventor",
            relationship_type_id=inventor["relationship_type_id"],
            relationship_type_version=inventor["version"],
            source_endpoint=patent,
            target_endpoint=professor,
            role_bindings={"inventor": professor.stable_reference},
            evidence_metadata={},
            requested_paths=("patent_to_professor", "professor_to_patent"),
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=inventor_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="person-on-professor-path",
            relationship_type_id=inventor["relationship_type_id"],
            relationship_type_version=inventor["version"],
            source_endpoint=patent,
            target_endpoint=person,
            role_bindings={"inventor": person.stable_reference},
            evidence_metadata={},
            requested_paths=("patent_to_professor",),
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=inventor_evidence,
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="professor-page-lists-patent",
            relationship_type_id=page_listing["relationship_type_id"],
            relationship_type_version=page_listing["version"],
            source_endpoint=professor,
            target_endpoint=patent,
            role_bindings={},
            evidence_metadata={"declaration_kind": "professor_page"},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=page_evidence,
        ),
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-ip",
        candidates=candidates,
        retained_assertions=tuple(
            assertion for assertions, _, _ in registries for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact for _, artifacts, _ in registries for artifact in artifacts
        ),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    valid_candidate_ids = {
        "company-is-patent-applicant",
        "professor-is-patent-inventor",
        "professor-page-lists-patent",
    }
    valid_outcomes = tuple(
        _outcome(result, candidate_id) for candidate_id in valid_candidate_ids
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == {
        relationship["relationship_type_id"] for relationship in relationships
    }
    assert all(outcome.admitted is True for outcome in valid_outcomes)
    _assert_canonical_decision_layers(request, result, "company-is-patent-applicant")
    owner = _outcome(result, "applicant-relabeled-owner")
    company_path = _outcome(result, "organization-on-company-path")
    professor_path = _outcome(result, "person-on-professor-path")
    assert owner.admitted is False
    assert "applicant_not_owner_or_assignee" in owner.reason_codes
    assert company_path.admitted is False
    assert (
        "company_paths_require_target_type_company_and_accepted_company_identity"
        in company_path.reason_codes
    )
    assert professor_path.admitted is False
    assert (
        "professor_paths_require_target_type_professor_and_accepted_professor_identity"
        in professor_path.reason_codes
    )
    assert result.inferred_relationship_type_ids == ()


def test_company_business_product_event_uses_catalog_time_semantics() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "company_business_product_event"
    )
    assert len(relationships) == 5
    module = _module()

    company = _canonical_endpoint(module, "company", "company-1")
    registries = [
        _retained_evidence(
            module,
            relationship["relationship_type_id"],
            relationship["required_evidence_kinds"],
        )
        for relationship in relationships
    ]
    candidates = []
    for relationship, (_, _, evidence) in zip(relationships, registries, strict=True):
        endpoint_type = relationship["target_entity_types"][0]
        candidates.append(
            module.RelationshipProjectionCandidate(
                candidate_id=f"valid:{relationship['relationship_type_id']}",
                relationship_type_id=relationship["relationship_type_id"],
                relationship_type_version=relationship["version"],
                source_endpoint=company,
                target_endpoint=_subobject_endpoint(
                    module,
                    endpoint_type,
                    f"{endpoint_type}-1",
                    parent_canonical_identity_ref=company.stable_reference,
                ),
                role_bindings={},
                evidence_metadata={},
                requested_paths=(),
                observed_at=NOW,
                source_event_time=(
                    NOW if relationship["time_semantics"] == "event_time" else None
                ),
                valid_from=(
                    NOW
                    if relationship["time_semantics"] == "validity_interval"
                    else None
                ),
                valid_to=None,
                evidence_bindings=evidence,
            )
        )
    financing = _relationship(catalog, "company_has_financing_event")
    financing_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"] == financing["relationship_type_id"]
    )
    candidates.append(
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:financing-as-validity-interval",
            relationship_type_id=financing["relationship_type_id"],
            relationship_type_version=financing["version"],
            source_endpoint=company,
            target_endpoint=_subobject_endpoint(
                module,
                "financing_event",
                "financing-event-invalid",
                parent_canonical_identity_ref=company.stable_reference,
            ),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=financing_evidence,
        )
    )
    product = _relationship(catalog, "company_has_product")
    product_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"] == product["relationship_type_id"]
    )
    product_index = next(
        index
        for index, candidate in enumerate(candidates)
        if candidate.relationship_type_id == product["relationship_type_id"]
    )
    capability = _relationship(catalog, "company_has_capability")
    capability_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"] == capability["relationship_type_id"]
    )
    candidates.insert(
        product_index,
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:typed-subobject-type-mismatch",
            relationship_type_id=capability["relationship_type_id"],
            relationship_type_version=capability["version"],
            source_endpoint=company,
            target_endpoint=module.RelationshipEndpointReference(
                reference_kind="typed_subobject",
                endpoint_type="capability",
                stable_reference="subobject:product:product-1",
                canonical_identity_id=None,
                parent_canonical_identity_ref=company.stable_reference,
            ),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=capability_evidence,
        ),
    )
    candidates.append(
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:dangling-domain-endpoint:typed-subobject",
            relationship_type_id=product["relationship_type_id"],
            relationship_type_version=product["version"],
            source_endpoint=company,
            target_endpoint=_subobject_endpoint(
                module,
                "product",
                "product-not-projected",
                parent_canonical_identity_ref=company.stable_reference,
            ),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=product_evidence,
        )
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-company-business",
        candidates=tuple(candidates),
        retained_assertions=tuple(
            assertion for assertions, _, _ in registries for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact for _, artifacts, _ in registries for artifact in artifacts
        ),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    valid_outcomes = tuple(
        _outcome(result, f"valid:{relationship['relationship_type_id']}")
        for relationship in relationships
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == {
        relationship["relationship_type_id"] for relationship in relationships
    }
    for relationship in relationships:
        outcome = _outcome(result, f"valid:{relationship['relationship_type_id']}")
        assert outcome.admitted is True
        assert outcome.effective_time_semantics == relationship["time_semantics"]
        assert outcome.target_reference_kind == "typed_subobject"
        assert outcome.target_parent_canonical_identity_ref == company.stable_reference
    _assert_typed_decision_layers(
        request, result, f"valid:{relationships[0]['relationship_type_id']}"
    )
    invalid_time = _outcome(result, "invalid:financing-as-validity-interval")
    dangling_subobject = _outcome(
        result, "invalid:dangling-domain-endpoint:typed-subobject"
    )
    wrong_subobject_type = _outcome(result, "invalid:typed-subobject-type-mismatch")
    assert invalid_time.admitted is False
    assert "invalid_time_semantics" in invalid_time.reason_codes
    assert dangling_subobject.admitted is False
    assert "typed_subobject_not_in_domain_projection" in (
        dangling_subobject.reason_codes
    )
    assert wrong_subobject_type.admitted is False
    assert "typed_subobject_not_in_domain_projection" in (
        wrong_subobject_type.reason_codes
    )

    date_assertions, date_artifacts, date_evidence = _retained_evidence(
        module,
        "company-product-date",
        product["required_evidence_kinds"],
    )
    date_candidate = module.RelationshipProjectionCandidate(
        candidate_id="valid:company_has_product:date-only",
        relationship_type_id=product["relationship_type_id"],
        relationship_type_version=product["version"],
        source_endpoint=company,
        target_endpoint=_subobject_endpoint(
            module,
            "product",
            "product-date-only",
            parent_canonical_identity_ref=company.stable_reference,
        ),
        role_bindings={},
        evidence_metadata={},
        requested_paths=(),
        observed_at=NOW,
        source_event_time=None,
        valid_from=date(2026, 7, 12),
        valid_to=None,
        evidence_bindings=date_evidence,
    )
    no_context_request = _projection_request(
        module,
        run_id="relationship-projection-run-date-no-context",
        candidates=(date_candidate,),
        retained_assertions=date_assertions,
        retained_artifacts=date_artifacts,
    )
    no_context_result = module.create_ephemeral_relationship_projection().project(
        no_context_request
    )
    no_context = _outcome(no_context_result, "valid:company_has_product:date-only")
    assert no_context.admitted is True
    assert no_context.current_projection_state == "indeterminate"
    assert "explicit_calendar_context_required" in (
        no_context.current_projection_reason_codes
    )
    assert no_context.projected_relationship_id is None

    explicit_context_request = _projection_request(
        module,
        run_id="relationship-projection-run-date-context",
        candidates=(date_candidate,),
        retained_assertions=date_assertions,
        retained_artifacts=date_artifacts,
        temporal_comparison_context=TemporalComparisonContext(timezone="Asia/Shanghai"),
    )
    explicit_context_result = module.create_ephemeral_relationship_projection().project(
        explicit_context_request
    )
    explicit_context = _outcome(
        explicit_context_result, "valid:company_has_product:date-only"
    )
    assert explicit_context.admitted is True
    assert explicit_context.current_projection_state == "current"
    assert explicit_context.current_projection_reason_codes == ()
    assert explicit_context.projected_relationship_id is not None

    with pytest.raises(
        ValueError,
        match="valid_from and valid_to must have the same temporal precision",
    ):
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:mixed-temporal-precision",
            relationship_type_id=product["relationship_type_id"],
            relationship_type_version=product["version"],
            source_endpoint=company,
            target_endpoint=_subobject_endpoint(
                module,
                "product",
                "product-mixed-time",
                parent_canonical_identity_ref=company.stable_reference,
            ),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=date(2026, 7, 12),
            valid_to=NOW,
            evidence_bindings=date_evidence,
        )


def test_taxonomy_topic_geography_keeps_typed_noncanonical_targets() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "taxonomy_topic_geography"
    )
    assert len(relationships) == 5
    module = _module()

    registries = [
        _retained_evidence(
            module,
            relationship["relationship_type_id"],
            relationship["required_evidence_kinds"],
        )
        for relationship in relationships
    ]
    candidates = []
    endpoints: dict[str, tuple[Any, Any]] = {}
    for relationship, (_, _, evidence) in zip(relationships, registries, strict=True):
        source_type = relationship["source_entity_types"][0]
        target_type = relationship["target_entity_types"][0]
        source = _canonical_endpoint(module, source_type, f"{source_type}-1")
        target = _registry_endpoint(module, target_type, f"{target_type}-1")
        endpoints[relationship["relationship_type_id"]] = (source, target)
        candidates.append(
            module.RelationshipProjectionCandidate(
                candidate_id=f"valid:{relationship['relationship_type_id']}",
                relationship_type_id=relationship["relationship_type_id"],
                relationship_type_version=relationship["version"],
                source_endpoint=source,
                target_endpoint=target,
                role_bindings={},
                evidence_metadata={},
                requested_paths=(),
                observed_at=NOW,
                source_event_time=None,
                valid_from=(
                    NOW
                    if relationship["time_semantics"] == "validity_interval"
                    else None
                ),
                valid_to=None,
                evidence_bindings=evidence,
            )
        )
    ipc = _relationship(catalog, "patent_has_ipc_classification")
    ipc_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"] == ipc["relationship_type_id"]
    )
    ipc_source, ipc_target = endpoints[ipc["relationship_type_id"]]
    candidates.append(
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:ipc-with-validity",
            relationship_type_id=ipc["relationship_type_id"],
            relationship_type_version=ipc["version"],
            source_endpoint=ipc_source,
            target_endpoint=ipc_target,
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=ipc_evidence,
        )
    )
    industry = _relationship(catalog, "company_in_industry")
    industry_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"] == industry["relationship_type_id"]
    )
    industry_source, industry_target = endpoints[industry["relationship_type_id"]]
    candidates.append(
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:industry-reversed",
            relationship_type_id=industry["relationship_type_id"],
            relationship_type_version=industry["version"],
            source_endpoint=industry_target,
            target_endpoint=industry_source,
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=industry_evidence,
        )
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-taxonomy",
        candidates=tuple(candidates),
        retained_assertions=tuple(
            assertion for assertions, _, _ in registries for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact for _, artifacts, _ in registries for artifact in artifacts
        ),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    valid_outcomes = tuple(
        _outcome(result, f"valid:{relationship['relationship_type_id']}")
        for relationship in relationships
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == {
        relationship["relationship_type_id"] for relationship in relationships
    }
    for relationship in relationships:
        outcome = _outcome(result, f"valid:{relationship['relationship_type_id']}")
        assert outcome.admitted is True
        assert outcome.target_reference_kind == "registry_entity"
        assert outcome.target_canonical_identity_id is None
        assert outcome.target_parent_canonical_identity_ref is None
    _assert_typed_decision_layers(
        request, result, f"valid:{relationships[0]['relationship_type_id']}"
    )
    invalid_time = _outcome(result, "invalid:ipc-with-validity")
    reversed_endpoint = _outcome(result, "invalid:industry-reversed")
    assert invalid_time.admitted is False
    assert "invalid_time_semantics" in invalid_time.reason_codes
    assert reversed_endpoint.admitted is False
    assert "endpoint_type_not_allowed" in reversed_endpoint.reason_codes

    typed_candidate = next(
        candidate
        for candidate in request.candidates
        if candidate.candidate_id == f"valid:{relationships[0]['relationship_type_id']}"
    )
    tampered_decision = next(
        decision
        for decision in request.decision_inputs
        if decision.decision_input_id == typed_candidate.decision_input_id
    ).model_copy(update={"selected_assertion_ids": ()})
    tampered_request = request.model_copy(
        update={
            "decision_inputs": tuple(
                tampered_decision
                if decision.decision_input_id == tampered_decision.decision_input_id
                else decision
                for decision in request.decision_inputs
            )
        }
    )
    tampered_result = module.create_ephemeral_relationship_projection().project(
        tampered_request
    )
    tampered = _outcome(tampered_result, typed_candidate.candidate_id)
    assert tampered.admitted is False
    assert "relationship_decision_input_continuity_mismatch" in (tampered.reason_codes)


def test_evidence_lineage_uses_retained_metadata_references() -> None:
    catalog = _catalog()
    relationships = tuple(
        relationship
        for relationship in catalog["relationships"]
        if relationship["family"] == "evidence_lineage"
    )
    assert len(relationships) == 6
    module = _module()

    registries = [
        _retained_evidence(
            module,
            relationship["relationship_type_id"],
            relationship["required_evidence_kinds"],
        )
        for relationship in relationships
    ]
    candidates = []
    for relationship, (_, _, evidence) in zip(relationships, registries, strict=True):
        source_type = relationship["source_entity_types"][0]
        target_type = relationship["target_entity_types"][0]
        candidates.append(
            module.RelationshipProjectionCandidate(
                candidate_id=f"valid:{relationship['relationship_type_id']}",
                relationship_type_id=relationship["relationship_type_id"],
                relationship_type_version=relationship["version"],
                source_endpoint=_lineage_endpoint(
                    module,
                    source_type,
                    f"{relationship['relationship_type_id']}:source",
                    lineage_family=(
                        "field"
                        if relationship["relationship_type_id"]
                        == "canonical_decision_selects_assertion"
                        else None
                    ),
                    subject_reference="canonical:professor:1",
                ),
                target_endpoint=_lineage_endpoint(
                    module,
                    target_type,
                    f"{relationship['relationship_type_id']}:target",
                    lineage_family=(
                        "field"
                        if relationship["relationship_type_id"]
                        == "canonical_decision_selects_assertion"
                        else None
                    ),
                    subject_reference="canonical:professor:1",
                ),
                role_bindings={},
                evidence_metadata={},
                requested_paths=(),
                observed_at=NOW,
                source_event_time=(
                    NOW if relationship["time_semantics"] == "event_time" else None
                ),
                valid_from=None,
                valid_to=None,
                evidence_bindings=evidence,
            )
        )
    selection = _relationship(catalog, "canonical_decision_selects_assertion")
    selection_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"] == selection["relationship_type_id"]
    )
    candidates.append(
        module.RelationshipProjectionCandidate(
            candidate_id="invalid:decision-assertion-cross-family",
            relationship_type_id=selection["relationship_type_id"],
            relationship_type_version=selection["version"],
            source_endpoint=_lineage_endpoint(
                module,
                "field_decision",
                "field-decision-1",
                lineage_family="field",
                subject_reference="canonical:professor:1",
            ),
            target_endpoint=_lineage_endpoint(
                module,
                "relationship_assertion",
                "relationship-assertion-1",
                lineage_family="relationship",
                subject_reference="canonical:company:1",
            ),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=selection_evidence,
        )
    )
    artifact_lineage = _relationship(catalog, "artifact_derived_from_artifact")
    artifact_evidence = next(
        evidence
        for relationship, (_, _, evidence) in zip(
            relationships, registries, strict=True
        )
        if relationship["relationship_type_id"]
        == artifact_lineage["relationship_type_id"]
    )
    candidates.append(
        module.RelationshipProjectionCandidate(
            candidate_id="rejected:artifact-lineage-disallowed-state",
            relationship_type_id=artifact_lineage["relationship_type_id"],
            relationship_type_version=artifact_lineage["version"],
            source_endpoint=_lineage_endpoint(module, "artifact", "derived"),
            target_endpoint=_lineage_endpoint(module, "artifact", "parent"),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=artifact_evidence,
        )
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-lineage",
        candidates=tuple(candidates),
        retained_assertions=tuple(
            assertion for assertions, _, _ in registries for assertion in assertions
        ),
        retained_artifacts=tuple(
            artifact for _, artifacts, _ in registries for artifact in artifacts
        ),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    valid_outcomes = tuple(
        _outcome(result, f"valid:{relationship['relationship_type_id']}")
        for relationship in relationships
    )
    assert {outcome.relationship_type_id for outcome in valid_outcomes} == {
        relationship["relationship_type_id"] for relationship in relationships
    }
    for relationship in relationships:
        outcome = _outcome(result, f"valid:{relationship['relationship_type_id']}")
        assert outcome.admitted is True
        assert outcome.source_reference_kind == "lineage_record"
        assert outcome.target_reference_kind == "lineage_record"
        assert outcome.source_canonical_identity_id is None
        assert outcome.target_canonical_identity_id is None
        _assert_typed_decision_layers(
            request, result, f"valid:{relationship['relationship_type_id']}"
        )
    mismatch = _outcome(result, "invalid:decision-assertion-cross-family")
    wrong_state = _outcome(result, "rejected:artifact-lineage-disallowed-state")
    assert mismatch.admitted is False
    assert (
        "decision_and_assertion_families_and_subjects_must_match"
        in mismatch.reason_codes
    )
    assert wrong_state.admitted is False
    assert "state_not_allowed" in wrong_state.reason_codes


def test_cross_domain_directions_validate_orientation_without_fabricating_edges() -> (
    None
):
    catalog = _catalog()
    scenarios = tuple(
        scenario
        for scenario in catalog["scenario_accounting"]
        if scenario["scenario_kind"] == "traversal_direction"
    )
    assert len(scenarios) == 8
    module = _module()

    probes = []
    for scenario in scenarios:
        direction = scenario["scenario_id"].removeprefix("traversal_scenario.")
        source_type, target_type = direction.split("_to_", maxsplit=1)
        probes.append(
            module.RelationshipDirectionProbe(
                probe_id=scenario["scenario_id"],
                scenario_id=scenario["scenario_id"],
                source_endpoint=_canonical_endpoint(
                    module, source_type, f"{source_type}-direction-source"
                ),
                target_endpoint=_canonical_endpoint(
                    module, target_type, f"{target_type}-direction-target"
                ),
                relationship_type_ids=tuple(scenario["relationship_type_ids"]),
                retained_relationship_refs=(),
            )
        )
    first = scenarios[0]
    first_direction = first["scenario_id"].removeprefix("traversal_scenario.")
    first_source_type, first_target_type = first_direction.split("_to_", maxsplit=1)
    probes.append(
        module.RelationshipDirectionProbe(
            probe_id="invalid:reversed-direction",
            scenario_id=first["scenario_id"],
            source_endpoint=_canonical_endpoint(
                module, first_target_type, f"{first_target_type}-wrong-source"
            ),
            target_endpoint=_canonical_endpoint(
                module, first_source_type, f"{first_source_type}-wrong-target"
            ),
            relationship_type_ids=tuple(first["relationship_type_ids"]),
            retained_relationship_refs=(),
        )
    )
    probes.append(
        module.RelationshipDirectionProbe(
            probe_id="invalid:dangling-domain-endpoint:direction",
            scenario_id=first["scenario_id"],
            source_endpoint=_canonical_endpoint(
                module, first_source_type, f"{first_source_type}-missing"
            ),
            target_endpoint=_canonical_endpoint(
                module, first_target_type, f"{first_target_type}-missing"
            ),
            relationship_type_ids=tuple(first["relationship_type_ids"]),
            retained_relationship_refs=(),
        )
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-directions",
        candidates=(),
        direction_probes=tuple(probes),
        retained_assertions=(),
        retained_artifacts=(),
    )
    assert all(not hasattr(probe, "source_potential_outcome") for probe in probes)

    result = module.create_ephemeral_relationship_projection().project(request)

    assert len(result.direction_outcomes) == 10
    outcomes = {outcome.probe_id: outcome for outcome in result.direction_outcomes}
    assert len(outcomes) == 10
    for scenario in scenarios:
        outcome = outcomes[scenario["scenario_id"]]
        assert outcome.orientation_valid is True
        assert outcome.source_potential_outcome == scenario["evidence_outcome"]
        assert outcome.available is False
        assert outcome.projected_relationship_ids == ()
    reversed_direction = outcomes["invalid:reversed-direction"]
    assert reversed_direction.orientation_valid is False
    assert "direction_orientation_mismatch" in reversed_direction.reason_codes
    assert reversed_direction.available is False
    dangling = outcomes["invalid:dangling-domain-endpoint:direction"]
    assert dangling.orientation_valid is False
    assert "canonical_endpoint_not_in_domain_projection" in dangling.reason_codes
    assert dangling.available is False
    assert result.path_eligibility_results == ()


def test_layers_and_source_potential_never_fabricate_canonical_facts() -> None:
    catalog = _catalog()
    layer_contracts = {item["layer"]: item for item in catalog["layer_contracts"]}
    assert set(layer_contracts) == {"canonical", "derived", "session"}
    assert layer_contracts["canonical"]["required_evidence_policy"] == "required"
    assert layer_contracts["derived"]["required_evidence_policy"] == "forbidden"
    assert layer_contracts["session"]["required_evidence_policy"] == "forbidden"
    outcome_counts = {
        outcome: sum(
            scenario["evidence_outcome"] == outcome
            for scenario in catalog["scenario_accounting"]
        )
        for outcome in ("supported", "insufficient_evidence", "absent")
    }
    assert outcome_counts == {
        "supported": 33,
        "insufficient_evidence": 7,
        "absent": 2,
    }
    module = _module()

    company_product = _relationship(catalog, "company_has_product")
    paper_reference = _relationship(catalog, "paper_references_paper")
    identity_split = _relationship(catalog, "canonical_identity_split_from")
    company = _canonical_endpoint(module, "company", "company-1")
    paper_1 = _canonical_endpoint(module, "paper", "paper-1")
    paper_2 = _canonical_endpoint(module, "paper", "paper-2")
    candidates = (
        module.RelationshipProjectionCandidate(
            candidate_id="source-potential:supported",
            relationship_type_id=company_product["relationship_type_id"],
            relationship_type_version=company_product["version"],
            source_endpoint=company,
            target_endpoint=_subobject_endpoint(
                module,
                "product",
                "product-1",
                parent_canonical_identity_ref=company.stable_reference,
            ),
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            catalog_scenario_id="catalog_scenario.company_has_product",
            observed_at=NOW,
            source_event_time=None,
            valid_from=NOW,
            valid_to=None,
            evidence_bindings=(),
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="source-potential:absent",
            relationship_type_id=paper_reference["relationship_type_id"],
            relationship_type_version=paper_reference["version"],
            source_endpoint=paper_1,
            target_endpoint=paper_2,
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            catalog_scenario_id="catalog_scenario.paper_references_paper",
            observed_at=NOW,
            source_event_time=None,
            valid_from=None,
            valid_to=None,
            evidence_bindings=(),
        ),
        module.RelationshipProjectionCandidate(
            candidate_id="source-potential:insufficient",
            relationship_type_id=identity_split["relationship_type_id"],
            relationship_type_version=identity_split["version"],
            source_endpoint=paper_1,
            target_endpoint=paper_2,
            role_bindings={},
            evidence_metadata={},
            requested_paths=(),
            catalog_scenario_id="catalog_scenario.canonical_identity_split_from",
            observed_at=NOW,
            source_event_time=NOW,
            valid_from=None,
            valid_to=None,
            evidence_bindings=(),
        ),
    )
    layer_probes = (
        module.RelationshipLayerProbe(
            layer="derived",
            stable_reference="derived:paper-similarity:1",
            attempt_canonical_projection=True,
            evidence_bindings=(),
        ),
        module.RelationshipLayerProbe(
            layer="session",
            stable_reference="session:displayed-set:1",
            attempt_canonical_projection=True,
            evidence_bindings=(),
        ),
    )
    request = _projection_request(
        module,
        run_id="relationship-projection-run-layers",
        candidates=candidates,
        direction_probes=(),
        layer_probes=layer_probes,
        retained_assertions=(),
        retained_artifacts=(),
    )

    result = module.create_ephemeral_relationship_projection().project(request)

    expected_potential = {
        "source-potential:supported": "supported",
        "source-potential:absent": "absent",
        "source-potential:insufficient": "insufficient_evidence",
    }
    for candidate in candidates:
        assert not hasattr(candidate, "source_potential_outcome")
        outcome = _outcome(result, candidate.candidate_id)
        assert (
            outcome.source_potential_outcome
            == expected_potential[candidate.candidate_id]
        )
        assert outcome.admitted is False
        assert "missing_required_evidence_kind" in outcome.reason_codes
        assert "source_potential_is_not_accepted_evidence" in outcome.reason_codes
        assert outcome.projected_relationship_id is None
    assert {outcome.layer for outcome in result.layer_outcomes} == {
        "derived",
        "session",
    }
    assert all(
        outcome.canonical_projection_allowed is False
        for outcome in result.layer_outcomes
    )
    assert all(
        "noncanonical_layer_cannot_project_canonical_fact" in outcome.reason_codes
        for outcome in result.layer_outcomes
    )
    assert result.current_relationships == ()
