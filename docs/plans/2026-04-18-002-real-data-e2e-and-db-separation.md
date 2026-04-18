---
title: Real-Data E2E Validation and Mock/Real Database Separation
date: 2026-04-18
status: active
owner: claude
extends:
  - docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
---

# Real-Data E2E and DB Separation Plan

## 0. 背景

到 Round 7 为止，所有测试（38 tests V001/V002/seed_loader/company + 6 canonical_writer）
都**mock 数据**跑在共享的 `miroflow_test` 数据库里。pytest teardown 会
`alembic downgrade base`，销毁数据。**好消息**：pytest 自身隔离干净；
**坏消息**：每次跑测试都冲掉真实导入的数据，真实 E2E 需要反复重跑
`run_phase1_e2e.sh` 才能恢复。

更深的问题是：项目目标是回答 `docs/测试集答案.xlsx` 的真实问题，**只跑合成数据
无法证明 pipeline 对真实教授/企业有用**。必须有独立的真实数据 E2E 门槛。

## 1. 两个目标

1. **Mock 与 Real 数据物理隔离**——pytest 跑 mock 永不动 real 库；real E2E 跑真数据永不被 pytest 清空。
2. **真实数据 E2E 门槛**（按域）：
   - Company：xlsx → canonical → news refresh → Serving API 链路 end-to-end 能对真实企业产出完整画像
   - Professor：roster URL → discovery → enrichment → paper_collector → canonical_writer 对真实深圳 STEM 教授能稳产 canonical rows
   - Web Search API：验证 google/bing/serper（以及通过代理 `100.64.0.14:7890`）可用
   - Cross-domain：典型跨域问题（"丁文伯参与的公司"）返回正确

## 2. Database 分层策略

引入**三套 Postgres database**，同一个 pgtest 容器内：

| DB Name | 用途 | 生命周期 | 谁在用 |
|---|---|---|---|
| `miroflow_test_mock` | pytest 套件专用。所有 mock fixture 都用这个。teardown 清空。 | 每次 pytest 会话 | `pytest apps/*/tests/` |
| `miroflow_real` | 真实数据常驻。xlsx 导入、professor 真实 crawling、news refresh 的数据都落这里。手动 downgrade 才清空。 | 长期 | `scripts/run_real_e2e_*.sh` + 演示 |
| `miroflow_scratch` | 临时探查/演示/本机 dev，可任意销毁 | 按需 | 开发者 ad-hoc |

**具体变更**：

1. `apps/miroflow-agent/scripts/run_phase1_e2e.sh` 改为用 `miroflow_real`
2. pytest fixture 默认 DSN 指向 `miroflow_test_mock`（env 变量兜底）
3. 新增 `scripts/run_real_e2e_company.sh`、`run_real_e2e_professor.sh`、`run_real_e2e_web_search.sh`
4. 文档：在 CLAUDE.md 补 Database Conventions 小节

**初始化**：

```bash
sudo -n docker exec pgtest psql -U miroflow -c "CREATE DATABASE miroflow_test_mock;"
sudo -n docker exec pgtest psql -U miroflow -c "CREATE DATABASE miroflow_real;"
sudo -n docker exec pgtest psql -U miroflow -c "CREATE DATABASE miroflow_scratch;"

# 三个 DB 都装 extensions
for db in miroflow_test_mock miroflow_real miroflow_scratch; do
  sudo -n docker exec pgtest psql -U miroflow -d $db -c "CREATE EXTENSION IF NOT EXISTS vector;"
  sudo -n docker exec pgtest psql -U miroflow -d $db -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
done

# Real DB 一次性 upgrade + seed
DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run alembic upgrade head
DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python -m src.data_agents.storage.postgres.seed_loader
```

## 3. Real-Data E2E 脚本（按域）

### 3.1 Company Real E2E（`scripts/run_real_e2e_company.sh`）

核心链路：xlsx → canonical → （TODO Phase 2）news refresh → 查询 API

验收：
- [ ] 跑一次导入 `docs/专辑项目导出1768807339.xlsx`，`miroflow_real.company` 有 1024 行
- [ ] 查询若干具体公司（极智视觉、旭宏医疗、普渡科技等）的 detail API，字段齐
- [ ] 融资事件≥ 500 条
- [ ] 导入**第二次**相同文件：idempotent（no duplicate rows），import_batch.run_status='skipped'
- [ ] 【Phase 2 就绪后】针对 top 20 公司运行 news refresh，每家 ≥1 条近 30 天新闻

### 3.2 Professor Real E2E（`scripts/run_real_e2e_professor.sh`）

核心链路：roster URL → discovery → enrichment → canonical_writer → canonical 表

前提：
- pipeline_v2 能通过代理 `100.64.0.14:7890` 访问目标高校网页
- Round 6 的 canonical_writer 能消化 `EnrichedProfessorProfile`
- 需要 `professor/release.py` 的 canonical 写入分支（Round 7.5 新增）

