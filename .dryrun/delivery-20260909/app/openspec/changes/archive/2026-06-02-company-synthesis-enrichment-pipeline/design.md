## Context

The Company domain already has a canonical XLSX import path, append-only
`company_snapshot` rows, `company.profile_summary`,
`company.technology_route_summary`, team-member rows, source news rows, product
and scenario tables, signal events, upload-scoped enrichment batches, Yiou and
PitchHub site-search adapters, official-site product capture, Milvus company
backfill, and admin detail views.

The current behavior does not match the desired operating model:

- XLSX is the trusted baseline, but `company.quality_status` defaults to
  `needs_review` and promotion currently depends on synthesized narrative
  fields rather than XLSX baseline completeness.
- Company detail payloads expose snapshot `description` and `business` as
  summary fields, so synthesized `company.profile_summary` and
  `technology_route_summary` may not be visible even when generated.
- Product and scenario extraction is source-specific and sparse. It consumes
  Yiou/PitchHub body text and official-product pages, but does not synthesize
  from XLSX descriptions, full official-site material, or gated generic web
  search results.
- Generic Serper is currently shaped like news search. The target behavior is
  identity-query search plus LLM/ReAct decisions about whether snippets are
  enough or full page fetches are needed.
- Long company profiles are needed for retrieval, not only for page display.

## Goals / Non-Goals

**Goals:**

- Publish XLSX-backed company base records automatically when identity is
  resolved and baseline fields are complete enough.
- Keep product, scenario, generic-web, and uncertain external facts reviewable
  independently from company base publish status.
- Generate longer, source-grounded company profiles and technology/production
  summaries from XLSX plus accepted high-quality source materials.
- Structure XLSX `team_raw` with LLM while preserving raw text and avoiding
  invented background.
- Extract product name, product description, product category, technical tags,
  target customers, and application scenarios from XLSX descriptions, official
  website material, Yiou/PitchHub material, and accepted generic web material.
- Run bounded official-site crawling for every uploaded company with a website.
- Run generic Serper identity searches for full names and trusted short names,
  using `gl="cn"` and `hl="zh-cn"`, then use a ReAct-style workflow to fetch
  full pages only when snippets are insufficient.
- Let newer, attributable financing evidence create funding signals and latest
  funding candidates without overwriting XLSX baseline silently.
- Persist audit evidence for query generation, snippet sufficiency, fetch
  decisions, source judgment, synthesis input, accepted facts, rejected facts,
  and miss reasons.
- Refresh company vectors only for touched companies.

**Non-Goals:**

- Do not require manual review before XLSX-backed company base records can be
  published.
- Do not extract recruiting or job-trend signals in this change.
- Do not let generic web search directly overwrite XLSX identity, baseline
  profile, or financing fields.
- Do not run an unbounded 1024-company live enrichment during implementation;
  validation must be bounded first.
- Do not redesign the whole Company schema unless an audit/source-material gap
  cannot be represented by existing tables.

## Decisions

1. **Separate company base quality from enrichment quality.**

   `company.quality_status` represents whether the XLSX-backed company base
   record is publishable. `company_product.quality_status`,
   `company_application_scenario.quality_status`, and event status represent
   reviewability of enriched facts. This prevents external-source uncertainty
   from blocking the whole company directory.

   Alternative considered: keep the current promotion rule and mark products
   ready faster. That would still leave companies without synthesized narratives
   stuck in review and would conflate company readiness with product readiness.

2. **Treat XLSX as a trusted baseline and source material, not as a low-quality
   crawler input.**

   XLSX fields SHOULD be written directly when they are explicit fields
   (industry, region, website, funding baseline, team raw, patent count, etc.).
   LLM synthesis uses XLSX text for long narratives, team structuring, and
   product/scenario fallback, but the original values remain preserved.

   Alternative considered: re-judge all XLSX fields with LLM. This adds cost and
   can degrade a trusted operator-provided source.

3. **Use source tiers for synthesis confidence.**

   XLSX and official websites are highest-priority owned/baseline sources.
   Yiou and 36Kr/PitchHub are high-quality third-party enrichment sources.
   Generic web search is supplementary and cannot contribute facts until LLM
   source judgment confirms company identity and fact attribution.

4. **Prefer a bounded internal ReAct-style runner before adding a large agent
   dependency.**

   The workflow needs four inspectable tools: `serper_search`, `fetch_webpage`,
   `judge_source`, and `extract_company_facts`. The first implementation SHOULD
   be a small deterministic tool loop using the existing OpenAI-compatible LLM
   client and existing HTTP fetchers. LangChain or LangGraph MAY be introduced
   only if the implementation keeps deterministic limits, audit records, and
   testability. This satisfies the ReAct behavior while avoiding an opaque batch
   agent.

