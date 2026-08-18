# Verification Contract: fetch-top-pages-for-enumerations

Created 2026-08-18 before production-code edits.

## Mode

- Deterministic loop logic: unit TDD on `_DualWebLaneAdapter` with fake
  providers + fake page fetcher (RED first).
- RAG-level GREEN additionally requires the full seven-session replay (R2
  gate) with the trace journal showing round-2 views when they fire.

## RED definitions

### RED-1 (5.1): enumeration snippet window too small

- Adapter-level: enumeration-shaped request, fetched page body of 2000+
  chars where the org list starts at char 1300 → current evidence snippet
  cuts at 1200 → list lost. RED asserts the list entries survive.

### RED-2 (5.2): thin round-1 free-rides

- Fake providers return 3 org-looking results on round-1 views; current
  code issues no further searches. RED asserts a refined view set is
  searched (provider call count grows by the refined set size) and merged
  results include round-2 items.

### RED-3 (5.2): rich round-1 does not over-fetch

- 8+ org-looking round-1 results → no additional searches beyond round-1
  views (call count unchanged).

## GREEN gates

1. Unit suites green (new + serving regression).
2. Full replay ALL PASS (R2 gate prerequisite).
3. Trace journal on a live enumeration turn shows fetched-page evidence and
   round-2 views when the refinement fired.
