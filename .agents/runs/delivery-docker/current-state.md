# delivery-docker — current state（容器交付路径）

> 本文件记录**事实与决定**：冻结输入、代码侧实证结论、本机环境怪癖、以及我做的取舍。
> 原始测量数据（构建耗时、启动秒数、RSS、探针输出、replay 结果）在 `verification.md`。
> 人类侧执行方案见 `docs/plans/2026-09-21-customer-site-delivery-plan.md`（裸机路径，
> 本目录对应的是它的**容器路径对照实现**）。

Task contract（本次切片）：

- Goal：给冻结交付 v1 增加一条**容器交付路径**（镜像 tar + compose），并做端到端演练，
  使团队可以拿它和裸机路径比证据、选主路径。
- Out of scope：不改服务代码；不碰活线（pid 519941 @18188）；不碰其他 rehearsal 目录
  （`.worktrees/{canonical-v2-s11-consolidation,collection-line,data-rebuild,embedding-lane-f1f2}`、
  `/var/tmp/mirothinker-delivery-kit/`）；不做产物轮换/发布流程改动。
- Done when：镜像能构建并落成 tar；在本机用真实数据（冻结绝对路径挂载）+ scratch 状态目录
  + 端口 18298 起来并出答案；`/chat` `/main` 通；嵌入探针 200 + 4096 维；replay 门结果明确
  （跑或说清为什么跑不了）；uid/权限配方与失败症状成文；README（中文）覆盖
  载入/落位/起服务/首启口令/改密/验收/回滚/常见故障；证据与提交落在本 worktree。

## 1. 冻结输入（本次交付 v1）

| 项 | 值 |
|---|---|
| 代码点 | `delivery-v1`（附注 tag）→ commit `36df47b8`，活线 worktree `.worktrees/canonical-v2-s11-consolidation` 即此提交 |
| 服务包 | `/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound/`（4.1 GB） |
| 索引根 | `/var/tmp/mirothinker-data-v2/index-v3-v2/`（2.4 GB） |
| 发布 bundle | `s12g/serving-bundle-run16.json`（tracked，随代码树进镜像路径） |
| 启动命令 | `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh`（单行 env 赋值 + `uv run python …/s12e/serve_s12e_port.py 18188 …`） |
| 活线身份 | pid 519941，`0.0.0.0:18188`，RSS 18 168 732 KiB（≈17.3 GiB），全程未动 |

容器内**新增固定路径**（本路径不参与冻结契约，只是镜像内的代码落点）：

- 代码：`/opt/mirothinker`
- 符号链接：`/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` → `/opt/mirothinker`
  （让冻结命令文件里的代码绝对路径原样成立 ⇒ 冻结命令文件一行不改）

## 2. 代码侧实证结论（读代码得到，演练已在验证的会另外标注）

启动是 `--serve --serve-existing --serving-pack …` 的**pack 模式**：

1. pack 模式下**不会被读**的输入：`--database-url`、`--candidate-staging-root`、
   `--accepted-backup-gate-root` 下的 gate 内容、`--source-manifest`、
   `--recorded-decision-bundle`、`--envelope-output` 指向的信封文件
   （`complete_candidate_runner.py:1154-1175`；create_builder 只在非 serve-existing 路径调用）。
   它们只需要「是绝对路径」+ 信封的**父目录存在** + 全链路无符号链接祖先
   （`complete_candidate_runner.py:299-314`）。
2. pack 模式下**会被真读**的输入：`--recorded-serving-bundle`（路径 + sha256）、
   `--recorded-embedding-bundle`（内容哈希绑定，含 `dimension: 4096` 与嵌入端点）、
   `--index-root`、`--serving-pack`、`--index-marker-sha256`。
3. **逐字符比对的三处**：服务包 `manifest.index_root` ↔ 索引 marker 的 `root` ↔
   serving bundle 的 `index_root`/`envelope_path` 与 CLI 传入值
   （`knowledge_serving_isolated.py:6573-6591`）。⇒ 容器内路径必须与冻结点一致，
   而宿主机路径通过 bind mount 自由映射。
4. **mount-receipt 写失败不会让启动失败**（代码阅读 + **实测**）：`_write_mount_receipt`
   捕获 OSError 只打 warning（`serving_pack_loader.py:404-414`），代价是每次启动全量重新哈希。
   实测只读数据根（`:ro`）能正常启动并过健康检查，唯一痕迹是
   `serving pack mount receipt could not be written: …`。可通过
   `CANONICAL_V2_SERVING_RECEIPT_PATH` 把 receipt 指到可写路径
   （`serving_pack_loader.py:364-368`；本条路径本次只做代码定位，未实测）。
5. **权限问题的文案（经过实测订正）**：原按代码阅读预测的是
   `serving pack file is missing or unsafe: <name>`（`serving_pack_loader.py:312-318`
   的 `is_file()` 为假分支）。**实测不是**：本机 Python 3.12.3 下 `Path.is_file()` 对
   EACCES 抛 `PermissionError`（容器内实测 `file.is_file() -> PermissionError: [Errno 13]`），
   所以 uid 不匹配时看到的是原生 traceback + `complete candidate runner failed: PermissionError`，
   退出码 2（原文见 `verification.md` §5）。结论不变：**是权限，不是缺文件**，
   而且比预测更难读 —— 所以入口预检要负责翻译。
