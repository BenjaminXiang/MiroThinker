## Why

Operators need to visually inspect professor profile summaries at list scale before deciding whether the newly generated summary data is correct. The current `/professor` list receives `summary_fields.profile_summary` from the API but does not render it, so summary quality cannot be reviewed without opening each professor detail page one by one.

## What Changes

- Add a profile-summary preview to the professor list UI.
- Keep existing professor detail workbench behavior unchanged; the full cleaned summary remains visible in the detail page.
- Do not change APIs, database schema, summary generation, quality gates, or data values.

## Capabilities

### New Capabilities

- `professor-list-summary-visibility`: Show professor profile-summary previews in the admin professor list for batch quality review.

### Modified Capabilities

- `professor-admin-workbench-ui`: The professor admin surface must expose cleaned profile summaries at list scale, not only in the detail workbench.

## Impact

- Affected frontend code: `apps/admin-console/frontend/src/pages/DomainList.tsx`.
- Affected tests: admin-console frontend page tests for the professor list.
- No backend API, storage, migration, or data recollection impact.
