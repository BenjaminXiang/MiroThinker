# D0 诊断门证据 — B3+B2 逐实体丢失去向（2026-09-11）

> 范围：close-workbook-gaps 的 B3（g2-t1/g5-t1 首问清单缺失）与 B2（g2-t2/g5-t2 追问收窄缺失）。
> 本切片只诊断、不修复。全部证据离线取自生产痕迹与只读数据包，无任何网络访问。

## 0. 方法与会话锚定

数据源（全部只读）：

1. **生产 turn-trace 日志** `var/turn-trace/2026-09-10.jsonl`（worktree 内，18188 真实服务落盘）——
   每轮 lane 计数、web gate drops、session_snapshot（上一轮提交后的 displayed 计数与 anchor）、
   web_outcomes（每个 web 视图原文）。
2. **生产 web lane 缓存** `var/turn-trace/web_lane.sqlite3`（含 WAL，复制后只读）——
   视图键 `sha256(view)`（`web_lane_resilience.py:278`），命中即生产当天真实 bocha/serper 返回体。
3. **run14 归档答案** 主仓 `.agents/runs/testset-baseline-20260909/results-diff-run14-20260910.json`，
   命中口径 = runner `_hit`（`term.casefold() in answer.casefold()`）。
4. **run14 封印包** `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3`（47,071 docs），
   数据天花板；区分"实体自有 identity 文档"与"他文档顺带提及（mention）"。

run14 会话锚定（排除同日 s12f/复跑会话）：
归档 g2-t1 elapsed=41.9s 精确匹配 `JgjH8u4MaHqeIQOTbZuUr4mY20cMC4nF` t1（41.91s）；
归档 g5-t2 elapsed=11.7s 精确匹配 `-YZXc4pO5OHEHdpQtuyKW7XEXtVHYiZc` t2（11.65s）。
且 g2 的 12 家承载集、g5 的 4 家承载集与归档答案逐字一致。
（同日另有 5 承载集的 g2 会话与 5/9 承载集的 g5 会话，属其它 run，见 d0-evidence.json `sessions`。）

采集脚本：`collect_d0_evidence.py`（本目录，可重跑）；结构化证据：`d0-evidence.json`。

## 1. 逐实体丢失去向表（run14 锚定）

阶段定义：0=不在包（数据天花板）｜1=检索未召回（web 面未见；vector/supplemental 为盲格）｜
2=已召回但未进承载/展示集｜3=进承载集但答案未含｜4=答案含但命名未命中 GT 词。

### g2-t1 `中国有哪些成熟的酒店送餐机器人供应商`（FAIL：实体层缺 普渡/开普勒/九号；关键点 5/10）

生产 lane 计数：exact 0 / structured 0 / lexical 0 / web 66→66 / vector 48 / supplemental 10。
**类目查询的确定性 lane 全部空转，web+vector+supplemental 承重。**

| 实体 | 包内 | web 证据 | 承载集 | 答案 | 丢失去向 |
|---|---|---|---|---|---|
| 普渡 | ✓（深圳市普渡科技+成都市普渡机器人两个 identity） | **8 个视图命中**（"普渡机器人携手亚朵…酒店服务"、pudutech 官网） | ✗ | ✗ | **② 召回后未进展示集** |
| 九号 | ✓ | **7 个视图命中**（"九号飞碟D2酒店送物机器人"、"纳恩博(北京)"入厂商榜） | ✗ | ✗ | **② 召回后未进展示集** |
| 开普勒 | ✓（9 文档） | 0 | ✗ | ✗ | ①（vector/supplemental 盲格） |
| 安赛步 | ✓（10 文档） | 0 | ✗ | ✗ | ①（同上） |
| 艾唯尔 | ✓（自有 identity：深圳市艾唯尔科技有限公司，龙岗地址、送餐机器人"小艾"） | 0 | ✗ | ✗ | ①（同上）——**包内资料完整却从未出层** |
| 云迹/擎朗 | ✓ | 8/9 | ✓ | ✓ | 未丢 |
| 小村/中科世界/锐曼 | ✓ | **0/0/1** | ✓ | ✓ | 未丢——**它们 web 面无证据却进了承载集，证明 vector/supplemental lane 在 t1 是有效供源** |

