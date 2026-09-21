# Canonical V2 服务栈 · 容器交付 runbook（v1）

> 这套东西解决的是「把**冻结版本**的服务栈交付到甲方服务器并稳定运行」。
> 冻结物：代码点 `delivery-v1`（commit `36df47b8`）+ 服务包 `serving-pack-run16-readerbound`
> + 索引根 `index-v3-v2` + 发布 bundle + 4 个密钥文件。
> 本文只讲**容器形态**：镜像 tar + docker compose。裸机形态（systemd user unit +
> 现场 `uv sync` + 现场装 Chromium）见 `docs/plans/2026-09-21-customer-site-delivery-plan.md`。
>
> 一句话差别：**裸机形态把环境搭在甲方机器上；容器形态把环境装进镜像里** ——
> 现场从「装环境 + 落数据」变成「载镜像 + 落数据」。

---

## 0. 一页速览

| 项 | 容器形态 |
|---|---|
| 交付物 | 镜像 tar（gzip 后 **1.40 GiB**，含 sha256）+ `compose.yaml` + 本手册 + 数据面（另传 ≈7 GB）+ 密钥（另渠道） |
| 现场网络要求 | **无**（不需要 Docker Hub / PyPI / apt；载镜像即可） |
| 现场动作 | ① `docker load` ② 落数据到宿主机的数据根 ③ 放 4 个密钥文件 ④ `docker compose up -d` |
| 镜像内已有 | python 3.12 + uv + `.venv`（构建期 `uv sync` 完成）+ Chromium 及系统依赖 + 代码 + 冻结账本路径 |
| 端口 | 容器内**固定 18188**；宿主机端口由 `MIROTHINKER_HOST_PORT` 决定（默认 18188） |
| 启动耗时 | **≈291 s**（容器不改变启动相位；健康检查 `start_period: 420s`） |
| 内存 | 实测稳态 RSS **≈17.3 GiB**；宿主机 **≥64 GB** 是硬约束 |
| 状态（账号/口令/日志/配置） | 落在**宿主机**挂进来的目录里，换镜像不丢 |
| 回滚 | 换回旧镜像 tag（或旧版本），一条命令重启；数据面不动 |

---

## 1. 交付物与传输

| # | 文件 | 说明 |
|---|---|---|
| 1 | `mirothinker-serving-v1.tar` | 镜像本体（`docker load` 即用） |
| 2 | `mirothinker-serving-v1.tar.sha256` | 校验和 |
| 3 | `kit-manifest.txt` | 镜像 ID、尺寸、构建耗时、tar 的 sha256、冻结点 commit |
| 4 | `compose.yaml` | 现场编排（数据/状态/密钥挂载 + 端口 + 资源 + 健康检查） |
| 5 | `README.md` | 本文 |
| 6 | 数据面（另传） | `serving-pack-run16-readerbound/`（≈4.1 GB）+ `index-v3-v2/`（≈2.4 GB） |
| 7 | 密钥（另渠道） | `.deepseek_api_key`、`.bocha_api_key`、`.serper_api_key`、`.sglang_api_key`（0600） |

传输（在甲方机器上执行）：

```bash
# ① 校验 + 载入镜像（不需要任何外网）
sha256sum -c mirothinker-serving-v1.tar.sha256
docker load -i mirothinker-serving-v1.tar
docker images | grep mirothinker-serving          # 期望看到 mirothinker-serving:v1
```

> 镜像 4.30 GiB（`docker save` tar 4.37 GiB；gzip 副本 **1.40 GiB**，跨网传这个），
> 比裸机形态多出来的部分主要是 `.venv`（1.5 GB）与 Chromium 及其系统依赖 ——
> 换来的是现场零环境搭建。传输示例：
>
> ```bash
> # 传输（1.4 GB）→ 现场只需 docker load
> scp mirothinker-serving-v1.tar.gz* 甲方:/var/tmp/
> sha256sum -c mirothinker-serving-v1.tar.gz.sha256
> docker load -i mirothinker-serving-v1.tar.gz
> ```

---

## 2. 落位数据（宿主机的路径随便放，容器内的路径一个字都不能改）

**为什么不能改容器内路径**：服务包 `manifest.json` 里记着索引根绝对路径、索引 marker 里也记着
`root`、serving bundle 里还会**逐字符**比对这两者与命令行传入值。所以三个绝对路径
（服务包、索引根、封装 bundle 指向的信封路径）在容器内必须逐字符与冻结点一致。

容器形态的好处正在这里：**宿主机上这些文件放哪儿都行**，由 `compose.yaml` 的挂载把它映射到
容器内的冻结路径 —— 不需要在宿主机上复刻同一棵 `/var/tmp/...` 目录树。

