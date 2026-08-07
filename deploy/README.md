# Canonical V2 上线运维（本机单机全套）

部署形态：本机单机，服务进程 + 嵌入式 Milvus Lite + 本地 serving-pack，
对外经**另一台机器的 nginx** 转发并做认证。暂不需要域名/HTTPS。

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
- 18188 硬编码绑 0.0.0.0（s12a runner 钉死），**必须靠防火墙收口**（见下）。
- 已知迁移阻塞项：Milvus Lite 2.5.1 close 死锁（见 FIXLOG 2026-08-07 条目），
  只影响重新构建的收尾，不影响运行中的服务。

## 文件

- `start-canonical-v2.sh` — 启动入口，exec s12g 钉死的完整启动命令
- `canonical-v2-backend.service` — 用户级 systemd unit（Restart=on-failure）
- `backup-canonical-v2.sh` — 备份到 `/md1/backups/canonical-v2/<时间戳>/`，保留 14 份
- `install.sh` — 安装 unit + 每日 03:17 备份 cron（无需 sudo）

## 安装 / 切换

```bash
bash deploy/install.sh
# 停掉当前手工后台进程后：
systemctl --user start canonical-v2-backend
journalctl --user -u canonical-v2-backend -f
```

## 防火墙（本机，需要 sudo + nginx 机器 IP）

18188 只放行 nginx 转发机器，其余来源一律拒绝：

```bash
sudo ufw allow from <NGINX_HOST_IP> to any port 18188 proto tcp
sudo ufw deny 18188
# 注意：不要 ufw enable 全局默认策略前没确认 22(ssh) 等已放行
```

## nginx 转发配置（在另一台机器上）

```nginx
server {
    listen 80;
    location / {
        auth_basic "canonical-v2";
        auth_basic_user_file /etc/nginx/.htpasswd;   # htpasswd -c 生成
        proxy_pass http://<本机IP>:18188;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;        # 流式回答必须
        proxy_read_timeout 300s;
    }
}
```

`/logs` 管理页含全部用户问答内容，认证通过后建议再加一层来源 IP 白名单
（nginx `allow/deny` 或单独的 location 规则）。

## 恢复

```bash
# 停服务后，把某份备份拷回（sqlite 库是一致性快照，可直接用）
systemctl --user stop canonical-v2-backend
rsync -a --delete /md1/backups/canonical-v2/<时间戳>/ /var/tmp/mirothinker-canonical-v2-s12f/
systemctl --user start canonical-v2-backend
```

## 待办（上线前必须闭环）

- [ ] 拿到 nginx 机器 IP，执行上面的防火墙规则
- [ ] 切换 systemd 守护并观察一次自动拉起
- [ ] 首次备份实跑 + 恢复演练一次
- [ ] 访问日志保留策略定稿（当前无限期，建议 90 天滚动清理）
- [ ] 历史文档中残留的 `miroflow:miroflow` 弱口令清理（120 个 .agents 历史文档，
      均为 build 期 disposable PG 的记录；真实轮换在 PG 重新启用时再做）
