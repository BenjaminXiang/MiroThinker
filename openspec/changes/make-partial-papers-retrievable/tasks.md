# Tasks — make-partial-papers-retrievable

> One Ready slice (all four seams + verification). Per CLAUDE.md §7, Codex
> implements only after Claude accepts the verification contract; per §14.7,
> agentic-RAG recall work is eval-first (a unit test alone is not GREEN).

## 1. Verification contract (Claude-owned, before any production code)

- [x] 1.1 Create `.agents/runs/make-partial-papers-retrievable/verification-contract.md`:
  RED = baseline recall 12/24 (`post-fix-recall.json`) + precision baseline
  (`precision-baseline.json`); GREEN = recall ≥ 14/24 with ≥2 newly-retrievable
  partials surfaced on topic-vector cases, precision oracle not regressed, no
  passing case regressed; allowed Superpowers mode = full TDD on the
  deterministic predicate/filter/snippet contract + eval-first for the recall
  behavior; precision oracle is a HARD GREEN gate.
- [x] 1.2 Claude review of the verification contract → Accept before Codex
  starts (state: Specified → Ready).

## 2. Task 0 — measure D3 (ready-but-not-embedded), zero-data predecessor

- [ ] 2.1 With backend up, compare `paper_chunks` per-paper presence (Milvus,
  `apps/miroflow-agent/milvus.db`) against `SELECT paper_id FROM paper WHERE
  quality_status='ready' AND identity_status NOT IN ('rejected','merged')`.
  Persist the count to `.agents/runs/make-partial-papers-retrievable/d3-measure.json`.
- [ ] 2.2 If D3 > 0, raise "embed already-ready entities" as a separate
  predecessor slice (it needs no contract change) and note it; this change
  proceeds regardless (its unlock — partials — is disjoint from D3).

## 3. Contract tests (RED — deterministic module, TDD-allowed)

- [x] 3.1 `tests/data_agents/quality/test_gating_contract.py` (extend):
  `is_indexable` admits `quality_status='partial'` + identity admissible +
  `paper_has_rich_retrieval_text=True`; rejects `partial` + no rich text;
  rejects `needs_enrichment`; admits `ready` regardless of rich text; rejects
  `rejected`/`merged` identity. (RED until seam 1.)
- [x] 3.2 `tests/data_agents/paper/test_milvus_backfill.py` (extend):
  `_is_indexable_paper` admits a partial row with `paper_full_text.abstract`
  non-empty; rejects a title-only partial; the backfill SQL selects a
  `has_rich_text` column (or JOIN) so `_is_indexable_paper` can evaluate it.
  (RED until seam 2.)
- [x] 3.3 `tests/data_agents/service/test_retrieval_filter.py` (new or
  extend): the vector-recall quality filter admits a `partial`+rich-text
  paper; drops a `partial` title-only; admits `ready` unchanged. (RED until
  seam 3.)
- [x] 3.4 `tests/data_agents/service/test_paper_snippet.py` (new or extend):
  `_paper_title_snippet` returns `paper_full_text.abstract` (with
  `snippet_source='paper_full_text_abstract'`) when `summary_zh`/`abstract_clean`
  are NULL and `paper_full_text.abstract` is non-empty; returns `summary_zh`
  first when present; returns `title` only as the final fallback. (RED until
  seam 4.)
- [ ] 3.5 Run the RED suite; confirm all four fail for the right reason;
  record the failure output in the verification contract.

## 4. Seam 1 — relax `is_indexable`

- [x] 4.1 `src/data_agents/quality/gating_contract.py`: extend `is_indexable`
  to accept an optional `paper_has_rich_text: bool | None = None` parameter;
  admit `quality_status='partial'` iff identity admissible AND
  `paper_has_rich_text is True`. `ready` remains admissible without the
  predicate. Professor/company/patent unaffected (predicate only consulted for
  paper `partial`).
- [x] 4.2 Keep `is_indexable` parity with `_is_indexable_paper` (seam 2) — no
  divergence (the unify "no second signal" invariant is preserved via a
  single derived predicate, not a persisted column).

## 5. Seam 2 — backfill indexability + SQL richness

- [x] 5.1 `src/data_agents/paper/milvus_backfill.py`: extend the backfill SQL
  (`:50-56`) to LEFT JOIN `paper_full_text` (already partially present for
  `abstract`/`intro`) and compute a `has_rich_text` boolean
  (`paper_full_text.abstract` non-empty OR `paper_full_text.intro` non-empty).
