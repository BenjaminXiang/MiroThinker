# Change Log: prof-quality-status-rework

## 2026-05-14 — Child scaffolded

- Created the child OpenSpec artifact set from the
  `prof-admin-workbench` parent.
- Pinned Child 1 as backend-only and migration-free.
- Added explicit child-spec review gate before implementation.

## 2026-05-14 — Child spec review closure

- Defined `field_contradiction` as a narrow set of machine-detectable
  anomalies and explicitly excluded missing fields from contradiction
  handling.
- Promoted the required key-field list for `ready` into the spec before
  implementation.
- Pinned the `rule_id -> pipeline_issue.stage` mapping to existing
  V006/V023 stage values.
- Strengthened the real-data acceptance gate from "not 100 percent
  needs_review" to a cohort-based check: official-source,
  identity-resolved, non-anomalous professors must not remain
  `needs_review`.
- Closed the final status/persistence ambiguities: missing official
  source is explicitly `low_confidence`, and `external_blocking_issue`
  is display-only because the durable issue row already exists from an
  external reporter.

## 2026-05-15 — Backend implementation pass

- Added a persisted-state professor quality evaluator with the
  four-state cascade, human override watermark handling, quality-gate
  self-feedback exclusion, and field-contradiction detection.
- Added SQL loading and persistence helpers for
  `ProfessorCanonicalState`, professor `quality_status`, and
  quality-gate-authored `pipeline_issue` rows.
- Wired `write_professor_bundle` through the loader/evaluator/persist
  helper so canonical writes update `professor.quality_status`.
- Added `scripts/run_professor_quality_re_eval.py` with dry-run,
  selected-professor, distribution, and issue-count reporting.

## 2026-05-15 — Real-data verification closure

- Ran `miroflow_real` dry-run and write-pass re-evaluation with the
  local libpq DSN and recorded distribution / issue-count evidence.
- Verified that the write pass leaves the professor distribution at
  `needs_enrichment=493`, `ready=2`, and does not assign
  `needs_review` to the current real-data cohort.
- Verified quality-gate issue idempotency by re-running the write pass:
  `professor_quality_gate` counts stayed at `open=1195`,
  `resolved=1195`, with no duplicate `(professor_id, description)`
  groups.
- Fixed the persistence report to use database `rowcount` semantics
  instead of generated reason counts, so idempotent reruns report
  `issues_upserted=0` and `stale_issues_reconciled=0`.
