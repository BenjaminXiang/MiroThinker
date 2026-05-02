---
title: "W13-2 (rev 2): 跨域关系 writer（professor↔company / professor↔patent / company↔patent，P0-2）"
date: 2026-05-02
revision: 2
revised_reason: "rev 1 假设的 schema 与 V005b 实际不符（role_id/role_type/match_reason 等列名 + 真实枚举值不同；link 表无 run_id）。本版按 V005b 真实 schema 重写。"
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w12-1-company-kg-batch-e.md
schema_source: apps/miroflow-agent/alembic/versions/V005b_init_cross_domain_relations.py
prd_anchor:
  - docs/Professor-Data-Agent-PRD.md §7.1（company_roles）
  - docs/Professor-Data-Agent-PRD.md §7.2（patent_ids）
  - docs/Company-Data-Agent-PRD.md §6.1
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §6（跨域链接）
---

# W13-2 (rev 2): 跨域关系 writer

## 1. Goal

V005b 创建了 3 张关系表（`professor_company_role` / `professor_patent_link` / `company_patent_link`）；`apps/miroflow-agent/src/data_agents/service/retrieval.py:359-410` 已 SELECT 这些表。但全仓 `grep "INSERT INTO professor_company_role"` 0 命中：

- `apps/miroflow-agent/src/data_agents/professor/link_backfill.py:22-92` 仅写 SQLite `released_objects.core_facts`
- `apps/miroflow-agent/src/data_agents/professor/cross_domain_linker.py:70-84` 仅在内存里改 `core_facts`

直接结果：用户问"X 教授参与了哪些公司 / 专利"chat 永远空响应；C 类型 endpoint handler（W13-4 已实施）即便上线也命中 0 条。

本 spec：上线 Postgres writer，**严格按 V005b 真实 schema** 实现。

## 2. Schema 真实约束（V005b，**只读引用**）

### 2.1 `professor_company_role`

| 列 | 类型 | 约束 |
|---|---|---|
| `role_id` | UUID PK | DEFAULT gen_random_uuid() |
| `professor_id` | TEXT NOT NULL | FK → professor |
| `company_id` | TEXT NOT NULL | FK → company |
| `role_type` | TEXT NOT NULL | CHECK ∈ `[founder, cofounder, chief_scientist, advisor, board_member]` |
| `link_status` | TEXT NOT NULL DEFAULT 'candidate' | CHECK ∈ `[verified, candidate, rejected]` |
| `evidence_source_type` | TEXT NOT NULL | CHECK ∈ `[company_official_site, professor_official_profile, trusted_media, xlsx_team_with_explicit_role, gov_registry]` |
| `evidence_url` | TEXT **NOT NULL** | — |
| `evidence_page_id` | UUID nullable | FK → source_page (可选) |
| `match_reason` | TEXT **NOT NULL** | 自由文本，记录"为什么这条 link 成立" |
| `source_ref` | TEXT nullable | 可填 professor_id / company_id / 来源 run_id |
| `verified_by` | TEXT nullable | CHECK ∈ `[rule_auto, llm_auto, rule_and_llm, human_reviewed, xlsx_anchored]` OR NULL |
| `start_year`, `end_year` | INT nullable | 可选 |
| `is_current` | BOOL nullable | 可选 |
| `verified_at`, `rejected_at`, `rejected_reason` | nullable | 状态变化记录 |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | — |

唯一约束：`(professor_id, company_id, role_type)`（同教授同公司不同 role 各一行）

### 2.2 `professor_patent_link`

| 列 | 约束 |
|---|---|
| `link_id` UUID PK | DEFAULT gen_random_uuid() |
| `professor_id`, `patent_id` | NOT NULL |
| `link_role` | CHECK ∈ `[inventor, applicant_represented_person]` |
| `link_status` | CHECK ∈ `[verified, candidate, rejected]` |
| `evidence_source_type` | CHECK ∈ `[patent_xlsx_inventor_match, company_official_site, personal_homepage]` |
| `match_reason` | NOT NULL |
| `verified_by` | nullable, 同上枚举 |
| `verified_at`, `created_at`, `updated_at` | — |

