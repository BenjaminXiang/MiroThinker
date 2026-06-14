# Tasks: prof-lifecycle-state

## 1. Schema

- [x] T1.1: Choose storage shape for lifecycle state and merge target.
- [x] T1.2: Add reversible migration.
- [x] T1.3: Add schema tests or assertions.

## 2. Writers

- [x] T2.1: Ensure professor canonical writes default to `active`.
- [x] T2.2: Add explicit lifecycle update helper for admin/backfill
  use.
- [x] T2.3: Prevent normal pipeline refresh from clearing an explicit
  archived or merged state without evidence.

## 3. Quality and retrieval

- [x] T3.1: Update professor quality evaluator inputs to read lifecycle
  separately.
- [x] T3.2: Ensure lifecycle alone does not force non-ready quality.
- [x] T3.3: Default professor retrieval to active records.
- [x] T3.4: Add tests for active, archived-ready, and merged cases.

## 4. Admin/API

- [x] T4.1: Expose lifecycle state in professor admin detail payload.
- [x] T4.2: Add filtering by lifecycle state where appropriate.
- [x] T4.3: Add audit evidence for lifecycle changes.

## 5. Verification

- [x] T5.1: Run migration/schema tests.
- [x] T5.2: Run professor quality tests.
- [x] T5.3: Run retrieval tests affected by active-default behavior.
