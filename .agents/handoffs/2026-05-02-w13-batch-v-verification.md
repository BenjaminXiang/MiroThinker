---
title: "Batch V (Wave 13 P1 验证): W13-V1 + W13-V2 + W13-V3（3 spec）"
date: 2026-05-02
owner: codex-ops
specs:
  - .agents/specs/2026-05-02-w13-V1-paper-summary-zh-dogfood.md
  - .agents/specs/2026-05-02-w13-V2-company-milvus-dogfood.md
  - .agents/specs/2026-05-02-w13-V3-intent-benchmark-archive.md
slice: 1+2+3 of 3
status: ready
---

# Batch V handoff（3 sub-slice，可并行）

P1 验证批：跑真实数据归档。每个 sub-slice 输出独立产物，互不冲突，可并行跑。

## CRITICAL — 内网 LLM + proxy

```bash
# 必须 unset 代理 —— 内网 Gemma-4 / Qwen / Embedding 一律不走 proxy
unset https_proxy HTTPS_PROXY
```

LLM 调用一律走 `from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings`。auto-memory `feedback_codex_deviations` + `feedback_proxy_llm` 是历史踩坑。

## 顺序与依赖

| Slice | 依赖 | 耗时（估计） |
|---|---|---|
| W13-V1 paper summary_zh | W13-1 land 后才能验"接口可见"；不 land 也可跑回填本身 | LLM 50 条 ≈ 5-10 min |
| W13-V2 company milvus | W10-1 + W10-4 已 land；本身 1025 公司 narrative ≈ 1-2 hr；Milvus backfill ≈ 30 min；retrieval 抽样 ≈ 30 min（含人工标注）| 3-4 hr |
| W13-V3 intent benchmark | 100 条 LLM 调用 ≈ 5 min | 5-10 min |

建议执行顺序：V3（最快）→ V1（中）→ V2（最长）。三者不冲突文件，也可三机/三 shell 并行。

## Read order

1. 本 handoff
2. 3 个 spec 全文（gates / steps / 归档路径）
3. `apps/miroflow-agent/src/data_agents/professor/llm_profiles.py:70-73`（gemma4 endpoint）
4. `apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py`（V1）
5. `apps/miroflow-agent/scripts/run_company_narrative_backfill.py`（V2）
6. `apps/miroflow-agent/scripts/run_milvus_backfill.py`（V2 阶段 2）
7. `apps/admin-console/tests/test_classifier_benchmark.py:73`（V3 marker）

## 文件冲突地图

| 输出 | V1 | V2 | V3 |
|---|---|---|---|
| `docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl` | 🆕 | | |
| `docs/source_backfills/company-narrative-backfill-2026-05-02.jsonl` | | 🆕 | |
| `docs/source_backfills/intent-classifier-benchmark-2026-05-02.log` | | | 🆕 |
| `docs/solutions/integration-issues/paper-summary-zh-dogfood-2026-05-02.md` | 🆕 | | |
| `docs/solutions/integration-issues/company-milvus-dogfood-2026-05-02.md` | | 🆕 | |
| `docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md` | | | 🆕 |

无冲突。

## Critical decisions（claude 已锁）

V1:
- 50 条小批先跑（test_mock + real 各一次）；全量另起
- summary_zh 单段（不动 4 段式）
- 失败 paper 不 retry，归档失败原因

V2:
- 三阶段：narrative → Milvus → retrieval 抽样
- Top-5 ≥ 85% 由人工标注（不接受 LLM 自评）
- 类别：10 行业 × 5 query

V3:
- 阈值：overall ≥ 90% / per-class ≥ 70% / C per-class ≥ 80%
- ADR 提供方案对比，user 拍板 systemd vs GH Action
- 偶发 89% 不算 fail；连续 2 次 < 90% 才提调优

## Do-not

- ❌ 不改 abstract_translator / narrative_enrichment / classifier 的 prompt
- ❌ 不改 fixture（intent_classifier_benchmark.jsonl）
- ❌ 不硬编码 api_key / endpoint / extra_body —— 走 llm_profiles
- ❌ 不在跑 LLM 时 export https_proxy
- ❌ 不 commit 跑出的 jsonl/log 到 git（仅放 `docs/source_backfills/`，由 claude 后续合 commit）
- ❌ 不修任何 source code（除非发现 bug，先报告 → 等 claude 决策）
- ❌ 不在生产 real DB 上 `--force` 穿越任何 abort（abort 必须报）

## Tests / checks（每 sub-slice 完成后）

```bash
# V1
ls -la docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl
wc -l docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl  # 期望 ≥ 45

# V2
ls -la docs/source_backfills/company-narrative-backfill-2026-05-02.jsonl
# Milvus row count
python -c "from pymilvus import Collection; ..."  # 略

# V3
ls -la docs/source_backfills/intent-classifier-benchmark-2026-05-02.log
grep -E "overall|per_class" docs/source_backfills/intent-classifier-benchmark-2026-05-02.log
```

## Done criteria

1. ✅ 3 spec 各自 §9 done criteria 全部满足
2. ✅ 6 份归档文件（3 jsonl/log + 3 md/ADR）落 `docs/`
3. ✅ 不修 source code
4. ✅ 报告每个 sub-slice 的关键 metric（成功率 / 准确率 / 耗时 / token）
5. ✅ ADR-008 含方案对比 + 推荐

## Stop conditions

- V1 写入成功率 < 80% → 检查 LLM endpoint；明确报失败前 `不要重跑`
- V2 narrative 覆盖率 < 90% → 检查源数据；不强行往下走 Milvus
- V2 Top-5 < 70% → 大概率 vectorizer / embedding 模型有问题；escalate W10-1 follow-up
- V3 overall < 80% → escalate W11-1 / classifier prompt 严重问题
- 任何 spec 在 §10/11 出现新分歧 → 立即 BLOCKED 报告，等 claude 决策

## Report

```
Summary:
  W13-V1 paper summary_zh dogfood:
    - test_mock: N 条写入 / 平均长度 / 中文比例
    - real: N 条写入 / 平均长度 / 中文比例
    - W13-1 接口验证：5 条 GET 中 N 条 summary_zh 非空
  W13-V2 company milvus dogfood:
    - narrative 覆盖率: A% (profile_summary) / B% (technology_route_summary)
    - Milvus 行数: C
    - Top-5 准确率（50 条）: D%
  W13-V3 intent benchmark:
    - overall: X%
    - per-class: A=X% B=X% C=X% D=X% E=X% F=X% G=X%
    - 错分样本: N 条（按类列出）
    - ADR-008: 推荐方案 = systemd / GH Action

Archived:
- docs/source_backfills/paper-summary-zh-dogfood-2026-05-02.jsonl
- docs/source_backfills/company-narrative-backfill-2026-05-02.jsonl
- docs/source_backfills/intent-classifier-benchmark-2026-05-02.log
- docs/solutions/integration-issues/paper-summary-zh-dogfood-2026-05-02.md
- docs/solutions/integration-issues/company-milvus-dogfood-2026-05-02.md
- docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md

Risks/notes:
- LLM token 总消耗
- 跑 V2 narrative 全量耗时
- 任何 BLOCKED 项
```
