---
title: "W9-1 slice 1 — V012 schema + openalex_metrics + canonical_writer"
date: 2026-04-30
owner: codex
spec: .agents/specs/2026-04-30-w9-1-prof-academic-metrics.md
slice: 1 of 3
status: ready
---

# Slice 1 scope

仅 schema 层 + metrics fetcher + writer 写入逻辑 + 单测。**不**做：回填执行、pipeline_v3 集成、admin API 变更、Milvus schema 变更。这些是 slice 2 / 3。

## Read order（按 CLAUDE.md §3）

1. **本 handoff**（你正在读的文件）— slice 范围与 do-not 规则
2. **`.agents/specs/2026-04-30-w9-1-prof-academic-metrics.md`** — 完整设计契约；§6.1 / §6.2 / §6.3 / §6.4 给出代码骨架
3. `apps/miroflow-agent/alembic/versions/V011_add_rag_tables.py` — V012 的写法模板
4. `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py:1-50` — 现有 imports / 结构
5. `apps/miroflow-agent/src/data_agents/professor/author_id_picker.py` — OpenAlex 客户端复用模式
6. `apps/miroflow-agent/src/data_agents/canonical/professor.py` — Professor BaseModel 现状

## Files

**CREATE**：
- `apps/miroflow-agent/alembic/versions/V012_add_professor_metrics.py`（约 30 行）
- `apps/miroflow-agent/src/data_agents/professor/openalex_metrics.py`（约 100 行）
- `apps/miroflow-agent/tests/storage/test_v012_migration.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_openalex_metrics.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_canonical_writer_metrics.py`

**MODIFY**：
- `apps/miroflow-agent/src/data_agents/canonical/professor.py`
  - Professor BaseModel 末尾追加 5 字段（spec §6.2 给出代码）
- `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py`
  - 新增 `upsert_professor_metrics` 函数（spec §6.4 给出代码）

## Do-not rules

- ❌ 不动 `pipeline_v3.py` —— slice 2 处理
- ❌ 不动 `apps/admin-console/backend/api/data.py` —— slice 3 处理
- ❌ 不动 `storage/milvus_collections.py` 或 `professor/vectorizer.py` —— slice 3 处理
- ❌ 不要对 `miroflow_real` 跑 `alembic upgrade`（只对 `DATABASE_URL_TEST` 跑）
- ❌ 不要删 `EnrichedProfessorProfile` 的 `source_paper_count` / `official_paper_count`，**只加 deprecated 注释**
- ❌ 不要发明 spec §6.2 之外的 `metrics_source` 枚举值（仅 `"openalex"` / `"verified_link_only"` / `"mixed"` / `None`）
- ❌ 不要单独跑回填脚本（slice 2 的事）
- ❌ 不要触碰 React 前端 / `domains.py` / 其他 admin-console 文件

## Tests / checks

```bash
cd apps/miroflow-agent

# 1. 迁移可双向（先确认 DATABASE_URL_TEST 已设）
DATABASE_URL=$DATABASE_URL_TEST uv run alembic upgrade V012
DATABASE_URL=$DATABASE_URL_TEST uv run alembic downgrade V011
DATABASE_URL=$DATABASE_URL_TEST uv run alembic upgrade V012

# 2. 3 个新 pytest
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/storage/test_v012_migration.py \
  tests/data_agents/professor/test_openalex_metrics.py \
  tests/data_agents/professor/test_canonical_writer_metrics.py \
  -n0 --no-cov

# 3. 回归现有测试不破
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/storage/ tests/data_agents/professor/ \
  -n0 --no-cov

# 4. ORCID audit（顺手跑，提供给 slice 2 评估覆盖率）
DATABASE_URL=$DATABASE_URL uv run python -c "
import psycopg
conn = psycopg.connect('$DATABASE_URL')
total = conn.execute('SELECT count(*) FROM professor').fetchone()[0]
with_orcid = conn.execute('''
  SELECT count(DISTINCT p.professor_id)
  FROM professor p
  WHERE EXISTS (SELECT 1 FROM professor_orcid o WHERE o.professor_id = p.professor_id)
''').fetchone()[0]
print(f'ORCID coverage: {with_orcid}/{total} = {with_orcid*100/total:.1f}%')
"
```

## Done criteria

1. ✅ V012 alembic upgrade + downgrade 双向 clean
2. ✅ Professor BaseModel 加 5 字段后 mypy / pydantic 校验通过；现有调用方不受破坏
3. ✅ `upsert_professor_metrics` 处理 4 种情况（spec §8 edge cases）：
   - OpenAlex match → `metrics_source='openalex'`
   - 仅 verified link 算 paper_count → `metrics_source='verified_link_only'`
   - 混合 → `metrics_source='mixed'`
   - 全部失败 → 保留旧值，不覆盖（不写 NULL）
4. ✅ `openalex_metrics.fetch_metrics` 至少 5 个单测：
   - happy path（返 h_index / cited_by_count / works_count）
   - HTTP timeout
   - 5xx
   - 404（作者不存在）
   - 限速 429（带 retry）
5. ✅ paper_count 计算 SQL 与 spec §7 invariant 1 严格一致：`COUNT(*) FROM professor_paper_link WHERE professor_id = ? AND link_status = 'verified'`
6. ✅ 全部 6 类不变量（spec §7）在测试中显式断言

## Report back（slice 完成时）

按 AGENTS.md §9 reporting format：

```text
Summary:
- <what changed in 1-2 lines>

Changed files:
- <path>: <reason>
- <path>: <reason>

Verification:
- alembic upgrade V012 — <pass/fail + 输出>
- alembic downgrade V011 → V012 — <pass/fail>
- pytest tests/storage/test_v012_migration.py — <N passed>
- pytest tests/data_agents/professor/test_openalex_metrics.py — <N passed>
- pytest tests/data_agents/professor/test_canonical_writer_metrics.py — <N passed>
- ORCID coverage audit — <N/M = X%>

Risks / notes:
- <任何与 spec 偏离的地方，必须显式说明原因>
- <ORCID 覆盖率结论，给 slice 2 评估>
- <发现的次要 issue（非本 slice 范围）记 pipeline_issue 或 follow-up todo>
```

## Stop conditions（按 AGENTS.md §10）

如果遇到以下情形，停下来 escalate 给 claude review，**不要自决**：

- spec §6 的 schema 与现有 canonical/professor.py 有冲突（如字段名重复）
- V011 在 `DATABASE_URL_TEST` 上未应用，导致 V012 无法干净 upgrade
- `professor_orcid` 表不存在或 schema 与 V011 不符
- OpenAlex API 完全不可达（影响 slice 2 但不阻塞 slice 1 单测，因为单测应 mock）
- 任何超出 5 个文件创建 + 2 个文件修改的额外 churn

## 完成后

报告附在你的 commit 之前；commit 信息按 AGENTS.md §9 风格。slice 1 通过 claude review 后再启动 slice 2。
