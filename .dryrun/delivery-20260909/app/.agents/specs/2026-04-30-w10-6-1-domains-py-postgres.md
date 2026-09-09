---
title: "W10-6.1: domains.py 6 handler 从 SQLite 切到 Postgres"
date: 2026-04-30
owner: claude
status: ready-for-codex
audience: codex
wave: Wave 10
gap: "#25, #30, #31"
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_spec: .agents/specs/2026-04-30-admin-console-architecture.md
architecture_decision: 方案 B (改后端 domains.py 内部切 Postgres，前端 URL 不变)
---

# W10-6.1: domains.py 6 handler 从 SQLite 切到 Postgres

## 1. Goal

`apps/admin-console/backend/api/domains.py` 6 个路由（`/api/{domain}` 全套：list / detail / filters / patch / delete / related）当前走 `SqliteReleasedObjectStore`，与 canonical Postgres `miroflow_real` 严重脱钩——同一查询 4 vs 249 教授差距已实测。

按 W10-6.0 决定的方案 B：改后端不改前端。把 6 handler 改为对 Postgres canonical 表查询/写入，输出 schema 保持现有 `ReleasedObject`，React 零改动。

完成后：
- React DomainList / RecordDetail 立即看到 canonical 数据（教授 775、企业 1024、论文 7297）
- React 编辑/删除/批量操作直接对 canonical 表生效
- 上传/导出 (W10-6.2/6.3 / 6.4) 后续切

## 2. Non-goals

- **不**动 React 前端代码（fetchDomainList 等 URL 不变）
- **不**重写 data.py 的 11 路由（那是 /browse 用的）
- **不**改 ReleasedObject Pydantic shape（`id` / `display_name` / `core_facts` / `summary_fields` / `evidence` / `last_updated` / `quality_status`）
- **不**做 SQLite store 物理删除（W10-6.5）；本 slice 仅切流量
- **不**做 batch.py / export.py / upload.py（W10-6.2-4）

## 3. User-visible behavior

- React `/domain/professor` 看到 ~775 行（vs 当前 19 行）
- 清华深研院 filter 后看到 ~249 行（vs 当前 4 行）
- React 上的 quality 标记 / 删除立即在 `/browse` 也可见
- API URL 不变（`/api/{domain}`、`/api/{domain}/{id}` 等）
- 输出 JSON 结构不变（前端无需适配）

## 4. Affected paths

```
MODIFY:
  apps/admin-console/backend/api/domains.py  (6 handlers 重写)
  apps/admin-console/backend/deps.py
    + 移除 get_store / get_sqlite_store 的依赖；保留 get_pg_conn（已有）
    + 注：sqlite_store.py 文件**不删**（W10-6.5 才删）

  apps/admin-console/tests/test_data_api.py（如有 SQLite-specific assert，更新为 Postgres）

CREATE:
  apps/admin-console/tests/test_domains_postgres.py
    + 6 个新 handler 各 2-3 个测试（list / detail / filters / patch / delete / related）

引用但不改:
  apps/admin-console/backend/api/data.py — 复用 PROFESSOR_LIST_SELECT_SQL / 类似
    SQL 模板（**不直接 import**，复制需要的 SQL 片段；保持 domains.py 自包含）
  src/data_agents/canonical/{professor,company,paper,patent}.py — 读模型字段

NOT MODIFY:
  apps/admin-console/frontend/src/  (React 零改动)
  apps/miroflow-agent/src/data_agents/storage/sqlite_store.py  (保留至 W10-6.5)
```

## 5. Architecture / Data flow

```
React DomainList → fetch /api/professor?filters=JSON
                          ↓
       domains.py:48 list_domain(domain, q, page, ...)
                          ↓
      [新] _list_from_postgres(conn, domain, ...)
            ↓
       SELECT FROM professor / company / paper / patent
       LATERAL JOIN ... (类似 data.py 的 PROFESSOR_LIST_SELECT_SQL)
            ↓
       _row_to_released_object(row)
            ↓
       PaginatedResponse(items=[ReleasedObject, ...], total, page, page_size)
                          ↓
                  React 渲染（无变化）
```

## 6. Interface contracts