5. **Use DeepSeek v4 pro as the active synthesis LLM through environment
   configuration.**

   Company synthesis, source judgment, and structured extraction SHOULD use the
   shared OpenAI-compatible LLM profile resolver with `deepseek-v4-pro`,
   `https://api.deepseek.com`, and `DEEPSEEK_API_KEY`. Runtime calls SHOULD use
   non-thinking mode for this rollout unless a later implementation task
   explicitly requires reasoning output. The Anthropic-compatible DeepSeek base
   URL may be recorded for future provider-specific clients, but this change
   uses the OpenAI-compatible path unless a later implementation task proves the
   Anthropic-compatible path is required.

6. **Generic web search uses identity-only queries.**

   Generic Serper queries MUST be generated from company full name, registered
   name, XLSX project/short name, and trusted LLM-extracted aliases. They MUST
   NOT append product, financing, founder, or keyword tails by default. Those
   richer terms remain appropriate for bounded high-trust site search when they
   are part of Yiou/PitchHub matching.

7. **Snippet sufficiency is a first-class LLM decision.**

   The runner first inspects Serper snippets. If the snippet clearly lacks
   company relevance, it rejects without fetching. If the snippet is relevant
   but insufficient for product/financing/scenario/team facts, it fetches the
   page body and re-judges. This controls cost and reduces noise.

8. **Synthesis outputs write through existing domain tables where possible.**

   Products and scenarios continue to use `upsert_company_product` and
   `upsert_company_application_scenario`. Financing continues to use
   `company_signal_event`. Long narratives update `company.profile_summary` and
   `company.technology_route_summary`. Team structure should extend
   `company_team_member` if the current columns are sufficient; otherwise add a
   small evidence-backed structure rather than overloading raw text.

9. **Company detail uses synthesized fields first.**

   Admin/release payloads MUST expose `company.profile_summary` and
   `technology_route_summary` first, falling back to snapshot `description` and
   `business` only when synthesized fields are absent. The detail page order is
   `Basic Information -> Products -> Application Scenarios -> Recent Events`.

10. **Long profiles are retrieval material.**

   Company vector text, chat context, and retrieval payloads must include long
   profile text, technology/production summary, products, target customers,
   scenarios, structured team highlights, and newer financing signals when
   present. Page display alone is not enough.

11. **Every missing enrichment outcome needs an operational reason.**

   Upload-scoped batch state should distinguish no queries, no results, all
   results rejected, fetch failed, snippet insufficient but fetch blocked, LLM
   rejected, synthesis produced no facts, and persistence failed.

## Risks / Trade-offs

- **LLM synthesis may invent facts** -> Prompts must require source-grounded JSON,
  evidence spans, and source IDs. Generic web facts need source judgment before
  synthesis.
- **Generic search may retrieve same-name or competitor pages** -> Identity-only
  queries improve recall, but accepted material must pass LLM identity and fact
  attribution gates.
- **Official websites may be JavaScript-heavy or noisy** -> Use bounded fetch,
  reader fallback where available, noise guards, and source-material audit.
- **A long narrative could bury stale XLSX information** -> Keep source dates and
  allow high-trust newer financing facts to produce new signal events instead of
  silently rewriting XLSX.
- **ReAct loops can become expensive** -> Hard-limit query count, result count,
  fetch count, body chars, LLM calls, and per-company time.
- **Changing quality promotion may publish bad rows if XLSX is malformed** ->
  Require resolved identity plus baseline completeness, keep low-confidence or
  malformed imports in review, and report promotion counts.
- **Schema changes may be needed for audit/source material** -> Prefer existing
  `company_news_item` and enrichment audit tables first. Add migration only when
  tests show existing tables cannot represent ReAct decisions or synthesis
  provenance.

## Migration Plan

1. Add failing tests for company quality promotion, summary-field priority,
   detail page order, long narrative validation, XLSX/team/product synthesis,
   identity-only query generation, Serper locale payload, ReAct decision audit,
   and vector text inclusion.
2. Implement P0 behavior without live web dependencies: quality promotion,
   API/detail fixes, long narrative generation, XLSX product/scenario fallback,
   team structuring, and vector text inclusion.
3. Add official-site source-material capture as a bounded upload-batch stage.
4. Add generic web search ReAct stage with dry-run first, query/fetch/judgment
   audit, and strict source judgment.
5. Add synthesis persistence for accepted materials and newer financing signals.
6. Run focused tests and OpenSpec validation after each stage.
7. Run bounded validation on a small sample, then a 100-company validation
   without full 1024-company refresh.
8. Refresh Milvus only for touched companies and run representative chat/RAG
   smoke checks.

Rollback is staged: disable new upload-batch stages by flag, leave XLSX base
records published, and keep external products/scenarios/events review-gated if
source synthesis is paused.

## Open Questions

- Whether existing enrichment audit tables can represent every ReAct decision
  cleanly or a dedicated `company_source_material` table is needed.
- Whether product/scenario results synthesized only from XLSX plus official
  material can be promoted to `ready` automatically at the same threshold, or
  official-only and XLSX-only should use different confidence cutoffs.
- Whether team structuring should extend `company_team_member` columns directly
  or write a separate evidence-backed team enrichment table.
