# Change Log: prof-fact-extraction-expansion

## 2026-05-14 — Child scaffolded

- Created the child OpenSpec artifact set from the
  `prof-admin-workbench` parent.
- Sequenced this child after `prof-quality-status-rework` and before
  `prof-admin-workbench-ui` so the workbench can consume improved
  canonical facts.
- Added explicit preflight and child-spec review gates.

## 2026-05-14 — Fact idempotency clarified

- Pinned duplicate detection to the active-fact key
  `professor_id + fact_type + normalized_fact_key`.
- Confirmed `source_page_id` and `evidence_span` are provenance, not
  duplicate-key dimensions.
