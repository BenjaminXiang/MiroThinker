# 四道闸门 · 执行日志

> 只追加。每片记录：做了什么 → 发现了什么 → 怎么验证 → 影响哪些问题。

## 第 1 轮 · 2026-10-26 22:00 CST · 闸门 1 侦察与立项

### 做了什么

1. 建立 `version-customer-runtime` 变更（proposal / specs delta / tasks /
   acceptance / verification-contract）。
2. 对客户机做全量侦察：`find ... -newermt '2026-10-21'` + `sha256sum`，
   与本地各分支逐文件比对。

### 发现了什么

- **回灌范围是 31 个 py 文件，不是最初以为的 5 个。** 其中 9 个与
  `switch/embedding-model-to-qwen37-flash` 一致；18 个不同；4 个在该分支不存在
  （`excel_structure.py`、`excel_ingest.py`、`run_scheduled_job.py`、
  `news_connectors/deepseek.py`，只存在于 10-23 的 `codex/canonical-v2-s12a-ready`
  快照）。部署树是三条血统的并集。
- **`:18188` 是「进程冻结」，不是「另一个应用」。（第 2 轮更正）** 它的命令行
  指向 `.worktrees/embedding-switch-line/.../s12e/serve_s12e_port.py`，与客户机
  走同一条启动链（`serve_s12e_port` → `complete_candidate_runner` →
  `import backend.main`）。真实原因是该进程 **10-16 启动后从未重启**，Python 把
  当时的模块 import 冻结在内存里，环境也停在当时（无答案缓存开关）。所以实测中
  同一问法在客户机返回 `structured_payload.local_patent_count=450` + 本地引用，
  在 18188 返回 `exact/structured/lexical/vector` 全 0 候选的散文合成，SSE 协议
  也不同（`answer` vs `answer_chunk`）—— 这是 10 天前的代码，不是另一个产品。
  结论不变：此前「已部署 18188」的说法对 10-16 之后的工作不成立。
- 客户机 `run.sh` 里 `CANONICAL_V2_TURN_DEBUG_DIR="$B/var/turn-debug"` **是开着的**；
  本地 18188 的 debug 目录指向仓库内，已积累 1,683 个文件 / 26 MB。

### 怎么验证

- 两侧 `sha256sum` 全量比对（31 行清单）。
- `curl :18188/api/chat/stream` 与 `https://gxzx-coze-api.idea.edu.cn/api/chat/stream`
  同问对比；`/proc/<pid>/cmdline`、`PYTHONPATH`、`environ` 取证。
- 只读查询 dev pack `lookup.sqlite3`：47,068 文档、优必选 451 条，排除「数据不在包里」
  这一解释。

### 影响哪些问题

- 「客户现场已验收」的结论仍然成立（行为在客户机上确实存在），但**不可复现**；
  闸门 1 是后续一切验收的前提。
- dev 线的性质在**第 2 轮**定稿：同一条启动链、同一个 app，但进程自 10-16 冻结；
  「影子自 10-16」成立，「不是产品应用」不成立。

## 第 2 轮 · 2026-10-26 22:15 CST · 闸门 1 落地（1.1–1.5）

### 做了什么

1. **快照分支** `hotfix/customer-20261026`（worktree `.worktrees/customer-20261026`）：
   客户机 `apps/` 逐字节复制 + `run.sh` + `sha256` 清单；提交 `82047a7b`
   （41 文件，+2315/−528）。剔除 49 个补丁残留（44 个 `.bak-*`、5 个 `.pre-*`），
   名单留在 `prod-snapshot/excluded-patch-residue.txt`。
2. **漂移检查** `apps/admin-console/scripts/check_runtime_drift.py`（+7 单测）：
   按文件哈希比对部署树与 git ref，默认范围 `apps/admin-console` +
   `apps/miroflow-agent`，默认排除 `tests/`，把 `.env`/`*.db` 作为运行时文件报告而非判失败。
   对客户机实跑：**0 changed / 0 only-deployed，697 文件，exit 0**。
3. **4 条采纳行为测试**（48 + 4 通过）+ 三条 RED 证明（见下）。
4. **debug 面归档（部分完成）**：turn-debug 共 1,683 文件 / 26 MB 归档到
   `/tmp/turn-debug-archive/`（4.3 MB tgz）。其中 75 个未跟踪的 lane-watch 文件
   已删除；**1,608 个已被 auto-snapshot 入库的历史文件保留**——删掉它们只会形成
   一个 1,683 文件的噪声提交，收益为零。真正「止写」要等 1.6 重启去掉
   `CANONICAL_V2_TURN_DEBUG_DIR`，该开关在客户机 `run.sh` 里同样开着，已记录。
