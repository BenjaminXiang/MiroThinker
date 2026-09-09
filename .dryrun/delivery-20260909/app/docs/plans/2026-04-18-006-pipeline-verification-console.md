---
title: Pipeline 正确性验证控制台（Round 8c, 三 PR）
date: 2026-04-18
status: draft-pending-review
owner: claude
extends:
  - docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
  - docs/plans/2026-04-18-004-admin-console-professor-and-ui.md
  - docs/plans/2026-04-18-005-data-quality-guards-and-identity-gate.md
reviewers_required:
  - plan-ceo-review
  - plan-eng-review
---

# Pipeline 正确性验证控制台

## 0. 用户意图（来自 @Benjamin 最终确认）

"人机审核台，更多的作用在开发阶段，实际使用阶段是 bad cases 追踪。"

这是**pipeline 正确性的验证工具**，不是数据维护台。管理员打开这台子是为了回答：

1. 我们 pipeline 对某机构的覆盖率够吗？是否漏人？
2. 某位教授的字段跟官网能不能对上？
3. 随机抽 10 位教授 5 篇论文，归属对不对？
4. 出错的这条记录，是 pipeline 哪一步写的、哪一步漏掉的？
5. 遇到 bad case → 一键标记 → 直接驱动 pipeline 修复（成为下一轮 Round 7.x 的输入）

非目标：**不**做异常评分 / 多 LLM 共识 / professor-level 审核工作流。

## 1. 当前 schema 已有但未暴露的 provenance

| 对象 | 已有字段 | 当前 API 是否返回 |
|---|---|---|
| `professor.primary_official_profile_page_id` → `source_page.url` | ✅ 在表 | ❌ |
| `professor_affiliation.source_page_id` → `source_page.url, page_role, fetched_at` | ✅ | ❌ |
| `professor_fact.source_page_id, evidence_span, confidence` | ✅ | ❌ |
| `professor_paper_link.evidence_page_id, evidence_api_source, match_reason, rejected_reason, topic_consistency_score, verified_by, verified_at, is_officially_listed` | ✅ | 部分 |
| `paper.canonical_source, openalex_id, doi` | ✅ | ✅ 已返 |

这意味着 **8c-A 几乎不写新逻辑，只扩 SELECT + 加 JOIN**。

## 2. 三个 PR（Codex #4 修正：8c-A 必须先 merge，8c-B/8c-C 可并行）

### 8c-A — Provenance 透出（纯后端查询扩展）

**目标**：详情页每个字段可点击查看来源 URL / 抓取时间 / 提取片段。

**文件改动**：
- `apps/admin-console/backend/api/data.py` — 新 SQL + Pydantic 模型扩展
- `apps/admin-console/tests/test_professor_api.py`，`test_paper_api.py` — 断言新字段存在

**API 契约变更（附带新增字段）**：

```python
class ProfessorFactValue(BaseModel):
    # existing
    value_raw: str
    value_normalized: str | None
    value_code: str | None
    confidence: float | None
    evidence_span: str | None
    # NEW
    source_page_url: str | None
    source_page_role: str | None
    source_page_fetched_at: datetime | None

class ProfessorAffiliation(BaseModel):
    # existing
    institution: str
    title: str | None
    ...
    # NEW
    source_page_url: str | None
    source_page_role: str | None

class PaperSummaryWithProvenance(BaseModel):
    # existing (reuse PaperSummary)
    paper_id: str
    title_clean: str
    ...
    topic_consistency_score: float | None
    # NEW
    link_status: str
    match_reason: str | None
    rejected_reason: str | None
    verified_by: str | None
    verified_at: datetime | None
    evidence_api_source: str | None
    evidence_page_url: str | None
    is_officially_listed: bool

class ProfessorDetailResponse(BaseModel):
    professor: Professor
    affiliations: list[ProfessorAffiliation]
    facts_by_type: dict[str, list[ProfessorFactValue]]
    # CHANGED: 三桶代替 verified+candidate only
    verified_papers: list[PaperSummaryWithProvenance]
    candidate_papers: list[PaperSummaryWithProvenance]
    rejected_papers: list[PaperSummaryWithProvenance]   # NEW
    # NEW
    primary_profile_url: str | None
    research_directions_source: str | None  # official_only | paper_driven | merged
    source_pages_used: int
```

