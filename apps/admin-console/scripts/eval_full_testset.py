"""Golden-set eval against the LIVE canonical-v2 chat API.

Two modes:

- ``head`` (default): every head-turn case is an independent first turn, one
  fresh cookie jar per case.  This is the regression gate for single-turn
  answer quality.
- ``full``: cases run in their ``turn_group`` order with one cookie jar per
  group, so pronoun/``上述企业`` follow-ups are exercised instead of being
  silently skipped.

Scoring is on ``answer_text`` only (not the whole JSON envelope): required
entities must appear in the answer body, forbidden entities must not, and
answer coverage is significant-term overlap with the standard answer.
Whitespace is removed before matching so a standard phrase split across lines
(q23) is still comparable.  Errors count as misses for every required entity.

Usage:
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  export no_proxy=localhost,127.0.0.1,::1
  uv run python scripts/eval_full_testset.py \
      [--base http://localhost:18188] [--mode head|full] [--out PATH]
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import re
import time
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
_REFUSAL_MARKERS = (
    "无法", "不能", "不予", "不建议", "不提供", "违法", "违规", "涉黄", "涉赌",
    "涉毒", "法律", "安全", "风险", "拒绝",
)


def _terms(text: str) -> set[str]:
    return {t for t in _TERM_RE.findall(text or "") if t.lower() not in _STOP and len(t) >= 2}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _hits(text: str, entities: list[str]) -> list[str]:
    normalized_text = _normalize(text)
    return [e for e in entities if e and _normalize(e) in normalized_text]


def _ask(client: httpx.Client, query: str) -> tuple[float, dict]:
    started = time.monotonic()
    response = client.post("/api/chat", json={"query": query})
    latency = time.monotonic() - started
    response.raise_for_status()
    return latency, response.json()


def _score_case(
    *,
    case: dict,
    resp: dict,
    latency: float,
    mode: str,
    turn_index: int,
) -> dict:
    answer = resp.get("answer_text") or ""
    required = case.get("required_entities") or []
    forbidden = case.get("forbidden_entities") or []
    hits = _hits(answer, required)
    bad = _hits(answer, forbidden)
    ans_terms = _terms(case.get("answer") or "")
    resp_terms = _terms(answer)
    coverage = (
        len(ans_terms & resp_terms) / len(ans_terms) if ans_terms else 0.0
    )
    refusal_expected = bool(case.get("refusal_expected"))
    refusal_ok = (
        not refusal_expected
        or any(marker in answer for marker in _REFUSAL_MARKERS)
    )
    return {
        "qid": case["qid"],
        "turn_group": case.get("turn_group"),
        "turn_index": turn_index,
        "mode": mode,
        "query": case["query"],
        "required_hit": f"{len(hits)}/{len(required)}",
        "missing": [e for e in required if e not in hits],
        "forbidden_hit": bad,
        "answer_coverage": round(coverage, 2),
        "qtype": resp.get("query_type"),
        "latency_seconds": round(latency, 2),
        "answer_text": answer,
        "citations": len(resp.get("citations") or []),
        "refusal_expected": refusal_expected,
        "refusal_ok": refusal_ok,
        "coref": bool(case.get("coref_needs_label")),
        "disambiguation": bool(case.get("disambiguation_expected")),
    }


def _run_case(
    *,
    client: httpx.Client,
    case: dict,
    mode: str,
    turn_index: int,
) -> dict:
    required = case.get("required_entities") or []
    try:
        latency, resp = _ask(client, case["query"])
    except Exception as exc:  # noqa: BLE001 - a failed call is a miss
        return {
            "qid": case["qid"],
            "turn_group": case.get("turn_group"),
            "turn_index": turn_index,
            "mode": mode,
            "query": case["query"],
            "required_hit": f"0/{len(required)}",
            "missing": list(required),
            "forbidden_hit": [],
            "answer_coverage": 0.0,
            "error": str(exc)[:200],
            "latency_seconds": 0.0,
            "answer_text": "",
            "citations": 0,
            "refusal_expected": bool(case.get("refusal_expected")),
            "refusal_ok": False,
            "coref": bool(case.get("coref_needs_label")),
            "disambiguation": bool(case.get("disambiguation_expected")),
        }
    return _score_case(
        case=case, resp=resp, latency=latency, mode=mode, turn_index=turn_index
    )


def _groups(cases: list[dict], *, mode: str) -> list[list[dict]]:
    if mode == "head":
        return [[case] for case in cases if case.get("is_head_turn")]
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for case in cases:
        key = str(case.get("turn_group") or case["qid"])
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(case)
    return [grouped[key] for key in order]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:18188")
    ap.add_argument("--mode", choices=("head", "full"), default="head")
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    args = ap.parse_args()

    cases = yaml.safe_load(FIXTURE.read_text())["cases"]
    groups = _groups(cases, mode=args.mode)
    runnable = sum(len(group) for group in groups)
    print(
        f"loaded {len(cases)} cases; mode={args.mode}; "
        f"{len(groups)} conversation(s); {runnable} runnable turns"
    )

    rows: list[dict] = []
    for group in groups:
        with httpx.Client(base_url=args.base, timeout=180.0) as client:
            for turn_index, case in enumerate(group, start=1):
                row = _run_case(
                    client=client,
                    case=case,
                    mode=args.mode,
                    turn_index=turn_index,
                )
                rows.append(row)
                missing = f" miss={row['missing']}" if row.get("missing") else ""
                print(
                    f"qid {row['qid']:>3} {row['required_hit']:>5}"
                    f" lat={row['latency_seconds']:>6.2f}s"
                    f" forb={len(row['forbidden_hit'])}"
                    f" cov={row['answer_coverage']:.0%}"
                    f" refusal_ok={row['refusal_ok']}"
                    f"{missing}  {row['query'][:34]}"
                )

    total_required = 0
    total_hits = 0
    forbidden_violations = 0
    refusal_misses = 0
    coverages: list[float] = []
    latencies: list[float] = []
    errors = 0
    for row in rows:
        required = row["required_hit"].split("/")
        total_required += int(required[1])
        total_hits += int(required[0])
        if row["forbidden_hit"]:
            forbidden_violations += 1
        if row["refusal_expected"] and not row["refusal_ok"]:
            refusal_misses += 1
        coverages.append(row["answer_coverage"])
        if "error" in row:
            errors += 1
        else:
            latencies.append(row["latency_seconds"])

    summary = {
        "mode": args.mode,
        "runnable_turns": runnable,
        "required_recall": (
            f"{total_hits}/{total_required} "
            f"({100 * total_hits / total_required:.0f}%)"
            if total_required
            else "n/a"
        ),
        "forbidden_violation_cases": forbidden_violations,
        "refusal_misses": refusal_misses,
        "errors": errors,
        "mean_answer_coverage": (
            round(sum(coverages) / len(coverages), 3) if coverages else 0
        ),
        "mean_latency_seconds": (
            round(sum(latencies) / len(latencies), 2) if latencies else 0
        ),
        "max_latency_seconds": max(latencies) if latencies else 0,
        "rows": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    for key in (
        "mode",
        "runnable_turns",
        "required_recall",
        "forbidden_violation_cases",
        "refusal_misses",
        "errors",
        "mean_answer_coverage",
        "mean_latency_seconds",
        "max_latency_seconds",
    ):
        print(f"  {key}: {summary[key]}")
    print(f"  written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
