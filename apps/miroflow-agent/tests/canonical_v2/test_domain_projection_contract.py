from __future__ import annotations

import builtins
from collections.abc import Iterator, Mapping, ValuesView
from datetime import date, datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
from pathlib import Path
import sys
from typing import Any

from pydantic import BaseModel
import pytest

from src.data_agents.canonical_v2.canonical_decision_engine import (
    CurrentFieldSelection,
)
from src.data_agents.canonical_v2.canonical_identity_resolution import (
    SourceIdentityAssignment,
)
from src.data_agents.canonical_v2.contracts import CanonicalDecision
from src.data_agents.canonical_v2.contracts import CanonicalIdentity
from src.data_agents.canonical_v2.contracts import CanonicalIdentityState
from src.data_agents.canonical_v2.contracts import DecisionMethod
from src.data_agents.canonical_v2.contracts import DecisionState
from src.data_agents.canonical_v2.contracts import PolicyDecision
from src.data_agents.canonical_v2.contracts import PolicyKind
from src.data_agents.canonical_v2.contracts import PolicyOutcome
from src.data_agents.canonical_v2.contracts import PolicyReference
from src.data_agents.canonical_v2.contracts import SourceAssertion
from src.data_agents.canonical_v2.contracts import TemporalDateValue
from src.data_agents.canonical_v2.domain_inclusion import (
    create_domain_inclusion_result,
)
from src.data_agents.canonical_v2.domain_catalog import (
    CATALOG_CONTENT_SHA256 as INSTALLED_CATALOG_CONTENT_SHA256,
)


TARGET_MODULE = "src.data_agents.canonical_v2.domain_projection"
NOW = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s6-domain-projection-r1"
RUN_ID = "domain-projection-run-1"
PROJECTION_VERSION = "domain-projection-v1"
REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG_EVIDENCE_PATH = (
    REPO_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s6/domain-catalog-v1.json"
)


def _module() -> Any:
    return import_module(TARGET_MODULE)


def _accepted_catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _catalog_value(catalog: Any, key: str) -> Any:
    if isinstance(catalog, dict):
        return catalog[key]
    return getattr(catalog, key)


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


def _rehashed_result_payload(result: Any, **updates: Any) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload.update(updates)
    payload.pop("content_sha256")
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def _policy(kind: PolicyKind) -> PolicyReference:
    return PolicyReference(
        policy_id=f"canonical-v2-{kind.value}",
        policy_version=f"{kind.value}-v1",
        policy_kind=kind,
        content_sha256="3" * 64,
        effective_at=NOW - timedelta(days=1),
    )


def _company_inputs() -> dict[str, tuple[Any, ...]]:
    identity_id = "company-c1"
    source_identity_id = "source-company-1"
    identity_decision_id = "identity-decision:company-c1"
    identity = CanonicalIdentity(
        canonical_identity_id=identity_id,
        entity_type="company",
        state=CanonicalIdentityState.active,
        display_name="Shenzhen Quantum Works",
        source_identity_ids=(source_identity_id,),
        identity_decision_id=identity_decision_id,
        release_id=RELEASE_ID,
    )
    assignment = SourceIdentityAssignment(
        release_id=RELEASE_ID,
        source_identity_id=source_identity_id,
        canonical_identity_id=identity_id,
        identity_decision_id=identity_decision_id,
    )
    selected_values = {
        "name": "Shenzhen Quantum Works",
        "normalized_name": "shenzhen quantum works",
        "profile_summary": "Builds evidence-backed quantum sensing products.",
        "technology_route_summary": "Integrated photonic quantum sensing.",
    }
    assertions: list[SourceAssertion] = []
    decisions: list[CanonicalDecision] = []
    current_fields: list[CurrentFieldSelection] = []
    for field_path, value in selected_values.items():
        assertion_id = f"assertion:company-c1:{field_path}"
        decision_id = f"field-decision:company-c1:{field_path}"
        assertion = SourceAssertion(
            assertion_id=assertion_id,
            source_record_id="record:company-c1",
            source_identity_id=source_identity_id,
            subject_entity_type="company",
            field_path=field_path,
            value=value,
            observed_at=NOW - timedelta(hours=1),
            assertion_run_id="assertion-run-1",
        )
        decision = CanonicalDecision(
            decision_id=decision_id,
            canonical_identity_id=identity_id,
            field_path=field_path,
            state=DecisionState.selected,
            candidate_assertion_ids=(assertion_id,),
            selected_assertion_ids=(assertion_id,),
            conflicting_assertion_ids=(),
            policy=_policy(PolicyKind.field_selection),
            method=DecisionMethod.deterministic,
            method_version="field-selection-v1",
            decision_run_id="field-selection-run-1",
            confidence=1.0,
            rationale="Single valid retained assertion.",
            release_id=RELEASE_ID,
            decided_at=NOW - timedelta(minutes=30),
        )
        current = CurrentFieldSelection(
            release_id=RELEASE_ID,
            canonical_identity_id=identity_id,
            field_path=field_path,
            value=value,
            decision_id=decision_id,
            supporting_assertion_ids=(assertion_id,),
        )
        assertions.append(assertion)
        decisions.append(decision)
        current_fields.append(current)
    inclusion = PolicyDecision(
        decision_id="inclusion:company-c1",
        policy=_policy(PolicyKind.inclusion),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        path=None,
        outcome=PolicyOutcome.admitted,
        supporting_assertion_ids=tuple(
            assertion.assertion_id for assertion in assertions
        ),
        evaluated_at=NOW - timedelta(minutes=15),
    )
    return {
        "canonical_identities": (identity,),
        "source_identity_assignments": (assignment,),
        "source_assertions": tuple(assertions),
        "canonical_decisions": tuple(decisions),
        "current_fields": tuple(current_fields),
        "inclusion_decisions": (inclusion,),
    }


