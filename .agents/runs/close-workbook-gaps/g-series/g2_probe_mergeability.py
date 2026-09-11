#!/usr/bin/env python3
"""G2 probe: for each company stem cluster, strong-evidence agreement check.

Strong evidence = registered_address + legal_representative (both fields are
populated for ~5.5k docs). Counts clusters where both disagree (=> likely
distinct legal entities sharing a brand) vs agree/unknown.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402


def joined(value):
    if value is None:
        return ""
    if isinstance(value, list):
        if all(isinstance(v, dict) for v in value):
            return "|".join(sorted(L.name_of(v) for v in value if L.name_of(v)))
        return "|".join(L.name_of(v) for v in value if L.name_of(v))
    return L.name_of(value)


docs = [r for r in L.load_lookup(L.RUN14_DB) if r["domain"] == "company"]
groups = defaultdict(list)
for r in docs:
    k = L.company_name_key(r["content"].get("name"), 3)
    if k:
        groups[k].append(r)

both_disagree = agree_or_unknown = both_disagree_industry = 0
detail = []
for k, members in sorted(groups.items()):
    if len(members) < 2:
        continue
    addr = [joined(m["content"].get("registered_address")) for m in members]
    legal = [joined(m["content"].get("legal_representative")) for m in members]
    ind = [joined(m["content"].get("industry")) for m in members]
    addr_ne = [v for v in addr if v]
    legal_ne = [v for v in legal if v]
    ind_ne = [v for v in ind if v]
    addr_conf = len(set(addr_ne)) >= 2
    legal_conf = len(set(legal_ne)) >= 2
    ind_conf = len(set(ind_ne)) >= 2
    if addr_conf and legal_conf:
        both_disagree += 1
        if ind_conf:
            both_disagree_industry += 1
    else:
        agree_or_unknown += 1
    detail.append(
        {
            "cluster": k,
            "size": len(members),
            "addr_conflict": addr_conf,
            "legal_conflict": legal_conf,
            "industry_conflict": ind_conf,
            "names": [m["content"].get("name") for m in members],
        }
    )

print(f"stem clusters total: {len(detail)}")
print(f"addr AND legal_rep both conflict (=> likely distinct legal entities): {both_disagree}")
print(f"  ... of those also industry conflict: {both_disagree_industry}")
print(f"addr/legal agree or unknown (=> merge candidate with strong evidence): {agree_or_unknown}")
print()
print("== clusters where addr+legal both disagree ==")
for d in detail:
    if d["addr_conflict"] and d["legal_conflict"]:
        print(f"- {d['cluster']} ({d['size']}): " + "; ".join(d["names"]))
