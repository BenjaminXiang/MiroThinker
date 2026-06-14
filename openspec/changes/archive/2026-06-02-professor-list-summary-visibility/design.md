## Context

The admin console has two professor surfaces. `/professor` renders the generic domain list, while `/professor/{id}` is routed to the professor-specific workbench. The list API already returns `summary_fields.profile_summary`, and the workbench already renders the full cleaned summary, but the list columns omit the summary field. Operators therefore cannot review generated profile summaries at scale.

## Goals / Non-Goals

**Goals:**

- Make `profile_summary` visible on the `/professor` list.
- Keep the list suitable for scanning by truncating long summaries in the table cell.
- Preserve existing routing, filters, quality actions, and professor detail workbench behavior.
- Verify with a frontend test that professor list rows display the summary preview from `summary_fields.profile_summary`.

**Non-Goals:**

- Do not change summary generation, parsing, or quality-status rules.
- Do not change backend response schemas or database storage.
- Do not add a new review workflow or editable summary grid.
- Do not alter non-professor domain list columns.

## Decisions

- Add the summary preview as a professor-only column in `DomainList.tsx`, sourced from `record.summary_fields.profile_summary`.
  - Rationale: the API already returns the needed field, so the fix belongs at the UI rendering boundary.
  - Alternative considered: add a separate summary audit page. This is heavier and unnecessary for the immediate quality review need.
- Render absent summaries as `-`.
  - Rationale: this matches existing table behavior for missing core facts and keeps missing summaries visible during audit.
- Use table-cell truncation instead of changing the data shape.
  - Rationale: operators can scan many rows without losing the full summary in the detail workbench.

## Risks / Trade-offs

- Wide rows may reduce table density. Mitigation: set a bounded column width and ellipsis behavior.
- Some summaries may be generated but semantically poor. Mitigation: this change intentionally exposes the text for human quality review; it does not declare summaries correct.
- Tests may need browser-layout shims because Ant Design uses DOM APIs in jsdom. Mitigation: reuse the existing frontend test setup pattern.
