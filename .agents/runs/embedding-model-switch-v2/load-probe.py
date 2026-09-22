#!/usr/bin/env python3
"""Concurrent chat probe: error rate and latency under parallel turns.

Built 2026-09-23 for the "no unverified items" pass before the fembed cutover:
the recall gate measures one turn at a time, so nothing had exercised the
serving stack with several sessions in flight (lane budgets, web cache,
breakers, the local vector lane).

  python3 load-probe.py <base-url> [workers] [label]

Exit 0 iff every turn returned an answer with at least one citation.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

QUERIES = [
    "优必选有哪些专利",
    "深圳有哪些做具身智能的公司",
    "字节跳动在深圳有哪些业务布局",
    "深南电路的主要客户有哪些",
    "深圳大学的丁文伯教授研究方向是什么",
    "普渡科技的送餐机器人产品",
    "深圳做医疗机器人的企业有哪些",
    "河套深港科技创新合作区深圳园区有哪些政策",
]


def one_turn(base_url: str, idx: int, query: str, label: str) -> dict:
    session = f"load:{label}-{idx}"
    body = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"miroflow_chat_session={session}",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    started = time.monotonic()
    status = 0
    raw = b""
    error = None
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            status = response.status
            for chunk in response:
                raw += chunk
    except Exception as exc:  # noqa: BLE001 - the probe reports, never raises
        error = f"{type(exc).__name__}: {exc}"
    seconds = round(time.monotonic() - started, 2)

    events: dict[str, int] = {}
    answer = None
    lanes = None
    for block in raw.decode("utf-8", errors="replace").split("\n\n"):
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if not name:
            continue
        events[name] = events.get(name, 0) + 1
        if data and name in ("answer", "retrieval_done"):
            try:
                payload = json.loads(data)
            except ValueError:
                continue
            if name == "answer":
                answer = payload
            else:
                lanes = payload.get("lanes")

    citations = len((answer or {}).get("citation_map") or {})
    vector = next(
        (l for l in (lanes or []) if isinstance(l, dict) and l.get("lane") == "vector"),
        None,
    )
    return {
        "idx": idx,
        "query": query,
        "status": status,
        "seconds": seconds,
        "error": error,
        "events": events,
        "answer_style": (answer or {}).get("answer_style"),
        "citations": citations,
        "lanes": [(l.get("lane"), l.get("status"), l.get("candidates")) for l in (lanes or [])],
        "vector_candidates": None if vector is None else vector.get("candidates"),
        "bytes": len(raw),
    }


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18296"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else len(QUERIES)
    label = sys.argv[3] if len(sys.argv) > 3 else time.strftime("%H%M%S")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(lambda pair: one_turn(base_url, pair[0], pair[1], label), enumerate(QUERIES))
        )
    wall = round(time.monotonic() - started, 2)

    ok = [r for r in results if r["status"] == 200 and r["citations"] > 0 and not r["error"]]
    print(f"load probe against {base_url} | label={label} workers={workers} wall={wall}s")
    for r in sorted(results, key=lambda r: r["idx"]):
        lanes = ",".join(f"{n}:{s}/{c}" for n, s, c in r["lanes"]) or "-"
        print(
            f"  [{r['idx']}] {r['seconds']:7.2f}s http={r['status']} cite={r['citations']:2d} "
            f"vec={r['vector_candidates']} style={r['answer_style']} lanes={lanes} "
            f"{'ERR ' + str(r['error']) if r['error'] else ''}"
        )
    seconds = [r["seconds"] for r in results]
    print(
        f"  ---- ok={len(ok)}/{len(results)} p50={statistics.median(seconds)}s "
        f"max={max(seconds)}s errors={sum(1 for r in results if r['error'])}"
    )
    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
