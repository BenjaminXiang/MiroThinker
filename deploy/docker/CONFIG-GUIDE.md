# 现场配置指南（甲方运维版）

> 面向对象：**甲方的运维/系统管理员**。目标只有一句：**把 4 个密钥填进去，其余什么都不用配。**
> 本文是 [README.md](./README.md)（故障处置与运维手册）的**前置配置篇**；
> 安装步骤见同目录 `README-FIRST.txt`，一键安装脚本是 `install-site.sh`。

---

## 1. 一句话结论

**除了 4 个密钥文件，所有配置都已经在交付包里预置好了。** 具体来说：

| 你可能以为要做的 | 实际情况 |
|---|---|
| 编辑 `compose.yaml` / `.env` / 任何配置文件 | **不需要**：安装器自动生成 `.env`（路径、端口、运行 uid 全部自动推导） |
| 改数据路径、建目录 | **不需要**：安装器按冻结路径落位数据面与状态目录 |
| 建数据库、跑迁移 | **不需要**：`postgres:16` 随栈启动，库名固定 `miroflow_collection_v1`，迁移在每次启动时幂等执行 |
| 配嵌入端点 / 模型 / 维度 | **不需要也不允许**：这三项由**冻结的发布包**决定（页面只读展示），换模型需要我方重建索引 |
| 配检索/联网/采集参数、答案用哪个大模型档位 | **不需要**：已按线上同款预置（`chat_llm_profile=deepseekv4flash` 等） |
| 填密钥 | **需要**：见 §2 —— 这是现场唯一的手工输入 |

---

## 2. 密钥清单（现场唯一要准备的东西）

4 个密钥文件放在**交付包目录下的 `secrets/`** 里，文件名必须完全一致，权限 0600：

| 文件 | 管什么 | 从哪里要 | 不填会怎样 |
|---|---|---|---|
| `.sglang_api_key` | **嵌入服务**（语义检索/向量道） | 我方提供（我方模型服务的 key） | **强烈建议必填**：向量道不可用，语义类问题会显著变差甚至整轮失败（这一版还没有"只降级不报错"的保护） |
| `.deepseek_api_key` | **问答用的大模型**（成文/改写） | 甲方自行申请（DeepSeek 开放平台）或找我方代配 | 仍能问答：答案退化为**基于本地数据的模板式要点**（不再是大模型成文的段落），验收门（replay）会是 6/7 而不是 7/7 |
| `.bocha_api_key` | 联网检索（博查） | 甲方自行申请，或找我方代配 | 联网补充通道不可用：只答本地知识库内容；建议给 |
| `.serper_api_key` | 联网检索（Serper/Google） | 同上 | 同上；与博查是**双通道**，只给一个也能工作（覆盖率略降） |

> **`.sglang_api_key` 喂的是"所有嵌入道"，只放这一次就够**：同一个文件会被容器入口脚本投影到
> 两条嵌入权威各自的凭据槽位 —— 自建端点（v1 槽位 `SGLANG_API_KEY`，按文件直读）与第三方
> 网关（候选槽位 `CANONICAL_V2_EMBEDDING_API_KEY`）。站点实际跑哪条道，这个文件里就放哪条道的
> key；**不需要**为第二条道再准备一个文件，也不需要设任何环境变量。
> 排障：`docker compose exec -T app env MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1 /usr/local/bin/mirothinker-entrypoint`
> 会打印"凭据收据"（只有槽位名与是否已设置，从不打印值）。

**放置命令（把 `<你的key>` 换成真实值；在交付包目录里执行）**

```bash
# 4 个都填（推荐）：每条命令一行，执行 4 次
sudo install -m 600 /dev/stdin secrets/.sglang_api_key  <<< "<你的key>"
sudo install -m 600 /dev/stdin secrets/.deepseek_api_key <<< "<你的key>"
sudo install -m 600 /dev/stdin secrets/.bocha_api_key   <<< "<你的key>"
sudo install -m 600 /dev/stdin secrets/.serper_api_key  <<< "<你的key>"

# 检查（应看到 4 行、权限 -rw-------）
sudo ls -l secrets/
```