| 宿主机（可改） | 容器内（冻结/固定，别改） | 内容 |
|---|---|---|
| `${MIROTHINKER_DATA_ROOT}`（默认 `/var/tmp/mirothinker-data-v2`） | `/var/tmp/mirothinker-data-v2` | 服务包 + 索引根 + 手工召回道 |
| └ 其中 `serving-pack-run16-readerbound/` | 同名 | `manifest.json` `relationships.json` `lookup.sqlite3` `institution_catalog.json` marker |
| └ 其中 `index-v3-v2/` | 同名 | `lookup.sqlite3` `vector_matrix.npz` marker（**不得含 `milvus.db`**） |
| └ 其中 `manual-recall-v1/` | 同名 | 手工召回道（空目录即可，容器会自动补建） |
| `${MIROTHINKER_STATE_DIR}`（默认 `/var/tmp/mirothinker-canonical-v2-s12f`） | `/var/tmp/mirothinker-canonical-v2-s12f` | admin 账号库、会话密钥、首启口令、访问日志、更正库 |
| `${MIROTHINKER_MANAGED_DIR}`（默认 `./state/config-managed`） | `/opt/mirothinker/config/managed` | `/admin` 页保存的受管配置（**必须挂，否则换容器即丢**） |
| `${MIROTHINKER_SECRETS_DIR}`（默认 `./secrets`） | `/opt/mirothinker/`（4 个同名文件） | 4 个密钥（只读挂载） |
| `${MIROTHINKER_LOG_DIR}`（默认 `./state/logs`） | `/opt/mirothinker/logs` | 运行期日志/抓取缓存（可丢） |

落位示例（甲方机器）：

```bash
sudo mkdir -p /srv/mirothinker/data /srv/mirothinker/state /srv/mirothinker/state/config-managed
# 把两个数据目录放到 /srv/mirothinker/data/ 下（保留目录名）
#   /srv/mirothinker/data/serving-pack-run16-readerbound/...
#   /srv/mirothinker/data/index-v3-v2/...
# 密钥：放进 ./secrets/ 四个文件（0600）
```

### 2.1 数据根必须可写（首启会写 mount-receipt）

- 首启通过完整校验后，服务会在**服务包的父目录**写 `<pack>.mount-receipt.json`；
  下次启动凭它走快路径（跳过 artifact 的重新哈希）。
- **只读挂载不会让启动失败**（实测，见 §10）：唯一后果是那一行
  `serving pack mount receipt could not be written: …`，然后每次启动都全量重新哈希。
- 如果数据根必须只读：把 `CANONICAL_V2_SERVING_RECEIPT_PATH` 指到可写路径
  （compose 里已给出注释示例），或在 `/admin` 页把 `serving.mount_receipt_path` 设为可写路径。

---

## 3. uid / 权限（一条配方 + 失败症状）

**配方（一行）**：容器的运行身份必须 = **数据目录的属主**：

```yaml
# compose.yaml
user: "${MIROTHINKER_UID:-1000}:${MIROTHINKER_GID:-1000}"
```

现场怎么取这个 uid：

```bash
stat -c '%u:%g' /srv/mirothinker/data/index-v3-v2     # 例如 1004:1004
export MIROTHINKER_UID=1004 MIROTHINKER_GID=1004
```

或者反过来：把数据目录 `chown -R` 到你想用的容器用户。三选一，别都不做：

| 做法 | 适用 |
|---|---|
| `user: "<数据属主 uid>:<gid>"`（推荐） | 数据已就位、属主已确定 |
| `chown -R <uid>:<gid>` 宿主机数据目录 + 固定 uid | 想固定一个服务账号 |
| 以 root 运行（不设 `user:`） | **不推荐**：状态目录/受管配置会变成 root 属主，后续非 root 运维改不动 |

> 用数字 uid 运行意味着容器里**没有对应的 passwd 条目**（`id -un` 打印不出用户名，
> 入口日志里会看到 `<no passwd entry>`）。这是正常的；服务不依赖 passwd，
> 但如果现场要加 shell 工具或日志采集，注意这一点。

**失败症状（重要，容易误判）**：uid 不匹配时，应用侧报错是**原生 `PermissionError` 的 traceback**
（实测，Python 3.12.3 的 `Path.is_file()` 对 EACCES 不再返回 False 而是抛异常，
所以连"文件缺失或损坏"那种兜底文案都不会出现）：

| 现象（实测原文） | 真实原因 | 一句话修 |
|---|---|---|
| `PermissionError: [Errno 13] Permission denied: '/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound/manifest.json'` + `complete candidate runner failed: PermissionError …`，进程退出码 **2** | 容器 uid 读不到服务包（目录 0700 / 父目录不可穿行） | 把 `user:` 设成数据属主 uid |
| `PermissionError: [Errno 13] Permission denied: '/var/tmp/mirothinker-data-v2/index-v3-v2/.canonical-v2-isolated-index-target.json'`，退出码 **2** | 同上，卡在索引根（实测目录是 `drwx------`） | 同上 |
| 日志只有一行 `serving pack mount receipt could not be written: …` + 启动变慢 | 数据根只读/不可写（**不是** uid 问题，服务照常启动、健康检查照过） | 让数据根可写，或设 `CANONICAL_V2_SERVING_RECEIPT_PATH` |
| 管理面打不开/没有账号，日志里只有一行 warning | 状态目录不存在或不可写（账号库没法建） | 建目录并 chown；容器入口会直接拦下并报名字 |
| 嵌入探针 401/403，其它都正常 | `.sglang_api_key` 是 0600 且属主不是容器 uid → 挂进去了但读不到 | 同上 |
| `docker compose ps` 显示 `Restarting (78)` | 入口预检失败 + `restart: unless-stopped` 在重启循环；78 就是预检的退出码 | 看日志里 `[entrypoint] 预检失败：…` |

