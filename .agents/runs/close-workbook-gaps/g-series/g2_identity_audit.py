#!/usr/bin/env python3
"""G2 sections 1-2: identity fragmentation + cross-identity field conflicts (run14 pack).

Read-only. Writes machine-readable results to g-series/out/.
Run:  python3 g2_identity_audit.py [--run14 DB] [--outdir DIR]
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402

CONFLICT_FIELDS = [
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
    "registered_capital",
    "credit_code",
    "aliases",
]

COMPLETENESS_FIELDS = [
    "industry",
    "industry_tags",
    "tech_tags",
    "geography",
    "registered_address",
    "founded_at",
    "legal_representative",
    "website",
    "profile_summary",
    "technology_route_summary",
    "product_description",
    "team_description",
    "registered_capital",
    "credit_code",
    "key_personnel",
]


def joined(value, sort=True):
    if value is None:
        return ""
    if isinstance(value, list):
        if sort and all(isinstance(v, dict) for v in value):
            return "|".join(sorted(L.name_of(v) for v in value if L.name_of(v)))
        return "|".join(L.name_of(v) for v in value if L.name_of(v))
    return L.name_of(value)


def trunc(s, n=90):
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def stats_for(frag, hist, total_docs):
    return {
        "fragmented_entities": len(frag),
        "docs_in_fragmented": sum(len(v) for v in frag.values()),
        "size_hist": dict(sorted(hist.items())),
        "max_size": max(hist) if hist else 1,
        "total_docs": total_docs,
    }


def sample_clusters(frag, k=10, member_fn=None):
    ranked = sorted(frag.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = []
    for key, members in ranked[:k]:
        out.append(
            {
                "key": key,
                "size": len(members),
                "members": [member_fn(m) for m in members],
            }
        )
    return out


def member_brief(r):
    c = r["content"]
    return {
        "cid": r["cid"],
        "name": c.get("name") or c.get("canonical_name_zh") or c.get("title"),
        "family": L.assertion_family(c),
        "run_id": c.get("run_id"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run14", default=L.RUN14_DB)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    docs = L.load_lookup(args.run14)
    by_dom = defaultdict(list)
    for r in docs:
        by_dom[r["domain"]].append(r)
    counts = {d: len(by_dom[d]) for d in L.DOMAINS}
    print("release:", L.release_ids(args.run14).get("release_id"))
    print("counts:", counts)

    report = {"release": L.release_ids(args.run14).get("release_id"), "counts": counts}

    # ---------------------------------------------------------- section 1: fragmentation
    frag_report = {}

    comp = by_dom["company"]
    for tier, label in ((1, "exact"), (2, "core"), (3, "stem")):
        groups, frag, hist = L.group_stats(
            comp, lambda r, t=tier: L.company_name_key(r["content"].get("name"), t)
        )
        frag_report[f"company_{label}"] = stats_for(frag, hist, len(comp))
        if label == "stem":
            report["company_stem_groups_top"] = sample_clusters(frag, 25, member_brief)
            report["company_core_groups_top"] = sample_clusters(
                L.group_stats(
                    comp, lambda r: L.company_name_key(r["content"].get("name"), 2)
                )[1],
                15,
                member_brief,
            )
            # Pudu cluster trace
            pudu = {
                k: v
                for k, v in frag.items()
                if "普渡" in k or any("普渡" in str(m["content"].get("name")) for m in v)
            }
            report["company_pudu_clusters"] = sample_clusters(pudu, 5, member_brief)

    prof = by_dom["professor"]
    groups, frag, hist = L.group_stats(
        prof, lambda r: L.professor_name_key(
            r["content"].get("canonical_name_zh") or r["content"].get("name")
        )
    )
    frag_report["professor_name"] = stats_for(frag, hist, len(prof))
    report["professor_name_samples"] = sample_clusters(frag, 10, member_brief)
    groups, frag2, hist2 = L.group_stats(
        prof,
        lambda r: L.professor_name_key(
            r["content"].get("canonical_name_zh") or r["content"].get("name")
        )
        + "|"
        + str(r["content"].get("institution") or ""),
    )
    frag_report["professor_name_institution"] = stats_for(frag2, hist2, len(prof))

    pap = by_dom["paper"]
    groups, frag, hist = L.group_stats(pap, lambda r: L.paper_title_key(r["content"].get("title")))
    frag_report["paper_title_norm"] = stats_for(frag, hist, len(pap))
    report["paper_title_samples"] = sample_clusters(frag, 10, member_brief)
    groups, frag2, hist2 = L.group_stats(
        pap, lambda r: str(r["content"].get("doi") or "").strip().lower()
    )
    frag_report["paper_doi"] = stats_for(frag2, hist2, len(pap))
    if frag2:
        report["paper_doi_samples"] = sample_clusters(frag2, 5, member_brief)

    pat = by_dom["patent"]
    groups, frag, hist = L.group_stats(
        pat, lambda r: L.patent_number_key(r["content"].get("patent_number"))
    )
    frag_report["patent_number"] = stats_for(frag, hist, len(pat))
    report["patent_number_samples"] = sample_clusters(frag, 10, member_brief)

    report["fragmentation"] = frag_report
    print("\n== fragmentation ==")
    for k, v in frag_report.items():
        print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")

    # ---------------------------------------------------------- section 2: conflicts
    groups, stem_frag, _ = L.group_stats(
        comp, lambda r: L.company_name_key(r["content"].get("name"), 3)
    )
    core_groups, core_frag, _ = L.group_stats(
        comp, lambda r: L.company_name_key(r["content"].get("name"), 2)
    )

    def compute_conflicts(frag):
        field_stats = {
            f: {"conflict": 0, "coverage_gap": 0, "no_conflict": 0}
            for f in CONFLICT_FIELDS
        }
        field_examples = defaultdict(list)
        cluster_rows = []
        for key, members in sorted(frag.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            n_conf = 0
            for f in CONFLICT_FIELDS:
                vals = [joined(m["content"].get(f)) for m in members]
                nonempty = [v for v in vals if v]
                if len(set(nonempty)) >= 2:
                    field_stats[f]["conflict"] += 1
                    if len(field_examples[f]) < 5:
                        uniq = []
                        for v in nonempty:
                            if v not in uniq:
                                uniq.append(v)
                        field_examples[f].append(
                            {"cluster": key, "values": [trunc(v) for v in uniq[:4]]}
                        )
                    n_conf += 1
                elif nonempty:
                    field_stats[f]["coverage_gap"] += 1
                else:
                    field_stats[f]["no_conflict"] += 1
            cluster_rows.append(
                {
                    "cluster": key,
                    "size": len(members),
                    "conflicting_fields": n_conf,
                    "members": [
                        {"name": m["content"].get("name"), "cid": m["cid"],
                         "family": L.assertion_family(m["content"])}
                        for m in members
                    ],
                }
            )
        return field_stats, dict(field_examples), cluster_rows

    stem_stats, stem_examples, stem_rows = compute_conflicts(stem_frag)
    core_stats, core_examples, core_rows = compute_conflicts(core_frag)
    stem_examples = {k: v for k, v in stem_examples.items() if v}
    core_examples = {k: v for k, v in core_examples.items() if v}

    placeholder_docs = Counter()
    for m in comp:
        c = m["content"]
        fam = L.assertion_family(c)
        fam = "COMP-legacy" if fam.startswith("COMP-") else fam
        for f in ("profile_summary", "technology_route_summary", "product_description"):
            if L.is_placeholder(c.get(f)):
                placeholder_docs[(f, fam)] += 1

    report["conflicts"] = {
        "stem": {
            "field_stats": stem_stats,
            "field_examples": stem_examples,
            "clusters_all": sorted(
                stem_rows,
                key=lambda x: (-x["conflicting_fields"], -x["size"], x["cluster"]),
            ),
        },
        "core": {
            "field_stats": core_stats,
            "field_examples": core_examples,
            "clusters_all": core_rows,
        },
        "placeholder_docs_by_field_family": {
            f"{f}|{fam}": n for (f, fam), n in sorted(placeholder_docs.items())
        },
    }
    for scope, stats in (("stem", stem_stats), ("core", core_stats)):
        print(f"\n== company {scope}-cluster conflicts (clusters with >=2 distinct values) ==")
        for f in CONFLICT_FIELDS:
            s = stats[f]
            print(
                f"  {f:28s} conflict={s['conflict']:4d} coverage_gap={s['coverage_gap']:4d}"
                f" no_conflict={s['no_conflict']:4d}"
            )

    # ---------------------------------------------------------- provenance / completeness
    fam_counts = Counter()
    fam_completeness = defaultdict(list)
    fam_placeholder = Counter()
    run_counts = Counter()
    field_nonempty = Counter()
    COVERAGE_FIELDS = [
        "normalized_name", "industry", "industry_tags", "tech_tags", "geography",
        "registered_address", "website", "founded_at", "legal_representative",
        "profile_summary", "technology_route_summary", "product_description",
        "team_description", "registered_capital", "credit_code", "aliases",
        "key_personnel",
    ]
    for m in comp:
        c = m["content"]
        fam_raw = L.assertion_family(c)
        fam = "COMP-legacy" if fam_raw.startswith("COMP-") else fam_raw
        fam_counts[fam] += 1
        run_counts[c.get("run_id")] += 1
        score = sum(
            1
            for f in COMPLETENESS_FIELDS
            if joined(c.get(f))
        )
        fam_completeness[fam].append(score)
        if any(L.is_placeholder(c.get(f)) for f in ("profile_summary", "technology_route_summary")):
            fam_placeholder[fam] += 1
        for f in COVERAGE_FIELDS:
            v = joined(c.get(f))
            if v and not L.is_placeholder(v):
                field_nonempty[f] += 1

    report["provenance"] = {
        "families": dict(fam_counts.most_common()),
        "run_ids": dict(run_counts.most_common()),
        "completeness_mean_by_family": {
            k: round(statistics.mean(v), 2)
            for k, v in sorted(fam_completeness.items())
        },
        "completeness_median_by_family": {
            k: statistics.median(v) for k, v in sorted(fam_completeness.items())
        },
        "completeness_max_by_family": {
            k: max(v) for k, v in sorted(fam_completeness.items())
        },
        "placeholder_docs_by_family": dict(fam_placeholder.most_common()),
        "field_nonempty_counts": dict(field_nonempty.most_common()),
    }
    print("\n== company provenance ==")
    print(json.dumps(report["provenance"], ensure_ascii=False, indent=2))

    # ---------------------------------------------------------- Pudu full sample
    pudu_docs = [
        m
        for m in comp
        if "普渡" in str(m["content"].get("name") or "")
        and L.company_name_key(m["content"].get("name"), 3) == "普渡"
    ]
    pudu_dump = []
    for m in pudu_docs:
        c = m["content"]
        pudu_dump.append(
            {
                "cid": m["cid"],
                "family": L.assertion_family(c),
                "run_id": c.get("run_id"),
                "last_updated": c.get("last_updated"),
                "name": c.get("name"),
                "normalized_name": c.get("normalized_name"),
                "industry": joined(c.get("industry")),
                "industry_tags": joined(c.get("industry_tags")),
                "tech_tags": joined(c.get("tech_tags")),
                "geography": joined(c.get("geography")),
                "registered_address": c.get("registered_address"),
                "founded_at": c.get("founded_at"),
                "legal_representative": joined(c.get("legal_representative")),
                "website": c.get("website"),
                "profile_summary": trunc(c.get("profile_summary") or "", 200),
                "technology_route_summary": trunc(c.get("technology_route_summary") or "", 200),
                "product_description": trunc(c.get("product_description") or "", 200),
                "quality_status": c.get("quality_status"),
            }
        )
    report["pudu_full_sample"] = pudu_dump
    print("\n== Pudu docs in audit scope ==")
    for d in pudu_dump:
        print(f"  {d['cid']} | {d['name']} | {d['family']} | industry={d['industry']}")

    out_path = os.path.join(args.outdir, "g2-run14-identity-audit.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("\nwrote", out_path)


if __name__ == "__main__":
    main()
