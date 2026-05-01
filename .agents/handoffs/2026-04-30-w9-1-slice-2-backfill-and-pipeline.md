---
title: "W9-1 slice 2: ORCID prep + metrics backfill + pipeline_v3 集成"
date: 2026-04-30
owner: codex
spec: .agents/specs/2026-04-30-w9-1-prof-academic-metrics.md
slice: 2 of 3
status: ready
prereq: slice 1 已 commit (310a2bd) — V012 + openalex_metrics + canonical_writer.upsert_professor_metrics
---

# W9-1 slice 2: ORCID prep + metrics backfill + pipeline_v3 集成

## CRITICAL — codex CLI 代理

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

**注**：python pipeline 调外部 API 时**必须 unset proxy**（OpenAlex / Serper 直连）；proxy 仅 codex CLI 用。

## Slice 1 完成状态（已确认）

slice 1 commit `310a2bd` 入主线，含 V012 alembic + openalex_metrics + canonical_writer.upsert_professor_metrics + 21 个 pytest（全过）。

**关键 finding**（必须 slice 2 处理）：ORCID 覆盖率 audit 结果 = **0/787 = 0.0%**。
`professor_orcid` 表 V011 已建但从未填。如不先 ORCID backfill，metrics 回填的 h_index/citation_count 几乎全 NULL，仅 paper_count 有值（=verified link 实计数）。

## Slice 2 范围（3 步骤）

### Step A: ORCID 数据预填（运维步骤，无代码改动）

跑现有的 `scripts/run_professor_orcid_backfill.py`：

```bash
cd apps/miroflow-agent
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy
DATABASE_URL=$DATABASE_URL_REAL uv run python scripts/run_professor_orcid_backfill.py --dry-run --limit 5
# 看 dry-run 输出确认它能查到 OpenAlex
DATABASE_URL=$DATABASE_URL_REAL uv run python scripts/run_professor_orcid_backfill.py --limit 50
# 试 50 个，看成功率
DATABASE_URL=$DATABASE_URL_REAL uv run python scripts/run_professor_orcid_backfill.py
# 全量（787 教授，约 30-60 分钟，OpenAlex 0.1s/call rate）
```

完成后再次 audit：
```sql
SELECT count(DISTINCT p.professor_id)
FROM professor p
WHERE EXISTS (SELECT 1 FROM professor_orcid o WHERE o.professor_id = p.professor_id);
```

**目标**：覆盖率 ≥ 50%（OpenAlex 通过 name+institution 匹配，外加 ORCID 字段非空）。如果覆盖率 < 30%，stop & escalate（可能 backfill 脚本本身有 bug）。

### Step B: 创建 metrics 回填脚本

CREATE: `apps/miroflow-agent/scripts/run_professor_metrics_backfill.py`

功能：
- 输入：`miroflow_real` 中所有 `identity_status='resolved'` 教授（W9-1 范围内）
- 对每位：
  1. 取 ORCID（professor_orcid 表）+ 可选 OpenAlex_id
  2. 调 `openalex_metrics.fetch_metrics(orcid=..., openalex_author_id=...)`
  3. 决定 metrics_source:
     - 有 ORCID + OpenAlex 返 source='openalex' → metrics_source='openalex'
     - 无 ORCID 或 fetch 返 unmatched → metrics_source='verified_link_only'
     - 混合（部分字段从 OpenAlex，部分从其他源）→ 'mixed'（slice 2 不需用 'mixed'，留 W12 用）
  4. 调 `canonical_writer.upsert_professor_metrics(...)`
- 支持 `--dry-run` / `--limit N` / `--resume`（按 metrics_computed_at IS NULL 找 todo）
- 每 50 个教授 commit 一次（避免长事务）
- 失败 prof 写 pipeline_issue (issue_type='metrics_fetch_failed')
- 完整输出 JSONL log 到 `docs/source_backfills/professor-metrics-backfill-{今日}.jsonl`

CREATE: `apps/miroflow-agent/tests/scripts/test_run_professor_metrics_backfill.py`
- mock fetch_metrics + DB；测 happy path / no orcid / fetch fail / resume

### Step C: pipeline_v3 集成（stage 11.5）

MODIFY: `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py`

在 stage 11 (Cross-Domain Bidirectional Writes) 后插入 stage 11.5：
- 对当前 V3 run 处理过的每个 professor，调 upsert_professor_metrics
- 用同一个 run_id（pipeline_v3 已有的）
- 不阻塞主流程：metrics 失败时记 pipeline_issue，继续 stage 12 (Vectorization)

## Read order

1. **本 handoff**
2. spec `.agents/specs/2026-04-30-w9-1-prof-academic-metrics.md` §6.4 / §8 / §10
3. `apps/miroflow-agent/scripts/run_professor_orcid_backfill.py` — 看 OpenAlex 调用模式 + idempotent 写入
4. `apps/miroflow-agent/src/data_agents/storage/postgres/professor_orcid.py` — upsert_professor_orcid 接口
5. `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py:1-50` 与 stage 11 的位置
6. slice 1 commit `310a2bd` 的 openalex_metrics.py + canonical_writer.py 改动

