## Context

P8 archived a read-only post-full audit and reported P9 as blocked by
`field_defect:cuhk-sds-bresar-title`. The real `miroflow_real` row for
`BRESAR, Miha` stores an entire reader Markdown page in
`professor_affiliation.title`; the expected title is `助理教授`.

The likely source is the generic profile extractor. It treats `Title` as an
academic-position label, but reader-captured Markdown can begin with metadata
such as `Title: ... URL Source: ... Markdown Content: ...`. Without a
bounded-title guard, the metadata title line can be promoted into the structured
Professor title field and then written by the canonical path.

## Goals / Non-Goals

**Goals:**

- Enforce that Professor title/position extraction returns only bounded
  academic role phrases.
- Prevent reader metadata, navigation text, and unrelated profile sections from
  being stored as `professor_affiliation.title`.
- Repair and verify the known CUHK(SZ) SDS BRESAR, Miha case.
- Preserve source traceability through the existing `run_id` and `source_page`
  surfaces.
- Keep the P9 publish/index blocker visible until the real row is re-verified.

**Non-Goals:**

- No schema migration.
- No publish refresh, RAG index refresh, or Milvus refresh.
- No duplicate merge or broad identity cleanup.
- No bulk historical cleanup beyond the targeted rerun or targeted row
  verification needed to prove the BRESAR blocker is removed.
- No change to Professor seed CRUD or manual trigger semantics.

## Decisions

### Decision 1: Fix extraction at the title boundary

The repair will reject or normalize title candidates before they reach
canonical writes. The guard will require the accepted title to match known
academic-role patterns or a short role phrase and reject candidates containing
reader metadata (`URL Source`, `Published Time`, `Markdown Content`), page
chrome, section labels, or long body text.

Alternative considered: update only the BRESAR row in Postgres. That would not
prevent the same page-reader metadata from contaminating future recollection
runs.

### Decision 2: Treat `Title:` reader metadata differently from academic title labels

The extractor can still support genuine English academic labels, but `Title:`
at the start of a page-reader blob must not be accepted unless the extracted
value itself passes the bounded title guard.

Alternative considered: remove English `Title` support entirely. That is safer
for reader metadata but can regress English faculty pages that genuinely label
the academic role as `Title`.

### Decision 3: Recheck P8 blocker through the audit report

After the parser/data fix, the P8 audit command should classify
`cuhk-sds-bresar-title` as resolved only when the real current value is exactly
`助理教授` and contamination markers are absent. P9 remains blocked while the
audit reports it unresolved.

Alternative considered: manually edit the P9 handoff. That would weaken the
evidence chain and could allow publish/index work to proceed without real data
verification.

## Risks / Trade-offs

- Over-strict title validation can drop legitimate long titles -> mitigation:
  keep accepted role patterns broad enough for existing Professor profile tests
  such as `教授，博士生导师`.
- The real row may need a targeted recollection rerun after code repair ->
  mitigation: run the smallest seed/profile rerun that rewrites the BRESAR row
  and record exact evidence.
- Additional contaminated fields may exist outside title -> mitigation: this
  change records sibling findings but only fixes the title/position blocker
  unless the same helper can safely prevent them.
- Historical quality-gate issues remain after this change -> mitigation: keep
  them in the P9 handoff as separate publish/index decisions.
