# 容器交付路径（2026-09-21，对照选项）

> [客户现场交付方案](./2026-09-21-customer-site-delivery-plan.md) 的**对照实现**：
> 甲方允许装 Docker，所以除了「裸机（systemd + 现场 uv sync + 现场装 Chromium）」，
> 还可以走「镜像 tar + docker compose」。本文件只讲这条路径**是什么、测得什么、边界在哪**，
> 现场 runbook 在 `deploy/docker/README.md`（随 kit 一起交付），
> 原始证据在 `.agents/runs/delivery-docker/{current-state.md,verification.md}`（分支 `delivery/docker`）。
>
> 一句话差别：**裸机形态把环境搭在甲方机器上；容器形态把环境装进镜像里** ——
> 现场从「装环境 + 落数据」变成「载镜像 + 落数据」。

## 1. 它把哪些现场工作消灭了

| 裸机形态的现场工作 | 容器形态 |
|---|---|
| `uv sync` 重建 venv（1.5 GB，需外网到 PyPI） | 镜像内已同步好（构建期完成） |
| `playwright install --with-deps chromium`（需 root 装系统依赖） | 镜像内已装，且装到全局可读路径（非 root 也能用） |
| 建 systemd user unit + `loginctl enable-linger` | `docker compose up -d`（`restart: unless-stopped` 自带开机自启） |
| 为满足解析期存在性检查手工铺空目录（门禁根 `s12a/` 等） | 镜像内已创建（含两个真实小账本文件） |
| 宿主机必须复刻 `/var/tmp/...` 冻结目录树 | 冻结路径只在**容器内**成立；宿主机数据放哪儿都行，由 compose 映射 |
| 现场要有 Python 环境才能跑 replay 门 | 容器内 `mirothinker-replay` 离线跑（同一脚本、同一断言） |

**现场网络要求：无**（不需要 Docker Hub、PyPI、apt；`docker load` 即可）。

## 2. 实测数据（本机 2026-09-21，活线 pid 519941 全程未动）

| 指标 | 数值 |
|---|---|
| 镜像 | 4.30 GiB；`docker save` tar 4.37 GiB；**gzip 副本 1.40 GiB**（跨网传这个，`docker load -i *.tar.gz` 实测 21 s） |
| 构建 | 增量（层缓存命中）99–134 s；全新构建本次未单独测（按分层估算 5–8 min，构建期需要外网） |
| 启动（`up -d` → `/api/health` 200） | **486 s**（首启）/ 482 s（有 receipt）/ 486 s（带受管配置）/ 501 s（只读数据根，与另一次并行故受干扰） |
| 稳态 RSS | **17.64 GiB**（容器内进程 VmRSS 之和）／`docker stats` 17.35 GiB（对照裸机活线 17.32 GiB） |
| 探针 | `/chat` `/main` `/api/health` 全 200；嵌入端点 **HTTP 200 + 维度 4096** |
| 真实问答 | `query_type=canonical_v2:A:answer`、答案 578 字、**6 条引用**、575 个流式 `answer_chunk`、无 `error` 事件 |
| replay 门 | 受管配置为空（首启态）**6/7**；放入含 `serving.chat_llm_profile` 的 `settings.json` 后 **7/7 全过**（169 s） |
| 数据根只读（`:ro`） | **启动成功**，仅一行 `serving pack mount receipt could not be written`（不是失败！见 §4） |
| uid 不匹配 | 入口预检点名报错、退出码 78；绕过预检后应用侧是 `PermissionError: [Errno 13] …manifest.json`（退出码 2） |

## 3. uid / 权限（一条配方）

容器运行身份必须 = **数据目录属主**：

```yaml
user: "${MIROTHINKER_UID:-1000}:${MIROTHINKER_GID:-1000}"   # compose
```

现场取值：`stat -c '%u:%g' <数据根>/index-v3-v2`（本机是 `1004:1004`）。
否则：索引根目录是 `drwx------`、`.deepseek_api_key` 是 `0600`，容器该读不到就真读不到。
**失败症状不是"缺文件"而是 `PermissionError` 的 traceback**（本机 Python 3.12.3 下
`Path.is_file()` 对 EACCES 抛异常，不会返回 False）—— 看起来像崩溃，其实是权限。
容器入口脚本会在启动前把这件事翻译成人话并指名路径与 uid（可用
`MIROTHINKER_SKIP_PREFLIGHT=1` 关掉，自己看服务原生报错）。

