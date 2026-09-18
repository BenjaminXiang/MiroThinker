# 配置页重写执行日志（2026-09-18 · 第 1 轮：A/B/C1/C2；第 2 轮：C3 切线上线 + 回滚演练）

> 计划（冻结决策）：[2026-09-18-admin-config-redesign.md](./2026-09-18-admin-config-redesign.md)
> OpenSpec change：`redesign-admin-config-page`（代理侧门禁）
> 状态：**已上线 18188**（A/B 片 + C1/C2 完成；C3 切线与回滚演练双向完成；线上 PATCH 级验收待有会话时复验）。
> 分支 `feat/admin-config-redesign`（worktree `.worktrees/admin-config-redesign`，基于 `0af01f33`），
> 提交（rebase 到服务线快照 `29d54983` 后）：`b05465dc`（change + 计划）、`6f856a0e`（A 契约）、
> `6e48d8f9`（B 页面）、`194d596b` / `38370f7c` / `72fa365c`（验证与文档）。

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
- 回滚路径（rebase 后实际验证过的）：服务线 `git reset --hard 29d54983`（本片上线前的自动快照）
  + 重启 ≈11 分钟；或 `git revert` 本片提交（`b05465dc`…`72fa365c`）。受管设置/密钥文件与认证库
  不受影响（页面重写不写它们，契约改动是增量列）。

---

# 第 2 轮（C3）：切线上线 18188 + 回滚演练（父会话）

## 1. 做了什么

服务线 `.worktrees/canonical-v2-s11-consolidation`（分支 `codex/canonical-v2-s12a-ready`，
systemd user unit `canonical-v2-backend`，端口 18188，服务包 `serving-pack-run16-sealed`）。
每次重启都要把整个服务包加载完才应答 `/api/health`（10–11.5 分钟）：

| 时间（+08） | 动作 | 服务就绪 |
|---|---|---|
| 16:27:47 | 快进到 `72fa365c` + 重启（**切线上线**） | 16:39:10 |
| 16:40:45 | **回滚**：`git reset --hard 29d54983` + 重启 | 16:52:08 |
| 16:53:09 | **正向恢复**：`git merge --ff-only 72fa365c` + 重启 | ≈17:03 |

## 2. 发现了什么

1. **回滚与恢复都是"一条命令 + 一次重启"**，中间不用动受管设置/密钥/认证库；回滚态下旧页（1093 行）
   在新契约上照常服务——契约改动是增量列，旧页不会被打断。
2. **两个态是可判别的**（下表），所以"上线成功"和"回滚成功"不是口头结论，而是可复跑的检查。
3. **服务的字节 = 树的字节**：`sha256(/static/admin.html)` 与活线树里的同名文件一致（`6a5bc8b3…`），
   活线树在两端都干净（`git status --porcelain` 为空）。
4. 最终 tip（rebase 后）`72fa365c` 上重跑定向子集：**85 passed in 2.48s**。

| 探针（只走公开面） | 回滚态（`29d54983`） | 恢复态（`72fa365c`） |
|---|---|---|
| `GET /static/admin.html` | 200，**1093 行** | 200，**142 行** |
| 旧页标记（`FIELD_SPECS\|statusTiles\|providerTable`） | **8** | **0** |
| 卡片容器（4 × `id="card-*"`；另有横幅与只读快照） | **0** | **4 + 2** |
| 壳内 js/css 引用 / 资源可取 | 0 引用 | 2 引用，均 **200** |
| `GET /admin`（登录门） | 302 | 302 |
| `GET /api/canonical-v2/admin/config`（无会话） | 401 | 401 |

## 3. 怎么验证

每次等到 `/api/health` 返回 200 再取标记（`curl` + `wc -l` / `grep -c`），回滚与恢复各跑一次。
证据：`.agents/runs/redesign-admin-config-page/verification.md` §6。

**诚实缺口**：A1/A2/A3/A5 是 PATCH 级线上验收，需要已登录的 `/admin` 会话。管理员口令已由操作者
自行轮换（admin-auth 库 `password_change ok`，epoch 1→2），首启口令文件失效，父会话没有可用会话
（两次未认证登录被拒，审计里是 `login fail`）。这几条以 scratch-18296 证据为准，标记为
**线上待复验**——同提交、同包、同目录，差别只在"用哪个会话点页面"。

## 4. 影响哪些问题

- 计划 §4 的验收线：①–⑥ 在第 1 轮 scratch 演示，⑦ 回滚演练本轮在 18188 上完成；切片状态从
  **候选** 推进到 **已上线**（线上 PATCH 级复验待会话）。
- 运维语义提醒（沿用第 1 轮第 5 节）：`config/managed/settings.json` 现在只含操作者写过的键；
  重启后刚保存的字段会显示为"env 覆盖"而变灰（既有优先级语义，不是 bug）。接手运维的人要知道这两条。
