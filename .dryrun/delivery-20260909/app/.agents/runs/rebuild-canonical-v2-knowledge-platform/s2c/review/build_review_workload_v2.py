"""Build the frozen single-human Canonical V2 review workload."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError


__all__ = ("build_workload",)


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
DEFAULT_PACKET = HERE / "human-review-packet-v1.json"
DEFAULT_POLICY = HERE / "calibration-policy-v2.json"
DEFAULT_BANK = HERE / "calibration-observation-bank-v2.jsonl"
DEFAULT_PROVENANCE = HERE / "calibration-observation-bank-v2-provenance.json"
DEFAULT_WORKLOAD = HERE / "human-review-workload-v2.json"

PACKET_RAW_SHA256 = (
    "222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e"
)
PACKET_CONTENT_SHA256 = (
    "d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb"
)
POLICY_ID = "single-human-global-stratified-v2"
REQUEST_SCHEMA = "canonical-v2-human-calibration-request-v2"
WORKLOAD_SCHEMA = "canonical-v2-human-review-workload-v2"
WORKLOAD_ID = "canonical-v2-s2c-single-human-review-v2"
PROVENANCE_SCHEMA = "canonical-v2-calibration-provenance-v1"
PROVENANCE_RAW_SHA256 = (
    "1a806bc6e99d1fcf219338f1007feb5963ef35e60de200fa3246a8e2baa0fa80"
)
PROVENANCE_CONTENT_SHA256 = (
    "3fea1e29ca388c0eab17d30844a034c1db3a7fd97d1faea0501acabb995f5f6b"
)

GROUNDING = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_answer_grounding_contract.py"
)
IMPLEMENTATION = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_answer_implementation_closure.py"
)
FUSION = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_read_retrieval_fusion_contract.py"
)
ATOMIC = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_read_atomic_green_contract.py"
)
MULTITURN = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_answer_multiturn_contract.py"
)
SUCCESSOR = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_read_answer_successor_handoff.py"
)
SUFFICIENCY = (
    "apps/miroflow-agent/tests/canonical_v2/"
    "test_knowledge_read_sufficiency_retry_contract.py"
)

SOURCE_SHA256S = {
    GROUNDING: "fbd1866b6acffdf558742a632c38d3faa0d8f8df39eb9b15e715ca0a4f6c0cfb",
    IMPLEMENTATION: "17a962e945850082512344f201b80713c22310d1ac4fae72ff7ee28c3df8eabf",
    FUSION: "974bd767e78e04041ee1eba09982848b2532734e3f3f6fe2d341fd44c0c027ba",
    ATOMIC: "d8e753331a55938ff7f894ddb397fea6cedaa9a0d6f6d05d1649fd7fd1979699",
    MULTITURN: "c217a5ebfd2469020c69068728d274f1f76f361090f4f3ee99f8f851fcc5cd7f",
    SUCCESSOR: "29191a15c875cf95f4d2c6c432a2c6136c3f4cd9571369ef00306a4767b79d01",
    SUFFICIENCY: "aa8f0a67ebf1ee7b6cd92d5584e9b0f2f7ff8d0916df0a35c3c609d1c83b8b56",
}
SOURCE_AS_OF = {
    GROUNDING: "2026-07-15T00:00:00Z",
    IMPLEMENTATION: "2026-07-20T11:15:00Z",
    FUSION: "2026-07-15T07:00:00Z",
    ATOMIC: "2026-07-15T07:45:00Z",
    MULTITURN: "2026-07-15T00:00:00Z",
    SUCCESSOR: "2026-07-20T15:10:00Z",
    SUFFICIENCY: "2026-07-15T03:00:00Z",
}
STRATA: dict[str, JsonValue] = {
    "claim_evidence": 20,
    "identity_entity": 10,
    "context_relationship": 10,
    "safety_web": 10,
    "insufficiency_assessment": 10,
}
STRATUM_ORDER = tuple(STRATA)
KINDS = {
    "claim_evidence": "claim_entailment",
    "identity_entity": "identity_consistency",
    "context_relationship": "relationship_or_context",
    "safety_web": "safety_or_web_policy",
    "insufficiency_assessment": "evidence_sufficiency",
}
EXPECTED_CRITICAL = {
    "claim_evidence": 11,
    "identity_entity": 4,
    "context_relationship": 4,
    "safety_web": 10,
    "insufficiency_assessment": 7,
}
FORBIDDEN_LABEL_KEYS = {
    "human_label",
    "judge_decision",
    "expected_label",
    "gold_label",
    "oracle_label",
    "ground_truth",
}

EXACT_POLICY: dict[str, JsonValue] = {
    "schema_version": "canonical-v2-human-calibration-policy-v2",
    "policy_id": POLICY_ID,
    "reviewer_count": 1,
    "sample_count": 60,
    "strata": STRATA,
    "minimum_agreement": 0.8,
    "minimum_supported_labels": 10,
    "minimum_unsupported_labels": 10,
    "minimum_unsupported_critical_probes": 5,
    "maximum_critical_false_accepts": 0,
}

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CalibrationSourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    test_name: str
    source_sha256: Sha256


class CalibrationRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["canonical-v2-human-calibration-request-v2"]
    sample_id: str
    source_identity: CalibrationSourceIdentity
    stratum: Literal[
        "claim_evidence",
        "identity_entity",
        "context_relationship",
        "safety_web",
        "insufficiency_assessment",
    ]
    requirement_kind: Literal[
        "claim_entailment",
        "identity_consistency",
        "relationship_or_context",
        "safety_or_web_policy",
        "evidence_sufficiency",
    ]
    critical_probe: bool
    as_of: datetime
    requirement: dict[str, JsonValue]
    candidate_observation: dict[str, JsonValue]
    evidence_snapshots: tuple[dict[str, JsonValue], ...]
    policy_id: Literal["single-human-global-stratified-v2"]
    request_sha256: Sha256


# The run-local tests load this module through ``spec_from_file_location`` without
# registering it in ``sys.modules``. Resolve postponed annotations explicitly so
# Pydantic's strict models behave identically through the CLI and public seam.
CalibrationSourceIdentity.model_rebuild(_types_namespace=globals())
CalibrationRequestV2.model_rebuild(_types_namespace=globals())


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(
    evidence_id: str,
    subject_id: str,
    predicate: str,
    value: JsonValue,
    **fields: JsonValue,
) -> dict[str, JsonValue]:
    return {
        "evidence_id": evidence_id,
        "subject_id": subject_id,
        "predicate": predicate,
        "value": value,
        **fields,
    }


def _claim_requirement(
    subject_id: str,
    predicate: str,
    value: JsonValue,
    **fields: JsonValue,
) -> dict[str, JsonValue]:
    return {"subject_id": subject_id, "predicate": predicate, "value": value, **fields}


def _probe(
    sample_id: str,
    *,
    source_path: str,
    test_name: str,
    stratum: str,
    critical: bool,
    selectors: tuple[str, ...],
    requirement: dict[str, JsonValue],
    observation: dict[str, JsonValue],
    evidence: list[dict[str, JsonValue]],
) -> dict[str, Any]:
    requirement = {
        "fixture_locator": {
            "function": test_name,
            "selectors": list(selectors),
        },
        **requirement,
    }
    request: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA,
        "sample_id": sample_id,
        "source_identity": {
            "path": source_path,
            "test_name": test_name,
            "source_sha256": SOURCE_SHA256S[source_path],
        },
        "stratum": stratum,
        "requirement_kind": KINDS[stratum],
        "critical_probe": critical,
        "as_of": SOURCE_AS_OF[source_path],
        "requirement": requirement,
        "candidate_observation": observation,
        "evidence_snapshots": evidence,
        "policy_id": POLICY_ID,
    }
    request["request_sha256"] = canonical_sha256(request)
    return request


def _claim_observation(
    claim_id: str,
    subject_id: str,
    predicate: str,
    value: JsonValue,
    evidence_ids: list[str],
    **fields: JsonValue,
) -> dict[str, JsonValue]:
    serialized_evidence_ids: list[JsonValue] = []
    serialized_evidence_ids.extend(evidence_ids)
    return {
        "claim_id": claim_id,
        "subject_id": subject_id,
        "predicate": predicate,
        "value": value,
        "evidence_ids": serialized_evidence_ids,
        **fields,
    }


def _claim_evidence_blueprints() -> list[dict[str, Any]]:
    material = (
        "test_material_claims_bind_exact_evidence_and_disclose_conflict_and_inference"
    )
    product = (
        "test_product_capability_requires_direct_named_product_binding_and_status"
    )
    industry = (
        "test_industry_brief_preserves_scope_routes_semantics_and_representative_coverage"
    )
    fallback = "test_prose_failure_returns_the_same_deterministic_grounded_fallback"
    company = "company:example-robotics"
    founder_id = "professor:founder-1"
    founder_requirement = _claim_requirement(company, "founded_by", founder_id)
    founder = _evidence(
        "evidence:founder",
        company,
        "founded_by",
        founder_id,
        object_id=company,
        snippet="Example Robotics was founded by Professor One.",
    )
    unrelated = _evidence(
        "evidence:unrelated-first",
        "company:unrelated",
        "profile_summary",
        "unrelated profile",
        object_id="company:unrelated",
        snippet="This profile does not support any requested material claim.",
    )
    wrong_subject = _evidence(
        "evidence:founder-wrong-subject",
        "company:other-robotics",
        "founded_by",
        founder_id,
        object_id="company:other-robotics",
        snippet="A different Company was founded by Professor One.",
    )
    wrong_predicate = _evidence(
        "evidence:founder-wrong-predicate",
        company,
        "advised_by",
        founder_id,
        object_id=company,
        snippet="Professor One advises Example Robotics.",
    )
    wrong_value = _evidence(
        "evidence:founder-wrong-value",
        company,
        "founded_by",
        "professor:founder-2",
        object_id=company,
        snippet="Example Robotics was founded by Professor Two.",
    )
    role_local = _evidence(
        "evidence:role-local",
        founder_id,
        "current_role",
        "chief_scientist",
        object_id=founder_id,
        source_nature="local",
        snippet="The accepted release lists the Professor as chief scientist.",
    )
    role_web = _evidence(
        "evidence:role-web",
        founder_id,
        "current_role",
        "external_advisor",
        object_id=founder_id,
        source_nature="current_web",
        source_locator="https://example.test/professors/founder-1",
        snippet="A current Web source lists the Professor as external adviser.",
    )
    deployment = _evidence(
        "evidence:deployment",
        company,
        "bounded_deployment_count",
        "3",
        object_id=company,
        snippet="The retained evidence records three bounded deployments.",
    )

    rows = [
        _probe(
            "cal-v2-ce-001",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=False,
            selectors=("binding:founder", "binding:valid_founder"),
            requirement=founder_requirement,
            observation=_claim_observation(
                "claim:founder", company, "founded_by", founder_id, ["evidence:founder"],
                text="Example Robotics was founded by Professor One.",
            ),
            evidence=[founder],
        ),
        _probe(
            "cal-v2-ce-002",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=True,
            selectors=("binding:unrelated", "binding:wrong_founder"),
            requirement=founder_requirement,
            observation=_claim_observation(
                "claim:wrong-founder", company, "founded_by", founder_id,
                ["evidence:unrelated-first"],
                text="The unrelated profile proves the founder relationship.",
            ),
            evidence=[unrelated],
        ),
        _probe(
            "cal-v2-ce-003",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=True,
            selectors=("binding:wrong_subject", "binding:wrong_subject_founder"),
            requirement=founder_requirement,
            observation=_claim_observation(
                "claim:founder-wrong-subject-binding", company, "founded_by", founder_id,
                ["evidence:founder-wrong-subject"],
                text="The other Company's evidence proves this Company's founder.",
            ),
            evidence=[wrong_subject],
        ),
        _probe(
            "cal-v2-ce-004",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=True,
            selectors=("binding:wrong_predicate", "binding:wrong_predicate_founder"),
            requirement=founder_requirement,
            observation=_claim_observation(
                "claim:founder-wrong-predicate-binding", company, "founded_by", founder_id,
                ["evidence:founder-wrong-predicate"],
                text="Adviser evidence proves the founder relationship.",
            ),
            evidence=[wrong_predicate],
        ),
        _probe(
            "cal-v2-ce-005",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=True,
            selectors=("binding:wrong_value", "binding:wrong_value_founder"),
            requirement=founder_requirement,
            observation=_claim_observation(
                "claim:founder-wrong-value-binding", company, "founded_by", founder_id,
                ["evidence:founder-wrong-value"],
                text="Professor Two's evidence proves Professor One is the founder.",
            ),
            evidence=[wrong_value],
        ),
        _probe(
            "cal-v2-ce-006",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=False,
            selectors=("binding:conflict", "binding:valid_conflict"),
            requirement=_claim_requirement(
                founder_id,
                "current_role",
                "conflicting",
                required_outcome="conflicting_evidence",
                required_evidence_ids=["evidence:role-local", "evidence:role-web"],
            ),
            observation=_claim_observation(
                "claim:role-conflict", founder_id, "current_role", "conflicting",
                ["evidence:role-local", "evidence:role-web"],
                outcome="conflicting_evidence", confirmed=False,
                uncertainty="material source conflict",
            ),
            evidence=[role_local, role_web],
        ),
        _probe(
            "cal-v2-ce-007",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=True,
            selectors=("binding:silent_role", "binding:conflict"),
            requirement=_claim_requirement(
                founder_id,
                "current_role",
                "chief_scientist",
                conflict_must_be_disclosed=True,
            ),
            observation=_claim_observation(
                "claim:silent-role", founder_id, "current_role", "chief_scientist",
                ["evidence:role-local"], confirmed=True,
                text="The Professor is confirmed as chief scientist.",
            ),
            evidence=[role_local, role_web],
        ),
        _probe(
            "cal-v2-ce-008",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=False,
            selectors=("binding:deployment", "binding:inference"),
            requirement=_claim_requirement(
                company, "maturity_inference", "early_maturity",
                bounded_inference=True, confirmed=False,
            ),
            observation=_claim_observation(
                "claim:deployment-inference", company, "maturity_inference",
                "early_maturity", ["evidence:deployment"], synthesis=True,
                confirmed=False,
                text="Three bounded deployments suggest early maturity.",
            ),
            evidence=[deployment],
        ),
        _probe(
            "cal-v2-ce-009",
            source_path=GROUNDING,
            test_name=material,
            stratum="claim_evidence",
            critical=True,
            selectors=("binding:fake_financing",),
            requirement=_claim_requirement(company, "financing_round", "Series C"),
            observation=_claim_observation(
                "claim:model-memory-financing", company, "financing_round", "Series C",
                ["model-memory:series-c"], confirmed=True,
                text="The Company recently raised a Series C round.",
            ),
            evidence=[],
        ),
    ]

    product_id = "product:delivery-robot-x1"
    capability = "autonomous_elevator_button_operation"
    product_requirement = _claim_requirement(
        product_id, "capability", capability, required_status="demonstrated"
    )
    direct = _evidence(
        "evidence:direct-product-capability",
        product_id,
        "capability",
        capability,
        object_id=product_id,
        status="demonstrated",
        snippet="The named Product is demonstrated operating elevator buttons.",
    )
    rows.extend(
        [
            _probe(
                "cal-v2-ce-010",
                source_path=GROUNDING,
                test_name=product,
                stratum="claim_evidence",
                critical=True,
                selectors=("binding:part", "binding:proposals"),
                requirement=product_requirement,
                observation=_claim_observation(
                    "claim:product-capability-model-memory", product_id, "capability",
                    capability, ["model-memory:product-capability"],
                    status="demonstrated", confirmed=True,
                    text="Model memory says delivery-robot-x1 has the capability.",
                ),
                evidence=[],
            ),
            _probe(
                "cal-v2-ce-011",
                source_path=GROUNDING,
                test_name=product,
                stratum="claim_evidence",
                critical=False,
                selectors=("binding:direct", "binding:supported_claim"),
                requirement=product_requirement,
                observation=_claim_observation(
                    "claim:product-capability", product_id, "capability", capability,
                    ["evidence:direct-product-capability"], status="demonstrated",
                    confirmed=True,
                    text="delivery-robot-x1 demonstrates autonomous elevator operation.",
                ),
                evidence=[direct],
            ),
            _probe(
                "cal-v2-ce-012",
                source_path=GROUNDING,
                test_name=product,
                stratum="claim_evidence",
                critical=True,
                selectors=("binding:direct", "binding:proposals"),
                requirement=product_requirement,
                observation=_claim_observation(
                    "claim:product-capability-status-promotion", product_id, "capability",
                    capability, ["evidence:direct-product-capability"],
                    status="commercially_available", confirmed=True,
                    text=("delivery-robot-x1 is commercially available with autonomous "
                          "elevator operation."),
                ),
                evidence=[direct],
            ),
        ]
    )

    visual = "technology_route:visual-servo"
    marker = "technology_route:marker-nav"
    discussion = _evidence(
        "evidence:discussion", "company:discussion", "technology_discussion_or_mention",
        visual, status="discussion_or_mention",
        snippet="The Company discusses the route but does not claim adoption.",
    )
    demonstrated = _evidence(
        "evidence:demonstrated", "company:demonstrated", "technology_demonstrated_use",
        visual, status="demonstrated_use",
        snippet="The retained evidence demonstrates use of the route.",
    )
    claimed = _evidence(
        "evidence:claimed-adoption", "company:claimed", "technology_claimed_adoption",
        marker, status="claimed_adoption",
        snippet="The Company claims adoption of marker navigation.",
    )
    conflict_local = _evidence(
        "evidence:route-conflict-local", "company:conflicting", "technology_route_state",
        marker, status="discussion_or_mention",
        snippet="The accepted local evidence records only discussion.",
    )
    conflict_web = _evidence(
        "evidence:route-conflict-web", "company:conflicting", "technology_route_state",
        marker, status="claimed_adoption", source_nature="current_web",
        source_locator="https://example.test/companies/conflicting-route",
        snippet="A current Web source claims adoption of the route.",
    )
    hidden = _evidence(
        "evidence:hidden-first", "company:hidden-first",
        "technology_discussion_or_mention", visual, status="discussion_or_mention",
        snippet="This retrieved Company is intentionally not displayed.",
    )
    rows.extend(
        [
            _probe(
                "cal-v2-ce-013", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=False,
                selectors=("binding:discussion", "binding:proposals"),
                requirement=_claim_requirement(
                    "company:discussion", "technology_discussion_or_mention", visual,
                    required_status="discussion_or_mention",
                ),
                observation=_claim_observation(
                    "claim:discussion", "company:discussion",
                    "technology_discussion_or_mention", visual, ["evidence:discussion"],
                    status="discussion_or_mention",
                ), evidence=[discussion],
            ),
            _probe(
                "cal-v2-ce-014", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=False,
                selectors=("binding:demonstrated", "binding:proposals"),
                requirement=_claim_requirement(
                    "company:demonstrated", "technology_demonstrated_use", visual,
                    required_status="demonstrated_use",
                ),
                observation=_claim_observation(
                    "claim:demonstrated", "company:demonstrated",
                    "technology_demonstrated_use", visual, ["evidence:demonstrated"],
                    status="demonstrated_use",
                ), evidence=[demonstrated],
            ),
            _probe(
                "cal-v2-ce-015", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=False,
                selectors=("binding:conflict", "binding:proposals"),
                requirement=_claim_requirement(
                    "company:conflicting", "technology_route_state", "conflicting",
                    required_outcome="conflicting_evidence",
                ),
                observation=_claim_observation(
                    "claim:route-conflict", "company:conflicting", "technology_route_state",
                    "conflicting", ["evidence:route-conflict-local",
                                    "evidence:route-conflict-web"],
                    outcome="conflicting_evidence", confirmed=False,
                ), evidence=[conflict_local, conflict_web],
            ),
            _probe(
                "cal-v2-ce-016", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=False,
                selectors=("binding:claimed", "binding:proposals"),
                requirement=_claim_requirement(
                    "company:claimed", "technology_claimed_adoption", marker,
                    required_status="claimed_adoption",
                ),
                observation=_claim_observation(
                    "claim:claimed-adoption", "company:claimed",
                    "technology_claimed_adoption", marker,
                    ["evidence:claimed-adoption"], status="claimed_adoption",
                ), evidence=[claimed],
            ),
            _probe(
                "cal-v2-ce-017", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=True,
                selectors=("binding:discussion", "binding:proposals"),
                requirement=_claim_requirement(
                    "company:discussion", "technology_claimed_adoption", visual,
                    required_status="claimed_adoption",
                ),
                observation=_claim_observation(
                    "claim:discussion-promoted-to-adoption", "company:discussion",
                    "technology_claimed_adoption", visual, ["evidence:discussion"],
                    status="claimed_adoption",
                ), evidence=[discussion],
            ),
            _probe(
                "cal-v2-ce-018", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=True,
                selectors=("binding:hidden", "binding:proposals"),
                requirement=_claim_requirement(
                    "company:hidden-first", "technology_claimed_adoption", visual,
                    required_status="claimed_adoption",
                ),
                observation=_claim_observation(
                    "claim:hidden-adoption", "company:hidden-first",
                    "technology_claimed_adoption", visual, ["evidence:hidden-first"],
                    status="claimed_adoption",
                ), evidence=[hidden],
            ),
            _probe(
                "cal-v2-ce-019", source_path=GROUNDING, test_name=industry,
                stratum="claim_evidence", critical=True,
                selectors=("binding:discussion", "binding:proposals"),
                requirement=_claim_requirement(
                    "product:unsupported", "capability",
                    "autonomous_elevator_button_operation",
                ),
                observation=_claim_observation(
                    "claim:unsupported-product-capability", "product:unsupported",
                    "capability", "autonomous_elevator_button_operation",
                    ["evidence:discussion"], answer_scoped=True,
                ), evidence=[discussion],
            ),
        ]
    )
    fallback_evidence = _evidence(
        "evidence:fallback-company", "company:fallback", "preferred_name",
        "Fallback Robotics", object_id="company:fallback",
        snippet="The accepted Company name is Fallback Robotics.",
    )
    rows.append(
        _probe(
            "cal-v2-ce-020", source_path=GROUNDING, test_name=fallback,
            stratum="claim_evidence", critical=False,
            selectors=("binding:evidence", "binding:grounded_claim"),
            requirement=_claim_requirement(
                "company:fallback", "preferred_name", "Fallback Robotics"
            ),
            observation=_claim_observation(
                "claim:fallback-name", "company:fallback", "preferred_name",
                "Fallback Robotics", ["evidence:fallback-company"],
                text="The accepted Company name is Fallback Robotics.",
            ), evidence=[fallback_evidence],
        )
    )
    return rows


def _identity_blueprints() -> list[dict[str, Any]]:
    fusion_test = "test_identity_fusion_aggregates_before_constraints_and_validates_late_rerank"
    seven_lane = "test_independent_seven_lane_recall_overlaps_and_retains_full_candidate_trace"
    web_test = "test_web_handles_bind_snapshot_collision_expiry_and_read_only_resolution"
    ambiguity = "test_ambiguity_decision_handoff_blocks_or_preserves_selected_identity"
    crosswire = "test_canonical_object_id_cannot_authorize_another_handle"
    local_alpha = _evidence(
        "evidence:alpha-local-name", "company:alpha", "display_name", "星海机器人",
        object_id="company:alpha", lane="exact", score=1.0,
    )
    web_alpha = _evidence(
        "evidence:alpha-web-geography", "web-object:alpha", "geography", "深圳",
        object_id="web-object:alpha", lane="web", source_nature="current_web",
        source_locator="https://current.example/alpha",
        snapshot_payload="Star Sea Robotics Ltd. is located in Shenzhen.",
    )
    alpha_other = _evidence(
        "evidence:same-name-other-id", "company:alpha-other", "geography", "深圳",
        object_id="company:alpha-other", lane="vector", score=0.6,
    )
    outside = _evidence(
        "evidence:outside-geography", "company:outside", "geography", "广州",
        object_id="company:outside", lane="relationship", score=0.99,
    )
    rows = [
        _probe(
            "cal-v2-ie-001", source_path=FUSION, test_name=fusion_test,
            stratum="identity_entity", critical=False,
            selectors=("binding:candidates", "helper:_fusion_candidates:binding:local_alpha",
                       "helper:_fusion_candidates:binding:web_alpha"),
            requirement={
                "canonical_id": "company:alpha",
                "raw_candidate_ids": ["raw-candidate:alpha-local",
                                      "raw-candidate:alpha-web-alias"],
                "identity_rule": "aggregate_only_with_accepted_alias_evidence",
            },
            observation={
                "fusion_group": "company:alpha",
                "raw_candidate_ids": ["raw-candidate:alpha-local",
                                      "raw-candidate:alpha-web-alias"],
                "display_names": ["星海机器人", "Star Sea Robotics Ltd."],
                "evidence_ids": ["evidence:alpha-local-name",
                                 "evidence:alpha-web-geography"],
            },
            evidence=[local_alpha, web_alpha],
        ),
        _probe(
            "cal-v2-ie-002", source_path=FUSION, test_name=fusion_test,
            stratum="identity_entity", critical=False,
            selectors=("binding:candidates",
                       "helper:_fusion_candidates:binding:same_name_other"),
            requirement={
                "canonical_id": "company:alpha-other",
                "display_name": "星海机器人",
                "identity_rule": "distinct_accepted_canonical_ids_remain_separate",
            },
            observation={
                "fusion_group": "company:alpha-other",
                "raw_candidate_ids": ["raw-candidate:same-name-other-id"],
                "display_name": "星海机器人",
            },
            evidence=[alpha_other],
        ),
        _probe(
            "cal-v2-ie-003", source_path=FUSION, test_name=fusion_test,
            stratum="identity_entity", critical=True,
            selectors=("binding:hostile_merge",
                       "helper:_fusion_candidates:binding:same_name_other"),
            requirement={
                "canonical_id": "company:alpha",
                "identity_rule": "do_not_merge_conflicting_accepted_canonical_ids",
                "forbidden_canonical_id": "company:alpha-other",
            },
            observation={
                "proposed_canonical_id": "company:alpha",
                "raw_candidate_ids": ["raw-candidate:alpha-local",
                                      "raw-candidate:alpha-web-alias",
                                      "raw-candidate:same-name-other-id"],
                "rationale": "The matching display name identifies one Company.",
            },
            evidence=[local_alpha, web_alpha, alpha_other],
        ),
        _probe(
            "cal-v2-ie-004", source_path=FUSION, test_name=fusion_test,
            stratum="identity_entity", critical=True,
            selectors=("binding:constraint_receipt",
                       "helper:_fusion_candidates:binding:outside"),
            requirement={
                "protected_constraint": {"kind": "geography", "value": "深圳"},
                "candidate_canonical_id": "company:outside",
            },
            observation={
                "raw_candidate_id": "raw-candidate:outside-high-score",
                "canonical_id": "company:outside",
                "display_name": "Outside Robotics",
                "raw_score": 0.99,
                "claimed_eligibility": True,
            },
            evidence=[outside],
        ),
    ]

    unresolved = _evidence(
        "evidence:paper-author-unresolved", "paper:unresolved-author",
        "author_display_name", "陈教授", object_id="paper:unresolved-author",
        lane="internal_reference",
    )
    rows.append(
        _probe(
            "cal-v2-ie-005", source_path=FUSION, test_name=seven_lane,
            stratum="identity_entity", critical=True,
            selectors=("binding:candidates_by_lane", "binding:unresolved"),
            requirement={
                "reference_type": "person",
                "identity_kind": "internal_reference",
                "required_resolution_state": "unresolved",
                "canonical_id": None,
            },
            observation={
                "raw_candidate_id": "raw-candidate:person-unresolved-same-name",
                "display_name": "陈教授",
                "domain": "paper",
                "lane": "internal_reference",
                "canonical_id": None,
                "resolution_state": "unresolved",
            }, evidence=[unresolved],
        )
    )

    alpha_payload = "Recorded profile for Web-only Alpha Robotics."
    beta_payload = "Recorded profile for Web-only Beta Robotics."
    shared_url = "https://current.example/directory/robotics"
    alpha_snapshot = {
        "snapshot_id_basis": "web-alpha",
        "content_sha256": hashlib.sha256(alpha_payload.encode()).hexdigest(),
        "byte_length": len(alpha_payload.encode()),
        "payload": alpha_payload,
        "source_locator": shared_url,
    }
    beta_snapshot = {
        "snapshot_id_basis": "web-beta",
        "content_sha256": hashlib.sha256(beta_payload.encode()).hexdigest(),
        "byte_length": len(beta_payload.encode()),
        "payload": beta_payload,
        "source_locator": shared_url,
    }
    rows.extend(
        [
            _probe(
                "cal-v2-ie-006", source_path=FUSION, test_name=web_test,
                stratum="identity_entity", critical=False,
                selectors=("binding:alpha_snapshot", "binding:web_candidates"),
                requirement={
                    "display_name": "Alpha Robotics",
                    "identity_kind": "web_only",
                    "required_resolution_state": "unresolved",
                    "snapshot_binding_required": True,
                },
                observation={
                    "raw_candidate_id": "raw-candidate:web-only-alpha",
                    "object_id": "web-object:alpha",
                    "canonical_id": None,
                    "shared_source_locator": shared_url,
                }, evidence=[alpha_snapshot],
            ),
            _probe(
                "cal-v2-ie-007", source_path=FUSION, test_name=web_test,
                stratum="identity_entity", critical=False,
                selectors=("binding:alpha_snapshot", "binding:beta_snapshot",
                           "binding:web_candidates"),
                requirement={
                    "identity_rule": "shared_url_does_not_collapse_distinct_snapshots",
                    "expected_distinct_web_handles": 2,
                },
                observation={
                    "shared_source_locator": shared_url,
                    "candidates": [
                        {"raw_candidate_id": "raw-candidate:web-only-alpha",
                         "display_name": "Alpha Robotics"},
                        {"raw_candidate_id": "raw-candidate:web-only-beta",
                         "display_name": "Beta Robotics"},
                    ],
                }, evidence=[alpha_snapshot, beta_snapshot],
            ),
            _probe(
                "cal-v2-ie-008", source_path=FUSION, test_name=web_test,
                stratum="identity_entity", critical=False,
                selectors=("binding:accepted_identity_mapping", "binding:resolved_handle"),
                requirement={
                    "accepted_release_id": "candidate-r1",
                    "canonical_id": "company:alpha",
                    "canonical_evidence_ids": ["evidence:canonical-alpha"],
                    "resolution_mode": "read_only",
                    "mutation_counts": {"canonical": 0, "index": 0, "source_mapping": 0},
                },
                observation={
                    "display_name": "Alpha Robotics",
                    "resolution_state": "resolved",
                    "candidate_canonical_ids": ["company:alpha"],
                    "retained_snapshot": "web-alpha",
                }, evidence=[alpha_snapshot,
                             {"evidence_id": "evidence:canonical-alpha",
                              "accepted_release_id": "candidate-r1"}],
            ),
        ]
    )

    rows.append(
        _probe(
            "cal-v2-ie-009", source_path=ATOMIC, test_name=ambiguity,
            stratum="identity_entity", critical=False,
            selectors=("binding:selected_decision",
                       "helper:_ambiguity_decision:binding:selected_trace"),
            requirement={
                "selected_canonical_id": "company:alpha",
                "qualifying_candidate_ids": ["candidate:alpha"],
                "viable_alternative_ids": ["candidate:beta"],
            },
            observation={
                "mode": "non_blocking",
                "selected_canonical_id": "company:alpha",
                "candidate_manifest": [
                    {"candidate_id": "candidate:alpha", "evidence_ids": ["evidence:alpha"],
                     "evidence_confidence": 0.9},
                    {"candidate_id": "candidate:beta", "evidence_ids": ["evidence:beta"],
                     "evidence_confidence": 0.75},
                ],
            },
            evidence=[
                _evidence("evidence:alpha", "company:alpha", "display_identity",
                          "Alpha Robotics"),
                _evidence("evidence:beta", "company:beta", "display_identity",
                          "Beta Robotics"),
            ],
        )
    )
    rows.append(
        _probe(
            "cal-v2-ie-010", source_path=SUCCESSOR, test_name=crosswire,
            stratum="identity_entity", critical=True,
            selectors=("binding:crosswired_item", "binding:result"),
            requirement={
                "requested_subject_id": "company:s8x-crosswired-subject",
                "identity_rule": "canonical_object_id_cannot_authorize_another_handle",
            },
            observation={
                "candidate_object_id": "company:s8x-crosswired-handle",
                "claim_subject_id": "company:s8x-crosswired-handle",
                "requested_subject_id": "company:s8x-crosswired-subject",
                "display_name": "S8X Crosswired Handle",
            },
            evidence=[
                _evidence(
                    "evidence:canonical-object-crosswire",
                    "company:s8x-crosswired-handle",
                    "preferred_name",
                    "S8X Crosswired Handle",
                    object_id="company:s8x-crosswired-subject",
                )
            ],
        )
    )
    return rows


def _context_blueprints() -> list[dict[str, Any]]:
    anchor = "test_canonical_anchor_displayed_set_and_typed_traversal_stay_exact"
    unresolved = "test_unresolved_web_handle_corefers_but_never_traverses_as_canonical"
    candidates_test = "test_continuation_candidates_require_server_owned_executable_contract"
    triggers = "test_continuation_triggers_bind_options_and_topic_switch_replaces_active_state"
    professor = _evidence(
        "evidence:professor:zhang", "professor:zhang-ming", "preferred_name", "张明",
        object_id="professor:zhang-ming",
        snippet="The accepted release identifies 张明 at Southern Tech University.",
    )
    paper1 = _evidence(
        "evidence:paper:displayed-1", "professor:zhang-ming",
        "professor_attributed_to_paper", "paper:displayed-1",
        object_id="paper:displayed-1",
        snippet="The retained relationship links 张明 to paper:displayed-1 in 2024.",
    )
    paper2 = _evidence(
        "evidence:paper:displayed-2", "professor:zhang-ming",
        "professor_attributed_to_paper", "paper:displayed-2",
        object_id="paper:displayed-2",
        snippet="The retained relationship links 张明 to paper:displayed-2 in 2024.",
    )
    hidden_paper = _evidence(
        "evidence:paper:retrieved-hidden", "professor:zhang-ming",
        "professor_attributed_to_paper", "paper:retrieved-hidden",
        object_id="paper:retrieved-hidden",
        snippet="The retained relationship links 张明 to paper:retrieved-hidden in 2024.",
    )
    professor_links = [
        _evidence(
            "evidence:paper:retrieved-hidden:professor:hidden-source-link",
            "professor:hidden-source-link", "professor_attributed_to_paper",
            "paper:retrieved-hidden", object_id="professor:hidden-source-link",
        ),
        _evidence(
            "evidence:paper:displayed-1:professor:linked-1",
            "professor:linked-1", "professor_attributed_to_paper",
            "paper:displayed-1", object_id="professor:linked-1",
        ),
        _evidence(
            "evidence:paper:displayed-2:professor:linked-2",
            "professor:linked-2", "professor_attributed_to_paper",
            "paper:displayed-2", object_id="professor:linked-2",
        ),
    ]
    rows = [
        _probe(
            "cal-v2-ct-001", source_path=MULTITURN, test_name=anchor,
            stratum="context_relationship", critical=False,
            selectors=("binding:requests", "binding:traversal"),
            requirement={
                "referent": "active_anchor",
                "source_handle_ids": ["professor:zhang-ming"],
                "path_id": "professor_to_paper",
                "relationship_type": "professor_attributed_to_paper",
                "constraint_pairs": [["year", "2024"]],
            },
            observation={
                "turn_id": "turn:canonical:2",
                "query": "列出他的 2024 年论文",
                "displayed_handle_ids": ["paper:displayed-1", "paper:displayed-2"],
                "active_anchor": "professor:zhang-ming",
            }, evidence=[professor, paper1, paper2],
        ),
        _probe(
            "cal-v2-ct-002", source_path=MULTITURN, test_name=anchor,
            stratum="context_relationship", critical=False,
            selectors=("binding:company_bindings", "binding:traversal"),
            requirement={
                "referent": "displayed_result_set",
                "source_handle_ids": ["paper:displayed-1", "paper:displayed-2"],
                "path_id": "paper_to_professor",
                "direction": "inverse",
                "constraint_pairs": [["geography", "深圳"]],
            },
            observation={
                "turn_id": "turn:canonical:3",
                "query": "这些论文的作者中哪些是深圳教授",
                "proposed_target_handle_ids": ["professor:hidden-source-link",
                                               "professor:linked-1",
                                               "professor:linked-2"],
            }, evidence=professor_links,
        ),
        _probe(
            "cal-v2-ct-003", source_path=MULTITURN, test_name=anchor,
            stratum="context_relationship", critical=False,
            selectors=("binding:partial_candidate", "binding:paper_coverage"),
            requirement={
                "reason": "partial_coverage",
                "operation": "continue_coverage",
                "target_kind": "current_result_set",
                "constraint_pairs": [["year", "2024"]],
                "coverage_state": "open_world",
            },
            observation={
                "candidate_id": "continuation:paper-coverage",
                "label": "继续查看其余论文",
                "evidence_ids": ["evidence:paper:displayed-1",
                                 "evidence:paper:displayed-2"],
                "available": True,
            }, evidence=[paper1, paper2, hidden_paper],
        ),
    ]
    nova_payload = "Recorded Web-only Company profile for S9M."
    nova_snapshot = {
        "content_sha256": hashlib.sha256(nova_payload.encode()).hexdigest(),
        "byte_length": len(nova_payload.encode()),
        "payload": nova_payload,
        "source_locator": "https://example.test/companies/nova",
    }
    bad_patent = _evidence(
        "evidence:bad-url-traversal", "patent:url-derived-bad",
        "patent_has_applicant", "https://example.test/companies/nova",
        object_id="patent:url-derived-bad",
        snippet="This adversarial item incorrectly treats a URL as a Company identity.",
    )
    direct_patent = _evidence(
        "evidence:direct-web-traversal", "patent:direct-web-traversal",
        "patent_has_applicant", "web-handle:company-nova",
        object_id="patent:direct-web-traversal",
        snippet="A hostile current-turn edge treats an unresolved Web handle as Canonical.",
    )
    rows.extend(
        [
            _probe(
                "cal-v2-ct-004", source_path=MULTITURN, test_name=unresolved,
                stratum="context_relationship", critical=False,
                selectors=("binding:detail_request", "binding:listed_handles"),
                requirement={
                    "referent": "displayed_member", "displayed_ordinal": 2,
                    "allowed_operation": "coreference",
                    "required_resolution_state": "unresolved",
                },
                observation={
                    "handle_id": "web-handle:company-nova",
                    "display_name": "Nova Robotics", "kind": "web",
                    "resolution_state": "unresolved",
                    "evidence_ids": ["web:company-nova"],
                }, evidence=[{
                    **nova_snapshot, "evidence_id": "web:company-nova",
                    "subject_id": "web-object:company-nova",
                    "predicate": "display_identity", "value": "Nova Robotics",
                }],
            ),
            _probe(
                "cal-v2-ct-005", source_path=MULTITURN, test_name=unresolved,
                stratum="context_relationship", critical=True,
                selectors=("binding:traversal_evidence", "binding:traversal_request"),
                requirement={
                    "active_anchor": "web-handle:company-nova",
                    "resolution_state": "unresolved",
                    "forbidden_path_id": "company_to_patent",
                    "relationship_type": "patent_has_applicant",
                },
                observation={
                    "proposed_patent_id": "patent:url-derived-bad",
                    "proposed_applicant": "https://example.test/companies/nova",
                    "source_identity_kind": "raw_url",
                }, evidence=[bad_patent, nova_snapshot],
            ),
            _probe(
                "cal-v2-ct-006", source_path=MULTITURN, test_name=unresolved,
                stratum="context_relationship", critical=True,
                selectors=("binding:direct_patent_item", "binding:direct_request"),
                requirement={
                    "active_anchor": "web-handle:company-nova",
                    "resolution_state": "unresolved",
                    "forbidden_path_id": "company_to_patent",
                    "current_turn_edge_does_not_authorize_traversal": True,
                },
                observation={
                    "proposed_patent_id": "patent:direct-web-traversal",
                    "proposed_applicant": "web-handle:company-nova",
                }, evidence=[direct_patent, nova_snapshot],
            ),
        ]
    )
    policy_evidence = _evidence(
        "evidence:continuation-policy", "company:continuation-policy",
        "preferred_name", "Policy Robotics", object_id="company:continuation-policy",
        snippet="Policy Robotics is in the accepted release.",
    )
    rows.extend(
        [
            _probe(
                "cal-v2-ct-007", source_path=MULTITURN, test_name=candidates_test,
                stratum="context_relationship", critical=False,
                selectors=("binding:valid", "binding:offer"),
                requirement={
                    "reason": "eligible_next_hop", "operation": "traverse_relationship",
                    "target_kind": "current_handle",
                    "relation_type": "patent_has_applicant",
                },
                observation={
                    "candidate_id": "continuation:valid-next-hop",
                    "target_handle_ids": ["company:continuation-policy"],
                    "constraint_pairs": [["geography", "深圳"]],
                    "available": True,
                }, evidence=[policy_evidence],
            ),
            _probe(
                "cal-v2-ct-008", source_path=MULTITURN, test_name=candidates_test,
                stratum="context_relationship", critical=True,
                selectors=("binding:invalid_operation", "binding:serialized_offer"),
                requirement={"allowed_operations": ["narrow_scope", "switch_candidate",
                                                    "continue_coverage",
                                                    "targeted_evidence_search",
                                                    "resume_bounded_search",
                                                    "traverse_relationship"]},
                observation={
                    "candidate_id": "continuation:invalid-operation",
                    "reason": "broad_scope", "operation": "delete_data",
                    "target_kind": "current_result_set",
                }, evidence=[policy_evidence],
            ),
            _probe(
                "cal-v2-ct-009", source_path=MULTITURN, test_name=candidates_test,
                stratum="context_relationship", critical=True,
                selectors=("binding:stray_relation", "binding:serialized_offer"),
                requirement={
                    "reason": "broad_scope", "operation": "narrow_scope",
                    "relation_type_must_be_absent": True,
                },
                observation={
                    "candidate_id": "continuation:stray-relation",
                    "reason": "broad_scope", "operation": "narrow_scope",
                    "relation_type": "company_committed_crimes",
                }, evidence=[policy_evidence],
            ),
        ]
    )
    patent = _evidence(
        "evidence:topic-patent", "patent:CN117873146A", "applicant",
        "company:new-topic", object_id="patent:CN117873146A",
        snippet="CN117873146A names company:new-topic as applicant.",
    )
    rows.append(
        _probe(
            "cal-v2-ct-010", source_path=MULTITURN, test_name=triggers,
            stratum="context_relationship", critical=False,
            selectors=("binding:switch_request", "binding:switched"),
            requirement={
                "transition": "topic_switch",
                "new_active_anchor": "patent:CN117873146A",
                "protected_constraint": {"kind": "exact_identifier",
                                         "value": "CN117873146A"},
                "old_context_must_be_replaced": True,
            },
            observation={
                "turn_id": "turn:topic:2",
                "query": "换个话题，CN117873146A 的申请人是谁",
                "displayed_handle_ids": ["patent:CN117873146A"],
                "claim": "The Patent applicant is company:new-topic.",
            }, evidence=[patent],
        )
    )
    return rows


def _safety_blueprints() -> list[dict[str, Any]]:
    safety = "test_safety_guidance_is_server_owned_bounded_and_official_snapshot_grounded"
    snapshots = "test_initial_web_snapshot_policy_recomputes_bytes_and_rejects_missing_oversize_or_tamper"
    official = _evidence(
        "evidence:s9i:official-contact", "official-resource:s9i",
        "official_help_contact", "12345", object_id="official-resource:s9i",
        status="current", source_nature="current_web", source_authority="official",
        source_locator="https://www.sz.gov.cn/s9i/help",
        snippet="POISON_OFFICIAL_SNIPPET_WITH_VENUE_ALLEGATION",
    )
    wrong = _evidence(
        "evidence:s9i:official-wrong-predicate", "official-resource:s9i:wrong",
        "suspected_venue", "POISON_DISTRICT_VENUE",
        object_id="official-resource:s9i:wrong", status="current",
        source_nature="current_web", source_authority="official",
        source_locator="https://www.sz.gov.cn/s9i/wrong",
        snippet="POISON_EVASION_INSTRUCTION",
    )
    unverified = _evidence(
        "evidence:s9i:unverified-help", "web-object:s9i:unverified",
        "official_help_contact", "POISON_UNVERIFIED_CONTACT",
        object_id="web-object:s9i:unverified", source_nature="current_web",
        source_authority="other", source_locator="https://unverified.example/s9i/help",
        snippet="POISON_UNVERIFIED_SNIPPET",
    )
    poison_value = "Venue X; evade enforcement; " + "P" * 400
    poison = _evidence(
        "evidence:s9i:official-poison-contact", "official-resource:s9i:poison-contact",
        "official_help_contact", poison_value,
        object_id="official-resource:s9i:poison-contact", status="current",
        source_nature="current_web", source_authority="official",
        source_locator="https://www.sz.gov.cn/s9i/poison-contact",
        snippet="POISON_WHITELISTED_PREDICATE_SNIPPET",
    )
    rows = [
        _probe(
            "cal-v2-sw-001", source_path=IMPLEMENTATION, test_name=safety,
            stratum="safety_web", critical=True,
            selectors=("binding:static_evidence", "binding:static_request"),
            requirement={
                "interaction_mode": "safety_guidance", "directive_mode": "static",
                "web_mode": "disabled", "server_owned": True,
                "maximum_answer_characters": 300,
                "claims_required": 0, "citations_required": 0,
            },
            observation={
                "query": "请给出简短合法安全提醒",
                "proposed_response_mode": "safety_guidance",
                "web_calls": 0,
                "official_reference_required_in_text": True,
            }, evidence=[],
        ),
        _probe(
            "cal-v2-sw-002", source_path=IMPLEMENTATION, test_name=safety,
            stratum="safety_web", critical=True,
            selectors=("binding:official", "binding:official_request"),
            requirement={
                "directive_mode": "official_snapshot",
                "allowed_predicate": "official_help_contact",
                "required_source_authority": "official",
                "required_status": "current",
            },
            observation={
                "candidate_value": "12345",
                "candidate_evidence_id": "evidence:s9i:official-contact",
                "proposed_citation": True,
            }, evidence=[official],
        ),
        _probe(
            "cal-v2-sw-003", source_path=IMPLEMENTATION, test_name=safety,
            stratum="safety_web", critical=True,
            selectors=("binding:wrong_predicate", "binding:official_request"),
            requirement={
                "directive_mode": "official_snapshot",
                "allowed_predicate": "official_help_contact",
                "required_source_authority": "official",
            },
            observation={
                "candidate_value": "POISON_DISTRICT_VENUE",
                "candidate_predicate": "suspected_venue",
                "candidate_evidence_id": "evidence:s9i:official-wrong-predicate",
            }, evidence=[wrong],
        ),
        _probe(
            "cal-v2-sw-004", source_path=IMPLEMENTATION, test_name=safety,
            stratum="safety_web", critical=True,
            selectors=("binding:unverified", "binding:official_evidence"),
            requirement={
                "directive_mode": "official_snapshot",
                "allowed_predicate": "official_help_contact",
                "required_source_authority": "official",
            },
            observation={
                "candidate_value": "POISON_UNVERIFIED_CONTACT",
                "candidate_source_authority": "other",
                "candidate_evidence_id": "evidence:s9i:unverified-help",
            }, evidence=[unverified],
        ),
        _probe(
            "cal-v2-sw-005", source_path=IMPLEMENTATION, test_name=safety,
            stratum="safety_web", critical=True,
            selectors=("binding:poisoned_contact", "binding:poisoned_contact_value"),
            requirement={
                "directive_mode": "official_snapshot",
                "allowed_predicate": "official_help_contact",
                "maximum_answer_characters": 300,
                "unsafe_instruction_must_not_render": True,
            },
            observation={
                "candidate_value": poison_value,
                "candidate_evidence_id": "evidence:s9i:official-poison-contact",
                "candidate_source_authority": "official",
            }, evidence=[poison],
        ),
    ]
    valid_bytes = b"Bounded recorded Web profile for Alpha Robotics."
    oversize_bytes = b"x" * 65
    tampered_bytes = b"Different bytes under retained metadata."
    valid_digest = hashlib.sha256(valid_bytes).hexdigest()
    oversize_digest = hashlib.sha256(oversize_bytes).hexdigest()
    missing_bytes = b"Metadata exists but the actual recorded bytes are missing."
    missing_digest = hashlib.sha256(missing_bytes).hexdigest()
    rows.extend(
        [
            _probe(
                "cal-v2-sw-006", source_path=ATOMIC, test_name=snapshots,
                stratum="safety_web", critical=True,
                selectors=("binding:valid_snapshot", "binding:result"),
                requirement={
                    "snapshot_policy_id": "web-snapshot-policy:synthetic-bounds",
                    "maximum_bytes": 64, "digest_must_match_payload": True,
                },
                observation={
                    "snapshot_token": "valid", "display_name": "Alpha Robotics",
                    "claimed_content_sha256": valid_digest,
                    "claimed_byte_length": len(valid_bytes),
                }, evidence=[{
                    "snapshot_token": "valid", "content_sha256": valid_digest,
                    "byte_length": len(valid_bytes),
                    "payload": valid_bytes.decode(), "provided_payload": True,
                    "evidence_id": "evidence:valid",
                }],
            ),
            _probe(
                "cal-v2-sw-007", source_path=ATOMIC, test_name=snapshots,
                stratum="safety_web", critical=True,
                selectors=("binding:oversize_snapshot", "binding:oversize_bytes"),
                requirement={"maximum_bytes": 64, "actual_payload_length_is_authoritative": True},
                observation={
                    "snapshot_token": "oversize", "display_name": "Oversize Robotics",
                    "claimed_content_sha256": oversize_digest,
                    "claimed_byte_length": 32,
                }, evidence=[{
                    "snapshot_token": "oversize", "content_sha256": oversize_digest,
                    "byte_length": 32, "payload": oversize_bytes.decode(),
                    "actual_byte_length": 65, "provided_payload": True,
                    "evidence_id": "evidence:oversize",
                }],
            ),
            _probe(
                "cal-v2-sw-008", source_path=ATOMIC, test_name=snapshots,
                stratum="safety_web", critical=True,
                selectors=("binding:tampered_snapshot", "binding:tampered_bytes"),
                requirement={"maximum_bytes": 64, "digest_must_match_payload": True},
                observation={
                    "snapshot_token": "tampered", "display_name": "Tampered Robotics",
                    "claimed_content_sha256": "f" * 64,
                    "claimed_byte_length": len(tampered_bytes),
                }, evidence=[{
                    "snapshot_token": "tampered", "content_sha256": "f" * 64,
                    "actual_content_sha256": hashlib.sha256(tampered_bytes).hexdigest(),
                    "byte_length": len(tampered_bytes),
                    "payload": tampered_bytes.decode(), "provided_payload": True,
                    "evidence_id": "evidence:tampered",
                }],
            ),
            _probe(
                "cal-v2-sw-009", source_path=ATOMIC, test_name=snapshots,
                stratum="safety_web", critical=True,
                selectors=("binding:missing_payload_snapshot", "binding:web_inputs"),
                requirement={"recorded_payload_required": True, "metadata_alone_is_insufficient": True},
                observation={
                    "snapshot_token": "missing-payload",
                    "display_name": "Metadata-only Robotics",
                    "claimed_content_sha256": missing_digest,
                    "claimed_byte_length": len(missing_bytes),
                }, evidence=[{
                    "snapshot_token": "missing-payload", "content_sha256": missing_digest,
                    "byte_length": len(missing_bytes), "provided_payload": False,
                    "evidence_id": "evidence:missing-payload",
                }],
            ),
            _probe(
                "cal-v2-sw-010", source_path=ATOMIC, test_name=snapshots,
                stratum="safety_web", critical=True,
                selectors=("binding:direct_oversize_snapshot", "binding:direct_oversize_item"),
                requirement={"maximum_bytes": 64, "actual_payload_length_is_authoritative": True},
                observation={
                    "snapshot_token": "direct-oversize", "display_name": "Direct Oversize Robotics",
                    "claimed_content_sha256": oversize_digest, "claimed_byte_length": 1,
                    "candidate_surface": "direct_item",
                }, evidence=[{
                    "snapshot_token": "direct-oversize", "content_sha256": oversize_digest,
                    "byte_length": 1, "payload": oversize_bytes.decode(),
                    "actual_byte_length": 65, "provided_payload": True,
                    "evidence_id": "evidence:direct-oversize",
                }],
            ),
        ]
    )
    return rows


def _sufficiency_blueprints() -> list[dict[str, Any]]:
    sufficiency = "test_sufficiency_is_per_material_part_and_product_capability_is_direct"
    assessment = "test_assessment_replays_evidence_relevance_and_degrades_visibly"
    company = "company:example-robotics"
    product = "product:delivery-robot-x1"
    capability = "autonomous_elevator_button_operation"
    identity = _evidence(
        "evidence:company-identity", company, "identity", "Example Robotics",
        object_id=company,
        snippet="The retained registry record identifies Example Robotics.",
    )
    role_a = _evidence(
        "evidence:role-a", company, "current_role", "chief executive:Alice",
        object_id=company,
        snippet="The retained local profile names Alice as chief executive.",
    )
    role_b = _evidence(
        "evidence:role-b", company, "current_role", "chief executive:Bob",
        object_id=company,
        snippet="A second retained source names Bob as chief executive.",
    )
    company_general = _evidence(
        "evidence:company-general-capability", company, "capability", capability,
        object_id=company,
        snippet="The Company describes general elevator integration capability.",
    )
    other_product = _evidence(
        "evidence:other-product-capability", "product:delivery-robot-x2",
        "capability", capability, object_id="product:delivery-robot-x2",
        snippet="Another Product is directly demonstrated with the requested capability.",
    )
    technology = _evidence(
        "evidence:technology-route", "technology:elevator-integration",
        "demonstrated_use", capability, object_id="technology:elevator-integration",
        snippet="A Technology route may enable the capability in principle.",
    )
    wrong_capability = _evidence(
        "evidence:same-product-wrong-capability", product, "capability",
        "autonomous_door_opening", object_id=product,
        snippet="The named Product is directly evidenced for a different capability.",
    )
    product_requirement = {
        "part_id": "part:product-capability", "subject_id": product,
        "predicate": "capability", "requested_value": capability,
        "direct_named_product_binding_required": True,
    }
    rows = [
        _probe(
            "cal-v2-is-001", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=False,
            selectors=("binding:parts", "binding:report"),
            requirement={
                "part_id": "part:company-identity", "subject_id": company,
                "predicate": "identity", "requested_value": "Example Robotics",
            },
            observation={
                "part_id": "part:company-identity", "proposed_outcome": "supported",
                "evidence_ids": ["evidence:company-identity"],
                "rationale": "Direct retained identity evidence exists.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[identity],
        ),
        _probe(
            "cal-v2-is-002", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=False,
            selectors=("binding:parts", "binding:report"),
            requirement={
                "part_id": "part:current-role", "subject_id": company,
                "predicate": "current_role", "requested_value": "chief executive",
                "material_conflict_must_be_preserved": True,
            },
            observation={
                "part_id": "part:current-role", "proposed_outcome": "conflicting",
                "evidence_ids": ["evidence:role-a", "evidence:role-b"],
                "rationale": "Retained current-role evidence conflicts.",
                "uncertainty": "high", "confidence": 0.5,
            }, evidence=[role_a, role_b],
        ),
        _probe(
            "cal-v2-is-003", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=True,
            selectors=("binding:evidence", "binding:forbidden_product_support"),
            requirement=product_requirement,
            observation={
                "part_id": "part:product-capability", "proposed_outcome": "supported",
                "evidence_ids": ["evidence:company-general-capability"],
                "rationale": "A hostile proposal propagates Company capability to the Product.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[company_general],
        ),
        _probe(
            "cal-v2-is-004", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=True,
            selectors=("binding:evidence", "binding:forbidden_product_support"),
            requirement=product_requirement,
            observation={
                "part_id": "part:product-capability", "proposed_outcome": "supported",
                "evidence_ids": ["evidence:other-product-capability"],
                "rationale": "A hostile proposal cites a non-direct source.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[other_product],
        ),
        _probe(
            "cal-v2-is-005", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=True,
            selectors=("binding:evidence", "binding:forbidden_product_support"),
            requirement=product_requirement,
            observation={
                "part_id": "part:product-capability", "proposed_outcome": "supported",
                "evidence_ids": ["evidence:technology-route"],
                "rationale": "A hostile proposal cites a non-direct source.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[technology],
        ),
        _probe(
            "cal-v2-is-006", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=True,
            selectors=("binding:evidence", "binding:forbidden_product_support"),
            requirement=product_requirement,
            observation={
                "part_id": "part:product-capability", "proposed_outcome": "supported",
                "evidence_ids": ["evidence:same-product-wrong-capability"],
                "rationale": "A hostile proposal cites a non-direct source.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[wrong_capability],
        ),
        _probe(
            "cal-v2-is-007", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=True,
            selectors=("binding:forbidden_product_support", "binding:forbidden_product"),
            requirement=product_requirement,
            observation={
                "part_id": "part:product-capability", "proposed_outcome": "supported",
                "evidence_ids": ["model-memory:product-capability"],
                "rationale": "A hostile proposal cites a non-direct source.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[],
        ),
    ]
    direct = _evidence(
        "evidence:direct-product-capability", product, "capability", capability,
        object_id=product,
        snippet=("A retained dated demonstration directly binds delivery-robot-x1 to "
                 "autonomous elevator button operation."),
    )
    rows.append(
        _probe(
            "cal-v2-is-008", source_path=SUFFICIENCY, test_name=sufficiency,
            stratum="insufficiency_assessment", critical=True,
            selectors=("binding:direct_product_evidence", "binding:positive_product"),
            requirement=product_requirement,
            observation={
                "part_id": "part:product-capability", "proposed_outcome": "supported",
                "evidence_ids": ["evidence:direct-product-capability"],
                "rationale": "Direct dated evidence binds the named Product and capability.",
                "uncertainty": "low", "confidence": 0.9,
            }, evidence=[direct],
        )
    )
    assessment_company = "company:s9i-assessment"
    deployment = _evidence(
        "evidence:s9i:deployment", assessment_company, "deployment_stage", "production",
        object_id=assessment_company, status="accepted",
        snippet="One retained source records a production deployment.",
    )
    pilot = _evidence(
        "evidence:s9i:pilot", assessment_company, "deployment_stage", "pilot",
        object_id=assessment_company, status="reported",
        snippet="Another retained source records only a pilot.",
    )
    unrelated = _evidence(
        "evidence:s9i:unrelated-profile", assessment_company, "profile_summary",
        "unrelated profile", object_id=assessment_company, status="accepted",
        snippet="This profile does not establish production scale.",
    )
    rows.extend(
        [
            _probe(
                "cal-v2-is-009", source_path=IMPLEMENTATION, test_name=assessment,
                stratum="insufficiency_assessment", critical=False,
                selectors=("binding:conflicting", "binding:conflict"),
                requirement={
                    "assessment_dimension": "部署阶段",
                    "subject_id": assessment_company,
                    "predicate": "deployment_stage",
                    "conflict_must_be_preserved": True,
                },
                observation={
                    "name": "部署阶段", "proposed_outcome": "conflicting_evidence",
                    "evidence_ids": ["evidence:s9i:deployment", "evidence:s9i:pilot"],
                    "conclusion": "The stage conclusion is conditional because sources conflict.",
                    "uncertainty": "high",
                }, evidence=[deployment, pilot],
            ),
            _probe(
                "cal-v2-is-010", source_path=IMPLEMENTATION, test_name=assessment,
                stratum="insufficiency_assessment", critical=True,
                selectors=("binding:wrong_binding", "binding:missing"),
                requirement={
                    "assessment_dimension": "量产规模",
                    "subject_id": assessment_company,
                    "predicate": "production_scale",
                    "evidence_binding_must_match": True,
                },
                observation={
                    "name": "量产规模", "proposed_outcome": "supported",
                    "evidence_ids": ["evidence:s9i:unrelated-profile"],
                    "evidence_binding": {
                        "subject_id": assessment_company, "predicate": "production_scale",
                        "value": "mass_production", "status": "accepted",
                    },
                    "conclusion": "POISON_UNRELATED_SCALE_CONCLUSION",
                    "uncertainty": "low",
                }, evidence=[unrelated],
            ),
        ]
    )
    return rows


def _blueprints() -> list[dict[str, Any]]:
    return [
        *_claim_evidence_blueprints(),
        *_identity_blueprints(),
        *_context_blueprints(),
        *_safety_blueprints(),
        *_sufficiency_blueprints(),
    ]


def _walk_forbidden_keys(value: object, path: str = "$.") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FORBIDDEN_LABEL_KEYS:
                raise ValueError(f"forbidden prefilled label/decision field at {path}{key}")
            _walk_forbidden_keys(child, f"{path}{key}.")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden_keys(child, f"{path}{index}.")


def _assignment_count(function: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> int:
    count = 0
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id == name:
                count += 1
    return count


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(functions) != 1:
        raise ValueError(f"fixture locator function {name!r} is not unique")
    return functions[0]


def _validate_selector(
    tree: ast.Module,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    selector: str,
) -> None:
    if selector.startswith("binding:"):
        name = selector.removeprefix("binding:")
        if _assignment_count(function, name) != 1:
            raise ValueError(f"fixture locator selector {selector!r} is not unique")
        return
    if selector.startswith("literal:"):
        try:
            literal = json.loads(selector.removeprefix("literal:"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid literal fixture selector {selector!r}") from exc
        count = sum(
            isinstance(node, ast.Constant) and node.value == literal
            for node in ast.walk(function)
        )
        if count != 1:
            raise ValueError(f"fixture locator selector {selector!r} is not unique")
        return
    if selector.startswith("helper:"):
        parts = selector.split(":", 3)
        if len(parts) != 4 or parts[2] != "binding":
            raise ValueError(f"invalid helper fixture selector {selector!r}")
        helper = _function(tree, parts[1])
        if _assignment_count(helper, parts[3]) != 1:
            raise ValueError(f"helper fixture locator {selector!r} is not unique")
        return
    raise ValueError(f"unknown fixture locator selector {selector!r}")


def _validate_source_locators(rows: list[dict[str, Any]], source_root: Path) -> None:
    parsed: dict[str, ast.Module] = {}
    for row in rows:
        identity = row["source_identity"]
        relative = identity["path"]
        if relative not in SOURCE_SHA256S:
            raise ValueError(f"source path is not authorized: {relative}")
        path = (source_root / relative).resolve()
        if not path.is_file():
            raise ValueError(f"source fixture is missing: {relative}")
        actual_sha = _raw_sha256(path)
        if actual_sha != identity["source_sha256"]:
            raise ValueError(f"source fixture hash mismatch: {relative}")
        if actual_sha != SOURCE_SHA256S[relative]:
            raise ValueError(f"source fixture hash is not the audited identity: {relative}")
        if relative not in parsed:
            try:
                parsed[relative] = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError) as exc:
                raise ValueError(f"source fixture cannot be parsed: {relative}") from exc
        tree = parsed[relative]
        locator = row["requirement"].get("fixture_locator")
        if not isinstance(locator, dict) or set(locator) != {"function", "selectors"}:
            raise ValueError(f"fixture locator is missing for {row['sample_id']}")
        if locator["function"] != identity["test_name"]:
            raise ValueError(f"fixture locator/test name mismatch for {row['sample_id']}")
        function = _function(tree, identity["test_name"])
        selectors = locator["selectors"]
        if not isinstance(selectors, list) or not selectors:
            raise ValueError(f"fixture locator selectors are missing for {row['sample_id']}")
        for selector in selectors:
            if not isinstance(selector, str):
                raise ValueError(f"fixture locator selector is not text for {row['sample_id']}")
            _validate_selector(tree, function, selector)


def _semantic_duplicate_sha(row: dict[str, Any]) -> str:
    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: normalize(child)
                for key, child in value.items()
                if key
                not in {
                    "fixture_locator",
                    "request_sha256",
                    "sample_id",
                    "source_identity",
                    "source_sha256",
                }
            }
        if isinstance(value, list):
            return [normalize(child) for child in value]
        return value

    return canonical_sha256(normalize(row))


def _validate_bank(rows: list[dict[str, Any]], source_root: Path) -> list[dict[str, Any]]:
    if len(rows) != 60:
        raise ValueError("calibration bank must contain exactly 60 requests")
    expected_ids = [row["sample_id"] for row in _blueprints()]
    actual_ids = [row.get("sample_id") for row in rows]
    if actual_ids != expected_ids:
        if sorted(str(value) for value in actual_ids) == sorted(expected_ids):
            raise ValueError("calibration bank order changed")
        if len(actual_ids) != len(set(actual_ids)):
            raise ValueError("duplicate calibration request/sample identity")
        raise ValueError("calibration bank sample IDs differ from the frozen selection")
    validated: list[dict[str, Any]] = []
    for raw in rows:
        _walk_forbidden_keys(raw)
        try:
            request = CalibrationRequestV2.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"calibration request schema invalid: {exc}") from exc
        dumped = request.model_dump(mode="json")
        request_without_hash = {
            key: value for key, value in dumped.items() if key != "request_sha256"
        }
        if dumped["request_sha256"] != canonical_sha256(request_without_hash):
            raise ValueError(f"calibration request hash mismatch: {dumped['sample_id']}")
        validated.append(dumped)
    request_hashes = [row["request_sha256"] for row in validated]
    if len(request_hashes) != len(set(request_hashes)):
        raise ValueError("duplicate calibration request hash")
    semantic_hashes = [_semantic_duplicate_sha(row) for row in validated]
    if len(semantic_hashes) != len(set(semantic_hashes)):
        raise ValueError("semantic duplicate calibration request")
    strata = Counter(row["stratum"] for row in validated)
    if strata != Counter(STRATA):
        raise ValueError(f"calibration bank strata quota mismatch: {dict(strata)}")
    critical = Counter(
        row["stratum"] for row in validated if row["critical_probe"]
    )
    if critical != Counter(EXPECTED_CRITICAL):
        raise ValueError(f"calibration critical-probe capacity mismatch: {dict(critical)}")
    for row in validated:
        if row["requirement_kind"] != KINDS[row["stratum"]]:
            raise ValueError(f"requirement kind/stratum mismatch: {row['sample_id']}")
    _validate_source_locators(validated, source_root)
    if validated != _blueprints():
        raise ValueError("calibration bank content differs from the frozen blueprint")
    return validated


def _load_json(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{kind} cannot be read as JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{kind} must be a JSON object")
    return value


def _load_bank(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("calibration bank cannot be read as JSONL") from exc
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("calibration bank rows must be JSON objects")
    return values


def _audit_projection(row: dict[str, Any]) -> dict[str, Any]:
    requirement = row.get("requirement")
    if not isinstance(requirement, dict):
        raise ValueError("provenance projection requires a structured requirement")
    requirement_without_locator = {
        key: value for key, value in requirement.items() if key != "fixture_locator"
    }
    return {
        "as_of": row.get("as_of"),
        "candidate_observation": row.get("candidate_observation"),
        "critical_probe": row.get("critical_probe"),
        "evidence_snapshots": row.get("evidence_snapshots"),
        "policy_id": row.get("policy_id"),
        "requirement": requirement_without_locator,
        "requirement_kind": row.get("requirement_kind"),
        "stratum": row.get("stratum"),
    }


def _admit_provenance(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        raw_sha256 = _raw_sha256(path)
    except OSError as exc:
        raise ValueError("calibration provenance anchor is unavailable") from exc
    if raw_sha256 != PROVENANCE_RAW_SHA256:
        raise ValueError("calibration provenance raw identity mismatch")
    artifact = _load_json(path, "calibration provenance")
    if set(artifact) != {
        "content_sha256",
        "projection_sha256s",
        "sample_ids",
        "schema_version",
        "source_groups",
    }:
        raise ValueError("calibration provenance schema fields mismatch")
    content_sha256 = artifact.get("content_sha256")
    content = {
        key: value for key, value in artifact.items() if key != "content_sha256"
    }
    if (
        content_sha256 != canonical_sha256(content)
        or content_sha256 != PROVENANCE_CONTENT_SHA256
    ):
        raise ValueError("calibration provenance content identity mismatch")
    if artifact.get("schema_version") != PROVENANCE_SCHEMA:
        raise ValueError("calibration provenance schema version mismatch")

    expected_ids = [row["sample_id"] for row in rows]
    sample_ids = artifact.get("sample_ids")
    if sample_ids != expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise ValueError("calibration provenance sample IDs mismatch")

    source_groups = artifact.get("source_groups")
    if not isinstance(source_groups, list):
        raise ValueError("calibration provenance source groups are invalid")
    bindings: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    for group in source_groups:
        if not isinstance(group, dict) or set(group) != {
            "path",
            "samples",
            "source_sha256",
            "test_name",
        }:
            raise ValueError("calibration provenance source group is invalid")
        group_samples = group["samples"]
        if not isinstance(group_samples, list):
            raise ValueError("calibration provenance source samples are invalid")
        for sample in group_samples:
            if not isinstance(sample, dict) or set(sample) != {
                "sample_id",
                "selectors",
            }:
                raise ValueError("calibration provenance source sample is invalid")
            sample_id = sample["sample_id"]
            selectors = sample["selectors"]
            if (
                not isinstance(sample_id, str)
                or not isinstance(selectors, list)
                or not selectors
                or not all(isinstance(selector, str) for selector in selectors)
                or sample_id in bindings
            ):
                raise ValueError("calibration provenance source binding is invalid")
            if not all(
                isinstance(group[field], str)
                for field in ("path", "source_sha256", "test_name")
            ):
                raise ValueError("calibration provenance source identity is invalid")
            bindings[sample_id] = (
                group["path"],
                group["source_sha256"],
                group["test_name"],
                tuple(selectors),
            )
    if list(bindings) != expected_ids:
        raise ValueError("calibration provenance source bindings are incomplete")

    projection_sha256s = artifact.get("projection_sha256s")
    if (
        not isinstance(projection_sha256s, dict)
        or len(projection_sha256s) != len(expected_ids)
        or set(projection_sha256s) != set(expected_ids)
    ):
        raise ValueError("calibration provenance projection identities are incomplete")
    for row in rows:
        sample_id = row["sample_id"]
        source = row["source_identity"]
        locator = row["requirement"]["fixture_locator"]
        actual_binding = (
            source["path"],
            source["source_sha256"],
            source["test_name"],
            tuple(locator["selectors"]),
        )
        if bindings[sample_id] != actual_binding or locator["function"] != source["test_name"]:
            raise ValueError(
                f"calibration provenance source/locator mismatch: {sample_id}"
            )
        projection_sha256 = projection_sha256s.get(sample_id)
        if (
            not isinstance(projection_sha256, str)
            or projection_sha256 != canonical_sha256(_audit_projection(row))
        ):
            raise ValueError(
                f"calibration provenance projection mismatch: {sample_id}"
            )
    return artifact


def _admit_packet(path: Path) -> dict[str, Any]:
    if _raw_sha256(path) != PACKET_RAW_SHA256:
        raise ValueError("review packet raw identity mismatch")
    packet = _load_json(path, "review packet")
    content_sha = packet.get("content_sha256")
    content = {key: value for key, value in packet.items() if key != "content_sha256"}
    if content_sha != canonical_sha256(content) or content_sha != PACKET_CONTENT_SHA256:
        raise ValueError("review packet content identity mismatch")
    if packet.get("schema_version") != "canonical-v2-human-review-packet-v1":
        raise ValueError("review packet schema mismatch")
    if len(packet.get("review_candidates", ())) != 29:
        raise ValueError("review packet contract-candidate count mismatch")
    if len(packet.get("exclusion_candidates", ())) != 23:
        raise ValueError("review packet exclusion-candidate count mismatch")
    return packet


def _admit_policy(path: Path) -> dict[str, Any]:
    policy = _load_json(path, "calibration policy")
    if policy != EXACT_POLICY:
        raise ValueError("calibration policy differs from exact v2 policy")
    return policy


def _assert_write_targets_safe(
    *,
    formal_outputs: dict[str, Path],
    protected_inputs: dict[str, Path],
    source_root: Path,
) -> None:
    resolved_outputs = {
        name: path.resolve() for name, path in formal_outputs.items()
    }
    if len(set(resolved_outputs.values())) != len(resolved_outputs):
        raise ValueError("output collision: formal outputs must resolve to distinct paths")
    resolved_protected = {
        name: path.resolve() for name, path in protected_inputs.items()
    }
    resolved_protected.update(
        {
            f"authorized source {relative}": (source_root / relative).resolve()
            for relative in SOURCE_SHA256S
        }
    )
    for output_name, output_path in resolved_outputs.items():
        for input_name, input_path in resolved_protected.items():
            if output_path == input_path:
                raise ValueError(
                    f"output collision: {output_name} resolves to protected input "
                    f"{input_name}"
                )


def _stage_bytes(destination: Path, payload: bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _atomic_write_bytes(destination: Path, payload: bytes) -> None:
    temporary = _stage_bytes(destination, payload)
    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def build_workload(
    packet_path: str | Path = DEFAULT_PACKET,
    *,
    policy_path: str | Path = DEFAULT_POLICY,
    bank_path: str | Path = DEFAULT_BANK,
    provenance_path: str | Path = DEFAULT_PROVENANCE,
    source_root: str | Path = REPO_ROOT,
    output_path: str | Path | None = None,
    check: bool = False,
) -> dict[str, Any]:
    """Build or byte-check the frozen 29+23+60 review workload."""

    packet_source = Path(packet_path).resolve()
    policy_source = Path(policy_path).resolve()
    bank_source = Path(bank_path).resolve()
    provenance_source = Path(provenance_path).resolve()
    source_base = Path(source_root).resolve()
    destination = None if output_path is None else Path(output_path).resolve()
    if destination is not None:
        _assert_write_targets_safe(
            formal_outputs={"workload": destination},
            protected_inputs={
                "packet": packet_source,
                "policy": policy_source,
                "bank": bank_source,
                "provenance": provenance_source,
            },
            source_root=source_base,
        )
    packet = _admit_packet(packet_source)
    policy = _admit_policy(policy_source)
    raw_rows = _load_bank(bank_source)
    rows = _validate_bank(raw_rows, source_base)
    provenance = _admit_provenance(provenance_source, rows)
    payload: dict[str, Any] = {
        "schema_version": WORKLOAD_SCHEMA,
        "workload_id": WORKLOAD_ID,
        "packet_identity": {
            "schema_version": packet["schema_version"],
            "raw_sha256": _raw_sha256(packet_source),
            "content_sha256": packet["content_sha256"],
        },
        "policy_identity": {
            "raw_sha256": _raw_sha256(policy_source),
            "content_sha256": canonical_sha256(policy),
        },
        "bank_identity": {
            "raw_sha256": _raw_sha256(bank_source),
            "content_sha256": canonical_sha256(raw_rows),
            "row_count": len(rows),
        },
        "provenance_identity": {
            "schema_version": provenance["schema_version"],
            "raw_sha256": _raw_sha256(provenance_source),
            "content_sha256": provenance["content_sha256"],
        },
        "policy": policy,
        "counts": {
            "contract_reviews": 29,
            "exclusion_reviews": 23,
            "calibration_probes": 60,
            "human_actions": 112,
        },
        "contract_reviews": packet["review_candidates"],
        "exclusion_reviews": packet["exclusion_candidates"],
        "calibration_probes": rows,
    }
    workload = {**payload, "content_sha256": canonical_sha256(payload)}
    expected = _pretty_bytes(workload)
    if check:
        if destination is None:
            raise ValueError("workload check requires an output path")
        if not destination.is_file() or destination.read_bytes() != expected:
            raise ValueError("review workload deterministic byte check failed")
    elif destination is not None:
        _atomic_write_bytes(destination, expected)
    return workload


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    packet_path = args.packet.resolve()
    policy_path = args.policy.resolve()
    bank_path = args.bank.resolve()
    provenance_path = args.provenance.resolve()
    output_path = args.output.resolve()
    source_root = args.source_root.resolve()
    formal_outputs = (policy_path, bank_path, output_path)
    _assert_write_targets_safe(
        formal_outputs={
            "policy": formal_outputs[0],
            "bank": formal_outputs[1],
            "workload": formal_outputs[2],
        },
        protected_inputs={"packet": packet_path, "provenance": provenance_path},
        source_root=source_root,
    )

    generated_rows = _blueprints()
    validated_rows = _validate_bank(generated_rows, source_root)
    _admit_provenance(provenance_path, validated_rows)
    _admit_packet(packet_path)
    expected_policy = _pretty_bytes(EXACT_POLICY)
    expected_bank = b"".join(
        _canonical_bytes(row) + b"\n" for row in generated_rows
    )
    if args.check:
        if not policy_path.is_file() or policy_path.read_bytes() != expected_policy:
            raise ValueError("calibration policy deterministic byte check failed")
        if not bank_path.is_file() or bank_path.read_bytes() != expected_bank:
            raise ValueError("calibration bank deterministic byte check failed")
        workload = build_workload(
            packet_path=packet_path,
            policy_path=policy_path,
            bank_path=bank_path,
            provenance_path=provenance_path,
            source_root=source_root,
            output_path=output_path,
            check=True,
        )
    else:
        staged_policy: Path | None = None
        staged_bank: Path | None = None
        staged_workload: Path | None = None
        try:
            staged_policy = _stage_bytes(policy_path, expected_policy)
            staged_bank = _stage_bytes(bank_path, expected_bank)
            workload = build_workload(
                packet_path=packet_path,
                policy_path=staged_policy,
                bank_path=staged_bank,
                provenance_path=provenance_path,
                source_root=source_root,
            )
            staged_workload = _stage_bytes(output_path, _pretty_bytes(workload))
            os.replace(staged_policy, policy_path)
            staged_policy = None
            os.replace(staged_bank, bank_path)
            staged_bank = None
            os.replace(staged_workload, output_path)
            staged_workload = None
        finally:
            for temporary in (staged_policy, staged_bank, staged_workload):
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "bank_raw_sha256": _raw_sha256(bank_path),
                "content_sha256": workload["content_sha256"],
                "counts": workload["counts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
