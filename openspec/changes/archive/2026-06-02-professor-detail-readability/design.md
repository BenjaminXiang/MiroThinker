## Context

The admin professor detail endpoint already returns canonical identity, facts, experience, summaries, sources, and quality diagnosis. The frontend currently displays all facts as a flat table under "研究与产出". This is technically complete but poor for review: non-research facts appear in the research section, source URLs dominate the page, and the official research paragraph stored in `profile_raw_text` is not returned by the admin API.

## Goals / Non-Goals

**Goals:**

- Surface an official research overview paragraph when `profile_raw_text` contains a labeled research section.
- Keep atomic `research_topic` facts visible as scan-friendly tags.
- Move education, work experience, awards, and academic positions into separate readable sections.
- Preserve the existing source/evidence section for provenance.
- Verify Ahmed-like SIGS data paths with backend and frontend tests.

**Non-Goals:**

- Do not alter professor crawling, summary generation, quality gates, canonical fact rows, or migrations.
- Do not rewrite the whole workbench layout.
- Do not infer or synthesize a research overview when the raw profile text lacks a clear research section.

## Decisions

- Extract `research_overview` in the admin API from `profile_raw_text` using conservative section-boundary parsing.
  - Rationale: this avoids schema changes while exposing already-captured official text for review.
  - Alternative considered: persist a new fact type. That is a better durable data-model improvement, but it requires a broader migration/backfill plan.
- Group facts in the frontend by `fact_type`.
  - Rationale: the payload already has typed facts; grouping at presentation time fixes the readability defect without changing canonical data.
- Keep full source URLs in the source/evidence section and reduce repeated per-row source emphasis in content sections.
  - Rationale: reviewers need provenance, but repeated identical URLs in every fact row make the content hard to read.

## Risks / Trade-offs

- Section parsing may miss unusual raw-text formats. Mitigation: only expose the field when a clear research label and body are present; otherwise omit it.
- Some facts may still have rough parser text. Mitigation: the UI groups them so quality issues are easier to see and report.
- This is a readability repair, not a semantic correctness guarantee for generated summaries.
