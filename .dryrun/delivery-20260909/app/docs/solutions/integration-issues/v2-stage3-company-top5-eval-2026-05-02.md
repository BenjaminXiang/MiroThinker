---
title: "V2 Stage 3 — Company Milvus Top-5 retrieval evaluation 2026-05-02"
date: 2026-05-02
owner: claude
status: needs_human_annotation
related_specs:
  - .agents/specs/2026-05-02-w13-V2-company-milvus-dogfood.md
context: 50 条 query × 10 行业 × 5 query；跑 RetrievalService(domains=("company",))；输出 csv 待人工标注 hit/miss
---

# V2 Stage 3 — Company Top-5 评估

## 1. 执行命令

```bash
cd /home/longxiang/MiroThinker/apps/admin-console
unset https_proxy HTTPS_PROXY
MILVUS_USE_REAL_CLIENT=1 \
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python /tmp/v2_stage3_eval.py
```

## 2. 50 条 query（10 行业 × 5）

类别：手术机器人 / 自动驾驶 / AI 芯片 / 大模型 / 量子 / 工业软件 / 生物医药 / 新能源 / 半导体 / 工业母机

风格混合：短指令（"做 AI 芯片"）/ 中等查询（"L4 自动驾驶解决方案"）/ 长描述（"做血管介入机器人的"）。

完整列表见 `/tmp/v2_stage3_eval.py` 内置 QUERIES。

## 3. 输出

- `docs/source_backfills/v2-stage3-company-top5-eval-2026-05-02.csv`
  - 列：idx / category / query / top1_id / top1_name / top1_summary / ... / top5_* / human_top1..5 / error
  - 50 条全部 5 hits（Total queries: 50, with results: 50）

## 4. Top-1 抽样观察（Claude 主观）

| # | 行业 | query | top1 | 主观贴题度 |
|---|---|---|---|---|
| 1 | 手术机器人 | 做手术机器人的公司 | 箴石医疗设备（手术导航机器人）| ✅ |
| 2 | 手术机器人 | 腔镜手术机器人深圳厂商 | 箴石医疗设备 | ✅ |
| 3 | 手术机器人 | 骨科机器人企业 | 箴石医疗设备 | 🟡 弱命中（前 5 含柳叶刀骨科）|
| 6 | 自动驾驶 | 自动驾驶感知公司 | 待标注 | — |
| 11 | AI 芯片 | 做 AI 芯片 | 待标注 | — |
| 16 | 大模型 | 做大模型的公司 | 待标注 | — |
| 21 | 量子 | 量子计算公司 | 待标注 | — |
| 26 | 工业软件 | 工业软件公司 | 满天星工业软件 | ✅ |
| 27 | 工业软件 | 深圳 EDA 工具 | 满天星工业软件 | 🟡 弱命中 |
| 31 | 生物医药 | 做基因测序的公司 | 儒瀚科技 | 待人工核 |
| 36 | 新能源 | 做储能的公司 | 启垠科技（深圳）| 待人工核 |
| 41 | 半导体 | 深圳半导体设备 | 华芯智能装备 | ✅ 设备厂商命中 |
| 42 | 半导体 | 光刻胶供应商 | 精石光掩膜技术 | 🟡 相关但不直接是光刻胶 |
| 46 | 工业母机 | 工业母机企业 | 金一信息科技 | 待人工核 |
| 47 | 工业母机 | 深圳 CNC 机床 | 深圳矢量层流科技 | 🟡 弱命中 |
| 48 | 工业母机 | 做激光切割机的 | 深圳浦华激光技术 | ✅ |

## 5. 人工标注流程

打开 csv，对每条 query 的 top1..top5：

- 在 `human_top1..5` 列填：
  - `hit` — top-N 中有 1 个或更多相关公司（按行业匹配 OR 业务点匹配）
  - `miss` — top-N 全部无关
  - `partial` — 部分相关（如行业大类对但具体业务点偏）

按 V2 spec §5：
- 阈值：Top-5 准确率 ≥ 85% (≥ 43 / 50)
- 命中口径：top-N 中至少 1 条公司业务/行业与 query 大类匹配 → hit

## 6. chat 端到端实测（host curl 验证）

```
POST /api/chat {"query": "深圳做手术机器人的公司"} → HTTP 200
- query_type: D_cross_domain_topic
- 教授命中 4: 徐天添、匡绍龙、李孟棠、王琼
- 公司命中 6: 奥昇 / 深圳惟德 / 柳叶刀 / 爱博合创 / 箴石 / 通甪
- 论文命中 1
- answer_text (LLM 合成)：
  "在深圳从事医疗机器人相关领域的公司包括奥昇医疗科技 [6]、
   深圳惟德精准医疗科技 [7]、深圳柳叶刀机器人 [8]、
   深圳爱博合创医疗机器人 [9] 以及箴石医疗设备 [10]。"
```

证明 admin-console chat.py 端到端通：retrieval + LLM 合成 + citation 全链路。

## 7. 重要副发现

`apps/miroflow-agent/src/data_agents/storage/milvus_collections.py:148-159` 全局 monkey-patch：
- 默认 `.db` URI 走 in-memory mock client
- 必须 `MILVUS_USE_REAL_CLIENT=1` 才用真 Milvus

admin-console 生产进程 env 已设此标志（`/proc/{pid}/environ` 实测确认）。但**仓库代码 / 文档 / spec 中没显式说明这个 env 要求** — 任何未来在本地 dev 跑 `uv run uvicorn ...` 的人会 silent 0 hits。

需要 follow-up：
- 在 `apps/admin-console/backend/main.py` 启动时强制 set `os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")` 或在 deps.py 跳过 monkey-patch
- 或在 README / CLAUDE.md 显式记此 env 要求

## 8. Done

- ✅ 50/50 retrieve OK；csv 已归档
- ✅ chat curl 实测 D 类 query 通
- ⏳ 人工标注（user 操作；目标 ≥ 85% Top-5 hit）
- ⏳ MILVUS_USE_REAL_CLIENT 显式化 follow-up（独立 spec）

## 9. Files

- `docs/source_backfills/v2-stage3-company-top5-eval-2026-05-02.csv` — 50 query × top5 + human_topN 列待标
- 本文：`docs/solutions/integration-issues/v2-stage3-company-top5-eval-2026-05-02.md`
- query 脚本：`/tmp/v2_stage3_eval.py`（一次性脚本；可作 follow-up 进 `scripts/`）
