# Next-Step Gap-Fill Plan — Deep Investigation (2026-07-02)

> Deep first-principles investigation of how to fill the retrieval-generation gaps next, grounded
> in the root-cause map (`2026-07-02-retrieval-gaps-root-cause-map.md`) + the per-professor gate
> findings. Key shift: the professor path BYPASSES the external-throttling blocker (E).

## The key reframe

The throttling (E) blocks the PAPER path (abstracts from OpenAlex/arXiv) — but NOT the
PROFESSOR path. The professor ready gate (`quality_gate.py`) does NOT require h_index/
citation_count (my earlier assumption was wrong). The GT-4 professors are blocked by
HETEROGENEOUS LOCAL data-quality issues, each resolvable without external sources:

| Professor | Status | Exact gate reason | Fix (local) |
|---|---|---|---|
| 柯文德 | needs_review | `duplicate_verified_paper_links` | dedup the verified paper links the gate flags (same-title/same-content dup, not paper_id dup — my GROUP BY paper_id missed it) |
| 任尔夫 | needs_review | `external_blocking_issue` + `field_contradiction` + `shallow_or_repetitive_profile_summary` | resolve the open pipeline_issue + the field contradiction + re-generate a richer profile |
| 王强 | needs_enrichment | `profile_summary_too_short` + `missing_research_overview_zh` | re-generate a longer profile_summary + add research_overview_zh (LLM from papers/raw text) |
| 刘桂良 | needs_review | `external_blocking_issue` + `field_contradiction` | resolve the open pipeline_issue + the field contradiction |

So qid27 is unblockable WITHOUT resolving E — by per-professor data-quality remediation →
promote → embed (professor_profiles Milvus) → professor vector recall finds them.

## Next-step priority (by leverage × tractability, E-bypass first)

### Path 1 — Professor data-quality remediation → promote+embed (HIGHEST, bypasses E)
- **Lever**: directly unblocks qid27 (professor vector recall) + raises the professor recall
  ceiling (~2338 not-ready professors). No external-source dependency.
- **For the GT-4** (tractable, ~hours): per-professor fix the gate reason (dedup papers /
  resolve pipeline_issue + contradiction / re-gen profile + research_overview) → re-run
  `evaluate_professor_quality` → ready → `run_milvus_backfill --domain professor` → eval-verify
  qid27 GREEN.
- **For the ~2338** (workstream): the same reasons are heterogeneous (duplicate papers,
  contradictions, shallow profiles, missing research_overview) — this is the
  `professor-core-profile-paper-quality` + `professor-fact-cross-format-dedup` workstream
  territory. Batch by reason-class (dedup batch / contradiction batch / profile-regen batch).
- **Blocker**: none external. Per-professor investigative + LLM (profile regen) — local.

### Path 2 — Multi-turn eval harness (parallel, no data dep)
- **Lever**: unblocks 6 coref cases (qid2/4/5/8/10/12 — currently RED because the eval sends
  standalone, no session_id → SessionContext never fires).
- **Fix**: extend `eval_answer.py` to carry session_id across 问题N multi-turn groups (POST
  /api/chat with the prior turn's session) → the system's `_rewrite_query_with_context` resolves
  他/上述企业/这论文 → L1/L3 measurable on multi-turn.
- **Blocker**: none. Pure eval-harness work.

### Path 3 — Paper abstract+summary → promote+embed (BLOCKED by E)
- **Lever**: the ~75% not-ready papers (the big recall ceiling) + the 20 embodied papers for
  qid27's rescue.
- **Fix**: the chain is proven (abstract→summary→promote→embed, 4 done). Complete the 20
  embodied + scale to ~34k.
- **Blocker**: E (OpenAlex 503 / arXiv 429). Must resolve E first (rotate IP / polite-pool
  mailto / wait / cache) OR find the abstracts via Crossref title-search (worked for 4, 429'd
  mid-run — retry with backoff).

### Path 4 — L3 eval stability (parallel, no data dep)
- **Lever**: make the regression gate reliable (L3 variance currently dominates — qid11/17/20
  swing run-to-run).
- **Fix**: averaged runs (3× per case, median) OR a stronger/more-stable judge; then set the
  L3 threshold + enable the gate.

### Architectural roots (A/B/C — DEFERRED, biggest/slowest)
- **A** (pattern-list classifier → learning/normalization-first router): the principled fix for
  FM5/qid11/qid14-class gaps; new query forms keep hitting the rule-list. Big.
- **B** (single-hop recall → graph-aware multi-hop): the principled fix for FM4-class; the
  rescue is one wire-up, the architecture is single-domain. Big.
- **C** (rigid name matching → normalized+fuzzy all types): company fixed; professor/paper
  uninvestigated. Medium.
- These are the durable roots but NOT the binding constraint now (Path 1-4 unblock the eval's
  RED cases first).

## Recommended sequence

1. **Path 1 (GT-4 professors)** — start here. Bypasses E, directly unblocks qid27, local. Sub-
   agent per professor: load state → find the gate reason (done above) → fix it (dedup /
   resolve-issue / re-gen-profile) → re-evaluate → promote → embed → eval-verify.
2. **Path 2 (multi-turn harness)** — parallel, no dep. Unlocks 6 cases.
3. **Path 4 (L3 stability)** — parallel, makes the gate trustworthy.
4. **Path 3 (papers)** — after E is resolved (or Crossref-retry succeeds). The big ceiling.
5. **Architectural A/B/C** — after the eval is mostly GREEN, as the durable fix.

## Why this order (first-principles)

- **E-bypass first**: Path 1 unblocks a measurable eval win (qid27) WITHOUT the environmental
  blocker — highest leverage-per-effort right now.
- **No-data-dep paths parallel**: Path 2 (harness) + Path 4 (L3 stability) need no data/E —
  they expand eval-coverage + reliability while Path 1/3 work on data.
- **E-blocked path queued**: Path 3 (papers) is the biggest ceiling but needs E resolved —
  don't block on it; do Path 1 first (same eval case, professor side).
- **Architectural last**: A/B/C are the roots, but fixing them before the eval is GREEN risks
  over-architecting; the symptom-patches (FM5/qid11/FM4/qid14) cover the eval's current cases.
  Tackle the roots when the eval surfaces that the patches no longer suffice.
