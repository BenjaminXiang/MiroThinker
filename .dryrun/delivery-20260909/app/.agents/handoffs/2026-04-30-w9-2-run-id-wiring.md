---
title: "W9-2: Round 7.16 phase 2 — 全 writer wiring run_id (3 sub-slice)"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-04-30-w9-2-run-id-wiring-phase-2.md
slice: 1+2+3 of 3
status: ready
---

# W9-2 handoff（拆 3 sub-slice）

## CRITICAL — codex CLI proxy + sandbox

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

沙箱限制：**不要 git commit**；claude 后续 commit。

## Read order

1. **本 handoff**
2. `.agents/specs/2026-04-30-w9-2-run-id-wiring-phase-2.md` 完整契约
3. W9-1 slice 1+2 commit `310a2bd` / `6de8ebb` / `91e1412`（看 professor 域 writer 已用模式：required keyword `run_id`，open_pipeline_run / close_pipeline_run）
4. `apps/miroflow-agent/src/data_agents/storage/postgres/pipeline_run.py`（open/close API）
5. `apps/miroflow-agent/alembic/versions/V001_init_source_layer.py` PIPELINE_RUN_KINDS / PIPELINE_RUN_STATUSES（合法 enum）

## Sub-slice 拆分（按域）

### sub-slice 1: paper 域

MODIFY:
- `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py`：所有 upsert_* 函数 run_id 改为 required keyword（无 default）
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`：`_DRY_RUN_SENTINEL_RUN_ID` 仅 dry-run；wet-run 必须 open_pipeline_run 拿真 run_id
- `apps/miroflow-agent/src/data_agents/storage/postgres/paper_full_text.py`：upsert 路径 run_id required

CREATE: `apps/miroflow-agent/tests/data_agents/test_run_id_wiring_paper.py`
- 验证 paper writer signature `run_id` 无 default
- mock writer 验证 reject sentinel UUID（'00000000-...'）

### sub-slice 2: company / patent 域

MODIFY:
- `apps/miroflow-agent/src/data_agents/company/canonical_import.py`：写入路径 run_id required
- `apps/miroflow-agent/src/data_agents/patent/*`：所有 writer 同
- `apps/miroflow-agent/src/data_agents/canonical/{company,patent,source,relations}.py`：模型 run_id 字段已存在不动

CREATE: `apps/miroflow-agent/tests/data_agents/test_run_id_wiring_company_patent.py`

### sub-slice 3: scripts/ + audit + CI 守门

MODIFY: 所有 `apps/miroflow-agent/scripts/run_*` 写入类脚本，必须 open/close pipeline_run（如 W9-1 slice 2 的 metrics backfill 已示范）。具体清单：
- run_company_import_e2e.py / run_company_release_e2e.py
- run_paper_release_e2e.py
- run_patent_import_e2e.py / run_patent_release_e2e.py
- run_homepage_paper_ingest.py（已有 sentinel 路径，wet-run 改 open_pipeline_run）
- run_professor_release_e2e.py / run_professor_url_md_e2e.py
- 其他 staging / backfill 类（grep 找）

CREATE:
- `apps/miroflow-agent/scripts/audit_run_id_coverage.py`（spec §6.4 给签名）
- `apps/miroflow-agent/tests/data_agents/test_run_id_wiring.py`（合并的 CI 守门测试）

跑 audit：
```bash
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/audit_run_id_coverage.py > docs/source_backfills/run-id-coverage-2026-05-02.txt
```

## Critical decisions（spec 已锁定）

- legacy_backfill 行**不**重新 wiring（仅约束新写入）
- sentinel UUID 保留形式 `_DRY_RUN_SENTINEL_RUN_ID = UUID('00000000-0000-0000-0000-000000000000')`（多处引用）
- CI 守门测试是**强制**（非 marker）
- run_kind 用合法 enum：`backfill_real` / `professor_v3` / `legacy_backfill` 等
- close_pipeline_run status：合法 `running/succeeded/partial/failed`

## Do-not

- ❌ 不重新写历史数据（保留 legacy_backfill UUID）
- ❌ 不移除 sentinel UUID 的定义（兼容已知调用）
- ❌ 不 commit
- ❌ 不动 professor 域已有的 W9-1 slice 1+2 wiring（已正确）
- ❌ 不破坏现有 dry-run 行为

## Tests / checks

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/ -n0 --no-cov

# audit 跑全 4 域
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/audit_run_id_coverage.py
# 期望: legacy_backfill UUID 行数 + 真 run_id 行数 + NULL 行数 全部统计

# 抽样 V3 e2e 跑一次小 sample 验证新行 run_id 真值
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_professor_pipeline_v3_e2e.py --institution "南方科技大学" --limit 3
# 跑后查 SELECT run_id FROM professor WHERE last_refreshed_at >= now() - interval '5 min' GROUP BY run_id
# 期望: 1 个非 legacy_backfill 的 UUID
```

## Done criteria

1. 4 域全部 writer signature `run_id` required；CI 守门测试通过
2. scripts/ 中所有 writer 类脚本都 open/close pipeline_run
3. audit 报告归档 `docs/source_backfills/run-id-coverage-2026-05-02.txt`
4. 现有 V3 e2e 跑 3 prof 后 metrics 表 run_id 是真值（非 legacy / 非 sentinel）
5. dry-run 路径仍能识别 sentinel（不破坏 W9-5 dogfood dry-run 行为）

## Stop conditions

- writer 函数太多，超 10 个修改文件 → stop, escalate（拆 sub-slice）
- 有 writer 与 sentinel 强耦合不易改 → stop, 记 follow-up
- pipeline_run insert 反复失败 → DB 层异常，stop

## Report

```
Summary: <changes per sub-slice>
Changed files:
Verification:
- pytest tests/data_agents/: N passed
- audit run-id coverage: <数字 by 域>
- V3 e2e 3 prof: run_id = <真值 UUID>
Risks/notes:
```
