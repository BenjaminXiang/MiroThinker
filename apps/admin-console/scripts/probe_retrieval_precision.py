"""Probe retrieval precision + coverage against a gold-entity set.

For each gold query: POST /api/chat to the LIVE backend (:18188), read
matched_objects/matched_professors, check which gold entities appear
(retrieval recall) vs. which are in the DB at all (coverage).

Distinguishes Layer C (precision: in-DB-but-not-retrieved) from Layer E
(coverage: not-in-DB). NOT a synthesis measure — reads retrieval output only,
so it's independent of the dump-prompt problem.

Usage (backend must be UP on :18188):
  uv --directory apps/admin-console run --no-sync python scripts/probe_retrieval_precision.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import requests
import yaml

REPO = Path(__file__).resolve().parents[3]
GOLD = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "retrieval_gold.yaml"
BACKEND = os.environ.get("PROBE_BACKEND", "http://localhost:18188")
DSN = "postgresql://miroflow:miroflow@localhost:15432/miroflow_real"


def _in_db(name: str, domain: str) -> bool:
    # company has registered_name + aliases; professor has canonical_name + aliases.
    if domain == "company":
        sql = (
            "SELECT 1 FROM company "
            "WHERE canonical_name ILIKE %s OR registered_name ILIKE %s "
            "OR aliases::text ILIKE %s LIMIT 1"
        )
    else:
        sql = (
            "SELECT 1 FROM professor "
            "WHERE canonical_name ILIKE %s OR aliases::text ILIKE %s LIMIT 1"
        )
    params = (f"%{name}%", f"%{name}%", f"%{name}%") if domain == "company" else (f"%{name}%", f"%{name}%")
    with psycopg.connect(DSN) as c:
        return c.execute(sql, params).fetchone() is not None


def _retrieved_names(query: str, domain: str) -> list[str]:
    r = requests.post(f"{BACKEND}/api/chat", json={"query": query}, timeout=120)
    r.raise_for_status()
    j = r.json()
    sp = j.get("structured_payload") or {}
    key = "matched_objects" if domain == "company" else "matched_professors"
    rows = sp.get(key) or []
    out = []
    for o in rows:
        n = o.get("canonical_name") or o.get("title") or o.get("name") or ""
        if n:
            out.append(str(n))
    return out


def _found(gold: str, retrieved: list[str]) -> bool:
    return any(gold in n for n in retrieved)


def main() -> int:
    data = yaml.safe_load(GOLD.read_text())
    print(f"backend: {BACKEND}")
    print(f"{'qid':<28} {'recall':>7} {'cover':>7}  query")
    print("-" * 84)
    agg_recall, agg_cov, n = [], [], 0
    for q in data["queries"]:
        qid, query, dom = q["qid"], q["query"], q["domain"]
        gold = q.get("gold_entities") or []
        if not gold:
            continue
        n += 1
        try:
            retrieved = _retrieved_names(query, dom)
        except Exception as exc:
            print(f"{qid:<28}  ERROR: {exc}")
            continue
        recall = sum(1 for g in gold if _found(g, retrieved)) / len(gold)
        cov = sum(1 for g in gold if _in_db(g, dom)) / len(gold)
        agg_recall.append(recall)
        agg_cov.append(cov)
        print(f"{qid:<28} {recall*100:>6.0f}% {cov*100:>6.0f}%  {query[:36]}")
        c_gap = [g for g in gold if _in_db(g, dom) and not _found(g, retrieved)]
        e_gap = [g for g in gold if not _in_db(g, dom)]
        if c_gap:
            print(f"      [C precision, in-DB not retrieved]: {c_gap}")
        if e_gap:
            print(f"      [E coverage, not in DB]: {e_gap}")
    if agg_recall:
        print("-" * 84)
        print(
            f"aggregate: recall={sum(agg_recall)/len(agg_recall)*100:.0f}%  "
            f"coverage={sum(agg_cov)/len(agg_cov)*100:.0f}%  (n={n})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