6. 端口被钉死 18188：`_parse_args` 校验 `host=0.0.0.0 and port=18188`
   （`complete_candidate_runner.py:225-229`），s12e shim 再 monkeypatch 成 argv 值。
   ⇒ 容器内必须监听 18188，对外端口只能靠端口映射。
7. 健康检查端点：`GET /api/health` → `{"status":"ok"}`（`apps/admin-console/backend/main.py:128-130`）。
8. 状态目录解析：访问日志/更正库由冻结命令文件给出
   `CANONICAL_V2_ACCESS_LOG_DB` / `CANONICAL_V2_CORRECTIONS_DB`；admin 账号库与签名密钥
   从其父目录推导（`admin_auth.py:127-145`，默认 `/var/tmp/mirothinker-canonical-v2-s12f`）。
9. 受管配置落点：`<repo_root>/config/managed/{settings.json,secrets.json}`
   （`managed_config.py:987-1000`、`managed_secrets.py:597-607`，可用
   `CANONICAL_V2_MANAGED_SETTINGS` / `CANONICAL_V2_MANAGED_SECRETS` 覆盖）
   ⇒ **在容器形态下这是「写进容器层就会丢」的东西，必须挂出来**。
10. 密钥文件查找：cwd + 其各级父目录 + 模块文件各级父目录
    （`providers/local_api_key.py:20-31`、`canonical_v2_runtime_sources.py:116-125`）
    ⇒ 容器 cwd 必须是 `/opt/mirothinker`，4 个密钥文件挂在 `/opt/mirothinker/` 下同名位置。
11. Chromium：tier-1 网页渲染用 playwright，浏览器懒启动；启动失败只降级（httpx+BS4），
    **静默**（`providers/page_fetch.py:150-200`）⇒ 容器必须自带浏览器 + 系统依赖，
    并把 `PLAYWRIGHT_BROWSERS_PATH` 指到全局可读路径（否则非 root 找不到）。

## 3. 本机环境怪癖（影响构建，平台队需要知道）

| 事实 | 证据 | 影响 |
|---|---|---|
| `docker info` **不需要 sudo**（用户 `longxiang` 在 `docker` 组） | §verification 见 `docker info` 输出 | 无需提权，符合硬约束 |
| Docker Hub 直连不通（`registry-1.docker.io` 超时），但 daemon 配了 14 个 registry mirror | `curl registry-1.docker.io` 超时；`pull hello-world`/`ubuntu:24.04` 成功 | 基础镜像能拉；现场改镜像 tag 需要重传 tar |
| **容器出网是白名单**：`pypi.org:443`、`astral.sh:443`、`files.pythonhosted.org:443` 全部 `Errno 101 Network is unreachable`；`archive.ubuntu.com:80`、`cdn.playwright.dev:443`、`100.64.0.27:18005` 通 | `docker run python:3.13-slim` TCP 探针 | ① 构建必须 `--network=host`（已写进 `build-image.sh`）；② astral 安装脚本（走 GitHub CDN）会挂死 ⇒ uv 改装自 PyPI；③ 现场运行时对模型服务的可达性与裸机一致（18005 从容器可达） |
| 索引根目录 mode `drwx------`（700）、`.deepseek_api_key` mode 0600 | `ls -l` | 容器 uid 必须 = 数据属主（1004），否则读不到；见 README §3 |
| 本机资源 | 503 GiB 内存 / 96 核 / `/var/tmp` 所在盘可用 1 TB | 可与活线容器并行做演练 |

## 4. 我做的决定（reviewer 请重点看这里）

1. **演练用数据副本，而不是直接挂活线数据根**：把服务包与索引根 `cp -a` 到
   `/var/tmp/mirothinker-docker-data-v2/`（逐文件尺寸一致；首启的全量哈希校验会证明字节一致），
   再把它挂进容器。理由：① 本机数据根是**活线共享**的，容器首启会在包父目录写/覆盖
   `.mount-receipt.json`（活线 02:12 写的那个），我不想在地面让别人动我的活线；
   ② 副本让「只读挂载」实验可做而不碰活线。代价：多占 6.6 GB 磁盘 + 一次 3 s 拷贝。
   另一路（裸机）演练用的是原目录 ⇒ 两条路径的证据可对照。
2. **镜像只带根 `.venv`（不带 `apps/*/` 的两个 venv）**：root workspace 把 admin-console /
   miroflow-agent 作为 editable 成员装进同一个 venv，服务启动路径就是它。
   `UV_PROJECT_ENVIRONMENT=/opt/mirothinker/.venv` 让容器内任何目录下的 `uv run` 复用同一个环境，
   避免现场无外网时 `uv run` 试图新建/同步第二个 venv。省下约 2.6 GB 镜像体积。
3. **用符号链接承接冻结命令文件里的代码绝对路径**（`…/canonical-v2-s11-consolidation` → `/opt/mirothinker`），
   而不是改命令文件。产物里因此**没有一行改动过的服务代码或冻结参数**。
