#!/usr/bin/env python3
"""泛化探针判定：性质检查（不依赖测试集 GT）。

P1 无捏造：答案覆盖句里点名的公司必须能在 run14 包中按名字查到。
P2 精度：覆盖句点名的公司，其包内文本必须命中该查询的类目词（否则 = 召回/披露噪声）。
P3 形态：公司域枚举轮必须带覆盖句；非枚举轮不得带。
P4 时延：逐轮 elapsed 汇总。

用法: python3 check_generalization.py --results generalization-live-r1.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3"
COVERAGE_RX = re.compile(r"此外，本次检索还召回以下相关本地企业：([^。]+)。")
NAME_SPLIT = re.compile(r"[、，,]\s*")

CATEGORY_TERMS = {
    "gen-drone": ("无人机", "飞行器", "航拍", "无人飞行"),
    "gen-storage": ("储能", "电池", "锂电", "电源"),
    "gen-lidar": ("激光雷达", "光电", "传感", "探测器"),
    "gen-medical": ("医疗", "器械", "临床", "诊断", "体外"),
    "gen-professor": ("机器人", "人工智能", "智能", "自动化"),
    "gen-paper": ("太阳能", "钙钛矿", "光伏"),
    "gen-patent": ("机器人", "专利"),
    "gen-cross": ("无人机", "飞行器", "影像", "云台"),
}


def pack_name_text(cur: sqlite3.Cursor, name: str) -> str | None:
    rows = cur.execute(
        "select document_json from lookup_document "
        "where projection_id='lookup:exact-lookup:company' and document_json like ? "
        "limit 5",
        (f'%"{name}"%',),
    ).fetchall()
    for (content,) in rows:
        d = json.loads(content)
        inner = d.get("lookup_content")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                continue
        if isinstance(inner, dict) and inner.get("name") == name:
            parts = [
                json.dumps(inner.get(k), ensure_ascii=False)
                for k in ("profile_summary", "technology_route_summary", "product_description", "industry")
            ]
            return " ".join(p for p in parts if p)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.results).read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{PACK}?mode=ro&immutable=1", uri=True)
    cur = con.cursor()

    report = []
    for sess in data:
        sid = sess["id"]
        terms = CATEGORY_TERMS.get(sid, ())
        for t in sess["turns"]:
            text = t.get("answer_text") or ""
            m = COVERAGE_RX.search(text)
            names = [n.strip() for n in NAME_SPLIT.split(m.group(1))] if m else []
            named_ok, named_missing, named_offcategory = [], [], []
            for n in names:
                if not n or n.endswith("家") or n.startswith("等"):
                    continue
                body = pack_name_text(cur, n)
                if body is None:
                    named_missing.append(n)
                elif terms and not any(k in body for k in terms):
                    named_offcategory.append(n)
                else:
                    named_ok.append(n)
            enum_like = any(k in t["query"] for k in ("哪些", "推荐", "厂商", "供应商"))
            report.append({
                "session": sid, "turn": t["turn"], "query": t["query"],
                "query_type": t.get("query_type"), "elapsed": t.get("elapsed"),
                "has_coverage": bool(m), "coverage_n": len(names),
                "pack_found": len(named_ok), "not_in_pack": named_missing,
                "off_category": named_offcategory,
                "enum_like": enum_like,
                "form_ok": (bool(m) == (enum_like and sess["domain"] in ("company", "mixed"))),
            })
    for r in report:
        flag = "OK " if r["form_ok"] else "FORM"
        print(f"{flag} {r['session']}#{r['turn']} cover={r['coverage_n']:2d} "
              f"pack={r['pack_found']:2d} off={len(r['off_category'])} "
              f"miss={len(r['not_in_pack'])} {r['elapsed']}s :: {r['query'][:22]}")
        if r["off_category"]:
            print(f"      OFF-CATEGORY: {r['off_category']}")
        if r["not_in_pack"]:
            print(f"      NOT-IN-PACK : {r['not_in_pack']}")
    out = Path(args.results).with_name(Path(args.results).stem + "-check.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"check -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
