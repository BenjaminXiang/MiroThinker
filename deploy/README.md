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
  `access-logs.sqlite3`（访问日志）。
- 外部依赖只有 embedding（100.64.0.27:18005）和 reranker（18006），fail-closed，
  远端挂了检索即不可用——需要在那台机器上保证这两个服务常驻。
- 已知迁移阻塞项：Milvus Lite 2.5.1 close 死锁（见 FIXLOG 2026-08-07 条目），
  只影响重新构建的收尾，不影响运行中的服务。

## 对外访问（2026-08-09 已生效）

- 公网入口：`https://star.sustech.edu.cn/guoxian`（校网关 → dbg21:3001 → gpu01:18188）
- 认证：dbg21 nginx `auth_basic`，凭据文件 `/etc/nginx/htpasswd_canonical_v2`，
  用户名/密码存于 gpu01 `~/canonical-v2-basic-auth.txt`（0600）
- 页面：`/guoxian/chat`（对话）、`/guoxian/browse`（数据浏览）、`/guoxian/logs`（访问日志）
- 前端三个页面全部使用**相对路径**引用 API/静态资源/导航，因此同一套代码
  在 18188 根路径和 /guoxian 前缀下都可用
- dbg21 配置：`/etc/nginx/conf.d/sustech-ai.conf` 的 `location ^~ /guoxian/` 块
  （根映射 `proxy_pass http://100.64.0.4:18188/;` + `proxy_redirect / /guoxian/;`
  + `absolute_redirect off;`，改配置前按该目录惯例先 `cp` 带时间戳的 .bak）

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
- [ ] `/api/canonical-v2/admin/status` 直连即 500（pre-existing，browse 页顶栏受影响；
      怀疑是 operations 运行环境未配置，需单独排查）
- [ ] 历史文档中残留的 `miroflow:miroflow` 弱口令清理（120 个 .agents 历史文档，
      均为 build 期 disposable PG 的记录；真实轮换在 PG 重新启用时再做）