本镜像的入口脚本会在启动前把这些**提前翻译成人话**（`[entrypoint] 预检失败：…`，
退出码 78），所以正常情况下你看到的是指名道姓的错误，而不是「缺文件」。
确实要带病启动、自己看服务原生报错：设 `MIROTHINKER_SKIP_PREFLIGHT=1`（此时会看到上表的 PermissionError）。

---

## 4. 起服务

```bash
cd <kit 目录>          # 里面有 compose.yaml / README.md / mirothinker-serving-v1.tar
export MIROTHINKER_DATA_ROOT=/srv/mirothinker/data
export MIROTHINKER_STATE_DIR=/srv/mirothinker/state
export MIROTHINKER_SECRETS_DIR=./secrets
export MIROTHINKER_MANAGED_DIR=/srv/mirothinker/state/config-managed
export MIROTHINKER_UID=1004 MIROTHINKER_GID=1004
export MIROTHINKER_HOST_PORT=18188        # 甲方反代指到这个端口

docker compose up -d
docker compose logs -f app                # 启动相位（实测 276 s；见 §10），看到 uvicorn 起来即完成
```

判断「起没起来」：

- `docker compose ps` 的 `STATUS` 从 `health: starting` → `healthy`（**启动相位跑完端口才 bind**，
  所以在此之前 HTTP 探针全是 connection refused，属正常）；
- 容器内 `curl -s http://127.0.0.1:18188/api/health` 返回 `{"status":"ok"}`；
- 首次启动日志里会出现 `candidate_release_id=…`、`serving_pack=/var/tmp/…`、
  包/索引的校验行；任何 integrity/release 不匹配都会**fail-closed 并点名**，不需要猜。
- **启动耗时对解释器补丁版本敏感**：镜像里的 Python 必须与封印该服务包的解释器一致
  （当前 **3.12.12**）；不一致不会报错，只会静默多花 ≈190 s（见 §12.3）。
- 采集库那一行在更前面：`[entrypoint] 采集库迁移就绪：{…}` 与
  `[canonical-v2] console_database=configured`（没有这一行就是没配 PG，采集面会 503）。

---

## 4.1 采集库（PostgreSQL）也在栈里

第二轮起，栈里多了 `db` 服务（官方 `postgres:16`，库名固定 **`miroflow_collection_v1`**）。
它带来的是采集面：`/seeds`、`/upload`、`/jobs` 与 `/admin` 的新鲜度面板。

**为什么是 postgres:16 而不是 17**：迁移集（`apps/miroflow-agent/alembic`，43 个版本、head V042、
42 张表）只用到 `pgcrypto`（V001 的 `gen_random_uuid()`），16 与 17 都够；
选 16 是因为与现网/构建环境同版本（`postgres:16` 已在镜像清单里，现场不必再拉），少一个变量。
**不需要 pgvector**（迁移里没有任何 `vector` 类型；V029 里的 “vector” 只是注释文字）。

### 4.1.1 凭据与 DSN

| 项 | 位置 |
|---|---|
| 用户/口令 | `secrets/postgres.env`（0600，**不入 git**；模板 `secrets.example/postgres.env`） |
| 库名 | `miroflow_collection_v1`（钉在 compose 里，不随凭据文件漂移） |
| app 侧 DSN | 入口脚本从 `POSTGRES_*` 组装 → `postgresql://<user>:<pw>@db:5432/miroflow_collection_v1`，也可用显式 `DATABASE_URL` 覆盖 |

**为什么不用 compose 插值拼 DSN**：`env_file` 只把变量塞进容器，不参与 compose 的 `${…}` 插值；
如果靠插值，忘记 `--env-file` 就会拼出「空口令」的 DSN，报错还很难看出来。
现在的做法是「凭据只进容器、DSN 在容器入口组装」，所以**普通 `docker compose up -d` 就够**，
不需要额外命令行参数；没放凭据文件时 compose 会直接报 `env file … not found`（fail-loud）。

`DATABASE_URL` 是控制台/采集线的**唯一** DSN（`apps/admin-console/backend/console_dsn.py`；
`DATABASE_URL_TEST` 只是回退）。**不要**设 `CANONICAL_V2_DATABASE_URL` ——
那是 V2 运维面的另一个库，且要求 `CANONICAL_V2_EXPECTED_DATABASE` /
`CANONICAL_V2_TARGET_KIND` / `CANONICAL_V2_BACKUP_GATE_ROOT` 三个伴随变量、
语义是「可破坏目标」；把它指到采集库等于让运维面把采集库当候选库用。

### 4.1.2 迁移是幂等的（每次启动都会跑一次）

```bash
docker compose exec -T app mirothinker-migrate --status     # 只报告：版本 + 表数
docker compose exec -T app mirothinker-migrate              # 等待 + 标记 + alembic upgrade head
```

