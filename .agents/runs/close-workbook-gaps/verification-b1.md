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