4. **入口预检把「状态目录不可写」升级为硬失败（退出码 78）**，可用
   `MIROTHINKER_SKIP_PREFLIGHT=1` 绕过。理由：应用侧对不可写状态目录只有一行 warning 且管理面直接不可用，
   在容器里这会被当成「容器坏了」；预检把它变成指名道姓的错误。这是**有意的行为差异**（见 README §9）。
5. **数据根可写性只警告不失败**：与应用行为对齐（receipt 写失败不影响启动），
   入口只解释代价（每次启动全量哈希）。
6. **compose 强制挂载受管配置目录**（`/opt/mirothinker/config/managed`）：不挂就会写进容器层，
   `down && up` 或换镜像即丢 —— 这是容器路径**新增**的失败模式，必须在编排层堵住。
7. **宿主机路径全部参数化，容器内路径全部硬编码**：冻结契约从「宿主机目录树必须同构」
   变成「compose 的容器内 target 必须同构」，宿主机怎么放都行。
8. **保持 `restart: unless-stopped` + `mem_limit: 40g` + `shm_size: 1gb` + healthcheck
   `start_period: 420s`**：分别对应「开机自启」「别 OOMKill 启动」「Chromium 渲染」
   「端口 291 s 后才 bind」。
9. 演练端口 18298（宿主机）→ 容器内固定 18188；证明端口映射与「容器内端口不可改」的兼容性。

## 5. 产物清单（本 worktree，分支 `delivery/docker`）

| 文件 | 作用 |
|---|---|
| `deploy/docker/Dockerfile` | 单阶段镜像：ubuntu:24.04 + python3.12 + uv(PyPI) + 代码 → `uv sync` + Chromium + 冻结账本路径 |
| `deploy/docker/compose.yaml` | 编排：冻结路径 bind mount、受管配置/日志/状态目录、4 个密钥只读、端口、内存、健康检查、日志上限 |
| `deploy/docker/entrypoint.sh` | 容器入口：uid/HOME 预检 + 人话错误；最后 exec **冻结的生产启动脚本**（`deploy/start-canonical-v2.sh`） |
| `deploy/docker/verify.sh` | 容器内验收探针（`mirothinker-verify`）：HTTP + 嵌入 200/4096 + 内存 |
| `deploy/docker/build-image.sh` | 构建 + 冒烟 + 导出 kit（tar/sha256/manifest/compose/README） |
| `deploy/docker/README.md` | 现场 runbook（中文）：载入/落位/uid/起服务/首启口令/改密/验收/换包回滚/故障/边界 |
| `deploy/docker/ledger/**` | 两个镜像内必需的账本小文件（取自重建树，字节一致） |
| `.dockerignore` | 构建上下文卫生（排除 `.git`/`.venv`/`htmlcov`/`report.html`/`.tmp-*`/缓存） |
| `.agents/runs/delivery-docker/{current-state.md,verification.md,rehearse.sh,artifacts/}` | 证据与可复现演练脚本 |

## 5. 演练结论摘要（原始数字见 `verification.md`）

1. **容器能跑起来并出正确的答案**：三次启动 482–486 s；稳态 RSS 17.64 GiB（对照活线 17.32 GiB）；
   `/api/health` `/chat` `/main` 全 200（宿主机侧与容器内各一遍）；嵌入探针 HTTP 200 + **维度 4096**；
   真实问答 `query_type=canonical_v2:A:answer`、6 条引用、575 个流式 `answer_chunk`、无 error 事件。
2. **只读数据根不阻塞启动**（订正了任务书的初始假设）：唯一后果是一行
   `serving pack mount receipt could not be written`，然后每次启动全量重新哈希。
3. **uid 不匹配**：入口预检点名报错（退出码 78）；绕过预检后应用侧是原生
   `PermissionError … manifest.json` / `… .canonical-v2-isolated-index-target.json`（退出码 2）。
   —— 「看起来像崩溃、其实是权限」这条判断成立，只是文案与代码阅读时预测的不同。
4. **验收门与受管配置强相关**：受管配置为空（首启态）时 replay 门 **6/7**（G1 走降级渲染路径，
   第一句是 `（以下为基于本地数据的简要信息）`）；把 live 的 `config/managed/settings.json`
   （含 `serving.chat_llm_profile`）放进挂载目录后 **7/7 全过**。
5. **启动时间待对齐**：容器实测 482–486 s，交付计划里的裸机值是 291 s（出自
   `2026-09-18-collection-line-log.md:1274`）。receipt 有无只差 4 s ⇒ 差异不在 receipt；
   必须与裸机演练在同一台机器上背靠背比一次再下结论。
6. **交付 kit 已产出**：镜像 4.30 GiB / tar 4.37 GiB / **gzip 1.40 GiB**，sha256 与 image ID
   记录在 `/var/tmp/mirothinker-docker-kit/kit-manifest.txt`；镜像层与演练镜像逐层一致
   （image ID 因 config 时间戳不同而不同，对账请看层 ID）。
