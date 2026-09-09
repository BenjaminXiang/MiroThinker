## Context

The Company domain already has canonical company rows, XLSX snapshots, `company_news_item`, `company_signal_event`, `company_product`, `company_product_evidence`, and a company Milvus collection. The previous Yiou/PitchHub change made public source discovery work through Serper web search and reader-fallback detail fetches.

The missing closure is downstream use of that source evidence. `run_company_signal_extract.py` extracts events from `company_news_item`, but it does not distinguish source adapters or report source-level outcomes. `run_company_official_product_capture.py` extracts products from official websites, but source-profile text from Yiou/PitchHub is not consumed by a product extractor. Company detail/release payloads expose only basic snapshot fields and funding-only data, and Milvus company text does not include recent events/products.

## Goals / Non-Goals

**Goals:**

- Extract and persist signal events from accepted Yiou/PitchHub source records.
- Extract and persist product records from source-profile body text with evidence spans.
- Persist structured financing fields, product fields, and first-class application scenarios.
- Expose products, recent events, and source evidence in company release/detail APIs and the frontend detail view.
- Include products and recent signal events in company Milvus text/payloads.
- Provide bounded runbooks/E2E scripts that prove the ingest -> event/product -> display -> retrieval loop.

**Non-Goals:**

- Do not redesign the existing company schema unless a blocking field is missing.
- Do not claim all 1025 companies are enriched until full live backfill completes and reports coverage.
- Do not replace generic news ingestion, official website product capture, or existing XLSX import.
- Do not force online RAG to depend on live web search; source enrichment writes evidence first, then RAG reads local DB/Milvus.

## Decisions

1. Reuse `company_news_item` as the source-evidence staging table.
   - Yiou/PitchHub detail text is already stored in `summary_clean`; the signal and product extractors should consume that field as source body text.
   - Source provenance remains `source_adapter` plus `extraction_diagnostics`.

2. Add a source-product extractor instead of overloading official-site HTML extraction.
   - Official-site extraction is HTML/card oriented.
   - Yiou/PitchHub source records are text/Markdown-like bodies, so a separate text extractor can look for product/service sections and LLM JSON when available.
   - Product writes still go through `upsert_company_product` so dedupe and evidence writes remain centralized.

3. Keep signal extraction as an LLM-backed step, but make it source-aware.
   - The existing event schema is sufficient for funding/product/partnership/order/award/expansion/executive signals.
   - The prompt should permit source profile pages with financing history and product summaries while still rejecting unsupported rumors.
   - The runner should report source-adapter counts and inserted counts.

4. Extend release/detail payloads rather than adding a new admin endpoint first.
   - `/api/company/{id}` and `/api/data/companies/{id}` are the current surfaces users inspect.
   - Products and recent events should appear in `core_facts` or explicit detail arrays, with evidence links preserved.

5. Refresh company Milvus with enriched local DB text.
   - `run_milvus_backfill.py --domain company` remains the refresh entrypoint.
   - `_COMPANY_SQL` should aggregate recent signal-event summaries and product summaries into the text/payload.

6. Keep financing in `company_signal_event`, but make its normalized JSON contract explicit.
   - Do not create a duplicate financing table.
   - Funding events should normalize `round`, `amount_raw`, `amount_cny_wan`, `investors_raw`, `investors`, `fa_info`, `source_adapter`, and `source_url` when available.
   - APIs should project this JSON into typed financing payloads.

7. Extend `company_product` for product structure and add first-class scenarios.
   - Product rows should carry product category, target customers, application scenario labels, and technical tags.
   - Application scenarios need their own table because they are searchable/filterable business facts and can relate to a product but also stand alone at company level.
   - Scenario evidence should mirror product evidence: source URL, evidence span, confidence, extractor version, and creation timestamp.

