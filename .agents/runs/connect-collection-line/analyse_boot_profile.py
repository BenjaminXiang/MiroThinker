"""Aggregate a py-spy speedscope profile: where did the boot spend its samples?

Usage: python3 analyse_boot_profile.py <speedscope.json>

Prints the top frames by self-samples with their share, and a coarse grouping by
the module the frame belongs to, so the silent stretches of the boot stop being
silent. Sample counts, not wall-clock, are the unit: py-spy samples at a fixed
rate, so share-of-samples == share-of-time.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

FRAME_KEYS = ("name", "file", "line")
GROUP_RULES = (
    ("读包/校验 (pack, hash, envelope)", ("canonical_v2/release", "serving_pack", "envelope", "seal", "manifest", "sha256", "hashlib")),
    ("向量快照 (npz / embedding)", ("embed", "npz", "numpy", "vector", ".npy")),
    ("索引装载 (lookup / sqlite)", ("sqlite", "lookup", "index_projection")),
    ("关系/身份投影", ("relationship", "identity", "projection")),
    ("检索栈构造 (retrieval/knowledge_read)", ("retrieval", "knowledge_read", "planner", "query_planner")),
    ("web/浏览器预热", ("chromium", "playwright", "web_search", "bocha", "serper")),
    ("应用装配 (imports, fastapi, uvicorn)", ("importlib", "<frozen importlib", "fastapi", "starlette", "uvicorn", "pydantic")),
)


def group_of(frame: dict) -> str:
    blob = f"{frame.get('name','')} {frame.get('file','')}".lower()
    for label, needles in GROUP_RULES:
        if any(n in blob for n in needles):
            return label
    return "其他"


def main() -> int:
    data = json.load(open(sys.argv[1]))
    profile = data["profiles"][0]
    frames = data["shared"]["frames"]
    self_samples: Counter[int] = Counter()
    for sample in profile["samples"]:
        if sample:
            self_samples[sample[-1]] += 1
    total = sum(self_samples.values()) or 1

    print(f"total samples: {total}  (rate {data.get('samplingRate', {}).get('hz', '?')} Hz)")
    print("\n=== by group ===")
    groups: Counter[str] = Counter()
    for index, count in self_samples.items():
        groups[group_of(frames[index])] += count
    for label, count in groups.most_common():
        print(f"  {count/total*100:5.1f}%  {count:6d}  {label}")

    print("\n=== top 25 self frames ===")
    for index, count in self_samples.most_common(25):
        frame = frames[index]
        name = frame.get("name", "?")
        where = frame.get("file") or ""
        line = frame.get("line")
        short = f"{where.split('/')[-1]}:{line}" if where else ""
        print(f"  {count/total*100:5.1f}%  {count:6d}  {name}  {short}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
