---
title: 教授 PRD 收口必须以真实数据的 Phase A 严格门禁为准
date: 2026-04-14
category: docs/solutions/best-practices
module: apps/miroflow-agent professor pipeline v3
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - 判断教授域是否真正达到 PRD 交付标准
  - 合并多批真实 URL E2E 结果后准备发布教授搜索库
  - 需要把 URL 质量、论文精度和检索质量统一收口
tags: [professor-pipeline, prd, phase-a-gate, real-data, e2e, retrieval, audit]
---

# 教授 PRD 收口必须以真实数据的 Phase A 严格门禁为准

## Context

教授域在 2026-04-14 之前已经补齐了多类实现修复，包括：

- URL 级 `ready / paper_backed / required_fields` 质量门
- 官方 publication 证据 fallback
- 学科感知 quality gate
- 真实共享检索库刷新与 Top-5 检索评测

但这些单点通过还不等于 PRD 已经完成。真正的风险在于三类漂移：

- URL E2E 通过了，但发布到共享检索库后的对象名字或 ID 仍然被旧批次污染
- 质量门通过了，但 profile 级别的论文证据样本量不足，无法证明大样本精度
- 检索链路在小样本 query 上通过，但更大真实样本集上的 Top-5 目标命中率不稳定

这轮最终收口证明，教授域不能只看单个 URL 报告，也不能只看单个发布批次。PRD 完成标准必须是同一套真实数据上的三段式严格门禁全部通过。

## Guidance

把教授 PRD 的最终验收固定成下面四步，并以最后一步的严格 gate 作为唯一放行信号。

1. 先生成当前代码下的 clean real-data URL E2E 汇总。
   不要混用历史失败产物或旧 rerun 目录。必须明确挑选“当前代码对应的最新有效 summary”，再聚合成统一 summary 和 clean `current_enriched_v3.jsonl`。

2. 用 clean `current_enriched_v3.jsonl` 重刷教授共享库。
   这一步的意义不是再验证 URL，而是清掉共享库里可能残留的旧 professor 对象和旧 ID。发布时应使用域级替换，而不是在脏库上增量叠加。

3. 基于 clean snapshot 做 profile-level 抽检与 retrieval eval。
   URL 级 gate 只能证明“每个 seed URL 至少能放出一个达标教授样本”，不能证明大样本 profile 级精度。需要：
   - profile audit manifest
   - machine audit JSON
   - profile query set
   - retrieval Top-5 eval JSON

4. 最后用 `run_professor_phase_a_gate.py` 消费三类输入统一判定：
   - aggregated URL summary
   - machine audit JSON
   - retrieval eval JSON

当前这轮真实收口中，唯一应被视为 PRD 完成信号的报告是：

- [phase_a_gate_report.json](../../../logs/data_agents/professor_phase_a_gate_prd_full_profilelevel_20260414/phase_a_gate_report.json)

它已经给出：

- `go_for_phase_b = true`
- `url_gate_pass_rate = 1.0`
- `url_paper_backed_rate = 1.0`
- `url_required_fields_rate = 1.0`
- `url_quality_ready_rate = 1.0`
- `manual_identity_accuracy = 1.0` over `58` samples
- `manual_paper_link_accuracy = 0.9722` over `180` judged papers
- `retrieval_top5_rate = 1.0` over `58` real professor queries

## Why This Matters

教授数据的质量问题，最危险的不是“完全抓不到”，而是“看起来能用，但局部还是错的”。

如果只看 URL E2E：

- 你可能放过名字污染后的旧对象
- 你不知道 profile 级论文证据是否有足够样本量
- 你不知道发布到共享库后，真实检索是否还能稳定命中目标教授

如果只看检索：

- 你可能把一个能搜到、但本身质量状态不够的对象也视为通过

三段式严格 gate 的价值，在于同时验证三件事：

- 抓取和清洗链真实可用
- 教授-论文链在样本量上达标
- 共享搜索域的最终用户查询结果可用

这比“单次脚本跑通”更接近 PRD 真正关心的交付质量。

## When to Apply

- 发布教授域到共享检索库之前
- 论文发现、姓名清洗、主页抽取或发布逻辑发生改动之后
- 需要回答“教授 PRD 是否已经完成”时
- 需要决定是否继续做 ORCID / DBLP / 更多增强项时

