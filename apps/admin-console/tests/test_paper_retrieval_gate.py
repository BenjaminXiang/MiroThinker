"""Slice A tests for the ID-grounded paper retrieval gate.

These tests exercise evaluator code only.  They intentionally do not import or
change the production chat/retrieval path.
"""

from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from paper_retrieval_gate import (  # noqa: E402
    CaseManifest,
    CaseScore,
    ClassifierExpectation,
    EvaluationObservation,
    HoldoutAccessEvent,
    HoldoutReceipt,
    ManifestCase,
    RankedResult,
    ScoringPolicy,
    Type4PrecisionScore,
    aggregate_gate,
    canonical_response_to_observation,
    cohen_kappa,
    gate_exit_code,
    score_case,
    score_classifier,
    score_type4_precision,
    sign_holdout_receipt,
    validate_holdout_receipt,
)


RULE_HASH = "a" * 64


def _case(**overrides: object) -> ManifestCase:
    data: dict[str, object] = {
        "case_id": "type1-echo-red",
        "query": "请介绍论文 Target Paper",
        "path": "type1",
        "priority": "P0",
        "priority_reason": "named true-RED query-echo counterexample",
        "expected_ids": ["PAPER-target"],
        "predicate": {"id": "exact-title", "version": "v1", "args": {}},
        "required_intents": ["paper_identity"],
        "forbidden_claims": ["wrong-paper"],
        "expected_outcome": "success",
        "scoring_policy": {
            "retrieval": "contains_expected",
            "citation": "expected_ids",
            "semantics": "required_intents",
        },
        "strata": ["english", "named_true_red"],
        "source": "synthetic boundary fixture",
        "judgment_method": "canonical ID",
        "reviewer": "slice-a-implementer",
    }
    data.update(overrides)
    return ManifestCase.model_validate(data)


