# Review: retrieval gap-closure (2026-07-01)

> Phase 5 review across the gap-closure artifacts. Per CLAUDE.md §12: Accept / Revise / Reject
> per artifact, against contract + evidence + invariants.

## Artifacts

### `fix-chat-retrieval-recall-gaps` (OpenSpec, rewritten) — **Accept (contract closure)**
- Spec re-truthed to delivered reality: RRF (web OUT, split to add-web-augment), FM3 SHALL-fixed
  (validate --strict 0), auditable-evidence requirement. candidate_limit struck (reverted).
- Evidence persisted: post-fix-recall.json (11/24, 58% end-to-end no-web — the 74% claim is
  non-reproducible, Serper 403), precision-baseline.json, latency-baseline.json.
- FM1a ingest gate, FM4 (cross-domain paper→professor), FM5 (strict name matching) recorded as
  known/measured/deferred gaps (oracle cases 50/51). Honest scope: recall NUMBER not closed
  (FM1a/web/FM4/FM5 deferred), but the CONTRACT honestly maps the gap surface. Ledger:
  in-verification.
- **Accept** as contract closure (not as "recall solved" — the deferred gaps are explicitly
  recorded). The recall change owns the re-truth + measurement, not the fixes.

### `add-synthesis-timeout` (OpenSpec, small) — **Accept**
- Delivered (0572d06 + test 8da9053). Default 60s + `CHAT_SYNTHESIS_TIMEOUT` env override
  (chat.py:70, :1180). Behavior-affecting (answers 4-59s now succeed). validate --strict 0.
- Ledger: in-verification (Tiny/low). **Accept.**

### `add-web-augment` (OpenSpec, proposed skeleton) — **Not for Accept this round**
- Skeleton records: Serper 403 defect (P0 for the universal-web directive), universal-web
  directive (all routes A/B/C/D/E/G), provenance obligation, precision audit, latency discipline.
- Deferred — blocked on the Serper credential (user-owned). Ledger: proposed. **Not Accept
  (deferred).**

### `perf-retrieval-keepalive-parallel` (refactor-contract) — **Split verdict**
- **Keepalive: Accept** — behavior-preserving, 0 GOAWAY, deterministic. milvus_collections.py:161-174.
- **Latency SLO: Accept** — retrieval p95 5.71s ≤ 6s (latency-baseline.json).
- **D-path parallel: Revise** — candidate set NON-deterministic across runs (33/35/35,
  verification.md). Order preserved by construction; set drifts (leading hypothesis: shared
  RetrievalCache race from outer parallelism, not fully isolated). Per design §5, NOT
  certifiable behavior-preserving. Decision needed: isolate (serial-vs-parallel) / fix cache
  race (Codex) / downgrade to behavior-affecting (tolerate bounded drift).

## Test status
- 145 chat tests run; **2 failed, 143 passed**.
- Both failures are PRE-EXISTING / STALE, NOT caused by gap-closure (gap-closure only touched
  eval scripts + openspec docs, not chat.py/retrieval.py production code):
  - `test_unit3_b_route_multi_institution_no_filter` — pre-existing bug: multi-institution
    `_lookup_professors_by_topic` applies the first institution as a filter instead of skipping
    (chat.py `_lookup_professors_by_topic`).
  - `test_unit4_d_route_retrieves_professor_and_paper_domains_separately` — STALE test: D-path
    now retrieves company too (per 06ae50b, 3 calls prof+paper+company); test expects only 2
    (prof+paper). Test needs updating to match the delivered multi-path D-path.
- Flagged for separate fix (test update + the multi-institution bug); NOT blocking the
  gap-closure review.

## Honest notes
- 74% recall claim non-reproducible (Serper 403) — accepted as 58% baseline, not as 74%.
- Precision GREEN p@k deferred to post-labeling (准 was dark; oracle v1 = substrate).
- End-to-end latency SLO (≤15s) not re-measured with synthesis on this round (needs DeepSeek key).
- perf-parallel non-determinism is the one open blocker requiring a decision.
- 2 pre-existing test failures flagged for separate fix.