**SQL 模式**：每个返回字段的 query 都 `LEFT JOIN source_page` 拿 url + page_role + fetched_at。

**验证清单**：
- [ ] `GET /api/data/professors/{id}` 返 三桶 paper 数组
- [ ] 每条 fact / affiliation / paper_link 都有 `source_page_url` 或 None
- [ ] `rejected_papers` 按 `rejected_at DESC` 倒排
- [ ] 旧的 test 断言还绿（向后兼容：新增字段不破坏现有契约）

### 8c-B — Pipeline 覆盖率与来源分布（Codex #2/#3/#11 修正）

**目标**：一页 `/pipeline` 展示"哪个机构的 pipeline 坏了、论文来自哪些源"。

**新 API**（Codex #11: anomalies 合进 coverage 的可选参数；#2: funnel 改名 source-breakdown）：

```python
@router.get("/api/pipeline/coverage-by-institution", response_model=list[InstitutionCoverage])
def list_coverage(anomaly_only: bool = False):
    """
    默认返全量机构；anomaly_only=True 仅返阈值跑偏的子集
    （rejection_rate > 60% 或 with_verified_papers / professor_count < 0.2）。
    """

class InstitutionCoverage(BaseModel):
    institution: str
    professor_count: int                  # COUNT DISTINCT prof
    with_verified_papers: int
    with_research_directions: int
    empty_authors_papers: int
    identity_gate_rejection_rate: float
    avg_topic_consistency_score: float | None
    anomaly_flags: list[str]              # 空列表 = 正常；非空 = 命中阈值的问题标签

@router.get("/api/pipeline/source-breakdown", response_model=SourceBreakdown)
class SourceBreakdown(BaseModel):
    """
    不是 funnel（不同阶段对象粒度不一致，不单调递减）。
    这是"link 按源头的计数分布"，用于回答"我们的 link 有多大比例来自 OpenAlex 自动匹配 vs 官网抓取 vs 人工确认"。
    """
    by_evidence_api_source: dict[str, int]  # e.g. {"openalex": 5400, "official_page": 1420, ...}
    by_verified_by: dict[str, int]          # e.g. {"llm_auto": 4631, "rule_auto": 667, "human_reviewed": 12}
    by_link_status: dict[str, int]          # {"verified": N, "rejected": M, "candidate": K}
```

**Codex #3 修正：机构去重逻辑**  
`professor_affiliation` 一位教授可多行（主/历史/挂靠）。聚合必须按**当前主机构**：

```sql
-- 每位教授只在其当前主机构记一次
WITH primary_aff AS (
  SELECT DISTINCT ON (professor_id) professor_id, institution
    FROM professor_affiliation
   WHERE is_primary = true AND is_current = true
   ORDER BY professor_id, created_at DESC
)
SELECT pa.institution,
       COUNT(DISTINCT pa.professor_id) AS professor_count,
       ...
  FROM primary_aff pa
  LEFT JOIN ...
 GROUP BY pa.institution;
```

**UI**：
- 扩展 `backend/static/browse.html` 加 `#pipeline` tab
- 表 1：institution × 7 指标，可按 column 排序，`anomaly_flags` 非空的行高亮红
- 表 2（小）：source-breakdown 3 个字典渲染成三列柱状数字

**验证清单**：
- [ ] `coverage-by-institution` 返回 9 所深圳高校（按 primary+current 去重）
- [ ] `coverage-by-institution?anomaly_only=true` 仅返 `anomaly_flags` 非空的子集
- [ ] `source-breakdown.by_evidence_api_source` 求和 == `professor_paper_link` 总数
- [ ] 多机构挂靠的教授只在主机构计一次（断言某个已知跨任的教授不重复）

### 8c-C — 随机抽样 + pipeline_issue 记录（人的出口）

**目标**：管理员 1 小时抽 30 位教授，积累 10-20 条 pipeline 错误报告，直接交付给下一轮 Round 7.x。

**新表**（含 Codex #5/#6/#7/#8 + Eng E1/E2 修正）：