def _replicated_company_inputs(count: int) -> dict[str, tuple[Any, ...]]:
    base = _company_inputs()
    replicated: dict[str, list[Any]] = {key: [] for key in base}
    for index in range(count):
        suffix = f":bulk-{index:03d}"

        def suffixed(value: str) -> str:
            return f"{value}{suffix}"

        identity = base["canonical_identities"][0]
        assignment = base["source_identity_assignments"][0]
        assertions = base["source_assertions"]
        decisions = base["canonical_decisions"]
        current_fields = base["current_fields"]
        inclusion = base["inclusion_decisions"][0]
        assertion_ids = {
            assertion.assertion_id: suffixed(assertion.assertion_id)
            for assertion in assertions
        }

        replicated["canonical_identities"].append(
            identity.model_copy(
                update={
                    "canonical_identity_id": suffixed(identity.canonical_identity_id),
                    "source_identity_ids": tuple(
                        suffixed(value) for value in identity.source_identity_ids
                    ),
                    "identity_decision_id": suffixed(identity.identity_decision_id),
                }
            )
        )
        replicated["source_identity_assignments"].append(
            assignment.model_copy(
                update={
                    "source_identity_id": suffixed(assignment.source_identity_id),
                    "canonical_identity_id": suffixed(assignment.canonical_identity_id),
                    "identity_decision_id": suffixed(assignment.identity_decision_id),
                }
            )
        )
        replicated["source_assertions"].extend(
            assertion.model_copy(
                update={
                    "assertion_id": assertion_ids[assertion.assertion_id],
                    "source_record_id": suffixed(assertion.source_record_id),
                    "source_identity_id": suffixed(assertion.source_identity_id),
                    "assertion_run_id": suffixed(assertion.assertion_run_id),
                }
            )
            for assertion in assertions
        )
        replicated["canonical_decisions"].extend(
            decision.model_copy(
                update={
                    "decision_id": suffixed(decision.decision_id),
                    "canonical_identity_id": suffixed(decision.canonical_identity_id),
                    "candidate_assertion_ids": tuple(
                        assertion_ids[value]
                        for value in decision.candidate_assertion_ids
                    ),
                    "selected_assertion_ids": tuple(
                        assertion_ids[value]
                        for value in decision.selected_assertion_ids
                    ),
                    "conflicting_assertion_ids": tuple(
                        assertion_ids[value]
                        for value in decision.conflicting_assertion_ids
                    ),
                    "decision_run_id": suffixed(decision.decision_run_id),
                }
            )
            for decision in decisions
        )
        replicated["current_fields"].extend(
            current.model_copy(
                update={
                    "canonical_identity_id": suffixed(current.canonical_identity_id),
                    "decision_id": suffixed(current.decision_id),
                    "supporting_assertion_ids": tuple(
                        assertion_ids[value]
                        for value in current.supporting_assertion_ids
                    ),
                }
            )
            for current in current_fields
        )
        replicated["inclusion_decisions"].append(
            inclusion.model_copy(
                update={
                    "decision_id": suffixed(inclusion.decision_id),
                    "subject_identity_id": suffixed(inclusion.subject_identity_id),
                    "supporting_assertion_ids": tuple(
                        assertion_ids[value]
                        for value in inclusion.supporting_assertion_ids
                    ),
                }
            )
        )
    return {key: tuple(values) for key, values in replicated.items()}


def _paper_inputs() -> dict[str, tuple[Any, ...]]:
    identity_id = "paper-c1"
    source_identity_id = "source-paper-1"
    identity_decision_id = "identity-decision:paper-c1"
    identity = CanonicalIdentity(
        canonical_identity_id=identity_id,
        entity_type="paper",
        state=CanonicalIdentityState.active,
        display_name="Traceable Knowledge Graphs",
        source_identity_ids=(source_identity_id,),
        identity_decision_id=identity_decision_id,
        release_id=RELEASE_ID,
    )
    assignment = SourceIdentityAssignment(
        release_id=RELEASE_ID,
        source_identity_id=source_identity_id,
        canonical_identity_id=identity_id,
        identity_decision_id=identity_decision_id,
    )
    author_assertion_id = "assertion:paper-c1:authors"
    author_decision_id = "field-decision:paper-c1:authors"
    publication_assertion_id = "assertion:paper-c1:publication"
    publication_decision_id = "field-decision:paper-c1:publication"
    selected_values: dict[str, Any] = {
        "authors": [
            {
                "subobject_id": "paper-author:paper-c1:1",
                "parent_canonical_identity_id": identity_id,
                "supporting_assertion_ids": [author_assertion_id],
                "decision_ids": [author_decision_id],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "name": "Ada Chen",
                "author_order": 1,
            }
        ],
        "title": "Traceable Knowledge Graphs",
        "venue": {"reference_id": "venue-1", "name": "Evidence Journal"},
        "year": 2025,
        "publication": [
            {
                "subobject_id": "paper-publication:paper-c1:1",
                "parent_canonical_identity_id": identity_id,
                "supporting_assertion_ids": [publication_assertion_id],
                "decision_ids": [publication_decision_id],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "venue": {
                    "reference_id": "venue-1",
                    "name": "Evidence Journal",
                },
                "publication_date": "2025-05-02",
                "year": 2025,
            }
        ],
    }
    assertions: list[SourceAssertion] = []
    decisions: list[CanonicalDecision] = []
    current_fields: list[CurrentFieldSelection] = []
    for field_path, value in selected_values.items():
        assertion_id = f"assertion:paper-c1:{field_path}"
        decision_id = f"field-decision:paper-c1:{field_path}"
        assertion = SourceAssertion(
            assertion_id=assertion_id,
            source_record_id="record:paper-c1",
            source_identity_id=source_identity_id,
            subject_entity_type="paper",
            field_path=field_path,
            value=value,
            observed_at=NOW - timedelta(hours=1),
            assertion_run_id="assertion-run-1",
        )
        decision = CanonicalDecision(
            decision_id=decision_id,
            canonical_identity_id=identity_id,
            field_path=field_path,
            state=DecisionState.selected,
            candidate_assertion_ids=(assertion_id,),
            selected_assertion_ids=(assertion_id,),
            conflicting_assertion_ids=(),
            policy=_policy(PolicyKind.field_selection),
            method=DecisionMethod.deterministic,
            method_version="field-selection-v1",
            decision_run_id="field-selection-run-1",
            confidence=1.0,
            rationale="Single valid retained assertion.",
            release_id=RELEASE_ID,
            decided_at=NOW - timedelta(minutes=30),
        )
        current = CurrentFieldSelection(
            release_id=RELEASE_ID,
            canonical_identity_id=identity_id,
            field_path=field_path,
            value=value,
            decision_id=decision_id,
            supporting_assertion_ids=(assertion_id,),
        )
        assertions.append(assertion)
        decisions.append(decision)
        current_fields.append(current)
    inclusion = PolicyDecision(
        decision_id="inclusion:paper-c1",
        policy=_policy(PolicyKind.inclusion),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        path=None,
        outcome=PolicyOutcome.admitted,
        supporting_assertion_ids=tuple(
            assertion.assertion_id for assertion in assertions
        ),
        evaluated_at=NOW - timedelta(minutes=15),
    )
    return {
        "canonical_identities": (identity,),
        "source_identity_assignments": (assignment,),
        "source_assertions": tuple(assertions),
        "canonical_decisions": tuple(decisions),
        "current_fields": tuple(current_fields),
        "inclusion_decisions": (inclusion,),
    }


