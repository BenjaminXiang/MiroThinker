---
title: Professor/Paper PRD Gap Assessment 2026-05-04
date: 2026-05-04
status: active
owner: codex
module: apps/miroflow-agent professor/paper
problem_type: data_quality_gap
severity: high
tags: [professor, paper, prd, data-quality, stem, e2e]
---

# Professor/Paper PRD Gap Assessment 2026-05-04

## Scope

This note reassesses the current professor and paper collection/cleaning flow
against:

- `docs/Data-Agent-Shared-Spec.md`
- `docs/Professor-Data-Agent-PRD.md`
- `docs/Paper-Data-Agent-PRD.md`

The question is whether collecting professor/paper data while the pipeline is
still being developed has created product-quality risk.

## Current Live Data Snapshot

Captured from `miroflow_real` on 2026-05-04 UTC.

### Professor

| Metric | Value |
|---|---:|
| professor total | 787 |
| `quality_status=ready` | 774 |
| `quality_status=needs_review` | 13 |
| `identity_status=resolved` | 775 |
| missing name | 0 |
| missing primary institution | 4 |
| missing `profile_summary` | 0 |
| missing official profile page | 0 |
| missing title | 52 |
| missing department | 167 |
| professors with active research topic | 752 |

### Professor-Paper Links

| Link status | Links | Distinct professors |
|---|---:|---:|
| verified | 4184 | 412 |
| rejected | 4103 | 531 |

Only `412/787 = 52.4%` of current professors have at least one verified paper
link. This is the biggest gap for PRD requirements around representative
papers, paper-backed profile updates, and professor-to-paper navigation.

### Paper

| Metric | Value |
|---|---:|
| paper total | 7297 |
| `quality_status=needs_review` | 7297 |
| `identity_status=unverified` | 7297 |
| missing title_clean | 111 |
| missing authors | 828 |
| missing year | 886 |
| missing `summary_zh` | 3841 |
| missing abstract | 3271 |
| missing DOI | 2377 |
| missing DOI/OpenAlex/S2/arXiv external ID | 2367 |

Paper is not PRD-ready as a published canonical domain. It is useful as
intermediate evidence and retrieval material, but not yet a fully validated
paper knowledge base.

### Source Trace

| Metric | Value |
|---|---:|
| source_page total | 5598 |
| official source_page | 5505 |
| source_page with clean_text_path | 4 |

The high official-source count is good, but persisted clean text is not yet a
complete audit trail. Evidence URLs exist, while full source text replay remains
weak.

## PRD Alignment

### What Is Working

- Professor identity main anchor is mostly aligned with the PRD: official
  profile pages exist for current professor rows, names are present, and
  profile summaries are filled.
- Quality gates are preventing obvious low-quality professor rows from being
  treated as all-ready; `needs_review` rows are visible.
- Professor-paper link validation is conservative: rejected links are tracked
  instead of silently published.
- The new STEM full-harvest is correctly isolated from live Postgres while it is
  still running; it writes artifacts/SQLite first, which avoids polluting live
  serving data during development.

### Main Gaps

1. **Professor coverage is not complete.**
   Current live professor count is 787, while the 2026-05-04 STEM-only harvest
   discovered 1603 unique candidates before per-professor processing. Current
   serving data is therefore visibly incomplete for Shenzhen STEM coverage.

2. **Professor-paper coverage is insufficient.**
   Only about half of professors have verified paper links. This misses the
   PRD's "professor -> paper jump" and "paper-backed professor profile update"
   expectations for many professors.

3. **Paper domain is still unverified.**
   All 7297 paper rows are `needs_review/unverified`. `summary_zh` is missing
   for 3841 papers, and 2367 papers lack DOI/OpenAlex/S2/arXiv IDs. This does
   not meet the paper PRD's minimum published-object quality.

4. **The source audit trail is partial.**
   Official source pages are tracked, but `clean_text_path` coverage is very
   low. If operators need to re-audit why a field was extracted, URL evidence is
   often available, but local replay of the exact cleaned text is not.

5. **Live data was produced across evolving pipeline versions.**
   The current data is a mixture of prior runs, backfills, and newer gates. That
   is acceptable during development, but it means live rows should not be
   treated as a single clean full-harvest release until a fresh STEM run is
   validated and cut over.

## Product Risk

The biggest risk is not that the data is unusable. The risk is that current
professor rows look mostly ready while the paper domain and professor-paper
relations are not equally mature.

User-visible effects:

- Professor profile questions can often work.
- Paper-heavy questions may miss relevant papers or return unverified papers.
- "Which papers belong to this professor?" can be incomplete.
- Retrieval may recall paper chunks, but source confidence and canonical paper
  readiness are not yet aligned with PRD-level publication.

## Recommended Roadmap

### P0. Finish Current STEM Full-Harvest Assessment

- Wait for `host-professor-stem-full-harvest-2026-05-04T11-54-16Z.txt`.
- Read `e2e_report.json`, `quality_report.json`, `enriched_v3.jsonl`, and
  `paper_staging.jsonl`.
- Produce per-institution metrics:
  - discovered
  - released
  - blocked
  - ready
  - paper_staging count
  - verified paper coverage
  - alerts

### P1. Treat Paper Readiness As The Main Quality Gate

- Do not promote paper rows to `ready` only because they exist.
- For each paper, require:
  - non-empty title
  - authors
  - year
  - abstract or full-text-derived content
  - `summary_zh`
  - evidence source
  - either verified external ID or validated professor-paper link

### P2. Rebuild Professor/Paper Live Store From Clean Batch Roots

- Preserve company/patent.
- Rebuild professor/paper/professor_paper_link from the validated clean
  full-harvest artifacts.
- Keep rows that fail evidence gates as `needs_review` or
  `needs_enrichment`.

### P3. Strengthen Operator Observability

- Add pipeline summaries for professor/paper harvest:
  - stage counts
  - institution breakdown
  - field gaps
  - paper-link rejection reasons
  - source text replay paths
- Surface these in admin-console, not only in JSONL logs.

### P4. Retrieval Acceptance

After a clean rebuild:

- re-run professor topical retrieval
- re-run paper topical retrieval
- re-run professor -> paper and paper -> professor relationship queries
- manually sample top-k results for at least the largest STEM institutions

## Current Operating Decision

Do not cut the running STEM harvest directly into live Postgres/Milvus. Use it
as evidence to identify extraction and paper-link gaps first. A clean cutover is
only safe after the full-harvest report shows acceptable professor-paper
coverage and paper readiness issues have been addressed or explicitly marked as
review/enrichment work.

## Follow-up Fixes Applied

After this assessment, the smoke artifact exposed a quality-gate miss: a
refusal-style `profile_summary` saying the model could not construct a
scholarly profile was released as `needs_enrichment` rather than blocked at L1.

Fixes:

- `quality_gate.py` now treats additional refusal phrases such as
  `无法构建符合学术规范` and `若要生成高质量的学术摘要` as
  `profile_summary_boilerplate`.
- `pipeline_v3.py` now writes `enriched_v3.jsonl` / `paper_staging.jsonl`
  incrementally as each professor finishes, and logs Stage 2-6 progress every
  25 processed professors. This avoids opaque long-running harvests where no
  artifacts exist until all 1603 tasks finish.
- `scripts/analyze_professor_harvest_artifacts.py` produces per-institution
  and per-gap harvest summaries and re-applies the current quality gate to old
  artifacts.

Validation:

```bash
cd apps/miroflow-agent
UV_CACHE_DIR=/tmp/mirothinker-uv-cache-status uv run pytest \
  tests/data_agents/professor/test_quality_gate.py \
  tests/scripts/test_analyze_professor_harvest_artifacts.py -q
UV_CACHE_DIR=/tmp/mirothinker-uv-cache-status uv run ruff check \
  src/data_agents/professor/pipeline_v3.py \
  src/data_agents/professor/quality_gate.py \
  scripts/analyze_professor_harvest_artifacts.py \
  tests/data_agents/professor/test_quality_gate.py \
  tests/scripts/test_analyze_professor_harvest_artifacts.py
```

Earlier fixed full-harvest run, before the low-signal web-search override:

- log: `docs/source_backfills/host-professor-stem-full-harvest-2026-05-04T12-27-43Z.txt`
- output: `apps/miroflow-agent/logs/data_agents/professor_stem_full_harvest_2026-05-04T12-27-43Z`

## 2026-05-04 14:11 UTC E2E Baseline

The 12-profile host E2E baseline before the low-signal web-search override was:

- log: `docs/source_backfills/host-professor-stem-wide-harvest-2026-05-04T14-11-28Z.txt`
- output: `apps/miroflow-agent/logs/data_agents/professor_stem_wide_harvest_2026-05-04T14-11-28Z`
- analyzer: `apps/miroflow-agent/logs/data_agents/professor_stem_wide_harvest_2026-05-04T14-11-28Z/harvest_analysis.json`

