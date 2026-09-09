# Change Log: prof-quality-status-rework

## 2026-05-21 — real DB write pass completed

- After user approval, ran the `miroflow_real` write pass with
  `scripts/run_professor_quality_re_eval.py`.
- Write pass evaluated 495 professors and persisted 495 evaluations.
  Distribution before and after remained `needs_enrichment=493`,
  `ready=2`, with `needs_review=0`.
- Quality-gate issue counts before and after remained unchanged:
  `affiliation=246`, `coverage=492`, `research_directions=457`.
- Re-ran the write pass to verify status/issue-count idempotence; the
  distribution and quality-gate issue counts remained unchanged.
- Post-rerun SQL guard found `duplicate_open_quality_gate_uq_key_count=0`.

## 2026-05-21 — implementation and dry-run checkpoint

- Added canonical-state quality evaluation in `professor/quality_gate.py`,
  including `ProfessorCanonicalState`, persisted-state source/fact/
  affiliation/issue dataclasses, and
  `evaluate_professor_quality(...)`.
- Implemented the four-state cascade from the spec:
  `needs_review` anomalies, `low_confidence` scrape/source failures,
  `ready`, then `needs_enrichment` for trustworthy incompleteness.
- Added SQL loading, idempotent quality-gate issue persistence, and
  stale quality-gate issue reconciliation. The evaluator ignores
  `reported_by = professor_quality_gate` open rows as blocking inputs,
  and `external_blocking_issue` remains display-only.
- Wired evaluation into
  `professor/canonical_writer.py::write_professor_bundle` so
  `professor.quality_status` is persisted in the canonical write
  transaction.
- Added `scripts/run_professor_quality_re_eval.py` with dry-run,
  selected-professor, distribution, and issue-count reporting.
- Verification: focused quality/script suite `43 passed`,
  canonical-writer integration regression `1 passed`, Ruff passed.
- `miroflow_real` dry-run evaluated 495 professors and wrote 0 rows:
  before and evaluated distribution both `needs_enrichment=493`,
  `ready=2`, with `needs_review=0`. T6.4 write pass is held until
  dry-run review because it mutates `miroflow_real`.

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
