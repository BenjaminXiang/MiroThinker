# Design: paper-pdf-fulltext-ingest

## Scope

This change extends existing `paper_full_text` support from arXiv-like
fetches to PDFs linked from professor pages.

## Fetch policy

The fetcher must enforce:

- maximum PDF byte size;
- request timeout;
- allowed content types;
- redirect cap;
- per-seed or per-run PDF count cap.

Violations write `pipeline_issue` rows and do not crash the seed run.

## Persistence

Raw PDF content is persisted by sha256 or by an approved blob reference
that includes sha256. Extracted text writes to `paper_full_text` with
source URL, fetch timestamp, byte size, sha256, and run id.

## Rollback

Rows are attributable by run id and sha256. A bad run can remove or
ignore affected `paper_full_text` rows and blob objects.
