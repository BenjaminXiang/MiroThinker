# Design: prof-summary-fields

## Scope

This change adds professor-level aggregate summaries:

- `paper_summary`: research-output summary from verified papers.
- `patent_summary`: technology-output summary from verified patents.

The fields are additive columns on `professor` or an equivalent
professor summary table if implementation finds a stronger local
pattern. The chosen storage must be queryable by the professor vector
publisher.

## Input eligibility

Paper inputs must come from accepted links, such as verified
`professor_paper_link` rows or page declarations accepted by the paper
identity gate. Rejected or uncertain links are excluded.

Patent inputs must come from accepted `professor_patent_link` rows.
Title-only patent candidates excluded by the current schema remain
ineligible until `patent-page-only-canonical` resolves them.

## Generation

The generator can use an injected LLM client or deterministic fallback
template. Tests must mock LLM calls. The output should be concise,
source-grounded, and not invent claims beyond linked rows.

## Refresh

When either summary changes, the implementation must expose a refresh
signal for `prof-double-milvus-collection` so the research vector can be
rebuilt for that professor.

## Rollback

Columns are additive and nullable. A bad run can clear summaries for a
run id and regenerate after fixing the generator.
