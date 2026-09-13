#!/usr/bin/env python3
"""Session E2E probe: run one multi-turn session against 18188 and preserve
the answer text, the raw SSE, the timing marks and the per-turn turn-debug
artifacts (candidate-level evidence).

Usage:
  python3 probe_session_e2e.py --tag ubt-1 \
      --query "优必选科技怎么样" --query "该公司的专利有哪些"
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

TURN_DEBUG_DIR = Path(
    "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/turn-debug"
)


def stream_timed(base_url: str, jar: CookieJar, query: str, timeout: int = 240) -> tuple[dict, bytes]:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    t0 = time.time()
    ttft = None
    answer = ""
    events = {"answer_chunk": 0, "error": 0, "done": 0}
    errors: list[str] = []
    raw = bytearray()
    current = None
    try:
        with opener.open(req, timeout=timeout) as resp:
            for raw_line in resp:
                raw += raw_line
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                now = time.time()
                if line.startswith("event: "):
                    current = line[7:].strip()
                    if current == "done":
                        events["done"] += 1
                    elif current == "error":
                        events["error"] += 1
                elif line.startswith("data: ") and current in ("answer_chunk", "answer", "error"):
                    payload = line[6:]
                    if current == "answer_chunk":
                        events["answer_chunk"] += 1
                        if ttft is None:
                            ttft = round(now - t0, 2)
                        answer += payload
                    elif current == "answer":
                        try:
                            ans = json.loads(payload)
                            if isinstance(ans, dict) and ans.get("answer_text"):
                                answer = ans["answer_text"]
                        except json.JSONDecodeError:
                            pass
                    else:
                        errors.append(payload[:500])
    except Exception as exc:  # noqa: BLE001
        events["error"] += 1
        errors.append(f"{type(exc).__name__}: {exc}")
    total = round(time.time() - t0, 2)
    return {
        "query": query,
        "ttft": ttft,
        "total": total,
        "answer": answer,
        "events": events,
        "errors": errors,
        "raw_bytes": len(raw),
    }, bytes(raw)


def newest_turn_debug(after_ts: float) -> list[Path]:
    out = [p for p in TURN_DEBUG_DIR.glob("turn-debug-*.json") if p.stat().st_mtime >= after_ts - 1]
    return sorted(out, key=lambda p: p.stat().st_mtime)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:18188")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--query", action="append", required=True)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    run_dir = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parent

    jar = CookieJar()
    results = []
    for i, q in enumerate(args.query, 1):
        t_start = time.time()
        r, raw = stream_timed(args.base_url, jar, q)
        (run_dir / f"e2e-{args.tag}-t{i}.sse").write_bytes(raw)
        copied = []
        for p in newest_turn_debug(t_start):
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("query") != q:
                continue
            dest = run_dir / f"e2e-{args.tag}-t{i}-{p.name}"
            shutil.copy2(p, dest)
            copied.append(
                {
                    "src": p.name,
                    "dest": dest.name,
                    "answer_chars": data.get("answer_chars"),
                    "committed": len(data.get("committed_names") or []),
                    "recalled": len(data.get("recalled_handles") or []),
                }
            )
        r["turn_debug"] = copied
        results.append(r)
        print(
            f"[{args.tag}#{i}] ttft={r['ttft']} total={r['total']} "
            f"err={r['events']['error']} ans_len={len(r['answer'])} "
            f"debug={[c['src'] for c in copied]} :: {q[:30]}",
            flush=True,
        )
    (run_dir / f"e2e-{args.tag}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"-> e2e-{args.tag}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
