# B1 验证记录：G3-simple 企业→专利直扫移植（数据线 → 部署线）

日期：2026-09-10。执行：子代理（B1 slice）。OpenSpec：`close-workbook-gaps`（不动 openspec/，由主上下文更新）。
改动位置：worktree `.worktrees/canonical-v2-s11-consolidation`（分支 `codex/canonical-v2-s12a-ready`），commit `b20161d`。

## 结论（先说结果）

- **移植已完成并提交**：G3-simple 直扫块按源语义落入部署线 `_company_to_patent_relationship_candidates`（排序后、return 前），+79 行。
- **g17-t1 未转绿**（RED→仍 RED：CN 号 0→0，citations_local 0→0）。原因不在移植块本身，而在它上游的两道闸门——在 s12f 服务包上该函数**永远不会被执行**（详见"根因"）。
- **移植过程中发现并修复了源块自身的一个契约缺陷**（策略排除的实体会被直扫重新放回）；该缺陷在数据线同样存在（同源块在 data-rebuild 上跑同一测试同样失败）。
- 回归门 replay：3 次运行 1 次 7/7、2 次 6/7，失败项均为历史记录在案的 LLM 渲染抖动断言（改动代码在本服务包上不可达，无法造成这些失败）；聚焦 pytest 93 passed / 0 failed。

## RED（改前，快照 runner）

命令：`python .agents/runs/close-workbook-gaps/run_testset_snapshot.py --base-url http://127.0.0.1:18188 --only 17 --out .agents/runs/close-workbook-gaps/red-g17.json`
（快照 runner = `cp .agents/runs/testset-baseline-20260909/run_testset.py`，B1 全程使用同一快照。）

- `[g17-t1] FAIL 20.3s canonical_v2:A:answer cit=0(L0/W0)`，fails: `regex:CN\d{9,}[A-Z]? hits=0`。答案为"专利布局方向"式泛泛描述（LLM 综合），无 CN 号、无引用。
- `[g17-t2] PASS 4.5s`（CN117873146A 精确详情，改前即绿）。

## 改动摘要（commit b20161d，唯一改动文件）

`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`：+79 行 / -0 行，插在 `_company_to_patent_relationship_candidates` 的 `candidates.sort(...)` 之后、`return tuple(candidates[: request.max_candidates])` 之前（插入点原 :3801）。

与源块（data-rebuild 同文件 :3801–:3860，commit `790f4d1`）的差异，仅两处适配：

1. `release_id=authority.internal_authority.bundle.release_id` → `release_id=bundle.release_id`（目标函数 :3232 已有局部变量 `bundle`，与其余代码一致）。
2. **新增路径资格护栏**（源块没有）：直扫跳过任一 `verified_relationship_traversal` 决策为 `excluded` 或带 `hard_exclusion_codes` 的端点（企业与专利两侧都查；无资格行则不放行）。排序/去重语义不变（`sorted(public_projections.items())`，`existing_patent_ids` 去重）。

为何必须加护栏：不加时聚焦测试 `test_s8r2_executes_release_scoped_company_to_patent_relationship_traversal` 失败——直扫把被路径资格策略**排除**的 patent-ada/company-robotics 重新放回结果（HEAD 上该测试通过；逐字移植后失败；加护栏后通过）。同一缺陷在数据线可复现（data-rebuild worktree 跑同一测试同样 FAILED）——**源块自身的缺陷，数据线需要同源修复**（本任务不动 data-rebuild）。

静态检查：`import src.data_agents.canonical_v2.knowledge_read_isolated` OK；`ruff check` 全过；`ruff format --diff` 仅剩 3 处 HEAD 即存在的格式漂移（:7161/:7175/:7314，与本次改动无关）。

## GREEN（改后，同一快照 runner，服务已重启加载新代码）

重启：`systemctl --user restart canonical-v2-backend.service`（00:40 与 00:50 各一次，分别对应逐字版与加护栏版）；轮询 `/api/chat/stream` 真实查询确认就绪（~80s）。