入口脚本在 exec 服务之前调它，**有界**（`MIROTHINKER_MIGRATE_WAIT_SECONDS`，默认 120 s）
且**失败只降级**：PG 不可用不影响 `/chat`（采集面本来就是 503 + 导航隐藏）。
实测：首次（空库）`{"revision_before": "", "revision": "V042", "tables": 42}`；
第二次 `{"revision_before": "V042", "revision": "V042"}` ⇒ 幂等。

迁移合同是 fail-closed 的（`alembic/env.py` → `resolve_destructive_database_target`）：
只认 `ALEMBIC_DATABASE_URL` + `ALEMBIC_EXPECTED_DATABASE` + `ALEMBIC_TARGET_KIND`，
并且连接后要用 `shobj_description()` 读回**库身份标记**才肯迁移。
`mirothinker-migrate` 会先幂等地写这个标记：

```sql
COMMENT ON DATABASE miroflow_collection_v1
  IS 'miroflow:destructive-target:v1:disposable:miroflow_collection_v1';
```

> ⚠️ 注意 `disposable` 这个词：迁移合同**只允许** `disposable` / `isolated-candidate`
> 两种目标类型（`database_target.py:25`），没有「生产库」这一档。所以客户现场的采集库
> 也只能标成 `disposable`。语义上别扭，但这是现网代码的既成契约 —— 别把 `COMMENT` 上的
> `disposable` 误读成「这个库可以随便删」，它只是迁移器的准入令牌。

### 4.1.3 pgdata、备份与恢复

- pgdata 用**具名卷** `mirothinker-pgdata`（`docker volume`），不进镜像层；
  用卷而不是 bind mount 的原因：官方镜像的入口脚本要自己 chown 数据目录，
  用宿主目录就得先 `sudo chown 999:999 <dir>`（可做，但多一步且容易忘，症状见 §8）。
- **逻辑备份（推荐）**：

```bash
# 备份：pg_dump 从 db 容器里出（不需要把 5432 暴露到宿主）
docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d miroflow_collection_v1 \
  --no-owner --no-acl' | gzip > /srv/mirothinker/backup/miroflow_collection_v1-$(date +%F).sql.gz
# 恢复（先建一个空库再灌；不要直接覆盖生产库）
docker compose exec -T db sh -lc 'psql -q -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS miroflow_collection_v1_restore" \
  -c "CREATE DATABASE miroflow_collection_v1_restore"'
gunzip -c /srv/mirothinker/backup/…sql.gz | docker compose exec -T db sh -lc \
  'psql -q -U "$POSTGRES_USER" -d miroflow_collection_v1_restore'
```

- **物理备份**：`docker run --rm -v mirothinker-pgdata:/data -v /srv/mirothinker/backup:/backup alpine tar czf /backup/pgdata-$(date +%F).tgz -C /data .`
  （最快，但只能整体还原到同版本 PG）。
- 实测（本机）：`pg_dump` 114 871 B；restore 到 scratch 库后**42 张表的行数逐表一致**，
  `professor_seed=2 / pipeline_run=3 / alembic=V042`，`pipeline_run` 的 run_id+status 摘要 md5 相同。
- 备份路径建议：`/srv/mirothinker/backup/`（与数据根同级，纳入磁盘告警）。

### 4.1.4 不装 PG / PG 坏了

- **不装**：栈是「都进容器」，所以默认就有 PG。要退回「不装 PG」的旧形态：
  用 override 去掉 `db` 服务与 `POSTGRES_*`/`env_file`，或直接只起 `docker compose up -d app`
  并把 `DATABASE_URL`、`POSTGRES_USER`、`POSTGRES_PASSWORD` 都不给 ⇒ 采集面回到
  「503 + 导航隐藏」，`/chat` 不受影响（这是设计行为，不是故障）。
- **PG 坏了**：入口的迁移有界等待超时后只打警告并继续启动；
  `console_database` 仍是 `configured`，采集面接口返回 503 `postgres_unavailable`。
  修好 db 后重启 app 容器即可（`docker compose up -d --force-recreate app`）。

---

## 5. 首启口令与改密
```bash
# 首启口令文件在状态目录（宿主机直接可见，因为它是挂进来的）
cat ${MIROTHINKER_STATE_DIR}/admin-initial-password.txt
# 浏览器打开 http://<甲方地址>:18188/main 登录 → 立即改密
```

状态目录里你会看到：`admin-auth.sqlite3`（账号库）、`admin-auth.key`（会话签名密钥）、
`admin-initial-password.txt`（首启一次性口令）、`access-logs.sqlite3`、`corrections.sqlite3`。
它们都在宿主机上，**换镜像/重建容器不丢**；备份 = 备份这个目录。

> 容器形态不做「多副本共享状态」：状态目录是单机 bind mount，只能挂给一个容器。

---

## 6. 验收

