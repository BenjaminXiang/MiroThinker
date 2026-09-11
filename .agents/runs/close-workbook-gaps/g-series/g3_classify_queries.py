#!/usr/bin/env python3
"""G3 step 1: classify access-log turns into category/recommendation queries.

Deterministic rules (documented in g3-category-anchoring.md §1):
  family A: 有哪些 / 哪几家 / 哪些企业 / 有哪些公司 ...
  family B: 推荐 / 帮我找 / 给我找 / 有哪些值得关注 ...
  family C: 供应商 / 厂商 / 制造商 / 生产商 / 服务商 / 代理商 / 分销商
  family D: 做…的公司 / 做…的企业 / 生产…的厂家
  family E: 龙头 / 代表企业 / 头部企业 / 知名企业 / 相关企业

Read-only against the access log. Writes g3-category-queries.json.
"""
import json
import re
import sqlite3

ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"
OUT = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series/g3-category-queries.json"

FAMILIES = [
    ("A_有哪些", re.compile(r"有哪些|有哪些公司|哪几家公司|哪几家|哪家|哪些公司|哪些企业|有什么公司|有什么企业")),
    ("B_推荐", re.compile(r"推荐|值得关注|值得投|知名|头部|龙头|代表(企业|公司|性)|标杆")),
    ("C_供应商", re.compile(r"供应商|厂商|制造商|生产商|服务商|代理商|分销商|集成商|厂家|供应链")),
    ("D_做的公司", re.compile(r"做[^？。，,]{0,10}的(公司|企业|厂)|从事[^？。，,]{0,10}的(公司|企业)|生产[^？。，,]{0,8}的")),
    ("E_其他枚举", re.compile(r"还有哪些|都有哪些|列举|清单一?下|盘点|梳理")),
]


def classify(query: str):
    hits = [name for name, pat in FAMILIES if pat.search(query)]
    return hits


def main():
    con = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "SELECT turn_id, session_id, turn_count, query, query_type, status, started_at"
        " FROM turns ORDER BY started_at"
    )
    rows = cur.fetchall()
    con.close()

    cat_rows = []
    for turn_id, sid, tc, q, qt, st, ts in rows:
        q = (q or "").strip()
        hits = classify(q)
        if hits:
            cat_rows.append(
                {
                    "turn_id": turn_id,
                    "session_id": sid,
                    "turn_count": tc,
                    "query": q,
                    "query_type": qt,
                    "status": st,
                    "started_at": ts,
                    "families": hits,
                }
            )

    payload = {
        "access_log": ACCESS,
        "total_turns": len(rows),
        "category_turns": len(cat_rows),
        "distinct_category_queries": len({r["query"] for r in cat_rows}),
        "distinct_category_sessions": len({r["session_id"] for r in cat_rows}),
        "family_counts": {
            name: sum(1 for r in cat_rows if name in r["families"]) for name, _ in FAMILIES
        },
        "rows": cat_rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print("total_turns:", len(rows))
    print("category_turns:", len(cat_rows))
    print("distinct_category_queries:", payload["distinct_category_queries"])
    print("distinct_sessions:", payload["distinct_category_sessions"])
    print("family_counts:", payload["family_counts"])
    print()
    for r in cat_rows[:60]:
        print(f"[{','.join(r['families'])}] {r['query']}")
    print("...")
    for r in cat_rows[-40:]:
        print(f"[{','.join(r['families'])}] {r['query']}")


if __name__ == "__main__":
    main()
