---
title: "W10-4: Company technology_route_summary LLM enrichment"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review + 操作 backfill
wave: Wave 10
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w10-1-company-milvus.md  # 字段已加（V014）
prd_anchor: docs/Company-Data-Agent-PRD.md §模块二 R2 technology_route_summary
---

# W10-4: Company technology_route_summary LLM enrichment

## 1. Goal

W10-1 V014 已加 `company.profile_summary` / `company.technology_route_summary` 列。但当前全 1037 公司这两列 NULL。Milvus embed text 退化到 `description`（xlsx 导入文本，常 50-150 chars）。

PRD §模块二 R2：`technology_route_summary` 200-500 字 reflection of 公司技术路线，与行业趋势相关。

**本 spec**：用 Gemma-4 local LLM 从 `company.description` 合成 `profile_summary` (200-300) + `technology_route_summary` (300-500)。

## 2. Non-goals

- **不**抓 company website（user 锁定 input source = description only）
- **不**做 paper full_text 关联（缺 company-paper mapping）
- **不**改 Milvus collection schema
- **不**修改 V3 pipeline；走 backfill 脚本（user 锁定）
- **不**做 cron 定期刷新

## 3. User-visible behavior

| 用户面 | 行为 |
|---|---|
| `company.profile_summary` | 200-300 chars 公司画像（行业 + 主营 + 创立背景）|
| `company.technology_route_summary` | 300-500 chars 技术路线 + 产品 + 行业地位 |
| Milvus `company_profiles` 重新 embed | semantic 查"做无人机的 AI 公司"召回率提升 |
| `description` 字段 | 不动（保留 xlsx raw） |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/src/data_agents/company/narrative_enrichment.py  # ~120 lines
    NarrativeResult dataclass
    generate_company_narrative(description, name, industry, llm_client, ...) -> NarrativeResult
    _SYSTEM_PROMPT / build_user_prompt
  apps/miroflow-agent/scripts/run_company_narrative_backfill.py  # ~200 lines
    --only-missing (default) / --all
    --limit / --resume
    open_pipeline_run('backfill_real') + close_pipeline_run
  apps/miroflow-agent/tests/data_agents/company/test_narrative_enrichment.py
  apps/miroflow-agent/tests/scripts/test_run_company_narrative_backfill.py
```

## 5. Architecture / Data flow

```
SELECT c.company_id, c.canonical_name, c.industry, c.hq_city,
       cs.description  -- 从 latest company_snapshot LATERAL JOIN
  FROM company c
  LEFT JOIN LATERAL (SELECT description FROM company_snapshot
                      WHERE company_id = c.company_id
                      ORDER BY snapshot_created_at DESC LIMIT 1) cs ON true
  WHERE c.identity_status = 'resolved'
    AND (c.profile_summary IS NULL OR c.technology_route_summary IS NULL)
  ↓
generate_company_narrative()  -- 单 LLM call 输出 JSON {"profile_summary":..., "technology_route_summary":...}
  ↓
UPDATE company SET profile_summary, technology_route_summary, updated_at, run_id
```

## 6. Interface contracts

### 6.1 narrative_enrichment.py

```python
@dataclass(frozen=True, slots=True)
class NarrativeResult:
    profile_summary: str  # 200-300, "" if rejected
    technology_route_summary: str  # 300-500, "" if rejected
    error: str | None

_SYSTEM_PROMPT = (
    "你是深圳科创平台的企业画像合成助手。根据提供的企业基本信息（行业、所在城市、原始介绍），"
    "合成两段中文文本：\n"
    "1. profile_summary（200-300字）：企业画像，包含主营业务、行业定位、创立背景。\n"
    "2. technology_route_summary（300-500字）：技术路线、核心产品、研发方向、行业地位。\n"
    "规则：\n"
    "- 只使用提供的内容，不要编造未出现的事实。\n"
    "- 中文，连贯叙述，不要 bullet。\n"
    "- 不要 Markdown 标记。\n"
    "- 输出严格 JSON：{\"profile_summary\":\"...\", \"technology_route_summary\":\"...\"}"
)

def generate_company_narrative(
    *,
    company_name: str,
    industry: str | None,
    hq_city: str | None,
    description: str | None,
    llm_client: Any,
    llm_model: str,
    extra_body: dict | None = None,
) -> NarrativeResult:
    # 同 summary_reinforcement 模式：try/except，validate length，coerce JSON
```

### 6.2 backfill 脚本

复用 `run_profile_summary_reinforcement.py` 模式：
- `resolve_*_llm_settings("gemma4", include_profile=True)` 拿 client + model + extra_body
- open/close pipeline_run（kind='backfill_real'）
- per-company try/except + rollback
- jsonl checkpoint
- `--limit` / `--resume`

## 7. Invariants

- description 为空 / 太短 (< 30 chars) → skip（写入 jsonl `status=skipped_short_input`）
- profile_summary 长度 < 200 / > 300 → 单次 retry；仍不过 → write empty + jsonl reject
- technology_route_summary 同（300-500）
- 不破坏 description / company_snapshot 任何字段
- run_id required（W9-2 phase 2 已锁定 wiring）
- 公司主键 company_id 不变

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| description NULL（罕见） | skip + jsonl |
| description 太短（< 30 chars） | skip |
| 已有 profile_summary 长度 ≥ 200 | --only-missing skip；--all 覆盖 |
| LLM JSON 输出格式错（缺 key） | retry 1 次；仍错 → reject |
| LLM 长度违规 | retry 1 次 |
| Gemma-4 timeout | jsonl error；下次 resume |
| 行业为空 | prompt 里写 "行业未填写" |

## 9. Validation

```bash
cd apps/miroflow-agent

# 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/company/test_narrative_enrichment.py \
                tests/scripts/test_run_company_narrative_backfill.py \
                -n0 --no-cov -v

# 既有不退化
uv run pytest tests/data_agents/company/ -n0 --no-cov

# 操作 backfill（claude 跑）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  unset https_proxy HTTPS_PROXY && \
  uv run python scripts/run_company_narrative_backfill.py \
    --only-missing > logs/data_agents/company/narrative_backfill_2026-05-02.json

# 抽样验证
SELECT canonical_name, length(profile_summary), length(technology_route_summary)
  FROM company WHERE profile_summary IS NOT NULL LIMIT 5;

# Milvus 重 embed company_profiles（W10-3 retrieve 即生效）
uv run python scripts/run_milvus_backfill.py --domain company --rebuild --milvus-uri ./milvus.db
```

## 10. Done criteria

1. ✅ narrative_enrichment.py 单测过
2. ✅ backfill 脚本单测过；既有 company tests 不退化
3. ✅ claude 操作 backfill ≥ 90% 公司有非空 narrative
4. ✅ Milvus company_profiles 重 embed 后 retrieve 命中率改善（抽样查"做 XX 的公司"）
5. ✅ docs/solutions/ 写 1 篇 lesson

## 11. Stop conditions

- LLM JSON 输出连续 3 次解析失败 → 切回单次 prompt 分别生成（fallback）
- description 普遍 < 30 chars → 早期回报；可能需要 W10-4-ext 抓 website

## 12. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| LLM provider | Gemma-4 local |
| 输入源 | description only |
| 触发 | 独立 backfill 脚本 |
| 单次 LLM 输出 2 字段 vs 2 次调用 | 单次（节省 latency；JSON 解析失败 fallback 拆 2 次） |
| --only-missing 阈值 | profile_summary IS NULL OR technology_route_summary IS NULL |
