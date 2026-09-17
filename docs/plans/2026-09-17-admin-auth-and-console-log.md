# 后台管理台 + 登录 · 执行日志（2026-09-17）

> 计划（冻结）：[后台管理台 + 登录（2026-09-17）](./2026-09-17-admin-auth-and-console.md)
> OpenSpec change：`add-admin-auth-and-console`（英文，代理侧门禁）。
> 本文件只追加：每轮"做了什么 → 发现了什么 → 怎么验证 → 影响哪些问题"。

## 轮次 1（2026-09-17 下午）：实现 + scratch 冒烟（子代理在隔离工作树）

**做了什么**：按冻结设计实现全片——`admin_auth.py`（SQLite 账号库：scrypt 加盐、密码代次、审计表、幂等播种）、
`admin_session.py`（HMAC 签名 Cookie：载荷=用户名/签发/过期/代次，绝对 12h + 空闲 1h，改密/删号即失效）、
登录限流（用户名+IP，5 次锁 60s、指数退避）、8 个端点（login/logout/me/password/accounts+reset）、
门禁中间件（6 个管理页 302→`/main`、`/api/canonical-v2/*` 401、写操作同源校验、身份只认会话）、
`/main` 壳（登录表单/仪表盘：状态卡+快捷入口+账号区+用户/退出）、六页导航接入、
`/review` 评审台管理面侧整体退役（含 18189 引用）。提交：`d5876da5`、`c943f88e`、`25554934`。

**发现了什么**：① 评审台实际有 4 个测试文件（设计只写了 2 个），多出的两个（launcher/UI）读被删资产，一并删除；
② `conftest` 共享 `client` 需带登录态（新增 `authorized_client`），11 个既有测试文件随之适配——
两处把"头即身份"的旧断言改成"会话身份"，`test_patch_anonymous_operator_is_recorded` 改为"无会话即拒绝（401，不写）"；
③ 我（父会话）复核发现公开 chat 路径仍用 `X-Remote-User` 记日志身份（可伪造），按共识改为恒记 anonymous
（修复 `301e85dc`）。

**怎么验证**：R1–R7 共 **84 个新测试** RED→GREEN（先见 `ModuleNotFoundError`/评审台资产仍在的失败）；
全量 admin-console 套件 failures-before **98 failed / 1263 passed / 122 errors** → after **25 failed / 1316 passed / 105 errors**，
`comm -13` 为空（**零新增失败**；减少的 90 条=被删评审台测试）；scratch 端口 18295 冒烟 20 步全过（跑完停服）。

**影响哪些问题**：切片 1.1–4.2/5.1/6.1/6.2 完成；6.3 切线与 5.2/5.3 文档留父会话。

## 轮次 2（2026-09-17 晚）：切 18188 + A1–A7 验收 + 回滚演练（父会话）

**做了什么**：活线 ff `8fc0fa7f → 301e85dc` + 一次重启（本切片不改 serve 命令文件）；
首启播种成功（`admin-auth.sqlite3`/`admin-auth.key`/`admin-initial-password.txt` 全部 0600）；
逐条跑 A1–A7；回滚演练 = `reset --hard 8fc0fa7f` + 重启（回滚态）→ `merge --ff-only` 回 + 重启（正向态）。

**发现了什么**：① 播种与重启用时：首启 **11m10s**，回滚态/正向态各约 **12 分钟**；
② `patch` 对"无变化"的配置提交直接早退（不写文件、不审计）——A5 探针首测因此 422/无审计，改用真实变更后通过；
③ 回滚后账号库/密钥/口令文件原样保留，正向重启**不重复播种**（`initial password` 日志 0 次，原口令仍可登录）；
④ 门禁对公开面零影响（`/chat` 正常、replay 门 7/7）。

**怎么验证（全部实测数字）**：
- A1：6 页 `302 → /main`；管理 API `401`（带伪头同样 401）；`/main` `/chat` `/static/*` `/api/health` `200`；`/review`、`/api/review/*` `404`。
- A2：登录 `200`；`me` 返回 `{"username":"admin","role":"admin"}`；`/main` 带 `data-admin-user="admin"`；5 次错+第 6 次 `429 retry_after=60`；62s 后正确登录 `200`。
- A3/A4：登出（浏览器往返）后 `me` `401`；重置口令→旧会话 `401`、旧口令拒绝、新口令 `200`；删号→会话 `401`、登录拒绝；删末账号 `409`。
- A5：两次携 `X-Remote-User: boss` 的配置 PATCH → `audit.jsonl` 的 `operator` 均为 `admin`，`boss` 全库不出现。
- A6：公开探针「字节跳动」→ ByteDance Ltd.（TTFT 3.03s/总 13.34s）；**replay 门 7/7 ALL PASS**；boot 日志 `milvus` 计数 **0**。
- A7：回滚态 `/logs` `/admin` 管理 API `200`、`/main` `/api/auth/login` `404`（无门禁旧态）；账号库/密钥/口令文件未动；回滚正向复验通过。
- 审计表：`login ok 6 / fail 7 / locked 2`、`account_create 2`、`account_delete ok 2（+1 失败=末账号守卫）`、`password_reset 1`、`logout 2`；账号仅剩 `admin`。

**影响哪些问题**：管理面从"裸露"变为应用内认证（甲方单机自包含）；`X-Remote-User` 全面作废（公开面记 anonymous）；
`/review` 从管理面消失（构建侧 human-review 校验家族仍待独立切片）；遗留候选见计划 §3 与账本备注。