命令：`python .agents/runs/close-workbook-gaps/run_testset_snapshot.py --base-url http://127.0.0.1:18188 --only 17 --out .agents/runs/close-workbook-gaps/green-g17.json`

- `[g17-t1] FAIL 13.7s cit=0(L0/W0)`，CN 号 hits=0 —— **未转绿**。
- `[g17-t2] PASS 4.6s` —— 无退化。

## 根因：两道上游闸门使移植块在 s12f 包上不可达

实时 SSE 探针（`curl -X POST :18188/api/chat/stream`）取证：

**闸门 A（规划层绑定失败）**：「优必选有哪些专利」的 `plan_done` 为 `lanes:["exact","structured","lexical","vector","web"], domains:["patent"]`——**没有 relationship 道**。链条：`_ReleaseBoundQueryPlanner.plan` 依赖 `_resolve_named_company_patent_source` 注入 displayed_entity_ids；但 ① `COMPANY_NAME_PATTERN` 要求"公司"后缀（"优必选"没有）；② `_NAMED_COMPANY_PATENT_PATTERN` 要求"的专利"（问句是"有哪些专利"）；③ 逐字别名通道要求别名/规范名整体出现在问句中——s12f 包里优必选的 name=normalized_name=「深圳市优必选科技股份有限公司」，aliases=[优必选科技, UBTECH, 深圳市优必选科技有限公司, …]，**没有裸"优必选"**。绑定失败 → `_relationship_path` 返回空 → 不排 relationship 道。

**闸门 B（读侧分发绕过）**：用可绑定问句「深圳市优必选科技有限公司的专利有哪些」探针——`plan_done` 确实排出 `lanes:["relationship","web"]`，但 `retrieval_done` 显示 relationship 道 **0 候选**。原因：`knowledge_read_isolated.py:5404-5419` 的分发——`has_relationship_scoped_eligibility = any(result.relationship_decision_ids ...)`，而 s12f 包 `relationships.json` 里 `public_path_eligibility_results` 共 **5,659 条，relationship_decision_ids 非空者 0 条** → company_to_patent 永远走 `_source_bound_relationship_candidates`（只扫 `current_relationships` 关系表：692 行，其中 patent_has_applicant 121 行覆盖 48 家企业，**优必选不在其中**）→ 返回空。移植块所在的 `_company_to_patent_relationship_candidates` 在本包上不可达。

**正对照**：「深圳市普渡科技有限公司的专利有哪些」→ relationship 道返回 **17 候选**（与关系表中普渡的 17 行一致）——车道机械正常，缺口确实在数据与分发路径。

注：数据线（790f4d1）同样的分发逻辑；该块在数据线生效是因为其验证用的包（run13+）带逐边资格行。s12f 包没有，设计文档 §B1 的"读路径可达但未扫字段绑定"假设在部署线不成立。

## SQLite 真实性核对（只读探针）

服务包：`/var/tmp/mirothinker-canonical-v2-s12f/serving-pack/lookup.sqlite3`（表 `lookup_document`，JSON 在 `document_json`，域在 `json_extract(document_json,'$.domain')`，投影内容在 `lookup_content` 内层 JSON）。**可复跑探针脚本**：`.agents/runs/close-workbook-gaps/probe_s12f_bindings.py`（`python3` 直跑，只读；本节的全部数字来自其输出）。

