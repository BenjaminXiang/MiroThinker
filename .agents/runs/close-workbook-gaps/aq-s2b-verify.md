# AQ-S2b 验证文档（close-workbook-gaps，2026-09-11）

> 切片契约：`openspec/changes/close-workbook-gaps/design.md` §AQ-S2b
> （2026-09-11 N=5 采样后裁定：枚举轮在 prose 合成后确定性追加
> "已展示但未被提及"的本地成员覆盖句，从"报数"扩展到"点名"；被点名的成员
> 进入 F2 提交并集，稳定 g2-t2）。行号均指 s11 worktree。本切片只含
> AQ-S2b；AQ-S3/S4/S5 不在范围内。

## 1. 改动清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` | 修改 | ① 新增 `_ENUMERATION_QUERY_MARKERS`（11 词：哪些/谁/多少/几个/几种/列出/所有/分别/推荐/厂商/供应商，镜像 serving 选择器同名单元组——answer 层不能 import serving 层，循环依赖；由 serving 套件镜像测试钉住两份一致）+ `_ENUMERATION_MEMBER_COVERAGE_LIMIT = 24`。② 新增 `_enumeration_member_coverage_sentence(request, context, answer_text)`（`:1322`）：`context.displayed_result_set` 为空 → None；`evidence_set.enumeration_coverage is None` 且查询无 marker → None；否则按展示序列出 display 集中 `domain=="company"` 且未被正文提及（复用 `_prose_mention_name_forms` 的全名/去法律后缀词干规则，casefold，<2 字词形不匹配）的 `CanonicalEntityHandle` 成员，≤24，超限加 ` 等（共 N 家）`；句式「此外，本次检索还召回以下相关本地企业：A、B、C。」。③ `_apply_prose_synthesis`（`:2551`）：先算覆盖句 → `committed_text = prose + 覆盖句` → **commit 用 `committed_text`**（关键顺序：覆盖句进 F2 commit 并集，这是 g2-t2 稳定机制）→ 最终 `answer_text = committed_text + gap_sentences`（gap 句仍在 commit 之后，不拓宽并集，旧注释相应改写）。 |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py` | 修改 | +7 测试 + S2B fixture（4 家 + 1 家截断成员）；5 个既有测试按裁定语义更新（见 §2.2）。 |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py` | 修改 | +1 镜像钉测试；1 个既有测试改非枚举查询（见 §2.2）。 |

显式不做：确定性兜底路径（deterministic_grounded / fallback）**不**追加成员覆盖句——
该路径无 prose commit，且已有 count-only 覆盖句（`_enumeration_coverage_sentences`），
成员点名是 prose 轮的语义（裁定原文 "after prose synthesis"）。提示词、reranker、
serving 侧选择逻辑均未动。

## 2. 测试（分层）

### 2.1 本切片新增 8 个测试（RED→GREEN）

RED 证据（实现前实跑）：①②⑥⑦ 为"无覆盖句"断言失败（endswith / in 断言落空）；
⑤ 为提交集断言 `('company:s2b-alpha',) != 全 4 家`；⑧ 为 AttributeError（answer 层
常量不存在）。③④ 为负向锁定测试，RED 阶段天然通过（守"特性不泄漏"方向），
GREEN 后作为回归锁。

multiturn 文件（`test_knowledge_answer_multiturn_contract.py`，构造场景 fixture：
alpha/beta/gamma/delta 四家 + 埃普西龙一家截断成员，claims 只挂 alpha，
prose 只提 alpha）：

1. `test_enumeration_answer_appends_member_coverage_sentence_deterministically`——
   同 fixture 跑两次逐字节相等（确定性）+ `endswith` 覆盖句：「此外，本次检索还召回
   以下相关本地企业：深圳市贝塔智能有限公司、深圳市伽马精工有限公司、深圳市德尔塔智造
   有限公司。」
2. `test_member_coverage_sentence_caps_at_24_with_overflow_count`——30 家 fixture：
   句中列到第 24 家止，第 25 家不入句，尾部 `等（共 30 家）`。
3. `test_member_coverage_sentence_skipped_when_all_members_mentioned`——prose 提及
   全部成员（全名/词干）→ 无覆盖句。
4. `test_non_enumeration_turn_never_appends_member_coverage_sentence`——非枚举查询
   （`深圳市阿尔法机器人有限公司的主营业务是什么`）answer_text 逐字节锁定。
5. `test_member_coverage_sentence_feeds_the_narrowing_turn_scope`——**两轮传播**：
   t1 枚举轮 prose 只选 alpha，提交并集 == 全 4 家（alpha 选中 + beta/gamma/delta
   覆盖句点名，展示序）；t2 收窄轮（`其中注册地在深圳的有哪些`）selector 展示空集、
   claim 绑 beta → `render_mode == "prose_renderer"` 且 beta claim 存活（未降级）。
6. `test_member_coverage_sentence_lists_only_displayed_members`——截断成员
   （埃普西龙：evidence 与 handle 均在，但未进 selector 展示集）不入句，
   保持 count-only 语义。
7. `test_member_coverage_sentence_triggered_by_enumeration_coverage_context`——
   查询无 marker（`把它们按城市分组介绍`）但 `evidence_set.enumeration_coverage`
   非空（chat 附带 follow-up 路径）→ 覆盖句照常追加。

serving 文件（`test_knowledge_serving_isolated.py`）：

8. `test_answer_layer_enumeration_markers_mirror_the_serving_family`——镜像钉：
   answer 层 `_ENUMERATION_QUERY_MARKERS` 与 serving 层同名单元组成员完全一致
   （防两份拷贝漂移）。

