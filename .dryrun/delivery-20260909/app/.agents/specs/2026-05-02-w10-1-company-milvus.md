---
title: "W10-1: Company Milvus collection + 嵌入"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 10
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-04-30-w9-1-prof-academic-metrics.md  # 模式参考（professor）
prd_anchor: docs/Company-Data-Agent-PRD.md §模块二 R1
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §6 检索
---

# W10-1: Company Milvus collection + 嵌入

## 1. Goal

PRD §模块二 R1 要求：企业语义检索能按"做无人机的 AI 公司"召回。当前 Postgres `company` 表只有 `description`（xlsx 导入），无 `profile_summary` / `technology_route_summary`，且 Milvus 没有 company collection → 任何 B/D 类型查企业语义查询命中率为 0。

**本 spec**：
- 加 V014 migration：`company.profile_summary` / `company.technology_route_summary` (Text, nullable)
- 新建 `company_profiles` Milvus 4096-dim collection
- 新建 `company.vectorizer`（mirror professor.vectorizer 但单 vector）
- run_milvus_backfill.py 加 `--domain company`

W10-4（LLM enrichment）会填充新列；本 spec 完成后即使新列为 NULL，embed 文本可降级到 `description`。

## 2. Non-goals

- **不**实施 W10-4（technology_route_summary 的 LLM enrichment 单列）
- **不**做 RetrievalService 接入（W10-3）
- **不**改 React UI / admin-console
- **不**动 SqliteReleasedObjectStore（W10-6.5 退役）
- **不**改 chat.py（chat 调 RetrievalService，W10-3 后才生效）

## 3. User-visible behavior

| 用户面 | 行为 |
|---|---|
| 跑 `run_milvus_backfill.py --domain company` | 读 Postgres company 表 → 拼文本 → embed → 写 Milvus `company_profiles` |
| `MilvusClient(uri).has_collection("company_profiles")` | True |
| 抽样 50 公司 search by name/profile | 召回 top-10 中包含 query 公司本身（自一致性） |
| 暂时 不影响 admin-console / chat | RetrievalService W10-3 后才接入 |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V014_add_company_narrative_fields.py
  apps/miroflow-agent/src/data_agents/company/vectorizer.py
  apps/miroflow-agent/tests/storage/test_v014_migration.py
  apps/miroflow-agent/tests/data_agents/company/test_vectorizer.py
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py

修改：
  apps/miroflow-agent/src/data_agents/canonical/company.py
    Company model 加 profile_summary / technology_route_summary 字段
  apps/miroflow-agent/src/data_agents/storage/milvus_collections.py
    + COMPANY_PROFILES_COLLECTION 常量
    + ensure_company_profiles_collection / drop_company_profiles_collection
  apps/miroflow-agent/scripts/run_milvus_backfill.py
    + --domain company 路径 + _backfill_company_domain()
```

## 5. Architecture / Data flow

```
Postgres company（V014 后含 profile_summary + technology_route_summary）
  ↓ SELECT company_id, canonical_name, industry, hq_city, description,
            profile_summary, technology_route_summary
  ↓
_compose_company_text(row)  -- 拼接逻辑见 §6.2
  ↓
EmbeddingClient.embed_batch()  -- Qwen3-Embedding-8B 4096-dim
  ↓
Milvus company_profiles collection（fields: id, name, industry, hq_city,
  description, profile_summary, technology_route_summary, profile_vector）
