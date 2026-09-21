# Canonical V2 上线运维（本机单机全套）

部署形态：本机（gpu01，tailnet 100.64.0.4）单机，服务进程 + 嵌入式
Milvus Lite + 本地 serving-pack。对外经 **dbg21（100.64.0.34）的 nginx**
转发并做认证，公网入口 `https://star.sustech.edu.cn/guoxian`。

## 架构事实（上线前必读）

- **PG 不在服务路径上**。启动参数里的 `postgresql://...@127.0.0.1:55458`
  是 build 期的 disposable 目标，当前并未运行，也不需要运行。chat session
  存储对 PG 是 fail-open（`storage/chat_session.py::_mark_postgres_unavailable`），
  PG 挂了自动降级。
- 服务期数据全部自包含在 `/var/tmp/mirothinker-canonical-v2-s12f/`：
  `serving-pack/`（结构化数据 + milvus.db）、`index-v1/`（向量索引）、
  `access-logs.sqlite3`（访问日志）、`corrections.sqlite3`（修正覆盖库，见下）、
  `manual-recall-v1/`（人工知识侧车，见下）。
- 外部依赖：embedding（100.64.0.27:18005）与 reranker（18006），fail-closed，
  远端挂了检索即不可用——需要在那台机器上保证这两个服务常驻。
- **聊天 LLM 也是外部依赖**（2026-09-09 起）：`CHAT_LLM_PROFILE=deepseekv4flash`
  （`api.deepseek.com`，密钥 `.deepseek_api_key`）。原 `gemma4` 档走学校网关
  `star.sustech.edu.cn`，2026-09-09 实测整站 502，答案静默退化为模板；切换后恢复
  `answer_style=llm_synthesized`。档位选择依据测试集实测：flash 22/25 > pro 21/25，
  且 pro 在「优必选有哪些专利」触发 `LLM prose response contains a private marker`
  导致**空答案**。LLM 不可用时服务不报错、答案退化为模板，属静默降级。
- 已知迁移阻塞项：Milvus Lite 2.5.1 close 死锁（见 FIXLOG 2026-08-07 条目），
  只影响重新构建的收尾，不影响运行中的服务。

## 对外访问（2026-08-09 已生效，两区分级）

- 公网入口：`https://star.sustech.edu.cn/guoxian`（校网关 → dbg21:3001 → gpu01:18188）
- **公开区（无需登录）**：`/guoxian/chat` 对话页、`/api/chat*`、`/static/*`
  - chat 页示例问题为静态写死（`STATIC_DEMO_QUESTIONS`），不依赖需登录的数据浏览 API
- **管理区（auth_basic）**：`/guoxian/logs`（访问日志）、`/guoxian/browse`（数据浏览）、
  `/guoxian/api/canonical-v2/admin/*`、`/guoxian/api/canonical-v2/operations/*`
  - 凭据文件 `/etc/nginx/htpasswd_canonical_v2`，用户名/密码存于 gpu01
    `~/canonical-v2-basic-auth.txt`（0600）
- dbg21 配置：`/etc/nginx/conf.d/sustech-ai.conf` 的 5 个 `/guoxian` location 块，
  公共代理配置抽在 `/etc/nginx/snippets/canonical-v2-proxy.conf`
  （`rewrite ^/guoxian(/.*)$ $1 break;` + 裸 `proxy_pass`——不要改回
  `proxy_pass .../;` 形式，长前缀 location 会把路径剥错）
- 改 dbg21 配置前按该目录惯例先 `cp` 带时间戳的 .bak
- 4 个管理块各有一行 `proxy_set_header X-Remote-User $remote_user;`、
  公开块用 `proxy_set_header X-Remote-User "";` 清掉客户端自带同名头
  ——**2026-09-17 起后端不再用该头做身份**（留痕取登录用户名，见下节），
  这两行现在只留作历史兼容，删掉也不影响行为

## 管理台登录与账号播种（add-admin-auth-and-console，2026-09-17）

