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
NOW = datetime(2026, 7, 14, 19, 30, tzinfo=timezone.utc)


class _MissingKnowledgeGapFeedbackModule(RuntimeError):
    """Exact Task 10.2 RED sentinel; nested import failures must fail normally."""


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


def _signal(module: Any, trigger: str) -> Any:
    trace_fields: dict[str, str]
    demand_observation_ids: tuple[str, ...] = ()
    if trigger == "repeated_web_dependence":
        trace_fields = {"telemetry_key": "telemetry:repeated-web"}
        demand_observation_ids = ("demand:web:1", "demand:web:2")
    elif trigger == "recurring_product_capability":
        trace_fields = {
            "answer_trace_id": "answer:product-capability:turn-2",
            "telemetry_key": "telemetry:product-capability",
        }
        demand_observation_ids = ("demand:product:1", "demand:product:2")
    elif trigger == "missing_relationship":
        trace_fields = {"query_trace_id": "query:missing-relationship:turn-1"}
    elif trigger == "benchmark_failure":
        trace_fields = {"benchmark_case_id": "benchmark:answer:case-9"}
    elif trigger == "index_parity":
        trace_fields = {"telemetry_key": "parity:candidate-r1:index-company"}
    else:
        trace_fields = {"answer_trace_id": "answer:user-feedback:turn-9"}
    return module.GapSignal(
        signal_id=f"signal:{trigger}",
        trigger=trigger,
        release_id="candidate-r1",
        affected_domains=("company",),
        affected_paths=(
            "semantic_recall" if trigger != "user_feedback" else "answer_rendering",
        ),
        observed_symptom=f"synthetic Task 10.2 fixture: {trigger}",
        evidence_ids=(f"observation:{trigger}",),
        demand_observation_ids=demand_observation_ids,
        observed_at=NOW,
        **trace_fields,
    )


def test_recorded_classifier_is_content_bound_and_only_proposes_initial_outcomes() -> (
    None
):
    module = _module()
    requests: list[Any] = []

    def recorded_classifier(request: Any) -> Any:
        requests.append(request)
        return module.GapClassificationProposal(
            classification_input_sha256=request.content_sha256,
            gap_class="synthesis",
            confidence=0.72,
            proposed_owner="answer_quality",
            proposed_remediation="review_grounded_answer_generation",
            severity="high",
            rationale="The feedback concerns a supported answer-generation defect.",
        )

    feedback = module.create_ephemeral_knowledge_gap_feedback(
        classifier=recorded_classifier,
        clock=lambda: NOW,
    )
    signal = _signal(module, "user_feedback")

    gap = feedback.record(signal)

    assert isinstance(gap, KnowledgeGap)
    assert len(requests) == 1
    request = requests[0]
    assert request.signal_id == signal.signal_id
    assert request.release_id == signal.release_id
    assert request.trigger is module.GapTrigger.user_feedback
    assert request.evidence_ids == signal.evidence_ids
    assert request.demand_observation_ids == signal.demand_observation_ids
    assert request.demand_count == 1
    assert request.scenario_families
    assert request.observed_at == signal.observed_at
    assert request.content_sha256
    assert gap.gap_class is GapClass.synthesis
    assert gap.classification_confidence == 0.72
    assert gap.proposed_owner == "answer_quality"
    assert gap.proposed_remediation == "review_grounded_answer_generation"
    assert gap.status is GapStatus.open
    assert gap.review_state is ReviewState.unreviewed
    assert gap.created_at == NOW
    assert gap.updated_at == NOW
    assert gap.resolved_release_id is None
    assert gap.resolution_verification_ids == ()

    same_gap = feedback.record(signal)
    changed_signal = module.GapSignal.model_validate(
        {
            **signal.model_dump(mode="python"),
            "observed_symptom": "synthetic Task 10.2 fixture: changed user_feedback",
        }
    )
    changed_gap = feedback.record(changed_signal)

    assert same_gap.gap_id == gap.gap_id
    assert changed_gap.gap_id != gap.gap_id
    assert requests[0].content_sha256 == requests[1].content_sha256
    assert requests[2].content_sha256 != requests[0].content_sha256
    with pytest.raises(ValidationError, match="content_sha256"):
        module.GapClassificationRequest.model_validate(
            {
                **requests[0].model_dump(mode="python"),
                "observed_symptom": "cross-wired observation",
            }
        )