## 4. 三个「别想当然」的实测结论

1. **只读挂载不会让启动失败**：任务书最初的假设（"父目录必须可写，只读大概会崩"）不成立 ——
   服务侧写 mount-receipt 失败只打一行 warning（`serving_pack_loader.py:404-414`），
   代价是**每次启动都全量重新哈希**。要既只读又保留快路径：把
   `CANONICAL_V2_SERVING_RECEIPT_PATH` 指到可写路径。
2. **验收门依赖受管配置**：全新首启（`config/managed` 为空）时 replay 门 **6/7**，
   `G1_framing` 第 3 轮失败（`subject not in first sentence`）—— 因为答案走了降级渲染路径，
   以 `（以下为基于本地数据的简要信息）` 开头。把 `/admin` 该配的（chat LLM 选档 + 密钥）
   配好即 **7/7**。⇒ 验收前必须先做交付方案 P3 的配置步骤，否则红的是配置不是容器。
3. ~~启动 486 s vs 方案里的 291 s~~ → **已归因并修复（同日）**：根因是**解释器的补丁版本**——包的 release binding 含
   `reader_contract_digest = sha256(python 补丁版本 + pydantic + 源码字节)`，镜像基础系统的 Python 是 **3.12.3**，而封印用的是 **3.12.12**
   ⇒ 摘要不符 ⇒ 每次启动**静默重放重建 ≈190 s**（不报错、日志看不出）。同机同数据根背靠背实测：
   裸机（3.12.12）**275 s** ／ 容器（3.12.3）**466 s** ／ 容器（预编译 18,915 个 pyc，仍 3.12.3）**466 s** ／
   **容器（改用 3.12.12）276 s** ✅（差异全在未记账段的一段 239 s：`serving_pack_loader.py::_canonical_sha256` 的重放）。
   ⇒ **两条交付路径都必须钉 CPython 3.12.12**；验收时比对启动耗时即可发现不一致（≈280 s 合格 / ≈470 s 说明补丁不匹配）。

## 5. 容器不解决的问题 + 新增的失败模式

**不解决**：① 冻结的路径契约（只是从"宿主机路径"挪到"compose 的容器内 target"，
仍逐字符不可改）；② ≈7 GB 数据面仍要另传另校验；③ ≈291 s（或实测 486 s）启动相位不变；
④ ≈18 GB 内存硬约束不变（还多一层 cgroup 限制，设小了直接 OOMKill，没有 swap 兜底）；
⑤ 外部依赖（模型服务 / Bocha / Serper / 抓取目标）可达性不变，代理环境变量同样不生效。

**新增**：① uid/属主不匹配（挂进来的 0700/0600 对容器 uid 不可读）；
② **受管配置写进容器层就丢**（`/admin` 保存的 `settings.json`/`secrets.json` 必须挂出来，
compose 已强制挂）；③ 未挂载的运行期写入（`logs/`、`/tmp`）随 `down` 消失；
④ 镜像 tar 传输损坏（自带 sha256）；⑤ 同一数据根被两个容器同时挂（单实例约束）；
⑥ 镜像 ID 不可逐位复现（层一致、config 时间戳不同）⇒ 交付以 tar 为准、对账看层 ID。

## 6. 交付物与命令（我方 → 现场）

```bash
# 我方出包（构建机需要外网；现场不需要）
deploy/docker/build-image.sh mirothinker-serving:v1
#   → /var/tmp/mirothinker-docker-kit/{mirothinker-serving-v1.tar[.gz], *.sha256,
#      kit-manifest.txt, compose.yaml, README.md, secrets/}

# 现场（三条）
sha256sum -c mirothinker-serving-v1.tar.gz.sha256 && docker load -i mirothinker-serving-v1.tar.gz
# 落数据面到宿主机数据根 + 放 4 个密钥文件（0600）
docker compose up -d                      # 端口/内存/挂载/健康检查都在 compose.yaml 里
docker compose exec -T app mirothinker-verify     # 一键验收（含嵌入 200 + 4096 维）
docker compose exec -T app mirothinker-replay --out-dir /tmp/accept   # replay 门
```

换包/回滚：换镜像 tag（≈486 s 重启）／替换数据根里的包内容并删掉同名
`.mount-receipt.json`（必须删，否则 fail-closed）／换回旧 tag。详见 runbook §7。
