from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import pytest


TARGET_PATH = Path(__file__).with_name("claim_level_case_contract.py")
TARGET_MODULE_NAME = "canonical_v2_s2c_claim_level_case_contract"


class _MissingClaimLevelCaseContractModule(AssertionError):
    """The exact S2C1 schema/validator target is intentionally absent in RED."""


def _contract_module() -> Any:
    if not TARGET_PATH.is_file():
        raise _MissingClaimLevelCaseContractModule(
            f"exact target file is absent: {TARGET_PATH}"
        )
    spec = importlib.util.spec_from_file_location(TARGET_MODULE_NAME, TARGET_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("claim-level target file cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        raise AssertionError(
            f"claim-level target has an unexpected missing dependency: {exc.name}"
        ) from exc
    return module


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _rehash(payload: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(payload)
    updated.pop("content_sha256", None)
    updated["content_sha256"] = _canonical_sha256(updated)
    return updated


def _case_payload(*, case_id: str = "case-company-founder") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "canonical-v2-claim-level-case-contract-v1",
        "contract_version": "claim-level-contract-v1",
        "case_id": case_id,
        "source_case_id": "ch-reviewed-badcase-near-name-company",
        "corpus_id": "canonical-v2-s2c-v1",
        "query": "深圳智航无界科技的联合创始人是谁，不要混入近名公司",
        "review_state": "human_reviewed",
        "required_claims": [
            {
                "claim_id": "claim:req-founder-role",
                "subject": {
                    "entity_id": "company:target",
                    "entity_type": "company",
                },
                "predicate": "has_founder_role",
                "object_constraint": {
                    "kind": "literal",
                    "value": "联合创始人",
                },
                "materiality": "material",
                "evidence_obligation": "direct_named_evidence",
                "source_snapshot_ids": ["snapshot:company-official"],
                "temporal_scope": "as_of",
            }
        ],
        "forbidden_claims": [
            {
                "claim_id": "claim:forbid-company-capability-propagation",
                "subject": {
                    "entity_id": "company:target",
                    "entity_type": "company",
                },
                "predicate": "entails_product_capability",
                "object_constraint": {
                    "kind": "literal",
                    "value": "任意具体产品能力",
                },
                "materiality": "material",
                "evidence_obligation": "direct_named_product_evidence",
                "source_snapshot_ids": ["snapshot:company-official"],
                "temporal_scope": "as_of",
            }
        ],
        "required_entities": [
            {
                "constraint_id": "entity:req-target",
                "entity_id": "company:target",
                "entity_type": "company",
                "canonical_name": "深圳智航无界科技",
                "allowed_aliases": ["无界智航"],
                "match_policy": "reviewed_identity_or_alias",
            }
        ],
        "forbidden_entities": [
            {
                "constraint_id": "entity:forbid-near-name",
                "entity_id": "company:near-name",
                "entity_type": "company",
                "canonical_name": "深圳智航无人机有限公司",
                "allowed_aliases": [],
                "match_policy": "reviewed_identity_or_alias",
            }
        ],
        "allowed_variants": [
            {
                "variant_id": "variant:req-founder-role",
                "claim_id": "claim:req-founder-role",
                "variant_kind": "semantic_equivalence",
                "accepted_values": ["共同创始人", "联合创始人"],
            }
        ],
        "source_snapshots": [
            {
                "snapshot_id": "snapshot:company-official",
                "source_nature": "official_company_site",
                "source_locator": "https://example.invalid/snapshots/company-target",
                "content_sha256": "1" * 64,
                "captured_at": "2026-07-13T00:00:00Z",
                "review_state": "human_reviewed",
            }
        ],
        "as_of": "2026-07-13T00:00:00Z",
        "evidence_availability": "snapshotted",
        "unavailable_evidence_reason": None,
        "enumeration_policy": {
            "obligation_id": "enumeration:coverage",
            "mode": "required_members",
            "scope": "reviewed_company_set",
            "universe_entity_ids": ["company:target"],
            "required_entity_ids": ["company:target"],
            "expected_coverage": {
                "checked": 1,
                "eligible": 1,
                "displayed": 1,
                "omitted": 0,
                "unknown": 0,
                "continuation_required": False,
            },
        },
        "stage_oracles": [
            {
                "oracle_id": "stage:protected-slots",
                "stage": "query_understanding",
                "expectations": [
                    {
                        "expectation_id": "expect:target-name-slot",
                        "observable_kind": "protected_slot",
                        "operator": "contains",
                        "value": {
                            "kind": "name",
                            "value": "深圳智航无界科技",
                        },
                        "hard": True,
                    }
                ],
            },
            {
                "oracle_id": "stage:rendered-identity",
                "stage": "rendered_answer",
                "expectations": [
                    {
                        "expectation_id": "expect:exclude-near-name",
                        "observable_kind": "rendered_entity",
                        "operator": "excludes",
                        "value": "company:near-name",
                        "hard": True,
                    }
                ],
            },
        ],
        "outcome_policy": {
            "aggregation": "all_hard_requirements_per_case",
            "hard_requirement_ids": [
                "claim:req-founder-role",
                "claim:forbid-company-capability-propagation",
                "entity:req-target",
                "entity:forbid-near-name",
                "expect:target-name-slot",
                "expect:exclude-near-name",
                "enumeration:coverage",
            ],
            "soft_metric_ids": ["soft:style-quality"],
            "reference_prose_normative": False,
        },
        "reference_context": {
            "answer_role": "review_only",
            "reference_prose": "历史回答可能包含错误或过时事实，仅供审阅。",
            "reference_key_points": "不得把近名公司当成目标公司。",
        },
    }
    return _rehash(payload)


def _expect_invalid(module: Any, payload: dict[str, Any]) -> None:
    with pytest.raises((ValidationError, ValueError)):
        module.ClaimLevelCaseContract.model_validate(payload)


def test_claim_level_contract_binds_strict_schema_version_hash_and_unique_ids() -> None:
    module = _contract_module()
    payload = _case_payload()

    contract = module.ClaimLevelCaseContract.model_validate(payload)

    assert contract.schema_version == "canonical-v2-claim-level-case-contract-v1"
    assert contract.content_sha256 == payload["content_sha256"]
    assert contract.model_dump(mode="json")["case_id"] == payload["case_id"]
    assert (
        module.ClaimLevelCaseContract.model_validate(
            contract.model_dump(mode="json")
        ).content_sha256
        == payload["content_sha256"]
    )
    with pytest.raises(TypeError):
        contract.stage_oracles[0].expectations[0].value["kind"] = "mutated"
    stale_copy = contract.model_copy(update={"query": "mutated with a stale hash"})
    with pytest.raises((ValidationError, ValueError)):
        module.ClaimLevelCaseContract.model_validate(stale_copy)
    with pytest.raises((ValidationError, ValueError)):
        module.validate_case_contracts((stale_copy,))

    unknown = deepcopy(payload)
    unknown["normative_reference_answer"] = "forbidden schema escape"
    _expect_invalid(module, _rehash(unknown))

    duplicate = deepcopy(payload)
    duplicate["required_claims"].append(deepcopy(duplicate["required_claims"][0]))
    _expect_invalid(module, _rehash(duplicate))

    wrong_schema_version = deepcopy(payload)
    wrong_schema_version["schema_version"] = "canonical-v2-claim-level-case-contract-v0"
    _expect_invalid(module, _rehash(wrong_schema_version))

    missing_schema_version = deepcopy(payload)
    missing_schema_version.pop("schema_version")
    _expect_invalid(module, _rehash(missing_schema_version))

    wrong_contract_version = deepcopy(payload)
    wrong_contract_version["contract_version"] = "claim-level-contract-v0"
    _expect_invalid(module, _rehash(wrong_contract_version))

    missing_contract_version = deepcopy(payload)
    missing_contract_version.pop("contract_version")
    _expect_invalid(module, _rehash(missing_contract_version))

    tampered = deepcopy(payload)
    tampered["query"] = "changed without rehash"
    _expect_invalid(module, tampered)


def test_claim_constraints_require_subject_object_materiality_and_evidence() -> None:
    module = _contract_module()
    assert module.ClaimLevelCaseContract.model_validate(_case_payload())

    missing_subject = _case_payload()
    missing_subject["required_claims"][0].pop("subject")
    _expect_invalid(module, _rehash(missing_subject))

    missing_predicate = _case_payload()
    missing_predicate["required_claims"][0].pop("predicate")
    _expect_invalid(module, _rehash(missing_predicate))

    missing_materiality = _case_payload()
    missing_materiality["required_claims"][0].pop("materiality")
    _expect_invalid(module, _rehash(missing_materiality))

    ambiguous_object = _case_payload()
    ambiguous_object["required_claims"][0]["object_constraint"]["entity_id"] = (
        "person:founder"
    )
    _expect_invalid(module, _rehash(ambiguous_object))

    unsupported_material = _case_payload()
    unsupported_material["required_claims"][0]["evidence_obligation"] = "none"
    _expect_invalid(module, _rehash(unsupported_material))

    required_and_forbidden = _case_payload()
    required_and_forbidden["forbidden_claims"][0]["claim_id"] = "claim:req-founder-role"
    _expect_invalid(module, _rehash(required_and_forbidden))

    semantic_contradiction = _case_payload()
    semantic_contradiction["forbidden_claims"][0] = deepcopy(
        semantic_contradiction["required_claims"][0]
    )
    semantic_contradiction["forbidden_claims"][0]["claim_id"] = (
        "claim:forbid-same-founder-role"
    )
    semantic_contradiction["outcome_policy"]["hard_requirement_ids"][1] = (
        "claim:forbid-same-founder-role"
    )
    _expect_invalid(module, _rehash(semantic_contradiction))


def test_entity_constraints_and_variants_use_reviewed_identity_references() -> None:
    module = _contract_module()
    contract = module.ClaimLevelCaseContract.model_validate(_case_payload())
    assert contract.required_entities[0].allowed_aliases == ("无界智航",)
    assert contract.allowed_variants[0].claim_id == "claim:req-founder-role"

    dangling_variant = _case_payload()
    dangling_variant["allowed_variants"][0]["claim_id"] = "claim:missing"
    _expect_invalid(module, _rehash(dangling_variant))

    identity_overlap = _case_payload()
    identity_overlap["forbidden_entities"][0]["entity_id"] = "company:target"
    _expect_invalid(module, _rehash(identity_overlap))

    duplicate_alias = _case_payload()
    duplicate_alias["required_entities"][0]["allowed_aliases"] = [
        "无界智航",
        "无界智航",
    ]
    _expect_invalid(module, _rehash(duplicate_alias))

    duplicate_entity_id = _case_payload()
    duplicate_entity = deepcopy(duplicate_entity_id["required_entities"][0])
    duplicate_entity["constraint_id"] = "entity:req-target-duplicate"
    duplicate_entity["canonical_name"] = "另一个名称"
    duplicate_entity_id["required_entities"].append(duplicate_entity)
    duplicate_entity_id["outcome_policy"]["hard_requirement_ids"].append(
        "entity:req-target-duplicate"
    )
    _expect_invalid(module, _rehash(duplicate_entity_id))

    mismatched_subject_type = _case_payload()
    mismatched_subject_type["required_claims"][0]["subject"]["entity_type"] = (
        "professor"
    )
    _expect_invalid(module, _rehash(mismatched_subject_type))


def test_dynamic_evidence_and_enumeration_require_replayable_coverage_context() -> None:
    module = _contract_module()
    assert module.ClaimLevelCaseContract.model_validate(_case_payload())

    missing_snapshot = _case_payload()
    missing_snapshot["source_snapshots"] = []
    _expect_invalid(module, _rehash(missing_snapshot))

    missing_as_of = _case_payload()
    missing_as_of["as_of"] = None
    _expect_invalid(module, _rehash(missing_as_of))

    outside_universe = _case_payload()
    outside_universe["enumeration_policy"]["required_entity_ids"] = [
        "company:not-in-universe"
    ]
    _expect_invalid(module, _rehash(outside_universe))

    impossible_coverage = _case_payload()
    impossible_coverage["enumeration_policy"]["expected_coverage"]["displayed"] = 2
    _expect_invalid(module, _rehash(impossible_coverage))

    unavailable = _case_payload(case_id="case-explicit-unavailable-evidence")
    unavailable["source_snapshots"] = []
    unavailable["evidence_availability"] = "unavailable"
    unavailable["unavailable_evidence_reason"] = "reviewed source snapshot unavailable"
    for claim_group in ("required_claims", "forbidden_claims"):
        for claim in unavailable[claim_group]:
            claim["source_snapshot_ids"] = []
    assert module.ClaimLevelCaseContract.model_validate(_rehash(unavailable))


def test_stage_oracles_allow_observable_outcomes_not_private_call_order() -> None:
    module = _contract_module()
    contract = module.ClaimLevelCaseContract.model_validate(_case_payload())
    assert tuple(oracle.stage for oracle in contract.stage_oracles) == (
        "query_understanding",
        "rendered_answer",
    )

    private_observable = _case_payload()
    private_observable["stage_oracles"][0]["expectations"][0]["observable_kind"] = (
        "private_helper_invoked"
    )
    _expect_invalid(module, _rehash(private_observable))

    private_order = _case_payload()
    private_order["stage_oracles"][0]["private_call_order"] = [
        "classify",
        "retrieve",
    ]
    _expect_invalid(module, _rehash(private_order))

    duplicate_oracle = _case_payload()
    duplicate_oracle["stage_oracles"][1]["oracle_id"] = duplicate_oracle[
        "stage_oracles"
    ][0]["oracle_id"]
    _expect_invalid(module, _rehash(duplicate_oracle))

    nested_observable = _case_payload(case_id="case-nested-observable")
    nested_observable["stage_oracles"][0]["expectations"][0]["value"] = {
        "items": [{"value": "original"}]
    }
    nested_contract = module.ClaimLevelCaseContract.model_validate(
        _rehash(nested_observable)
    )
    with pytest.raises(TypeError):
        nested_contract.stage_oracles[0].expectations[0].value["items"][0]["value"] = (
            "mutated"
        )


def test_hard_outcomes_remain_per_case_and_reference_prose_is_review_only() -> None:
    module = _contract_module()
    first = _case_payload(case_id="case-a")
    second = _case_payload(case_id="case-b")
    second["reference_context"]["reference_prose"] = (
        "Completely different explanatory wording is allowed."
    )
    second = _rehash(second)

    contracts = module.validate_case_contracts((first, second))

    assert tuple(contract.case_id for contract in contracts) == ("case-a", "case-b")
    assert all(
        contract.outcome_policy.aggregation == "all_hard_requirements_per_case"
        and contract.outcome_policy.reference_prose_normative is False
        and "claim:req-founder-role" in contract.outcome_policy.hard_requirement_ids
        for contract in contracts
    )

    prose_normative = _case_payload()
    prose_normative["outcome_policy"]["reference_prose_normative"] = True
    _expect_invalid(module, _rehash(prose_normative))

    prose_as_hard_requirement = _case_payload()
    prose_as_hard_requirement["outcome_policy"]["hard_requirement_ids"].append(
        "reference:prose"
    )
    _expect_invalid(module, _rehash(prose_as_hard_requirement))

    dangling_hard_requirement = _case_payload()
    dangling_hard_requirement["outcome_policy"]["hard_requirement_ids"].append(
        "claim:missing"
    )
    _expect_invalid(module, _rehash(dangling_hard_requirement))

    duplicate_hard_requirement = _case_payload()
    duplicate_hard_requirement["outcome_policy"]["hard_requirement_ids"].append(
        "claim:req-founder-role"
    )
    _expect_invalid(module, _rehash(duplicate_hard_requirement))

    cross_namespace_collision = _case_payload()
    cross_namespace_collision["stage_oracles"][0]["expectations"][0][
        "expectation_id"
    ] = "claim:req-founder-role"
    cross_namespace_collision["outcome_policy"]["hard_requirement_ids"].remove(
        "expect:target-name-slot"
    )
    _expect_invalid(module, _rehash(cross_namespace_collision))

    pending_claim_evidence = _case_payload()
    pending_claim_evidence["acceptance_eligible"] = True
    pending_claim_evidence["source_snapshots"][0]["review_state"] = (
        "pending_user_review"
    )
    _expect_invalid(module, _rehash(pending_claim_evidence))

    vacuous_acceptance = _case_payload()
    vacuous_acceptance["acceptance_eligible"] = True
    vacuous_acceptance["required_claims"] = []
    vacuous_acceptance["forbidden_claims"] = []
    vacuous_acceptance["required_entities"] = []
    vacuous_acceptance["forbidden_entities"] = []
    vacuous_acceptance["allowed_variants"] = []
    vacuous_acceptance["stage_oracles"] = []
    vacuous_acceptance["enumeration_policy"] = {
        "applicable": False,
        "reason": "non_enumeration_turn",
    }
    vacuous_acceptance["outcome_policy"]["hard_requirement_ids"] = []
    _expect_invalid(module, _rehash(vacuous_acceptance))

    required_atomic_hard_ids = (
        "claim:req-founder-role",
        "claim:forbid-company-capability-propagation",
        "entity:req-target",
        "entity:forbid-near-name",
        "expect:target-name-slot",
        "expect:exclude-near-name",
        "enumeration:coverage",
    )
    for required_id in required_atomic_hard_ids:
        omitted_hard_requirement = _case_payload()
        omitted_hard_requirement["outcome_policy"]["hard_requirement_ids"].remove(
            required_id
        )
        _expect_invalid(module, _rehash(omitted_hard_requirement))

    with pytest.raises((ValidationError, ValueError)):
        module.validate_case_contracts((first, first))