- 优必选企业 id：`company-c-64e631c0e0cd9e91d032d209`（name=深圳市优必选科技股份有限公司；aliases 如上，无裸"优必选"）。
- 绑定核对 SQL 语义：`SELECT canonical_object_id, document_json FROM lookup_document WHERE json_extract(document_json,'$.domain')='patent'`，解内层 `applicants` 过滤 `canonical_company_id == 该 id` → **58 条**（与设计 §B1 的 58 一致；含 CN117873146A）。完整清单含 CN116357192A … CN223519677U（记录于本会话输出，必要时可重跑同一脚本）。
- `relationships.json`：`candidate_projection_result.public_domain_projections` 共 5,659 条（patent 1,931 / company 1,737 / professor 1,428 / paper 563），其中绑定优必选 id 的专利 58 条——**若函数可达，直扫即可命中**。另有数据纹理：关系表 121 行的专利中仅 9 条 applicants 带 canonical_company_id——关系表与 id 绑定几乎互补。
- g17-t1 答案不含任何 CN 号（仍 RED），无"答案 CN 号 ↔ 绑定"可核对；附查：普渡探针答案里的 10 个 CN 号（CN222052626U 等）**均不在本地绑定中** → 来自网络/LLM，且 17 个本地关系候选也没产生本地引用（citations=0）——引用楼层属 B4 范围，是 g17-t1 转绿的后续依赖。

## 回归门（replay_fix_round1.py，活端点 18188）

3 次运行（均需 `--out-dir`，产物在 `.agents/runs/close-workbook-gaps/replay-b1*`）：

| 运行 | 代码状态 | 结果 |
|---|---|---|
| replay-b1 | 逐字移植版 | **7/7 ALL PASS** |
| replay-b1-final | 加护栏版（最终提交） | 6/7：G1-T3「subject not in first sentence」、G7#3「required substring missing: 优必选」 |
| replay-b1-final-rerun | 同上 | 6/7：G1-T3（签名还多了"河套深圳园区…"禁用串），G7 全过 |
| replay-b1-final-run3 | 同上 | 6/7：G1-T3 同签名再败 + G3-T2「neither clarification nor person-scoped answer」（新签名），G7 全过 |

判定为**预存抖动而非本次回归**：① 这些断言在历史记录中反复失败于未改动代码——`.agents/runs/testset-baseline-20260909/regression/replay-7session.log`（含 G1-T3 与 G3_person_pronoun FAIL）、`replay-after-s18.log`（G1-T3 + G7×2）、`replay-s18-interp-run1.log`（G1-T3 + G7）均含同签名失败，`replay-s18-fix.log` 则全过；「neither clarification nor person-scoped」签名亦见于 `add-turn-trace-observability/trace-baseline`、`enforce-never-refuse-contracts/replay-v2`、`fix-round-1-serving-pipeline/baseline-2026-08-17` 的历史 report.json；② 三次失败子集互不相同（G7 自愈、G3 新败），是 deepseekv4flash 的 LLM 渲染方差；③ 本次改动位于 s12f 包上不可达的函数（闸门 B 证据），无法在因果上影响 replay 会话。

## 聚焦 pytest

`cd apps/miroflow-agent && uv run pytest tests/canonical_v2 -k "relationship or patent" -q`（worktree 内）：

- 逐字移植版（-x）：**1 failed**（`test_s8r2_executes_release_scoped_company_to_patent_relationship_traversal`，排除端点被直扫重新放回）、18 passed、12 skipped、1233 deselected。
- 加护栏版（最终提交 b20161d）：**93 passed, 26 skipped, 1233 deselected, 0 failed**（138s）。skipped 均为需 `CANONICAL_V2_TEST_*` 显式环境的 Postgres 集成测试（预存条件跳过）。
- 同一测试在 HEAD（改前）通过、在 data-rebuild（数据线，含源块）失败 → 缺陷随源块引入数据线，护栏只在部署线补上。

## 遗留风险 / 未决事项（需主上下文决策，均已超出 B1 已批准设计文本）

1. **g17-t1 转绿需要两个追加改动**（任缺不可）：
   - 闸门 A（规划绑定）：让"优必选"短名绑定企业。选项：数据侧 C1 别名闭包（新包加 alias"优必选"）；或规划侧加"问句 token 是别名前缀"的补充通道（有误绑风险，需设计评审）。
   - 闸门 B（读侧分发）：s12f 类无逐边资格行的包上，company_to_patent 实际执行 `_source_bound_relationship_candidates`——B1 意图的直扫需同样落在该函数（或改分发条件）。两处都属行为变更，需先修订 design.md §B1。
