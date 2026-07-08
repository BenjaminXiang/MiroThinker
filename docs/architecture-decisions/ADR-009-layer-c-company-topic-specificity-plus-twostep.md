# ADR-009: Layer C company-topic — specificity-floor retrieval + two-step leader selection

- **Date:** 2026-07-07
- **Status:** Accepted (grilling-validated, empirical)
- **Supersedes:** the frequency `core_score` in `d365a6c` (partial, recall-neutral); the reverted rerank-over-top-30 attempt
- **Related:** `docs/superpowers/specs/2026-07-07-retrieval-generation-rebuild-design.md` (Layer C), ADR lineage in `docs/architecture-decisions/`

## Context

Company topic search (e.g. "深圳有哪些做具身智能的公司") must surface recognized
industry leaders. Stuck symptom: golds **无界智航 / 优必选 / 越疆** were not surfacing.
The prior handoff diagnosis ("118 over-match, keyword can't distinguish, name tiebreak")
was **wrong**, verified against the live DB on 2026-07-07:

- All three golds are **in-DB with strong core signals** → Layer C (precision), NOT Layer E
  (coverage): 无界智航 mentions `具身智能` ×15 in core text, 越疆 ×8, 优必选 ×9.
- Under the then-current `core_score` — a count over **all** `term_groups`, including the
  generic `智能` / `AI` / `人工智能` expansion (added because "具身智能" contains "智能") —
  the golds ranked **越疆 #30, 无界智航 #32, 优必选 #52**, buried behind keyword-spam:
  蓝色涌现 ("海洋户外科技" / marine toys) and 缔宙 ("AI基础软件", 注册资本100万) ranked
  #1–2. The single most famous Shenzhen robotics company (优必选, founded 2012) was #52.
- Scoring on the **specific** term only lifts 无界智航 #32 → #4 — but 优必选 stays #20 and
  越疆 #37. Frequency cannot encode "recognized leader"; it encodes verbosity.
