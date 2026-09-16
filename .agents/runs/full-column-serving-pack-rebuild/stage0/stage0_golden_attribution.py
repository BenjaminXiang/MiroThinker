"""Stage 0 sensor #2: golden set + per-lane attribution against the live
canonical serving stack (127.0.0.1:18188, pack candidate-v2-20260819-r1).

Three hit-rate metrics from the goal function:
  点名命中 (exact)      — entity named by name/number/title: exact lane recalls
  语义命中 (vector)     — attribute query: local evidence cited
  关系命中 (relationship) — bound relations traversable: relationship lane fired

Failure classes:
  SCOPE_GAP          target not in pack AND all local lanes 0
  EXACT_MISS_MATCH_HIT  exact=0 but lexical/vector>0 (alias/matching gap)
  LOCAL_DROPPED      local lanes recalled but citations are all web
  RELATION_MISS      relation query but relationship lane absent or 0
  PASS               local recall AND locally-cited (or exact-lane hit for 点名)

Deterministic sampling (seed 42); one fresh session per query; results and the
golden set itself are persisted next to this script.

Read-only against the serving stack (no behavior change).
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

import psycopg

RUN_DIR = Path(__file__).resolve().parent
PACK_LOOKUP = "/var/tmp/mirothinker-data-v2/serving-pack/lookup.sqlite3"
PG_DSN = "postgresql://miroflow@127.0.0.1:55458/miroflow_light_lane_r1"
CHAT_STREAM = "http://127.0.0.1:18188/api/chat/stream"

random.seed(42)


def _norm(name: str | None) -> str:
    return (name or "").strip().casefold()


def load_pack_entities() -> dict:
    conn = sqlite3.connect(f"file:{PACK_LOOKUP}?mode=ro", uri=True)
    ent: dict[str, list[dict]] = {"company": [], "professor": [], "patent": [], "paper": []}
    for (dj,) in conn.execute("SELECT document_json FROM lookup_document"):
        d = json.loads(dj)
        c = json.loads(d["lookup_content"])
        dom = d["domain"]
        if dom == "company":
            ent[dom].append({"name": c.get("name") or "", "aliases": c.get("aliases") or []})
        elif dom == "professor":
            name = c.get("canonical_name_zh") or c.get("name") or ""
            if name:
                ent[dom].append({"name": name})
        elif dom == "patent":
            if c.get("patent_number"):
                ent[dom].append({"name": c["patent_number"], "title": c.get("title") or ""})
        elif dom == "paper":
            if c.get("title"):
                ent[dom].append({"name": c["title"]})
    conn.close()
    return ent


def build_golden_set() -> list[dict]:
    pack = load_pack_entities()
    pg = psycopg.connect(PG_DSN, connect_timeout=5)

    # dedupe pack names
    def _uniq(items: list[dict], key: str = "name") -> list[dict]:
        seen, out = set(), []
        for it in items:
            k = _norm(it.get(key))
            if k and k not in seen:
                seen.add(k)
                out.append(it)
        return out

    companies = _uniq(pack["company"])
    professors = _uniq(pack["professor"])
    patents = _uniq(pack["patent"])
    papers = _uniq(pack["paper"])

    en_style = [c for c in companies if re.search(r"\b(Ltd|Inc|Corp|LLC|Limited)\b", c["name"], re.I)]
    alias_filled = [c for c in companies if c["aliases"]]
    zh_named = [c for c in companies if not re.search(r"[A-Za-z]{3}", c["name"])][:2000]

    queries: list[dict] = []

    def add(kind: str, qtype: str, query: str, target: str, expect: str) -> None:
        queries.append(
            {"kind": kind, "qtype": qtype, "query": query, "target": target, "expect": expect}
        )

    # --- 点名 in-pack ---------------------------------------------------------
    for c in random.sample(zh_named, min(3, len(zh_named))):
        add("company", "点名", c["name"], c["name"], "exact")
    for c in en_style[:2]:
        add("company", "点名", c["name"], c["name"], "exact")
    if alias_filled:
        c = alias_filled[0]
        add("company", "点名", c["name"], c["name"], "exact")
    # known alias probe (Chinese -> English entity)
    add("company", "点名", "字节跳动", "ByteDance Ltd.", "exact")

    for p in random.sample(professors, min(5, len(professors))):
        add("professor", "点名", p["name"], p["name"], "exact")

    for p in random.sample(patents, min(3, len(patents))):
        add("patent", "点名", p["name"], p["name"], "exact")

    for p in random.sample(papers, min(4, len(papers))):
        add("paper", "点名", p["name"][:60], p["name"], "exact")

    # --- 点名 pool-only paper (scope gap probe) --------------------------------
    pack_paper_titles = {_norm(p["name"]) for p in papers}
    pool_only = [
        r[0]
        for r in pg.execute(
            "SELECT title FROM paper WHERE title IS NOT NULL ORDER BY paper_id"
        )
        if _norm(r[0]) not in pack_paper_titles
    ]
    for t in random.sample(pool_only, min(5, len(pool_only))):
        add("paper", "点名-池外", t[:60], t, "exact")

    # --- 属性 -------------------------------------------------------------------
    for c in random.sample(zh_named, min(2, len(zh_named))):
        add("company", "属性", f"{c['name']}是做什么的", c["name"], "semantic")
    profs_with_dir = pg.execute(
        "SELECT name FROM professor WHERE research_directions::text NOT IN ('null','[]','\"\"') ORDER BY professor_id"
    ).fetchall()
    for (n,) in random.sample(profs_with_dir, min(2, len(profs_with_dir))):
        add("professor", "属性", f"{n}的研究方向", n, "semantic")

    # --- 关系 -------------------------------------------------------------------
    bound_companies = pg.execute(
        """
        SELECT resolved_company, COUNT(*) AS n FROM applicant_binding
        WHERE status = 'resolved' AND resolved_company IS NOT NULL
        GROUP BY resolved_company ORDER BY n DESC LIMIT 40
        """
    ).fetchall()
    pack_company_names = {_norm(c["name"]) for c in companies}
    in_pack_bound = [r[0] for r in bound_companies if _norm(r[0]) in pack_company_names]
    for name in in_pack_bound[:3]:
        add("company", "关系", f"{name}有哪些专利", name, "relationship")

    linked_profs = pg.execute(
        """
        SELECT p.name, COUNT(*) AS n FROM prof_paper_link l
        JOIN professor p ON p.professor_id = l.professor_id
        GROUP BY p.name ORDER BY n DESC LIMIT 40
        """
    ).fetchall()
    pack_prof_names = {_norm(p["name"]) for p in professors}
    in_pack_linked = [r[0] for r in linked_profs if _norm(r[0]) in pack_prof_names]
    for name in in_pack_linked[:3]:
        add("professor", "关系", f"{name}的论文", name, "relationship")

    return queries


def probe(query: str, session_id: str) -> dict:
    body = json.dumps({"query": query, "session_id": session_id}).encode()
    req = urllib.request.Request(
        CHAT_STREAM,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    lanes: dict[str, int] = {}
    plan_lanes: list[str] = []
    citations: list[dict] = []
    answer_text = ""
    with urllib.request.urlopen(req, timeout=180) as resp:
        event = None
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: ") and event:
                payload = json.loads(line[6:])
                if event == "plan_done":
                    plan_lanes = payload.get("lanes", [])
                elif event == "retrieval_done":
                    for lane in payload.get("lanes", []):
                        lanes[lane["lane"]] = lane["candidates"]
                elif event == "answer":
                    citations = payload.get("citations", [])
                    answer_text = payload.get("answer_text", "")
                event = None
    return {
        "plan_lanes": plan_lanes,
        "lane_candidates": lanes,
        "citations": citations,
        "answer_text": answer_text,
    }


def classify(item: dict, result: dict, in_pack: bool) -> dict:
    lanes = result["lane_candidates"]
    local_lanes = {k: v for k, v in lanes.items() if k != "web"}
    exact = lanes.get("exact", 0)
    local_any = any(v > 0 for v in local_lanes.values())
    web = lanes.get("web", 0)
    non_web_cites = [c for c in result["citations"] if c.get("type") != "web"]
    target_in_answer = _norm(item["target"])[:20] in _norm(result["answer_text"])

    if item["expect"] == "relationship":
        rel_ok = lanes.get("relationship", 0) > 0
        if rel_ok and (non_web_cites or target_in_answer):
            verdict = "PASS"
        elif rel_ok:
            verdict = "RELATION_EMPTY"
        elif local_any or web:
            verdict = "RELATION_NOT_PLANNED"
        else:
            verdict = "RELATION_MISS"
    elif not in_pack and not local_any:
        verdict = "SCOPE_GAP"
    elif exact > 0 and (non_web_cites or target_in_answer):
        verdict = "PASS"
    elif exact > 0:
        verdict = "EXACT_HIT_NOT_CITED"
    elif local_any and not non_web_cites:
        verdict = "LOCAL_DROPPED"
    elif local_any:
        verdict = "PASS"
    else:
        verdict = "ALL_LOCAL_MISS"

    return {
        **item,
        "in_pack": in_pack,
        "plan_lanes": result["plan_lanes"],
        "lane_candidates": lanes,
        "citation_types": {
            t: len([c for c in result["citations"] if c.get("type") == t])
            for t in {c.get("type") for c in result["citations"]}
        },
        "target_in_answer": target_in_answer,
        "verdict": verdict,
        "answer_head": result["answer_text"][:100],
    }


def main() -> None:
    golden = build_golden_set()
    (RUN_DIR / "stage0-golden-set.json").write_text(
        json.dumps(golden, ensure_ascii=False, indent=2)
    )
    print(f"golden set: {len(golden)} queries")

    # pack membership for scope classification
    pack = load_pack_entities()
    pack_names = {
        "company": {_norm(c["name"]) for c in pack["company"]},
        "professor": {_norm(p["name"]) for p in pack["professor"]},
        "patent": {_norm(p["name"]) for p in pack["patent"]},
        "paper": {_norm(p["name"]) for p in pack["paper"]},
    }

    rows = []
    for i, item in enumerate(golden):
        session = f"stage0-{i}"
        t0 = time.time()
        try:
            result = probe(item["query"], session)
            err = None
        except Exception as exc:  # noqa: BLE001 — record probe failures verbatim
            result = {"plan_lanes": [], "lane_candidates": {}, "citations": [], "answer_text": ""}
            err = f"{type(exc).__name__}: {exc}"
        in_pack = _norm(item["target"]) in pack_names.get(item["kind"], set())
        row = classify(item, result, in_pack)
        row["error"] = err
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        print(
            f"[{i+1}/{len(golden)}] {item['qtype']}/{item['kind']} "
            f"'{item['query'][:24]}' -> {row['verdict']} "
            f"lanes={row['lane_candidates']} cites={row['citation_types']} ({row['seconds']}s)"
        )
        time.sleep(0.5)

    # aggregate
    summary: dict[str, dict] = {}
    for row in rows:
        bucket = f"{row['qtype']}/{row['kind']}"
        summary.setdefault(bucket, {"n": 0, "verdicts": {}})
        summary[bucket]["n"] += 1
        summary[bucket]["verdicts"][row["verdict"]] = (
            summary[bucket]["verdicts"].get(row["verdict"], 0) + 1
        )
    metrics = {
        "点名命中(exact>0 or PASS)": len(
            [r for r in rows if r["qtype"].startswith("点名") and r["lane_candidates"].get("exact", 0) > 0]
        ),
        "点名总数": len([r for r in rows if r["qtype"].startswith("点名")]),
        "属性本地引用": len(
            [r for r in rows if r["qtype"] == "属性" and (r["citation_types"].get("local") or sum(v for k, v in r["citation_types"].items() if k != "web"))]
        ),
        "关系车道触发": len(
            [r for r in rows if r["qtype"] == "关系" and r["lane_candidates"].get("relationship", 0) > 0]
        ),
    }
    out = {"summary": summary, "metrics": metrics, "rows": rows}
    (RUN_DIR / "stage0-attribution.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )
    print("\n=== summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