管理面自带应用级登录后，**后端自己就是那一层门**：dbg21 的 nginx basic auth
退化为可选的第二层（甲方单机部署没有 nginx 时，唯一门就是它）。

- 入口：`/main`（未登录=登录表单，登录后=同 URL 的仪表盘：状态卡 / 快捷入口 /
  账号区 / 右上角当前用户 + 退出登录）。六个管理页（`/admin` `/logs` `/browse`
  `/jobs` `/upload` `/seeds`）与全部 `/api/canonical-v2/*` 管理 API 需要会话：
  页面未登录 302 → `/main`，API 401 `{"detail":"authentication_required"}`。
- 公开面不变：`/chat`、`/api/chat*`、`/static/*`、`/api/health`、`/api/auth/login`。
- 首启播种：账号库为空时创建 `admin` 账号 + 随机 16 位口令，口令打印一次到
  `journalctl`（`[admin-auth] first-boot administrator ...`）并写入 0600 文件
  `<状态目录>/admin-initial-password.txt`。幂等：库非空时不再打印/不再改写文件。
  自动化部署可用 `CANONICAL_V2_ADMIN_INITIAL_PASSWORD` 固定首启口令。
- 会话：HMAC-SHA256 签名 Cookie `cv2_admin_session`（HttpOnly / SameSite=Lax；
  请求经 HTTPS 时才带 Secure），载荷含用户名、签发时间、到期时间、口令代次；
  空闲 1 小时滑动、绝对 12 小时；**改密/重置口令/删号立即让该账号所有旧 Cookie 失效**。
  密钥 `<状态目录>/admin-auth.key`（0600，首用生成，重启后旧会话仍有效）。
- 账号与审计：`<状态目录>/admin-auth.sqlite3`（schema `canonical-v2-admin-auth-v1`，
  scrypt 加盐哈希，明文永不落库；`audit` 表记录登录/登出/账号操作）。
  写操作（POST/PATCH/PUT/DELETE）要求同源（`Origin` / `Sec-Fetch-Site` 校验，无 CSRF token）；
  登录 5 次失败锁该「用户名+来源 IP」1 分钟，继续失败翻倍（上限 30 分钟）。
- 环境变量：`CANONICAL_V2_ADMIN_AUTH_DB`（默认 `<access-logs.sqlite3 同目录>/admin-auth.sqlite3`）、
  `CANONICAL_V2_ADMIN_AUTH_KEY`、`CANONICAL_V2_ADMIN_INITIAL_PASSWORD`。
- 首次登录后请改密并删除 `admin-initial-password.txt`（页面会提示到文件消失）。
- **HTTPS 建议**：应用不内置 TLS。公网/跨网段部署请在前面加一层 HTTPS 终止
  （nginx/caddy），并透传 `Host` 与 `X-Forwarded-Proto`（后端据此决定 Cookie 的
  Secure 与同源判定）；纯内网单机可先用 HTTP，但登录口令与会话 Cookie 都是明文传输。
- 备份：`backup-canonical-v2.sh` 已覆盖状态目录整目录（含账号库/密钥/审计）；
  回滚只切回启动命令文件 + 重启，账号库与审计**不删**，再上线时继续复用同一批账号。


## 数据编辑（覆盖层，2026-08-10 上线）

`/guoxian/browse` 页支持字段级纠错与手工新增记录（不提供删除）。
所有写入进独立修正库 `corrections.sqlite3`（schema
`canonical-v2-corrections-v1`，WAL，0600），**不改动发布产物**；读路径在
API 层做 overlay 合并，无修正库时与上线前逐字节一致。

- 生效时机：浏览页**立即生效**；chat 回答随**下次构建**生效
  （`GET /api/canonical-v2/admin/corrections/export` 导出 active 记录
  JSONL，作为构建输入）
- 留痕：operator 取登录用户名（2026-09-17 前取 `X-Remote-User` 头），
  修改原因必填；纠错保存原值，可撤销（软撤销，历史保留）
