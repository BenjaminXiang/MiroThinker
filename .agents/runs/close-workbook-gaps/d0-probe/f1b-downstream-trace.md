# F1-B 下游断点诊断：lexical 48 窗之后，GT 在哪一环被丢/重排

日期：2026-09-11。作者：code agent（诊断专用切片，未改任何生产代码）。
数据：离线重放 run14 sealed pack 上的 g2-t1 / g5-t1 两个首轮（探针
`replay_f1b_downstream.py`，输出 `f1b-downstream-trace.json`，日志
`f1b-probe.log`），对照线上 trace（`var/turn-trace/2026-09-11.jsonl`）与验收答案
（主仓 `.agents/runs/testset-baseline-20260909/results-b3b2-acc-r1.json`）。

## 结论（TL;DR）

**断点只有一处主因：serving 重排器把"随机 hex 的 canonical id 字符串"当成了局部候选的排序键。**

- 本地 exact/structured/lexical 车道的候选构造器 `_candidate_from_document`
  把 `raw_score` 写死为 `1.0`（`knowledge_read_isolated.py:8741`），车道内部的
  F1 fusedScore 排名（云迹1/普渡2/开普勒3/擎朗4/九号8/艾唯尔12）不进入分数。
- `_serving_reranker` 对 local 桶按 `(-raw_score, result_id)` 排序
  （`knowledge_serving_isolated.py:2525-2526`）。raw_score 全员并列 1.0 后，
  次序退化为 `result_id`（= `fused-result:company-c-<随机hex>`）的字符串序——
  **重放实测：ordered 前 48 里的 24 家本地公司，canonical id hex 前缀严格升序，
  一字不差**。
- 随后 `candidate_limit = max(0, plan.max_candidates - direct_result_count) = 48`
  （`knowledge_read.py:8059-8060`）一刀切掉 hex 序靠后的全部候选；selector 的
  local≤16 窗口（`knowledge_serving_isolated.py:5851-5857`）再切一刀。
- 任务书假设的疑点 `knowledge_read.py:7795`（`direct_object_ids` 保序截断）被证伪：
  各车道 `items=()`，direct_items 实测为空，`direct_result_count=0`，该截断未触发。

g2 六 GT 的死法：**5 家死于 stage③ 的 48 截断（hex 序 53/91/95/93/51），
云迹（hex 序 35）过了 ③ 但死在 stage④ 的 local-16 窗口（它是第 18 个 local）**。
g5：深南电路（hex 序 9，纯运气）一路活到答案；顺易捷（lexical 第 9，hex 序 67）
死于 stage③；其余 6 家（嘉立创/一博/兴森/则成/上达/精诚达）从未进入本地召回
（F1 窗口外，属已接受的 F1 存量问题；且即使 vector 车道在生产中召回它们，
raw_score<1.0 也会排在 48 个 1.0 并列之后，同样死于 ③）。

最终答案里的 6 家（中智卫安/睿博天米/中铧/锐曼/中科世界/笨笨）全部是 hex 序
前 16 的"幸运儿"，prose LLM 在这 16 家里按 claim 文本挑了 6 家——stage⑥ 的
LLM 选择行为本身符合设计，**它从未见过 canonical 的普渡/开普勒/擎朗/九号/艾唯尔**。

## 六实体 × 六阶段表（canonical 口径）

阶段定义：① 车道输出（lexical 位次）② lane→direct_items 组装 ③ 融合+重排+
candidate_limit=48 截断（ordered 位次 / 是否存活）④ selector claims+displayed
（local≤16/web≤48）⑤ prose payload 展示集 ⑥ 生产最终答案（验收录制）。

### g2-t1 「中国有哪些成熟的酒店送餐机器人供应商」

| GT | ①lexical | ②direct | ③ordered(是否≤48) | ④displayed | ⑤payload | ⑥答案 |
|---|---|---|---|---|---|---|
| 云迹科技 | 1 | 空 | 35（活） | **出局：第18个local>16** | 无 | 未点名 |
| 普渡（深圳市普渡科技有限公司） | 2 | 空 | 53（**死**） | 无 | 无 | 未点名 |
| 开普勒 | 3 | 空 | 91（**死**） | 无 | 无 | 未点名 |
| 擎朗 | 4 | 空 | 95（**死**） | 无 | 无 | 未点名 |
| 九号机器人 | 8 | 空 | 93（**死**） | 无 | 无 | 未点名 |
| 艾唯尔 | 12 | 空 | 51（**死**，差3位） | 无 | 无 | 未点名 |

