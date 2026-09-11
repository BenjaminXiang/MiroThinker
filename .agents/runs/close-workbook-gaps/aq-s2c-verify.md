# AQ-S2c 验证文档（close-workbook-gaps，2026-09-11）

> 切片契约：`openspec/changes/close-workbook-gaps/design.md` §AQ-S2b amendment
> （2026-09-11，A-2 排名表后裁定：枚举轮成员覆盖句的成员来源从"展示集（claim
> 窗 32）"扩到"本轮召回集（read 窗 64）"——recalled-but-not-claimed 成员
> （深南电路 rank37 / 嘉立创 rank56）按召回 rank 序点名，cap 32，read 窗外的
> 未检索项仍 count-only；claim 窗 32/32 不动；被点名成员进 F2 提交并集，收窄轮
> 继承全池）。行号均指 s11 worktree。本切片只含 AQ-S2c。

## 0. 可行性结论（通道勘察）

答案层拿到召回集**不需要新契约**：`request.evidence_set.entity_handles` 即
本轮 read 窗全量句柄 —— `knowledge_read.py:8059-8112` 中
`ordered[:plan.max_candidates]`（枚举轮 = 64，`_ENUMERATION_CANDIDATE_WINDOW`）
经 fusion → rerank → 截窗后逐候选构造，`entity_handles` 顺序即召回 rank 序；
serving 层不二次截断（claim 窗在 `_answer_selector` 的 claims 层生效，不回写
evidence_set）；`_advance_session` 把全部句柄注册进 `state.handles`
（`knowledge_answer.py:2736-2751`），commit 阶段可按 id 取回。备选通道
`enumeration_coverage.retrieved_ids`（`_unique_object_ids(items)` 首现序）只携带
object_id、无 display_name/domain，且混入 direct/supplemental 项，语义不如
entity_handles 准确，未采用。

## 1. 改动清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` | 修改 | ① `_ENUMERATION_MEMBER_COVERAGE_LIMIT` 24→32（`:1323`）。② 新增 `_is_enumeration_turn(request)`（`:1326`）：`enumeration_coverage` 非空 或 查询含 marker —— 把覆盖句与 commit 扫描的触发门禁收敛为一个定义。③ `_enumeration_member_coverage_sentence`（`:1337`）：成员源从 `context.displayed_result_set.handles`（展示集）换成 `request.evidence_set.entity_handles`（召回集，rank 序）；`displayed is None → None` 早退改为 `context is None → None`（无会话上下文不点名）+ 召回集过滤后空 → None；过滤（CanonicalEntityHandle + company + 未提及 `_prose_mention_name_forms`）、措辞、cap 尾注格式不变。④ `_commit_prose_scope`（`:2650`）：枚举轮把 F2 "answer-named" 提及扫描池从展示集扩到召回集句柄（展示集句柄在前保持原序，召回新增 canonical company 句柄按 rank 序追加），非枚举轮保持 displayed-only 扫描 —— 覆盖句点名的未展示成员由此进并集，prose 正文直接点名的召回成员也不再漏出会话宇宙（堵 S2b 下"提及即排除出覆盖句 ⇒ 永不进并集"的对偶漏洞）。 |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py` | 修改 | +3 新测试 + `_s2c_request`/`_S2C_RECALL_IDS/NAMES` fixture（40 家召回窗，`粤科NN` 品牌别名互不冲突）；6 个既有测试按裁定语义更新断言、1 个重命名（见 §2.2）。 |

显式不做：claim 窗（local 32 / web 32）不动；确定性兜底路径仍不追加成员覆盖句
（无 prose commit）；prompt、reranker、serving 选择逻辑、schema/存储均未动；
`enumeration_coverage` 的 read 侧构建逻辑未动。

## 2. 测试（分层）

### 2.1 本切片新增 3 个测试（RED→GREEN）

RED 证据（实现前实跑）：新增 3 + 更新断言的 6 个共 9 个失败
（endswith/in/handle_ids 断言落空）；2 个负向锁定（全提及不触发、非枚举轮
commit 门禁）RED 阶段天然通过，GREEN 后作为回归锁。

1. `test_member_coverage_sentence_sources_the_recalled_set_beyond_the_claim_window`——
   40 召回 / claim 窗展示前 32 / prose 提及前 8 家 → 未提及 32 家（rank 9-40）
   全部入句，claim 窗外的 rank 33-40 逐家点名，恰好 32 个不触发尾注。
2. `test_member_coverage_sentence_follows_recall_rank_order`——召回序
   （丙、甲、丁、乙）与展示序（甲、乙）刻意不一致，句子逐字节锁定为召回序。
3. `test_member_coverage_sentence_names_all_resolve_to_recalled_handles`——
   无捏造（live P1 的离线镜像）：解析句中名单，每个名字都能解析回
   `evidence_set.entity_handles` 的 display_name，数量 == 32、尾注 == 40 家。

### 2.2 既有测试更新（行为变化属本切片裁定语义，共 8 个）

1. `_S2B_COVERAGE_SENTENCE` 常量 +埃普西龙（截断成员现被点名）；
   `test_enumeration_answer_appends_member_coverage_sentence_deterministically`
   与 `test_member_coverage_sentence_triggered_by_enumeration_coverage_context`
   随常量流转，docstring 改 AQ-S2c 语义。
2. `test_member_coverage_sentence_caps_at_24_with_overflow_count` →
   `..._caps_at_32_...`：fixture 30→40 家，断言第 32 家入句 / 第 33 家不入 /
   `等（共 40 家）`。