```bash
# ① 容器内一键探针：/api/health、/chat、/main、嵌入端点（HTTP 200 + 维度 4096）、内存
docker compose exec -T app mirothinker-verify

# ② replay 回归门（7 组会话）—— 容器内离线跑，不需要现场 Python 环境、不需要出网
docker compose exec -T app mirothinker-replay --out-dir /tmp/accept
# 全部通过时退出码 0；报告落 /tmp/accept/report.json（要留档就 cp 到挂载目录）
docker compose exec -T app bash -lc 'cp /tmp/accept/report.json /opt/mirothinker/logs/accept-report.json'

# ③ 人工抽检：/chat 点名 / 语义 / 关系 各一问，看本地引用是否齐全
# ④ 内存：docker stats --no-stream   （实测稳态 ≈17.4 GiB）
```

> **replay 门与受管配置的关系（实测，别踩）**：受管配置目录为空（全新首启）时，
> 本机实测 replay 门是 **6/7**——`G1_framing` 第 3 轮失败
> （`subject not in first sentence`：答案以 `（以下为基于本地数据的简要信息）` 这行降级提示开头）。
> 把宿主机上的 `config/managed/settings.json`（含 `serving.chat_llm_profile`，内容非机密）放进
> 受管配置目录后，同一问得到正常的流式散文答案（575 个 `answer_chunk` 事件），**7/7 全过**。
> ⇒ **验收前必须先做交付计划 P3 的 `/admin` 配置（chat LLM 选档 + 密钥）**，
> 否则门会红，但红的是配置不是容器。

> **镜像里三份 pyproject、只有一个 venv**：镜像为体积只带根 workspace 的 `.venv`
> （服务启动用的就是它），并统一设 `UV_NO_SYNC=1` ⇒ 容器内任何目录下的
> `uv run` 都直接复用这个已固化环境，**不会**试着联网同步第二个 venv。
> 所以文档里那条原始命令在容器内也能跑（实测）：
>
> ```bash
> docker compose exec -T app bash -lc \
>   'cd apps/admin-console && uv run python scripts/replay_fix_round1.py \
>      --base-url http://127.0.0.1:18188 --out-dir /tmp/accept'
> ```
>
> 推荐仍用 `mirothinker-replay`（等价、更短、且不依赖 cwd）。作业门里有同样的场景：
> 采集作业的 argv 是 `cd apps/miroflow-agent && uv run python scripts/…`，
> 没有 `UV_NO_SYNC=1` 时会去装该项目的 dev 组（`inline-snapshot` 等）并失败
> —— 这也是这个变量必须留在镜像里的原因（实测：设之前 preview 作业 `adapter_missing`
> 之外还会撞 uv 报错，设之后作业正常跑通）。

---

## 7. 换包 / 回滚

| 场景 | 动作 | 停机 |
|---|---|---|
| 换镜像（代码/依赖升级） | `docker load -i mirothinker-serving-v1-1.tar` → 改 tag → `docker compose up -d` | ≈291 s |
| 回滚镜像 | 把 `MIROTHINKER_IMAGE` 换回旧 tag → `docker compose up -d`（旧镜像留着即可） | ≈291 s |
| **换数据包**（新服务包，路径名不变） | 替换宿主机数据根里 `serving-pack-run16-readerbound/` 的内容 → 删掉同名 `.mount-receipt.json` → 重启 | ≈291 s + 全量校验 |
| 换数据包（想保留旧包做回滚） | 新包放到另一个目录名（如 `serving-pack-run17/`），用挂载覆盖命令文件把 `--serving-pack` 指过去（见 compose 注释示例）→ 重启 | ≈291 s |
| 配置回滚 | `/admin` 改回上一版 → 重启生效 | ≈291 s |
| 整体停服 | `docker compose stop`（保留容器与数据）或 `down`（删容器，数据/状态在宿主机不动） | 立即 |

> 换数据包时**务必**删掉旧的 `.mount-receipt.json`：它是「同名包内容不变」的凭证，
> 换了内容但保留 receipt 会导致启动直接失败（这是设计上的 fail-closed，不是 bug）。

---

## 8. 常见故障

