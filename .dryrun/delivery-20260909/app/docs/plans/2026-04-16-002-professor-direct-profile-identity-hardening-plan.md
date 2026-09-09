---
title: Professor Direct-Profile Identity Hardening Plan
date: 2026-04-16
owner: codex
status: completed
---

# Professor Direct-Profile Identity Hardening Plan

## Outcome

Implemented on 2026-04-16 UTC and validated with real-data E2E.

Final verification artifacts:

- [direct-profile round4 summary](../../logs/data_agents/professor_url_md_e2e_direct_identityfix_round4_20260416/url_e2e_summary.json)
- [URL.md sample 20-22 round2 summary](../../logs/data_agents/professor_url_md_e2e_urlmd_sample20_22_round2_20260416/url_e2e_summary.json)

Observed outcome:

- `SYSU detail page` resolved to `陈伟津`
- `CUHK personal root homepage` resolved to `Jianwei Huang`
- `docs/教授 URL.md` indexes `20-22` all `gate_passed=true`

## Goal

Close the remaining professor-pipeline issues that still surface in real direct-profile E2E after the Gemma4 transport/key fixes:

1. Root-homepage direct-profile URLs can still fall back into roster discovery and promote nav tabs such as `Teaching` into professor seeds.
2. Detail-page direct-profile URLs can still promote section headings such as `工作履历` into canonical `name`.
3. Shared quality gate can still mark non-empty but obviously wrong `profile.name` values as `ready`.
4. Official publication fallback can still misclassify footer/copyright text as `official_top_papers`.

The target is not just unit green. The target is real-data E2E with the current regression URLs no longer failing for the old reasons.

## Non-Goals

- Do not revisit Gemma4 provider wiring or key loading unless new evidence appears.
- Do not broaden retrieval or paper-source behavior outside the exposed issues above.
- Do not loosen URL E2E gate; keep it strict and make upstream data cleaner instead.

## Scope

Primary real regression URLs:

- `http://materials.sysu.edu.cn/teacher/162`
- `https://jianwei.cuhk.edu.cn/`

Primary supporting E2E path:

- `docs/教授 URL.md` seed `20` and then the existing `20-22` sample batch once fixes land

## Workstreams

### W1. Direct-profile discovery hardening

Problem:

- `https://jianwei.cuhk.edu.cn/` is a professor root homepage, but `_looks_like_direct_profile_url()` returns `False` for `/`, so discovery falls back to roster parsing and turns nav links into professor candidates.

Implementation:

1. Add regression tests for direct-profile discovery when:
   - seed label looks like a professor name or a direct professor seed
   - URL path is `/` but host/content pattern still indicates a single-professor homepage
   - negative fixtures prove lab/group/department homepages do not short-circuit
2. Extend direct-profile detection in [discovery.py](../../apps/miroflow-agent/src/data_agents/professor/discovery.py) so root-homepage professor seeds can short-circuit to `DiscoveredProfessorSeed(name=seed_label, profile_url=seed.roster_url, ...)` instead of roster recursion.
   The direct-profile shortcut must stay narrow:
   - URL path is exactly `/` with no query or fragment
   - `seed_label` is not institution/department text and is not an obvious non-person label
   - `seed_label` matches a person-like signal:
     - Chinese: 2-4 CJK characters after normalization
     - English: 2-4 title-cased tokens or `Lastname, Firstname` after normalization
   - known list/search/directory hosts or paths remain excluded
3. Keep current exclusions for obvious directory/list/search pages.

Success criteria:

- `https://jianwei.cuhk.edu.cn/` no longer yields `profile_url=https://jianwei.cuhk.edu.cn/teaching.html`
- discovery resolves the seed as the professor page itself

### W2. Detail-page name extraction hardening

Problem:

- `http://materials.sysu.edu.cn/teacher/162` can still produce `name="工作履历"` because section-heading candidates survive profile extraction and then win the canonical-name merge.

Implementation:

1. Add failing tests for profile extraction rejecting:
   - `工作履历`
   - `Teaching`
   - `Biography`
   - `Research`
   - `Publications`
   when they appear as headings or page-title fragments
2. Tighten [profile.py](../../apps/miroflow-agent/src/data_agents/professor/profile.py) name extraction so section labels and generic page sections do not enter the name candidate pipeline.
3. Expand [name_selection.py](../../apps/miroflow-agent/src/data_agents/professor/name_selection.py) only where needed as a second guardrail, not as the primary fix.

Success criteria:

- the SYSU regression URL no longer emits `name="工作履历"`
- the CUHK regression path no longer emits `name="Teaching"` even if discovery regresses

### W3. Quality gate identity hardening

Problem:

- URL E2E correctly blocks bad names, but shared quality gate still allows `ready` as long as `profile.name` is non-empty.

Implementation:

1. Add failing tests in [test_quality_gate.py](../../apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py) for profiles whose `name` is:
   - `Teaching`
   - `工作履历`
   - other obvious non-person labels already recognized by `name_selection`
2. Update [quality_gate.py](../../apps/miroflow-agent/src/data_agents/professor/quality_gate.py):
   - treat `profile.name` non-person labels as an explicit L1 failure
   - extend reader-artifact/non-person checks to `profile.name`, not just `name_en/title/profile_summary`
3. Keep canonical shared quality semantics unchanged: `ready / needs_review / needs_enrichment / low_confidence`

Success criteria:

- bad-name profiles cannot end in `ready`
- bad-name profiles cannot be released
- direct-profile regressions stop showing `released=1 ready=1 identity_failed`

### W4. Official publication footer filtering

Problem:

- `official_top_papers` can still absorb footer strings like `Copyright ... All Rights Reserved ...`.

Implementation:

1. Add failing homepage crawler tests for footer/copyright strings.
2. Tighten [homepage_crawler.py](../../apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py):
   - add blockers for `copyright`, `all rights reserved`, `designed by`, similar footer markers
   - keep current legitimate inline-publication title coverage
   - keep the change scoped to `_extract_official_publication_signals()` and related inline-publication parsing helpers, not paper source ranking
3. Re-verify that existing official publication fallback tests still pass.

Success criteria:

- footer text never appears in `official_top_papers`
- real CUHK regression output no longer carries the copyright pseudo-paper

## Execution Order

1. W1 discovery hardening
2. W2 detail-page name extraction hardening
3. W3 quality gate identity hardening
4. W4 publication footer filtering
5. Real-data E2E reruns
6. Claude cross-review on touched files
7. Docs refresh with final status and residual gaps

This order is deliberate:

- W1 and W2 remove the primary upstream identity corruption
- W3 makes the release path safe even if a name bug slips through
- W4 cleans the remaining official publication noise without blocking identity work

## Verification Plan

### Unit / contract

- Discovery tests for root-homepage direct-profile seeds
- Profile extraction tests for section-heading rejection
- Quality gate tests for non-person `profile.name`
- Homepage crawler tests for copyright/footer blocker

### Real-data E2E

Run after implementation:

1. Direct-profile regression batch:
   - SYSU detail page
   - CUHK professor homepage root
2. `docs/教授 URL.md` seed `20`, `limit=1`
3. `docs/教授 URL.md` sample `20-22`, `limit=2` if runtime remains acceptable

Expected outcomes:

- no Gemma4 401 regressions
- no `name="工作履历"` or `name="Teaching"` in enriched outputs
- no `official_top_papers` footer pollution
- direct-profile batch should move from `identity_failed` to either fully passing or failing for a new, narrower reason

## Risks

- Root-homepage direct-profile detection can become over-broad and accidentally treat lab/group homepages as professor pages.
- Over-tight name filters can drop legitimate short names or transliterated headings.
- Publication blockers can over-filter real English paper titles if the blocker list is too broad.

Mitigations:

- keep direct-profile detection gated by seed context and real regression fixtures
- use TDD with negative and positive examples
- keep real direct-profile E2E as the deciding signal after each fix group
