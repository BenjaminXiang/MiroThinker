---
title: "W10-5: get_object / get_related 实装"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 10
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w10-3-retrieval-service-4-domains.md  # retrieve() 已 4 域
prd_anchor: docs/Agentic-RAG-PRD.md §3 RetrievalService get_object/get_related
---

# W10-5: get_object / get_related 实装

## 1. Goal

PRD §3 设计 RetrievalService 含 3 个方法：`retrieve` (W10-3 已成) / `get_object` / `get_related_objects`。当前 W10-3 后 `retrieve` 4 域可用，但 `get_object` / `get_related` 未实装 → C 类型（跨域跳转）handler 无 backend 接口。

**本 spec**：实装两个方法，从 canonical relations 表（professor_paper_link / professor_company_role / professor_patent_link / company_patent_link）SQL JOIN 取数。

## 2. Non-goals

- **不**加 redis cache（user 锁定 SQL 直查）
- **不**改 retrieve()
- **不**做 Milvus 关系搜索
- **不**做 cross-domain 推荐（仅同域 by id 取数 + 直接关系）

## 3. User-visible behavior

| 调用 | 行为 |
|---|---|
| `get_object(domain, object_id)` | 从 canonical 主表读单行；返 dict / None |
| `get_related_objects(domain, object_id, target_domain)` | 从对应 link 表 JOIN 主表读多行 |

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/service/retrieval.py
    RetrievalService 加 get_object / get_related_objects 方法

CREATE / MODIFY:
  apps/miroflow-agent/tests/data_agents/service/test_retrieval_get_object.py
    test_get_professor / test_get_company / test_get_paper / test_get_patent
    test_get_unknown_id_returns_none
  apps/miroflow-agent/tests/data_agents/service/test_retrieval_get_related.py
    test_get_papers_for_professor (via professor_paper_link)
    test_get_companies_for_professor (via professor_company_role)
    test_get_patents_for_company (via company_patent_link)
    ... 等
```

## 5. Interface contracts

```python
class RetrievalService:
    def get_object(
        self,
        *,
        domain: Literal["professor", "paper", "company", "patent"],
        object_id: str,
    ) -> dict | None:
        """SELECT * FROM <domain> WHERE <pk> = %s LIMIT 1.
        Returns row dict (canonical fields) or None if not found.
        Identity-soft-deleted rows (identity_status='inactive') return None."""
        sql_map = {
            "professor": "SELECT ... FROM professor WHERE professor_id = %s",
            "paper": "SELECT ... FROM paper WHERE paper_id = %s",
            "company": "SELECT ... FROM company WHERE company_id = %s AND identity_status='resolved'",
            "patent": "SELECT ... FROM patent WHERE patent_id = %s",
        }
        with self._pg_conn_factory() as conn:
            row = conn.execute(sql_map[domain], (object_id,)).fetchone()
            return dict(row) if row else None

    def get_related_objects(
        self,
        *,
        source_domain: Literal["professor", "paper", "company", "patent"],
        source_id: str,
        target_domain: Literal["professor", "paper", "company", "patent"],
        limit: int = 50,
    ) -> list[dict]:
        """JOIN canonical link table for the (source_domain, target_domain) pair."""
        # routing table — see §6
```

## 6. Routing table

| (source, target) | Link table | SQL |
|---|---|---|
| (professor, paper) | `professor_paper_link` | `WHERE professor_id=%s AND link_status='verified'` |
| (paper, professor) | `professor_paper_link` | `WHERE paper_id=%s AND link_status='verified'` |
| (professor, company) | `professor_company_role` | `WHERE professor_id=%s AND status='active'` |
| (company, professor) | `professor_company_role` | `WHERE company_id=%s AND status='active'` |
| (professor, patent) | `professor_patent_link` | `WHERE professor_id=%s` |
| (patent, professor) | `professor_patent_link` | `WHERE patent_id=%s` |
| (company, patent) | `company_patent_link` | `WHERE company_id=%s` |
| (patent, company) | `company_patent_link` | `WHERE patent_id=%s` |
| (paper, paper) | n/a → 返空 |
| (other unsupported) | 返空 |

每对 (source, target) 实现一个内部 helper `_get_<src>_<tgt>(conn, source_id, limit)`，返主表 join 结果。

## 7. Invariants

- 同 source/target 域（如 professor → professor）: 不支持，返空
- 不存在的 source_id: 返空 list（不 raise）
- target row 软删（identity_status='inactive' / link_status='rejected'）: 过滤
- limit ≤ 200（防大查询；user 锁定 50 default）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| source_domain == target_domain | 返空 list |
| 不支持的 (src, tgt) 对 | 返空 list |
| canonical 主表 JOIN 缺行（孤儿 link） | 跳过该行 |
| limit > 200 | clamp 到 200 |
| object_id 为空 / None | get_object 返 None；get_related 返空 |

## 9. Validation

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/service/test_retrieval_get_object.py \
                tests/data_agents/service/test_retrieval_get_related.py \
                tests/data_agents/service/test_retrieval.py \
                tests/data_agents/service/test_retrieval_company_patent.py \
                -n0 --no-cov -v
```

## 10. Done criteria

1. ✅ get_object 4 域支持 + None handling
2. ✅ get_related 7+ (src,tgt) 对支持（spec §6 表）
3. ✅ 单测覆盖每对 (src,tgt) + soft-delete + limit 边界
4. ✅ 既有 retrieval / search_service tests 不退化

## 11. Stop conditions

- canonical link 表名与 spec §6 不一致（如最近改名）→ 检 V005a/V005b
- limit > 200 已被 retrieve() 强约束 → 复用现有 clamp helper

## 12. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 数据源 | canonical relations 表 SQL JOIN（user 锁定）|
| Cache | 不加 |
| domain hint required | 显式参数 domain（必传） |
| limit default | 50 |
