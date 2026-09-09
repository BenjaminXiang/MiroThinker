#!/usr/bin/env python3
"""A4: real-traffic pack-hit evidence (read-only).

Question: what fraction of real logged queries mention an entity that the
serving pack (s12f) can answer about — and how much does run14 (47k docs)
add? Matching is deliberately simple: substring hit of a pack entity name /
alias / paper title / patent number inside the query text.

Outputs per-pack hit rates + a miss sample for manual review.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"
S12F = "/var/tmp/mirothinker-canonical-v2-s12f/serving-pack/lookup.sqlite3"
RUN14 = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"


def load_names(path: str) -> dict[str, list[str]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    names: dict[str, list[str]] = {"company": [], "professor": [], "paper": [], "patent": []}
    for (dj,) in con.execute("SELECT document_json FROM lookup_document"):
        d = json.loads(dj)
        lc = d["lookup_content"]
        c = json.loads(lc) if isinstance(lc, str) else lc
        dom = d.get("domain")
        if dom == "company":
            pool = [c.get("name"), c.get("normalized_name"), *(c.get("aliases") or [])]
            names["company"].extend(x for x in pool if x and len(x) >= 2)
        elif dom == "professor":
            pool = [c.get("name"), c.get("canonical_name_zh"), c.get("canonical_name_en")]
            names["professor"].extend(x for x in pool if x and len(x) >= 2)
        elif dom == "paper":
            for key in ("title", "title_zh"):
                t = c.get(key)
                if t and len(t) >= 10:
                    names["paper"].append(t)
        elif dom == "patent":
            pn = c.get("patent_number")
            if pn:
                names["patent"].append(pn)
            t = c.get("title")
            if t and len(t) >= 8:
                names["patent"].append(t)
    con.close()
    return {k: sorted(set(v), key=len, reverse=True) for k, v in names.items()}


def main() -> None:
    log = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
    queries = [r[0] for r in log.execute(
        "SELECT query FROM turns WHERE status != 'error'").fetchall()]
    log.close()
    queries = [q.strip() for q in queries if q and q.strip()]
    print(f"turns with query text: {len(queries)}")

    packs = {"s12f": load_names(S12F), "run14": load_names(RUN14)}
    for tag, names in packs.items():
        print(f"{tag} name pools: " + ", ".join(f"{k}={len(v)}" for k, v in names.items()))

    for tag, names in packs.items():
        hits: Counter = Counter()
        hit_queries: set[int] = set()
        for i, q in enumerate(queries):
            for dom, pool in names.items():
                if any(n in q for n in pool):
                    hits[dom] += 1
                    hit_queries.add(i)
        print(f"\n[{tag}] entity-mentioning queries: {len(hit_queries)}/{len(queries)} "
              f"= {len(hit_queries)/len(queries):.1%}; per-domain hits: {dict(hits)}")

    # queries hitting run14 but NOT s12f = what the data upgrade would add
    s12f_all = [n for pool in packs["s12f"].values() for n in pool]
    run14_all = [n for pool in packs["run14"].values() for n in pool]
    gained = []
    for q in queries:
        if any(n in q for n in run14_all) and not any(n in q for n in s12f_all):
            gained.append(q)
    print(f"\nqueries covered by run14 but NOT s12f: {len(gained)}")
    for q in gained[:15]:
        print(f"  - {q[:80]}")


if __name__ == "__main__":
    main()
