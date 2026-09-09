---
title: "W13-8: 实时公司新闻 — Serper-based web search news connector（替代 Tushare/CNStock）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w12-1-company-kg-batch-e.md  # tushare/cnstock 旧设计被本 spec 替换
prd_anchor:
  - docs/Company-Data-Agent-PRD.md §3.2 数据源（新闻页 / PR 稿件 / Web Search）
  - docs/Company-Data-Agent-PRD.md §6.3 监控信号（融资 / 并购 / 产品发布 / 上市 / 高管变动）
context: User 决策 (2026-05-02) — Tushare token 注册积分门槛 + CNStock 闭源接口不适合。核心需求是实时新闻，应走 Serper news search。
---

# W13-8: 实时公司新闻 — Serper-based web search news connector

## 1. Goal

W12-1 commit `5241c9d` 已交付 Tushare + CNStock connector，但用户经评估后决定弃用：

- Tushare：注册需积分、news API 不实时（T+1 财经摘要为主），且对深圳科创公司覆盖不足
- CNStock：闭源 API、不可控、机构对接成本高

核心需求：**实时**（≤ 24h 新鲜度）公司新闻，覆盖融资 / 产品发布 / 上市 / 高管变动 / 并购等事件。

替代方案：复用 M5.2 已实装的 Serper 基础设施（`apps/admin-console/backend/services/web_search_cache.py`），用 `tbm=nws` (news vertical) 拉新闻。

## 2. Non-goals

- **不**删除现有 `tushare.py` / `cnstock.py`（保留作为 deprecated；仅在 `__init__.py` 不导出）
- **不**改 `signal_event_extractor.py`（仍用 Gemma-4 从 NewsRecord 抽事件类型）
- **不**改 `company_news_item` / `company_signal_event` schema
- **不**做 RSS feed / 微信公众号订阅 / Twitter 流（非本期；Serper 一条路径优先）
- **不**实现"近实时" push（webhook / SSE）；本 spec 是 cron pull-based

## 3. User-visible behavior

| 场景 | 行为 |
|---|---|
| chat C "X 公司最近有什么新闻" | 命中 `company_news_item` 含 ≤ 24h 新闻（最近一次 ingest 后）|
| chat / dashboard "X 公司近期事件" | 命中 `company_signal_event` 时间线（融资 X 万 / 高管变动 / 上市）|
| 周 cron 跑 top200 公司 | 每家拉 ≤ 10 条 ≤ 7 天新闻；写 `company_news_item`；触发 `signal_event_extractor` |
| 月 cron 跑 others（≈ 800 公司）| 每家拉 ≤ 5 条 ≤ 30 天新闻 |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py
    class SerperNewsConnector(NewsConnector):
        def __init__(self, api_key: str, *, endpoint, session, timeout): ...
        def fetch(self, company_canonical_name: str, since: date) -> list[NewsRecord]: ...

  apps/miroflow-agent/tests/data_agents/company/test_serper_news_connector.py
    - mock httpx：成功响应解析为 NewsRecord
    - mock httpx：API 5xx 失败 → 返 []
    - mock httpx：API 401 → 抛 SerperAuthError（可识别错误）
    - 时间过滤：since 之前的结果被丢弃
    - dedup by source_url

修改：
  apps/miroflow-agent/src/data_agents/company/news_connectors/__init__.py
    + from .serper import SerperNewsConnector
    （不删 Tushare/CNStock import；只是新增 Serper）

  apps/miroflow-agent/scripts/run_company_news_ingest.py
    _build_connectors:
      新增 "serper" 选项
      "all" 默认仅启用 serper（tushare/cnstock 仅当显式 --connector=tushare/cnstock 时启用）
      新增 SERPER_API_KEY 读取（env or settings.local.json）

  apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py
    新增：选 connector=serper 时仅装 Serper；选 connector=all 默认含 serper
```

## 5. Interface contract

```python
class SerperNewsConnector:
    """Serper.dev news search connector for company news ingest.

    Uses Serper's `/search` endpoint with `type=news` (Google News vertical).
    Each query is the company's canonical_name + a noise-reduction tail.
    """

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://google.serper.dev/news",
        session: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
        result_cap: int = 10,           # serper 默认 10 条/查询
    ) -> None: ...

    def fetch(self, company_canonical_name: str, since: date) -> list[NewsRecord]:
        """Query Google News via Serper, filter by `since`, dedup by URL.

        Query template (中文优先 + 噪声词排除):
            f"{name} (融资 OR 发布 OR 收购 OR 上市 OR 任命 OR 中标) -招聘 -招标公告"

        Time filter via Serper `tbs=qdr:d` (≤ 24h) / `qdr:w` (7d) / `qdr:m` (30d):
            choose based on (today - since).days
        """
