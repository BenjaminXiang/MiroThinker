## Why

P9 has refreshed the Professor split Milvus indexes from `miroflow_real` and
verified the BRESAR title in the refreshed identity index. The final P0-P10
stage now needs a user-facing/API validation gate that proves the refreshed
artifact is usable and records launch decisions for the remaining data-quality
risks.

## What Changes

- Add a P10 final-validation contract for the Professor domain.
- Re-run the current P8 audit as a final preflight before user-facing checks.
- Validate the P9 persistent Milvus URI with retrieval-service and API-level
  Professor checks.
- Verify BRESAR, Miha remains visible with `title=助理教授` when the explicit
  quality-filter setting allows it.
- Record the effect of quality-status filtering, because BRESAR is currently
  `needs_enrichment`.
- Inspect representative Professor results for dirty canonical names surfaced
  during P9, including `面包屑`.
- Record final launch decisions for duplicate-risk groups, quality-gate issue
  counts, seed 5 carryover, and skipped cleanup operations.

## Capabilities

### New Capabilities

- `professor-final-validation`: Defines the P10 contract for final Professor
  audit preflight, refreshed-index validation, user-facing/API smokes,
  quality-filter decisions, residual-risk classification, and final artifacts.

### Modified Capabilities

- None.

## Impact

- Affected runtime/scripts:
  - `apps/miroflow-agent/scripts/run_professor_post_full_quality_audit.py`
  - `apps/miroflow-agent/src/data_agents/service/retrieval.py`
  - `apps/admin-console/backend/api/chat.py`
- Affected evidence:
  - `openspec/changes/prof-final-validation/acceptance.md`
  - `.agents/runs/prof-final-validation/verification.md`
- Expected checks:
  - P8 audit command against `miroflow_real`.
  - Professor retrieval-service smokes against `/tmp/p9prof25.db`.
  - API or chat-level smoke where the runtime can be started safely.
  - Targeted tests/lint for any touched code.
