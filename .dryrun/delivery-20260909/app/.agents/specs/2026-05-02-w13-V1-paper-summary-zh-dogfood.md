---
title: "W13-V1: paper.summary_zh 真实回填 dogfood（P1 验证）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（操作执行）；claude review + 归档
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w12-6-paper-summary-zh.md
  - .agents/specs/2026-05-02-w13-1-paper-summary-zh-api-fix.md
prd_anchor: docs/Paper-Data-Agent-PRD.md §4.1 + §4.2
---

# W13-V1: paper.summary_zh 真实回填 dogfood（P1 验证）

## 1. Goal

W12-6 已交付 `abstract_translator.py` + `run_paper_summary_zh_backfill.py` + V018 列 + 单测，但**从未跑过真实回填**：

- `find apps/miroflow-agent/logs/data_agents -type d -name "summary_zh*"` 无结果
- git log 无 `data(...summary_zh...)` 归档 commit
- Milvus paper_chunks 当前 embedding 几乎来自 `abstract_clean`（`milvus_backfill.py:156` 优先级链回退）

本 spec：在 `miroflow_test_mock` 与 `miroflow_real` 上各跑一次 `--limit 50` 真实回填，归档 checkpoint，验收：

- LLM 调用走 `resolve_professor_llm_settings("gemma4")`（不硬编码）
- summary_zh 长度分布、token 计数、失败率
- 至少 1 条 paper 在 `/api/domains/papers/{paper_id}` 返回中文摘要（依赖 W13-1 上线）

## 2. Non-goals

- **不**全量回填（先 50 条 small batch 验收 LLM 链路；全量另起）
- **不**改 abstract_translator / backfill 脚本逻辑
- **不**改 4 段式 prompt 结构
- **不**触发 `run_milvus_backfill.py paper`（W13-V 之外的另一个 paper Milvus dogfood spec）

## 3. User-visible behavior

| 环境 | 输入 | 输出 |
|---|---|---|
| `miroflow_test_mock` | `--limit 50 --target test_mock` | 50 条 paper 中含 abstract_clean 非空者 backfill；checkpoint 落 `logs/data_agents/paper/summary_zh_runs/<run_id>.jsonl` |
| `miroflow_real` | `--limit 50 --target real` | 同上；归档到 `docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl` |
| W13-1 上线后 `GET /api/domains/papers/<paper_id>` | 任一已 backfill paper | `summary_zh` 字段非空中文 |

## 4. Operational steps

```bash
cd /home/longxiang/MiroThinker

# 1. 清代理（内网 gemma4）
unset https_proxy HTTPS_PROXY

# 2. 确认 V018 已 upgrade
cd apps/miroflow-agent
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run alembic current  # 期望含 V018
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run alembic current  # 同上

# 3. test_mock dogfood
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run python scripts/run_paper_summary_zh_backfill.py --limit 50 --dry-run=false

# 4. real dogfood
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_paper_summary_zh_backfill.py --limit 50 --dry-run=false

# 5. 归档 checkpoint 到 docs/
mkdir -p docs/source_backfills
cp logs/data_agents/paper/summary_zh_runs/<run_id>.jsonl \
   docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl

# 6. 抽查 5 条 paper 在 admin API（需要 W13-1 已 land）
curl http://localhost:8000/api/domains/papers/<paper_id>
# 期望 summary_zh 非空中文
```

## 5. Validation gates

| 指标 | 阈值 | 验证方式 |
|---|---|---|
| 写入成功率 | ≥ 90%（50 条中 ≥ 45 写入）| jsonl checkpoint 中 `status=written` 占比 |
| 中文比例 | ≥ 95% 字符为中日韩字符 | 正则抽样 5 条 |
| 长度分布 | 200-400 字（abstract_translator §1） | jsonl 中 `summary_zh.length` 分布 |
| 失败原因分布 | LLM timeout / parse error / abstract_clean 空 | 单独列出 |
| Token 总消耗 | 报告即可（无阈值）| llm_profile 客户端的 usage 字段 |
| W13-1 接口可见性 | 抽 5 条 GET 200 + summary_zh 非空 | curl |

不达标处理：

- 写入成功率 < 90% → 检查 LLM endpoint / proxy / token 限额；再跑 1 次
- 中文比例 < 95% → prompt 退化（abstract_translator.py:32-85）；提 W12-6 followup spec
- abstract_clean 空导致 skip ≥ 30% → 检查 V004 paper 表数据完整性（与 W13-V2 paper Milvus dogfood 对齐）

## 6. Affected paths

```
新增（产物）：
  docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl
  docs/solutions/integration-issues/paper-summary-zh-dogfood-2026-05-02.md
    （回填执行结果总结：执行时间 / 写入成功率 / 长度分布 / 5 条样本 / 异常列表）

不修改任何代码（除非发现 bug，需要先报告）
```

## 7. Invariants

- LLM 调用必须经 `resolve_professor_llm_settings("gemma4", include_profile=True)`
- 不能硬编码 api_key / base_url / extra_body（auto-memory 红线）
- `--target test_mock` 与 `--target real` 任一报错都不要 `--force` 穿越（除非用户授权）
- run_id 必须由 runtime 生成（V007 trace；不可 sentinel）
- 跑前必须 `unset https_proxy HTTPS_PROXY`（内网 LLM 不走 proxy）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| 50 条 paper 中 30 条 abstract_clean 空 | 仅 backfill 20 条；归档时显式说明分母 |
| LLM 输出含英文/格式异常 | log warn + skip 该条；不写错误内容 |
| Postgres locked / concurrent backfill 冲突 | 退避 + 单线程跑（脚本默认）|
| Gemma-4 服务不可达 | abort 跑；记 `pipeline_issue` `gemma4_endpoint_down` |

## 9. Done criteria

1. ✅ test_mock + real 各跑 50 条
2. ✅ 写入成功率 ≥ 90%
3. ✅ 归档 checkpoint 到 `docs/source_backfills/`
4. ✅ 写 dogfood report 到 `docs/solutions/integration-issues/`
5. ✅ W13-1 land 后抽 5 条 GET 验证
6. ✅ 数据观察：长度 / 中文比例 / 失败原因
7. ✅ 任何脱离 spec 的发现 → 报告 + 不自行修代码

## 10. Open questions

| 问题 | 默认决策 |
|---|---|
| 50 条够吗？| 够；本批是 LLM 链路 + V018 + W13-1 联调验证；全量另起 |
| test_mock 与 real 分别跑还是只 real？| 都跑（test_mock 有 fixtures，便于回归） |
| 失败 paper 是否 retry？| 否；归档失败原因后单立 |
| `summary_zh` 为单段还是 4 段式？| 单段（W12-6 当前实现；不在本批改 prompt） |
