---
title: "W13-3 (rev 2): Patent Postgres writer + 多申请人切分 + summary_text LLM 化（P0-3）"
date: 2026-05-02
revision: 2
revised_reason: "rev 1 假设 patent.summary_text/summary_text_method/quality_status 列与 company_patent_link.run_id 列存在；V004/V005b 都没有。本版按 V004 真实 schema 重写：summary_text/summary_text_method/quality_status 由 W13-6 V019 加，本 spec 仅依赖 V019 land 后写入；link 表无 run_id 是设计选择（trace 经 source_ref）。"
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w13-2-cross-domain-relation-writers.md
  - .agents/specs/2026-05-02-w13-6-quality-status-alembic-v019.md
  - .agents/specs/2026-05-02-w10-2-patent-milvus.md
schema_source:
  - apps/miroflow-agent/alembic/versions/V004_init_paper_patent_domain.py (patent table, 20 cols)
  - apps/miroflow-agent/alembic/versions/V005b_init_cross_domain_relations.py (company_patent_link)
prd_anchor: docs/Patent-Data-Agent-PRD.md §3.1, §4.1, §6.1, §6.2, §10
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §6（跨域链接）
---

# W13-3 (rev 2): Patent Postgres writer + 多申请人切分 + summary_text LLM 化

## 1. Goal

V004 已建 `patent` 主表 + V007 加 `run_id` + V005b 加 `professor_patent_link` / `company_patent_link`。`apps/miroflow-agent/src/data_agents/patent/release.py` 能跑出 1931 行 jsonl（`logs/debug/patent_release_e2e_20260416T142916Z/patent_records.jsonl`），但**没有任何代码写 patent 表**。下游受阻：

- W10-2 Milvus collection（`patent_profiles`）建了 → backfill 依赖 patent 表 → 永空
- W10-3 RetrievalService `_VALID_DOMAINS` 含 patent → 召回 0
- chat A_patent_profile（chat.py:2090-2114）依赖 patent 表 → miss

本 spec：

1. 把 release.py 输出**真实落 Postgres** `patent` 表
2. 修 release.py 多申请人切分（命中率从 76/1931 = 3.9% → 预期 ≥ 30%）
3. summary_text 用 LLM 生成（依赖 W13-6 V019 加列）
4. 候选关联落 `company_patent_link`（用 V005b 真实列）

## 2. Schema 真实约束

### 2.1 `patent` 表（V004 + V007）

实测 20 列：

| 列 | 来源 | 备注 |
|---|---|---|
| `patent_id` | V004 | PAT-... PK |
| `patent_number` | V004 | xlsx 公开号 |
| `title_clean`, `title_raw`, `title_en` | V004 | — |
| `applicants_raw` | V004 | 原始整串（带 `;；\n`）|
| `applicants_parsed` | V004 | **JSONB list**（已切分；release.py 当前没真切）|
| `inventors_raw` | V004 | xlsx 缺该列；通常 NULL |
| `inventors_parsed` | V004 | **JSONB list**（多为空）|
| `filing_date`, `publication_date`, `grant_date` | V004 | DATE |
| `patent_type`, `status` | V004 | TEXT |
| `abstract_clean` | V004 | LLM 输入用 |
| `technology_effect` | V004 | LLM 输入用 |
| `ipc_codes` | V004 | JSONB list（多为空）|
| `first_seen_at`, `updated_at` | V004 | TIMESTAMPTZ |
| `run_id` | V007 | UUID（require_real_run_id 验证）|

**V004 实际无以下 W13-3 rev 1 假设的列**：
- `summary_text`
- `summary_text_method`
- `quality_status`

→ 这 3 列由 **W13-6 V019** 加（quality_status 4 域统一加 + patent.summary_text + patent.summary_text_method）。本 spec 实施**必须等 W13-6 V019 land 后**。

### 2.2 `company_patent_link`（V005b）

| 列 | 约束 |
|---|---|
| `link_id` UUID PK | gen_random_uuid() |
| `company_id`, `patent_id` | NOT NULL |
| `link_role` | CHECK ∈ `[applicant, assignee]` |
| `link_status` | CHECK ∈ `[verified, candidate, rejected]` DEFAULT 'candidate' |
| `evidence_source_type` | CHECK ∈ `[patent_xlsx_applicant_exact_match, patent_xlsx_applicant_normalized_match, gov_registry, company_official_site]` |
| `match_reason` | NOT NULL |
| `verified_by`, `verified_at`, `created_at`, `updated_at` | — |

