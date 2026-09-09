---
title: "W11-4: E 类型科创知识 web search synthesis"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 11
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor: docs/Agentic-RAG-PRD.md §2.1 type E
---

# W11-4: E 类型科创知识 web search synthesis

## 1. Goal

PRD §2.1 E 类型：科创领域知识问答（"什么是 GAN"/"transformer 应用场景"），不在内部 4 域中。当前 chat.py 对 E 类型直接 LLM synthesis，但缺权威外部信号 → 答案可能编造。

**本 spec**：E handler 用 Serper web search 取 top 5 结果作为 evidence，喂给 LLM synthesis；evidence list 顶部标 `[web]` tag。

## 2. Non-goals

- **不**改 retrieval service（E 路径不走 Milvus）
- **不**做 chrome / Playwright 抓页
- **不**改 chat.py 其他 handler

## 3. User-visible behavior

| 场景 | 行为 |
|---|---|
| Q: "什么是 GAN" → E classifier | Serper 搜 → 5 结果 → LLM synthesis 答案 |
| ChatResponse.evidence | top 5 含 `source_type='web'` 标记 |
| 同 query 24h 内重复 | 命中 cache（无 API call）|
| Serper 失败 | fallback 纯 LLM；evidence = []；answer_text 含 "未引用网络搜索" 提示 |

## 4. Affected paths

```
新增：
  apps/admin-console/backend/services/web_search_cache.py
    Postgres cache table（or in-memory LRU；24h TTL）
  apps/admin-console/tests/test_chat_e_web_search.py

修改：
  apps/admin-console/backend/api/chat.py
    E handler 调 web search → 拼 prompt → LLM synthesis
    evidence list 加 web 项

新增（如选 Postgres cache）：
  apps/miroflow-agent/alembic/versions/V017_add_web_search_cache.py
```

## 5. Schema (Postgres cache)

```python
# V017
op.create_table(
    "web_search_cache",
    sa.Column("query_sha1", sa.String(40), primary_key=True),
    sa.Column("query_text", sa.Text, nullable=False),
    sa.Column("results", postgresql.JSONB, nullable=False),
    sa.Column("provider", sa.String(32), nullable=False, server_default="serper"),
    sa.Column("cached_at", sa.DateTime(tz=True), nullable=False, server_default=sa.func.now()),
)
op.create_index("ix_web_search_cache_cached_at", "web_search_cache", ["cached_at"])
```

24h TTL via `cached_at > now() - interval '24 hours'`。

## 6. Interface contracts

```python
class WebSearchCache:
    def __init__(self, dsn: str, *, ttl_seconds: int = 86400) -> None: ...
    
    def get(self, query: str, provider: str = "serper") -> list[dict] | None:
        """SHA1(query) → JSONB results；过期返 None"""
    
    def set(self, query: str, results: list[dict], *, provider: str = "serper") -> None:
        """UPSERT ON CONFLICT (query_sha1)"""

# chat.py E handler
def _handle_e_query(query: str, ...):
    cached = web_cache.get(query)
    if cached is None:
        cached = serper_client.search(query, top_n=5)
        if cached:
            web_cache.set(query, cached)
    if not cached:
        # fallback
        return ChatResponse(answer_text="...纯 LLM...", evidence=[], ...)
    
    evidence = [Evidence(
        source_type="web",
        title=r["title"],
        snippet=r["snippet"],
        url=r["link"],
    ) for r in cached[:5]]
    
    answer = llm_synthesize(query, evidence)
    return ChatResponse(answer_text=answer, evidence=evidence, query_type="E", ...)
```

## 7. Invariants

- Serper 失败 / 0 结果 → fallback 纯 LLM（不挂）
- cache 24h TTL
- evidence list 中 web 项 source_type="web"，与 professor/paper 区分
- 不影响 A/B/C/D/F/G handler

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| Serper 5xx / timeout | 不 cache 失败；fallback LLM；error 计 metric |
| query 含敏感词 (politics) | 现有 F handler 已 reject；E 不到这步 |
| cache 行损坏（手工编辑） | json.JSONDecodeError → 视为 None |
| query 长度 > 1000 chars | trunc 到 1000 后哈希 |
| 未配 SERPER_API_KEY | startup 时 log + 直接走 fallback path |

## 9. Validation

```bash
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest apps/admin-console/tests/test_chat_e_web_search.py -v

# Serper 可达时端到端（claude 操作）
SERPER_API_KEY=... uv run python -c "
from backend.api.chat import _handle_e_query
print(_handle_e_query('什么是 GAN'))
"
```

## 10. Done criteria

1. ✅ V017 + WebSearchCache CRUD
2. ✅ E handler 调 Serper + cache + fallback
3. ✅ 单测 (cached / cold / Serper down / fallback) 全过
4. ✅ 既有 chat tests 不退化

## 11. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| Provider | Serper |
| Caching | per-query 24h |
| Cache 存储 | Postgres web_search_cache (V017) |
| evidence source_type | "web" |
