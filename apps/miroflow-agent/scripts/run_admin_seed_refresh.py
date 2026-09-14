#!/usr/bin/env python3
"""Run one admin-triggered professor-seed refresh.

Spawned by the shared job gate as ``professor-seed-refresh`` / ``professor-seed-refresh-sample``.
It only wires arguments to the existing in-process runner (:func:`run_single_seed`) and reports the
declared summary line — the seeding semantics stay where they were.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.seed_runner import run_single_seed  # noqa: E402

TRIGGER_MODES = ("preview", "sample", "full")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-id", required=True, type=int, dest="seed_id")
    parser.add_argument("--trigger-mode", required=True, choices=list(TRIGGER_MODES))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--operator", default="anonymous")
    args = parser.parse_args(argv)
    if args.trigger_mode == "sample" and args.limit is None:
        parser.error("--limit is required for sample mode")

    result = run_single_seed(
        args.seed_id,
        trigger_mode=args.trigger_mode,
        limit=args.limit,
    )
    status = getattr(result, "status", None) or "unknown"
    print(
        json.dumps(
            {
                "job_summary": {
                    "items_processed": 1,
                    "items_failed": 0 if status == "success" else 1,
                    "seed_id": args.seed_id,
                    "trigger_mode": args.trigger_mode,
                    "limit": args.limit,
                    "operator": args.operator,
                    "seed_status": str(status),
                }
            },
            ensure_ascii=False,
        )
    )
    return 0 if status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
