# Phase 6 design inputs (recon agent, 2026-08-19)

实现级设计输入，供 contextual-query-interpretation change 起草用。

## 1. 插入缝：chat 服务 _answer_locked 规划前（推荐）

理解型缺陷（P1 锚点/P3 软主题/P4 指代/P6 扩展）全部发生在绑定/意图层：
canonical_v2_chat.py `_answer_locked` 内四个决策点——
① 澄清闸门 `_referent_clarification_needed`(:730)
② displayed_ids 绑定 `_planning_displayed_ids`/`_history_displayed_ids`(:574/:643)
③ 软主题 `continuation_soft_subject`/`_soft_subject_name`(:1585-1606)
④ 扩展改写 `_expansion_subject_rewrite`(:543)
serving 改写器只能加召回视图，改不了锚点与澄清——放那里治不了 P1/P4/P6。
_ServingQueryRewriter(:1883) 保留原职责；后续可吃 interpreter 的
self_contained_query 作为输入。新模块 canonical_v2_query_interpreter.py
（admin backend），镜像 _ServingQueryRewriter 隔离模式（懒建 client、
有界 executor、硬超时、异常全吞）。

## 2. 接口（Pydantic）

输入：current_query + history_turns（≤5 轮 q/a_head，Phase 0 给
_CommittedSession(:949) 加环形缓冲字段）+ 结构化清单
（active_anchor/displayed_names/referent_history/soft_subject/enumeration_active）。

    class Interpretation(BaseModel):
        subject_ref: SubjectRef | None  # name, source: anchor|displayed|history|query_named|inferred, canonical_id|None, evidence_quote
        intent: Literal["profile","deepen","switch","expand","enumerate","relation","clarify_ambiguous"]
        self_contained_query: str
        confidence: float  # 0-1
        referent_kind: Literal["singular","set","none"]

## 3. 确定性校验（不过即整体弃用 LLM 输出）

1. subject_ref.name 必须命中会话主体清单（锚点/展示/历史/软主题）——防幻觉绑定
2. 查询显式命名其他主体 → 一票否决（复用 has_explicit_named_subject）
3. 人称代词域错配 → 拒绑定仍澄清（复用 referent_subject_domain）
4. subject 过 is_headline_shaped_name——标题永不绑（P1 复发挡板）
5. protected constraints 保留（_extract_protected_slots append-back 不变量）
6. 枚举轮永不单主体（G7 深圳国创教训，Phase 3 豁免不松动）
7. confidence < 0.7 或 schema 非法 → 视同未产出

## 4. 降级设计

机制照抄 _ServingQueryRewriter.__call__(:1965)：executor submit +
future.result(timeout=1.5)，异常/超时/解析失败 → None；四个决策点写成
`if interp is None or 校验失败: 走现路径`——**None=今天的行为，天然零回归**。
超时是墙钟预算不是 contextvar（contextvar 仅供 trace）。
env：CHAT_CONTEXTUAL_INTERPRETATION=off（总开关，默认 off，过闸前留开关后）、
CHAT_INTERPRETER_TIMEOUT_SECONDS=1.5；模型走 CHAT_LLM_PROFILE 快档、temp 0。
观测：复用 TurnTraceCollector.set_interpretation(:1414/:1646 现成缝)
+ 降级 token（interpretation-off/timeout/rejected）。

## 5. GO/NO-GO 闸门

① 七会话重放开层后全 PASS、关闭后亦全 PASS（双向）
② 金标 head-turn + Layer D runner（eval_multi_turn.py）≥ 词表基线；
   新增长尾 RED 用例（该团队/这所大学/零指代省略/裸指示词）≥6 条全过
③ 延迟：e2e p95 劣化 ≤1s；解释器自身 p95 ≤1.5s、超时率 ≤5%
④ 幻觉绑定 = 0（校验拒绝记录全量可查）
⑤ 任一不过 → 留在开关后，本轮照常收尾

## 6. 风险（与 Phase 3 冲突场景）

- LLM 越权解除澄清（G6 正确澄清被推翻，P7 复发源）：约束为清单空时无权 resolve
- LLM 丢显式主体优先（G5 复发）：校验②
- 标题型 subject 绑定（P1 复发）：校验④
- 多意图合并成单改写：interpreter 只供绑定/意图，视图仍多路并行
- 枚举轮误设软主题（G7 中毒）：校验⑥
- 长枚举轮延迟叠加（CHAT_LLM_TIMEOUT_SECONDS=90 运维现实）：1.5s 硬顶
- 原文历史入会话：隐私/保留期需用户拍板（建议随会话 TTL ≤5 轮销毁）

关键文件：canonical_v2_chat.py(:1460-1634 决策缝/:730 澄清闸/:949 会话/
:1069-1238 软主题+标题护栏)；followup_referents.py（词表权威，全保留为
校验器）；knowledge_serving_isolated.py(:1656-1700 常量/:1822 gate/
:1883 rewriter/:2199-2289 视图装配)；turn_trace_context.py（trace 通道
先例）；scripts/replay_fix_round1.py + eval_multi_turn.py（验收 oracle）。
