# Design: prof-fact-extraction-expansion

## Scope

This child change improves professor collected data quality after the
quality evaluator is corrected. It is sequenced before the dedicated UI
so the workbench can display real experience facts instead of mostly
placeholder sections.

## Eligible set

The preflight counts professors that have non-empty `profile_raw_text`.
It separately reports:

- rows missing `profile_summary`;
- rows missing each target fact type;
- rows skipped because no `profile_raw_text` exists;
- rows already carrying active facts for the target type.

The runner must not assume the earlier inflated `~492` count. Counts are
an acceptance artifact.

## Extractor

The extractor uses an injected LLM client. Tests use a mocked client and
make no real HTTP calls. The model output is parsed into structured
items:

- `fact_type`: one of `education`, `work_experience`, `award`,
  `academic_position`;
- `value_raw`;
- `value_normalized`;
- `evidence_span`;
- `confidence` in `[0, 1]`.

Low-confidence items may be written, but the confidence value must
remain visible to downstream quality evaluation and admin review.

## Persistence

Each fact is written to `professor_fact` with:

- `professor_id`;
- `fact_type`;
- `value_raw`;
- `value_normalized`;
- `source_page_id` for the official profile page when available;
- `evidence_span`;
- `confidence`;
- `status = active`;
- `run_id`.

The write path must be idempotent for repeated runs over the same
profile text. Duplicate detection is application-level because the
current schema has only an index on `(professor_id, fact_type)`, not a
natural unique key. The active-fact key is `professor_id + fact_type +
normalized_fact_key`, where `normalized_fact_key` is `value_normalized`
when present and otherwise a deterministic normalized form of
`value_raw`. `source_page_id` and `evidence_span` stay as provenance and
do not create separate active facts for the same normalized value.

Current code already writes some `professor_fact` rows from the
canonical writer when the in-memory profile carries those fields. This
child must not duplicate that path blindly. It must either reuse the
existing helper after adding the normalized-key behavior, or add a
dedicated backfill helper with the same idempotency contract. The
missing completion work is the structured extractor, bounded backfill
runner, durable normalized-key idempotency, and the `academic_position`
write path.

## Runner

The runner performs:

1. preflight count;
2. per-professor extraction and summary generation;
3. per-professor transaction boundaries or equivalent isolation;
4. failure logging without aborting the whole batch;
5. post-backfill call to Child 1 re-evaluation.

The runner reports processed, skipped, failed, facts_written,
summaries_written, and re-evaluated counts.

## LLM and proxy behavior

The runner should reuse the proxy-safe LLM-client pattern from the paper
`summary_zh` backfill. Ambient proxy inheritance should not be
introduced silently.

## Rollback

Facts inserted by this child carry `run_id`. Rollback marks those facts
`superseded` where supported by the existing fact-status constraint, or
uses the established project rollback pattern for facts if a stricter
status set is found during implementation.
