# 检索段时延分解（offline harness）

- 生成时间: 2026-09-12T15:36:44.375014+00:00
- 运行来源: `/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/latency/latency_harness.py`
- 组件: worktree `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` + sealed pack `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
- 引导耗时: {"import_s": 2.64, "load_recorded_inputs_s": 0.0, "pack_open_s": 330.07, "planner_compose_s": 73.19, "read_compose_s": 226.61}

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
- 本机: plan 1.35s / read 11.856s (outer 11.856s, delegate 10.276s, 外层校验 1.58s)
- lanes: {"structured": 0.0005, "exact": 0.1541, "vector": 2.6578, "lexical": 8.9906}
- web: search 1.873s (cache 11/11), fetch 38.569s, judge 1.433s, views 0.621s
- rewriter: live (1.341s) → ["深圳 激光雷达 公司", "深圳 激光雷达 厂商", "深圳 激光雷达 企业 产业链"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 38.569 | 0.0 |
| read.outer | 1 | 11.856 | 20.927 |
| read.delegate | 1 | 10.276 | 19.328 |
| web.enrich | 1 | 9.994 | 0.0 |
| read.lane.lexical | 1 | 8.991 | 19.055 |
| read.lane.vector | 1 | 2.658 | 12.688 |
| web.provider.search | 11 | 1.873 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.579 | 1.598 |
| web.judge.batch | 1 | 1.433 | 0.0 |
| plan.total | 1 | 1.35 | 0.0 |
| plan.proposal | 1 | 1.343 | 0.212 |
| plan.rewrite.live | 1 | 1.341 | 0.209 |
| web.views | 1 | 0.621 | 0.0 |
| read.lane.exact | 1 | 0.154 | 0.157 |
| answer.total | 1 | 0.13 | 0.0 |
| read.sufficiency | 1 | 0.076 | 0.076 |

thread samples: {"canonical-v2-query-rewrite_0": 214, "asyncio-waitpid-0": 214, "canonical-v2-tiered-fetch_0": 214, "MainThread": 214, "ThreadPoolExecutor-0_3": 187, "canonical-v2-web_1": 186, "canonical-v2-web_0": 186, "canonical-v2-web_4": 185, "canonical-v2-web_3": 185, "canonical-v2-web_2": 185, "canonical-v2-web_7": 184, "canonical-v2-web_6": 184, "canonical-v2-web_5": 184, "ThreadPoolExecutor-0_1": 151, "ThreadPoolExecutor-0_0": 151, "ThreadPoolExecutor-0_2": 151, "canonical-v2-llm-judge_0": 26, "ThreadPoolExecutor-1_0": 1}
- 1469× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 337× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 214× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 150× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 150× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 141× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678

### g2-t1 — 中国有哪些成熟的酒店送餐机器人供应商

- 线上同轮: total 38.62s / lanes {"web": {"in": 70, "retained": 70, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 3, "retained": 3, "filtered": 0}}
- 本机: plan 0.857s / read 8.416s (outer 8.414s, delegate 6.881s, 外层校验 1.533s)
- lanes: {"web": 6.6448, "structured": 0.0001, "exact": 0.1125, "lexical": 0.7893, "vector": 2.7387}
- web: search 1.678s (cache 12/12), fetch 7.582s, judge 1.283s, views 0.56s
- rewriter: live (0.853s) → ["酒店送餐机器人供应商", "酒店服务机器人厂商", "酒店配送机器人品牌"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| read.lane.web | 2 | 18.732 | 33.154 |
| read.outer | 1 | 8.414 | 13.766 |
| web.fetch.page | 8 | 7.582 | 0.0 |
| read.delegate | 1 | 6.881 | 12.23 |
| web.enrich | 1 | 4.777 | 0.0 |
| read.lane.vector | 1 | 2.739 | 11.823 |
| web.provider.search | 12 | 1.678 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.533 | 1.536 |
| web.judge.batch | 1 | 1.283 | 0.0 |
| plan.total | 1 | 0.857 | 0.0 |
| plan.proposal | 1 | 0.855 | 0.052 |
| plan.rewrite.live | 1 | 0.853 | 0.05 |
| read.lane.lexical | 1 | 0.789 | 9.644 |
| web.views | 2 | 0.56 | 0.0 |
| answer.total | 1 | 0.127 | 0.0 |
| read.lane.exact | 1 | 0.113 | 0.13 |

thread samples: {"canonical-v2-llm-judge_0": 156, "canonical-v2-web_7": 156, "canonical-v2-web_6": 156, "canonical-v2-web_5": 156, "canonical-v2-web_4": 156, "canonical-v2-web_3": 156, "canonical-v2-web_2": 156, "canonical-v2-web_1": 156, "canonical-v2-web_0": 156, "canonical-v2-query-rewrite_0": 156, "asyncio-waitpid-0": 156, "canonical-v2-tiered-fetch_0": 156, "MainThread": 156, "ThreadPoolExecutor-2_2": 103, "ThreadPoolExecutor-2_1": 103, "ThreadPoolExecutor-2_0": 103, "ThreadPoolExecutor-2_3": 102, "ThreadPoolExecutor-3_0": 1}
- 1751× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 156× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 102× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 91× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 68× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 32× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263

### pcb-t1 — 我想找PCB打板， 有哪些推荐

- 线上同轮: total 29.07s / lanes {"web": {"in": 66, "retained": 66, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 11, "retained": 11, "filtered": 0}}
- 本机: plan 1.064s / read 7.514s (outer 7.512s, delegate 6.002s, 外层校验 1.51s)
- lanes: {"structured": 0.0003, "exact": 0.1123, "lexical": 0.785, "vector": 2.8268, "web": 5.8188}
- web: search 1.747s (cache 8/8), fetch 17.003s, judge 0.496s, views 0.567s
- rewriter: live (1.062s) → ["PCB打板 推荐 厂商", "PCB打样 小批量 厂家", "PCB打板 平台 对比"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 17.003 | 0.0 |
| read.outer | 1 | 7.512 | 13.855 |
| read.delegate | 1 | 6.002 | 12.342 |
| read.lane.web | 1 | 5.819 | 12.158 |
| web.enrich | 1 | 4.75 | 0.0 |
| read.lane.vector | 1 | 2.827 | 12.024 |
| web.provider.search | 8 | 1.747 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.51 | 1.512 |
| plan.total | 1 | 1.064 | 0.0 |
| plan.proposal | 1 | 1.063 | 0.028 |
| plan.rewrite.live | 1 | 1.062 | 0.028 |
| read.lane.lexical | 1 | 0.785 | 9.322 |
| web.views | 1 | 0.567 | 0.0 |
| web.judge.batch | 1 | 0.496 | 0.0 |
| answer.total | 1 | 0.121 | 0.0 |
| read.lane.exact | 1 | 0.112 | 0.119 |

thread samples: {"canonical-v2-llm-judge_0": 151, "canonical-v2-web_7": 151, "canonical-v2-web_6": 151, "canonical-v2-web_5": 151, "canonical-v2-web_4": 151, "canonical-v2-web_3": 151, "canonical-v2-web_2": 151, "canonical-v2-web_1": 151, "canonical-v2-web_0": 151, "canonical-v2-query-rewrite_0": 151, "asyncio-waitpid-0": 151, "canonical-v2-tiered-fetch_0": 151, "MainThread": 151, "ThreadPoolExecutor-4_3": 95, "ThreadPoolExecutor-4_2": 95, "ThreadPoolExecutor-4_1": 95, "ThreadPoolExecutor-4_0": 95, "ThreadPoolExecutor-5_0": 1}
- 1472× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 182× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 151× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 95× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 75× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 65× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217

### pcb-t2 — 上述企业有哪些是深圳的企业

- 线上同轮: total 15.22s / lanes {"web": {"in": 84, "retained": 27, "filtered": 57}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 32, "retained": 32, "filtered": 0}, "lexical": {"in": 0, "retained": 0, "filtered": 0}, "vector": {"in": 32, "retained": 32, "filtered": 0}}
- 本机: plan 1.232s / read 9.409s (outer 9.408s, delegate 8.002s, 外层校验 1.406s)
- lanes: {"exact": 0.1904, "structured": 0.2265, "lexical": 0.3246, "vector": 0.3323, "web": 7.8732}
- web: search 6.186s (cache 4/12), fetch 7.891s, judge 1.269s, views 2.66s
- rewriter: live (1.223s) → ["深圳 企业 名单", "深圳 上市公司 企业"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| read.outer | 1 | 9.408 | 11.784 |
| read.delegate | 1 | 8.002 | 10.375 |
| web.fetch.page | 5 | 7.891 | 0.0 |
| read.lane.web | 1 | 7.873 | 10.241 |
| web.provider.search | 12 | 6.186 | 0.0 |
| web.enrich | 1 | 3.555 | 0.0 |
| web.views | 2 | 2.66 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.404 | 1.407 |
| web.judge.batch | 1 | 1.269 | 0.0 |
| plan.total | 1 | 1.232 | 0.0 |
| plan.proposal | 1 | 1.226 | 0.044 |
| plan.rewrite.live | 1 | 1.223 | 0.041 |
| read.lane.vector | 1 | 0.332 | 5.004 |
| read.lane.lexical | 1 | 0.325 | 3.969 |
| read.lane.structured | 1 | 0.227 | 0.381 |
| read.lane.exact | 1 | 0.19 | 0.307 |

thread samples: {"canonical-v2-llm-judge_0": 210, "canonical-v2-web_7": 210, "canonical-v2-web_6": 210, "canonical-v2-web_5": 210, "canonical-v2-web_4": 210, "canonical-v2-web_3": 210, "canonical-v2-web_2": 210, "canonical-v2-web_1": 210, "canonical-v2-web_0": 210, "canonical-v2-query-rewrite_0": 210, "asyncio-waitpid-0": 210, "canonical-v2-tiered-fetch_0": 210, "MainThread": 210, "ThreadPoolExecutor-6_3": 156, "ThreadPoolExecutor-6_2": 156, "ThreadPoolExecutor-6_1": 156, "ThreadPoolExecutor-6_0": 155, "ThreadPoolExecutor-6_4": 155, "ThreadPoolExecutor-7_0": 2}
- 2513× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 210× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 154× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 113× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 95× read@ssl.py:1103 <- recv_into@ssl.py:1251 <- readinto@socket.py:720 <- _read_status@client.py:292
- 70× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
