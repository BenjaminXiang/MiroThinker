"""Session-sticky multi-turn eval for /api/chat.

Loads the existing single-turn fixture plus the synthesized multi-turn fixture,
groups rows by ``turn_group``, and replays each group as one conversation using
the same ``miroflow_chat_session`` cookie for every turn in that group.

Runs against the LIVE backend, so the backend must already be UP. This script
does not start services.

Usage:
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  export no_proxy=localhost,127.0.0.1,::1
  uv run python scripts/eval_multi_turn.py [--base http://localhost:18188] [--out .agents/runs/layer-d-multi-turn-context/red-baseline-<date>.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO = Path(__file__).resolve().parents[3]
BASE_FIXTURE = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "test_cases.yaml"
SYNTH_FIXTURE = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "multi_turn_cases.yaml"
_DEFAULT_OUT = (
    REPO
    / ".agents"
    / "runs"
    / "layer-d-multi-turn-context"
    / f"red-baseline-{date.today().isoformat()}.json"
)

SESSION_COOKIE = "miroflow_chat_session"
NO_PROXY_VALUE = "localhost,127.0.0.1,::1"
PROXY_ENV_VARS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
    "no_proxy",
    "NO_PROXY",
)

# Keep this intentionally aligned with eval_full_testset.py.
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

DOMAIN_ID_KEYS = {
    "professor": "professor_id",
    "company": "company_id",
    "paper": "paper_id",
    "patent": "patent_id",
}
LIST_KEYS_BY_DOMAIN = {
    "professor": ("matched_professors", "professors", "linked_professors"),
    "company": ("matched_objects", "matched_companies", "companies", "linked_companies"),
    "paper": ("papers", "matched_papers", "linked_papers"),
    "patent": ("patents", "matched_patents", "linked_patents"),
}


def _terms(text: str) -> set[str]:
    return {t for t in _TERM_RE.findall(text or "") if t.lower() not in _STOP and len(t) >= 2}


def _hit(response_text: str, entities: Sequence[str]) -> list[str]:
    low = response_text.lower()
    return [e for e in entities if e and e.lower() in low]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _case_qid(case: dict[str, Any]) -> str:
    return str(case.get("qid", "")).strip()


def _validate_case(case: Any, *, fixture: Path, index: int) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError(f"{fixture}: cases[{index}] must be a mapping")
    required = ("qid", "turn_group", "is_head_turn", "query", "answer")
    missing = [key for key in required if key not in case]
    if missing:
        raise ValueError(f"{fixture}: cases[{index}] missing required keys: {missing}")
    if not isinstance(case.get("turn_group"), str) or not case["turn_group"].strip():
        raise ValueError(f"{fixture}: cases[{index}] turn_group must be a non-empty string")
    if not isinstance(case.get("is_head_turn"), bool):
        raise ValueError(f"{fixture}: cases[{index}] is_head_turn must be a boolean")
    if not isinstance(case.get("query"), str) or not case["query"].strip():
        raise ValueError(f"{fixture}: cases[{index}] query must be a non-empty string")
    for key in ("required_entities", "forbidden_entities"):
        if key in case and not isinstance(case[key], list):
            raise ValueError(f"{fixture}: cases[{index}] {key} must be a list")
    expected_query_type = case.get("expected_query_type")
    if expected_query_type is not None and not isinstance(expected_query_type, (str, list)):
        raise ValueError(f"{fixture}: cases[{index}] expected_query_type must be a string or list")
    if isinstance(expected_query_type, list) and not all(isinstance(item, str) for item in expected_query_type):
        raise ValueError(f"{fixture}: cases[{index}] expected_query_type list items must be strings")
    expected_set_derived = case.get("expected_set_derived")
    if expected_set_derived is not None and not isinstance(expected_set_derived, bool):
        raise ValueError(f"{fixture}: cases[{index}] expected_set_derived must be a boolean")

    normalized = dict(case)
    normalized.setdefault("required_entities", [])
    normalized.setdefault("forbidden_entities", [])
    normalized["_fixture"] = str(fixture.relative_to(REPO))
    normalized["_fixture_index"] = index
    return normalized


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f"{path}: expected top-level mapping with a cases list")
    return [_validate_case(case, fixture=path, index=i) for i, case in enumerate(data["cases"])]


def _load_all_cases(fixtures: Sequence[Path]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for fixture in fixtures:
        cases.extend(_load_fixture(fixture))
    return cases


def _group_cases(cases: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(case["turn_group"], []).append(case)
    return grouped


def _ordered_group_turns(group: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    heads = [case for case in group if case.get("is_head_turn")]
    followups = [case for case in group if not case.get("is_head_turn")]
    return heads + followups


def _runnable_groups(grouped: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        (turn_group, _ordered_group_turns(group))
        for turn_group, group in grouped.items()
        if any(not case.get("is_head_turn") for case in group)
    ]


def _prepare_loopback_env() -> list[str]:
    removed: list[str] = []
    for name in PROXY_ENV_VARS:
        if name in os.environ:
            os.environ.pop(name, None)
            removed.append(name)
    os.environ["no_proxy"] = NO_PROXY_VALUE
    return removed


def _new_session_id(group_index: int, turn_group: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", turn_group).strip("-") or "group"
    slug = slug[:32].strip("-") or "group"
    return f"eval-mt-{group_index:02d}-{slug}-{uuid.uuid4().hex[:8]}"


def _response_text(response_json: dict[str, Any]) -> str:
    return json.dumps(response_json, ensure_ascii=False, sort_keys=True)


def _id_from_item(item: Any, domain: str) -> str | None:
    if not isinstance(item, dict):
        return None
    key = DOMAIN_ID_KEYS[domain]
    value = item.get(key) or item.get("id") or item.get("entity_id")
    return str(value) if value else None


def _append_unique(bucket: list[str], value: str | None) -> None:
    if value and value not in bucket:
        bucket.append(value)


def _displayed_ids_by_domain(response_json: dict[str, Any]) -> dict[str, list[str]]:
    ids: dict[str, list[str]] = {domain: [] for domain in DOMAIN_ID_KEYS}
    for citation in response_json.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        domain = citation.get("type")
        if domain in ids:
            _append_unique(ids[domain], str(citation.get("id") or ""))

    structured_payload = response_json.get("structured_payload") or {}
    if not isinstance(structured_payload, dict):
        return {domain: values for domain, values in ids.items() if values}

    for domain, key in DOMAIN_ID_KEYS.items():
        _append_unique(ids[domain], str(structured_payload.get(key) or ""))
        for list_key in LIST_KEYS_BY_DOMAIN[domain]:
            for item in structured_payload.get(list_key) or []:
                _append_unique(ids[domain], _id_from_item(item, domain))

    return {domain: values for domain, values in ids.items() if values}


def _collect_string_values(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            found.update(_collect_string_values(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_string_values(item))
    elif isinstance(value, str) and value:
        found.add(value)
    return found


_ENTITY_ID_PREFIXES = ("PROF", "COMP", "PAPER", "PAT")


def _looks_like_entity_id(value: str) -> bool:
    return value.startswith(_ENTITY_ID_PREFIXES)


def _collect_source_like_ids(value: Any, *, source_context: bool = False) -> set[str]:
    # Only entity-ID-shaped strings count as "source references"; labels/URLs under
    # source-ish keys (source_url, source_label) would otherwise false-fail the check.
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if "url" in key_lower:
                continue
            nested_source_context = source_context or any(
                marker in key_lower for marker in ("source", "member", "from", "basis", "input")
            )
            found.update(_collect_source_like_ids(nested, source_context=nested_source_context))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_source_like_ids(item, source_context=source_context))
    elif source_context and isinstance(value, str) and _looks_like_entity_id(value):
        found.add(value)
    return found


def _set_derived_assertion(
    response_json: dict[str, Any],
    prior_displayed_ids: dict[str, list[str]],
) -> dict[str, Any]:
    basis_ids = {object_id for ids in prior_displayed_ids.values() for object_id in ids}
    if not basis_ids:
        return {
            "passed": False,
            "reason": "no prior displayed IDs available for set-derived check",
            "basis_ids": [],
            "payload_basis_overlap": [],
            "source_ids_outside_basis": [],
        }

    structured_payload = response_json.get("structured_payload") or {}
    if not isinstance(structured_payload, dict) or not structured_payload:
        return {
            "passed": False,
            "reason": "response has no structured_payload mapping/evidence",
            "basis_ids": sorted(basis_ids),
            "payload_basis_overlap": [],
            "source_ids_outside_basis": [],
        }

    # The set-derived check verifies the operation ran over the PRIOR set, not a fresh
    # global search. For traversal the payload carries an explicit `source_ids` list
    # (the members traversed): pass iff those are a non-empty subset of the prior basis.
    # Target IDs are intentionally NEW (the whole point of traversal) and must NOT be
    # counted as violations, so the old "any source-like id outside basis" sweep is gone.
    explicit_source_ids = structured_payload.get("source_ids")
    if isinstance(explicit_source_ids, list) and explicit_source_ids:
        source_set = {str(sid) for sid in explicit_source_ids if sid}
        outside = sorted(source_set - basis_ids)
        overlap = sorted(source_set & basis_ids)
        passed = bool(overlap) and not outside
        reason = "ok"
        if not overlap:
            reason = "source_ids do not overlap prior displayed set"
        elif outside:
            reason = "source_ids contain members outside prior displayed set (global re-search)"
        return {
            "passed": passed,
            "reason": reason,
            "basis_ids": sorted(basis_ids),
            "payload_basis_overlap": overlap,
            "source_ids_outside_basis": outside,
        }

    # Narrowing/other: no explicit source_ids — fall back to "members referenced at all".
    payload_ids = _collect_string_values(structured_payload)
    overlap = sorted(basis_ids & payload_ids)
    passed = bool(overlap)
    return {
        "passed": passed,
        "reason": "ok" if passed else "structured_payload does not reference prior displayed set IDs",
        "basis_ids": sorted(basis_ids),
        "payload_basis_overlap": overlap,
        "source_ids_outside_basis": [],
    }



def _query_type_assertion(actual: str | None, expected: str | list[str] | None) -> dict[str, Any] | None:
    if expected is None:
        return None
    expected_values = [expected] if isinstance(expected, str) else list(expected)
    return {
        "expected": expected_values,
        "actual": actual,
        "passed": actual in expected_values,
    }


def _answer_coverage(answer: str, response_text: str) -> tuple[float | None, list[str], list[str]]:
    answer_terms = _terms(answer)
    if not answer_terms:
        return None, [], []
    response_terms = _terms(response_text)
    hit = sorted(answer_terms & response_terms)
    missing = sorted(answer_terms - response_terms)
    return len(hit) / len(answer_terms), hit, missing


def _score_case(
    case: dict[str, Any],
    response_json: dict[str, Any],
    prior_displayed_ids: dict[str, list[str]],
    coverage_threshold: float,
) -> dict[str, Any]:
    response_text = _response_text(response_json)
    required = [str(item) for item in case.get("required_entities") or []]
    forbidden = [str(item) for item in case.get("forbidden_entities") or []]
    hits = _hit(response_text, required)
    forbidden_hits = _hit(response_text, forbidden)
    coverage, coverage_hits, coverage_missing = _answer_coverage(str(case.get("answer") or ""), response_text)
    query_type = response_json.get("query_type")

    failure_notes: list[str] = []
    if len(hits) != len(required):
        failure_notes.append("missing required entities")
    if forbidden_hits:
        failure_notes.append("forbidden entities present")
    if coverage is not None and coverage < coverage_threshold:
        failure_notes.append(f"answer coverage below threshold {coverage_threshold:.0%}")

    routing_assertions: dict[str, Any] = {}
    query_type_check = _query_type_assertion(query_type, case.get("expected_query_type"))
    if query_type_check is not None:
        routing_assertions["query_type"] = query_type_check
        if not query_type_check["passed"]:
            failure_notes.append("query_type assertion failed")

    if case.get("expected_set_derived") is True:
        set_derived = _set_derived_assertion(response_json, prior_displayed_ids)
        routing_assertions["set_derived"] = set_derived
        if not set_derived["passed"]:
            failure_notes.append("set-derived assertion failed")

    return {
        "required_hit": f"{len(hits)}/{len(required)}",
        "required_hit_count": len(hits),
        "required_total": len(required),
        "missing": [e for e in required if e not in hits],
        "forbidden_hit": forbidden_hits,
        "answer_coverage": round(coverage, 3) if coverage is not None else None,
        "answer_coverage_terms_hit": coverage_hits,
        "answer_coverage_terms_missing": coverage_missing[:12],
        "query_type": query_type,
        "routing_assertions": routing_assertions,
        "failure_notes": failure_notes,
        "passed": not failure_notes,
    }


def _error_row(
    *,
    case: dict[str, Any],
    turn_group: str,
    turn_index: int,
    session_id: str,
    error: str,
) -> dict[str, Any]:
    scored = not case.get("is_head_turn")
    return {
        "qid": _case_qid(case),
        "turn_group": turn_group,
        "turn_index": turn_index,
        "session_id": session_id,
        "fixture": case.get("_fixture"),
        "is_head_turn": bool(case.get("is_head_turn")),
        "scored": scored,
        "query": case.get("query"),
        "error": error[:240],
        "failure_notes": [error[:240]] if scored else [],
        "passed": False if scored else None,
    }


def _run_group(
    *,
    base_url: str,
    timeout: float,
    group_index: int,
    turn_group: str,
    turns: Sequence[dict[str, Any]],
    coverage_threshold: float,
) -> list[dict[str, Any]]:
    session_id = _new_session_id(group_index, turn_group)
    rows: list[dict[str, Any]] = []
    prior_displayed_ids: dict[str, list[str]] = {}

    with httpx.Client(
        base_url=base_url,
        timeout=timeout,
        cookies={SESSION_COOKIE: session_id},
        trust_env=False,
    ) as client:
        for turn_index, case in enumerate(turns, start=1):
            scored = not case.get("is_head_turn")
            try:
                response = client.post("/api/chat", json={"query": case["query"]})
                response_json = response.json()
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    _error_row(
                        case=case,
                        turn_group=turn_group,
                        turn_index=turn_index,
                        session_id=session_id,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue

            row: dict[str, Any] = {
                "qid": _case_qid(case),
                "turn_group": turn_group,
                "turn_index": turn_index,
                "session_id": session_id,
                "fixture": case.get("_fixture"),
                "is_head_turn": bool(case.get("is_head_turn")),
                "scored": scored,
                "query": case.get("query"),
                "http_status": response.status_code,
                "answer_excerpt": str(response_json.get("answer_text") or "")[:300],
                "citations_count": len(response_json.get("citations") or []),
                "structured_payload_keys": sorted((response_json.get("structured_payload") or {}).keys()),
            }
            if scored:
                row.update(_score_case(case, response_json, prior_displayed_ids, coverage_threshold))
            else:
                row.update(
                    {
                        "query_type": response_json.get("query_type"),
                        "failure_notes": [],
                        "passed": None,
                    }
                )
            rows.append(row)

            displayed_ids = _displayed_ids_by_domain(response_json)
            if displayed_ids:
                prior_displayed_ids = displayed_ids

    return rows


def _summarize(rows: Sequence[dict[str, Any]], *, group_count: int, turn_count: int) -> dict[str, Any]:
    scored = [row for row in rows if row.get("scored")]
    passed = [row for row in scored if row.get("passed")]
    failed = [row for row in scored if row.get("passed") is False]
    total_required = sum(int(row.get("required_total") or 0) for row in scored)
    total_required_hit = sum(int(row.get("required_hit_count") or 0) for row in scored)
    coverages = [float(row["answer_coverage"]) for row in scored if row.get("answer_coverage") is not None]

    query_type_checks = [
        row["routing_assertions"]["query_type"]
        for row in scored
        if isinstance(row.get("routing_assertions"), dict) and "query_type" in row["routing_assertions"]
    ]
    set_derived_checks = [
        row["routing_assertions"]["set_derived"]
        for row in scored
        if isinstance(row.get("routing_assertions"), dict) and "set_derived" in row["routing_assertions"]
    ]

    return {
        "groups": group_count,
        "turns": turn_count,
        "scored_cases": len(scored),
        "passed_cases": len(passed),
        "failed_cases": len(failed),
        "required_recall": (
            f"{total_required_hit}/{total_required} ({100 * total_required_hit / total_required:.0f}%)"
            if total_required
            else "n/a"
        ),
        "forbidden_violation_cases": sum(1 for row in scored if row.get("forbidden_hit")),
        "mean_answer_coverage": round(sum(coverages) / len(coverages), 3) if coverages else None,
        "query_type_assertions": (
            f"{sum(1 for item in query_type_checks if item.get('passed'))}/{len(query_type_checks)}"
            if query_type_checks
            else "n/a"
        ),
        "set_derived_assertions": (
            f"{sum(1 for item in set_derived_checks if item.get('passed'))}/{len(set_derived_checks)}"
            if set_derived_checks
            else "n/a"
        ),
        "failed_qids": [row.get("qid") for row in failed],
    }


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run session-sticky multi-turn /api/chat eval.")
    parser.add_argument("--base", default="http://localhost:18188")
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--coverage-threshold", type=float, default=0.20)
    parser.add_argument(
        "--fixtures",
        nargs="*",
        default=[str(BASE_FIXTURE), str(SYNTH_FIXTURE)],
        help="YAML fixtures to load; defaults to test_cases.yaml plus multi_turn_cases.yaml.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    fixtures = [Path(item).resolve() for item in args.fixtures]
    cases = _load_all_cases(fixtures)
    grouped = _group_cases(cases)
    runnable = _runnable_groups(grouped)
    turn_count = sum(len(turns) for _, turns in runnable)
    scored_count = sum(1 for _, turns in runnable for case in turns if not case.get("is_head_turn"))
    removed_proxy_vars = _prepare_loopback_env()

    print(
        f"loaded {len(cases)} cases from {len(fixtures)} fixtures; "
        f"running {len(runnable)} groups / {scored_count} scored follow-ups"
    )
    rows: list[dict[str, Any]] = []
    for group_index, (turn_group, turns) in enumerate(runnable, start=1):
        print(f"\n=== group {group_index}/{len(runnable)}: {turn_group} ({len(turns)} turns) ===")
        group_rows = _run_group(
            base_url=args.base,
            timeout=args.timeout,
            group_index=group_index,
            turn_group=turn_group,
            turns=turns,
            coverage_threshold=args.coverage_threshold,
        )
        rows.extend(group_rows)
        for row in group_rows:
            if not row.get("scored"):
                mark = "HEAD"
            elif row.get("passed"):
                mark = "OK"
            else:
                mark = "FAIL"
            print(
                f"qid {str(row.get('qid')):>8} {mark:<4} "
                f"qtype {str(row.get('query_type')):<24} {str(row.get('query'))[:42]}"
            )

    summary = _summarize(rows, group_count=len(runnable), turn_count=turn_count)
    report = {
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "base": args.base,
            "fixtures": [str(path) for path in fixtures],
            "coverage_threshold": args.coverage_threshold,
            "session_cookie": SESSION_COOKIE,
            "proxy_env_unset": removed_proxy_vars,
            "no_proxy": os.environ.get("no_proxy"),
        },
        "summary": summary,
        "rows": rows,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print(f"  written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
