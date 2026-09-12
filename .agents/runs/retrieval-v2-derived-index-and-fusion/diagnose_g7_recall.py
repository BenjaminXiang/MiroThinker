#!/usr/bin/env python3
"""Is the G7 audit entity present in the local candidate pool at all?

Reads the serving turn-debug records for the enumeration query and reports,
per turn, whether the required entity (优必选) appears in `recalled_handles`
and in `committed_names`, plus its rank. Separates a *recall* defect from an
*ordering/selection* defect: a reranker can only fix the second.

    python3 diagnose_g7_recall.py [turn-debug-dir]
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time

TARGET = "优必选"
QUERY_MARKER = "具身智能"


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else (
        "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/turn-debug"
    )
    rows = []
    for path in glob.glob(os.path.join(root, "turn-debug-*.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            continue
        if QUERY_MARKER not in (record.get("query") or ""):
            continue
        handles = record.get("recalled_handles") or []
        names = [(handle.get("display_name") or "") for handle in handles]
        recalled_at = [i for i, name in enumerate(names) if TARGET in name]
        committed = record.get("committed_names") or []
        committed_at = [i for i, name in enumerate(committed) if TARGET in name]
        rows.append(
            (
                os.path.getmtime(path),
                len(handles),
                recalled_at,
                len(committed),
                committed_at,
                record.get("answer_chars"),
                record.get("turn_id") or "",
            )
        )

    rows.sort()
    print(f"query marker: {QUERY_MARKER!r}  target: {TARGET!r}  turns: {len(rows)}")
    print(f"{'when':8} {'recalled':>8} {TARGET + '@recall':>12} {'committed':>9} {TARGET + '@commit':>12} {'chars':>6}")
    recalled_hits = 0
    committed_hits = 0
    for when, recalled_n, recalled_at, committed_n, committed_at, chars, _turn in rows:
        recalled_hits += bool(recalled_at)
        committed_hits += bool(committed_at)
        stamp = time.strftime("%H:%M:%S", time.localtime(when))
        print(
            f"{stamp:8} {recalled_n:>8} {str(recalled_at):>12} {committed_n:>9} "
            f"{str(committed_at):>12} {str(chars):>6}"
        )
    if rows:
        print(
            f"\nrecall coverage {recalled_hits}/{len(rows)}; "
            f"commit coverage {committed_hits}/{len(rows)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
