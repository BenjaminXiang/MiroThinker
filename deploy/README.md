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
  `access-logs.sqlite3`（访问日志）、`corrections.sqlite3`（修正覆盖库，见下）。
- 外部依赖只有 embedding（100.64.0.27:18005）和 reranker（18006），fail-closed，
  远端挂了检索即不可用——需要在那台机器上保证这两个服务常驻。
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
- 4 个管理块各有一行 `proxy_set_header X-Remote-User $remote_user;`
  （把 basic auth 用户名透传给后端做操作留痕）；公开块用
  `proxy_set_header X-Remote-User "";` 清掉客户端自带同名头，防伪造

## 数据编辑（覆盖层，2026-08-10 上线）

`/guoxian/browse` 页支持字段级纠错与手工新增记录（不提供删除）。
所有写入进独立修正库 `corrections.sqlite3`（schema
`canonical-v2-corrections-v1`，WAL，0600），**不改动发布产物**；读路径在
API 层做 overlay 合并，无修正库时与上线前逐字节一致。

- 生效时机：浏览页**立即生效**；chat 回答随**下次构建**生效
  （`GET /api/canonical-v2/admin/corrections/export` 导出 active 记录
  JSONL，作为构建输入）
- 留痕：operator 取自 `X-Remote-User` 头（即 basic auth 用户名），
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

## 文件

- `start-canonical-v2.sh` — 启动入口，exec s12g 钉死的完整启动命令
- `canonical-v2-backend.service` — 用户级 systemd unit（Restart=on-failure）
- `backup-canonical-v2.sh` — 备份到 `/md1/backups/canonical-v2/<时间戳>/`，保留 14 份
- `purge-access-logs.sh` — 访问日志 90 天滚动清理
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
- [x] 访问日志保留策略（90 天滚动清理，`purge-access-logs.sh`，每日 03:41 cron）
- [x] 数据编辑覆盖层（2026-08-10：字段纠错 + 手工新增 + 撤销 + 导出，
      operator 经 nginx X-Remote-User 透传，端到端验证通过）
- [ ] `/api/canonical-v2/admin/status` 直连即 500（pre-existing，browse 页顶栏受影响；
      怀疑是 operations 运行环境未配置，需单独排查）
- [ ] 历史文档中残留的 `miroflow:miroflow` 弱口令清理（120 个 .agents 历史文档，
      均为 build 期 disposable PG 的记录；真实轮换在 PG 重新启用时再做）
