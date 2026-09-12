# 检索段时延分解（offline harness）

- 生成时间: 2026-09-12T09:09:30.070685+00:00
- 运行来源: `/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/latency/latency_harness.py`
- 组件: worktree `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` + sealed pack `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
- 引导耗时: {"import_s": 2.66, "load_recorded_inputs_s": 0.0, "pack_open_s": 325.25, "planner_compose_s": 80.28, "read_compose_s": 225.99}

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
- 本机: plan 0.01s / read 12.109s (outer 12.109s, delegate 10.314s, 外层校验 1.795s)
- lanes: {"structured": 0.0004, "exact": 0.5455, "lexical": 0.9558, "vector": 3.799, "web": 11.157}
- web: search 2.23s (cache 8/8), fetch 25.198s, judge 1.181s, views 0.96s
- rewriter: replay (0s) → ["深圳 激光雷达 企业 产业链", "深圳 激光雷达 厂商", "深圳 激光雷达 公司"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 7 | 25.198 | 0.0 |
| read.outer | 1 | 12.109 | 16.675 |
| read.lane.web | 1 | 11.157 | 15.72 |
| read.delegate | 1 | 10.314 | 14.837 |
| web.enrich | 1 | 9.001 | 0.0 |
| read.lane.vector | 1 | 3.799 | 14.173 |
| web.provider.search | 8 | 2.23 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.795 | 1.837 |
| web.judge.batch | 1 | 1.181 | 0.0 |
| web.views | 1 | 0.96 | 0.0 |
| read.lane.lexical | 1 | 0.956 | 0.971 |
| read.lane.exact | 1 | 0.545 | 0.552 |
| answer.total | 1 | 0.134 | 0.0 |
| embed.batch | 2 | 0.122 | 0.0 |
| embed.http | 1 | 0.12 | 0.0 |
| read.sufficiency | 1 | 0.083 | 0.084 |

thread samples: {"asyncio-waitpid-0": 210, "canonical-v2-tiered-fetch_0": 210, "MainThread": 210, "canonical-v2-web_0": 209, "canonical-v2-web_1": 208, "canonical-v2-web_2": 207, "canonical-v2-web_4": 206, "canonical-v2-web_3": 206, "canonical-v2-web_6": 205, "canonical-v2-web_5": 205, "canonical-v2-web_7": 203, "ThreadPoolExecutor-0_3": 188, "ThreadPoolExecutor-0_1": 168, "ThreadPoolExecutor-0_2": 167, "ThreadPoolExecutor-0_0": 167, "canonical-v2-llm-judge_0": 44, "ThreadPoolExecutor-1_0": 3}
- 1519× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 353× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 210× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 172× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678
- 166× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7608 <- timing_delegate_execute@latency_harness.py:1066
- 149× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620

### g2-t1 — 中国有哪些成熟的酒店送餐机器人供应商

- 线上同轮: total 38.62s / lanes {"web": {"in": 70, "retained": 70, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 3, "retained": 3, "filtered": 0}}
- 本机: plan 0.003s / read 11.815s (outer 11.813s, delegate 10.236s, 外层校验 1.577s)
- lanes: {"structured": 0.0004, "exact": 0.2546, "lexical": 2.0603, "vector": 3.7593, "web": 10.271}
- web: search 2.38s (cache 12/12), fetch 31.148s, judge 0.645s, views 0.991s
- rewriter: replay (0s) → ["酒店服务机器人厂商", "酒店配送机器人品牌", "酒店送餐机器人供应商"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 9 | 31.148 | 0.0 |
| read.outer | 1 | 11.813 | 14.96 |
| read.lane.web | 1 | 10.271 | 13.412 |
| read.delegate | 1 | 10.236 | 13.375 |
| web.enrich | 1 | 8.604 | 0.0 |
| read.lane.vector | 1 | 3.759 | 12.982 |
| web.provider.search | 12 | 2.38 | 0.0 |
| read.lane.lexical | 1 | 2.06 | 11.037 |
| iso.validate_release_bound_vector_evidence | 1 | 1.577 | 1.584 |
| web.views | 2 | 0.991 | 0.0 |
| web.judge.batch | 1 | 0.645 | 0.0 |
| embed.batch | 2 | 0.526 | 0.0 |
| read.lane.exact | 1 | 0.255 | 0.257 |
| embed.http | 1 | 0.161 | 0.0 |
| answer.total | 1 | 0.126 | 0.0 |
| read.sufficiency | 1 | 0.091 | 0.092 |

thread samples: {"canonical-v2-llm-judge_0": 201, "canonical-v2-web_7": 201, "canonical-v2-web_6": 201, "canonical-v2-web_5": 201, "canonical-v2-web_4": 201, "canonical-v2-web_3": 201, "canonical-v2-web_2": 201, "canonical-v2-web_1": 201, "canonical-v2-web_0": 201, "asyncio-waitpid-0": 201, "canonical-v2-tiered-fetch_0": 201, "MainThread": 201, "ThreadPoolExecutor-2_3": 168, "ThreadPoolExecutor-2_2": 165, "ThreadPoolExecutor-2_1": 164, "ThreadPoolExecutor-2_0": 164, "ThreadPoolExecutor-3_0": 2}
- 1874× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 201× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 164× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7608 <- timing_delegate_execute@latency_harness.py:1066
- 154× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 140× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678
- 139× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620

### pcb-t1 — 我想找PCB打板， 有哪些推荐

- 线上同轮: total 29.07s / lanes {"web": {"in": 66, "retained": 66, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 11, "retained": 11, "filtered": 0}}
- 本机: plan 0.002s / read 8.432s (outer 8.431s, delegate 6.891s, 外层校验 1.54s)
- lanes: {"structured": 0.0001, "exact": 0.2007, "lexical": 3.5303, "vector": 5.3032, "web": 6.7124}
- web: search 1.93s (cache 8/8), fetch 18.383s, judge 0.612s, views 0.738s
- rewriter: replay (0s) → ["PCB打样 小批量 厂家", "PCB打板 推荐 厂商", "PCB打板 平台 对比"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 18.383 | 0.0 |
| read.outer | 1 | 8.431 | 16.399 |
| read.delegate | 1 | 6.891 | 14.856 |
| read.lane.web | 1 | 6.712 | 14.677 |
| web.enrich | 1 | 5.343 | 0.0 |
| read.lane.vector | 1 | 5.303 | 14.574 |
| read.lane.lexical | 1 | 3.53 | 12.508 |
| web.provider.search | 8 | 1.93 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.539 | 1.542 |
| web.views | 1 | 0.738 | 0.0 |
| web.judge.batch | 1 | 0.612 | 0.0 |
| embed.batch | 2 | 0.562 | 0.0 |
| read.lane.exact | 1 | 0.201 | 0.203 |
| embed.http | 1 | 0.135 | 0.0 |
| answer.total | 1 | 0.133 | 0.0 |
| read.sufficiency | 1 | 0.043 | 0.043 |

thread samples: {"canonical-v2-llm-judge_0": 126, "canonical-v2-web_7": 126, "canonical-v2-web_6": 126, "canonical-v2-web_5": 126, "canonical-v2-web_4": 126, "canonical-v2-web_3": 126, "canonical-v2-web_2": 126, "canonical-v2-web_1": 126, "canonical-v2-web_0": 126, "asyncio-waitpid-0": 126, "canonical-v2-tiered-fetch_0": 126, "MainThread": 126, "ThreadPoolExecutor-4_1": 91, "ThreadPoolExecutor-4_0": 91, "ThreadPoolExecutor-4_3": 90, "ThreadPoolExecutor-4_2": 90, "ThreadPoolExecutor-5_0": 2}
- 1054× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 126× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 90× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7608 <- timing_delegate_execute@latency_harness.py:1066
- 64× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 64× create_connection@socket.py:850 <- connect_tcp@sync.py:208 <- _connect@connection.py:124 <- handle_request@connection.py:78
- 62× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263

### pcb-t2 — 上述企业有哪些是深圳的企业

- 线上同轮: total 15.22s / lanes {"web": {"in": 84, "retained": 27, "filtered": 57}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 32, "retained": 32, "filtered": 0}, "lexical": {"in": 0, "retained": 0, "filtered": 0}, "vector": {"in": 32, "retained": 32, "filtered": 0}}
- 本机: plan 0.01s / read 7.362s (outer 7.361s, delegate 5.941s, 外层校验 1.42s)
- lanes: {"lexical": 0.3756, "exact": 0.4246, "structured": 0.5055, "vector": 0.4949, "web": 5.8215}
- web: search 4.333s (cache 8/12), fetch 6.509s, judge 1.039s, views 2.843s
- rewriter: replay (0s) → ["深圳 企业 名单", "(\"崇达技术股份有限公司\" OR \"深圳顺易捷科技有限公司\" OR \"深圳市兴森快捷电路科技股份有限公司\" OR \"深圳市一博科技股份有限公司\" OR \"深圳市精诚达电路科技股份有限公司\" OR \"百芯智能制造科技（深圳）有限公司\" OR \"深圳赛维创新技术集团有限公司\" OR \"深圳天创无限科技有限公司\" OR \"深圳市嘉之宏电子有限公司\" OR \"深圳市驭鹰者电子有限公司\" OR \"深圳市鑫盈通达电子科技有限公司\" OR \"深圳市赛尔博特软件有限公司\" OR \"深圳市鸿洋电路科技有限公司\" OR \"深圳市星河电路股份有限公司\" OR \"深圳市柳鑫实业股份有限公司\" OR \"上达电子（深圳）股份有限公司\" OR \"深圳市深华科电子有限公司\" OR \"深圳和美精艺半导体科技股份有限公司\" OR \"深圳市升达康科技有限公司\" OR \"深圳市动力飞扬智能装备有限公司\" OR \"深圳市尊大电子科技有限公司\" OR \"深圳市亿科迈科技有限公司\" OR \"深圳市声雄电子有限公司\" OR \"深圳市汇芯高新科技有限公司\" OR \"深圳市则成电子股份有限公司\" OR \"深圳市特普生科技有限公司\" OR \"诡谷子人工智能科技（深圳）有限公司\" OR \"深圳市零壹八科技有限公司\" OR \"深圳市中科领创实业有限公司\" OR \"深圳市赛晟科技有限公司\" OR \"深圳市盛矽电子科技有限公司\" OR \"深圳市迈威科技有限公司\") 是深圳的企业", "崇达技术股份有限公司 百度百科 深圳"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| read.outer | 1 | 7.361 | 12.148 |
| web.fetch.page | 8 | 6.509 | 0.0 |
| read.delegate | 1 | 5.941 | 10.726 |
| read.lane.web | 1 | 5.822 | 10.604 |
| web.provider.search | 12 | 4.333 | 0.0 |
| web.views | 2 | 2.843 | 0.0 |
| web.enrich | 1 | 1.46 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.417 | 1.421 |
| web.judge.batch | 1 | 1.039 | 0.0 |
| read.lane.structured | 1 | 0.505 | 5.104 |
| read.lane.vector | 1 | 0.495 | 6.103 |
| read.lane.exact | 1 | 0.425 | 0.442 |
| read.lane.lexical | 1 | 0.376 | 0.392 |
| embed.batch | 2 | 0.251 | 0.0 |
| embed.http | 1 | 0.205 | 0.0 |
| answer.total | 1 | 0.081 | 0.0 |

thread samples: {"canonical-v2-llm-judge_0": 144, "canonical-v2-web_7": 144, "canonical-v2-web_6": 144, "canonical-v2-web_5": 144, "canonical-v2-web_4": 144, "canonical-v2-web_3": 144, "canonical-v2-web_2": 144, "canonical-v2-web_1": 144, "canonical-v2-web_0": 144, "asyncio-waitpid-0": 144, "canonical-v2-tiered-fetch_0": 144, "MainThread": 144, "ThreadPoolExecutor-6_4": 113, "ThreadPoolExecutor-6_3": 113, "ThreadPoolExecutor-6_2": 113, "ThreadPoolExecutor-6_1": 113, "ThreadPoolExecutor-6_0": 112, "ThreadPoolExecutor-7_0": 4}
- 1597× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 144× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 112× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7608 <- timing_delegate_execute@latency_harness.py:1066
- 57× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 54× wait@threading.py:359 <- result@_base.py:451 <- _merged_results_for_views@knowledge_serving_isolated.py:1377 <- merged_for_views@latency_harness.py:606
- 54× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