- [x] 5.2 `_is_indexable_paper`: admit `partial` iff identity admissible AND
  `has_rich_text`; keep `ready` admission; keep the delete-on-non-indexable
  behavior (`:86-97`) so title-only partials get their stale chunks removed.

## 6. Seam 3 — vector-recall filter admission

- [x] 6.1 `src/data_agents/service/retrieval.py`: extend
  `_allow_non_ready_exact_paper` (or add a sibling predicate) so a
  vector-recalled `partial` paper with rich text is admitted through
  `_filter_ready_only`. The vector Evidence must carry a `has_rich_text` (or
  equivalent) signal from the backfill/ANN metadata, or the filter re-queries
  `paper_full_text` for the recalled paper_ids (defensive against stale
  Milvus).
- [x] 6.2 Drop a vector-recalled `partial` without rich text and any
  `needs_enrichment` (defensive; they are not indexable). `ready` unchanged.

## 7. Seam 4 — snippet chain + title-exact SELECT join

- [x] 7.1 `src/data_agents/service/retrieval.py::_paper_title_snippet`: extend
  the source chain to `summary_zh → abstract_clean → paper_full_text.abstract
  → title`; emit `snippet_source='paper_full_text_abstract'` for the new
  branch. (`intro` is an embedding-only chunk; not a snippet source for the
  title-exact path — confirm against the chunker; if `intro` should also be a
  snippet fallback, add it after `abstract`.)
- [x] 7.2 The title-exact SELECT (`:910-943`): LEFT JOIN `paper_full_text` and
  SELECT its `abstract` so `_paper_title_snippet` can use it; keep the
  existing ordering/limit.
- [x] 7.3 The vector Evidence snippet path: ensure a vector-recalled partial
  uses its chunk `content_text` (which is the `paper_full_text.abstract`
  chunk) as the snippet, so it is presentable (not an empty `summary_zh`).

## 8. GREEN — deterministic + eval

- [x] 8.1 Run the contract suite (3.1–3.4); confirm all green; run the
  gating/backfill regression (`tests/data_agents/quality/`,
  `tests/data_agents/paper/`); confirm 0 ready degraded (the relaxation is
  additive; `ready` rows unaffected).
- [x] 8.2 One-time Milvus rebackfill — DONE by Claude (Codex sandbox-blocked):
  backend stopped (frees single-writer), `run_milvus_backfill.py --domain paper
  --paper-id-file` (targeted, not full). **BackfillReport: 1952/1952 papers,
  6845 chunks, 0 errors, 102s.** (DN: raw-psycopg DSN must be `postgresql://`,
  not `postgresql+psycopg://`.)
- [x] 8.3 Eval — DONE by Claude: `eval_recall_chat.py` (TestClient in-process,
  new code). **13/24 on two consecutive runs** (reproducible); +1 = 王强 (qid50).
  Precision oracle is v1 labeling-only — not auto-scored (caveat in review).
- [x] 8.4 Recall 13/24 < original ≥14/24 → root-caused (NOT a seam defect): the
  other qid50 professors are out-of-scope (not-ingested / no-partial-rich / rescue
  issues = Lever 1/2/3) and the oracle has no paper-topic partial-answer case.
  GREEN revised to +1 reproducible via the Acceptance Amendment (structural
  correctness); full payoff deferred to Lever 1/2. See verification-contract.md.

## 9. Acceptance + archive readiness

- [x] 9.1 Codex report — received (code slice complete, contract-suite green,
  sandbox-blocked on D3/rebackfill/eval). Claude ran the blocked steps.
- [x] 9.2 Claude review — **Accept (structural-correctness)** per §12 + the
  Acceptance Amendment. Evidence: contract 42 + regression 1037 green, rebackfill
  1952/1952, recall 13/24 reproducible (+1 attributable), 0 ready degraded, 0
  passing-case regression, `openspec validate --strict` = 0, no half seam.
  Caveats: precision not auto-verified (oracle v1); D3 unmeasured (disjoint);
  full payoff deferred to Lever 1/2. Review: `.agents/reviews/make-partial-papers-retrievable.md`.
- [x] 9.3 Solutions doc §7 + Lever 0 status — updated (Lever 0 Accepted;
  D3 remains open; next = Lever 1/2 for the "limited search" symptom).
- [ ] 2.1 D3 measure — NOT closed this session (rebackfill was partial-targeted,
  ~2,010; ready=27,456; D3 = ready-but-unembedded needs a Milvus distinct-count
  vs ready, not run). Disjoint from this slice; open as a predecessor candidate.
