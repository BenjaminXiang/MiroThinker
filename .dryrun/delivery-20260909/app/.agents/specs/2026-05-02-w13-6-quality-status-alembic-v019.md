---
title: "W13-6 (rev 2): alembic V019 — 4 域 quality_status + patent summary_text/method（修 W12-7 + 支持 W13-3）"
date: 2026-05-02
revision: 2
revised_reason: "rev 1 仅覆盖 4 域 quality_status；W13-3 rev 2 决策合并 patent.summary_text + patent.summary_text_method 一起加入 V019（避免单独再起 V020）。"
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w12-7-summary-quality-gate.md
  - .agents/specs/2026-05-02-w13-3-patent-postgres-writer.md
prd_anchor:
  - docs/Data-Agent-Shared-Spec.md §4.3 quality_status canonical map
  - docs/quality-status-compatibility.md
  - docs/Patent-Data-Agent-PRD.md §4.1 (patent summary_text)
---

# W13-6 (rev 2): alembic V019 — 4 域 quality_status + patent.summary_text/method

## 1. Goal

W12-7 commit `840ffdc` 写了 `scripts/run_quality_gate_reassess.py`（含 `WHERE p.quality_status='ready'` 与 `UPDATE professor SET quality_status='partial'`），并在 `apps/miroflow-agent/src/data_agents/contracts.py` 的 ProfessorRecord/CompanyRecord/PaperRecord/PatentRecord 都定义了 `quality_status: QualityStatus = "needs_review"` 字段。但 alembic 历史 V001–V018 **从未** `ALTER TABLE ... ADD COLUMN quality_status` —— 全仓 `grep 'quality_status' apps/miroflow-agent/alembic/` 0 命中。

实测（2026-05-02 host Bash 真连 `miroflow_real`）：

| 表 | identity_status | quality_status | run_id |
|---|---|---|---|
| professor | ✅ | ❌ | ✅ |
| company   | ✅ | ❌ | ✅ |
| paper     | ❌ | ❌ | ✅ |
| patent    | ❌ | ❌ | ✅ |

直接结果：

- W12-7 reassess 跑 `psycopg.errors.UndefinedColumn: column p.quality_status does not exist`
- contracts.py 的 Pydantic 模型字段在 INSERT/UPDATE 时落不到 DB（canonical_writer 当前没在 SET 列里包含 quality_status，所以"哑写"）
- PRD §4.3 / quality-status-compatibility 标准 4 域统一字段未在物理层落地

**rev 2 新增**：W13-3 (rev 2) 需要 `patent.summary_text TEXT` 和 `patent.summary_text_method TEXT CHECK ∈ ('llm','fallback_template')` 列。把这两列合并到 V019 中，避免再起一个 V020。

本 spec：

1. V019 alembic 给 4 域主表加 `quality_status TEXT NOT NULL DEFAULT 'needs_review'`
2. 同时给 `patent` 加 `summary_text TEXT` + `summary_text_method TEXT`（W13-3 依赖）
3. `run_quality_gate_reassess.py` 不改（V019 落地后即可跑）

## 2. Non-goals

- **不**给 paper/patent 加 identity_status（独立 spec；本 batch 只修 quality_status / patent summary 字段）
- **不**改 contracts.py（quality_status 字段已对齐；patent summary_text 不在 PatentRecord 当前 model，待 W13-3 一起处理）
- **不**改 canonical_writer 把 quality_status 写进 INSERT 列（保留默认值即可；W13-3 patent writer 会写 patent 三列）
- **不**回填非 'needs_review' 的状态（DEFAULT 即可）
- **不**改 chat / retrieval / admin DTO 对 quality_status 的暴露（独立 spec）
- **不**给 paper / company / professor 加 summary_text（patent 独有；其他域用 profile_summary / summary_zh）

## 3. User-visible behavior

| 场景 | 之前 | 之后 |
|---|---|---|
| `run_quality_gate_reassess.py --dry-run` | UndefinedColumn raise | dry-run 跑通；列出 ~5 prof candidate（含丁文伯）|
| `run_quality_gate_reassess.py` 实跑 | raise | 跑通；UPDATE ~5 prof ready→partial（依赖 quality_status='ready' 起点；首次跑前所有 prof 都是默认 needs_review，所以**首次跑结果应该是 0 demoted**）|
| `SELECT quality_status FROM {professor,company,paper,patent} LIMIT 1` | column does not exist | 返回 'needs_review' |

**重要矛盾**：W12-7 reassess 期望 "ready → partial"，但 V019 默认 'needs_review'。意思是首次 V019 落地后，没有任何 prof 是 'ready'，reassess 找不到候选。

**怎么解决这个矛盾**：

