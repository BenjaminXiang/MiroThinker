# Agentic RAG 操作指南

> 面向运维人员的实操手册。系统代码已全部 ship；本文讲 **如何把它跑起来**。
>
> 配套参考：
> - `docs/plans/2026-04-20-003-agentic-rag-execution-plan.md` — 执行计划 (M0-M6)
> - `docs/solutions/integration-issues/homepage-paper-ingest-dogfood-template-2026-04-22.md` — 首次跑完后填的验收日志
> - `CLAUDE.md` → "Agentic RAG env vars (M4+)" — 环境变量清单

## 系统总览

```
┌────────────────────────────────────────────────────────────────────┐
│                     Postgres (DATABASE_URL)                         │
│   professor  ←─→  professor_paper_link  ←─→  paper                  │
│                                                 │                    │
│                                                 ↓                    │
│                                      paper_full_text (V011)         │
│                                      paper_title_resolution_cache   │
│                                      professor_orcid                │
└────────────────────────────────────────────────────────────────────┘
                                ↓
                    ┌───────────────────────┐
                    │ Milvus (MILVUS_URI)   │
                    │  professor_profiles   │  ← already populated
                    │  paper_chunks         │  ← M3 backfill populates
                    └───────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│ admin-console (FastAPI)                                             │
│   /api/chat                                                         │
│     B: retrieve(prof)                                               │
│     D: retrieve(prof+paper) + SQL(company)                          │
│     E: retrieve(paper) ── low conf ──→ Serper + rerank              │
└────────────────────────────────────────────────────────────────────┘
```

## 一次性前置准备

### 1. 依赖 + 环境变量

```bash
# 从仓库根目录
cd apps/miroflow-agent
uv sync

cd ../admin-console
uv sync
```

环境变量（写到 `.env` 或 shell）：

```bash
# 必选
export DATABASE_URL="postgresql://user:pass@host:5432/miroflow_real"
export SERPER_API_KEY="..."               # Serper E-route fallback

# 可选（有合理默认值）
export CHAT_USE_RETRIEVAL_SERVICE=on      # M4 flag；off 回退 SQL LIKE
export CHAT_E_WEB_FALLBACK_THRESHOLD=0.5  # E-route 置信度阈值
export MILVUS_URI=./milvus.db             # Milvus-Lite 本地文件

# 本地 LLM (embedding / reranker / gemma4) API key
# 任选其一设置，或写到 <repo-root>/.sglang_api_key 文件
export API_KEY="k8#pL2@mN9!qjfkew87@#$0204"
```

### 2. 应用 V011 迁移

从 `apps/miroflow-agent/` 目录：

```bash
# 先检查当前版本
DATABASE_URL=$DATABASE_URL uv run alembic current
# → V010 或更早

# 升级到 V011
DATABASE_URL=$DATABASE_URL uv run alembic upgrade V011

# 确认三张新表
psql "$DATABASE_URL" -c "
  SELECT tablename FROM pg_tables
  WHERE tablename IN ('paper_full_text',
                      'paper_title_resolution_cache',
                      'professor_orcid');
"
```

### 3. 冒烟验证

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=$DATABASE_URL uv run pytest \
  tests/storage/test_v011_migration.py \
  tests/storage/test_paper_full_text_writer.py \
  tests/storage/test_title_resolution_cache.py \
  tests/storage/test_professor_orcid_writer.py \
  -n0
# → 期望 33 passed, 0 skipped
```

## 首次运行完整流水线

### 阶段 1 — 抓主页论文 (M2.4)

```bash
cd apps/miroflow-agent

# Dry-run 先看 10 个老师的论文抓取情况，不写库
DATABASE_URL=$DATABASE_URL uv run python scripts/run_homepage_paper_ingest.py \
  --dry-run --limit 10

# 选 5 个跑真实写入
DATABASE_URL=$DATABASE_URL uv run python scripts/run_homepage_paper_ingest.py \
  --limit 5

# 检查结果
psql "$DATABASE_URL" -c "
  SELECT evidence_source_type, count(*)
  FROM professor_paper_link
  GROUP BY evidence_source_type;
"
# → 期望看到 personal_homepage 这一行的计数增加

psql "$DATABASE_URL" -c "
  SELECT source, count(*) FROM paper_full_text GROUP BY source;
"
# → arxiv / openalex / failed 分布
```

如果 5 个 prof 平均 ≥ 15 篇论文（003 §R3 的验收门槛），展开跑全量：

```bash
# 全量跑（~800 profs，可能 1-2 小时；支持 --resume）
DATABASE_URL=$DATABASE_URL nohup uv run python scripts/run_homepage_paper_ingest.py \
  > logs/homepage_ingest.out 2>&1 &
```

### 阶段 2 — Milvus 向量化 (M3)

```bash
cd apps/miroflow-agent

# 先灌 100 篇论文 chunks 看看
DATABASE_URL=$DATABASE_URL uv run python scripts/run_milvus_backfill.py \
  --domain=paper --limit=100 --milvus-uri=./milvus.db

# 全量
DATABASE_URL=$DATABASE_URL uv run python scripts/run_milvus_backfill.py \
  --domain=paper --milvus-uri=./milvus.db