2. **引用楼层依赖**：即使两道闸门修好，普渡探针显示 relationship 道本地候选不产生本地引用（citations=0），g17-t1 的 `citations_local ≥ 1` 断言仍依赖 B4（GAP-07 引用楼层）落地。
3. **数据线同源缺陷**：790f4d1 的 G3 块缺路径资格护栏（data-rebuild 上同测试失败），建议数据线回植本提交的护栏逻辑。
4. **回归门抖动治理**：G1-T3/G7 两条断言在 LLM 综合答案上不稳定（历史即如此），与本次改动无关但会反复干扰门禁判定——建议主上下文考虑隔离/加固（属 B4/B5 面）。
5. 服务当前运行的是 b20161d 代码；回滚方式：`git revert b20161d`（或 checkout 该文件）后 `systemctl --user restart canonical-v2-backend.service`——数据未动。

## 第二轮（2026-09-10）：闸门 A/B + 引用楼层落地；g17-t1 仍 RED，根因定位为第三道闸门（约束层）

执行：子代理（B1 slice 第二轮）。代码位置：worktree 分支 `codex/canonical-v2-s12a-ready`，生产代码由系统自动快照 commit `1860b8c` 收录，本轮补提测试 commit `673edb7`（4 个测试文件，不 push）。服务已重启加载本轮代码（`systemctl --user restart canonical-v2-backend.service`）。

### 结论（先说结果）

- **g17-t1 未转绿**，但第一轮识别的两道闸门均已验证打开：Gate A（裸短名"优必选"绑定 → 规划排 relationship 道）✓、Gate B（直扫落入 `_source_bound_relationship_candidates` 并集，车道返回 48 候选）✓。第一轮的"引用楼层依赖"（遗留事项 2）也已落地并端到端验证 ✓。
- **48→0 的真正丢失点在本轮定位：第三道闸门（约束层）**。`knowledge_read.py:_apply_constraints` 的 `displayed_entity_set` 保护槽把 48 个直扫候选**全部硬拒**——直扫证据项按设计不携带 `LocalSourceRelationshipTrace`（扫描边没有逐边关系权威可绑），而 displayed-witness 只从各类 trace 派生 → 无见证 → 槽拒 → 候选不进证据集 → claims=0 → 答案"未能建立到具体专利条目的关联"、citations=0。最小复现：`.agents/runs/close-workbook-gaps/repro_constraint_gate_scan_items.py`（worktree 内 `uv run python` 直跑，输出 `outcome: rejected / failed slot: displayed_entity_set`）。
- **正对照端到端全绿**：「深圳市普渡科技有限公司有哪些专利」→ relationship 道 17 候选 → 答案 16 个 CN 号 + **16 张 `local-source-*` 本地引用卡**（type=patent, url=null）。

### 本轮改动（均在 1860b8c / 673edb7）

1. `followup_referents.py`：`_compact_company_alias` 移入（Gate A 共享）。
2. `knowledge_read_isolated.py`：`_resolve_named_company_patent_source` 增派生短名通道（Gate A）；`_direct_patent_applicant_scan` 提取为共享辅助并被 `_source_bound_relationship_candidates` 并集调用（Gate B）。
3. `knowledge_serving_isolated.py`：选择器聚焦分支接纳无 trace 直扫项——新增 `_claim_binding_binds_anchor`（**只认绑定值端**，subject 侧会误放回跨锚候选，负向测试锁定）。
4. `canonical_v2_chat.py`：`_public_citations` 对 relationship 道无 URL 本地证据发 `local-source-<sha256(local:{handle_id})[:16]>` 卡（不暴露内部 id）。
5. 测试：Gate A 绑定 3 例 + 选择器 1 例（serving）、Gate B 并集 2 例 + 护栏 2 例（build）、s8r2 authoritative_zero 期望改为 1 个扫描候选（contract）、chat adapter 新增 local-card 测试 + 物理属主 sha 更新。

