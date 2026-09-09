#!/usr/bin/env python3
"""Compose the S2 current/legacy/unavailable baseline report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_DIMENSIONS = {
    "coverage_and_reach",
    "recall_at_k",
    "precision_at_k_and_rank",
    "intent",
    "answer_support_and_citation",
    "universal_web",
    "multi_turn",
    "latency",
    "provider_calls_and_cost",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "value": None, "reason": reason}


def _paper_recall(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    selected = [row for row in rows if int(row.get("qid", -1)) >= 100]
    if not selected:
        return None
    hit = sum(len(row.get("hits", [])) for row in selected)
    required = sum(
        len(row.get("hits", [])) + len(row.get("misses", [])) for row in selected
    )
    return {
        "cases": len(selected),
        "hit": hit,
        "required": required,
        "recall": hit / required if required else None,
    }


def _answer_legacy(
    answer: dict[str, Any],
    golden: dict[str, Any],
    full_testset: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = golden.get("rows", [])
    l1_hit = sum(len(row.get("l1_hit", [])) for row in rows)
    l1_miss = sum(len(row.get("l1_miss", [])) for row in rows)
    l3_values = [row["l3_avg"] for row in rows if row.get("l3_avg") is not None]
    return [
        {
            "status": "legacy",
            "metric": "reviewed_true_accuracy",
            "population": answer.get("head_cases"),
            "value": answer.get("true_accuracy"),
            "limitation": (
                "Old V042/real-provider run on a different oracle and substrate; not comparable "
                "to Canonical V2 acceptance."
            ),
        },
        {
            "status": "legacy",
            "metric": "legacy_answer_eval",
            "population": len(rows),
            "l1_hit": l1_hit,
            "l1_required": l1_hit + l1_miss,
            "l2_violations": sum(len(row.get("l2_violations", [])) for row in rows),
            "l3_mean": sum(l3_values) / len(l3_values) if l3_values else None,
            "limitation": "Legacy evaluator output; scorer/gold quality was not revalidated in S2.",
        },
        {
            "status": "legacy",
            "metric": "legacy_full_testset_coverage",
            "population": full_testset.get("head_cases"),
            "required_recall": full_testset.get("required_recall"),
            "mean_answer_coverage": full_testset.get("mean_answer_coverage"),
            "forbidden_violation_cases": full_testset.get(
                "forbidden_violation_cases"
            ),
            "limitation": "Older legacy fixture/scorer run; retained as historical evidence only.",
        },
    ]


def build_report(
    source_inventory_path: Path,
    corpus_manifest_path: Path,
    intent_result_path: Path,
    legacy_paths: dict[str, Path],
    *,
    git_commit: str,
) -> dict[str, Any]:
    inventory = _load(source_inventory_path)
    corpus = _load(corpus_manifest_path)
    intent = _load(intent_result_path)
    legacy = {name: _load(path) for name, path in legacy_paths.items()}
    recovery = inventory["recovery_database_snapshot"]
    databases = recovery.get("databases", [])
    public_counts = databases[0].get("public_core_counts", {}) if databases else {}
    salvage = recovery.get("salvage", {})
    source_domains = sorted(
        {
            domain
            for source in inventory.get("sources", [])
            for domain in source.get("domains", [])
            if domain in {"professor", "company", "paper", "patent"}
        }
    )

    recall = legacy["recall"]
    precision = legacy["precision"]
    precision_labels = legacy["precision_labels"]
    latency = legacy["latency"]
    multi_turn = legacy["multi_turn"]
    recall_rows = recall.get("rows", [])
    recall_hit = recall.get("total_hit")
    recall_required = recall.get("total_req")
    recall_value = (
        recall_hit / recall_required
        if isinstance(recall_hit, (int, float))
        and isinstance(recall_required, (int, float))
        and recall_required
        else None
    )

    input_paths = {
        "source_inventory": source_inventory_path,
        "corpus_manifest": corpus_manifest_path,
        "offline_intent": intent_result_path,
        **{f"legacy_{name}": path for name, path in legacy_paths.items()},
    }
    dimensions: dict[str, Any] = {
        "coverage_and_reach": {
            "current": {
                "status": "measured_current",
                "scope": "source_evidence_and_recovery_substrate_only",
                "source_domains_with_inventoried_evidence": source_domains,
                "recovery_public_core_counts": public_counts,
                "salvage": {
                    "paper_distinct_ids": salvage.get("paper", {}).get("distinct_ids"),
                    "professor_paper_link_distinct_ids": salvage.get(
                        "professor_paper_link", {}
                    ).get("distinct_ids"),
                    "professor_ids": salvage.get("professor_paper_link", {}).get(
                        "distinct_professor_ids"
                    ),
                    "paper_ids_in_links": salvage.get("professor_paper_link", {}).get(
                        "distinct_paper_ids"
                    ),
                    "field_errors": salvage.get("field_errors", {}).get("total"),
                },
                "retrieval_reach": _unavailable(
                    "Recovery public domain tables are empty and no accepted canonical release or "
                    "verified Milvus copy exists."
                ),
            },
            "legacy": [],
        },
        "recall_at_k": {
            "current": _unavailable(
                "No current canonical retrieval substrate or verified index copy can run the frozen corpus."
            ),
            "legacy": [
                {
                    "status": "legacy",
                    "metric": "required_entity_recall",
                    "hit": recall_hit,
                    "required": recall_required,
                    "recall": recall_value,
                    "paper_rollup": _paper_recall(recall_rows),
                    "limitation": (
                        "Stored post-fix V042/real-Milvus run on a changed 41-entity oracle; not a "
                        "Canonical V2 or frozen-corpus measurement."
                    ),
                }
            ],
        },
        "precision_at_k_and_rank": {
            "current": _unavailable(
                "No current retrieval substrate and no complete reviewed relevance labels/rank oracle."
            ),
            "legacy": [
                {
                    "status": "legacy",
                    "metric": "candidate_capture_only",
                    "rows": len(precision.get("rows", [])),
                    "precision_at_k": None,
                    "rank_metric": None,
                    "unsourced_web_candidates": precision.get("total_unsourced_web"),
                    "label_status": precision_labels.get("_status"),
                    "label_case_scaffolds": len(precision_labels.get("cases", [])),
                    "limitation": (
                        "The stored precision harness explicitly did not score precision; its label "
                        "file remains incomplete, so zero listed false positives is not a precision value."
                    ),
                }
            ],
        },
        "intent": {
            "current": {
                "status": "measured_current",
                "metric": "deterministic_rule_fallback_accuracy",
                "cases": intent.get("cases"),
                "correct": intent.get("correct"),
                "accuracy": intent.get("accuracy"),
                "by_type": intent.get("by_type"),
                "fixture_sha256": intent.get("fixture_sha256"),
                "command": intent.get("command"),
                "limitations": intent.get("limitations", [])
                + ["Uses the separate committed 100-case intent fixture, not the frozen S2 corpus."],
            },
            "legacy": [],
        },
        "answer_support_and_citation": {
            "current": _unavailable(
                "No current accepted evidence set, answer trace, Web lane, or provider run exists."
            ),
            "legacy": _answer_legacy(
                legacy["answer"], legacy["golden_answer"], legacy["full_testset"]
            ),
        },
        "universal_web": {
            "current": _unavailable(
                "S2 makes no live provider calls; universal invocation and provenance cannot be measured."
            ),
            "legacy": [
                {
                    "status": "legacy",
                    "metric": "unsourced_web_candidates_in_capture",
                    "value": precision.get("total_unsourced_web"),
                    "invocation_rate": None,
                    "limitation": (
                        "Candidate capture covered 12 legacy rows and cannot establish universal Web "
                        "invocation, claim provenance, or source quality."
                    ),
                }
            ],
        },
        "multi_turn": {
            "current": _unavailable(
                "No accepted current canonical release or data-grounded session replay is available."
            ),
            "legacy": [
                {
                    "status": "legacy",
                    "metric": "layer_d_red_baseline",
                    **multi_turn.get("summary", {}),
                    "limitation": "Pre-incident V042 run on legacy fixtures and response scorer.",
                }
            ],
        },
        "latency": {
            "current": _unavailable(
                "No current end-to-end retrieval/answer/provider path can run on the recovered substrate."
            ),
            "legacy": [
                {
                    "status": "legacy",
                    "metric": "retrieval_overall_p95",
                    "runs_per_case": latency.get("runs"),
                    "cases": len(latency.get("rows", [])),
                    "p95_seconds": latency.get("overall_p95"),
                    "legacy_verdict": latency.get("slo_verdict"),
                    "limitation": "Old DB/Milvus path; excludes the future universal Web/LLM plan and answer cost.",
                }
            ],
        },
        "provider_calls_and_cost": {
            "current": _unavailable(
                "S2 performs no live Web/LLM/embedding/reranking calls and no current cost trace exists."
            ),
            "legacy": [
                {
                    "status": "unavailable",
                    "value": None,
                    "reason": "Stored legacy artifacts do not contain complete provider-call or cost accounting.",
                }
            ],
        },
    }
    assert set(dimensions) == REQUIRED_DIMENSIONS
    return {
        "schema_version": "canonical-v2-s2-baseline-report-v1",
        "git_commit": git_commit,
        "measured_at": intent.get("measured_at"),
        "source_checkpoint_at": inventory.get("captured_at"),
        "corpus_schema_version": corpus.get("schema_version"),
        "corpus_approval_state": corpus.get("approval_state"),
        "status_definitions": {
            "measured_current": "Recomputed in S2 on this checkout using current immutable/offline inputs.",
            "legacy": "Stored result from a previous substrate, corpus, scorer, or provider run.",
            "unavailable": "No valid current measurement is possible without a missing substrate, label, or provider run.",
        },
        "comparison_policy": {
            "cross_population_comparison_allowed": False,
            "rule": (
                "Do not compare or aggregate results across changed database/index releases, corpus "
                "hashes, labels, scorers, provider/model versions, or metric definitions."
            ),
        },
        "input_artifacts": {
            name: _artifact(path) for name, path in sorted(input_paths.items())
        },
        "dimensions": dimensions,
        "legacy_oracle_limitations": [
            "The old precision artifact was candidate capture, not scored Precision@K.",
            "Legacy retrieval corpora changed over time and include unsatisfiable or incomplete gold.",
            "Legacy answer judges/scorers were not validated against the frozen S2 corpus.",
            "No legacy artifact provides complete Universal Web invocation, provider-call, or cost accounting.",
        ],
        "safety": {
            "database_reads": 0,
            "milvus_client_opens": 0,
            "provider_calls": 0,
            "source_mutations": 0,
            "backup_restore_gate_accepted": False,
            "rebuild_writes_authorized": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-inventory", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--intent-result", required=True, type=Path)
    parser.add_argument("--legacy", action="append", default=[])
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    legacy_paths: dict[str, Path] = {}
    for item in args.legacy:
        name, value = item.split("=", 1)
        legacy_paths[name] = Path(value)
    report = build_report(
        args.source_inventory,
        args.corpus_manifest,
        args.intent_result,
        legacy_paths,
        git_commit=args.git_commit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"dimensions": len(report["dimensions"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