def _domain_inputs(
    *,
    domain: str,
    identity_id: str,
    display_name: str,
    selected_values: dict[str, Any],
) -> dict[str, tuple[Any, ...]]:
    source_identity_id = f"source-{identity_id}"
    identity_decision_id = f"identity-decision:{identity_id}"
    identity = CanonicalIdentity(
        canonical_identity_id=identity_id,
        entity_type=domain,
        state=CanonicalIdentityState.active,
        display_name=display_name,
        source_identity_ids=(source_identity_id,),
        identity_decision_id=identity_decision_id,
        release_id=RELEASE_ID,
    )
    assignment = SourceIdentityAssignment(
        release_id=RELEASE_ID,
        source_identity_id=source_identity_id,
        canonical_identity_id=identity_id,
        identity_decision_id=identity_decision_id,
    )
    assertions: list[SourceAssertion] = []
    decisions: list[CanonicalDecision] = []
    current_fields: list[CurrentFieldSelection] = []
    for field_path, value in selected_values.items():
        assertion_id = f"assertion:{identity_id}:{field_path}"
        decision_id = f"field-decision:{identity_id}:{field_path}"
        validity_intervals = (
            {
                (member.get("valid_from"), member.get("valid_to"))
                for member in value
                if isinstance(member, dict)
            }
            if isinstance(value, list) and value
            else {(None, None)}
        )
        member_valid_from, member_valid_to = (
            next(iter(validity_intervals))
            if len(validity_intervals) == 1
            else (None, None)
        )
        valid_from = (
            TemporalDateValue(value=date.fromisoformat(member_valid_from))
            if isinstance(member_valid_from, str) and len(member_valid_from) == 10
            else None
        )
        valid_to = (
            TemporalDateValue(value=date.fromisoformat(member_valid_to))
            if isinstance(member_valid_to, str) and len(member_valid_to) == 10
            else None
        )
        assertion = SourceAssertion(
            assertion_id=assertion_id,
            source_record_id=f"record:{identity_id}",
            source_identity_id=source_identity_id,
            subject_entity_type=domain,
            field_path=field_path,
            value=value,
            observed_at=NOW - timedelta(hours=1),
            valid_from=valid_from,
            valid_to=valid_to,
            assertion_run_id="assertion-run-1",
        )
        decision = CanonicalDecision(
            decision_id=decision_id,
            canonical_identity_id=identity_id,
            field_path=field_path,
            state=DecisionState.selected,
            candidate_assertion_ids=(assertion_id,),
            selected_assertion_ids=(assertion_id,),
            conflicting_assertion_ids=(),
            policy=_policy(PolicyKind.field_selection),
            method=DecisionMethod.deterministic,
            method_version="field-selection-v1",
            decision_run_id="field-selection-run-1",
            confidence=1.0,
            rationale="Single valid retained assertion.",
            release_id=RELEASE_ID,
            decided_at=NOW - timedelta(minutes=30),
        )
        current = CurrentFieldSelection(
            release_id=RELEASE_ID,
            canonical_identity_id=identity_id,
            field_path=field_path,
            value=value,
            decision_id=decision_id,
            supporting_assertion_ids=(assertion_id,),
            valid_from=valid_from,
            valid_to=valid_to,
        )
        assertions.append(assertion)
        decisions.append(decision)
        current_fields.append(current)
    inclusion = PolicyDecision(
        decision_id=f"inclusion:{identity_id}",
        policy=_policy(PolicyKind.inclusion),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        path=None,
        outcome=PolicyOutcome.admitted,
        supporting_assertion_ids=tuple(
            assertion.assertion_id for assertion in assertions
        ),
        evaluated_at=NOW - timedelta(minutes=15),
    )
    return {
        "canonical_identities": (identity,),
        "source_identity_assignments": (assignment,),
        "source_assertions": tuple(assertions),
        "canonical_decisions": tuple(decisions),
        "current_fields": tuple(current_fields),
        "inclusion_decisions": (inclusion,),
    }


