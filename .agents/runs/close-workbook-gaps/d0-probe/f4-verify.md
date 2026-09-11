# F4 验证 — reranker 桶内稳定序修复新旧对照（2026-09-11）

> 变更（close-workbook-gaps B3B2-F4，形态见 design.md「F1-B downstream diagnostic and
> fix F4」段）：`_serving_reranker` 桶内排序键由 `(-raw_score, result_id)` 改为仅
> `-raw_score`（`knowledge_serving_isolated.py:2524-2534`）。本地车道候选
> `raw_score` 全为 1.0，旧键在等分后按随机 hex id 字符串排序；Python sort 稳定，
> 等分候选保持输入序（= 融合首见序 = 车道序 = F1 排名）。不改 48 截断与
> selector local-16 窗（独立决策）。

## 1. 同模式清查（result_id / fused-result 决胜）

- 缺陷点唯一：仅 `_serving_reranker.candidate_key` 为"分数并列后按随机 id 决胜"
  的排名场景，已修。全 canonical_v2 目录 grep `result_id`/`canonical_id` 参与
  sort key 的所有命中复核如下：
- 留观不动（非同类缺陷，无分数维度，确定性归一化序）：`serving_pack_loader.py`
  :927/993/1074/1274 与 `knowledge_read_isolated.py:5508`——车道内部
  `(domain, canonical_id, …)` 归一化排序，canonical_id 对同一实体稳定，非随机
  决胜；改序属另行设计。
- 无 id 决胜：`knowledge_serving_isolated.py:831/893/3308` 为 tier 序/枚举下标
  稳定序；build/postgres 层的 id 排序是 canonical 身份约定序，与排名无关。
- 回放等值校验不受影响：`knowledge_read.py:8034-8045` 仅校验 `ordered_result_ids`
  的集合成员/重复/非空，不校验排序键（回归 328/328 实证）。

## 2. 单测

- 新增 `test_serving_reranker_equal_scores_keep_input_order`：6 个 raw_score=1.0
  的 local lexical 候选，result_id 严格反字典序输入（ff00→aa00）。旧键输出必反转
  （aa00 在前——已用旧键公式对同一组 token 复核确认），稳定序键保持输入序。
- rerank 簇：`-k reranker` 4 passed（新增 1 + 既有 3 不动通过）。

## 3. 离线重放新旧阶段表（canonical-only 口径）

方法：同一探针 `replay_f1b_downstream.py`（sealed pack run14 字节一致副本），
前版输出保留在 `f1b-downstream-trace.json`，F4 后输出在
`f1b-downstream-trace.after-f4.json`；对照由 `compare_f4_stages.py` 生成——
canonical-only 口径：eligible 内 `canonical_id` 非空 + 展示名精确匹配
（探针 gt_table 原生列是子串匹配，会被 web 标题误命中，两口径差异见 §5）。

列：`车道 / eligible序 / ordered序 / local序号 / displayed / payload`。

### g2-t1「中国有哪些成熟的酒店送餐机器人供应商」

| GT | ①lexical | 旧 ordered（local序） | 旧 ④/⑤ | 新 ordered（local序） | 新 ④/⑤ |
|---|---|---|---|---|---|
| 云迹 | 1 | 35（18） | 出局/出局 | **1（1）** | **1 / 1** |
| 普渡 | 2 | 53（27） | 死/死 | **3（2）** | **3 / 3** |
| 开普勒 | 3 | 91（46） | 死/死 | **5（3）** | **5 / 5** |
| 擎朗 | 4 | 95（48） | 死/死 | **7（4）** | **7 / 7** |
| 九号 | 8 | 93（47） | 死/死 | **15（8）** | **15 / 15** |
| 艾唯尔 | 12 | 51（26） | 死/死 | **23（12）** | **23 / 23** |

新 ordered 序恰为 2×lane序−1（local/web 1:1 交错的奇数位）——local 桶=车道序
的直接证据。**六 GT 全活到 payload，local 序 1-12 全在 16 窗内**（任务预期达成）。

### g5-t1「我想找PCB打板， 有哪些推荐」

| GT | ①lexical | 旧 ordered（local序） | 旧 ④/⑤ | 新 ordered（local序） | 新 ④/⑤ |
|---|---|---|---|---|---|
| 深南电路 | 41 | 9（5，hex 运气） | 9 / 9 | 81（41） | 死/死 |
| 顺易捷 | 9 | 67（34） | 死/死 | **17（9）** | **17 / 17** |
| 其余 6 家 | 未入窗 | — | — | — | —（F1 窗口外，不变） |

**顺易捷复活**（任务预期达成）。**需注意的交换**：深南电路旧靠 hex 序运气进窗
（ordered 9），F4 后回到真实车道位（ordered 81 > 48 截断）——g5 payload 内
canonical GT 1→1（运气换成排名）。这是"去随机化"的必然反面，不是回归：
深南电路的 lexical 41 位超出 48 截断×交错放大（local 序 24 以外必死），
属 48 窗语义（本切片不动）；若 F1 窗口后续放宽，稳定序才能把它带上来。
旧生产答案（stage⑥ 录制）点名深南电路——验收重跑时 g5 展示集构成会变
（出：深南电路；入：顺易捷），主上下文验收时留意。

## 4. 回归

- agent 四文件套件（read_isolated / serving_isolated / turn_trace_reporting /
  serving_pack_loader）：**328 passed**（基线 327 + 本切片新增 1），与基线逐数
  对照无差。
- admin trace 两文件（turn_trace_hook / turn_trace_store）：**16/16 passed**，与
  基线一致。

## 5. 保真边界与口径备注

- 重放保真边界同 `f1b-downstream-trace.md` §重放保真边界（web 车道用 trace
  录制视图；哈希伪向量 embedding；page_fetcher 关闭；stage⑥ 为验收录制答案，
  不随离线码变；milvus 走字节一致副本）。
- 探针 gt_table 原生 displayed/payload 列是子串匹配：g2 普渡/九号、
  g5 嘉立创（web 候选 eligible#100/ordered#8）等行会被 web 标题误命中；
  §3 表格全部由 `compare_f4_stages.py` 按 canonical-only 口径重算，两版 JSON
  原始数据未改。

## 6. 产物

- 代码：`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
  （`candidate_key` 去 result_id 决胜 + 注释）。
- 测试：`apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
  （新增 1 个）。
- 证据：`f1b-downstream-trace.json`（前版，未动）、
  `f1b-downstream-trace.after-f4.json`（F4 后）、`compare_f4_stages.py`（对照
  生成器）、运行日志 `f4-probe.log`（*.log 不入库）。
- 本文件。
