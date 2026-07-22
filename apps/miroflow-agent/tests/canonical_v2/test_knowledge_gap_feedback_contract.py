from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from pydantic import ValidationError
import pytest

from src.data_agents.canonical_v2.contracts import GapClass
from src.data_agents.canonical_v2.contracts import GapSeverity
from src.data_agents.canonical_v2.contracts import GapStatus
from src.data_agents.canonical_v2.contracts import KnowledgeGap
from src.data_agents.canonical_v2.contracts import ReviewState


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_gap_feedback"
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
TRIGGERS = (
    "no_result",
    "insufficient_evidence",
    "repeated_web_dependence",
    "recurring_product_capability",
    "missing_relationship",
    "user_feedback",
    "benchmark_failure",
    "index_parity",
)
SCENARIO_FAMILY_TOKEN_BY_TRIGGER = {
    "no_result": "no_result",
    "insufficient_evidence": "insufficient_evidence",
    "repeated_web_dependence": "web_dependence",
    "recurring_product_capability": "product_capability",
    "missing_relationship": "relationship",
    "user_feedback": "user_feedback",
    "benchmark_failure": "benchmark",
    "index_parity": "index_parity",
}


class _MissingKnowledgeGapFeedbackModule(RuntimeError):
    """Exact Task 10.1 RED sentinel; nested import failures must fail normally."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingKnowledgeGapFeedbackModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _signal_payload(trigger: str) -> dict[str, Any]:
    trace_fields: dict[str, str]
    if trigger == "repeated_web_dependence":
        trace_fields = {"telemetry_key": f"telemetry:{trigger}"}
    elif trigger == "recurring_product_capability":
        trace_fields = {
            "answer_trace_id": "answer:product:delivery-robot-x1:turn-7",
            "telemetry_key": f"telemetry:{trigger}",
        }
    elif trigger == "benchmark_failure":
        trace_fields = {"benchmark_case_id": "benchmark:company-recall:case-7"}
    elif trigger == "index_parity":
        trace_fields = {"telemetry_key": "release-parity:candidate-r1:index-company"}
    elif trigger in {"insufficient_evidence", "user_feedback"}:
        trace_fields = {"answer_trace_id": f"answer:{trigger}:turn-1"}
    else:
        trace_fields = {"query_trace_id": f"query:{trigger}:turn-1"}

    path_by_trigger = {
        "no_result": "semantic_recall",
        "insufficient_evidence": "answer_synthesis",
        "repeated_web_dependence": "information_retrieval",
        "recurring_product_capability": "answer_product_capability",
        "missing_relationship": "relationship_traversal",
        "user_feedback": "answer_rendering",
        "benchmark_failure": "semantic_recall",
        "index_parity": "semantic_recall",
    }
    domains_by_trigger = {trigger: ("company",) for trigger in TRIGGERS} | {
        "missing_relationship": ("professor", "company")
    }
    evidence_by_trigger = {
        "no_result": (),
        "insufficient_evidence": ("evidence:company:partial-profile",),
        "repeated_web_dependence": ("web-snapshot:company:latest",),
        "recurring_product_capability": (
            "evidence:product:delivery-robot-x1:identity",
            "evidence:company:general-integration-capability",
        ),
        "missing_relationship": (
            "evidence:professor:identity",
            "evidence:company:identity",
        ),
        "user_feedback": ("answer-observation:turn-1",),
        "benchmark_failure": ("benchmark-observation:company-recall:case-7",),
        "index_parity": ("index-discrepancy:index-company:point-7",),
    }
    symptom_by_trigger = {
        trigger: f"synthetic Task 10.1 fixture: {trigger}" for trigger in TRIGGERS
    } | {
        "recurring_product_capability": (
            "Named Product delivery-robot-x1 repeatedly requested capability "
            "autonomous_elevator_button_operation; retained evidence supports only "
            "Company general integration and lacks direct Product-capability binding."
        )
    }
    demand_observations_by_trigger = {trigger: () for trigger in TRIGGERS} | {
        "repeated_web_dependence": (
            "demand:web-dependence:query-1",
            "demand:web-dependence:query-2",
            "demand:web-dependence:query-3",
        ),
        "recurring_product_capability": (
            "demand:delivery-robot-x1:turn-1",
            "demand:delivery-robot-x1:turn-3",
            "demand:delivery-robot-x1:turn-5",
            "demand:delivery-robot-x1:turn-7",
        ),
    }
    return {
        "signal_id": f"signal:{trigger}",
        "trigger": trigger,
        "release_id": "candidate-r1",
        "affected_domains": domains_by_trigger[trigger],
        "affected_paths": (path_by_trigger[trigger],),
        "observed_symptom": symptom_by_trigger[trigger],
        "evidence_ids": evidence_by_trigger[trigger],
        "demand_observation_ids": demand_observations_by_trigger[trigger],
        "observed_at": NOW,
        **trace_fields,
    }


def _signal(module: Any, trigger: str) -> Any:
    return module.GapSignal(**_signal_payload(trigger))


def test_all_named_gap_triggers_return_traceable_typed_open_gaps() -> None:
    module = _module()
    feedback = module.create_ephemeral_knowledge_gap_feedback()

    pairs = tuple(
        (_signal(module, trigger), feedback.record(_signal(module, trigger)))
        for trigger in TRIGGERS
    )

    assert len({gap.gap_id for _, gap in pairs}) == len(TRIGGERS)
    for signal, gap in pairs:
        assert isinstance(gap, KnowledgeGap)
        assert gap.release_id == signal.release_id
        assert gap.affected_domains == signal.affected_domains
        assert gap.affected_paths == signal.affected_paths
        assert gap.observed_symptom == signal.observed_symptom
        assert gap.evidence_ids == signal.evidence_ids
        if signal.demand_observation_ids:
            assert gap.demand_count == len(signal.demand_observation_ids)
            assert gap.demand_count > 1
        else:
            assert gap.demand_count >= 1
        assert gap.scenario_families
        expected_family_token = SCENARIO_FAMILY_TOKEN_BY_TRIGGER[signal.trigger.value]
        assert any(expected_family_token in family for family in gap.scenario_families)
        assert isinstance(gap.severity, GapSeverity)
        assert (
            gap.query_trace_id,
            gap.answer_trace_id,
            gap.benchmark_case_id,
            gap.telemetry_key,
        ) == (
            signal.query_trace_id,
            signal.answer_trace_id,
            signal.benchmark_case_id,
            signal.telemetry_key,
        )
        assert any(
            (
                gap.query_trace_id,
                gap.answer_trace_id,
                gap.benchmark_case_id,
                gap.telemetry_key,
            )
        )
        assert gap.status is GapStatus.open
        assert gap.review_state is ReviewState.unreviewed
        assert gap.created_at == gap.updated_at
        assert gap.created_at.tzinfo is not None
        assert gap.resolved_release_id is None
        assert gap.resolved_release_state is None
        assert gap.resolution_verification_ids == ()
        assert gap.proposed_owner
        assert gap.proposed_remediation


def test_explicit_ownership_signals_do_not_collapse_into_one_gap_class() -> None:
    module = _module()
    feedback = module.create_ephemeral_knowledge_gap_feedback()
    expected_classes = {
        "repeated_web_dependence": GapClass.knowledge_coverage,
        "recurring_product_capability": GapClass.knowledge_coverage,
        "missing_relationship": GapClass.relationship,
        "index_parity": GapClass.index_parity,
    }

    actual = {
        trigger: feedback.record(_signal(module, trigger)).gap_class
        for trigger in TRIGGERS
    }

    for trigger, expected in expected_classes.items():
        assert actual[trigger] is expected
    assert actual["missing_relationship"] is not GapClass.knowledge_coverage
    assert actual["index_parity"] is not GapClass.knowledge_coverage


def test_product_capability_signal_cannot_submit_or_return_canonical_state() -> None:
    module = _module()
    feedback = module.create_ephemeral_knowledge_gap_feedback()
    payload = _signal_payload("recurring_product_capability")

    caller_owned_outcome_fields = {
        "gap_id": "caller-selected-gap-id",
        "gap_class": "knowledge_coverage",
        "status": "resolved",
        "classification_confidence": 1.0,
        "review_state": "accepted",
        "proposed_owner": "caller-selected-owner",
        "proposed_remediation": "caller-selected-remediation",
        "demand_count": 999,
        "scenario_families": ("caller-selected-family",),
        "severity": "critical",
        "created_at": NOW,
        "updated_at": NOW,
        "resolved_release_id": "release-r2",
        "resolved_release_state": "active",
        "resolution_verification_ids": ("caller-verification",),
        "canonical_relationship": "product_has_capability",
    }
    for field, value in caller_owned_outcome_fields.items():
        with pytest.raises(ValidationError):
            module.GapSignal(**payload, **{field: value})

    gap = feedback.record(module.GapSignal(**payload))
    output_fields = set(gap.model_dump(mode="python"))

    assert isinstance(gap, KnowledgeGap)
    assert gap.gap_class is GapClass.knowledge_coverage
    assert gap.status is GapStatus.open
    assert gap.review_state is ReviewState.unreviewed
    assert gap.demand_count >= 1
    assert gap.affected_paths == ("answer_product_capability",)
    assert gap.answer_trace_id == "answer:product:delivery-robot-x1:turn-7"
    assert "delivery-robot-x1" in gap.observed_symptom
    assert "autonomous_elevator_button_operation" in gap.observed_symptom
    assert "lacks direct Product-capability binding" in gap.observed_symptom
    assert gap.proposed_remediation == "collect_direct_product_capability_evidence"
    assert gap.resolved_release_id is None
    assert gap.resolution_verification_ids == ()
    assert {
        "canonical_relationship",
        "product_has_capability",
        "canonical_mutation",
    }.isdisjoint(output_fields)