```sql
CREATE TABLE pipeline_issue (
    issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- target reference (至少一个非空 — Codex #7)
    professor_id text REFERENCES professor(professor_id) ON DELETE SET NULL,  -- Codex #8
    link_id uuid REFERENCES professor_paper_link(link_id) ON DELETE SET NULL, -- Eng E2
    institution text,

    -- classification
    stage text NOT NULL CHECK (stage IN (
        'discovery',           -- roster 没发现这位
        'name_extraction',     -- 名字抓错
        'affiliation',         -- 机构/职称错
        'paper_attribution',   -- 论文归属错
        'paper_quality',       -- paper 本身是垃圾
        'research_directions', -- 研究方向不对
        'identity_gate',       -- gate 判错
        'coverage',            -- 整机构漏
        'data_quality_flag'    -- 未分类的通用质量标（Eng E1 合并 review_flag）
    )),
    severity text NOT NULL CHECK (severity IN ('high','medium','low')),
    description text NOT NULL,
    description_hash text GENERATED ALWAYS AS (md5(description)) STORED,  -- Codex #6

    -- 证据快照 (Codex #5)
    -- 报告时当场 dump paper/fact/link/affiliation 的关键字段，
    -- 后续 pipeline 重跑后还能还原现场
    evidence_snapshot jsonb,

    -- lifecycle
    reported_by text NOT NULL,
    reported_at timestamptz NOT NULL DEFAULT now(),
    resolved boolean NOT NULL DEFAULT false,
    resolved_at timestamptz,
    resolution_notes text,
    resolution_round text,            -- 解决它的 Round 标识（7.16, 7.17 等）

    -- Codex #7: 至少一个 target 非空
    CONSTRAINT ck_pipeline_issue_has_target CHECK (
        professor_id IS NOT NULL OR link_id IS NOT NULL OR institution IS NOT NULL
    )
);

-- Codex #6: 防重不错杀——同人同类问题但描述不同仍允许
CREATE UNIQUE INDEX uq_pipeline_issue_open
    ON pipeline_issue (
        COALESCE(professor_id,''),
        COALESCE(link_id::text,''),
        COALESCE(institution,''),
        stage,
        reported_by,
        description_hash
    ) WHERE resolved = false;

CREATE INDEX idx_pipeline_issue_unresolved ON pipeline_issue(resolved, reported_at DESC);
CREATE INDEX idx_pipeline_issue_stage ON pipeline_issue(stage, resolved);
-- Eng E3: 按教授列 bug 报告的索引
CREATE INDEX idx_pipeline_issue_professor
    ON pipeline_issue(professor_id) WHERE professor_id IS NOT NULL;
```

**`evidence_snapshot` 内容规范**（Codex #5）：

```json
{
  "type": "paper_link_rejection",
  "captured_at": "2026-04-18T12:34:56Z",
  "paper": {
    "paper_id": "PAPER-...",
    "title_clean": "...",
    "authors_display": "...",
    "venue": "...",
    "year": 2023,
    "source_url": "...",
    "doi": "...",
    "openalex_id": "..."
  },
  "link": {
    "link_status": "rejected",
    "match_reason": "...",
    "rejected_reason": "...",
    "topic_consistency_score": 0.35,
    "verified_by": null,
    "evidence_api_source": "openalex:..."
  },
  "professor": {
    "canonical_name": "...",
    "institution": "...",
    "research_topics": ["...", "..."]
  }
}
```

报告时后端从当前 DB 状态 dump 这些字段进 `evidence_snapshot`。pipeline 后续重跑修改数据，`pipeline_issue` 表独立保留现场。

**API**（含 Codex #4/#9 修正）：