def _combine_inputs(
    *inputs: dict[str, tuple[Any, ...]],
) -> dict[str, tuple[Any, ...]]:
    return {
        key: tuple(item for values in inputs for item in values[key])
        for key in inputs[0]
    }


def _request(module: Any, inputs: dict[str, tuple[Any, ...]]) -> Any:
    accepted = _accepted_catalog()
    request_inputs = dict(inputs)
    inclusion_decisions = request_inputs.pop("inclusion_decisions")
    identities = request_inputs["canonical_identities"]
    inclusion_result = create_domain_inclusion_result(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        evaluated_at=inclusion_decisions[0].evaluated_at,
        approved_source_scope_manifest_sha256="4" * 64,
        policy_decisions=inclusion_decisions,
        identity_domains={
            identity.canonical_identity_id: identity.entity_type
            for identity in identities
        },
    )
    return module.DomainProjectionRequest(
        release_id=RELEASE_ID,
        build_run_id=RUN_ID,
        as_of=NOW,
        projection_version=PROJECTION_VERSION,
        catalog_schema_version=accepted["schema_version"],
        catalog_version=accepted["catalog_version"],
        catalog_content_sha256=INSTALLED_CATALOG_CONTENT_SHA256,
        inclusion_result=inclusion_result,
        **request_inputs,
    )


def test_projection_seam_exposes_four_explicit_root_models() -> None:
    module = _module()

    root_models = {
        "company": module.CompanyProjection,
        "paper": module.PaperProjection,
        "patent": module.PatentProjection,
        "professor": module.ProfessorProjection,
    }

    assert all(issubclass(model, BaseModel) for model in root_models.values())
    assert module.DomainProjectionBuilder.project
    assert module.DomainProjectionRequest
    assert module.DomainProjectionResult


def test_packaged_catalog_matches_task_6_1_and_types_all_frozen_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = _accepted_catalog()
    real_builtin_open = builtins.open
    real_path_open = Path.open

    def rejects_agents_path(value: object) -> bool:
        try:
            return ".agents" in Path(value).parts  # type: ignore[arg-type]
        except TypeError:
            return False

    def guarded_builtin_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if rejects_agents_path(file):
            raise AssertionError(
                "product module must not read .agents execution artifacts"
            )
        return real_builtin_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if rejects_agents_path(path):
            raise AssertionError(
                "product module must not read .agents execution artifacts"
            )
        return real_path_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_builtin_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    package = import_module("src.data_agents.canonical_v2")
    monkeypatch.setattr(package, "domain_projection", sys.modules[TARGET_MODULE])
    monkeypatch.delitem(sys.modules, TARGET_MODULE, raising=False)
    module = _module()

    packaged = module.PACKAGED_CATALOG
    assert _catalog_value(packaged, "schema_version") == accepted["schema_version"]
    assert _catalog_value(packaged, "catalog_version") == accepted["catalog_version"]
    # The packaged catalog may legitimately evolve past the s6 accepted copy
    # (s12f applicant-binding added company_name); bind the packaged catalog to
    # its own installed identity instead of the historical s6 hash.
    assert _catalog_value(packaged, "content_sha256") == (
        INSTALLED_CATALOG_CONTENT_SHA256
    )

    root_models = {
        "company": module.CompanyProjection,
        "paper": module.PaperProjection,
        "patent": module.PatentProjection,
        "professor": module.ProfessorProjection,
    }
    domains = {item["domain"]: item for item in accepted["domains"]}
    assert sum(len(item["fields"]) for item in domains.values()) == 101
    assert sum(len(item["subobjects"]) for item in domains.values()) == 28

    for domain, model in root_models.items():
        expected_fields = {item["field_path"] for item in domains[domain]["fields"]}
        assert expected_fields <= set(model.model_fields)

    subobject_models = module.DOMAIN_SUBOBJECT_MODELS
    assert set(subobject_models) == set(domains)
    all_models: list[type[BaseModel]] = []
    for domain, domain_models in subobject_models.items():
        expected = {
            item["subobject_type"]: item for item in domains[domain]["subobjects"]
        }
        assert set(domain_models) == set(expected)
        for subobject_type, model in domain_models.items():
            assert issubclass(model, BaseModel)
            assert {
                member["member_name"] for member in expected[subobject_type]["members"]
            } <= set(model.model_fields)
            all_models.append(model)
    assert len(all_models) == 28
    assert len(set(all_models)) == 28


def test_company_projection_binds_active_identity_current_selection_and_inclusion() -> (
    None
):
    module = _module()
    accepted = _accepted_catalog()
    inputs = _company_inputs()
    request = _request(module, inputs)

    builder = module.create_ephemeral_domain_projection_builder()
    assert isinstance(builder, module.DomainProjectionBuilder)
    result = builder.project(request)

    assert result.release_id == RELEASE_ID
    assert result.build_run_id == RUN_ID
    assert result.catalog_content_sha256 == INSTALLED_CATALOG_CONTENT_SHA256
    assert result.rejected_projections == ()
    assert len(result.projections) == 1
    company = result.projections[0]
    assert isinstance(company, module.CompanyProjection)
    assert company.canonical_identity_id == "company-c1"
    assert company.identity_decision_id == "identity-decision:company-c1"
    assert company.inclusion_decision_id == "inclusion:company-c1"
    assert company.id == "company-c1"
    assert company.name == "Shenzhen Quantum Works"
    assert company.normalized_name == "shenzhen quantum works"
    assert company.profile_summary == (
        "Builds evidence-backed quantum sensing products."
    )
    assert company.technology_route_summary == ("Integrated photonic quantum sensing.")
    assert company.website is None
    lineage = {item.field_path: item for item in company.field_lineage}
    assert set(lineage) == {
        "name",
        "normalized_name",
        "profile_summary",
        "technology_route_summary",
    }
    for current in inputs["current_fields"]:
        item = lineage[current.field_path]
        assert item.decision_id == current.decision_id
        assert item.supporting_assertion_ids == current.supporting_assertion_ids
    assert len(company.content_sha256) == 64


