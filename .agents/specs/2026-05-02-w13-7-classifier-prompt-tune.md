---
title: "W13-7: classifier prompt tune — B 类与 G 类拒分错"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施 prompt 调整）；claude review
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-V3-intent-benchmark-archive.md
  - .agents/specs/2026-05-02-w11-1-c-type-classifier.md
prd_anchor: docs/Agentic-RAG-PRD.md §F-R1 100 条意图基准 ≥ 90%
---

# W13-7: classifier prompt tune — B 类与 G 类拒分错

## 1. Goal

V3 真实跑 100 条 benchmark：overall 69%（gate 90% fail）。逐类：

| 类 | 准确率 | 错分主因 |
|---|---:|---|
| A | 70% | 边缘 |
| B | **35%** | → D（"深圳做激光雷达的公司"被分成跨域）|
| C | 93% | OK |
| D | 100% | OK |
| E | 80% | OK |
| F | 100% | OK |
| G | **50%** | → A（"介绍无界智航"分成精确）|

错分模式归因（见 `docs/source_backfills/intent-classifier-benchmark-2026-05-02-real.txt`）：

- B 类带地域修饰（"深圳"）的复合 query → 模型误判为 D 跨域聚合
- G 类带"介绍 X"模板的精确 entity query → 模型直接 A，而非走 G 的"先列候选 + 默认高置信"

## 2. Non-goals

- **不**改 fixture 数据（100 条已锁；prompt 必须能在固定 fixture 上达 90%）
- **不**改 100 条 benchmark gate 阈值
- **不**改 classifier model（仍 LLM）
- **不**做 in-the-loop self-tuning / RL；仅 prompt-engineering

## 3. Affected paths

```
修改：
  apps/admin-console/backend/api/chat.py
    _CLASSIFIER_SYSTEM 提示词加：
    - B 类："带地域修饰（深圳/广东）+ 行业关键词"仍属 B
      example：Q "深圳哪些公司做激光雷达" → type B target_domain=company
    - G 类："介绍 X" / "X 是谁" / "X 的相关信息"模板优先 G + 多候选 → clarification
      example：Q "介绍无界智航" → type G target_domain=company（多候选触发 clarification）
新增测试：
  apps/admin-console/tests/test_chat_classifier_b_g_tune.py
    - 5 个 B 类带地域 query → assert ctype=='B'
    - 5 个 G 类"介绍 X" → assert ctype=='G'
    - 既有 W11-1 / W9-3 测试不退化
```

## 4. Validation

```bash
cd apps/admin-console
unset https_proxy HTTPS_PROXY
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_chat_classifier_b_g_tune.py \
                tests/test_chat_classifier_c_type.py \
                tests/test_chat_v1.py -v

# 真跑 100 条 benchmark（claude 操作）
uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v
# 期望：overall ≥ 90%, B per-class ≥ 70%, G per-class ≥ 70%
```

## 5. Done criteria

1. ✅ overall ≥ 90%
2. ✅ B per-class ≥ 70%（从 35% 提升）
3. ✅ G per-class ≥ 70%（从 50% 提升）
4. ✅ 既有 chat regression 不退化（85+ tests）
5. ✅ ruff 通过

## 6. Stop conditions

- prompt 调优 1 轮后 overall < 85% → escalate；可能 fixture 标签需要 review
- B 类提升导致 D 类下降 < 80% → 重新平衡 prompt
- 修改 prompt 影响 chat 现有用户 query 行为（实测 curl 几条 D 类 query 验证）

## 7. Open questions

| 问题 | 默认决策 |
|---|---|
| 加 few-shot examples 还是改 system 描述？| few-shot（直接给 5 条 B + 5 条 G 反例）|
| 错分 fixture 是否需要复审？ | 否，本 spec 假设 fixture 标签正确 |
