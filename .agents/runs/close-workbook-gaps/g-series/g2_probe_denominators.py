#!/usr/bin/env python3
"""G2 probe: s12f denominators — DOI coverage, exact-name dup counts per domain."""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402

for db, label in ((L.S12F_DB, "s12f"), (L.RUN14_DB, "run14")):
    docs = L.load_lookup(db)
    print(f"== {label} ==")
    for dom in L.DOMAINS:
        rows = [r for r in docs if r["domain"] == dom]
        keys = Counter()
        for r in rows:
            c = r["content"]
            if dom == "company":
                k = (c.get("name") or "").strip()
            elif dom == "professor":
                k = L.professor_name_key(c.get("canonical_name_zh") or c.get("name"))
            elif dom == "paper":
                k = L.paper_title_key(c.get("title"))
            else:
                k = L.patent_number_key(c.get("patent_number"))
            if k:
                keys[k] += 1
        dups = {k: n for k, n in keys.items() if n > 1}
        extra = ""
        if dom == "paper":
            with_doi = sum(1 for r in rows if str(r["content"].get("doi") or "").strip())
            extra = f" doi_nonempty={with_doi}"
        print(
            f"  {dom:9s} docs={len(rows):6d} unique_keys={len(keys):6d}"
            f" dup_keys={len(dups):4d} dup_docs={sum(dups.values()):4d}{extra}"
        )