def test_invalid_or_failed_classifier_degrades_and_cannot_override_invariants() -> None:
    module = _module()

    def wrong_binding(request: Any) -> Any:
        return module.GapClassificationProposal(
            classification_input_sha256="f" * 64,
            gap_class="context",
            confidence=0.99,
            proposed_owner="unsafe-owner",
            proposed_remediation="unsafe-remediation",
            severity=GapSeverity.critical,
            rationale="Wrongly bound response.",
        )

    def invalid_schema(request: Any) -> dict[str, Any]:
        return {
            "classification_input_sha256": request.content_sha256,
            "gap_class": "context",
            "confidence": 0.99,
            "proposed_owner": "unsafe-owner",
            "proposed_remediation": "unsafe-remediation",
            "severity": "critical",
            "rationale": "Schema-invalid response.",
            "unexpected": True,
        }

    def timeout(_: Any) -> Any:
        raise TimeoutError("recorded classifier timeout")

    def bypassed_validation(request: Any) -> Any:
        return module.GapClassificationProposal.model_construct(
            classification_input_sha256=request.content_sha256,
            gap_class=GapClass.context,
            confidence=0.99,
            proposed_owner="unsafe-owner",
            proposed_remediation="unsafe-remediation",
            severity=GapSeverity.critical,
            rationale="",
        )

    for classifier in (wrong_binding, invalid_schema, timeout, bypassed_validation):
        feedback = module.create_ephemeral_knowledge_gap_feedback(
            classifier=classifier,
            clock=lambda: NOW,
        )
        gap = feedback.record(_signal(module, "benchmark_failure"))

        assert isinstance(gap, KnowledgeGap)
        assert gap.gap_class is GapClass.retrieval_precision
        assert gap.classification_confidence <= 0.5
        assert gap.review_state is ReviewState.unreviewed
        assert gap.proposed_owner == "acceptance_quality"
        assert gap.proposed_remediation == "review_benchmark_failure"
        assert gap.status is GapStatus.open

    def programmer_defect(_: Any) -> Any:
        raise AssertionError("classifier implementation defect")

    defective = module.create_ephemeral_knowledge_gap_feedback(
        classifier=programmer_defect,
        clock=lambda: NOW,
    )
    with pytest.raises(AssertionError, match="classifier implementation defect"):
        defective.record(_signal(module, "benchmark_failure"))

    def hostile_but_valid(request: Any) -> Any:
        return module.GapClassificationProposal(
            classification_input_sha256=request.content_sha256,
            gap_class="knowledge_coverage",
            confidence=1.0,
            proposed_owner="canonical_writer",
            proposed_remediation="create_product_has_capability_relationship",
            severity="low",
            rationale="Attempts to override the deterministic index owner.",
        )

    expected_protected = {
        "repeated_web_dependence": (
            GapClass.knowledge_coverage,
            "offline_evidence_enrichment",
            "collect_repeatedly_missing_local_evidence",
        ),
        "recurring_product_capability": (
            GapClass.knowledge_coverage,
            "offline_evidence_enrichment",
            "collect_direct_product_capability_evidence",
        ),
        "missing_relationship": (
            GapClass.relationship,
            "relationship_enrichment",
            "collect_missing_relationship_evidence",
        ),
        "index_parity": (
            GapClass.index_parity,
            "release_index",
            "repair_index_parity",
        ),
    }
    for trigger, (gap_class, owner, remediation) in expected_protected.items():
        protected = module.create_ephemeral_knowledge_gap_feedback(
            classifier=hostile_but_valid,
            clock=lambda: NOW,
        ).record(_signal(module, trigger))

        assert protected.gap_class is gap_class
        assert protected.proposed_owner == owner
        assert protected.proposed_remediation == remediation
        assert protected.status is GapStatus.open
        assert protected.review_state is ReviewState.unreviewed