- Deterministic magnitude (funding / patents / products) is **data-blocked**: the funding
  field is empty even for 优必选; product-count is noise-inverted (spam 缔宙 has 7 products
  vs 优必选's 5).
- A business-keyword pre-filter cuts 38 spam but **also drops 3 real golds** (卧安 / 商汤 /
  丘脑) and still buries 优必选 #20 / 越疆 #33.

## Decision

Two **complementary** mechanisms, each validated empirically:

1. **Retrieval specificity-floor (deterministic, auditable — Route-C pure).** Score
   `_lookup_companies_by_topic` on the **specific** topic term(s) only — exclude the generic
   `智能`/`AI`/`人工智能` expansion group from `score_terms` (keep it in the match predicates,
   so broad recall is unchanged). Lifts high-specificity golds (无界智航 → top-10). Tiny,
   reversible, one-line-ish change.

2. **Two-step synthesis leader-selection (semantic, in the synthesis layer).** Widen
   retrieval `LIMIT` 30 → ~45; add a **Step-1 LLM call** that selects ~10 recognized leaders
   from a compact leaderboard (name + business + profile-head + specific-count); enrich
   **only those**; Step-2 synthesizes via the existing kill-dump path. Surfaces
   famous-but-low-frequency leaders and rejects spam.

The LLM judges **only a deterministically-retrieved set** — it never writes queries — so the
CLAUDE.md §5 / Route-C invariant (retrieval deterministic + auditable; no agentic retrieval)
is preserved. LLM judgment lives in the Layer-A synthesis layer, exactly where Route-C puts
reasoning.

## Evidence (deepseek-v4-pro, temperature=0, 2026-07-07)

Leaderboard-selection probe over the top-40 具身智能-mentioners:

- **优必选** (retrieval rank #20) → selected **#1** ("全球人形机器人龙头")
- **越疆** (retrieval rank #37) → selected **#9** ("智能机械臂领军企业")
- **乐聚** → selected #3
- Spam correctly **rejected**: 缔宙 (AI软件), 极数迭代 (数据标注), 感进 (扫地机),
  亮源/枣橙 (陪伴), 国际先进技术应用推进中心 (机构).
- **无界智航 NOT surfaced** by LLM selection — a genuine *recognition gap* (less famous),
  not an info problem. It is caught instead by the **specificity-floor** (retrieval rank #4).
  This complementarity is by design.

## Alternatives rejected (with evidence)

- **Frequency `core_score` (`d365a6c`):** buries leaders (优必选 #52). Measures verbosity,
  not leadership. Recall-neutral 38% was structurally inevitable, not a tuning miss.
- **Rerank over top-30 (reverted):** failed because the candidate pool was
  frequency-contaminated (优必选 #52 was never in the top-30). Rerank cannot surface what is
  not in its input. Rerank **over the full pool** remains a fallback if Step-1 selection
  proves unreliable on other topics.
- **Deterministic significance prior (funding/patents/products):** data-blocked (funding
  empty, product-count inverted). Would require a Layer-E backfill.
- **Business-keyword pre-filter:** cuts real golds (卧安/商汤/丘脑) and still buries 优必选 #20.
- **Company vector embeddings (6514):** viable but heavier; deferred — two-step achieves the
  goal without it. Embedding 6.5k short texts is cheap; the real friction is the Milvus
  single-writer lock while the backend is up.

## Consequences

- +1 LLM call (~1–2 s) per company-topic query. Accuracy > latency >> cost per the rebuild.
- Synthesis enrichment bounded to ~10 (not 45) — cost controlled.
- Stale claim corrected: `canonical_name` NULL pollution is **false** for the `company`
  table (0 null / 0 empty of 6514). Do not act on it.

## Verification (GREEN criteria)

- Retrieval probe: 无界智航 in top-10 after the specificity fix; 优必选/越疆 surfaced after
  the two-step selection.
- Leaderboard-selection probe (already green): leaders surfaced, spam rejected.
- `eval_true_accuracy`: 具身智能 case improves; PCB / delivery / medical non-regression.

## Revision (2026-07-07): additive union — Verified Accepted

The first implementation made Step-1 selection **authoritative** (retrieval top-45 → Step-1
picks 10 → those only). Live E2E (`POST /api/chat "深圳有哪些做具身智能的公司"`) revealed the
gap: 无界智航 was lifted to **retrieval pool rank #4** by the specificity-floor, but Step-1
**dropped it** (deepseek's recognition gap), so it never reached the answer. The two mechanisms
were chained, not unioned.

**Fix (Codex Revise, accepted):** Step-1 is now **additive** —
`final = dedup( Step-1_selected ∪ specificity_top5 )`, leaders-first, capped at 15
(`_compose_company_topic_selection`). The fallback path also gets the union, so 无界智航
surfaces even if Step-1 fails. Unit RED→GREEN: 8 tests pass (incl. "LLM-missed
high-specificity candidate still appears" + "fallback also adds specificity top-K").

**Verified E2E (2026-07-07, live backend, new code):**
- 无界智航 → **SURFACED** (matched_objects rank 12, answer citation [13]) — the namesake
  stuck case is fixed.
- 优必选 → **#1**, featured first in the answer (was retrieval #52 originally).
- 乐聚 → surfaced.
- Spam (缔宙/蓝色涌现) absent from the answer; specificity-topK additions (极数迭代/格松/诺因)
  are on-topic embodied companies — the accepted trade-off.

**Known limitation — 越疆:** still not surfaced. It is specificity rank #37 (outside the
top-5 union guarantee) and Step-1 picks it only sometimes (variance). Guaranteeing 越疆 would
require K≥37 (floods the set with spam) — steep diminishing returns. Left as
Step-1-dependent; a follow-up may revisit if 越疆 matters enough.

**Eval-infra caveat:** `eval_true_accuracy` could NOT validate regression this round — its
in-process Milvus Lite fails to bind the socket after the backend is killed
(`Connection refused on …milvus.db.sock`), contaminating vector-retrieval cases. Non-regression
is instead covered by Codex's unit-regression suite (11 existing tests pass:
multi-domain-entity-stack / classifier-b-g-tune / synthesis-depth). Fixing the eval's in-process
Milvus startup is a separate follow-up.

## Open follow-ups

- Generalize the specificity-floor rule: only exclude the generic group when a more specific
  compound term exists in the same query.
- Professor Layer C (视触觉 false positives, vector-fusion path) — separate slice.
- 越疆 surfacing (Step-1-dependent today) — revisit if needed.
- Fix `eval_true_accuracy` in-process Milvus Lite startup so it can run with the backend down.