Observed results:

| Metric | Value |
|---|---:|
| processed profiles | 12 |
| enriched STEM profiles | 11 |
| non-STEM filtered | 1 |
| released L1 | 10 |
| blocked L1 | 1 |
| ready | 9 |
| needs_enrichment | 1 |
| low_confidence | 1 |
| paper staging rows | 45 |
| official_site verified staging | 43 |
| OpenAlex candidate staging | 2 |
| failed_tasks rows | 0 |
| dirty-title scan hits | 0 |

The remaining blocked profile is `尤政院士`. The SIGS official pages
`/yzys/main.htm`, `/yzys/list.htm`, and `/yzys_181/list.htm` currently contain
navigation/title text but no substantive academic fields. The current decision
is to keep this row out of release with `insufficient_academic_signal` and
`profile_summary_boilerplate`, rather than publish a guessed profile.

The title parser fixes were validated against the previously dirty real-page
examples:

- `张雅鸥`: author markers and leading author names are no longer included in
  the paper title.
- `王晓浩`: short journal tails such as `Adv. Funct. Mater.` are no longer
  included in the paper title.
- `金欣`: `IEEE Trans...` venue tails are no longer included in the paper
  title.
- `陈道毅`: leading `and G. H. Jirka` / `and W. Brutsaert` author fragments
  are no longer included in the paper title.

The current isolated full-harvest task was started after the 12-profile E2E:

- tmux session: `prof_stem_full_2026_05_04T14_17_44Z`
- log: `docs/source_backfills/host-professor-stem-full-harvest-2026-05-04T14-17-44Z.txt`
- output: `apps/miroflow-agent/logs/data_agents/professor_stem_full_harvest_2026-05-04T14-17-44Z`

It intentionally unsets live Postgres DSNs and uses `--skip-vectorize`, so it
does not write to live Postgres/Milvus. Use this run to measure coverage,
per-institution release/blocked ratios, and remaining extraction gaps before
any shared-store rebuild.

## 2026-05-04 14:38 UTC Low-Signal Web Search E2E

The low-academic-signal homepage fallback was validated with:

- log: `docs/source_backfills/host-professor-stem-wide-harvest-low-signal-websearch-2026-05-04T14-38-58Z.txt`
- output: `apps/miroflow-agent/logs/data_agents/professor_stem_wide_harvest_low_signal_websearch_2026-05-04T14-38-58Z`
- analyzer: `apps/miroflow-agent/logs/data_agents/professor_stem_wide_harvest_low_signal_websearch_2026-05-04T14-38-58Z/harvest_analysis.json`

This run intentionally kept `--skip-web-search` enabled. The expected behavior
is that normal records skip web search, while profiles with no title,
department, research directions, papers, awards, positions, education, or work
experience force a web-search fallback.

Observed results:

| Metric | Value |
|---|---:|
| processed profiles | 12 |
| enriched STEM profiles | 11 |
| non-STEM filtered | 1 |
| released L1 | 11 |
| blocked L1 | 0 |
| ready | 9 |
| needs_enrichment | 2 |
| paper staging rows | 45 |
| official_site verified staging | 43 |
| OpenAlex candidate staging | 2 |
| low-signal web searches | 1 |
| low-signal web-search skips | 0 |
| identity verified pages | 3 |
| failed_tasks rows | 0 |
| dirty-title scan hits | 0 |

`尤政院士` is the key regression target. The empty SIGS homepage now triggers
`web_search_start ... low_academic_signal=True | reason=low_signal_override`,
then `web_search_done ... verified=3`. The release remains
`needs_enrichment`, because web search recovered research directions and
official evidence but did not recover verified publication anchors or paper
signals. This is acceptable under the current PRD interpretation: do not guess
papers or relationships when public evidence is absent, but do not block a
profile once it has source-grounded academic signal.

The previous full-harvest tmux run
`prof_stem_full_2026_05_04T14_17_44Z` used old no-fallback semantics and has
been stopped. The current detached full-harvest task is:

- tmux session: `prof_stem_full_low_signal_web_2026_05_04T14_45_20Z`
- log: `docs/source_backfills/host-professor-stem-full-harvest-low-signal-websearch-2026-05-04T14-45-20Z.txt`
- output: `apps/miroflow-agent/logs/data_agents/professor_stem_full_harvest_low_signal_websearch_2026-05-04T14-45-20Z`

It still unsets live Postgres DSNs and uses `--skip-vectorize`; it is safe for
coverage measurement and does not write to live Postgres/Milvus.
