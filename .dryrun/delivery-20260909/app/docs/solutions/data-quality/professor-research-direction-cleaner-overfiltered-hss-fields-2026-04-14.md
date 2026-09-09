---
title: Professor Research Direction Cleaner Overfiltered Legitimate HSS Fields
date: 2026-04-14
category: docs/solutions/data-quality
module: professor-enrichment-pipeline
problem_type: logic_error
component: homepage-crawler
symptoms:
  - Real professor URL E2E marked `深圳大学` as `needs_enrichment` or `needs_review` even though the official profile page clearly contained a `研究领域` field
  - Structured extraction recovered the `研究领域` label, but downstream `research_directions` still became empty
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [professor-pipeline, research-directions, hss, direction-cleaner, e2e-validation]
---

# Professor Research Direction Cleaner Overfiltered Legitimate HSS Fields

## Problem
The pipeline already knew how to find structured `研究方向/研究领域` sections, but the shared research-direction cleaner was too aggressive. It treated generic tokens like `课程` and `教学` as unconditional noise markers, which caused legitimate humanities and education fields such as `课程与教学论` to be truncated away.

## Symptoms
- The real URL-MD batch `logs/data_agents/professor_url_md_e2e_fullrefresh_20260414/url_e2e_summary.json` showed `007_深圳大学` failing with:
  - `missing_required_fields:research_directions`
  - `quality_status_failed:needs_review`
- Direct inspection of the official page `http://fe.szu.edu.cn/info/1021/1191.htm` showed:
  - `研究领域`
  - `课程与教学论`
- Running the official-direction extractor against the cached HTML proved the label was found, but the final cleaned value still became `[]`.

## What Didn't Work
- Treating all occurrences of `课程` as course noise.
- Treating all occurrences of `教学` as teaching-noise.
- Relying on the LLM alone to recover directions from official pages. The page already contained a deterministic structured field; the bug was downstream cleanup, not LLM recall.

## Solution
Tighten the direction cleaner and keep structured extraction deterministic.

1. In [direction_cleaner.py](../../../apps/miroflow-agent/src/data_agents/professor/direction_cleaner.py), replace the over-broad single-word sentinels with more contextual phrases:
   - keep `主讲课程`, `课程：`, `课程:`, `课程建设`
   - keep `教学成果`, `教学改革`
   - remove the bare `课程` and `教学` sentinels
2. Keep structured research-direction extraction in [profile.py](../../../apps/miroflow-agent/src/data_agents/professor/profile.py) and [homepage_crawler.py](../../../apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py) feeding the shared cleaner, so the fix applies consistently across HTML parsing and homepage crawling.
3. Lock the regression with a targeted test:

```python
def test_keeps_curriculum_theory_as_legitimate_hss_direction():
    raw = ["课程与教学论"]
    assert clean_directions(raw) == ["课程与教学论"]
```

## Why This Works
The original heuristic optimized for STEM faculty pages where `课程` often appears inside teaching or syllabus noise. That assumption does not hold for education and broader HSS pages, where `课程与教学论` is itself a canonical research field.

The fix preserves the original intent of stripping obvious course-teaching noise, but only when the surrounding phrase actually looks like course metadata rather than a domain concept.

## Prevention
- Keep both levels of regression coverage:
  - unit-level cleaner tests in [test_direction_cleaner.py](../../../apps/miroflow-agent/tests/data_agents/professor/test_direction_cleaner.py)
  - structured extraction tests in [test_profile_extraction.py](../../../apps/miroflow-agent/tests/data_agents/professor/test_profile_extraction.py)
- Validate against real URL-MD samples, not synthetic smoke tests.
- Representative real proof from 2026-04-14 UTC:
  - before fix: `007_深圳大学` failed on missing `research_directions`
  - after fix: [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_target_007_20260414/url_e2e_summary.json) shows `靳玉乐` with `research_directions=["课程与教学论"]`, `paper_count=350`, and `gate_passed=true`
- Keep HSS-specific direction examples in tests so future cleaner tweaks do not silently re-break them.

## Related Issues
- [Discipline-Aware Professor Quality Gate](../best-practices/discipline-aware-professor-quality-gate-2026-04-14.md)
- [Official Publication Evidence Fallback For Professor Paper Signals](../integration-issues/official-publication-evidence-fallback-2026-04-14.md)
