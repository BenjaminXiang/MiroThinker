# 用户会话审计增强（W5）执行日志

> 只追加（append-only）。每轮一条：**做了什么 → 发现 → 怎么验证 → 影响哪些问题**。
> 上游规划 [`2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`](./2026-09-07-system-wrapup-config-center-and-periodic-refresh.md)
> §1.4 现状盘点 / §4 D5 定案 / §6 W5 验收线 / §9.1 双线日历 D3–D4；
> change-id `add-session-audit-enrichment`；证据目录 `.agents/runs/admin-audit-logs-w5/`；
> 分支 `feat/admin-audit-logs`（worktree `.worktrees/admin-audit-logs`，基线 = W1 分支尖 `852a85b7`）。

---

## 2026-09-14 · 第 1 轮：审计维度、过滤、导出、统计、保留期落地（W5）

### 做了什么

1. **独立 worktree**：`.worktrees/admin-audit-logs`（分支 `feat/admin-audit-logs`，从 W1 的
   `feat/admin-config-center` 拉出）。全程未重启 18188、未碰 live 资产、未碰 `data-rebuild` /
   `canonical-v2-s11-consolidation` / `admin-config-center` 三个 worktree；访问日志只以**只读副本**方式参与验证。
2. **记录侧补身份**：`turns.user_identity`（取 nginx 管理区透传的 `X-Remote-User`；无该头或空值记字面量
   `anonymous`，归一化时去空白、截断 120 字符）。**不记 IP、不记 cookie、不 getUser-Agent**；记录仍在
   chat 流式端点的唯一记录口 `_record_access_turn` 内完成、仍 fail-open。
3. **老库无损增量迁移**：打开旧库（`canonical-v2-access-log-v1`）时用 `PRAGMA table_info` 探测缺列并
   `ALTER TABLE ADD COLUMN`，旧行保持 `NULL`、读侧用 `COALESCE(NULLIF(...),'anonymous')` 统一显示「匿名」。
   **schema marker 故意不升位**：回滚到 W5 之前的代码仍能打开迁移后的库（记录列保留无害），这是规划里写的回滚路径。
4. **查询侧组合过滤**：`GET …/access-logs/sessions` 新增 `since` / `until` / `query_type` / `identity`，与既有
   `q` / `status` 按 AND 组合（会话级语义：某条约束由该会话的任一回合满足即可）。
5. **导出**：`GET …/access-logs/export?format=csv|jsonl`，与页面用同一套过滤参数，字段集与页面逐轮所见完全一致
   （身份/会话/轮次/类型/状态/起止时间/耗时/回答风格/问题/回答/错误详情/引用/建议追问），带
   `X-Access-Log-Sessions|Turns|Truncated` 三个响应头与 `max_turns` 上限。
6. **统计**：`GET …/access-logs/stats`：总量（会话/轮次/错误/中断/错误率）、每日会话与轮次（UTC）、
   `query_type` 分布、身份分布、Top 提问；默认窗口近 30 天并在响应里标明，列表排序确定性化
   （次数降序 + 键升序）。
7. **保留期进配置中心**：`deploy/purge-access-logs.sh` 改为按规定顺序解析保留期
   **位置参数 > `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS` > 受管配置 `paths.access_log_retention_days` > 90 天**，
   与 W1 的 `env > file > default` 优先级镜像；打印生效值与来源；配置读不通/类型不对/超范围时**回落到 90 天并告警**
   （绝不因配置问题少删或多删）。脚本保持纯标准库（cron 不 import 应用栈）。`/logs` 页展示生效值与来源。
8. **页面** `backend/static/logs.html` 原地扩展（**不另起新页面**，仍与 `/browse`、`/chat` 同体系静态页、无 `innerHTML`）：
   检索 + 状态 + 提问类型 + 身份 + 起止日期筛选、CSV/JSONL 导出按钮、概览面板（统计卡 + 每日/类型/Top 提问三张表）、
   保留期读数、会话与回合的身份标签（匿名显示「匿名」）。
9. **测试**：3 个新测试文件共 28 个用例（迁移 4 / 过滤-导出-统计 17 / 清理脚本 7）；全量套件 before/after 各一次；
   scratch 端口 **18289**（非 18188）+ scratch 库（live 库只读副本）+ scratch 受管配置的真实 HTTP 冒烟 21 次调用、
   六条断言全 PASS。

### 发现

1. **§1.4 对 `query_type` 的描述与实际不符（重要）**：规划写「query_type（A–G）存了但不可筛」，但库里的值**不是单字母**，
   而是复合串 `canonical_v2:<行为类>:<回答形态>`。只读核对两个 live 库（2026-09-14）：
   `canonical-v2:A:answer` 1471 / `canonical_v2:G:clarification_only` 86 / `canonical_v2:F:safety_guidance` 6 /
   空串 36（s12f 库，1599 轮）。因此**没有**做「A–G 单选」的硬编码下拉，而是：接口接受**精确值**（空串也是一个合法桶，
   对应"该轮没记类型"，即报错/中断轮），页面的类型下拉**由统计返回的观测值动态填充**，要按字母看仍然可用
   （`query_type=canonical_v2:A:answer`）。这一条同时解释了为什么"字母"维度此前感觉缺失。
2. **两个 live 库都是 v1 且没有身份列**，行为空是既成事实，直接决定迁移策略必须"加列 + 读侧归一"，不能回填。
3. **live 语料存在日期空洞**：s12f 库的回合集中在 08-07…08-19 与 09-07…09-13 两段，中间（08-20…09-06）无数据。
   第一次组合过滤探针正好落在这个空洞里（HTTP 与 SQL 都是 0），改到 08-10…08-13 窗口后拿到 40 个会话的真实对照——
   如实记录，避免把"探针选错窗口"误读成"过滤不对"。
