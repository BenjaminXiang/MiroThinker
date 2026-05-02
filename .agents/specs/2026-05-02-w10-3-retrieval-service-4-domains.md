---
title: "W10-3: RetrievalService 4 域全覆盖"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 10
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w10-1-company-milvus.md
  - .agents/specs/2026-05-02-w10-2-patent-milvus.md
prd_anchor: docs/Agentic-RAG-PRD.md §3 RetrievalService
---

# W10-3: RetrievalService 4 域全覆盖

## 1. Goal

W10-1+W10-2 已建 company_profiles / patent_profiles Milvus collections。但 `RetrievalService` 只支持 `professor` + `paper` 域 query。本 spec 扩展到 4 域。

## 2. Non-goals

- **不**改 RetrievalService 公开接口（`retrieve(query, domain, limit, filters)` 不变）
- **不**做 cross-domain ranking（W10-5）
- **不**做 cache 调优

## 3. User-visible behavior

| 调用 | 行为 |
|---|---|
| `retrieve(query, domain="company")` | 命中 company_profiles → Evidence list |
| `retrieve(query, domain="patent")` | 命中 patent_profiles → Evidence list |
| `retrieve(query, domain="professor"/"paper")` | 不变 |

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/service/retrieval.py
    + 加 COMPANY_OUTPUT_FIELDS / PATENT_OUTPUT_FIELDS
    + _domain_search_config 加 company / patent 分支
    + _row_to_evidence 加 company / patent 映射

CREATE / MODIFY:
  apps/miroflow-agent/tests/data_agents/service/test_retrieval_company_patent.py
    test_retrieve_company / test_retrieve_patent / fallback / metadata
```

## 5. Interface

### 5.1 新 OUTPUT_FIELDS

```python
_COMPANY_OUTPUT_FIELDS = ["id", "name", "industry", "hq_city",
                         "description", "profile_summary",
                         "technology_route_summary"]
_PATENT_OUTPUT_FIELDS = ["id", "patent_number", "title",
                        "abstract", "technology_effect",
                        "patent_type", "ipc_codes"]
```

### 5.2 _row_to_evidence 扩展

```python
if domain == "company":
    object_id = str(entity.get("id") or "")
    name = str(entity.get("name") or "")
    snippet = str(entity.get("profile_summary") or
                  entity.get("technology_route_summary") or
                  entity.get("description") or
                  name)[:500]
    return Evidence(
        object_type="company",
        object_id=object_id,
        score=raw_score,
        snippet=snippet,
        source_url=None,
        metadata=dict(entity),
    )

if domain == "patent":
    object_id = str(entity.get("id") or "")
    snippet = (str(entity.get("title") or "") + "\n" +
               str(entity.get("abstract") or "")[:500])
    return Evidence(
        object_type="patent",
        object_id=object_id,
        score=raw_score,
        snippet=snippet,
        source_url=None,
        metadata=dict(entity),
    )
```

## 6. Invariants

- Evidence.object_type 取值 4 域名
- 现有 professor / paper 行为不变
- 现有 test_retrieval.py / test_search_service.py 全过

## 7. Tests

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/service/test_retrieval_company_patent.py \
                tests/data_agents/service/test_retrieval.py \
                -n0 --no-cov -v
```

## 8. Done criteria

1. ✅ 4 域 retrieve() 都返回 Evidence list
2. ✅ 4+ 新单测过
3. ✅ 既有 retrieval / search_service tests 不退化

## 9. Stop conditions

- Evidence schema 不接受 company/patent object_type → 改 schema 或扩 Literal
- Milvus collection 不存在时 retrieve 不应 raise（log + 返空）

## 10. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| score normalization 改？ | 不改 |
| filters 跨 4 域？ | 现有通用 metadata key/value 过滤即可；company hq_city / patent patent_type 自动支持 |