def test_graph_validation_indexes_full_assertion_ids_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    inputs = _replicated_company_inputs(128)
    request = _request(module, inputs)
    baseline = module.create_ephemeral_domain_projection_builder().project(request)
    assert len(inputs["canonical_identities"]) == 128
    assert len(inputs["source_assertions"]) == 512
    full_assertion_key_traversals = 0
    real_index_unique = module._index_unique

    class TraversalCountingAssertionMapping(Mapping[str, Any]):
        def __init__(self, values: dict[str, Any]) -> None:
            self._values = values

        def __getitem__(self, key: str) -> Any:
            return self._values[key]

        def __iter__(self) -> Iterator[str]:
            nonlocal full_assertion_key_traversals
            yield from self._values
            full_assertion_key_traversals += 1

        def __len__(self) -> int:
            return len(self._values)

        def __contains__(self, key: object) -> bool:
            return key in self._values

        def values(self) -> ValuesView[Any]:
            return self._values.values()

    def instrumented_index_unique(
        values: Any,
        attribute: str,
        label: str,
    ) -> Any:
        indexed = real_index_unique(values, attribute, label)
        if label == "source assertions":
            return TraversalCountingAssertionMapping(indexed)
        return indexed

    monkeypatch.setattr(module, "_index_unique", instrumented_index_unique)
    result = module.create_ephemeral_domain_projection_builder().project(request)

    assert full_assertion_key_traversals == 1
    assert result.content_sha256 == baseline.content_sha256
    assert result.model_dump(mode="json") == baseline.model_dump(mode="json")


def test_projection_indexes_current_fields_by_identity_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    inputs = _replicated_company_inputs(128)
    request = _request(module, inputs)
    baseline = module.create_ephemeral_domain_projection_builder().project(request)
    full_current_field_traversals = 0
    real_validate_graph = module._ProjectionContext._validate_graph

    class TraversalCountingCurrentFields(dict[tuple[str, str], Any]):
        def items(self) -> Any:
            nonlocal full_current_field_traversals
            full_current_field_traversals += 1
            return super().items()

    def instrumented_validate_graph(context: Any) -> None:
        real_validate_graph(context)
        context.current_by_subject_path = TraversalCountingCurrentFields(
            context.current_by_subject_path
        )

    monkeypatch.setattr(
        module._ProjectionContext,
        "_validate_graph",
        instrumented_validate_graph,
    )
    result = module.create_ephemeral_domain_projection_builder().project(request)

    assert full_current_field_traversals <= 1
    assert result.content_sha256 == baseline.content_sha256
    assert result.model_dump(mode="json") == baseline.model_dump(mode="json")


def test_paper_projection_types_authors_without_placeholder_enrichment() -> None:
    module = _module()
    inputs = _paper_inputs()
    result = module.create_ephemeral_domain_projection_builder().project(
        _request(module, inputs)
    )

    assert result.rejected_projections == ()
    assert len(result.projections) == 1
    paper = result.projections[0]
    assert isinstance(paper, module.PaperProjection)
    assert paper.id == "paper-c1"
    assert paper.title == "Traceable Knowledge Graphs"
    assert paper.year == 2025
    assert paper.venue.reference_id == "venue-1"
    assert len(paper.authors) == 1
    author = paper.authors[0]
    assert isinstance(author, module.DOMAIN_SUBOBJECT_MODELS["paper"]["author"])
    assert author.parent_canonical_identity_id == "paper-c1"
    assert author.name == "Ada Chen"
    assert author.author_order == 1
    assert author.supporting_assertion_ids == ("assertion:paper-c1:authors",)
    assert author.decision_ids == ("field-decision:paper-c1:authors",)
    assert len(paper.publications) == 1
    publication = paper.publications[0]
    assert isinstance(
        publication,
        module.DOMAIN_SUBOBJECT_MODELS["paper"]["publication"],
    )
    assert publication.parent_canonical_identity_id == "paper-c1"
    assert publication.year == 2025
    assert publication.supporting_assertion_ids == ("assertion:paper-c1:publication",)
    assert publication.decision_ids == ("field-decision:paper-c1:publication",)

    assert paper.summary_text is None
    assert paper.summary_zh is None
    assert paper.abstract is None
    assert paper.quality_status == "partial"
    assert {item.field_path for item in paper.field_lineage} == {
        "authors",
        "publication",
        "title",
        "venue",
        "year",
    }