步骤：
1. 取 `docs/教授 URL.md` 的一个最小集合（例如只南科大 SIGS 或只港中文深圳 3 位教授）先 smoke
2. 跑 `uv run python scripts/run_professor_enrichment_v2_e2e.py --institution SUSTech --limit 3`
3. 跑新的 canonical bridge（一次性脚本 `scripts/run_professor_canonical_backfill.py`）：从 enriched.jsonl 读 → 调 canonical_writer → 写入 `miroflow_real`
4. 查 `miroflow_real.professor`，至少 3 行
5. 查 `professor_fact`，每位教授 ≥ 1 research_topic fact
6. 查 `professor_paper_link`，至少 1 verified link（来自 paper_collector 官方 publication page 证据）

**验收关键**：evidence_url 链条走通（即每条 fact 点开能看到原始 URL 和抓取时间）。

### 3.3 Web Search API 可用性（`scripts/run_real_e2e_web_search.sh`）

检查 `libs/miroflow-tools/src/miroflow_tools/mcp_servers/` 下三个 search 提供商：

- google_search
- sogou_search
- serper

步骤：
1. 清代理 env 后设 `100.64.0.14:7890` 专用
2. 运行每个 provider 一条测试 query（"深圳 云鲸智能"）
3. 验证返回合理结果（≥3 条结果）
4. 记录每个 provider 的：延迟、速率限制、错误率

**不通过即算硬阻塞 chat v3+ 的 online_freshness_patch**，必须修。

### 3.4 跨域 Real E2E（`scripts/run_real_e2e_cross_domain.sh`）

只在 Round 7.5 和 team_resolver（未来 Round）都完成后才能跑。

验收：
- 查 "丁文伯" → 返回清华 SIGS 副教授 + 无界智航（professor_company_role）
- 查 "优必选 专利" → 返回优必选公司 + N 个 company_patent_link

## 4. 测试数据隔离规则（pytest 侧）

### 4.1 Fixture 契约

修改 `tests/postgres/conftest.py`、`tests/professor/test_canonical_writer.py` 的 `pg_dsn` fixture：

```python
DEFAULT_TEST_DSN = "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock"

@pytest.fixture(scope="session")
def pg_dsn() -> str:
    return os.environ.get("DATABASE_URL_TEST") or DEFAULT_TEST_DSN
```

新的 env 变量 `DATABASE_URL_TEST` 专给测试，`DATABASE_URL` 留给 real E2E 脚本和手动查询。这样**同一台机器上两个活动同时进行**不会互相踩踏。

### 4.2 Mock 数据来源规则

- **合成输入**：单元测试用的 `EnrichedProfessorProfile`、`CompanyRow`、`PaperStagingRecord` 等 Pydantic 实例**必须**在测试文件里本地构造。不得 read real xlsx 或 real crawl output。
- **小样本真实输入**：集成测试（`test_canonical_import_xlsx.py`）可以读 `docs/专辑项目导出1768807339.xlsx`，但目标库必须是 `miroflow_test_mock`，跑完 downgrade。
- **禁止**：测试套件在 `miroflow_real` 写入任何数据。

### 4.3 CI 约束

`.github/workflows/postgres-tests.yml` 里：

```yaml
env:
  DATABASE_URL_TEST: postgresql+psycopg://miroflow:miroflow@localhost:5432/miroflow_test_mock
  # 明确不设 DATABASE_URL，防止测试意外指向"真"库
```

## 5. 当前已知缺口与 TODO

| 缺口 | 影响 | 补救 Round |
|---|---|---|
| `professor/release.py` 未调用 canonical_writer | Professor canonical 表在 real DB 没有任何真实数据 | Round 7.5 |
| `news_refresh.py` 未实现 | 无法演示投研级别 fresh news | Phase 2 |
| Chat API 不存在 | 端用户无法对话 | Round 8+（见 chat plan） |
| Web search 未 smoke 过 proxy | online_freshness_patch 可能拿不到结果 | 本计划 §3.3 作为最小动作先跑 |

## 6. 提议的执行顺序

1. **立即**（本会话可做）：
   - `§2` 初始化三个 DB
   - 迁移 `DATABASE_URL_TEST` env 到所有 conftest
   - `§3.3` Web search API 可用性 smoke test
   - 跑一次 `run_real_e2e_company.sh` 确认 company 实数导入在 `miroflow_real` 有效

2. **下一 Round**（Round 7.5）：
   - `professor/release.py` 加 canonical_writer 分支
   - 写 `scripts/run_real_e2e_professor.sh`
   - 跑真实教授 E2E（先取 3 位）

3. **之后**：
   - Round 8：chat-app v0
   - Phase 2：news refresh
   - Round 7.5 扩到全量深圳 STEM 高校

## 7. 成功指标

Phase 1 + Phase 3（到当前为止）算"完整打通"的标志：

- `miroflow_real.company` ≥ 1020 行
- `miroflow_real.professor` ≥ 10 行（至少 10 位有官方详情页锚定的教授）
- `miroflow_real.professor_paper_link` verified ≥ 30 行
- `miroflow_real.professor_company_role` ≥ 1 行（至少一个验证过的跨域关系，例如丁文伯→无界智航）
- Web search API 返回正常 ≥ 1 个 provider
- pytest `DATABASE_URL_TEST=... pytest -v` 57+ pass，**完全不触及** `miroflow_real`