| 症状 | 排查顺序 |
|---|---|
| 容器起不来，`docker compose ps` 显示 `Exited (78)` | 看 `docker compose logs app` 的 `[entrypoint] 预检失败`：它直接点名是哪个路径、容器 uid 是多少、该改成什么 |
| 一直 `health: starting`，超过 6 分钟 | ① `docker compose logs -f app` 看卡在哪个相位；② `docker stats` 看内存是否被限死；③ 数据是否真的挂进来了（`docker compose exec app ls /var/tmp/mirothinker-data-v2`） |
| 端口访问不到 | 检查 `MIROTHINKER_HOST_PORT` → 容器内**永远**是 18188；`ss -ltnp \| grep <port>`；甲方防火墙 |
| `bind source path does not exist` | 密钥文件没放齐（4 个都要）或数据根路径写错 —— 这是 compose 的保护，别用 `-v` 短语法绕过（短语法会**建目录**，反而更难查） |
| OOM / 被 kill（exit 137） | 宿主机内存 <64 GB，或 `MIROTHINKER_MEM_LIMIT` 调得太小（实测稳态 17.3 GiB，启动峰值更高）；先看 `dmesg -T \| tail` 与 `docker inspect -f '{{.State.OOMKilled}}'` |
| 网页抓取质量变差但服务正常 | Chromium 起不来（降级为 httpx+BS4，**静默降级**）。自检：`docker compose exec app /opt/mirothinker/.venv/bin/python -c "from playwright.sync_api import sync_playwright;p=sync_playwright().start();print(p.chromium.executable_path);p.stop()"` |
| `/admin` 改完配置，重建容器后没了 | 受管配置目录没挂（`MIROTHINKER_MANAGED_DIR`）。它是 `/opt/mirothinker/config/managed` 的挂载点，**必须在挂载清单里** |
| `env file … not found: ./secrets/postgres.env` | 采集库凭据文件没放。`cp secrets.example/postgres.env secrets/postgres.env` + 填口令（模板见 §4.1.1） |
| db 容器起不来，日志 `initdb: error: could not change permissions of directory "/var/lib/postgresql/data"` | 用了 **bind mount** 做 pgdata 但宿主目录属主不是 uid 999。要么改用默认的具名卷，要么 `sudo chown -R 999:999 <pgdata 目录>` |
| 采集面 503 `postgres_unavailable`，但 `console_database=configured` | DSN 有、连不上：看 `docker compose ps db` 是否 healthy；`docker compose logs db`；`docker compose exec -T app mirothinker-migrate --status` |
| 采集作业跑不起来，日志里是 uv 的 `Failed to download …` | 镜像丢了 `UV_NO_SYNC=1`（三份 pyproject 的 dev 组差异会让 `uv run` 想联网）。见 §12.2 |
| 视频/日志目录越来越大 | `docker compose logs` 已限 50 MB×5；`logs/debug` 缓存挂到了宿主机，可定期清 |

---

## 9. 容器解决了什么 / 不解决什么（别把容器当银弹）

### 解决了

| 裸机形态的现场工作 | 容器形态 |
|---|---|
| `uv sync` 重建 venv（需外网到 PyPI，1.5 GB 下载） | 镜像内已同步，现场零网络 |
| `playwright install --with-deps chromium` + root 装系统依赖 | 镜像内已装（全局可读路径，非 root 也能用） |
| 建 systemd user unit + `loginctl enable-linger` | `docker compose up -d`（`restart: unless-stopped` 自带开机自启） |
| 为满足解析期存在性检查手工铺空目录（门禁根 `s12a/` 等） | 镜像内已创建（含 2 个真实小账本文件） |
| 宿主机必须复刻 `/var/tmp/...` 冻结目录树 | 冻结路径只在容器内成立，宿主机路径自由 |
| 现场 Python 环境才能跑 replay 门 | 容器内 `uv run` 直接跑（离线） |

### 不解决

1. **冻结的路径契约本身**：只是从「宿主机路径」搬到了「compose 的容器内目标路径」，
   依然一个字都不能改（服务包 manifest / 索引 marker / serving bundle 三处逐字符比对）。
2. **≈7 GB 数据面**：仍要另传、另落位、另校验（镜像里**不放**数据）。
3. **≈291 s 启动**：启动相位是代码行为，容器不会让它变快（`start_period` 只是别误判）。
4. **≈18 GB 内存**：硬约束不变；容器反而多一层 cgroup 限制，设置过小会 OOM。
5. **外部依赖**：模型服务（嵌入 :18005 / 重排 :18006 / LLM）、Bocha/Serper、抓取目标 —— 网络可达性
   与裸机相同，容器不提供任何代理或缓存（代理环境变量在本客户端也**不生效**，`trust_env=False`）。
6. **数据面权限设计**：容器不能替你决定 uid，反而把 uid 问题变得更显式（见 §3）。

### 容器**新增**的失败模式（裸机没有的）

| 新增失败模式 | 说明 | 处置 |
|---|---|---|
| uid/属主不匹配 | 挂载进来的文件对容器 uid 不可读（尤其是 mode 0700 的索引根、0600 的密钥）；裸机下不会有这一层 | §3 配方 + 入口预检 |
| 受管配置写进容器层 | `/admin` 的 `settings.json`/`secrets.json` 若未挂出，`docker compose down && up` 或换镜像即丢失 | compose 已强制挂载 `MIROTHINKER_MANAGED_DIR` |
| `docker compose down` 清掉未挂载的运行期写入 | 例如 `/opt/mirothinker/logs`、`/tmp` 下的产物 | compose 已挂 `logs`；replay 报告记得 `cp` 出来 |
| 宿主机重启后容器不自启（若 compose 没配 restart） | 本 compose 已设 `restart: unless-stopped` | 加 `docker` 服务开机自启 |
| 镜像 tar 传输损坏 | 7→2 GB 级文件传输 | `sha256sum -c`（交付物自带） |
| 内存被 cgroup 限死 | `mem_limit` 设太小直接 OOMKill，且**不再有 swap 兜底** | 保持 ≥40g（默认） |
| `no-new-privileges`/seccomp 类加固误伤 Chromium | 部分加固策略会让浏览器起不来，表现为静默降级 | 用 `mirothinker-verify` 的 Chromium 自检行 |
| 时间/时区漂移 | 容器内 TZ 固定 `Asia/Shanghai`，与宿主机不一致时日志时间戳会对不上 | 需要时在 compose 里覆盖 `TZ` |
| 两次启动共用同一数据根（误操作） | 两个容器同时挂同一数据根/状态目录 → SQLite 争用、mount-receipt 互相覆盖 | 单实例部署；状态目录只挂给一个容器 |
| **采集库也进了栈** | 新增 `db` 容器 + 具名卷：多一份要备份的数据（pgdata），多一个启动依赖顺序，多一处凭据文件（`secrets/postgres.env`） | §4.1 的备份/恢复与故障处置；`db` 挂了只影响采集面（`/chat` 不受影响） |
| **建库顺序与迁移耦合** | 首次启动时 app 会等 PG（有界 120 s）再迁移；PG 起得慢只是让 app 晚一点进入启动相位，超时则降级（采集面 503） | 观察 `[entrypoint] 采集库迁移…` 行；必要时调 `MIROTHINKER_MIGRATE_WAIT_SECONDS` |
| **pgdata 属主** | 用具名卷时官方镜像自己 chown；改成 bind mount 就得先 `chown 999:999`，否则 initdb 直接失败 | §8 对照表 |

