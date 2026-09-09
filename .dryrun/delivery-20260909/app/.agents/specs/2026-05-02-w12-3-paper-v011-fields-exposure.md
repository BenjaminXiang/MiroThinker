---
title: "W12-3: paper V011 字段暴露（pdf_url + 详情扩展）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 12
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor: docs/Paper-Data-Agent-PRD.md §模块三 R5
---

# W12-3: paper V011 字段暴露

## 1. Goal

V011 已加 `paper_full_text` (pdf_url, abstract, intro, ...) + `paper_title_resolution_cache` (title_sha1, match_source, match_confidence)。当前 admin-console `/api/data/papers` 完全不暴露这些字段 → 用户看不到 PDF 链接，运维看不到 cache 命中。

**本 spec**：
- `pdf_url` 暴露在 `/api/data/papers` 列表 + 详情
- `pdf_sha256` / `source` / `match_source` / `match_confidence` 仅详情

## 2. Non-goals

- **不**改 Postgres schema（V011 已充分）
- **不**改 React DomainList 列定义（domains.py W10-6.1 后会自动透传）
- **不**改 chat.py（不影响 RAG path）

## 3. User-visible behavior

| 端点 | 行为 |
|---|---|
| `GET /api/data/papers` | 列表多 `pdf_url` 字段（NULL if no full_text）|
| `GET /api/data/papers/{id}` | 详情多 `pdf_url` / `pdf_sha256` / `full_text_source` / `title_match_source` / `title_match_confidence` |
| `/browse` papers tab | 列表表头加 "PDF" 列，可点链接打开 PDF |
| React DomainList | 通过 W10-6.1 后的 domains.py 自动包含 |

## 4. Affected paths

```
修改：
  apps/admin-console/backend/api/data.py
    PaperListItem 加 pdf_url
    PaperDetailResponse / PaperDetail 加 5 字段
    PAPER_LIST_SELECT_SQL 加 LEFT JOIN paper_full_text + paper_title_resolution_cache
    PAPER_DETAIL_SELECT_SQL 同
  apps/admin-console/backend/static/browse.html
    paper tab COLUMNS 加 pdf_url 列定义（render link）
  apps/admin-console/backend/api/domains.py（仅 paper detail handler）
    返回结构含新字段（W10-6.1 已切 Postgres SQL）

CREATE / MODIFY:
  apps/admin-console/tests/test_data_api.py
    test_paper_list_includes_pdf_url
    test_paper_detail_includes_full_text_metadata
    既有 paper test 同步对齐
```

## 5. Schema 联接

```sql
SELECT p.paper_id, p.title_clean, p.title_raw, p.doi, p.year, p.venue,
       p.citation_count, p.abstract_clean, p.canonical_source,
       pft.pdf_url, pft.pdf_sha256, pft.source AS full_text_source,
       prc.match_source AS title_match_source,
       prc.match_confidence AS title_match_confidence
  FROM paper p
  LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id
  LEFT JOIN paper_title_resolution_cache prc ON prc.title_sha1 = encode(sha1(coalesce(p.title_clean, p.title_raw, '')), 'hex')
  WHERE ...
```

注：`title_sha1` 是 stored value of sha1(title_clean) — 需先确认计算逻辑（W12-3 实施时检 paper.py / paper_title_resolution_cache.py）。如计算复杂，仅在 detail 加这层 JOIN，列表跳过。

## 6. Interface

### 6.1 PaperListItem

```python
class PaperListItem(BaseModel):
    paper_id: str
    title: str
    year: int | None
    venue: str | None
    citation_count: int | None
    canonical_source: str
    pdf_url: str | None  # NEW
    # ... existing fields
```

### 6.2 PaperDetail

```python
class PaperDetail(PaperListItem):
    abstract_clean: str | None
    pdf_sha256: str | None  # NEW
    full_text_source: str | None  # NEW (openalex/arxiv/serper/...)
    title_match_source: str | None  # NEW (openalex/arxiv/...)
    title_match_confidence: float | None  # NEW
    # ... existing
```

## 7. Invariants

- 现有 paper / professor / company / patent endpoints 不退化
- pdf_url NULL when paper_full_text row missing
- title_match_source NULL when cache missing
- React DomainList 通过 W10-6.1 domains.py 透传，无需 React 改动

## 8. Validation

```bash
cd apps/admin-console

uv run pytest tests/test_data_api.py -k paper -v

# 端到端
curl -s "http://localhost:8088/api/data/papers?limit=3" | jq '.[].pdf_url'
curl -s "http://localhost:8088/api/data/papers/PAPER-XXX" | jq '.pdf_url, .full_text_source'
```

## 9. Done criteria

1. ✅ PaperListItem / PaperDetail 多字段
2. ✅ SQL JOIN 联通 paper_full_text + paper_title_resolution_cache
3. ✅ 既有 test 不退化；新 test 过
4. ✅ /browse paper tab 显示 PDF 链接

## 10. Stop conditions

- title_match cache key 计算与 cache 行不一致 → 列表去掉 cache JOIN（仅详情）；spec §5 已留这个 fallback
- 既有 PaperListItem schema 严格不接受 nullable 字段 → 用 Optional[str] 兼容

## 11. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 暴露字段范围 | pdf_url 列表+详情；cache_key/match_source 仅详情 |
| React 入口 | 自动透传 W10-6.1 domains.py（不动 React） |
| 列表 cache JOIN | 详情才 JOIN（spec §5 fallback） |
