# 检索段时延分解（offline harness）

- 生成时间: 2026-09-12T06:56:38.627730+00:00
- 运行来源: `/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/latency/latency_harness.py`
- 组件: worktree `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` + sealed pack `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
- 引导耗时: {"import_s": 10.54, "load_recorded_inputs_s": 0.0, "pack_open_s": 328.0, "planner_compose_s": 70.64, "read_compose_s": 225.97}

## 偏差声明 (deviations)
- prose LLM stubbed: generation (live 1.1-6.8s) excluded from answer.total
- contextual interpreter (chat.py, 3s timeout, before planning) not replayed
- replay view order = turn-trace completion order, truncated to the first 3 non-base views
- milvus + web-lane cache are private byte copies; pack/index/marker identity checks still run against the real paths
- session carry for PCB turn 2 comes from this harness's own turn-1 selector output
- replayed turns reuse the live web-view cache when the view text matches (day pinned to the recorded as_of)

## 逐轮分解

### dji-t1 — 大疆创新主要做什么

- 线上同轮: total 75.45s / lanes {"web": {"in": 61, "retained": 50, "filtered": 11}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 0, "retained": 0, "filtered": 0}, "vector": {"in": 16, "retained": 16, "filtered": 0}}
- 本机: plan 0.01s / read 69.275s (outer 69.275s, delegate 67.524s, 外层校验 1.751s)
- lanes: {"structured": 0.0004, "exact": 1.2993, "lexical": 2.4723, "web": 6.7808, "vector": 67.4864}
- web: search 3.878s (cache 8/8), fetch 7.159s, judge 1.834s, views 1.256s
- rewriter: replay (0s) → ["大疆创新 主营业务", "大疆 影像设备 行业应用 大疆创新", "大疆 无人机 产品线 大疆创新"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| read.outer | 1 | 69.275 | 81.109 |
| read.delegate | 1 | 67.524 | 79.355 |
| read.lane.vector | 1 | 67.486 | 79.317 |
| web.fetch.page | 2 | 7.159 | 0.0 |
| read.lane.web | 1 | 6.781 | 6.902 |
| web.provider.search | 8 | 3.878 | 0.0 |
| web.enrich | 1 | 3.641 | 0.0 |
| read.lane.lexical | 1 | 2.472 | 2.497 |
| web.judge.batch | 1 | 1.834 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.751 | 1.753 |
| read.lane.exact | 1 | 1.299 | 1.315 |
| web.views | 1 | 1.256 | 0.0 |
| embed.batch | 2 | 0.059 | 0.0 |
| embed.http | 1 | 0.057 | 0.0 |
| answer.total | 1 | 0.011 | 0.0 |
| plan.total | 1 | 0.01 | 0.0 |

thread samples: {"asyncio-waitpid-0": 1082, "canonical-v2-tiered-fetch_0": 1082, "MainThread": 1082, "canonical-v2-web_1": 1081, "canonical-v2-web_0": 1081, "canonical-v2-web_4": 1079, "canonical-v2-web_3": 1079, "canonical-v2-web_2": 1079, "canonical-v2-web_5": 1078, "canonical-v2-web_7": 1077, "canonical-v2-web_6": 1077, "ThreadPoolExecutor-0_2": 1052, "ThreadPoolExecutor-0_1": 1052, "ThreadPoolExecutor-0_0": 1052, "ThreadPoolExecutor-0_3": 1051, "canonical-v2-llm-judge_0": 995, "ThreadPoolExecutor-1_0": 1}
- 13207× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 1082× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 930× wait@threading.py:355 <- result@_base.py:451 <- execute@knowledge_read.py:7608 <- timing_delegate_execute@latency_harness.py:971
- 331× _canonical_sha256@domain_projection_models.py:35 <- validate_envelope@domain_projection_models.py:375 <- model_validate_json@main.py:766 <- _validated_public_projection@knowledge_read_isolated.py:8150
- 250× __get__@enum.py:202 <- <genexpr>@knowledge_read_isolated.py:7630 <- _professor_vector_display_names@knowledge_read_isolated.py:7627 <- vector_recall@serving_pack_loader.py:1236
- 159× <genexpr>@knowledge_read_isolated.py:7628 <- _professor_vector_display_names@knowledge_read_isolated.py:7627 <- vector_recall@serving_pack_loader.py:1236 <- wrapped@latency_harness.py:527