```

## 6. Interface contracts

### 6.1 V014 migration

```python
def upgrade():
    op.add_column("company", sa.Column("profile_summary", sa.Text(), nullable=True))
    op.add_column("company", sa.Column("technology_route_summary", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("company", "technology_route_summary")
    op.drop_column("company", "profile_summary")
```

### 6.2 `_compose_company_text(row)`

```python
def _compose_company_text(row: dict) -> str:
    name = (row.get("canonical_name") or "").strip()
    industry = (row.get("industry") or "").strip()
    hq_city = (row.get("hq_city") or "").strip()
    profile = (row.get("profile_summary") or "").strip()
    tech_route = (row.get("technology_route_summary") or "").strip()
    description = (row.get("description") or "").strip()

    parts: list[str] = []
    header = name
    if industry or hq_city:
        chunks = [c for c in (industry, hq_city) if c]
        header = f"{name}，{'，'.join(chunks)}"
    parts.append(header)

    # 优先 profile_summary + technology_route_summary 拼接（W10-4 后生效）
    narrative_chunks = [c for c in (profile, tech_route) if c]
    if narrative_chunks:
        parts.append(" ".join(narrative_chunks))
    elif description:
        # 降级：未做 LLM enrichment 时用 xlsx description
        parts.append(description[:1800])

    return "\n".join(parts)
```

### 6.3 Milvus collection schema

```
COMPANY_PROFILES_COLLECTION = "company_profiles"

fields:
  id (VARCHAR PK, max_length=64)            -- company_id (COMP-xxx)
  name (VARCHAR max_length=256)
  industry (VARCHAR max_length=128)
  hq_city (VARCHAR max_length=64)
  description (VARCHAR max_length=2048)
  profile_summary (VARCHAR max_length=2048)
  technology_route_summary (VARCHAR max_length=2048)
  profile_vector (FLOAT_VECTOR dim=4096)

index:
  field_name="profile_vector"
  index_type="AUTOINDEX"
  metric_type="COSINE"
```

## 7. Invariants

- 4096-dim 与 paper / professor 一致（同 embedding model）
- AUTOINDEX + COSINE 与现有一致
- `id` = `company_id`（COMP-{12hex}）
- description 字段保留（兼容 search by raw 介绍）
- 文本字符串如超 max_length 用 Python slice 截断（不 raise）
- 单 vector（不 dual vector；user 锁定）
- collection 不存在时 ensure_*() 创建；存在时不重建（rebuild 走 drop_*）
- empty narrative + empty description → 跳过该 company（计 profs_skipped）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| profile_summary / tech_route 全 NULL → 用 description | 见 §6.2 fallback chain |
| 三者都 NULL → 仅 name + industry | header 自身 embed（弱信号但不为空） |
| description > 1800 chars | slice 到 1800 |
| company 表中 identity_status='inactive' | SQL 过滤掉（与 V003 paper 行为一致） |
| 行无 canonical_name | 跳过 |
| 重复 company_id（理论不应发生） | upsert 覆盖 |

## 9. Validation commands

```bash
cd apps/miroflow-agent

# 1. V014 应用
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run alembic upgrade V014
# 验证：psql -c "\d+ company" 应见 profile_summary / technology_route_summary

# 2. 新单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/storage/test_v014_migration.py \
                 tests/data_agents/company/test_vectorizer.py \
                 tests/scripts/test_run_milvus_backfill_company.py \
                 -n0 --no-cov -v

# 3. 既有 company / milvus 单测不退化
uv run pytest tests/data_agents/company/ tests/storage/ tests/scripts/ -n0 --no-cov

# 4. dry-run 检查 collection 设计（claude 后续操作）
DATABASE_URL=... uv run python scripts/run_milvus_backfill.py \
  --domain company --milvus-uri ./milvus.db --dry-run
# 期望：JSON 报告 missing_fields 列出新 collection 字段
```

## 10. Expected evidence（codex 报告）

1. V014 migration 单测过
2. vectorizer 单测过（mock embedding client；4096-dim 输入 → upsert 写入）
3. run_milvus_backfill_company 单测过（mock conn + milvus + embedding）
4. 既有 milvus_collections.py 测试不退化
5. claude 后续操作环节（不 codex 跑）：
   - `alembic upgrade V014` against miroflow_real
   - run_milvus_backfill.py --domain company → 跑全量
   - 抽样 5 company search → 自身在 top-10

## 11. Migration / rollback

- 加列：alembic upgrade V014（毫秒级）
- 下线：alembic downgrade V013（删两列；如有数据丢失但本 spec 阶段无）
- Milvus collection 删除：drop_company_profiles_collection() + 手动 milvus_client.drop_collection()

## 12. Stop conditions

- W014 与现有 schema 冲突（不太可能；新列） → escalate
- vectorizer mock 单测显示 dim 错位 → 检查 EmbeddingClient 调用 path
- collection name 已被占用（人工误建） → drop_collection 后重试

## 13. Done criteria

1. ✅ V014 + 4 个新文件 + 3 个修改文件
2. ✅ 5+ 个新单测过；既有不退化
3. ✅ ensure_company_profiles_collection / drop_company_profiles_collection 可调
4. ✅ run_milvus_backfill.py --domain company --dry-run 输出 JSON 报告
5. ✅ W10-3 / W10-4 后续可基于本 spec 接入（不阻塞）

## 14. Open questions（spec 已锁）

| 问题 | 决策 |
|---|---|
| 单 vector vs dual vector？ | 单 vector（user 锁定 "拼接"） |
| description 是否参与 embed？ | 降级路径，profile/tech 全空时使用 |
| 新列在 W10-4 前如何填？ | 不填；NULL 是合法状态；embed 走 description fallback |
| company_id 长度？ | 64（同 V002 schema） |
| 跑全量需多久？ | ~1037 公司 × 1.5 sec/embed ≈ 25 min（claude 后续操作） |
