# Slice contract — paper-retrievability-baseline

> Claude-owned. **Measurement slice** — adds eval cases + runs baselines; NO
> production-code change, so no OpenSpec change required (behavior-preserving per
> CLAUDE.md §8). Establishes the **behavioral retrievability baseline for the paper
> domain** that the structural analysis cannot provide. Model-facing artifact —
> English per [[language_preference]]. Grounded in the 2026-07-09 grill session +
> `docs/solutions/2026-07-03-data-gap-first-principles.md`.

## Why (first principles)

The user's question — "are all papers retrievable? the whole point of collecting
and cleaning paper data is to make them retrievable-and-generatable for user
questions" — has a **structural** answer (already measured) and a **behavioral**
answer (not yet measured). This slice produces the behavioral answer for papers.

Structural retrievability (CAN a paper physically be retrieved) is already
quantified by `docs/solutions/2026-07-03-data-gap-first-principles.md` §3 + §9:

| Paper status | Count | Retrievable? | Why |
|---|---|---|---|
| `ready` | 25,990 | yes | full gate passed |
| `partial` + rich text (full text collected) | ~1,952 | yes (**was no** — Lever 0 fixed) | `summary_zh` NULL was the only block; pure structural waste |
| `partial` title-only | ~7,212 | **no (deliberate)** | only a title chunk → precision risk |
| `needs_enrichment` | 14,343 | **no** | 0 have full-text abstract → genuinely data-poor |

≈ 56% retrievable / 44% not; the 44% is mostly deliberate (precision / no data),
not a bug. The retrieval LOGIC is sound; the paper ceiling is DATA (Lever 3).

**What is NOT measured**: behavioral retrievability — "if a query is strongly
relevant to a paper in the DB, does the pipeline actually surface AND cite it?"
Structural soundness does not prove behavioral soundness (the embedding-source ⊋
snippet-source "recalled-but-invisible" defect was exactly a bug structural
analysis could not catch). And today the oracle has ≈0 paper-anchored cases, so
there is no paper-domain recall or true-accuracy number at all.

## Contract (grilling output, grounded in code)

- **Relevance-conditional, two-sided.** Recall side: for any (query Q, paper P)
  where P is *strongly relevant* to Q, P MUST be retrieved into candidates AND
  cited in the answer. Precision side: if P is irrelevant to Q, it should NOT be
  cited.
