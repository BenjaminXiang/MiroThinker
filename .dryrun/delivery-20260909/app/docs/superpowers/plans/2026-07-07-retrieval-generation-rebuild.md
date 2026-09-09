# Retrieval-Generation Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or
> superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild the retrieve→context→fuse→synthesize pipeline as layers (route C hybrid),
measured toward 90%+ end-to-end.

**Architecture:** Deterministic precise retrieval (auditable) + LLM reasoning on grounded
evidence. Probe-first (measure C/E), then C→A→D, B/kill-dump parallel, E probe-directed.

**Spec:** `docs/superpowers/specs/2026-07-07-retrieval-generation-rebuild-design.md`
**Contract:** doc-as-contract (`openspec/` absent).

---

## Slice 0: Probe — retrieval precision/coverage baseline (DETAILED, test-first)

The probe IS the failing test: it will show retrieval is imprecise (the baseline "failure").
C makes it green. Settles A-vs-C with data.

**Files:**
- Create: `apps/admin-console/scripts/probe_retrieval_precision.py`
- Create: `apps/admin-console/tests/fixtures/retrieval_gold.yaml`

- [ ] **Step 1: Write the gold-entity set**

Create `apps/admin-console/tests/fixtures/retrieval_gold.yaml` — gold entities sourced from
**authoritative rankings / domain knowledge, NOT the DB** (avoid circular bias). Each query lists
expected relevant entities by canonical-ish name (probe matches by substring, IDs vary):

```yaml
# Gold entities from authoritative sources (industry rankings / domain knowledge),
# NOT from the DB — avoids circular bias in measuring retrieval precision.
queries:
  - qid: pcb_makers
    query: "国内做PCB的厂商主要有哪些"
    domain: company
    # 2022 国内PCB十强 (Prismark / 行业榜单), authoritative
    gold_entities: [鹏鼎控股, 臻鼎科技, 东山精密, 深南电路, 景旺电子, 沪电股份, 健鼎, 华通, 建滔, 紫翔, 欣兴]
    notes: "DB has 深南电路/崇达技术/兴森快捷; rest absent = coverage gap"

  - qid: delivery_robot_suppliers
    query: "中国有哪些成熟的酒店送餐机器人供应商"
    domain: company
    gold_entities: [普渡科技, 擎朗智能, 云迹科技, 猎户星空, 惊鸿, YOUI机器人, 锐曼智能]
    notes: "DB has 普渡科技/锐曼; 擎朗/云迹/猎户星空 absent = coverage gap; 普渡 in-DB-not-retrieved-leading = precision"

  - qid: visuotactile_professors
    query: "清华做视触觉的教授有哪些"
    domain: professor
    gold_entities: [潘挺睿]   # 潘挺睿 = 触觉/视触觉传感 (清华深研院); authoritative
    notes: "false positives = 黎维彬(多孔材料)/Tsuboi(线粒体)/訾牧聪(水合物) = precision"

  - qid: embodied_shenzhen_companies
    query: "深圳有哪些做具身智能的公司"
    domain: company
    gold_entities: [优必选, 无界智航, 智元机器人, 越疆, 节卡, 达闼]
    notes: "subset in DB; measures precision + coverage"

  - qid: dexterous_hand_professors
    query: "有哪些做灵巧手的教授"
    domain: professor
    gold_entities: []  # to fill from domain knowledge
    notes: "establishes a professor-topic recall baseline"
```

(Expand to ~10-15 queries before the baseline run; the 5 above are the seed from the failing examples.)

- [ ] **Step 2: Write the probe script**

Create `apps/admin-console/scripts/probe_retrieval_precision.py`:

```python
"""Probe retrieval precision + coverage against a gold-entity set.

For each gold query: POST /api/chat to the LIVE backend (:18188), read
matched_objects/matched_professors, check which gold entities appear
(retrieval recall) vs. which are in the DB at all (coverage).

Distinguishes Layer C (precision: in-DB-but-not-retrieved) from Layer E
(coverage: not-in-DB). NOT a synthesis measure — reads retrieval output only.

Usage (backend must be UP on :18188):
  uv run python scripts/probe_retrieval_precision.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import requests
import yaml

REPO = Path(__file__).resolve().parents[3]
GOLD = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "retrieval_gold.yaml"
BACKEND = "http://localhost:18188"
DSN = "postgresql://miroflow:miroflow@localhost:15432/miroflow_real"


def _in_db(name: str, domain: str) -> bool:
    table = "company" if domain == "company" else "professor"
    name_col = "canonical_name" if domain == "company" else "canonical_name"
    with psycopg.connect(DSN) as c:
        r = c.execute(
            f"SELECT 1 FROM {table} WHERE {name_col} ILIKE %s "
            f"OR aliases::text ILIKE %s LIMIT 1",
            (f"%{name}%", f"%{name}%"),
        ).fetchone()
    return r is not None


def _retrieved_names(query: str, domain: str) -> list[str]:
    r = requests.post(f"{BACKEND}/api/chat", json={"query": query}, timeout=100)
    r.raise_for_status()
    j = r.json()
    sp = j.get("structured_payload") or {}
    key = "matched_objects" if domain == "company" else "matched_professors"
    rows = sp.get(key) or []
    names = []
    for o in rows:
        n = o.get("canonical_name") or o.get("title") or o.get("name") or ""
        if n:
            names.append(str(n))
    return names


def _found(gold: str, retrieved: list[str]) -> bool:
    return any(gold in n for n in retrieved)


def main() -> int:
    data = yaml.safe_load(GOLD.read_text())
    print(f"{'qid':<28} {'rec':>6} {'cov':>6}  query")
    print("-" * 80)
    for q in data["queries"]:
        qid, query, dom = q["qid"], q["query"], q["domain"]
        gold = q["gold_entities"]
        if not gold:
            continue
        retrieved = _retrieved_names(query, dom)
        recall = sum(1 for g in gold if _found(g, retrieved)) / len(gold)
        cov = sum(1 for g in gold if _in_db(g, dom)) / len(gold)
        # precision gap = covered-but-not-retrieved
        covered_not_retrieved = [g for g in gold if _in_db(g, dom) and not _found(g, retrieved)]
        print(f"{qid:<28} {recall*100:>5.0f}% {cov*100:>5.0f}%  {query[:34]}")
        if covered_not_retrieved:
            print(f"      [C-precision gap, in-DB not retrieved]: {covered_not_retrieved}")
        absent = [g for g in gold if not _in_db(g, dom)]
        if absent:
            print(f"      [E-coverage gap, not in DB]: {absent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the probe baseline (backend must be up on :18188)**

```bash
uv --directory apps/admin-console run --no-sync python scripts/probe_retrieval_precision.py
```

Expected baseline: **low recall** (precision failures — e.g. 普渡 in-DB-not-leading;
视触觉 false positives) + **coverage gaps** (PCB makers absent). Record the numbers.
This is the "failing test" — it proves C and E are real and quantifies each.

- [ ] **Step 4: Commit**

```bash
git add apps/admin-console/scripts/probe_retrieval_precision.py \
        apps/admin-console/tests/fixtures/retrieval_gold.yaml
git commit -m "feat(probe): retrieval precision/coverage baseline tool + gold set

Measures matched_objects recall vs DB coverage per gold query; distinguishes
Layer C (precision: in-DB not retrieved) from Layer E (coverage: not in DB).
Gold from authoritative rankings, not DB (no circular bias). Baseline run to follow.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Slice 1: Layer C — retrieval precision (outlined, probe-guided)

Detail after the probe baseline shows the precision gaps. Direction:
- **Company** (`_lookup_companies_by_topic`, chat.py:975-1103): field-tiered —
  `product_category`/`industry` hit = tier1; narrative/scenario = tier2; score + threshold;
  tier1 first. Failing test: "PCB厂商" returns product_category=印制电路板 makers, equipment
  suppliers demoted/excluded.
- **Professor** (`_lookup_professors_by_topic`/retrieval.py): rerank → absolute score gate;
  paper-rescue requires research_topic real match. Failing test: "视触觉" returns
  research_topic-matching profs, multi-pore/线粒体 profs excluded.
- Thresholds tuned by the probe. Each sub-slice is its own test-first commit.

## Slice 2: Layer A — two-step reasoning synthesis (outlined)

- Step 1 (structured relevance/sufficiency, audit-logged) → Step 2 (synthesize/refuse).
- Relevance criteria = field-hit + LLM fallback (same fields as C).
- Kill rule-2 dump mandate. Failing test: 2-relevant+5-irrelevant evidence → main list only 2.
- Deepseek-v4-pro for accuracy; two-step (accuracy > latency >> cost).

## Slice 3: Layer B + kill-dump (parallel quick-win, outlined)

- Marketplace blacklist + web entity-name dedup + source-aware render.
- Can run in parallel with Slice 1/2 (decoupled from retrieval).

## Slice 4: Layer D — set coreference + cross-domain (outlined)

- Resolve 上述/这些/他们 → last_result_set; cross-domain intent → batch get_related_objects.
- `looks_like_narrowing_query` distinguishes same-domain-narrow vs cross-domain-jump.
- Failing test: 10-prof list → "上述教授参与的企业" → returns their companies, not global re-search.

## Slice 5: Layer E — coverage backfill (probe-directed, long-running)

- Backfill notable companies by category (PCB top-10, delivery-robot leaders) via company pipeline.
- Priority set by the probe's coverage gaps.

## Self-review
- Spec coverage: probe (Slice 0) + C (1) + A (2) + B (3) + D (4) + E (5) — all 5 layers + probe.
- Sequence respects dependency (probe→C→A→D, B parallel, E probe-directed).
- Slice 0 detailed & test-first; 1-5 outlined (probe-guided, 边建边调) — not over-specified upfront.
- Invariants: no agentic retrieval, retrieval auditable, A-G semantics unchanged.