```python
@router.get("/api/review/sample", response_model=list[ProfessorSample])
def sample_professors(
    institution: str | None = None,
    n: int = 10,
    seed: str | None = None,     # Codex #9: 可重放抽样
):
    """
    返回 n 位随机教授的一屏审核卡片，含 top papers、facts、provenance URLs。
    seed 传入则使用 `ORDER BY hashtext(professor_id || :seed)` 保证
    同一 seed 两次调用返回同一批——审核者刷新不丢现场。
    """

# Codex #4: 既然 8c-C 现在晚于 8c-A merge，直接复用 8c-A 的 PaperSummaryWithProvenance
class ProfessorSample(BaseModel):
    professor_id: str
    canonical_name: str
    canonical_name_en: str | None
    institution: str
    primary_profile_url: str | None
    research_directions: list[str]                             # top 5
    research_directions_source: str | None                     # paper_driven/official_only/merged
    verified_papers: list[PaperSummaryWithProvenance]          # top 3（8c-A 模型）
    rejected_papers: list[PaperSummaryWithProvenance]          # top 3
    facts_by_type: dict[str, int]

@router.post("/api/review/issues", response_model=PipelineIssue)
def report_issue(body: PipelineIssueCreate):
    """记录一条 pipeline bug，后端自动 dump evidence_snapshot。"""

class PipelineIssueCreate(BaseModel):
    professor_id: str | None = None
    link_id: str | None = None
    institution: str | None = None
    stage: Literal['discovery','name_extraction','affiliation',
                   'paper_attribution','paper_quality',
                   'research_directions','identity_gate','coverage',
                   'data_quality_flag']  # Eng E1 合并 flag
    severity: Literal['high','medium','low']
    description: str
    reported_by: str
    # evidence_snapshot 由后端按 target 自动生成，不由前端传

@router.get("/api/review/issues", response_model=list[PipelineIssue])
def list_issues(resolved: bool | None = None, stage: str | None = None, limit: int = 100):
    """列 unresolved issues by stage，驱动下一轮 fix。"""

@router.patch("/api/review/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, body: ResolveRequest):
    """解决一条 issue，记录 resolution_round。"""
```

**UI**：`/review.html` 新页
- 顶部按钮：`采样 10 位 [选机构]`
- 每张卡片：教授头图 / 名字 / 5 条方向 / 3 verified + 3 rejected papers（带 DOI 链接）/ 一行 "mark bug" 按钮
- 点 "mark bug" 弹 modal：选 stage、severity、描述、reporter 名字
- 右侧列 `unresolved issues`，按 stage 分组

**Alembic migration**：`alembic/versions/V006_pipeline_issue.py`（两行 CREATE TABLE + indices）

**验证清单**：
- [ ] `sample?institution=清华大学深圳国际研究生院&n=10` 返 10 位教授，含 provenance URL
- [ ] `POST /api/review/issues` 正确写入，约束生效（非法 stage 返 400）
- [ ] `GET /api/review/issues?resolved=false&stage=identity_gate` 能筛
- [ ] Alembic upgrade / downgrade 双向成功

## 3. 测试策略（Stage 3 TDD）

### 单元 / 集成测试（pytest + TestClient + miroflow_test_mock）
- `tests/test_professor_api.py` — 扩 3 断言：rejected_papers 桶存在、source_page_url 可见、primary_profile_url 可见
- `tests/test_paper_api.py` — 扩 2 断言：rejected 教授桶、evidence_api_source 可见
- `tests/test_pipeline_api.py` (新) — 覆盖 coverage-by-institution / stage-funnel / anomalies
- `tests/test_review_api.py` (新) — sample endpoint shape / issue CRUD / CHECK 约束

### Fixtures
- 沿用 `professor_postgres_client` 已有的 postgres_data_ready — mock DB 已有真实 10 教授 + 500 paper_staging
- 新 fixture `mock_pipeline_issues` 预置 3 条 issues 覆盖各 stage

### 覆盖目标
- 8c-A 新增 ~10 断言
- 8c-B 新增 ~8 断言
- 8c-C 新增 ~12 断言（含 alembic migration 测试）
- 总 +30 断言，预期全绿

## 4. 交付顺序（Codex #4/#10 修正后）

**Lane 1 先行（必须 merge 才能开 Lane 2）**：
- **8c-A**：provenance 透出 + `PaperSummaryWithProvenance` 模型
- **V006 migration**：`pipeline_issue` 表 + 索引

**Lane 2 与 Lane 3 并行**（都依赖 Lane 1 的 Pydantic 模型）：
- **Lane 2 / 8c-B**：coverage-by-institution + source-breakdown endpoints + `/pipeline` UI tab
- **Lane 3 / 8c-C**：`/api/review/sample`, `/api/review/issues`, `/review.html` UI

