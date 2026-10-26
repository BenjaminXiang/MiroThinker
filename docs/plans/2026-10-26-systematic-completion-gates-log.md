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
