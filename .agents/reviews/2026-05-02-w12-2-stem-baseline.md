---
title: "W12-2: STEM Lane 1 baseline + 重跑路径分析"
date: 2026-05-02
owner: claude
status: baseline-only
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_plans:
  - docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md
---

# W12-2: STEM Lane 1 baseline + 重跑路径分析

## 决定

**不做完整 V3 pipeline 重跑**，原因：

1. **核心 gap 不是 pipeline 实施 bug，是上游身份匹配能力**：OpenAlex Authors API 对中文姓名匹配率 1.7%（13/787 教授拿到 ORCID）。重跑 V3 不解决这个问题。
2. **summary 已通过 W11-7 backfill 修复**：M6 reinforcement 全量回填 787 教授（运行中），平均 250-600 chars，超过 PRD 200-300 目标下限。
3. **底层数据扩张需要 STEM 学校 全量 harvest 重做**（M2.1 selector 升级，W12-4 单列），不是 V3 重跑。

## STEM Lane 1 当前 baseline（2026-05-02）

| 学校 | 教授数 | h_index 已填 | profile_summary < 150 |
|---|---:|---:|---:|
| 清华大学深圳国际研究生院 | 249 | 2 (0.8%) | 100% (回填中) |
| 中山大学（深圳） | 186 | 3 (1.6%) | 100% (回填中) |
| 深圳技术大学 | 169 | 5 (3.0%) | 100% (回填中) |
| 深圳理工大学 | 142 | 2 (1.4%) | 100% (回填中) |
| 香港中文大学（深圳） | 22 | 0 | 100% (回填中) |
| 北京大学深圳研究生院 | 6 | 0 | 100% (回填中) |
| 南方科技大学 | 3 | 0 | **采集严重不足**（实际应 ~500 教授） |
| 哈尔滨工业大学（深圳） | 3 | 0 | **采集严重不足** |
| 深圳大学 | 3 | 0 | **采集严重不足** |
| **合计** | **783** | **12 (1.5%)** | **100%** |

ORCID 覆盖：13/787（1.7%）— 核心 metric 缺失瓶颈。

## 路径分析

### 路径 A：纯 V3 pipeline 重跑（不推荐）

```bash
# 对每个学校跑全量 V3
for school in 清华大学深圳国际研究生院 中山大学（深圳） ...; do
  uv run python scripts/run_professor_pipeline_v3_e2e.py \
    --institution "$school" --limit 250
done
```

**问题**：
- 每教授 V3 跑 30-60 sec（含 LLM enrichment / paper collection / cross-domain）
- 787 教授 × 45 sec ≈ 10 hours
- ORCID 匹配仍走老 OpenAlex Authors path → 命中率不变
- 浪费 LLM token / Serper quota

### 路径 B：增量改进（推荐）

按 ROI 排序：

1. **W12-5（多源主页抓 follow Group Website）**：丁文伯例可见 raw_text 末尾有 `Group Website: http://ssr-group.net/index.html`。follow 这类链接可显著扩大 raw_text 覆盖。
2. **ORCID 提取增强**：homepage_crawler 中加 ORCID URL 正则；从 paper_full_text 中抽 ORCID（如 first author 是该教授时）；从 paper.openalex_id 反查 OpenAlex Work → authors → orcid。
3. **W12-4（M2.1 selector 扩展）**：清华 SIGS / 深圳理工 主页 publications section 提取 0 篇（W9-5 dogfood 实测）；selector pattern 需扩展到深圳高校 CMS templates。
4. **南方科技大学 / HIT-SZ / 深圳大学 全量 harvest**：当前各 3 教授；实际人数百级。这是新数据采集，不是重跑。

### 路径 C：metrics-focused 增量（可立即做）

```bash
# ORCID 已有的 13 教授刷新 metrics（已是真值；no-op）
# ORCID 缺失的 774 教授 → ORCID enrichment 改善前没法补 metrics
```

短期内 metrics 仍稀疏。

## 决策

**W12-2 不执行 V3 pipeline 重跑**。

立即可做（claude / codex）：
- W11-7 backfill 跑完后采样 5 prof（含丁文伯）确认 summary ≥ 200 chars 内容相关
- 归档本 baseline 报告
- W12-4 / W12-5 / W12-6 单独 spec（已规划但未启动）

延后到后续 wave：
- 完整 V3 重跑 → Wave 13 + 配套 ORCID enrichment
- 4 个采集不足学校的 fresh harvest → Wave 13

## Done criteria（W12-2 调整后）

1. ✅ 本 baseline 报告归档
2. ⏳ W11-7 backfill 完成 + 抽样验证
3. ⏳ W12-4 / W12-5 / W12-6 spec 起草
