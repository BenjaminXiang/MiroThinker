#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Evaluate strict Phase A professor acceptance gates from E2E and manual metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_url_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    sampled_urls = int(summary.get("sampled_urls") or len(summary.get("results", [])) or 0)
    gate_passed_urls = int(summary.get("gate_passed_urls") or 0)
    identity_passed_urls = int(summary.get("identity_passed_urls") or 0)
    paper_backed_urls = int(summary.get("paper_backed_urls") or 0)
    required_fields_passed_urls = int(summary.get("required_fields_passed_urls") or 0)
    quality_ready_urls = int(summary.get("quality_ready_urls") or 0)
    return {
        "sampled_urls": sampled_urls,
        "gate_passed_urls": gate_passed_urls,
        "identity_passed_urls": identity_passed_urls,
        "paper_backed_urls": paper_backed_urls,
        "required_fields_passed_urls": required_fields_passed_urls,
        "quality_ready_urls": quality_ready_urls,
        "url_gate_pass_rate": _safe_rate(gate_passed_urls, sampled_urls),
        "url_identity_pass_rate": _safe_rate(identity_passed_urls, sampled_urls),
        "url_paper_backed_rate": _safe_rate(paper_backed_urls, sampled_urls),
        "url_required_fields_rate": _safe_rate(required_fields_passed_urls, sampled_urls),
        "url_quality_ready_rate": _safe_rate(quality_ready_urls, sampled_urls),
        "degraded_ratio": float(summary.get("degraded_ratio") or 0.0),
        "degradation_alerts": summary.get("degradation_alerts") or {},
    }


def _collect_manual_metrics(audit: dict[str, Any] | None) -> dict[str, Any]:
    if audit is None:
        return {
            "manual_identity_samples": 0,
            "manual_identity_correct": 0,
            "manual_identity_accuracy": None,
            "manual_paper_link_samples": 0,
            "manual_paper_link_correct": 0,
            "manual_paper_link_accuracy": None,
        }

    identity_samples = 0
    identity_correct = 0
    paper_samples = 0
    paper_correct = 0
    for item in audit.get("items", []):
        manual = item.get("manual") or {}
        identity_value = manual.get("identity_correct")
        if isinstance(identity_value, bool):
            identity_samples += 1
            identity_correct += int(identity_value)

        judged = int(manual.get("paper_matches_judged") or 0)
        correct = int(manual.get("paper_matches_correct") or 0)
        if judged < 0 or correct < 0 or correct > judged:
            raise ValueError("manual paper match counts must satisfy 0 <= correct <= judged")
        paper_samples += judged
        paper_correct += correct

    return {
        "manual_identity_samples": identity_samples,
        "manual_identity_correct": identity_correct,
        "manual_identity_accuracy": _safe_rate(identity_correct, identity_samples),
        "manual_paper_link_samples": paper_samples,
        "manual_paper_link_correct": paper_correct,
        "manual_paper_link_accuracy": _safe_rate(paper_correct, paper_samples),
    }


def _collect_retrieval_metrics(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "retrieval_query_samples": 0,
            "retrieval_judged_result_count": 0,
            "retrieval_relevant_result_count": 0,
            "retrieval_top5_relevant_queries": 0,
            "retrieval_duplicate_target_queries": 0,
            "retrieval_duplicate_target_rate": None,
            "retrieval_top5_rate": None,
        }
    query_count = int(payload.get("query_count") or 0)
    judged_result_count = int(payload.get("judged_result_count") or 0)
    relevant_result_count = int(payload.get("relevant_result_count") or 0)
    relevant_queries = int(payload.get("top5_relevant_query_count") or 0)
    if query_count < 0 or judged_result_count < 0 or relevant_result_count < 0:
        raise ValueError("retrieval eval counts must be non-negative")
    if relevant_queries < 0 or relevant_queries > query_count:
        raise ValueError("retrieval query counts must satisfy 0 <= relevant <= query_count")
    if relevant_result_count > judged_result_count:
        raise ValueError("retrieval result counts must satisfy 0 <= relevant <= judged")
    if judged_result_count > 0:
        top5_rate = relevant_result_count / judged_result_count
    elif payload.get("top5_relevance_rate") is not None:
        top5_rate = float(payload["top5_relevance_rate"])
    elif payload.get("top5_exact_target_rate") is not None:
        top5_rate = float(payload["top5_exact_target_rate"])
    else:
        top5_rate = _safe_rate(relevant_queries, query_count)
    return {
        "retrieval_query_samples": query_count,
        "retrieval_judged_result_count": judged_result_count,
        "retrieval_relevant_result_count": relevant_result_count,
        "retrieval_top5_relevant_queries": relevant_queries,
        "retrieval_top5_exact_target_queries": int(
            payload.get("top5_exact_target_query_count") or 0
        ),
        "retrieval_duplicate_target_queries": int(
            payload.get("top5_duplicate_target_query_count") or 0
        ),
        "retrieval_duplicate_target_rate": (
            float(payload["top5_duplicate_target_rate"])
            if payload.get("top5_duplicate_target_rate") is not None
            else None
        ),
        "retrieval_top5_rate": top5_rate,
    }


