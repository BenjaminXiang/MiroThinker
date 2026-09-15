#!/usr/bin/env python3
"""Session probe for serving-index-process-scope: drive named sessions against
a live canonical-v2 entry and record per-turn wall time + SSE answer text.

Usage:
  python probe_sessions.py --base-url http://127.0.0.1:18294 --out-dir <dir> \
      --label before
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

SESSIONS: list[tuple[str, list[str]]] = [
    ("S1_entity", ["字节跳动", "他们公司主要做什么"]),
    ("S2_entity", ["字节跳动"]),
    ("S3_category", ["深圳有哪些做具身智能的公司"]),
    ("S4_patent", ["优必选有哪些专利"]),
]


def post_turn(base_url: str, jar: CookieJar, query: str, timeout: int) -> dict:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    raw = b""
    with opener.open(req, timeout=timeout) as resp:
        for chunk in resp:
            raw += chunk
    text = raw.decode("utf-8", errors="replace")
    answer: dict = {}
    for line in text.splitlines():
        if line.startswith("data: {") and '"query_type"' in line:
            try:
                answer = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    return {"answer": answer, "raw": text}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18294")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", default="probe")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []
    for name, queries in SESSIONS:
        jar = CookieJar()
        for idx, query in enumerate(queries, start=1):
            started = time.time()
            result = post_turn(args.base_url, jar, query, args.timeout)
            elapsed = round(time.time() - started, 2)
            stem = f"{args.label}-{name}-t{idx}"
            (out_dir / f"{stem}.sse").write_text(result["raw"], encoding="utf-8")
            answer = result["answer"]
            row = {
                "session": name,
                "turn": idx,
                "query": query,
                "wall_seconds": elapsed,
                "query_type": answer.get("query_type"),
                "answer_text": answer.get("answer_text", ""),
                "citation_count": len(answer.get("citations") or []),
                "evidence_count": len(answer.get("evidence") or []),
            }
            summary.append(row)
            print(json.dumps({k: row[k] for k in ("session", "turn", "query", "wall_seconds", "query_type", "citation_count")}, ensure_ascii=False), flush=True)
    (out_dir / f"{args.label}-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
