## Context

The Company domain already has a usable XLSX import, canonical Postgres rows, narrative summaries, Milvus indexing, and basic chat retrieval. It is not complete as a data collection product because several important pieces remain open:

- `data.iyiou.com` is only reachable through a generic Serper `site:` filter, so it is not a durable source adapter with source-specific provenance, diagnostics, and acceptance.
- Official website and product-page capture exists only as a plan; there is no implemented product/enrichment table, crawler, extractor, or writer.
- The publish contract omits PRD-listed optional fields that are already present in the XLSX/canonical layer, including credit code, legal representative, registered capital, and patent count.
- Team raw introductions are captured from XLSX but are reduced to `name` and `role` before release, losing the background text needed for founder education and work-experience queries.
- Real E2E acceptance for the current XLSX file has not been rerun after these gaps are closed.

This change turns the Company domain from "main path usable, enrichment incomplete" into a source-grounded enrichment pipeline with honest acceptance evidence.

## Goals / Non-Goals

**Goals:**

- Add a first-class Yiou source adapter path for `data.iyiou.com` content with adapter-level provenance and extraction diagnostics.
- Add an official website/product-page capture path that can discover, fetch, extract, and store product-oriented company enrichment records with field evidence.
- Extend Company release contracts to expose PRD-listed optional publish fields when present.
- Promote captured team raw introductions into richer key-person structures with description, education hints, and work-experience hints.
- Preserve XLSX/canonical data as the skeleton source and treat external sources as reviewable enrichments unless stronger evidence supports an update.
- Run an E2E flow with `docs/专辑项目导出1768807339.xlsx` that covers import, enrichment/backfill, release, and retrieval smoke checks.

**Non-Goals:**

- Do not build a general web-scale crawler.
- Do not depend on paid enterprise APIs or login-gated sites.
- Do not claim complete Yiou coverage for every company; this change establishes the source adapter and acceptance harness.
- Do not overwrite XLSX/canonical identity fields from search snippets or low-confidence extraction.
- Do not expand online RAG domains beyond the current code contract unless a separate change covers that behavior.
- Do not mutate the XLSX source file.

## Decisions

1. Treat external sources as additive evidence and enrichment.
   - Rationale: the XLSX import is the stable company skeleton. Media, PR, and official pages are useful but vary in freshness and authority.
   - Implementation direction: external items store source URL, source type, adapter name, fetched timestamp, extraction status, and confidence. Canonical fields are widened only from already-imported structured source fields or high-confidence official-source product extraction.

2. Implement Yiou as a named adapter, not just a Serper flag.
   - Rationale: `site:data.iyiou.com` proves discovery can work, but it does not provide a stable adapter contract, source diagnostics, or an acceptance target.
   - Implementation direction: keep the existing Serper connector available as the discovery/fetch mechanism, but wrap `data.iyiou.com` usage in a Yiou-specific adapter surface that emits normalized `CompanyNewsRecord`/signal candidates with `source_adapter='iyiou'` or equivalent provenance.

3. Add product capture as a bounded official-site pipeline.
   - Rationale: product information is a core company query surface and is not present in the XLSX skeleton.
   - Implementation direction: implement additive storage for product records and per-field evidence if existing tables cannot represent product-level data. The crawler is bounded by company scope, same-host URLs, depth/page limits, and product/about/solution/news URL heuristics. Extraction starts rule-based and may add LLM fallback later if tests prove it is needed.

4. Extend publish contracts without making optional fields required.
   - Rationale: PRD lists credit code, legal representative, registered capital, and patent count as publishable but optional. The release DTO should expose them when known without breaking records that lack them.
   - Implementation direction: add optional fields to `CompanyRecord` and `to_released_object().core_facts`, backed first by `CompanyImportRecord` fields and later by canonical Postgres snapshots.

5. Promote team raw intro using deterministic extraction first.
   - Rationale: `team_raw` is already captured. Basic description preservation and simple education/work hint extraction can remove major information loss without relying on an LLM for the E2E.
   - Implementation direction: add optional `description`, `education_structured`, and `work_experience` fields to `CompanyKeyPerson`; preserve raw intro text as description and extract conservative hints from explicit university/degree/company/role phrases.

6. Validate with the real XLSX and a narrow E2E before broad claims.
   - Rationale: previous evidence proved import/search paths worked, but not the enrichment closure requested in this change.
   - Implementation direction: run unit/contract tests first, then an E2E command using `docs/专辑项目导出1768807339.xlsx`. If external network/API credentials are missing, the E2E must still validate deterministic XLSX import/release/key-person/product storage and record skipped external source checks with clear blockers.

## Risks / Trade-offs

- Source availability and anti-bot behavior may make live Yiou/official pages flaky. Mitigation: adapter tests use fixtures; real E2E records fetch failures separately from parser/storage failures.
- Official websites are heterogeneous and may be JS-rendered. Mitigation: Phase 1 crawler is bounded and HTML-first, with diagnostics for unsupported pages rather than fabricated product data.
- Product extraction can overclaim if a page is about a solution category rather than a named product. Mitigation: require evidence spans and confidence; store uncertain items as review-needed.
- Extending contracts can expose empty/null optional fields in API consumers. Mitigation: keep fields optional and include regression tests for JSON release shape.
- Current working tree has many unrelated changes. Mitigation: keep edits scoped to this change's OpenSpec and Company-domain files.

## Migration Plan

1. Add contract tests for Company release optional fields and richer key-person output.
2. Extend `CompanyKeyPerson` and `CompanyRecord` while preserving backward-compatible optional defaults.
3. Add deterministic key-person intro promotion and conservative education/work hint extraction.
4. Add product storage migration and writer if existing tables cannot represent product-level official-site evidence.
5. Add official-site crawler and product extractor tests using local HTML fixtures.
6. Add Yiou adapter tests proving source-specific provenance and diagnostics while reusing existing Serper discovery/fetch where appropriate.
7. Wire scripts or script options for Yiou ingest and official product capture.
8. Run focused unit/contract tests.
9. Run the real XLSX E2E with `docs/专辑项目导出1768807339.xlsx`, including import, release, enrichment/product backfill where possible, and retrieval smoke checks.
10. Record acceptance evidence and remaining external-source failures without overstating completion.

Rollback for code is a normal git revert of this change's Company files. Rollback for any E2E data writes must be scoped by the recorded run ID, source adapter, or generated product IDs; destructive deletion requires an explicit cleanup plan.

## Open Questions

- Whether product records should immediately be surfaced in `/api/chat` answers or only stored for later retrieval UI is outside this change unless current retrieval code already has a company product slot.
- If live Yiou pages block requests during E2E, fixture-backed adapter acceptance remains valid but live coverage must be marked as skipped with the network blocker.
