# Acceptance: paper-homepage-enrichment-completion

## Spec validation

- [x] `openspec validate paper-homepage-enrichment-completion` exits 0.

## Tier evidence

- [x] Page-declared paper evidence records `prof_homepage_tier2` or
  `prof_homepage_tier3`.
- [x] Missing tier classification is not silently downgraded to a
  generic source label.

## Enrichment

- [x] arXiv participates as the fourth enrichment fallback where
  identifier input is available.
- [x] Author metadata is merged without weakening stronger source
  evidence.
- [x] DOI/arXiv contradictions create open pipeline issues.
- [x] `citation_count` remains OpenAlex-only.

## Summary and Milvus

- [x] `summary_zh` changes are discoverable by the paper Milvus refresh
  path.
- [x] A targeted refresh can re-embed affected paper chunks without
  requiring a full rebuild.
- [x] The clean rebuild order is documented and tested on a bounded
  sample.

Evidence:

- Refresh signal contract: `paper.summary_zh` writes update
  `paper.updated_at`; the paper Milvus backfill path can consume this
  with `--changed-since <timestamp>`.
- Targeted paper refresh command: `run_milvus_backfill.py --domain paper
  --paper-id <paper_id>` for exact rows, or
  `run_milvus_backfill.py --domain paper --changed-since <timestamp>`
  for rows changed after a recorded summary/enrichment timestamp.
- Bounded E2E:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t5_codex uv run --no-sync pytest tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py tests/postgres/test_paper_summary_milvus_refresh_e2e.py -q -n0`
  exited 0 with `3 passed`.

Clean rebuild order:

1. Run page-first paper ingest.
2. Run paper metadata enrichment and `summary_zh` generation.
3. Let paper quality promotion evaluate the enriched row.
4. Run paper Milvus refresh with either `--paper-id` for exact affected
   rows or `--changed-since` using the timestamp captured before the
   summary/enrichment write.
5. Run retrieval validation against refreshed paper chunks.
