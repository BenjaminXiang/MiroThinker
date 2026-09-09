---
title: Professor STEM Issue Closure Plan
date: 2026-04-17
status: active
owner: codex
origin:
  - docs/solutions/workflow-issues/professor-stem-rebuild-current-problems-2026-04-17.md
  - docs/plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md
---

# Professor STEM Issue Closure Plan

## Goal

Close the currently known STEM rebuild blockers and repopulate shared `professor` and `paper` with clean data that can support workbook-style professor and paper questions.

## Wave 1: Parser and extraction hardening

Status: JSON robustness completed; official-anchored crawl mainline is aligned on targeted real E2E, with residual school/CMS detail-extraction fixes still in progress

### Unit 1A. Homepage LLM JSON robustness

Files:

- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py`

Acceptance:

- salvage first valid JSON object from mixed LLM output
- keep existing validation / filtering behavior
- pass targeted unit tests
- pass targeted real E2E rerun if the failing seed reproduces this parse issue

### Unit 1B. Serper provider transport hardening

Files:

- `apps/miroflow-agent/src/data_agents/providers/web_search.py`
- provider tests

Acceptance:

- current valid Serper key works through the provider path
- transport logic is robust to current TLS/proxy environment quirks

### Unit 1C. Official-detail-page anchored recursion correction

Status: mainline aligned; residual school/CMS detail-extraction fixes in progress

This is the canonical execution spec for the current crawl-mainline correction. `2026-04-17-002` Lane A must mirror this unit, not redefine it. School-adapter / roster-discovery expansion remains delegated to `2026-04-17-002` Lane B.

Files:

- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py`

Acceptance:

- official detail page candidate links are classified early by LLM into `personal_homepage / lab_or_group / publication_page / academic_profile / cv / ignore`
- `academic_profile` explicitly covers ORCID / Scholar / DBLP / ResearchGate / Semantic Scholar style academic profile URLs
- generic same-domain official links can no longer bypass the link planner and get fetched blindly
- `academic_profile / cv` are treated as strong optional anchors, not hard prerequisites
- only anchored personal/lab pages and their publication subpages feed richer profile/paper extraction
- if link planning fails, conservative fallback is allowed only for strong-signal official `academic_profile / cv / publication_page` links; `personal_homepage / lab_or_group` are intentionally excluded from fallback to preserve precision
- no generic same-domain relevant-page fallback is allowed
- targeted red-green tests explicitly cover `personal_homepage / lab_or_group` selection plus `academic_profile / cv` early planning
- targeted real E2E proves the corrected path on teachers whose official pages expose external personal homepage / CV / publication anchors

## Wave 2: STEM paper-backed closure

Status: completed for the previously failing `中山大学（深圳） 医学院` and `深圳理工大学 算力微电子学院` targeted runs, and for quality-gated official-publication vs ORCID source selection on targeted real E2E; broad confirmation still in progress.

Paper-source policy for this wave:

- official publication evidence is the primary paper fact source when the official chain yields usable titles/citations
- if official publication extraction is weak or fragmented, official-anchored ORCID / Scholar / CV are the next preferred anchors and outrank hybrid author search when they yield usable papers
- verified OpenAlex / hybrid remains the conservative fallback when official publication and official-anchored profile sources do not yield papers
- absence of ORCID alone is never a failure condition

### Unit 2A. Targeted failing schools

Targets:

- `中山大学（深圳） 医学院`
- `深圳理工大学 算力微电子学院`

Acceptance:

- both move from `paper_backed_failed` to passing or to a clearly understood non-parser evidence gap
- targeted red-green tests prove official publication and official-linked ORCID outrank hybrid paper results
- targeted red-green tests prove missing ORCID does not block official publication-driven closure
- targeted real E2E artifacts prove `段成国` switches from fragmented official-site titles to `official_linked_orcid`, while `李海洲` keeps high-quality `official_site` papers

### Unit 2B. Broad STEM batch rerun

Acceptance:

- broad STEM batch failure count decreases from the current `2/36`
- no regressions on already-green schools

## Wave 3: Storage redesign and release rebuild

Status: completed for the script + scratch validation path; live shared-store cutover still pending. `ProfessorPaperLink` contract/store/admin read-path, per-run paper/link publication, and the new shared-store batch-DB rebuild path are all implemented and tested; live shared-store rebuild is next.

### Unit 3A. First-class professor-paper relation design

Status: completed

Acceptance:

- implement a fact layer that separates canonical paper objects from verified authorship links
- stop using weak/unsafe serving fields as facts

### Unit 3B. Shared release rebuild

Status: in progress

Acceptance:

- rebuild `professor`, `paper`, and `professor_paper_link` from the new clean path only
- shared store no longer relies on old `ready` defaults or unsafe strong links
- preserve already-green `company / patent` domains during the cutover
- merge verified serving-side backfills for `丁文伯 -> 深圳无界智航` and `pFedGPA` during rebuild

## Wave 4: Workbook validation

Status: scratch rebuilt shared-store validation completed; live shared-store validation pending.

Acceptance:

- workbook coverage audit passes the required STEM subset
- live shared store supports professor/paper workbook-style queries

Progress note:

- a scratch rebuilt shared DB using the clean `丁文伯 / 王学谦` professor batch plus preserved `company/patent` already reaches `16 pass + 1 out_of_scope` on real workbook audit
- the remaining Wave 4 work is to move from scratch proof to live shared-store cutover after the running full-harvest family shards finish

## Release-Readiness Gate

Before any rebuilt STEM professor object can be released as `ready`, all of the following must be true:

- `identity_clean_passed`: human name, institution, and source profile are coherent; no obvious non-person label or title/department slot pollution
- `required_fields_passed`: at least `name`, `institution`, `profile_url or homepage`, and a non-template `profile_summary` are present
- `scholarly_output_passed`: scholarly output is backed by official publication evidence or verified professor-paper links; optional ORCID/Scholar/DBLP/CV anchors can strengthen this, but are not mandatory prerequisites
- `serving_projection_safe`: candidate or weak relations do not appear in released authoritative fields such as `top_papers`, `company_roles`, or any backward-compat relation projection

Anything that fails one of these checks must remain `needs_review` or `needs_enrichment`; no default-to-ready behavior is allowed.

## Immediate Next Step

Use the corrected mainline to close the remaining residual blockers in this order:

1. fix targeted school/CMS family detail-extraction failures exposed by full-harvest real E2E
2. widen the green path across the remaining STEM school families
3. repopulate the live shared store from the clean batch DB roots only after the collection mainline is green
4. run workbook validation against that rebuilt live shared DB and fix any remaining relation / serving issues it exposes

Note:

- `丁文伯 -> 深圳无界智航` is no longer treated as a live rebuild blocker
- the verified serving-side backfill closes workbook `q1` for the rebuild cutover
- automatic web-search still needs a later quality pass to recover founder-grade evidence without the backfill
