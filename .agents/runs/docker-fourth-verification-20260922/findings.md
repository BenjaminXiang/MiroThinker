# 本轮新发现的缺陷（含已修 / 未修）

按"会让甲方踩坑"的严重度排序。修的是**机制**（脚本/文档，v2 重打交付件时自动带上），
没有手改 v1.1 现货产物（v2 会重新打镜像与数据面）。

| # | 缺陷 | 触发条件 | 已观测到的后果 | 处置 |
|---|---|---|---|---|
| **D1** | 交付包**没有 `secrets/` 目录**，而 README-FIRST/CONFIG-GUIDE §2 让操作者在装之前把 key 放进 `secrets/`（还给了一条 `install -m 600 … secrets/.<name>` 的原文命令） | 全新交付包 | 文档给的第一条命令直接 `install: cannot create regular file 'secrets/.deepseek_api_key': No such file or directory`（`raw/02-sudo-attempt1.log` 第 1 节） | **已修**：`build-site-bundle.sh` 出包时创建 `secrets/` 并放 `README.txt`（kit 里本来就有这份说明） |
| **D2** | `mirothinker-serving-v1.1.tar.gz.sha256` 里是**打包机绝对路径**（`/var/tmp/mirothinker-docker-kit-v11/…`） | README-FIRST 第 ① 步照抄 `sha256sum -c` | 打包机上**校验的是另一个文件**（仍 exit 0）；甲方机器上 `No such file or directory` + `WARNING: 1 listed file could not be read`（`raw/01-verify.log` 3b/3c） | **已修**：`build-image.sh` 写相对文件名；`build-site-bundle.sh` 落包时再归一一次（旧 kit 也救得回来） |
| **D3** | 真 root 安装**不归一属主**：状态目录/数据根/密钥/受管配置/日志都是 `root:root`（容器内 uid = 数据属主 1004） | `sudo ./install-site.sh` | 容器入口预检 `状态目录不可写` → `exit 78` 无限重启（`restarts=12`），安装器 `exit 13`（`raw/02b-sudo-attempt2.log`）；密钥 0600 root 时容器读不到 ⇒ 凭据按"缺失"处理（连接测试 401 / `api_key_source=none`） | **已修**：`install-site.sh` 解包后按数据属主 `chown -R` 归一（数据根/状态目录/`secrets/`/受管/日志）；`.env` 归给 `SUDO_UID`（非 sudo 的 `docker compose` 也能读） |
| **D4** | 安装器用**固定 `/tmp` 文件名**（`/tmp/mirothinker-checksums.out`、`/tmp/mirothinker-load.out`） | 这台机器上有人非 root 跑过一次，之后再用 `sudo` 跑（Ubuntu 24.04 默认 `fs.protected_regular=2`） | `line 295: Permission denied` → 报"校验失败"并 `exit 11`（误导性根因；`raw/02-sudo-attempt1.log`） | **已修**：改 `mktemp` + `trap … EXIT` 清理 |
| **D5** | `--no-up` 是**空操作**（只置 `DO_UP=0`，全脚本未再使用） | 用 `--no-up` 想"只准备不起服务" | 照样 `docker compose up -d` 并等健康（与文档承诺不符） | **已修**：`--no-up` 时打印落地状态与起服务命令后 `exit 0` |
| **D6** | entrypoint 的"一行修复"会建议 `user: "0:0"`（因为宿主机上该目录属主是 root） | D3 场景下的报错文案 | 建议把容器跑成 root —— 方向反了（正解是把宿主资产归属主/重跑安装器） | **未修**（仅报告）：建议下一版把该分支文案改成"重跑 install-site.sh（它会归一属主）" |
| **D7** | CONFIG-GUIDE §3 写"文件方式换 key **只 restart 不够**，必须 `up -d --force-recreate app`"（原结论是 inode 语义**推断**，未做实验） | 换 key 文件后重启服务 | **实测推翻**：`docker compose restart app` 就会按路径重新挂载新文件并生效（281 s，功能级 200→401 见 `raw/03-force-recreate.log`）；真正会咬人的是**属主**：`sudo install -m 600` 放的文件 root:root 0600，容器读不到 ⇒ 凭据"缺失"（复原时实测 401，`chown 1004:1004` + restart 后回到 ok:true/200） | **已修文档**：CONFIG-GUIDE §3/§6 改为"`restart` 即生效"+"换完 key 重跑安装器或 chown 归属主"；`--force-recreate` 降级为"保险做法，非必须" |
| **D8** | `/admin` 保存成功的提示是裸机的重启命令：`重启后生效：systemctl --user restart canonical-v2-backend` | 在容器形态里用页面填 key | 现场运维照抄会得到一个不存在的 unit（容器里没有 systemd） | **未修**（仅报告）：v2 建议由服务端下发可配置的重启提示（如 `MIROTHINKER_RESTART_HINT="docker compose restart app"`） |

## 另外两条（不是缺陷，但影响交付判断）

- **首启耗时**：本次实测"冷数据面 + 无 mount-receipt"的首启 ≈ **455 s**（README-FIRST 写的是 7 分 13 秒≈433 s）；
  之后（有 receipt）的三次重启都稳定在 **281 s**（文档承诺 ≈276 s）。安装器幂等重跑（服务已起）总耗时 **109 s**。
- **`secrets/` 的属主**：即使安装器归一过，**之后**再用 `sudo install -m 600` 换 key 又会把文件变回
  `root:root 0600`（D7 实测）——所以"换 key 后重跑安装器"这条必须写进文档（已写）。