**为什么改顺序（Codex #4）**：8c-C 的 `ProfessorSample` 复用 8c-A 定义的 `PaperSummaryWithProvenance`。如果 A 和 C 并行，两个 Codex lane 会同时改 `backend/api/data.py` 的 Pydantic 模型命名空间，必然冲突。顺序化后 C 直接 import A 的模型。

**每个 Lane 的流水**（套用 CLAUDE.md Stage 3-7）：
1. **Stage 3 TDD** — Claude 写 test stubs
2. **Stage 4 Codex 实现** — 独立 worktree，`isolation: "worktree"`
3. **Stage 5 Claude 交叉验证** — 读 Codex 源码对照本 doc + test
4. **Stage 6 /ce:review** — 多代理安全 + 性能 review
5. **Stage 7 /ce:compound** — 沉淀到 docs/solutions/

## 4.0 已知限制（Codex #1/#12）

**#1 — pipeline stage trace 是后验推断，不是日志**。`stage-funnel` 和 `pipeline_issue.stage` 都是从 `evidence_api_source` + `verified_by` 字段反推，没有真正的 `run_id` / `pipeline_version` 记录。调试某条 link 具体是哪一次 v3 pipeline 跑产出的——本 round 不能回答。**追加到 TODOS**：Round 7.16 加 `pipeline_run` 表 + `run_id` FK 到 `professor_paper_link` / `professor_fact`。

**#12 — 性能断言不做数字阈值**。原计划有 `EXPLAIN ANALYZE <50ms` 断言，依赖测试环境和数据规模。撤掉。代之以**结构性约束**：
- 每个 endpoint 的 SQL 必须 O(1) 查询数（不允许 N+1）
- 新查询走 LATERAL JOIN 或单 CTE
- 依赖索引必须在 migration 中创建

测试里只断言"返回成功"，不断言 wall-time。生产负载再回来调优。

## 4.4 Eng Review 修正项（3 amendments）

### E1. 合并 `review_flag` 到 `pipeline_issue`（DRY, Code Quality Q2）
删除原设计中的独立 `review_flag` 表。所有 flag 按钮点击都 INSERT 到 `pipeline_issue`，用 `stage` 字段区分语义。这样一个队列、一个审核出口。

`stage` CHECK 扩展：加上 `'data_quality_flag'` 值，用于前端一键打标（当管理员不想分类 pipeline stage，只是说"这个看着不对"时）。

```sql
stage text NOT NULL CHECK (stage IN (
    'discovery','name_extraction','affiliation','paper_attribution',
    'paper_quality','research_directions','identity_gate','coverage',
    'data_quality_flag'   -- 新增：未分类的通用质量标
))
```

API 简化：`/api/review/flags` 端点全部删除；保留 `/api/review/issues`（原 8c-C 中已有）。前端 "一键 flag" 按钮 POST 到 `/api/review/issues` with `stage='data_quality_flag'`。

### E2. `pipeline_issue.link_id` FK（Arch Q1）
加 FK 防止 orphan：

```sql
CREATE TABLE pipeline_issue (
    ...
    link_id uuid REFERENCES professor_paper_link(link_id) ON DELETE SET NULL,
    ...
);
```
若某条 link 被人工硬删（清理脚本），关联的 issue 不会悬空——`link_id` 置 NULL，issue 本身保留供审阅。

### E3. `pipeline_issue(professor_id)` 索引（Perf Q3）
补一条部分索引，加速"列出这位教授的所有 bug 报告"查询：

```sql
CREATE INDEX idx_pipeline_issue_professor
    ON pipeline_issue(professor_id)
    WHERE professor_id IS NOT NULL;
```

## 4.5 CEO Review 修正项（HOLD SCOPE, 3 amendments）

### A1. `rejected_papers` 分页（Architecture Q1）
`ProfessorDetailResponse` 返 `rejected_papers` 时 `LIMIT 50` 并多带一字段：

```python
class ProfessorDetailResponse(BaseModel):
    ...
    rejected_papers: list[PaperSummaryWithProvenance]   # LIMIT 50
    rejected_papers_total: int                           # 用于前端 "还有 N 条"
```
SQL：`... ORDER BY ppl.rejected_at DESC NULLS LAST LIMIT 50` + 另一个 `COUNT(*)` CTE。

