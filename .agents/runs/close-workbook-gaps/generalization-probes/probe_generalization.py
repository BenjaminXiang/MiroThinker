#!/usr/bin/env python3
"""泛化探针：测试集之外的查询行为验证（P1 一致性 / P2 覆盖句精度 / P3 形态 / P4 时延）。

用法:
  python3 probe_generalization.py --base-url http://127.0.0.1:18188 --out generalization-live-r1.json

设计：与 run_testset.py 同一 SSE 协议（复用其 post_turn）；探针查询**不在**
测试集（docs/测试集答案.xlsx）中，覆盖：其它类目枚举、其它收窄过滤、其它域
（教授/论文/专利）、跨域锚点。判定不依赖 GT——用性质检查（见 check_generalization.py）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.cookiejar import CookieJar
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "testset-baseline-20260909"))
from run_testset import post_turn  # noqa: E402

SESSIONS: list[dict] = [
    {"id": "gen-drone", "domain": "company", "turns": [
        "深圳有哪些做无人机整机的公司",
        "上述企业里有哪些成立于十年以上",
        "它们的产品主要用在哪些行业",
    ]},
    {"id": "gen-storage", "domain": "company", "turns": [
        "深圳有哪些做储能电池的公司",
        "上述企业里规模较大的有哪几家",
    ]},
    {"id": "gen-lidar", "domain": "company", "turns": [
        "深圳有哪些做激光雷达的公司",
        "上述企业里谁的产品用于自动驾驶",
    ]},
    {"id": "gen-medical", "domain": "company", "turns": [
        "深圳有哪些做医疗器械的公司",
    ]},
    {"id": "gen-professor", "domain": "professor", "turns": [
        "深圳有哪些研究机器人的教授",
        "他有哪些论文",
    ]},
    {"id": "gen-paper", "domain": "paper", "turns": [
        "有哪些关于钙钛矿太阳能电池的论文",
    ]},
    {"id": "gen-patent", "domain": "patent", "turns": [
        "深圳的机器人专利主要有哪些申请人",
    ]},
    {"id": "gen-cross", "domain": "mixed", "turns": [
        "大疆创新主要做什么",
        "它有哪些专利",
    ]},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:18188")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    results = []
    for sess in SESSIONS:
        if only and sess["id"] not in only:
            continue
        jar = CookieJar()
        turns = []
        for i, q in enumerate(sess["turns"], 1):
            t0 = time.time()
            res = post_turn(args.base_url, jar, q, args.timeout)
            answer = res.get("answer") or {}
            text = answer.get("answer_text") or ""
            cits = answer.get("citations") or []
            turns.append({
                "turn": i, "query": q, "elapsed": res.get("elapsed"),
                "error": res.get("error"),
                "query_type": answer.get("query_type"),
                "answer_style": answer.get("answer_style"),
                "answer_text": text,
                "citations_total": len(cits),
                "events": res.get("events"),
                "raw_len": res.get("raw_len"),
            })
            print(f"[{sess['id']}#{i}] {q[:28]} -> {answer.get('query_type')} "
                  f"({res.get('elapsed')}s, {len(text)} chars, {len(cits)} cits)")
        results.append({**{k: v for k, v in sess.items() if k != "turns"}, "turns": turns})

    out = Path(args.out)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"results -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