5. **快照树冒烟**：`import backend.main` → FastAPI 应用 72 条路由，证明快照不只是字节相同。

### 发现了什么

- **更正第 1 轮判断**：`:18188` 与客户机是同一条启动链，只是进程 10-16 起未重启、
  import 冻结。已同步改 §1 正文与本日志第 1 轮条目。
- 客户机 `apps/miroflow-agent/.env` 在源码树内（运行时残留；漂移检查报告但不判失败）。
- 部署包不带 8 个测试文件（`test_standalone_anchor.py`、`test_canonical_v2_answer_cache.py`、
  `test_alias_foothold.py` 等），故测试默认不参与漂移判定。
- **全量 admin-console 套件：1607 passed / 31 failed / 105 errors**。105 个 error 全部是
  conftest 的「拒绝在真实库上跑」守卫（需 `DATABASE_URL_TEST`）；31 个 failure 分布在
  14 个模块，抽检三例（`test_main_milvus_env`、`test_chat_context_helpers`、
  `test_star_coupling_defaults`）都是**部署代码与分支测试的契约不一致**（star 端点仍为默认、
  alias SQL 形态不同、milvus env 未设置）——正是本变更要暴露的分歧，不是本轮引入。
  三个抽检文件与 `backend/main.py` 在快照提交后未被改动。

### 怎么验证（RED 证据）

- **主题教授守卫**：把它改成恒假后跑 `test_standalone_anchor.py` →
  `FAILED test_topic_professor_query_does_not_anchor_a_company`，报错值正是
  `('company-c-lingqiao', '浙江灵巧智能科技有限公司')`，与线上症状一致；随后恢复（`git diff` 干净）。
- **缓存门**：用采纳前的测试文件跑采纳后的代码 → 4 条失败（`local_only` 键已不存在、
  长度/标记改读 HTTP 信封），说明语义确实变了，新测试锁的是新契约。
- **通用人名屏蔽**：运行时把 `_ENTITY_LINK_GENERIC_PERSON_NAMES` 清空 →
  `_entity_name_forms("professor", {"教授"})` 由 `[]` 变 `['教授']`。

### 影响哪些问题

- 闸门 1 的 1.1–1.5 完成：**最新行为第一次进入版本控制**，并有 5 个模块的测试与漂移门守着。
  （1.5 只做到「归档 + 删未跟踪」，止写仍挂在 1.6。）
- 仍未完成：1.6 dev 重启到版本化树。阻塞是配置一致性——客户机的 managed secrets 在
  `code/config/managed/secrets.json`（本地只有 example），manual-recall 数据在客户机
  `var/manual-recall-v1`（本地 `/var/tmp/.../manual-recall-v1` 只有 28 KB）。
  需要一次明确的「把哪些现场配置复制到 dev」决定，再排 6–10 分钟的重载窗口。

## 第 3 轮 · 2026-10-26 23:15 CST · 闸门 2 落地（评测门）

### 做了什么

1. **把评测从「一次性脚本」变成「有基线的门」**：`eval_full_testset.py` 增加
   `--baseline` / `--fail-on-regression` / `--tolerance`，逐题 diff、硬计数检查、退出码。
2. **双分制**：
   - `required_recall`（逐字命中）＝**回归轴**，只要求不降；
   - `product_pass`（有答案 + ≥1 引用 + 该拒答时拒答 + 无禁词）＝**可用轴**。
3. **波动容忍**：单题掉 1 记 `fluctuation`；单题掉 ≥2、总掉超过容差（默认 3）、
   禁用/拒答/错误计数上升、题目消失 → 才算 `regression`。
4. **基线入库**：`apps/admin-console/scripts/eval-baselines/baseline-full.json`
   （客户机 2026-10-26，full 模式 27 轮）。
5. **入口**：`just eval-gate`（默认指向客户机，输出落 `/tmp`，失败退出 1）。
6. **14 条单测**覆盖打分、分组、可用轴、容差与回归语义（不联网）。

### 发现了什么

- **基线：required 77/120（64%）、product_pass 26/27、0 forbidden、0 refusal miss、
  0 error、平均 14.51s、最大 84.01s（q15）**。比日志里上一轮的 81/120 低 4 个，
  主要是 q2（0/5）、q15（4/6，84s）、q19/q21 表述波动——不是新退化，是同一套数据
  在另一天的取值。