## Examples

这轮最终验收对应的真实产物链如下：

- Clean aggregated URL E2E:
  - [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_prd_full_aggregated_20260414/url_e2e_summary.json)
  - [current_enriched_v3.jsonl](../../../logs/data_agents/professor_url_md_e2e_prd_full_aggregated_20260414/current_enriched_v3.jsonl)
- Clean professor publish:
  - [publish_report.json](../../../logs/data_agents/professor_search_refresh_prd_full_20260414/publish_report.json)
- Profile-level machine audit:
  - [phase_a_machine_audit.json](../../../logs/data_agents/professor_phase_a_profile_machine_audit_prd_full_20260414/phase_a_machine_audit.json)
- Profile-level retrieval eval:
  - [retrieval_eval.json](../../../logs/data_agents/professor_phase_a_retrieval_eval_prd_full_20260414/retrieval_eval.json)
- Final strict gate:
  - [phase_a_gate_report.json](../../../logs/data_agents/professor_phase_a_gate_prd_full_profilelevel_20260414/phase_a_gate_report.json)

本轮最终通过的核心数字是：

- `41/41` 真实 URL 在当前代码下全部 `gate_passed`
- `58/58` profile identity 样本正确
- `175/180` judged paper links 正确
- `58/58` 真实 professor query 的目标对象进入 Top-5

实际命令链也应固定下来，避免以后人工拼装输入时重新引入漂移：

```bash
./.venv/bin/python apps/miroflow-agent/scripts/run_professor_phase_a_machine_audit.py \
  --audit-manifest-json logs/data_agents/professor_phase_a_profile_audit_prd_full_20260414/phase_a_audit_manifest.json \
  --output-dir logs/data_agents/professor_phase_a_profile_machine_audit_prd_full_20260414

./.venv/bin/python apps/miroflow-agent/scripts/run_professor_phase_a_query_set.py \
  --input-json logs/data_agents/professor_phase_a_profile_machine_audit_prd_full_20260414/phase_a_machine_audit.json \
  --output-dir logs/data_agents/professor_phase_a_profile_query_set_prd_full_20260414

./.venv/bin/python apps/miroflow-agent/scripts/run_professor_retrieval_top5_eval.py \
  --query-set-json logs/data_agents/professor_phase_a_profile_query_set_prd_full_20260414/query_set.json \
  --shared-db-path logs/data_agents/released_objects.db \
  --vector-db-path logs/data_agents/professor_phase_a_retrieval_eval_prd_full_20260414/retrieval_eval_milvus.db \
  --output-dir logs/data_agents/professor_phase_a_retrieval_eval_prd_full_20260414

./.venv/bin/python apps/miroflow-agent/scripts/run_professor_retrieval_top5_eval.py \
  --judged-report-json logs/data_agents/professor_phase_a_retrieval_eval_prd_full_20260414/retrieval_top5_report.json \
  --output-dir logs/data_agents/professor_phase_a_retrieval_eval_prd_full_20260414

./.venv/bin/python apps/miroflow-agent/scripts/run_professor_phase_a_gate.py \
  --url-summary logs/data_agents/professor_url_md_e2e_prd_full_aggregated_20260414/url_e2e_summary.json \
  --manual-audit-json logs/data_agents/professor_phase_a_profile_machine_audit_prd_full_20260414/phase_a_machine_audit.json \
  --retrieval-eval-json logs/data_agents/professor_phase_a_retrieval_eval_prd_full_20260414/retrieval_eval.json \
  --output-dir logs/data_agents/professor_phase_a_gate_prd_full_profilelevel_20260414
```

## Related

- [教授 URL.md 收口必须逐 URL 验证 `ready` + 论文数据](../workflow-issues/professor-url-md-ready-paper-closure-2026-04-08.md)
- [Data-Agent PRD gap closure must use real-source E2E gates](../workflow-issues/data-agent-real-e2e-gates-2026-04-02.md)
- [官方 publication 证据必须进入教授论文 gate](../integration-issues/official-publication-evidence-fallback-2026-04-14.md)
- [学科感知的 professor quality gate](./discipline-aware-professor-quality-gate-2026-04-14.md)
