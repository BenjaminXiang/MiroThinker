## Why

Tsinghua SIGS faculty profile pages expose rich structured content in a shared tab template, but the Professor pipeline currently stores most of that content only as raw text. This leaves many SIGS professors, including Ahmed Elazab, marked `needs_enrichment` even though the official page contains research directions, CV entries, publications, and awards.

## What Changes

- Add SIGS tab-template extraction for official profile pages that use `.sudy-tab`.
- Preserve rich tab content as source-grounded structured facts and research topics rather than only `profile_raw_text`.
- Keep the existing quality gate semantics; repaired records should improve because required canonical facts and summaries become available, not because thresholds are weakened.
- Verify the repair by re-crawling a random sample of SIGS teachers after implementation and reporting the extracted fields.

## Capabilities

### New Capabilities

- `professor-sigs-tab-template-extraction`: Extract structured Professor fields from the Tsinghua SIGS tab profile template.

### Modified Capabilities

- `professor-fact-extraction`: SIGS tab sections must be eligible for deterministic structured facts where the official page already labels CV, academic positions, projects, publications, and awards.
- `professor-profile-field-extraction-integrity`: SIGS tab section labels and body content must not contaminate title extraction while still allowing section-specific field extraction.

## Impact

- Affected code: `apps/miroflow-agent/src/data_agents/professor/profile.py`, canonical writer/fact persistence if needed, and Professor tests.
- Affected runtime: SIGS seed re-crawls and targeted post-fix sample validation.
- No schema, public API, migration, or quality-status enum changes are expected.