```

### 阶段 3 — 画像反向增强 (M6)

```bash
cd apps/miroflow-agent

# Dry-run 看效果
DATABASE_URL=$DATABASE_URL uv run python scripts/run_profile_summary_reinforcement.py \
  --dry-run --limit 10

# 真实写入
DATABASE_URL=$DATABASE_URL uv run python scripts/run_profile_summary_reinforcement.py \
  --limit 50
```

### 阶段 4 — 启动 Chat 服务 (M4)

```bash
cd apps/admin-console
DATABASE_URL=$DATABASE_URL \
MILVUS_URI=/path/to/apps/miroflow-agent/milvus.db \
SERPER_API_KEY=$SERPER_API_KEY \
CHAT_USE_RETRIEVAL_SERVICE=on \
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

测试 B/D/E 三类查询：

```bash
# B — 语义 prof 检索
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"南科大做机器人的教授"}' | jq

# D — 跨域
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"深圳做AI的教授和企业"}' | jq

# E — 知识问答 + Serper fallback
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"DeepSeek V3 使用什么训练方法"}' | jq
```

## 日常运维

### 回滚

```bash
# 关 RetrievalService（chat 立即回退 SQL LIKE + rule-based FAQ）
export CHAT_USE_RETRIEVAL_SERVICE=off
# 重启 chat 服务即可
```

Milvus 集合出问题：

```bash
# Drop paper_chunks 集合（不影响 professor_profiles）
cd apps/miroflow-agent
uv run python -c "
from pymilvus import MilvusClient
from src.data_agents.storage.milvus_collections import drop_paper_chunks_collection
client = MilvusClient(uri='./milvus.db')
drop_paper_chunks_collection(client)
"

# 然后重新 M3 backfill
```

V011 迁移回滚（极端情况）：

```bash
cd apps/miroflow-agent
DATABASE_URL=$DATABASE_URL uv run alembic downgrade V010
# paper_full_text / paper_title_resolution_cache / professor_orcid 三张表都会被 drop
# 业务数据（professor / paper / professor_paper_link）不受影响
```

### 增量更新

M2.4 / M3 backfill 都支持 `--resume`。每次运行会在
`logs/data_agents/.../<run_id>.jsonl` 写 checkpoint，下次带 `--resume` 跳过已处理。

M6 summary reinforcement 也有 `--resume`。

### 监控

关键表的行数 + 更新频率：

```sql
-- 论文覆盖率
SELECT
  (SELECT count(*) FROM paper) AS paper_total,
  (SELECT count(*) FROM paper_full_text) AS with_full_text,
  round(100.0 * (SELECT count(*) FROM paper_full_text) /
        NULLIF((SELECT count(*) FROM paper), 0), 2) AS pct_covered;

-- Link 按来源分布
SELECT evidence_source_type, count(*)
FROM professor_paper_link
GROUP BY evidence_source_type
ORDER BY count(*) DESC;

-- 最近的 pipeline_issue
SELECT issue_type, severity, count(*)
FROM pipeline_issue
WHERE created_at > now() - interval '24 hours'
GROUP BY issue_type, severity
ORDER BY count(*) DESC;
```

## 常见问题

- **"retrieve 返回空"** → Milvus 集合为空。先跑 `run_milvus_backfill.py`。或者 `CHAT_USE_RETRIEVAL_SERVICE=off` 临时回退。
- **"Serper 配额耗尽"** → 提高 `CHAT_E_WEB_FALLBACK_THRESHOLD` 减少 E-route 触发 web search，或换 key。
- **"Gemma4 超时"** → 检查 `100.64.0.27:18005` / `18006` 端点是否可达；代理污染？确认 `trust_env=False` 已在所有新客户端生效。
- **"论文被 identity gate 拒了"** → 检查 `ProfessorContext.name_variants` 是否填了（M1），以及 `professor_orcid` 是否有该 prof 的 ORCID 行（M1 shortcut）。非主页路径才会经过这道门；主页路径直接接受。

## 运维成本参考（估算）

| 任务 | 规模 | 一次性耗时 | 备注 |
|---|---|---|---|
| V011 迁移 | 一次 | < 1s | 空表 |
| homepage ingest 全量 | ~800 profs | 1-2 h | 受限于 arxiv 3s 节流 |
| M3 paper_chunks backfill 全量 | ~8k papers × 1-3 chunks | 30 min | 受 embed 端点吞吐影响 |
| M6 summary reinforcement 全量 | ~800 profs | ~30 min | gemma4 每次 ~2s |
| chat 单次请求 | 1 | P50 < 1.5s | embed + 2 ANN + rerank + gemma |

## 迭代路线

所有 003 计划的 milestone 已 ship。进一步工作是基于实跑数据调优：

- **M1.4 eval set** — 跑过 dogfood 后用真实结果反向标注，量化 identity gate v2 的提升
- **M5.2 reranker 调优** — 看 E-route top-3 web hits 质量，决定是否要调整 Qwen3-Reranker-8B 的 batch size
- **Company/Patent 向量化** — 等对应数据管线成熟后，把 `milvus_collections.py` 扩展出 `company_profiles` / `patent_profiles`
- **ProfessorVectorizer 的增量更新** — M6 写新的 summary 后自动 re-embed，不用全量 backfill