### 6.1 输出 ReleasedObject 兼容

每域行 → ReleasedObject 转换规则：

**professor**:
```python
{
  "id": row["professor_id"],          # PROF-XXXX
  "object_type": "professor",
  "display_name": row["canonical_name"],
  "core_facts": {
    "name": row["canonical_name"],
    "name_en": row["canonical_name_en"],
    "name_zh": row["canonical_name_zh"],
    "institution": row["primary_affiliation_institution"],  # LATERAL JOIN
    "department": row["primary_affiliation_department"],
    "title": row["primary_affiliation_title"],
    "discipline_family": row["discipline_family"],
    "h_index": row["h_index"],         # W9-1 之后可填
    "citation_count": row["citation_count"],
    "paper_count": row["paper_count"],
    "research_topic_count": row["research_topic_count"],
    "verified_paper_count": row["paper_count"],  # 同义；保留 backward compat
  },
  "summary_fields": {
    "profile_summary": row["profile_summary"],
  },
  "evidence": [],  # 默认空 list；详情 endpoint 才填
  "last_updated": row["last_refreshed_at"].isoformat(),
  "quality_status": _derive_quality_status(row),
}
```

`_derive_quality_status` 规则（与 SQLite store 之前的标签对齐）：
- `identity_status = 'merged'` → `"merged"`
- `identity_status = 'inactive'` → `"inactive"`
- 否则按其他指标 → `"ready"` / `"needs_review"` / `"low_confidence"` / `"needs_enrichment"`（Round 7.x quality_gate 已分类）

**company / paper / patent** 类似映射，本 spec 不全列，codex 实施时按 canonical model 字段 + 现有 data.py SQL 推。

### 6.2 6 handler 签名（保持现状）

```python
@router.get("/{domain}")  # list
@router.get("/{domain}/filters/{field}")  # filter options
@router.get("/{domain}/{object_id}")  # detail
@router.patch("/{domain}/{object_id}")  # update
@router.delete("/{domain}/{object_id}", status_code=204)  # delete
@router.get("/{domain}/{object_id}/related")  # related cross-domain
```

### 6.3 PATCH 写入语义

```python
# 当前 SQLite store: store.update_record(domain, id, core_facts=..., quality_status=...)
# 新: 直接 UPDATE canonical 表 + 标 run_id

UPDATE professor SET
  canonical_name = COALESCE(%(name)s, canonical_name),
  ...
  -- quality_status 的特殊处理:
  -- 其实 Postgres 没有直接的 quality_status 列，是 derived from identity_status + 其他
  -- 用户要 PATCH quality_status='ready' 时，按规则 reverse-map（如更新 identity_status='resolved'）
WHERE professor_id = %(id)s
```

**关键决策**（codex 自决细节）：quality_status 的写入 mapping 由 codex 根据 derive 规则反向推理。

### 6.4 DELETE 语义

```python
# 当前 SQLite store: store.delete(domain, id)
# 新: 软删 canonical 表（identity_status='merged' 或 'deleted'）；不真 DROP

UPDATE professor SET
  identity_status = 'inactive',
  updated_at = now(),
  run_id = %(run_id)s
WHERE professor_id = %(id)s
```

软删保留 audit trail；硬删需要 cascade 到 link 表，风险高。

## 7. Invariants

1. React 零改动；URL + 输出 schema 完全保持
2. 任何 PATCH / DELETE 必须带 run_id（spec W9-2 要求；先用 admin-console 自己生成的 run_id）
3. 输出 ReleasedObject.id 与 canonical 表的 PK 一一对应（PROF-/COMP-/PAPER-/PAT- 前缀）
4. quality_status 必为 4 个 canonical 值或 derive 后的合法 label（`merged`/`inactive` 等）
5. /api/{domain} 与 /api/data/{domain}s 返回的 total（同 filter 下）必须一致（一致性 invariant 在测试中断言）
6. SQLite store 仍可 import（W10-6.5 才删）；本 slice 完成后**没有任何路径**再读 SQLite

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| 域不在 4 个之内（如 `/api/foo`） | DomainEnum 验证；返 422 |
| filters JSON 解析失败 | 422（与现有行为一致） |
| sort_by 不在 allowed 列表 | 422 |
| paper 表中 quality_status 派生未定义 | 用 fallback `"needs_review"` |
| PATCH 更新 deprecated 字段（如 source_paper_count） | 忽略（warn log） |
| filter 用了 SQLite store 时代特有的 key | 422 + 列出 supported keys |

