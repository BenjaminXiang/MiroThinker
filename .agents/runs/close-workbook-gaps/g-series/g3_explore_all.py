#!/usr/bin/env python3
"""Exploratory: raw n-gram candidates over ALL access-log turns (no keep-filter).

Used to calibrate the deterministic filter that g3_terms.py applies.
"""
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series")
from g3_terms import build_strip_re, PUNCT, CAND_MIN, CAND_MAX, valid_candidate  # noqa: E402

ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"

STRIP_RE = build_strip_re()


def runs_of(q):
    for ch in PUNCT:
        q = q.replace(ch, "\x00")
    q = STRIP_RE.sub("\x00", q)
    return [p.strip() for p in q.split("\x00") if p.strip()]


def main():
    topn = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    con = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT query FROM turns")
    qc = Counter((q or "").strip() for q, in cur.fetchall())
    con.close()

    turns = Counter()
    whole_run = Counter()
    ex = defaultdict(list)
    for q, n in qc.items():
        rs = runs_of(q)
        runs = set(rs)
        seen = set()
        for run in rs:
            L = len(run)
            for i in range(L):
                for j in range(i + CAND_MIN, min(L, i + CAND_MAX) + 1):
                    s = run[i:j]
                    if not valid_candidate(s) or s in seen:
                        continue
                    seen.add(s)
                    turns[s] += n
                    if s in runs:
                        whole_run[s] += n
                    if len(ex[s]) < 3:
                        ex[s].append(q)
    print(f"distinct queries={len(qc)} candidates={len(turns)}")
    ranked = sorted(turns.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    for s, c in ranked[:topn]:
        flag = "RUN" if whole_run[s] else "   "
        print(f"{c:5d}t {whole_run[s]:5d}w {flag}  {s:16s}  {ex[s][0][:70]}")
    print()
    print("--- whole-run survivors only, top 60 ---")
    wr = [(s, c) for s, c in ranked if whole_run[s]]
    for s, c in wr[:60]:
        print(f"{c:5d}t  {s:16s}  {ex[s][0][:70]}")


if __name__ == "__main__":
    main()
