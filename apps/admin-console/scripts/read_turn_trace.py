#!/usr/bin/env python3
"""Read Canonical V2 turn-trace journals (task 1.1.4).

Line-streaming CLI over the append-only JSONL day files written by
backend.services.canonical_v2_turn_trace.TurnTraceJournalStore.

Usage:
  uv run python scripts/read_turn_trace.py [--date YYYY-MM-DD] [--session ID]
      [--degradation TOKEN] [--status STATUS] [--dir PATH] [--expand TRACE_ID]

Defaults: --dir from TURN_TRACE_DIR else var/turn-trace; --date = today (UTC).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date as date_type, datetime, timedelta
from pathlib import Path
import sys


def _default_root() -> Path:
    env_dir = os.getenv("TURN_TRACE_DIR", "").strip()
    return Path(env_dir) if env_dir else Path("var") / "turn-trace"


def _iter_day_files(root: Path, day: str | None) -> list[Path]:
    if day is not None:
        candidate = root / f"{day}.jsonl"
        return [candidate] if candidate.is_file() else []
    return sorted(
        entry
        for entry in root.iterdir()
        if entry.is_file() and entry.name.endswith(".jsonl")
    )


def _matches(entry: dict, session: str | None, degradation: str | None,
             status: str | None) -> bool:
    if session and entry.get("session_id") != session:
        return False
    if degradation and entry.get("degradation") != degradation:
        return False
    if status and entry.get("status") != status:
        return False
    return True


def _summary_line(entry: dict) -> str:
    lanes = " ".join(
        f"{name}:{counts.get('in', 0)}/{counts.get('retained', 0)}"
        for name, counts in (entry.get("lanes") or {}).items()
    )
    anchor = (entry.get("session_snapshot") or {}).get("active_anchor_name")
    subject = entry.get("answer_subject") or anchor or "-"
    web = len(entry.get("web_outcomes") or [])
    drops = entry.get("gate_drops") or {}
    drop_text = " ".join(f"{gate}:-{count}" for gate, count in drops.items())
    parts = [
        f"[{entry.get('ts_start', '?')[:19]}]",
        f"{entry.get('session_id', '?')}#{entry.get('turn_ordinal', '?')}",
        f"status={entry.get('status', '?')}",
        f"degradation={entry.get('degradation', '?')}",
        f"subject={subject}",
    ]
    if lanes:
        parts.append(f"lanes({lanes})")
    if web:
        parts.append(f"web_outcomes={web}")
    if drop_text:
        parts.append(f"drops({drop_text})")
    parts.append(entry.get("trace_id", ""))
    return "  ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="UTC day to read (default: today)")
    parser.add_argument("--session", help="filter by session id")
    parser.add_argument("--degradation", help="filter by degradation token")
    parser.add_argument("--status", help="filter by turn status")
    parser.add_argument("--dir", type=Path, default=None,
                        help="journal root (default TURN_TRACE_DIR or var/turn-trace)")
    parser.add_argument("--expand", metavar="TRACE_ID",
                        help="print the full record for one trace id")
    parser.add_argument("--all", action="store_true",
                        help="scan every day file instead of one day")
    args = parser.parse_args(argv)

    root = args.dir if args.dir is not None else _default_root()
    if args.all:
        files = _iter_day_files(root, None)
    else:
        day = args.date or datetime.now(UTC).date().isoformat()
        files = _iter_day_files(root, day)

    if not files:
        print(f"no trace files under {root}", file=sys.stderr)
        return 1

    matched = 0
    for file in files:
        with file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    print(f"skip malformed line in {file.name}", file=sys.stderr)
                    continue
                if args.expand is not None:
                    if entry.get("trace_id") == args.expand:
                        print(json.dumps(entry, ensure_ascii=False, indent=2))
                        return 0
                    continue
                if _matches(entry, args.session, args.degradation, args.status):
                    print(_summary_line(entry))
                    matched += 1
    if args.expand is not None:
        print(f"trace id not found: {args.expand}", file=sys.stderr)
        return 1
    if matched == 0:
        print("no matching turns", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