唯一约束：`(professor_id, patent_id)`

### 2.3 `company_patent_link`

| 列 | 约束 |
|---|---|
| `link_id` UUID PK | — |
| `company_id`, `patent_id` | NOT NULL |
| `link_role` | CHECK ∈ `[applicant, assignee]` |
| `link_status` | CHECK ∈ `[verified, candidate, rejected]` |
| `evidence_source_type` | CHECK ∈ `[patent_xlsx_applicant_exact_match, patent_xlsx_applicant_normalized_match, gov_registry, company_official_site]` |
| `match_reason` | NOT NULL |

唯一约束：`(company_id, patent_id, link_role)`

### 2.4 关于 `run_id`

3 张关系表**都没有 `run_id` 列**（V005b 故意设计）。trace 通过 `source_ref` 反查源 row 的 `run_id`：

```sql
SELECT pr.run_id
FROM professor_company_role pcr
JOIN professor pr ON pr.professor_id = pcr.source_ref
WHERE pcr.role_id = '...'
```

本 spec **不**给 link 表加 run_id。

## 3. Non-goals

- **不**改 V005b schema（CHECK / 列名 / 唯一索引 / NOT NULL）
- **不**写 `professor_patent_link`（依赖 W13-3 patent 主表非空；本 spec 仅写 professor_company_role + company_patent_link 部分）

  实际上 `professor_patent_link` 的 inventor 信号在 W13-3 之后从 patent inventor 字段抽，单独 spec；本 spec 只覆盖：
  - **professor_company_role** （从 link_backfill / cross_domain_linker 写入）
  - 记录 `company_patent_link` writer **接口定义**（实施在 W13-3 patent writer 里调；本 spec 不在 patent 域写）

- **不**做退役 SQLite released_objects（W10-6 单独跟进）；本 spec 双写过渡
- **不**做 `cross_domain_linker.py` 内存模型改造（仍可用于教授画像合成）
- **不**做 `verified` 自动 promotion（写 'candidate' 即可；human_reviewed / 后续 spec 处理）

## 4. User-visible behavior

| 场景 | 之前 | 之后 |
|---|---|---|
| 跑 `run_real_e2e_professor_backfill.py` | 仅 SQLite 写 core_facts | 同时 Postgres `professor_company_role` INSERT |
| `RetrievalService.get_related_objects("professor", "PROF-X", "company")` | 命中 0 | 命中真实 link 行（含 role_type / match_reason 证据）|
| W13-4 chat C 类 "X 教授参与了哪些公司" | 空响应 | 返回 link 列表 + 证据来源 |

## 5. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/professor/link_backfill.py
    新增函数 upsert_professor_company_role_pg(...)（按 V005b schema）
    在原 SQLite 写 core_facts 路径旁并行写 Postgres
    入参：professor_id, company_id, role_type (CHECK),
          evidence_source_type (CHECK), evidence_url (NOT NULL),
          match_reason (NOT NULL), source_ref, verified_by
    返回：role_id (UUID)

  apps/miroflow-agent/src/data_agents/professor/cross_domain_linker.py
    新增 helper：build_company_role_link_records(profile, *, source_ref)
      从教授画像（official_anchor / xlsx 团队列）提取候选 link，
      生成符合 V005b schema 的字典列表（含 evidence_source_type / match_reason）

新增测试：
  apps/miroflow-agent/tests/data_agents/professor/test_link_backfill_postgres.py
    - upsert idempotent on (professor_id, company_id, role_type)
    - role_type 非法值 → CheckConstraint raise
    - evidence_source_type 非法值 → CheckConstraint raise
    - evidence_url 缺失 → NotNullViolation raise
    - match_reason 缺失 → NotNullViolation raise
    - 二次写更新 verified_at / verified_by / link_status='verified'
    - source_ref = professor_id 时，run_id trace 仍可 JOIN 到 professor 表
  apps/miroflow-agent/tests/data_agents/professor/test_cross_domain_linker_pg.py
    - build_company_role_link_records: 教授官网 bio 含 "founder of X" → role_type='founder'
    - xlsx 团队列含 "Chief Scientist" → role_type='chief_scientist'
    - 多公司同教授 → 多行 link
