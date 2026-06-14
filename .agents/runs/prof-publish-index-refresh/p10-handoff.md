# P10 Handoff: Professor Final Validation

## Current P9 Checkpoint

- Active P9 change: `prof-publish-index-refresh`.
- Persistent Professor Milvus Lite URI: `/tmp/p9prof25.db`.
- P9 rebuild source database: `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`.
- Rebuild mode: `--rebuild` with `MILVUS_USE_REAL_CLIENT=1`.
- Rebuild result: `profs_total=2344`, `profs_processed=2344`,
  `profs_skipped=0`, `profs_with_errors=0`.
- Persistent collection counts from a fresh process:
  `professor_identity_profiles=2344`, `professor_research_profiles=589`.

## Required P10 Checks

1. Run a fresh P8 audit preflight and confirm `p9_blockers=[]` still holds.
2. Run final Professor retrieval/API checks against the refreshed P9 URI.
3. Verify the BRESAR, Miha CUHK(SZ) SDS result remains visible with
   `title=助理教授` and no contaminated title text.
4. Confirm the quality-status filter setting for user-facing/API checks:
   BRESAR is currently `needs_enrichment`, so `FILTER_BY_QUALITY_STATUS=1`
   will hide that row unless quality remediation is performed first.
5. Inspect representative Professor user-facing results for dirty canonical
   names. The P9 identity smoke surfaced `面包屑` entries near the BRESAR
   result; P10 must decide whether this is acceptable for launch or requires a
   separate cleanup change.
6. Record the duplicate-risk and quality-gate findings from the audit as
   launch residual risks or blockers. P9 did not merge duplicates, mass-promote
   quality statuses, unblock seed 5, delete historical rows, migrate schema,
   publish legacy enriched JSONL, or expand online RAG domains.

## Suggested P10 Evidence

- P8 audit command and parsed summary.
- `/api/chat` or retrieval-service smoke for BRESAR identity.
- A research retrieval smoke against `professor_research_profiles`.
- A quality-filter-on check showing the expected ready-only behavior.
- A quality-filter-off check showing BRESAR title visibility.
- A short operator-facing decision table for residual risks.
