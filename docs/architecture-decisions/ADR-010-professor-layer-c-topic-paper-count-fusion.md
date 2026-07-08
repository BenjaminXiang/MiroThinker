# ADR-010: Professor Layer C — topic-paper-count fusion (retrieval-side, deterministic)

- **Date:** 2026-07-08
- **Status:** Accepted (grilling-validated, empirical)
- **Related:** ADR-009 (company Layer C — synthesis-owned, deliberately contrasted here); `docs/superpowers/specs/2026-07-07-retrieval-generation-rebuild-design.md` (professor Layer C, whose proposed fix this supersedes)
- **Supersedes:** the rebuild design's professor Layer C proposal ("paper-rescue requires `research_topic` real match") — data-blocked.

## Context

Professor topic search (e.g. "清华做视触觉的教授有哪些") buries the gold: 潘挺睿 (视触觉/触觉传感)
retrieved at **rank 7**, behind false positives 黎维彬 (多孔材料) / Tsuboi (线粒体) / 訾牧聪 (水合物)
at ranks 1-3. The synthesis (kill-dump, already shipped) compensates — it features 潘挺睿 and drops
the false positives from the answer — but that compensation is **fragile**: synthesis sees only
`profile_summary[:100]` (vs the reranker's 500 chars), no audit log, borderline-leak risk
(丁文伯=人机交互 leaked for 视触觉), and ±3 run variance.

The rebuild design proposed: "paper-rescue requires `research_topic` real match." **Data-blocked** —
`professor_fact.research_topic` values are mostly empty (潘挺睿/黎维彬/Tsuboi all `[]`).

## Root cause (code-verified)

The one clean precision signal — **topic-paper-count** (a prof with N papers whose title contains
the topic is genuinely on-topic) — is **structurally suppressed**. `_lookup_professors_by_topic`
gates paper-rescue on `len(rows) < limit` (chat.py:2258); 清华深研院 has hundreds of profs, so
vector recall is always thick → rescue never fires → the topic-paper-count signal is never used.
False positives survive because tangential topic mentions in their summaries land them in the
Milvus top-64 and the reranker cannot distinguish core research from tangential mention.

## Evidence (2026-07-08, live DB)

Paper-title signal (verified links: 107k total, 57k `verified`) cleanly separates gold from
false positives:

| professor | verified papers | 触觉/视触/haptic/tactile papers | verdict |
|---|---|---|---|
| 潘挺睿 (gold) | 25 | **4** | gold → should rank #1 |
| 张盛 | — | 2 | likely-legit (gold set incomplete) |
| 丁文伯 | 11 | 1 | borderline → #2-4 |
| 黎维彬 (FP) | 22 | **0** | demote |
| Tsuboi (FP) | 10 | **0** | demote |
| 訾牧聪 (FP) | 23 | **0** | demote |

Simulation — re-rank the retrieved set by `(topic_paper_count DESC, vector_rank ASC)`:
潘挺睿 **#7 → #1**; 张盛 #2, 聂晓梅 #3, 丁文伯 #4; all 6 false positives (0 papers) demoted to
the tail. Deterministic, auditable.

## Decision

**Retrieval-side topic-paper-count fusion** (Layer C — retrieval owns it, unlike ADR-009 where
synthesis owned it):

1. In `_lookup_professors_by_topic`, after vector retrieval (top-64 → rerank → RRF → top-N),
   compute `topic_paper_count` per prof via direct SQL:
   `professor_paper_link JOIN paper WHERE (title_clean/title_raw ILIKE topic-terms) AND link_status='verified'`,
   grouped by professor_id. Topic-terms = query topic + English equivalents
   (视触觉→触觉/视触/haptic/tactile; 灵巧手→dexterous; 具身智能→embodied).
2. **Re-rank by `(topic_paper_count DESC, vector_rank ASC)`** — topic-paper profs first (by count),
   0-paper profs demoted to the tail (not dropped).
3. Synthesis (kill-dump) unchanged — remains the backstop.

No Milvus re-index, no data backfill, no `research_topic` facts, no synthesis change.
Deterministic + auditable → Route-C invariant preserved.

## Why retrieval owns it here (contrast with ADR-009)

ADR-009 (company) made **synthesis** own leader-judgment because "recognized leader" is an
inherently **semantic** signal (no deterministic SQL can rank 优必选 above keyword-spam). Here the
signal is **deterministic and clean** (4 vs 0 topic papers) — so retrieval CAN own it, and should,
to keep the invariant (retrieval auditable; LLM doesn't judge relevance). The two ADRs are
deliberately opposite on the locus question, forced by the signal type.

## Alternatives rejected (with evidence)

- **`research_topic` real match (rebuild design's proposal):** data-blocked — facts are empty.
- **Synthesis-only / harden kill-dump (widen `[:100]`, add paper titles to evidence):** keeps
  relevance judgment implicit, unaudited, variance-prone. Appropriate as a *backstop*, not the
  primary. (The `[:100]` hardening remains a separate minor follow-up.)
- **Hard gate (drop 0-topic-paper profs):** too aggressive — drops legit profs whose papers don't
  title-match the topic; demote-not-drop is safer.
- **Un-suppress the vector paper-rescue:** the rescue uses vector paper search + `get_related_objects`;
  direct SQL title-match is more precise and auditable than vector paper recall.
- **Embed `profile_raw_text` in the research vector:** feasible but requires a Milvus re-index under
  the single-writer lock — heavier; unnecessary given the paper-count signal suffices.

## Known limitation

A prof who works on the topic but whose paper titles don't contain the topic terms is demoted with
the false positives. Mitigations: broad topic terms (Chinese + English), the synthesis backstop,
and graceful degradation (if no prof has topic papers → pure vector rank = current behavior).

## Verification (GREEN criteria)

- 视触觉 POST: 潘挺睿 **#1** in `matched_professors`; false positives demoted to the tail.
- 灵巧手 / 具身智能 professor-topic: non-regression (count-primary sort generalizes).
- Synthesis still features the gold (backstop intact).
- Deterministic + audit-logged (the count + re-rank are SQL, replayable).

## Revision (2026-07-08): re-rank MUST run AFTER the paper-rescue — Verified Accepted

Codex's first implementation wired the re-rank BEFORE the paper-rescue. Live E2E revealed the
gap: for thin-recall topics (视触觉 at 清华深研院 — vector returns only ~6 profs, all false-
positives with 0 topic papers), the gold (潘挺睿, 4 视触觉 papers) enters via the paper→professor
rescue, which APPENDS rescued profs to `rows`. A re-rank wired before the rescue never sees
潘挺睿 → he stays at #7. Fix (Claude, one-line move): re-rank AFTER the rescue block, so it covers
the full set (vector + rescued) and lifts the gold to #1.

Verified: `matched_professors` — 潘挺睿 #1 (was #7); 黎维彬/Tsuboi/訾牧聪 (0 papers) demoted to
the tail; answer features 潘挺睿 first. Audit log: `professor_topic_rerank rows=19 nonzero={…}`.

This generalizes the original root-cause finding (#1 in the session notes): the paper-rescue is
not merely "suppressed when recall is thick" — when recall is THIN it fires and is the gold's
entry path, so the count-fusion re-rank must sit downstream of it.
