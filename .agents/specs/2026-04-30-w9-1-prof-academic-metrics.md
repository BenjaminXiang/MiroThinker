---
title: "W9-1: 教授学术指标 3 层暴露"
date: 2026-04-30
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review 兜底
wave: Wave 9
gap: "#5"
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-04-30-admin-console-architecture.md  # admin-console UI 可见性约束
prd_anchor: docs/Professor-Data-Agent-PRD.md §模块一 R2
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §4.3 教授；§5.2 教授强制规则
---

# W9-1: 教授学术指标 3 层暴露

## 1. Goal

PRD §模块一 R2 要求教授画像卡片展示 **H-index / 总引用数 / 论文数**。当前 `EnrichedProfessorProfile` 已有这 3 个字段，但：

- canonical Postgres `professor` 表**没有专列**——仅 `professor_fact` 中以 `fact_type='publication_count_reported'` 存（无 h_index）
- `paper_count` 在代码里有 3 个语义不同的口径：`source_paper_count` / `official_paper_count` / `paper_count`，混用
- admin API（`/api/data/professors`）/ chat profile / Milvus `professor_profiles` collection metadata 三处都没暴露

本 spec 把 3 个 metrics 提升为 canonical 主表一等列，统一口径，**Postgres + admin API + Milvus 三层完整暴露**。

## 2. Non-goals

- **不**重新设计 `professor_fact` 表。fact rows 仍可存（已有 `publication_count_reported`），但本 spec 之后 metrics 主路径走 column，不走 fact
- **不**实施 W10-6.1（domains.py 切 Postgres）。本 spec 完成后 React DomainList / RecordDetail 仍看不到新字段（走 SQLite store），属预期；W10-6.1 配套修复
- **不**做独立的月度刷新 cron。metrics 跟随 V3 pipeline run 同步刷新 + 一次性回填
- **不**修改 `EnrichedProfessorProfile`（`models.py:122-156`）字段定义；它已有 3 个字段
- **不**重建 ORCID backfill / OpenAlex client。复用 `author_id_picker.py` + `run_professor_orcid_backfill.py` 现有管道
- **不**实施 React UI 字段渲染。React DomainList / RecordDetail 升级在 W10-6 + W11-x

## 3. User-visible behavior（W9-1 完成后）

| 用户面 | 行为变化 | 端点 / 文件 |
|---|---|---|
| `/api/data/professors`（list） | `ProfessorListItem` 多 `h_index` / `citation_count` / `paper_count` 3 字段；NULL 表示未计算 | `apps/admin-console/backend/api/data.py:1167-1199` |
| `/api/data/professors/{id}`（detail） | `ProfessorDetailResponse.professor` 多 3 字段 + `metrics_computed_at` + `metrics_source` | 同上 |
| `/browse` 教授 tab | 列表表头多 3 列（H-index / 总引用 / 论文数）；点详情可见时间戳与来源 | `apps/admin-console/backend/static/browse.html:780-795` 列定义 |
| chat profile | A/B 类型查教授时返回的 `core_facts` 含 3 个 metrics | `apps/admin-console/backend/api/chat.py` 教授 profile 拼装 |
| Milvus `professor_profiles` collection | 每条 entity 的 metadata 含 `h_index` / `citation_count` / `paper_count`；可用于 retrieval 时按指标排序/过滤 | `src/data_agents/storage/milvus_collections.py` |
| **React UI（DomainList / RecordDetail）** | **看不到新字段**（仍走 SQLite store）。预期；W10-6.1 修复 | — |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V012_add_professor_metrics.py
  apps/miroflow-agent/src/data_agents/professor/openalex_metrics.py
  apps/miroflow-agent/scripts/run_professor_metrics_backfill.py
  apps/miroflow-agent/tests/storage/test_v012_migration.py
  apps/miroflow-agent/tests/data_agents/professor/test_openalex_metrics.py
  apps/miroflow-agent/tests/scripts/test_run_professor_metrics_backfill.py
  apps/admin-console/tests/test_data_api.py（增 metrics 校验，文件已存在则 append）

修改：
  apps/miroflow-agent/src/data_agents/canonical/professor.py
    + Professor model 加 5 字段
  apps/miroflow-agent/src/data_agents/professor/canonical_writer.py
    + write_professor_bundle() 写入 metrics 列
  apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py
    + Stage 11 后插入 metrics 刷新；与 cross-domain writes 同 transaction
  apps/miroflow-agent/src/data_agents/storage/milvus_collections.py
    + professor_profiles schema 加 3 metadata 字段
  apps/miroflow-agent/src/data_agents/professor/vectorizer.py
    + vectorize_professor() 向量化时把 metrics 写 Milvus metadata
  apps/admin-console/backend/api/data.py
    + ProfessorListItem 加 3 字段；PROFESSOR_LIST_SELECT_SQL 增列；ProfessorDetailResponse 同
  apps/admin-console/backend/api/chat.py
    + 教授 profile 卡片 core_facts 加 3 字段
  apps/admin-console/backend/static/browse.html
    + 教授 tab COLUMNS 加 3 列定义

