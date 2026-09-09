## Why

After the live title resolver and DeepSeek summary backfill, the Paper domain
still has 19,800 active rows missing `summary_zh` and 19,884 rows missing
`abstract_clean`. The remaining rows are dominated by source gaps rather than
safe direct LLM summarization inputs, so the next change must split source
acquisition, parser repair, and summary generation into explicit lanes.

## What Changes

- Add a source-gap classification contract for active Paper rows missing
  `summary_zh` or `abstract_clean`.
- Split Paper cleanup into independent lanes:
  - existing abstract or full-text input -> LLM summary fast path;
  - DOI/OpenAlex/Crossref/arXiv identifier metadata -> bounded resolver
    enrichment;
  - professor-page PDF/full-text links -> capped slow full-text acquisition;
  - `prof_page_only` rows with unresolved titles -> homepage/parser cleanup and
    conservative title re-resolution;
  - review-only or unsafe rows -> diagnostic residual evidence instead of
    fabricated summaries.
- Require run reports that make skipped rows and source-acquisition failures
  visible by lane, including 403/timeout/content-type PDF failures, bad DOI
  values, unresolved `prof_page_only` titles, and rejected LLM summaries.
- Preserve the Professor official-page seed boundary: the system may enrich
  already discovered Paper rows by title or identifier, but MUST NOT discover a
  Professor's paper list through author-name provider searches.
- Keep summary writes source-grounded. LLMs may translate or summarize usable
  abstracts/full-text inputs, but must not invent abstracts or paper summaries
  for rows that have no usable source text.

## Capabilities

### New Capabilities

- None. This change extends existing Paper enrichment, full-text, and cleanup
  contracts.

### Modified Capabilities

- `paper-homepage-enrichment-completion`: add source-gap lane classification,
  existing-abstract summary fast path, and conservative title re-resolution
  requirements for remaining `prof_page_only` rows.
- `paper-fulltext-from-prof-page`: add slow-lane PDF/full-text acquisition
  reporting and bounded failure accounting for rows still missing abstracts.
- `paper-pipeline-cleanup`: add residual unsafe-row handling so source-gapped
  rows are not promoted by direct LLM fabrication or author-name discovery.

## Impact

- Affected code:
  - `apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py`
  - `apps/miroflow-agent/scripts/run_paper_title_enrichment_backfill.py`
  - Paper source-gap audit or closure scripts to be added or extended
  - Paper resolver, full-text fetcher, DOI quality, and title-quality helpers
  - targeted Paper script and data-agent tests
- Affected data:
  - new source-gap audit artifacts for active Paper rows;
  - lane-specific backfill reports for summary fast path, resolver enrichment,
    full-text slow lane, parser/title cleanup, and residual review buckets;
  - existing `paper.summary_zh`, `paper.abstract_clean`, `paper_full_text`, and
    quality status fields may be updated only by evidence-gated write lanes.
- This change is behavior-affecting. The modified Paper capabilities own the
  behavior contract for clearing remaining Paper source gaps without unsafe
  LLM fabrication.
