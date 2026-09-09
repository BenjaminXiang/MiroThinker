---
title: Professor STEM Rebuild Current Problems
date: 2026-04-17
status: active
owner: codex
---

# Professor STEM Rebuild Current Problems

## Baseline

Current shared store status:

- `professor = 0`
- `paper = 0`
- `company = 1037`
- `patent = 1931`

This is intentional. Old polluted professor/paper data has been purged, but the clean rebuilt domains are not yet released.

## Already Contained

1. Old `2026-04-05` polluted professor/paper shared data has been removed from the live shared store.
2. School-adapter phase 1 is working for multiple Shenzhen STEM school families.
3. `gemma4`, `dashscope`, `ark`, `Embedding`, `Rerank`, and `OpenAlex` are available.
4. `Serper` key is valid, and direct `curl` requests succeed.
5. `admin-console` local test environment is now stable when run through `uv run python -m pytest`; the professor-paper relation read path is green.
6. A new clean shared-store rebuild path now exists: it can preserve current `company/patent`, rebuild `professor/paper/professor_paper_link` from batch-level clean professor SQLite outputs, and merge serving-side backfills for `丁文伯 -> 深圳无界智航` and `pFedGPA`.
7. This rebuild path has already been proven on real data with a scratch shared DB: using the clean `丁文伯 / 王学谦` batch plus preserved `company/patent`, workbook audit is `16 pass + 1 out_of_scope`.
8. The paper-source mainline is now proven on targeted real E2E: weak fragmented official publication extraction no longer overrides official-anchored ORCID (`段成国`), while high-quality official publication evidence still stays primary (`李海洲`).

## Still Open

### 1. Mainline is aligned; residual school/CMS family detail extraction is still open

The collection mainline is now the intended one in code:

- official school seed -> roster / teacher-search discovery
- official teacher detail page
- extract candidate anchored links from the official detail page
- let LLM classify and prioritize those candidates
- recurse only into anchored personal homepage / lab page / publication page
- treat ORCID / Scholar / DBLP / CV as strong anchored signals when present, but not as a prerequisite
- extract richer profile and paper evidence only from those anchored pages and their publication subpages
- when paper evidence is selected, official publication titles are primary only if they are usable; otherwise official-anchored ORCID / Scholar / CV must outrank hybrid author search

The remaining open problem is now narrower: some school/CMS families still expose real detail links in inline JS or similar non-anchor structures, and current roster extraction can miss them. Those misses degrade downstream profile/paper quality even though the mainline itself is correct. Until those residual extraction gaps are green on real E2E, live rebuild should not be treated as fully closed.

### 2. Live shared STEM release rebuild is not yet completed

The clean path can now write `professor`, `paper`, and `professor_paper_link` into per-run stores, and the new shared-store rebuild path has been validated on a scratch DB. However, the live shared store still has not been repopulated from the ongoing full STEM harvest batches. Until that live rebuild runs against the real shared DB, the web console will continue to show `professor = 0` and `paper = 0`.

### 3. Full-harvest coverage is still being validated on real school seeds

Current broad STEM batch is still a `limit-per-url=2` validation run. It is useful for quality regression detection, but it is not sufficient for coverage-sensitive workbook questions such as `丁文伯` or `王学谦`. Full-harvest real E2E is now the main open coverage gate.

### 4. URL-MD batch aggregation was previously missing, and is now fixed but still needs broad rerun confirmation

Per-URL stores now receive clean `paper` and `professor_paper_link` objects, and batch-level `released_objects.db` aggregation has been added. This has been verified on a real `深圳理工大学 算力微电子学院` rerun, but it still needs confirmation on a larger STEM batch after the currently running broad rerun completes.

### 5. Professor-company automatic web-search closure is still open

The serving-side backfill path already closes workbook `q1` on the rebuilt scratch DB, and the latest real Serper round now proves more about the automatic path: it can stably recover `丁文伯 -> 无界智航` as a public-web company mention and verify a collaboration-level link, but it still does not recover founder-grade evidence. Current evidence shows this relation is unlikely to come from university pages and should be treated as a public-web discovery problem with two different success thresholds:

- **mainline rebuild threshold**: verified backfill is sufficient to rebuild the live store and close workbook `q1`
- **automatic enrichment threshold**: founder-grade evidence should eventually be recovered without the backfill, but this is now a post-cutover quality improvement item rather than a live rebuild blocker

## Non-Blockers For Current Wave

These should not block STEM collection closure:

- vectorization / rerank serving quality
- HSS quality closure
- broad admin console UI work

## Current Priority

1. Close the residual school/CMS family detail-extraction gaps exposed by real full-harvest E2E
2. Expand the now-corrected mainline across the remaining STEM school families
3. Rebuild and republish clean `professor / paper / professor_paper_link` into the live shared store using the new batch-DB rebuild path
4. Re-run workbook-style and URL-MD real-data gates on the rebuilt live shared store
5. After the live rebuild is green, return to automatic professor-company founder-evidence recovery and any residual field/model optimization
