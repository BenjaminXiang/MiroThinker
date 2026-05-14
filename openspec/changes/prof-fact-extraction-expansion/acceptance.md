# Acceptance: prof-fact-extraction-expansion

## 1. Spec validation

- [x] `openspec validate prof-fact-extraction-expansion` exits 0.
- [ ] Child spec review is complete before implementation starts.

## 2. Preflight evidence

- [ ] Eligible professor count with non-empty `profile_raw_text` is
  recorded.
- [ ] Missing-summary count is recorded.
- [ ] Missing target fact counts are recorded for `education`,
  `work_experience`, `award`, and `academic_position`.
- [ ] Skipped rows without `profile_raw_text` are recorded.

## 3. Extraction and persistence

- [ ] Each target fact type has unit test coverage.
- [ ] Malformed LLM output is rejected or safely skipped.
- [ ] Low-confidence facts retain confidence values for downstream
  review.
- [ ] Facts are written with provenance and run id.
- [ ] Re-running the same batch does not duplicate active facts.
- [ ] Duplicate detection uses
  `professor_id + fact_type + normalized_fact_key`.
- [ ] Re-seeing the same normalized fact from a different source page or
  evidence span updates or supplements the existing active fact instead
  of creating another active row.

## 4. Backfill and re-evaluation

- [ ] Runner reports processed, skipped, failed, facts_written, and
  summaries_written counts.
- [ ] Per-professor LLM failure does not abort the batch.
- [ ] Post-backfill re-evaluation runs through the Child 1 entry point.
- [ ] Quality-status distribution is recorded before and after the
  backfill sample.
