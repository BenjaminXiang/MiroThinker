---
title: "Professor Pipeline V3: Performance Optimization Opportunities"
date: "2026-04-07"
category: best-practices
module: src/data_agents/professor
problem_type: best_practice
component: tooling
severity: medium
status: historical_reference
superseded_by:
  - docs/solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md
  - docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md
applies_when:
  - "Full E2E collection across all 9 Shenzhen universities"
  - "Production data collection where time is a constraint"
  - "Scaling to more universities or larger faculty lists"
tags:
  - professor-pipeline
  - performance
  - parallelism
  - async
  - web-search
  - data-collection
---

# Professor Pipeline V3: Performance Optimization Opportunities

> Historical reference only. This document is a 2026-04-07 optimization snapshot, not current operating guidance.
>
> Current measured throughput and execution guidance live in [`docs/solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md`](../workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md). Current implementation priority is governed by [`docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md`](../../plans/2026-04-16-007-plan-portfolio-execution-roadmap.md).

## Context

Professor Pipeline V3 processes each professor through 8 sequential stages: Discovery → Regex Extraction → Homepage Crawl → Paper Collection → Agent Enrichment → Web Search + Identity Verification → Company Linking → Summary Generation → Quality Gate. A full E2E run across 9 Shenzhen universities with limit=5 per school takes significant time due to serial bottlenecks at multiple levels. This document catalogs optimization opportunities while preserving data quality invariants.

## Quality Invariants (Non-Negotiable)

These constraints must never be relaxed for performance:

1. **Identity verification**: confidence >= 0.8 required for web search results (`identity_verifier.py:CONFIDENCE_THRESHOLD`)
2. **Every web search result must pass identity verification** before merge — no bypass path
3. **L1 quality gate**: blocks incorrect data (empty name, non-Shenzhen institution, missing evidence, missing summary, boilerplate)
4. **LLM temperature for verification**: must stay at 0.1 for deterministic identity judgment
5. **Boilerplate detection**: `BOILERPLATE_KEYWORDS` check on summaries

## Optimization Opportunities

### Tier 1: High Impact, Low Risk

#### 1.1 Cross-School Parallelism (Script/Orchestrator Level)

**Current**: Schools run serially via bash loop or 3-way bash `&` parallelism.
**Bottleneck**: Each school's pipeline is independent — no shared state except the final SQLite store.
**Optimization**: Built-in multi-school orchestrator with configurable parallelism.

```python
# Current: serial
for seed_doc in seed_docs:
    result = await run_professor_pipeline_v3(config_for(seed_doc))

# Proposed: parallel with semaphore
school_semaphore = asyncio.Semaphore(parallel_schools)  # e.g., 3-4
async def run_school(seed_doc):
    async with school_semaphore:
        return await run_professor_pipeline_v3(config_for(seed_doc))

results = await asyncio.gather(*[run_school(s) for s in seed_docs])
```

**Impact**: ~3-4x wall-clock reduction for full E2E.
**Risk**: Low — each school's pipeline is already isolated. Only the final SQLite write needs serialization.
**Quality**: Unaffected — parallelism is at school level, not within verification logic.

#### 1.2 Async LLM Client Calls

**Current**: `client.chat.completions.create()` is synchronous, blocking the event loop despite the pipeline being async.
**Files**: `identity_verifier.py:129`, `web_search_enrichment.py:321`, `homepage_crawler.py`, `agent_enrichment.py`, `summary_generator.py`

```python
# Current (sync, blocks event loop):
response = llm_client.chat.completions.create(...)

# Proposed (truly async):
response = await async_llm_client.chat.completions.create(...)
```

**Impact**: With `max_concurrent=8`, currently 8 professors block on sync LLM calls. True async would allow the event loop to interleave LLM waits.
**Risk**: Low — OpenAI SDK supports `AsyncOpenAI` out of the box.
**Quality**: Unaffected — same prompts, same temperature, same model.

#### 1.3 Web Search Candidate Page Parallel Fetch

**Current**: `web_search_enrichment.py:289-348` processes candidates serially: fetch → verify → extract, one at a time.
**Bottleneck**: Each page fetch takes 5-20s, verification takes 2-5s LLM call. With 5 candidates, that's 35-125s per professor.

```python
# Current: serial
for candidate in unique_candidates[:max_pages]:
    html = fetch_html_fn(url, 20.0)       # 5-20s
    verification = await verify_identity(...)  # 2-5s
    if verification.is_same_person:
        extract = await extract_info(...)  # 2-5s

# Proposed: parallel fetch, serial verify
async def fetch_candidate(url):
    return url, fetch_html_fn(url, 20.0)

fetched = await asyncio.gather(*[
    fetch_candidate(c["link"]) for c in unique_candidates[:max_pages]
])

for url, html in fetched:
    verification = await verify_identity(...)  # Still serial — quality preserved
    if verification.is_same_person:
        extract = await extract_info(...)
```

**Impact**: Fetch time drops from serial sum to parallel max (e.g., 5 × 15s = 75s → ~15s).
**Risk**: Low — fetching is read-only. Verification remains serial per professor.
**Quality**: Unaffected — identity verification still runs on each page individually.

### Tier 2: Medium Impact, Medium Risk