def _evaluate_gate(
    *,
    url_metrics: dict[str, Any],
    manual_metrics: dict[str, Any],
    retrieval_metrics: dict[str, Any],
    thresholds: dict[str, float | int],
    manual_audit_present: bool,
    retrieval_eval_present: bool,
) -> tuple[list[str], list[str]]:
    blocking_reasons: list[str] = []
    warnings = [
        f"degradation_alert:{name}={count}"
        for name, count in sorted(url_metrics["degradation_alerts"].items())
        if count
    ]
    duplicate_target_queries = int(retrieval_metrics.get("retrieval_duplicate_target_queries") or 0)
    if duplicate_target_queries > 0:
        warnings.append(f"retrieval_duplicate_targets={duplicate_target_queries}")

    if url_metrics["sampled_urls"] <= 0:
        blocking_reasons.append("no_url_samples")
    else:
        if (url_metrics["url_gate_pass_rate"] or 0.0) < thresholds["min_url_gate_pass_rate"]:
            blocking_reasons.append("url_gate_rate_below_threshold")
        if (url_metrics["url_identity_pass_rate"] or 0.0) < thresholds["min_url_identity_pass_rate"]:
            blocking_reasons.append("url_identity_rate_below_threshold")
        if (url_metrics["url_paper_backed_rate"] or 0.0) < thresholds["min_url_paper_backed_rate"]:
            blocking_reasons.append("url_paper_backed_rate_below_threshold")
        if (url_metrics["url_required_fields_rate"] or 0.0) < thresholds["min_url_required_fields_rate"]:
            blocking_reasons.append("url_required_fields_rate_below_threshold")
        if (url_metrics["url_quality_ready_rate"] or 0.0) < thresholds["min_url_quality_ready_rate"]:
            blocking_reasons.append("url_quality_ready_rate_below_threshold")

    if not manual_audit_present:
        blocking_reasons.append("manual_identity_metrics_missing")
        blocking_reasons.append("manual_paper_link_metrics_missing")
    else:
        if manual_metrics["manual_identity_samples"] <= 0:
            blocking_reasons.append("manual_identity_metrics_missing")
        elif manual_metrics["manual_identity_samples"] < thresholds["min_identity_samples"]:
            blocking_reasons.append("manual_identity_samples_insufficient")
        elif (manual_metrics["manual_identity_accuracy"] or 0.0) < thresholds["min_identity_accuracy"]:
            blocking_reasons.append("manual_identity_rate_below_threshold")

        if manual_metrics["manual_paper_link_samples"] <= 0:
            blocking_reasons.append("manual_paper_link_metrics_missing")
        elif manual_metrics["manual_paper_link_samples"] < thresholds["min_paper_link_samples"]:
            blocking_reasons.append("manual_paper_link_samples_insufficient")
        elif (manual_metrics["manual_paper_link_accuracy"] or 0.0) < thresholds["min_paper_link_accuracy"]:
            blocking_reasons.append("manual_paper_link_rate_below_threshold")

    if not retrieval_eval_present:
        blocking_reasons.append("retrieval_eval_missing")
    else:
        if retrieval_metrics["retrieval_query_samples"] < thresholds["min_retrieval_query_samples"]:
            blocking_reasons.append("retrieval_query_samples_insufficient")
        elif (retrieval_metrics["retrieval_top5_rate"] or 0.0) < thresholds["min_retrieval_top5_rate"]:
            blocking_reasons.append("retrieval_top5_rate_below_threshold")

    return blocking_reasons, warnings


