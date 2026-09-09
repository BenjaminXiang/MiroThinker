---
title: "Professor Pipeline V3: Quality Gate False Blocks — L1/L2 Separation for Correctness vs Richness"
date: "2026-04-07"
category: logic-errors
module: src/data_agents/professor
problem_type: logic_error
component: tooling
severity: critical
symptoms:
  - "SZTU (深圳技术大学) professors all blocked by institution_not_shenzhen — keyword missing from SHENZHEN_INSTITUTION_KEYWORDS"
  - "SYSU navigation labels '教学名师' and '师资力量' extracted as professor names, blocked by institution_not_shenzhen"
  - "HITSZ professors blocked by profile_summary_length_invalid — summaries 169/177 chars, threshold 200"
  - "3/9 universities had zero released professors with no errors in logs"
root_cause: missing_validation
resolution_type: code_fix
tags:
  - professor-pipeline
  - quality-gate
  - shenzhen-institutions
  - roster-discovery
  - l1-l2-separation
  - false-positive-block
---

# Professor Pipeline V3: Quality Gate False Blocks — L1/L2 Separation for Correctness vs Richness

## Problem

Professor Pipeline V3 E2E validation revealed that 3 out of 9 Shenzhen universities (HITSZ, SYSU, SZTU) had all discovered professors blocked at the L1 quality gate. Three independent gaps compounded: incomplete institution keyword list, missing non-person name filters, and an L1 rule that conflated data richness with data correctness.

## Symptoms

- **SZTU**: 2 professors blocked with `institution_not_shenzhen` despite "深圳技术大学" being a legitimate Shenzhen university — the keyword was simply missing from `SHENZHEN_INSTITUTION_KEYWORDS`
- **SYSU**: Navigation labels "教学名师" and "师资力量" extracted as professor names, then blocked with `institution_not_shenzhen` + `profile_summary_length_invalid`
- **HITSZ**: 2 professors blocked with `profile_summary_length_invalid` — summaries were 169/177 chars, below the 200-char L1 threshold, despite being valid data from a university whose homepage system provides minimal info
- 3/9 universities had zero released professors — 33% failure rate with no errors in logs. The quality gate silently blocked valid data.

## What Didn't Work

1. **E2E with `--skip-web-search`**: Prevented external data from supplementing sparse profiles, so HITSZ professors could never reach the 200-char summary threshold from official sources alone.
2. **Treating all L1 rules equally**: The quality gate conflated data richness (summary length) with data correctness (wrong institution), applying the same L1 hard block to both. There was no mechanism to distinguish "data is wrong" from "data is sparse but correct."

## Solution

### Fix 1: `contracts.py` — Complete institution keywords

```python
# Before (missing SZTU and SYSU-Shenzhen):
SHENZHEN_INSTITUTION_KEYWORDS = (
    "清华大学深圳国际研究生院",
    "南方科技大学", "SUSTech",
    "深圳大学",
    "北京大学深圳研究生院", "PKUSZ",
    "深圳理工大学",
    "哈尔滨工业大学（深圳）", "HIT Shenzhen",
    "香港中文大学（深圳）", "CUHK-Shenzhen",
)

# After:
SHENZHEN_INSTITUTION_KEYWORDS = (
    ...
    "深圳技术大学",              # SZTU — added
    "SZTU",                      # SZTU English — added
    ...
    "中山大学（深圳）",           # SYSU-Shenzhen — added
)
```

### Fix 2: `roster.py` — Complete non-person keyword filter

```python
# Added to _NON_PERSON_KEYWORDS:
    "教学名师",   # SYSU navigation label mistaken for professor name
    "师资力量",   # SYSU navigation label mistaken for professor name
```

### Fix 3: `quality_gate.py` — Demote summary length from L1 to L2

```python
# Before — L1 hard block on length:
summary = profile.profile_summary
if not summary or len(summary) < 200 or len(summary) > 300:
    l1_failures.append("profile_summary_length_invalid")
elif any(kw in summary for kw in BOILERPLATE_KEYWORDS):
    l1_failures.append("profile_summary_boilerplate")

# After — L1 only for missing/boilerplate; length moves to L2:
summary = profile.profile_summary
if not summary:
    l1_failures.append("summary_missing")
elif any(kw in summary for kw in BOILERPLATE_KEYWORDS):
    l1_failures.append("profile_summary_boilerplate")

# L2 — quality markers (non-blocking):
if summary and (len(summary) < 200 or len(summary) > 300):
    l2_flags.append("summary_length_suboptimal")
```