- 字段白名单：仅顶层标量字段可改；溯源/结构字段（field_lineage、
  evidence、*_id 等）返回 422
- 启动命令（s12g/serve-18188-command.sh）以
  `CANONICAL_V2_CORRECTIONS_DB=/var/tmp/mirothinker-canonical-v2-s12f/corrections.sqlite3`
  启用；缺该 env 或打开失败时浏览只读、写 API 503，不影响 chat
- API 面：`POST .../domains/{domain}/{id}/corrections`、
  `POST .../domains/{domain}/records`、`POST .../corrections/{id}/revert`、
  `POST .../records/{id}/revert`、`GET .../corrections[?status=]`、
  `GET .../corrections/export`（仅 active）
- 备份：`backup-canonical-v2.sh` 已把 corrections.sqlite3 纳入在线一致性备份

## 人工知识在线召回（2026-08-10 上线）

手工新增记录与企业文档上传**即时进入 chat 向量召回**，不等下次构建。

- 存储：可写侧车 `manual-recall-v1/manual-recall.json`（schema
  `canonical-v2-manual-recall-v1`，0600，原子重写），与发布产物完全隔离；
  写入时用 serving 同款 embedding（4096 维）预先 embed，查询期零新增外部调用
- 召回机制：侧车点在向量道排序截断**之前**并入候选；trace 以
  `target_id=manual-recall-v1` 标记，证据 `source_authority=manual_upload`，
  发布绑定校验按标记豁免（lane 契约识别的唯一非发布来源）
- 文档上传（`/guoxian/browse` 企业域"上传文档"，两步）：
  预览解析（pdf/docx/txt/md，扩展名 + magic 嗅探，≤10MiB，抽取截断
  24000 字符）→ 全文可编辑确认 → 分块（≤800 字符/块，≤200 块）embed 入库；
  API：`POST .../admin/company-documents/preview`（multipart）、
  `POST .../admin/company-documents`（json）、`GET .../company-documents`、
  `POST .../company-documents/{doc_id}/revert`
- 编辑挂钩：手工新增记录成功后同步 embed 进侧车（embed 失败则补偿撤销
  该记录并 502）；撤销记录时 tombstone 对应召回点
- 启动命令（s12g/serve-18188-command.sh）以
  `CANONICAL_V2_MANUAL_RECALL_DIR=/var/tmp/mirothinker-canonical-v2-s12f/manual-recall-v1`
  启用；缺该 env 或加载失败时 fail-open（无人工并集、上传 API 503），
  chat 行为与上线前一致；启动日志有 `manual_recall_store=` 行
- dbg21 管理块已加 `client_max_body_size 20M;`（默认 1M 会拦文档上传）
- 备份：随 `/var/tmp/mirothinker-canonical-v2-s12f/` 整目录 tar 覆盖，
  纯文件无需专门处理

## 文件

- `start-canonical-v2.sh` — 启动入口，exec s12g 钉死的完整启动命令
- `canonical-v2-backend.service` — 用户级 systemd unit（Restart=on-failure）
- `backup-canonical-v2.sh` — 备份到 `/md1/backups/canonical-v2/<时间戳>/`，保留 14 份
- `purge-access-logs.sh` — 访问日志滚动清理；保留期顺序为「位置参数 > `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS`
  > 受管配置 `paths.access_log_retention_days`（页面 /admin 同源可改）> 默认 90 天」，日志行会打印生效值与来源
- `firewall-18188.sh` + `canonical-v2-firewall.service` — 18188 收口（见下）
- `install.sh` — 安装 unit + 每日 03:17 备份 / 03:41 清理 cron（无需 sudo）

## 安装 / 切换

```bash
bash deploy/install.sh
# 停掉当前手工后台进程后：
systemctl --user start canonical-v2-backend
journalctl --user -u canonical-v2-backend -f
```

## 防火墙（本机，2026-08-09 已生效）

