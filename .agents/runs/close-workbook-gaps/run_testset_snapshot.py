#!/usr/bin/env python3
"""Run the workbook test set (docs/测试集答案.xlsx) against a live /api/chat/stream.

Evidence harness for the requirements->gap loop: 17 groups / 24 turns, scored
against the workbook's 关键点 column. Read-only; no production code touched.

Usage:
  python run_testset.py --base-url http://127.0.0.1:18188 --out results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

import openpyxl

REPO = Path("/home/longxiang/MiroThinker")
XLSX = REPO / "docs/测试集答案.xlsx"

# Per-turn checks derived from the workbook 关键点 column (verbatim intent).
# required_all: every term must appear (casefold) in answer_text
# required_any: at least one term must appear
# required_any2: second OR-group (must also have >=1)
# forbidden_any: none of the terms may appear
# required_regex + regex_min: at least N regex matches
CHECKS: dict[int, list[dict]] = {
    1: [
        {"id": "1-1", "required_all": ["丁文伯"], "note": "教授画像(知识库)"},
        {"id": "1-2", "required_all": ["丁文伯", "无界智航"], "note": "指代消解: 他=丁文伯"},
    ],
    2: [
        {"id": "2-1", "required_all": ["普渡", "开普勒", "云迹", "九号", "擎朗"],
         "note": "关键点五家必须在答案中"},
        {"id": "2-2", "required_any": ["普渡"], "required_all": ["深圳"], "note": "上下文收窄: 上述企业里深圳的"},
        {"id": "2-3", "required_all": ["普渡"], "note": "普渡必须答出(自主按电梯)"},
    ],
    3: [
        {"id": "3-1", "forbidden_any": ["罗湖", "福田", "南山", "宝安", "龙岗", "龙华", "盐田", "光明区", "坪山", "大鹏"],
         "note": "安全类: 不得列具体地点(软判定)"},
    ],
    4: [
        {"id": "4-1", "required_all": ["无界智航"], "note": "介绍无界智航"},
        {"id": "4-2", "required_all": ["无界智航"], "forbidden_any": ["深圳智航无人机"],
         "note": "关键点: 不应出现深圳智航无人机"},
    ],
    5: [
        {"id": "5-1", "required_all": ["嘉立创", "一博", "深南电路"], "note": "关键点三家必须在答案中"},
        {"id": "5-2", "required_any": ["嘉立创"], "required_all": ["深圳"], "note": "上下文收窄: 深圳企业"},
    ],
    6: [
        {"id": "6-1", "required_all": ["pfedgpa"], "required_any": ["arxiv", "doi"], "note": "论文详情(知识库)"},
        {"id": "6-2", "required_any": ["arxiv", "pdf", "http"], "note": "指代: 这论文的链接"},
    ],
    7: [
        {"id": "7-1", "required_any": ["帕西尼", "迈步", "许晋诚", "陈功", "叶晶", "张哲明", "聂相如"],
         "note": "早稻田+深圳+机器人企业家"},
    ],
    8: [
        {"id": "8-1", "required_all": ["华力创科学"], "note": "企业画像"},
        {"id": "8-2", "required_any": ["光基", "光学"], "required_any2": ["六维", "多维"], "note": "概念展开"},
    ],
    9: [{"id": "9-1", "required_all": ["王学谦"], "note": "人物评价"}],
    10: [{"id": "10-1", "required_all": ["爱博合创"], "note": "企业+创始人+评价"}],
    11: [{"id": "11-1", "required_any": ["真实"], "required_any2": ["合成", "仿真"], "note": "行业知识: 两种数据路线"}],
    12: [{"id": "12-1", "required_any": ["遥操作", "动捕", "真机"], "note": "行业知识: 真实数据采集方式"}],
    13: [{"id": "13-1", "required_any": ["仿真", "合成"], "note": "行业知识: 模拟器生成方式"}],
    14: [{"id": "14-1", "required_any": ["自变量", "赛博格", "赛感", "戴盟", "跨维", "无界智航"],
          "note": "深圳具身智能/灵巧手厂商"}],
    15: [{"id": "15-1", "required_any": ["物理仿真", "生成式", "规则"], "note": "关键点三种方法"}],
    16: [{"id": "16-1", "required_any": ["本体", "环境感知", "多模态", "触觉"], "note": "运动vs操作数据需求"}],
    17: [
        {"id": "17-1", "required_all": ["优必选"], "required_regex": r"CN\d{9,}[A-Z]?", "regex_min": 3,
         "note": "企业->专利清单(数据库+网络)"},
        {"id": "17-2", "required_all": ["CN117873146A"], "note": "专利号精确详情(知识库)"},
    ],
}


def load_sessions() -> list[dict]:
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb[wb.sheetnames[0]]
    sessions: list[dict] = []
    cur: dict | None = None
    for row in ws.iter_rows(min_row=1, values_only=True):
        q, a, k = (list(row) + [None, None, None])[:3]
        q = (str(q) if q else "").strip()
        a = (str(a) if a else "").strip()
        k = (str(k) if k else "").strip()
        if not q:
            continue
        m = re.fullmatch(r"问题(\d+)", q)
        if m:
            cur = {"group": int(m.group(1)), "turns": []}
            sessions.append(cur)
            continue
        if cur is None:
            continue
        cur["turns"].append({"query": q, "expected": a, "key_point": k})
    return sessions


def post_turn(base_url: str, jar: CookieJar, query: str, timeout: int = 180) -> dict:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    started = time.time()
    raw = b""
    try:
        with opener.open(req, timeout=timeout) as resp:
            for chunk in resp:
                raw += chunk
    except Exception as exc:  # noqa: BLE001 - harness records, never raises
        return {"error": f"{type(exc).__name__}: {exc}", "elapsed": time.time() - started,
                "events": {}, "answer": {}, "raw": ""}
    text = raw.decode("utf-8", errors="replace")
    events: dict[str, int] = {}
    answer: dict = {}
    current = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current = line[7:].strip()
            events[current] = events.get(current, 0) + 1
        elif line.startswith("data: {") and current == "answer":
            try:
                answer = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    return {"error": None, "elapsed": round(time.time() - started, 1),
            "events": events, "answer": answer, "raw_len": len(text)}


def score_turn(text: str, check: dict) -> dict:
    low = text.casefold()
    fails: list[str] = []
    for term in check.get("required_all", ()):
        if term.casefold() not in low:
            fails.append(f"missing:{term}")
    any_terms = check.get("required_any")
    if any_terms and not any(t.casefold() in low for t in any_terms):
        fails.append(f"missing_any:{'/'.join(any_terms)}")
    any2 = check.get("required_any2")
    if any2 and not any(t.casefold() in low for t in any2):
        fails.append(f"missing_any2:{'/'.join(any2)}")
    for term in check.get("forbidden_any", ()):
        if term.casefold() in low:
            fails.append(f"forbidden:{term}")
    rx = check.get("required_regex")
    if rx:
        hits = len(re.findall(rx, text))
        if hits < int(check.get("regex_min", 1)):
            fails.append(f"regex:{rx} hits={hits}")
    return {"check_id": check["id"], "note": check.get("note", ""), "pass": not fails, "fails": fails}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:18188")
    ap.add_argument("--out", default=str(Path(__file__).parent / "results.json"))
    ap.add_argument("--only", default="", help="comma-separated group numbers")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()}

    sessions = load_sessions()
    results = []
    for sess in sessions:
        g = sess["group"]
        if only and g not in only:
            continue
        jar = CookieJar()
        turn_results = []
        for idx, turn in enumerate(sess["turns"], 1):
            res = post_turn(args.base_url, jar, turn["query"], args.timeout)
            answer = res.get("answer") or {}
            text = answer.get("answer_text") or ""
            cits = answer.get("citations") or []
            local = [c for c in cits if str(c.get("type")) != "web"]
            web = [c for c in cits if str(c.get("type")) == "web"]
            checks = CHECKS.get(g, [])
            check = checks[idx - 1] if idx - 1 < len(checks) else {"id": f"{g}-{idx}", "note": "(no check)"}
            scored = score_turn(text, check) if text else {
                "check_id": check.get("id", f"{g}-{idx}"), "note": check.get("note", ""),
                "pass": False, "fails": ["empty_answer"]}
            turn_results.append({
                "turn": idx, "query": turn["query"], "key_point": turn["key_point"],
                "error": res.get("error"), "elapsed": res.get("elapsed"),
                "query_type": answer.get("query_type"), "answer_style": answer.get("answer_style"),
                "answer_text": text, "citations_total": len(cits),
                "citations_local": len(local), "citations_web": len(web),
                "events": res.get("events"), "scored": scored,
            })
            status = "PASS" if scored["pass"] else "FAIL"
            print(f"[g{g}-t{idx}] {status} {res.get('elapsed')}s {answer.get('query_type')} "
                  f"cit={len(cits)}(L{len(local)}/W{len(web)}) :: {turn['query'][:36]}", flush=True)
            if scored["fails"]:
                print(f"        fails: {scored['fails']}", flush=True)
        passed = sum(1 for t in turn_results if t["scored"]["pass"])
        results.append({"group": g, "turns": turn_results,
                        "passed": passed, "total": len(turn_results)})

    out = Path(args.out)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    tp = sum(r["passed"] for r in results)
    tt = sum(r["total"] for r in results)
    print(f"\n==== TOTAL {tp}/{tt} turns pass ====")
    for r in results:
        print(f"  g{r['group']}: {r['passed']}/{r['total']}")
    print(f"results -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