### Fix 4: Tests updated

- `test_fails_l1_summary_too_short` → renamed `test_short_summary_passes_l1_with_l2_flag`: asserts L1 pass + L2 `summary_length_suboptimal`
- Added `test_fails_l1_missing_summary`: empty summary → L1 `summary_missing`
- 12/12 quality gate tests pass, 245/245 professor module tests pass

## Why This Works

**Design principle**: University websites' core value is discovering teacher listings. The quality gate must separate two fundamentally different concerns:

- **Data correctness** (L1 hard block): empty name, non-Shenzhen institution, missing official evidence, completely missing summary, boilerplate summary. These indicate the data is *wrong* and must be rejected.
- **Data richness** (L2 quality marker): summary too short/long, missing research directions, needs enrichment. These indicate the data is *incomplete but valid* and can be addressed by downstream enrichment workflows.

The original L1 gate treated a 169-char summary from HITSZ identically to a non-Shenzhen institution — both as hard blocks. But HITSZ's sparse homepage system is a *data source limitation*, not a data error. The professor exists, has a name, belongs to a Shenzhen university, and has an official evidence URL. Blocking such records prevents the pipeline from fulfilling its primary purpose: discovering which teachers each university has.

For the keyword gaps: `SHENZHEN_INSTITUTION_KEYWORDS` is the authoritative allowlist. Missing entries cause silent false positives that look like data quality issues but are actually configuration gaps. Similarly, `_NON_PERSON_KEYWORDS` must cover all navigation label patterns that university websites use near faculty listings.

## Prevention

1. **Audit institution keywords when adding university support**: Every new university must have all name variants (Chinese full name, English abbreviation, parenthetical campus notation) in `SHENZHEN_INSTITUTION_KEYWORDS`. If an entire university is blocked on `institution_not_shenzhen`, it is almost certainly a missing keyword.

2. **Maintain the L1/L2 separation principle**: Before adding any new L1 rule, ask: "Can this condition be caused by a legitimate data source providing sparse information?" If yes, it belongs in L2. L1 is for *incorrect* data; L2 is for *incomplete* data.

3. **Expand `_NON_PERSON_KEYWORDS` proactively**: When onboarding a new university, inspect its faculty page HTML for navigation labels, section headers, and UI elements that could be mistaken for person names. Add them before the first crawl.

4. **Per-university E2E pass/fail visibility**: A per-university summary (not just aggregate counts) makes systematic blocks immediately visible. "6/9 passing" should be a red flag that triggers per-university investigation.

## Verification

- 12/12 quality gate unit tests pass
- 245/245 professor module tests pass (0 regressions)
- Quality gate correctly: blocks empty summary (L1 `summary_missing`), blocks boilerplate (L1 `profile_summary_boilerplate`), passes short summary with L2 flag `summary_length_suboptimal`

## Files Modified

| File | Change |
|------|--------|
| `src/data_agents/contracts.py` | Added "深圳技术大学", "SZTU", "中山大学（深圳）" to `SHENZHEN_INSTITUTION_KEYWORDS` |
| `src/data_agents/professor/roster.py` | Added "教学名师", "师资力量" to `_NON_PERSON_KEYWORDS` |
| `src/data_agents/professor/quality_gate.py` | `profile_summary_length_invalid` (L1) → `summary_missing` (L1) + `summary_length_suboptimal` (L2) |
| `tests/data_agents/professor/test_quality_gate.py` | Updated tests for new L1/L2 semantics |

## Related Issues

- `docs/solutions/integration-issues/cuhk-ssl-crawler-markdown-fallback-2026-04-07.md` — Same E2E validation session; line 141 states "3 blocked by quality gate (data sparsity, not crawler issues)" — this is the upstream symptom that the quality gate redesign resolves
- `docs/solutions/workflow-issues/data-agent-real-e2e-gates-2026-04-02.md` — Establishes the E2E verification framework; documents the same pattern of navigation labels extracted as fake professors (line 71)
- `docs/solutions/professor-pipeline-v2-deployment-patterns-2026-04-05.md` — Section 4 documents missing domain suffix patterns, same problem class as missing `SHENZHEN_INSTITUTION_KEYWORDS`
- `docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md` — Unit 9 planned quality gate changes for V3; this change extends that plan to also cover `profile_summary` length (not just `retired_evaluation_field`)
