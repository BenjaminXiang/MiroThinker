---
title: "W10-2: Patent Milvus collection + 嵌入"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 10
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w10-1-company-milvus.md  # 同模式
prd_anchor: docs/Patent-Data-Agent-PRD.md §模块四 R1
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §6 检索
---

# W10-2: Patent Milvus collection + 嵌入

## 1. Goal

PRD §模块四 R1 要求：专利能按"无人机自主避障"等技术语义召回。当前 Postgres `patent` 已有 `abstract_clean` + `technology_effect`，但 Milvus 无 patent collection → A/D 类型查专利只能走 SQL 文本匹配（命中率低）。

**本 spec**：
- 新建 `patent_profiles` Milvus 4096-dim collection
- 新建 `src/data_agents/patent/vectorizer.py`（mirror professor.vectorizer 单 vector）
- run_milvus_backfill.py 加 `--domain patent`
- 嵌入文本 = `abstract_clean`（user 锁定 "仅 summary_text" → 解释为专利唯一权威 summary 字段）

## 2. Non-goals

- **不**改 patent canonical schema（已有所需字段）
- **不**做 RetrievalService 接入（W10-3）
- **不**改 admin-console / React
- **不**清洗 abstract_clean 中的 OCR/格式残留（已是 _clean 字段）

## 3. User-visible behavior

| 用户面 | 行为 |
|---|---|
| 跑 `run_milvus_backfill.py --domain patent` | 读 Postgres patent 表 → embed → 写 Milvus `patent_profiles` |
| MilvusClient.has_collection("patent_profiles") | True |
| 抽样 50 patent search by abstract | 自一致性 top-10 包含自身 |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/src/data_agents/patent/vectorizer.py
  apps/miroflow-agent/tests/data_agents/patent/test_vectorizer.py
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_patent.py

修改：
  apps/miroflow-agent/src/data_agents/storage/milvus_collections.py
    + PATENT_PROFILES_COLLECTION 常量
    + ensure_patent_profiles_collection / drop_patent_profiles_collection
  apps/miroflow-agent/scripts/run_milvus_backfill.py
    + --domain patent 路径 + _backfill_patent_domain()
```

## 5. Architecture / Data flow

```
Postgres patent
  ↓ SELECT patent_id, patent_number, title_clean, abstract_clean,
           technology_effect, patent_type, ipc_codes
  ↓
_compose_patent_text(row)  -- §6.1
  ↓
EmbeddingClient.embed_batch()
  ↓
Milvus patent_profiles collection
```

## 6. Interface contracts

### 6.1 `_compose_patent_text(row)`

```python
def _compose_patent_text(row: dict) -> str:
    title = (row.get("title_clean") or "").strip()
    abstract = (row.get("abstract_clean") or "").strip()
    technology_effect = (row.get("technology_effect") or "").strip()

    parts: list[str] = []
    if title:
        parts.append(title)
    if abstract:
        parts.append(abstract[:1800])
    elif technology_effect:
        # 罕见：abstract 为空时退到 effect
        parts.append(technology_effect[:1800])

    return "\n".join(parts)
```

注：user 锁定 "仅 summary_text"。专利无 `summary_text` 字段；最贴近的语义字段是 `abstract_clean`（专利摘要）。`title_clean` 加进来作为前缀（embedding 头部更稳定）。

### 6.2 Milvus collection schema

```
PATENT_PROFILES_COLLECTION = "patent_profiles"

fields:
  id (VARCHAR PK, max_length=64)               -- patent_id
  patent_number (VARCHAR max_length=64)
  title (VARCHAR max_length=512)
  abstract (VARCHAR max_length=2048)
  technology_effect (VARCHAR max_length=1024)
  patent_type (VARCHAR max_length=32)
  ipc_codes (VARCHAR max_length=512)            -- JSON-encoded list
  profile_vector (FLOAT_VECTOR dim=4096)

index:
  field_name="profile_vector"
  index_type="AUTOINDEX"
  metric_type="COSINE"
```

## 7. Invariants

- 4096-dim Qwen3-Embedding-8B
- AUTOINDEX + COSINE
- `id` = `patent_id`
- 单 vector
- abstract_clean 为空 + technology_effect 为空 + title 为空 → 跳过该专利
- ipc_codes 序列化 JSON 字符串入 Milvus（非数组）
- collection 创建 idempotent

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| abstract_clean 全空 (rare) | 用 technology_effect；都空则 跳过 |
| title 含特殊字符（IPC 缩写、希腊字母） | 不清洗；embedding 自处理 |
| abstract > 1800 chars | slice |
| ipc_codes is None | "[]" |
| 重复 patent_id（理论不应发生） | upsert 覆盖 |
| identity 软删（无标记） | 不过滤 |

## 9. Validation commands

```bash
cd apps/miroflow-agent

# 单测
uv run pytest tests/data_agents/patent/test_vectorizer.py \
              tests/scripts/test_run_milvus_backfill_patent.py \
              -n0 --no-cov -v

# 既有不退化
uv run pytest tests/data_agents/patent/ tests/scripts/ -n0 --no-cov

# dry-run（claude 操作）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_milvus_backfill.py \
  --domain patent --milvus-uri ./milvus.db --dry-run
```

## 10. Expected evidence

1. vectorizer 单测过；run_milvus_backfill_patent 单测过
2. ensure / drop helper 可被 import 调
3. dry-run 输出含 missing_fields = expected_fields（首次跑前）
4. claude 操作：跑全量 patent (~ 数百 patent；具体数 待 SELECT count(*) 后验证)
5. 抽样 5 patent search → top-10 含自身

## 11. Migration / rollback

- 无 schema 变更；无 alembic
- collection drop 与 W10-1 同模式

## 12. Stop conditions

- abstract_clean 全空率高（> 50%） → 数据质量问题，escalate
- ipc_codes 序列化失败 → 单测捕获

## 13. Done criteria

1. ✅ vectorizer + ensure/drop helper + run_milvus_backfill 改动
2. ✅ 单测全过；既有不退化
3. ✅ collection 可创建 / drop / 上写

## 14. Open questions（spec 已锁）

| 问题 | 决策 |
|---|---|
| 单 vector vs dual？ | 单 vector |
| 嵌入字段？ | abstract_clean 主，title_clean 前缀，technology_effect 兜底 |
| ipc_codes 入 Milvus？ | 入（JSON 字符串），便于后续 W10-3 按 IPC 过滤 |
| inventors / applicants 入 Milvus？ | 不入（ID 检索走 Postgres，不走语义） |
