## Context

Tsinghua SIGS faculty pages use a shared `.sudy-tab` template. The profile page contains all tab bodies in the initial HTML and JavaScript only switches visible tabs via `mouseenter`. Current Professor extraction keeps most of this content in `profile_raw_text`, while structured `research_topic`, CV facts, awards, and profile summaries remain missing for most SIGS records.

## Goals / Non-Goals

**Goals:**

- Deterministically parse SIGS tab sections from official profile HTML.
- Extract official research text into canonical `research_topic` inputs without treating long paragraphs as invalid.
- Make SIGS CV, academic-position, award, project, and publication sections available to downstream persistence and summary generation.
- Add regression tests using the Ahmed Elazab template and at least one sibling SIGS template.
- Validate the repair by randomly sampling SIGS teachers after implementation.

**Non-Goals:**

- Do not change the Professor quality-status enum or lower quality thresholds.
- Do not add schema migrations.
- Do not delete or archive existing SIGS professor rows in this change.
- Do not require browser hover automation for normal crawling because the source HTML already contains the tab bodies.

## Decisions

- Add a SIGS-specific tab parser inside the Professor profile extraction boundary. This keeps the school template handling close to existing SIGS title/email parsing and avoids a new dependency.
- Store long SIGS research paragraphs as research direction candidates only when they are under the official `研究领域` tab/section. The generic short-field guard remains unchanged for non-SIGS pages.
- Use deterministic section labels for facts where possible. LLM fact backfill may still enrich later, but the official tab parser must provide a structured baseline without relying on model availability.
- Keep publication extraction bounded to the existing homepage-publication path. This change will make the tab section easier to consume but will not rewrite paper canonicalization.

## Risks / Trade-offs

- SIGS pages may contain empty sections. Empty tab sections must not create empty facts.
- Long research paragraphs can be too verbose for atomic topics. The parser should preserve source-grounded text while existing topic splitting/quality filters decide how to index it.
- Existing records may need a targeted re-crawl or backfill after code lands. This change verifies a random sample but does not perform destructive full-data cleanup.
