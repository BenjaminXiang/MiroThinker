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

Two axes are reported, because they answer different questions and used to be
conflated:

- ``required_recall`` (exact) is the **regression** axis: it only has to not go
  down.  It under-reports honest answers that phrase a fact differently, so it
  is not an acceptance score.
- ``product_pass`` is the **usability** axis: the turn answered, cited at least
  one source (or refused when refusal was expected), and violated no forbidden
  entity.  This is the number a product decision can use.

Against a baseline the script reports per-turn regressions/improvements and, with
``--fail-on-regression``, exits non-zero if any turn regressed or any forbidden /
refusal / error total went up.

Usage:
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  export no_proxy=localhost,127.0.0.1,::1
  uv run python scripts/eval_full_testset.py \\
      [--base http://localhost:18188] [--mode head|full] [--out PATH] \\
      [--baseline PATH] [--fail-on-regression]
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "test_cases.yaml"
_DEFAULT_OUT = (
    REPO
    / ".agents"
    / "runs"
    / "retrieval-generation-alignment"
    / f"full-testset-{date.today().isoformat()}.json"
)

# Coarse Chinese/English significant-term extractor for answer-coverage.
_TERM_RE = re.compile(r"[一-鿿]{2,}|[A-Za-z][A-Za-z0-9\-]{2,}")
_STOP = {
    "的",
    "了",
    "和",
    "与",
    "及",
    "或",
    "在",
    "为",
    "是",
    "有",
    "等",
    "年",
    "月",
    "日",
    "进行",
    "通过",
    "可以",
    "以及",
    "一个",
    "这个",
    "目前",
    "其中",
}
_REFUSAL_MARKERS = (
    "无法",
    "不能",
    "不予",
    "不建议",
    "不提供",
    "违法",
    "违规",
    "涉黄",
    "涉赌",
    "涉毒",
    "法律",
    "安全",
    "风险",
    "拒绝",
)
# The composer is a model: the same question can lose one exact token without any
# regression in meaning. A gate that fails on that is red half the time and gets
# ignored, so one-entity dips are reported as fluctuations; two or more on one
# turn, a total dip beyond tolerance, or any worse hard counter is a regression.
HARD_TURN_DROP = 2
DEFAULT_TOTAL_TOLERANCE = 3


def _terms(text: str) -> set[str]:
    return {
        t
        for t in _TERM_RE.findall(text or "")
        if t.lower() not in _STOP and len(t) >= 2
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _hits(text: str, entities: list[str]) -> list[str]:
    normalized_text = _normalize(text)
    return [e for e in entities if e and _normalize(e) in normalized_text]


def load_cases(path: Path = FIXTURE) -> list[dict]:
    return yaml.safe_load(Path(path).read_text())["cases"]


def groups_for(cases: list[dict], *, mode: str) -> list[list[dict]]:
    """Split cases into conversations: one case each in ``head``, one per group in ``full``."""
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


def _ask(client: httpx.Client, query: str) -> tuple[float, dict]:
    started = time.monotonic()
    response = client.post("/api/chat", json={"query": query})
    latency = time.monotonic() - started
    response.raise_for_status()
    return latency, response.json()


def _product_pass(
    *,
    answer: str,
    citations: int,
    refusal_expected: bool,
    refusal_ok: bool,
    forbidden: list[str],
    errored: bool,
) -> bool:
    """A turn a product owner would call usable.

    Refusal cases are usable when they refuse; answer cases are usable when they
    answered with at least one citation.  Exact required-entity recall is the
    regression axis and deliberately not part of this judgement.
    """
    if errored or forbidden:
        return False
    if refusal_expected:
        return refusal_ok
    return bool(answer) and citations > 0


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
    coverage = len(ans_terms & resp_terms) / len(ans_terms) if ans_terms else 0.0
    refusal_expected = bool(case.get("refusal_expected"))
    refusal_ok = not refusal_expected or any(
        marker in answer for marker in _REFUSAL_MARKERS
    )
    citations = len(resp.get("citations") or [])
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
        "citations": citations,
        "refusal_expected": refusal_expected,
        "refusal_ok": refusal_ok,
        "product_pass": _product_pass(
            answer=answer,
            citations=citations,
            refusal_expected=refusal_expected,
            refusal_ok=refusal_ok,
            forbidden=bad,
            errored=False,
        ),
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
            "product_pass": False,
            "coref": bool(case.get("coref_needs_label")),
            "disambiguation": bool(case.get("disambiguation_expected")),
        }
    return _score_case(
        case=case, resp=resp, latency=latency, mode=mode, turn_index=turn_index
    )


def _hits_of(row: dict) -> tuple[int, int]:
    """Read ``required_hit`` ("2/5") so old baselines stay comparable."""
    raw = str(row.get("required_hit") or "0/0")
    got, _, total = raw.partition("/")
    try:
        return int(got), int(total)
    except ValueError:
        return 0, 0


def summarize(rows: list[dict], *, mode: str) -> dict:
    total_required = 0
    total_hits = 0
    forbidden_violations = 0
    refusal_misses = 0
    product_passes = 0
    coverages: list[float] = []
    latencies: list[float] = []
    errors = 0
    for row in rows:
        got, total = _hits_of(row)
        total_required += total
        total_hits += got
        if row["forbidden_hit"]:
            forbidden_violations += 1
        if row["refusal_expected"] and not row["refusal_ok"]:
            refusal_misses += 1
        if row.get("product_pass"):
            product_passes += 1
        coverages.append(row["answer_coverage"])
        if "error" in row:
            errors += 1
        else:
            latencies.append(row["latency_seconds"])
    return {
        "mode": mode,
        "runnable_turns": len(rows),
        "required_hits": total_hits,
        "required_total": total_required,
        "required_recall": (
            f"{total_hits}/{total_required} ({100 * total_hits / total_required:.0f}%)"
            if total_required
            else "n/a"
        ),
        "forbidden_violation_cases": forbidden_violations,
        "refusal_misses": refusal_misses,
        "errors": errors,
        "product_pass": product_passes,
        "product_pass_rate": (round(product_passes / len(rows), 3) if rows else 0.0),
        "mean_answer_coverage": (
            round(sum(coverages) / len(coverages), 3) if coverages else 0
        ),
        "mean_latency_seconds": (
            round(sum(latencies) / len(latencies), 2) if latencies else 0
        ),
        "max_latency_seconds": max(latencies) if latencies else 0,
        "rows": rows,
    }


def compare_to_baseline(
    current: dict, baseline: dict, *, total_tolerance: int = DEFAULT_TOTAL_TOLERANCE
) -> dict:
    """Regression check with tolerance for model phrasing noise.

    Hard regressions: a turn disappears, a turn loses >= ``HARD_TURN_DROP``
    required entities, the total drops beyond ``total_tolerance``, or any of the
    forbidden / refusal-miss / error counters rises. Single-entity dips are
    reported as ``fluctuations`` because the answer composer rephrases.
    """
    current_rows = {str(row["qid"]): row for row in current.get("rows", [])}
    baseline_rows = {str(row["qid"]): row for row in baseline.get("rows", [])}
    regressed: list[dict] = []
    fluctuations: list[dict] = []
    improved: list[dict] = []
    for qid, base_row in baseline_rows.items():
        if qid not in current_rows:
            regressed.append({"qid": qid, "reason": "turn no longer runs"})
            continue
        was, _ = _hits_of(base_row)
        now, _ = _hits_of(current_rows[qid])
        delta = now - was
        if delta <= -HARD_TURN_DROP:
            regressed.append(
                {"qid": qid, "reason": "required hits", "was": was, "now": now}
            )
        elif delta == -1:
            fluctuations.append({"qid": qid, "was": was, "now": now})
        elif delta > 0:
            improved.append({"qid": qid, "was": was, "now": now})
    added = sorted(set(current_rows) - set(baseline_rows))

    counters = {}
    for key in ("forbidden_violation_cases", "refusal_misses", "errors"):
        was = int(baseline.get(key) or 0)
        now = int(current.get(key) or 0)
        if now > was:
            regressed.append({"qid": "-", "reason": key, "was": was, "now": now})
        counters[key] = {"was": was, "now": now}

    for key in ("required_hits", "product_pass"):
        counters[key] = {
            "was": int(baseline.get(key) or 0),
            "now": int(current.get(key) or 0),
        }

    total_delta = counters["required_hits"]["now"] - counters["required_hits"]["was"]
    if total_delta < -total_tolerance:
        regressed.append(
            {
                "qid": "-",
                "reason": "total required hits",
                "was": counters["required_hits"]["was"],
                "now": counters["required_hits"]["now"],
            }
        )

    return {
        "verdict": "regression" if regressed else "pass",
        "regressed": regressed,
        "fluctuations": fluctuations,
        "improved": improved,
        "added_turns": added,
        "total_delta": total_delta,
        "total_tolerance": total_tolerance,
        "counters": counters,
    }


def format_comparison(comparison: dict) -> str:
    lines = [f"baseline verdict: {comparison['verdict']}"]
    if comparison["regressed"]:
        lines.append("  regressed:")
        for item in comparison["regressed"]:
            detail = item.get("reason", "")
            if "was" in item:
                detail = f"{detail}: {item['was']} -> {item['now']}"
            lines.append(f"    qid {item['qid']}: {detail}")
    if comparison.get("fluctuations"):
        dipped = ", ".join(
            f"qid {item['qid']} {item['was']}->{item['now']}"
            for item in comparison["fluctuations"]
        )
        lines.append(f"  fluctuations (within tolerance): {dipped}")
    if comparison["improved"]:
        moved = ", ".join(
            f"qid {item['qid']} {item['was']}->{item['now']}"
            for item in comparison["improved"]
        )
        lines.append(f"  improved: {moved}")
    if comparison["added_turns"]:
        lines.append(f"  new turns: {', '.join(comparison['added_turns'])}")
    counters = comparison["counters"]
    lines.append(
        "  totals: required {was}->{now}, product_pass {pw}->{pn}, "
        "forbidden {fw}->{fn}, refusal_miss {rw}->{rn}, errors {ew}->{en}".format(
            was=counters["required_hits"]["was"],
            now=counters["required_hits"]["now"],
            pw=counters["product_pass"]["was"],
            pn=counters["product_pass"]["now"],
            fw=counters["forbidden_violation_cases"]["was"],
            fn=counters["forbidden_violation_cases"]["now"],
            rw=counters["refusal_misses"]["was"],
            rn=counters["refusal_misses"]["now"],
            ew=counters["errors"]["was"],
            en=counters["errors"]["now"],
        )
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:18188")
    ap.add_argument("--mode", choices=("head", "full"), default="head")
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    ap.add_argument(
        "--baseline", default=None, help="previous run JSON to compare against"
    )
    ap.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit 1 when any turn regressed or a forbidden/refusal/error total rose",
    )
    ap.add_argument(
        "--tolerance",
        type=int,
        default=DEFAULT_TOTAL_TOLERANCE,
        help="how many required hits the total may dip before it counts as a regression",
    )
    ap.add_argument(
        "--label", default=None, help="free-form tag recorded in the output"
    )
    args = ap.parse_args()

    cases = load_cases()
    groups = groups_for(cases, mode=args.mode)
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
                    f" pass={row['product_pass']}"
                    f"{missing}  {row['query'][:34]}"
                )

    summary = summarize(rows, mode=args.mode)
    summary["label"] = args.label
    summary["base_url"] = args.base

    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text())
        comparison = compare_to_baseline(
            summary, baseline, total_tolerance=args.tolerance
        )
        summary["comparison"] = comparison
        print("\n=== BASELINE ===")
        print(format_comparison(comparison))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    for key in (
        "mode",
        "runnable_turns",
        "required_recall",
        "product_pass_rate",
        "forbidden_violation_cases",
        "refusal_misses",
        "errors",
        "mean_answer_coverage",
        "mean_latency_seconds",
        "max_latency_seconds",
    ):
        print(f"  {key}: {summary[key]}")
    print(f"  written: {args.out}")

    if (
        args.fail_on_regression
        and summary.get("comparison", {}).get("verdict") == "regression"
    ):
        print("\nGATE FAILED: regression against baseline", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
