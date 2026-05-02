---
title: "W12-6: paper.summary_zh 字段 + 中文翻译 backfill"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review + 操作 backfill
wave: Wave 12
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-7-summary-generator-raw-text.md
  - .agents/specs/2026-05-02-w12-5-multi-source-homepage-crawl.md
prd_anchor: docs/Paper-Data-Agent-PRD.md §模块三 R6
---

# W12-6: paper.summary_zh 字段 + 中文翻译 backfill

## 1. Goal

paper 表 `abstract_clean` 多为英文（OpenAlex / arxiv 主源）。中文用户在 admin-console / chat 中看英文摘要 UX 差。Milvus paper_chunks 也用英文 embed → 中文 query 命中率受限。

**本 spec**：
- V018 加 `paper.summary_zh` 列（Text, nullable）
- 新建 LLM 翻译 backfill 脚本（Gemma-4 local，与 W11-7 一致）
- W11-7 reinforcement 优先用 summary_zh（fallback abstract_clean）
- Milvus paper_chunks 重 embed 用 summary_zh

## 2. Non-goals

- **不**改 paper canonical schema（除新列）
- **不**重新爬 paper 全文
- **不**做实时翻译（仅 backfill）
- **不**翻译 paper.title（独立工作）

## 3. User-visible behavior

| 用户面 | 行为 |
|---|---|
| `/api/data/papers/{id}` 详情 | 多 summary_zh 字段（中文摘要 200-400 字） |
| Milvus paper_chunks search 中文 query | 召回率提升 |
| W11-7 reinforcement | prompt 中 paper context 用中文 abstract |
| `/browse` paper tab | 中文摘要列（可选） |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V018_add_paper_summary_zh.py
  apps/miroflow-agent/src/data_agents/paper/abstract_translator.py
    translate_abstract_to_zh(text, llm_client, llm_model, ...) -> str | None
    _SYSTEM_PROMPT 中文翻译；目标长度 200-400 chars
  apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py
    --only-missing / --limit / --resume / --dry-run
    open/close pipeline_run('backfill_real')

修改：
  apps/miroflow-agent/src/data_agents/canonical/paper.py
    Paper model 加 summary_zh: str | None = None
  apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py
    PaperContext.abstract 优先取 summary_zh，fallback abstract_clean
    （若 caller 已 fetch paper_full_text，可从 query 增 LEFT JOIN paper.summary_zh）
  apps/miroflow-agent/scripts/run_milvus_backfill.py
    paper domain SQL 加 summary_zh；_compose_paper_chunk_text 优先 summary_zh

新增 tests:
  apps/miroflow-agent/tests/data_agents/paper/test_abstract_translator.py
  apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py
  apps/miroflow-agent/tests/storage/test_v018_migration.py
```

## 5. Schema

V018:
```python
op.add_column("paper", sa.Column("summary_zh", sa.Text(), nullable=True))
```

## 6. Translation prompt

```python
_SYSTEM_PROMPT = (
    "你是科技论文中文摘要助手。给定英文学术论文摘要，输出 200-400 字"
    "中文 paraphrase（不直译，提炼核心方法 + 结果 + 应用领域）。\n"
    "规则：\n"
    "- 保持事实准确，不增不减\n"
    "- 中文流畅，避免直译欧化句式\n"
    "- 使用领域术语\n"
    "- 不要 Markdown / bullet\n"
    "- 直接输出中文摘要文本"
)
```

输出 200-400 chars 中文。validator 同 W11-7 reinforcement style：长度 + boilerplate keyword check。

## 7. Invariants

- abstract_clean 为空 → skip（写 jsonl `skipped_no_abstract`）
- abstract_clean 已是中文（zh char ratio > 0.6） → skip
- summary_zh 长度 < 150 / > 500 → reject + 1 retry
- 不破坏 paper.abstract_clean
- run_id required (W9-2 phase 2 已锁)

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| abstract_clean 为空 | skip |
| 已是中文 | skip（避免双语循环）|
| 长度违规 | retry 1 次 |
| LLM 输出含英文 | accept（中英混合也可）|
| arxiv abstract 含 LaTeX | LLM 自处理；不预处理 |
| paper 数量大（10K+ 时） | --limit 控制；resume 支持 |

## 9. Validation

```bash
cd apps/miroflow-agent

# 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/storage/test_v018_migration.py \
                tests/data_agents/paper/test_abstract_translator.py \
                tests/scripts/test_run_paper_summary_zh_backfill.py \
                -n0 --no-cov -v

# 既有不退化
uv run pytest tests/data_agents/paper/ -n0 --no-cov

# 操作 backfill（claude）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run alembic upgrade V018
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_paper_summary_zh_backfill.py --only-missing --limit 10 --dry-run

# Milvus rebuild
uv run python scripts/run_milvus_backfill.py --domain paper --rebuild --milvus-uri ./milvus.db
```

## 10. Done criteria

1. ✅ V018 + abstract_translator 单测过
2. ✅ backfill 单测 + 既有 paper test 不退化
3. ✅ smoke 10 paper claude 操作过
4. ✅ Milvus paper_chunks rebuild 用 summary_zh

## 11. Stop conditions

- 多数 paper abstract 为空 → 早回报；W12-6 rollback；focus W11-7 已 paper-driven
- LLM 中英混合输出比例 > 50% → 强约束 prompt + 单元测试

## 12. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 数据源 | abstract_clean only（不爬 PDF） |
| 字段化 | 加 paper.summary_zh 列（V018） |
| 触发 | 独立 backfill 脚本 |
| LLM provider | Gemma-4 local |
| 长度 | 200-400 chars |
