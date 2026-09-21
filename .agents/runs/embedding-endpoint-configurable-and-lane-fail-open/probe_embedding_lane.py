"""Probe: does the embedding lane degrade instead of killing the turn?

Two phases, one scratch serving instance each (port 18285, /var/tmp/embedlane-285):

* phase 1 — ``CANONICAL_V2_EMBEDDING_BASE_URL=http://10.255.255.1:9/v1`` (a
  black-holed address): the ordinary question must still be answered and the
  retrieval trace must show the vector lane unavailable;
* phase 2 — no override (the real endpoint): the vector lane must serve evidence
  again.

Evidence is written verbatim: the raw SSE body, the JSON responses, the
retrieval-trace rows, per-turn wall clock, and the access-log rows.

Usage:
  python probe_embedding_lane.py --base-url http://127.0.0.1:18285 \
      --out .agents/runs/embedding-endpoint-configurable-and-lane-fail-open/probe
"""

from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request


def _post(base_url: str, path: str, body: dict, timeout: int) -> tuple[str, float]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        wall = time.monotonic() - started
        return f"HTTP {exc.code}\n{raw.decode('utf-8', 'replace')}", wall
    return raw.decode("utf-8", "replace"), time.monotonic() - started


def _sse_events(body: str) -> dict[str, list]:
    events: dict[str, list] = {}
    for block in re.split(r"\n\n+", body):
        name = None
        payload = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                payload = line[len("data:") :].strip()
        if name is None:
            continue
        if payload is None:
            events.setdefault(name, []).append(None)
            continue
        try:
            events.setdefault(name, []).append(json.loads(payload))
        except json.JSONDecodeError:
            events.setdefault(name, []).append(payload)
    return events


def _sse_answer(events: dict[str, list]) -> str:
    chunks: list[str] = []
    for item in events.get("answer_chunk", []):
        if isinstance(item, dict):
            chunks.append(str(item.get("text") or ""))
    return "".join(chunks)


def _lane_rows(response: dict) -> list[dict]:
    trace = ((response.get("structured_payload") or {}).get("canonical_v2")) or {}
    return [
        {
            "lane": row.get("lane"),
            "status": row.get("status"),
            "failure_kind": row.get("failure_kind"),
            "candidate_count": row.get("candidate_count"),
        }
        for row in trace.get("retrieval_traces", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--query", default="深圳有哪些芯片设计企业")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result: dict = {"phase": args.phase, "base_url": args.base_url, "turns": []}

    # Turn 1: the user-facing streaming entry.
    stream_body, stream_wall = _post(
        args.base_url, "/api/chat/stream", {"query": args.query}, args.timeout
    )
    (out / f"phase-{args.phase}-stream.txt").write_text(stream_body, encoding="utf-8")
    events = _sse_events(stream_body)
    answer = _sse_answer(events)
    result["turns"].append(
        {
            "entry": "/api/chat/stream",
            "wall_seconds": round(stream_wall, 2),
            "event_names": sorted(events),
            "error_events": events.get("error", []),
            "done_events": len(events.get("done", [])),
            "answer_chars": len(answer),
            "answer_head": answer[:160],
        }
    )

    # Turn 2: the synchronous entry, which carries the retrieval trace.
    sync_body, sync_wall = _post(
        args.base_url, "/api/chat", {"query": f"{args.query}（trace）"}, args.timeout
    )
    (out / f"phase-{args.phase}-sync.json").write_text(sync_body, encoding="utf-8")
    try:
        sync = json.loads(sync_body.split("\n", 1)[-1] if sync_body.startswith("HTTP") else sync_body)
    except json.JSONDecodeError:
        sync = {}
    result["turns"].append(
        {
            "entry": "/api/chat",
            "wall_seconds": round(sync_wall, 2),
            "answer_chars": len(str(sync.get("answer") or "")),
            "lane_rows": _lane_rows(sync),
        }
    )

    (out / f"phase-{args.phase}-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