唯一约束：`(company_id, patent_id, link_role)`

**V005b 实际无 `run_id` 列**（同 W13-2，trace 经 source_ref → patent.run_id 反查）。

## 3. Non-goals

- **不**做 inventors 抽取（xlsx 缺源；CNIPA / 智慧芽 接入由后续 spec）
- **不**写 `professor_patent_link`（依赖 inventor 抽取，独立 spec）
- **不**改 V004 / V005b / V007 schema（V019 单独加 summary_text/method/quality_status，由 W13-6 spec 处理）
- **不**做 patent quality_gate（domain quality_gate.py 后续）
- **不**改 patent 域 Milvus vectorizer（W10-2 已在）
- **不**改 chat 路由（B/D/E patent 由后续 spec 接）

## 4. User-visible behavior

| 场景 | 之前 | 之后 |
|---|---|---|
| `run_patent_release_e2e.py` 后 `SELECT count(*) FROM patent` | 0 | 1931 |
| `applicants_parsed` JSONB | 单元素 list（整串）| 多元素 list（按 `;；\n` 切分）|
| `SELECT count(*) FROM company_patent_link WHERE link_status='candidate'` | 0 | ≥ 76 (旧 normalize 命中率)，预期 ≥ 600（多申请人切分后翻倍翻倍）|
| `patent.summary_text` (V019 后) | NULL | LLM 生成 150-300 字 problem/method/effect |
| `patent.summary_text_method` (V019 后) | NULL | 'llm' 或 'fallback_template' |
| `patent.quality_status` (V019 后) | 'needs_review' (默认) | title + applicants_parsed + filing_date 都有效 → 'ready'；否则 'needs_review' |
| Milvus `patent_profiles` collection | 0 | ≥ 1931 行（`run_milvus_backfill.py --domain=patent` 后）|
| `patent.run_id` | NULL（之前 jsonl-only）| V007 trace 通过 require_real_run_id 的 uuid |

## 5. Affected paths

```
新增：
  apps/miroflow-agent/src/data_agents/patent/canonical_writer.py
    upsert_patent(conn, *, record, run_id) -> patent_id
      INSERT INTO patent (
        patent_id, patent_number, title_clean, title_raw, title_en,
        applicants_raw, applicants_parsed, inventors_raw, inventors_parsed,
        filing_date, publication_date, grant_date, patent_type, status,
        abstract_clean, technology_effect, ipc_codes,
        summary_text,           -- V019 后才有
        summary_text_method,    -- V019 后才有
        quality_status,         -- V019 后才有
        run_id, first_seen_at, updated_at
      )
      ON CONFLICT (patent_id) DO UPDATE ...

    upsert_company_patent_link(conn, *, patent_id, company_id, link_role,
                               evidence_source_type, match_reason,
                               link_status='candidate', verified_by=None) -> link_id
      INSERT INTO company_patent_link (...)
      ON CONFLICT (company_id, patent_id, link_role) DO UPDATE ...

  apps/miroflow-agent/src/data_agents/patent/summary_llm.py
    generate_patent_summary_text(record, *, llm_client) -> tuple[str, Literal["llm","fallback_template"]]
    Prompt 输入：title_clean + abstract_clean + technology_effect + applicants_parsed
    输出：≤ 300 字单段 problem/method/effect
    LLM 走：from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
            settings = resolve_professor_llm_settings("gemma4", include_profile=True)

修改：
  apps/miroflow-agent/src/data_agents/patent/release.py
    + 修 build_summary_text → 调 summary_llm.generate_patent_summary_text（fail fallback 现有裸拼）
    + applicants 字段在 release_result 里改用 _split_tokens 切分后的 list
      （_split_tokens 在 import_xlsx.py:20 已支持 ;|；|\n；release 当前传整串）
    + record_to_patent_dict（新 helper）：把 PatentRecord → 适合 INSERT 的 dict
      含 quality_status 计算：title_clean & applicants_parsed[0] & filing_date 都非空 → 'ready'，否则 'needs_review'
  apps/miroflow-agent/src/data_agents/patent/linkage.py
    + link_company_ids: 对 applicants_parsed 每个 token 独立 normalize（不只首项）
      返回 list[(company_id, evidence_source_type, match_reason)]
        其中 evidence_source_type:
          - 完全相同（含 "（深圳）"等）→ 'patent_xlsx_applicant_exact_match'
          - normalize 后命中（去公司后缀）→ 'patent_xlsx_applicant_normalized_match'
        match_reason: e.g. "applicants_parsed[2]='广和通通信有限公司' normalized to '广和通' → COMP-A1B2"
  apps/miroflow-agent/scripts/run_patent_release_e2e.py
    + report writer 新增：把 release_result.patent_records → patent 表 + company_patent_link
    + run_id 由 runtime 注入（require_real_run_id）

新增测试：
  apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer.py
    - upsert_patent idempotent on patent_id
    - run_id sentinel 拒收
    - quality_status 计算（含 / 缺）
    - applicants_parsed JSONB list 写入
  apps/miroflow-agent/tests/data_agents/patent/test_summary_llm.py
    - mock LLM；prompt 含 title/abstract/effect
    - LLM 失败 fallback 到模板
    - LLM 输出 < 50 chars → fallback
    - LLM 输出 > 300 chars → 截断 + "…"
  apps/miroflow-agent/tests/data_agents/patent/test_linkage_multi_applicant.py
    - "公司A; 公司B；公司C\n公司D" → 4 token；分别 normalize
    - 命中数 vs 整串：≥ 2x 提升
    - evidence_source_type 区分 exact / normalized
  apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer_company_patent_link.py
    - upsert idempotent on (company_id, patent_id, link_role)
    - link_role 非法值 raise (CHECK)
    - evidence_source_type 非法值 raise
    - match_reason 缺失 raise (NotNull)
  apps/miroflow-agent/tests/scripts/test_run_patent_release_e2e_pg.py
    - 端到端 fixture（10 行 xlsx）→ patent 表 10 行 + company_patent_link 命中 N 行
```

