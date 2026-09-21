# 容器交付线 · 第 4 组未验证项闭环（2026-09-22，工作区 delivery/docker @ 8ef6e822）

来源：`docs/plans/2026-09-21-customer-site-migration-log.md` 第 12 轮末尾的
「未验证」四项。本目录是这四项的**执行与证据**，人类文档由父 agent 写。

## 要关掉的 4 个命题

1. `--force-recreate` 的**反向实验**（现结论是从 bind-mount inode 语义推断的，没有观测）。
2. `/admin`「手填 key」表单**在浏览器里真提交一次**（上次只验到运行时凭据解析 + 连接测试）。
3. **真 root（sudo）下的安装**（上次是无 sudo，uid 1004）。
4. **跨文件系统传送后的完整链路**（/var/tmp 在 /，/home 在 sda1）。

## 演练链（一条链跑完 4 项）

```
交付包 /var/tmp/mirothinker-site-bundle-v11（3.4 GB，原样）
   │  ① 跨 fs 拷贝（/ → /home，真字节拷贝） + 校验（两个大 tar + 逐文件清单）
   ▼
/home/longxiang/delivery-xfer-v11/site-bundle      ← 传输后的副本
   │  ② 按 CONFIG-GUIDE §2 的原文命令放 4 个 key（sudo install -m 600）→ sudo ./install-site.sh
   ▼
宿主机站点：SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922，端口 18298
   │  ③ 在该实例上做 --force-recreate 反向实验（换错 key → restart → recreate → 复原）
   │  ④ 在同一实例上做浏览器表单提交（/main 登录 → /admin 填 key → 保存 → 测试）
   ▼
证据：本目录 01..04 + raw/
```

## 边界（未触碰）

- 活线 18188（pid 519941）、8 小时构建（pid 2077915，/var/tmp/mirothinker-data-v2/{staging-v4,index-v4}）、
  18297 别的 agent 的 scratch（pid 1335614）—— 全程不碰。
- 端口只用 18298；site root 新目录，不复用 `mirothinker-delivery-rehearsal*`。
- 不 prune、不 rmi、不删他人容器/卷；不 push。
- 密钥内容不回显（只打印路径、mode、sha256 前缀）。

## 环境事实（本次实测）

- `df`: / = /dev/nvme0n1p2（881 GB 可用）；/home = /dev/sda1（1.3 TB 可用）⇒ 跨 fs 为真。
- `sudo -n true` 通过（longxiang uid 1004，免密）。
- 交付包 tar 记录 uid:gid = 1004:1004（`tar -tvzf --numeric-owner`）。
- 4 个真实 key：`/home/longxiang/MiroThinker/.{deepseek,bocha,serper,sglang}_api_key`；
  嵌入 key 实测 `http://100.64.0.27:18005/v1/embeddings` → 200 + 4096 维。
