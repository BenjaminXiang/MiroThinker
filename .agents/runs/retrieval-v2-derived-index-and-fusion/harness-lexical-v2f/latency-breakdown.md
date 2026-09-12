# 检索段时延分解（offline harness）

- 生成时间: 2026-09-12T16:16:01.146835+00:00
- 运行来源: `/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/latency/latency_harness.py`
- 组件: worktree `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` + sealed pack `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
- 引导耗时: {"import_s": 2.63, "load_recorded_inputs_s": 0.0, "pack_open_s": 321.5, "planner_compose_s": 72.08, "read_compose_s": 223.25}

## 偏差声明 (deviations)
- prose LLM stubbed: generation (live 1.1-6.8s) excluded from answer.total
- contextual interpreter (chat.py, 3s timeout, before planning) not replayed
- replay view order = turn-trace completion order, truncated to the first 3 non-base views
- milvus + web-lane cache are private byte copies; pack/index/marker identity checks still run against the real paths
- session carry for PCB turn 2 comes from this harness's own turn-1 selector output
- replayed turns reuse the live web-view cache when the view text matches (day pinned to the recorded as_of)

## 逐轮分解

### lidar-t1 — 深圳有哪些做激光雷达的公司

- 线上同轮: total 44.68s / lanes {"web": {"in": 51, "retained": 51, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 4, "retained": 4, "filtered": 0}}
- 本机: plan 1.046s / read 11.846s (outer 11.846s, delegate 10.267s, 外层校验 1.579s)
- lanes: {"structured": 0.0005, "exact": 0.2366, "vector": 2.6826, "lexical": 9.1357, "web": 10.3587}
- web: search 1.501s (cache 12/12), fetch 20.346s, judge 0.988s, views 0.643s
- rewriter: live (1.036s) → ["深圳 激光雷达 公司", "深圳 激光雷达 厂商", "深圳 激光雷达 企业 产业链"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 7 | 20.346 | 0.0 |
| read.outer | 1 | 11.846 | 20.994 |
| read.lane.web | 1 | 10.359 | 19.504 |
| read.delegate | 1 | 10.267 | 19.409 |
| read.lane.lexical | 1 | 9.136 | 19.135 |
| web.enrich | 1 | 8.702 | 0.0 |
| read.lane.vector | 1 | 2.683 | 12.675 |
| iso.validate_release_bound_vector_evidence | 1 | 1.578 | 1.585 |
| web.provider.search | 12 | 1.501 | 0.0 |
| plan.total | 1 | 1.046 | 0.0 |
| plan.proposal | 1 | 1.039 | 0.219 |
| plan.rewrite.live | 1 | 1.036 | 0.216 |
| web.judge.batch | 1 | 0.988 | 0.0 |
| web.views | 2 | 0.643 | 0.0 |
| read.lane.exact | 1 | 0.237 | 0.24 |
| answer.total | 1 | 0.137 | 0.0 |

thread samples: {"canonical-v2-query-rewrite_0": 205, "asyncio-waitpid-0": 205, "canonical-v2-tiered-fetch_0": 205, "MainThread": 205, "canonical-v2-web_0": 182, "canonical-v2-web_2": 181, "canonical-v2-web_1": 181, "canonical-v2-web_4": 180, "canonical-v2-web_3": 180, "canonical-v2-web_7": 179, "canonical-v2-web_6": 179, "canonical-v2-web_5": 179, "ThreadPoolExecutor-0_3": 152, "ThreadPoolExecutor-0_1": 146, "ThreadPoolExecutor-0_0": 146, "ThreadPoolExecutor-0_2": 146, "canonical-v2-llm-judge_0": 52, "ThreadPoolExecutor-1_0": 1}
- 1567× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 273× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 205× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 145× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 145× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678
- 120× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1439 <- enrich@latency_harness.py:620

### g2-t1 — 中国有哪些成熟的酒店送餐机器人供应商

- 线上同轮: total 38.62s / lanes {"web": {"in": 70, "retained": 70, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 3, "retained": 3, "filtered": 0}}
- 本机: plan 0.812s / read 5.83s (outer 5.829s, delegate 4.288s, 外层校验 1.541s)
- lanes: {"structured": 0.0003, "exact": 0.104, "lexical": 0.6069, "vector": 2.79, "web": 4.0904}
- web: search 1.523s (cache 12/12), fetch 18.218s, judge 1.284s, views 0.601s
- rewriter: live (0.809s) → ["酒店送餐机器人供应商", "酒店服务机器人厂商", "酒店配送机器人品牌"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 9 | 18.218 | 0.0 |
| read.outer | 1 | 5.829 | 13.643 |
| read.delegate | 1 | 4.288 | 12.1 |
| read.lane.web | 1 | 4.09 | 11.899 |
| read.lane.vector | 1 | 2.79 | 11.817 |
| web.enrich | 1 | 2.179 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.54 | 1.543 |
| web.provider.search | 12 | 1.523 | 0.0 |
| web.judge.batch | 1 | 1.284 | 0.0 |
| plan.total | 1 | 0.812 | 0.0 |
| plan.proposal | 1 | 0.81 | 0.038 |
| plan.rewrite.live | 1 | 0.809 | 0.036 |
| read.lane.lexical | 1 | 0.607 | 0.648 |
| web.views | 2 | 0.601 | 0.0 |
| answer.total | 1 | 0.134 | 0.0 |
| read.lane.exact | 1 | 0.104 | 0.125 |

thread samples: {"canonical-v2-llm-judge_0": 126, "canonical-v2-web_7": 126, "canonical-v2-web_6": 126, "canonical-v2-web_5": 126, "canonical-v2-web_4": 126, "canonical-v2-web_3": 126, "canonical-v2-web_2": 126, "canonical-v2-web_1": 126, "canonical-v2-web_0": 126, "canonical-v2-query-rewrite_0": 126, "asyncio-waitpid-0": 126, "canonical-v2-tiered-fetch_0": 126, "MainThread": 126, "ThreadPoolExecutor-2_3": 74, "ThreadPoolExecutor-2_2": 74, "ThreadPoolExecutor-2_1": 74, "ThreadPoolExecutor-2_0": 73, "ThreadPoolExecutor-3_0": 1}
- 1286× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 126× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 72× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 58× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 47× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 39× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678

### pcb-t1 — 我想找PCB打板， 有哪些推荐

- 线上同轮: total 29.07s / lanes {"web": {"in": 66, "retained": 66, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 11, "retained": 11, "filtered": 0}}
- 本机: plan 1.048s / read 6.63s (outer 6.628s, delegate 5.099s, 外层校验 1.529s)
- lanes: {"structured": 0.0003, "exact": 0.1518, "lexical": 0.7114, "vector": 2.6095, "web": 4.8828}
- web: search 1.695s (cache 8/8), fetch 21.016s, judge 0.434s, views 0.549s
- rewriter: live (1.046s) → ["PCB打板 推荐 厂商", "PCB打样 小批量 厂家", "PCB打板 平台 对比"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 21.016 | 0.0 |
| read.outer | 1 | 6.628 | 14.469 |
| read.delegate | 1 | 5.099 | 12.936 |
| read.lane.web | 1 | 4.883 | 12.717 |
| web.enrich | 1 | 3.882 | 0.0 |
| read.lane.vector | 1 | 2.61 | 11.9 |
| web.provider.search | 8 | 1.695 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.529 | 1.532 |
| plan.total | 1 | 1.048 | 0.0 |
| plan.proposal | 1 | 1.047 | 0.043 |
| plan.rewrite.live | 1 | 1.046 | 0.043 |
| read.lane.lexical | 1 | 0.711 | 4.947 |
| web.views | 1 | 0.549 | 0.0 |
| web.judge.batch | 1 | 0.434 | 0.0 |
| read.lane.exact | 1 | 0.152 | 0.157 |
| answer.total | 1 | 0.12 | 0.0 |

thread samples: {"canonical-v2-llm-judge_0": 115, "canonical-v2-web_7": 115, "canonical-v2-web_6": 115, "canonical-v2-web_5": 115, "canonical-v2-web_4": 115, "canonical-v2-web_3": 115, "canonical-v2-web_2": 115, "canonical-v2-web_1": 115, "canonical-v2-web_0": 115, "canonical-v2-query-rewrite_0": 115, "asyncio-waitpid-0": 115, "canonical-v2-tiered-fetch_0": 115, "MainThread": 115, "ThreadPoolExecutor-4_2": 61, "ThreadPoolExecutor-4_1": 61, "ThreadPoolExecutor-4_0": 61, "ThreadPoolExecutor-4_3": 60, "ThreadPoolExecutor-5_0": 2}
- 1145× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 115× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 63× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 60× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 53× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 42× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1439 <- enrich@latency_harness.py:620

### pcb-t2 — 上述企业有哪些是深圳的企业

- 线上同轮: total 15.22s / lanes {"web": {"in": 84, "retained": 27, "filtered": 57}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 32, "retained": 32, "filtered": 0}, "lexical": {"in": 0, "retained": 0, "filtered": 0}, "vector": {"in": 32, "retained": 32, "filtered": 0}}
- 本机: plan 0.776s / read 8.272s (outer 8.269s, delegate 6.866s, 外层校验 1.403s)
- lanes: {"exact": 0.1962, "structured": 0.3081, "lexical": 0.3272, "vector": 0.3849, "web": 6.7347}
- web: search 6.347s (cache 4/12), fetch 5.069s, judge 1.123s, views 2.892s
- rewriter: live (0.765s) → ["深圳 企业 名单", "深圳 上市公司 企业"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| read.outer | 1 | 8.269 | 11.975 |
| read.delegate | 1 | 6.866 | 10.569 |
| read.lane.web | 1 | 6.735 | 10.436 |
| web.provider.search | 12 | 6.347 | 0.0 |
| web.fetch.page | 5 | 5.069 | 0.0 |
| web.views | 2 | 2.892 | 0.0 |
| web.enrich | 1 | 2.328 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.401 | 1.404 |
| web.judge.batch | 1 | 1.123 | 0.0 |
| plan.total | 1 | 0.776 | 0.0 |
| plan.proposal | 1 | 0.77 | 0.043 |
| plan.rewrite.live | 1 | 0.765 | 0.039 |
| read.lane.vector | 1 | 0.385 | 3.576 |
| read.lane.lexical | 1 | 0.327 | 0.517 |
| read.lane.structured | 1 | 0.308 | 0.496 |
| read.lane.exact | 1 | 0.196 | 0.291 |

thread samples: {"canonical-v2-llm-judge_0": 178, "canonical-v2-web_7": 178, "canonical-v2-web_6": 178, "canonical-v2-web_5": 178, "canonical-v2-web_4": 178, "canonical-v2-web_3": 178, "canonical-v2-web_2": 178, "canonical-v2-web_1": 178, "canonical-v2-web_0": 178, "canonical-v2-query-rewrite_0": 178, "asyncio-waitpid-0": 178, "canonical-v2-tiered-fetch_0": 178, "MainThread": 178, "ThreadPoolExecutor-6_3": 132, "ThreadPoolExecutor-6_2": 132, "ThreadPoolExecutor-6_1": 132, "ThreadPoolExecutor-6_0": 132, "ThreadPoolExecutor-6_4": 131, "ThreadPoolExecutor-7_0": 2}
- 2156× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 178× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 131× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 94× read@ssl.py:1103 <- recv_into@ssl.py:1251 <- readinto@socket.py:720 <- _read_status@client.py:292
- 57× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 56× wait@threading.py:359 <- result@_base.py:451 <- _merged_results_for_views@knowledge_serving_isolated.py:1380 <- merged_for_views@latency_harness.py:606