8. Treat admin company XLSX upload as the scoped enrichment entry point.
   - Upload import remains responsible for parsing and canonicalizing XLSX rows into `company`, `company_snapshot`, team, and imported funding event rows.
   - After import, load company IDs from `company_snapshot.import_batch_id` and pass those IDs into Yiou/PitchHub news ingest, signal extraction, and source product/scenario extraction.
   - Search query broadening uses uploaded XLSX text: canonical name, normalized name, project name, description, and team text. When the configured LLM is available, it extracts aliases, founder names, and distinctive keywords for additional site-search queries; deterministic acceptance still confirms company relevance before writing source rows.
   - Upload-triggered enrichment is batch scoped and supports an optional `COMPANY_UPLOAD_ENRICHMENT_LIMIT` guard for operational throttling.

9. Split upload import from external enrichment execution.
   - The admin upload task imports XLSX data, creates an enrichment batch, inserts per-company checkpoint rows, and returns `queued`.
   - A separate runner owns source discovery, signal extraction, source product/scenario extraction, official-site product capture, and Milvus refresh.
   - The runner is resumable by `batch_id`; it only reprocesses unfinished companies by default.
   - This avoids a long-running HTTP/admin background task becoming the only source of truth for 1025-company enrichment.

10. Persist search/miss audit as first-class operational evidence.
   - Query diagnostics go to `company_enrichment_search_audit`.
   - Per-company counters and miss reasons go to `company_enrichment_company_state`.
   - This lets operators distinguish `no search results`, `all results rejected`, `source fetch failed`, and `parsed but no products/events`.

11. Keep deterministic extraction first, then use LLM fallback narrowly.
   - Rule-based extraction remains cheap and predictable for known layouts.
   - LLM fallback only runs for supported source rows with usable body text where deterministic extraction misses products/scenarios.
   - Fallback output is validated, evidence-bound, and defaults to `needs_review`.

12. Make review and stale cleanup operational paths explicit.
   - Product/scenario review updates the target row and records an audit action.
   - Stale cleanup only closes old running pipeline rows matching explicit filters, preserving newer live rows.

## Risks / Trade-offs

- Source profile pages may contain old or aggregated financing records. Mitigation: keep `event_date`, `source_adapter`, source URL, and confidence; do not hide provenance.
- Text product extraction can over-extract company slogans. Mitigation: require product/service section hints, reasonable name length, evidence spans, and `needs_review` quality until manually verified.
- Application scenario extraction can over-generalize broad marketing copy. Mitigation: only extract concrete scenario phrases near product/use-case markers, default to `needs_review`, and keep evidence spans.
- Full 1025-company live runs consume Serper and embedding quota. Mitigation: implement bounded `--limit`, source filters, and report files before full backfill.
- Upload-triggered live enrichment can be slow or externally rate-limited. Mitigation: scope every command to uploaded company IDs, expose command reports in the upload pipeline summary, and support an optional company-count limit for staged runs.
- A resumable runner adds state tables. Mitigation: keep the state schema small, append-only for search/review audit, and keep canonical products/events in existing domain tables.
- LLM fallback can over-extract product names. Mitigation: run it only after deterministic miss, require evidence span, validate lengths, and keep `needs_review`.
- Frontend display can become noisy. Mitigation: show compact recent products/events cards and keep raw JSON available.

## Migration Plan

1. Add tests for source-aware event extraction, source-text product extraction, company release/detail payloads, and Milvus company text.
2. Add a reversible migration for product structure columns and application scenario tables.
3. Implement minimal code to pass focused tests.
4. Run a bounded DB E2E on known companies such as `深圳旭宏医疗科技有限公司`.
5. Refresh company Milvus for the changed subset or run a dry-run when vector infrastructure is unavailable.
6. Run company/chat smoke queries and record evidence.
7. Add a reversible migration for enrichment batch/checkpoint/audit/review tables.
8. Convert upload-triggered enrichment into queued resumable batch execution and run a bounded upload-batch E2E.

Rollback is limited to disabling the new scripts and reverting API payload additions. Existing source/news rows remain valid evidence.
