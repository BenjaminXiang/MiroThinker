# 配置页重写执行日志（2026-09-18 · 第 1 轮：A/B/C1/C2）

> 计划（冻结决策）：[2026-09-18-admin-config-redesign.md](./2026-09-18-admin-config-redesign.md)
> OpenSpec change：`redesign-admin-config-page`（代理侧门禁）
> 状态：**候选**（切线上线 + 回滚演练 C3 待父会话执行）。
> 分支 `feat/admin-config-redesign`（worktree `.worktrees/admin-config-redesign`，基于 `0af01f33`），
> 两个提交：`765ac453`（A 契约）、`2acb5f7a`（B 页面）。

## 1. 做了什么

**A · 服务端契约**（`managed_config.py`）

- 新增 `FIELD_CATALOG`（23 行，覆盖全部白名单路径）：label / kind / group / order /
  min / max / step / consumer / connection / test_arg，默认值直接从 `ManagedSettings()`
  派生（目录不可能与 schema 漂移）；双向 fail-closed 覆盖测试（缺行、孤儿行都报名字）。
- `EffectiveField.as_dict()` 携带上述列 → `/config` 的 `fields` 直接可渲染；页面不再持有任何
  字段清单/类型表。**请求/响应形状只增字段**。
- 保存语义按三态收敛：**显式 `null` = 清除 override**（bool / 文本 / 非空 int / 嵌套域开关都成立）；
  **文件只保留操作者写过的键**（diff 保存）；**无变化 = 不写文件、不写审计**。

**B · 页面**（`admin.html` 壳 + `admin.js` + `admin.css`）

- 四张卡：采集与构建（collection.\* + 各域新鲜度 + 采集历史）、检索与回答（serving.\* + 来源徽章 +
  rerank 运行期徽章 + \[测试 Rerank 连通性\]）、存储与保留（paths.\* + 三个库计数/体积 + 磁盘 +
  保留期预览）、连接与密钥（5 张连接卡：运行期徽章/来源/掩码/只写密钥/端点模型/测试/保存本卡）。
- 页首生效横幅：`N 项未保存` / `已保存的改动需重启生效` + 可复制的重启命令；
  每卡「保存本卡」只发本卡脏字段（bool 三态：默认·启用·停用；数值/文本留空 = 默认）。
- 删除：客户端 `FIELD_SPECS`、整表 `collectPatch`、Provider key 表、全局「立即检查」按钮、
  表单里的端点重复入口、卡内原始 JSON（移入只读快照）。

## 2. 发现了什么（超出设计文档的三点）

1. **「保存=整表倾倒」的根因在服务端，不在页面**：`ManagedSettingsStore.patch()` 一直把**默认值填满的
   整份文档**写盘（不是只写改动的键）。所以「只提交脏字段」若不做服务端改动，验收线②（文件里只有那一个键）
   无法成立。本轮把写盘改成**只持久化操作者写过的键**，审计记录仍保留解析后的 before/after 全量文档；
   `changed` 改为「操作者键的差集」（否则把一个非空 int 清回默认时，生效值没变，会被误判为 no-op）。
1. **端点字段的「归属」必须由目录给出**：要让页面在连接卡里渲染 `extraction_endpoints.*`、并把未保存值
   喂给 `connections/test`，页面需要知道「哪一行属于哪个连接、哪个参数是 base_url / 哪个是 model」。
   若靠字段名后缀约定，等于把第二份 schema 又搬回客户端。于是目录多了两列：`connection`、`test_arg`。
   （设计 §1 的表是「at least」清单。）
1. **「保存 → 重启生效」的真实链路**：启动时 `apply_managed_runtime_config` 把文件里「与默认不同」的值
   注入进程 env，所以重启后页面上该字段会显示为 **env 覆盖**（不可编辑）——这正是「已生效」的证据，
   本轮在 scratch 上取证（`CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS`）。

## 3. 怎么验证（分层）

- **新增测试 30 条**（`test_managed_config_catalogue.py` 11、`test_managed_settings_store.py` +8、
  `test_admin_config_single_channel.py` 4、`test_admin_config_page_shell.py` 7），全部 tmp 文件 +
  真实路由图，不碰线上状态目录；另更新 2 个旧页面标记测试（B8）。
- **定向套件 116 passed**（catalogue / store / 单通道 / 页面壳 / config API / secrets API / 控制台壳 /
  门禁 / runtime bootstrap）。
- **全量 before/after 差异**：`25 failed, 1316 passed` → `25 failed, 1346 passed`，
  失败集合**逐行一致**（130 行 before = 130 行 after，`comm` 双向为空）；多出的 30 个通过正是新测试。
- **scratch 冒烟（端口 18296，scratch settings/secrets）**：A1–A6 逐条演示，含
  ① 临时加一行目录 → 页面零改动即出现（做完已撤，`git status` 干净）；
  ② 保存只写脏键 / 清默认回退；③ bool 三态；④ 端点只在连接卡；⑤ 测试（未保存值，真实发起一次最小调用）
  →保存→横幅「需重启生效」+ 可复制命令；⑥ 卡片 1/3 自带展示、无独立状态块。
  跑完停服，18188 全程未动（仅 `ss` 观察）。转录：
  `.agents/runs/redesign-admin-config-page/{verification.md,scratch-smoke-transcript.txt}`。

## 4. 影响哪些问题（对照计划 §1 的四个毛病）

| 毛病 | 状态 |
|---|---|
| 一个字段两条通道（端点既在表单又在连接表） | 已消除：端点只在连接卡，单通道有 grep 级测试 |
| schema 三份拷贝（模型 → EffectiveField → 客户端 FIELD_SPECS） | 已消除：目录是唯一真相，页面纯函数渲染，覆盖双向 fail-closed |
| 保存=整表倾倒、bool 回不到默认 | 已消除：只写脏字段、`null` 清 override、无变化 no-op |
| 一页四个关切且与 /main 重复 | 已消除：四卡各自带状态/编辑/验证，Provider 表与全局检查按钮下线（`providers/health-check` API 保留） |

## 5. 未做项与风险

- **C3 未做**（属父会话）：18188 切线上线 + 验收线 A7 回滚演练。上线前建议在线上再走一遍
  A1–A6（同一份检查在 scratch 上已跑通）。
- 卡片 1 未接 `/jobs`（运行/闸门状态仍在任务运维页）；design §3 提到的 "gate/run state" 按计划/
  任务书的卡 1 清单执行，未扩 `/system-status`。
- `patch()` 写盘语义变化影响所有写入方（页面 PATCH、CLI 消费者、运维脚本）：文件从「全量文档」变成
  「覆盖项集合」，解析视图（`raw()`/`effective()`）不变；回滚是单提交回退（无 schema/格式变化）。
- 回滚命令：`git revert 2acb5f7a 765ac453` 或把服务线快进回 `0af01f33` 后重启；受管设置/密钥文件与
  认证库不受影响（页面重写不写它们，契约改动是增量列）。
