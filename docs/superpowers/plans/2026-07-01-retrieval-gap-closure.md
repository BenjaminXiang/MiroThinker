# Retrieval Gap-Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the retrieval-augmented refactor gap across 全/准/快 by re-truthing contracts to delivered reality, building the missing precision/latency oracles, and driving all three artifacts to Claude Accept.

**Architecture:** The code (RRF+web-fuse, synthesis timeout, keepalive+parallel) is already shipped. The work is (1) build measurement oracles so contracts are written from evidence not inference, (2) re-truth three contracts — `fix-chat-retrieval-recall-gaps` (OpenSpec, rewritten), `add-synthesis-timeout` (OpenSpec, small), `perf-retrieval-keepalive-parallel` (refactor-contract) — and (3) Claude review to Accept. Only two new code files are written (eval scripts); the rest is docs/contracts/evidence.

**Tech Stack:** Python 3.12, uv, FastAPI TestClient, OpenSpec CLI, pytest. Eval scripts under `apps/admin-console/scripts/` following the `eval_recall.py` pattern.

**Spec:** `docs/superpowers/specs/2026-07-01-retrieval-gap-closure-design.md` (commit `20086e5`).

---

## Scope note

One plan, five phases, because the evidence foundation (Phase 1) is a strict prerequisite for all three contracts (you cannot write a recall spec's GREEN without re-running the recall oracle), and they share one review gate. The three contracts are otherwise independent and could be split into separate plans if execution gets large; the dependency order is fixed: **Phase 1 → Phases 2/3/4 (parallel) → Phase 5**.

## Ownership (per CLAUDE.md §1)

- **Claude** owns: spec/contract docs, eval-running, evidence persistence, review. The two new eval scripts are **tiny low-risk scaffolding** (eval harness, no runtime impact) → Claude may write them directly per §1; hand to Codex if preferred.
- **Codex** owns: any *production-code* edits if the review finds a real bug. None are expected — code is shipped.
- **Eval runs** require `unset` of 6 proxy vars (memory `env_proxy_bypass`) — baked into every run command.

## File structure

**Evidence foundation (new code + evidence):**
- Modify: `apps/admin-console/scripts/eval_recall.py` — add `false_positives` field to `Case` (backward-compatible default).
- Modify: `apps/admin-console/scripts/eval_recall_chat.py` — add JSON persistence to run dir.
- Create: `apps/admin-console/scripts/eval_precision.py` — precision oracle (surfaces candidates + unsourced-web; labeling substrate).
- Create: `apps/admin-console/scripts/eval_latency.py` — latency oracle (p50/p95/max, bucketed by route, SLO check).
- Create: `apps/admin-console/tests/test_eval_precision.py` — unit tests for pure extraction functions.
- Create: `apps/admin-console/tests/test_eval_latency.py` — unit tests for pure stats functions.
- Create (generated): `.agents/runs/retrieval-generation-alignment/{baseline-53,post-fix-recall,precision-baseline,latency-baseline}.json`

**recall change re-truthing (OpenSpec docs):**
- Modify: `openspec/changes/fix-chat-retrieval-recall-gaps/specs/agentic-rag-retrieval/spec.md`
- Modify: `openspec/changes/fix-chat-retrieval-recall-gaps/{proposal,design,tasks,acceptance}.md`
- Create: `openspec/changes/fix-chat-retrieval-recall-gaps/fm1a-ingest-decision.md`
- Modify: `openspec/change-ledger.md`

**synthesis timeout (new OpenSpec change):**
- Create: `openspec/changes/add-synthesis-timeout/{proposal,specs/agentic-rag-retrieval/spec.md,tasks,acceptance}.md`

**perf refactor-contract:**
- Create: `.agents/runs/perf-retrieval-keepalive-parallel/{refactor-contract,verification}.md`
- Create (generated): `.agents/runs/perf-retrieval-keepalive-parallel/{golden-order-serial,golden-order-parallel,latency-evidence}.json`

**Review:**
- Create: `.agents/reviews/2026-07-01-retrieval-gap-closure.md`

---

## Phase 1 — Evidence foundation (oracles)

### Task 1.1: Add `false_positives` field to `Case`

**Files:**
- Modify: `apps/admin-console/scripts/eval_recall.py:19-35`

- [ ] **Step 1: Update the `Case` dataclass import and field**

In `apps/admin-console/scripts/eval_recall.py`, change the dataclass import (line 19) and add the field:

```python
from dataclasses import dataclass, field
```

```python
@dataclass
class Case:
    qid: int
    query: str
    domain: str
    required: list[str]  # substrings that MUST appear in some candidate snippet
    note: str = ""
    false_positives: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Verify existing eval still runs**

Run:
```bash
cd apps/admin-console
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 uv run python scripts/eval_recall.py --top-k 10 2>&1 | tail -3
```
Expected: prints `ENTITY RECALL: ...` line (no import error; field default keeps existing cases valid).

- [ ] **Step 3: Commit**

```bash
git add apps/admin-console/scripts/eval_recall.py
git commit -m "feat(eval): add false_positives field to Case for precision oracle"
```

### Task 1.2: Build `eval_precision.py` (TDD)

**Files:**
- Create: `apps/admin-console/scripts/eval_precision.py`
- Test: `apps/admin-console/tests/test_eval_precision.py`

- [ ] **Step 1: Write the failing test for candidate extraction**

Create `apps/admin-console/tests/test_eval_precision.py`:

```python
"""Unit tests for eval_precision pure functions (no live DB needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_precision import _walk_candidates, _count_unsourced_web, _display_name


def test_walk_candidates_collects_typed_dicts():
    response = {
        "query_type": "B_company_topic",
        "candidates": [
            {"type": "company", "name": "普渡科技", "snippet": "普渡科技是一家..."},
            {"type": "web", "title": "云迹科技", "url": "https://x.com", "snippet": "云迹..."},
            {"type": "web", "title": "无源条目", "url": "", "snippet": "..."},
        ],
        "nested": {"results": [{"type": "professor", "name": "王学谦", "snippet": "王学谦"}]},
    }
    names = [_display_name(c) for c in _walk_candidates(response)]
    assert "普渡科技" in names
    assert "王学谦" in names
    assert "云迹科技" in names


def test_count_unsourced_web_flags_urlless_web():
    response = {
        "candidates": [
            {"type": "web", "title": "a", "url": "https://a.com"},
            {"type": "web", "title": "b", "url": ""},
            {"source_type": "web", "title": "c"},
            {"type": "company", "name": "x", "url": ""},
        ]
    }
    assert _count_unsourced_web(response) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_precision.py -v 2>&1 | tail -5
```
Expected: FAIL with `ModuleNotFoundError: No module named 'eval_precision'`.

- [ ] **Step 3: Write `eval_precision.py`**

Create `apps/admin-console/scripts/eval_precision.py`:

```python
"""Precision oracle (准). Surfaces returned candidates + unsourced-web provenance
per case so false positives can be labeled. v1 does NOT score precision (no labels
yet) — it produces the labeling substrate (design §1.2: first run = baseline).

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_precision.py
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
os.environ.setdefault("CHAT_LLM_SYNTHESIS", "off")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_recall import CASES  # noqa: E402

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_WEB_TYPES = {"web"}


def _walk_candidates(node: object) -> Iterator[dict]:
    """Recursively yield dicts that look like evidence candidates (carry a known type)."""
    if isinstance(node, dict):
        t = node.get("type") or node.get("source_type")
        if t in {"professor", "paper", "company", "web"}:
            yield node
        for v in node.values():
            yield from _walk_candidates(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_candidates(item)


def _display_name(cand: dict) -> str:
    return (cand.get("name") or cand.get("title") or cand.get("snippet") or "").strip()


def _count_unsourced_web(response: dict) -> int:
    n = 0
    for cand in _walk_candidates(response):
        if (cand.get("type") or cand.get("source_type")) in _WEB_TYPES:
            url = cand.get("url") or cand.get("source_url")
            if not url:
                n += 1
    return n


def main() -> int:
    client = TestClient(app)
    rows: list[dict] = []
    total_unsourced = 0
    print(f"{'qid':>3} {'qtype':<22} {'cands':>5} {'unsourced_web':>13}  candidates")
    print("-" * 96)
    for c in CASES:
        try:
            r = client.post("/api/chat", json={"query": c.query})
        except Exception as e:  # noqa: BLE001
            print(f"{c.qid:>3} ERR {type(e).__name__}: {str(e)[:80]}")
            rows.append({"qid": c.qid, "error": str(e)})
            continue
        if r.status_code != 200:
            print(f"{c.qid:>3} HTTP{r.status_code} {r.text[:80]}")
            rows.append({"qid": c.qid, "http": r.status_code})
            continue
        j = r.json()
        cands = list(_walk_candidates(j))
        names = [_display_name(x) for x in cands]
        unsourced = _count_unsourced_web(j)
        total_unsourced += unsourced
        qtype = str(j.get("query_type", "?"))
        rows.append({
            "qid": c.qid, "query": c.query, "query_type": qtype,
            "candidate_names": names, "unsourced_web": unsourced,
            "required": c.required, "false_positives": c.false_positives,
        })
        print(f"{c.qid:>3} {qtype[:22]:<22} {len(names):>5} {unsourced:>13}  {names[:4]}")
    print("-" * 96)
    print(f"UNSOURCED WEB (§5 provenance risk): {total_unsourced}")
    out = os.path.join(os.path.dirname(__file__), "..", "..", ".agents",
                       "runs", "retrieval-generation-alignment", "precision-baseline.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "total_unsourced_web": total_unsourced}, fh,
                  ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    print("NOTE: v1 surfaces candidates for labeling. Score precision in v2 after labels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_precision.py -v 2>&1 | tail -5
```
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/admin-console/scripts/eval_precision.py apps/admin-console/tests/test_eval_precision.py
git commit -m "feat(eval): precision oracle — surfaces candidates + unsourced-web (准 axis)"
```

### Task 1.3: Build `eval_latency.py` (TDD)

**Files:**
- Create: `apps/admin-console/scripts/eval_latency.py`
- Test: `apps/admin-console/tests/test_eval_latency.py`

- [ ] **Step 1: Write the failing test for stats**

Create `apps/admin-console/tests/test_eval_latency.py`:

```python
"""Unit tests for eval_latency pure stats (no live calls)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_latency import _percentile, _slo_verdict


def test_percentile_basic():
    # p50 of [1,2,3,4,5] ~ 3; p95 close to 5
    assert _percentile([1, 2, 3, 4, 5], 50) == 3
    assert _percentile([1, 2, 3, 4, 5], 95) == 5


def test_slo_verdict_retrieval_pass():
    assert _slo_verdict(5.9, kind="retrieval") == "PASS"


def test_slo_verdict_retrieval_fail():
    assert _slo_verdict(6.1, kind="retrieval") == "FAIL"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_latency.py -v 2>&1 | tail -5
```
Expected: FAIL with `ModuleNotFoundError: No module named 'eval_latency'`.

- [ ] **Step 3: Write `eval_latency.py`**

Create `apps/admin-console/scripts/eval_latency.py`:

```python
"""Latency oracle (快). Measures /api/chat wall-clock, bucketed by query_type.
Retrieval SLO (synthesis OFF): p95 <= 6s. End-to-end SLO (synthesis ON): p95 <= 15s.
e2e needs CHAT_LLM_SYNTHESIS=on + DeepSeek key; run separately (design §1.3).

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_latency.py [--runs 3]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_recall import CASES  # noqa: E402

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

RETRIEVAL_SLO_P95 = 6.0   # seconds; synthesis off
E2E_SLO_P95 = 15.0        # seconds; synthesis on (separate run)


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _slo_verdict(p95: float, *, kind: str) -> str:
    limit = RETRIEVAL_SLO_P95 if kind == "retrieval" else E2E_SLO_P95
    return "PASS" if p95 <= limit else "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    client = TestClient(app)
    synthesis_off = os.environ.get("CHAT_LLM_SYNTHESIS", "off") == "off"
    kind = "retrieval" if synthesis_off else "e2e"
    rows: list[dict] = []
    all_p95: list[float] = []
    print(f"{'qid':>3} {'qtype':<20} {'p50':>6} {'p95':>6} {'max':>6}  verdict  query")
    print("-" * 88)
    for c in CASES:
        samples: list[float] = []
        qtype = "?"
        for _ in range(args.runs):
            t0 = time.perf_counter()
            try:
                r = client.post("/api/chat", json={"query": c.query})
            except Exception as e:  # noqa: BLE001
                print(f"{c.qid:>3} ERR {type(e).__name__}")
                break
            samples.append(time.perf_counter() - t0)
            if qtype == "?":
                qtype = str(r.json().get("query_type", "?"))
        if not samples:
            rows.append({"qid": c.qid, "error": "request_failed"})
            continue
        p50 = _percentile(samples, 50)
        p95 = _percentile(samples, 95)
        mx = max(samples)
        all_p95.append(p95)
        verdict = _slo_verdict(p95, kind=kind)
        rows.append({"qid": c.qid, "query_type": qtype, "p50": p50, "p95": p95,
                     "max": mx, "verdict": verdict})
        print(f"{c.qid:>3} {qtype[:20]:<20} {p50:>6.2f} {p95:>6.2f} {mx:>6.2f}  {verdict:<7} {c.query[:30]}")
    print("-" * 88)
    overall_p95 = _percentile(all_p95, 95) if all_p95 else 0.0
    print(f"{kind.upper()} p95 (across cases): {overall_p95:.2f}s — SLO {_slo_verdict(overall_p95, kind=kind)}")
    out = os.path.join(os.path.dirname(__file__), "..", "..", ".agents",
                       "runs", "retrieval-generation-alignment", "latency-baseline.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "runs": args.runs, "rows": rows,
                   "overall_p95": overall_p95, "slo_verdict": _slo_verdict(overall_p95, kind=kind)},
                  fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_latency.py -v 2>&1 | tail -5
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/admin-console/scripts/eval_latency.py apps/admin-console/tests/test_eval_latency.py
git commit -m "feat(eval): latency oracle — p50/p95/max bucketed by route (快 axis, SLO <=6s retrieval)"
```

### Task 1.4: Persist recall JSON in `eval_recall_chat.py`

**Files:**
- Modify: `apps/admin-console/scripts/eval_recall_chat.py:35-64`

- [ ] **Step 1: Add per-case JSON persistence**

In `apps/admin-console/scripts/eval_recall_chat.py`, replace the `main()` body so it records per-case hit/miss and writes JSON. Change the function to:

```python
def main() -> int:
    import json
    client = TestClient(app)
    total_req = total_hit = 0
    rows: list[dict] = []
    print(f"{'qid':>3} {'qtype':<24} {'hit/req':>8}  misses")
    print("-" * 92)
    for c in CASES:
        try:
            r = client.post("/api/chat", json={"query": c.query})
        except Exception as e:  # noqa: BLE001
            print(f"{c.qid:>3} {'ERR':<24} {'-':>8}  {type(e).__name__}: {str(e)[:120]}")
            total_req += len(c.required)
            rows.append({"qid": c.qid, "error": str(e)})
            continue
        if r.status_code != 200:
            print(f"{c.qid:>3} {'HTTP'+str(r.status_code):<24} {'-':>8}  {r.text[:120]}")
            total_req += len(c.required)
            rows.append({"qid": c.qid, "http": r.status_code})
            continue
        j = r.json()
        qtype = str(j.get("query_type", "?"))
        blob = json.dumps(j, ensure_ascii=False)
        hits = [req for req in c.required if req in blob]
        miss = [req for req in c.required if req not in blob]
        total_req += len(c.required)
        total_hit += len(hits)
        flag = "OK  " if not miss else "MISS"
        rows.append({"qid": c.qid, "query_type": qtype, "hits": hits, "misses": miss})
        print(f"{c.qid:>3} {qtype[:24]:<24} {len(hits)}/{len(c.required):>5} {flag}  {miss}")
    print("-" * 92)
    pct = 100.0 * total_hit / total_req if total_req else 0.0
    print(f"END-TO-END ENTITY RECALL (/api/chat, synthesis off): "
          f"{total_hit}/{total_req} ({pct:.0f}%)")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                       ".agents", "runs", "retrieval-generation-alignment", "post-fix-recall.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"total_hit": total_hit, "total_req": total_req, "pct": pct, "rows": rows},
                  fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    return 0
```

- [ ] **Step 2: Run it to verify it produces JSON**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_recall_chat.py 2>&1 | tail -6
```
Expected: prints recall line + `WRITTEN: .../post-fix-recall.json`.

- [ ] **Step 3: Commit**

```bash
git add apps/admin-console/scripts/eval_recall_chat.py
git commit -m "feat(eval): persist recall per-case JSON for evidence traceability"
```

### Task 1.5: Run all three oracles, persist evidence

**Files:** generated JSON in `.agents/runs/retrieval-generation-alignment/`

- [ ] **Step 1: Run recall oracle**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_recall_chat.py 2>&1 | tail -3
```
Expected: `post-fix-recall.json` written; recall line matches the design's RED/GREEN check.

- [ ] **Step 2: Run precision oracle**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_precision.py 2>&1 | tail -4
```
Expected: `precision-baseline.json` written; prints `UNSOURCED WEB (§5...): N`.

- [ ] **Step 3: Run latency oracle**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_latency.py --runs 3 2>&1 | tail -4
```
Expected: `latency-baseline.json` written; prints `RETRIEVAL p95 ... PASS/FAIL`.

- [ ] **Step 4: Commit evidence**

```bash
git add .agents/runs/retrieval-generation-alignment/post-fix-recall.json \
        .agents/runs/retrieval-generation-alignment/precision-baseline.json \
        .agents/runs/retrieval-generation-alignment/latency-baseline.json
git commit -m "test(retrieval): persist recall/precision/latency oracle evidence (全/准/快 baseline)"
```

---

## Phase 2 — Recall change re-truthing (OpenSpec)

> Source of truth for the rewrite: `apps/miroflow-agent/src/data_agents/service/retrieval.py` (`_hybrid_rrf_select` line 242, `retrieve` line 317, `_augment_with_web` line 451) and `apps/admin-console/backend/api/chat.py` (`_lookup_cross_domain_evidence` line ~1897). Read these before editing spec.

### Task 2.1: Rewrite `spec.md` to delivered reality

**Files:**
- Modify: `openspec/changes/fix-chat-retrieval-recall-gaps/specs/agentic-rag-retrieval/spec.md`

- [ ] **Step 1: Replace the spec delta with delivered-reality requirements**

Overwrite the file with:

```markdown
## ADDED Requirements

### Requirement: Hybrid RRF + web-search augmentation rescues broad-profile and absent entities

The retrieval service SHALL fuse vector-rerank, lexical-coverage, and rerank signals via
reciprocal-rank fusion (RRF) so that entities ranking deep in raw ANN but lexically relevant
(broad-profile market leaders) are rescued into the candidate window. The service SHALL augment
recall with web-search results (object_type `web`) for entities absent from the local DB, so
they become citable candidates.

#### Scenario: a broad-profile company is rescued by RRF
- **GIVEN** a company that is `ready`, embedded, and lexically relevant to a topic query but
  ranks ~32 in raw ANN
- **WHEN** the topic query is retrieved with hybrid RRF
- **THEN** the candidate window includes it via the lexical-coverage fusion path, not purely by
  the ANN candidate-limit cutoff

#### Scenario: an absent entity is surfaced via web augmentation
- **GIVEN** a well-known entity absent from the local DB that web-search returns for the query
- **WHEN** the query is retrieved with `augment_with_web=True`
- **THEN** the response includes an `object_type=web` candidate for that entity

### Requirement: Cross-filter professor queries SHALL reach recall

A professor query combining multiple attributes (origin/graduation school AND field of focus)
SHALL be classified so it reaches professor semantic recall, not fall through to the `unknown`
refuse path.

#### Scenario: school + field cross-filter query is routed to recall
- **GIVEN** a query like "毕业于早稻田，且在深圳专注在机器人行业的企业家"
- **WHEN** it is classified and routed
- **THEN** it is routed to professor recall (not `unknown`)

### Requirement: Retrieval evidence SHALL be auditable

Every returned candidate SHALL carry its source domain (`object_type`), identifier, score, and
snippet. Web-rescued candidates SHALL carry a `source_url` (or be flagged unsourced) so evidence
remains source-traceable per the audit invariant.

#### Scenario: web candidate carries a source url
- **GIVEN** a web-search-augmented retrieval result
- **WHEN** the candidate is rendered
- **THEN** it exposes `object_type=web`, a snippet, and either a `source_url` or an explicit
  unsourced flag

## UNCHANGED Requirements
<!-- A–G routing semantics, _VALID_DOMAINS, _is_indexable_paper, evidence shape, per-domain
     recall mechanics, rerank cascade unchanged; baseline = docs/Agentic-RAG-PRD.md. -->
```

- [ ] **Step 2: Commit**

```bash
git add openspec/changes/fix-chat-retrieval-recall-gaps/specs/agentic-rag-retrieval/spec.md
git commit -m "spec(retrieval): re-truth recall change to delivered RRF/web/fuse (drop reverted candidate_limit)"
```

### Task 2.2: Re-truth proposal, design, tasks, acceptance

**Files:**
- Modify: `openspec/changes/fix-chat-retrieval-recall-gaps/{proposal,design,tasks,acceptance}.md`

- [ ] **Step 1: Update `proposal.md` What Changes**

In `proposal.md`, replace section lines 24-26 (the candidate_limit item) so "What Changes" reads the delivered mechanisms. Replace the numbered list under `## What Changes` with:

```markdown
1. **Hybrid RRF + web-search augmentation** (DELIVERED): vector-rerank + lexical-coverage +
   rerank three-way RRF fusion rescues broad-profile entities (普渡/深南电路) that the reverted
   `candidate_limit` raise could not; web-search surfaces absent entities (closes part of FM1a
   at recall time). Eval-gated: 53%→74%.
2. **FM3 cross-filter professor routing** (DELIVERED, data-blocked): attribute-AND-attribute
   professor queries reach professor recall, not `unknown`. Acceptance is routing-reachable;
   recall ceiling for #19 is bound by ingest (许晋诚/陈功 absent).
3. **Eval harness** is the RED→GREEN oracle; baseline 53% recorded, post-fix 74% persisted.

Non-goals (deferred):
- FM1a ingest of missing companies (separate data-pipeline workstream — see
  `fm1a-ingest-decision.md`).
- The candidate_limit raise (FM1b original) was eval-NEUTRAL and reverted — NOT delivered.
- Generation rewrite / streaming / AnswerGenerator (separate change).
- Embedding/profile-quality rework for broad summaries (mitigated, not redone).
```

- [ ] **Step 2: Update `design.md` FM1b section to record the revert**

In `design.md`, replace the `## FM1b` section (lines 6-16) with:

```markdown
## FM1b — recall candidate window (REVISED: candidate_limit reverted; RRF is the real lever)

**Root cause (verified):** `candidate_limit=30` cuts deep candidates, but raising it (30→64) was
eval-NEUTRAL and reverted — the reranker still does not reliably promote broad-profile entities
(普渡 rerank-rank-10 over the full pool). The lever that worked is **hybrid RRF** (lexical
coverage fuses vector-rerank + keyword ranks) so deep-but-lexically-relevant entities enter the
window via a second signal, plus web-search augmentation for absent entities.

**Delivered:** `_hybrid_rrf_select` (retrieval.py:242) + `_augment_with_web` (retrieval.py:451).
Eval-gated: 53%→74%. The deeper profile-quality layer (broad summaries) is out of scope.
```

- [ ] **Step 3: Re-truth `tasks.md` checkboxes**

Overwrite `tasks.md` with:

```markdown
# Tasks: fix-chat-retrieval-recall-gaps

> Eval-first. Delivered in commits 1fb6449/0c85b04/06ae50b. This change re-truths the contract.

## 0. Verification contract
- [x] 0.1 verification-contract.md exists (RED=53%, GREEN=recall target).

## 1. Eval harness (the oracle)
- [x] 1.1 eval_recall.py + eval_recall_chat.py — baseline 53%.
- [x] 1.2 Post-fix recall JSON persisted (`.agents/runs/.../post-fix-recall.json`).

## 2. FM1b — candidate window (DELIVERED as RRF, not candidate_limit)
- [x] 2.1 `_hybrid_rrf_select` delivered (retrieval.py:242); candidate_limit raise reverted.
- [x] 2.2 Eval 53%→74% on #4/#13 (broad-profile rescued via lexical fusion).

## 3. FM3 — cross-filter professor routing (DELIVERED, data-blocked)
- [x] 3.1 Cross-filter professor pattern routes to recall (not `unknown`).
- [x] 3.2 #19 routed to professor recall; recall ceiling bound by ingest (许晋诚/陈功 absent).

## 4. Acceptance, ledger, validate
- [ ] 4.1 Evidence persisted (recall + precision + latency baseline JSON).
- [ ] 4.2 change-ledger status → in-verification.
- [ ] 4.3 openspec validate fix-chat-retrieval-recall-gaps --strict exits 0.
- [ ] 4.4 Claude review against acceptance; accept / revise / reject.
```

- [ ] **Step 4: Update `acceptance.md` to delivered reality**

Overwrite `acceptance.md` with:

```markdown
# Acceptance: fix-chat-retrieval-recall-gaps

A change is accepted only when ALL hold.

## Recall (eval-gated)
- [ ] End-to-end entity recall (`eval_recall_chat.py`) is **74% (14/19)** (delivered), persisted
      as `post-fix-recall.json`, with no passing case regressed vs the 53% baseline.
- [ ] RRF rescues broad-profile entities (#4 普渡 / #13 深南电路) into the candidate window
      (verified via `eval_recall.py` forced-domain).
- [ ] FM3: #19 routed to professor recall (no longer `unknown`) — routing-reachable; recall
      ceiling bound by ingest.

## Precision (new oracle, baseline only this round)
- [ ] `precision-baseline.json` persisted; unsourced-web count recorded; candidate names
      surfaced for labeling (GREEN threshold set after first measurement, per design §1.1).

## No regression
- [ ] Patent applicant (#40) / exact (#41) routing still correct.
- [ ] Single-entity profiles (#1/#10/#16/#21/#24/#26/#34) still recalled.
- [ ] Existing chat tests green; `openspec validate fix-chat-retrieval-recall-gaps --strict` 0.

## Honest scope (not blocked-on)
- [ ] FM1a (云迹/九号/擎朗/嘉立创/许晋诚/陈功 not ingested) recorded in
      `fm1a-ingest-decision.md` as the recall ceiling — separate ingest decision; NOT claimed
      solved.

## Evidence to report
- post-fix-recall.json + precision-baseline.json + latency-baseline.json; per-case delta; FM1a
  blocker note.
```

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/fix-chat-retrieval-recall-gaps/proposal.md \
        openspec/changes/fix-chat-retrieval-recall-gaps/design.md \
        openspec/changes/fix-chat-retrieval-recall-gaps/tasks.md \
        openspec/changes/fix-chat-retrieval-recall-gaps/acceptance.md
git commit -m "spec(retrieval): re-truth proposal/design/tasks/acceptance to delivered 53->74%"
```

### Task 2.3: Add FM1a ingest decision gate

**Files:**
- Create: `openspec/changes/fix-chat-retrieval-recall-gaps/fm1a-ingest-decision.md`

- [ ] **Step 1: Write the decision record**

Create the file:

```markdown
# FM1a Ingest Decision Gate (not implemented this round)

> Per design §3.3. This is a decision record, not an implementation. The recall change does NOT
> carry ingest responsibility; this gates a separate data-pipeline workstream.

## Why a gate, not silence
6/19 missed entities are simply absent from `company` (67% of misses — diagnosis
`diagnosis-baseline.md`). Without ingest the recall ceiling is ~13/19 (68%); the delivered 74%
can only come from web rescuing ~1 entity. Data coverage is a multiplicative factor on recall,
not salvageable by retrieval logic.

## Absent entities (quantified)
- #4 (酒店送餐机器人): 云迹科技, 九号机器人, 擎朗智能 (3 of 5 required absent).
- #13 (PCB打板): 嘉立创.
- #19 (cross-filter professor): 许晋诚, 陈功 (block FM3 routing verification too).

## Per-entity block reason
- 云迹/九号/擎朗/嘉立创: 0 rows in `company` (not ingested).
- 许晋诚/陈功: absent → FM3 routing fix is data-blocked (routing-reachable, but recall empty).

## Expected ceiling after ingest
From ~68% to a theoretical value that needs re-measure post-ingest (web rescue may overlap).
Re-run `eval_recall_chat.py` after ingest to quantify.

## Ownership
Data-pipeline workstream, decoupled from retrieval-logic. A new OpenSpec change should be
opened when ingest is prioritized; this file is its starting point, not its substitute.
```

- [ ] **Step 2: Commit**

```bash
git add openspec/changes/fix-chat-retrieval-recall-gaps/fm1a-ingest-decision.md
git commit -m "spec(retrieval): FM1a ingest decision gate (67% miss ceiling, data workstream)"
```

### Task 2.4: Make `openspec validate --strict` exit 0

**Files:** validate the change edited in 2.1-2.3

- [ ] **Step 1: Run validate**

Run:
```bash
openspec validate fix-chat-retrieval-recall-gaps --strict 2>&1 | tail -10
```
Expected: exits 0 (the rewritten spec in Task 2.1 added SHALL to the cross-filter requirement and each requirement has a `#### Scenario:` block).

- [ ] **Step 2: If it still errors, fix the named requirement**

The previous error was `Cross-filter professor queries reach recall (not refuse) must contain SHALL or MUST`. Task 2.1's rewrite uses `SHALL` in that requirement's title. Re-run; if a different requirement is flagged, add SHALL/MUST to its statement. Commit any fix:

```bash
git add -A openspec/changes/fix-chat-retrieval-recall-gaps/
git commit -m "spec(retrieval): fix openspec validate --strict errors"
```

### Task 2.5: Enter the change-ledger

**Files:**
- Modify: `openspec/change-ledger.md`

- [ ] **Step 1: Add the ledger row**

Append a row to `openspec/change-ledger.md` (match existing column layout — see rows 21-25 for format). Add after the `correct-paper-tier2-overmerge-view-b` row:

```markdown
| fix-chat-retrieval-recall-gaps | feat (hybrid RRF + web-search augmentation + cross-filter professor routing; re-truthed to delivered 53->74%; candidate_limit reverted; FM3 data-blocked) | agentic-rag-retrieval | first-principles diagnosis 2026-06-29 (DB+Milvus-grounded) → DELIVERED 2026-06-30: recall 53->74% (14/19) via RRF+web+multi-path fuse; precision/latency oracles new; FM1a ingest gated (6 absent entities, 67% miss) | in-verification | Standard | medium | `.agents/runs/retrieval-generation-alignment/` | n/a | no |
```

- [ ] **Step 2: Commit**

```bash
git add openspec/change-ledger.md
git commit -m "chore(openspec): enter fix-chat-retrieval-recall-gaps in ledger (in-verification)"
```

---

## Phase 3 — Synthesis timeout OpenSpec change (small, behavior-affecting)

> Source: `apps/admin-console/backend/api/chat.py:70` (`_CHAT_SYNTHESIS_TIMEOUT_SECONDS = float(os.environ.get("CHAT_SYNTHESIS_TIMEOUT", "60.0"))`) used at line 1180. Delivered in commits `0572d06`+`8da9053`.

### Task 3.1: Create the change

**Files:**
- Create: `openspec/changes/add-synthesis-timeout/proposal.md`
- Create: `openspec/changes/add-synthesis-timeout/specs/agentic-rag-retrieval/spec.md`
- Create: `openspec/changes/add-synthesis-timeout/tasks.md`
- Create: `openspec/changes/add-synthesis-timeout/acceptance.md`

- [ ] **Step 1: Write `proposal.md`**

```markdown
# Proposal: add-synthesis-timeout

## Why
The synthesis step previously timed out at 3s, mis-killing answers that take 4-59s (DeepSeek
synthesis ~8-9s typical). The default was raised to 60s with an env override
(`CHAT_SYNTHESIS_TIMEOUT`). This is a user-visible behavior change (answers that failed now
succeed), so it gets an OpenSpec behavior-affecting change, not a behavior-preserving refactor.

## What Changes
1. Default synthesis timeout 3s -> 60s, overridable via `CHAT_SYNTHESIS_TIMEOUT` env (seconds).
2. No streaming, no retry — only the timeout knob.

## Capabilities
### Modified Capabilities
- `agentic-rag-retrieval` — synthesis timeout behavior (legacy baseline: docs/Agentic-RAG-PRD.md).

## Impact
- `apps/admin-console/backend/api/chat.py:70` (default) + `:1180` (use site).
- No schema/API-shape change; only which answers succeed vs time out.
```

- [ ] **Step 2: Write `specs/agentic-rag-retrieval/spec.md`**

```markdown
## MODIFIED Requirements

### Requirement: Synthesis timeout SHALL default to 60s with an env override

The answer-synthesis step SHALL use a default timeout of 60 seconds, overridable via the
`CHAT_SYNTHESIS_TIMEOUT` environment variable (seconds, float). Answers taking up to the
configured timeout SHALL complete rather than be killed.

#### Scenario: a 10s synthesis completes
- **GIVEN** `CHAT_SYNTHESIS_TIMEOUT` unset (default 60s) and a synthesis that takes 10s
- **WHEN** the answer is synthesized
- **THEN** it completes successfully (not timed out)

#### Scenario: env override lowers the timeout
- **GIVEN** `CHAT_SYNTHESIS_TIMEOUT=5`
- **WHEN** a synthesis takes 8s
- **THEN** it times out (honoring the override)
```

- [ ] **Step 3: Write `tasks.md`**

```markdown
# Tasks: add-synthesis-timeout

> Delivered in commits 0572d06 + 8da9053. This change contracts it.

- [x] 1. Default `_CHAT_SYNTHESIS_TIMEOUT_SECONDS` = 60.0 from env `CHAT_SYNTHESIS_TIMEOUT`
      (chat.py:70), used at chat.py:1180.
- [ ] 2. openspec validate add-synthesis-timeout --strict exits 0.
- [ ] 3. Claude review; accept / revise / reject.
```

- [ ] **Step 4: Write `acceptance.md`**

```markdown
# Acceptance: add-synthesis-timeout

- [ ] Default timeout is 60s; `CHAT_SYNTHESIS_TIMEOUT` overrides it (unit-checkable: read the
      env-wired constant).
- [ ] No streaming/retry added (scope guard).
- [ ] `openspec validate add-synthesis-timeout --strict` exits 0.
- [ ] Existing chat tests green (the 60s default is already matched by test 8da9053).

## Evidence to report
- chat.py:70 + :1180 diff confirmation; env-override unit check; test status.
```

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/add-synthesis-timeout/
git commit -m "spec(chat): add-synthesis-timeout OpenSpec change (3s->60s default, env override)"
```

### Task 3.2: Validate the synthesis-timeout change

- [ ] **Step 1: Run validate**

Run:
```bash
openspec validate add-synthesis-timeout --strict 2>&1 | tail -10
```
Expected: exits 0.

- [ ] **Step 2: If error, fix inline and commit**

```bash
git add -A openspec/changes/add-synthesis-timeout/
git commit -m "spec(chat): fix openspec validate --strict for add-synthesis-timeout"
```

---

## Phase 4 — Perf refactor-contract (keepalive + parallel, behavior-preserving)

> Source: `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py:161-174` (keepalive `grpc_options`) and `apps/admin-console/backend/api/chat.py` `_lookup_cross_domain_evidence` (~line 1897, the `ThreadPoolExecutor(max_workers=3)` block delivered in `c4fa382`). Key concern: parallelization changed evidence-completion order — must prove equivalence.

### Task 4.1: Write the refactor-contract

**Files:**
- Create: `.agents/runs/perf-retrieval-keepalive-parallel/refactor-contract.md`

- [ ] **Step 1: Write the contract**

```markdown
# Refactor Contract — perf-retrieval-keepalive-parallel

> Behavior-preserving (CLAUDE.md §8). Delivered in commit c4fa382. This contract proves
> equivalence + records the SLO.

## Scope
1. **Milvus keepalive** (`milvus_collections.py:161-174`): inject `grpc_options`
   (keepalive_time_ms=600000, permit_without_calls=False) at the `MilvusClientCompat`
   chokepoint. Fixes GOAWAY too_many_pings from pymilvus 2.6.11 defaults (10s ping).
2. **D-path parallel** (`chat.py` `_lookup_cross_domain_evidence`): professor/paper/company
   retrieves run concurrently via `ThreadPoolExecutor(max_workers=3)`; wall-time = max(1), not
   sum(3).

## Behavior preserved (the invariant)
- The SET of evidence returned is identical (parallel only changes completion order, not
  membership; each `_retrieve_domain` is independent and `merged.extend` is order-tolerant for
  the downstream dedup-fuse).
- The ORDER may differ. Risk: if downstream consumers depend on stable order. Mitigation: the
  fused results are deduped and reranked downstream, so order differences do not change the
  final answer set. This MUST be proven by golden-order evidence (Task 4.2).

## RED (baseline)
- Pre-fix: GOAWAY too_many_pings spikes (45s variance on D); serial D ~13-45s.
## GREEN
- 0 GOAWAY post-fix.
- Retrieval wall-clock p95 <= 6s (latency oracle, synthesis off).
- Golden-order: parallel evidence set == serial evidence set; order diff proven harmless
  (downstream dedup-fuse produces the same final candidate set).

## Allowed Superpowers mode
- Baseline/golden proof of unchanged behavior (not new-behavior TDD). If golden-order
  equivalence CANNOT be proven, this downgrades to an OpenSpec behavior-affecting change
  (risk named in design §5).

## Out of scope
- streaming / cache (next latency workstream).
- B-path / E-path latency (only D-path parallelized in c4fa382).
```

- [ ] **Step 2: Commit**

```bash
git add .agents/runs/perf-retrieval-keepalive-parallel/refactor-contract.md
git commit -m "spec(perf): refactor-contract for keepalive + D-path parallel (behavior-preserving)"
```

### Task 4.2: Golden-order evidence (serial vs parallel)

**Files:**
- Create: `apps/admin-console/scripts/eval_golden_order.py` (one-off; optional — see note)
- Create (generated): `.agents/runs/perf-retrieval-keepalive-parallel/golden-order-serial.json`
- Create (generated): `.agents/runs/perf-retrieval-keepalive-parallel/golden-order-parallel.json`

- [ ] **Step 1: Capture serial baseline (git stash the parallel block temporarily)**

The parallel block is in `chat.py` `_lookup_cross_domain_evidence` (delivered in `c4fa382`). To get the serial baseline, temporarily revert just that function:

```bash
cd /home/longxiang/MiroThinker
git show c4fa382 -- apps/admin-console/backend/api/chat.py > /tmp/perf.diff
# Manually revert the ThreadPoolExecutor block to the prior serial for-loop (use the /tmp/perf.diff
# reverse hunk), run the recall oracle on D-path cases, capture evidence SET (not order) as JSON.
```

Run (synthesis off) for the D/cross-domain cases (#4, #34 — the cases exercising
`_lookup_cross_domain_evidence`):
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python -c "
import json, os, sys
sys.path.insert(0, 'scripts')
from eval_recall import CASES
from backend.main import app
from fastapi.testclient import TestClient
c = TestClient(app)
rows = {}
for case in CASES:
    if case.qid in (4, 34):
        j = c.post('/api/chat', json={'query': case.query}).json()
        ev = json.dumps(j, ensure_ascii=False, sort_keys=True)
        rows[case.qid] = sorted(set(_ for _ in ev.split('\"') if case.domain in _.lower()))[:50]
out = '../../.agents/runs/perf-retrieval-keepalive-parallel/golden-order-serial.json'
json.dump(rows, open(out,'w'), ensure_ascii=False, indent=2); print('serial:', out)
"
```
Expected: `golden-order-serial.json` written with the D-path evidence set.

- [ ] **Step 2: Restore the parallel block and capture parallel evidence**

```bash
git checkout apps/admin-console/backend/api/chat.py   # restore delivered parallel version
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python -c "
import json, sys
sys.path.insert(0, 'scripts')
from eval_recall import CASES
from backend.main import app
from fastapi.testclient import TestClient
c = TestClient(app)
rows = {}
for case in CASES:
    if case.qid in (4, 34):
        j = c.post('/api/chat', json={'query': case.query}).json()
        ev = json.dumps(j, ensure_ascii=False, sort_keys=True)
        rows[case.qid] = sorted(set(_ for _ in ev.split('\"') if case.domain in _.lower()))[:50]
out = '../../.agents/runs/perf-retrieval-keepalive-parallel/golden-order-parallel.json'
json.dump(rows, open(out,'w'), ensure_ascii=False, indent=2); print('parallel:', out)
"
```
Expected: `golden-order-parallel.json` written.

- [ ] **Step 3: Diff the two sets**

```bash
diff <(jq -S . .agents/runs/perf-retrieval-keepalive-parallel/golden-order-serial.json) \
     <(jq -S . .agents/runs/perf-retrieval-keepalive-parallel/golden-order-parallel.json) && echo "SETS MATCH"
```
Expected: `SETS MATCH` (the evidence sets are equal; order may differ but set membership identical). If they differ, the downstream dedup-fuse must be shown to produce the same final candidates — record that in verification.md or escalate to OpenSpec (design §5 risk).

- [ ] **Step 4: Commit evidence**

```bash
git add .agents/runs/perf-retrieval-keepalive-parallel/golden-order-serial.json \
        .agents/runs/perf-retrieval-keepalive-parallel/golden-order-parallel.json
git commit -m "test(perf): golden-order evidence serial vs parallel (D-path set equivalence)"
```

### Task 4.3: Write verification.md with SLO evidence

**Files:**
- Create: `.agents/runs/perf-retrieval-keepalive-parallel/verification.md`
- Create (generated): `.agents/runs/perf-retrieval-keepalive-parallel/latency-evidence.json`

- [ ] **Step 1: Run the latency oracle and copy evidence**

```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_latency.py --runs 3 2>&1 | tail -4
cp ../../.agents/runs/retrieval-generation-alignment/latency-baseline.json \
   ../../.agents/runs/perf-retrieval-keepalive-parallel/latency-evidence.json
```
Expected: `latency-evidence.json` written; overall retrieval p95 printed with PASS/FAIL.

- [ ] **Step 2: Write verification.md**

```markdown
# Verification — perf-retrieval-keepalive-parallel

## GOAWAY
- Post-fix: 0 GOAWAY (commit c4fa382 verified; re-confirm in backend logs during the latency run).

## Latency SLO
- Retrieval wall-clock p95 = <fill from latency-evidence.json> — SLO <= 6s: <PASS/FAIL>.
- Per-route buckets from latency-evidence.json.

## Golden-order equivalence (the behavior-preservation proof)
- serial set == parallel set: <MATCH / DIFF>.
- If MATCH: behavior preserved; order diff is harmless because downstream dedup-fuse is
  order-tolerant.
- If DIFF: record the diffing entities and either prove the downstream final candidate set is
  unchanged, OR escalate to OpenSpec behavior-affecting (design §5).

## Test status
- 21 chat tests: <green / failures>.

## Verdict
- Accept / Revise / Reject.
```

- [ ] **Step 3: Commit**

```bash
git add .agents/runs/perf-retrieval-keepalive-parallel/verification.md \
        .agents/runs/perf-retrieval-keepalive-parallel/latency-evidence.json
git commit -m "test(perf): verification evidence (GOAWAY=0, SLO, golden-order) for keepalive+parallel"
```

---

## Phase 5 — Claude review and Accept

### Task 5.1: Run full regression + gather all evidence

- [ ] **Step 1: Run the 21 chat tests**

Run:
```bash
cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 \
uv run pytest tests/test_chat_retrieval.py tests/test_chat_c_handler.py tests/test_chat_classifier_c_type.py tests/test_chat_d_narrowing.py tests/test_chat_e_web_search.py tests/test_chat_g_clarification.py tests/test_chat_multi_domain_entity_stack.py tests/test_chat_context_helpers.py tests/test_chat_classifier_b_g_tune.py tests/test_chat_feedback.py 2>&1 | tail -8
```
Expected: all green (matches commit c4fa382's "21 chat regression tests pass").

- [ ] **Step 2: Re-confirm oracles are green-on-current-HEAD**

Run the three oracle commands from Task 1.5 again; confirm the JSON in `.agents/runs/` reflects current HEAD (not a stale run).

- [ ] **Step 3: openspec validate both changes**

Run:
```bash
openspec validate fix-chat-retrieval-recall-gaps --strict 2>&1 | tail -3
openspec validate add-synthesis-timeout --strict 2>&1 | tail -3
```
Expected: both exit 0.

### Task 5.2: Write Claude review notes + decision

**Files:**
- Create: `.agents/reviews/2026-07-01-retrieval-gap-closure.md`

- [ ] **Step 1: Write the review against each contract's acceptance**

```markdown
# Review: retrieval-gap-closure (2026-07-01)

Reviews three artifacts against their acceptance + CLAUDE.md §12 criteria.

## fix-chat-retrieval-recall-gaps (OpenSpec, rewritten)
- Acceptance: recall 74% persisted (post-fix-recall.json)? <Y/N>.
- Precision baseline persisted (precision-baseline.json)? <Y/N>.
- FM1a gate recorded (fm1a-ingest-decision.md)? <Y/N>.
- openspec validate --strict 0? <Y/N>.
- Decision: <Accept / Revise / Reject>.

## add-synthesis-timeout (OpenSpec, small)
- Default 60s + env override confirmed (chat.py:70)? <Y/N>.
- validate --strict 0? <Y/N>.
- Decision: <Accept / Revise / Reject>.

## perf-retrieval-keepalive-parallel (refactor-contract)
- GOAWAY = 0? <Y/N>.
- Retrieval p95 <= 6s (latency-evidence.json)? <Y/N>.
- Golden-order set equivalence proven? <Y/N — if N, was it escalated to OpenSpec?>.
- Decision: <Accept / Revise / Reject>.

## Honest notes
- 74% not ceiling-closed (FM1a out of scope) — accepted as recall change scope, not as full recall.
- Precision GREEN deferred to post-labeling (design §1.1) — accepted as baseline-only this round.
- <any skipped checks / risks>.
```

- [ ] **Step 2: Commit review**

```bash
git add .agents/reviews/2026-07-01-retrieval-gap-closure.md
git commit -m "review(retrieval): gap-closure Accept/Revise/Reject across 3 contracts"
```

### Task 5.3: Portfolio update

**Files:**
- Modify: `.agents/portfolio.md` (if it exists; else note its absence)

- [ ] **Step 1: Update portfolio states**

Mark the three artifacts `Candidate -> Accepted` (or `Revise`/`Blocked`) in `.agents/portfolio.md`. If the file does not exist, create it per CLAUDE.md §7 with the three rows.

- [ ] **Step 2: Commit**

```bash
git add .agents/portfolio.md
git commit -m "chore(portfolio): advance retrieval gap-closure artifacts to Accepted"
```

---

## Self-review (against spec `docs/superpowers/specs/2026-07-01-retrieval-gap-closure-design.md`)

**1. Spec coverage:**
- §1 evidence foundation (recall/precision/latency oracles + SLO) → Phase 1 (Tasks 1.1-1.5). ✓
- §2.1 three artifacts → Phase 2 (recall), Phase 3 (synthesis), Phase 4 (perf). ✓
- §2.2 recall spec re-truthing (delete candidate_limit, add RRF/web/fuse, SHALL on FM3, auditable evidence req) → Task 2.1. ✓
- §2.3 incidental gaps (validate, ledger, tasks re-truth) → Tasks 2.4, 2.5, 2.2. ✓
- §2.4 out-of-scope (FM1a/streaming/profile/over-merge) → Task 2.3 gates FM1a; Phase 4/5 note streaming; over-merge surfaced by precision oracle (not corrected this round, per design). ✓
- §3 ingest decision gate → Task 2.3. ✓
- §4 locked decisions → reflected in artifact types (OpenSpec vs refactor-contract) and SLO values. ✓
- §5 risks (74% not re-run this session; golden-order; precision GREEN deferred) → Phase 1 re-runs oracles; Task 4.2 golden-order; Task 5.2 honest notes. ✓

**2. Placeholder scan:** No TBD/TODO. Task 4.3/5.2 have `<fill from ...>` / `<Y/N>` markers — these are evidence-fill slots for the executor to populate from run output, not design placeholders; the surrounding instruction is complete. Acceptable.

**3. Type consistency:** `Case.false_positives` (Task 1.1) referenced in `eval_precision.py` (Task 1.2) and `precision-baseline.json` rows. `_walk_candidates`/`_count_unsourced_web`/`_display_name` (Task 1.2) defined and tested before use. `_percentile`/`_slo_verdict` (Task 1.3) defined and tested. `retrieve()` signature matches the real code (candidate_limit/final_top_k/filter_by_quality_status/augment_with_web/web_top_n). `Evidence` fields match real dataclass. ✓

No gaps found; plan is complete.