def test_patent_and_professor_project_typed_subobject_siblings() -> None:
    module = _module()
    patent_id = "patent-c1"
    patent_values: dict[str, Any] = {
        "applicants": [
            {
                "subobject_id": "patent-applicant:patent-c1:1",
                "parent_canonical_identity_id": patent_id,
                "supporting_assertion_ids": ["assertion:patent-c1:applicants"],
                "decision_ids": ["field-decision:patent-c1:applicants"],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "name": "Shenzhen Quantum Works",
                "applicant_order": 1,
            }
        ],
        "ipc_codes": [
            {
                "subobject_id": "patent-ipc:patent-c1:G01R",
                "parent_canonical_identity_id": patent_id,
                "supporting_assertion_ids": ["assertion:patent-c1:ipc_codes"],
                "decision_ids": ["field-decision:patent-c1:ipc_codes"],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "code": "G01R",
                "version": "2025.01",
            }
        ],
        "patent_milestone": [
            {
                "subobject_id": "patent-milestone:patent-c1:filing",
                "parent_canonical_identity_id": patent_id,
                "supporting_assertion_ids": ["assertion:patent-c1:patent_milestone"],
                "decision_ids": ["field-decision:patent-c1:patent_milestone"],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "kind": "filing",
                "date": "2025-01-02",
            }
        ],
        "summary_text": "A source-grounded quantum sensing patent.",
        "title": "Quantum sensing apparatus",
    }
    professor_id = "professor-c1"
    professor_values: dict[str, Any] = {
        "affiliation_history": [
            {
                "subobject_id": "professor-affiliation:professor-c1:1",
                "parent_canonical_identity_id": professor_id,
                "supporting_assertion_ids": [
                    "assertion:professor-c1:affiliation_history"
                ],
                "decision_ids": ["field-decision:professor-c1:affiliation_history"],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "valid_from": "2024-09-01",
                "institution": {
                    "reference_id": "institution-1",
                    "name": "Shenzhen Evidence Institute",
                },
                "title": "Professor",
            }
        ],
        "contact": [
            {
                "subobject_id": "professor-contact:professor-c1:email",
                "parent_canonical_identity_id": professor_id,
                "supporting_assertion_ids": ["assertion:professor-c1:contact"],
                "decision_ids": ["field-decision:professor-c1:contact"],
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "kind": "email",
                "value": "ada@example.edu.cn",
                "public_source": {
                    "assertion_id": "assertion:professor-c1:contact",
                    "decision_id": "field-decision:professor-c1:contact",
                    "field_path": "contact",
                },
            }
        ],
        "canonical_name_zh": "陈艾达",
        "company_roles": [],
        "department": {
            "reference_id": "department-1",
            "name": "量子工程系",
        },
        "email": "ada@example.edu.cn",
        "homepage": "https://example.edu.cn/ada",
        "institution": "Shenzhen Evidence Institute",
        "name": "Ada Chen",
        "paper_summary": "Source-grounded Paper summary.",
        "patent_ids": [],
        "patent_summary": "Source-grounded Patent summary.",
        "profile_summary": "Professor of quantum sensing.",
        "research_directions": [
            {"reference_id": "topic-quantum-sensing", "name": "Quantum sensing"}
        ],
        "title": "Professor",
    }
    inputs = _combine_inputs(
        _domain_inputs(
            domain="patent",
            identity_id=patent_id,
            display_name="Quantum sensing apparatus",
            selected_values=patent_values,
        ),
        _domain_inputs(
            domain="professor",
            identity_id=professor_id,
            display_name="Ada Chen",
            selected_values=professor_values,
        ),
    )

    result = module.create_ephemeral_domain_projection_builder().project(
        _request(module, inputs)
    )
    projections = {item.entity_type: item for item in result.projections}

    patent = projections["patent"]
    assert isinstance(patent, module.PatentProjection)
    assert isinstance(
        patent.applicants[0],
        module.DOMAIN_SUBOBJECT_MODELS["patent"]["applicant"],
    )
    assert isinstance(
        patent.ipc_codes[0],
        module.DOMAIN_SUBOBJECT_MODELS["patent"]["ipc_classification"],
    )
    assert isinstance(
        patent.milestones[0],
        module.DOMAIN_SUBOBJECT_MODELS["patent"]["patent_milestone"],
    )
    assert patent.patent_number is None
    assert patent.title_en is None
    assert patent.quality_status == "partial"

    professor = projections["professor"]
    assert isinstance(professor, module.ProfessorProjection)
    assert isinstance(
        professor.affiliation_history[0],
        module.DOMAIN_SUBOBJECT_MODELS["professor"]["affiliation_history"],
    )
    assert isinstance(
        professor.contacts[0],
        module.DOMAIN_SUBOBJECT_MODELS["professor"]["contact"],
    )
    assert professor.contacts[0].public_source.assertion_id == (
        "assertion:professor-c1:contact"
    )
    assert professor.office is None
    assert professor.phone is None
    assert professor.canonical_name_en is None
    assert professor.quality_status == "partial"
    assert result.counts_by_domain == {
        "company": 0,
        "paper": 0,
        "patent": 1,
        "professor": 1,
    }


@pytest.mark.parametrize(
    ("subject_domain", "foreign_domain"),
    (("company", "paper"), ("paper", "company")),
)
def test_inclusion_supporting_assertions_cannot_cross_wire_canonical_subjects(
    subject_domain: str,
    foreign_domain: str,
) -> None:
    module = _module()
    inputs = dict(_combine_inputs(_company_inputs(), _paper_inputs()))
    subject_identity_id = f"{subject_domain}-c1"
    foreign_assertion = next(
        assertion
        for assertion in inputs["source_assertions"]
        if assertion.subject_entity_type == foreign_domain
    )
    decisions = list(inputs["inclusion_decisions"])
    decision_index = next(
        index
        for index, decision in enumerate(decisions)
        if decision.subject_identity_id == subject_identity_id
    )
    decisions[decision_index] = decisions[decision_index].model_copy(
        update={"supporting_assertion_ids": (foreign_assertion.assertion_id,)}
    )
    inputs["inclusion_decisions"] = tuple(decisions)

    with pytest.raises(
        module.DomainProjectionIntegrityError,
        match="inclusion supporting assertion.*subject identity",
    ):
        module.create_ephemeral_domain_projection_builder().project(
            _request(module, inputs)
        )


