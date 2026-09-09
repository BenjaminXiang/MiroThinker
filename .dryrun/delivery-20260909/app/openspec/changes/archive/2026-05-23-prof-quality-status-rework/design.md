# Design: prof-quality-status-rework

## Scope

This child change implements the backend quality-status contract from
`prof-admin-workbench`. It is the first implementation child because it
removes the universal `needs_review` default before any backfill or UI
work depends on the quality signal.

## Data model inputs

The evaluator consumes a `ProfessorCanonicalState` value assembled from:

- the `professor` row;
- active `professor_fact` rows;
- current and historical `professor_affiliation` rows;
- official `source_page` metadata reachable from those rows;
- external open `pipeline_issue` rows where
  `reported_by != professor_quality_gate`;
- the latest `professor_admin_action` when the UI child exists.

The evaluator is pure: it performs no SQL and writes nothing. SQL
loading and persistence are owned by call sites.

## Quality rules

Priority cascade:

1. `needs_review` for true anomalies: unresolved identity status,
   same-name conflict, field contradiction, or external blocking issue.
2. `low_confidence` for low-quality scrape/parse signals: non-person
   name, reader artifacts, profile blob, or no official source.
3. `ready` when official source, resolved identity, required key fields,
   and no anomalies are present.
4. `needs_enrichment` for trustworthy but incomplete rows.

The exact required key fields and machine-detectable contradiction
rules are pinned in `specs/professor-quality-status/spec.md`. In short,
`ready` requires official source, resolved identity, canonical name,
current institution, title or department, research topic, profile
summary, and a verified paper/link signal when paper/link candidates
exist. Missing fields are enrichment gaps, not contradictions.

## Reason persistence

The write call sites persist one open `pipeline_issue` row per non-ready
reason with:

- `reported_by = professor_quality_gate`;
- an existing V006/V023 `stage` value;
- a deterministic `description_hash`;
- `professor_id` set and `link_id` / `institution` unset for
  professor-level quality reasons.

Upsert identity follows the existing `uq_pipeline_issue_open` index:
`professor_id`, `link_id`, `institution`, `stage`, `reported_by`,
`description_hash`, `WHERE resolved = false`.

Rows previously written by this gate and no longer emitted by the
current evaluation are marked `resolved = true`. Rows from any other
`reported_by` are never resolved by this change.

## Canonical watermark

The canonical watermark is the latest timestamp across:

- `professor.updated_at`;
- active `professor_fact.updated_at`;
- `professor_affiliation.updated_at`;
- external open `pipeline_issue.reported_at` where
  `reported_by != professor_quality_gate`.

If `latest_admin_action.action` is `confirm_ready` or `send_to_review`
and its `observed_data_updated_at` is not older than the current
watermark, the evaluator returns the override status with
`rule_id = human_override`. A later canonical data change or newly filed
external issue makes the override stale.

Whether a pure `source_page` re-fetch should advance the watermark is
left out of Child 1 and must not be guessed during implementation.

## Call sites

- `canonical_writer.write_professor_bundle`: evaluate after professor,
  fact, and affiliation writes, then persist `professor.quality_status`
  and quality-gate issue rows in the same transaction.
- `scripts/run_professor_quality_re_eval.py`: load canonical state for
  all or selected professors, evaluate, persist status and reasons, and
  report before/after distributions.

## Rollback

No migration is introduced. A bad evaluation run is corrected by fixing
the evaluator and re-running the re-evaluation script. Quality-gate
issue rows are attributable by `reported_by = professor_quality_gate`.
