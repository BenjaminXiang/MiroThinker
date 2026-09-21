#!/usr/bin/env python3
"""Canonical-v2 recall-regression harness (embedding-model-switch gate).

Runs every case through the production chat path (`POST /api/chat/stream`),
records per turn the answer, the citations, the per-lane candidate counts and
(when the serving instance writes one) the candidate layer, then writes one
machine-readable JSON so a pre-switch run and a post-switch run can be diffed
with `--diff`.

Why this exists: the replay gate (`replay_fix_round1.py`) locks the *behaviour*
contract (wording, clarification, citation shape, multi-turn anchoring) and
never looks at recall. A vector-lane regression shows up as "same answer shape,
fewer of the right companies/papers", which the replay gate cannot see. The
plan `docs/plans/2026-09-21-embedding-model-switch-plan.md` §4 makes recall
non-regression the blocking gate for the embedding swap; §4.3 requires the
baseline to be captured *before* the switch; §4.4 fixes the verdict rules
implemented in `--diff` below.

Legacy note: `scripts/eval_recall*.py` target the pre-canonical stack
(Milvus + Postgres + backend.deps) and cannot run against canonical-v2. This
harness talks only to the live HTTP surface plus the two opt-in debug sinks the
serving process itself writes (`CANONICAL_V2_TURN_DEBUG_DIR`, `TURN_TRACE_DIR`).

Usage — baseline / after-switch capture (one line each):

  cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
      --base-url http://127.0.0.1:18295 --label baseline-qwen3-8b-4096 \
      --cases ../../.agents/runs/embedding-model-switch/testset-cases.json \
              ../../.agents/runs/embedding-model-switch/semantic-probes.json \
      --turn-debug-dir /var/tmp/recall-295/turn-debug \
      --turn-trace-dir /var/tmp/recall-295/turn-trace \
      --out .agents/runs/embedding-model-switch/baseline.json

  (after the switch: same command, --label after-1024, --out after.json,
   pointed at the switched scratch instance)

Usage — verdict:

  uv run python scripts/eval_recall_canonical_v2.py \
      --diff .agents/runs/embedding-model-switch/baseline.json after.json

Diff exit codes: 0 = PASS, 1 = FAIL, 2 = REVIEW.

Candidate layer: the service streams per-lane *counts* only (`retrieval_done`)
and returns empty `evidence`/`structured_payload` (`canonical_v2_chat.py`
`_map_response`), so "is the GT entity in the candidate set?" cannot be answered
over HTTP alone. It is read from the per-turn debug dump
(`_maybe_dump_turn_debug`, `turn-debug-<session-suffix>-<turn>.json`), which
carries `recalled_handles` / `committed_names` / `evidence_items`. A run whose
instance has no debug dir still works but records
`candidate_layer.available=false`, and `--diff` then reports REVIEW because the
L1 entity check was not evaluated.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = "canonical-v2-recall-eval-v1"
SESSION_COOKIE = "miroflow_chat_session"
LOCAL_CITATION_TYPES = frozenset({"professor", "paper", "patent", "company"})
# §4.4: probe lane drop that forces human review, and the median-lane gate.
PROBE_LANE_REVIEW_DROP = 0.50
MEDIAN_LANE_FAIL_DROP = 0.30
_TAIL_BYTES = 512 * 1024


# --- cases -----------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _load_cases_file(path: Path) -> tuple[str, list[dict[str, Any]]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = payload["cases"]
        suite = str(payload.get("suite", "testset"))
        for case in cases:
            case.setdefault("suite", suite)
        return suite, cases
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        return _cases_from_workbook(path)
    raise SystemExit(
        f"unsupported --cases file {path}: expected a harness JSON or the "
        "test-set workbook (docs/测试集答案.xlsx)"
    )


def _cases_from_workbook(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Best-effort cases from the raw workbook, via the project's own parser.

    The derived entities are the parser's heuristics, not a reviewed GT; the
    committed `testset-cases.json` is the reviewed list the baseline protocol
    uses. This route exists so the harness can be pointed straight at the
    frozen workbook without a conversion step.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from parse_testset import parse_workbook
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit(f"cannot import parse_testset helpers: {exc}") from exc

    print(
        "WARNING: --cases points at the workbook; required entities are "
        "auto-derived by parse_testset heuristics and are NOT the reviewed GT. "
        "Use testset-cases.json for the frozen baseline.",
        file=sys.stderr,
    )
    cases: list[dict[str, Any]] = []
    turn_by_group: Counter[str] = Counter()
    for raw in parse_workbook(path):
        group = raw["turn_group"] or f"qid{raw['qid']}"
        turn_by_group[group] += 1
        derived = raw["required_entities"]
        cases.append(
            {
                "case_id": f"wb-qid{raw['qid']}",
                "group": group,
                "turn": turn_by_group[group],
                "kind": "labeled" if derived else "unlabeled",
                "query": raw["query"],
                "expected_entities": [
                    {"id": f"auto{i}", "label": name, "match": [name], "domain": ""}
                    for i, name in enumerate(derived)
                ],
                "forbidden_entities": [
                    {"id": f"forbid{i}", "label": name, "match": [name], "domain": ""}
                    for i, name in enumerate(raw["forbidden_entities"])
                ],
                "note": "auto-derived from 关键点; unreviewed",
                "suite": "testset",
            }
        )
    return "testset", cases


def _group_of(case: dict[str, Any]) -> str:
    return str(case.get("group") or case["case_id"])


def _slug(case_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z-]", "", case_id)[:7] or "case"


def _group_slugs(cases: Sequence[dict[str, Any]]) -> dict[str, str]:
    """One session slug per turn group: a group's turns must share a session or
    the follow-ups ("他/上述企业/这论文") lose their antecedent and the group's
    multi-turn semantics disappear."""
    slugs: dict[str, str] = {}
    for case in cases:
        slugs.setdefault(_group_of(case), _slug(case["case_id"]))
    return slugs


def _session_id(run_id: str, slug: str) -> str:
    session_id = f"session:chat:{run_id}-{slug}"
    if len(_session_suffix(session_id)) != len(run_id) + 1 + len(slug):
        raise SystemExit(
            f"run id {run_id!r} is too long: the serving process names its "
            "per-turn debug dump after the last 12 characters of the session id, "
            "so the group slug must survive that truncation"
        )
    return session_id


def _order_cases(cases: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    order: dict[str, int] = {}
    for case in cases:
        order.setdefault(_group_of(case), len(order))
    return sorted(cases, key=lambda c: (order[_group_of(c)], int(c["turn"])))


# --- HTTP / SSE ------------------------------------------------------------

def _post_turn(
    base_url: str, session_id: str, query: str, timeout: float
) -> dict[str, Any]:
    body = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"{SESSION_COOKIE}={session_id}",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    started = time.monotonic()
    raw = b""
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for chunk in response:
            raw += chunk
    elapsed = time.monotonic() - started
    return {
        "events": _parse_sse(raw.decode("utf-8", errors="replace")),
        "raw_bytes": len(raw),
        "seconds": round(elapsed, 2),
    }


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    name: str | None = None
    data: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].strip())
        elif not line.strip():
            if name is not None:
                payload: dict[str, Any] = {}
                if data:
                    try:
                        decoded = json.loads("\n".join(data))
                        if isinstance(decoded, dict):
                            payload = decoded
                    except json.JSONDecodeError:
                        payload = {"_unparsed": "\n".join(data)}
                events.append((name, payload))
            name, data = None, []
    return events


def _last(events: Sequence[tuple[str, dict[str, Any]]], wanted: str) -> dict[str, Any] | None:
    for name, payload in reversed(events):
        if name == wanted:
            return payload
    return None


# --- per-turn sinks --------------------------------------------------------

def _session_suffix(session_id: str) -> str:
    return session_id.rsplit(":", 1)[-1][:12] or "session"


def _read_turn_debug(
    root: Path, session_id: str, turn: int, query: str, *, deadline: float = 10.0
) -> dict[str, Any] | None:
    """Read the serving process's per-turn debug dump, waiting briefly for it.

    The dump is written inside the turn, before the `answer` event, so the file
    is normally already there; the wait only covers clock/order surprises.
    """
    path = root / f"turn-debug-{_session_suffix(session_id)}-{turn:02d}.json"
    stop = time.monotonic() + deadline
    while True:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                if payload.get("session_id") == session_id and payload.get("query") == query:
                    return payload
        if time.monotonic() >= stop:
            return None
        time.sleep(0.25)


def _tail_records(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_BYTES))
            blob = handle.read()
        if size > _TAIL_BYTES:
            blob = blob.split(b"\n", 1)[-1]
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in blob.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            records.append(decoded)
    return records


def _read_trace_record(
    root: Path, session_id: str, turn: int
) -> dict[str, Any] | None:
    """The turn-trace journal record for one turn (append-only JSONL per UTC day)."""
    today = datetime.now(UTC).date()
    for day in (today, today - timedelta(days=1)):
        path = root / f"{day.isoformat()}.jsonl"
        if not path.exists():
            continue
        for record in reversed(_tail_records(path)):
            if (
                record.get("session_id") == session_id
                and record.get("turn_ordinal") == turn
            ):
                return record
    return None


# --- scoring ---------------------------------------------------------------

def _entity_hit(entity: dict[str, Any], blobs: Iterable[str]) -> bool:
    needles = [
        _normalize(alias)
        for alias in (entity.get("match") or [entity.get("label") or entity["id"]])
    ]
    needles = [needle for needle in needles if needle]
    if not needles:
        return False
    for blob in blobs:
        normalized = _normalize(blob)
        if any(needle in normalized for needle in needles):
            return True
    return False


def _candidate_names(debug: dict[str, Any] | None, web_items: Sequence[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    if debug:
        for handle in debug.get("recalled_handles") or ():
            if isinstance(handle, dict) and handle.get("display_name"):
                names.append(str(handle["display_name"]))
        for name in debug.get("committed_names") or ():
            names.append(str(name))
        for slot in debug.get("protected_slots") or ():
            if isinstance(slot, dict) and slot.get("value"):
                names.append(str(slot["value"]))
    for item in web_items:
        for key in ("title", "label"):
            if item.get(key):
                names.append(str(item[key]))
        if item.get("url"):
            names.append(str(item["url"]))
    return names


def _score_turn(
    case: dict[str, Any],
    *,
    answer_text: str,
    citation_blobs: Sequence[str],
    candidate_blobs: Sequence[str] | None,
) -> dict[str, Any]:
    entities: dict[str, dict[str, Any]] = {}
    for entity in case.get("expected_entities") or ():
        answer_hit = _entity_hit(entity, [answer_text])
        citation_hit = _entity_hit(entity, citation_blobs)
        entities[entity["id"]] = {
            "label": entity.get("label", entity["id"]),
            "answer": answer_hit,
            "citations": citation_hit,
            "answer_or_citations": answer_hit or citation_hit,
            "candidate": (
                None if candidate_blobs is None else _entity_hit(entity, candidate_blobs)
            ),
        }
    forbidden = [
        entity["id"]
        for entity in case.get("forbidden_entities") or ()
        if _entity_hit(entity, [answer_text])
    ]
    expected = list(entities)
    answer_all = bool(expected) and all(
        entities[eid]["answer_or_citations"] for eid in expected
    )
    candidate_all: bool | None = None
    if expected and candidate_blobs is not None:
        candidate_all = all(entities[eid]["candidate"] for eid in expected)
    return {
        "entities": entities,
        "forbidden_present": forbidden,
        "answer_all_entities": answer_all,
        "candidate_all_entities": candidate_all,
    }


# --- one turn --------------------------------------------------------------

def _run_case(
    case: dict[str, Any],
    *,
    base_url: str,
    session_id: str,
    run_id: str,
    timeout: float,
    turn_debug_dir: Path | None,
    turn_trace_dir: Path | None,
) -> dict[str, Any]:
    query = str(case["query"])
    record: dict[str, Any] = {
        "case_id": case["case_id"],
        "suite": case.get("suite", "testset"),
        "group": case.get("group"),
        "turn": int(case["turn"]),
        "kind": case.get("kind", "unlabeled"),
        "query": query,
        "session_id": session_id,
        "run_id": run_id,
        "note": case.get("note", ""),
    }
    try:
        response = _post_turn(base_url, session_id, query, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        record.update(
            {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "seconds": None,
                "sse_events": {},
                "answer": None,
                "lanes": {},
                "lanes_trace": {},
                "web": {},
                "candidate_layer": {"available": False, "source": None},
                "hits": {
                    "entities": {},
                    "forbidden_present": [],
                    "answer_all_entities": False,
                    "candidate_all_entities": None,
                },
            }
        )
        return record

    events = response["events"]
    counts = Counter(name for name, _ in events)
    answer = _last(events, "answer") or {}
    retrieval = _last(events, "retrieval_done") or {}
    web_items = retrieval.get("web_items") or []

    lanes: dict[str, dict[str, Any]] = {}
    for lane in retrieval.get("lanes") or ():
        if not isinstance(lane, dict) or not lane.get("lane"):
            continue
        name = str(lane["lane"])
        entry = lanes.setdefault(name, {"candidates": 0, "status": lane.get("status")})
        entry["candidates"] += int(lane.get("candidates") or 0)

    debug = (
        _read_turn_debug(turn_debug_dir, session_id, int(case["turn"]), query)
        if turn_debug_dir is not None
        else None
    )
    trace = (
        _read_trace_record(turn_trace_dir, session_id, int(case["turn"]))
        if turn_trace_dir is not None
        else None
    )

    citations = [
        {
            "type": str(citation.get("type", "")),
            "id": str(citation.get("id", "")),
            "label": str(citation.get("label", "")),
            "url": citation.get("url"),
        }
        for citation in answer.get("citations") or ()
        if isinstance(citation, dict)
    ]
    nature = Counter(
        "web" if citation["type"] == "web" else "local" for citation in citations
    )
    citation_blobs = [
        blob
        for citation in citations
        for blob in (citation["label"], citation["url"] or "", citation["id"])
        if blob
    ]
    answer_text = str(answer.get("answer_text") or "")

    candidate_blobs: list[str] | None = None
    if debug is not None:
        candidate_blobs = _candidate_names(debug, web_items)

    hits = _score_turn(
        case,
        answer_text=answer_text,
        citation_blobs=citation_blobs,
        candidate_blobs=candidate_blobs,
    )

    trace_lanes = {
        str(name): {
            "in": int(counts_.get("in") or 0),
            "retained": int(counts_.get("retained") or 0),
            "filtered": int(counts_.get("filtered") or 0),
        }
        for name, counts_ in ((trace or {}).get("lanes") or {}).items()
        if isinstance(counts_, dict)
    }
    web_outcomes = [
        outcome for outcome in ((trace or {}).get("web_outcomes") or ())
        if isinstance(outcome, dict)
    ]
    record.update(
        {
            "status": "ok",
            "error": None,
            "seconds": response["seconds"],
            "raw_bytes": response["raw_bytes"],
            "sse_events": dict(sorted(counts.items())),
            "answer": {
                "query_type": answer.get("query_type"),
                "answer_style": answer.get("answer_style"),
                "understood_subject": answer.get("understood_subject"),
                "answer_chars": len(answer_text),
                "text": answer_text,
                "citations": citations,
                "citation_nature": {
                    "local": nature.get("local", 0),
                    "web": nature.get("web", 0),
                },
            },
            "lanes": {name: lanes[name] for name in sorted(lanes)},
            "lanes_trace": {name: trace_lanes[name] for name in sorted(trace_lanes)},
            "web": {
                "items": len(web_items),
                "attempted": sum(int(o.get("attempted") or 0) for o in web_outcomes),
                "cache_hit": sum(int(o.get("cache_hit") or 0) for o in web_outcomes),
                "errored": sum(int(o.get("errored") or 0) for o in web_outcomes),
                "timed_out": sum(int(o.get("timed_out") or 0) for o in web_outcomes),
                "degradation": None if trace is None else trace.get("degradation"),
            },
            "candidate_layer": {
                "available": debug is not None,
                "source": "turn-debug" if debug is not None else None,
                "recalled_handles": len((debug or {}).get("recalled_handles") or ()),
                "handles_local": sum(
                    1
                    for handle in ((debug or {}).get("recalled_handles") or ())
                    if isinstance(handle, dict) and handle.get("kind") == "canonical"
                ),
                "handles_web": sum(
                    1
                    for handle in ((debug or {}).get("recalled_handles") or ())
                    if isinstance(handle, dict) and handle.get("kind") == "web"
                ),
                "evidence_total": ((debug or {}).get("evidence_items") or {}).get("total"),
                "evidence_by_lane": ((debug or {}).get("evidence_items") or {}).get(
                    "by_lane"
                ),
                "candidate_names": len(candidate_blobs or ()),
            },
            "hits": hits,
        }
    )
    return record


# --- aggregates ------------------------------------------------------------

def _vector_candidates(record: dict[str, Any]) -> int | None:
    lanes = record.get("lanes") or {}
    if "vector" in lanes:
        return int(lanes["vector"].get("candidates") or 0)
    trace_lanes = record.get("lanes_trace") or {}
    if "vector" in trace_lanes:
        return int(trace_lanes["vector"].get("in") or 0)
    return None


def _aggregate(records: Sequence[dict[str, Any]], wall_seconds: float) -> dict[str, Any]:
    by_kind: Counter[str] = Counter(record["kind"] for record in records)
    vectors = [
        value
        for value in (_vector_candidates(record) for record in records)
        if value is not None
    ]
    local = sum(
        int((record.get("answer") or {}).get("citation_nature", {}).get("local", 0))
        for record in records
    )
    web = sum(
        int((record.get("answer") or {}).get("citation_nature", {}).get("web", 0))
        for record in records
    )
    expected_total = sum(
        len((record.get("hits") or {}).get("entities") or {}) for record in records
    )
    answer_hits = sum(
        1
        for record in records
        for entity in ((record.get("hits") or {}).get("entities") or {}).values()
        if entity.get("answer_or_citations")
    )
    candidate_checked = sum(
        1
        for record in records
        for entity in ((record.get("hits") or {}).get("entities") or {}).values()
        if entity.get("candidate") is not None
    )
    candidate_hits = sum(
        1
        for record in records
        for entity in ((record.get("hits") or {}).get("entities") or {}).values()
        if entity.get("candidate")
    )
    return {
        "cases": len(records),
        "cases_by_kind": dict(sorted(by_kind.items())),
        "cases_with_candidate_layer": sum(
            1 for record in records if (record.get("candidate_layer") or {}).get("available")
        ),
        "errors": sum(1 for record in records if record.get("status") != "ok"),
        "expected_entities": expected_total,
        "entities_hit_in_answer_or_citations": answer_hits,
        "entities_checked_in_candidate_layer": candidate_checked,
        "entities_hit_in_candidate_layer": candidate_hits,
        "cases_all_entities_hit_answer": sum(
            1
            for record in records
            if (record.get("hits") or {}).get("answer_all_entities")
        ),
        "vector_candidates": {
            "n": len(vectors),
            "median": statistics.median(vectors) if vectors else None,
            "min": min(vectors) if vectors else None,
            "max": max(vectors) if vectors else None,
        },
        "citation_nature_totals": {"local": local, "web": web},
        "turns_with_llm_synthesis": sum(
            1
            for record in records
            if (record.get("answer") or {}).get("answer_style") == "llm_synthesized"
        ),
        "web_provider_attempts": sum(
            int((record.get("web") or {}).get("attempted") or 0) for record in records
        ),
        "web_provider_cache_hits": sum(
            int((record.get("web") or {}).get("cache_hit") or 0) for record in records
        ),
        "wall_seconds": round(wall_seconds, 1),
    }


def _capture(args: argparse.Namespace) -> int:
    cases: list[dict[str, Any]] = []
    for path in args.cases:
        _, loaded = _load_cases_file(Path(path))
        cases.extend(loaded)
    cases = _order_cases(cases)
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        cases = [case for case in cases if case["case_id"] in wanted]
        if not cases:
            raise SystemExit(f"--only matched no case: {sorted(wanted)}")

    run_id = args.run_id or secrets.token_hex(2)
    slugs = _group_slugs(cases)
    sessions = {group: _session_id(run_id, slug) for group, slug in slugs.items()}
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    print(
        f"target={args.base_url} label={args.label} cases={len(cases)} "
        f"groups={len(slugs)} run_id={run_id} "
        f"turn_debug_dir={args.turn_debug_dir} turn_trace_dir={args.turn_trace_dir}",
        flush=True,
    )
    for index, case in enumerate(cases, start=1):
        session_id = sessions[_group_of(case)]
        record = _run_case(
            case,
            base_url=args.base_url,
            session_id=session_id,
            run_id=run_id,
            timeout=args.timeout,
            turn_debug_dir=args.turn_debug_dir,
            turn_trace_dir=args.turn_trace_dir,
        )
        records.append(record)
        vector = _vector_candidates(record)
        hits = (record.get("hits") or {}).get("entities") or {}
        hit_text = (
            ",".join(
                f"{entity['label']}={'Y' if entity['answer_or_citations'] else 'n'}"
                for entity in hits.values()
            )
            or "-"
        )
        print(
            f"[{index}/{len(cases)}] {record['case_id']} {record['kind']} "
            f"{record.get('seconds')}s vector={vector} cand="
            f"{'yes' if (record.get('candidate_layer') or {}).get('available') else 'no'} "
            f"hits[{hit_text}] {record.get('error') or ''}".rstrip(),
            flush=True,
        )
    wall = time.monotonic() - started

    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "canonical-v2-recall-eval",
        "label": args.label,
        "base_url": args.base_url,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "run_id": run_id,
        "cases_source": [str(path) for path in args.cases],
        "candidate_layer_sources": {
            "turn_debug_dir": None if args.turn_debug_dir is None else str(args.turn_debug_dir),
            "turn_trace_dir": None if args.turn_trace_dir is None else str(args.turn_trace_dir),
        },
        "aggregate": _aggregate(records, wall),
        "cases": records,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    aggregate = payload["aggregate"]
    print(
        f"\nwrote {out} ({len(records)} cases, {wall:.0f}s)\n"
        f"  answer-layer entity hits {aggregate['entities_hit_in_answer_or_citations']}"
        f"/{aggregate['expected_entities']}, "
        f"candidate-layer {aggregate['entities_hit_in_candidate_layer']}"
        f"/{aggregate['entities_checked_in_candidate_layer']}\n"
        f"  vector candidates median={aggregate['vector_candidates']['median']} "
        f"n={aggregate['vector_candidates']['n']}\n"
        f"  citations local={aggregate['citation_nature_totals']['local']} "
        f"web={aggregate['citation_nature_totals']['web']}\n"
        f"  llm_synthesized turns={aggregate['turns_with_llm_synthesis']} "
        f"web_provider_attempts={aggregate['web_provider_attempts']} "
        f"cache_hits={aggregate['web_provider_cache_hits']}",
        flush=True,
    )
    return 0 if aggregate["errors"] == 0 else 1


# --- diff / verdict --------------------------------------------------------

def _median_vector(records: Sequence[dict[str, Any]]) -> float | None:
    values = [
        value for value in (_vector_candidates(record) for record in records) if value is not None
    ]
    return statistics.median(values) if values else None


def _drop(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before == 0:
        return None
    return (before - after) / before


def _entity_rows(
    before: dict[str, Any], after: dict[str, Any]
) -> list[tuple[str, str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str, str]] = []
    before_entities = (before.get("hits") or {}).get("entities") or {}
    after_entities = (after.get("hits") or {}).get("entities") or {}
    for entity_id, before_entity in before_entities.items():
        after_entity = after_entities.get(entity_id)
        if after_entity is None:
            rows.append((entity_id, "?", "?", "?", "missing-in-after"))
            continue
        flags: list[str] = []
        if before_entity.get("answer_or_citations") and not after_entity.get("answer_or_citations"):
            flags.append("ANSWER hit->miss")
        if before_entity.get("candidate") and after_entity.get("candidate") is False:
            flags.append("CANDIDATE hit->miss")
        rows.append(
            (
                entity_id,
                "Y" if before_entity.get("answer_or_citations") else "n",
                "Y" if after_entity.get("answer_or_citations") else "n",
                "Y" if before_entity.get("candidate") else "n",
                "Y" if after_entity.get("candidate") else "n",
                " ".join(flags) or "-",
            )
        )
    return rows


def _diff(args: argparse.Namespace) -> int:
    first = json.loads(Path(args.diff[0]).read_text(encoding="utf-8"))
    second = json.loads(Path(args.diff[1]).read_text(encoding="utf-8"))
    a_records = {record["case_id"]: record for record in first["cases"]}
    b_records = {record["case_id"]: record for record in second["cases"]}
    shared = [case_id for case_id in a_records if case_id in b_records]
    only_a = [case_id for case_id in a_records if case_id not in b_records]
    only_b = [case_id for case_id in b_records if case_id not in a_records]

    print(
        f"A = {args.diff[0]} label={first.get('label')} base_url={first.get('base_url')}\n"
        f"B = {args.diff[1]} label={second.get('label')} base_url={second.get('base_url')}\n"
        f"shared cases={len(shared)} only-in-A={len(only_a)} only-in-B={len(only_b)}"
    )
    print(
        "\ncase_id    suite     kind           ansA ansB candA candB vecA  vecB  d_vec%  vec_id"
    )
    print("-" * 96)
    for case_id in shared:
        a, b = a_records[case_id], b_records[case_id]
        va, vb = _vector_candidates(a), _vector_candidates(b)
        delta = _drop(va, vb)
        print(
            f"{case_id:<10} {a.get('suite',''):<9} {a.get('kind',''):<14} "
            f"{'Y' if (a.get('hits') or {}).get('answer_all_entities') else ('n' if (a.get('hits') or {}).get('entities') else '-'):<4} "
            f"{'Y' if (b.get('hits') or {}).get('answer_all_entities') else ('n' if (b.get('hits') or {}).get('entities') else '-'):<4} "
            f"{'Y' if (a.get('candidate_layer') or {}).get('available') else '-':<5} "
            f"{'Y' if (b.get('candidate_layer') or {}).get('available') else '-':<5} "
            f"{va if va is not None else '-':<5} {vb if vb is not None else '-':<5} "
            f"{'%+.0f%%' % (-100 * delta) if delta is not None else '-':<7} "
            f"{'<==' if delta is not None and delta > 0 else ''}"
        )

    fails: list[str] = []
    reviews: list[str] = []

    # Rule 1 (plan §4.4.1): a test-set turn that was a hit must not become a miss.
    for case_id in shared:
        a, b = a_records[case_id], b_records[case_id]
        if a.get("suite") != "testset":
            continue
        kind = a.get("kind")
        if kind not in {"labeled", "concept"}:
            continue
        lenient = kind == "concept" and args.lenient_concepts
        for row in _entity_rows(a, b):
            entity_id, ans_a, ans_b, cand_a, cand_b, flag = row
            if flag == "-":
                continue
            label = ((a.get("hits") or {}).get("entities") or {}).get(entity_id, {}).get(
                "label", entity_id
            )
            message = f"rule1({kind}) {case_id} [{label}] {flag}"
            if lenient:
                reviews.append(message + " (concept, --lenient-concepts)")
            else:
                fails.append(message)

    # Rule 2 (plan §4.4.2): probes — GT lost, or a >50% vector-lane drop.
    for case_id in shared:
        a, b = a_records[case_id], b_records[case_id]
        if a.get("suite") != "probes":
            continue
        for row in _entity_rows(a, b):
            entity_id, _, _, _, _, flag = row
            if flag == "-":
                continue
            label = ((a.get("hits") or {}).get("entities") or {}).get(entity_id, {}).get(
                "label", entity_id
            )
            reviews.append(f"rule2(probe {a.get('kind')}) {case_id} [{label}] {flag}")
        delta = _drop(_vector_candidates(a), _vector_candidates(b))
        if delta is not None and delta > PROBE_LANE_REVIEW_DROP:
            reviews.append(
                f"rule2(probe) {case_id} vector candidates "
                f"{_vector_candidates(a)} -> {_vector_candidates(b)} "
                f"({-100 * delta:.0f}% drop)"
            )

    # Rule 3 (plan §4.4.3): median vector-lane drop.
    median_a = _median_vector([a_records[case_id] for case_id in shared])
    median_b = _median_vector([b_records[case_id] for case_id in shared])
    median_delta = _drop(median_a, median_b)
    if median_delta is not None and median_delta > MEDIAN_LANE_FAIL_DROP:
        fails.append(
            f"rule3 median vector candidates {median_a} -> {median_b} "
            f"({-100 * median_delta:.0f}% drop > {MEDIAN_LANE_FAIL_DROP:.0%})"
        )

    # Coverage guards: the L1 entity check must have been evaluated on both sides.
    for case_id in shared:
        a, b = a_records[case_id], b_records[case_id]
        if not (a.get("candidate_layer") or {}).get("available"):
            reviews.append(f"coverage {case_id} candidate layer unavailable in A")
        elif not (b.get("candidate_layer") or {}).get("available"):
            reviews.append(f"coverage {case_id} candidate layer unavailable in B")
    for case_id in only_a:
        reviews.append(f"coverage {case_id} present in A only")
    for case_id in only_b:
        reviews.append(f"coverage {case_id} present in B only")

    aggregate_a, aggregate_b = first["aggregate"], second["aggregate"]
    print("\naggregate           A                B                delta")
    print("-" * 72)
    for label, key in (
        ("cases", "cases"),
        ("answer entity hits", "entities_hit_in_answer_or_citations"),
        ("expected entities", "expected_entities"),
        ("cases all-hit (answer)", "cases_all_entities_hit_answer"),
        ("candidate-layer hits", "entities_hit_in_candidate_layer"),
        ("candidate-layer checked", "entities_checked_in_candidate_layer"),
        ("llm-synthesized turns", "turns_with_llm_synthesis"),
        ("citation local", "citation_nature_totals"),
        ("citation web", "citation_nature_totals"),
    ):
        if key == "citation_nature_totals":
            value_a = aggregate_a[key]["local" if "local" in label else "web"]
            value_b = aggregate_b[key]["local" if "local" in label else "web"]
        else:
            value_a = aggregate_a.get(key)
            value_b = aggregate_b.get(key)
        print(f"{label:<20} {str(value_a):<16} {str(value_b):<16} {_fmt_delta(value_a, value_b)}")
    vector_a, vector_b = aggregate_a["vector_candidates"], aggregate_b["vector_candidates"]
    print(
        f"{'vector median (all)':<20} {str(vector_a['median']):<16} {str(vector_b['median']):<16} "
        f"{_fmt_delta(vector_a['median'], vector_b['median'])}"
    )
    print(
        f"{'vector median (shared)':<20} {str(median_a):<16} {str(median_b):<16} "
        f"{_fmt_delta(median_a, median_b)}"
    )
    for suite in ("testset", "probes"):
        suite_a = _median_vector(
            [a_records[case_id] for case_id in shared if a_records[case_id].get("suite") == suite]
        )
        suite_b = _median_vector(
            [b_records[case_id] for case_id in shared if b_records[case_id].get("suite") == suite]
        )
        print(
            f"{'vector median (' + suite + ')':<20} {str(suite_a):<16} {str(suite_b):<16} "
            f"{_fmt_delta(suite_a, suite_b)}"
        )
    print(
        f"{'vector coverage (n)':<20} {str(vector_a['n']):<16} {str(vector_b['n']):<16} "
    )
    print(
        f"{'local/web mix':<20} "
        f"{aggregate_a['citation_nature_totals']['local']}/{aggregate_a['citation_nature_totals']['web']:<11}"
        f"{aggregate_b['citation_nature_totals']['local']}/{aggregate_b['citation_nature_totals']['web']:<11}"
    )
    print(
        f"{'wall seconds':<20} {str(aggregate_a['wall_seconds']):<16} "
        f"{str(aggregate_b['wall_seconds']):<16}"
    )

    verdict = "PASS" if not fails else "FAIL"
    if verdict == "PASS" and reviews:
        verdict = "REVIEW"
    print(f"\nVERDICT: {verdict} — {len(fails)} fail-level, {len(reviews)} review-level")
    for entry in fails:
        print(f"  FAIL   {entry}")
    for entry in reviews:
        print(f"  REVIEW {entry}")
    if verdict == "PASS":
        print("  (no labeled turn lost an entity, no probe lost its GT or >50% of its vector candidates, median vector lane within 30%)")
    return {"PASS": 0, "FAIL": 1, "REVIEW": 2}[verdict]


def _fmt_delta(before: Any, after: Any) -> str:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return f"{after - before:+g}"
    return ""


# --- CLI -------------------------------------------------------------------

def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Canonical-v2 recall-regression harness: capture per-case recall "
            "evidence from the live chat path, or diff two captures."
        )
    )
    parser.add_argument("--base-url", help="serving entry, e.g. http://127.0.0.1:18295")
    parser.add_argument(
        "--cases",
        nargs="+",
        help="case files (harness JSON, or docs/测试集答案.xlsx)",
    )
    parser.add_argument("--out", help="capture JSON to write")
    parser.add_argument("--label", default="unlabeled", help="free-text run label (pack/model)")
    parser.add_argument(
        "--only",
        help=(
            "comma-separated case ids; a group's earlier turns are not replayed, "
            "so referent-dependent follow-ups lose their antecedent"
        ),
    )
    parser.add_argument("--run-id", help="session prefix override (default: random 4 hex)")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument(
        "--turn-debug-dir",
        type=Path,
        help="serving instance's CANONICAL_V2_TURN_DEBUG_DIR (candidate layer)",
    )
    parser.add_argument(
        "--turn-trace-dir",
        type=Path,
        help="serving instance's TURN_TRACE_DIR (lane in/retained/filtered, web outcomes)",
    )
    parser.add_argument(
        "--lenient-concepts",
        action="store_true",
        help=(
            "downgrade 关键点 concept-string regressions from FAIL to REVIEW "
            "(the strings are answer wording, not KB entities)"
        ),
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("A.json", "B.json"),
        help="print the per-case table, the aggregate deltas and the §4.4 verdict",
    )
    args = parser.parse_args(argv)
    if args.diff is None and not (args.base_url and args.cases and args.out):
        parser.error("--base-url, --cases and --out are required unless --diff is used")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.diff is not None:
        return _diff(args)
    return _capture(args)


if __name__ == "__main__":
    sys.exit(main())