## Files

**EXECUTE (operational)**:
- `scripts/run_professor_orcid_backfill.py` 全量跑

**CREATE**:
- `apps/miroflow-agent/scripts/run_professor_metrics_backfill.py` (~150 行)
- `apps/miroflow-agent/tests/scripts/test_run_professor_metrics_backfill.py` (≥ 5 tests)
- `docs/source_backfills/professor-metrics-backfill-{今日}.jsonl` (运行后产出)

**MODIFY**:
- `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py` (加 stage 11.5)

**NOT in scope**:
- admin API data.py（slice 3）
- chat.py / browse.html（slice 3）
- Milvus collection schema（slice 3）

## Do-not rules

- ❌ ORCID backfill 跑 miroflow_real **必须先 dry-run + limit 50** 看成功率，再全量
- ❌ metrics backfill **必须 idempotent**（resume 模式下重复 prof 不重复调 OpenAlex）
- ❌ commit 频率 50 prof/次（不要单事务跑全量，OOM 风险）
- ❌ 不动 Milvus / admin API（slice 3）
- ❌ pipeline_v3 集成里失败时**不可 raise**（不能阻塞主流程）

## Tests / checks

```bash
cd apps/miroflow-agent
export DATABASE_URL_TEST="postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock"

# Step A 后验证 ORCID 覆盖
unset http_proxy https_proxy
DATABASE_URL=$DATABASE_URL uv run python -c "
import psycopg, os
dsn = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
with psycopg.connect(dsn) as conn:
    total = conn.execute('SELECT count(*) FROM professor').fetchone()[0]
    has = conn.execute('SELECT count(DISTINCT professor_id) FROM professor_orcid').fetchone()[0]
    print(f'ORCID coverage: {has}/{total} = {has*100/total:.1f}%')
"

# Step B 单测
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/scripts/test_run_professor_metrics_backfill.py \
  -n0 --no-cov

# Step B dry-run
DATABASE_URL=$DATABASE_URL uv run python scripts/run_professor_metrics_backfill.py --dry-run --limit 5

# Step B 全量回填
DATABASE_URL=$DATABASE_URL uv run python scripts/run_professor_metrics_backfill.py

# 验证：抽样 5 个有 ORCID 的教授看 metrics 已写
DATABASE_URL=$DATABASE_URL uv run python -c "
import psycopg, os
dsn = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
with psycopg.connect(dsn) as conn:
    rows = conn.execute('''
      SELECT professor_id, canonical_name, h_index, citation_count, paper_count, metrics_source
      FROM professor
      WHERE metrics_source = 'openalex'
      LIMIT 5
    ''').fetchall()
    for r in rows: print(r)
"

# Step C 单测（pipeline_v3 stage 11.5 集成）
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/data_agents/professor/test_pipeline_v3*.py -k "metrics" \
  -n0 --no-cov

# Step C 真实 V3 跑一次小 sample 验证
DATABASE_URL=$DATABASE_URL uv run python scripts/run_professor_pipeline_v3_e2e.py \
  --institution "南方科技大学" --limit 3 --skip-vectorize
# 验证：3 个 prof 的 metrics 字段都填了
```

## Done criteria

1. ✅ ORCID 覆盖率 ≥ 50%（或 explicit 解释为何低于）
2. ✅ run_professor_metrics_backfill.py 创建 + ≥ 5 单测全过
3. ✅ 全量回填后 `metrics_source IS NOT NULL` 行 ≥ 90%（剩余是真无 ORCID 的）
4. ✅ pipeline_v3 stage 11.5 集成；测试覆盖；V3 e2e 跑 3 prof 验证
5. ✅ JSONL 归档 `docs/source_backfills/professor-metrics-backfill-{今日}.jsonl`
6. ✅ 现有 tests/storage + tests/data_agents/professor 不退化（test_web_search_enrichment 21 fail 已知 pre-existing，不计入退化）

## Stop conditions

- ORCID backfill 50 prof dry-run 成功率 < 30%（脚本自身可能有 bug）
- OpenAlex API 持续 5xx 或 429 不缓解
- canonical_writer.upsert_professor_metrics 在真实数据上行为异常
- 超出 3 文件创建 + 1 文件修改的 churn

## Report format

按 AGENTS.md §9：

```
Summary: <changes>
Changed files:
Verification:
- ORCID coverage before/after: 0% → X%
- pytest test_run_professor_metrics_backfill.py: N passed
- 全量回填: M/N profs successful, K with metrics_source='openalex', L with 'verified_link_only'
- pipeline_v3 e2e 3 prof: metrics 字段填情况
Risks/notes:
```
