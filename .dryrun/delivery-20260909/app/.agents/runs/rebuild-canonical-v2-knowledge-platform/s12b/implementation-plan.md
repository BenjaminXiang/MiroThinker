# S12B Four-Domain Candidate Serving Implementation Plan

**Goal:** Complete Task 12.2 as one lean vertical slice from the verified restored SQLite copy to the
normal chat API/UI.

**Architecture:** Normalize only source-backed fields at the S12A mapper boundary, build typed
relationships from explicit source endpoint fields, then load a hash-validated policy/provider
bundle into the already accepted planner/read/answer/runtime composition. The workbook remains an
external acceptance oracle and never enters build or serving code.

## Plan

- [x] Add focused RED tests for real restored Paper, Patent, and Professor field shapes; preserve
      Company behavior and typed gaps for unusable records.
- [x] Implement deterministic four-domain normalization and verify non-zero projections.
- [x] Add focused RED tests for Professor/Paper, Professor/Company, and Company/Patent relationships,
      including missing/cross-release endpoint rejection and path eligibility.
- [x] Implement the three relationship authorities and isolated read traversal needed by customer
      questions.
- [x] Add focused RED tests for a content-addressed, secret-free serving bundle and production
      `--serve` dependency loading.
- [x] Implement planning/Web/answer provider adapters from environment settings and bind the bundle
      to the existing `/api/chat` and `/chat` runtime without active-pointer discovery or writes.
- [x] Run one fresh isolated build, parity audit, and one real chat smoke; update only Task 12.2
      evidence and ledgers when all checks pass.

## Focused verification

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_build_isolated.py -k 'four_domain or customer_relationship'
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py
uv run pytest -q -n0 ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py -k 'serv'
```

The final build/chat commands are recorded with the generated S12B artifact paths in
`s12b/verification.md`; no full-suite run is planned.

## Invariants

- Original sources remain unopened/frozen; only the verified read-only restored copy is admitted.
- Every projected field and relationship retains source assertion/decision lineage.
- Lookup/vector projections bind exactly one Candidate release.
- Serving configuration is content-addressed and contains no credentials.
- No active release pointer is read, changed, promoted, or rolled back.

## Rollback

Remove only S12B code/artifacts and rebuild the isolated target from S12A r12 inputs. No production
state or source bytes require rollback.