## 6. Interface contract

```python
def upsert_patent(
    conn: psycopg.Connection,
    *,
    record: PatentRecord,
    run_id: str,
) -> str: ...

def upsert_company_patent_link(
    conn: psycopg.Connection,
    *,
    patent_id: str,
    company_id: str,
    link_role: Literal["applicant", "assignee"] = "applicant",
    evidence_source_type: Literal[
        "patent_xlsx_applicant_exact_match",
        "patent_xlsx_applicant_normalized_match",
        "gov_registry",
        "company_official_site",
    ],
    match_reason: str,                     # NOT NULL
    link_status: Literal["candidate", "verified", "rejected"] = "candidate",
    verified_by: Literal["rule_auto", "llm_auto", "rule_and_llm", "human_reviewed", "xlsx_anchored"] | None = None,
) -> str: ...

def generate_patent_summary_text(
    record: PatentRecord,
    *,
    llm_client,                           # caller 注入；用 resolve_professor_llm_settings("gemma4")
) -> tuple[str, Literal["llm", "fallback_template"]]: ...
```

LLM 调用**必须**走：

```python
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
settings = resolve_professor_llm_settings("gemma4", include_profile=True)
# 不要硬编码 api_key / endpoint / extra_body —— auto-memory feedback_codex_deviations
# 跑前外层 unset https_proxy HTTPS_PROXY (auto-memory feedback_proxy_llm)
```

## 7. Invariants

- `applicants_parsed` 是真正 JSONB list（`_split_tokens` 拆 `;|；|\n` 后剥空白）
- `link_company_ids` 对每个 token 独立 normalize；命中即生成候选 link 记录（保持 token 顺序）
- `summary_text` 长度 ≥ 50 chars 时 method='llm'；否则 fallback 模板 + method='fallback_template'
- `summary_text` 长度 > 300 chars 截断 + "…"
- `run_id` 必走 `runtime.require_real_run_id`；sentinel 'all-zeros' 拒收
- `quality_status` 计算：`title_clean` + `applicants_parsed[0]` + `filing_date` 全非空 → 'ready'；否则 'needs_review'
- `summary_text` 不强求 4 段式（patent PRD 没要求；只要 LLM 单段 problem/method/effect）
- `match_reason` 必填非空（V005b NOT NULL）
- 同 patent 多个不同 applicant 各自命中 → 多行 link（唯一索引含 link_role；同 link_role 重复 token 仅第一次）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| `applicants_raw` = "" | applicants_parsed = []；quality_status='needs_review'；不写 link |
| 多申请人 normalize 命中相同 company_id | 仅 INSERT 一条 link（ON CONFLICT 跳过）|
| LLM 超时 / fail | fallback 模板 + method='fallback_template'；不阻塞 |
| LLM 输出 < 50 chars | fallback |
| LLM 输出 > 300 chars | 截断 + "…" + method 仍 'llm' |
| FK violation（company_id 不存在）| skip + `pipeline_issue` `unmapped_company_alias` |
| filing_date 缺 / 非法 | quality_status='needs_review'（不阻塞 INSERT）|
| 同 patent 重跑 | upsert_patent ON CONFLICT DO UPDATE（保留 first_seen_at；更新 updated_at）|
| evidence_source_type 推断不出 | 使用 'patent_xlsx_applicant_normalized_match'（保守 fallback）|

