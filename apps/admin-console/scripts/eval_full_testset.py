"""Full test-set eval: run EVERY head-turn question from docs/测试集答案.xlsx (via the
parsed tests/fixtures/test_cases.yaml golden set) through /api/chat and score against
the standard answer.

Scores per case:
- required recall: required_entities present in the response (the golden must-appear set).
- forbidden precision: forbidden_entities must NOT appear.
- answer coverage: significant-term overlap with the full standard `answer` (coarse semantic).
- flags: coref (multi-turn — will fail single-turn), refusal_expected, disambiguation.

Runs against the LIVE backend (HTTP), so the backend must be UP. Multi-turn (coref) cases
are sent standalone and will miss coref — recorded, not scored as regressions.

Usage:
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  export no_proxy=localhost,127.0.0.1,::1
  uv run python scripts/eval_full_testset.py [--base http://localhost:18188] [--out .agents/runs/retrieval-generation-alignment/full-testset-<date>.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "test_cases.yaml"
_DEFAULT_OUT = (
    REPO / ".agents" / "runs" / "retrieval-generation-alignment"
    / f"full-testset-{date.today().isoformat()}.json"
)

# Coarse Chinese/English significant-term extractor for answer-coverage.
_TERM_RE = re.compile(r"[一-鿿]{2,}|[A-Za-z][A-Za-z0-9\-]{2,}")
_STOP = {
    "的", "了", "和", "与", "及", "或", "在", "为", "是", "有", "等", "年", "月", "日",
    "进行", "通过", "可以", "以及", "一个", "这个", "目前", "其中",
}


def _terms(text: str) -> set[str]:
    return {t for t in _TERM_RE.findall(text or "") if t.lower() not in _STOP and len(t) >= 2}


def _hit(response_text: str, entities: list[str]) -> list[str]:
    low = response_text.lower()
    return [e for e in entities if e and e.lower() in low]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:18188")
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    args = ap.parse_args()

    cases = yaml.safe_load(FIXTURE.read_text())["cases"]
    head_cases = [c for c in cases if c.get("is_head_turn")]
    print(f"loaded {len(cases)} cases ({len(head_cases)} head-turn / single-turn runnable)")

    rows = []
    tot_req = tot_hit = 0
    forbidden_violations = 0
    coverages = []
    flag_counts = {"coref": 0, "refusal": 0, "disambiguation": 0}
    with httpx.Client(base_url=args.base, timeout=60.0) as client:
        for c in head_cases:
            qid = c["qid"]
            query = c["query"]
            required = c.get("required_entities") or []
            forbidden = c.get("forbidden_entities") or []
            answer = c.get("answer") or ""
            flags = {
                "coref": bool(c.get("coref_needs_label")),
                "refusal": bool(c.get("refusal_expected")),
                "disambiguation": bool(c.get("disambiguation_expected")),
            }
            for f, v in flags.items():
                if v:
                    flag_counts[f] += 1
            try:
                r = client.post("/api/chat", json={"query": query})
                resp = r.json()
                text = json.dumps(resp, ensure_ascii=False)
            except Exception as exc:  # noqa: BLE001
                rows.append({"qid": qid, "query": query, "error": str(exc)[:120], **flags})
                continue
            hits = _hit(text, required)
            bad = _hit(text, forbidden)
            ans_terms = _terms(answer)
            resp_terms = _terms(text)
            cov = (len(ans_terms & resp_terms) / len(ans_terms)) if ans_terms else 0.0
            tot_req += len(required)
            tot_hit += len(hits)
            if bad:
                forbidden_violations += 1
            coverages.append(cov)
            rows.append(
                {
                    "qid": qid,
                    "query": query,
                    "required_hit": f"{len(hits)}/{len(required)}",
                    "missing": [e for e in required if e not in hits],
                    "forbidden_hit": bad,
                    "answer_coverage": round(cov, 2),
                    "qtype": resp.get("query_type"),
                    **flags,
                }
            )
            mark = "OK" if len(hits) == len(required) and not bad else ("FLAG" if any(flags.values()) else "MISS")
            print(
                f"qid {qid:>3} {mark:<5} req {len(hits)}/{len(required)}  forb {len(bad)}  "
                f"cov {cov:.0%}  {flags}  {query[:34]}"
            )

    summary = {
        "head_cases": len(head_cases),
        "required_recall": f"{tot_hit}/{tot_req} ({100 * tot_hit / tot_req:.0f}%)" if tot_req else "n/a",
        "forbidden_violation_cases": forbidden_violations,
        "mean_answer_coverage": round(sum(coverages) / len(coverages), 3) if coverages else 0,
        "flag_counts": flag_counts,
        "rows": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    for k in ("head_cases", "required_recall", "forbidden_violation_cases", "mean_answer_coverage", "flag_counts"):
        print(f"  {k}: {summary[k]}")
    print(f"  written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