注：普渡/九号在 stage④⑤ 的"命中"是 web 网页标题（如「普渡机器人携手亚朵集团…」）
的同名误配，canonical 公司本体从未进入展示集。生产答案点名的 6 家在 selector
local 序列的位次：中智卫安4、睿博天米10、中铧12、锐曼13、中科世界15、笨笨16——
全部压在 16 窗内，与 turn-2 回放视图里的 6 家 displayed set 完全一致。

### g5-t1 「我想找PCB打板， 有哪些推荐」

| GT | ①lexical | ②direct | ③ordered(是否≤48) | ④⑤ | ⑥答案 |
|---|---|---|---|---|---|
| 嘉立创 | 未入窗（pool 54） | 空 | 无 canonical | web 标题误配 | 未点名 |
| 深南电路 | 41 | 空 | 9（活，hex运气） | displayed #9 | **点名（唯一存活GT）** |
| 一博 | 未入窗（pool 98） | 空 | 无 | 无 | 未点名 |
| 顺易捷 | 9 | 空 | 67（**死**） | 无 | 未点名 |
| 兴森 | 未入窗（pool 70） | 空 | 无 | 无 | 未点名 |
| 则成 | 未入窗（pool 62） | 空 | 无 | 无 | 未点名 |
| 上达 | 未入窗（无分） | 空 | 无 | 无 | 未点名 |
| 精诚达 | 未入窗（无分） | 空 | 无 | 无 | 未点名 |

## 断点定位（精确到行）

1. **主断点（丢序）**：
   `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py:8741`
   `_candidate_from_document()` 对 exact/structured/lexical 三车道一律
   `raw_score=1.0`（同函数 8717 `score=1.0`）——车道的 F1 fusedScore 排名不带出。
   `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py:2524-2598`
   `_serving_reranker()`：分桶（mixed/local/web/other）后每桶
   `sort(key=(-raw_score, result_id))`（2525-2526, 2574-2577），再 local/web 1:1
   交错（2578-2588）。1.0 大并列 → 实际按 `fused-result:company-c-<hex>` 字符串序。
   重放证实：g2/g5 两轮，用该算法对 eligible 复算，`predicted == actual` 完全一致。
2. **放大器（截断）**：`knowledge_read.py:8059-8060`
   `candidate_limit = max(0, plan.max_candidates - direct_result_count)`，
   `ordered = ordered[:48]`——hex 序 49 名以后全部消隐（GT 5/6 死于此）；
   `knowledge_serving_isolated.py:5851-5857` selector `local_claim_limit =
   max(bundle.max_candidates, 16) = 16`（bundle `max_candidates=8`）——交错序列里
   第 17 个起的 local 不再进 claims/displayed（云迹死于此：第 18 个 local）。
3. **证伪项**：`knowledge_read.py:7793-7799` 的 `direct_object_ids` 48 截断——
   实测所有车道 `items=()`（web 车道只产 candidates，`knowledge_serving_isolated.py:1638-1641`），
   `direct_result_count=0`，该路径本轮未触发。
4. **下游无辜**：融合 `_default_groups` 保 lane 首见序（`knowledge_read.py:6091-6118`，
   重放中 eligible 位次=lexical 位次：云迹1/普渡2/开普勒3/擎朗4/九号8/艾唯尔12）；
   selector→payload→grounding 透传（stage④=stage⑤）；prose LLM 在错误的输入集上
   做了正常选择。

## 最小修复形态候选

### 提案 A（推荐）：reranker 桶内排序改稳定序——去掉 result_id 决胜键

