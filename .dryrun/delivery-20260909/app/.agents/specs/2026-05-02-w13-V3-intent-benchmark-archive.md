---
title: "W13-V3: 100 条意图基准复跑 + CI gate 决策（P1 验证）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（操作执行）；claude review + CI 决策
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-1-c-type-classifier.md
  - .agents/specs/2026-05-02-w13-4-c-type-endpoint-handler.md
prd_anchor: docs/Agentic-RAG-PRD.md §F-R1（≥ 90% accuracy / per-class ≥ 70-80%）
---

# W13-V3: 100 条意图基准复跑 + CI gate 决策（P1 验证）

## 1. Goal

W9-3 已交付 `apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl`（100 条；分布 50/20/15/5/5/3/2 = A/B/C/D/E/F/G）+ `tests/test_classifier_benchmark.py`（marker `requires_classifier_llm`，pass gate `OVERALL=0.90 / PER_CLASS=0.70`）。但 `.github/workflows/postgres-tests.yml` 不跑 admin-console 测试，CI 上根本无 gate；目前仅线下手跑。

本 spec：

1. 在内网（可达 Gemma-4）跑一次完整 benchmark，归档结果
2. 决策 CI 落点：方案 A = systemd timer cron；方案 B = GH Action workflow（需 self-hosted runner 或代理跨网）
3. 把决策结果落 `.agents/specs/...` 跟进 spec

## 2. Non-goals

- **不**改 fixture 数据（W9-3 的 100 条）
- **不**改 classifier prompt（W11-1 + 后续 W13-4 影响 C 类型）
- **不**改 classifier 实现
- **不**全权决策 GH Action vs systemd（仅给出对比 + 推荐）

## 3. User-visible behavior

| 阶段 | 输入 | 输出 |
|---|---|---|
| 阶段 1 复跑 | `pytest -m requires_classifier_llm` + Gemma-4 endpoint | 报告：overall accuracy / per-class accuracy / 错分样本列表 |
| 阶段 2 决策 | 阶段 1 结果 + 跨网/资源 / 维护成本 | 一份 ADR-style 决策文档（systemd vs GH Action vs 不在 CI） |

## 4. Operational steps

```bash
cd /home/longxiang/MiroThinker

# 0. 清代理（内网 gemma4）
unset https_proxy HTTPS_PROXY

# 1. 复跑 benchmark
cd apps/admin-console
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v --tb=short \
  | tee /tmp/intent_benchmark_2026-05-02.log

# 2. 解析输出（记 overall / per-class / 错分样本）
# 3. 归档
mkdir -p docs/source_backfills
cp /tmp/intent_benchmark_2026-05-02.log \
   docs/source_backfills/intent-classifier-benchmark-2026-05-02.log

# 4. 写决策文档
# docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md
```

## 5. Validation gates

| 指标 | 阈值 | 报告位置 |
|---|---|---|
| Overall accuracy | ≥ 90%（PRD §F-R1）| `docs/source_backfills/intent-classifier-benchmark-2026-05-02.log` |
| Per-class A/B/C/D/E/F/G | ≥ 70%（PRD §F-R1 软门）| 同上 |
| C per-class | ≥ 80%（W11-1 §6 invariants）| 同上 |
| Token cost | 报告即可 | log |

不达标：

- Overall < 90% → 立即 escalate；prompt 调优独立 spec（不在本 spec 范围）
- C per-class < 80% → 检查 W11-1 prompt + fixture C 子集（15 条）

## 6. CI gate 决策（核心产出）

| 方案 | 优点 | 缺点 | 推荐 |
|---|---|---|---|
| A. systemd user timer（每日 02:00 跑）| 内网直接到 Gemma-4；不跨网；与 name-identity / topic-noise 共用 timer 模式 | 需要本地机器；输出落本地，CI 不可见 | ✅ 主选 |
| B. GH Action workflow（PR 触发）| 与 PR 强绑定；阻塞合并 | 需要 self-hosted runner（公网到内网穿透）；维护成本大 | ⚠️ 备选 |
| C. 仅手跑（保留现状）| 零成本 | 漂移风险高（W11-1 后续改 prompt 可能悄悄 regress）| ❌ 不接受 |

推荐：**方案 A**（systemd timer + 失败时邮件 / Slack 提示）。如内网/外网受限严格则方案 C 改为"每次 chat.py 改动 PR 必须线下手跑 + 报告 commit"。

## 7. Affected paths

```
新增（产物）：
  docs/source_backfills/intent-classifier-benchmark-2026-05-02.log
  docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md

可能新增（如选方案 A）：
  ops/systemd/intent-benchmark.service
  ops/systemd/intent-benchmark.timer
  scripts/run_intent_benchmark_periodic.sh
  （这部分不在本 spec 范围；ADR 之后另起 spec）
```

## 8. Invariants

- 跑前 `unset https_proxy HTTPS_PROXY`（auto-memory）
- 不改 fixture 数据
- ADR 必须含两个方案的对比 + 推荐 + 决策日期 + owner
- 报告必须含错分样本列表（每类抽 ≤ 3 条）

## 9. Edge cases

| 场景 | 处理 |
|---|---|
| Gemma-4 endpoint 不可达 | abort；报 `gemma4_endpoint_down` 不强 retry |
| 100 条全跑超时（> 5 min）| 接受；记录耗时；ADR 中提示 "CI 跑全集需要 5 min budget" |
| LLM 偶发偏差导致 overall 89% | 报告 + 注明（不算 fail；连续 2 次 < 90% 才提 prompt 调优）|

## 10. Done criteria

1. ✅ 100 条全部跑过；overall + per-class accuracy 数字记录在档
2. ✅ 错分样本列表（按类）归档
3. ✅ ADR-008 文档落地（含方案对比 + 推荐 + 决策日期）
4. ✅ token 总消耗与耗时报告

## 11. Open questions

| 问题 | 默认决策 |
|---|---|
| ADR 推荐方案是否需 user 拍板？| 是；本 spec 仅给推荐，user 锁后另起 spec 落地 |
| 跑结果如果 overall ≥ 95%，能不能更激进上 95% gate？| 当前不动；3 次连续 ≥ 95% 后再考虑 |
| C handler（W13-4）上线后是否要重跑？| 是；W13-4 land 后必跑一次（C handler 不影响 classifier 精度，但本批一并对齐）|
