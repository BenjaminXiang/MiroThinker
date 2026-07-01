# Portfolio — retrieval gap-closure (2026-07-01)

> Per CLAUDE.md §7. Tracks Active / Candidate / Blocked / Frozen / Abandoned / Accepted / Archived
> work for the retrieval-augmented refactor.

## Accepted (contract closed this round)
- **`add-synthesis-timeout`** (OpenSpec, Tiny/low) — delivered 0572d06+8da9053; behavior-affecting
  (3s→60s); validate 0; ledger in-verification. Review: Accept.

## Candidate → Accepted (contract closure; fixes deferred)
- **`fix-chat-retrieval-recall-gaps`** (OpenSpec, Standard/medium) — re-truthed to 58% measured
  (74% non-reproducible, Serper 403); RRF (web OUT); FM3 SHALL; FM1a gate + FM4/FM5 recorded as
  measured/deferred; validate 0; ledger in-verification. Review: Accept (contract closure, NOT
  "recall solved" — deferred gaps explicitly recorded).

## Split verdict
- **`perf-retrieval-keepalive-parallel`** (refactor-contract) — keepalive: Accept (0 GOAWAY,
  deterministic); latency SLO: Accept (p95 5.71s); **D-path parallel: Revise** (non-deterministic
  set 33/35/35, likely cache race, not isolated). Decision needed: isolate / fix / downgrade.

## Blocked / Deferred (proposed skeletons, not implemented)
- **`add-web-augment`** (OpenSpec, Standard/medium, proposed) — Serper 403 (P0 for universal-web
  directive), universal-web on all routes, provenance + precision audit. Blocked on Serper
  credential (user-owned).
- **FM1a ingest** (decision gate in recall change) — 6 absent entities, 67% of misses. Separate
  data-pipeline workstream.
- **FM4 cross-domain paper→professor** (known gap, oracle case 50) — wire `get_related_objects`
  on topic path. Solution doc: `docs/solutions/2026-07-01-retrieval-reach-gaps-fm4-fm5.md`.
- **FM5 strict company-name matching** (known gap, oracle case 51) — normalize + fuzzy +
  `registered_name` in lookup_company. Solution doc: same.
- **Move B / Move C** (the FM4/FM5 fixes) — follow-on changes; design done, not implemented.

## Separate fixes flagged (not gap-closure)
- `test_unit3_b_route_multi_institution_no_filter` — pre-existing bug (multi-institution filter).
- `test_unit4_d_route_retrieves_professor_and_paper_domains_separately` — stale test (D-path now
  includes company per 06ae50b; test expects only prof+paper).

## Oracles (Phase 1, Accepted)
- recall (`eval_recall_chat.py` + `eval_recall.py`) — 58% end-to-end no-web; cases 50/51 added.
- precision (`eval_precision.py`) — false-positive substrate; unsourced_web=0 (Serper dead).
- latency (`eval_latency.py`) — p95 5.71s, SLO ≤6s PASS.
- Evidence: `.agents/runs/retrieval-generation-alignment/{post-fix-recall,precision-baseline,latency-baseline}.json`.