def _build_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Professor Phase A Gate Report",
        "",
        "## Decision",
        f"- Go for Phase B: `{report['go_for_phase_b']}`",
        "",
        "## Inputs",
        f"- URL summary: `{report['inputs']['url_summary']}`",
        f"- Manual audit json: `{report['inputs']['manual_audit_json']}`",
        f"- Retrieval eval json: `{report['inputs']['retrieval_eval_json']}`",
        "",
        "## Blocking Reasons",
    ]
    if report["blocking_reasons"]:
        for reason in report["blocking_reasons"]:
            lines.append(f"- `{reason}`")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Warnings",
    ])
    if report["warnings"]:
        for warning in report["warnings"]:
            lines.append(f"- `{warning}`")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Metrics",
    ])
    for key in sorted(report["metrics"]):
        value = report["metrics"][key]
        if isinstance(value, float):
            lines.append(f"- `{key}`: `{value:.4f}`")
        else:
            lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate strict Phase A professor acceptance gates."
    )
    parser.add_argument("--url-summary", type=Path, required=True)
    parser.add_argument("--manual-audit-json", type=Path, default=None)
    parser.add_argument("--retrieval-eval-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--min-url-gate-pass-rate", type=float, default=1.0)
    parser.add_argument("--min-url-identity-pass-rate", type=float, default=1.0)
    parser.add_argument("--min-url-paper-backed-rate", type=float, default=1.0)
    parser.add_argument("--min-url-required-fields-rate", type=float, default=1.0)
    parser.add_argument("--min-url-quality-ready-rate", type=float, default=1.0)
    parser.add_argument("--min-identity-accuracy", type=float, default=0.95)
    parser.add_argument("--min-identity-samples", type=int, default=50)
    parser.add_argument("--min-paper-link-accuracy", type=float, default=0.90)
    parser.add_argument("--min-paper-link-samples", type=int, default=100)
    parser.add_argument("--min-retrieval-top5-rate", type=float, default=0.85)
    parser.add_argument("--min-retrieval-query-samples", type=int, default=50)
    args = parser.parse_args()

    if not args.url_summary.exists():
        print(json.dumps({"error": f"url summary not found: {args.url_summary}"}, ensure_ascii=False))
        return 1

    output_dir = args.output_dir or args.url_summary.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    url_summary = _load_json(args.url_summary)
    manual_audit = _load_json(args.manual_audit_json) if args.manual_audit_json else None
    retrieval_eval = _load_json(args.retrieval_eval_json) if args.retrieval_eval_json else None

    thresholds: dict[str, float | int] = {
        "min_url_gate_pass_rate": args.min_url_gate_pass_rate,
        "min_url_identity_pass_rate": args.min_url_identity_pass_rate,
        "min_url_paper_backed_rate": args.min_url_paper_backed_rate,
        "min_url_required_fields_rate": args.min_url_required_fields_rate,
        "min_url_quality_ready_rate": args.min_url_quality_ready_rate,
        "min_identity_accuracy": args.min_identity_accuracy,
        "min_identity_samples": args.min_identity_samples,
        "min_paper_link_accuracy": args.min_paper_link_accuracy,
        "min_paper_link_samples": args.min_paper_link_samples,
        "min_retrieval_top5_rate": args.min_retrieval_top5_rate,
        "min_retrieval_query_samples": args.min_retrieval_query_samples,
    }

    url_metrics = _collect_url_metrics(url_summary)
    manual_metrics = _collect_manual_metrics(manual_audit)
    retrieval_metrics = _collect_retrieval_metrics(retrieval_eval)
    blocking_reasons, warnings = _evaluate_gate(
        url_metrics=url_metrics,
        manual_metrics=manual_metrics,
        retrieval_metrics=retrieval_metrics,
        thresholds=thresholds,
        manual_audit_present=manual_audit is not None,
        retrieval_eval_present=retrieval_eval is not None,
    )

    report = {
        "inputs": {
            "url_summary": str(args.url_summary),
            "manual_audit_json": str(args.manual_audit_json) if args.manual_audit_json else None,
            "retrieval_eval_json": str(args.retrieval_eval_json) if args.retrieval_eval_json else None,
            "output_dir": str(output_dir),
        },
        "thresholds": thresholds,
        "go_for_phase_b": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "metrics": {
            **url_metrics,
            **manual_metrics,
            **retrieval_metrics,
        },
    }

    report_path = output_dir / "phase_a_gate_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = output_dir / "phase_a_gate_report.md"
    markdown_path.write_text(_build_markdown_report(report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nGate report saved to: {report_path}")
    print(f"Markdown gate report saved to: {markdown_path}")
    return 0 if report["go_for_phase_b"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
