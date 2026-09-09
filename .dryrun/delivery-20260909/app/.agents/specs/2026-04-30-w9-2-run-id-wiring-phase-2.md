---
title: "W9-2: Round 7.16 phase 2 — 全 writer wiring run_id"
date: 2026-04-30
owner: claude
status: ready-for-codex
audience: codex
wave: Wave 9
gap: "#8"
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_plan: docs/plans/2026-04-18-008-pipeline-run-id-trace.md
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §4.2 run_id 契约字段
---

# W9-2: Round 7.16 phase 2 — 全 writer wiring run_id

## 1. Goal

Round 7.16 phase 1（V007 alembic）已建 `pipeline_run` 表 + 给 4 域 canonical 表加 `run_id UUID` 列 + 40,834 行 legacy_backfill 占位回填。但 **phase 2 writer wiring 尚未完成**：当前各域 canonical writer 中，`run_id` 接收路径不一致——部分写入仍用 `_DRY_RUN_SENTINEL_RUN_ID = UUID('00000000-...')`、部分用真实 `pipeline_run.run_id`、部分依赖默认值。

本 spec 让所有 canonical writer 严格接收并写入真实 `run_id`，废止占位符路径，加 CI 守门测试防回归。

## 2. Non-goals

- **不**改 V007 alembic（已落地）
- **不**重新回填历史 `legacy_backfill` 行（数据已存在，本 spec 只确保**新写入**带真实 run_id）
- **不**改 chat.py 的 retrieval / dashboard 读路径（phase 2 是写入侧）
- **不**做跨 process 的 run_id 联邦传递（一个 pipeline run 对应一个 process）

## 3. User-visible behavior

- `pipeline_run` 表每次 V3 pipeline / dogfood / backfill 启动时新增一行（已有，但部分脚本没用）
- 所有 canonical 行新增/更新时 `run_id` 字段填真实 UUID（不是 sentinel `00000000-...`）
- CI 加守门：mock writer + 验证传入的 run_id 不是 sentinel 值
- 既有 legacy 行（`run_id` 已是 `legacy_backfill` 占位 UUID）保持不动

## 4. Affected paths

```
MODIFY:
  apps/miroflow-agent/src/data_agents/professor/canonical_writer.py  ← W9-1 已动；
    本 spec 进一步审计 write_professor_bundle / 关联 link 写入是否每处带真 run_id

  apps/miroflow-agent/src/data_agents/paper/canonical_writer.py
    ← 检查 upsert_paper / 链接写入

  apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py
    ← _DRY_RUN_SENTINEL_RUN_ID 仅用于 dry-run；wet-run 必须传真值

  apps/miroflow-agent/src/data_agents/company/canonical_import.py
    ← canonical 公司写入路径

  apps/miroflow-agent/src/data_agents/storage/postgres/paper_full_text.py
    ← V011 表写入时也带 run_id

  apps/miroflow-agent/src/data_agents/storage/postgres/pipeline_run.py
    ← 检查 open_pipeline_run / close_pipeline_run 调用方覆盖

  apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py
    ← 主编排传 run_id 到各 writer

  apps/miroflow-agent/scripts/run_*.py
    ← 各运维脚本必须 open_pipeline_run 后才调 writer

CREATE:
  apps/miroflow-agent/tests/data_agents/test_run_id_wiring.py
    ← CI 守门测试（mock writer，断言 run_id 非 sentinel）

  apps/miroflow-agent/scripts/audit_run_id_coverage.py
    ← 一次性 audit 脚本：扫所有 canonical 表，统计 legacy_backfill UUID 行数 vs 真 run_id 行数
```

## 5. Architecture / Data flow

```
script entry / pipeline_v3 启动
    ↓
open_pipeline_run() returns run_id (UUID)
    ↓
 propagate run_id 到所有 canonical writer 调用
    ↓
canonical_writer 各 method:
  write_professor_bundle(..., run_id=<real>)
  upsert_paper(..., run_id=<real>)
  upsert_company(..., run_id=<real>)
  upsert_patent(..., run_id=<real>)
  _upsert_professor_paper_link(..., run_id=<real>)
  upsert_paper_full_text(..., run_id=<real>)
    ↓
INSERT/UPDATE 时 run_id 列填真值
    ↓
close_pipeline_run(run_id, status='success'|'failed')
```

**关键不变量**：所有 writer 函数签名必须 `run_id` 为 required 参数（不是 keyword-only optional with default）。

## 6. Interface contracts

### 6.1 Writer 函数签名规范

```python
# 现有写法（多种不一致）
def upsert_paper(conn, *, paper, run_id=None) -> ...:        # ❌ 默认 None
def write_professor_bundle(conn, *, ..., run_id) -> ...:      # ✅ required keyword
def _upsert_professor_paper_link(conn, *, ..., run_id) -> ... # ✅ required
def upsert_paper_full_text(conn, *, ..., run_id=_SENTINEL) -> # ❌ 默认 sentinel

# 目标写法（统一为 required keyword-only）
def upsert_paper(conn, *, paper, run_id: UUID) -> ...:  # required, no default
```

### 6.2 sentinel 处理

- `_DRY_RUN_SENTINEL_RUN_ID = UUID('00000000-0000-0000-0000-000000000000')` 仅在 **dry-run** 路径（如 `homepage_ingest.py:32`）内部使用
- 任何 wet-run 路径 **不得**传 sentinel；CI 守门测试断言

### 6.3 pipeline_run 协议

```python
# 每个脚本启动时必须 open
run_id = open_pipeline_run(
    conn,
    pipeline_name="run_homepage_paper_ingest",  # 或脚本名
    pipeline_version="v3",
    started_by="codex" | "operator" | "ci",
    started_at=now(),
)

# 主流程结束（成功 / 失败 / 中断）必须 close
close_pipeline_run(conn, run_id=run_id, status="success", finished_at=now())
```

