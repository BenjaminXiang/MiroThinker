"""Stage 0 sensor #1: entity-level inventory for the goal function
"可达 × 诚实分级" (pool reachability x honest tiering).

Read-only. Measures, against the pool mirror (miroflow_light_lane_r1) and the
live serving pack (candidate-v2-20260819-r1 lookup.sqlite3):

  A. scope gap   — pool entities whose name has no pack counterpart (per domain)
  B. alias cover — pack alias fields populated? Chinese counterpart present for
                   English-legal-style company names? professor name_en?
  C. tier labels — pack eligibility_outcome distribution (admitted/limited)
  D. bindings    — resolved applicant bindings (company<->patent), alive
                   prof-paper links, per-entity coverage
  E. field floor — answer-critical field non-null rates in the pool mirror

Outputs: stage0-inventory.json next to this script + a printed summary.
Deterministic: no sampling here — full-population counts.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import psycopg

RUN_DIR = Path(__file__).resolve().parent
PACK_LOOKUP = "/var/tmp/mirothinker-data-v2/serving-pack/lookup.sqlite3"
PG_DSN = "postgresql://miroflow@127.0.0.1:55458/miroflow_light_lane_r1"

_EN_LEGAL = re.compile(r"\b(Ltd|Inc|Corp|Co|LLC|Limited|Company|Group|Holdings)\b", re.I)


def _norm(name: str | None) -> str:
    return (name or "").strip().casefold()


def load_pack() -> list[dict]:
    conn = sqlite3.connect(f"file:{PACK_LOOKUP}?mode=ro", uri=True)
    docs = []
    for (dj,) in conn.execute("SELECT document_json FROM lookup_document"):
        d = json.loads(dj)
        content = json.loads(d["lookup_content"])
        docs.append(
            {
                "domain": d["domain"],
                "outcome": d["eligibility_outcome"],
                "name": content.get("name")
                or content.get("canonical_name_zh")
                or content.get("title")
                or "",
                "name_en": content.get("canonical_name_en") or content.get("title_en"),
                "aliases": tuple(content.get("aliases") or ()),
                "content_text": d["lookup_content"],
                "patent_number": content.get("patent_number"),
            }
        )
    conn.close()
    return docs


def main() -> None:
    pack = load_pack()
    by_domain: dict[str, list[dict]] = {}
    for doc in pack:
        by_domain.setdefault(doc["domain"], []).append(doc)

    pg = psycopg.connect(PG_DSN, connect_timeout=5)

    # ---- A. scope gap: pool name -> pack name set (per domain) -------------
    pool_names: dict[str, set[str]] = {}
    pool_names["company"] = {
        _norm(r[0]) for r in pg.execute("SELECT company_name FROM company")
    }
    pool_names["professor"] = {
        _norm(r[0]) for r in pg.execute("SELECT name FROM professor")
    }
    pool_names["patent"] = {
        _norm(r[0]) for r in pg.execute("SELECT patent_number FROM patent")
    }
    pool_names["paper"] = {
        _norm(r[0]) for r in pg.execute("SELECT title FROM paper WHERE title IS NOT NULL")
    }
    pack_names = {
        dom: {
            _norm(d["patent_number"] if dom == "patent" else d["name"])
            for d in docs
        }
        for dom, docs in by_domain.items()
    }
    scope_gap = {}
    gap_samples = {}
    for dom, pool_set in pool_names.items():
        missing = sorted(pool_set - pack_names.get(dom, set()))
        scope_gap[dom] = {
            "pool": len(pool_set),
            "pack": len(pack_names.get(dom, set())),
            "pool_not_in_pack": len(missing),
            "coverage": round(1 - len(missing) / max(1, len(pool_set)), 4),
        }
        gap_samples[dom] = missing[:5]

    # ---- B. alias coverage --------------------------------------------------
    company_docs = by_domain.get("company", [])
    alias_filled = [d for d in company_docs if d["aliases"]]
    en_legal = [d for d in company_docs if _EN_LEGAL.search(d["name"] or "")]
    # crude Chinese-counterpart check: any CJK char in aliases or content
    def _has_cjk(s: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in s)

    en_no_cjk = [
        d
        for d in en_legal
        if not any(_has_cjk(a) for a in d["aliases"])
        and not _has_cjk(d["content_text"][:4000])
    ]
    prof_docs = by_domain.get("professor", [])
    prof_alias = [d for d in prof_docs if d["aliases"]]
    prof_en = [d for d in prof_docs if (d.get("name_en") or "").strip()]

    # ---- C. tier labels ------------------------------------------------------
    outcome_counts = Counter(d["outcome"] for d in pack)

    # ---- D. bindings ---------------------------------------------------------
    binding_status = dict(
        pg.execute("SELECT status, COUNT(*) FROM applicant_binding GROUP BY status").fetchall()
    )
    companies_with_patent = pg.execute(
        """
        SELECT COUNT(DISTINCT resolved_company) FROM applicant_binding
        WHERE status = 'resolved' AND resolved_company IS NOT NULL
        """
    ).fetchone()[0]
    link_status = dict(
        pg.execute("SELECT link_status, COUNT(*) FROM prof_paper_link GROUP BY link_status").fetchall()
    )
    profs_with_paper = pg.execute(
        "SELECT COUNT(DISTINCT professor_id) FROM prof_paper_link"
    ).fetchone()[0]
    prof_total = pg.execute("SELECT COUNT(*) FROM professor").fetchone()[0]

    # ---- E. field floor ------------------------------------------------------
    def _filled_ratio(table: str, col: str) -> tuple[int, int]:
        return pg.execute(
            f"SELECT COUNT(*) FILTER (WHERE {col} IS NOT NULL"
            f" AND {col}::text NOT IN ('null', '[]', '\"\"', '')),"
            f" COUNT(*) FROM {table}"
        ).fetchone()

    field_floor = {
        "company": {col: _filled_ratio("company", col) for col in ("business", "product_summary", "industry")},
        "paper": {col: _filled_ratio("paper", col) for col in ("abstract", "summary_zh", "doi")},
        "professor": {col: _filled_ratio("professor", col) for col in ("research_directions", "institution")},
    }
    field_ratio = {
        dom: {col: round(n / max(1, t), 4) for col, (n, t) in cols.items()}
        for dom, cols in field_floor.items()
    }

    result = {
        "pack": {
            "total_docs": len(pack),
            "by_domain": {d: len(v) for d, v in by_domain.items()},
            "eligibility_outcomes": dict(outcome_counts),
        },
        "scope_gap": scope_gap,
        "scope_gap_samples": gap_samples,
        "alias": {
            "company": {
                "total": len(company_docs),
                "alias_filled": len(alias_filled),
                "en_legal_style": len(en_legal),
                "en_legal_without_any_cjk": len(en_no_cjk),
                "en_no_cjk_samples": [d["name"] for d in en_no_cjk[:8]],
            },
            "professor": {
                "total": len(prof_docs),
                "alias_filled": len(prof_alias),
                "name_en_filled": len(prof_en),
            },
        },
        "bindings": {
            "applicant_binding_status": binding_status,
            "companies_with_resolved_patent_binding": companies_with_patent,
            "prof_paper_link_status": link_status,
            "professors_with_any_paper_link": profs_with_paper,
            "professors_total": prof_total,
        },
        "field_floor_ratio": field_ratio,
    }

    out = RUN_DIR / "stage0-inventory.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