> 说明：`install -m 600` 一步到位（写文件 + 设权限），比 `echo … > file && chmod 600` 更不容易留下"先 644 后被别人读到"的窗口。
> 密钥**不会**被我方看到；交付包里只有模板 `secrets.example/postgres.env`，没有真钥。

放好之后跑安装（或重跑，安装器是幂等的）：

```bash
sudo ./install-site.sh              # 正式安装
sudo ./install-site.sh --dry-run    # 先只看检查结果，不落地任何改动
```

**缺 key 时的行为**：安装器默认会 **停下来并逐条列出缺哪个文件、放哪里、用什么命令**（不会"半配置"起栈）。
如果你确定要在缺某个 key 的情况下先起来（例如先只让问答可用），加 `--accept-degraded-keys`，它会用 `[warn]` 标注缺项并继续。

---

## 3. 另一种等效填法：登录后在页面里填

也可以**先装、后补 key**：浏览器打开 `http://<机器IP>:18188/main`，登录后进 `/admin` → **密钥/连接**卡片：

- 页面是**掩码回显**（只显示"已设置/未设置"，不回显明文）；
- 保存时**原子写**、权限 0600，审计日志**只记动作不记明文**；
- **保存后在下次重启生效**（服务在启动时读取一次凭据；重启：
  `cd <交付包目录> && docker compose restart app`，约 5 分钟）。

> **换 key 之后怎么生效（2026-09-22 反向实验实测；此前"必须 --force-recreate"的说法已作废）**：
> * 两种方式都只需 **`cd <交付包目录> && docker compose restart app`**（服务在启动时读一次凭据，
>   启动相位 ≈5 分钟）。bind mount 挂的是**文件**：不重启时容器里看到的仍是旧文件内容；
>   而 `restart` 会按路径重新挂载 ⇒ 新文件即刻生效。`up -d --force-recreate app` 也行，
>   但**不是必须**（两者启动耗时一样，restart 更轻）。
> * **真正会让"换了 key 却没生效"的是属主**：`sudo install -m 600 …` 放进去的文件属主是
>   `root:root 0600`，容器以**数据属主**运行（安装器写进 .env 的 `MIROTHINKER_UID`），
>   读不到就当作"没有这个 key"（连接测试会显示"凭据缺失/401"，日志同样）。
>   ⇒ 换完 key 后**重跑一次 `sudo ./install-site.sh`**（幂等，它会把属主归一给数据属主），
>   或 `sudo chown $(sudo stat -c %u /var/tmp/mirothinker-data-v2/index-v3-v2) secrets/.*_api_key`，
>   然后 `docker compose restart app`。
> * 如果第一次安装时某个密钥是缺的，安装器会放一个**空的占位文件**（0600）；之后把真 key
>   写进同一个路径即可（内容写进去或换文件都可以，换文件记得 `restart app`）。
>
> 两条路等价，任选其一。密钥文件（§2）与页面（本节）指向同一批凭据；
> 页面更适合"先上线、后补 key"，文件更适合"一次装完"。

---

## 4. 管理员在页面上还会用到的唯一一处配置

`/admin` → **连接测试**卡片，逐项点"测试"即可（不需要填地址）：

| 项目 | 现场要不要改 | 说明 |
|---|---|---|
| **嵌入端点** | **不能改**（只读展示） | 地址/模型/维度由冻结发布包决定（`http://100.64.0.27:18005/v1`，`Qwen/Qwen3-Embedding-8B`，4096 维）。点"测试"会真的发一次请求：显示 200 + 维度，并给出**向量身份校验**结论（同一空间 cos ≥0.999/0.99 通过；未通过说明这个端点与索引不在同一向量空间）。**换模型必须我方重建索引**，现场改动无效（页面会明确标注"只读"） |
| **chat LLM 档位** | 一般不用改 | 已预置 `deepseekv4flash`（= DeepSeek 的 `deepseek-v4-flash`）。**你只需要 `.deepseek_api_key`**；换上 key 重启后档位即生效。若要换档位，选一档 → 点"测试" → 重启 |
| Bocha / Serper | 不用改 | 地址由提供方钉死，只需 key |
| Rerank 端点 | 不用配 | 默认关闭；配了才启用 |