---

## 10. 实测数据（本机演练，2026-09-21）

| 指标 | 数值 |
|---|---|
| 镜像尺寸 | **4.9 GiB**（含托管 CPython 3.12.12 + 18915 个预编译 pyc）；`docker save` tar ≈5.1 GiB；gzip 副本 **1.56 GiB** |
| 构建耗时 | 增量（层缓存命中）≈2 min；全新构建含 Chromium 与 `uv sync` 约 5–8 min（构建机需外网） |
| **容器启动（up → `/api/health` 200）** | **276 s**（与同机裸机的 275 s 同档；数据根 = 活线目录 `:ro`＋预热 receipt＋热缓存） |
| 容器启动（解释器与包不一致时） | 466 s（Python 3.12.3；多出的是 ≈190 s 的 reconstruction 重放，见 §12.3） |
| 容器启动（compose 全栈首启，含 PG 迁移） | 479–481 s（迁移本身 0.075–0.20 s，不进关键路径） |
| 稳态 RSS | 17.6 GiB（cgroup 17.4–17.8）；对照活线 17.3 GiB |
| 采集库（PG） | 首次迁移 `revision_before="" → V042`，42 张表；二次/三次 `revision_before=V042 == revision`（幂等） |
| 采集面 | 登录 200；`/seeds` `/upload` `/jobs` `/admin` 200；4 个 admin API 200；`console_database=configured` |
| preview 采集（唯一一次真跑） | run `succeeded`，**443 s**，`written_profile_count=0`、`diagnostic_profile_count=995`、抓取缓存 +996 文件；`trigger_mode=preview`（不落库） |
| `pg_dump` / restore 对账 | dump 116 484 B；restore 到 scratch 库后 **42/42 张表行数全等**（`professor_seed=3`、`pipeline_run=4`、`pipeline_issue=2`、`alembic_version=1`，其余为空） |
| `down` + `up` | 迁移幂等 + 数据留存（具名卷 `mirothinker-pgdata`） |
| 数据根只读挂载 | 启动成功；仅一行 `serving pack mount receipt could not be written`（设了 `CANONICAL_V2_SERVING_RECEIPT_PATH` 则连这行也没有） |
| uid 不匹配 | 入口预检点名（退出码 78）；绕过预检是 `PermissionError … manifest.json`（退出码 2） |

> 完整原始日志：`.agents/runs/delivery-docker/verification.md` 与 `/var/tmp/mirothinker-docker-logs/`。

## 11. 镜像内的冻结账本路径（为什么镜像里要有这些东西）

服务启动在**解析期**会要求一批绝对路径存在（其中两个文件真的会被读并做哈希绑定）。
容器形态把这件事收进镜像，现场不必铺：

| 镜像内路径 | 原因 | 来源 |
|---|---|---|
| `/opt/mirothinker/` | 代码树（editable 指针指向这里） | 仓库 `delivery-v1`（commit `36df47b8`） |
| `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` → `/opt/mirothinker`（符号链接） | 让**冻结命令文件**里的代码绝对路径（启动脚本/`serve_s12e_port.py`/`--recorded-serving-bundle`）原样成立 ⇒ 一行都不用改 | 构建时创建 |
| `…/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/` | 门禁根 + `--envelope-output` 的父目录（解析期要求存在） | 构建时创建（空目录即可） |
| 同上 `s12a/recorded-decision-bundle-v1.json` | 解析期传入的决策包（`--serve-existing` 路径不读其内容，但保持一致） | 取自重建树，字节一致 |
| 同上 `s12c/qwen-embedding-bundle-v1.json` | **运行期真的会读**：嵌入端点/模型/维度（维度 4096）在这里 | 取自重建树，字节一致 |
| `…/full-column-serving-pack-rebuild/`（父目录） | `--source-manifest` 的父目录（`--serve-existing` 路径不读该文件） | 构建时创建（空目录即可） |
| `…/apps/miroflow-agent/milvus.db`（**故意不存在**） | 冻结参数里这是「禁止出现的 Milvus 路径」，服务会校验包里没有它 | 不创建（正确状态就是不存在） |

