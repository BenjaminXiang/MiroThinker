#!/usr/bin/env python3
"""Offline re-judge of a saved workbook regression run.

Loads per-group.json from a previous run and re-runs the (possibly updated)
evaluation logic against each recorded answer, reporting which turns flipped
and why. Never touches the network except for the optional LLM semantic judge,
which falls back to word-level results on any failure.

Usage:
  python rejudge_workbook.py <per-group.json> [--json-out out.json]
"""
from __future__ import annotations

import argparse
import json
import sys

from workbook_regression import _evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_json")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    with open(args.run_json, encoding="utf-8") as fh:
        report = json.load(fh)

    flips: list[dict] = []
    stats = {"unchanged_pass": 0, "unchanged_fail": 0, "pass_to_fail": 0, "fail_to_pass": 0}
    new_turns = []
    for turn in report["turns"]:
        verdict = _evaluate(
            turn["query"], turn["answer_text"], turn["reference_answer"], turn["key_points"]
        )
        old_status = turn.get("status")
        new_status = verdict["status"]
        key = "unchanged"
        if old_status != new_status:
            key = "pass_to_fail" if old_status == "pass" else "fail_to_pass"
        stats[key if key in stats else ("unchanged_pass" if new_status == "pass" else "unchanged_fail")] += 1
        if old_status != new_status:
            flips.append(
                {
                    "turn": turn["turn"],
                    "old": old_status,
                    "new": new_status,
                    "notes": verdict["notes"],
                    "missing": verdict["missing"],
                }
            )
        new_turns.append(
            {
                **turn,
                "status": new_status,
                "missing": verdict["missing"],
                "notes": verdict["notes"],
            }
        )

    print(f"old PASS {report['passed']}/{len(report['turns'])}")
    new_passed = sum(1 for t in new_turns if t["status"] == "pass")
    print(f"new PASS {new_passed}/{len(new_turns)}")
    print("flips:")
    for flip in flips:
        print(
            f"  turn {flip['turn']}: {flip['old']} -> {flip['new']} "
            f"notes={flip['notes']} missing={flip['missing']}"
        )
    print("new failures:")
    for turn in new_turns:
        if turn["status"] != "pass":
            print(
                f"  turn {turn['turn']} [{turn['group']}] {turn['query'][:36]}"
                f" missing={turn['missing'][:4]} notes={turn['notes'][:4]}"
            )

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"report": report, "rejudged_turns": new_turns, "flips": flips}, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
