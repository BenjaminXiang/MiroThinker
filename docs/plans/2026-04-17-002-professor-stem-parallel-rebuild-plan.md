---
title: Professor STEM Parallel Rebuild Plan
date: 2026-04-17
status: active
owner: codex
origin:
  - docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md
  - docs/solutions/integration-issues/professor-stem-api-availability-and-risk-factors-2026-04-17.md
---

# Professor STEM Parallel Rebuild Plan

## Goal

Rebuild the Shenzhen STEM professor pipeline so that real `docs/教授 URL.md` E2E and workbook-style questions can be answered from clean released data, without reintroducing the 2026-04-05 professor/paper data quality failures.

## Current Ground Truth

- old shared `professor` and `paper` objects have already been purged from `logs/data_agents/released_objects.db`
- school-level adapter wave 1 is working on real data for multiple STEM schools
- the major remaining failures are no longer platform API outages
- the main remaining risks are now concentrated in residual school/CMS family extraction gaps, full-harvest coverage closure, and live shared-store rebuild

## Parallel Execution Lanes

### Lane A. Official-detail-page anchored recursion + homepage/LLM hardening

Canonical execution spec: `docs/plans/2026-04-17-003-professor-stem-issue-closure-plan.md`, Unit 1C. This lane is the portfolio view of that same unit and must not diverge from it.

Scope:
- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- related tests in `apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py`

Targets:
- preserve the current aligned mainline where the official detail page decides crawl direction before generic recursion can widen scope
- official detail page candidate links must be classified into `personal_homepage / lab_or_group / publication_page / academic_profile / cv / ignore`
- `academic_profile` explicitly covers ORCID / Scholar / DBLP / ResearchGate / Semantic Scholar style academic profile URLs
- only LLM-selected anchored HTML pages may continue into deeper HTML collection
- conservative fallback is allowed only when link planning fails, and only for strong-signal official `academic_profile / cv / publication_page` targets; generic same-domain relevant pages are never allowed to bypass the link planner
- `personal_homepage / lab_or_group` are intentionally not in the fallback whitelist: if planning fails, the system should prefer recall loss over recursively following a possibly wrong external site
- stop blind same-domain follow-through from official pages
- keep tolerant JSON parsing and strict slot cleaning for title, department, summary, and publication blocks
- treat ORCID as a strong optional anchor, not as a prerequisite for collection closure

Acceptance:
- targeted red-green tests proving ignored same-domain official links are not fetched
- targeted red-green tests proving `personal_homepage / lab_or_group` candidates are selected early and no ignored same-domain page is fetched
- targeted red-green tests proving `CV / Scholar / DBLP` candidates enter early link planning
- targeted real E2E rerun on teachers whose official pages anchor external personal homepages / lab pages / CV PDFs / publication pages

### Lane B. School adapter expansion for STEM schools

Scope:
- `apps/miroflow-agent/src/data_agents/professor/roster.py`
- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
- adapter tests in `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py` and `test_school_adapters.py`

Targets:
- expand deterministic coverage for remaining STEM school families
- reduce generic heuristic discovery on known Shenzhen school domains
- ensure recursive follow-through from school roster to faculty profile to official-detail-page anchored personal homepage / lab homepage where present

Acceptance:
- real URL-MD E2E on the STEM seed set
- no regression on already-green school families

### Lane C. STEM paper evidence closure

Scope:
- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- `apps/miroflow-agent/src/data_agents/paper/openalex.py`
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py`
- official evidence parsing in `homepage_crawler.py`

Targets:
- close `paper_backed_failed` on remaining STEM hard cases
- treat official publication evidence as the primary paper fact source only when the extracted titles/citations are usable
- when official publication extraction is weak or fragmented, prefer official-anchored ORCID / Scholar / CV before verified OpenAlex matches
- absence of ORCID must never be treated as a failure condition by itself; ORCID is a strong optional anchor, not a prerequisite
- keep professor-paper relations conservative and traceable

Acceptance:
- targeted red-green tests proving official publication and official-linked ORCID outrank hybrid results
- targeted red-green tests proving missing ORCID does not block official publication or other official anchors
- targeted real E2E reruns proving `段成国` falls back from weak official fragments to `official_linked_orcid` while `李海洲` stays on high-quality `official_site`
- targeted real E2E reruns for current failing STEM departments
- paper-backed failure count materially reduced on the broad STEM batch

### Lane D. Release rebuild + workbook closure

Scope:
- professor/paper release contracts and serving projection
- workbook coverage audit and retrieval validation scripts

Targets:
- rebuild `professor` then `paper` released domains from the new clean pipeline only
- validate against workbook-style questions
- keep weak or candidate relations out of released authoritative answers

Acceptance:
- shared store reflects rebuilt clean objects only
- workbook coverage audit passes the required STEM questions
- web console no longer shows old ready-but-wrong professor records
- release gate is explicit: `ready` requires clean identity, required profile fields, non-template summary, and scholarly output backed by official publication evidence or verified professor-paper links
- candidate or weak relations never enter released authoritative serving fields

## Execution Order

1. Lane A and Lane B run first in parallel.
2. Lane C starts as soon as fresh failing seeds from the broad STEM batch are known.
3. Lane D runs only after enough clean STEM profiles and verified paper links exist.

## Real E2E Gate

No lane is considered complete until it passes real-data E2E.

Required evidence per lane:

- targeted failing-seed rerun
- broad STEM batch rerun where relevant
- updated summary artifact under `logs/data_agents/`

## API Policy For This Wave

- use `gemma4` as default
- keep `dashscope` and `ark` as hot fallback options
- treat `Serper` as optional enrichment only
- keep vectorization disabled until collection-quality closure is stable

## Immediate Next Step

Use the now-aligned mainline to close the remaining full-harvest blockers in this order:

1. fix residual school/CMS family detail extraction gaps exposed by real full-harvest E2E
2. rerun the affected targeted seeds until they flip green
3. resume broad full-harvest validation and only then cut over the live shared-store rebuild
