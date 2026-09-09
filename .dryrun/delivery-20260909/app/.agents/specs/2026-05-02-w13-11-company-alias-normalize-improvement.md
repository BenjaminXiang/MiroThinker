---
title: "W13-11: company alias / multi-applicant normalize 提升 (3.9% → 目标 30%+)"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（normalize 算法改进 + 单测 + dogfood）
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-3-patent-postgres-writer.md
prd_anchor: docs/Patent-Data-Agent-PRD.md §10 acceptance（patent 关联企业 ≥ 90%）
---

# W13-11: company alias / multi-applicant normalize 提升

## 1. Goal

W13-3 patent e2e full real DB 实测：

- patent: 1931
- candidates from multi-applicant split: 76
- linked: 76 (33 distinct companies)
- **命中率 76/1931 = 3.9%**

PRD §10 要求 patent 关联企业 ≥ 90%。当前差距巨大。根因：

1. PG `company.canonical_name` 是短名（"极智视觉科技（深圳）"）；专利 xlsx applicants 是全名（"极智视觉科技（深圳）有限公司"）。`registered_name` 列虽然有全名匹配，但 1024 公司中很多 registered_name 还是短名 / 缺。
2. `linkage.link_company_ids` 当前 normalize 仅去 `深圳市/有限公司/集团` 三个后缀，对"（深圳）"、"广东"、"科技股份"、"无线"等修饰词不处理。
3. 专利 applicant 中的"深圳市广和通无线股份有限公司"vs 公司主表"广和通"完全无法 normalize 一致。

## 2. Non-goals

- **不**改 V005b CHECK 枚举或 schema
- **不**改 W13-3 patent writer 接口
- **不**用 LLM 做模糊匹配（成本高；本 spec 仅规则化）
- **不**做反向：从 patent 反推创建新 company（保留候选集封闭性）

## 3. 改进策略（按优先级）

### 3.1 全字符串 normalize 升级
`apps/miroflow-agent/src/data_agents/company/normalization.py`：

```python
# 加 normalize 步骤（按顺序）：
# 1. 去地域前缀：'深圳市', '深圳', '广东省', '广东', '上海市', '北京'
# 2. 去公司后缀：'有限公司', '股份有限公司', '股份', '集团有限公司', '集团', '科技有限公司'
# 3. 去括号修饰：'（深圳）', '(深圳)', '（中国）', '(中国)'
# 4. 去技术词：'无线', '科技', '技术', '智能'（可选；可能误删）— 需 A/B test
# 5. 去标点 / 全半角统一
```

### 3.2 alias 表
在 company 表加 `aliases JSONB` 列（V021 alembic — V020 已被 W13-12 占用）：

```sql
ALTER TABLE company ADD COLUMN aliases JSONB DEFAULT '[]'::jsonb;
-- 已知别名：从 W12-1 phase 1 xlsx 列 'aliases' 导入
-- 或 LLM 生成简称：'广和通无线股份' → ['广和通', '广和通无线']
```

`linkage.link_company_ids` 在 normalize 失败后，再试 alias 表 LIKE 匹配。

### 3.3 编辑距离 fallback
对未命中的 applicant，跑 fuzzy match（edit distance ≤ 3 或 token Jaccard ≥ 0.7）；命中作为 `link_status='candidate'` + `evidence_source_type='patent_xlsx_applicant_normalized_match'`，需 human review 升级到 `verified`。

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/company/normalization.py
    扩 normalize 规则；加单元测试
  apps/miroflow-agent/src/data_agents/patent/linkage.py
    link_company_ids: 失败时降级 fuzzy match（可选）

新增：
  apps/miroflow-agent/alembic/versions/V021_add_company_aliases.py
    （单列 JSONB；V020 已被 W13-12 paper/patent identity_status 占用）
  apps/miroflow-agent/scripts/run_company_alias_seed.py
    从 W12-1 xlsx 导入已知别名；或用 LLM 生成简称（需 user 决策）

新增测试：
  apps/miroflow-agent/tests/data_agents/company/test_normalization_v2.py
    输入 / 期望 normalize 结果（30+ 案例）
  apps/miroflow-agent/tests/data_agents/patent/test_linkage_alias_match.py
    候选 link 命中率从 76 → 600+ (target 30% × 1931)
```

## 5. Validation

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=... uv run pytest tests/data_agents/company/test_normalization_v2.py \
                                       tests/data_agents/patent/test_linkage_alias_match.py -v

# Alembic V020 + dogfood
unset https_proxy HTTPS_PROXY
DATABASE_URL=...miroflow_real uv run alembic upgrade head
DATABASE_URL=...miroflow_real uv run python scripts/run_company_alias_seed.py
# 重跑 patent e2e
DATABASE_URL=...miroflow_real uv run python scripts/run_patent_release_e2e.py \
  --database-url=...miroflow_real \
  --report-output=logs/data_agents/patent_e2e/report-w13-11.json
# 期望：company_patent_links_written ≥ 600 (vs 76)
```

## 6. Done criteria

1. ✅ normalization v2 单测 ≥ 30 案例覆盖
2. ✅ patent e2e dogfood：command_patent_links 写入率 ≥ 30%（≥ 600 / 1931）
3. ✅ V020 alembic upgrade + downgrade OK
4. ✅ 既有 patent / company 测试不退化

## 7. Open questions

| 问题 | 默认决策 |
|---|---|
| alias 表 vs JSONB 列？| JSONB 列（少一张表；查询 `aliases @> ARRAY['广和通']` 简单）|
| LLM 生成简称是否本 spec | 否；先规则化 + xlsx 已有 alias；LLM 后续 |
| fuzzy match 阈值 | edit_distance ≤ 3 OR token Jaccard ≥ 0.7（看实际命中率调）|
| `verified` 升级流程 | 不本 spec；human_reviewed by browse UI |
