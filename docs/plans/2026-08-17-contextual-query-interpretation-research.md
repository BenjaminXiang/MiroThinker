# 调研报告：LLM 理解 + 确定性校验（contextual query interpretation）

> 背景：用户 2026-08-17 Accept `deepening-turn-anchor-carryover` 时判定闭集词表为
> "头痛医头"式过渡方案，要求深入调研"对用户问题全面理解"的正式方案后立项。
> 本报告综合外部（学术 + 工程实践）与仓库内部先例，给出设计推演与立项建议。
> 调研人：ZCode，2026-08-17。

## 0. 结论先行

1. **方案是业界主流成熟模式**：检索前用一次 LLM 调用把上下文依赖的追问"去语境化"
   （de-contextualization / query reformulation before retrieval）——NVIDIA 官方 RAG
   蓝图、Elastic、主流 RAG 框架都用它；学术上 TREC CAsT 已积累七年（任务定义就是
   "把对话轮改写成自包含查询"）。
2. **仓库内部已有一半**：服务路径的 `_ServingQueryRewriter` 本来就是"LLM 提案 +
   protected-slot 确定性校验 + 失败零回归降级"模式，只是**上下文盲**。本方案不是
   引入新架构，是给既有 LLM 腿喂上下文 + 加主体校验。
3. **Legacy 教训说明为什么必须带校验**：旧 A-G LLM 分类器 benchmark 0.690（门 0.9），
   边界类 B=0.35 / G=0.50 最弱——纯 LLM 判别不可靠；规则先行 + LLM 补充是它换来的秩序。
4. **一个立项前必须决策的硬缺口**：V2 会话**不保留对话原文**（只有结构化状态）。
   理解层要么先加轻量对话历史存储，要么覆盖面打折。
5. **延迟预算可行**：SLO p95 检索 6s / 端到端 15s；现有 rewriter 2.0s 超时一腿的
   经验表明预算内可容纳一次快模型调用。

## 1. 外部调研

### 1.1 学术线（TREC CAsT 与改写研究）

- **TREC CAsT**（Conversational Assistance Track, 2019–2021+）：任务即"上下文依赖的
  对话轮 → 自包含查询"；方法从 T5 改写（2020–21）演进到 LLM 改写；ir_datasets 提供
  人工改写版 ground truth——**可直接借鉴其数据形态构造我们的改写评测集**。
- **失效模式研究**（对我们校验层设计的直接输入）：
  - QueryBandits（arXiv 2508.16697）：one-size-fits-all 改写策略本身是幻觉来源，
    应按 query 类型自适应选策略；
  - 幻觉的具体形态 = **无中生有的属性**（编造主体没说过的限定）+ **丢失约束**
    （改写丢了地理/年份/否定等硬约束）；
  - "Generate, but Verify"（NeurIPS 2025）：加验证步显著降幻觉——与我们的确定性
    校验层同构。

### 1.2 工程线（生产系统做法）

- **NVIDIA RAG Blueprint 2.6**（官方生产蓝图）：检索前一次额外 LLM 调用做
  decontextualize；`CONVERSATION_HISTORY=5` 轮 user/assistant 消息对；明确承认
  延迟代价并提供低延迟退化选项（简单拼接历史）；运行时开关可切。**注意：它没有
  输出校验——我们的确定性校验层是超越该蓝本的强化**。
- **Elastic / Meilisearch / 社区共识**：rewrite-then-retrieve 是标准模式；进阶做法是
  多个平行改写器（共指消解、召回扩展、约束过滤各一）。
- **结构化输出 + 校验**（Instructor / Guardrails AI / OpenAI Structured Outputs）：
  Pydantic schema 校验 + 失败自动重问重试、约束解码保证 JSON 合法——提案-校验-兜底
  三段是成熟工程模式，工具链现成。

## 2. 仓库内部先例

### 2.1 既有提案-校验模式（直接放大）

`knowledge_serving_isolated.py` 的 `_ServingQueryRewriter`（:1366–1400, :1621–1664）：
每轮跑 LLM 生成 1–3 条改写视图，`temperature=0`、JSON 输出、**2.0s 硬超时**、失败降级
为"只保留确定性视图（零回归）"；改写后 protected-slot 校验把被丢弃的地理/年份/引号名/
否定词/软主体**追加回**视图文本。→ 本方案 = 同一骨架 + 会话上下文输入 + 主体存在性校验。

### 2.2 Legacy A-G 分类器的教训（ADR-008）

规则先行（~20 条正则），LLM 仅补规则漏网（2.5s 超时、temp 0、JSON、8 个 few-shot、
`CHAT_QUERY_CLASSIFIER=off` 开关）。Benchmark：**整体 0.690 vs 门 0.900**；A=0.70、
**B=0.35**、C=0.93、D=1.0、E=0.80、F=1.0、**G=0.50**。教训：边界模糊类（语义列表、
歧义）恰是 LLM 最弱处——理解层必须 (a) 只提案不裁决，(b) 带 benchmark 门 + 分类型指标。

