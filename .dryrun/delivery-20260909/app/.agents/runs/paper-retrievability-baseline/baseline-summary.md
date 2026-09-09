# Paper-retrievability baseline (2026-07-09)

> Behavioral retrievability baseline for the PAPER domain. Retrieval leg (synthesis OFF).
> Companion to `slice-contract.md`. Numbers are a **lower bound** (candidate-generator Q3
> deferred). Methodology per [[validation_methodology_fresh_fetch]] — run against the live
> `miroflow_real` DB + real Milvus index, backend cycled for the in-process eval.

## Headline

**Paper-domain e2e recall = 7/20 (35%)** — but the headline hides that retrievability is
**path-dependent**. Decomposed by access path:

| Type | Access path | Result | Verdict |
|---|---|---|---|
| 1 | by paper title (self) | **6/6 (100%)** | ✅ ready papers ARE retrievable by title |
| 2 | professor → their papers | **1/9 (11%)** | ❌ cross-domain traversal weak (FM4-reverse) |
| 4 | topic → papers | **0/4 (0%)** | ❌ paper-topic queries misclassified `unknown` |
| 3 | company → papers | **n/a** | ⚠ no structural gold: `professor_company_role` is empty |

**Answer to "are all papers retrievable?": A paper is retrievable when you ask for IT directly
(100%), but NOT when you ask for it via a professor (11%) or a topic (0%).** Retrievability is
gated by the access path, not by the paper's indexability.

## Method + two eval runs

| Eval | Path | synth | Paper result | Note |
|---|---|---|---|---|
| `eval_recall.py` | single-domain `retrieve(domains=("paper",))` | off | 4/20 (20%) | noisy: snippet chain is `summary_zh→abstract→title`, so ready papers with `summary_zh` yield a **Chinese** snippet → English title tokens false-miss (qid102/103/105) |
| `eval_recall_chat.py` | full `/api/chat` (routing + cross-domain) | off | **7/20 (35%)** | primary; checks full JSON, resolves snippet-language artifact; Type1 → 6/6 |

Overall e2e (all domains): **21/43 (49%)**. Historical 13/24 preserved at
`post-fix-recall.pre-paper-baseline-2026-07-09.json`; new run overwrote `post-fix-recall.json`.

## Failure-mode analysis (the actionable part)

### Type1 — self-retrievability: WORKS (6/6)
A `ready` paper is retrieved end-to-end when queried by its own title (ShuffleNet V2, ESRGAN,
MoS2, Memristors, TRPV1, Polymer electrolytes all OK via `A_paper_profile`). **Structural
retrievability (Lever 0) is functioning for direct lookup.** (The 3 "misses" in `eval_recall.py`
were snippet-language false-negatives, confirmed by the e2e pass.)

### Type2 — professor → papers: WEAK (1/9) — FM4-reverse gap
"X教授发表了哪些论文" is classified `A_prof_profile` → returns the professor's profile, which
incidentally lists some papers (常瑞华→VCSEL hit; 刘江/陈勇勇→0). There is **no dedicated
professor→paper traversal** that pulls the professor's `professor_paper_link` papers into the
answer. This is the reverse of FM4 (which is paper→professor). Fix lever: wire a professor→paper
traversal on the `A_prof_profile` paper-subquestion (analogous to the shipped
`_lookup_professors_by_topic` rescue, but reversed).

### Type4 — topic → papers: ZERO (0/4) — classification gap
"关于perovskite钙钛矿材料的论文有哪些" and "关于联邦学习federated learning的最新论文" are both
classified **`unknown`** (not `B_semantic_topic_search`), so no topic retrieval runs at all.
The perovskite/FL papers DO exist and ARE vector-retrievable (single-domain `eval_recall.py`
surfaced "Hybrid Perovskite"/"FedTC" snippets) — they are blocked at the **query classifier**,
not at retrieval. Fix lever: classifier must route paper-topic queries to a paper topic-search
path. **This is a new finding, absent from the 2026-07-02 root-cause map.**

### Type3 — company → papers: structurally DEAD (no gold)
`professor_company_role` is **empty** (0 rows, all link_status). There is no `company_paper_link`
table. So the company→professor→paper chain has no data — company-paper cross-domain
retrievability has **no structural backing at all**. Recorded as a data gap (separate from
retrieval logic). The company↔professor link population is its own data workstream.

## Bar (set from this baseline)

Type-aware, not a single % (a single 35% hides the path-dependence):
- **Type1 (self): hold 100%** — no regression tolerated.
- **Type2 (professor→paper): 11% → ≥80%** — needs the professor→paper traversal fix.
- **Type4 (topic→paper): 0% → ≥80%** — needs the classifier fix FIRST (paper-topic → topic search,
  not `unknown`), then topic recall.
- **Type3 (company→paper): unblockable until `professor_company_role` is populated.**
- If Type2 + Type4 reach ≥80%, overall paper recall ≈ (6 + 7.2 + 3.2)/20 ≈ **82%** — so the
  interim ≥80% overall target is achievable from the retrieval/classification fixes alone,
  WITHOUT Slice B (Lever 3 data backfill).

## Gaps → levers (prioritized)

| Gap | Root cause | Lever | E-gated? |
|---|---|---|---|
| Type4 0% | query classifier → `unknown` for paper-topic | classifier fix (NEW finding) | no (local) |
| Type2 11% | no professor→paper traversal | wire traversal (FM4-reverse) | no (local) |
| Type3 dead | `professor_company_role` empty | data: populate company↔professor links | data workstream |
| headline ceiling | ~24,285 `needs_enrichment` papers have no abstract | **Slice B / Lever 3** abstract backfill | yes (OpenAlex) + local PDF |

## Deferred

- **Generation leg (true-accuracy, synthesis ON + LLM-judge):** not run. Retrieval is the binding
  constraint (you cannot cite what was not retrieved/classified), so the Type2/Type4 diagnosis is
  unchanged by synthesis. The generation leg would only test the "retrieved-but-not-cited" seam
  on Type1 (where retrieval is 100%) — a refinement, run after the Type2/Type4 fixes surface more
  retrieved candidates. Needs paper head-turn cases in `tests/fixtures/test_cases.yaml`.
- **Slice B (Lever 3):** the dominant data ceiling (~24,285 needs_enrichment papers, up from
  14,343). Pursued after this baseline per the A→B decision.

## Repro

```bash
# backend DOWN (Milvus single-writer free; per [[milvus-single-writer-real-index]])
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
cd apps/admin-console
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 \
uv run python scripts/eval_recall.py --top-k 10          # single-domain diagnostic + per-domain rollup
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_recall_chat.py                # e2e /api/chat (primary)
```
