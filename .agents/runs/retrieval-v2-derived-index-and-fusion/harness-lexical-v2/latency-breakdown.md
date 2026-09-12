# 检索段时延分解（offline harness）

- 生成时间: 2026-09-12T14:42:53.018404+00:00
- 运行来源: `/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/latency/latency_harness.py`
- 组件: worktree `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` + sealed pack `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
- 引导耗时: {"import_s": 2.85, "load_recorded_inputs_s": 0.0, "pack_open_s": 324.53, "planner_compose_s": 73.41, "read_compose_s": 227.07}

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
- 本机: plan 0.009s / read 11.918s (outer 11.918s, delegate 10.302s, 外层校验 1.616s)
- lanes: {"structured": 0.0004, "exact": 0.6315, "lexical": 1.133, "vector": 3.7037, "web": 11.0662}
- web: search 2.099s (cache 12/12), fetch 29.572s, judge 1.309s, views 0.876s
- rewriter: replay (0s) → ["深圳 激光雷达 企业 产业链", "深圳 激光雷达 厂商", "深圳 激光雷达 公司"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 29.572 | 0.0 |
| read.outer | 1 | 11.918 | 16.168 |
| read.lane.web | 1 | 11.066 | 15.314 |
| read.delegate | 1 | 10.302 | 14.544 |
| web.enrich | 1 | 8.874 | 0.0 |
| read.lane.vector | 1 | 3.704 | 13.759 |
| web.provider.search | 12 | 2.099 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.615 | 1.623 |
| web.judge.batch | 1 | 1.309 | 0.0 |
| read.lane.lexical | 1 | 1.133 | 1.149 |
| web.views | 2 | 0.876 | 0.0 |
| read.lane.exact | 1 | 0.631 | 0.639 |
| answer.total | 1 | 0.133 | 0.0 |
| embed.batch | 2 | 0.13 | 0.0 |
| embed.http | 1 | 0.127 | 0.0 |
| read.sufficiency | 1 | 0.081 | 0.081 |

thread samples: {"asyncio-waitpid-0": 206, "canonical-v2-tiered-fetch_0": 206, "MainThread": 206, "canonical-v2-web_0": 204, "canonical-v2-web_3": 203, "canonical-v2-web_2": 203, "canonical-v2-web_1": 203, "canonical-v2-web_5": 202, "canonical-v2-web_4": 202, "canonical-v2-web_6": 201, "canonical-v2-web_7": 191, "ThreadPoolExecutor-0_3": 188, "ThreadPoolExecutor-0_1": 170, "ThreadPoolExecutor-0_2": 169, "ThreadPoolExecutor-0_0": 169, "canonical-v2-llm-judge_0": 42, "ThreadPoolExecutor-1_0": 3}
- 1608× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 216× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 206× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 168× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 149× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 140× select@selectors.py:468 <- _run_once@base_events.py:1961 <- run_forever@base_events.py:645 <- run_until_complete@base_events.py:678

### g2-t1 — 中国有哪些成熟的酒店送餐机器人供应商

- 线上同轮: total 38.62s / lanes {"web": {"in": 70, "retained": 70, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 3, "retained": 3, "filtered": 0}}
- 本机: plan 0.003s / read 10.195s (outer 10.194s, delegate 8.658s, 外层校验 1.536s)
- lanes: {"structured": 0.0003, "exact": 0.1686, "lexical": 2.4555, "vector": 4.176, "web": 8.4634}
- web: search 3.842s (cache 10/12), fetch 11.002s, judge 1.55s, views 2.74s
- rewriter: replay (0s) → ["酒店服务机器人厂商", "酒店配送机器人品牌", "酒店送餐机器人供应商"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 11.002 | 0.0 |
| read.outer | 1 | 10.194 | 15.212 |
| read.delegate | 1 | 8.658 | 13.674 |
| read.lane.web | 1 | 8.463 | 13.479 |
| read.lane.vector | 1 | 4.176 | 13.297 |
| web.enrich | 1 | 4.162 | 0.0 |
| web.provider.search | 12 | 3.842 | 0.0 |
| web.views | 2 | 2.74 | 0.0 |
| read.lane.lexical | 1 | 2.455 | 3.582 |
| web.judge.batch | 1 | 1.55 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.535 | 1.537 |
| read.lane.exact | 1 | 0.169 | 0.17 |
| answer.total | 1 | 0.133 | 0.0 |
| embed.batch | 2 | 0.069 | 0.0 |
| embed.http | 1 | 0.051 | 0.0 |
| read.sufficiency | 1 | 0.043 | 0.043 |

thread samples: {"canonical-v2-llm-judge_0": 177, "canonical-v2-web_7": 177, "canonical-v2-web_6": 177, "canonical-v2-web_5": 177, "canonical-v2-web_4": 177, "canonical-v2-web_3": 177, "canonical-v2-web_2": 177, "canonical-v2-web_1": 177, "canonical-v2-web_0": 177, "asyncio-waitpid-0": 177, "canonical-v2-tiered-fetch_0": 177, "MainThread": 177, "ThreadPoolExecutor-2_3": 142, "ThreadPoolExecutor-2_2": 142, "ThreadPoolExecutor-2_1": 142, "ThreadPoolExecutor-2_0": 142, "ThreadPoolExecutor-3_0": 1}
- 1797× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 177× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 141× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 83× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 59× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
- 50× wait@threading.py:359 <- result@_base.py:451 <- _merged_results_for_views@knowledge_serving_isolated.py:1377 <- merged_for_views@latency_harness.py:606

### pcb-t1 — 我想找PCB打板， 有哪些推荐

- 线上同轮: total 29.07s / lanes {"web": {"in": 66, "retained": 66, "filtered": 0}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 0, "retained": 0, "filtered": 0}, "lexical": {"in": 64, "retained": 64, "filtered": 0}, "vector": {"in": 64, "retained": 64, "filtered": 0}, "supplemental": {"in": 11, "retained": 11, "filtered": 0}}
- 本机: plan 0.002s / read 9.06s (outer 9.059s, delegate 7.523s, 外层校验 1.536s)
- lanes: {"structured": 0.0001, "exact": 0.3394, "lexical": 3.7053, "vector": 5.4814, "web": 7.277}
- web: search 2.427s (cache 12/12), fetch 21.999s, judge 1.014s, views 0.896s
- rewriter: replay (0s) → ["PCB打样 小批量 厂家", "PCB打板 推荐 厂商", "PCB打板 平台 对比"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 21.999 | 0.0 |
| read.outer | 1 | 9.059 | 16.583 |
| read.delegate | 1 | 7.523 | 15.045 |
| read.lane.web | 1 | 7.277 | 14.797 |
| read.lane.vector | 1 | 5.481 | 14.698 |
| web.enrich | 1 | 5.345 | 0.0 |
| read.lane.lexical | 1 | 3.705 | 3.975 |
| web.provider.search | 12 | 2.427 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.535 | 1.538 |
| web.judge.batch | 1 | 1.014 | 0.0 |
| web.views | 2 | 0.896 | 0.0 |
| read.lane.exact | 1 | 0.339 | 0.343 |
| embed.batch | 2 | 0.198 | 0.0 |
| answer.total | 1 | 0.14 | 0.0 |
| embed.http | 1 | 0.121 | 0.0 |
| read.sufficiency | 1 | 0.04 | 0.04 |

thread samples: {"canonical-v2-llm-judge_0": 142, "canonical-v2-web_7": 142, "canonical-v2-web_6": 142, "canonical-v2-web_5": 142, "canonical-v2-web_4": 142, "canonical-v2-web_3": 142, "canonical-v2-web_2": 142, "canonical-v2-web_1": 142, "canonical-v2-web_0": 142, "asyncio-waitpid-0": 142, "canonical-v2-tiered-fetch_0": 142, "MainThread": 142, "ThreadPoolExecutor-4_2": 106, "ThreadPoolExecutor-4_1": 106, "ThreadPoolExecutor-4_0": 105, "ThreadPoolExecutor-4_3": 105, "ThreadPoolExecutor-5_0": 3}
- 1131× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 162× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 142× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 104× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 93× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 71× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620

### pcb-t2 — 上述企业有哪些是深圳的企业

- 线上同轮: total 15.22s / lanes {"web": {"in": 84, "retained": 27, "filtered": 57}, "exact": {"in": 0, "retained": 0, "filtered": 0}, "structured": {"in": 32, "retained": 32, "filtered": 0}, "lexical": {"in": 0, "retained": 0, "filtered": 0}, "vector": {"in": 32, "retained": 32, "filtered": 0}}
- 本机: plan 0.009s / read 7.806s (outer 7.804s, delegate 6.39s, 外层校验 1.414s)
- lanes: {"exact": 0.2366, "lexical": 0.3662, "vector": 0.4113, "structured": 0.4991, "web": 6.2554}
- web: search 2.613s (cache 8/12), fetch 7.997s, judge 1.246s, views 2.06s
- rewriter: replay (0s) → ["深圳 企业 名单", "(\"崇达技术股份有限公司\" OR \"深圳顺易捷科技有限公司\" OR \"深圳市兴森快捷电路科技股份有限公司\" OR \"深圳市一博科技股份有限公司\" OR \"深圳市精诚达电路科技股份有限公司\" OR \"百芯智能制造科技（深圳）有限公司\" OR \"深圳赛维创新技术集团有限公司\" OR \"深圳天创无限科技有限公司\" OR \"深圳市嘉之宏电子有限公司\" OR \"深圳市驭鹰者电子有限公司\" OR \"深圳市鑫盈通达电子科技有限公司\" OR \"深圳市赛尔博特软件有限公司\" OR \"深圳市鸿洋电路科技有限公司\" OR \"深圳市星河电路股份有限公司\" OR \"深圳市柳鑫实业股份有限公司\" OR \"上达电子（深圳）股份有限公司\" OR \"深圳市深华科电子有限公司\" OR \"深圳和美精艺半导体科技股份有限公司\" OR \"深圳市升达康科技有限公司\" OR \"深圳市动力飞扬智能装备有限公司\" OR \"深圳市尊大电子科技有限公司\" OR \"深圳市亿科迈科技有限公司\" OR \"深圳市声雄电子有限公司\" OR \"深圳市汇芯高新科技有限公司\" OR \"深圳市则成电子股份有限公司\" OR \"深圳市特普生科技有限公司\" OR \"诡谷子人工智能科技（深圳）有限公司\" OR \"深圳市零壹八科技有限公司\" OR \"深圳市中科领创实业有限公司\" OR \"深圳市赛晟科技有限公司\" OR \"深圳市盛矽电子科技有限公司\" OR \"深圳市迈威科技有限公司\") 是深圳的企业", "崇达技术股份有限公司 百度百科 深圳"]

| stage | calls | wall_s | cpu_s |
|---|---:|---:|---:|
| web.fetch.page | 8 | 7.997 | 0.0 |
| read.outer | 1 | 7.804 | 12.106 |
| read.delegate | 1 | 6.39 | 10.689 |
| read.lane.web | 1 | 6.255 | 10.553 |
| web.provider.search | 12 | 2.613 | 0.0 |
| web.enrich | 1 | 2.511 | 0.0 |
| web.views | 2 | 2.06 | 0.0 |
| iso.validate_release_bound_vector_evidence | 1 | 1.412 | 1.415 |
| web.judge.batch | 1 | 1.246 | 0.0 |
| read.lane.structured | 1 | 0.499 | 6.934 |
| read.lane.vector | 1 | 0.411 | 2.561 |
| read.lane.lexical | 1 | 0.366 | 0.382 |
| read.lane.exact | 1 | 0.237 | 0.24 |
| embed.batch | 2 | 0.186 | 0.0 |
| embed.http | 1 | 0.122 | 0.0 |
| answer.total | 1 | 0.08 | 0.0 |

thread samples: {"canonical-v2-llm-judge_0": 152, "canonical-v2-web_7": 152, "canonical-v2-web_6": 152, "canonical-v2-web_5": 152, "canonical-v2-web_4": 152, "canonical-v2-web_3": 152, "canonical-v2-web_2": 152, "canonical-v2-web_1": 152, "canonical-v2-web_0": 152, "asyncio-waitpid-0": 152, "canonical-v2-tiered-fetch_0": 152, "MainThread": 152, "ThreadPoolExecutor-6_3": 121, "ThreadPoolExecutor-6_2": 121, "ThreadPoolExecutor-6_1": 121, "ThreadPoolExecutor-6_0": 121, "ThreadPoolExecutor-6_4": 120, "ThreadPoolExecutor-7_0": 2}
- 1691× _worker@thread.py:90 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 152× _do_waitpid@unix_events.py:1408 <- run@threading.py:1012 <- _bootstrap_inner@threading.py:1075 <- _bootstrap@threading.py:1032
- 119× wait@threading.py:359 <- result@_base.py:451 <- execute@knowledge_read.py:7673 <- timing_delegate_execute@latency_harness.py:1066
- 82× wait@threading.py:355 <- result@_base.py:451 <- fetch@page_fetch.py:208 <- fetch@page_fetch.py:263
- 55× read@ssl.py:1105 <- recv@ssl.py:1232 <- read@sync.py:128 <- _receive_event@http11.py:217
- 49× wait@threading.py:359 <- result@_base.py:451 <- _enrich_with_page_text@knowledge_serving_isolated.py:1436 <- enrich@latency_harness.py:620