### 6.4 audit_run_id_coverage.py

```python
# 一次性 SQL 报告：
#   per-table 总行数 / legacy_backfill UUID 行数 / 真 run_id 行数 / NULL 行数
#
# 输出 docs/source_backfills/run-id-coverage-{YYYY-MM-DD}.txt
```

### 6.5 CI 守门测试

```python
# tests/data_agents/test_run_id_wiring.py
@pytest.mark.parametrize("writer_fn,sample_args", [
    (upsert_paper, {...}),
    (write_professor_bundle, {...}),
    (upsert_company, {...}),
    ...
])
def test_writer_rejects_sentinel_run_id(writer_fn, sample_args):
    """所有 wet-run writer 必须 reject sentinel run_id"""
    sentinel = UUID('00000000-0000-0000-0000-000000000000')
    with pytest.raises(ValueError, match="sentinel"):
        writer_fn(mock_conn, run_id=sentinel, **sample_args)


def test_writer_requires_run_id():
    """所有 writer signature 必须 run_id 为 required"""
    import inspect
    for fn in [upsert_paper, write_professor_bundle, ...]:
        sig = inspect.signature(fn)
        assert "run_id" in sig.parameters
        assert sig.parameters["run_id"].default is inspect.Parameter.empty, \
            f"{fn.__name__} must require run_id (no default)"
```

## 7. Invariants

1. canonical 4 域的 `run_id` 列：phase 2 完成后**新行** `run_id != '00000000-...'` 且 `!= NULL`
2. legacy（V007 已写）行 `run_id = legacy_backfill UUID` 保留不动
3. dry-run 路径（如 homepage_ingest --dry-run）的 sentinel 与 wet-run 严格隔离；CI 测两条路径
4. 任何写入 canonical 表的代码路径都必须先 `open_pipeline_run` 取 run_id
5. 脚本中途崩溃：`close_pipeline_run(status='failed')` 必须由 `try/finally` 包裹保证调用
6. CI 守门测试是**强制性**（非 marker，默认跑）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| 脚本启动时 `pipeline_run` 表写不进 | 立刻 abort；不落 canonical 数据 |
| 主流程异常中断 | finally 块 `close_pipeline_run(status='failed')` |
| 多脚本并发跑 | 各自独立 run_id；不共享 |
| dogfood / backfill / 普通 V3 run | 都走相同 open/close 协议；不区分子类型（仅 `pipeline_name` 字段区分） |
| 已有 legacy 行被 W9-1/2 修改 | UPDATE 时**仍**填真实新 run_id，覆盖 legacy_backfill UUID |

## 9. Validation commands

```bash
cd apps/miroflow-agent

# 1. 单测
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/data_agents/test_run_id_wiring.py \
  -n0 --no-cov

# 2. 现有测试不退化
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/data_agents/ tests/storage/ \
  -n0 --no-cov

# 3. 跑 audit
DATABASE_URL=$DATABASE_URL uv run python scripts/audit_run_id_coverage.py
# → 报告 docs/source_backfills/run-id-coverage-{YYYY-MM-DD}.txt

# 4. 真实 V3 pipeline 跑一次小 sample，验证新行 run_id 是真值
DATABASE_URL=$DATABASE_URL uv run python scripts/run_professor_pipeline_v3_e2e.py \
  --institution "南方科技大学" --limit 3
psql "$DATABASE_URL" -c "
  SELECT run_id, count(*) FROM professor
  WHERE last_refreshed_at >= now() - interval '5 minutes'
  GROUP BY run_id;
"
# → 应该看到 1 个非 legacy_backfill 的 UUID + count 数
```

## 10. Slice 拆分（推荐 codex 实施时）

W9-2 涉及 4 域 + 多个脚本，建议拆 3 slice：

- **W9-2 slice 1**：professor 域（writer 签名硬化 + 调用方 + 测试）
- **W9-2 slice 2**：paper / company / patent 域 + sentinel 隔离
- **W9-2 slice 3**：scripts/ 全审计 + audit 脚本 + CI 守门

每 slice 独立 codex 派发 + claude review。

## 11. Open questions（claude 自决，2026-05-01）

- [x] **legacy_backfill 行是否要重新走 phase 2 wiring 写一遍真 run_id**：否。phase 2 仅约束**新写入**；历史 legacy_backfill 行不动（数据已发布的 audit 价值低于改动风险）
- [x] **sentinel UUID 是否换成 enum / Literal**：保留 UUID 形式（已被多处引用）；用 module-level 常量 `_DRY_RUN_SENTINEL_RUN_ID` 唯一定义
- [x] **CI 守门测试覆盖到哪些 writer**：全部 canonical_writer + storage/postgres/* 的写函数 + run_homepage_paper_ingest / run_professor_pipeline_v3_e2e 等主入口
- [x] **scripts 中是否所有都要 open/close pipeline_run**：是。但低风险脚本（如 audit / read-only）可略；本 spec 范围仅 writer 类脚本

**所有阻塞 codex 实施的决策已锁定；本 spec 状态：`ready-for-codex`**。

## 12. 与 Shared-Spec / 其他 wave 的衔接

- Shared-Spec §4.2：本 spec 完成后，"run_id 必填" 描述由"phase 1，phase 2 wiring 进行中"升级为"已强制全 writer 走真 run_id"
- W9-1：W9-1 slice 2 的 metrics 写入也走真 run_id（W9-1 spec §6.4 已要求）；W9-2 进一步把约束扩到所有 writer
- W10-6.4 upload.py 切 canonical：upload 路径也必须走 pipeline_run 协议