### 2.3 评测基建已备（可直接当验收 oracle）

- Layer D 多轮 runner（`scripts/eval_multi_turn.py`）：19 组用例、按 required/forbidden
  实体 + 覆盖率 + query_type + set_derived 评分；RED 基线 1/17 → 修复后 D-scope 9/9。
- `scripts/eval_true_accuracy.py` LLM-judge：27 qid，overall ≥0.7 过线。
- 金标集 `docs/测试集答案.xlsx`：17 组 42 行（含多轮）。

### 2.4 硬约束与缺口

| 约束 | 现状 | 影响 |
|---|---|---|
| 对话原文 | `_CommittedSession` 只存结构化状态（锚点/展示集/soft subject/web 残留），**无 query 文本历史** | 理解层需要近几轮原文；须先加环形缓冲（NVIDIA 用 5 轮） |
| 延迟 SLO | 检索 p95 ≤6s、端到端 ≤15s（`eval_latency.py`） | 改写在检索前、不可并行；预算 ~1–2s，需快模型 |
| 哲学契约 | CONTEXT.md 已定义 Retrieval plan / Query rewrite = "LLM 提议 + 确定性校验保留精确约束" | 立项不是破坏确定性，是补完既定设计 |

## 3. 方案设计推演（经调研修正）

**Phase 0（前置小改）**：会话加对话原文环形缓冲（≤5 轮）+ 改写决策入 journal/trace
（与登记 §3 遥测合并做）；UI"查看检索过程"展示"系统理解为：关于 X 的问题"。

**Phase 1（语境化改写，主菜）**：升级现有 rewriter 为 context-aware：
- 输入：当前句 + 近 5 轮原文 + 会话主体清单（soft subject / 锚点名 / 展示集成员名）；
- 输出（JSON schema）：`{self_contained_query, subject_ref, subject_source}`；
- 确定性校验（每一项都对应已知失效模式）：
  1. `subject_ref` 必须命中会话主体清单（防幻觉绑定——张天尧问题在改写层复现的挡板）；
  2. 查询显式命名了别的主体 → 一票否决 LLM 绑定（显式 > 推断）；
  3. 人称代词跨域错配 → 仍强制澄清（复用现有闸门）；
  4. protected constraints 必须保留（复用现有 append-back 校验）；
  5. 失败/超时/JSON 不合法 → 回退词表管线（今天 Accept 的层）；
- 模型：快档模型（`CHAT_LLM_PROFILE` 可切）、temp 0、JSON schema 约束；
- eval-first 验收：Layer D runner + 金标集；词表版成绩为回归下限；**新增长尾 RED 用例**
  = 本次实测的漏网清单（该团队/这所大学/这家机构/零指代省略/裸指示词）。

**Phase 2（结构化理解决策，视 Phase 1 数据再启）**：输出扩为
`{subject, aspect, operation(deepen|switch|expand|enumerate)}`，统一收编现在散落在
各 handler 的猜测——这是"全面理解"的完整形态，但侵入面大，应在 Phase 1 证明价值后立项。

**风险清单**：幻觉绑定（校验①挡）；丢约束（校验④挡）；过度合并多意图
（QueryBandits 结论：保留多视图并行，不要单改写一锤定音）；延迟（快模型+超时降级）；
成本（每轮 +1 调用；同句可缓存）。

## 4. 立项建议

- change id：`contextual-query-interpretation`（Standard→Epic，行为面，全套 OpenSpec +
  verification-contract；eval-first）。
- 验收线草案：① Layer D ≥ 词表版基线且单轮零回归；② 新增长尾用例 ≥6 条全过；
  ③ 延迟 p95 劣化 ≤1s；④ 改写决策 100% 可观测（journal + UI）。
- 需用户拍板的三个决策点：① 每轮 +1 次 LLM 调用的成本是否接受（可先灰度开关）；
  ② 对话原文入会话状态的保留期限（建议 ≤5 轮随会话 TTL 销毁）；
  ③ Phase 2 是否预留。

## 附：主要参考

- TREC CAsT 2019 Overview (arXiv:2003.13624)；ir_datasets CAsT（人工改写 GT）；
  CAsT 2021（T5→LLM 改写演进）
- NVIDIA RAG Blueprint 2.6 Multi-Turn（生产蓝图：检索前 decontextualize + 5 轮历史）
- QueryBandits（arXiv:2508.16697，改写策略自适应/幻觉）；Generate-but-Verify（NeurIPS 2025）
- Elastic Search Labs / Meilisearch 查询改写实践；Instructor / Guardrails AI /
  OpenAI Structured Outputs（提案-校验-重试工具链）
- 仓库内部：ADR-008；`_ServingQueryRewriter`（:1366）；`eval_multi_turn.py`；
  `eval_true_accuracy.py`；CONTEXT.md（Retrieval plan / Query rewrite 定义）
