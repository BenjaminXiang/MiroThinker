# Design: patent-page-only-canonical

## Scope

This change resolves title-only patents listed on professor pages. The
implementation must choose one storage strategy:

1. Relax patent canonical schema to allow `patent_number` NULL for
   `canonical_source="prof_page_only"`.
2. Add a separate `patent_candidate` table for title-only page evidence.

The chosen strategy must support idempotency, provenance, promotion
when a patent number later appears, and rollback.

## Storage Decision

Use the nullable canonical-row strategy.

Rationale:
- Professor-page title-only patents need the same downstream surfaces as
  numbered patents: `professor_patent_link`, quality status, admin review,
  release/backfill visibility, and future Milvus refresh. A separate
  candidate table would duplicate those contracts and require promotion
  plumbing before users can see or review the evidence.
- PostgreSQL unique constraints already allow multiple NULL values, so
  relaxing `patent.patent_number` preserves strict uniqueness for numbered
  patents while permitting page-only canonical rows.
- Title-only rows remain non-ready by policy: they start
  `quality_status="needs_enrichment"` and `identity_status="unverified"`.
- Deduplication for title-only rows is handled by stable `patent_id`
  generation from professor/page/title evidence rather than by
  `patent_number`.
- The page evidence URL belongs on `professor_patent_link`, not the
  canonical `patent` row, because the evidence proves a professor-page
  relationship to a patent candidate. V032 adds nullable
  `evidence_url` and `evidence_anchor` columns so old link rows remain
  valid while new homepage-ingest rows retain provenance.

Rollback:
- V026 relaxes `patent.patent_number` to nullable.
- V026 downgrade fills NULL `patent_number` values with their primary-key
  `patent_id` before restoring `NOT NULL`, preserving reversibility without
  deleting page-only evidence.
- V032 drops only the additive `professor_patent_link` evidence URL
  columns.

## Quality

Title-only page patents start as `needs_enrichment` unless the page
evidence is malformed. They are not `ready` until a patent number or
equivalent authoritative identifier is confirmed.

## Deduplication

Numbered patents still hard-match on patent number. Title-only
candidates dedupe within professor/page scope using normalized title
and evidence URL. Cross-professor title-only merges are not automatic
without a confirmed identifier.

## Promotion / Merge

When a later professor-page ingest sees a patent number for a title that
was previously captured as title-only, the writer promotes the existing
title-only canonical row instead of inserting a duplicate when all of
these conditions hold:

- same `professor_id`;
- same `professor_patent_link.evidence_url`;
- same `professor_patent_link.evidence_anchor` using NULL-safe equality;
- same `patent.title_clean`;
- existing row has `patent_number IS NULL`;
- no other canonical row already owns the incoming `patent_number`.

Promotion updates the existing row with the confirmed `patent_number`,
keeps the existing `patent_id`, preserves the professor link, and keeps
the row `quality_status="needs_enrichment"` until xlsx/admin enrichment
or future quality rules promote it.

If another canonical row already owns the incoming `patent_number`, the
writer keeps strict numbered matching and links to that numbered row; it
does not destructively merge the old title-only row in this change.

Malformed page candidates, such as blank titles, remain diagnostics:
they file `pipeline_issue.stage="data_quality_flag"` and must not create
canonical `patent` rows.

## Rollback

If using nullable canonical rows, rollback deletes or reclassifies rows
with `canonical_source="prof_page_only"` and NULL patent number. If
using a candidate table, rollback drops the candidate table.