## 9. Validation

```bash
cd /home/longxiang/MiroThinker/apps/miroflow-agent
unset https_proxy HTTPS_PROXY

DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/patent/ -n0 --no-cov -v

# Milvus 端到端 dry-run（W10-2 已 land；本 spec 完成后填 1931 行）
uv run python scripts/run_milvus_backfill.py --domain=patent --limit=10 --dry-run

# 既有 patent 测试不退化
uv run pytest tests/data_agents/patent/ tests/scripts/test_run_patent_release_e2e.py -n0 --no-cov

# claude 后续操作：实跑 e2e
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_patent_release_e2e.py
# 期望：patent 表 1931 行；company_patent_link ≥ 600 行；summary_text 全部生成
```

## 10. Done criteria

1. ✅ `canonical_writer.upsert_patent` + `upsert_company_patent_link` 上线
2. ✅ `summary_llm.generate_patent_summary_text` 用 `resolve_professor_llm_settings("gemma4")`
3. ✅ `linkage.link_company_ids` 处理切分后多 token；evidence_source_type 区分 exact/normalized
4. ✅ `run_patent_release_e2e.py` 完整跑：xlsx → release → patent 表 + company_patent_link 表
5. ✅ run_id wiring 通过 sentinel 拒收测试
6. ✅ `quality_status` 计算单测覆盖
7. ✅ 全部新单测通过；既有 patent 测试不退化
8. ✅ ruff 通过

## 11. 顺序与依赖

依赖链：

```
W13-6 V019 (加 patent.summary_text + summary_text_method + 4 域 quality_status)
    ↓ land
W13-3 (本 spec) — upsert_patent 写入新列
    ↓ land
[manual: claude 跑 run_patent_release_e2e.py 全量 1931 行]
    ↓
W10-2 Milvus backfill --domain=patent
```

W13-3 与 W13-2 / W13-4 / W13-5 / W13-1 **无文件冲突**；可并行实施（但 W13-3 实施依赖 V019 schema 落地）。

## 12. Open questions（已锁）

| 问题 | 默认决策 |
|---|---|
| LLM 失败率多高 escalate？| < 5% 单跑 OK；> 10% prompt 调优 |
| `evidence_source_type` 是否含 'patent_xlsx_applicant_partial_match'（编辑距离/包含）？| 否，本期仅 exact + normalized |
| inventors 是否本期补？ | 否（xlsx 缺源）；后续 spec 接 CNIPA/智慧芽 |
| `professor_patent_link` 何时写？ | 等 inventor 抽取上线（独立 spec）|
| `link_role='applicant' vs 'assignee'`？ | 默认 'applicant'（xlsx 来源）；'assignee' 留 follow-up |
| Milvus backfill 是否在本 spec？ | 否；由 W13-V follow-up（W13-3 land 后人工跑）|
| `run_id` 是否加 link 表？ | 否（V005b 故意没设计；trace 经 source_ref）|

## 13. Stop conditions

- W13-6 V019 未 land → 本 spec 不能开始；BLOCKED 报告
- LLM 失败率 > 10%（10 条样本）→ prompt 调优独立 1 轮
- multi-applicant 切分后命中率 < 1.5x（说明 normalize 还有 bug）→ escalate normalization.py
- run_id sentinel 触发 → escalate runtime
- CHECK constraint 频次拒收 > 5%（说明 link_role / evidence_source_type 推断逻辑 bug）→ escalate

## 14. 实施前必读

1. `apps/miroflow-agent/alembic/versions/V004_init_paper_patent_domain.py:100-146`（patent 真实列）
2. `apps/miroflow-agent/alembic/versions/V005b_init_cross_domain_relations.py:255-360`（company_patent_link 列 + CHECK）
3. `apps/miroflow-agent/src/data_agents/patent/release.py`（当前 release flow）
4. `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:20`（_split_tokens 已实现）
5. `apps/miroflow-agent/src/data_agents/patent/normalization.py`（applicant normalize 当前规则）
6. `apps/miroflow-agent/src/data_agents/runtime.py`（require_real_run_id）
7. `apps/miroflow-agent/src/data_agents/professor/llm_profiles.py:70-73`（gemma4 endpoint resolver）
