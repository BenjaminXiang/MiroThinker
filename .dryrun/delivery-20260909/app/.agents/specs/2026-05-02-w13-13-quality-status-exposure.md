---
title: "W13-13: retrieval / chat / admin DTO 暴露 quality_status + filter ready 进检索池"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（接口扩展）
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-6-quality-status-alembic-v019.md
  - .agents/specs/2026-05-02-w13-D2-quality-status-promotion-flow.md
prd_anchor: docs/Data-Agent-Shared-Spec.md §7.2（quality_status='ready' 才进检索池）
---

# W13-13: quality_status exposure + filter ready

## 1. Goal

V019 加列 + W13-D2 promote 流程后，所有 4 域有 quality_status 字段。但当前：

- `apps/miroflow-agent/src/data_agents/service/retrieval.py` 不过滤 quality_status
- `apps/admin-console/backend/api/domains.py` DTO 不暴露
- `apps/admin-console/backend/api/chat.py` 不感知

PRD §7.2 要求"仅 quality_status='ready' 进检索池"。本 spec：

1. retrieval search 加 filter `quality_status='ready'`
2. admin DTO 加 `quality_status` 字段（含 / 不含 都展示给 user）
3. chat evidence metadata 加 quality_status（前端可标 badge）

## 2. Non-goals

- **不**改 4 域 Milvus collection schema（不加 quality_status 列；用 PG join 过滤）
- **不**改 W13-D2 promotion 规则
- **不**做 chat answer prompt 中"已审核 / 未审核"显式标注（独立 UX spec）

## 3. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/service/retrieval.py
    search 完成后用 PG 二次过滤：quality_status='ready' 才进 final_top_k
    （ANN search 仍用 Milvus 全集；过滤在 _row_to_evidence 后）
    配置开关：FILTER_BY_QUALITY_STATUS env (default true，避免突然过滤所有 needs_review 数据)

  apps/admin-console/backend/api/domains.py
    各域 DTO 加 quality_status field
    DOMAIN_SELECT_SQL 都加 col

  apps/miroflow-agent/src/data_agents/service/retrieval.py:_PROFESSOR_OUTPUT_FIELDS, _PAPER_OUTPUT_FIELDS, ...
    加 'quality_status'（如 Milvus 已含；否则 PG join 时拿）

新增测试：
  apps/miroflow-agent/tests/data_agents/service/test_retrieval_quality_filter.py
    - default filter on：only ready 命中
    - FILTER_BY_QUALITY_STATUS=0：所有 needs_review 也命中
    - 4 域分别测
  apps/admin-console/tests/test_data_api_quality_status.py
    - GET /api/domains/professors/{id} 返 quality_status
    - GET /api/domains/companies / papers / patents 同上
```

## 4. Validation

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=... uv run pytest tests/data_agents/service/test_retrieval_quality_filter.py -v

cd ../admin-console
DATABASE_URL_TEST=... uv run pytest tests/test_data_api_quality_status.py -v

# Real curl after W13-D2 promote
curl http://localhost:8088/api/domains/professors/PROF-XXX | jq .quality_status
# 期望：'ready' 或 'needs_review'
```

## 5. Done criteria

1. ✅ retrieval default 过滤 'ready'（chat 仅命中 ready 数据）
2. ✅ FILTER_BY_QUALITY_STATUS=0 env 关闭过滤
3. ✅ admin DTO 4 域都暴露 quality_status
4. ✅ 单测 + chat regression 不退化
5. ✅ ruff 通过

## 6. 顺序

依赖：
- W13-6 V019 已 land（4 域 quality_status 列存在）
- W13-D2 promote 流程（否则全 needs_review，filter on 后 retrieval 全空）
- W13-12 paper/patent identity_status（可选；本 spec 不依赖）

## 7. Stop conditions

- filter on 后 chat 命中急剧下降（W13-D2 未 promote 完）→ 临时 FILTER_BY_QUALITY_STATUS=0
- Milvus 与 PG join 性能差 → 改用 Milvus filter expr（需要 collection schema 加 quality_status；改动大）