`_serving_reranker` 的 `candidate_key` 由 `(-raw_score, result_id)` 改为仅
`-raw_score`（Python sort 稳定，并列保持输入序）。输入序 = 融合首见序 =
lane 序（exact→structured→lexical→vector），即 F1 fusedScore 排名自然接管。
- 效果（按重放数据推算）：g2 local 桶 = lexical 窗序，前 24 local = lexical 前 24，
  六 GT 全部存活过 ③；selector 16 窗 = lexical 前 16，艾唯尔(#12) 在窗内，
  六 GT 全部进入 payload 展示集。g5：顺易捷(#9) 复活进窗；其余 6 家仍是 F1 窗口
  问题（已由 F1 切片另行处理）。
- 影响面：仅 serving 重排器的桶内次序；RerankProposal 契约形状不变；
  `raw_score` 全链 1.0 的录制回放校验（`knowledge_read.py:5294-6080` 等）
  不受影响；对命名实体类查询同样成立（exact 命中本来就在输入序头部，稳定序只会
  让它更靠前）；web 桶 raw_score 各不相同，行为不变。
- 确定性：lane 适配器与融合均确定，输入序确定，稳定排序结果确定。

### 提案 B（治本但面广，不建议本轮做）：raw_score 携带真实车道分

`_candidate_from_document` 传出归一化 fusedScore，使跨车道按真实相关度排序。
- 影响面：`raw_score`/`score` 全链有 `== 1.0` 的录制回放等值校验
  （`knowledge_read.py:1920/2234/2569/2924/5294-6080` 等多处），改动会触发
  回放契约级联；`_fused_candidate` 的 `max(raw_score)` 跨车道量纲混用需要一并
  设计。blast radius 明显大于 A，留作后续架构议题。

共同说明：A/B 都不解决 g5 的 6 家窗口外 GT（那是 F1 召回窗口的存量缺口，
pool 54-98 / 无分），也不改动 selector local-16 的"代表十六家"语义
（`knowledge_serving_isolated.py:5851-5858` 注释：其余由 coverage 句披露）。
若产品希望枚举轮展示 >16 家，那是第三个独立决策，不在本切片。

## 重放保真边界（偏差声明）

1. web 车道：探针用 trace 录得的 3 条改写视图 + 基视图（缓存命中），未复现生产
   gap-judge 的 2 条 follow-up 视图与补充探针（`create_llm_judge` 已摘为 None）。
   web 候选仍顶满 48 上限；local 桶由 lexical 主导，GT 结论不受影响。
2. embedding：生产是在线 Qwen 嵌入（`knowledge_build_isolated.py:6736`），探针用
   哈希伪向量。vector 候选 raw_score<1.0，在 local 桶不可能排到 48 个 1.0 并列
   之前，故不改变 GT 命运；vector 成员构成与生产的差异已记录。
3. page_fetcher 失败关闭：web 快照只有 snippet 级文本，快照准入仍通过（适配器
   自建 snippet 快照）；web claim 文本可能略薄于生产。
4. stage⑥ 为验收录制文件中的生产答案（prose LLM 不可离线运行）；stage⑤ payload
   展示集与 selector 输出完全一致，证明 LLM 的输入集确定。
5. milvus 独占锁：线上 18188 持有 sealed 索引。探针仅把 `_open_milvus_client`
   重定向到经 SQLite backup API 取得的字节一致副本（源以 `mode=ro` 打开；marker/
   root/identity 校验仍在真实 root 上跑）；未触碰线上进程与任何生产文件。

## 数据出处

- 探针：`.agents/runs/close-workbook-gaps/d0-probe/replay_f1b_downstream.py`
  （exit=0）；原始输出 `f1b-downstream-trace.json`；运行日志 `f1b-probe.log`。
- 线上 trace：`var/turn-trace/2026-09-11.jsonl`（g2-t1 07:11:22Z / g5-t1 07:12:33Z，
  lexical in=48/retained=48）。
- 生产答案：`/home/longxiang/MiroThinker/.agents/runs/testset-baseline-20260909/results-b3b2-acc-r1.json`
  （g2 点6家漏5+ GT；g5 点6家漏7 GT）。
- F1 窗口证据：`d0-probe/f1-category-recall.json`（48 窗名单 + GT pool 位次）。
- 注意：`f1b-downstream-trace.json` 内 `gt_table` 的 displayed/payload 列是子串
  匹配，会被 web 网页标题误命中（如「普渡机器人携手亚朵集团…」）；本报告的
  六阶段表已按 canonical-only 口径修正（eligible 内 `canonical_id` 非空判定）。