两个账本文件的字节校验（随镜像 COPY，来源为重建树同名文件的逐字节副本）：

```
2b4164ce9a7202cf01cb3e1afb5b9c9d71d219d50a93bd597008da74ed45985d  s12a/recorded-decision-bundle-v1.json
9b840145f94fbd7547f21bd7d4c7e7ce564e1a5f2960f45df31b1de30ceec23f  s12c/qwen-embedding-bundle-v1.json
```

镜像内自检：

```bash
docker compose exec -T app sha256sum \
  /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12{a,c}/*.json
```

---

## 12. 我方重建镜像（发新版本时）

```bash
cd <仓库 worktree>
deploy/docker/build-image.sh mirothinker-serving:v1.1     # 产出 kit 到 /var/tmp/mirothinker-docker-kit
```

- 构建需要外网（apt + PyPI + uv 安装脚本 + Chromium 浏览器包），**现场不需要**；
  > 构建机注意：本机容器出网是白名单（PyPI 不在内），所以 `build-image.sh` 用
  > `--network=host` 借宿主机网络；uv 从 **PyPI** 装（astral 官方安装脚本走 GitHub
  > release CDN，实测在容器里会挂住）。
- 版本编号沿用交付计划 §8.1：v1 = 本次冻结点；后续增量按 v1.1/v2 出**新 tag 的镜像**，
  现场按 §7 换 tag；
- 数据面不进镜像：换数据走 §7 的「换数据包」，与镜像版本解耦；
- 冻结纪律不变：v1 只接受「修致命问题」的补丁。

### 12.1 镜像不是逐位可复现的（对账方式）

同一个 Dockerfile 在两次构建里产生的**镜像层逐层相同**，但 image ID 不同
（image config 里的 `created` 时间戳参与 ID 计算）。所以：

- 交付/回滚**以 tar 为准**（tar 自带 sha256），不要用「在另一台机器重建一次」来对账；
- 要核对「两个镜像是不是同一份东西」，比 **层 ID**：
  ```bash
  docker history --no-trunc --format '{{.ID}}' mirothinker-serving:v1
  ```
- 演练用的镜像 ID 与交付 tar 里的镜像 ID 因此可能不相等（本次即是），这是正常的。

### 12.3 解释器版本是冻结契约的一部分（**最容易踩的坑**）

服务包 manifest 里记着**封印时那个"读者"的摘要**：

```
reader_contract_digest() = sha256( python=3.12.x  +  pydantic 版本  +  canonical_v2 包的 .py 字节 )
```

启动时 `open_serving_pack_authority` 会拿本机算出的摘要与包里记录的值比对
（`serving_pack_loader.py:284-309`）：

- **一致** ⇒ 直接信任封印时的 reconstruction，跳过重放（这是 run16 重封的意义）；
- **不一致** ⇒ 每次启动都把整张对象图重新序列化 + 哈希，**静默多花 ≈190 s**
  （实测 466 s vs 276 s；不会报错、不会拒载）。

本机实测：包由 **3.12.12** 封印（`ebc22047…`）；Ubuntu 24.04 自带 **3.12.3** 算出
`8b4b69de…` ⇒ 命中慢路径。镜像因此改用与封印一致的托管 CPython 3.12.12
（构建机 `uv python install 3.12.12`，由 `build-image.sh` 作为构建上下文 COPY 进去；
python-build-standalone 直连本机只有 ~17 KB/s，不适合放在构建里下载）。

**运维含义（两条路径都要遵守）**：

1. 现场重建 venv（裸机路径）时，**不要**用系统 python（Ubuntu 24.04 的 3.12.3 会命中慢路径），
   用 `uv python install 3.12.12` 后再 `uv sync`；或把 `.python-version` 钉成 `3.12.12`。
2. 下一次封印（run17+）如果换了构建机/解释器，**镜像与现场的解释器都要同步跟过去**，
   否则启动时间会从 ~276 s 掉到 ~466 s。检测方式：对比启动耗时，或
   `docker compose exec app python -c "import sys; print(sys.version)"`。

### 12.2 构建期踩过的坑（改 Dockerfile 前先看）

1. **不要用 astral 的 `install.sh` 装 uv**：它要从 GitHub release CDN 取二进制，
   在受限出网的构建环境里会长时间挂住 ⇒ 改用 `python3.12 -m pip install uv==<pin>`。
2. **构建期以 root 跑过 uv 之后，必须清 HOME 里的缓存目录**：否则运行期非 root 用户
   执行 `uv run` 会报 `Failed to initialize cache … Permission denied`，启动直接失败。
   （现 Dockerfile 已清理 `HOME` 并 `chmod 1777`，entrypoint 另有可写缓存目录兜底。）
3. **`--with-deps chromium` 必须在 root 阶段装**，并通过 `PLAYWRIGHT_BROWSERS_PATH`
   装到全局可读路径；否则非 root 运行的用户找不到浏览器，抓取静默降级。
