# Benchmark Completion Spec — retrieval-generation-alignment

> Defines WHEN the benchmark is "complete" (a reliable acceptance gate) + current state.
> Per the goal directive: the benchmark must be concretely complete, not verbally asserted.
> The adversarial review found the benchmark is currently INSENSITIVE (Lever 0 +1, Lever 1
> +303 ready both moved the oracle ~0) + precision UNVERIFIED + unstable (L3 variance).

## Completion criteria (all 5 required for the benchmark to gate acceptance)

### 1. Coverage — query-type × domain space
- **Required**: spans A (profile) / B (topic) / D (cross-domain) / G (not-found) ×
  {professor, company, paper, patent}; includes single-entity + list + topic forms.
- **Current**: professor-heavy; **few paper-topic cases**; **no classifier-phrasing-robustness
  cases**; patent only 2 cases.
- **Gap**: add paper-topic + phrasing-robustness + more patent/company-topic.

### 2. Sensitivity — the oracle reflects the change being made
- **Required**: for each lever (Lever 0 partial-papers, Lever 1 professor-readiness, root-A
  classifier), ≥1 case where that lever is the BINDING constraint (the answer is unrecoverable
  without the lever, recoverable with it).
- **Current**: **FAILING** — Lever 0/1 moved the real system but the oracle moved ~0. No case
  where a partial-with-rich-text paper is the answer (Lever 0); no case where a newly-ready prof
  is the answer (Lever 1); no brittle-phrasing case (root A).
- **Gap (concrete cases to add)**:
  - **L0-paper-topic**: a topic query whose answer is a `partial`+rich-text paper (now embedded).
  - **L1-prof-breadth**: a topic query whose answer is a professor promoted to `ready` this session
    (e.g. 周彦/Biostatistics) — was rescue-only, now vector-reachable.
  - **rootA-phrasing (RED today)**: bare "做X教授" / "X 教授" → currently routes `unknown` → 0;
    turns GREEN only when the classifier is hardened. This is a forced-RED regression sentinel.

### 3. Precision — labeled false-positive ground truth
- **Required**: per case, the set of TRUE-positive entities (so false positives are scoreable).
- **Current**: **FAILING** — `eval_precision.py` is v1 labeling-only (no labels); precision has
  NEVER been scored across Lever 0/1 work.
- **Gap**: author `precision-labels.json` (per-case true-positive sets); wire `eval_precision.py`
  to score against it.

### 4. Stability — low run-to-run variance
- **Required**: median over ≥3 runs (the LLM classifier + L3 judge swing qid11/17/20).
- **Current**: **FAILING** — single-run; variance unmeasured.
- **Gap**: a multi-run-median harness (`eval_recall_chat_stable.py`, N=3, median per-case +
  overall). Implementation committed with this spec.

### 5. Ground-truth quality — GT matches DB content
- **Required**: required-entities exist in the DB (else the case is unsatisfiable).
- **Current**: **partial** — known GT mismatches (qid24 web-drafted ≠ DB patents; qid27 GT-4
  blocked; FM1a absent entities 许晋诚/陈功/云迹/九号/擎朗/嘉立创/任尔夫 are NOT in the DB, so
  those cases are unsatisfiable without ingest).
- **Gap**: re-ground GT against the DB; split FM1a-absent cases into a separate "ingest-gated"
  set (not scored until ingested).

## Current completion state

| Criterion | Status |
|---|---|
| Coverage | ~60% (professor-heavy; paper-topic/phrasing/patent thin) |
| Sensitivity | ~0% (no lever-binding cases) — **the core gap** |
| Precision | 0% (labeling-only, never scored) |
| Stability | 0% (single-run) |
| GT quality | ~50% (FM1a-absent + web-drafted mismatches) |

**Overall: ~40% complete.** The benchmark RUNS but cannot reliably gate acceptance until
Sensitivity + Precision + Stability are closed.

## Artifacts committed with this spec

- `eval_recall_chat_stable.py` — multi-run-median stability harness (criterion 4) [to create].
- Sensitivity cases (L0/L1/rootA) added to a sensitivity eval (criterion 2) [to create].
- `precision-labels.json` scaffold (criterion 3) [to create].
- This spec = criteria 1 + 5 + the completion definition.

## "Complete" = all 5 criteria green. Until then, oracle results (e.g. 13/24) are NOT a
reliable Accept signal — they must be read alongside the direct breadth/quality measures.
