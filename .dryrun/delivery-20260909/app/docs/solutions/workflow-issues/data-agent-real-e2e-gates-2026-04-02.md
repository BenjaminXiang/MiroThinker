---
title: Data-Agent PRD gap closure must use real-source E2E gates
date: 2026-04-02
last_updated: 2026-04-03
category: docs/solutions/workflow-issues
module: apps/miroflow-agent data_agents
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - Closing PRD-to-code gaps for data agents
  - Verifying crawler or XLSX-based domain pipelines
  - Deciding whether a domain slice is actually complete
tags: [data-agents, e2e, real-data, professor-crawler, company-release, patent-release, pyright, openai-client]
---

# Data-Agent PRD gap closure must use real-source E2E gates

## Context
The data-agent PRDs describe end-to-end domain behavior, but local unit tests only prove that contract mapping and deterministic transforms behave under controlled inputs. During the April 2, 2026 gap-closure pass, mocked checks would have missed three real integration failures:

- live university roster pages needed school-specific crawler rules and anti-noise filtering
- paper APIs failed differently under full load (`OpenAlex` budget exhaustion and `Semantic Scholar` WAF blocking)
- hybrid search returned semantic noise ahead of exact company-name matches

Treating fixture-only checks as completion would have falsely marked the PRD gap closure as done.

## Guidance
Use a two-layer verification model for every data-agent slice:

1. Use unit tests and small deterministic tests only as development guardrails.
2. Mark a slice complete only after it passes a real-source E2E gate:
   - Professor: live roster seed document in `docs/教授 URL.md`
   - Company: real企名片导出 XLSX in `docs/专辑项目导出1768807339.xlsx`
   - Patent: real专利 XLSX in `docs/2025-12-05 专利.xlsx`
   - Paper: real professor-anchored discovery over all professors released by the professor E2E
   - Cross-domain search: real release JSONL from all four domains, indexed into SQLite + Milvus Lite

Real-source E2E should verify artifact counts, outward-facing fields, and relation traversal. On April 2, 2026:

- `scripts/run_professor_release_e2e.py --report-output -` released 3274/3274 professor objects from 7 real school roster seeds after adding school-specific roster/profile handling and fallback URLs.
- `scripts/run_company_release_e2e.py --report-output -` released 1025/1025 company records from the real XLSX.
- `scripts/run_patent_release_e2e.py --report-output -` released 1930/1930 patent records from the real XLSX, with non-empty `company_ids` on linked rows.
- `scripts/run_paper_release_e2e.py --source hybrid --report-output -` processed 3274 professor records, released 4069 de-duplicated papers, updated all 3274 professor records, and finished with `failed_professor_count=0`.
- `scripts/run_cross_domain_search_e2e.py --paper-released ... --report-output -` indexed 10298 release objects and verified company/professor/paper/patent single-domain search, professor+paper cross-domain routing, `professor_papers`, and `company_patents`.

On April 3, 2026, a fresh rerun against current code and current live school pages produced:

- `scripts/run_professor_crawler_e2e.py --output logs/debug/professor_crawler_e2e_20260403T001550Z.json` discovered 3274 unique professors from 7 school seeds, with 3274/3274 profile fetch success, 2877 structured profiles, 397 partial profiles, and zero failed roster/profile fetches.
- `scripts/run_professor_release_e2e.py --report-output -` released 3274/3274 professor records with 6542 official evidence entries and zero skips/failures.
- `scripts/run_company_release_e2e.py --report-output -` released 1025/1025 company records from the real company XLSX.
- `scripts/run_patent_release_e2e.py --report-output -` released 1930/1930 patent records from the real patent XLSX.
- `scripts/run_paper_release_e2e.py --source hybrid --professor-records logs/debug/professor_release_e2e_20260403T002114Z/professor_records.jsonl --max-workers 4 --max-papers-per-professor 5 --report-output -` processed 3274 professor anchors, matched 1929 authors, released 5434 de-duplicated papers, updated all 3274 professor records, and finished with `failed_professor_count=0`.
- `scripts/run_cross_domain_search_e2e.py --paper-released logs/debug/paper_release_e2e_20260403T002423Z/released_objects.jsonl --report-output -` indexed 11663 release objects and verified single-domain search, professor+paper cross-domain routing, `professor_papers`, and `company_patents`.
- `PYTHONPATH=apps/miroflow-agent .venv/bin/pytest apps/miroflow-agent/tests/data_agents -q` passed with `158 passed, 6 warnings in 27.69s`.
- `PYTHONPATH=apps/miroflow-agent .venv/bin/pytest apps/miroflow-agent/tests/data_agents -q -W error::SyntaxWarning -W error::UserWarning` later passed with `158 passed in 27.79s` after moving warning suppression to the true trigger boundaries.

On April 3, 2026, a second fresh rerun after the root-template and pyright cleanup produced:

- `PYTHONPATH=apps/miroflow-agent .venv/bin/pytest tests/test_recommended_client_templates.py -q -W error::SyntaxWarning -W error::UserWarning` passed with `2 passed in 2.73s`.
- `.venv/bin/pyright apps/miroflow-agent/src/data_agents` passed with `0 errors, 0 warnings, 0 informations` after binding pyright to the repo `.venv` in root `pyproject.toml` and tightening `publish_jsonl` / workbook / paper-provider / professor-release types.
- `PYTHONPATH=apps/miroflow-agent .venv/bin/pytest apps/miroflow-agent/tests/data_agents -q -W error::SyntaxWarning -W error::UserWarning` passed with `158 passed in 27.76s`.
- `scripts/run_professor_release_e2e.py --report-output -` released 3274/3274 professor records with 2877 structured inputs, 397 partial inputs, 6542 official evidence entries, and zero skips/failures.
- `scripts/run_company_release_e2e.py --report-output -` released 1025/1025 company records from `logs/debug/company_release_e2e_20260403T024135Z/`.
- `scripts/run_patent_release_e2e.py --report-output -` released 1930/1930 patent records from `logs/debug/patent_release_e2e_20260403T024135Z/`.
- `scripts/run_paper_release_e2e.py --source hybrid --professor-records logs/debug/professor_release_e2e_20260403T024530Z/professor_records.jsonl --max-workers 4 --max-papers-per-professor 5 --report-output -` processed 3274 professor anchors, matched 1939 authors, released 5482 de-duplicated papers, updated all 3274 professor records, and finished with `failed_professor_count=0`.
- `scripts/run_cross_domain_search_e2e.py --paper-released logs/debug/paper_release_e2e_20260403T024838Z/released_objects.jsonl --report-output -` indexed 11711 release objects and verified single-domain search, professor+paper cross-domain routing, `professor_papers`, and `company_patents`.

Two implementation patterns were necessary to make the full real gates reliable:

- Use school-specific professor roster extraction and profile-name cleanup when one school's HTML structure differs from generic assumptions. Generic extraction against PKUSZ/SZU pages produced navigation/topic names as fake professors until those pages got custom skip/extraction rules.
- For school sources with materially different page structures, one crawler strategy per school is acceptable and preferable to forcing one generic extractor. The generic path should remain as fallback, but school-specific strategies should own high-variance sources such as SIGS, HIT, PKUSZ, SUSTech, SZU, and CUHK-Shenzhen.
- Use provider fallback plus circuit breakers for large-scale paper discovery. OpenAlex returned `429 Insufficient budget ... $0 remaining`, and Semantic Scholar returned `429` with `x-api-key=blocked-by-waf`. The final `hybrid` strategy short-circuits those blocked providers process-wide and falls back to Crossref.

Cross-domain search also needs exact-first merging in hybrid mode. Returning Milvus semantic neighbors before SQLite exact matches caused company-name queries to miss the expected target in top-10 results. The service now merges SQL exact hits first, then appends semantic hits with deduplication.

Warning hygiene should be verified the same way as business logic. Three fixes on April 3, 2026 were only proven after rerunning the full suite with warnings promoted to errors:

- Use raw docstrings for helper text that documents literal JSON escapes such as `\/`, `\b`, and `\n`; otherwise Python can emit `SyntaxWarning` or silently interpret backslash escapes in documentation strings.
- Suppress known third-party warnings at the boundary that actually emits them, not at a higher-level caller. `openpyxl` workbook-style warnings were triggered by direct `load_workbook()` calls in both importer code and tests, and Milvus Lite's `pkg_resources` warning was triggered lazily during `MilvusClient(uri=...)`, not during `import pymilvus`.
- Validate the fix with both `pytest ... -W error::SyntaxWarning -W error::UserWarning` and script-level E2E commands run with `python -W error::UserWarning ...` so warning regressions cannot hide in CLI paths.

Template and static-analysis compatibility should be checked in the same gate. Two issues only showed up when root-level template tests and pyright were run in the current shell environment:

- Monkeypatched CLI tests may provide a reduced `argparse.Namespace`; provider builders should preserve parser defaults with `getattr(args, "model", DEFAULT_MODEL)` rather than assuming every parsed field exists.
- `openai.Client()` inherits shell proxy variables by default. If the environment points at a SOCKS proxy but `socksio` is not installed, client construction fails before any request is sent. The shared OpenAI compatibility helper now catches that `ImportError` and falls back to an explicit `DefaultHttpxClient(..., trust_env=False)`, and `QwenProvider` uses the same helper.
- Run `.venv/bin/pyright ...` with pyright bound to the repo virtualenv (`[tool.pyright] venvPath = "."`, `venv = ".venv"`). Otherwise installed packages such as `hydra` and `omegaconf` can appear missing even when runtime imports succeed.

## Why This Matters
PRD closure is about live behavior, not just code shape. Company/patent import and release can look correct in unit tests while live professor crawlers still extract page chrome as fake names, paper APIs silently fail under provider limits, or hybrid retrieval hides exact matches behind noisy nearest neighbors. Real E2E gates force those failures to surface before downstream publication and Agentic-RAG layers are declared done.

## When to Apply
- When a domain depends on live web crawling or externally hosted roster pages.
- When import data exists locally but release generation is still being added.
- When a reviewer asks whether a PRD gap is really closed across all schools and all release layers.
- When adding a fallback data provider or vector search path that may reorder exact matches.

## Examples
Before:

```text
Professor release tests pass, so professor domain is done.
```

After:

```text
Professor release mapping tests pass, but professor domain is not done until
the full real seed document in docs/教授 URL.md produces non-zero release
artifacts under scripts/run_professor_release_e2e.py.
```

Before:

```text
Patent linkage looks correct in unit tests.
```

After:

```text
Patent linkage is only considered delivered after the real patent XLSX E2E
produces release artifacts and linked rows with non-empty company_ids.
```

Before:

```text
Hybrid search can return Milvus results directly because semantic retrieval is enabled.
```

After:

```text
Hybrid search should merge SQLite exact matches first, then append Milvus semantic
matches, and a real cross-domain E2E query must prove target entities and relations
still appear in the result set.
```

## Related
- [2026-04-02-data-agent-prd-gap-closure-execution.md](/home/longxiang/MiroThinker/docs/superpowers/plans/2026-04-02-data-agent-prd-gap-closure-execution.md)