承载集（t1 prose 提交后 = 12 家，t2 探针视图逐字枚举证）：小村/锐曼/中科世界/中铧/中智卫安/普波/中舟/上海擎朗/云迹/睿博天米/智贝尔/科卫。

### g2-t2 `上述企业里总部在深圳的企业有哪些`（FAIL：pool 3/6 < 5）

生产 lane 计数：structured 12→12 / vector 12→12（= 承载集 12 家重查）/ web 74→**7**（`web_subject_consistency` 门丢 67）。

| 实体 | 包内 | t2 web 证据 | 承载输入 | 答案 | 丢失去向 |
|---|---|---|---|---|---|
| 小村/中科世界/锐曼 | ✓ | 1/1/2 | ✓ | ✓ | 未丢 |
| 普渡 | ✓ | **4**（泛深圳视图返普渡内容） | ✗ | ✗ | **② 结构性不可达**：不在 t1 提交的 12 家里；t2 web 面虽召回但被 subject-consistency 门丢 |
| 安赛步/艾唯尔 | ✓ | 0 | ✗ | ✗ | ①（继承 t1 的 ①，且 t2 无新召回通道可入） |

注：答案称"上述十家企业…总部都在深圳"——prose 从 12 选 10（正确剔除云迹/上海擎朗），
t2 自身的语义判断无误；丢的是**输入集构成**。

### g5-t1 `我想找PCB打板， 有哪些推荐`（FAIL：实体层缺一博）

生产 lane 计数：exact/structured/lexical 0 / web 64→64 / vector 48 / supplemental 13。

| 实体 | 包内 | web 证据 | 承载集 | 答案 | 丢失去向 |
|---|---|---|---|---|---|
| 嘉立创 | ✓ | 7 | ✓ | ✓ | 未丢 |
| 深南电路 | ✓（16 文档，identity=深南电路股份有限公司） | 2 | **✗** | **✓**（尾部"此外…深南电路…"提及句） | **② prose 答而未承载**：答案叙述提及但未进 selected_handle_ids，t2 结构性不可达 |
| 一博 | ✓（深圳市一博科技） | 0 | ✗ | ✗ | ①（盲格；同日另一会话一博进了承载 5 家——run 间不稳定） |

t1 prose 提交承载集 = 仅 4 家（顺易捷/驭鹰者/嘉立创/深华科），而答案正文讨论了 8 家+尾部提及 6 家。

### g5-t2 `上述企业有哪些是深圳的企业`（FAIL：key_points 2/12 < 0.75）

生产 lane 计数：structured 4→4 / vector 4→4（= 承载 4 家重查）/ web 84→**3**（门丢 81）。

| 实体 | 包内 | t2 web | 承载输入 | 答案 | 丢失去向 |
|---|---|---|---|---|---|
| 嘉立创/顺易捷 | ✓ | 1/3 | ✓ | ✓ | 未丢 |
| 深南电路 | ✓ | **2** | ✗ | ✗ | **② 继承**（t1 答而未承载）+ t2 web 召回被门丢 |
| 华秋 | **✗ 不在包** | 0 | ✗ | ✗ | **⓪ 数据缺口**（t1 答案尾部"华秋PCB"来自 web 文本，无 canonical identity 可承载） |
| 中信华 | **✗ 不在包** | 0 | ✗ | ✗ | ⓪ 数据缺口 |
| 领智 | **mention-only**（只出现在他文档，无自有 identity） | 0 | ✗ | ✗ | ⓪ 数据缺口（近似） |
| 兴森/一博/则成/上达/精诚达 | ✓ 均在包（兴森=深圳市兴森快捷、上达=上达电子(深圳)、精诚达=深圳市精诚达等 identity） | 0 | ✗ | ✗ | ①（盲格） |

**数据天花板结论**：11 家 GT 中 8 家有包内 identity、1 家 mention-only、2 家不在包。
key_points 12 项（含"广州"例外标记）的 0.75 阈值 = 9 命中，包内可及上限恰为 8+广州标记 = 9——
**验收阈值恰好压在数据天花板上**，任何 pipeline 修复都必须 8 家全中且"广州"例外正确表述才过线。

## 2. 机制链确认（代码级，worktree 行号）