**偏差上报**：设计 Gate A 第 1 条（扩展 `_NAMED_COMPANY_PATENT_PATTERN` 到"X有哪些专利"句型）**跳过未做**——探测证明派生短名通道已覆盖该句型，且天真扩展所有格模式会让「…的竞争对手有哪些专利」误触发所有权意图、打破既有锁定测试。

### g17（新三层 runner，green-g17-r2.json）

命令：`python3 .agents/runs/testset-baseline-20260909/run_testset.py --base-url http://127.0.0.1:18188 --only 17 --out .agents/runs/close-workbook-gaps/green-g17-r2.json`

- **t1「优必选有哪些专利」**：entity ✓ / provenance ✗（`local_citations:0<1`、`patent_ids:0<3`）。答案为 LLM 综合（answer_style=llm_synthesized），自称"未能建立到具体专利条目的关联"。
- **t2「专利 CN117873146A 的详细信息是什么」**：entity ✓ / completeness ✓（4/5=0.8）/ provenance ✗（`local_citations:0<1`）。t2 引用层红是预存 B4 范围（精确道本地证据无 URL 仍无卡，本轮只覆盖 relationship 道）；实体+完整层保住 = 无退化。

### 逐层证据（绑定 / 扫描 / 约束 / 选择 / 引用）

1. **绑定（Gate A）**：turn-trace `var/turn-trace/2026-09-09.jsonl` 19:46–19:48Z 三轮「优必选有哪些专利」均 `lanes=["relationship","web"]`（第一轮同问句为 exact/structured/lexical/vector/web 五道无 relationship）。
2. **扫描（Gate B）**：同一 trace `relationship: in=48, retained=48`；SSE `retrieval_done` 同数。注意 trace 的 retained 取自 `evidence_set.traces[].candidate_count`（车道层计数），**不代表候选进入证据集**——本轮根因正藏在这个读数下游。包内核对（probe_s12f_bindings.py）：优必选绑定 58 条、关系表提及 0 行 → 48 候选全部来自直扫（58−48=10 条被资格护栏排除）。
3. **约束层（根因）**：见上"结论"。补充：release-bound verifier 用同一 `_apply_constraints` 重算期望收据，观测=期望（全拒配全拒），故 turn 正常完成无完整性错误——缺陷是"静默全拒"而非崩溃。
4. **选择层**：静态确认不阻塞。t1 句型 `_search_view(query)==query` → 非聚焦分支 + "哪些"枚举全量准入；聚焦句型（"深圳市优必选科技有限公司的专利有哪些"）由本轮 `_claim_binding_binds_anchor` 值端见证兜底。
5. **引用层**：普渡 turn 16 张 local-source 卡端到端证明 `_public_citations` 改动生效；优必选 citations=0 是上游 claims=0 的果，非引用层之过。

### SQLite 交叉核对（只读）

- 普渡 = `company-c-c7447b81221857b0e6d3279c`：`applicants[].canonical_company_id` 绑定 **0 条**（直扫对普渡无贡献，17 候选全来自关系表）；关系表 17 行专利的 CN 号与答案 16 个 CN 号**完全重合**（唯一未入答案的是 CN223605703U）→ 普渡答案全本地。答案存档：`.agents/runs/close-workbook-gaps/pudu-answer-r2.json`。
- **修正第一轮的一处机制判断**：第一轮称"普渡答案 CN 号均不在本地绑定 → 来自网络/LLM"，当时核对的是 applicants 绑定表；按关系表专利的 CN 号核对则 16/16 全中——CN 号实际来自 traversal 候选 claim 的 snippet（第一轮 citations=0 仍属实，是引用楼层问题）。第一轮"闸门 B 分发绕过"等主结论不受影响。
- 优必选 g17-t1 答案无 CN 号，无"答案↔绑定"可核对；58 条绑定清单见第一轮。