```

NewsRecord schema 复用现有 `news_connectors/base.py:NewsRecord`：
- `company_id`（caller 传入；Serper 端不知公司 id）
- `source_url`（Serper `link`）
- `title`（Serper `title`）
- `summary`（Serper `snippet`）
- `published_at`（Serper `date` 解析为 UTC datetime）
- `raw_text`（snippet；如需正文 fetch 留 followup）

LLM / API 调用约束（见 auto-memory）：

```python
import os
api_key = os.environ.get("SERPER_API_KEY", "").strip()
# 不硬编码 endpoint，不写默认 key，不绕 settings
```

## 6. Invariants

- `SERPER_API_KEY` 缺失时连 connector 自身都不构造（与 Tushare/CNStock 保持 skip 风格）
- 同一 source_url 不重复入 `company_news_item`（DB 唯一索引或 ON CONFLICT DO NOTHING）
- `published_at` 必须 ≥ `since`；模糊时间（"2 days ago"）转换 UTC datetime
- 单次查询 ≤ 10 条；rate limit 1 query/sec（与 spec §sleep-seconds 默认一致）
- run_id wiring：`require_real_run_id`（V007 trace 已在）
- 不动 Tushare / CNStock 行为（连接器仍可用，仅默认不启）
- 噪声词列表内置于 connector（不写到外部 yaml）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| 公司名 = 通用词（"光明"）| Serper 噪声 ↑；query 加引号 + "公司"/"科技" 后缀 |
| 同一公司多个 canonical_name 别名 | caller 用主名；别名留下个 follow-up |
| Serper 返回 redirect URL（news.google.com → CMS）| 保留 Serper link（unique 用此），实际 URL 解析留 follow-up |
| `published_at` 缺 | filter date：用 cur fetched_at 兜底；signal_event_extractor 视为"近期" |
| Serper 月配额耗尽 | abort + log；不阻塞 next-ingest |
| 同一新闻多次 query 命中（关键词重叠）| dedup by source_url（同 spec §6 唯一索引）|

## 8. Validation

```bash
cd /home/longxiang/MiroThinker/apps/miroflow-agent

# 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/company/test_serper_news_connector.py \
                tests/scripts/test_run_company_news_ingest.py \
                -n0 --no-cov -v

# 既有 connector tests 不退化
uv run pytest tests/data_agents/company/test_news_connectors.py -n0 --no-cov

# 真实 dogfood（需 SERPER_API_KEY；claude 后续操作）
unset https_proxy HTTPS_PROXY  # serper 在 google.serper.dev，按需保留代理
SERPER_API_KEY=$SERPER_API_KEY \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_company_news_ingest.py \
    --connector=serper --priority=top200 --limit=10
# 期望：≥ 50 NewsRecord 写入；无 raise；source_url 不重复
```

## 9. Done criteria

1. ✅ `SerperNewsConnector` 实现 + 单测覆盖（HTTP 200/4xx/5xx/timeout/dedup/since）
2. ✅ `__init__.py` 导出；`run_company_news_ingest.py` --connector=serper 路径
3. ✅ 既有 Tushare/CNStock 行为不变（仍可手动启用）
4. ✅ ruff 通过

## 10. Operational follow-up（不在本 spec 范围）

- 真实 dogfood 跑 top200（≈ 200 公司 × 1 query × 10 results = 2000 NewsRecord）→ archive jsonl
- signal_event_extractor 真实 dogfood（验 LLM 抽事件类型 / 准确率）
- systemd timer：`run_company_news_ingest.timer`（top200 weekly / others monthly）
- Serper 月配额监控（dashboard）
- 别名 / 模糊公司名解决方案（cuhk-sz "中山大学（深圳）" 多形态）

## 11. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 用 Serper /search type=news 还是单独 google news SDK？| Serper（已实装基础设施 M5.2）|
| query 模板中文 OR 英文？| 中文优先；英文留 follow-up（多数用户用中文 query）|
| 时间过滤 since 还是 Serper qdr 参数？| 双层：Serper qdr 缩小搜索 + 客户端 since 校验 |
| 单次 ≤ 10 条够用吗？| top200 公司 weekly = 10*200=2000/周；signal_extractor LLM 处理 OK |
| 别名怎么解？| 本 spec 不解；caller 用 canonical_name；别名后续 |
| 是否同时去 fetch 正文（避免 snippet 不全）？| 否（Serper snippet 已够 signal_event_extractor LLM 抽取；正文 fetch 后续）|

## 12. Stop conditions

- Serper API 401 / 配额超限 → abort；记 `pipeline_issue` `serper_quota_exceeded`
- 单 query 平均结果 < 3 条（关键词噪声词调整不奏效）→ escalate；prompt 调优
- DB 唯一约束触发率 > 80%（dedup 工作正常但去重后样本极少）→ 频次降低 / 噪声词放宽

## 13. Risks

- Serper 月配额（典型 paid plan 50k queries/月）。weekly top200 = 800 q/月；monthly others = 800 q/月；total ≈ 1600 q/月。低于配额 5%。
- 公司同名（"光明" 集团 vs 食品 vs 物业）→ 关键词加权后仍可能错分；signal_event_extractor 端做去重保险