显式标 deprecated（不删）：
  apps/miroflow-agent/src/data_agents/professor/models.py
    EnrichedProfessorProfile 中 source_paper_count / official_paper_count
    （加 deprecated 注释；未来 wave 清理）
```

## 5. Architecture / Data flow

```
┌─────────── 数据源 ───────────┐
│ OpenAlex API（主源）         │
│   通过 author_id_picker.py    │
│   或 ORCID lookup 取 author   │
│   summary_stats              │
│     ├─ h_index                │
│     ├─ cited_by_count         │
│     └─ works_count（参考用）  │
│                              │
│ professor_paper_link（实算）│
│   COUNT(*) WHERE link_status  │
│     = 'verified'             │
│   → paper_count（权威）      │
└─────────────┬────────────────┘
              ↓
┌─── openalex_metrics.fetch_metrics(prof) ───┐
│   返回 ProfMetricsDict:                    │
│     h_index: int | None                    │
│     citation_count: int | None             │
│     paper_count_openalex: int | None       │
│     source: "openalex" | None              │
│   失败：返回全 None；记 pipeline_issue      │
└──────────────┬──────────────────────────────┘
               ↓
┌─── canonical_writer.upsert_professor_metrics(...) ───┐
│   paper_count 由 SQL 直算：                          │
│     SELECT count(*) FROM professor_paper_link        │
│     WHERE professor_id = %s AND link_status='verified'│
│   覆盖 openalex 那个 works_count                     │
│                                                       │
│   写入 professor 表 5 列：                            │
│     h_index / citation_count / paper_count /         │
│     metrics_computed_at / metrics_source             │
└──────────────┬─────────────────────────────────────────┘
               ↓
   两条触发路径：
   ┌──────────────────────┐  ┌──────────────────────────┐
   │ V3 pipeline stage    │  │ 一次性回填脚本           │
   │ 11.5（每次 run 同步）│  │ run_professor_metrics_   │
   │ pipeline_v3.py       │  │ backfill.py（775 条）    │
   └──────────┬───────────┘  └────────────┬─────────────┘
              └──────────────┬─────────────┘
                             ↓
              ┌──── Postgres professor 表 ────┐
              │  3 metrics columns + 时间戳    │
              └──────────────┬──────────────────┘
                             ↓
        ┌────────────────────┼─────────────────────┐
        ↓                    ↓                      ↓
   admin API           chat profile           Milvus collection
   (data.py)           (chat.py)              (vectorizer + backfill)