1. **t2 承载输入链**：`_planning_displayed_ids`（`canonical_v2_chat.py:574`，"上述企业"= set referent →
   返回 prior displayed ids）→ `QueryPlanningRequest.displayed_entity_ids`（`:1703`）→
   structured/vector lane 按 id 集重查（trace 12/12、4/4 完全吻合）。
2. **canonical-only 过滤**：`_displayed_ids`（`canonical_v2_chat.py:2035-2048`）只取
   `handle.kind == "canonical"`；`_next_referent_history`（`:680`，`:713-716`）归档时同样过滤——
   web-only 实体永远进不了下一轮参照。
3. **prose 收窄**：`_commit_prose_scope`（`knowledge_answer.py:2488-2559`）以
   `selected_handle_ids` 重写 session displayed set；空选中才保留全集（`:2498-2502`）。
   g5-t1 即 prose 选中 4 < 答案提及 14 的实例。
4. **`required_member_ids` 无生产者**：全仓唯一赋值是 `knowledge_read.py:4292`
   （从 context 抄入 policy）；两处声明默认 `()`（`knowledge_read.py:229/672`）——
   "required_members" 问责分支（`:6911-6939`）在生产中从未激活，
   representative 分支（`:6940+`）`checked/eligible/retrieved/displayed = available` 无成员级核算。
5. **web subject-consistency 门**：t2 两轮各丢 67/74、81/84——收窄轮 web 面即使召回
   GT 实体内容（普渡 4 视图、深南电路 2 视图）也被门丢弃。

## 3. 盲格与边界（诚实清单）

- **vector lane 逐实体成员不可知**：embedding 是远程服务（qwen bundle 指向 100.64.0.27:18005），
  离线无法重放 48 候选名单。小村/中科世界/锐曼 web 面 0 证据却进承载 → vector/supplemental
  在 t1 有效；开普勒/安赛步/艾唯尔是否进过 vector 候选不可判定。包内有 identity（若有点）只说明
  "可被召回"，不证明"被召回"。
- **supplemental lane 内容未落盘**（t1 in=10/13，t2 in=1-3）。
- **evidence set → displayed 的子阶段**（fusion/identity/selector 内部逐实体 disposition）
  生产未落盘；② 内部细分需离线重放栈才能继续拆（装配方案已备，本轮未执行——生产痕迹已足够定位）。
- **prose LLM 的 selected_handle_ids 真值**只有结果可考（t2 探针枚举），选择理由不可考。
- **interpretation** 生产 `CHAT_CONTEXTUAL_INTERPRETATION=on`；g5-t1 run14  traces 显示
  `degradation=interpretation-rejected`（一博会话之一），解释层当日未生效于这些轮次。
- 手动召回目录 `/var/tmp/mirothinker-data-v2/manual-recall-v1` **为空**，manual lane 零贡献，
  不是丢失去向。

## 4. 修复形态含义（证据指向，方案取舍留主上下文）

- **B3（t1 清单构成）**：普渡/九号是"web 证据充足却未进展示集"（② 内部，fusion→handle→selector 段）；
  开普勒/安赛步/艾唯尔是 ①（确定性 lane 对类目查询空转 + vector 未补位/未上位）；
  深南电路是"答而未承载"（prose 选中集与答案叙述脱节）。
- **B2（t2 收窄）**：结构性继承丢失 + subject-consistency 门双重锁死；
  `required_member_ids` 死代码使"上述企业"成员级问责不存在——t2 无法发现"少了谁"。
- **数据缺口**（华秋/中信华/领智）不是 pipeline 缺陷，与 C2 对账口径一致（8/11 在包）。
- **验收风险**：g5-t2 阈值恰好=数据天花板，pipeline 修复后仍须逐家核对 8 家在包实体全部命中。

## 5. 附带发现（移交对应切片）

- run14 g5-t2 答案尾部泄漏 `<|canonical_v2_answer_end|>`；g2-t2 尾部泄漏 `</｜｜DSML｜｜ parameter>`
  （全角竖线 DSML 变体）——B5 已覆盖 selection/answer 两类 marker，这两个变体列入 B5.4 线上复验清单。
- run 间非确定性大：同日 g2 承载集 12 vs 5、g5 承载集 4 vs 5 vs 9——修复验收需多 run 或固定 web 面，
  单次 replay 不能作为 GREEN 充分条件。
