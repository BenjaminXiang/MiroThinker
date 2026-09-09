# Acceptance — ingest-dedup-anchor-before-insert

## A1. Content-anchor dedup (spec §1)
- **A1.1** Co-authored paper on a 2nd prof's page → reuses existing `paper_id` via `professor_paper_link` (not INSERT). — Met: `test_page_only_publication_reuses_existing_canonical_title_year` (updated; asserts `not any("authors_display" in sql)` — the author gate is gone).
- **A1.2** DOI match → reuses via link. — Met: `test_find_existing_canonical_homepage_paper_uses_identifier_keys` (parametrized DOI).
- **A1.3** arxiv match → reuses via link. — Met: same (parametrized arxiv).
- **A1.4** No match → INSERT proceeds (unchanged). — Met: existing tests (194 passed).

## A2. Normalization consistency (spec §2)
- **A2.1** Anchor title normalization matches `canonical_writer._build_paper_id`'s title branch. — Met: code review (the fix reuses `_page_only_reuse_title_key` = `regexp_replace(lower(title), '\s+', '', 'g')`, equivalent to `_build_paper_id`'s `_WHITESPACE_RE.sub("", title_clean).lower()`).

## A3. No regression
- **A3.1** Existing same-prof dedup tests pass. — Met: 194 homepage_ingest tests passed.
- **A3.2** `canonical_writer.upsert_paper` unchanged. — Met: code review (only `_find_existing_canonical_homepage_paper` modified).

## Deferred
- **4.1** Real-DB ingest verification (2 profs, same co-authored paper → 1 paper + 2 links): deferred — the 194 unit tests (incl. the cross-prof dedup regression) are the primary evidence; a real ingest run is an operational follow-up.