### 回归门（replay_fix_round1.py --out-dir replay-b1-r2）

6/7 会话通过。3 处失败**全部命中历史抖动签名**，无新签名：G1-T3「subject not in first sentence: 国际先进技术应用推进中心」×1；G7「required substring missing: 优必选」×2（#2/#3）。G3-T2 本轮通过（其抖动未触发）。与本轮改动面最近的 G4_patents（T2「该公司的专利有哪些」）通过。历史同签名记录见第一轮"回归门"节。

### 修复建议（需主上下文决策，超出本轮授权，未实施）

在 `_apply_constraints`（knowledge_read.py，共享核）增一个与选择器 `_claim_binding_binds_anchor` **同语义**的 claim-binding 见证分支：relationship 道、绑定值端为 `canonical:<domain>:<id>`、status=accepted 时，把该端点 id 计入 `displayed_entity_witness_ids`。该见证只被 `displayed_entity_set` 分支消费（geography 槽走独立的 claim-subject 路径，注释明确见证永不满足地理槽），爆炸半径可控；发布侧 verifier 用同一函数重算期望，一致性自保持。属 retrieval-critical 行为变更，需先修订 design.md §B1 并加 OpenSpec 任务。

### 第二轮遗留 / 未决

1. g17-t1 转绿只差上述约束层见证一处改动；改后 t1 句型下选择层与引用层均已就位（聚焦句型亦已由 `_claim_binding_binds_anchor` 覆盖）。
2. t2 的 `local_citations ≥ 1` 依赖 B4 引用楼层扩展到精确道本地证据（本轮只覆盖 relationship 道）。
3. 第一轮遗留事项 3（数据线同源护栏回植）、4（抖动治理）不变。
4. 服务当前运行 1860b8c+673edb7 代码；回滚：`git revert 673edb7 1860b8c` 后重启服务（数据未动）。

## 第三轮（2026-09-10）：Gate C 约束层见证修复 —— g17-t1 三层全绿

执行：子代理（B1 slice 第三轮）。设计依据：`openspec/changes/close-workbook-gaps/design.md` "B1 revision 2 — Gate C" 节（主上下文已批准；锁定语义逐条核对与实际代码无冲突，`FusedCandidate.origin_lane` 字段名相符）。commit `197b7f5`（worktree 分支，未 push）。

### 结论（先说结果）

- **g17-t1 三层全绿**（新三层 runner）：entity ✓ / provenance ✓（`cit=16(L16/W0)`，16 个 CN 号 ≥3，本地引用 ≥1）。GAP-01 的 t1 目标达成。
- g17-t2 仍红在引用层（`local_citations:0<1`）——精确道本地证据无 URL 不发卡，属已知 B4 范围（第二轮已记录），本轮未动。
- 正对照普渡不回退（17 候选 / 16 CN / 16 本地卡）；replay 门 **7/7 全过**（本轮连历史抖动签名都未出现）。

### 改动（commit 197b7f5，+219 行，其中生产 +21）

`knowledge_read.py:_apply_constraints` 新增 claim-binding 见证分支（五个 trace 分支之后、`_constraint_failures` 之前）：仅当 `candidate.origin_lane == "relationship"` 且 trace 分支未产出见证时触发（trace 优先）；见证 = 绑定 **value 端**末端 id（`canonical:<domain>:<id>` 形状），且仅统计 `subject_id == canonical:<candidate.domain>:<candidate.canonical_id>` 的绑定（绑定必须是关于候选自己的）；不查 status（与 `_claim_binding_binds_anchor` 同语义——约束层不得比下游选择器更严）。爆炸半径：见证只被 `displayed_entity_set` 分支消费（geography 走 claim-subject 路径、exact_identifier 走 identity 路径，均不受影响）；`_apply_constraints` 全仓两个调用方（主流 + release-bound validator）共用同一函数，自洽。