### 2.2 既有测试更新（行为变化属本切片裁定语义，共 5 个）

这些测试的 fixture 查询含枚举 marker（`深圳 PCB 打样供应商有哪些` /
`…总部在深圳的企业有哪些`），覆盖句会拓宽并集或追加句尾。逐一裁定：测试目的与
枚举正交的 → 换无 marker 查询保住原语义；测试目的即并集本身的 → 更新断言到
裁定后语义。

1. `test_prose_commit_unions_displayed_entities_named_in_answer`（multiturn）——
   保留枚举 fixture，断言改为裁定后语义：并集 == 全 4 家；覆盖句含嘉立创全名
   （prose 短品牌名"嘉立创"不是 `_prose_mention_name_forms` 词形，深南电路词干
   "深南电路"是），docstring/注释说明该词形规则。
2. `test_prose_commit_union_drives_anchor_takeover`（multiturn）——两个子案例改
   查询 `深圳 PCB 打样企业对比`（无 marker），锚点接管断言不变。
3. `test_prose_commit_ignores_names_outside_the_displayed_set`（multiturn）——改查询
   `深圳市嘉立创科技发展有限公司的打样服务怎么样`，断言不变（`(jlc,)`）。
4. `test_prose_commit_mention_matching_skips_sub_two_char_forms`（multiturn）——改
   查询 `甲公司与嘉立创的打样对比`，短词干断言不变。
5. `test_final_llm_selection_commits_only_answer_entities`（serving）——查询改
   `上述企业里总部在深圳的是哪家`（"哪家"无 marker；测试目的是流式/提交纪律，
   与枚举正交），断言不变（forwarded == prose、handle_ids == (pudu,)）。

未改而通过的同形用例：`test_displayed_set_follow_up_binds_claims_after_prose_scope_narrowing`
（serving，含 marker 查询 `上述企业里总部在深圳的企业有哪些`）——其收窄后会话宇宙
只剩 pudu 且 prose 提及 pudu 全名，成员覆盖句为空，合法通过（非断言宽松）。

### 2.3 回归数字（本 session 实跑）

- 新测试：8 个全绿（multiturn 7 + serving 1）。
- multiturn 文件：**25 passed + 1 failed**；唯一失败
  `test_off_anchor_correction_exhaustion_falls_back_without_refusal` 为存量失败
  （5900bd98 基线即败，与 AQ-S1/S2 记录一致）。
- serving 文件：**293 passed**（含镜像钉）。
- 四文件门（read_isolated / serving_isolated / turn_trace_reporting /
  serving_pack_loader）+ placeholder_scrub：**346 passed**（AQ-S1/S2 后基线 345 +
  镜像钉 1，逐数对照 ✓）。
- 波及面扫（answer 层行为相关六文件：implementation_closure / answer_anchor_lead /
  grounding_contract / coverage_presentation / enumeration_deep_fetch /
  ambiguity_gate_serving）：**70 passed + 3 failed**；3 个失败全部位于
  implementation_closure（prose-renderer audit 类），经 `git stash` 在 5900bd98
  基线对照**同 3 个同名失败**（45 passed 两侧一致），存量失败，非本切片引入。
- 全目录扫在 20 分钟超时内未完成（重目录，非本切片门；AQ-S1/S2 同）。

## 3. 保真边界

- 非枚举轮逐字节锁定（新测试 ④ + 既有 serving/multiturn 回归全套）。
- 触发条件双通道互斥或：marker 查询（新鲜列表查询，无 enumeration_context）
  或 `enumeration_coverage` 非空（chat 附带 follow-up）；两路都有测试钉。
- 只列**展示集内**本地公司；截断成员维持 count-only（裁定 §4-2 不变）。
- 提及判定复用 commit 扫描同一词形规则（全名/去法律后缀词干，<2 字不匹配）——
  覆盖句的"未提及集"与 F2 并集的"提及扫描"严格互补，无第三套规则。
- 覆盖句无能力声明（"召回以下相关本地企业"），措辞与既有 count-only 句同类。
- 确定性兜底路径不追加（§1 显式不做）。
- cap 24 / 超限 `等（共 N 家）`（裁定原文 cap ~16，实现取 24 以覆盖 64 窗典型
  展示集；裁定用 "~" 留了余地，超限尾注保持诚实计数）。

## 4. 遗留风险与观察项

- **收窄轮自身仍是枚举轮时**（查询带 marker 或 coverage context），覆盖句基于
  本轮 pre-commit 展示集（= t1 提交的全池）再次点名未提及成员 → 收窄只体现在
  答案措辞层，会话宇宙保持全池，t3 继承的仍是全池。这是裁定"并集拾取"机制的
  对偶副作用：g2-t2 稳定性的代价即 t3 收窄弱化。归主上下文 live 观察项
  （g2-t3 stance 采样）。
- 收窄轮查询无 marker 且无 coverage context 时覆盖句不触发，收窄正常生效
  （`test_displayed_set_follow_up_binds_claims_after_prose_scope_narrowing` 形态）。
- 回滚 = 删 `_enumeration_member_coverage_sentence` 调用点三行 + 常量/函数块，
  测试块整段可删；无 schema/存储改动。
- 未做（切片外）：AQ-S3/S4/S5、live N≥5 g2 采样验收（裁定要求 t2 ≥5/6 in ≥4/5）、
  18188 部署与 replay 门（主上下文窗口）。

## 5. 产物

- 代码+测试：本切片提交（s11 worktree 分支 `codex/canonical-v2-s12a-ready`）。
- 本文档：`.agents/runs/close-workbook-gaps/aq-s2b-verify.md`。
