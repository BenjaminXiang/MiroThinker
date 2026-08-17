# Tasks: prof-fact-extraction-expansion

## 1. Child spec review gate

- [x] T1.1: Review this child spec after
  `prof-quality-status-rework` is scaffolded.
- [x] T1.2: Confirm the existing `professor_fact` status and
  uniqueness patterns before choosing the idempotency key. The schema
  has statuses `active`, `deprecated`, and `superseded`, and no natural
  unique key for facts.
- [x] T1.3: Confirm which LLM provider/client pattern is approved for
  this backfill.

## 2. Preflight

- [x] T2.1: Add preflight query for eligible rows with non-empty
  `profile_raw_text`.
- [x] T2.2: Report missing-summary count and missing target fact counts.
- [x] T2.3: Add preflight tests against seeded Postgres state.

## 3. Extractor

- [x] T3.1: Add structured extraction module under
  `src/data_agents/professor/`.
- [x] T3.2: Define parser/validator for the LLM output shape.
- [x] T3.3: Add mocked-client unit tests for each target fact type.
- [x] T3.4: Add low-confidence and malformed-output tests.

## 4. Persistence

- [x] T4.1: Add idempotent `professor_fact` write helper.
- [x] T4.2: Preserve source page, evidence span, confidence, status,
  and run id.
- [x] T4.3: Add repeat-run idempotency tests.
- [x] T4.4: Add tests proving the active-fact key is
  `professor_id + fact_type + normalized_fact_key`, independent of
  source page and evidence span.

## 5. Backfill runner

- [x] T5.1: Add a `run_*` style script for preflight and backfill.
- [x] T5.2: Share profile-text input between fact extraction and
  summary generation.
- [x] T5.3: Isolate per-professor failures and continue the batch.
- [x] T5.4: Invoke the Child 1 re-evaluation entry point after
  successful backfill.

## 6. Verification

- [x] T6.1: Run extractor and persistence unit tests.
- [x] T6.2: Run runner tests with mocked LLM.
- [x] T6.3: Run preflight on `miroflow_real` and record counts.
- [x] T6.4: Run a bounded real dry-run sample and record provider/auth
  result. A wet sample is deferred to ops credentials because the local
  configured profile currently returns 401.
- [x] T6.5: Record re-evaluation coverage from the mocked runner and
  note that real before/after quality distribution is blocked until an
  authorized LLM profile is available.
