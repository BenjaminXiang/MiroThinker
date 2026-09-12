#!/usr/bin/env python3
"""TTFT / 阶段时延探针：逐轮测量 SSE 流的阶段时间戳。

指标定义：
  t_request     → 请求发出
  t_first_event → 首个 SSE 事件（连接/服务响应）
  t_plan_done   → planning 阶段结束
  t_retrieval   → retrieval 阶段结束
  t_ttft        → 第一个 answer_chunk（= TTFT，用户看到答案的第一个字）
  t_done        → done 事件（整轮总时延）

用法:
  python3 probe_latency.py --base-url http://127.0.0.1:18188 --out latency-r1.json [--only name1,name2]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

# 会话级多轮（收窄轮依赖首轮），耗时目标：慢例与快例对照
SESSIONS: list[dict] = [
    {"id": "lat-dji", "turns": ["大疆创新主要做什么"]},
    {"id": "lat-professor", "turns": ["深圳有哪些研究机器人的教授"]},
    {"id": "lat-lidar", "turns": ["深圳有哪些做激光雷达的公司"]},
    {"id": "lat-storage", "turns": ["深圳有哪些做储能电池的公司"]},
    {"id": "lat-g2", "turns": ["中国有哪些成熟的酒店送餐机器人供应商"]},
    {"id": "lat-pcb", "turns": ["我想找PCB打板， 有哪些推荐", "上述企业有哪些是深圳的企业"]},
]


def stream_timed(base_url: str, jar: CookieJar, query: str, timeout: int = 240) -> dict:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat/stream", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    t0 = time.time()
    marks: dict[str, float | None] = {
        "first_event": None, "plan_done": None, "retrieval_done": None,
        "ttft": None, "done": None, "error": None,
    }
    events = {"answer_chunk": 0, "error": 0}
    answer_text = ""
    current = None
    try:
        with opener.open(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                now = time.time()
                if marks["first_event"] is None:
                    marks["first_event"] = round(now - t0, 2)
                if line.startswith("event: "):
                    current = line[7:].strip()
                    if current == "plan_done" and marks["plan_done"] is None:
                        marks["plan_done"] = round(now - t0, 2)
                    elif current == "retrieval_done" and marks["retrieval_done"] is None:
                        marks["retrieval_done"] = round(now - t0, 2)
                    elif current == "done":
                        marks["done"] = round(now - t0, 2)
                    elif current == "error":
                        events["error"] += 1
                elif line.startswith("data: ") and current == "answer_chunk":
                    events["answer_chunk"] += 1
                    if marks["ttft"] is None:
                        marks["ttft"] = round(now - t0, 2)
                    chunk = line[6:]
                    if len(answer_text) < 200_000:
                        answer_text += chunk
                elif line.startswith("data: {") and current == "answer":
                    try:
                        ans = json.loads(line[6:])
                        answer_text = ans.get("answer_text") or answer_text
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:  # noqa: BLE001
        marks["error"] = f"{type(exc).__name__}: {exc}"
    total = round(time.time() - t0, 2)
    return {"marks": marks, "total": total, "events": events, "answer_len": len(answer_text)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:18188")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    results = []
    for sess in SESSIONS:
        if only and sess["id"] not in only:
            continue
        jar = CookieJar()
        for i, q in enumerate(sess["turns"], 1):
            r = stream_timed(args.base_url, jar, q)
            m = r["marks"]
            print(f"[{sess['id']}#{i}] ttft={m['ttft']}s total={r['total']}s "
                  f"plan_done={m['plan_done']} retrieval_done={m['retrieval_done']} "
                  f"err={m['error'] or r['events']['error']} :: {q[:24]}")
            results.append({"session": sess["id"], "turn": i, "query": q, **r})
    out = Path(args.out)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
