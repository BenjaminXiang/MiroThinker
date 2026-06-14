## Why

P8 post-full Professor quality audit now reports `p9_readiness=ready` after the
CUHK(SZ) SDS BRESAR title repair. The next P0-P10 stage must refresh the
Professor publish/index surfaces from current `miroflow_real` canonical data
with row-level evidence before any final user-facing validation can be trusted.

## What Changes

- Add a P9 publish/index refresh gate for Professor canonical data.
- Re-run the P8 post-full audit as a P9 preflight and explicitly record the
  decision for remaining duplicate-risk and quality-gate issue findings.
- Refresh the Professor split Milvus indexes from `miroflow_real` canonical
  rows using the existing identity and research collections.
- Verify the refreshed index with deterministic counts, BRESAR spot checks, and
  retrieval smoke tests.
- Record skipped operations: canonical duplicate merge, quality-status mass
  promotion, seed 5 unblock attempts, deletion, schema migration, and legacy
  enriched-jsonl publish.

## Capabilities

### New Capabilities

- `professor-publish-index-refresh`: Defines the P9 contract for preflight,
  index refresh, publish evidence, skipped operations, and handoff to final
  user-facing validation.

### Modified Capabilities

- `professor-post-full-quality-audit`: P9 consumes the P8 audit result as a
  preflight gate and must not proceed while P8 reports P9 blockers.
- `professor-retrieval-index-split`: P9 must refresh and verify the split
  Professor identity and research collections from current canonical rows.

## Impact

- Affected runtime/scripts:
  - `apps/miroflow-agent/scripts/run_professor_post_full_quality_audit.py`
  - `apps/miroflow-agent/scripts/run_milvus_backfill.py`
  - `apps/miroflow-agent/src/data_agents/professor/vectorizer.py`
  - `apps/miroflow-agent/src/data_agents/service/retrieval.py`
- Affected tests:
  - `apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py`
  - `apps/miroflow-agent/tests/storage/test_milvus_collections.py`
  - `apps/miroflow-agent/tests/data_agents/professor/test_vectorizer_text_builders.py`
  - `apps/miroflow-agent/tests/data_agents/service/test_retrieval*.py`
- Affected evidence:
  - `openspec/changes/prof-publish-index-refresh/acceptance.md`
  - `.agents/runs/prof-publish-index-refresh/verification.md`