@pytest.mark.parametrize(
    ("assertion_valid_from", "current_valid_from"),
    (
        (NOW - timedelta(days=30), None),
        (None, NOW - timedelta(days=30)),
        (NOW - timedelta(days=30), NOW - timedelta(days=20)),
    ),
    ids=("dropped", "invented", "mismatched"),
)
def test_current_field_validity_must_equal_every_selected_assertion(
    assertion_valid_from: datetime | None,
    current_valid_from: datetime | None,
) -> None:
    module = _module()
    inputs = dict(_company_inputs())
    inputs["source_assertions"] = (
        inputs["source_assertions"][0].model_copy(
            update={"valid_from": assertion_valid_from}
        ),
        *inputs["source_assertions"][1:],
    )
    inputs["current_fields"] = (
        inputs["current_fields"][0].model_copy(
            update={"valid_from": current_valid_from}
        ),
        *inputs["current_fields"][1:],
    )

    with pytest.raises(
        module.DomainProjectionIntegrityError,
        match="current field validity.*selected assertion",
    ):
        module.create_ephemeral_domain_projection_builder().project(
            _request(module, inputs)
        )


@pytest.mark.parametrize(
    ("assertion_valid_from", "subobject_valid_from"),
    (
        (NOW - timedelta(days=30), None),
        (None, NOW - timedelta(days=30)),
        (NOW - timedelta(days=30), NOW - timedelta(days=20)),
    ),
    ids=("dropped", "invented", "mismatched"),
)
def test_typed_subobject_validity_must_equal_its_selected_evidence(
    assertion_valid_from: datetime | None,
    subobject_valid_from: datetime | None,
) -> None:
    module = _module()
    inputs = dict(_paper_inputs())
    assertion_index = next(
        index
        for index, assertion in enumerate(inputs["source_assertions"])
        if assertion.field_path == "authors"
    )
    current_index = next(
        index
        for index, current in enumerate(inputs["current_fields"])
        if current.field_path == "authors"
    )
    source_assertion = inputs["source_assertions"][assertion_index]
    author_values = [dict(member) for member in source_assertion.value]
    if subobject_valid_from is None:
        author_values[0].pop("valid_from", None)
    else:
        author_values[0]["valid_from"] = subobject_valid_from.isoformat()
    source_assertions = list(inputs["source_assertions"])
    source_assertions[assertion_index] = source_assertion.model_copy(
        update={
            "value": author_values,
            "valid_from": assertion_valid_from,
        }
    )
    current_fields = list(inputs["current_fields"])
    current_fields[current_index] = current_fields[current_index].model_copy(
        update={
            "value": author_values,
            "valid_from": assertion_valid_from,
        }
    )
    inputs["source_assertions"] = tuple(source_assertions)
    inputs["current_fields"] = tuple(current_fields)

    with pytest.raises(
        module.DomainProjectionIntegrityError,
        match="sub-object validity.*current selection",
    ):
        module.create_ephemeral_domain_projection_builder().project(
            _request(module, inputs)
        )


def test_result_rejects_rehashed_projection_with_wrong_inclusion_decision_id() -> None:
    module = _module()
    result = module.create_ephemeral_domain_projection_builder().project(
        _request(module, _company_inputs())
    )
    projection = result.projections[0].model_dump(mode="json")
    projection["inclusion_decision_id"] = "inclusion:forged"
    projection.pop("content_sha256")
    projection["content_sha256"] = _canonical_sha256(projection)
    manifest = result.manifest[0].model_dump(mode="json")
    manifest["projection_content_sha256"] = projection["content_sha256"]

    with pytest.raises(ValueError, match="projection inclusion decision"):
        module.DomainProjectionResult.model_validate(
            _rehashed_result_payload(
                result,
                projections=[projection],
                manifest=[manifest],
            )
        )


@pytest.mark.parametrize("case", ("excluded_outcome", "wrong_domain"))
def test_result_rejects_rehashed_projection_when_inclusion_semantics_change(
    case: str,
) -> None:
    module = _module()
    inputs = _company_inputs()
    result = module.create_ephemeral_domain_projection_builder().project(
        _request(module, inputs)
    )
    decision = inputs["inclusion_decisions"][0]
    identity_domain = "company"
    if case == "excluded_outcome":
        decision = PolicyDecision.model_validate(
            {
                **decision.model_dump(mode="json"),
                "outcome": "excluded",
                "hard_exclusion_codes": ["outside_company_scope"],
            }
        )
    elif case == "wrong_domain":
        identity_domain = "paper"
    else:
        raise AssertionError(f"unhandled semantic tampering fixture: {case}")
    inclusion_result = create_domain_inclusion_result(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        evaluated_at=decision.evaluated_at,
        approved_source_scope_manifest_sha256="4" * 64,
        policy_decisions=(decision,),
        identity_domains={"company-c1": identity_domain},
    )

    with pytest.raises(ValueError, match="projection inclusion semantics"):
        module.DomainProjectionResult.model_validate(
            _rehashed_result_payload(
                result,
                inclusion_result=inclusion_result.model_dump(mode="json"),
                inclusion_result_content_sha256=inclusion_result.content_sha256,
                inclusion_decisions=[decision.model_dump(mode="json")],
            )
        )