- 选项 A：V019 加列同时把所有"通过 V3 pipeline + name-identity gate 通过 + summary 非空"的 prof 设置为 'ready'。但 V3 pipeline 没有这个语义（identity_status='confirmed' 是最近义）。
- 选项 B：V019 加列后，单独跑一个 promotion 脚本，按现有数据"质量近似"批 promote 一波到 'ready'，再让 reassess 把 < 150 chars 的 demote 回 'partial'。
- 选项 C：W12-7 spec §3 描述的"原 ~5 prof ready→partial"基于 mental model（"我们假设它们已经是 ready"），实际 schema 上没有这状态。本 spec 只补列 + DEFAULT 'needs_review'，把 "ready 状态从哪来" 留给后续 spec。

**Claude 推荐：选项 C**。最小修复，不假设 promotion 流程。等 W13-D2（独立 spec）把 promote 流程定义清楚再做。

## 4. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V019_add_quality_status_and_patent_summary.py
    A. add_column 4 张表的 quality_status TEXT NOT NULL DEFAULT 'needs_review'
       加 CHECK constraint：quality_status IN ('needs_review','ready','low_confidence','needs_enrichment','partial','rejected')
       加索引：CREATE INDEX ix_<table>_quality_status

    B. add_column patent.summary_text TEXT (nullable)
       add_column patent.summary_text_method TEXT (nullable)
       加 CHECK constraint：summary_text_method IN ('llm','fallback_template') OR NULL
       不加索引（按 keyword 检索的是 abstract_clean / title_clean）

  apps/miroflow-agent/tests/storage/test_v019_migration.py
    A. 测试 V019 upgrade 后 4 表都有 quality_status 列 + 默认值 'needs_review'
       测试 quality_status CHECK 拒非法值
    B. 测试 patent 表新增 summary_text + summary_text_method 列
       测试 summary_text_method CHECK 拒非法值（如 'gpt' 'manual'）
       测试 summary_text_method 允许 NULL

修改（minimal）：
  apps/miroflow-agent/scripts/run_quality_gate_reassess.py
    （不改 SQL 主体；V019 落地后脚本即可跑通）
    可选：加 sanity-check：if 0 candidates and dry-run，打印提示语 "no prof in 'ready' state — promotion not yet run"
```

## 5. Schema (V019)

```python
"""V019: add quality_status (4 domains) + patent summary_text/method"""

revision = "V019"
down_revision = "V018"

VALID_QUALITY_STATUSES = (
    "needs_review", "ready", "low_confidence", "needs_enrichment", "partial", "rejected"
)
VALID_SUMMARY_METHODS = ("llm", "fallback_template")

