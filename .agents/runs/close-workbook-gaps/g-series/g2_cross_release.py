#!/usr/bin/env python3
"""G2 section 3: cross-release identity stability run14 vs s12f + patent applicant
binding integrity (applicants[].canonical_company_id resolving to company docs).

Read-only. Writes g-series/out/g2-cross-release.json.
Run:  python3 g2_cross_release.py [--run14 DB] [--s12f DB] [--outdir DIR]
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402

FP_FIELDS = [
    "name",
    "normalized_name",
    "industry",
    "industry_tags",
    "tech_tags",
    "geography",
    "registered_address",
    "website",
    "founded_at",
    "legal_representative",
    "profile_summary",
    "technology_route_summary",
    "product_description",
    "team_description",
    "quality_status",
    "aliases",
]

SAMPLE_KEYWORDS = [
    "优必选", "一博", "普渡", "嘉立创", "深南电路", "云迹", "九号", "越疆",
    "拓竹", "海柔", "速腾聚创", "逐际动力", "优地", "大疆", "迈瑞", "华大基因",
    "奥比中光", "众擎", "智平方", "元化智能",
]


def joined(value):
    if value is None:
        return ""
    if isinstance(value, list):
        if all(isinstance(v, dict) for v in value):
            return "|".join(sorted(L.name_of(v) for v in value if L.name_of(v)))
        return "|".join(L.name_of(v) for v in value if L.name_of(v))
    return L.name_of(value)


def fingerprint(c):
    payload = {f: joined(c.get(f)) for f in FP_FIELDS}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def index(rows, keyfn):
    out = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k:
            out[k].append(r)
    return out


def stability(left_rows, right_rows, keyfn):
    left = index(left_rows, keyfn)
    right = index(right_rows, keyfn)
    matched = sorted(set(left) & set(right))
    same = changed = ambiguous = 0
    changed_samples = []
    for k in matched:
        ls, rs = left[k], right[k]
        if len(ls) == 1 and len(rs) == 1:
            if ls[0]["cid"] == rs[0]["cid"]:
                same += 1
            else:
                changed += 1
                if len(changed_samples) < 15:
                    changed_samples.append(
                        {"key": k, "s12f": ls[0]["cid"], "run14": rs[0]["cid"]}
                    )
        else:
            ambiguous += 1
    pairs = same + changed
    return {
        "left_docs": len(left_rows),
        "right_docs": len(right_rows),
        "matched_keys": len(matched),
        "unambiguous_pairs": pairs,
        "same_id": same,
        "changed_id": changed,
        "changed_pct": round(100.0 * changed / pairs, 2) if pairs else None,
        "ambiguous_keys": ambiguous,
        "changed_samples": changed_samples,
    }


def company_bindings(patent_rows, company_ids):
    counts = Counter()
    names = {}
    for r in patent_rows:
        for a in r["content"].get("applicants") or []:
            if not isinstance(a, dict):
                continue
            cid = a.get("canonical_company_id")
            if cid:
                counts[cid] += 1
                names.setdefault(cid, a.get("company_name"))
    dangling = {i: n for i, n in counts.items() if i not in company_ids}
    return counts, names, dangling


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run14", default=L.RUN14_DB)
    ap.add_argument("--s12f", default=L.S12F_DB)
    ap.add_argument(
        "--outdir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"),
    )
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    run14 = L.load_lookup(args.run14)
    s12f = L.load_lookup(args.s12f)
    by = lambda rows, dom: [r for r in rows if r["domain"] == dom]  # noqa: E731

    out = {
        "run14_release": L.release_ids(args.run14).get("release_id"),
        "s12f_release": L.release_ids(args.s12f).get("release_id"),
        "counts": {
            "run14": {d: len(by(run14, d)) for d in L.DOMAINS},
            "s12f": {d: len(by(s12f, d)) for d in L.DOMAINS},
        },
    }

    # ------------------------------------------------- stability by domain
    comp14, comp12 = by(run14, "company"), by(s12f, "company")
    prof14, prof12 = by(run14, "professor"), by(s12f, "professor")
    pap14, pap12 = by(run14, "paper"), by(s12f, "paper")
    pat14, pat12 = by(run14, "patent"), by(s12f, "patent")

    out["stability"] = {
        "company_exact_name": stability(
            comp12, comp14, lambda r: (r["content"].get("name") or "").strip()
        ),
        "company_core_name": stability(
            comp12, comp14, lambda r: L.company_name_key(r["content"].get("name"), 2)
        ),
        "professor_name": stability(
            prof12, prof14,
            lambda r: L.professor_name_key(
                r["content"].get("canonical_name_zh") or r["content"].get("name")
            ),
        ),
        "professor_name_institution": stability(
            prof12, prof14,
            lambda r: L.professor_name_key(
                r["content"].get("canonical_name_zh") or r["content"].get("name")
            )
            + "|"
            + str(r["content"].get("institution") or ""),
        ),
        "paper_doi": stability(
            pap12, pap14,
            lambda r: str(r["content"].get("doi") or "").strip().lower(),
        ),
        "paper_title_norm": stability(
            pap12, pap14, lambda r: L.paper_title_key(r["content"].get("title"))
        ),
        "patent_number": stability(
            pat12, pat14, lambda r: L.patent_number_key(r["content"].get("patent_number"))
        ),
    }
    print("== id stability (s12f -> run14) ==")
    for k, v in out["stability"].items():
        print(
            f"  {k:28s} matched={v['matched_keys']:6d} pairs={v['unambiguous_pairs']:6d}"
            f" same={v['same_id']:6d} changed={v['changed_id']:6d}"
            f" changed%={v['changed_pct']} ambig={v['ambiguous_keys']}"
        )

    # ------------------------------------------- content change vs id change
    left = index(comp12, lambda r: (r["content"].get("name") or "").strip())
    right = index(comp14, lambda r: (r["content"].get("name") or "").strip())
    same_fp_changed_id = diff_fp_changed_id = same_fp_same_id = diff_fp_same_id = 0
    for k in sorted(set(left) & set(right)):
        ls, rs = left[k], right[k]
        if len(ls) != 1 or len(rs) != 1:
            continue
        fp_same = fingerprint(ls[0]["content"]) == fingerprint(rs[0]["content"])
        id_same = ls[0]["cid"] == rs[0]["cid"]
        if fp_same and id_same:
            same_fp_same_id += 1
        elif fp_same and not id_same:
            same_fp_changed_id += 1
        elif not fp_same and not id_same:
            diff_fp_changed_id += 1
        else:
            diff_fp_same_id += 1
    out["content_vs_id"] = {
        "same_fingerprint_same_id": same_fp_same_id,
        "same_fingerprint_changed_id": same_fp_changed_id,
        "diff_fingerprint_changed_id": diff_fp_changed_id,
        "diff_fingerprint_same_id": diff_fp_same_id,
    }
    print("\n== exact-name pairs: content fingerprint vs id ==")
    print(json.dumps(out["content_vs_id"], indent=2))

    # ------------------------------------------------- sample companies table
    def find(rows, kw):
        return [
            r for r in rows
            if kw in str(r["content"].get("name") or "")
        ]

    samples = []
    for kw in SAMPLE_KEYWORDS:
        lrows, rrows = find(comp12, kw), find(comp14, kw)
        samples.append(
            {
                "keyword": kw,
                "s12f": [
                    {"cid": r["cid"], "name": r["content"].get("name")} for r in lrows
                ],
                "run14": [
                    {"cid": r["cid"], "name": r["content"].get("name")} for r in rrows
                ],
            }
        )
    out["sample_companies"] = samples
    print("\n== sample companies ==")
    for s in samples:
        print(f"  [{s['keyword']}]")
        for side in ("s12f", "run14"):
            for r in s[side]:
                print(f"    {side:5s} {r['cid']} {r['name']}")

    # ------------------------------------------------- binding integrity
    comp_ids14 = {r["cid"] for r in comp14}
    comp_ids12 = {r["cid"] for r in comp12}
    bind14 = company_bindings(pat14, comp_ids14)
    bind12 = company_bindings(pat12, comp_ids12)
    out["bindings"] = {
        "run14": {
            "applicant_entries_with_company_id": sum(bind14[0].values()),
            "distinct_company_ids": len(bind14[0]),
            "dangling_ids": len(bind14[2]),
            "dangling_entries": sum(bind14[2].values()),
            "dangling_sample": list(bind14[2].items())[:10],
        },
        "s12f": {
            "applicant_entries_with_company_id": sum(bind12[0].values()),
            "distinct_company_ids": len(bind12[0]),
            "dangling_ids": len(bind12[2]),
            "dangling_entries": sum(bind12[2].values()),
            "dangling_sample": list(bind12[2].items())[:10],
        },
        "run14_top_bound": [
            {"cid": cid, "name": bind14[1].get(cid), "patents": n}
            for cid, n in bind14[0].most_common(15)
        ],
        "s12f_top_bound": [
            {"cid": cid, "name": bind12[1].get(cid), "patents": n}
            for cid, n in bind12[0].most_common(15)
        ],
    }
    print("\n== binding integrity ==")
    print(json.dumps(out["bindings"], ensure_ascii=False, indent=2))

    # anchor check: 优必选 / 普渡 by name sightings + id bindings
    anchors = {}
    for kw in ("优必选", "普渡"):
        for side, rows, comp_rows, bind in (
            ("run14", pat14, comp14, bind14),
            ("s12f", pat12, comp12, bind12),
        ):
            cids = {r["cid"] for r in comp_rows if kw in str(r["content"].get("name") or "")}
            by_id = {cid: bind[0].get(cid, 0) for cid in cids}
            by_name = sum(
                1 for r in rows
                for a in r["content"].get("applicants") or []
                if isinstance(a, dict) and kw in str(a.get("company_name") or "")
            )
            anchors.setdefault(kw, {})[side] = {
                "company_ids": sorted(cids),
                "bound_patents_by_id": by_id,
                "applicant_entries_by_name": by_name,
            }
    out["anchors"] = anchors
    print("\n== anchors (优必选/普渡) ==")
    print(json.dumps(anchors, ensure_ascii=False, indent=2))

    out_path = os.path.join(args.outdir, "g2-cross-release.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("\nwrote", out_path)


if __name__ == "__main__":
    main()
