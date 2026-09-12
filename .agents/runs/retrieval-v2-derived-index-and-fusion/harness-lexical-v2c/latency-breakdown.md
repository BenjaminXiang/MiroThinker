# 检索段时延分解（offline harness）

- 生成时间: 2026-09-12T15:06:36.866633+00:00
- 运行来源: `/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/latency/latency_harness.py`
- 组件: worktree `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` + sealed pack `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
- 引导耗时: {"import_s": 2.65, "load_recorded_inputs_s": 0.0, "pack_open_s": 330.02, "planner_compose_s": 73.45, "read_compose_s": 227.66}

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
- 本机: plan 0.01s / read 12.071s (outer 12.071s, delegate 10.255s, 外层校验 1.816s)
- lanes: {"structured": 0.0002, "exact": 0.4246, "lexical": 2.0086, "vector": 3.9749, "web": 11.2199}
- web: search 2.451s (cache 8/8), fetch 36.246s, judge 1.212s, views 0.99s
- rewriter: replay (0s) → ["深圳 激光雷达 企业 产业链", "深圳 激光雷达 厂商", "深圳 激光雷达 公司"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 36.246 | 0.0 |
| read.outer | 1 | 12.071 | 16.785 |
| read.lane.web | 1 | 11.22 | 15.932 |
| read.delegate | 1 | 10.255 | 14.928 |
| web.enrich | 1 | 9.001 | 0.0 |
| read.lane.vector | 1 | 3.975 | 14.063 |
| web.provider.search | 8 | 2.451 | 0.0 |
| read.lane.lexical | 1 | 2.009 | 2.25 |
| iso.validate_release_bound_vector_evidence | 1 | 1.815 | 1.857 |
| web.judge.batch | 1 | 1.212 | 0.0 |
| web.views | 1 | 0.99 | 0.0 |
| read.lane.exact | 1 | 0.425 | 0.43 |
| embed.batch | 2 | 0.168 | 0.0 |
| embed.http | 1 | 0.164 | 0.0 |
| answer.total | 1 | 0.137 | 0.0 |
| read.sufficiency | 1 | 0.083 | 0.084 |

thread samples: {"asyncio-waitpid-0": 207, "canonical-v2-tiered-fetch_0": 207, "MainThread": 207, "canonical-v2-web_0": 206, "canonical-v2-web_2": 205, "canonical-v2-web_1": 205, "canonical-v2-web_3": 204, "canonical-v2-web_5": 203, "canonical-v2-web_4": 203, "canonical-v2-web_7": 202, "canonical-v2-web_6": 202, "ThreadPoolExecutor-0_3": 189, "ThreadPoolExecutor-0_2": 167, "ThreadPoolExecutor-0_1": 167, "ThreadPoolExecutor-0_0": 166, "canonical-v2-llm-judge_0": 41, "ThreadPoolExecutor-1_0": 3}
- 1516× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 262× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 207× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 166× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 157× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678
- 148× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620

### g2-t1 — 中国有哪些成熟的酒店送餐机器人供应商

- 线上同轮: total 38.62s / lanes {"web": {"in": 70, "retained": 70, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 3, "retained": 3, "filtered": 0}}
- 本机: plan 0.003s / read 8.097s (outer 8.096s, delegate 6.615s, 外层校验 1.481s)
- lanes: {"structured": 0.0003, "exact": 0.1939, "lexical": 2.3746, "vector": 4.4423, "web": 6.412}
- web: search 2.081s (cache 12/12), fetch 12.425s, judge 1.036s, views 0.787s
- rewriter: replay (0s) → ["酒店服务机器人厂商", "酒店配送机器人品牌", "酒店送餐机器人供应商"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 12.425 | 0.0 |
| read.outer | 1 | 8.096 | 15.562 |
| read.delegate | 1 | 6.615 | 14.078 |
| read.lane.web | 1 | 6.412 | 13.874 |
| web.enrich | 1 | 4.562 | 0.0 |
| read.lane.vector | 1 | 4.442 | 13.717 |
| read.lane.lexical | 1 | 2.375 | 2.618 |
| web.provider.search | 12 | 2.081 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.481 | 1.483 |
| web.judge.batch | 1 | 1.036 | 0.0 |
| web.views | 2 | 0.787 | 0.0 |
| read.lane.exact | 1 | 0.194 | 0.198 |
| answer.total | 1 | 0.14 | 0.0 |
| embed.batch | 2 | 0.047 | 0.0 |
| read.sufficiency | 1 | 0.046 | 0.046 |
| embed.http | 1 | 0.045 | 0.0 |

thread samples: {"canonical-v2-llm-judge_0": 118, "canonical-v2-web_7": 118, "canonical-v2-web_6": 118, "canonical-v2-web_5": 118, "canonical-v2-web_4": 118, "canonical-v2-web_3": 118, "canonical-v2-web_2": 118, "canonical-v2-web_1": 118, "canonical-v2-web_0": 118, "asyncio-waitpid-0": 118, "canonical-v2-tiered-fetch_0": 118, "MainThread": 118, "ThreadPoolExecutor-2_3": 83, "ThreadPoolExecutor-2_2": 83, "ThreadPoolExecutor-2_1": 83, "ThreadPoolExecutor-2_0": 83, "ThreadPoolExecutor-3_0": 1}
- 1080× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 118× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 82× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 68× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 48× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 37× cache_get@web_lane_resilience.py:174 <- _provider_search@knowledge_serving_isolated.py:1095 <- provider_search@latency_harness.py:576 <- run@thread.py:59

### pcb-t1 — 我想找PCB打板， 有哪些推荐

- 线上同轮: total 29.07s / lanes {"web": {"in": 66, "retained": 66, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 11, "retained": 11, "filtered": 0}}
- 本机: plan 0.002s / read 11.761s (outer 11.759s, delegate 10.255s, 外层校验 1.504s)
- lanes: {"structured": 0.0001, "exact": 0.2494, "lexical": 2.7719, "vector": 4.577}
- web: search 2.921s (cache 10/11), fetch 17.812s, judge 1.336s, views 0.799s
- rewriter: replay (0s) → ["PCB打样 小批量 厂家", "PCB打板 推荐 厂商", "PCB打板 平台 对比"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 17.812 | 0.0 |
| read.outer | 1 | 11.759 | 15.613 |
| read.delegate | 1 | 10.255 | 14.106 |
| read.lane.vector | 1 | 4.577 | 13.734 |
| web.enrich | 1 | 4.551 | 0.0 |
| web.provider.search | 11 | 2.921 | 0.0 |
| read.lane.lexical | 1 | 2.772 | 11.809 |
| iso.validate_release_bound_vector_evidence | 1 | 1.503 | 1.507 |
| web.judge.batch | 1 | 1.336 | 0.0 |
| web.views | 1 | 0.799 | 0.0 |
| read.lane.exact | 1 | 0.249 | 0.254 |
| embed.batch | 2 | 0.176 | 0.0 |
| answer.total | 1 | 0.13 | 0.0 |
| embed.http | 1 | 0.093 | 0.0 |
| read.sufficiency | 1 | 0.062 | 0.062 |
| answer.selector | 1 | 0.003 | 0.003 |

thread samples: {"canonical-v2-llm-judge_0": 217, "canonical-v2-web_7": 217, "canonical-v2-web_6": 217, "canonical-v2-web_5": 217, "canonical-v2-web_4": 217, "canonical-v2-web_3": 217, "canonical-v2-web_2": 217, "canonical-v2-web_1": 217, "canonical-v2-web_0": 217, "asyncio-waitpid-0": 217, "canonical-v2-tiered-fetch_0": 217, "MainThread": 217, "ThreadPoolExecutor-4_3": 216, "ThreadPoolExecutor-4_2": 182, "ThreadPoolExecutor-4_1": 182, "ThreadPoolExecutor-4_0": 181, "ThreadPoolExecutor-5_0": 2}
- 2050× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 217× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 180× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 174× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 114× wait@threading.py:359 <- result@_base.py:451 <- _merged_results_for_views@knowledge_serving_isolated.py:1377 <- merged_for_views@latency_harness.py:606
- 91× do_handshake@ssl.py:1319 <- _create@ssl.py:1041 <- wrap_socket@ssl.py:455 <- _ssl_wrap_socket_impl@ssl_.py:527

### pcb-t2 — 上述企业有哪些是深圳的企业

- 线上同轮: total 15.22s / lanes {"web": {"in": 84, "retained": 27, "filtered": 57}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 32, "retained": 32, "filtered": 0}, "lexical": {"in": 0, "retained": 0, "filtered": 0}, "vector": {"in": 32, "retained": 32, "filtered": 0}}
- 本机: plan 0.006s / read 11.49s (outer 11.488s, delegate 10.115s, 外层校验 1.373s)
- lanes: {"exact": 0.0968, "lexical": 0.1483, "structured": 0.2443, "vector": 0.2718, "web": 12.8969}
- web: search 12.823s (cache 6/9), fetch 5.702s, judge 0s, views 12.652s
- rewriter: replay (0s) → ["深圳 企业 名单", "(\"崇达技术股份有限公司\" OR \"深圳顺易捷科技有限公司\" OR \"深圳市兴森快捷电路科技股份有限公司\" OR \"深圳市一博科技股份有限公司\" OR \"深圳市精诚达电路科技股份有限公司\" OR \"百芯智能制造科技（深圳）有限公司\" OR \"深圳赛维创新技术集团有限公司\" OR \"深圳天创无限科技有限公司\" OR \"深圳市嘉之宏电子有限公司\" OR \"深圳市驭鹰者电子有限公司\" OR \"深圳市鑫盈通达电子科技有限公司\" OR \"深圳市赛尔博特软件有限公司\" OR \"深圳市鸿洋电路科技有限公司\" OR \"深圳市星河电路股份有限公司\" OR \"深圳市柳鑫实业股份有限公司\" OR \"上达电子（深圳）股份有限公司\" OR \"深圳市深华科电子有限公司\" OR \"深圳和美精艺半导体科技股份有限公司\" OR \"深圳市升达康科技有限公司\" OR \"深圳市动力飞扬智能装备有限公司\" OR \"深圳市尊大电子科技有限公司\" OR \"深圳市亿科迈科技有限公司\" OR \"深圳市声雄电子有限公司\" OR \"深圳市汇芯高新科技有限公司\" OR \"深圳市则成电子股份有限公司\" OR \"深圳市特普生科技有限公司\" OR \"诡谷子人工智能科技（深圳）有限公司\" OR \"深圳市零壹八科技有限公司\" OR \"深圳市中科领创实业有限公司\" OR \"深圳市赛晟科技有限公司\" OR \"深圳市盛矽电子科技有限公司\" OR \"深圳市迈威科技有限公司\") 是深圳的企业", "崇达技术股份有限公司 百度百科 深圳"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| read.lane.web | 1 | 12.897 | 24.956 |
| web.provider.search | 9 | 12.823 | 0.0 |
| web.views | 2 | 12.652 | 0.0 |
| read.outer | 1 | 11.488 | 11.519 |
| read.delegate | 1 | 10.115 | 10.143 |
| web.fetch.page | 6 | 5.702 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.372 | 1.375 |
| read.lane.vector | 1 | 0.272 | 2.497 |
| read.lane.structured | 1 | 0.244 | 0.261 |
| read.lane.lexical | 1 | 0.148 | 0.151 |
| embed.batch | 2 | 0.131 | 0.0 |
| read.lane.exact | 1 | 0.097 | 0.099 |
| embed.http | 1 | 0.081 | 0.0 |
| answer.total | 1 | 0.056 | 0.0 |
| plan.total | 1 | 0.006 | 0.0 |
| answer.selector | 1 | 0.003 | 0.003 |

thread samples: {"canonical-v2-llm-judge_0": 226, "canonical-v2-web_7": 226, "canonical-v2-web_6": 226, "canonical-v2-web_5": 226, "canonical-v2-web_4": 226, "canonical-v2-web_3": 226, "canonical-v2-web_2": 226, "canonical-v2-web_1": 226, "canonical-v2-web_0": 226, "asyncio-waitpid-0": 226, "canonical-v2-tiered-fetch_0": 226, "MainThread": 226, "ThreadPoolExecutor-6_4": 225, "ThreadPoolExecutor-6_3": 197, "ThreadPoolExecutor-6_2": 197, "ThreadPoolExecutor-6_1": 197, "ThreadPoolExecutor-6_0": 197, "ThreadPoolExecutor-4_3": 17, "ThreadPoolExecutor-7_0": 2}
- 2543× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 226× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 196× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 189× do_handshake@ssl.py:1319 <- _create@ssl.py:1041 <- wrap_socket@ssl.py:455 <- start_tls@sync.py:165
- 144× wait@threading.py:359 <- result@_base.py:451 <- _merged_results_for_views@knowledge_serving_isolated.py:1377 <- merged_for_views@latency_harness.py:606
- 96× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