> 将来我方给出**新的嵌入端点**时：管理员只需在页面把地址改成新值 → 点"测试" → 重启。
> 但如果**模型或维度**变了，就不是现场能解决的事 —— 那需要我方重建索引并出一个新数据面包。

---

## 5. 请**不要**动的东西（以及动了会看到什么）

| 不要动 | 为什么 | 动了会看到什么（原文样式） |
|---|---|---|
| 交付包里的数据面压缩包（`serving-data-v*.tar.gz`）内容、落位后的 `manifest.json` | 服务包与索引根的哈希被三处逐字符比对 | 启动 fail-closed：日志出现 `serving pack file hash differs: <文件名>` 或 `serving pack release differs`，进程退出码 2 |
| 数据根路径 `/var/tmp/mirothinker-data-v2/…`、索引根 `index-v3-v2` | `manifest.json`、索引 marker、发布 bundle 三处写死了绝对路径 | `serving bundle index target differs` / `isolated target marker is missing or unsafe` |
| `compose.yaml` 里的挂载目标与 `user:`（uid/gid） | 容器内路径是冻结契约；uid 必须等于数据属主 | `PermissionError: [Errno 13] Permission denied: …/manifest.json`（**看着像崩溃，其实是权限**） |
| 冻结的启动命令文件（`--serving-pack`、`--index-root`、门禁目录等参数） | 与发布包的封印结果一一对应 | `serving pack index marker differs` / `complete candidate runner failed: RunnerConfigurationError: …` |
| 把 `postgres` 容器的端口暴露到公网 | 采集库只需本栈内部可达 | 无直接报错，但**数据泄露风险**；默认已不发布端口 |
| 升级镜像里的 Python / 换解释器 | 读者摘要含解释器补丁版本 | **不报错**，但每次启动多花 ≈190 秒（见 §6 最后一行） |

> 唯一可以安全修改的是：`secrets/` 里的 key、`/admin` 页面上的可选档位与地址（除嵌入端点）、以及 `docker compose` 的 `restart/stop`。

---

## 6. 症状 → 原因 → 动作

