---
title: "W10-6.1: domains.py 6 handler 切 Postgres（方案 B）"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-04-30-w10-6-1-domains-py-postgres.md
slice: 1+2 of 6
status: ready
---

# W10-6.1 handoff（拆 2 sub-slice）

## CRITICAL — codex CLI proxy

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

沙箱限制：不要 git commit；claude 后续 commit。

## Read order

1. **本 handoff**
2. `.agents/specs/2026-04-30-w10-6-1-domains-py-postgres.md` 完整契约（§6 接口 / §7 不变量 / §8 边界 / §10 验证命令）
3. `.agents/specs/2026-04-30-admin-console-architecture.md` §5（端点存储 inventory）
4. `apps/admin-console/backend/api/data.py` 现有 SQL 模板（PROFESSOR_LIST_SELECT_SQL etc.）
5. `apps/admin-console/backend/api/domains.py` 现有 6 handler（要重写的）
6. `apps/admin-console/backend/deps.py:30,40-46` `get_store` / `get_sqlite_store`（slice 1 不删）
7. `apps/miroflow-agent/src/data_agents/canonical/{professor,company,paper,patent}.py` 模型字段

## Sub-slice 拆分

### sub-slice 1: GET 路径（list / detail / filters / related）

MODIFY: `apps/admin-console/backend/api/domains.py`
- list_domain (GET /{domain}): 重写为 Postgres SQL，输出保持 `ReleasedObject` shape
- get_domain_object (GET /{domain}/{id}): 同
- get_filter_options (GET /{domain}/filters/{field}): SELECT DISTINCT + LIMIT 1000
- get_related (GET /{domain}/{id}/related): canonical relations 表 JOIN

每域（professor / company / paper / patent）独立 SQL 函数；不复用 data.py 的（保持 domains.py 自包含；data.py 在 W13-8 退役）。

CREATE: `apps/admin-console/tests/test_domains_postgres.py`
- 4 handler × 4 域 = 16 个 GET 测试
- 关键回归：返回 schema 含 ReleasedObject 7 字段
- 一致性：`/api/professor` total === `/api/data/professors` total（同 institution 下）

### sub-slice 2: 写入路径（patch / delete）

MODIFY: `apps/admin-console/backend/api/domains.py`
- update_record (PATCH /{domain}/{id}): UPDATE canonical 表 + UPDATE run_id
- delete_record (DELETE /{domain}/{id}): 软删（identity_status='inactive' 或域等价标记）+ 写 run_id

domains.py 中 `quality_status` 写入逻辑：用 reverse-derive map（spec §6.3 给规则）。

CREATE 测试：写入路径 + 一致性（编辑后 /browse 立即可见）。

## Critical decisions（spec 已锁定，提醒 codex 不要走偏）

- 输出 schema 保持 ReleasedObject（不改 React URL/字段映射）
- DELETE 走软删（identity_status='inactive'）
- filter options 加 LIMIT 1000
- run_id：调用方先 open_pipeline_run(`run_kind='backfill_real'`)；admin 写入用此 run_id

## Do-not

- ❌ 不动 `frontend/src/`
- ❌ 不删 `SqliteReleasedObjectStore`（W10-6.5 才删）
- ❌ 不动 `data.py` / `chat.py`（与 W9-1 slice 3 / 后续 W11 不冲突）
- ❌ 不要触碰其他 backend/api/* 模块
- ❌ 不要 git commit

## Tests / checks

```bash
cd apps/admin-console
uv run pytest tests/test_domains_postgres.py
uv run pytest tests/  # 现有不退化（注意 test_batch.py 历史 timeout，可 -k 跳）

# 一致性回归（spec §10）
TOTAL_DOMAINS=$(curl -s "http://localhost:8088/api/professor?filters=%7B%22institution%22%3A%22%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E6%B7%B1%E5%9C%B3%E5%9B%BD%E9%99%85%E7%A0%94%E7%A9%B6%E7%94%9F%E9%99%A2%22%7D" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("total"))')
TOTAL_DATA=$(curl -s "http://localhost:8088/api/data/professors?institution=%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E6%B7%B1%E5%9C%B3%E5%9B%BD%E9%99%85%E7%A0%94%E7%A9%B6%E7%94%9F%E9%99%A2" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("total"))')
[ "$TOTAL_DOMAINS" = "$TOTAL_DATA" ] && echo "PASS: $TOTAL_DOMAINS" || echo "FAIL: $TOTAL_DOMAINS != $TOTAL_DATA"
# 期望: 二者同（不再是 4 vs 249）
```

## Done criteria

1. 6 handler 全部走 Postgres
2. 单测全过；现有 admin-console 测试不退化
3. 一致性回归 PASS
4. React DomainList 测试连通（前端代码不动）
5. 写入：PATCH 后 `/browse` 与 React 同时可见

## Stop conditions

- 一致性回归 fail（数字仍 4 vs 249）
- frontend/src/ 被意外修改
- SqliteReleasedObjectStore 被误删
- 超出 2 文件修改 + 1 文件新建 churn

## Report

```
Summary:
Changed files:
Verification:
- pytest test_domains_postgres.py: N passed
- 现有 admin-console: N passed/skipped
- 一致性回归: PASS（教授 X / 企业 Y / 论文 Z / 专利 W）
- 写入回归: PATCH OK（before/after 截图或数字对比）
Risks/notes:
```