def upgrade():
    # Part A: quality_status on 4 canonical tables
    for table in ("professor", "company", "paper", "patent"):
        op.add_column(
            table,
            sa.Column(
                "quality_status",
                sa.Text(),
                nullable=False,
                server_default="needs_review",
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_quality_status",
            table,
            f"quality_status IN {VALID_QUALITY_STATUSES!r}",
        )
        op.create_index(
            f"ix_{table}_quality_status",
            table,
            ["quality_status"],
        )

    # Part B: patent.summary_text + summary_text_method (W13-3 dependency)
    op.add_column("patent", sa.Column("summary_text", sa.Text(), nullable=True))
    op.add_column(
        "patent",
        sa.Column("summary_text_method", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_patent_summary_text_method",
        "patent",
        f"summary_text_method IS NULL OR summary_text_method IN {VALID_SUMMARY_METHODS!r}",
    )

def downgrade():
    # Part B reverse
    op.drop_constraint("ck_patent_summary_text_method", "patent")
    op.drop_column("patent", "summary_text_method")
    op.drop_column("patent", "summary_text")

    # Part A reverse
    for table in ("professor", "company", "paper", "patent"):
        op.drop_index(f"ix_{table}_quality_status", table_name=table)
        op.drop_constraint(f"ck_{table}_quality_status", table_name=table)
        op.drop_column(table, "quality_status")
```

## 6. Invariants

### Part A — quality_status

- DEFAULT 'needs_review' — 与 contracts.py:9 `QUALITY_STATUS_CANONICAL_MAP` 默认值一致
- CHECK 枚举值与 `docs/quality-status-compatibility.md` 一致（含 'partial' 'rejected' 兼容 alias）
- 4 表都加索引：`quality_status` 是检索过滤常用列（ready 才进 retrieval；reassess 也按 quality_status='ready' 过滤）

### Part B — patent.summary_text / summary_text_method

- 两列都 nullable（W13-3 land 前 patent 行无 summary_text；W13-3 写时配对填）
- `summary_text_method` CHECK：`NULL OR IN ('llm','fallback_template')`（NULL 允许，因为 W13-3 land 前列即存在但无人写）
- W13-3 writer 必须保证：`summary_text NOT NULL` 时 `summary_text_method NOT NULL`（业务规则；本 spec 不强制 CHECK，由 W13-3 校验）
- 不加索引：summary_text 不是过滤列；admin / chat 按 patent_id 取行直接返该列即可

### 通用

- V019 是纯 alembic 迁移，不动业务代码（除可选的 reassess sanity-check）
- DOWN 必须可逆（drop column + drop index + drop check 6 项 + patent 3 项）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| miroflow_real 有 N 行 paper / patent | 加列 default 'needs_review'，行数不变；patent 多两列默认 NULL |
| canonical_writer 之前不写 quality_status 列 | 不影响；继续用 default |
| 旧 jsonl release path 写入 quality_status='ready' | 与 release.py 行为对齐（实际只在 jsonl 里，不入库）|
| pipeline_issue 是否需要相关字段 | 否；reassess 已 INSERT pipeline_issue（同一脚本）|
| W13-3 未 land 时直接查 patent.summary_text | 全 NULL（前端降级展示 abstract_clean / technology_effect）|
| 已有 patent 行（1931 行 jsonl 待入库）有 summary_text_method='gpt' 这种历史值 | 当前 jsonl 不入库 patent 表；V019 加列时表为空（实测 `count(*) FROM patent = 0`）|

## 8. Validation

```bash
cd apps/miroflow-agent

# 1. 单测：upgrade + downgrade
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/storage/test_v019_migration.py -n0 --no-cov -v

# 2. 实际 upgrade real DB
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run alembic upgrade head

# 3. 验证列存在
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python -c "
import psycopg
c = psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/miroflow_real')
for t in ['professor','company','paper','patent']:
    cur = c.cursor()
    cur.execute(f\"SELECT count(*), count(*) FILTER (WHERE quality_status='needs_review') FROM {t}\")
    print(t, cur.fetchone())
# Part B verify
cur = c.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='patent' AND column_name IN ('summary_text','summary_text_method') ORDER BY column_name\")
print('patent extras:', [r[0] for r in cur.fetchall()])
"
# 期望：patent extras: ['summary_text', 'summary_text_method']

# 4. reassess dry-run（应该跑通，候选 0 因为还没 promote）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_quality_gate_reassess.py --dry-run
# 期望：no errors；reassess 找 0 candidates（因为没有 prof 是 'ready'）

# 5. test_mock 验证 admin/chat 不退化（这两条新列尚未被 UI 读，不应影响）
cd ../admin-console
DATABASE_URL_TEST=... uv run pytest tests/ -k "domain or chat" -n0 --no-cov | tail
```

## 9. Done criteria

1. ✅ V019 alembic upgrade + downgrade 双向 OK（test_mock 跑过两次 up→down→up）
2. ✅ test_v019_migration 单测 通过（含 Part A quality_status + Part B patent.summary_text/method）
3. ✅ real DB upgrade 后：4 表都有 quality_status 列；行数不变；DEFAULT 命中
4. ✅ patent 表新增 summary_text + summary_text_method 列（实测 `information_schema.columns` 查得到，且行数不变）
5. ✅ patent.summary_text_method CHECK 拒非法值（如 'gpt' 'manual'）；NULL 允许
6. ✅ reassess dry-run 跑通（无 raise；候选 0 行）
5. ✅ admin / chat 既有测试不退化
6. ✅ ruff 通过

## 10. 顺序与依赖

- **必须在 Batch A (W13-1..5) 完成后** 落地（V019 在 V018 之后；Batch A 不动 alembic）
- **W13-6 之后**：另起 W13-D2 spec 决定 promotion 流程（哪些 prof 自动 promote 'ready'）+ canonical_writer 如何写 quality_status

## 11. Open questions

| 问题 | 默认决策 |
|---|---|
| 'partial' / 'rejected' 是 canonical 还是 alias？ | 看 quality-status-compatibility.md；本 spec 把它们都列入 CHECK，运行时按 canonical_map normalize |
| paper/patent 加 identity_status 是否本 spec 范围？ | 否。仅 quality_status |
| 是否同时加 last_updated 列？ | 否。已在各表（其他名称）|
| 默认值是 'needs_review' 还是 NULL？ | 'needs_review' — 与 Pydantic default 一致；NOT NULL |
| CHECK constraint 影响性能？ | 微（< 1ms / 1k rows）；可接受 |
| 是否回填 ready？ | 否（独立 spec W13-D2）|

## 12. Stop conditions

- V019 upgrade 在 real DB 失败 / 表锁等待 > 30s → escalate
- CHECK constraint 拒已有数据（不可能，因为新加列）→ N/A
- reassess dry-run 仍 raise（说明还有别的 column 缺）→ 单独 BLOCKED 报告

## 13. 后续 follow-up（不在本 spec 范围）

- W13-D2: promotion 决策 — 哪些 prof / company / paper / patent 自动从 needs_review → ready
- W13-7: canonical_writer 把 quality_status 写进 INSERT 列（4 域；patent 由 W13-3 一并处理）
- W13-9: paper / patent 加 identity_status（PRD 与 §5.5 hallucination prevention 对齐）
- W13-10: retrieval / chat / admin 暴露 quality_status（仅 ready 进检索池）

注：W13-8 编号已用于"Serper-based news connector"（替代 Tushare/CNStock）。
