---
title: Professor Generic Homepage Root Overrode Specific Profile URL
date: 2026-04-14
category: docs/solutions/data-quality
module: professor-enrichment-pipeline
problem_type: logic_error
component: homepage-crawler
symptoms:
  - Real professor URL E2E for `015_深圳理工大学_算力微电子学院` stayed red with `paper_backed_failed` even after the crawler learned how to read `发表了100余篇学术论文`
  - Running `crawl_homepage()` directly on the official profile page returned `official_paper_count=100`, but the full pipeline still wrote `official_paper_count=null`
  - Real professor URL E2E for `032_中山大学_深圳__生态学院` stalled on external `researchgate.net` homepages even though official `eco.sysu.edu.cn/teacher/...` pages were available
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [professor-pipeline, homepage-crawler, profile-url, official-paper-count, e2e-validation]
---

# Professor Generic Homepage Root Overrode Specific Profile URL

## Problem
Some discovered professor records carried both a `profile_url` and a `homepage`, but the `homepage` field could be either:
- a generic school root such as `https://www.suat-sz.edu.cn/`
- an external academic profile such as `https://www.researchgate.net/profile/...`

The homepage crawler always preferred `homepage` over `profile_url`, so it fetched the wrong page and never saw the professor-level evidence that was present on the official profile page.

## Symptoms
- In [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_target_015_currentcode_20260414/url_e2e_summary.json), `015_深圳理工大学_算力微电子学院` failed with:
  - `paper_backed_failed`
  - `quality_status_failed:needs_enrichment`
- The emitted `enriched_v3.jsonl` for that run showed:
  - `homepage=https://www.suat-sz.edu.cn/`
  - `profile_url=https://cme.suat-sz.edu.cn/info/1012/1294.htm`
  - `official_paper_count=null`
  - noisy research directions like `构建跨学科` that clearly came from the school homepage rather than the professor page
- For `032_中山大学_深圳__生态学院`, Stage 1 produced seeds such as:
  - `homepage=https://www.researchgate.net/profile/Tong_Bao`
  - `profile_url=http://eco.sysu.edu.cn/teacher/BaoTong`
  which meant the crawler was starting from ResearchGate instead of the official ecology faculty page.
- A direct real-page reproduction of `crawl_homepage()` against `https://cme.suat-sz.edu.cn/info/1012/1294.htm` returned:
  - `official_paper_count=100`
  - `research_directions=["高性能集成电路芯片设计与系统应用"]`

## What Didn't Work
- Only widening the publication-count regex. That made the direct crawler capable of reading `发表了100余篇学术论文`, but the pipeline still fetched the wrong URL.
- Looking only at the final `paper_count` field. The actual failure happened earlier: the crawler never entered the professor page that contained the evidence.

## Solution
Fix the crawler's entry-point selection before any HTML fetch happens.

1. In [homepage_crawler.py](../../../apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py), replace:

```python
homepage_url = profile.homepage or profile.profile_url
```

with a URL selector that:
- prefers `profile_url` when `homepage` is a generic site root
- prefers `profile_url` when both URLs are on the same host and `profile_url` has a deeper, more specific path
- prefers `profile_url` when `homepage` is an external academic profile host such as `researchgate.net`, `orcid.org`, `dblp.org`, `scholar.google`, `scopus`, or `webofscience`
- keeps `homepage` only when it is genuinely more specific or the only option

2. Keep the main-page narrative extraction in place so once the right page is fetched, sentences like:
- `长期从事高性能集成电路芯片设计与系统应用`
- `发表了100余篇学术论文`

can populate `research_directions` and `official_paper_count`.

3. Lock the regression with tests that prove both layers:
- main-page paper-count / narrative-direction extraction
- `profile_url` wins over a generic homepage root
- `profile_url` wins over external academic profile hosts

## Why This Works
This bug was not an extraction-capability problem. The parser already knew how to read the relevant profile page; it was simply pointed at the wrong URL. Fixing the URL-choice heuristic solves the failure at the source and avoids downstream workarounds in paper collection, quality gate, or profile ranking.

## Prevention
- Keep the crawler regression tests in [test_homepage_crawler.py](../../../apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py):
  - `test_extracts_main_page_paper_count_and_narrative_research_direction`
  - `test_prefers_specific_profile_url_over_generic_homepage_root`
  - `test_prefers_official_profile_url_over_external_research_profile`
- When a real E2E failure survives a parser fix, compare:
  - direct `crawl_homepage()` output on the expected `profile_url`
  - final `enriched_v3.jsonl` output from the full pipeline
  If the direct crawl works but pipeline output is empty or noisy, inspect URL selection before changing extraction rules.
- Real validation after the fix:
  - [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_target_015_after_homepageurlfix_20260414/url_e2e_summary.json)
  - `015_深圳理工大学_算力微电子学院` now selects `李慧云`, with `paper_count=100`, `quality_status=ready`, and `gate_passed=true`
  - [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_target_032_after_officialurlfix_20260414/url_e2e_summary.json)
  - `032_中山大学（深圳）生态学院` now selects `陈浩`, with `paper_count=796`, `quality_status=ready`, and `gate_passed=true`

## Related Issues
- [Official Publication Evidence Fallback For Professor Paper Signals](../integration-issues/official-publication-evidence-fallback-2026-04-14.md)
- [Professor Research Direction Cleaner Overfiltered Legitimate HSS Fields](./professor-research-direction-cleaner-overfiltered-hss-fields-2026-04-14.md)
