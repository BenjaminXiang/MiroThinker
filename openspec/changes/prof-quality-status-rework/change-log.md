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