- **product 轴唯一失败是 q2**：多轮「他是否有参与哪些企业的创立」退化成澄清、0 引用
  ——多轮指代仍然丢主体，这条恰好把「exact 分数掩盖的多轮问题」暴露出来。
- **两轴确实会打架**：q27（灵巧手教授）exact 仍 0/4，但 product_pass=true（有答案、
  有引用）。这正是当初「产品口径 vs 标准集口径」争论的实证。
- **时延不可直接做门**：第二次跑平均 5.41s、基线 14.51s，差别主要是答案缓存冷热，
  不是性能变化。故时延只报告、不判定。
- **门的自检通过**：对同一客户机再跑一次 → 76/120（q25 4→3），判定 `pass` +
  1 条 fluctuation，退出码 0。这正是设计意图——单点表述波动不该把门刷红。

### 怎么验证

- 基线跑：`eval_full_testset.py --base https://gxzx-coze-api.idea.edu.cn --mode full`
  → 27 轮全执行、0 error。
- 自检跑：带上 `--baseline ... --fail-on-regression` → `baseline verdict: pass`，
  `fluctuations: qid 25 4->3`，`totals: required 77->76`，退出码 0。
- 单测：`pytest tests/test_eval_gate.py` → 14 passed。

### 影响哪些问题

- 从此「这一版比上一版好还是坏」有一条可复现的命令与一份可对账的基线；
  闸门 3（数据竖切）的验收不再靠人肉对比日志。
- 未做：时延门、逐题人工判定、CI 接入、`head` 模式基线（目前只有 full）。

## 第 4 轮 · 2026-10-26 23:40 CST · 闸门 3 开工：先审计，不先动手

### 做了什么

1. 新建分支 `feat/professor-paper-slice`，写离线审计脚本
   `apps/miroflow-agent/scripts/audit_professor_paper_projection.py`（只读 pack，
   加载 `lookup.sqlite3` + `relationships.json`）。
2. 在本地 pack（`serving-pack-fembed-v3-synthdepth`，与客户机同源）上跑出量化结论。
3. 顺带量了教授字段质量（人名/邮箱/主页/模板 summary），因为投影前必须知道哪些记录可信。

### 发现了什么

- **边是有的**：10,742 条 `professor_attributed_to_paper`，覆盖 1,019 位教授（25.7%）、
  10,390 篇论文（42.4%），人均 10.5 篇。
- **但投影是 0**：`paper.professor_ids` 全空；1,019 位有边教授里 875 位（86%）
  `paper_count` 为空；271 位没有研究方向。
- **字段质量比预想差**：5 条垃圾人名；134 条（5.0%）邮箱被页面标签污染
  （`emailjun.zhu@cuhk.edu.cnofficeaddressphoneteachingareaotherbiography…`）；
  模板 summary 2,129 条（53.8%）。
- **边不能盲投**：边数第一的「面包屑」（217 篇）其实是一位真实教授（港中大深圳，
  医疗机器人），名字取自页面面包屑导航；「朱军」（210 篇）在港中大深圳确有此人
  （物理有机化学），但同名合并风险无法从 pack 内证伪。
- **外部身份源今天不可用**：OpenAlex 返回 429「免费额度耗尽，UTC 零点重置」，
  所以「补 ORCID/OpenAlex ID」这条线今天不能开工，先把能做的做掉。

### 怎么验证

- 审计脚本实跑：58.8s 加载 10,742 条边；输出
  `.agents/runs/professor-paper-slice/projection-audit.json`。
- 字段质量用 SQLite 聚合 + 严格邮箱规则（TLD 2–6、域名标签 ≤24、长度 ≤64）复核。

### 评估与决定

**评估**：闸门 1（可复现）与闸门 2（可度量）已可用；闸门 3 的瓶颈**不是「没有边」，
而是「边可信度 + 文档投影」**。直接投影会把「面包屑」这种记录和可能的同名合并
一起灌进答案，属于用错误数据换指标。

**决定**：闸门 3 的顺序改为 **3.1 字段质量门 + 投影构建器 → 3.2 物化并过评测门 →
3.3 身份扩充**。3.1 仍是离线、零风险，产出 `professor_projection.json` 与覆盖率报告；
3.2 才动服务线，并且先 overlay、不触发 20 小时全量重建。

### 影响哪些问题

- 把「论文反哺画像」从一句 PRD 变成可执行的三步，且第一步不依赖网络与重建。
- 明确了「同名合并」是比「没有链接」更危险的问题，后续任何链接扩充都要带证据门。