18188 硬编码绑 0.0.0.0（s12a runner 钉死），用 iptables 收口：
放行 `127.0.0.0/8` 与 `100.64.0.34`（dbg21），其余来源 DROP。

- 规则由 `canonical-v2-firewall.service`（系统级 oneshot，随开机执行
  `deploy/firewall-18188.sh`）持久化，幂等可重放
- 手工查看：`sudo iptables -L INPUT -n --line-numbers | head -5`
- 注意：规则插在 tailscale `ts-input` 之前，dbg21 经 tailnet 访问不受影响；
  其他 tailnet 设备（含同事笔记本）直连 18188 会被拒——这是有意为之

## 恢复

```bash
# 停服务后，把某份备份拷回（sqlite 库是一致性快照，可直接用）
systemctl --user stop canonical-v2-backend
rsync -a --delete /md1/backups/canonical-v2/<时间戳>/ /var/tmp/mirothinker-canonical-v2-s12f/
systemctl --user start canonical-v2-backend
```

## 待办

- [x] 防火墙收口 18188（2026-08-09，iptables + systemd 持久化，三路连通验证）
- [x] nginx 转发 + 认证（2026-08-09，dbg21 /guoxian 块，公网链路 401/200/302 验证）
- [x] 切换 systemd 守护并观察一次自动拉起（2026-08-07 验证：kill 后 50s 恢复）
- [x] 首次备份实跑 + 恢复演练一次（2026-08-07/09：946MB 快照，库 integrity ok，
      恢复副本行数与现网一致，manifest/npz 可解析）
- [x] 访问日志保留策略（默认 90 天滚动清理，`purge-access-logs.sh`，每日 03:41 cron；
      保留期改由受管配置 `paths.access_log_retention_days` 控制，2026-09-14 W5）
- [x] 数据编辑覆盖层（2026-08-10：字段纠错 + 手工新增 + 撤销 + 导出；
      operator 自 2026-09-17 起改取登录用户名）
- [x] 人工知识在线召回（2026-08-10：侧车向量并集 + 文档上传两步 UI +
      编辑挂钩 + nginx 20M body，直连/公网双路端到端验证）
- [ ] `/api/canonical-v2/admin/status` 直连即 500（pre-existing，browse 页顶栏受影响；
      怀疑是 operations 运行环境未配置，需单独排查）
- [ ] 历史文档中残留的 `miroflow:miroflow` 弱口令清理（120 个 .agents 历史文档，
      均为 build 期 disposable PG 的记录；真实轮换在 PG 重新启用时再做）

## 现场交付（2026-09-21 新增）

把本机这套服务搬到甲方服务器时用到的三个交付件。**方案与排期**见
`docs/plans/2026-09-21-customer-site-delivery-plan.md`（含路径冻结、验收、回退），
本节只讲怎么用；演练证据见 `.agents/runs/delivery-kit-rehearsal/`。

```bash
# 1) 我方机器：打交付包（默认输出 /var/tmp/mirothinker-delivery-kit/）
bash deploy/build-delivery-kit.sh --source-tree <代码树>
#    产物：code.tar(+sha256) / bundles/ / checksums.sha256 / sizes.tsv /
#          site-paths.txt / kit-manifest.txt
#    重跑很快：文件没变就不重打包，数据面按 路径+大小+时间 命中缓存，不重复读 7 GB

# 2) 目标机：先自检（只读，不启动服务，不改任何文件）
bash deploy/preflight.sh --repo <目标机代码根> --kit-dir <kit 目录>
#    可选：--fast（只比对大小，不跑 sha256）、--port N、
#          --no-network、--embedding-url/--rerank-url/--llm-url 覆盖探针地址
#    退出码 0=READY；有 [FAIL] 则非零，逐行给证据

# 3) 目标机：起服务后跑既有入口
bash deploy/install.sh && systemctl --user start canonical-v2-backend
```

