---
title: "W13-V2: Company Milvus + narrative 全量 dogfood（P1 验证）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（操作执行）；claude review + 归档
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w10-1-company-milvus.md
  - .agents/specs/2026-05-02-w10-4-company-narrative-enrichment.md
prd_anchor: docs/Company-Data-Agent-PRD.md §6.3 + §10
---

# W13-V2: Company Milvus + narrative 全量 dogfood（P1 验证）

## 1. Goal

W10-1（Company Milvus collection）+ W10-4（narrative LLM enrichment）已交付，但全部测试都是单测 + mock。本 spec：

1. 跑 `run_company_narrative_backfill.py` 全量（约 1025 公司） → 落 `profile_summary` + `technology_route_summary`
2. 跑 `run_milvus_backfill.py --domain=company` 全量 → `company_profiles` collection
3. 抽 50 条 query 评估 Top-5 召回准确率（PRD §10 ≥ 85%）
4. 归档 Operating Guide 风格 dogfood report

## 2. Non-goals

- **不**做 evaluation_summary 第三段（W13-D1 决策中）
- **不**改 narrative_enrichment 逻辑或 Milvus schema
- **不**接 chat B 路企业语义检索（chat.py 仍只用 paper；那是 P2 scope）
- **不**接 news_connectors / signal_event_extractor 真实抓取（W12-1 Phase 2 单立验证）

## 3. User-visible behavior

| 阶段 | 输入 | 输出 |
|---|---|---|
| 阶段 1 narrative backfill | 全 1025 公司（real DB）| `company.profile_summary` + `technology_route_summary` 两列覆盖率 ≥ 95% |
| 阶段 2 Milvus backfill | 阶段 1 完成后跑 | `company_profiles` collection 行数 ≈ 1025 |
| 阶段 3 retrieval 抽样 | 50 条 query（10 行业 × 5 query）| Top-5 ≥ 85% 召回准确率（人工标注） |

## 4. Operational steps

```bash
cd /home/longxiang/MiroThinker

# 0. 清代理（内网 gemma4）
unset https_proxy HTTPS_PROXY

cd apps/miroflow-agent

# 1. narrative backfill — 先 dry-run 50 条试跑
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_company_narrative_backfill.py --limit 50 --dry-run=false

# 2. 全量 narrative backfill
DATABASE_URL=...miroflow_real \
  uv run python scripts/run_company_narrative_backfill.py --dry-run=false
# 期望：覆盖率 ≥ 95%；checkpoint 落 logs/data_agents/company/narrative_runs/<run_id>.jsonl

# 3. Milvus backfill
MILVUS_URI=... DATABASE_URL=...miroflow_real \
  uv run python scripts/run_milvus_backfill.py --domain=company --limit=10 --dry-run
MILVUS_URI=... DATABASE_URL=...miroflow_real \
  uv run python scripts/run_milvus_backfill.py --domain=company

# 4. retrieval 抽样
uv run python -m pytest tests/scripts/test_run_company_retrieval_top5_eval.py -k smoke -v
# 如该脚本不存在则手写 50 条 query：
# 类别：手术机器人 / 自动驾驶 / AI 芯片 / 大模型 / 量子 / 工业软件 / 生物医药 / 新能源 / 半导体 / 工业母机
# 每类 5 query；retrieve top 5；人工标注 hit/miss

# 5. 归档
mkdir -p docs/source_backfills
mkdir -p docs/solutions/integration-issues
cp logs/data_agents/company/narrative_runs/<run_id>.jsonl \
   docs/source_backfills/company-narrative-backfill-2026-05-02.jsonl
# 写 docs/solutions/integration-issues/company-milvus-dogfood-2026-05-02.md
```

## 5. Validation gates

| 指标 | 阈值 | 数据来源 |
|---|---|---|
| narrative 覆盖率（profile_summary） | ≥ 95% | `SELECT count(*) FILTER (WHERE profile_summary IS NOT NULL) / count(*) FROM company` |
| narrative 覆盖率（technology_route_summary） | ≥ 95% | 同上 |
| 长度分布 | 200-300 字 / 100-200 字 | jsonl 抽 |
| Milvus collection 行数 | ≥ 95% × 公司数 | `db_milvus.collection.num_entities` |
| Top-5 召回准确率（PRD §10）| ≥ 85% | 50 条 query × 人工标注 |
| LLM 失败率 | < 5% | jsonl status 分布 |

不达标：

- narrative 覆盖率 < 95% → 检查源数据空缺；补一轮 retry
- Top-5 < 85% → 检查 vectorizer 拼字段（`vectorizer.py:_build_company_text`）；提 W10-1 follow-up

## 6. Affected paths

```
新增（产物）：
  docs/source_backfills/company-narrative-backfill-2026-05-02.jsonl
  docs/solutions/integration-issues/company-milvus-dogfood-2026-05-02.md
    （含：执行命令 / 覆盖率 / 5 条样本 / 50 条 retrieval 标注表 / Top-5 准确率 / 失败原因）
  apps/miroflow-agent/tests/scripts/test_run_company_retrieval_top5_eval.py（如不存在则简化为脚本）
```

## 7. Invariants

- LLM 走 `resolve_professor_llm_settings("gemma4")`（narrative_enrichment.py 已实装；本 spec 仅核对脚本是否硬编码 endpoint）
- 阶段 1 完成后才能跑阶段 2（Milvus 依赖 `profile_summary` 作 embedding 文本）
- run_id 经 require_real_run_id；sentinel 拒收
- Top-5 评估必须人工标注；不接受 LLM 自评

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| 公司缺 product_description / business_scope | narrative LLM 仍能 fallback；技术路线长度不足时降级到通用产业描述（已实装）|
| Milvus URI 不可达 | abort + 报错；不创空 collection |
| 阶段 3 query 中含品牌名（"小米的 AI 芯片公司"）| 视为带 entity 的复杂 query；标注允许"模糊命中" |

## 9. Done criteria

1. ✅ 全量 narrative backfill 覆盖率 ≥ 95%
2. ✅ Milvus company_profiles 行数 ≥ 95% × 公司数
3. ✅ Top-5 ≥ 85%（50 条人工标注）
4. ✅ 归档 jsonl 到 `docs/source_backfills/`
5. ✅ 写 dogfood report 到 `docs/solutions/integration-issues/`

## 10. Open questions

| 问题 | 默认决策 |
|---|---|
| 50 条 query 谁标？| codex 跑 retrieval；claude 标 + 复核 |
| 类别覆盖怎么选？| 10 行业 × 5 query；行业列表见 PRD §10 验收附录或自选典型 |
| 全量回填出错重跑机制？| 看 jsonl checkpoint，仅重跑 status≠'written' |
| 是否同时跑 evaluation_summary？| 否（W13-D1 未决）|
