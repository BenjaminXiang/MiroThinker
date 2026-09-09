---
title: "W12-1 batch E: Company KG plan 005 Phase 1-4 实施"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review + 操作长期 backfill
wave: Wave 12
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
detailed_plan: docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
prd_anchor: docs/Company-Data-Agent-PRD.md §模块二 R3-R5（KG）
---

# W12-1 batch E: Company KG Phase 1-4

## 1. Goal

plan 005 §10 Phase 1-4 的可执行实施。User 锁定 scope（Phase 1-4）+ 数据源（现有 company_news_item + 加 news API connector）。

Phase 1 (Company Canonical + XLSX Reimport)：本 session W10-1+W10-4 已部分覆盖（V014 narrative 字段；公司 1024 行已入）。**剩余**：xlsx reimport + needs_review queue 暂搁置（已有数据足够）。

Phase 2 (News & Event Layer)：**核心新增**。news API connector + signal_event LLM 抽取。

Phase 3 (Professor Canonical)：本 session W11-7 已部分覆盖。**剩余**：plan 005 §6 中 professor schema 完整字段 → 已基本对齐 V003-V010；不动。

Phase 4 (跨域 Resolvers)：W10-5 get_object/get_related 已实装。**剩余**：plan 005 §6 中跨域 verified link promotion rules → 与 V005a/V005b 已对齐；不动。

**本 spec 实际新增工作**：Phase 2 实施（news API connector + signal extraction）+ Phase 4 dedup helpers。

## 2. Sub-slice

### 2.1 W12-1a Phase 2.1 News API connector

新建 tushare（A 股 news）+ cnstock（财经新闻）connector，统一返 NewsRecord(company_id, source_url, title, summary, published_at, raw_text)。

```python
class NewsConnector(Protocol):
    def fetch(self, company_unified_credit_code: str, since: date) -> list[NewsRecord]: ...

class TushareConnector(NewsConnector):
    def __init__(self, api_token: str): ...
class CNStockConnector(NewsConnector):
    def __init__(self, api_token: str): ...
```

User 已确认加 API 依赖；token 通过环境变量 `TUSHARE_TOKEN` / `CNSTOCK_TOKEN`。

### 2.2 W12-1b Phase 2.2 News ingestion pipeline

新脚本 `scripts/run_company_news_ingest.py`：
- 遍历 company（按 priority：top 200 weekly / others monthly）
- 调 connector → dedup by source_url → 写 company_news_item
- run_id wiring (W9-2 phase 2 已锁)

### 2.3 W12-1c Phase 2.3 Signal event extraction (LLM)

新 module `signal_event_extractor.py`：
- 用 Gemma-4 local LLM 从 company_news_item 抽取 event_type / event_date / event_summary / dedup_key
- event_type 枚举（融资 / 并购 / 产品发布 / 上市 / 高管变动 / ...）
- 写入 company_signal_event 表（V002 已有 schema）
- dedup by (company_id, event_type, event_date) hash

### 2.4 W12-1d Phase 4 Dedup helpers

新 module `entity_dedup.py`：
- 公司 alias 模糊匹配（normalize_name + Jaccard）
- signal_event dedup_key 计算 + reasoning
- 不改 canonical schema；仅 helper

## 3. Non-goals

- **不**做 plan 005 Phase 5-6（Retrieval Planner / Admin Console v2）
- **不**重新爬 xlsx 现有公司
- **不**做实时新闻（日级 / 周级即可）
- **不**做跨语言 alias resolution
- **不**做 Phase 7 reasoning（推理图）

## 4. User-visible behavior

| 用户面 | 行为 |
|---|---|
| `company_news_item` 表 | 新增 30+ 条/公司 by 日级抓取 |
| `company_signal_event` | LLM 抽取出"融资 X 万 / 上市新三板"等事件 |
| C 类型 chat："这家公司最近有什么新闻" | 走 RetrievalService + canonical relations 命中 |
| Dashboard 公司详情卡 | 显示新闻流 + 事件时间线 |

## 5. Affected paths（汇总）

```
新增：
  apps/miroflow-agent/src/data_agents/company/news_connectors/
    __init__.py
    base.py (NewsConnector Protocol)
    tushare.py
    cnstock.py
  apps/miroflow-agent/src/data_agents/company/signal_event_extractor.py
  apps/miroflow-agent/src/data_agents/company/entity_dedup.py
  apps/miroflow-agent/scripts/run_company_news_ingest.py
  apps/miroflow-agent/scripts/run_company_signal_extract.py

新增 tests:
  apps/miroflow-agent/tests/data_agents/company/test_news_connectors.py
  apps/miroflow-agent/tests/data_agents/company/test_signal_event_extractor.py
  apps/miroflow-agent/tests/data_agents/company/test_entity_dedup.py
  apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py
  apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py

不动 schema：V002 已有 company_news_item / company_signal_event 表；不加 alembic
```

## 6. Critical decisions（user 已锁）

- Scope = Phase 1-4（Phase 1 + 3 + 4 大部分已 done；本 spec 重点 Phase 2 + Phase 4 dedup helpers）
- 数据源 = 现有 company_news_item + 加 tushare/cnstock connector
- LLM = Gemma-4 local（与 W11-7 / W10-4 一致）
- 不改 V002 schema（company_news_item / company_signal_event 已 schema 完整）

## 7. Invariants

- News dedup by source_url（不重复）
- Signal event dedup by (company_id, event_type, event_date)
- API token 缺失 → connector skip + log（不挂）
- run_id required (W9-2 phase 2 已锁)
- Tushare API 限频；ingest 脚本须 sleep 1-2 sec/call

## 8. Validation

```bash
cd apps/miroflow-agent

# Connector + extractor + dedup 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/company/test_news_connectors.py \
                tests/data_agents/company/test_signal_event_extractor.py \
                tests/data_agents/company/test_entity_dedup.py \
                tests/scripts/test_run_company_news_ingest.py \
                tests/scripts/test_run_company_signal_extract.py \
                -n0 --no-cov -v

# 既有不退化
uv run pytest tests/data_agents/company/ -n0 --no-cov

# 操作 backfill (claude，需 token)
TUSHARE_TOKEN=... DATABASE_URL=... \
  uv run python scripts/run_company_news_ingest.py --priority top200 --since 2026-04-01
DATABASE_URL=... \
  uv run python scripts/run_company_signal_extract.py --since 2026-04-01
```

## 9. Done criteria

1. ✅ 2 connectors 单测过（mock API response）
2. ✅ signal_event_extractor 单测过（mock LLM）
3. ✅ entity_dedup 单测过
4. ✅ ingest / extract 脚本单测过；--dry-run 无错
5. ✅ ruff pass；既有 company tests 不退化
6. ✅ claude 操作 top 200 公司 1 周内 news + event 抽取（backfill 量化）

## 10. Stop conditions

- Tushare / CNStock API 不可达 → 暂用 fixture mock；spec 仍可单测全过
- LLM JSON 输出不稳 → fallback 拆 2 prompt（per-event）
- company_news_item 表已用了别名 schema → check V002（spec 已确认 schema 完整）

## 11. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| Scope | Phase 1-4（实质新增 = Phase 2 + dedup） |
| 数据源 | tushare + cnstock + 现有 company_news_item |
| LLM | Gemma-4 local |
| API token | 环境变量 TUSHARE_TOKEN / CNSTOCK_TOKEN |
| Schema 变更 | 无（V002 已 ready） |
| 抓取频率 | top 200 daily / others weekly（claude 操作策略） |
