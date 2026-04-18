---
title: Official Publication Evidence Fallback For Professor Paper Signals
date: 2026-04-14
category: docs/solutions/integration-issues
module: professor-enrichment-pipeline
problem_type: integration_issue
component: assistant
symptoms:
  - Professor URL E2E reported `paper_backed_failed` for official faculty pages that visibly contained publication evidence
  - Site-wide `科研成果` pages could be miscounted as a professor's personal paper total when same-domain crawling followed low-affinity links
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [professor-pipeline, publication-evidence, homepage-crawler, paper-collector, e2e-validation]
---

# Official Publication Evidence Fallback For Professor Paper Signals

## Problem
The professor enrichment pipeline relied too heavily on external author disambiguation for `paper_count` and `top_papers`. That created false negatives for Chinese-name faculty pages whose official profiles contained usable publication evidence, and it also created a precision risk once homepage crawling started following broader same-domain "科研成果" links.

## Symptoms
- URL E2E batches repeatedly failed with `paper_backed_failed` and `quality_status_failed:needs_enrichment` on pages like `http://sa.sysu.edu.cn/zh-hans/teacher/faculty` and `http://saa.sysu.edu.cn/faculty`.
- A live regression run briefly produced `paper_count=12322` for `清华大学深圳国际研究生院`, which was obviously a site-wide research page count rather than a professor-level signal.
- Profiles such as `樊建平` still had `official_paper_count=null` and `publication_evidence_urls=[]`, confirming that some remaining failures were true evidence gaps rather than parser misses.

## What Didn't Work
- Relaxing OpenAlex/Semantic Scholar matching alone improved some English-name cases, but it did not solve official-page evidence that never entered the `paper_count/top_papers` contract.
- Counting publication mentions from any fetched same-domain page was too broad; it allowed low-affinity site navigation pages to leak institution-wide counts into professor records.

## Solution
Add an official publication evidence layer before paper enrichment, then constrain it with locality checks.

1. In [homepage_crawler.py](../../../apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py), upgrade link extraction from raw `href` collection to anchor-aware `_LinkInfo` parsing, score links by anchor text plus path affinity, and persist:
   - `official_paper_count`
   - `official_top_papers`
   - `publication_evidence_urls`
2. In [paper_collector.py](../../../apps/miroflow-agent/src/data_agents/professor/paper_collector.py), accept those official signals and use them as fallback paper evidence when external discovery has no usable paper set.
3. In [pipeline_v3.py](../../../apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py) and replay paths, pass the official publication fields through unchanged so quality gate and release continue reading the canonical `paper_count/top_papers` fields.
4. Restrict publication-count acceptance to the professor homepage itself or high-affinity publication subpages. Do not accept counts from arbitrary "relevant" same-domain pages.

Key implementation shape:

```python
# homepage_crawler.py
count_allowed = index == 0 or page.publication_candidate
page_count = _extract_publication_count(sanitized) if count_allowed else None
```

```python
# pipeline_v3.py
paper_result = await enrich_from_papers(
    official_paper_count=profile.official_paper_count,
    official_top_papers=profile.official_top_papers,
    publication_evidence_urls=profile.publication_evidence_urls,
    ...
)
```

```python
# paper_collector.py
if not hybrid_result and (official_top_papers or official_paper_count):
    collection_papers = _official_top_papers_to_raw_papers(...)
    collection_author_info = AcademicAuthorInfo(
        paper_count=official_paper_count or len(collection_papers),
        source="official_site",
        ...
    )
```

## Why This Works
The fix separates two concerns that were previously entangled:

- **Evidence discovery**: official faculty pages often contain publication counts or title lists that are good enough to satisfy the PRD's paper-backed requirement even when external person disambiguation is weak.
- **Identity precision**: publication counts are only trusted from the homepage or high-affinity publication subpages, so site-wide research hubs do not inflate professor-level records.

This keeps the downstream contract stable. Quality gate, search publishing, retrieval evaluation, and Phase A scripts still consume `paper_count` and `top_papers`; they do not need a new gating vocabulary.

## Prevention
- Keep the homepage crawler tests that lock both sides of the boundary:
  - anchor-text publication pages with local path affinity should populate official paper signals
  - low-affinity site-wide `科研成果` pages must not populate `official_paper_count`
- Keep the paper collector integration test that proves official publication signals can satisfy the paper stage without external academic hits.
- Validate with real URLs, not smoke tests. The representative validation batch is in:
  - [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_official_publication_validate_20260414/url_e2e_summary.json)
  - [url_e2e_summary.md](../../../logs/data_agents/professor_url_md_e2e_official_publication_validate_20260414/url_e2e_summary.md)
- Use at least one true-positive and one true-negative in every live verification batch. On 2026-04-14 UTC:
  - true positives stayed green: `清华大学深圳国际研究生院`, `中山大学（深圳）农业与生物技术学院`, `中山大学（深圳）航空航天学院`
  - true negative stayed red: `深圳理工大学 算力微电子学院`

## Related Issues
- [CUHK SSL Crawler Markdown Fallback](./cuhk-ssl-crawler-markdown-fallback-2026-04-07.md)
- [Gemma 4 LLM Integration Proxy and Provider Compat](./gemma-4-llm-integration-proxy-and-provider-compat-2026-04-06.md)
