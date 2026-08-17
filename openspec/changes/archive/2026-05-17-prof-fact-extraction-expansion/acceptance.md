# Acceptance: prof-fact-extraction-expansion

## 1. Spec validation

- [x] `openspec validate prof-fact-extraction-expansion` exits 0.
- [x] Child spec review is complete before implementation starts.

Evidence:

- The child was reviewed after `prof-quality-status-rework` completed.
- The LLM pattern is the professor profile resolver plus an OpenAI
  client using `httpx.Client(trust_env=False)` so ambient proxy settings
  do not break local profile access.

## 2. Preflight evidence

- [x] Eligible professor count with non-empty `profile_raw_text` is
  recorded.
- [x] Missing-summary count is recorded.
- [x] Missing target fact counts are recorded for `education`,
  `work_experience`, `award`, and `academic_position`.
- [x] Skipped rows without `profile_raw_text` are recorded.

Evidence:

- `miroflow_real` preflight on 2026-05-15:
  `total_professors=495`, `eligible_count=253`,
  `skipped_missing_profile_raw_text=242`,
  `missing_profile_summary_count=250`.
- Missing target fact counts:
  `education=253`, `work_experience=253`, `award=253`,
  `academic_position=253`.

## 3. Extraction and persistence

- [x] Each target fact type has unit test coverage.
- [x] Malformed LLM output is rejected or safely skipped.
- [x] Low-confidence facts retain confidence values for downstream
  review.
- [x] Facts are written with provenance and run id.
- [x] Re-running the same batch does not duplicate active facts.
- [x] Duplicate detection uses
  `professor_id + fact_type + normalized_fact_key`.
- [x] Re-seeing the same normalized fact from a different source page or
  evidence span updates or supplements the existing active fact instead
  of creating another active row.

Evidence:

- `tests/data_agents/professor/test_fact_extraction.py` covers all
  target types, malformed output, low confidence preservation,
  provenance/run id persistence, and normalized-key idempotency across a
  different source page and evidence span.

## 4. Backfill and re-evaluation

- [x] Runner reports processed, skipped, failed, facts_written, and
  summaries_written counts.
- [x] Per-professor LLM failure does not abort the batch.
- [x] Post-backfill re-evaluation runs through the Child 1 entry point.
- [x] Quality-status distribution follow-up is recorded as blocked for
  the real wet sample until an authorized LLM profile is available.

Evidence:

- `tests/scripts/test_run_professor_fact_backfill.py` covers
  per-professor failure isolation, report counts, summary writing, and
  Child 1 re-evaluation invocation with a mocked LLM.
- Bounded `miroflow_real` dry-run with `--limit 1 --dry-run` used the
  sentinel run id and performed no `pipeline_run` write; extraction
  reached the configured LLM profile but returned `401 Unauthorized`.
