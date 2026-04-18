---
title: Discipline-Aware Professor Quality Gate Must Stay Quality-First
date: 2026-04-14
category: docs/solutions/best-practices
module: professor-quality-gate
problem_type: best_practice
component: service_object
severity: high
applies_when:
  - Professor quality gate needs to cover humanities or social-science faculty without lowering overall data quality
  - URL E2E and release gating must stay semantically aligned on what counts as scholarly output
tags: [professor-quality-gate, hss, scholarly-output, url-e2e, data-quality]
---

# Discipline-Aware Professor Quality Gate Must Stay Quality-First

## Context
The professor pipeline originally treated `paper_count > 0` or `top_papers > 0` as the only acceptable scholarly output signal. That is appropriate for STEM, but it incorrectly leaves some humanities and social-science faculty in `needs_enrichment` even when their official pages clearly show discipline-appropriate academic output such as social-science projects or teaching/research awards. The risk on the other side is equally real: many STEM faculty pages also list awards, so a naive “awards can replace papers” rule would quietly degrade data quality.

## Guidance
Keep the shared gate narrow and explicit:

1. Continue requiring paper evidence for STEM.
2. Only enable fallback scholarly-output signals for a conservative HSS department set.
3. Only accept official HSS fallback signals that are still academically meaningful:
   - social-science style projects such as `国家社科`, `社科基金`, `教育部人文`, `教育部社科`
   - academic or teaching-achievement awards such as `教学成果`, `哲学社会科学`, `人文社科`, `优秀成果`
4. Reuse the same helper in both shared quality evaluation and URL E2E gate computation so the batch report cannot drift from the release gate.

The implementation lives in:
- [quality_gate.py](../../../apps/miroflow-agent/src/data_agents/professor/quality_gate.py)
- [run_professor_url_md_e2e.py](../../../apps/miroflow-agent/scripts/run_professor_url_md_e2e.py)

The shape is intentionally small:

```python
def has_scholarly_output_signal(profile):
    if _has_paper_signal(profile):
        return True
    if not _is_hss_profile(profile):
        return False
    return _has_hss_project_signal(profile.projects) or _has_hss_award_signal(profile.awards)
```

## Why This Matters
This preserves the core quality contract instead of weakening it.

- HSS faculty with real official scholarly signals are no longer forced into `needs_enrichment` just because paper APIs are weak.
- STEM faculty do not inherit the same relaxation through generic award text.
- URL E2E reports now reflect the same scholarly-output semantics as the release gate, which prevents “report says pass, release says fail” drift.

The recent read-only scan of real artifacts showed exactly this boundary:
- likely beneficiaries were HSS examples such as `深圳大学 / 教育学部 / 靳玉乐`, `李臣`, `叶文梓`, plus `深圳技术大学 / 创意设计学院 / 李立全`
- the same award-only logic would be unsafe for STEM examples under `深圳理工大学 / 算力微电子学院`

Representative evidence paths:
- [fullrefresh 深圳大学 教育学部](../../../logs/data_agents/professor_url_md_e2e_fullrefresh_20260414/007_深圳大学/enriched_v3.jsonl)
- [深圳大学 batch 01-10](../../../logs/data_agents/professor_url_fullflow_batch_01_10_20260413/004_深圳大学/enriched_v3.jsonl)
- [深圳技术大学 创意设计学院](../../../logs/data_agents/professor_url_fullflow_batch_32_41_20260413/040_深圳技术大学_创意设计学院/enriched_v3.jsonl)
- [深圳理工大学 算力微电子学院 risk sample](../../../logs/data_agents/professor_url_md_e2e_official_publication_round1_20260414/003_深圳理工大学_算力微电子学院/enriched_v3.jsonl)

## When to Apply
- When a professor page is clearly from education, law, humanities, arts, journalism, communication, history, philosophy, or Marxism studies.
- When the record lacks paper evidence but the official page contains strong academic awards or social-science project evidence.
- When adding new gates or reports that reason about `paper_backed` or `ready`; they must call the shared scholarly-output helper instead of reimplementing heuristics.

## Examples
Before:
- `教育学部` professor with no papers and official `国家级教学成果一等奖`
  -> `needs_enrichment`
- URL E2E still reported `paper_backed_passed = false`

After:
- same HSS record
  -> `ready`
- URL E2E now reports `paper_backed_passed = true`

Control case that must stay red:
- `计算机科学与工程系` professor with no papers but `国家科技进步奖二等奖`
  -> still `needs_enrichment`

Fresh verification for the rule itself:
- targeted unit + script tests: `5 passed`
- broader regression slice: `102 passed`
- live check artifacts:
  - [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_quality_gate_livecheck_20260414/url_e2e_summary.json)
  - [url_e2e_summary.md](../../../logs/data_agents/professor_url_md_e2e_quality_gate_livecheck_20260414/url_e2e_summary.md)

## Related
- [Quality Status Compatibility](../../../docs/quality-status-compatibility.md)
- [Official Publication Evidence Fallback For Professor Paper Signals](../integration-issues/official-publication-evidence-fallback-2026-04-14.md)
