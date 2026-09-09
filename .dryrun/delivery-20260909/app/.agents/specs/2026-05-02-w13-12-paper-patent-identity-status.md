---
title: "W13-12: V020 paper / patent 加 identity_status（与 §5.5 hallucination prevention 对齐）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（alembic + writer wiring）
wave: Wave 13 follow-up
schema_source:
  - apps/miroflow-agent/alembic/versions/V003_init_professor_domain.py (professor identity_status reference)
  - apps/miroflow-agent/alembic/versions/V002_init_company_domain.py (company identity_status reference)
prd_anchor: docs/Data-Agent-Shared-Spec.md §5.5 hallucination prevention
---

# W13-12: V020 paper / patent 加 identity_status

## 1. Goal

实测 V019 后：

| 表 | identity_status | quality_status |
|---|---|---|
| professor | ✅ | ✅ (W13-6) |
| company | ✅ | ✅ (W13-6) |
| paper | ❌ | ✅ (W13-6) |
| patent | ❌ | ✅ (W13-6) |

`identity_status` 是 §5.5 hallucination prevention 的核心字段（标记"实体身份是否已经过 name-identity gate 验证"）。professor 用它拦 same-name 不同人；company 用它拦同名公司。paper / patent 同样需要：

- paper：DOI / arXiv ID 验证 → identity_status='confirmed'；仅标题猜测 → 'unverified'
- patent：patent_number 唯一 → 'confirmed'（默认；e2e 直接 INSERT 用此）

## 2. Non-goals

- **不**改 professor / company identity_status 现有逻辑
- **不**给 W13-3 patent writer 加复杂识别（patent_number 唯一已够强）

## 3. Schema (V020)

```python
revision = "V020"
down_revision = "V019"

VALID_IDENTITY = ("confirmed", "unverified", "rejected", "merged")

def upgrade():
    for table in ("paper", "patent"):
        op.add_column(
            table,
            sa.Column(
                "identity_status",
                sa.Text(),
                nullable=False,
                server_default="unverified" if table == "paper" else "confirmed",
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_identity_status",
            table,
            f"identity_status IN {VALID_IDENTITY!r}",
        )
        op.create_index(f"ix_{table}_identity_status", table, ["identity_status"])

def downgrade():
    for table in ("paper", "patent"):
        op.drop_index(f"ix_{table}_identity_status", table_name=table)
        op.drop_constraint(f"ck_{table}_identity_status", table_name=table)
        op.drop_column(table, "identity_status")
```

## 4. Writer wiring

### paper
- `homepage_paper_ingest.py`：title 解析命中 OpenAlex DOI → 'confirmed'；fallback 仅 LLM 解析 → 'unverified'
- `multi_source_crawler` (W12-5)：DOI / arXiv 命中 → 'confirmed'

### patent
- W13-3 `canonical_writer.upsert_patent`：patent_number 非空 → 'confirmed'；为空 → 'unverified'

## 5. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V020_add_identity_status_paper_patent.py
  apps/miroflow-agent/tests/storage/test_v020_migration.py

修改：
  apps/miroflow-agent/src/data_agents/paper/homepage_paper_ingest.py
    upsert_paper 时根据 title_resolution_source 设 identity_status
  apps/miroflow-agent/src/data_agents/patent/canonical_writer.py
    upsert_patent dict 加 identity_status；'confirmed' if patent_number else 'unverified'
  apps/miroflow-agent/src/data_agents/patent/release.py
    record_to_patent_dict 加 identity_status
  apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer.py
    测试 confirmed / unverified 分支
```

## 6. Validation

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=... uv run pytest tests/storage/test_v020_migration.py \
                                       tests/data_agents/patent/ -v

# alembic upgrade real
DATABASE_URL=...miroflow_real uv run alembic upgrade head
# 检查 paper / patent 全部 identity_status 已设
```

## 7. Done criteria

1. ✅ V020 upgrade + downgrade OK
2. ✅ paper / patent 默认 identity_status 设置正确
3. ✅ writer wiring 单测 confirmed / unverified
4. ✅ 既有 W13-3 e2e regression 不退化

## 8. 顺序

W13-12 在 W13-D2 / W13-13 之前 land（让 retrieval 后续可按 identity_status 过滤）。
