#!/usr/bin/env python3
"""Measure the deterministic A-G classifier without data or provider access."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable


Classifier = Callable[[str], dict[str, Any] | None]


def measure_intent(
    fixture_path: Path,
    classifier: Classifier,
    *,
    git_commit: str,
    measured_at: str,
    command: str,
) -> dict[str, Any]:
    cases = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results: list[dict[str, str]] = []
    for case in cases:
        actual = classifier(case["query"]) or {}
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_type": case["expected_type"],
                "actual_type": str(actual.get("type", "UNKNOWN")),
            }
        )
    correct = sum(row["actual_type"] == row["expected_type"] for row in results)
    distribution = Counter(row["expected_type"] for row in results)
    by_type: dict[str, dict[str, Any]] = {}
    for query_type in sorted(distribution):
        selected = [row for row in results if row["expected_type"] == query_type]
        type_correct = sum(
            row["actual_type"] == row["expected_type"] for row in selected
        )
        by_type[query_type] = {
            "cases": len(selected),
            "correct": type_correct,
            "accuracy": type_correct / len(selected),
        }
    return {
        "schema_version": "canonical-v2-s2-offline-intent-v1",
        "status": "measured_current",
        "measurement_scope": "deterministic_rule_fallback_only",
        "git_commit": git_commit,
        "measured_at": measured_at,
        "command": command,
        "fixture_path": str(fixture_path),
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "cases": len(results),
        "correct": correct,
        "accuracy": correct / len(results) if results else None,
        "by_type": by_type,
        "mismatches": [
            row for row in results if row["actual_type"] != row["expected_type"]
        ],
        "limitations": [
            "Does not measure the provider-backed LLM classifier.",
            "Does not measure retrieval routing, database reach, query rewriting, or answer quality.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--admin-root", required=True, type=Path)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--measured-at", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.admin_root))
    chat_module = importlib.import_module("backend.api.chat")
    classifier: Classifier = getattr(chat_module, "_classify_query_by_rules")

    result = measure_intent(
        args.fixture,
        classifier,
        git_commit=args.git_commit,
        measured_at=args.measured_at,
        command=args.command,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "accuracy": result["accuracy"],
                "cases": result["cases"],
                "correct": result["correct"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