4. **导出格式的字段命名统一为 `citations` / `suggested_followups`**（CSV 里是多值字段的 JSON 文本，JSONL 里是原生数组），
   两种格式列名一致，避免"同名不同义"。
5. **既有 fail-open 有一处缝**：`_record_access_turn` 在进入 store 的 try/except **之前**就算 `latency_ms`，
   若 `started_at` 是 naive 时间会抛 `TypeError`。生产路径 `started_at` 恒来自 `_utc_now()`（带时区），不可达；
   按"不做范围外重构"只在验证报告里记录，未改（详见 verification.md 未验证项第 4 条）。
6. **W1 的受管配置 schema 已含 `paths.access_log_retention_days`（默认 90、env 覆盖）**，本片只补**读取端**
   （清理脚本 + 页面展示），未新增配置源、未改 schema——符合"保留期进配置中心"的既定分工。

### 怎么验证（分层，细节见 `.agents/runs/admin-audit-logs-w5/verification.md`）

1. **新测试（本片）**：`uv run pytest -q` 跑 3 个新文件 → **28 passed**；同 3 个文件在**改前代码**上（stash 六个生产文件后）
   为 10 failed + 1 collection error（`red-run-before-change.txt`），RED→GREEN 闭环。
2. **既有套件（本分支自测，非引用 W1 数据）**：全量 `apps/admin-console` → before
   **96 failed / 1024 passed / 29 skipped / 122 errors**，after **96 failed / 1052 passed / 29 skipped / 122 errors**；
   passed +28 = 新测试数；失败集合 `comm` 差异**新增 0 / 修复 0**；其中 access-log / purge 相关失败 **0**。
   218 条既有红是环境/数据依赖的基线红，与 W5 无关，未顺手修（范围外）。
3. **scratch 18289 真实 HTTP（六条断言全 PASS）**：① 带 `X-Remote-User` 写入 → 列表/详情可见该身份（无头写为匿名）；
   ② 组合过滤 HTTP 40 == SQL 40、空类型桶 34 == 34；③ CSV/JSONL 各 1071 行、抽样 11 轮逐字段与
   `/sessions/{id}` 比对 0 差异；④ 统计 6 项聚合与 `turns` 表 SQL 全等（1071 轮 / 644 会话 / 18 错误 / 3 中断 /
   error_rate 0.0168）；⑤ 保留期读出受管配置 45 天（`source=file`），无配置时 90 天（`source=default`），
   20 天窗口实删 461 轮 / 276 会话；⑥ 列名/响应体/行数据中 IP 形态串 **0 命中**。
   同一份 live 库副本的迁移对照：marker 仍为 `canonical-v2-access-log-v1`、列原位追加 `user_identity`、
   1530→1532 轮（+2 为冒烟写入）。冒烟结束后 scratch 服务已停，18188 仍 `GET /api/health → 200`。
4. **反向证据**：非法参数（naive 时间、`since>until`、超长身份、未知导出格式）均 4xx，不静默降级。

### 影响哪些问题

- **收尾规划 §6 W5 验收线四条全部达成**：新老库无损升级（旧行显示匿名）、组合过滤正确、导出与页面所见一致（抽样比对 0 差异）、
  统计与 `turns` 表 SQL 对账一致；另加保留期可配（默认 90 天不变）与 fail-open 不回归。
- **对 §9.1 双线日历 D3–D4（W5 = B 线）**：本片完成 W5；日历上的 W6/W7 未开始（同一 B 线后续切片）。
- **对 W1 的联动**：「保留期进配置中心」这条**不再欠账**——W1 提供 config schema 与页面可写项，W5 提供读取端与展示；
  两边读的是同一个文件、同一套优先级。
- **对 D5 隐私最小化**：记录侧只留身份（或无身份标记），不引入 IP 等网络标识；审计页与导出仍在管理区
  （`/api/canonical-v2/admin/*` + `/logs` 同属 auth_basic 区），未新增暴露面。
- **未影响**：chat/检索/回答/服务包行为零改动；18188 未重启、未部署，线上仍跑 W5 之前的代码；
  `release/customer-test` 未做热更新（本片不涉及门禁）。

### 未做 / 需拍板

- **未部署**：W5 未上 18188，也未进 nginx 管理区；验收依据是 scratch 端口的真实 HTTP + live 库只读副本。
- **chat 端点未端到端**：裸 V2 壳没装 serving-pack runtime，`POST /api/chat` 无法起一轮；身份写入是通过**真实的**
  `_record_access_turn` 记录口在真实 HTTP 上完成的（chat 端点调用同一函数）。
- **待拍板（老库迁移回滚路径）**：本片选择"schema marker 不升位 + 结构探测加列"，回滚到 W5 之前的代码仍能读写该库
  （身份列被忽略）。代价是 marker 不再单独表达"含身份列"。若要求 marker 严格表达结构版本，需改为升位到 v2，
  则回滚会因版本不符而拒绝打开（日志记录 fail-open 会静默停摆）——**这一点需要产品/运维确认选哪条**。
- **待拍板（对外 API 形状）**：`/sessions` 响应新增 `identities`、回合新增 `user_identity`（**纯增量字段**），
  `/sessions/{id}` 行为不变，`/stats`、`/export` 为新增端点；`access-logs` 系列目前只有 `/logs` 一个消费方，
  属管理区内部接口、无外部契约承诺。若认为需要对外承诺稳定性，建议在 W8 runbook 里把它登记为内部接口。
