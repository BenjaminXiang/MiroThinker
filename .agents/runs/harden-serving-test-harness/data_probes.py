#!/usr/bin/env python3
"""Data-foundation probes for the 16-gap registry (GAP-13/14/15/16).

Read-only assertions against the serving pack and the run14 pack lookup
SQLite files. Each probe prints PASS/RED with the measured value.

Thresholds come from openspec/changes/close-workbook-gaps/design.md (C1/C2):
  professor profile_summary boilerplate < 10%
  professor paper_summary placeholder   = 0%
  professor title placeholder           < 5%
  professor email placeholder           = 0%
  professor research_directions fill    >= 80%
  company aliases coverage              >= 30%
  serving pack doc counts               == run14 counts (47,071 total)
  paper professor_ids link rate         >= 10% (provisional, GAP-16)
  patent applicant-id binding rate      >= 60% of patents (serving pack)
"""

from __future__ import annotations

import json
import sqlite3
import sys

S12F = "/var/tmp/mirothinker-canonical-v2-s12f/serving-pack/lookup.sqlite3"
RUN14 = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"

BOILER_MARKERS = [
    "在深圳科创领域有持续贡献",
    "研究成果具有重要学术价值",
    "No dedicated summary",
    "Not supplied",
]
PLACEHOLDER = ("Not supplied by the historical source.", "No dedicated summary")


def docs(con, domain):
    for (dj,) in con.execute(
        "SELECT document_json FROM lookup_document WHERE projection_id=?",
        (f"lookup:exact-lookup:{domain}",),
    ):
        d = json.loads(dj)
        lc = d["lookup_content"]
        yield json.loads(lc) if isinstance(lc, str) else lc


def counts(con) -> dict[str, int]:
    return {
        r[0].split(":")[-1]: r[1]
        for r in con.execute(
            "SELECT projection_id, COUNT(*) FROM lookup_document GROUP BY projection_id"
        )
    }


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    s12f = sqlite3.connect(f"file:{S12F}?mode=ro", uri=True)
    run14 = sqlite3.connect(f"file:{RUN14}?mode=ro", uri=True)

    c12, c14 = counts(s12f), counts(run14)
    t12, t14 = sum(c12.values()), sum(c14.values())
    results.append((
        "GAP-15 serving pack == run14 (47,071 docs)",
        t12 == t14,
        f"serving={t12} {c12} vs run14={t14} {c14}",
    ))

    n = boiler = paper_ph = title_ph = email_ph = rd_fill = 0
    for c in docs(run14, "professor"):
        n += 1
        s = c.get("profile_summary") or ""
        if any(m in s for m in BOILER_MARKERS):
            boiler += 1
        if (c.get("paper_summary") or "").startswith(PLACEHOLDER):
            paper_ph += 1
        if (c.get("title") or "").startswith(PLACEHOLDER):
            title_ph += 1
        if (c.get("email") or "").startswith(PLACEHOLDER):
            email_ph += 1
        if c.get("research_directions"):
            rd_fill += 1
    results += [
        ("GAP-13a profile_summary boilerplate < 10%", boiler / n < 0.10,
         f"{boiler}/{n} = {boiler/n:.1%}"),
        ("GAP-13b paper_summary placeholder == 0%", paper_ph == 0,
         f"{paper_ph}/{n} = {paper_ph/n:.1%}"),
        ("GAP-13c title placeholder < 5%", title_ph / n < 0.05,
         f"{title_ph}/{n} = {title_ph/n:.1%}"),
        ("GAP-13d email placeholder == 0%", email_ph == 0,
         f"{email_ph}/{n} = {email_ph/n:.1%}"),
        ("GAP-13e research_directions fill >= 80%", rd_fill / n >= 0.80,
         f"{rd_fill}/{n} = {rd_fill/n:.1%}"),
    ]

    n = ali = 0
    for c in docs(run14, "company"):
        n += 1
        if c.get("aliases"):
            ali += 1
    results.append(("GAP-14 company aliases coverage >= 30%", ali / n >= 0.30,
                    f"{ali}/{n} = {ali/n:.1%}"))

    n = linked = 0
    for c in docs(run14, "paper"):
        n += 1
        if c.get("professor_ids"):
            linked += 1
    results.append(("GAP-16 paper professor_ids link rate >= 10% (provisional)",
                    linked / n >= 0.10, f"{linked}/{n} = {linked/n:.1%}"))

    n = bound = 0
    for c in docs(s12f, "patent"):
        n += 1
        apps = c.get("applicants") or []
        if any(isinstance(a, dict) and a.get("canonical_company_id") for a in apps):
            bound += 1
    results.append(("GAP-01-data serving patents with applicant-id >= 60%",
                    bound / n >= 0.60, f"{bound}/{n} = {bound/n:.1%} (bindings exist; read path is B1)"))

    s12f.close()
    run14.close()

    red = 0
    for name, ok, measured in results:
        print(f"{'PASS' if ok else 'RED '} {name}: {measured}")
        red += 0 if ok else 1
    print(f"\n{len(results) - red}/{len(results)} data assertions pass; {red} RED")
    return 0 if red == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