3. `test_member_coverage_sentence_skipped_when_all_members_mentioned`——prose
   提及全部 5 家（含埃普西龙）→ 无覆盖句；负向锁定"提及排除"在召回集语义下
   仍成立。
4. `test_non_enumeration_turn_never_appends_member_coverage_sentence`——prose
   点名召回但未展示的埃普西龙，非枚举轮：answer_text 逐字节不变 **且**
   committed == `(alpha,)`（commit 召回扫描门禁钉死）。
5. `test_member_coverage_sentence_feeds_the_narrowing_turn_scope`——t2 改绑
   埃普西龙（claim 窗外成员）：t1 并集 == 4 展示 + epsilon（rank 序末位），
   t2 收窄轮 epsilon claim 存活。
6. `test_member_coverage_sentence_lists_only_displayed_members` →
   `test_member_coverage_sentence_lists_recalled_members_beyond_the_claim_window`：
   语义翻转 —— 截断成员（召回但未展示）现在**必须**入句，这正是裁定目的。
7. `test_member_coverage_sentence_counts_short_brand_mentions`——埃普西龙未被
   短品牌提及，句尾变为 德尔塔+埃普西龙。

未改而通过的同形用例：F2 系列（recall==displayed fixture，S2c 下逐字节不变）、
`test_prose_commit_ignores_names_outside_the_displayed_set`（无 marker 查询，
门禁外）、serving 镜像钉（marker 双拷贝一致）。

### 2.3 回归数字（本 session 实跑）

- 新测试：3 个全绿；更新测试 8 个全绿。
- multiturn 文件：**32 passed + 1 failed**；唯一失败
  `test_off_anchor_correction_exhaustion_falls_back_without_refusal` 为存量失败
  （本切片实现前基线 29+1 同名失败，与 AQ-S1/S2/S2b/S5 记录一致）。
- serving 文件：**293 passed**（含镜像钉；基线 293 一致）。
- 四文件门（read_isolated / serving_isolated / turn_trace_reporting /
  serving_pack_loader）+ placeholder_scrub：**352 passed**（S5 后基线 352，
  逐数对照 ✓）。
- 波及面扫（answer 层行为相关六文件：implementation_closure / answer_anchor_lead /
  grounding_contract / coverage_presentation / enumeration_deep_fetch /
  ambiguity_gate_serving）：**70 passed + 3 failed**；3 个失败全部位于
  implementation_closure（prose-renderer audit 类，同 S2b/S5 基线同名同数），
  存量失败，非本切片引入。
- lint/format：`ruff check` E402 ×4 与 `ruff format --check` 漂移在两文件
  HEAD 版本上同样存在（`git show HEAD:…` / `git stash` 对照），存量，非本切片引入。

## 3. 保真边界

- 非枚举轮逐字节锁定 + commit 门禁（新 ⑤：无 marker 查询点名召回未展示成员
  不进并集；F2 负向用例保持 green）。
- 触发条件双通道互斥或不变（marker 查询 / enumeration_coverage 非空），
  收敛为 `_is_enumeration_turn` 单一定义，覆盖句与 commit 扫描共用。
- 只列**召回集内** canonical 本地公司（read 窗内）；read 窗外的未检索项无句柄
  可名，维持 count-only；cap 32 / 超限 `等（共 N 家）`。
- 顺序 == 召回 rank 序（entity_handles 序），与展示窗顺序解耦（新 ③ 钉住）。
- 提及判定复用 `_prose_mention_name_forms`（全名/去法律后缀词干/去城市词干≥4/
  品牌别名≥2）—— 覆盖句的"未提及集"与 F2 并集的"提及扫描"严格互补，
  无第三套规则。
- 覆盖句无能力声明（"召回以下相关本地企业"），措辞与 S2b 一致。

## 4. 遗留风险与观察项

- **收窄轮自身仍是枚举轮时**覆盖句再点名的 S2b 已知观察项，在 S2c 下从
  32 池放大到 64 池：收窄轮句子更长、会话宇宙保持全池的效应更强（t3 继承
  全池）。这是裁定"并集拾取"机制对偶副作用的放大版，归主上下文 live 观察项
  （g2-t3/g5-t3 stance 采样）。
- commit 扫描池在枚举轮扩到 64 句柄：每轮 O(64 × 词形数) 的子串扫描，成本可
  忽略；但 result_set hash 输入变长属预期（确定性不变，同一 payload 同一 hash）。
- 未做（切片外，需 live 环境，本切片禁网络、不碰 18188）：live g5 探针 +
  g5-t2 实测（裁定要求）、generalization probe 重跑（P2 precision 不得退化）、
  replay 门与 18188 部署 —— 主上下文窗口。
- 回滚 = 还原本提交两个文件；无 schema/存储/契约改动。
- 裁定的备选方案（claim 窗 64，payload +~6K chars）在 live 实测显示描述层才是
  瓶颈时再启用，本切片不预判。

## 5. 产物

- 代码+测试：本切片提交（s11 worktree 分支 `codex/canonical-v2-s12a-ready`）。
- 本文档：`.agents/runs/close-workbook-gaps/aq-s2c-verify.md`。
- 句子样例（40 召回 / 0 提及 / cap 32，实跑截取）：
  「此外，本次检索还召回以下相关本地企业：深圳市粤科01机器人有限公司、…、
  深圳市粤科32机器人有限公司 等（共 40 家）。」
- commit 传播证据（实跑）：t1 句尾点名「…深圳市德尔塔智造有限公司、
  深圳市埃普西龙有限公司。」→ t1 committed ==
  `(alpha, beta, gamma, delta, epsilon)` → t2 收窄轮 `claim:s2b-epsilon-geo`
  存活（`render_mode == "prose_renderer"`）。