```

## 6. Interface contracts

### 6.1 alembic V012

```python
# apps/miroflow-agent/alembic/versions/V012_add_professor_metrics.py
"""V012 add professor academic metrics columns

Revision ID: V012
Revises: V011
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column('professor',
        sa.Column('h_index', sa.Integer, nullable=True))
    op.add_column('professor',
        sa.Column('citation_count', sa.BigInteger, nullable=True))
    op.add_column('professor',
        sa.Column('paper_count', sa.Integer, nullable=True))
    op.add_column('professor',
        sa.Column('metrics_computed_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('professor',
        sa.Column('metrics_source', sa.Text, nullable=True))
    # 索引：按 h_index 排序的列表查询将走顺序扫描，暂不加索引；
    # 待 W10/W11 检索接入需要时再加。

def downgrade() -> None:
    for col in ('metrics_source', 'metrics_computed_at',
                'paper_count', 'citation_count', 'h_index'):
        op.drop_column('professor', col)
```

### 6.2 canonical/professor.py 模型扩展

```python
# 在现有 Professor BaseModel 末尾追加（保持 model_config = ConfigDict(extra="forbid")）
class Professor(BaseModel):
    # ... 现有字段不变 ...

    # W9-1: 学术指标（PRD §模块一 R2）
    h_index: int | None = None
    citation_count: int | None = None
    paper_count: int | None = None  # = verified professor_paper_link 计数
    metrics_computed_at: datetime | None = None
    metrics_source: Literal["openalex", "verified_link_only", "mixed", None] = None
```

### 6.3 OpenAlex metrics fetcher

```python
# src/data_agents/professor/openalex_metrics.py
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True, slots=True)
class ProfMetrics:
    h_index: int | None
    citation_count: int | None
    works_count_openalex: int | None  # 参考；不作为 paper_count 主源
    source: str  # "openalex" | "openalex_unmatched"
    fetched_at: datetime


def fetch_metrics(
    *,
    orcid: str | None = None,
    openalex_author_id: str | None = None,
    http_client=None,
    timeout: float = 10.0,
) -> ProfMetrics:
    """从 OpenAlex API 取作者 summary_stats。

    优先级：openalex_author_id > orcid。
    返回 ProfMetrics（可能全为 None），永不抛异常；调用方判 source 字段。
    """
    ...
```

### 6.4 canonical_writer 写入

```python
# src/data_agents/professor/canonical_writer.py 增加：
def upsert_professor_metrics(
    conn,
    *,
    professor_id: str,
    h_index: int | None,
    citation_count: int | None,
    metrics_source: str | None,
    run_id,
) -> None:
    """计算 paper_count（COUNT verified link）+ 写入 5 列。"""
    paper_count_row = conn.execute(
        """
        SELECT count(*)::int AS n
        FROM professor_paper_link
        WHERE professor_id = %s AND link_status = 'verified'
        """,
        (professor_id,),
    ).fetchone()
    paper_count = int(paper_count_row["n"]) if paper_count_row else 0

    conn.execute(
        """
        UPDATE professor
        SET h_index = %s,
            citation_count = %s,
            paper_count = %s,
            metrics_computed_at = now(),
            metrics_source = %s,
            run_id = %s,
            updated_at = now()
        WHERE professor_id = %s
        """,
        (h_index, citation_count, paper_count, metrics_source, run_id, professor_id),
    )
```

### 6.5 admin API（data.py）

```python
# ProfessorListItem 增字段：
class ProfessorListItem(BaseModel):
    # ... 现有字段 ...
    h_index: int | None = None
    citation_count: int | None = None
    paper_count: int | None = None  # 注意：替换原 verified_paper_count 还是并列？
    metrics_computed_at: datetime | None = None

# PROFESSOR_LIST_SELECT_SQL 增加：
#   p.h_index,
#   p.citation_count,
#   p.paper_count,
#   p.metrics_computed_at,
#   p.metrics_source
# （删除原 verified_link_counts.verified_paper_count LATERAL JOIN——已被 paper_count 列替代）
```

**关键决定**（spec 内确定）：删除 `verified_paper_count` LATERAL JOIN，统一改为 `p.paper_count`，避免列表查询每行 sub-query。Codex 实施时同步修改 `_list_professors` 的 ORDER BY 和 has_verified_papers filter 引用。

### 6.6 Milvus collection

```python
# src/data_agents/storage/milvus_collections.py
PROFESSOR_PROFILES_COLLECTION_FIELDS = [
    # ... 现有字段 ...
    {"name": "h_index", "dtype": "Int32", "is_nullable": True},
    {"name": "citation_count", "dtype": "Int64", "is_nullable": True},
    {"name": "paper_count", "dtype": "Int32", "is_nullable": True},
]
```

`vectorizer.py` 在 `vectorize_professor()` 调用 Milvus insert 时把 3 字段填进 metadata。

### 6.7 chat.py 教授 profile

教授 profile 卡片（A 类型 + B 类型命中教授时）的 `core_facts` 字典加：

```python
core_facts = {
    "name": prof["canonical_name"],
    # ... 现有字段 ...
    "h_index": prof["h_index"],
    "citation_count": prof["citation_count"],
    "paper_count": prof["paper_count"],
}
```

## 7. Invariants（不可破坏）

1. **paper_count 唯一定义**：`COUNT(*) FROM professor_paper_link WHERE professor_id = ? AND link_status = 'verified'`。任何其他口径不得写入 `professor.paper_count` 列
2. **metrics_source 必须在枚举内**：`{"openalex", "verified_link_only", "mixed", NULL}`
3. **NULL 语义 = 未计算**：UI 渲染必须区分"NULL（未算）"与"0（确为 0）"；不得用 `coalesce(metrics, 0)` 强转
4. **metrics_computed_at ≤ professor.last_refreshed_at**：metrics 不会比教授本身更新得更晚
5. **professor 被 merged_into 后不再算 metrics**：`identity_status = 'merged'` 的行 metrics 字段保持 NULL
6. **Milvus schema 变更走重建**：不在线 ALTER（Milvus 不稳定）；用 V011 已建立的 collection 重建流程
7. **OpenAlex 失败不阻塞**：API 错误时保留旧 metrics（不覆盖为 NULL），记 pipeline_issue 类型 `metrics_fetch_failed`
8. **deprecated 字段保留**：`source_paper_count` / `official_paper_count` 在 `EnrichedProfessorProfile` 仅加注释，不删（避免破坏现有 release 路径）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| 教授无 ORCID 也无 OpenAlex match | h_index / citation_count = NULL；paper_count = verified link COUNT（可能 0）；metrics_source = "verified_link_only" |
| OpenAlex API timeout / 5xx | retry 3 次（指数退避，复用 author_id_picker 现有 backoff）；仍失败则不覆盖原值 + 记 pipeline_issue |
| 同名教授 OpenAlex 匹配多个 author_id | 走 `author_id_picker.py` 既有消歧；若仍多候选，跳过 metrics 写入 + 记 pipeline_issue 类型 `metrics_ambiguous_author` |
| OpenAlex 返回 h_index = 0 | 写 0；不视为 NULL（0 是合法值，未发表者） |
| OpenAlex 返回 cited_by_count > 2^31 | citation_count 列用 BigInt，不溢出 |
| verified link COUNT(*) = 0 | paper_count = 0；不 NULL |
| 教授刚加入，pipeline_v3 未跑过 | 5 字段全 NULL；admin 列表显示 "—" |
| metrics 回填时教授已 merged | 跳过；不写 metrics |
| Milvus collection 重建中途失败 | 旧 collection 仍可服务；新 collection 改名失败时 alias 不切换 |
| 同 run_id 重复刷写 | UPSERT 语义；最后一次 run 覆盖前面 |

## 9. Failure modes

- **OpenAlex 限速（429）**：使用指数退避；> 3 次失败标 `metrics_source = NULL` 并入 `pipeline_issue`
- **数据库写入冲突**：`UPDATE ... WHERE professor_id = ?` 单行更新，无并发冲突；但与 V3 pipeline 的 cross-domain write 同 transaction，避免 metrics 与 link 不一致
- **Milvus rebuild 失败**：Postgres 已写入，Milvus 未对齐 → admin/chat 仍可见 metrics（从 PG 读），但 Milvus retrieval 不可按 metrics 排序；记 issue 单独修
- **回填脚本部分成功部分失败**：保留断点续传（按 `metrics_computed_at IS NULL` 查待处理）

## 10. Migration / rollback

```bash
# 升级
cd apps/miroflow-agent
DATABASE_URL=$DATABASE_URL uv run alembic upgrade V012

# 验证 schema
psql "$DATABASE_URL" -c "\d professor" | grep -E "h_index|citation_count|paper_count|metrics_"

# 回填（一次性）
uv run python scripts/run_professor_metrics_backfill.py --dry-run --limit 10
uv run python scripts/run_professor_metrics_backfill.py --limit 100
uv run python scripts/run_professor_metrics_backfill.py  # 全量

# 回滚
DATABASE_URL=$DATABASE_URL uv run alembic downgrade V011
# 自动删 5 列；旧代码不感知
```

Milvus 重建在 backfill 完成后单独执行：

```bash
# 先 dry-run 检查 collection 状态
uv run python scripts/run_milvus_backfill.py --collection professor_profiles --dry-run

# 重建（约 5-10 分钟，根据 775 条规模）
uv run python scripts/run_milvus_backfill.py --collection professor_profiles --rebuild
```

## 11. Validation commands

```bash
# 单元测试
cd apps/miroflow-agent
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/storage/test_v012_migration.py \
  tests/data_agents/professor/test_openalex_metrics.py \
  tests/data_agents/professor/test_canonical_writer.py \
  tests/scripts/test_run_professor_metrics_backfill.py \
  -n0 --no-cov

# admin-console API 单测
cd apps/admin-console
uv run pytest tests/test_data_api.py -k "metrics" -n0

# E2E 真实数据校验（W9-5 后做完 1 次）
curl -s "http://localhost:8088/api/data/professors/PROF-8000C9F994C3" | \
  jq '.professor | {h_index, citation_count, paper_count, metrics_source, metrics_computed_at}'

# 与 OpenAlex web 对照
# 选 1 名 ORCID 已知教授 → 在 https://openalex.org 查 → 比对 h_index / cited_by_count

# Milvus 校验
uv run python -c "
from src.data_agents.storage.milvus_collections import PROFESSOR_PROFILES_COLLECTION
from pymilvus import Collection
c = Collection(PROFESSOR_PROFILES_COLLECTION)
print(c.schema.fields)
# 期望含 h_index / citation_count / paper_count
"
```

## 12. Expected evidence（提交时必须附）

- ✅ V012 alembic upgrade / downgrade 双向通过的 commit hash
- ✅ pytest 6 个新测试文件全过；旧 test_data_api.py 在 metrics 加列后无 regression
- ✅ 真实回填 sample report：选 5 个有 ORCID 的教授，跑回填脚本，附 `before/after metrics` JSON 对比；归档到 `docs/source_backfills/round-9-w9-1-professor-metrics-2026-XX-XX.jsonl`
- ✅ 与 OpenAlex web 一致性核对：3 个教授样本（如 丁文伯 / 张三 / 李四），人工对照 h_index 与 cited_by_count 数字一致或偏差说明
- ✅ Milvus collection schema dump（含 3 字段）
- ✅ Shared-Spec §4.3 教授节"可选学术指标"由 🟡 升级为 ✅ 的 PR
- ✅ docs/index.md 6 列状态矩阵中 Professor 行更新

## 13. Assumptions

1. OpenAlex API 当前可达（沿用 `paper/openalex.py` 与 `professor/author_id_picker.py` 已建立的客户端）
2. ORCID / OpenAlex_id 在现有 775 条教授中已有相当覆盖（Round 7.x ORCID backfill 已跑，覆盖率应 > 70%；具体率见 W9-1 实施前 audit）
3. `professor_paper_link` 中 `link_status='verified'` 已是稳定的"已认证教授-论文挂链"标签（Round 8c paper_identity_gate 已落地）
4. V012 在 V011 已 upgrade 的 `miroflow_real` 上能干净 add column（Postgres `ALTER TABLE ADD COLUMN` 是 metadata-only，对 775 行无锁影响）
5. Milvus `professor_profiles` collection 已在产，且 `run_milvus_backfill.py` 支持 collection 级别重建
6. PRD §模块一 R2 中"近 5 年论文数"暂不实现（见 §14 open question）；本 spec 只交付 H-index / 总引用 / 总论文数

## 14. Open questions（已全部锁定 — 2026-04-30）

- [x] ~~OpenAlex 匹配率 audit~~ → **Codex 启动后边做边看**。Codex 启动时跑 SQL audit 拿覆盖率汇报；不阻塞；ORCID 缺失教授 `metrics_source = 'verified_link_only'`、`h_index`/`citation_count = NULL`。后续 wave 评估是否加 web search fallback
- [x] ~~"近 5 年论文数"~~ → **不交付**，标 deferred。本 spec 仅出 `h_index` / `citation_count` / `paper_count`；PRD R2 部分实现，`recent_5y_paper_count` 列 + 计算逻辑留给后续 wave（暂用 W12-X 占位）
- [x] ~~verified_paper_count 删除还是保留~~ → **删除**，统一用 `paper_count` 列。data.py 移除 `verified_link_counts` LATERAL JOIN；browse.html 列 `verified_paper_count` 同步改成 `paper_count`；浏览器 grep 确认无其他外部消费方硬编码后即可清理。test_data_api.py 中相关断言一并改
- [x] ~~Milvus retrieval 按 h_index 排序~~ → **仅写 metadata，排序留 W11**。本 spec 只在 `professor_profiles` collection schema 加 3 字段、vectorize 时填入；不动 `service/retrieval.py`。retrieval 排序能力由 W11-x Agentic RAG 完整化承载

**所有阻塞 codex 实施的决策已锁定；本 spec 状态：`ready-for-codex`**。

## 15. 与 Shared-Spec / 其他 spec 的衔接

- **Shared-Spec §4.3 教授**：完成后将"可选学术指标"由 🟡 升级为 ✅；在表中明确 metrics_source 枚举与 paper_count 唯一定义口径
- **Shared-Spec §6.1 第 3 层 canonical**：`professor` 表的 metrics 列加入示例字段
- **Shared-Spec §7.2 教授校验**：补一条"metrics_source 必须在枚举内"
- **W10-6.1**：本 spec 完成后，React DomainList / RecordDetail **仍看不到** metrics（走 SQLite store）。W10-6.1 的 `domains.py` 改写必须把 5 个新列同步映射到 `ReleasedObject.core_facts`。两个 spec 提交可在同一 wave，但本 spec 不依赖 W10-6.1
- **W9-3 100 条意图识别基准集**：基准集中"教授学术指标"类问题（A 类型）的标准答案需在 W9-1 完成后核对；建议两 spec 在同一 wave 实施
- **W9-5 M2.4 dogfood**：M2.4 写 `professor_paper_link` 的 verified 行；W9-1 的 paper_count = verified 实计数依赖该数据。M2.4 dogfood 完成（≥ 10 profs × 15 papers verified）后再跑 W9-1 回填，paper_count 会更准
