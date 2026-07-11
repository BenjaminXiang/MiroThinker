#!/usr/bin/env python3
"""Build the proposed S2 acceptance threshold registry."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any


CORPUS_MANIFEST_SHA256 = "dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088"
BASELINE_REPORT_SHA256 = "c31b1c240ecc96661cf0b6c3057f02e631f34fcfae7356bb6f827cb5695352a1"
APPROVED_CANDIDATE_SHA256 = (
    "15a99c284861854b98a4bbfb0653700103f7b3b26e58079296f2c24e4c6c81d0"
)
APPROVAL_RECORD = {
    "kind": "explicit_user_approval",
    "approved_on": "2026-07-11",
    "statement": (
        "批准 Task 2.5 阈值候选、corpus ground-truth policy，并接受 S2 tasks 2.1–2.5"
    ),
    "review_path": (
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/review.md"
    ),
}


def metric(
    metric_id: str,
    *,
    effect: str,
    dimension: str,
    population: str,
    operator: str,
    threshold: int | float,
    source_kind: str,
    source: str,
    rationale: str,
    measurement: str,
    approval: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "effect": effect,
        "dimension": dimension,
        "population": population,
        "operator": operator,
        "threshold": threshold,
        "source_kind": source_kind,
        "source": source,
        "rationale": rationale,
        "measurement": measurement,
        "approval": approval,
        **extra,
    }


def _prd_metrics() -> list[dict[str, Any]]:
    fixed = "prd_fixed"
    metrics = [
        metric(
            "intent_accuracy",
            effect="Retrievability",
            dimension="intent",
            population="100+ clear ordinary A-G instructions with per-class reporting",
            operator="gte",
            threshold=0.90,
            source_kind="prd_minimum",
            source="docs/Agentic-RAG-PRD.md:581",
            rationale="Preserves the contract minimum; aggregate and per-class results are both reported.",
            measurement="reviewed labeled fixture through the production classifier path",
            approval=fixed,
            sample_min=100,
            sample_source="docs/Agentic-RAG-PRD.md:237",
        ),
        metric(
            "company_semantic_latency_seconds",
            effect="Retrievability",
            dimension="latency",
            population="Company semantic retrieval over the accepted 6,000+ release",
            operator="lte",
            threshold=5.0,
            source_kind="prd_minimum",
            source="docs/Agentic-RAG-PRD.md:311",
            rationale="Preserves the Company semantic retrieval response-time ceiling.",
            measurement="p95 service retrieval latency excluding answer generation",
            approval=fixed,
        ),
        metric(
            "context_resolution_seconds",
            effect="Generation fidelity",
            dimension="multi_turn_latency",
            population="evaluated contextual/reference-resolution turns",
            operator="lt",
            threshold=0.5,
            source_kind="prd_minimum",
            source="docs/Multi-turn-Context-Manager-Design.md:333",
            rationale="Preserves the explicit reference-resolution latency requirement.",
            measurement="p95 context-resolution span before retrieval",
            approval=fixed,
        ),
        metric(
            "session_ttl_seconds",
            effect="Continuous operations",
            dimension="session",
            population="inactive conversation sessions",
            operator="eq",
            threshold=1800,
            source_kind="prd_minimum",
            source="docs/Multi-turn-Context-Manager-Design.md:30",
            rationale="Preserves the confirmed 30-minute context lifetime.",
            measurement="configuration plus expiry integration scenario",
            approval=fixed,
        ),
        metric(
            "route_ttft_seconds",
            effect="Generation fidelity",
            dimension="latency",
            population="ordinary streaming answer routes",
            operator="lte",
            threshold=25.0,
            source_kind="prd_minimum",
            source="docs/Agentic-RAG-PRD.md:574",
            rationale=(
                "Preserves the PRD 5–25 second target band as a 25 second hard ceiling; faster-than-5 "
                "responses pass because speed is not a user failure."
            ),
            measurement="p95 time to first user-visible answer token",
            approval=fixed,
            target_band=[5.0, 25.0],
            hard_ceiling=25.0,
            below_band_passes=True,
        ),
        metric(
            "company_import_coverage",
            effect="Knowledge coverage",
            dimension="domain_inclusion",
            population="valid records in the accepted Company export",
            operator="gte",
            threshold=0.95,
            source_kind="prd_minimum",
            source="docs/Company-Data-Agent-PRD.md:350",
            rationale="Preserves the Company export coverage requirement.",
            measurement="full-population source-to-release accounting",
            approval=fixed,
        ),
        metric(
            "company_required_field_completeness",
            effect="Trusted data",
            dimension="field_completeness",
            population="published Company release",
            operator="eq",
            threshold=1.0,
            source_kind="prd_minimum",
            source="docs/Company-Data-Agent-PRD.md:351",
            rationale=(
                "Preserves required release-field completeness; this population gate does not hide "
                "ordinary incomplete candidates from eligible exact paths."
            ),
            measurement="full-population typed-field validation",
            approval=fixed,
        ),
        metric(
            "company_team_structured_availability",
            effect="Knowledge coverage",
            dimension="typed_subobjects",
            population="Companies whose sources contain team information",
            operator="gte",
            threshold=0.80,
            source_kind="prd_minimum",
            source="docs/Company-Data-Agent-PRD.md:352",
            rationale="Preserves structured key-person availability on the applicable subset.",
            measurement="full applicable-subset structure validation",
            approval=fixed,
        ),
    ]

    top5_sources = {
        "professor": "docs/Agentic-RAG-PRD.md:231",
        "company": "docs/Company-Data-Agent-PRD.md:354",
        "paper": "docs/Paper-Data-Agent-PRD.md:429",
        "patent": "docs/Patent-Data-Agent-PRD.md:298",
    }
    for domain, source in top5_sources.items():
        extra: dict[str, Any] = {"k": 5}
        if domain != "professor":
            extra["sample_min"] = 50
        metrics.append(
            metric(
                f"{domain}_top5_relevance",
                effect="Retrievability",
                dimension="precision_at_k",
                population=f"reviewed {domain} information-retrieval queries",
                operator="gte",
                threshold=0.85,
                source_kind="prd_minimum",
                source=source,
                rationale="Preserves the applicable Top-5 relevance minimum.",
                measurement="human-reviewed relevance labels, reported per domain and path",
                approval=fixed,
                **extra,
            )
        )

    for metric_id, threshold, source in (
        ("company_dedup_accuracy", 0.95, "docs/Company-Data-Agent-PRD.md:353"),
        ("paper_dedup_accuracy", 0.95, "docs/Paper-Data-Agent-PRD.md:427"),
        ("patent_dedup_accuracy", 0.95, "docs/Patent-Data-Agent-PRD.md:297"),
    ):
        metrics.append(
            metric(
                metric_id,
                effect="Trusted data",
                dimension="identity",
                population="reviewed duplicate/non-duplicate pair gold",
                operator="gte",
                threshold=threshold,
                source_kind="prd_minimum",
                source=source,
                rationale="Preserves the domain deduplication accuracy minimum.",
                measurement="human-reviewed pair classification",
                approval=fixed,
                sample_min=100,
            )
        )

    for metric_id, source in (
        ("paper_summary_zh_completeness", "docs/Paper-Data-Agent-PRD.md:424"),
        ("paper_summary_text_completeness", "docs/Paper-Data-Agent-PRD.md:425"),
        ("patent_summary_text_completeness", "docs/Patent-Data-Agent-PRD.md:294"),
    ):
        metrics.append(
            metric(
                metric_id,
                effect="Knowledge coverage",
                dimension="enrichment_completeness",
                population="all included objects in the applicable full domain release",
                operator="gte",
                threshold=0.90,
                source_kind="prd_minimum",
                source=source,
                rationale=(
                    "Preserves the enrichment coverage minimum as an operations/release metric, not "
                    "a global per-object retrieval exclusion."
                ),
                measurement="full-population field lineage/status scan",
                approval=fixed,
            )
        )

    metrics.extend(
        [
            metric(
                "paper_attribution_accuracy",
                effect="Trusted data",
                dimension="relationship_accuracy",
                population="reviewed Professor-Paper attribution gold",
                operator="gte",
                threshold=0.90,
                source_kind="prd_minimum",
                source="docs/Paper-Data-Agent-PRD.md:426",
                rationale="Preserves the Paper authorship attribution minimum.",
                measurement="human-reviewed relationship sample",
                approval=fixed,
                sample_min=100,
            ),
            metric(
                "patent_import_coverage",
                effect="Knowledge coverage",
                dimension="domain_inclusion",
                population="valid records in the accepted Patent export",
                operator="gte",
                threshold=0.95,
                source_kind="prd_minimum",
                source="docs/Patent-Data-Agent-PRD.md:293",
                rationale="Preserves the Patent export coverage requirement.",
                measurement="full-population source-to-release accounting",
                approval=fixed,
            ),
            metric(
                "patent_company_relation_accuracy",
                effect="Trusted data",
                dimension="relationship_accuracy",
                population="reviewed Patent-Company relationship gold",
                operator="gte",
                threshold=0.90,
                source_kind="prd_minimum",
                source="docs/Patent-Data-Agent-PRD.md:295",
                rationale="Preserves the Patent applicant/Company association minimum.",
                measurement="human-reviewed relationship sample",
                approval=fixed,
                sample_min=100,
            ),
            metric(
                "patent_professor_relation_accuracy",
                effect="Trusted data",
                dimension="relationship_accuracy",
                population="reviewed Patent-Professor relationship gold",
                operator="gte",
                threshold=0.85,
                source_kind="prd_minimum",
                source="docs/Patent-Data-Agent-PRD.md:296",
                rationale="Preserves the Patent inventor/Professor association minimum.",
                measurement="human-reviewed relationship sample",
                approval=fixed,
                sample_min=50,
            ),
        ]
    )

    summary_quality_sources = {
        "paper": "docs/Agentic-RAG-PRD.md:379",
        "patent": "docs/Agentic-RAG-PRD.md:451",
    }
    for domain, source in summary_quality_sources.items():
        metrics.append(
            metric(
                f"{domain}_human_summary_quality",
                effect="Generation fidelity",
                dimension="human_summary_quality",
                population=f"reviewed {domain} explanations for non-specialist users",
                operator="gte",
                threshold=4.0,
                source_kind="prd_minimum",
                source=source,
                rationale="Preserves the human comprehensibility minimum.",
                measurement="human 1–5 rubric with source-grounding review",
                approval=fixed,
                scale_max=5.0,
            )
        )
    return metrics


def _hard_invariants() -> list[dict[str, Any]]:
    zero_metrics = [
        ("original_source_write_attempts", "Continuous operations", "source_safety"),
        ("destructive_target_ambiguity_writes", "Continuous operations", "target_safety"),
        ("wrong_identity_decisions", "Trusted data", "identity"),
        ("invented_recovery_facts", "Trusted data", "recovery_fidelity"),
        ("unsupported_material_claims", "Generation fidelity", "claim_support"),
        ("unsourced_material_web_claims", "Generation fidelity", "web_provenance"),
        ("broken_relationship_references", "Trusted data", "relationship_integrity"),
        ("mixed_release_references", "Continuous operations", "release_integrity"),
        ("index_parity_deviations", "Retrievability", "index_parity"),
        ("online_direct_canonical_writes", "Continuous operations", "write_authority"),
        ("prebackup_rebuild_writes", "Continuous operations", "backup_gate"),
        ("query_identity_mutations", "Trusted data", "identity_write_authority"),
        ("protected_slot_losses", "Retrievability", "query_rewrite"),
        ("undisplayed_set_references", "Generation fidelity", "multi_turn"),
        ("unsupported_followup_claims", "Generation fidelity", "progressive_exploration"),
    ]
    metrics = [
        metric(
            metric_id,
            effect=effect,
            dimension=dimension,
            population="all applicable deterministic checks and reviewed acceptance samples",
            operator="eq",
            threshold=0,
            source_kind="hard_invariant",
            source=".agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md",
            rationale="A named safety, identity, evidence, or consistency invariant has zero tolerance.",
            measurement="automated invariant plus reviewed scenario evidence",
            approval="user_confirmed_invariant",
        )
        for metric_id, effect, dimension in zero_metrics
    ]
    complete_metrics = [
        ("backup_family_coverage", "Continuous operations", "backup_gate", {}),
        ("independent_restore_coverage", "Continuous operations", "restore_gate", {}),
        ("material_claim_evidence_coverage", "Generation fidelity", "claim_support", {}),
        ("evaluation_trace_completeness", "Scenario acceptance", "traceability", {}),
        (
            "information_request_web_invocation",
            "Retrievability",
            "universal_web",
            {"unit": "case_rate"},
        ),
        ("provider_cost_trace_coverage", "Continuous operations", "provider_cost", {}),
    ]
    metrics.extend(
        metric(
            metric_id,
            effect=effect,
            dimension=dimension,
            population="all applicable accepted runs/cases",
            operator="eq",
            threshold=1.0,
            source_kind="hard_invariant",
            source="openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md",
            rationale="Completeness is required so missing evidence cannot be hidden by an aggregate score.",
            measurement="deterministic coverage/accounting check",
            approval="user_confirmed_invariant",
            **extra,
        )
        for metric_id, effect, dimension, extra in complete_metrics
    )
    metrics.extend(
        [
            metric(
                "non_information_web_invocation",
                effect="Retrievability",
                dimension="universal_web",
                population="refusal, clarification-only, and UI-control turns",
                operator="eq",
                threshold=0.0,
                source_kind="hard_invariant",
                source="openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md",
                rationale="Non-information turns must not spend provider budget or fabricate retrieval need.",
                measurement="trace invocation accounting",
                approval="user_confirmed_invariant",
            ),
            metric(
                "supplemental_retrieval_attempts",
                effect="Retrievability",
                dimension="bounded_retry",
                population="each information-retrieval turn after initial lane execution",
                operator="lte",
                threshold=1,
                source_kind="hard_invariant",
                source="openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md#8",
                rationale="Allows one targeted evidence-gap retry while preventing unbounded loops.",
                measurement="per-turn trace attempt count",
                approval="user_confirmed_invariant",
                unit="supplemental_wave",
                multiple_parallel_lanes_allowed=True,
            ),
            metric(
                "insufficient_evidence_disclosure",
                effect="Generation fidelity",
                dimension="limitation_disclosure",
                population="answers with a material unsupported or conflicting part",
                operator="eq",
                threshold=1.0,
                source_kind="hard_invariant",
                source="openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md",
                rationale="Every material evidence gap must be visible rather than filled from model memory.",
                measurement="claim/evidence/limitation trace check plus review",
                approval="user_confirmed_invariant",
            ),
            metric(
                "complex_progress_signal_coverage",
                effect="Generation fidelity",
                dimension="latency",
                population="complex cross-domain, Web, or supplemental-retrieval turns",
                operator="eq",
                threshold=1.0,
                source_kind="hard_invariant",
                source="docs/Agentic-RAG-PRD.md:575",
                rationale="Every complex long-running route must expose user-visible progress.",
                measurement="trace/UI-event coverage for required progress stages",
                approval="prd_fixed",
            ),
        ]
    )
    return metrics


def _calibrated_metrics() -> list[dict[str, Any]]:
    pending = "pending_user_approval"
    source = "calibration_proposal:user_effect_and_s2_baseline"
    metrics: list[dict[str, Any]] = [
        metric(
            "intent_per_class_accuracy",
            effect="Retrievability",
            dimension="intent",
            population="each A-G class independently",
            operator="gte",
            threshold=0.80,
            source_kind="calibrated",
            source=source,
            rationale=(
                "Prevents the high-volume exact class from masking weak conversational, cross-domain, "
                "refusal, or ambiguity behavior in the overall PRD intent score."
            ),
            measurement="reviewed per-class production-classifier accuracy",
            approval=pending,
            sample_min_per_class=20,
        )
    ]
    for domain in ("professor", "company", "paper", "patent"):
        for suffix, dimension, operator, threshold, population, measurement in (
            (
                "exact_recall_at_5",
                "recall_at_k",
                "gte",
                0.95,
                f"reviewed {domain} exact-name/title/identifier cases",
                "reviewed required-object recall at K=5",
            ),
            (
                "semantic_recall_at_10",
                "recall_at_k",
                "gte",
                0.80,
                f"reviewed {domain} semantic/topic cases",
                "reviewed required-object recall at K=10",
            ),
            (
                "exact_precision_at_1",
                "precision_at_k",
                "gte",
                0.95,
                f"reviewed {domain} unambiguous exact cases",
                "top-1 identity/relevance precision",
            ),
            (
                "semantic_ndcg_at_10",
                "ranking",
                "gte",
                0.80,
                f"graded-relevance {domain} semantic/topic cases",
                "human-labeled NDCG at K=10",
            ),
        ):
            metrics.append(
                metric(
                    f"{domain}_{suffix}",
                    effect="Retrievability",
                    dimension=dimension,
                    population=population,
                    operator=operator,
                    threshold=threshold,
                    source_kind="calibrated",
                    source=source,
                    rationale=(
                        "Balances breadth and precision by gating the path/domain independently; "
                        "ordinary incomplete enrichment is not a retrieval exclusion."
                    ),
                    measurement=measurement,
                    approval=pending,
                    sample_min=30,
                )
            )
        metrics.append(
            metric(
                f"{domain}_structured_filter_recall",
                effect="Retrievability",
                dimension="structured_filter",
                population=f"reviewed {domain} cases with satisfiable hard filters",
                operator="gte",
                threshold=0.90,
                source_kind="calibrated",
                source=source,
                rationale="Measures filter reach separately while protected constraint violations remain zero.",
                measurement="reviewed result-set recall with exact constraint validation",
                approval=pending,
                sample_min=20,
            )
        )

    metrics.extend(
        [
            metric(
                "required_relationship_family_scenario_coverage",
                effect="Knowledge coverage",
                dimension="relationship_coverage",
                population=(
                    "every PRD-required typed relationship family/direction, including explicit "
                    "supported, absent-data, and insufficient-evidence scenarios"
                ),
                operator="eq",
                threshold=1.0,
                source_kind="calibrated",
                source=source,
                rationale=(
                    "Prevents sparse relation gold from making missing business-required families "
                    "invisible; absent source data remains an explicit blocking gap rather than a false zero."
                ),
                measurement="catalog-to-reviewed-scenario coverage accounting",
                approval=pending,
            ),
            metric(
                "relationship_recall_at_10",
                effect="Retrievability",
                dimension="relationship_traversal",
                population="each reviewed supported relationship family/direction with non-empty gold",
                operator="gte",
                threshold=0.80,
                source_kind="calibrated",
                source=source,
                rationale="Requires useful reach without pretending data-absent relationship families are zero-quality retrieval.",
                measurement="per-family/direction required-edge recall at K=10",
                approval=pending,
                sample_min=20,
            ),
            metric(
                "relationship_result_precision",
                effect="Trusted data",
                dimension="relationship_traversal",
                population="each reviewed supported relationship family/direction",
                operator="gte",
                threshold=0.90,
                source_kind="calibrated",
                source=source,
                rationale="Balances relation reach with edge precision; wrong-identity edges remain a zero-tolerance invariant.",
                measurement="human-reviewed returned-edge precision",
                approval=pending,
                sample_min=20,
            ),
            metric(
                "workbook_key_point_coverage",
                effect="Scenario acceptance",
                dimension="reference_answer_fidelity",
                population="25 user-confirmed workbook cases, interpreting known-bad responses by key points",
                operator="gte",
                threshold=0.80,
                source_kind="calibrated",
                source=source,
                rationale="Uses case-specific reference gold without enforcing verbatim templates.",
                measurement="human-calibrated structured key-point coverage judge",
                approval=pending,
                sample_min=25,
            ),
            metric(
                "supported_answer_completeness",
                effect="Generation fidelity",
                dimension="answer_completeness",
                population="reviewed material answer parts that have available evidence",
                operator="gte",
                threshold=0.80,
                source_kind="calibrated",
                source=source,
                rationale="Rewards useful completeness while unsupported claims remain zero-tolerance.",
                measurement="claim-part coverage over the validated evidence set",
                approval=pending,
                sample_min=50,
            ),
            metric(
                "llm_judge_human_agreement",
                effect="Scenario acceptance",
                dimension="evaluation_quality",
                population="stratified human-double-reviewed calibration sample",
                operator="gte",
                threshold=0.80,
                source_kind="calibrated",
                source=source,
                rationale="LLM judgment can scale evaluation only after agreement with human labels is demonstrated.",
                measurement="agreement on pass/fail plus score correlation, reported by family/domain",
                approval=pending,
                sample_min=50,
            ),
            metric(
                "multi_turn_reference_accuracy",
                effect="Generation fidelity",
                dimension="multi_turn",
                population="reviewed anchor, referent, displayed-set, narrowing, and traversal turns",
                operator="gte",
                threshold=0.90,
                source_kind="calibrated",
                source=source,
                rationale="Measures correct user-reference resolution while identity mutation remains forbidden.",
                measurement="scenario-level correct binding rate by context family",
                approval=pending,
                sample_min=30,
            ),
            metric(
                "topic_switch_accuracy",
                effect="Generation fidelity",
                dimension="multi_turn",
                population="reviewed explicit and implicit topic-switch turns",
                operator="gte",
                threshold=0.95,
                source_kind="calibrated",
                source=source,
                rationale="Prevents stale anchors from contaminating a new user topic.",
                measurement="scenario-level topic-reset correctness",
                approval=pending,
                sample_min=20,
            ),
            metric(
                "web_candidate_top5_relevance",
                effect="Retrievability",
                dimension="web_precision",
                population="reviewed current-Web candidates for information requests",
                operator="gte",
                threshold=0.80,
                source_kind="calibrated",
                source=source,
                rationale="Universal Web augmentation must add useful current evidence without overwhelming local precision.",
                measurement="human-reviewed Web candidate relevance at K=5",
                approval=pending,
                sample_min=50,
            ),
            metric(
                "complex_full_response_seconds",
                effect="Generation fidelity",
                dimension="latency",
                population="complex cross-domain/Web progressive-answer routes with progress events",
                operator="lte",
                threshold=60.0,
                source_kind="calibrated",
                source=source,
                rationale="Provides a generous bounded completion budget while TTFT/progress protects perceived latency.",
                measurement="p95 final-answer completion latency",
                approval=pending,
            ),
            metric(
                "ordinary_provider_attempts",
                effect="Continuous operations",
                dimension="provider_cost",
                population="ordinary information-retrieval turns",
                operator="lte",
                threshold=12,
                source_kind="calibrated",
                source=source,
                rationale="A generous safety ceiling allows extensive LLM/Web use while preventing runaway call loops.",
                measurement="trace-counted Web/LLM/embedding/rerank attempts per turn",
                approval=pending,
            ),
            metric(
                "complex_provider_attempts",
                effect="Continuous operations",
                dimension="provider_cost",
                population="complex cross-domain or supplemental-retrieval turns",
                operator="lte",
                threshold=20,
                source_kind="calibrated",
                source=source,
                rationale="Allows richer multi-stage reasoning under an explicit finite ceiling.",
                measurement="trace-counted Web/LLM/embedding/rerank attempts per turn",
                approval=pending,
            ),
            metric(
                "provider_cost_regression_ratio",
                effect="Continuous operations",
                dimension="provider_cost",
                population="same route/corpus/provider configuration versus its accepted baseline",
                operator="lte",
                threshold=1.20,
                source_kind="calibrated",
                source=source,
                rationale="Caps unexplained p95 monetary-cost regression at 20% after an initial real-provider baseline exists.",
                measurement="p95 provider-reported monetary cost ratio with identical versioned inputs",
                approval=pending,
                applicability="post_initial_accepted_real_provider_baseline",
                initial_release_fallback_metrics=[
                    "provider_cost_trace_coverage",
                    "ordinary_provider_attempts",
                    "complex_provider_attempts",
                ],
            ),
        ]
    )
    return metrics


def build_pending_thresholds() -> dict[str, Any]:
    metrics = _prd_metrics() + _hard_invariants() + _calibrated_metrics()
    ids = [item["id"] for item in metrics]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate threshold metric id")
    return {
        "schema_version": "canonical-v2-s2-acceptance-thresholds-v1",
        "approval_state": "pending_user_approval",
        "corpus_version": "regression-v1+challenge-v1",
        "corpus_manifest_sha256": CORPUS_MANIFEST_SHA256,
        "baseline_report_sha256": BASELINE_REPORT_SHA256,
        "policy": {
            "aggregate_score_can_mask_dimension_failure": False,
            "ordinary_incompleteness_is_global_exclusion": False,
            "legacy_values_are_threshold_sources": False,
            "llm_judging_requires_human_calibration": True,
            "unavailable_measurement_blocks_acceptance": True,
            "unavailable_scope": "applicable_required_metrics_only",
            "domain_and_path_failures_are_reported_independently": True,
            "same_model_generation_cannot_create_unreviewed_gold": True,
        },
        "population_contract": {
            "frozen_seed_cases": 52,
            "current_domain_case_counts": {
                "company": 30,
                "paper": 7,
                "patent": 11,
                "professor": 12,
            },
            "all_required_samples_materialized": False,
            "materialization_required_before_metric_acceptance": True,
            "domain_relevance_query_minimum_per_domain": 50,
            "exact_query_minimum_per_domain": 30,
            "semantic_query_minimum_per_domain": 30,
            "structured_filter_minimum_per_domain": 20,
            "supported_relationship_minimum_per_family_direction": 20,
            "multi_turn_minimum": 30,
            "llm_judge_calibration_minimum": 50,
            "future_population_policy": {
                "versioned_and_hashed": True,
                "selected_without_candidate_output_knowledge": True,
                "human_review_required": True,
                "missing_population_blocks_owning_metric": True,
                "new_banks_do_not_rewrite_frozen_seed_cases": True,
                "owning_tasks": ["6.1", "8.1", "9.1"],
            },
        },
        "metrics": metrics,
    }


def _serialized_thresholds(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def accept_threshold_candidate(
    candidate: dict[str, Any],
    *,
    approved_candidate_sha256: str,
    approval_record: dict[str, str],
) -> dict[str, Any]:
    actual_sha256 = hashlib.sha256(_serialized_thresholds(candidate)).hexdigest()
    if actual_sha256 != approved_candidate_sha256:
        raise ValueError(
            "threshold content does not match the reviewed candidate SHA-256: "
            f"expected {approved_candidate_sha256}, got {actual_sha256}"
        )

    accepted = deepcopy(candidate)
    accepted["approval_state"] = "accepted"
    accepted["approved_candidate_sha256"] = approved_candidate_sha256
    accepted["approval_record"] = deepcopy(approval_record)
    for item in accepted["metrics"]:
        if item["source_kind"] == "calibrated":
            item["approval"] = "user_approved"
    return accepted


def build_thresholds() -> dict[str, Any]:
    return accept_threshold_candidate(
        build_pending_thresholds(),
        approved_candidate_sha256=APPROVED_CANDIDATE_SHA256,
        approval_record=APPROVAL_RECORD,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = build_thresholds()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_serialized_thresholds(document))
    print(
        json.dumps(
            {
                "approval_state": document["approval_state"],
                "metrics": len(document["metrics"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