```

## 6. Interface contract

```python
def upsert_professor_company_role(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    company_id: str,
    role_type: Literal["founder", "cofounder", "chief_scientist", "advisor", "board_member"],
    link_status: Literal["candidate", "verified", "rejected"] = "candidate",
    evidence_source_type: Literal[
        "company_official_site",
        "professor_official_profile",
        "trusted_media",
        "xlsx_team_with_explicit_role",
        "gov_registry",
    ],
    evidence_url: str,                  # NOT NULL — 必传
    match_reason: str,                   # NOT NULL — 必传，自由文本
    evidence_page_id: UUID | None = None,
    source_ref: str | None = None,       # trace 用：通常是 professor_id
    verified_by: Literal["rule_auto", "llm_auto", "rule_and_llm", "human_reviewed", "xlsx_anchored"] | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    is_current: bool | None = None,
) -> str:
    """Upsert by (professor_id, company_id, role_type); returns role_id (UUID str).

    Idempotent: same triple → UPDATE evidence_url + match_reason + verified_at + updated_at.
    """
```

`run_id` trace via `source_ref` join（不在本接口暴露；caller 写 `source_ref=professor_id`）。

## 7. role_type 推断（caller 责任）

`link_backfill.py` 从 `cross_domain_linker.py` 拿到的"教授-公司"配对里有上下文（role 信号字面量）：

| 信号 | role_type |
|---|---|
| "创始人 / 联合创始人 / founder / co-founder / cofounder" | `founder` / `cofounder` |
| "首席科学家 / chief scientist / CSO / 科学顾问首席" | `chief_scientist` |
| "顾问 / advisor / 技术顾问 / 学术顾问" | `advisor` |
| "董事 / board member / 独立董事" | `board_member` |
| 信号缺失或不明 | `advisor`（保守 default）|

如果信号不属于这 5 种（如"CTO"、"VP"），**当前不入库**（直接 skip + 记 `pipeline_issue` `role_type_not_in_check`），等后续 spec 扩 V005b CHECK。

## 8. evidence_source_type 选取（caller 责任）

| 信号来源 | evidence_source_type | 说明 |
|---|---|---|
| 教授官方主页 bio / 个人页"创立 X 公司" | `professor_official_profile` | W13-2 主要场景 |
| 公司"团队介绍"页明确列教授任 X 角色 | `company_official_site` | 公司官网爬取 |
| 公司 xlsx 导入的 `team_raw` 含明确角色 | `xlsx_team_with_explicit_role` | W12-1 phase 1 来源 |
| 媒体报道 / PR 稿件 | `trusted_media` | W13-8 Serper news 抽取 |
| 工商登记 | `gov_registry` | 后续 spec 接 |

## 9. match_reason 模板（caller 责任）

非空必填；推荐结构化短句 ≤ 200 chars，包含：

- 信号源（"教授主页 bio 第 3 段"/"公司团队页 #team-section"/"xlsx team_raw 列"）
- 触发模式（"regex matched 'founder of'"/"keyword matched '创始人'"/"LLM extracted role='cofounder'"）
- 抽取置信度（如 LLM-based："llm_confidence=0.92"）

示例：
```
"professor profile bio paragraph 3 mentions 'founder of 广和通' (regex match 'founder of \\w+')"
"company team page lists professor as 'Chief Scientist' (xpath /div[@class=team-list]/span[3])"
"xlsx team_raw column 5 explicit role 'CTO' (matched against fallback rule advisor)"
```

`signal_event_extractor.py` 后续可用此字段判断证据强度。

## 10. Invariants

- `evidence_url` / `match_reason` 必传（NOT NULL）；caller 不传抛 ValueError 早 fail（先于 PG raise）
- `role_type` / `evidence_source_type` 非合法枚举值 → caller pre-check raise（CheckConstraint 是后备）
- 唯一索引 `(professor_id, company_id, role_type)` → ON CONFLICT DO UPDATE（更新 evidence_url + match_reason + updated_at；保留 created_at）
- `link_status='verified'` 仅当 `verified_by IS NOT NULL`（业务规则；CHECK 已允许 verified + verified_by NULL，但本 writer 强制成对）
- 双写策略：先写 SQLite（保留兼容）→ 再写 PG；PG 失败时不回滚 SQLite，而是写 `pipeline_issue` `pg_link_write_failed` + 继续主流程
- `source_ref` 默认填 `professor_id`（trace 时可经 professor 表查 run_id）
- FK 必须存在：`professor_id` IN professor 表；`company_id` IN company 表；不存在 → 跳过 + 写 `pipeline_issue` `unmapped_*_id`

## 11. Edge cases

| 场景 | 处理 |
|---|---|
| 公司 normalize miss（公司主表无该 COMP-id）| skip + `pipeline_issue` `unmapped_company_alias` |
| 同教授同公司多 role（founder + advisor）| 两行（唯一索引含 role_type）|
| 双证据（官网 + 媒体）| 取 evidence_source_type 优先级（official > media > xlsx）；UPSERT 时 prefer 高优先级 |
| LLM 抽出 role='CTO'（不在 CHECK 枚举）| skip + `pipeline_issue` `role_type_not_in_check` + log warning |
| evidence_url 是相对路径 | caller 拼绝对（`urljoin(profile_url, evidence_url)`）；为空 → ValueError |
| match_reason 极长（> 1000 chars）| 截断到 800 + "…" |

## 12. Validation

```bash
cd /home/longxiang/MiroThinker/apps/miroflow-agent
unset https_proxy HTTPS_PROXY

DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/professor/test_link_backfill_postgres.py \
                tests/data_agents/professor/test_cross_domain_linker_pg.py \
                -n0 --no-cov -v

# 既有教授链路不退化
uv run pytest tests/data_agents/professor/ -n0 --no-cov

# retrieval get_related 用真 PG fixture
uv run pytest tests/data_agents/service/test_retrieval_get_related.py -n0 --no-cov -v
```

## 13. Done criteria

1. ✅ `link_backfill.py` 新增 `upsert_professor_company_role` PG 路径
2. ✅ idempotent + CHECK 拒非法 + NotNull 拒缺值 单测覆盖
3. ✅ 现有 SQLite 路径仍可用（双写过渡）
4. ✅ `tests/data_agents/service/test_retrieval_get_related.py` 用真 PG fixture 跑通至少 1 个 happy path
5. ✅ `cross_domain_linker.build_company_role_link_records` 单测覆盖 3 种 evidence_source_type
6. ✅ ruff 通过

## 14. 顺序与依赖

- 本 spec 仅依赖 V005b（已 land）和 V003 professor 主表（已 land）
- 与 W13-3 / W13-6 V019 **无依赖**：可并行实施
- W13-4 C handler（已 done）目前命中 0 条；本 spec land 后即可命中真数据

## 15. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| `run_id` 是否加到 link 表？ | **不加**。V005b 故意没设计；trace 经 source_ref 反查源 row |
| LLM 抽出 'CTO' / 'VP' 是否扩 CHECK？ | 否，本 spec 跳过这些；后续 spec 评估扩 CHECK |
| `evidence_url` 必传 vs 默认值？ | 必传，无 default；缺则不入库（来源不明的 link 不应入主表） |
| 双写过渡何时退役 SQLite？ | 不在本 spec 范围；W10-6 跟进 |
| `verified_by` 何时填？ | LLM 抽 → 'llm_auto'；regex 抽 → 'rule_auto'；二者都用 → 'rule_and_llm'；xlsx 锚定 → 'xlsx_anchored'；人工 → 'human_reviewed' |

## 16. Stop conditions

- PG 唯一约束触发率 > 50%（说明数据重复严重）→ 检查 cross_domain_linker 是否多次抽同一信号
- `unmapped_company_alias` 比例 > 20%（说明公司主表覆盖不足）→ 不阻塞本 spec；记 pipeline_issue 由 W12-1 phase 1 跟进
- CHECK constraint 拒收频次 > 10%（说明 role_type / evidence_source_type 枚举落差）→ escalate
- 任一 NotNull / FK 错误 > 1% → escalate