### RED → GREEN

- 新增 3 个测试（`test_knowledge_read_atomic_green_contract.py` 尾部，直接打 `_apply_constraints`，沿用该文件 `module._constraint_failures` 私测惯例）：
  1. `test_scan_candidate_claim_value_witnesses_displayed_anchor`（正向：扫描候选经 value 端见证通过 displayed_entity_set）——RED 失败 → GREEN 通过；
  2. `test_scan_candidate_claim_value_witness_rejections`（负向 ×4：跨锚 value / subject 端朝向 / 非 canonical value / 非 relationship 道，全拒）——RED 阶段即过（测的是拒绝方向），锁定不误放；
  3. `test_constraint_witness_matches_selector_claim_binding_anchor`（等价契约：5  fixture 矩阵上读层分支 ≡ 选择器 `_claim_binding_binds_anchor`）——RED 失败（锚在集合内那例两侧不一致）→ GREEN 通过。
- repro 脚本翻转：`.agents/runs/close-workbook-gaps/repro_constraint_gate_scan_items.py` 由"期望拒绝"翻转为 GREEN 护栏（`eligible: 1 / outcome: accepted`），docstring 同步更新。
- 静态：`ruff check` 全过；`ruff format` 我的行全 clean（测试文件仅剩 2151–2205 四块 HEAD 预存漂移，未动）。
- 预存回归：原子约束契约文件 8 passed；聚焦套件 `-k "relationship or patent"` **96 passed / 26 skipped / 0 failed**（138s，skip 均为预存 Postgres 集成条件）——无需改期望：s8r2 断言的 `fused_candidates` 是约束前全集，约束收据两侧同函数重算。

### 端到端证据

- runner：`python3 .agents/runs/testset-baseline-20260909/run_testset.py --base-url http://127.0.0.1:18188 --only 17 --out .agents/runs/close-workbook-gaps/green-g17-r3.json` → `[g17-t1] PASS 11.1s cit=16(L16/W0)`。
- turn-trace 前后对照（同问句、同车道计数）：19:48Z（修前）`relationship in=48/retained=48, citation_count=0` → 20:46Z（修后）`in=48/retained=48, citation_count=16`。48 个候选本轮终于穿过约束层进入证据集（约束前车道计数不变，变化发生在其下游——正是第二轮定位的丢失点）。
- 答案质量：列出 16 个 CN 号并诚实披露"共检索到48件相关专利，此处列出部分示例"（枚举覆盖披露机制正常工作）。
- **SQLite 交叉核对**：答案 16 个 CN 号在 s12f 包 lookup.sqlite3 中 **16/16 全部经 `applicants[].canonical_company_id` 绑定优必选**（含 1 条联合申请 CN117559877A：优纪元+优必选）。无虚构、无网络串号。

### 正对照与回归门

- 普渡（不重跑 runner，直接 SSE）：relationship 17 候选、答案 16 CN、16 张 local-source 卡——与第二轮一致，不回退（存档 `pudu-answer-r3.json`）。
- replay（`--out-dir replay-b1-r3`）：**7/7 ALL PASS**。前两轮的历史抖动签名（G1-T3 subject-not-in-first-sentence、G7 required-substring-优必选、G3-T2 clarification）本轮零出现；无需动用临时抖动政策。

### 第三轮遗留 / 未决

1. g17-t2 的 `local_citations ≥ 1`：精确道本地证据引用卡，属 B4（GAP-07 引用楼层扩展）范围。
2. 第二轮遗留 3（数据线同源护栏回植）、4（replay 抖动治理——本轮虽全过，历史签名仍在册）不变。
3. 服务当前运行 197b7f5；回滚：`git revert 197b7f5` 后 `systemctl --user restart canonical-v2-backend.service`（数据未动；前两轮回滚点见各轮末节）。
