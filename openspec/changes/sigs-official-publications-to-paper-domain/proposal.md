> **Cross-change correction (2026-07-10):** this change remains in verification, but its historical
> ready-first topic fallback is superseded by `close-retrieval-generation-contract` D1. The SIGS
> ingest/bridge capability still archives normally; archive is blocked until Task 5.20 aligns C0
> exact-title identity partials and D1 topic competition so neither conflicting rule can migrate.

## Why

SIGS professor pages already contain official publication lists, but those entries can remain trapped in professor raw profile text or be parsed with author strings as titles. This prevents officially listed papers from entering the paper canonical domain, professor-paper links, abstract enrichment, summaries, and paper retrieval indexes.

## What Changes

- Parse SIGS author-prefixed official publication entries into complete publication records where `clean_title` is the paper title, `authors_text` preserves listed authors, and `venue_text` / `year` are retained when present.
- Add an LLM-assisted publication extraction fallback for SIGS and similarly variable professor-page citation formats across institutions. Rules locate publication sections and provide a fast path; the LLM extracts structured items only from those source sections.
- Validate LLM output against source spans before paper-domain ingest. Titles, authors, venues, years, and identifiers must be grounded in the official page text; invalid or hallucinated items must not enter title resolution.
- Treat source headings such as "Representative Publications" or `代表性论文` only as provenance labels, not as a system judgment that the papers are representative works.
- Remove business-level per-professor caps from official page publication extraction and ingest; all officially listed page publications must be eligible for the paper bridge.
- Reuse the post-collection `paper.homepage_ingest.run_homepage_paper_ingest` path for SIGS official profile pages, rather than running OpenAlex/arXiv resolution synchronously inside professor seed recollection.
- Upsert each officially listed paper into canonical `paper` and create a verified `professor_paper_link` with `is_officially_listed=true` and the strongest applicable professor-page evidence tier.
- Attempt metadata, abstract, summary, full-text, and paper Milvus refresh through existing paper-domain enrichment paths. Page-only papers without abstracts must not fabricate `abstract_clean`; they remain enrichment/review candidates with diagnostic evidence.
- Produce rollout evidence for Ahmed Elazab first, then a random SIGS sample, then cross-institution parser/fallback audit evidence, then full SIGS with resume checkpoints.

## Capabilities

### New Capabilities

- `sigs-official-publications-to-paper-domain`: Bridge all official SIGS professor-page publication entries into paper canonical records, verified professor-paper links, enrichment, and rollout evidence. The publication-section extraction fallback is shared with non-SIGS official professor pages when the rule parser emits suspicious titles or low-recall citation sections.

### Modified Capabilities

- `paper-homepage-enrichment-completion`: Official professor-page paper ingest must accept all extracted official publication entries, avoid author-list titles, and preserve page tier evidence while writing canonical paper/link rows.
- `paper-fulltext-from-prof-page`: Professor-page paper ingest must continue to discover direct PDF links for official SIGS publication entries after the parser fix.

## Impact

- Affected parser: `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`.
- Affected ingest bridge: `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` and `apps/miroflow-agent/scripts/run_homepage_paper_ingest.py` where necessary.
- Affected follow-up scripts: `run_paper_summary_zh_backfill.py` and `run_milvus_backfill.py` for Ahmed/SIGS validation commands.
- Affected tests: homepage publication parser tests, homepage paper ingest tests, and targeted script tests for summary/index follow-up where behavior changes.
- No new database migration is expected; existing `paper`, `professor_paper_link`, `paper_full_text`, `pipeline_issue`, and Milvus backfill surfaces should be reused.