def _canonical_response(*, include_target: bool = True) -> dict:
    object_ids = ["PAPER-target"] if include_target else ["PAPER-other"]
    evidence_object = "PAPER-target" if include_target else "PAPER-other"
    return {
        "contract_version": "canonical-v1",
        "query": "Target Paper",  # explicitly excluded from scoring
        "prompt": "PAPER-target",  # explicitly excluded from scoring
        "debug": {"gold": "PAPER-target"},  # explicitly excluded
        "config": {"expected_ids": ["PAPER-target"]},  # explicitly excluded
        "result_sets": [
            {
                "result_set_id": "set-1",
                "domain": "paper",
                "object_ids": object_ids,
            }
        ],
        "evidence_items": [
            {
                "evidence_id": "ev1_target",
                "object_type": "paper",
                "object_id": evidence_object,
                "source_lane": "local",
            }
        ],
        "sections": [
            {
                "items": [
                    {
                        "claims": [
                            {
                                "claim_id": "claim-1",
                                "support_refs": [
                                    {"kind": "evidence", "evidence_id": "ev1_target"}
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
        "outcome": {"status": "success"},
    }


def test_manifest_rejects_mutable_or_unexplained_priority() -> None:
    with pytest.raises(ValidationError):
        _case(priority="P2")
    with pytest.raises(ValidationError):
        _case(priority_reason="")


def test_manifest_hash_changes_when_a_case_contract_changes() -> None:
    manifest = CaseManifest(
        manifest_id="paper-gate-dev-v1",
        snapshot_id="snapshot-fixture-v1",
        retrieval_active_rule_version="retrieval-active-v1",
        retrieval_active_rule_sha256=RULE_HASH,
        cases=(_case(),),
    )
    changed = manifest.model_copy(
        update={"cases": (_case(query="changed only before output"),)}
    )
    assert manifest.content_sha256() != changed.content_sha256()


def test_request_echo_prompt_debug_and_config_cannot_satisfy_retrieval() -> None:
    response = _canonical_response(include_target=False)
    # All excluded fields contain the target; the only result-set ID does not.
    observation = canonical_response_to_observation(
        case_id="type1-echo-red",
        response=response,
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    )
    result = score_case(_case(), observation)
    assert result.retrieval_pass is False
    assert "PAPER-target" in result.missing_retrieval_ids


def test_noncanonical_response_cannot_supply_scoring_fields() -> None:
    response = _canonical_response()
    response.pop("contract_version")
    observation = canonical_response_to_observation(
        case_id="type1-echo-red",
        response=response,
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    )
    result = score_case(_case(), observation)
    assert result.retrieval_pass is False
    assert result.citation_pass is False
    assert result.outcome_pass is False


def test_unknown_top_level_payload_cannot_be_injected_into_scoring_record() -> None:
    with pytest.raises(ValidationError):
        EvaluationObservation.model_validate(
            {
                "case_id": "type1-echo-red",
                "result_items": [],
                "evidence_items": [],
                "claims": [],
                "outcome": "no_result",
                "query": "PAPER-target",
            }
        )


def test_retrieved_target_without_claim_evidence_reference_fails_citation() -> None:
    response = _canonical_response()
    response["sections"][0]["items"][0]["claims"][0]["support_refs"] = []
    observation = canonical_response_to_observation(
        case_id="type1-echo-red",
        response=response,
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    )
    result = score_case(_case(), observation)
    assert result.retrieval_pass is True
    assert result.citation_pass is False


def test_claim_without_any_typed_support_is_a_hard_failure() -> None:
    case = _case(
        expected_ids=[],
        required_intents=[],
        scoring_policy={
            "retrieval": "not_applicable",
            "citation": "not_applicable",
            "semantics": "not_applicable",
        },
    )
    response = _canonical_response()
    response["sections"][0]["items"][0]["claims"][0]["support_refs"] = []
    observation = canonical_response_to_observation(
        case_id=case.case_id,
        response=response,
    )
    score = score_case(case, observation)
    assert score.claims_without_support == ("claim-1",)
    assert score.support_references_pass is False
    assert aggregate_gate((score,)).hard_gate_pass is False


def test_duplicate_evidence_identity_is_rejected() -> None:
    response = _canonical_response()
    response["evidence_items"].append(
        {
            "evidence_id": "ev1_target",
            "object_type": "paper",
            "object_id": "PAPER-other",
            "source_lane": "local",
        }
    )
    with pytest.raises(ValidationError, match="evidence_id values must be unique"):
        canonical_response_to_observation(
            case_id="type1-echo-red",
            response=response,
        )


def test_cited_target_with_incomplete_intent_fails_semantics() -> None:
    observation = canonical_response_to_observation(
        case_id="type1-echo-red",
        response=_canonical_response(),
        semantic_pass=True,
        satisfied_intents=set(),
    )
    result = score_case(_case(), observation)
    assert result.retrieval_pass is True
    assert result.citation_pass is True
    assert result.semantic_pass is False
    assert result.missing_intents == ("paper_identity",)


def test_type4_precision_uses_exactly_five_local_unique_slots() -> None:
    topics = {
        "topic-a": [
            RankedResult(object_id="A", source_lane="local"),
            RankedResult(object_id="A", source_lane="local"),  # duplicate -> zero
            RankedResult(object_id="B", source_lane="web"),  # Web -> zero
            RankedResult(object_id="C", source_lane="local"),
            # missing fifth slot -> zero
        ],
        "topic-b": [
            RankedResult(object_id=x, source_lane="local")
            for x in ("D", "E", "F", "G", "H", "IGNORED-BEYOND-FIVE")
        ],
    }
    labels = {
        "topic-a": {"A", "B", "C", "X", "Y"},
        "topic-b": {"D", "E", "F", "G", "H"},
    }
    score = score_type4_precision(topics, labels)
    assert score.relevant_slots == 7
    assert score.denominator_slots == 10
    assert score.micro_precision_at_5 == pytest.approx(0.7)
    assert "recall" not in score.model_dump()
    assert score.per_topic["topic-a"].duplicate_slots == (2,)
    assert score.per_topic["topic-a"].web_slots == (3,)
    assert score.per_topic["topic-a"].missing_slots == (5,)


def test_type4_requires_at_least_five_relevant_local_labels_per_topic() -> None:
    with pytest.raises(ValueError, match="at least five"):
        score_type4_precision(
            {"topic-a": [RankedResult(object_id="A", source_lane="local")]},
            {"topic-a": {"A"}},
        )


def test_type4_score_model_rejects_inconsistent_metric() -> None:
    with pytest.raises(ValidationError, match="micro_precision_at_5"):
        Type4PrecisionScore(
            relevant_slots=85,
            denominator_slots=100,
            micro_precision_at_5=0.84,
            per_topic={},
        )


def test_classifier_requires_type_domain_target_and_endpoint() -> None:
    expected = ClassifierExpectation(
        query_type="A",
        target_domain="professor",
        normalized_target="张巍",
        endpoint="professor-profile",
    )
    correct = score_classifier(
        expected,
        {
            "type": "A",
            "target_domain": "professor",
            "normalized_target": "张巍",
            "endpoint": "professor-profile",
        },
    )
    wrong_entity = score_classifier(
        expected,
        {
            "type": "A",
            "target_domain": "professor",
            "normalized_target": "大学张巍",
            "endpoint": "professor-profile",
        },
    )
    assert correct.passed is True
    assert wrong_entity.passed is False
    assert wrong_entity.field_passes == {
        "type": True,
        "target_domain": True,
        "normalized_target": False,
        "endpoint": True,
    }


def test_any_p0_hard_gate_failure_exits_nonzero() -> None:
    passing_observation = canonical_response_to_observation(
        case_id="type1-echo-red",
        response=_canonical_response(),
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    )
    passing = score_case(_case(), passing_observation)
    failing = passing.model_copy(
        update={"case_id": "one-failure", "citation_pass": False}
    )
    report = aggregate_gate((passing, failing))
    assert report.aggregate_pass_rate > 0.5
    assert report.hard_gate_pass is False
    assert gate_exit_code(report) != 0


def _semantic_score(
    case_id: str,
    *,
    priority: str = "P1",
    semantic_pass: bool = True,
    unsupported_material_claims: int = 0,
) -> CaseScore:
    case = _case(
        case_id=case_id,
        priority=priority,
        priority_reason="pre-output additive case" if priority == "P1" else "P0 floor",
    )
    observation = canonical_response_to_observation(
        case_id=case_id,
        response=_canonical_response(),
        semantic_pass=semantic_pass,
        satisfied_intents={"paper_identity"} if semantic_pass else set(),
        unsupported_material_claims=unsupported_material_claims,
    )
    return score_case(case, observation)


def test_p1_semantic_gate_accepts_exactly_ninety_percent() -> None:
    scores = tuple(
        _semantic_score(f"p1-{index}", semantic_pass=index < 9) for index in range(10)
    )
    report = aggregate_gate(scores)
    assert report.p1_semantic_pass_rate == pytest.approx(0.90)
    assert report.hard_gate_pass is True
    assert gate_exit_code(report) == 0


def test_p1_semantic_gate_rejects_below_ninety_percent() -> None:
    scores = tuple(
        _semantic_score(f"p1-{index}", semantic_pass=index < 8) for index in range(10)
    )
    report = aggregate_gate(scores)
    assert report.p1_semantic_pass_rate == pytest.approx(0.80)
    assert report.hard_gate_pass is False
    assert gate_exit_code(report) != 0


def test_unsupported_claim_is_zero_tolerance_even_with_ninety_percent_p1() -> None:
    scores = tuple(
        _semantic_score(
            f"p1-{index}",
            semantic_pass=index != 9,
            unsupported_material_claims=1 if index == 9 else 0,
        )
        for index in range(10)
    )
    report = aggregate_gate(scores)
    assert report.p1_semantic_pass_rate == pytest.approx(0.90)
    assert report.hard_gate_pass is False
    assert "p1-9" in report.failed_unsupported_claim_cases


@pytest.mark.parametrize(
    ("relevant", "expected_pass"),
    [(84, False), (85, True)],
)
def test_type4_threshold_is_part_of_the_hard_gate(
    relevant: int, expected_pass: bool
) -> None:
    case_score = _semantic_score("type4-gate", priority="P0").model_copy(
        update={"path": "type4", "retrieval_pass": None}
    )
    precision = Type4PrecisionScore(
        relevant_slots=relevant,
        denominator_slots=100,
        micro_precision_at_5=relevant / 100,
        per_topic={},
    )
    report = aggregate_gate((case_score,), type4_precision=precision)
    assert report.type4_precision_pass is expected_pass
    assert report.hard_gate_pass is expected_pass
    assert gate_exit_code(report) == (0 if expected_pass else 1)


def test_type4_case_without_precision_artifact_fails_closed() -> None:
    case_score = _semantic_score("type4-missing", priority="P0").model_copy(
        update={"path": "type4", "retrieval_pass": None}
    )
    report = aggregate_gate((case_score,))
    assert report.type4_precision_pass is False
    assert report.hard_gate_pass is False


def test_unknown_evidence_support_is_a_hard_failure_even_when_citation_is_na() -> None:
    case = _case(
        expected_ids=[],
        required_intents=[],
        scoring_policy={
            "retrieval": "not_applicable",
            "citation": "not_applicable",
            "semantics": "not_applicable",
        },
    )
    response = _canonical_response()
    response["sections"][0]["items"][0]["claims"][0]["support_refs"] = [
        {"kind": "evidence", "evidence_id": "ev1_unknown"}
    ]
    observation = canonical_response_to_observation(
        case_id=case.case_id,
        response=response,
    )
    score = score_case(case, observation)
    report = aggregate_gate((score,))
    assert score.unknown_evidence_ids == ("ev1_unknown",)
    assert report.hard_gate_pass is False


def test_exact_set_rejects_duplicate_result_ids() -> None:
    case = _case(
        scoring_policy={
            "retrieval": "exact_set",
            "citation": "expected_ids",
            "semantics": "required_intents",
        }
    )
    response = _canonical_response()
    response["result_sets"][0]["object_ids"] = ["PAPER-target", "PAPER-target"]
    observation = canonical_response_to_observation(
        case_id=case.case_id,
        response=response,
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    )
    score = score_case(case, observation)
    assert score.retrieval_pass is False
    assert score.duplicate_retrieval_ids == ("PAPER-target",)


def test_type3_requires_exact_edge_ids_and_relation_tiers() -> None:
    case = _case(
        path="type3",
        expected_edge_ids=["EDGE-company-prof", "EDGE-prof-paper"],
        expected_relation_tiers=["strong"],
        expected_paths=[
            {
                "company_id": "COMPANY-1",
                "professor_id": "PROF-1",
                "paper_id": "PAPER-target",
                "edge_ids": ["EDGE-company-prof", "EDGE-prof-paper"],
                "relation_tier": "strong",
            }
        ],
        scoring_policy={
            "retrieval": "exact_set",
            "citation": "expected_ids",
            "semantics": "required_intents",
        },
    )
    base = canonical_response_to_observation(
        case_id=case.case_id,
        response=_canonical_response(),
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    ).model_dump(mode="json")
    base["paths"] = [
        {
            "company_id": "COMPANY-1",
            "professor_id": "PROF-1",
            "paper_id": "PAPER-target",
            "edge_ids": ["EDGE-prof-paper"],
            "relation_tier": "secondary",
        }
    ]
    observation = EvaluationObservation.model_validate(base)
    score = score_case(case, observation)
    report = aggregate_gate((score,))
    assert score.path_pass is False
    assert score.missing_edge_ids == ("EDGE-company-prof",)
    assert score.unexpected_relation_tiers == ("secondary",)
    assert report.hard_gate_pass is False


def test_type3_compares_complete_path_tuples_not_only_unions() -> None:
    case = _case(
        path="type3",
        expected_ids=[],
        expected_edge_ids=["EDGE-ca", "EDGE-pa", "EDGE-cb", "EDGE-pb"],
        expected_relation_tiers=["strong", "secondary"],
        expected_paths=[
            {
                "company_id": "COMPANY-1",
                "professor_id": "PROF-1",
                "paper_id": "PAPER-1",
                "edge_ids": ["EDGE-ca", "EDGE-pa"],
                "relation_tier": "strong",
            },
            {
                "company_id": "COMPANY-1",
                "professor_id": "PROF-2",
                "paper_id": "PAPER-2",
                "edge_ids": ["EDGE-cb", "EDGE-pb"],
                "relation_tier": "secondary",
            },
        ],
        required_intents=[],
        scoring_policy={
            "retrieval": "not_applicable",
            "citation": "not_applicable",
            "semantics": "not_applicable",
        },
    )
    base = canonical_response_to_observation(
        case_id=case.case_id,
        response=_canonical_response(),
    ).model_dump(mode="json")
    # Same paper/edge/tier unions, deliberately attached to the wrong papers.
    base["paths"] = [
        {
            "company_id": "COMPANY-1",
            "professor_id": "PROF-2",
            "paper_id": "PAPER-1",
            "edge_ids": ["EDGE-cb", "EDGE-pb"],
            "relation_tier": "secondary",
        },
        {
            "company_id": "COMPANY-1",
            "professor_id": "PROF-1",
            "paper_id": "PAPER-2",
            "edge_ids": ["EDGE-ca", "EDGE-pa"],
            "relation_tier": "strong",
        },
    ]
    score = score_case(case, EvaluationObservation.model_validate(base))
    assert score.path_pass is False
    assert len(score.missing_paths) == 2
    assert len(score.unexpected_paths) == 2


def test_type3_duplicate_identical_path_is_a_hard_failure() -> None:
    expected_path = {
        "company_id": "COMPANY-1",
        "professor_id": "PROF-1",
        "paper_id": "PAPER-target",
        "edge_ids": ["EDGE-company-prof", "EDGE-prof-paper"],
        "relation_tier": "strong",
    }
    case = _case(
        path="type3",
        expected_ids=[],
        expected_edge_ids=expected_path["edge_ids"],
        expected_relation_tiers=["strong"],
        expected_paths=[expected_path],
        required_intents=[],
        scoring_policy={
            "retrieval": "not_applicable",
            "citation": "not_applicable",
            "semantics": "not_applicable",
        },
    )
    base = canonical_response_to_observation(
        case_id=case.case_id,
        response=_canonical_response(),
    ).model_dump(mode="json")
    base["paths"] = [expected_path, expected_path]
    score = score_case(case, EvaluationObservation.model_validate(base))
    assert score.path_pass is False
    assert len(score.duplicate_paths) == 1
    assert aggregate_gate((score,)).hard_gate_pass is False


def test_holdout_receipt_requires_access_log_rotation_signature_and_kappa() -> None:
    key = b"ci-only-test-key"
    labels_a = (True, True, False, False, True)
    labels_b = (True, False, False, False, True)
    assert cohen_kappa(labels_a, labels_b) >= 0.60

    unsigned = HoldoutReceipt(
        holdout_version="sealed-type4-v1",
        descriptor_sha256="b" * 64,
        run_id="run-001",
        output_sha256="c" * 64,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_labels=(labels_a, labels_b),
        access_log=(
            HoldoutAccessEvent(
                actor="ci-custodian", action="decrypt", at="2026-07-10T00:00:00Z"
            ),
            HoldoutAccessEvent(
                actor="ci-custodian", action="score", at="2026-07-10T00:01:00Z"
            ),
            HoldoutAccessEvent(
                actor="ci-custodian", action="disclose", at="2026-07-10T00:02:00Z"
            ),
            HoldoutAccessEvent(
                actor="ci-custodian", action="rotate", at="2026-07-10T00:03:00Z"
            ),
        ),
        used_holdout_disclosed=True,
        rotated_to_sha256="d" * 64,
        signature="",
    )
    signed = unsigned.model_copy(
        update={"signature": sign_holdout_receipt(unsigned, key)}
    )
    assert validate_holdout_receipt(signed, key).valid is True

    not_rotated = signed.model_copy(update={"rotated_to_sha256": None})
    assert validate_holdout_receipt(not_rotated, key).valid is False


def test_holdout_receipt_blocks_low_reviewer_agreement() -> None:
    key = b"ci-only-test-key"
    receipt = HoldoutReceipt(
        holdout_version="sealed-type4-v1",
        descriptor_sha256="b" * 64,
        run_id="run-002",
        output_sha256="c" * 64,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_labels=((True, True, False, False), (False, False, True, True)),
        access_log=(
            HoldoutAccessEvent(
                actor="ci-custodian", action="decrypt", at="2026-07-10T00:00:00Z"
            ),
        ),
        used_holdout_disclosed=True,
        rotated_to_sha256="d" * 64,
        signature="",
    )
    signed = receipt.model_copy(
        update={"signature": sign_holdout_receipt(receipt, key)}
    )
    verdict = validate_holdout_receipt(signed, key)
    assert verdict.valid is False
    assert "kappa" in verdict.failures


def test_holdout_receipt_requires_complete_ordered_access_lifecycle() -> None:
    key = b"ci-only-test-key"
    receipt = HoldoutReceipt(
        holdout_version="sealed-type4-v1",
        descriptor_sha256="b" * 64,
        run_id="run-003",
        output_sha256="c" * 64,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_labels=((True, False), (True, False)),
        access_log=(
            HoldoutAccessEvent(
                actor="ci-custodian", action="decrypt", at="2026-07-10T00:00:00Z"
            ),
            HoldoutAccessEvent(
                actor="ci-custodian", action="score", at="2026-07-10T00:01:00Z"
            ),
        ),
        used_holdout_disclosed=True,
        rotated_to_sha256="d" * 64,
        signature="",
    )
    signed = receipt.model_copy(
        update={"signature": sign_holdout_receipt(receipt, key)}
    )
    verdict = validate_holdout_receipt(signed, key)
    assert verdict.valid is False
    assert "access_log" in verdict.failures


def test_holdout_rotation_must_use_a_fresh_descriptor_hash() -> None:
    key = b"ci-only-test-key"
    receipt = HoldoutReceipt(
        holdout_version="sealed-type4-v1",
        descriptor_sha256="b" * 64,
        run_id="run-004",
        output_sha256="c" * 64,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_labels=((True, False), (True, False)),
        access_log=tuple(
            HoldoutAccessEvent(
                actor="ci-custodian",
                action=action,
                at=f"2026-07-10T00:0{index}:00Z",
            )
            for index, action in enumerate(("decrypt", "score", "disclose", "rotate"))
        ),
        used_holdout_disclosed=True,
        rotated_to_sha256="b" * 64,
        signature="",
    )
    signed = receipt.model_copy(
        update={"signature": sign_holdout_receipt(receipt, key)}
    )
    verdict = validate_holdout_receipt(signed, key)
    assert verdict.valid is False
    assert "rotation" in verdict.failures


def test_holdout_access_timestamps_must_be_monotonic() -> None:
    key = b"ci-only-test-key"
    times = (
        "2026-07-10T00:00:00Z",
        "2026-07-10T00:03:00Z",
        "2026-07-10T00:02:00Z",
        "2026-07-10T00:04:00Z",
    )
    receipt = HoldoutReceipt(
        holdout_version="sealed-type4-v1",
        descriptor_sha256="b" * 64,
        run_id="run-005",
        output_sha256="c" * 64,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_labels=((True, False), (True, False)),
        access_log=tuple(
            HoldoutAccessEvent(actor="ci-custodian", action=action, at=at)
            for action, at in zip(
                ("decrypt", "score", "disclose", "rotate"), times, strict=True
            )
        ),
        used_holdout_disclosed=True,
        rotated_to_sha256="d" * 64,
        signature="",
    )
    signed = receipt.model_copy(
        update={"signature": sign_holdout_receipt(receipt, key)}
    )
    verdict = validate_holdout_receipt(signed, key)
    assert verdict.valid is False
    assert "access_log" in verdict.failures


def test_scoring_policy_rejects_recall_metric() -> None:
    with pytest.raises(ValidationError):
        ScoringPolicy.model_validate(
            {
                "retrieval": "recall",
                "citation": "expected_ids",
                "semantics": "required_intents",
            }
        )


def _write_gate_inputs(tmp_path: Path, *, include_target: bool) -> tuple[Path, Path]:
    case = _case()
    manifest = CaseManifest(
        manifest_id="cli-gate-v1",
        snapshot_id="snapshot-fixture-v1",
        retrieval_active_rule_version="retrieval-active-v1",
        retrieval_active_rule_sha256=RULE_HASH,
        cases=(case,),
    )
    observation = canonical_response_to_observation(
        case_id=case.case_id,
        response=_canonical_response(include_target=include_target),
        semantic_pass=True,
        satisfied_intents={"paper_identity"},
    )
    manifest_path = tmp_path / "manifest.json"
    observations_path = tmp_path / "observations.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    observations_path.write_text(
        json.dumps([observation.model_dump(mode="json")], ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path, observations_path


@pytest.mark.parametrize(
    ("include_target", "expected_exit"),
    [(False, 1), (True, 0)],
)
def test_gate_cli_exit_code_tracks_hard_gate(
    tmp_path: Path, include_target: bool, expected_exit: int
) -> None:
    manifest_path, observations_path = _write_gate_inputs(
        tmp_path, include_target=include_target
    )
    script = Path(__file__).resolve().parents[1] / "scripts/paper_retrieval_gate.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--manifest",
            str(manifest_path),
            "--observations",
            str(observations_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == expected_exit, completed.stderr
    report = json.loads(completed.stdout)
    assert report["hard_gate_pass"] is (expected_exit == 0)


def test_gate_cli_rejects_missing_observation(tmp_path: Path) -> None:
    manifest_path, observations_path = _write_gate_inputs(tmp_path, include_target=True)
    observations_path.write_text("[]", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts/paper_retrieval_gate.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--manifest",
            str(manifest_path),
            "--observations",
            str(observations_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "observation IDs must match manifest case IDs" in completed.stderr


@pytest.mark.parametrize(("relevant_count", "expected_exit"), [(4, 1), (5, 0)])
def test_gate_cli_applies_type4_precision_input(
    tmp_path: Path, relevant_count: int, expected_exit: int
) -> None:
    case = _case(
        path="type4",
        expected_ids=[],
        required_intents=[],
        scoring_policy={
            "retrieval": "type4_precision_at_5",
            "citation": "not_applicable",
            "semantics": "not_applicable",
        },
    )
    manifest = CaseManifest(
        manifest_id="cli-type4-v1",
        snapshot_id="snapshot-fixture-v1",
        retrieval_active_rule_version="retrieval-active-v1",
        retrieval_active_rule_sha256=RULE_HASH,
        cases=(case,),
    )
    observation = canonical_response_to_observation(
        case_id=case.case_id,
        response=_canonical_response(),
    )
    manifest_path = tmp_path / "manifest.json"
    observations_path = tmp_path / "observations.json"
    type4_path = tmp_path / "type4.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    observations_path.write_text(
        json.dumps([observation.model_dump(mode="json")]), encoding="utf-8"
    )
    relevant_ids = [f"PAPER-{index}" for index in range(5)]
    results = [
        {"object_id": paper_id, "source_lane": "local"}
        for paper_id in relevant_ids[:relevant_count]
    ]
    if relevant_count < 5:
        results.append({"object_id": "PAPER-irrelevant", "source_lane": "local"})
    type4_path.write_text(
        json.dumps(
            {
                "topics": {"topic-1": results},
                "relevant_local_ids": {"topic-1": relevant_ids},
            }
        ),
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts/paper_retrieval_gate.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--manifest",
            str(manifest_path),
            "--observations",
            str(observations_path),
            "--type4-input",
            str(type4_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == expected_exit, completed.stderr
    report = json.loads(completed.stdout)
    assert report["type4_precision_pass"] is (expected_exit == 0)
