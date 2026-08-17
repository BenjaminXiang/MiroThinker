"""ID-grounded retrieval/citation/semantic gate for OpenSpec Slice A.

The scorer deliberately accepts a small normalized observation instead of a raw
response blob.  ``canonical_response_to_observation`` is the only raw-response
adapter and reads only canonical result, evidence, claim-support, and outcome
fields.  Request echoes, prompts, debug data, configuration, and free-form answer
text are therefore outside the scoring input by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


Priority = Literal["P0", "P1"]
PathName = Literal[
    "type1",
    "type2",
    "type3",
    "type4",
    "q004",
    "q017",
    "outcome",
    "classifier",
]
OutcomeName = Literal[
    "success",
    "partial_result",
    "no_result",
    "retrieval_error",
    "synthesis_error",
]
SourceLane = Literal["local", "web"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PredicateExpectation(FrozenModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class ScoringPolicy(FrozenModel):
    retrieval: Literal[
        "contains_expected",
        "exact_set",
        "type4_precision_at_5",
        "not_applicable",
    ]
    citation: Literal["expected_ids", "returned_ids", "not_applicable"]
    semantics: Literal["required_intents", "not_applicable"]


class ClassifierExpectation(FrozenModel):
    query_type: Literal["A", "B", "C", "D", "E", "F", "G"]
    target_domain: Literal["professor", "paper", "company", "patent", "none"]
    normalized_target: str
    endpoint: str = Field(min_length=1)


class PathExpectation(FrozenModel):
    company_id: str = Field(min_length=1)
    professor_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    edge_ids: tuple[str, ...] = Field(min_length=2, max_length=2)
    relation_tier: Literal["strong", "secondary"]


class ManifestCase(FrozenModel):
    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    path: PathName
    priority: Priority
    priority_reason: str = Field(min_length=1)
    expected_ids: tuple[str, ...] = ()
    expected_edge_ids: tuple[str, ...] = ()
    expected_relation_tiers: tuple[str, ...] = ()
    expected_paths: tuple[PathExpectation, ...] = ()
    expected_classifier: ClassifierExpectation | None = None
    predicate: PredicateExpectation
    required_intents: tuple[str, ...]
    forbidden_claims: tuple[str, ...] = ()
    expected_outcome: OutcomeName
    scoring_policy: ScoringPolicy
    strata: tuple[str, ...] = Field(min_length=1)
    source: str = Field(min_length=1)
    judgment_method: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    semantic_na_reason: str | None = None
    live_na_reason: str | None = None

    @field_validator("priority_reason")
    @classmethod
    def _priority_reason_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("priority_reason must explain the immutable assignment")
        return value

    @model_validator(mode="after")
    def _path_expectations_are_consistent(self) -> "ManifestCase":
        if not self.expected_paths:
            return self
        path_keys = {
            (path.paper_id, path.edge_ids, path.relation_tier)
            for path in self.expected_paths
        }
        if len(path_keys) != len(self.expected_paths):
            raise ValueError("expected_paths must be unique")
        path_edge_ids = {
            edge_id for path in self.expected_paths for edge_id in path.edge_ids
        }
        if path_edge_ids != set(self.expected_edge_ids):
            raise ValueError("expected_paths and expected_edge_ids must agree")
        path_tiers = {path.relation_tier for path in self.expected_paths}
        if path_tiers != set(self.expected_relation_tiers):
            raise ValueError("expected_paths and expected_relation_tiers must agree")
        return self


class CaseManifest(FrozenModel):
    schema_version: Literal["paper-retrieval-case-manifest-v1"] = (
        "paper-retrieval-case-manifest-v1"
    )
    manifest_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    retrieval_active_rule_version: Literal["retrieval-active-v1"]
    retrieval_active_rule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_at: str | None = None
    cases: tuple[ManifestCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> "CaseManifest":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique")
        return self

    def canonical_bytes(self) -> bytes:
        payload = self.model_dump(mode="json", exclude_none=True)
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def content_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class ClassifierObservation(FrozenModel):
    type: str
    target_domain: str
    normalized_target: str
    endpoint: str


class ResultItem(FrozenModel):
    object_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    source_lane: SourceLane = "local"
    rank: int = Field(ge=1)


class EvidenceObservation(FrozenModel):
    evidence_id: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    source_lane: SourceLane


class ClaimObservation(FrozenModel):
    claim_id: str = Field(min_length=1)
    support_evidence_ids: tuple[str, ...] = ()


class PathObservation(FrozenModel):
    company_id: str = Field(min_length=1)
    professor_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    edge_ids: tuple[str, ...]
    relation_tier: Literal["strong", "secondary"]


class SemanticObservation(FrozenModel):
    passed: bool = False
    satisfied_intents: tuple[str, ...] = ()
    detected_forbidden_claims: tuple[str, ...] = ()
    unsupported_material_claims: int = Field(default=0, ge=0)


class EvaluationObservation(FrozenModel):
    case_id: str = Field(min_length=1)
    canonical_contract: bool = True
    classifier: ClassifierObservation | None = None
    result_items: tuple[ResultItem, ...]
    evidence_items: tuple[EvidenceObservation, ...]
    claims: tuple[ClaimObservation, ...]
    paths: tuple[PathObservation, ...] = ()
    outcome: OutcomeName
    semantics: SemanticObservation = SemanticObservation()

    @model_validator(mode="after")
    def _canonical_ids_are_unique(self) -> "EvaluationObservation":
        evidence_ids = [item.evidence_id for item in self.evidence_items]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")
        return self


class ClassifierScore(FrozenModel):
    passed: bool
    field_passes: dict[str, bool]


class CaseScore(FrozenModel):
    case_id: str
    priority: Priority
    path: PathName
    contract_pass: bool = True
    classifier_pass: bool | None
    retrieval_pass: bool | None
    citation_pass: bool | None
    path_pass: bool | None = None
    support_references_pass: bool = True
    unsupported_claims_pass: bool = True
    semantic_pass: bool | None
    outcome_pass: bool
    missing_retrieval_ids: tuple[str, ...] = ()
    unexpected_retrieval_ids: tuple[str, ...] = ()
    duplicate_retrieval_ids: tuple[str, ...] = ()
    missing_citation_ids: tuple[str, ...] = ()
    unknown_evidence_ids: tuple[str, ...] = ()
    claims_without_support: tuple[str, ...] = ()
    missing_edge_ids: tuple[str, ...] = ()
    unexpected_edge_ids: tuple[str, ...] = ()
    missing_relation_tiers: tuple[str, ...] = ()
    unexpected_relation_tiers: tuple[str, ...] = ()
    missing_paths: tuple[str, ...] = ()
    unexpected_paths: tuple[str, ...] = ()
    duplicate_paths: tuple[str, ...] = ()
    missing_intents: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()

    def applicable_stage_values(self) -> tuple[bool, ...]:
        values = (
            self.contract_pass,
            self.classifier_pass,
            self.retrieval_pass,
            self.citation_pass,
            self.path_pass,
            self.support_references_pass,
            self.unsupported_claims_pass,
            self.semantic_pass,
            self.outcome_pass,
        )
        return tuple(value for value in values if value is not None)

    def passed(self) -> bool:
        values = self.applicable_stage_values()
        return bool(values) and all(values)


class GateReport(FrozenModel):
    hard_gate_pass: bool
    aggregate_pass_rate: float
    failed_p0_cases: tuple[str, ...]
    failed_cases: tuple[str, ...]
    failed_deterministic_cases: tuple[str, ...]
    failed_unsupported_claim_cases: tuple[str, ...]
    p0_semantic_pass: bool
    p1_semantic_pass_rate: float | None
    p1_semantic_pass: bool | None
    type4_precision_at_5: float | None
    type4_precision_pass: bool | None
    stage_passes: int
    stage_total: int


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def canonical_response_to_observation(
    *,
    case_id: str,
    response: Mapping[str, Any],
    semantic_pass: bool = False,
    satisfied_intents: Iterable[str] = (),
    detected_forbidden_claims: Iterable[str] = (),
    unsupported_material_claims: int = 0,
    classifier: Mapping[str, Any] | None = None,
) -> EvaluationObservation:
    """Normalize only score-eligible canonical fields from one response.

    In particular this function never recursively walks the response and never
    reads ``query``, ``answer_text``, ``prompt``, ``debug``, ``config``, or legacy
    untyped dictionaries.
    """

    canonical_contract = response.get("contract_version") == "canonical-v1"
    scoring_response = response if canonical_contract else {}

    result_items: list[ResultItem] = []
    for result_set in _as_sequence(scoring_response.get("result_sets")):
        result_set_map = _as_mapping(result_set)
        domain = str(result_set_map.get("domain") or "unknown")
        for rank, object_id in enumerate(
            _as_sequence(result_set_map.get("object_ids")), start=1
        ):
            if isinstance(object_id, str) and object_id:
                result_items.append(
                    ResultItem(
                        object_id=object_id,
                        object_type=domain,
                        source_lane="local",
                        rank=rank,
                    )
                )

    evidence_items: list[EvidenceObservation] = []
    for evidence in _as_sequence(scoring_response.get("evidence_items")):
        item = _as_mapping(evidence)
        evidence_id = item.get("evidence_id")
        object_id = item.get("object_id")
        object_type = item.get("object_type")
        source_lane = item.get("source_lane")
        if (
            isinstance(evidence_id, str)
            and evidence_id
            and isinstance(object_id, str)
            and object_id
            and isinstance(object_type, str)
            and object_type
            and source_lane in {"local", "web"}
        ):
            evidence_items.append(
                EvidenceObservation(
                    evidence_id=evidence_id,
                    object_id=object_id,
                    object_type=object_type,
                    source_lane=source_lane,
                )
            )

    claims: list[ClaimObservation] = []
    for section in _as_sequence(scoring_response.get("sections")):
        for answer_item in _as_sequence(_as_mapping(section).get("items")):
            for claim in _as_sequence(_as_mapping(answer_item).get("claims")):
                claim_map = _as_mapping(claim)
                claim_id = claim_map.get("claim_id")
                if not isinstance(claim_id, str) or not claim_id:
                    continue
                supports: list[str] = []
                for support in _as_sequence(claim_map.get("support_refs")):
                    support_map = _as_mapping(support)
                    if support_map.get("kind") != "evidence":
                        continue
                    evidence_id = support_map.get("evidence_id")
                    if isinstance(evidence_id, str) and evidence_id:
                        supports.append(evidence_id)
                claims.append(
                    ClaimObservation(
                        claim_id=claim_id,
                        support_evidence_ids=tuple(supports),
                    )
                )

    outcome_map = _as_mapping(scoring_response.get("outcome"))
    outcome = outcome_map.get("status")
    if outcome not in {
        "success",
        "partial_result",
        "no_result",
        "retrieval_error",
        "synthesis_error",
    }:
        # A legacy or malformed response did not expose the typed contract.  It
        # cannot be promoted to success by inference from a bare list/string.
        outcome = "synthesis_error"

    classifier_observation = None
    if classifier is not None:
        classifier_observation = ClassifierObservation.model_validate(classifier)

    return EvaluationObservation(
        case_id=case_id,
        canonical_contract=canonical_contract,
        classifier=classifier_observation,
        result_items=tuple(result_items),
        evidence_items=tuple(evidence_items),
        claims=tuple(claims),
        paths=(),
        outcome=outcome,
        semantics=SemanticObservation(
            passed=semantic_pass if canonical_contract else False,
            satisfied_intents=(
                tuple(sorted(set(satisfied_intents))) if canonical_contract else ()
            ),
            detected_forbidden_claims=tuple(sorted(set(detected_forbidden_claims))),
            unsupported_material_claims=unsupported_material_claims,
        ),
    )


def score_classifier(
    expected: ClassifierExpectation,
    actual: Mapping[str, Any] | ClassifierObservation,
) -> ClassifierScore:
    if isinstance(actual, ClassifierObservation):
        observed = actual
    else:
        observed = ClassifierObservation.model_validate(actual)
    field_passes = {
        "type": observed.type == expected.query_type,
        "target_domain": observed.target_domain == expected.target_domain,
        "normalized_target": (observed.normalized_target == expected.normalized_target),
        "endpoint": observed.endpoint == expected.endpoint,
    }
    return ClassifierScore(passed=all(field_passes.values()), field_passes=field_passes)


def _path_identity(path: PathExpectation | PathObservation) -> str:
    return json.dumps(
        {
            "company_id": path.company_id,
            "professor_id": path.professor_id,
            "paper_id": path.paper_id,
            "edge_ids": list(path.edge_ids),
            "relation_tier": path.relation_tier,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def score_case(case: ManifestCase, observation: EvaluationObservation) -> CaseScore:
    if case.case_id != observation.case_id:
        raise ValueError(
            f"case/observation ID mismatch: {case.case_id} != {observation.case_id}"
        )

    classifier_pass: bool | None = None
    failures: list[str] = []
    contract_pass = observation.canonical_contract
    if not contract_pass:
        failures.append("contract")
    if case.expected_classifier is not None:
        if observation.classifier is None:
            classifier_pass = False
        else:
            classifier_pass = score_classifier(
                case.expected_classifier, observation.classifier
            ).passed
        if not classifier_pass:
            failures.append("classifier")

    local_result_ids = tuple(
        item.object_id
        for item in observation.result_items
        if item.source_lane == "local"
    )
    local_result_set = set(local_result_ids)
    duplicate_retrieval_ids = tuple(
        sorted(
            object_id
            for object_id in local_result_set
            if local_result_ids.count(object_id) > 1
        )
    )
    expected_set = set(case.expected_ids)
    missing_retrieval_ids = tuple(sorted(expected_set - local_result_set))
    unexpected_retrieval_ids: tuple[str, ...] = ()

    retrieval_pass: bool | None
    if case.scoring_policy.retrieval == "not_applicable":
        retrieval_pass = None
    elif case.scoring_policy.retrieval == "contains_expected":
        retrieval_pass = not missing_retrieval_ids
    elif case.scoring_policy.retrieval == "exact_set":
        unexpected_retrieval_ids = tuple(sorted(local_result_set - expected_set))
        retrieval_pass = not (
            missing_retrieval_ids or unexpected_retrieval_ids or duplicate_retrieval_ids
        )
    else:
        # Type4 precision is aggregated across the frozen topic set.
        retrieval_pass = None
    if retrieval_pass is False:
        failures.append("retrieval")

    all_evidence_by_id = {item.evidence_id: item for item in observation.evidence_items}
    evidence_by_id = {
        item.evidence_id: item
        for item in observation.evidence_items
        if item.source_lane == "local"
    }
    cited_object_ids = {
        evidence_by_id[evidence_id].object_id
        for claim in observation.claims
        for evidence_id in claim.support_evidence_ids
        if evidence_id in evidence_by_id
    }
    referenced_evidence_ids = {
        evidence_id
        for claim in observation.claims
        for evidence_id in claim.support_evidence_ids
    }
    unknown_evidence_ids = tuple(
        sorted(referenced_evidence_ids - set(all_evidence_by_id))
    )
    claims_without_support = tuple(
        sorted(
            claim.claim_id
            for claim in observation.claims
            if not claim.support_evidence_ids
        )
    )
    support_references_pass = not unknown_evidence_ids and not claims_without_support
    if not support_references_pass:
        failures.append("unknown_evidence")
    if case.scoring_policy.citation == "not_applicable":
        citation_pass = None
        missing_citation_ids: tuple[str, ...] = ()
    else:
        citation_scope = (
            expected_set
            if case.scoring_policy.citation == "expected_ids"
            else local_result_set
        )
        missing_citation_ids = tuple(sorted(citation_scope - cited_object_ids))
        citation_pass = not missing_citation_ids
        if not citation_pass:
            failures.append("citation")

    path_pass: bool | None = None
    missing_edge_ids: tuple[str, ...] = ()
    unexpected_edge_ids: tuple[str, ...] = ()
    missing_relation_tiers: tuple[str, ...] = ()
    unexpected_relation_tiers: tuple[str, ...] = ()
    missing_paths: tuple[str, ...] = ()
    unexpected_paths: tuple[str, ...] = ()
    duplicate_paths: tuple[str, ...] = ()
    if case.path == "type3" or case.expected_edge_ids or case.expected_relation_tiers:
        actual_edge_ids = {
            edge_id for path in observation.paths for edge_id in path.edge_ids
        }
        actual_relation_tiers = {path.relation_tier for path in observation.paths}
        expected_edge_ids = set(case.expected_edge_ids)
        expected_relation_tiers = set(case.expected_relation_tiers)
        missing_edge_ids = tuple(sorted(expected_edge_ids - actual_edge_ids))
        unexpected_edge_ids = tuple(sorted(actual_edge_ids - expected_edge_ids))
        missing_relation_tiers = tuple(
            sorted(expected_relation_tiers - actual_relation_tiers)
        )
        unexpected_relation_tiers = tuple(
            sorted(actual_relation_tiers - expected_relation_tiers)
        )
        path_pass = not (
            missing_edge_ids
            or unexpected_edge_ids
            or missing_relation_tiers
            or unexpected_relation_tiers
        )
        if case.expected_paths:
            expected_path_keys = {_path_identity(path) for path in case.expected_paths}
            actual_path_identities = tuple(
                _path_identity(path) for path in observation.paths
            )
            actual_path_keys = set(actual_path_identities)
            missing_paths = tuple(sorted(expected_path_keys - actual_path_keys))
            unexpected_paths = tuple(sorted(actual_path_keys - expected_path_keys))
            duplicate_paths = tuple(
                sorted(
                    path_identity
                    for path_identity in actual_path_keys
                    if actual_path_identities.count(path_identity) > 1
                )
            )
            path_pass = (
                path_pass
                and not missing_paths
                and not unexpected_paths
                and not duplicate_paths
            )
        if not path_pass:
            failures.append("path")

    satisfied_intents = set(observation.semantics.satisfied_intents)
    missing_intents = tuple(sorted(set(case.required_intents) - satisfied_intents))
    if case.scoring_policy.semantics == "not_applicable":
        semantic_result: bool | None = None
    else:
        forbidden = set(case.forbidden_claims).intersection(
            observation.semantics.detected_forbidden_claims
        )
        semantic_result = (
            observation.semantics.passed
            and not missing_intents
            and not forbidden
            and observation.semantics.unsupported_material_claims == 0
        )
        if not semantic_result:
            failures.append("semantics")

    unsupported_claims_pass = observation.semantics.unsupported_material_claims == 0
    if not unsupported_claims_pass:
        failures.append("unsupported_claim")

    outcome_pass = observation.outcome == case.expected_outcome
    if not outcome_pass:
        failures.append("outcome")

    return CaseScore(
        case_id=case.case_id,
        priority=case.priority,
        path=case.path,
        contract_pass=contract_pass,
        classifier_pass=classifier_pass,
        retrieval_pass=retrieval_pass,
        citation_pass=citation_pass,
        path_pass=path_pass,
        support_references_pass=support_references_pass,
        unsupported_claims_pass=unsupported_claims_pass,
        semantic_pass=semantic_result,
        outcome_pass=outcome_pass,
        missing_retrieval_ids=missing_retrieval_ids,
        unexpected_retrieval_ids=unexpected_retrieval_ids,
        duplicate_retrieval_ids=duplicate_retrieval_ids,
        missing_citation_ids=missing_citation_ids,
        unknown_evidence_ids=unknown_evidence_ids,
        claims_without_support=claims_without_support,
        missing_edge_ids=missing_edge_ids,
        unexpected_edge_ids=unexpected_edge_ids,
        missing_relation_tiers=missing_relation_tiers,
        unexpected_relation_tiers=unexpected_relation_tiers,
        missing_paths=missing_paths,
        unexpected_paths=unexpected_paths,
        duplicate_paths=duplicate_paths,
        missing_intents=missing_intents,
        failures=tuple(failures),
    )


def aggregate_gate(
    scores: Iterable[CaseScore],
    *,
    type4_precision: Type4PrecisionScore | None = None,
) -> GateReport:
    score_list = tuple(scores)
    stage_values = [
        stage for score in score_list for stage in score.applicable_stage_values()
    ]
    stage_passes = sum(stage_values)
    stage_total = len(stage_values)
    deterministic_attributes = (
        "contract_pass",
        "classifier_pass",
        "retrieval_pass",
        "citation_pass",
        "path_pass",
        "support_references_pass",
        "outcome_pass",
    )
    failed_deterministic = tuple(
        score.case_id
        for score in score_list
        if any(
            getattr(score, attribute) is False for attribute in deterministic_attributes
        )
    )
    failed_unsupported = tuple(
        score.case_id for score in score_list if not score.unsupported_claims_pass
    )
    failed_p0_semantic = tuple(
        score.case_id
        for score in score_list
        if score.priority == "P0" and score.semantic_pass is False
    )
    p1_semantic_values = tuple(
        score.semantic_pass
        for score in score_list
        if score.priority == "P1" and score.semantic_pass is not None
    )
    p1_semantic_rate = (
        sum(p1_semantic_values) / len(p1_semantic_values)
        if p1_semantic_values
        else None
    )
    p1_semantic_pass = (
        p1_semantic_rate >= 0.90 if p1_semantic_rate is not None else None
    )

    has_type4_case = any(score.path == "type4" for score in score_list)
    type4_precision_value = (
        type4_precision.micro_precision_at_5 if type4_precision else None
    )
    type4_precision_pass: bool | None
    if has_type4_case:
        type4_precision_pass = (
            type4_precision_value is not None and type4_precision_value >= 0.85
        )
    elif type4_precision_value is not None:
        type4_precision_pass = type4_precision_value >= 0.85
    else:
        type4_precision_pass = None

    global_gate_pass = not (
        failed_deterministic
        or failed_unsupported
        or failed_p0_semantic
        or p1_semantic_pass is False
        or type4_precision_pass is False
    )
    failed = {score.case_id for score in score_list if not score.passed()}
    if type4_precision_pass is False:
        failed.update(score.case_id for score in score_list if score.path == "type4")
    failed_p0 = tuple(
        score.case_id
        for score in score_list
        if score.priority == "P0" and score.case_id in failed
    )
    return GateReport(
        hard_gate_pass=global_gate_pass,
        aggregate_pass_rate=(stage_passes / stage_total if stage_total else 0.0),
        failed_p0_cases=failed_p0,
        failed_cases=tuple(sorted(failed)),
        failed_deterministic_cases=failed_deterministic,
        failed_unsupported_claim_cases=failed_unsupported,
        p0_semantic_pass=not failed_p0_semantic,
        p1_semantic_pass_rate=p1_semantic_rate,
        p1_semantic_pass=p1_semantic_pass,
        type4_precision_at_5=type4_precision_value,
        type4_precision_pass=type4_precision_pass,
        stage_passes=stage_passes,
        stage_total=stage_total,
    )


def gate_exit_code(report: GateReport) -> int:
    return 0 if report.hard_gate_pass else 1


class RankedResult(FrozenModel):
    object_id: str = Field(min_length=1)
    source_lane: SourceLane


class Type4TopicScore(FrozenModel):
    relevant_slots: int
    denominator_slots: Literal[5] = 5
    precision_at_5: float
    duplicate_slots: tuple[int, ...] = ()
    web_slots: tuple[int, ...] = ()
    irrelevant_slots: tuple[int, ...] = ()
    missing_slots: tuple[int, ...] = ()


class Type4PrecisionScore(FrozenModel):
    relevant_slots: int = Field(ge=0)
    denominator_slots: int = Field(gt=0)
    micro_precision_at_5: float = Field(ge=0.0, le=1.0)
    per_topic: dict[str, Type4TopicScore]

    @model_validator(mode="after")
    def _metric_is_self_consistent(self) -> "Type4PrecisionScore":
        if self.relevant_slots > self.denominator_slots:
            raise ValueError("relevant_slots cannot exceed denominator_slots")
        expected = self.relevant_slots / self.denominator_slots
        if abs(self.micro_precision_at_5 - expected) > 1e-12:
            raise ValueError("micro_precision_at_5 must equal relevant/denominator")
        return self


class Type4ScoringInput(FrozenModel):
    topics: dict[str, tuple[RankedResult, ...]]
    relevant_local_ids: dict[str, frozenset[str]]


def score_type4_precision(
    topics: Mapping[str, Sequence[RankedResult]],
    relevant_local_ids: Mapping[str, set[str] | frozenset[str]],
) -> Type4PrecisionScore:
    if not topics:
        raise ValueError("at least one frozen Type4 topic is required")
    if set(topics) != set(relevant_local_ids):
        raise ValueError("topics and relevance-label keys must match exactly")

    per_topic: dict[str, Type4TopicScore] = {}
    total_relevant = 0
    for topic_id, results in topics.items():
        labels = set(relevant_local_ids[topic_id])
        if len(labels) < 5:
            raise ValueError(f"{topic_id} requires at least five relevant local labels")
        seen: set[str] = set()
        relevant_count = 0
        duplicate_slots: list[int] = []
        web_slots: list[int] = []
        irrelevant_slots: list[int] = []
        missing_slots: list[int] = []
        top_five = tuple(results[:5])
        for position in range(1, 6):
            if position > len(top_five):
                missing_slots.append(position)
                continue
            result = top_five[position - 1]
            if result.object_id in seen:
                duplicate_slots.append(position)
                continue
            seen.add(result.object_id)
            if result.source_lane != "local":
                web_slots.append(position)
                continue
            if result.object_id not in labels:
                irrelevant_slots.append(position)
                continue
            relevant_count += 1
        total_relevant += relevant_count
        per_topic[topic_id] = Type4TopicScore(
            relevant_slots=relevant_count,
            precision_at_5=relevant_count / 5,
            duplicate_slots=tuple(duplicate_slots),
            web_slots=tuple(web_slots),
            irrelevant_slots=tuple(irrelevant_slots),
            missing_slots=tuple(missing_slots),
        )

    denominator = 5 * len(topics)
    return Type4PrecisionScore(
        relevant_slots=total_relevant,
        denominator_slots=denominator,
        micro_precision_at_5=total_relevant / denominator,
        per_topic=per_topic,
    )


def cohen_kappa(labels_a: Sequence[bool], labels_b: Sequence[bool]) -> float:
    if not labels_a or len(labels_a) != len(labels_b):
        raise ValueError("reviewer label sequences must be non-empty and equal length")
    count = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b, strict=True)) / count
    a_true = sum(labels_a) / count
    b_true = sum(labels_b) / count
    expected = a_true * b_true + (1 - a_true) * (1 - b_true)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


class HoldoutAccessEvent(FrozenModel):
    actor: str = Field(min_length=1)
    action: Literal["decrypt", "score", "disclose", "rotate"]
    at: datetime

    @field_validator("at")
    @classmethod
    def _timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("access timestamp must include an offset")
        return value


class HoldoutReceipt(FrozenModel):
    schema_version: Literal["sealed-holdout-receipt-v1"] = "sealed-holdout-receipt-v1"
    holdout_version: str = Field(min_length=1)
    descriptor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_ids: tuple[str, str]
    reviewer_labels: tuple[tuple[bool, ...], tuple[bool, ...]]
    access_log: tuple[HoldoutAccessEvent, ...] = Field(min_length=1)
    used_holdout_disclosed: bool
    rotated_to_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    signature: str

    @model_validator(mode="after")
    def _reviewers_are_independent(self) -> "HoldoutReceipt":
        if self.reviewer_ids[0] == self.reviewer_ids[1]:
            raise ValueError("two distinct reviewer IDs are required")
        return self

    def signing_bytes(self) -> bytes:
        payload = self.model_dump(mode="json", exclude={"signature"})
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class HoldoutReceiptVerdict(FrozenModel):
    valid: bool
    failures: tuple[str, ...]
    kappa: float | None


def sign_holdout_receipt(receipt: HoldoutReceipt, key: bytes) -> str:
    if not key:
        raise ValueError("receipt signing key must not be empty")
    digest = hmac.new(key, receipt.signing_bytes(), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def validate_holdout_receipt(
    receipt: HoldoutReceipt, key: bytes
) -> HoldoutReceiptVerdict:
    failures: list[str] = []
    expected_signature = sign_holdout_receipt(receipt, key)
    if not hmac.compare_digest(receipt.signature, expected_signature):
        failures.append("signature")

    actions = {event.action for event in receipt.access_log}
    required_actions = ("decrypt", "score", "disclose", "rotate")
    action_positions = {
        action: next(
            (
                index
                for index, event in enumerate(receipt.access_log)
                if event.action == action
            ),
            None,
        )
        for action in required_actions
    }
    ordered_positions = tuple(action_positions[action] for action in required_actions)
    if (
        actions.issuperset(required_actions) is False
        or any(position is None for position in ordered_positions)
        or tuple(position for position in ordered_positions if position is not None)
        != tuple(
            sorted(position for position in ordered_positions if position is not None)
        )
    ):
        failures.append("access_log")
    event_times = tuple(event.at for event in receipt.access_log)
    if event_times != tuple(sorted(event_times)) and "access_log" not in failures:
        failures.append("access_log")
    if not receipt.used_holdout_disclosed:
        failures.append("disclosure")
    if (
        not receipt.rotated_to_sha256
        or receipt.rotated_to_sha256 == receipt.descriptor_sha256
    ):
        failures.append("rotation")

    kappa: float | None = None
    try:
        kappa = cohen_kappa(*receipt.reviewer_labels)
    except ValueError:
        failures.append("reviewer_labels")
    else:
        if kappa < 0.60:
            failures.append("kappa")

    return HoldoutReceiptVerdict(
        valid=not failures,
        failures=tuple(failures),
        kappa=kappa,
    )


def evaluate_manifest(
    manifest: CaseManifest,
    observations: Sequence[EvaluationObservation],
    *,
    type4_precision: Type4PrecisionScore | None = None,
) -> GateReport:
    expected_ids = tuple(case.case_id for case in manifest.cases)
    observation_ids = tuple(observation.case_id for observation in observations)
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("observation case IDs must be unique")
    if set(expected_ids) != set(observation_ids):
        missing = sorted(set(expected_ids) - set(observation_ids))
        unexpected = sorted(set(observation_ids) - set(expected_ids))
        raise ValueError(
            "observation IDs must match manifest case IDs "
            f"(missing={missing}, unexpected={unexpected})"
        )
    by_case_id = {observation.case_id: observation for observation in observations}
    scores = tuple(
        score_case(case, by_case_id[case.case_id]) for case in manifest.cases
    )
    return aggregate_gate(scores, type4_precision=type4_precision)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the ID-grounded Slice A paper retrieval gate."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--type4-input", type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = CaseManifest.model_validate(_read_json(args.manifest))
        raw_observations = _read_json(args.observations)
        if not isinstance(raw_observations, list):
            raise ValueError("observations must be a JSON list")
        observations = tuple(
            EvaluationObservation.model_validate(item) for item in raw_observations
        )
        type4_precision = None
        if args.type4_input:
            type4_input = Type4ScoringInput.model_validate(_read_json(args.type4_input))
            type4_precision = score_type4_precision(
                type4_input.topics, type4_input.relevant_local_ids
            )
        report = evaluate_manifest(
            manifest,
            observations,
            type4_precision=type4_precision,
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"gate input error: {exc}", file=sys.stderr)
        return 2

    print(report.model_dump_json(indent=2))
    return gate_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