### A2. `review_flag` / `pipeline_issue` 防重复 flag（Error Map Q2）
两表都加 **partial unique index**，同一人对同一对象 unresolved 状态只允许一次：

```sql
CREATE UNIQUE INDEX uq_review_flag_open
  ON review_flag (object_type, object_id, flagged_by)
  WHERE resolved_at IS NULL;

CREATE UNIQUE INDEX uq_pipeline_issue_open
  ON pipeline_issue (COALESCE(professor_id,''), COALESCE(link_id::text,''),
                     COALESCE(institution,''), stage, reported_by)
  WHERE resolved = false;
```
（注：postgres 不允许 NULL 进 unique，所以用 COALESCE fallback）

重复 POST 同 flag 会得 409，前端改成"已有该 flag 的 open issue"提示。

### A3. Alembic migration round-trip 测试（Test Q3）
新测试文件 `apps/admin-console/tests/test_migration_v006.py`：

```python
def test_v006_upgrade_downgrade_upgrade_is_idempotent(postgres_data_ready):
    """V006 迁移必须无害地走 upgrade → downgrade → upgrade 三次。"""
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    alembic_command.downgrade(config, "V005b")   # revert
    alembic_command.upgrade(config, "head")      # re-apply
    # 表存在且索引在位
    with psycopg.connect(pg_dsn) as conn:
        n = conn.execute("SELECT COUNT(*) FROM pipeline_issue").fetchone()[0]
        assert n == 0
        has_idx = conn.execute("""
            SELECT 1 FROM pg_indexes
             WHERE tablename='pipeline_issue' AND indexname='uq_pipeline_issue_open'
        """).fetchone()
        assert has_idx is not None
```

历史背景：V005b → V005a 往返曾因 CHECK 冲突失败，这类测试便宜买保险。

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Alembic migration 在 `miroflow_real` 锁表 | 新表无 FK 影响，`CREATE TABLE` 几乎瞬间；索引跟着加也 <1s |
| SQL JOIN 增加查询延迟（尤其 source_page 三层 JOIN） | 走 LATERAL JOIN + LIMIT，全部命中索引；测试加 `EXPLAIN ANALYZE` 断言 <50ms |
| 新字段破坏前端（旧 `/browse` 页可能 KeyError） | Pydantic 模型字段加 Optional，前端容错；browse.html 用 `obj.field ?? '—'` 渲染 |
| `pipeline_issue` 表未来 schema 演化 | 留 jsonb `metadata` 字段备用，初版不用 |

## 6. 非本轮事项

- **Round 8d** — 自动化 pipeline 质量监控，把 `pipeline_issue` 趋势作为 CI 指标
- **Round 7.16** — 基于累积的 `pipeline_issue`，优先修出现最多的 stage 的 bug
- 前端迁 React（Round 8e+）

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `gstack-plan-ceo-review` | Scope & strategy | 1 | CLEAR | HOLD SCOPE, 3 amendments (A1/A2/A3) |
| Eng Review | `gstack-plan-eng-review` | Architecture & tests | 1 | CLEAR | 3 amendments (E1/E2/E3) |
| Design Review | n/a | No UI framework change | 0 | SKIP | internal console, HTML only |
| Outside Voice (Codex) | `codex exec` | Independent 2nd opinion | 1 | CLEAR | 12 findings, all accepted & baked in |

**VERDICT:** CEO + ENG + OUTSIDE VOICE CLEARED. 18 amendments total (A1-3, E1-3, Codex 1-12). Ready for Stage 3 TDD.

**Unresolved:** 0.  
**Critical gaps:** 0.  

**Execution plan (post-Codex reshape):**
- Lane 1: **8c-A provenance + V006 migration** — must merge first
- Lane 2 (parallel): 8c-B coverage + source-breakdown
- Lane 3 (parallel): 8c-C sample + review issues (imports Lane 1 models)

**Known limitations deferred to Round 7.16:** pipeline `run_id` trace. See §4.0.

## 7. 参考

- `docs/plans/2026-04-18-005-data-quality-guards-and-identity-gate.md`（数据质量护栏，本 round 的前置）
- `docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md` §6.5（link schema）
- `memory/feedback_data_quality_guards.md`（三步工作流模板）