#### 2.1 LLM Batch Verification

**Current**: Each candidate page gets its own LLM identity verification call.
**Optimization**: Batch 2-3 candidate pages into a single LLM call with multi-page verification prompt.

```python
# Proposed: batch verification prompt
"""
判断以下 3 个网页中，哪些描述了同一位教授。
目标教授: {name}, {institution}
网页 1: {url1} — {content1[:1000]}
网页 2: {url2} — {content2[:1000]}
网页 3: {url3} — {content3[:1000]}
输出: [{page: 1, is_same_person: true, confidence: 0.9}, ...]
"""
```

**Impact**: 5 LLM calls → 2 calls per professor.
**Risk**: Medium — batch prompts may reduce verification accuracy. Requires prompt engineering and evaluation.
**Quality**: Needs validation — must confirm batch accuracy matches single-page accuracy before deployment.

#### 2.2 Homepage Crawl + Paper Collection Overlap

**Current**: `pipeline_v3.py:256-313` runs homepage crawl, then paper collection serially.
**These are independent**: Paper collection queries Semantic Scholar/OpenAlex APIs, homepage crawl fetches university pages.

```python
# Proposed: overlap
homepage_task = asyncio.create_task(crawl_homepage(...))
paper_task = asyncio.create_task(enrich_from_papers(...))
homepage_result, paper_result = await asyncio.gather(homepage_task, paper_task)
```

**Impact**: Saves 5-15s per professor (paper API calls overlap with homepage crawl).
**Risk**: Medium — paper collection currently uses the homepage-enriched profile. If overlapped, paper collection uses the pre-homepage profile. May miss research directions from homepage.
**Mitigation**: Run homepage crawl first for research directions, then overlap paper collection with agent enrichment.

#### 2.3 Discovery Phase Pagination Parallelism

**Current**: Multi-page roster discovery (e.g., CUHK 50 pages, SZU 100+ pages) fetches pages serially.
**Optimization**: Fetch 3-5 pages in parallel per university.

**Impact**: Discovery phase for large rosters drops from minutes to tens of seconds.
**Risk**: Medium — some university servers may rate-limit or block concurrent requests.
**Mitigation**: Configurable concurrency per domain, with exponential backoff on 429/503.

### Tier 3: Low Impact, Speculative

#### 3.1 Serper Batch Search

**Current**: Each professor generates 2-3 search queries, each sent individually to Serper API.
**Optimization**: Serper supports batch search endpoints (beta).
**Impact**: Minor — Serper API is fast (~200ms per call).

#### 3.2 LLM Response Caching

**Current**: No caching. Re-runs regenerate all LLM outputs.
**Optimization**: Cache LLM verification results keyed by (professor_name, institution, page_url, content_hash).
**Impact**: Significant for re-runs, zero for first run.
**Risk**: Low — cache invalidation is simple (content hash changes → cache miss).

#### 3.3 Early Termination in Web Search

**Current**: Processes all candidates up to `max_pages` even after finding high-confidence matches.
**Optimization**: Stop after 2-3 verified pages (diminishing returns).
**Impact**: Minor — most professors have few relevant candidates.

## Implementation Priority

| Priority | Optimization | Impact | Risk | Effort |
|----------|-------------|--------|------|--------|
| **P0** | 1.1 Cross-school parallelism | 3-4x | Low | 1 day |
| **P0** | 1.2 Async LLM calls | 2-3x for concurrent professors | Low | 1 day |
| **P1** | 1.3 Parallel candidate fetch | 3-5x per web search stage | Low | 0.5 day |
| **P2** | 2.2 Homepage + paper overlap | 1.2-1.5x per professor | Medium | 0.5 day |
| **P2** | 2.3 Discovery pagination parallelism | 2-3x for discovery stage | Medium | 0.5 day |
| **P3** | 2.1 Batch LLM verification | 2x for web search stage | Medium | 1 day + eval |
| **P3** | 3.2 LLM response caching | Re-run only | Low | 0.5 day |

## Time Budget Estimate (Current vs Optimized)

Per professor (single school, limit=5):

| Stage | Current | With P0+P1 |
|-------|---------|------------|
| Discovery | 10-30s | 10-30s (unchanged) |
| Regex + Homepage | 10-20s | 10-20s |
| Paper Collection | 10-30s | 10-30s |
| Agent Enrichment | 15-60s | 15-60s |
| Web Search + ID Verify | 30-120s | **10-30s** (parallel fetch) |
| Summary Generation | 5-10s | 5-10s |
| **Per-professor total** | **80-270s** | **60-180s** |
| **Per-school (5 profs, concurrent=8)** | **2-8 min** | **1-5 min** |
| **All 9 schools (serial)** | **18-72 min** | — |
| **All 9 schools (3-way parallel)** | **6-24 min** | **3-15 min** |

## Related

- `src/data_agents/professor/pipeline_v3.py` — main pipeline orchestration
- `src/data_agents/professor/web_search_enrichment.py` — web search + identity verification loop
- `src/data_agents/professor/identity_verifier.py` — LLM-based identity verification (CONFIDENCE_THRESHOLD=0.8)
- `docs/solutions/logic-errors/professor-pipeline-v3-quality-gate-false-blocks-2026-04-07.md` — quality gate L1/L2 separation