| 症状 | 原因 | 动作 |
|---|---|---|
| 安装器 `[FAIL] 缺少 N 个密钥文件` | 有 key 没放 | 按它打印的路径与命令模板放好，重跑 `install-site.sh` |
| 问答只给要点、不像大模型写的成文段落 | 缺 `.deepseek_api_key`（或档位不对，或 key 文件属主是 root 容器读不到） | 放 key（或页面填）→ `docker compose restart app`（约 5 分钟） |
| 语义类问题变差/失败 | 缺 `.sglang_api_key`，或嵌入端点不通，或 key 文件属主是 root | 放 key（属主归一并 `restart app`）；`/admin` → 嵌入端点 → "测试"应为 200 + 维度 4096 |
| 安装器 `[warn] 嵌入端点探针未过` | 出网不通或 key 不对 | 检查到 `100.64.0.27:18005` 的出网；`/admin` 点测试定位是地址还是凭据问题 |
| 问答没有联网内容 | 缺 `.bocha_api_key` / `.serper_api_key` | 放 key → 重启 |
| 出网通但抓不到网页 | **代理环境变量不生效**（客户端禁用代理） | 需要**直连**或**透明代理**；`http_proxy/https_proxy` 写了也没用 |
| 启动直接失败，日志 `PermissionError: … manifest.json` | 容器运行 uid ≠ 数据属主 | 重跑安装器（它会从数据属主推导 uid）；或 `chown -R` 数据目录到该 uid |
| 容器被 kill（exit 137） | 内存不足 | 该服务稳态占用 ≈17.6 GB，另有采集库；机器建议 ≥64 GB。看 `dmesg` 与 `docker inspect --format '{{.State.OOMKilled}}'` |
| 采集页（`/seeds` `/upload` `/jobs`）503，但 `/chat` 正常 | 采集库（PostgreSQL）未就绪 | `docker compose ps db` 应为 healthy；`docker compose logs db`；`docker compose exec app mirothinker-migrate --status` |
| 每次重启都多花 ≈190 秒 | 镜像里的 Python 与封印该数据包的解释器补丁版本不一致 | 换回交付包里的镜像（自带的解释器是 3.12.12）；**不要**自行升级镜像里的 Python |
| 放进 key 了但能力没变 | ① key 文件属主是 root（sudo install 放的，容器读不到）；② 或没重启（服务只在启动时读凭据） | 先归属主（重跑 `sudo ./install-site.sh` 或 `chown` 给数据属主），再 `docker compose restart app` |
| 安装器 `[FAIL] 校验失败` 且差异清单是空的 | 以前有人非 root 跑过，`/tmp` 里留下的固定文件 root 打不开（v1.1 的已知缺陷，v2 已改成 mktemp） | 删掉旧的 `/tmp/mirothinker-checksums.out`（或直接用 v2 包） |
| 安装器提示"某个 key 是目录" | 曾经缺文件时 docker 建了同名目录 | 安装器会自己删掉并放空占位文件；若提示非空目录，手动 `rm -rf` 后重跑 |
| `/main` 打不开、没有账号 | 状态目录不存在或不可写 | 安装器会自动创建（0700）；若手删过，重跑安装器 |

---

## 7. 网络前提（一次说清）

| 方向 | 需要什么 |
|---|---|
| **出网** | ① 嵌入服务端点（默认 `http://100.64.0.27:18005/v1`）；② chat LLM 端点（默认 `https://api.deepseek.com`）；③ Bocha `api.bochaai.com` / Serper `google.serper.dev`（联网检索）；④ 网页抓取目标（问答要取网页正文时） |
| **不需要** | PyPI、apt 源、Docker Hub —— 镜像与数据面都是离线交付物，现场不需要装任何依赖 |
| **代理** | **不支持**代理环境变量（服务客户端设了 `trust_env=False`）：必须能**直连**，或用**透明代理/网关** |
| **入网** | 只需放行 `18188`（问答与管理台）。采集库端口**不要**对外 |

---

## 8. 验收三步

```bash
# ① 安装器最后一步会自己跑容器内探针（应当看到"全通"）
#    期望：/api/health /chat /main → 200；嵌入端点 → 200 + 维度 4096；RSS ≈17.6 GiB

# ② 登录并改密
#    浏览器：http://<机器IP>:18188/main
#    首启口令在状态目录：/var/tmp/mirothinker-canonical-v2-s12f/admin-initial-password.txt
#    （root 安装时该文件的属主是**数据属主**、状态目录 0700 ⇒ 普通用户读不到就 `sudo cat`）
#    登录后**立即改密**（改完用新口令再登录一次确认）

# ③ 跑回归门（7 组真实会话）。**先确认 chat LLM 档位与 key 已就绪**，否则门会是 6/7：
cd <交付包目录>
docker compose exec -T app mirothinker-replay --out-dir /tmp/accept
#   期望最后一行：RESULT: ALL PASS（7/7）
#   6/7 且 G1_framing 失败 = 缺 LLM key 或档位未生效（答案走了"基于本地数据的简要信息"模板）→ 放 key → 重启 → 重跑
```

装完之后日常运维（巡检、备份采集库、换包回滚、常见故障）看 **[README.md](./README.md)**。
