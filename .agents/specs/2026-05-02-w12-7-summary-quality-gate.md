---
title: "W12-7: profile_summary quality_gate length check"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 12
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-7-summary-generator-raw-text.md
prd_anchor: docs/Professor-Data-Agent-PRD.md §模块一 R3 quality_gate
---

# W12-7: profile_summary quality_gate length check

## 1. Goal

W11-7 暴露 quality_gate.py 不校验 summary length 的 bug：丁文伯 75 chars 仍 `quality_status='ready'`，进入 admin-console / Milvus → 用户看到 PRD 不合规数据。

**本 spec**：quality_gate.py 加 length check（≥ 150 + 现有 BOILERPLATE 黑名单）；阻止 ready 状态推进。

## 2. Non-goals

- **不**改 BOILERPLATE_KEYWORDS（已存）
- **不**做 sentence-level entropy / NLP-based 检测
- **不**重新评估已 ready 的非 summary 维度（identity / content）
- **不**重新跑 quality_gate（脚本独立操作）

## 3. User-visible behavior

| 教授 summary 长度 | quality_gate 行为 |
|---|---|
| 0 / NULL | reject ("missing_profile_summary") |
| 1-149 chars | reject ("profile_summary_too_short") |
| ≥ 150 但含 BOILERPLATE keyword | reject ("profile_summary_boilerplate") |
| ≥ 150 + 无黑名单词 | accept |

reassess_quality 重跑后：原 `quality_status='ready'` 但 summary < 150 的 prof → 改 `quality_status='partial'` + pipeline_issue filed。

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/professor/quality_gate.py
    add _check_profile_summary_length(profile, *, min_length=150) -> CheckResult
    add _check_profile_summary_boilerplate(profile) -> CheckResult
    extend evaluate_professor_quality(...) gate chain

CREATE / MODIFY:
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py
    test_summary_length_check_rejects_below_150
    test_summary_length_check_accepts_above_150
    test_summary_boilerplate_check_rejects
    test_summary_full_check_accepts_clean

新增脚本：
  apps/miroflow-agent/scripts/run_quality_gate_reassess.py
    遍历 quality_status='ready' 的所有 prof
    跑新 quality_gate
    若 reject → UPDATE professor SET quality_status='partial' + pipeline_issue
```

## 5. Interface

```python
def _check_profile_summary_length(
    profile: EnrichedProfessorProfile, *, min_length: int = 150
) -> CheckResult:
    text = (profile.profile_summary or "").strip()
    if len(text) < min_length:
        return CheckResult(
            passed=False, code="profile_summary_too_short",
            message=f"profile_summary length {len(text)} < {min_length}",
        )
    return CheckResult(passed=True, code=None, message=None)

def _check_profile_summary_boilerplate(profile) -> CheckResult:
    text = (profile.profile_summary or "")
    for kw in BOILERPLATE_KEYWORDS:  # from summary_generator
        if kw in text:
            return CheckResult(
                passed=False, code="profile_summary_boilerplate",
                message=f"contains banned phrase: {kw}",
            )
    return CheckResult(passed=True, code=None, message=None)
```

## 6. Invariants

- min_length 默认 150（与 W11-7 reinforcement 一致）
- BOILERPLATE_KEYWORDS 从 summary_generator import（不重复定义）
- quality_status 只能 'ready' / 'partial' / 'rejected'（不动 enum）
- gate chain 顺序：identity > content > summary length > boilerplate
- summary 检查对 NULL 不 raise（视为 length=0）

## 7. Validation

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/professor/test_quality_gate.py \
                tests/scripts/test_run_quality_gate_reassess.py \
                -n0 --no-cov -v

# 既有不退化
uv run pytest tests/data_agents/professor/ -k quality -n0 --no-cov

# claude 操作 reassess
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_quality_gate_reassess.py
# 期望: ~ 5 prof 从 ready 改为 partial（W11-7 backfill 后剩 5 lt150）
```

## 8. Done criteria

1. ✅ quality_gate.py 加 2 个 check
2. ✅ 单测覆盖通过 / 拒绝 / 边界
3. ✅ reassess 脚本：原 ready 中 ~5 prof → partial
4. ✅ 既有 quality_gate tests 不退化

## 9. Stop conditions

- 多数 ready prof 被新 gate 拒（> 50%） → 阈值 150 太严；用 100
- BOILERPLATE 误报（合法 summary 命中） → 黑名单需 tune

## 10. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 长度阈值 | ≥ 150（与 reinforcement default 一致） |
| Boilerplate 检测 | 仅黑名单（无 entropy） |
| reassess 行为 | ready → partial + pipeline_issue |
