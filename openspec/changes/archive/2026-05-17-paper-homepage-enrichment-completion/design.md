# Design: paper-homepage-enrichment-completion

## Scope

This change finishes the enrichment and vector-refresh side of the
paper page-flow. It assumes candidate discovery already happened from a
professor page and never calls external services to discover papers by
author name.

## Tier evidence

The homepage ingest path must carry the page tier from the professor
source-page classification into paper evidence:

- Tier 2 official profile page -> `prof_homepage_tier2`
- Tier 3 personal/lab homepage -> `prof_homepage_tier3`

If a source page has not been classified, the ingest path must either
classify it before paper extraction or file a `pipeline_issue` with an
existing stage rather than silently using a generic page-only label.

## Enrichment merge

The enrichment aggregator keeps field-level priority:

1. OpenAlex
2. Crossref
3. Semantic Scholar
4. arXiv

`citation_count` remains OpenAlex-only. Authors are merged as a
structured field with provenance. ORCID-bearing author identities from a
trusted source win over plain display strings, but lower-priority
sources may fill missing author data.

Identifier contradictions are not silently merged. If a lower-priority
source returns a DOI or arXiv id that conflicts with an existing
canonical identifier for the same candidate, the row is not promoted to
`ready` until the issue is resolved.

## Summary and Milvus refresh

`summary_zh` can be written by a backfill or asynchronous enrichment
job. The write path must set a durable refresh signal that
`run_milvus_backfill.py` can consume. The minimal acceptable contract is
one of:

- an explicit `--paper-id` / `--changed-since` mode that re-embeds rows
  whose summary changed; or
- a pending-vector-refresh table/issue that marks the affected paper.

Chosen implementation contract:

- `run_paper_summary_zh_backfill.py` writes a checkpoint row with
  `milvus_refresh.domain="paper"`, `milvus_refresh.paper_id`, and the
  exact targeted command whenever it persists a non-dry-run
  `summary_zh`.
- `run_milvus_backfill.py --domain paper --paper-id <paper_id>` may be
  repeated to refresh only the affected papers.
- `paper.milvus_backfill.backfill_paper_chunks(..., paper_ids={...})`
  selects those rows, deletes their existing `paper_chunks`, and
  inserts freshly embedded chunks whose abstract text prefers
  `summary_zh`.

The implementation must document the chosen command order for a clean
rebuild:

1. page-first ingest;
2. enrichment and summary generation;
3. paper quality promotion;
4. Milvus paper chunk/vector refresh;
5. retrieval validation.

## Rollback

Identifier contradiction issues and refresh markers are attributable by
run id. A bad summary/vector refresh can be corrected by clearing the
affected rows and rerunning the documented rebuild sequence.
