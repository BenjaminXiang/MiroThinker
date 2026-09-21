# 验证汇总（本次演练：命令 → 结果）

时间：2026-09-22 00:50–02:20（+08）。工作区 `delivery/docker`，本次提交 `d756981a`（+本文件的提交）。

## ① 本次新写的验证脚本/探针（7 个）

| 文件 | 锁的是什么 |
|---|---|
| `01-verify-transfer.sh` | 跨 fs 拷贝后两个大归档 + 17 个文件逐一致；顺带复现 `.sha256` 绝对路径缺陷（3b/3c 段） |
| `02-sudo-install-attempt1.sh` | 按文档原样放 key + sudo 安装：拿到 D1（缺 secrets/）与 D4（/tmp 固定文件） |
| `02b-sudo-install-attempt2.sh` | v1.1 原版安装器（只换 /tmp 路径名）：拿到 D3（root 属主 ⇒ 容器 exit 78 ⇒ install exit 13） |
| `02c/02d-sudo-install-attempt3(b).sh` | 修好的安装器：健康通过、幂等重跑 exit 0、属主终态、容器内可读可写 |
| `03-force-recreate-experiment.sh` | 反向实验主剧本（宿主 inode/hash + 容器内 hash + 连接测试三路观测） |
| `03b-restore-ownership.sh` | 属主归一 + **只 restart** 复原 ⇒ 功能级回到 ok:true/200（并再次证明 restart 够） |
| `ab.sh` + `key_probe.py`/`llm_probe.py`/`llm_origin.py` | 浏览器操作封装（脱敏）+ 嵌入/对话连接测试探针（登录 → 连接测试 → 凭据来源） |

另：`02e-no-up.log` 是对**新代码路径**（`--no-up`）的实测：exit 0、22 ok/1 warn/0 FAIL、
运行中的容器未被触碰（Up 11 minutes）。

## ② 用到的既有回归面（不重复跑）

本次没有重跑 replay 门（7 组会话；≈170 s）。原因：本轮的验收对象是**容器交付机制**
（安装/传送/换 key），不是问答质量；问答质量门在同期"只填 key"轮次已 7/7。
容器内 `mirothinker-verify`（安装器第 8 步）本次**通过**（02d 日志）。

## ③ 逐条命令与结果（原始输出见 `raw/`）

```bash
# 传送 + 校验
cp -a /var/tmp/mirothinker-site-bundle-v11 /home/longxiang/delivery-xfer-v11/site-bundle   # 跨 fs
sha256sum -c <17 条 file 行（BUNDLE-MANIFEST）>            → 17/17 OK
sha256sum mirothinker-serving-v1.1.tar.gz                  → f842f6de… MATCH
sha256sum serving-data-v1.1.tar.gz                         → beb9449d… MATCH
sha256sum -c mirothinker-serving-v1.1.tar.gz.sha256        → 校验的是**打包机上的另一个文件**（缺陷 D2）

# sudo 安装（SITE_ROOT 前缀、端口 18298、PG 卷 mirothinker-pgdata-fourth-v11）
sudo ./install-site.sh                                     → 现货包：exit 11（D1+D4）；原版+tmp 唯一：exit 13（D3）
sudo ./install-site.sh（修好的）                            → 首启 ≈455 s 后 /api/health 200 →（被打断）补跑 exit 0
sudo ./install-site.sh（幂等重跑）                          → 25 ok / 0 warn / 0 FAIL、verify 全通、109 s
sudo ./install-site.sh --no-up                             → exit 0、容器未动、22 ok / 1 warn / 0 FAIL

# 反向实验（三路观测）
docker compose exec app sha256sum /opt/mirothinker/.sglang_api_key   # 容器看到的字节
sudo stat -c %i secrets/.sglang_api_key                             # inode 是否换
POST /api/canonical-v2/admin/connections/test {"connection":"embedding"}   # 服务用哪份凭据
  A 基线      → ok:true/200, api_key_source=legacy-file:.sglang_api_key
  换错 key 后未重启 → 容器仍是旧字节（挂载绑旧 inode）
  docker compose restart app（281 s）→ 容器已看新文件；功能级 ok:false/401/凭据缺失
  mv 换 inode + up -d --force-recreate（281 s）→ 同上（recreate 非必须）
  chown 归属主 + restart（281 s）→ 容器 hash == 宿主 hash，ok:true/200（复原）

# 浏览器（agent-browser 0.26.0）
open /main → fill 用户名/口令 → click 登录 → 进入管理台
open /admin → 对话模型卡：fill 新密钥 → 保存本卡 →「密钥已写入 llm.api_key」
            → 测试连通性 →「成功 · 152 ms · HTTP 200 · 凭据来源 legacy-file:.deepseek_api_key」
后端：state/config-managed/secrets.json 0600（值 sha256 == 真 key）、secrets-audit.jsonl 无明文
docker compose restart app（301 s）→ llm 测试：api_key_source=**managed-file(env:DEEPSEEK_API_KEY)**、ok:true/200
（收尾改密：旧口令 401 / 新口令 200）
```

## 未验到 / 未做（如实记录）

- **replay 门（7/7）本轮没跑**（理由见 ②）。
- **页面方式的"清除密钥"**（子弹窗确认）没点；只验了保存 + 测试。
- **跨机器（真甲方机器）**：跨 fs 是"同机两个文件系统"，不是"两台机器+U 盘"；
  镜像 `docker load` 走的是传送后的 tar.gz（已验），但"下载后再上传"这段网络过程没有模拟。
- **D6（entrypoint 文案建议 `user: "0:0"`）与 D8（页面重启提示是裸机命令）未修**，只报告。
- `install-site.sh` 的 `--fast` 分支、`--accept-degraded-keys` 分支本轮没跑（与本组命题无关）。
