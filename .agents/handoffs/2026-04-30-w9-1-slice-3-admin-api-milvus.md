---
title: "W9-1 slice 3: admin API + Milvus + chat profile + browse.html"
date: 2026-04-30
owner: codex
spec: .agents/specs/2026-04-30-w9-1-prof-academic-metrics.md
slice: 3 of 3
status: ready (pending slice 2 完成)
prereq: slice 2 已 commit (ORCID + metrics 回填 + pipeline_v3 集成完成)
---

# W9-1 slice 3: admin API + Milvus + chat profile + browse.html

把 slice 1+2 已写入 Postgres 的 metrics（h_index / citation_count / paper_count）暴露到 4 处用户面：data.py / chat.py / browse.html / Milvus collection。

## CRITICAL — codex CLI proxy

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

## Read order

1. **本 handoff**
2. spec `.agents/specs/2026-04-30-w9-1-prof-academic-metrics.md` §6.5 / §6.6 / §6.7
3. slice 1 commit `310a2bd` 与 slice 2 commits — 看 metrics 字段在 Postgres 怎么 schema
4. `apps/admin-console/backend/api/data.py:379-460`（PROFESSOR_LIST_SELECT_SQL）+ `:1167-1199`（list_professors）
5. `apps/admin-console/backend/api/chat.py` 教授 profile 拼装（Pattern A 与 B 命中后的 core_facts 构造）
6. `apps/admin-console/backend/static/browse.html:780-795` COLUMNS.professors
7. `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py` PROFESSOR_PROFILES_COLLECTION
8. `apps/miroflow-agent/src/data_agents/professor/vectorizer.py` vectorize_professor

## Files

**MODIFY**:
- `apps/admin-console/backend/api/data.py`
  - `ProfessorListItem` Pydantic 加 3 字段 + `metrics_computed_at`
  - `PROFESSOR_LIST_SELECT_SQL` 加 5 列 (`p.h_index`, `p.citation_count`, `p.paper_count`, `p.metrics_computed_at`, `p.metrics_source`)
  - **删除** `LEFT JOIN LATERAL (...) verified_link_counts` + 把 `verified_paper_count` 字段从 ProfessorListItem 移除（spec §13 决定）
  - `_list_professors` 函数：`has_verified_papers` filter 改用 `p.paper_count`
  - `ProfessorDetailResponse.professor` (CanonicalProfessor) 已带 5 字段（slice 1 已加），自动暴露

- `apps/admin-console/backend/api/chat.py`
  - 教授 profile 卡片 `core_facts` dict 加 3 字段（grep "core_facts" 找拼装位置）

- `apps/admin-console/backend/static/browse.html`
  - COLUMNS.professors 加 3 列：H-index / 引用 / 论文数
  - 模仿现有 `verified_paper_count` 列定义；render 函数处理 NULL → "—"

- `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py`
  - `professor_profiles` collection schema 末尾加 3 metadata 字段：
    - h_index Int32 nullable
    - citation_count Int64 nullable
    - paper_count Int32 nullable

- `apps/miroflow-agent/src/data_agents/professor/vectorizer.py`
  - `vectorize_professor()` 在 Milvus insert 时把 3 字段填进 entity metadata
  - 从 EnrichedProfessorProfile 取（slice 1 已有）或从 Postgres `professor` 表取

**EXECUTE (运维)**:
- 跑 `scripts/run_milvus_backfill.py --collection professor_profiles --rebuild`
  全量重建 collection（约 5-10 分钟，775 教授）

**CREATE**:
- `apps/admin-console/tests/test_data_api_metrics.py`
  - 测 ProfessorListItem 含 3 字段
  - 测 list 路径 SQL 包含 metrics 列
  - 测 detail 路径含 metrics
  - 测删了 verified_paper_count 后 has_verified_papers filter 仍工作

- `apps/miroflow-agent/tests/data_agents/professor/test_vectorizer_metrics.py`
  - mock Milvus client + EnrichedProfessorProfile
  - 测 metadata 含 3 字段（None / 有值都测）

