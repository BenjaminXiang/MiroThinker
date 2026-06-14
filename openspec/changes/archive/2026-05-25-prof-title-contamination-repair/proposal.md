## Why

P8 proved that the post-full Professor dataset is not ready for P9
publish/index work because the CUHK(SZ) SDS BRESAR, Miha profile has a
contaminated title field. The same defect class can leak reader metadata,
navigation text, and profile sections into structured Professor fields, so the
repair must enforce an extraction boundary instead of patching one row.

## What Changes

- Add a Professor profile-field extraction integrity guard for title/position
  fields.
- Repair the CUHK(SZ) SDS title extraction path so BRESAR, Miha's title is
  exactly `助理教授`.
- Add regression coverage for title contamination markers such as `URL Source`,
  `Published Time`, `Markdown Content`, navigation text, education sections,
  profile text, and publication sections.
- Run a targeted real-data verification against `miroflow_real` after repair.
- Update P8/P9 handoff evidence so the P9 blocker can be reassessed.
- Do not perform publish refresh, RAG index refresh, duplicate merge, schema
  migration, deletion, or broad historical cleanup in this change.

## Capabilities

### New Capabilities

- `professor-profile-field-extraction-integrity`: Defines the invariant that
  structured Professor title/position fields must be bounded role phrases and
  must reject page chrome, reader metadata, navigation text, and unrelated
  profile sections.

### Modified Capabilities

- `professor-post-full-quality-audit`: Adds the requirement that known
  field-extraction blockers can be rechecked after remediation before P9
  publish/index work proceeds.

## Impact

- Affected runtime:
  - `apps/miroflow-agent/src/data_agents/professor/roster.py`
  - `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py`
  - possible shared Professor field-normalization helper under
    `apps/miroflow-agent/src/data_agents/professor/`
- Affected tests:
  - `apps/miroflow-agent/tests/data_agents/professor/`
  - `apps/miroflow-agent/tests/scripts/test_run_professor_post_full_quality_audit.py`
- Affected scripts/evidence:
  - `apps/miroflow-agent/scripts/run_professor_post_full_quality_audit.py`
  - `openspec/changes/prof-title-contamination-repair/acceptance.md`
  - `.agents/runs/prof-title-contamination-repair/verification.md`