@pytest.mark.parametrize(
    "case",
    ("wrong_outcome", "dropped_code", "reordered_codes", "unknown_domain"),
)
def test_result_rejects_rehashed_rejection_semantic_tampering(case: str) -> None:
    module = _module()
    inputs = dict(_company_inputs())
    decision = inputs["inclusion_decisions"][0]
    exclusion_codes = ("outside_company_scope", "source_validation_failed")
    excluded_decision = PolicyDecision.model_validate(
        {
            **decision.model_dump(mode="json"),
            "outcome": "excluded",
            "hard_exclusion_codes": list(exclusion_codes),
        }
    )
    inputs["inclusion_decisions"] = (excluded_decision,)
    result = module.create_ephemeral_domain_projection_builder().project(
        _request(module, inputs)
    )
    assert result.rejected_projections[0].reason_codes == (
        "inclusion_excluded",
        *exclusion_codes,
    )
    rejected = result.rejected_projections[0].model_dump(mode="json")
    if case == "wrong_outcome":
        rejected["reason_codes"] = ["inclusion_review", *exclusion_codes]
    elif case == "dropped_code":
        rejected["reason_codes"] = ["inclusion_excluded", exclusion_codes[0]]
    elif case == "reordered_codes":
        rejected["reason_codes"] = [
            "inclusion_excluded",
            *reversed(exclusion_codes),
        ]
    elif case == "unknown_domain":
        rejected["entity_type"] = "institution"
    else:
        raise AssertionError(f"unhandled rejection tampering fixture: {case}")

    with pytest.raises(ValueError, match="rejected projection semantics"):
        module.DomainProjectionResult.model_validate(
            _rehashed_result_payload(result, rejected_projections=[rejected])
        )


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("wrong_domain", "domain does not match"),
        ("unknown_field", "unknown company fields"),
        ("duplicate_scalar", "duplicate current field selection"),
        ("dangling_decision_assertion", "missing assertion"),
        ("crosswired_candidate_assertion", "candidate assertion"),
        ("release_mismatch", "identity release"),
        ("invalid_cardinality", "invalid typed company projection"),
        ("future_observation", "future source assertion"),
    ),
)
def test_projection_inputs_fail_closed_on_sibling_invariants(
    case: str,
    message: str,
) -> None:
    module = _module()
    inputs = dict(
        _combine_inputs(_company_inputs(), _paper_inputs())
        if case == "crosswired_candidate_assertion"
        else _company_inputs()
    )

    if case == "wrong_domain":
        assertion = inputs["source_assertions"][0].model_copy(
            update={"subject_entity_type": "paper"}
        )
        inputs["source_assertions"] = (
            assertion,
            *inputs["source_assertions"][1:],
        )
    elif case == "unknown_field":
        unknown_path = "invented_company_fact"
        inputs["source_assertions"] = (
            inputs["source_assertions"][0].model_copy(
                update={"field_path": unknown_path}
            ),
            *inputs["source_assertions"][1:],
        )
        inputs["canonical_decisions"] = (
            inputs["canonical_decisions"][0].model_copy(
                update={"field_path": unknown_path}
            ),
            *inputs["canonical_decisions"][1:],
        )
        inputs["current_fields"] = (
            inputs["current_fields"][0].model_copy(update={"field_path": unknown_path}),
            *inputs["current_fields"][1:],
        )
    elif case == "duplicate_scalar":
        inputs["current_fields"] = (
            *inputs["current_fields"],
            inputs["current_fields"][0],
        )
    elif case == "dangling_decision_assertion":
        inputs["source_assertions"] = inputs["source_assertions"][1:]
    elif case == "crosswired_candidate_assertion":
        company_decision = next(
            decision
            for decision in inputs["canonical_decisions"]
            if decision.canonical_identity_id == "company-c1"
        )
        paper_assertion = next(
            assertion
            for assertion in inputs["source_assertions"]
            if assertion.subject_entity_type == "paper"
        )
        inputs["canonical_decisions"] = tuple(
            decision.model_copy(
                update={
                    "candidate_assertion_ids": tuple(
                        sorted(
                            (
                                *decision.candidate_assertion_ids,
                                paper_assertion.assertion_id,
                            )
                        )
                    )
                }
            )
            if decision.decision_id == company_decision.decision_id
            else decision
            for decision in inputs["canonical_decisions"]
        )
    elif case == "release_mismatch":
        inputs["canonical_identities"] = (
            inputs["canonical_identities"][0].model_copy(
                update={"release_id": "different-release"}
            ),
        )
    elif case == "invalid_cardinality":
        invalid_value = ["Shenzhen Quantum Works", "Duplicate scalar"]
        inputs["source_assertions"] = (
            inputs["source_assertions"][0].model_copy(update={"value": invalid_value}),
            *inputs["source_assertions"][1:],
        )
        inputs["current_fields"] = (
            inputs["current_fields"][0].model_copy(update={"value": invalid_value}),
            *inputs["current_fields"][1:],
        )
    elif case == "future_observation":
        inputs["source_assertions"] = (
            inputs["source_assertions"][0].model_copy(
                update={"observed_at": NOW + timedelta(seconds=1)}
            ),
            *inputs["source_assertions"][1:],
        )
    else:
        raise AssertionError(f"unhandled invariant fixture: {case}")

    with pytest.raises(module.DomainProjectionIntegrityError, match=message):
        module.create_ephemeral_domain_projection_builder().project(
            _request(module, inputs)
        )


def test_projection_order_hash_and_manifest_are_deterministic() -> None:
    module = _module()
    inputs = _combine_inputs(_company_inputs(), _paper_inputs())
    reversed_inputs = {key: tuple(reversed(values)) for key, values in inputs.items()}
    builder = module.create_ephemeral_domain_projection_builder()

    original = builder.project(_request(module, inputs))
    reordered = builder.project(_request(module, reversed_inputs))

    assert original.model_dump(mode="json") == reordered.model_dump(mode="json")
    assert original.content_sha256 == reordered.content_sha256
    assert original.manifest == reordered.manifest
    assert [
        (item.entity_type, item.canonical_identity_id) for item in original.projections
    ] == [("company", "company-c1"), ("paper", "paper-c1")]
    assert tuple(item.projection_content_sha256 for item in original.manifest) == tuple(
        item.content_sha256 for item in original.projections
    )
