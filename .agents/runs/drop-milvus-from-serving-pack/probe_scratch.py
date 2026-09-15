"""Scratch probe: capture one turn's SSE and its public web items.

Writes the verbatim SSE stream and a small extracted summary so the web-lane
evidence (web_items before/after the topical floor) is reproducible from disk.

Usage:
  python probe_scratch.py --base-url http://127.0.0.1:18295 \
      --query "详细介绍一下 国先中心（深圳）" \
      --out .agents/runs/web-lane-topical-floor/scratch/user-case.json
"""

from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import sys
import urllib.request


def post_turn(base_url: str, query: str, timeout: int) -> tuple[str, dict[str, list]]:
    body = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    raw = b""
    with opener.open(request, timeout=timeout) as response:
        for chunk in response:
            raw += chunk
    text = raw.decode("utf-8", errors="replace")
    events: dict[str, list] = {}
    for block in re.split(r"\n\n+", text):
        name = None
        payload = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                payload = line[len("data:") :].strip()
        if name and payload is not None:
            try:
                events.setdefault(name, []).append(json.loads(payload))
            except json.JSONDecodeError:
                events.setdefault(name, []).append(payload)
    return text, events


def answer_text(events: dict[str, list]) -> str:
    chunks: list[str] = []
    for item in events.get("answer_delta", []) + events.get("token", []):
        if isinstance(item, dict):
            chunks.append(str(item.get("text") or item.get("delta") or ""))
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18295")
    parser.add_argument("--query", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    text, events = post_turn(args.base_url, args.query, args.timeout)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".sse.txt").write_text(text, encoding="utf-8")
    retrieval = [
        item for item in events.get("retrieval_done", []) if isinstance(item, dict)
    ]
    web_items = []
    for item in retrieval:
        web_items.extend(item.get("web_items") or [])
    summary = {
        "query": args.query,
        "base_url": args.base_url,
        "event_names": sorted({name for name in events}),
        "web_items": web_items,
        "answer": answer_text(events) or json.dumps(
            events.get("answer", events.get("final", [])), ensure_ascii=False
        )[:4000],
    }
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
