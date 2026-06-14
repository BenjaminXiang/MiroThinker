# Tasks: patent-page-only-canonical

## 1. Storage decision

- [x] T1.1: Choose nullable canonical row vs candidate table.
- [x] T1.2: Record decision rationale in `design.md` before code edits.
- [x] T1.3: Add reversible migration for the chosen strategy.

## 2. Writer behavior

- [x] T2.1: Write title-only page patent candidates without losing
  evidence.
- [x] T2.2: Set initial status to `needs_enrichment`.
- [x] T2.3: Keep numbered patents on hard patent-number matching.
- [x] T2.4: Add idempotency tests for repeated page ingest.

## 3. Promotion behavior

- [x] T3.1: Define how a later numbered patent promotes or merges a
  title-only candidate.
- [x] T3.2: Add tests for promotion/merge.
- [x] T3.3: Ensure rejected malformed candidates remain diagnostic and
  do not become canonical ready rows.

## 4. Verification

- [x] T4.1: Run patent homepage ingest tests.
- [x] T4.2: Run migration/schema tests.
- [x] T4.3: Run a bounded page sample containing title-only patents, or
  record why no real sample is available.
