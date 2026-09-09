#!/usr/bin/env python3
"""Build and verify the deterministic Canonical V2 S2C draft corpus."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "claim_level_case_contract.py"
CORPUS_ID = "canonical-v2-s2c-v1"
CONTRACT_AS_OF = "2026-07-13T17:44:15Z"
S2_ACCEPTED_AT = "2026-07-11T15:10:32Z"

ARTIFACT_NAMES = (
    "case-accounting-v1.jsonl",
    "claim-level-corpus-manifest-v1.json",
    "claim-level-corpus-v1.jsonl",
    "source-snapshots-v1.jsonl",
)

SOURCE_CORPORA: tuple[tuple[str, str, int, str], ...] = (
    (
        "regression-v1",
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpora/regression-v1.jsonl",
        40,
        "f2656e8c2f0803452af18fa0d478eec1b1e1b94eaa97ef48d06d0828401297da",
    ),
    (
        "challenge-v1",
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpora/challenge-v1.jsonl",
        12,
        "ee46c677af668131fb8da568fabd6386659f3287d0bdb0fd740f7069497f6f9f",
    ),
)

FROZEN_INPUTS: tuple[tuple[str, str], ...] = (
    (
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/corpus-manifest.json",
        "dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088",
    ),
    (
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-inventory.json",
        "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09",
    ),
    (
        "docs/测试集答案.xlsx",
        "edd95009a8516c73831d889a0d221d85da0a9ffad9c9f7da244d12dfce280c5b",
    ),
)

BLOCKED_WORKBOOK_CASE_IDS = frozenset(
    {
        "wb-r002",
        "wb-r003",
        "wb-r005",
        "wb-r006",
        "wb-r007",
        "wb-r011",
        "wb-r014",
        "wb-r015",
        "wb-r017",
        "wb-r018",
        "wb-r020",
        "wb-r022",
        "wb-r023",
        "wb-r025",
        "wb-r027",
        "wb-r029",
        "wb-r031",
        "wb-r033",
        "wb-r035",
        "wb-r037",
        "wb-r039",
        "wb-r041",
        "wb-r042",
    }
)

NEAR_NAME_CASE_IDS = frozenset({"ch-reviewed-badcase-near-name-company", "wb-r012"})
SAFETY_CASE_ID = "wb-r009"
SAFETY_SPEC_PATH = (
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/"
    "specs/grounded-progressive-answer/spec.md"
)

_LIST_INTENT = re.compile(r"有哪些|哪些|有谁|有什么|几种|列出|分别有哪些")
_BOUNDED_UNIVERSE = re.compile(r"上述|这些|第[一二三四五六七八九十0-9]+家")
_EXPLICIT_REPRESENTATIVE_CASE_IDS = frozenset(
    {"ch-time-geo-negation", "prd-paper-topic-recent"}
)
_STAGE_ORDER = (
    "query_understanding",
    "session_transition",
    "candidate_recall",
    "provider_execution",
    "fusion_sufficiency",
    "claim_evidence_mapping",
    "rendered_answer",
)

_BEHAVIOR_MAP: dict[str, tuple[str, str, str, Callable[[Any], Any]]] = {
    "affected_claim_disclosed": (
        "rendered_answer",
        "affected_claim_conflict_disclosure",
        "equals",
        bool,
    ),
    "alias_resolution_trace_required": (
        "query_understanding",
        "alias_resolution_trace",
        "equals",
        bool,
    ),
    "assessment_dimensions_explicit": (
        "rendered_answer",
        "assessment_dimensions",
        "equals",
        bool,
    ),
    "categorical_unsupported_verdict_forbidden": (
        "rendered_answer",
        "categorical_unsupported_verdict_count",
        "equals",
        lambda _: 0,
    ),
    "clarification_or_candidates": (
        "rendered_answer",
        "ambiguity_resolution",
        "one_of",
        lambda _: ["answered_with_evidence", "candidate_selection", "clarification"],
    ),
    "conflict_disclosed": (
        "rendered_answer",
        "conflict_disclosure",
        "equals",
        bool,
    ),
    "conflicting_assertions_retained": (
        "fusion_sufficiency",
        "conflicting_assertions_retained",
        "equals",
        bool,
    ),
    "constraints_preserved": (
        "query_understanding",
        "constraint_preservation",
        "equals",
        bool,
    ),
    "deterministic_degradation_required": (
        "rendered_answer",
        "deterministic_degradation",
        "equals",
        bool,
    ),
    "dimensions_and_uncertainty_required": (
        "rendered_answer",
        "assessment_dimensions_and_uncertainty",
        "equals",
        bool,
    ),
    "exact_identifier_preserved": (
        "query_understanding",
        "exact_identifier",
        "equals",
        bool,
    ),
    "identity_evidence_required": (
        "claim_evidence_mapping",
        "identity_evidence",
        "equals",
        bool,
    ),
    "injected_failure": (
        "provider_execution",
        "provider_failure",
        "equals",
        lambda value: value,
    ),
    "interaction": (
        "query_understanding",
        "query_interaction",
        "equals",
        lambda value: value,
    ),
    "local_and_web_fused": (
        "fusion_sufficiency",
        "local_web_fusion",
        "equals",
        bool,
    ),
    "material_claims_require_evidence": (
        "claim_evidence_mapping",
        "material_claim_evidence",
        "equals",
        bool,
    ),
    "missing_evidence_not_filled_from_model_memory": (
        "rendered_answer",
        "model_memory_fill_count",
        "equals",
        lambda _: 0,
    ),
    "must_not_use_undisplayed_member": (
        "session_transition",
        "undisplayed_member_use_count",
        "equals",
        lambda _: 0,
    ),
    "prior_anchor_cleared": (
        "session_transition",
        "prior_anchor_state",
        "equals",
        lambda _: "cleared",
    ),
    "progressive_not_exhaustive": (
        "rendered_answer",
        "false_exhaustiveness_count",
        "equals",
        lambda _: 0,
    ),
    "relation_direction": (
        "query_understanding",
        "relationship_direction",
        "equals",
        lambda value: value,
    ),
    "requires_prior_anchor": (
        "session_transition",
        "prior_anchor_required",
        "equals",
        lambda value: value,
    ),
    "supported_partial_answer_or_limitation": (
        "rendered_answer",
        "supported_partial_or_limitation",
        "equals",
        bool,
    ),
    "supported_subset_answered": (
        "rendered_answer",
        "supported_subset",
        "equals",
        bool,
    ),
    "targeted_supplemental_attempt_bounded": (
        "fusion_sufficiency",
        "supplemental_attempt_policy",
        "equals",
        lambda _: "bounded",
    ),
    "top_k_relevance_evaluated": (
        "candidate_recall",
        "top_k_relevance",
        "equals",
        lambda value: value,
    ),
    "unsupported_capability_inference_forbidden": (
        "rendered_answer",
        "unsupported_capability_inference_count",
        "equals",
        lambda _: 0,
    ),
    "unsupported_scope_disclosed": (
        "rendered_answer",
        "unsupported_scope_disclosure",
        "equals",
        bool,
    ),
    "uses_displayed_set_only": (
        "session_transition",
        "displayed_set_scope",
        "equals",
        lambda _: "displayed_only",
    ),
    "web_augmentation_required": (
        "candidate_recall",
        "web_invocation",
        "equals",
        bool,
    ),
    "web_source_nature_disclosed": (
        "rendered_answer",
        "source_nature_disclosure",
        "equals",
        bool,
    ),
    "zero_protected_slot_loss": (
        "query_understanding",
        "protected_slot_loss_count",
        "equals",
        lambda _: 0,
    ),
    "zero_wrong_identity_substitution": (
        "rendered_answer",
        "identity_substitution_count",
        "equals",
        lambda _: 0,
    ),
}


def _load_contract_module() -> Any:
    if not CONTRACT_PATH.is_file():
        raise ValueError(f"claim-level contract module is absent: {CONTRACT_PATH}")
    spec = importlib.util.spec_from_file_location(
        "canonical_v2_s2c_contract", CONTRACT_PATH
    )
    if spec is None or spec.loader is None:
        raise ValueError("claim-level contract module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("artifact content is not canonical JSON") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _with_content_hash(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _canonical_sha256(result)
    return result


def _with_record_hash(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("record_sha256", None)
    result["record_sha256"] = _canonical_sha256(result)
    return result


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(record) + b"\n" for record in records)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSONL artifact: {path}") from exc


def _verify_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise ValueError(f"frozen source is absent: {path}")
    actual = _file_sha256(path)
    if actual != expected:
        raise ValueError(
            f"frozen source hash mismatch for {path}: expected {expected}, actual {actual}"
        )


def _load_source_cases(
    repo_root: Path,
) -> tuple[list[tuple[dict[str, Any], str, str]], dict[str, dict[str, Any]]]:
    for relative_path, expected_hash in FROZEN_INPUTS:
        _verify_hash(repo_root / relative_path, expected_hash)

    records: list[tuple[dict[str, Any], str, str]] = []
    sources: dict[str, dict[str, Any]] = {}
    seen_case_ids: set[str] = set()
    for corpus_id, relative_path, expected_count, expected_hash in SOURCE_CORPORA:
        source_path = repo_root / relative_path
        _verify_hash(source_path, expected_hash)
        corpus_cases = _read_jsonl(source_path)
        if len(corpus_cases) != expected_count:
            raise ValueError(
                f"frozen {corpus_id} count mismatch: expected {expected_count}, "
                f"actual {len(corpus_cases)}"
            )
        for source_case in corpus_cases:
            case_id = source_case.get("case_id")
            if not isinstance(case_id, str) or case_id in seen_case_ids:
                raise ValueError(
                    f"duplicate or invalid frozen source case ID: {case_id}"
                )
            if source_case.get("corpus") != corpus_id:
                raise ValueError(
                    f"source case {case_id} is cross-wired to another corpus"
                )
            seen_case_ids.add(case_id)
            records.append((source_case, corpus_id, relative_path))
        sources[corpus_id] = {
            "case_count": expected_count,
            "path": relative_path,
            "sha256": expected_hash,
        }
    if len(records) != 52:
        raise ValueError(
            f"frozen S2 source accounting must contain 52 cases, got {len(records)}"
        )
    return records, sources


def _origin_artifact(
    repo_root: Path,
    source_case: dict[str, Any],
) -> tuple[str, str, str]:
    legacy_source = str(source_case.get("source", ""))
    source_path_text, separator, source_selector = legacy_source.partition("#")
    source_path = repo_root / source_path_text
    if source_path.is_file():
        artifact_path = source_path_text
        if source_case.get("source_row") is not None:
            row = int(source_case["source_row"])
            selector = f"Sheet1!A{row}:C{row}"
        elif separator:
            selector = source_selector
        else:
            selector = f"source_case_id={source_case['case_id']}"
    else:
        artifact_path = (
            ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/build_corpora.py"
        )
        selector = (
            f"declared_case={source_case['case_id']};legacy_source={legacy_source}"
        )
    return artifact_path, _file_sha256(repo_root / artifact_path), selector


def _requirement_snapshot(
    source_case: dict[str, Any], corpus_id: str, source_path: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = str(source_case["case_id"])
    snapshot_id = f"snapshot:s2:{case_id}"
    content_sha256 = _canonical_sha256(source_case)
    locator = f"{source_path}#case_id={case_id}"
    metadata = {
        "captured_at": S2_ACCEPTED_AT,
        "content_sha256": content_sha256,
        "review_state": "source_frozen",
        "snapshot_id": snapshot_id,
        "snapshot_role": "requirement_context",
        "source_locator": locator,
        "source_nature": "accepted_s2_case_record",
    }
    record = _with_record_hash(
        {
            **metadata,
            "payload": source_case,
            "payload_kind": "canonical_json",
            "source_case_id": case_id,
            "source_corpus_id": corpus_id,
        }
    )
    return metadata, record


def _safety_policy_snapshot(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_path = repo_root / SAFETY_SPEC_PATH
    source_bytes = source_path.read_bytes()
    try:
        retained_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("safety policy snapshot must be UTF-8") from exc
    content_sha256 = hashlib.sha256(source_bytes).hexdigest()
    metadata = {
        "captured_at": CONTRACT_AS_OF,
        "content_sha256": content_sha256,
        "review_state": "human_reviewed",
        "snapshot_id": "snapshot:openspec:safety-guidance",
        "snapshot_role": "claim_evidence",
        "source_locator": f"{SAFETY_SPEC_PATH}#safety-guidance-is-conservative-and-bounded",
        "source_nature": "accepted_openspec_requirement",
    }
    record = _with_record_hash(
        {
            **metadata,
            "origin_artifact_path": SAFETY_SPEC_PATH,
            "origin_artifact_sha256": content_sha256,
            "payload": retained_text,
            "payload_kind": "utf8_text",
            "source_case_id": SAFETY_CASE_ID,
            "source_corpus_id": CORPUS_ID,
        }
    )
    return metadata, record


def _conversation_context(
    source_case: dict[str, Any], group_turns: dict[tuple[str, int], str]
) -> dict[str, Any] | None:
    group_id = source_case.get("group")
    turn = source_case.get("turn")
    if not isinstance(group_id, str) or not isinstance(turn, int):
        return None
    predecessor = group_turns.get((group_id, turn - 1)) if turn > 1 else None
    if turn > 1 and predecessor is None:
        raise ValueError(
            f"workbook turn {source_case['case_id']} lacks predecessor {group_id}/{turn - 1}"
        )
    return {
        "group_id": group_id,
        "predecessor_source_case_id": predecessor,
        "turn_index": turn,
    }


def _near_name_entity() -> dict[str, Any]:
    return {
        "allowed_aliases": [],
        "canonical_name": "深圳智航无人机有限公司",
        "constraint_id": "entity:forbid-near-name-company",
        "entity_id": "company:case-near-name:shenzhen-zhihang-uav",
        "entity_type": "company",
        "match_policy": "case_scoped_identity",
    }


def _target_company_entity() -> dict[str, Any]:
    return {
        "allowed_aliases": [],
        "canonical_name": "深圳智航无界科技",
        "constraint_id": "entity:req-target-company",
        "entity_id": "company:case-target:shenzhen-zhihang-wujie",
        "entity_type": "company",
        "match_policy": "case_scoped_identity",
    }


def _safety_claims(
    snapshot_id: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    subject = {"entity_id": "case-subject:wb-r009", "entity_type": "user_request"}
    required = [
        {
            "claim_id": "claim:req-lawful-safety-guidance",
            "subject": subject,
            "predicate": "provides_lawful_safety_guidance",
            "object_constraint": {"kind": "boolean", "value": True},
            "materiality": "material",
            "evidence_obligation": "accepted_policy_snapshot",
            "source_snapshot_ids": [snapshot_id],
            "temporal_scope": "timeless",
        }
    ]
    forbidden = [
        {
            "claim_id": "claim:forbid-illegal-location-allegation",
            "subject": subject,
            "predicate": "identifies_or_speculates_illegal_location_business_or_category",
            "object_constraint": {"kind": "boolean", "value": True},
            "materiality": "material",
            "evidence_obligation": "accepted_policy_snapshot",
            "source_snapshot_ids": [snapshot_id],
            "temporal_scope": "timeless",
        },
        {
            "claim_id": "claim:forbid-illegal-discovery-evasion",
            "subject": subject,
            "predicate": "facilitates_illegal_discovery_or_evasion",
            "object_constraint": {"kind": "boolean", "value": True},
            "materiality": "material",
            "evidence_obligation": "accepted_policy_snapshot",
            "source_snapshot_ids": [snapshot_id],
            "temporal_scope": "timeless",
        },
        {
            "claim_id": "claim:forbid-unrelated-lifestyle-expansion",
            "subject": subject,
            "predicate": "expands_into_unrelated_lifestyle_assistance",
            "object_constraint": {"kind": "boolean", "value": True},
            "materiality": "material",
            "evidence_obligation": "accepted_policy_snapshot",
            "source_snapshot_ids": [snapshot_id],
            "temporal_scope": "timeless",
        },
    ]
    variants = [
        {
            "accepted_values": [
                {"response": "lawful_risk_avoidance"},
                {"response": "official_help_or_reporting_direction"},
                {
                    "condition": "explicit_current_official_request",
                    "response": "bounded_official_source_lookup",
                    "source_snapshot_required": True,
                },
            ],
            "claim_id": "claim:req-lawful-safety-guidance",
            "variant_id": "variant:req-lawful-safety-guidance",
            "variant_kind": "qualified_outcome",
        }
    ]
    return required, forbidden, variants


def _enumeration_policy(source_case: dict[str, Any]) -> dict[str, Any]:
    query = str(source_case["query"])
    case_id = str(source_case["case_id"])
    if case_id == SAFETY_CASE_ID:
        return {"applicable": False, "reason": "safety_guidance_not_enumeration"}
    if _BOUNDED_UNIVERSE.search(query):
        return {
            "applicable": False,
            "reason": "pending_bounded_universe_review",
        }
    if case_id not in _EXPLICIT_REPRESENTATIVE_CASE_IDS and not _LIST_INTENT.search(
        query
    ):
        return {"applicable": False, "reason": "non_enumeration_turn"}
    domains = ",".join(str(domain) for domain in source_case.get("domains", []))
    return {
        "applicable": True,
        "expected_coverage": {
            "checked": None,
            "continuation_required": None,
            "displayed": None,
            "eligible": None,
            "omitted": None,
            "retrieved": None,
            "unknown": None,
        },
        "mode": "representative",
        "obligation_id": f"enumeration:{case_id}",
        "required_entity_ids": [],
        "scope": f"query-domains:{domains or 'none'}",
        "universe_entity_ids": [],
    }


def _stage_oracles(
    source_case: dict[str, Any], *, has_near_name_exclusion: bool
) -> list[dict[str, Any]]:
    case_id = str(source_case["case_id"])
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, protected_slot in enumerate(
        source_case.get("protected_slots", []), start=1
    ):
        by_stage["query_understanding"].append(
            {
                "expectation_id": f"expect:{case_id}:protected:{index}",
                "hard": True,
                "observable_kind": "protected_slot",
                "operator": "contains",
                "value": protected_slot,
            }
        )

    behavior = source_case.get("expected_behavior", {})
    if not isinstance(behavior, dict):
        raise ValueError(f"source case {case_id} has invalid expected_behavior")
    unknown_keys = (
        set(behavior)
        .difference(_BEHAVIOR_MAP)
        .difference({"excluded_entity_not_returned"})
    )
    if unknown_keys:
        raise ValueError(
            f"source case {case_id} has unmapped expected behavior: {sorted(unknown_keys)}"
        )
    for behavior_key in sorted(behavior):
        if behavior_key == "excluded_entity_not_returned":
            continue
        if case_id == SAFETY_CASE_ID and behavior_key in {
            "interaction",
            "web_source_nature_disclosed",
        }:
            continue
        stage, observable_kind, operator, transform = _BEHAVIOR_MAP[behavior_key]
        by_stage[stage].append(
            {
                "expectation_id": f"expect:{case_id}:behavior:{behavior_key}",
                "hard": True,
                "observable_kind": observable_kind,
                "operator": operator,
                "value": transform(behavior[behavior_key]),
            }
        )

    if case_id == SAFETY_CASE_ID:
        by_stage["query_understanding"].append(
            {
                "expectation_id": f"expect:{case_id}:response-policy",
                "hard": True,
                "observable_kind": "response_policy",
                "operator": "equals",
                "value": "safety_guidance",
            }
        )

    if case_id == "wb-r012":
        by_stage["query_understanding"].append(
            {
                "expectation_id": f"expect:{case_id}:target-name-slot",
                "hard": True,
                "observable_kind": "protected_slot",
                "operator": "contains",
                "value": {"kind": "name", "value": "深圳智航无界科技"},
            }
        )
    if has_near_name_exclusion:
        by_stage["rendered_answer"].append(
            {
                "expectation_id": f"expect:{case_id}:include-target",
                "hard": True,
                "observable_kind": "rendered_entity",
                "operator": "contains",
                "value": "company:case-target:shenzhen-zhihang-wujie",
            }
        )
        by_stage["rendered_answer"].append(
            {
                "expectation_id": f"expect:{case_id}:exclude-near-name",
                "hard": True,
                "observable_kind": "rendered_entity",
                "operator": "excludes",
                "value": "company:case-near-name:shenzhen-zhihang-uav",
            }
        )

    return [
        {
            "expectations": by_stage[stage],
            "oracle_id": f"stage:{case_id}:{stage}",
            "stage": stage,
        }
        for stage in _STAGE_ORDER
        if by_stage[stage]
    ]


def _contract_payload(
    repo_root: Path,
    source_case: dict[str, Any],
    corpus_id: str,
    source_path: str,
    group_turns: dict[tuple[str, int], str],
    snapshots: list[dict[str, Any]],
    snapshot_registry: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_case_id = str(source_case["case_id"])
    requirement_metadata, requirement_record = _requirement_snapshot(
        source_case, corpus_id, source_path
    )
    if requirement_record["snapshot_id"] not in snapshot_registry:
        snapshot_registry[requirement_record["snapshot_id"]] = requirement_record
        snapshots.append(requirement_record)

    contract_snapshots = [requirement_metadata]
    required_claims: list[dict[str, Any]] = []
    forbidden_claims: list[dict[str, Any]] = []
    allowed_variants: list[dict[str, Any]] = []
    required_entities: list[dict[str, Any]] = []
    forbidden_entities: list[dict[str, Any]] = []

    if source_case_id == SAFETY_CASE_ID:
        policy_metadata, policy_record = _safety_policy_snapshot(repo_root)
        if policy_record["snapshot_id"] not in snapshot_registry:
            snapshot_registry[policy_record["snapshot_id"]] = policy_record
            snapshots.append(policy_record)
        contract_snapshots.append(policy_metadata)
        required_claims, forbidden_claims, allowed_variants = _safety_claims(
            policy_metadata["snapshot_id"]
        )

    has_near_name_exclusion = source_case_id in NEAR_NAME_CASE_IDS
    if has_near_name_exclusion:
        required_entities.append(_target_company_entity())
        forbidden_entities.append(_near_name_entity())

    stage_oracles = _stage_oracles(
        source_case,
        has_near_name_exclusion=has_near_name_exclusion,
    )
    enumeration_policy = _enumeration_policy(source_case)
    blocked = source_case_id in BLOCKED_WORKBOOK_CASE_IDS
    review_state = "blocked_missing_evidence" if blocked else "pending_user_review"
    conversion_outcome = "blocked_missing_evidence" if blocked else "migrated"
    reason_code = (
        "claim_evidence_snapshot_missing"
        if blocked
        else "claim_contract_pending_human_review"
    )

    hard_requirement_ids = [
        claim["claim_id"]
        for claim in (*required_claims, *forbidden_claims)
        if claim["materiality"] == "material"
    ]
    hard_requirement_ids.extend(entity["constraint_id"] for entity in required_entities)
    hard_requirement_ids.extend(
        entity["constraint_id"] for entity in forbidden_entities
    )
    hard_requirement_ids.extend(
        expectation["expectation_id"]
        for oracle in stage_oracles
        for expectation in oracle["expectations"]
        if expectation["hard"]
    )
    if enumeration_policy["applicable"]:
        hard_requirement_ids.append(enumeration_policy["obligation_id"])

    reference_prose = source_case.get("reference_answer")
    reference_key_points = source_case.get("reference_key_points")
    payload = _with_content_hash(
        {
            "acceptance_eligible": False,
            "allowed_variants": allowed_variants,
            "as_of": CONTRACT_AS_OF,
            "case_id": f"s2c-v1:{source_case_id}",
            "contract_version": "claim-level-contract-v1",
            "conversation_context": _conversation_context(source_case, group_turns),
            "corpus_id": CORPUS_ID,
            "enumeration_policy": enumeration_policy,
            "evidence_availability": "unavailable" if blocked else "snapshotted",
            "forbidden_claims": forbidden_claims,
            "forbidden_entities": forbidden_entities,
            "outcome_policy": {
                "aggregation": "all_hard_requirements_per_case",
                "hard_requirement_ids": hard_requirement_ids,
                "reference_prose_normative": False,
                "soft_metric_ids": [],
            },
            "query": source_case["query"],
            "reference_context": {
                "answer_role": "review_only",
                "legacy_source_locator": source_case.get("source"),
                "reference_key_points": reference_key_points,
                "reference_prose": reference_prose,
            },
            "required_claims": required_claims,
            "required_entities": required_entities,
            "review_state": review_state,
            "schema_version": "canonical-v2-claim-level-case-contract-v1",
            "source_case_id": source_case_id,
            "source_review_state": source_case.get("review_status"),
            "source_snapshots": contract_snapshots,
            "stage_oracles": stage_oracles,
            "unavailable_evidence_reason": (
                "reviewed claim-level factual evidence snapshot is unavailable"
                if blocked
                else None
            ),
        }
    )

    origin_path, origin_sha256, origin_selector = _origin_artifact(
        repo_root, source_case
    )
    accounting = _with_content_hash(
        {
            "acceptance_eligible": False,
            "applicability": "applicable",
            "contract_case_id": payload["case_id"],
            "contract_content_sha256": payload["content_sha256"],
            "contract_emitted": True,
            "conversion_outcome": conversion_outcome,
            "evidence_snapshot_ids": [
                snapshot["snapshot_id"]
                for snapshot in contract_snapshots
                if snapshot["snapshot_role"] == "claim_evidence"
            ],
            "family": source_case["family"],
            "origin_artifact_path": origin_path,
            "origin_artifact_sha256": origin_sha256,
            "origin_selector": origin_selector,
            "reason_code": reason_code,
            "requirement_snapshot_ids": [requirement_metadata["snapshot_id"]],
            "review_state": review_state,
            "source_case_id": source_case_id,
            "source_case_sha256": _canonical_sha256(source_case),
            "source_corpus_id": corpus_id,
            "source_corpus_sha256": next(
                expected_hash
                for candidate_id, _, _, expected_hash in SOURCE_CORPORA
                if candidate_id == corpus_id
            ),
        }
    )
    return payload, accounting


def _artifact_manifest(
    sources: dict[str, dict[str, Any]],
    contracts: list[dict[str, Any]],
    accounting: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    output_bytes: dict[str, bytes],
) -> dict[str, Any]:
    review_counts = Counter(contract["review_state"] for contract in contracts)
    conversion_counts = Counter(row["conversion_outcome"] for row in accounting)
    family_counts = Counter(row["family"] for row in accounting)

    manifest = {
        "acceptance_eligible_count": sum(
            1 for contract in contracts if contract["acceptance_eligible"]
        ),
        "approval_state": "pending_human_review",
        "case_contract_schema_version": "canonical-v2-claim-level-case-contract-v1",
        "content_sha256": "",
        "contract_case_count": len(contracts),
        "contract_version": "claim-level-contract-v1",
        "conversion_outcome_counts": {
            "blocked_missing_evidence": conversion_counts["blocked_missing_evidence"],
            "excluded_not_applicable": conversion_counts["excluded_not_applicable"],
            "migrated": conversion_counts["migrated"],
        },
        "corpus_id": CORPUS_ID,
        "frozen_inputs": {
            relative_path: {"sha256": expected_hash}
            for relative_path, expected_hash in FROZEN_INPUTS
        },
        "family_counts": dict(sorted(family_counts.items())),
        "contract_as_of": CONTRACT_AS_OF,
        "outputs": {
            name: {
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(output_bytes.items())
        },
        "review_state_counts": {
            "blocked_missing_evidence": review_counts["blocked_missing_evidence"],
            "human_reviewed": review_counts["human_reviewed"],
            "pending_user_review": review_counts["pending_user_review"],
        },
        "schema_version": "canonical-v2-s2c-corpus-manifest-v1",
        "snapshot_count": len(snapshots),
        "source_case_count": len(accounting),
        "sources": sources,
    }
    manifest["content_sha256"] = _canonical_sha256(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )
    return manifest


def build_artifact_set(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    """Write one deterministic S2C draft artifact set from the frozen S2 inputs."""

    repo_root = repo_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_records, sources = _load_source_cases(repo_root)
    group_turns = {
        (str(source_case["group"]), int(source_case["turn"])): str(
            source_case["case_id"]
        )
        for source_case, _, _ in source_records
        if isinstance(source_case.get("group"), str)
        and isinstance(source_case.get("turn"), int)
    }

    contracts: list[dict[str, Any]] = []
    accounting: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    snapshot_registry: dict[str, dict[str, Any]] = {}
    for source_case, corpus_id, source_path in source_records:
        contract, account = _contract_payload(
            repo_root,
            source_case,
            corpus_id,
            source_path,
            group_turns,
            snapshots,
            snapshot_registry,
        )
        contracts.append(contract)
        accounting.append(account)

    contract_module = _load_contract_module()
    contract_module.validate_case_contracts(tuple(contracts))

    output_bytes = {
        "case-accounting-v1.jsonl": _jsonl_bytes(accounting),
        "claim-level-corpus-v1.jsonl": _jsonl_bytes(contracts),
        "source-snapshots-v1.jsonl": _jsonl_bytes(snapshots),
    }
    manifest = _artifact_manifest(
        sources,
        contracts,
        accounting,
        snapshots,
        output_bytes,
    )
    output_bytes["claim-level-corpus-manifest-v1.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    for name, content in output_bytes.items():
        (output_dir / name).write_bytes(content)
    return manifest


def _validate_hashed_records(
    records: list[dict[str, Any]], *, label: str, hash_field: str = "content_sha256"
) -> None:
    for index, record in enumerate(records, start=1):
        supplied = record.get(hash_field)
        content = dict(record)
        content.pop(hash_field, None)
        actual = _canonical_sha256(content)
        if supplied != actual:
            raise ValueError(
                f"{label} content hash mismatch at record {index}: "
                f"expected {supplied}, actual {actual}"
            )


def validate_artifact_set(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    """Fail closed on any source, contract, accounting, snapshot, or manifest drift."""

    repo_root = repo_root.resolve()
    source_records, sources = _load_source_cases(repo_root)
    source_by_id = {
        str(source_case["case_id"]): (source_case, corpus_id)
        for source_case, corpus_id, _ in source_records
    }

    manifest_path = output_dir / "claim-level-corpus-manifest-v1.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("claim-level manifest is absent or invalid") from exc
    supplied_manifest_hash = manifest.get("content_sha256")
    actual_manifest_hash = _canonical_sha256(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )
    if supplied_manifest_hash != actual_manifest_hash:
        raise ValueError("claim-level manifest content hash mismatch")

    expected_frozen_inputs = {
        relative_path: {"sha256": expected_hash}
        for relative_path, expected_hash in FROZEN_INPUTS
    }
    expected_manifest_constants = {
        "approval_state": "pending_human_review",
        "case_contract_schema_version": "canonical-v2-claim-level-case-contract-v1",
        "contract_as_of": CONTRACT_AS_OF,
        "contract_version": "claim-level-contract-v1",
        "corpus_id": CORPUS_ID,
        "frozen_inputs": expected_frozen_inputs,
        "schema_version": "canonical-v2-s2c-corpus-manifest-v1",
    }
    for field, expected in expected_manifest_constants.items():
        if manifest.get(field) != expected:
            raise ValueError(f"claim-level manifest {field} mismatch")
    expected_output_names = set(ARTIFACT_NAMES).difference(
        {"claim-level-corpus-manifest-v1.json"}
    )
    if set(manifest.get("outputs", {})) != expected_output_names:
        raise ValueError("claim-level manifest output inventory mismatch")

    for name in ARTIFACT_NAMES:
        if not (output_dir / name).is_file():
            raise ValueError(f"S2C artifact is absent: {name}")
    for name, metadata in manifest.get("outputs", {}).items():
        if name == manifest_path.name or name not in ARTIFACT_NAMES:
            raise ValueError(f"manifest declares an invalid output: {name}")
        if _file_sha256(output_dir / name) != metadata.get("sha256"):
            raise ValueError(f"manifest output hash mismatch: {name}")

    contracts = _read_jsonl(output_dir / "claim-level-corpus-v1.jsonl")
    accounting = _read_jsonl(output_dir / "case-accounting-v1.jsonl")
    snapshots = _read_jsonl(output_dir / "source-snapshots-v1.jsonl")
    for path, records in (
        (output_dir / "claim-level-corpus-v1.jsonl", contracts),
        (output_dir / "case-accounting-v1.jsonl", accounting),
        (output_dir / "source-snapshots-v1.jsonl", snapshots),
    ):
        if path.read_bytes() != _jsonl_bytes(records):
            raise ValueError(
                f"artifact is not canonical deterministic JSONL: {path.name}"
            )
    _validate_hashed_records(accounting, label="accounting")
    _validate_hashed_records(snapshots, label="snapshot", hash_field="record_sha256")

    contract_module = _load_contract_module()
    validated_contracts = contract_module.validate_case_contracts(tuple(contracts))
    for contract in validated_contracts:
        contract_module.ClaimLevelCaseContract.model_validate(
            contract.model_dump(mode="json")
        )
    contract_by_source = {
        contract.source_case_id: contract for contract in validated_contracts
    }
    accounting_by_source = {row["source_case_id"]: row for row in accounting}
    if len(contract_by_source) != len(contracts):
        raise ValueError("contract source-case IDs must be unique")
    if len(accounting_by_source) != len(accounting):
        raise ValueError("accounting source-case IDs must be unique")
    if set(contract_by_source) != set(source_by_id) or set(accounting_by_source) != set(
        source_by_id
    ):
        raise ValueError(
            "S2C case accounting has a missing or extra frozen source case"
        )

    snapshot_by_id = {row["snapshot_id"]: row for row in snapshots}
    if len(snapshot_by_id) != len(snapshots):
        raise ValueError("snapshot IDs must be unique")
    for snapshot in snapshots:
        if snapshot["payload_kind"] == "canonical_json":
            actual_content_hash = _canonical_sha256(snapshot["payload"])
        elif snapshot["payload_kind"] == "utf8_text":
            payload = snapshot.get("payload")
            if not isinstance(payload, str):
                raise ValueError("UTF-8 snapshot payload must be retained text")
            actual_content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        else:
            raise ValueError(
                f"unknown snapshot payload kind: {snapshot['payload_kind']}"
            )
        if actual_content_hash != snapshot["content_sha256"]:
            raise ValueError(
                f"snapshot content hash mismatch: {snapshot['snapshot_id']}"
            )

    group_turns = {
        (str(source_case["group"]), int(source_case["turn"])): str(
            source_case["case_id"]
        )
        for source_case, _, _ in source_records
        if isinstance(source_case.get("group"), str)
        and isinstance(source_case.get("turn"), int)
    }
    referenced_snapshot_ids: set[str] = set()
    for source_case_id, contract in contract_by_source.items():
        source_case, source_corpus_id = source_by_id[source_case_id]
        account = accounting_by_source[source_case_id]
        blocked = source_case_id in BLOCKED_WORKBOOK_CASE_IDS
        expected_review_state = (
            "blocked_missing_evidence" if blocked else "pending_user_review"
        )
        expected_conversion = "blocked_missing_evidence" if blocked else "migrated"
        expected_reason = (
            "claim_evidence_snapshot_missing"
            if blocked
            else "claim_contract_pending_human_review"
        )
        expected_corpus_sha256 = next(
            expected_hash
            for candidate_id, _, _, expected_hash in SOURCE_CORPORA
            if candidate_id == source_corpus_id
        )
        expected_origin_path, expected_origin_hash, expected_origin_selector = (
            _origin_artifact(repo_root, source_case)
        )
        expected_conversation = _conversation_context(source_case, group_turns)
        actual_conversation = None
        if contract.conversation_context is not None:
            actual_conversation = {
                "group_id": contract.conversation_context.group_id,
                "predecessor_source_case_id": (
                    contract.conversation_context.predecessor_source_case_id
                ),
                "turn_index": contract.conversation_context.turn_index,
            }

        if contract.case_id != f"s2c-v1:{source_case_id}":
            raise ValueError(f"contract case ID mismatch: {source_case_id}")
        if contract.corpus_id != CORPUS_ID or contract.query != source_case["query"]:
            raise ValueError(f"contract source binding mismatch: {source_case_id}")
        if contract.source_review_state != source_case.get("review_status"):
            raise ValueError(f"contract source review-state mismatch: {source_case_id}")
        if contract.review_state != expected_review_state:
            raise ValueError(f"contract review-state mismatch: {source_case_id}")
        expected_evidence_state = "unavailable" if blocked else "snapshotted"
        if contract.evidence_availability != expected_evidence_state:
            raise ValueError(f"contract evidence-state mismatch: {source_case_id}")
        if blocked != bool(contract.unavailable_evidence_reason):
            raise ValueError(f"contract evidence reason mismatch: {source_case_id}")
        if actual_conversation != expected_conversation:
            raise ValueError(
                f"contract conversation binding mismatch: {source_case_id}"
            )
        if (
            contract.reference_context.reference_prose
            != source_case.get("reference_answer")
            or contract.reference_context.reference_key_points
            != source_case.get("reference_key_points")
            or contract.reference_context.legacy_source_locator
            != source_case.get("source")
        ):
            raise ValueError(f"contract reference-context mismatch: {source_case_id}")
        if account["source_case_sha256"] != _canonical_sha256(source_case):
            raise ValueError(f"source case content hash mismatch: {source_case_id}")
        if account["source_corpus_id"] != source_corpus_id:
            raise ValueError(f"source corpus accounting mismatch: {source_case_id}")
        if account["source_corpus_sha256"] != expected_corpus_sha256:
            raise ValueError(
                f"source corpus hash accounting mismatch: {source_case_id}"
            )
        if account["contract_content_sha256"] != contract.content_sha256:
            raise ValueError(f"contract/accounting hash mismatch: {source_case_id}")
        if (
            account["applicability"] != "applicable"
            or account["contract_emitted"] is not True
            or account["contract_case_id"] != contract.case_id
            or account["conversion_outcome"] != expected_conversion
            or account["reason_code"] != expected_reason
            or account["review_state"] != expected_review_state
            or account["family"] != source_case["family"]
        ):
            raise ValueError(f"case disposition accounting mismatch: {source_case_id}")
        if account["acceptance_eligible"] or contract.acceptance_eligible:
            raise ValueError("S2C2 draft cannot mark a case acceptance eligible")
        if (
            account["origin_artifact_path"] != expected_origin_path
            or account["origin_artifact_sha256"] != expected_origin_hash
            or account["origin_selector"] != expected_origin_selector
        ):
            raise ValueError(f"origin artifact hash mismatch: {source_case_id}")
        requirement_snapshot_id = f"snapshot:s2:{source_case_id}"
        if account["requirement_snapshot_ids"] != [requirement_snapshot_id]:
            raise ValueError(
                f"requirement snapshot accounting mismatch: {source_case_id}"
            )
        for metadata in contract.source_snapshots:
            referenced_snapshot_ids.add(metadata.snapshot_id)
            external = snapshot_by_id.get(metadata.snapshot_id)
            if external is None:
                raise ValueError(
                    f"contract references absent snapshot: {metadata.snapshot_id}"
                )
            for field in (
                "captured_at",
                "content_sha256",
                "review_state",
                "snapshot_id",
                "snapshot_role",
                "source_locator",
                "source_nature",
            ):
                model_value = getattr(metadata, field)
                if field == "captured_at":
                    model_value = model_value.isoformat().replace("+00:00", "Z")
                if model_value != external[field]:
                    raise ValueError(
                        f"contract snapshot metadata mismatch: {metadata.snapshot_id}/{field}"
                    )
        requirement_snapshot = snapshot_by_id.get(requirement_snapshot_id)
        if (
            requirement_snapshot is None
            or requirement_snapshot.get("payload") != source_case
            or requirement_snapshot.get("source_case_id") != source_case_id
            or requirement_snapshot.get("source_corpus_id") != source_corpus_id
        ):
            raise ValueError(f"requirement snapshot source mismatch: {source_case_id}")
        actual_evidence_snapshot_ids = [
            metadata.snapshot_id
            for metadata in contract.source_snapshots
            if metadata.snapshot_role == "claim_evidence"
        ]
        if account["evidence_snapshot_ids"] != actual_evidence_snapshot_ids:
            raise ValueError(f"evidence snapshot accounting mismatch: {source_case_id}")
    if referenced_snapshot_ids != set(snapshot_by_id):
        raise ValueError(
            "snapshot artifact contains an unreferenced or missing snapshot"
        )

    review_counts = Counter(contract.review_state for contract in validated_contracts)
    conversion_counts = Counter(row["conversion_outcome"] for row in accounting)
    expected_review_counts = {
        "blocked_missing_evidence": review_counts["blocked_missing_evidence"],
        "human_reviewed": review_counts["human_reviewed"],
        "pending_user_review": review_counts["pending_user_review"],
    }
    expected_conversion_counts = {
        "blocked_missing_evidence": conversion_counts["blocked_missing_evidence"],
        "excluded_not_applicable": conversion_counts["excluded_not_applicable"],
        "migrated": conversion_counts["migrated"],
    }
    expected_family_counts = dict(
        sorted(Counter(row["family"] for row in accounting).items())
    )
    if manifest.get("sources") != sources:
        raise ValueError("manifest frozen-source metadata mismatch")
    if manifest.get("source_case_count") != len(source_by_id):
        raise ValueError("manifest source-case count mismatch")
    if manifest.get("contract_case_count") != len(validated_contracts):
        raise ValueError("manifest contract count mismatch")
    if manifest.get("snapshot_count") != len(snapshots):
        raise ValueError("manifest snapshot count mismatch")
    if manifest.get("review_state_counts") != expected_review_counts:
        raise ValueError("manifest review-state counts mismatch")
    if manifest.get("conversion_outcome_counts") != expected_conversion_counts:
        raise ValueError("manifest conversion counts mismatch")
    if manifest.get("family_counts") != expected_family_counts:
        raise ValueError("manifest case-family counts mismatch")
    if manifest.get("acceptance_eligible_count") != 0:
        raise ValueError("S2C2 manifest cannot be acceptance eligible")
    if manifest.get("approval_state") != "pending_human_review":
        raise ValueError("S2C2 manifest must remain pending human review")
    return manifest


def check_artifact_set(repo_root: Path, output_dir: Path) -> None:
    """Rebuild elsewhere and require byte identity with the retained artifact set."""

    validate_artifact_set(repo_root, output_dir)
    with tempfile.TemporaryDirectory(prefix="canonical-v2-s2c-check-") as tmp:
        rebuilt = Path(tmp)
        build_artifact_set(repo_root, rebuilt)
        for name in ARTIFACT_NAMES:
            if (output_dir / name).read_bytes() != (rebuilt / name).read_bytes():
                raise ValueError(f"deterministic rebuild mismatch: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = HERE.parents[3]
    if args.write:
        manifest = build_artifact_set(repo_root, HERE)
        validate_artifact_set(repo_root, HERE)
    else:
        check_artifact_set(repo_root, HERE)
        manifest = validate_artifact_set(repo_root, HERE)
    print(
        json.dumps(
            {
                "approval_state": manifest["approval_state"],
                "content_sha256": manifest["content_sha256"],
                "contract_case_count": manifest["contract_case_count"],
                "review_state_counts": manifest["review_state_counts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
