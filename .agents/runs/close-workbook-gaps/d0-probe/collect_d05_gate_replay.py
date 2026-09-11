"""D0.5 Q2 — byte-faithful offline replay of the web subject-consistency gate.

Reconstructs the merged web result lists of the run14-anchored g2-t2 / g5-t2
turns from the production web-lane cache (view payloads keyed by
sha256(view)), re-runs the REAL gate helpers imported from
knowledge_serving_isolated, and validates against the production trace
counts (g2-t2: 74 -> 7; g5-t2: 84 -> 3).

Production caps one web-lane call at _SERVING_WEB_MAX_QUERY_VIEWS (=4) views
while the trace journals six views per turn; the four views that fed the
gated call are identified by brute force: every ordered 4-view permutation is
merged with the real `_discovery_front_merge`, and only permutations whose
merged count equals the trace `in=` count are admitted. The gate's survivor
set and the dropped-item classification are then computed across ALL admitted
permutations; if they disagree, the spread is reported instead of hidden.

Every dropped item is classified:

  A  tier-4: names a displayed member by compact alias only (dropped when
     kept >= floor) — on-topic by construction, pass-through candidate.
  B  tier-5, but the item's summary/page text names a displayed member
     through the full identity forms — the gate's title+snippet window
     missed on-topic evidence.
  C  tier-5, names a GT entity that is NOT in the displayed set (e.g. 普渡
     for g2, 深南电路 for g5) — off-displayed-subject, GT-relevant.
  D  remainder — off-topic noise the gate exists to drop.

Read-only: the WAL-mode cache is copied to scratch first; no network, no
writes outside this directory's JSON output.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    _DualWebLaneAdapter,
    _NormalizedWebResult,
    _anchor_location_qualifier,
    _discovery_front_merge,
    _is_brand_discovery_view,
    _merge_web_results_across_views,
    _normalized_web_identity,
    _relaxed_serper_query,
    _web_identity_forms,
    _web_identity_text_matches,
    _web_result_relevance_tier,
    _apply_web_subject_consistency,
    _SERVING_WEB_MAX_QUERY_VIEWS,
    _WEB_SUBJECT_CONSISTENCY_FLOOR,
)
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)

JOURNAL = ROOT / "var/turn-trace/2026-09-10.jsonl"
CACHE_DB = ROOT / "var/turn-trace/web_lane.sqlite3"
OUT = Path(__file__).with_name("d05-gate-replay.json")

TURNS = {
    "g2-t2": {
        "session_marker": "JgjH8u4M",
        "expected_in": 74,
        "expected_retained": 7,
        "expected_gate_drop": 67,
        # displayed order taken verbatim from the turn's OR view string
        "bound_names": [
            "深圳市小村机器人智能科技有限公司",
            "深圳市锐曼智能技术有限公司",
            "深圳中科世界机器人有限公司",
            "中铧机器人（深圳）有限公司",
            "深圳中智卫安机器人技术有限公司",
            "深圳市普波科技有限公司",
            "深圳市中舟智能科技有限公司",
            "上海擎朗智能科技有限公司",
            "云迹科技股份有限公司",
            "睿博天米科技（深圳）有限公司",
            "深圳市智贝尔机器人设备科技有限公司",
            "深圳科卫机器人科技有限公司",
        ],
        "off_set_gt_aliases": ["普渡", "九号", "开普勒", "安赛步", "艾唯尔"],
    },
    "g5-t2": {
        "session_marker": "YZXc4pO5",
        "expected_in": 84,
        "expected_retained": 3,
        "expected_gate_drop": 81,
        "bound_names": [
            "深圳顺易捷科技有限公司",
            "深圳市驭鹰者电子有限公司",
            "深圳嘉立创科技集团股份有限公司",
            "深圳市深华科电子有限公司",
        ],
        "off_set_gt_aliases": [
            "深南电路", "一博", "兴森", "华秋", "中信华", "则成", "上达", "精诚达", "领智",
        ],
    },
}


def scratch_cache() -> sqlite3.Connection:
    scratch = Path(tempfile.mkdtemp(prefix="d05-gate-"))
    for suffix in ("", "-wal", "-shm"):
        source = Path(f"{CACHE_DB}{suffix}")
        if source.exists():
            shutil.copyfile(source, scratch / f"web_lane.sqlite3{suffix}")
    return sqlite3.connect(scratch / "web_lane.sqlite3")


def trace_turn(session_marker: str) -> dict:
    with JOURNAL.open() as handle:
        for line in handle:
            record = json.loads(line)
            if session_marker in record.get("session_id", "") and record.get("turn_ordinal") == 2:
                return record
    raise SystemExit(f"turn not found for {session_marker}")


def payload_for(cache: sqlite3.Connection, provider: str, view: str) -> tuple[list, str]:
    key = hashlib.sha256(view.encode("utf-8")).hexdigest()
    row = cache.execute(
        "SELECT payload_json, day FROM web_cache WHERE provider=? AND view_key=? AND day='2026-09-10'",
        (provider, key),
    ).fetchone()
    if row is not None:
        return json.loads(row[0]), row[1]
    row = cache.execute(
        "SELECT payload_json, day FROM web_cache WHERE provider=? AND view_key=?",
        (provider, key),
    ).fetchone()
    if row is not None:
        return json.loads(row[0]), f"{row[1]}(off-day)"
    return [], "MISS"


def gate_split(
    merged: tuple[_NormalizedWebResult, ...],
    *,
    bound_names: tuple[str, ...],
    query: str,
) -> dict:
    """Runs the REAL _apply_web_subject_consistency on the merged list.

    The split into survivors/dropped comes from the production gate itself
    (via a minimal LaneRequest), so the replay automatically reflects gate
    code changes (F3); per-item tiers are still computed for classification.
    """
    request = LaneRequest(
        lane="web",
        release_id="candidate-v2-20260819-r1",
        query_view="view:replay",
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=10000,
            max_results=48,
        ),
        query_text=f"{query} [lane=web]",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=48,
        bound_entity_ids=tuple(
            f"company-c-replay-{index:02d}" for index in range(len(bound_names))
        ),
        bound_entity_names=bound_names,
    )
    filtered = _apply_web_subject_consistency(results=merged, request=request)
    survivor_ids = {id(result) for result in filtered}

    anchor_qualifier = next(
        (
            qualifier
            for name in bound_names
            if (qualifier := _anchor_location_qualifier(name, query)) is not None
        ),
        None,
    )
    tiered = [
        (
            _web_result_relevance_tier(
                result=result,
                bound_entity_names=bound_names,
                anchor_qualifier=anchor_qualifier,
            ),
            index,
            result,
        )
        for index, result in enumerate(merged)
    ]
    kept = [e for e in tiered if e[0] in (0, 1)]
    related = [e for e in tiered if e[0] in (2, 3)]
    survivors = [e for e in tiered if id(e[2]) in survivor_ids]
    dropped = [e for e in tiered if id(e[2]) not in survivor_ids]
    return {
        "anchor_qualifier": anchor_qualifier,
        "tier_counts": {f"t{t}": sum(1 for e in tiered if e[0] == t) for t in range(6)},
        "kept_t01": len(kept),
        "related_t23": len(related),
        "backfill_branch": len(kept) < _WEB_SUBJECT_CONSISTENCY_FLOOR,
        "survivors": survivors,
        "dropped": dropped,
    }


def classify(tier: int, result: _NormalizedWebResult, spec: dict, member_forms) -> tuple[str, str]:
    if tier in (2, 3):
        # Full-name hit on a displayed member that lost the backfill
        # truncation (kept < floor): the strongest should-keep class.
        return "B+", "full-name hit on a displayed member, cut by backfill truncation"
    if tier == 4:
        return "A", "alias-only hit on a displayed member"
    full_text = _normalized_web_identity(f"{result.title} {result.snippet} {result.summary}")
    for name, forms in member_forms.items():
        if any(_web_identity_text_matches(form, full_text) for form in forms):
            return "B", f"summary/page names displayed member {name}"
    for alias in spec["off_set_gt_aliases"]:
        if _normalized_web_identity(alias) in full_text:
            return "C", f"names off-displayed GT entity alias {alias}"
    return "D", "no displayed-member or GT signal"


def replay_turn(cache: sqlite3.Connection, spec: dict) -> dict:
    trace = trace_turn(spec["session_marker"])
    outcomes = trace["web_outcomes"]

    # Logical views: pair each recorded bocha query with its relaxed serper
    # form (the trace records the exact per-provider query text).
    bocha_views = list(dict.fromkeys(o["view"] for o in outcomes if o["provider"] == "bocha-v1"))
    serper_views = {o["view"] for o in outcomes if o["provider"] == "serper-v1"}
    views = []
    missing = []
    normalize = _DualWebLaneAdapter._normalize_results
    for view in bocha_views:
        relaxed = _relaxed_serper_query(view)
        relaxed = relaxed if relaxed in serper_views else None
        provider_lists: dict[str, list] = {"bocha-v1": [], "serper-v1": []}
        raw, day = payload_for(cache, "bocha-v1", view)
        provider_lists["bocha-v1"] = raw
        if day == "MISS":
            missing.append(f"bocha|{view[:40]}")
        if relaxed is not None:
            raw, day = payload_for(cache, "serper-v1", relaxed)
            provider_lists["serper-v1"] = raw
            if day == "MISS":
                missing.append(f"serper|{relaxed[:40]}")
        views.append(
            (
                view,
                _merge_web_results_across_views(
                    [
                        tuple(normalize(provider_version=p, results=provider_lists[p]))
                        for p in ("bocha-v1", "serper-v1")
                    ]
                ),
            )
        )

    # The gated call saw exactly _SERVING_WEB_MAX_QUERY_VIEWS views; find all
    # ordered permutations whose merged count reproduces the trace `in=`.
    cap = _SERVING_WEB_MAX_QUERY_VIEWS
    admitted: list[tuple[tuple[str, ...], tuple[_NormalizedWebResult, ...]]] = []
    for perm in itertools.permutations(range(len(views)), cap):
        per_view = [views[index][1] for index in perm]
        ordered_views = tuple(views[index][0] for index in perm)
        discovery = tuple(
            position
            for position, text in enumerate(ordered_views[1:], start=1)
            if _is_brand_discovery_view(text)
        )
        merged = _discovery_front_merge(per_view, discovery)
        if len(merged) == spec["expected_in"]:
            admitted.append((ordered_views, merged))

    bound_names = tuple(spec["bound_names"])
    member_forms = {name: _web_identity_forms(name) for name in bound_names}
    query = trace["query_raw"]

    per_perm = []
    for ordered_views, merged in admitted:
        split = gate_split(merged, bound_names=bound_names, query=query)
        survivors = [
            {"tier": tier, "title": r.title[:80], "url": r.url,
             "providers": list(r.corroborating_provider_versions)}
            for tier, _, r in split["survivors"]
        ]
        dropped_items = []
        for tier, _, r in split["dropped"]:
            cls, why = classify(tier, r, spec, member_forms)
            dropped_items.append(
                {"tier": tier, "class": cls, "why": why, "title": r.title[:80],
                 "url": r.url, "snippet": r.snippet[:120],
                 "providers": list(r.corroborating_provider_versions)}
            )
        class_counts: dict[str, int] = {}
        for item in dropped_items:
            class_counts[item["class"]] = class_counts.get(item["class"], 0) + 1
        per_perm.append(
            {
                "views": list(ordered_views),
                "anchor_qualifier": split["anchor_qualifier"],
                "tier_counts": split["tier_counts"],
                "kept_t01": split["kept_t01"],
                "related_t23": split["related_t23"],
                "backfill_branch": split["backfill_branch"],
                "survivor_count": len(survivors),
                "survivors_match_trace": len(survivors) == spec["expected_retained"],
                "survivor_urls": sorted(s["url"] for s in survivors),
                "survivors": survivors,
                "dropped_class_counts": class_counts,
                "dropped_items": dropped_items,
            }
        )

    distinct_survivor_sets = {tuple(p["survivor_urls"]) for p in per_perm}
    class_spread: dict[str, list[int]] = {}
    for p in per_perm:
        for cls in ("A", "B+", "B", "C", "D"):
            class_spread.setdefault(cls, []).append(p["dropped_class_counts"].get(cls, 0))
    class_range = {
        cls: [min(values), max(values)] for cls, values in class_spread.items()
    } if per_perm else {}

    canonical = per_perm[0] if per_perm else None
    return {
        "query": query,
        "recorded_views": [v for v, _ in views],
        "missing_payloads": missing,
        "view_cap": cap,
        "admitted_permutations": len(admitted),
        "expected_in": spec["expected_in"],
        "expected_retained": spec["expected_retained"],
        "expected_gate_drop": spec["expected_gate_drop"],
        "distinct_survivor_sets": len(distinct_survivor_sets),
        "class_count_range_across_permutations": class_range,
        "canonical_permutation": canonical,
    }


def main() -> None:
    cache = scratch_cache()
    report = {name: replay_turn(cache, spec) for name, spec in TURNS.items()}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for name, result in report.items():
        print(
            f"{name}: admitted_perms={result['admitted_permutations']} "
            f"distinct_survivor_sets={result['distinct_survivor_sets']} "
            f"class_range={result['class_count_range_across_permutations']}"
        )
        canonical = result["canonical_permutation"]
        if canonical is not None:
            print(
                f"  canonical: survivors={canonical['survivor_count']} "
                f"(trace {result['expected_retained']}, match={canonical['survivors_match_trace']}) "
                f"backfill={canonical['backfill_branch']} "
                f"tiers={canonical['tier_counts']} classes={canonical['dropped_class_counts']} "
                f"anchor_qualifier={canonical['anchor_qualifier']}"
            )
        print(f"  missing={result['missing_payloads']}")


if __name__ == "__main__":
    main()