- `kit/site-paths.txt` 是**目标机路径清单**：每行给出种类
  （`dir`/`file`/`parentdir`/`string`）、对应的命令行参数或环境变量、我方取值
  （对照用）、检查命令与用途。带 `[现场改写]` 的必须换成目标机自己的路径。
- `preflight.sh` 的取值来自**目标机自己的命令文件**（不读清单里的参考路径），
  因此命令文件先改好再跑；它会做三处冻结字符串的交叉核对（索引根、索引 marker
  sha256、发布 bundle 的 envelope_path/database_name）——这三处不一致启动会
  fail-closed。
- 探针口径：嵌入端点断言 **HTTP 200 + 维度 4096**；重排只判可达（该道 fail-open）；
  LLM 档位与地址从 `config/managed/settings.json` 的 `serving.chat_llm_profile`
  出发、按 `llm_profiles.py` 解析（密钥按同名规则找 `.deepseek_api_key`
  / `.sglang_api_key`，只打印路径不打印内容）。
- 本机现存实例（18188）与 `deploy/*.sh` 的既有脚本不受影响：`preflight.sh`
  只读；端口占用会作为 `[FAIL]` 报出来（同时在跑的实例不会被碰）。

## 外部反代接入要求（nginx / Caddy，2026-09-21 实测）

把 18188 挂到外部域名（例如 `star.sustech.edu.cn`）时，反代侧必须满足下面四条；
否则典型症状是"页面能开、但登录或流式回答失败"：

1. **透传原始 Host 与 `X-Forwarded-Proto` / `X-Forwarded-Host`**
   后端用它们决定 Cookie 的 `Secure` 标记与**写操作的同源判定**（`Origin` / `Sec-Fetch-Site` 校验，无 CSRF token）：
   - Caddy：`reverse_proxy` 默认自动带 `X-Forwarded-For/Host/Proto`，写 `reverse_proxy 100.64.0.4:18188` 即可；
   - nginx：必须显式写 `proxy_set_header Host $host;`、`proxy_set_header X-Forwarded-Proto $scheme;`、
     `proxy_set_header X-Forwarded-Host $host;`；
   - **不要**把 Host 改成上游地址（`proxy_set_header Host 100.64.0.4:18188;`）——登录会被同源校验拒绝。
2. **SSE 不缓冲**：`/api/chat/stream` 是 `text/event-stream`。nginx 必须 `proxy_buffering off;`
   （Caddy 默认即时 flush，无需额外配置）。
3. **超时给足**：一轮问答可达 30–60 s；nginx 显式设 `proxy_read_timeout 300s; proxy_send_timeout 300s;`
   （默认 60 s 可能掐断长回答）。
4. **路径前缀可用**：前端 API 调用是相对路径（`fetch("api/chat/stream")`），根路径与子路径都能工作；
   子路径（如 `/guoxian/`）用 `proxy_pass http://127.0.0.1:18188/;`（尾斜杠剥前缀）。

**网络前提**：18188 由 `firewall-18188.sh` 收口，只放行 `127.0.0.0/8`、`100.64.0.0/10`（tailnet 整段）
与 `100.64.0.34`（dbg21），其余一律 DROP。反代所在机器要么在 tailnet 内，要么把它的源 IP
加进该脚本的 `SPECS` 后再 `apply`。

**安全建议**：对外只暴露 `/chat` 与 `/api/chat*`；管理面（`/main` `/admin` `/logs` `/seeds` `/upload`
`/jobs` `/browse`）即使有应用级登录，也建议在反代上加第二层（IP 白名单或 basic auth）——dbg21 当年就是这么做的。

**已实测（2026-09-21）**：带 `Host: star.sustech.edu.cn` + `X-Forwarded-Proto: https` +
`X-Forwarded-Host: star.sustech.edu.cn` 请求本机 `GET /chat` → **200**，`GET /` → **302 → /chat**。
即**应用侧无需任何改动**，只差"反代指向 + 网络放行"两件事。
