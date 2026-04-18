"""Aggregate all v3 enriched_v3.jsonl files into a single canonical-ready
stream, deduped by (canonical_name, institution), preferring records with
paper-driven / merged research_directions over official_only and higher
paper_count over lower.

Output: write merged records to --out (default
logs/data_agents/professor/enriched_v3_merged.jsonl). The existing backfill
script run_real_e2e_professor_backfill.py can consume this file via --source.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO_ROOT / "logs" / "data_agents"
DEFAULT_OUT = DEFAULT_ROOT / "professor" / "enriched_v3_merged.jsonl"

# Preference: higher == keep. (source_score, has_paper_count, paper_count, dir_count)
_SOURCE_SCORE = {"merged": 3, "paper_driven": 2, "official_only": 1, "": 0, None: 0}


def _score(record: dict) -> tuple[int, int, int, int]:
    src = record.get("research_directions_source")
    source_score = _SOURCE_SCORE.get(src, 0)
    paper_count = record.get("paper_count") or 0
    # Guard against implausibly inflated paper counts (e.g. 12322) — they
    # come from contaminated profiles where the pipeline found a same-name
    # different person. Prefer records in a plausible 0..2000 band.
    plausible = 1 if 0 <= paper_count <= 2000 else 0
    dir_count = len(record.get("research_directions") or [])
    return (source_score, plausible, paper_count, dir_count)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    best_per_key: dict[tuple[str, str], dict] = {}
    files_read = 0
    records_seen = 0
    records_structured = 0

    for fp in sorted(args.root.rglob("enriched_v3.jsonl")):
        files_read += 1
        for line in fp.open("r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records_seen += 1
            if record.get("extraction_status") != "structured":
                continue
            records_structured += 1
            name = (record.get("name") or "").strip()
            institution = (record.get("institution") or "").strip()
            if not name or not institution:
                continue
            key = (name, institution)
            existing = best_per_key.get(key)
            if existing is None or _score(record) > _score(existing):
                best_per_key[key] = record

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fout:
        for record in best_per_key.values():
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"files read            : {files_read}")
    print(f"records seen          : {records_seen}")
    print(f"records structured    : {records_structured}")
    print(f"unique profs written  : {len(best_per_key)}")
    print(f"output path           : {args.out}")

    source_counts = Counter(r.get("research_directions_source") or "(empty)"
                            for r in best_per_key.values())
    print("merged source distribution:")
    for src, n in source_counts.most_common():
        print(f"  {src}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