## NOT in scope

- domains.py 切 Postgres（W10-6.1 范围）
- 用户端 React UI（仍走 SQLite store；W10-6.1 修复）
- ProfessorListItem 与 domains.py 的 ReleasedObject 同步 — W10-6.1 处理
- 任何 frontend/src/ 改动

## Do-not rules

- ❌ 不动 frontend/src/ — React UI 不应 break
- ❌ 不删除 SqliteReleasedObjectStore（W10-6.5）
- ❌ Milvus rebuild 必须先 dry-run 看 schema diff 再 --rebuild
- ❌ chat profile 加字段时**不可破坏**现有 core_facts schema（只追加，不重命名）
- ❌ browse.html 列定义模仿现有风格；不引入新依赖

## Tests / checks

```bash
cd apps/admin-console
uv run pytest tests/test_data_api_metrics.py -n0 --no-cov
uv run pytest tests/ -n0 --no-cov  # 现有不退化

cd ../miroflow-agent
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/data_agents/professor/test_vectorizer_metrics.py \
  -n0 --no-cov

# 烟测 admin API
curl -s "http://localhost:8088/api/data/professors?page=1&page_size=2" | jq '.items[0] | keys'
# 期望：含 h_index / citation_count / paper_count / metrics_computed_at

curl -s "http://localhost:8088/api/data/professors/PROF-XXXXXXXXXXXX" | jq '.professor | {h_index, citation_count, paper_count, metrics_source}'
# 期望：3 字段不空（如该教授有 ORCID 匹配）

# 烟测 chat profile
curl -s -X POST "http://localhost:8088/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "介绍清华的丁文伯"}' | jq '.structured_payload.core_facts | {h_index, citation_count, paper_count}'

# Milvus 重建后验证 schema
DATABASE_URL=$DATABASE_URL uv run python -c "
from src.data_agents.storage.milvus_collections import PROFESSOR_PROFILES_COLLECTION
from pymilvus import Collection, connections
connections.connect(uri='./milvus.db')
c = Collection(PROFESSOR_PROFILES_COLLECTION)
fields = [f.name for f in c.schema.fields]
assert 'h_index' in fields, fields
assert 'citation_count' in fields, fields
assert 'paper_count' in fields, fields
print('Milvus schema OK:', fields)
"
```

## Done criteria

1. ✅ data.py ProfessorListItem 含 3 字段 + metrics_computed_at；list / detail 路径都暴露
2. ✅ verified_paper_count 老字段已删；has_verified_papers filter 改用 paper_count
3. ✅ chat profile core_facts 含 3 字段
4. ✅ browse.html 教授 tab 列表显示 3 列
5. ✅ Milvus professor_profiles 重建后 schema 含 3 metadata 字段；至少 100 行实测有非 NULL h_index
6. ✅ 单测全过；现有测试不退化

## Stop conditions

- domains.py / SQLite store 路径意外被影响（应该完全不动）
- React UI（5180）测试不通（应该零改动）
- Milvus 重建破坏现有 collection 数据
- 超出 5 文件创建 + 5 文件修改 churn

## Report

按 AGENTS.md §9：

```
Summary: data.py + chat.py + browse.html + Milvus + vectorizer 把 metrics 暴露到用户面
Changed files: ...
Verification:
- pytest test_data_api_metrics.py: N passed
- pytest test_vectorizer_metrics.py: N passed
- 现有 admin-console tests: N passed
- API 烟测: data.py list 含 3 字段, detail 含 metrics_source
- chat profile 烟测: 3 字段返回
- Milvus rebuild: 5-10 min, schema 含 h_index/citation_count/paper_count
Risks/notes:
- <ReleasedObject 与 ProfessorListItem schema 不同步（W10-6.1 修）>
- <实测 h_index/citation 非空率（取决于 ORCID 覆盖率）>
```