## 9. Failure modes

- Postgres 暂不可达：500 + 友好错误（admin-console 挂时即不可用，无 graceful degradation 到 SQLite）
- SQL 语法错（如 LATERAL JOIN 在 paper / patent 表上需调整）：codex 实施时各域独立测

## 10. Validation commands

```bash
cd apps/admin-console

# 单测
uv run pytest tests/test_domains_postgres.py -n0 --no-cov

# 现有 admin-console 测试不退化
uv run pytest tests/ -n0 --no-cov

# 一致性回归（最重要）：W10-6.6 验收命令
TOTAL_DOMAINS=$(curl -s "http://localhost:8088/api/professor?filters=%7B%22institution%22%3A%22%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E6%B7%B1%E5%9C%B3%E5%9B%BD%E9%99%85%E7%A0%94%E7%A9%B6%E7%94%9F%E9%99%A2%22%7D&page_size=1" | jq '.total')
TOTAL_DATA=$(curl -s "http://localhost:8088/api/data/professors?institution=%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E6%B7%B1%E5%9C%B3%E5%9B%BD%E9%99%85%E7%A0%94%E7%A9%B6%E7%94%9F%E9%99%A2&page_size=1" | jq '.total')
[ "$TOTAL_DOMAINS" = "$TOTAL_DATA" ] && echo "PASS: $TOTAL_DOMAINS" || echo "FAIL: $TOTAL_DOMAINS != $TOTAL_DATA"

# 写入回归
curl -X PATCH "http://localhost:8088/api/professor/PROF-XXXX" \
  -H "Content-Type: application/json" \
  -d '{"quality_status":"ready"}'
curl -s "http://localhost:8088/api/data/professors/PROF-XXXX" | jq '.professor.identity_status'
# 应反映上一步 PATCH 的更改
```

## 11. Slice 拆分

- **slice 1**: list / detail / filters / related（GET 路径，4 handler）
- **slice 2**: patch / delete（写入 / 删除路径，2 handler）+ 一致性回归

写入路径风险更高，独立 slice 便于 review。

## 12. Expected evidence

- ✅ 6 handler 全部走 Postgres，pytest 覆盖
- ✅ 一致性回归 PASS：4 个域的 `/api/{domain}` 与 `/api/data/{domain}s` 返回同 total（同 filter 下）
- ✅ React UI 实测：DomainList 教授数从 19 → 775；清华深研院 4 → 249
- ✅ 写入实测：React PATCH → /browse 可见
- ✅ Shared-Spec / index.md 同步：状态矩阵 React UI 行升级

## 13. Open questions（claude 自决）

- [x] **R1: 是否复用 data.py SQL** → 否，复制片段保持 domains.py 自包含。理由：长期 data.py 会随 /browse 退役（W13-8）；不耦合
- [x] **R2: PATCH 写入 quality_status 是否需 reverse-map**：是。canonical 表无直接列，按 derive 规则反向推
- [x] **R3: DELETE 是软删还是硬删**：软删（identity_status='inactive'）；保留 audit
- [x] **R4: ReleasedObject schema 调整**：保持不变，前端零改
- [x] **R5: filter options 的 SELECT DISTINCT 性能** → 加 explicit LIMIT 1000；不必过度优化（数据量级小）

**所有阻塞 codex 实施的决策已锁定；本 spec 状态：`ready-for-codex`**。

## 14. 与其他 wave 的衔接

- 依赖 W9-1 完成（W9-1 给 professor 加 metrics 列；本 spec 把它们映射到 ReleasedObject.core_facts）
- 协作 W10-6.2/3/4：write/upload 路径在后续 sub-slice 切；本 slice 不动
- W13-8 retiring /browse：本 spec 完成后 data.py 仍在但作 /browse 专属；W13-8 一起删