- **Structural vs behavioral retrievability (this slice's framing).**
  - Structural (capability): `is_indexable` + embedded + passes vector-recall
    filter + non-empty snippet — the 4 seams. **Done/measured** (Lever 0).
  - Behavioral (obligation): strongly-relevant → surfaced + cited. **Unmeasured
    for papers. This slice measures it.**
- **Relevance judged by LLM-judge** (= existing `eval_true_accuracy.py`,
  deepseek-v4-pro, temp=0, synthesis ON). Not a new direction.
- **Query distribution = reuse + extend the existing oracle**
  (`eval_recall.py` CASES + `tests/fixtures/test_cases.yaml`).
- **Two measurement legs:**
  - Retrieval leg → `eval_recall.py` / `eval_recall_chat.py` (synthesis OFF,
    entity-substring in top-K / JSON; domain=`paper`).
  - Generation leg (combined) → `eval_true_accuracy.py` (LLM-judge, synthesis ON).
  - Known seam: neither eval isolates "retrieved-but-not-cited"; recorded as a
    logged limitation, not a blocker.

## Slice A scope (this slice)

1. **Author paper-anchored oracle cases** — structural gold, 4 query types (below).
2. **Run the baseline** — paper-domain recall + paper-domain true-accuracy.
3. **Set the bar** — after the baseline number exists (baseline-first; user
   confirmed). Interim target ≥80% paper-domain recall; remaining-unreachable
   gaps logged in FM1a/FM4/FM5 discipline (like `fix-chat-retrieval-recall-gaps`),
   not a blind chase to 100%.

### The 4 paper-query types + structural gold sources

| Type | Query shape | Structural gold (Postgres-grounded) | Notes |
|---|---|---|---|
| 1. Title-self | query = paper title / core topic | the paper's distinctive identifier | like existing qid16 (pFedGPA); tests per-paper self-retrievability |
| 2. Professor→paper set | "X教授关于Y的论文" | papers authored by X ∩ topic Y, via professor↔paper link (`link_status='verified'`, `identity_status='resolved'`) | **FM4 territory** — cross-domain retrieval leg |
| 3. Company→paper | "X公司相关的论文" | papers linked to company X | cross-domain |
| 4. Topic→paper | "关于Y技术的论文" | papers whose `abstract_clean` matches topic Y | structural gold weakest here (semantic) → LLM-judge true-accuracy is the complementary measure |

Authoring principle: **structural gold feeds the recall eval (auditable, no judge
noise); handwritten standard answers feed true-accuracy (semantic quality).**
Relevance judgment belongs to the LLM-judge; candidate enumeration belongs to
structure. (The independent candidate-generator for measuring recall of *unlisted*
relevant papers — Q3 — is deferred; see Caveats.)

## RED (true today — demonstrably absent)

- **No paper-domain recall number.** `eval_recall.py` CASES has exactly 1
  `domain="paper"` case (qid16, pFedGPA). n=1 → statistically meaningless.
- **No paper head-turn in `test_cases.yaml`** for `eval_true_accuracy.py` (the
  one "论文" mention is a follow-up turn, not a head-turn).
- **Candidate-generator blind spot**: recall only checks LISTED required papers;
  it cannot discover a strongly-relevant paper that retrieval never surfaced.
  Therefore any baseline recall is a **lower bound**, not a ceiling.

## GREEN (done criteria — all required)

- ≥N (target ~12–15) paper cases authored across the 4 types, with structural gold
  verified against Postgres (real paper_ids / authorship links), committed to
  `eval_recall.py` CASES + `test_cases.yaml` head-turn cases.
- **Paper-domain recall** number produced + persisted
  (`.agents/runs/retrieval-generation-alignment/` + this dir).
- **Paper-domain true-accuracy** number produced + persisted.
- **Bar set**: an explicit target (interim ≥80% recall) with the residual gaps
  logged (which types/papers miss, and the Lever they map to).
- **Known limitations recorded**: lower-bound caveat; Milvus single-writer
  sequencing (below); "retrieved-but-not-cited" seam unmeasured.
- No production code touched; no migration; no persisted column.

## Caveats / constraints

- **Lower bound.** Baseline recall under-counts missed-but-relevant papers until
  the independent candidate-generator (Q3) lands. A "good" early number MUST NOT
  be read as "all papers are behaviorally retrievable." This is the explicit
  reason the bar is set AFTER the baseline, not before.
- **Milvus single-writer (per [[milvus-single-writer-real-index]]).** The two
  evals have conflicting backend needs: `eval_recall_chat.py` is TestClient
  in-process (needs backend DOWN / no single-writer conflict); `eval_true_accuracy.py`
  is HTTP to live backend :18188 (needs backend UP). **Sequence them** — do NOT
  run both simultaneously. `eval_recall.py` (pure retrieve() diagnostic) may be
  the lower-friction recall measure if TestClient conflict bites.
- **Proxy unset for any localhost step** (per [[env_proxy_bypass]]):
  `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY`.
- **Codex sandbox blocks localhost.** Codex can write the authoring tooling /
  case schema; the case-DB-grounding + eval RUN is localhost → Claude/user-owned
  (same pattern as `make-partial-papers-retrievable` handoff §localhost).
- This slice MEASURES; it does not FIX. The dominant paper-retrievability fix is
  Lever 3 (slice B), pursued only after this baseline quantifies the hole.

## Files

- Author: `apps/admin-console/scripts/eval_recall.py` (CASES — add paper cases)
- Author: `apps/admin-console/tests/fixtures/test_cases.yaml` (paper head-turn cases)
- Run: `eval_recall.py` / `eval_recall_chat.py` (recall leg); `eval_true_accuracy.py` (generation leg)
- Persist: `.agents/runs/retrieval-generation-alignment/{paper-recall-baseline,paper-true-accuracy-baseline}.json` + this dir

## Deferred — Slice B (Lever 3, after this baseline)

Abstract backfill for the ~14,343 `needs_enrichment` papers (the dominant
paper-retrievability ceiling; E-gated OpenAlex + local PDF/intro bypass). Pursued
only after this baseline quantifies the paper-domain recall hole and prioritizes
the lever. Separate change; not started here.

## References (source of truth)

- `docs/solutions/2026-07-03-data-gap-first-principles.md` — keystone structural analysis (§3 paper breakdown, §9 status, Levers 0–4)
- `openspec/changes/make-partial-papers-retrievable/` + `.agents/runs/make-partial-papers-retrievable/verification-contract.md` — Lever 0 (structural retrievability, Accepted)
- `openspec/changes/make-professors-retrievable-beyond-ready/proposal.md` — retrievability≠completeness contract
- `apps/admin-console/scripts/eval_{recall,recall_chat,true_accuracy,precision}.py` — the eval harness
- `apps/admin-console/tests/fixtures/test_cases.yaml` — the shared oracle (recall + true-accuracy)
