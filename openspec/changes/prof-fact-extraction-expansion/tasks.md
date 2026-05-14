# Tasks: prof-fact-extraction-expansion

## 1. Child spec review gate

- [ ] T1.1: Review this child spec after
  `prof-quality-status-rework` is scaffolded.
- [x] T1.2: Confirm the existing `professor_fact` status and
  uniqueness patterns before choosing the idempotency key. The schema
  has statuses `active`, `deprecated`, and `superseded`, and no natural
  unique key for facts.
- [ ] T1.3: Confirm which LLM provider/client pattern is approved for
  this backfill.

## 2. Preflight

- [ ] T2.1: Add preflight query for eligible rows with non-empty
  `profile_raw_text`.
- [ ] T2.2: Report missing-summary count and missing target fact counts.
- [ ] T2.3: Add preflight tests against seeded Postgres state.

## 3. Extractor

- [ ] T3.1: Add structured extraction module under
  `src/data_agents/professor/`.
- [ ] T3.2: Define parser/validator for the LLM output shape.
- [ ] T3.3: Add mocked-client unit tests for each target fact type.
- [ ] T3.4: Add low-confidence and malformed-output tests.

## 4. Persistence

- [ ] T4.1: Add idempotent `professor_fact` write helper.
- [ ] T4.2: Preserve source page, evidence span, confidence, status,
  and run id.
- [ ] T4.3: Add repeat-run idempotency tests.
- [ ] T4.4: Add tests proving the active-fact key is
  `professor_id + fact_type + normalized_fact_key`, independent of
  source page and evidence span.

## 5. Backfill runner

- [ ] T5.1: Add a `run_*` style script for preflight and backfill.
- [ ] T5.2: Share profile-text input between fact extraction and
  summary generation.
- [ ] T5.3: Isolate per-professor failures and continue the batch.
- [ ] T5.4: Invoke the Child 1 re-evaluation entry point after
  successful backfill.

## 6. Verification

- [ ] T6.1: Run extractor and persistence unit tests.
- [ ] T6.2: Run runner tests with mocked LLM.
- [ ] T6.3: Run preflight on `miroflow_real` and record counts.
- [ ] T6.4: Run a bounded real backfill sample after review.
- [ ] T6.5: Record before/after quality distribution from Child 1
  re-evaluation.
