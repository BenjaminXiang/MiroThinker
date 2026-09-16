#!/usr/bin/env python3
"""D9: Professor homepage periodic crawl — seed-driven pipeline.

Reads professor_seeds.json, fetches each school's faculty roster page,
extracts professor entries (name + profile URL), and diffs against the
existing professor pool to identify new/changed professors.

Output: JSONL batches in s12e-professor-backfill format for incremental
build integration.

Usage:
    uv run --directory apps/miroflow-agent python \\
        .agents/runs/full-column-serving-pack-rebuild/d9/crawl_professors.py \\
        [--dry-run] [--school SUSTech]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

RUN_DIR = Path(__file__).resolve().parent
SEEDS_FILE = RUN_DIR / "professor_seeds.json"
PACK_LOOKUP = "/var/tmp/mirothinker-data-v2/serving-pack-old-run12/lookup.sqlite3"
OUTPUT_DIR = RUN_DIR / "batches"
NOW = datetime.now(timezone.utc)

USER_AGENT = "MiroThinkerBot/1.0 (academic-research; contact: xiangl3@mail.sustech.edu.cn)"
FETCH_DELAY = 2.0  # seconds between requests
TIMEOUT = 15


def fetch(url: str) -> str | None:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  fetch error {url}: {exc}", file=sys.stderr)
        return None


def load_existing_professors() -> set[str]:
    """Load professor names from the current pack's lookup."""
    conn = sqlite3.connect(f"file:{PACK_LOOKUP}?mode=ro", uri=True)
    names = set()
    for (dj,) in conn.execute(
        "SELECT document_json FROM lookup_document WHERE document_json LIKE '%\"domain\":\"professor\"%'"
    ):
        import json as _json
        d = _json.loads(dj)
        content = _json.loads(d.get("lookup_content", "{}"))
        name = content.get("canonical_name_zh") or content.get("name") or ""
        if name:
            names.add(name.strip())
    conn.close()
    return names


def extract_sustech_professors(html: str) -> list[dict]:
    """SUSTech unified faculty page: extract professor name + profile URL."""
    professors = []
    # SUSTech faculty pages use standard HTML with faculty cards
    # Pattern: links to /faculty/xxx with professor names
    for match in re.finditer(
        r'href="(/faculty/[^"]+)"[^>]*>([^<]{2,20})<', html
    ):
        url_path, name = match.group(1), match.group(2).strip()
        if name and len(name) >= 2:
            professors.append({
                "name": name,
                "profile_url": f"https://faculty.sustech.edu.cn{url_path}",
                "school": "南方科技大学",
            })
    return professors


def extract_generic_professors(html: str, school: str) -> list[dict]:
    """Generic fallback: extract Chinese names near teacher/faculty links."""
    professors = []
    for match in re.finditer(
        r'href="([^"]*(?:teacher|faculty|person|staff|szdw)[^"]*)"[^>]*>\s*([\u4e00-\u9fff]{2,4})\s*<',
        html,
        re.IGNORECASE,
    ):
        url, name = match.group(1), match.group(2).strip()
        if name:
            full_url = url if url.startswith("http") else f"https://example.com{url}"
            professors.append({"name": name, "profile_url": full_url, "school": school})
    return professors


ADAPTERS = {
    "sustech_unified": extract_sustech_professors,
}


def crawl_seed(seed: dict, existing: set[str], dry_run: bool) -> list[dict]:
    school = seed["school"]
    url = seed.get("seed_url")
    adapter_name = seed.get("adapter")
    if not url or not adapter_name:
        print(f"[SKIP] {school}: no URL or adapter")
        return []
    print(f"[CRAWL] {school}: {url}")
    html = fetch(url)
    if html is None:
        return []
    adapter = ADAPTERS.get(adapter_name)
    if adapter:
        professors = adapter(html)
    else:
        professors = extract_generic_professors(html, school)
    new = [p for p in professors if p["name"] not in existing]
    print(f"  found {len(professors)} professors, {len(new)} new")
    if not dry_run:
        time.sleep(FETCH_DELAY)
    return new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--school", help="only crawl this school")
    args = parser.parse_args()

    seeds = json.loads(SEEDS_FILE.read_text())
    if args.school:
        seeds = [s for s in seeds if args.school in s["school"]]
    if not seeds:
        print("no matching seeds", file=sys.stderr)
        return 1

    print("Loading existing professors from pack...")
    existing = load_existing_professors()
    print(f"  {len(existing)} existing professor names")

    all_new: list[dict] = []
    for seed in seeds:
        found = crawl_seed(seed, existing, args.dry_run)
        all_new.extend(found)

    print(f"\nTotal new professors: {len(all_new)}")
    if args.dry_run:
        print("[DRY RUN] no batch file written")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_file = OUTPUT_DIR / f"professor-crawl-{NOW.strftime('%Y%m%d')}.jsonl"
    with open(batch_file, "w") as f:
        for prof in all_new:
            f.write(json.dumps(prof, ensure_ascii=False) + "\n")
    print(f"Batch written: {batch_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
