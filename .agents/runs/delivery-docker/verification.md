# delivery-docker — verification（原始证据）

> 结论与取舍在 `current-state.md`；这里只有**跑过的命令与原始数字**。
> 时间：2026-09-21（16:00–16:35 完成主要演练）。宿主：`gpu01`（Ubuntu 22.04，kernel 5.15，
> 503 GiB RAM / 96 核）。活线（pid 519941 @18188，worktree `canonical-v2-s11-consolidation`）
> **全程未动**：演练前 RSS 18 168 732 KiB → 演练后 18 168 708 KiB（同一进程，未重启）。

## 0. 前置检查

```
$ docker info            # 不需要 sudo（用户 longxiang 在 docker 组，gid 123）
Client: Docker Engine - Community 28.5.1 / Server: 28.5.1
Containers: 82  Running: 8   Images: 57   Storage Driver: overlay2   Cgroup Version: 2
$ id
uid=1004(longxiang) gid=1004(longxiang) groups=1004(longxiang),27(sudo),123(docker)
$ docker compose version --short
v2.40.2
```

宿主机出网 vs 容器出网（决定构建方式，见 §2）：

```
$ curl -sS -o /dev/null -w "pypi:%{http_code}\n" https://pypi.org/simple/        # 宿主机
pypi:200
$ docker run --rm python:3.13-slim python -c "<TCP 探针：容器内>"
  pypi.org:443 -> OSError: [Errno 101] Network is unreachable
  files.pythonhosted.org:443 -> OSError: [Errno 101] Network is unreachable
  astral.sh:443 -> OSError: [Errno 101] Network is unreachable
  archive.ubuntu.com:80 -> TCP OK
  cdn.playwright.dev:443 -> TCP OK
  100.64.0.27:18005 -> TCP OK          # 嵌入服务从容器内可达（运行期依赖满足）
```

## 1. 构建

| 次 | 结果 | 原始证据 |
|---|---|---|
| #1 | **挂死（失败）** | `RUN curl … astral.sh/uv/0.9.27/install.sh` 在容器内 8 分钟无输出、构建日志不再增长（脚本要从 GitHub release CDN 取二进制；容器出网白名单不放行，见 §0） |
| #2 | **失败** | 改用 PyPI：`python3.12 -m pip install uv==0.9.27` → `WARNING: Retrying … 'NewConnectionError … [Errno 101] Network is unreachable': /simple/uv/` |
| #3 | **成功** | `docker buildx build --load --network=host` + uv 从 PyPI 装 |

构建命令（终版即 `deploy/docker/build-image.sh` 的内容）：

```
docker buildx build --load --network=host \
  --file deploy/docker/Dockerfile --tag mirothinker-serving:v1 .
```

第一次以非 root 跑冒烟时抓到的真 bug（已修，见 README §12.2）：

```
$ docker run --rm --user 1004:1004 --entrypoint /bin/bash mirothinker-serving:v1 -lc 'cd /opt/mirothinker/apps/admin-console && uv run python -c "import sys"'
error: Failed to initialize cache at `/var/tmp/mirothinker-home/.cache/uv`
  Caused by: failed to open file `/var/tmp/mirothinker-home/.cache/uv/sdists-v9/.git`: Permission denied (os error 13)
```

修好后（终版镜像）的冒烟输出：

```
python deps: ok
chromium: /opt/ms-playwright/chromium-1208/chrome-linux64/chrome exists: True
uv 0.9.27
uv run ok: 3.12.3
```

### 1.1 最终 kit（`/var/tmp/mirothinker-docker-kit/`）

```
$ cat kit-manifest.txt
kit: mirothinker-serving (container 交付 v1)
built_at: 2026-09-21T16:31:18+08:00
commit: 36df47b84cdf115e982c3d6e16b6057d5dc66cab
image_tag: mirothinker-serving:v1
image_id: sha256:c72fd10ea157b66c0e706af227f4463098a15bbd8359e24a8aa887e76490f725
image_size_bytes: 4618248368          # 4.30 GiB
image_size_human: 4.4GB
build_seconds: 99                     # 增量构建（层缓存命中）
tar: mirothinker-serving-v1.tar
tar_bytes: 4690109440                 # 4.37 GiB
tar_sha256: 0164e3dcf78505a58fdab4016cd41e73dc7351014712281dcd9aaf26bf030fb2
tar_gz: mirothinker-serving-v1.tar.gz
tar_gz_bytes: 1507821271              # 1.40 GiB
tar_gz_sha256: a8bb532f6f5b10d1e71fc1558971ea85d90c67e4177d4b6881b85a9752c6bbd7
data_plane_not_included: serving-pack-run16-readerbound + index-v3-v2（约 7 GB，另行传输）
```

镜像 ID 与层一致性的对比（评审用）：

```
$ docker history --no-trunc --format '{{.ID}} {{.Size}}' mirothinker-serving:v1  # 8 层
$ diff <(…新镜像 8 层…) <(…演练镜像 2d1eaa1e 8 层…)
1c1            ← 只有第 1 行（image 自身的 ID）不同
```
⇒ 两次构建**层逐层相同**，image ID 因 config 的 `created` 时间戳不同而不同；
交付 tar 的 image ID（`c72fd10e`）与演练镜像 ID（`2d1eaa1e`）不相等属正常，内容层等价。

## 2. 演练编排（本目录的 `rehearse.sh`）

| 轮 | 镜像 ID | 受管配置 | 数据根 | 宿主机端口 | 启动耗时 | replay |
|---|---|---|---|---|---|---|
| ① | `2915c457` | 空（首启态） | rw | 18298 | **486 s** | 未跑到（驱动脚本 bug，见 §3.5） |
| ② | `2915c457` | 空（首启态） | rw | 18298 | **482 s** | **6/7**（G1 失败） |
| ③ | `2d1eaa1e` | live `settings.json` | rw | 18298 | **486 s** | **7/7 ALL PASS** |
| ④ | `2d1eaa1e` | live `settings.json` | **ro** | 18398 | 501 s（与③并行，受干扰） | 未跑 |
| ⑤ | `2d1eaa1e` | — | rw | — | — | uid 不匹配实验（§5） |

数据挂载（容器内即冻结绝对路径）：

| 宿主机 | 容器内 |
|---|---|
| `/var/tmp/mirothinker-docker-data-v2` | `/var/tmp/mirothinker-data-v2`（服务包 + 索引根 + 手工召回道） |
| `/var/tmp/mirothinker-docker-state-v1` | `/var/tmp/mirothinker-canonical-v2-s12f` |
| `/var/tmp/mirothinker-docker-kit/state/config-managed` | `/opt/mirothinker/config/managed` |
| `/var/tmp/mirothinker-docker-kit/secrets/.{deepseek,bocha,serper,sglang}_api_key`（指向 `/home/longxiang/MiroThinker/` 下同名真文件的**符号链接**） | `/opt/mirothinker/.{同名}`（只读） |
| `/var/tmp/mirothinker-docker-kit/state/logs` | `/opt/mirothinker/logs` |

容器内固定监听 18188；宿主机 `-p <port>:18188`。密钥从未被复制（只挂符号链接，容器只读引用）。

## 3. 演练 ①-③：主演练（数据根可写，uid=1004:1004）

### 3.1 启动相位（第③轮，`docker logs -t` 时间戳）

```
15:54:52.98  [entrypoint] 预检通过，交给冻结生产启动脚本：…/deploy/start-canonical-v2.sh
15:55:00.88  [canonical-v2] console_database=unconfigured            (+8 s)
15:59:59.62  candidate_release_id=candidate-v2-20260916-r1           (+5 min 7 s：包权限/校验/关系图)
15:59:59.62  serving_pack=/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound
15:59:59.63  fast_boot=0
16:02:51.29  [canonical-v2] console_database=unconfigured            (+7 min 59 s：索引/装配/管理面)
16:02:51.45  INFO:     Started server process [22]
16:02:51.46  INFO:     Application startup complete.
16:02:51.46  INFO:     Uvicorn running on http://0.0.0.0:18188
16:03:03     健康检查通过：boot_wall_clock=486s
```

> 容器内 18188 = 冻结命令文件钉死的端口；宿主机 18298 只是端口映射。
> 启动相位结束前端口不 bind ⇒ healthcheck 的 `start_period: 420s` 必须大于启动耗时。

### 3.2 探针（宿主机侧，发布端口 18298）

```
  host  /api/health  HTTP 200
  host  /chat        HTTP 200
  host  /main        HTTP 200
```

### 3.3 容器内 `mirothinker-verify`

```
== HTTP 探针 (http://127.0.0.1:18188) ==
  [OK]   /api/health -> HTTP 200
  [OK]   /chat -> HTTP 200
  [OK]   /main -> HTTP 200
== 嵌入端点探针（断言 HTTP 200 + 维度 4096）==
  [OK]   http://100.64.0.27:18005/v1 HTTP 200，维度 4096（model=Qwen/Qwen3-Embedding-8B）
== 内存 ==
  RSS 合计: 17.64 GiB
  cgroup memory.current: 17.82 GiB
== 结果：全通 ==
$ docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.MemPerc}}'
mirothinker-docker-rw-app-1 17.35GiB / 40GiB 43.37%
```

⇒ 与裸机活线同量级（活线 `ps` RSS 18 168 708 KiB = 17.32 GiB）。

### 3.4 一条真实问题过 `/api/chat/stream`（第③轮，带受管配置）

请求：容器内 `POST http://127.0.0.1:18188/api/chat/stream`，`{"query": "介绍一下 国际先进技术应用推进中心（深圳）"}`

```json
{
  "query_type": "canonical_v2:A:answer",
  "answer_len": 578,
  "citations": 6,
  "has_error_event": false,
  "events": {"stage": 3, "plan_done": 1, "progress": 5, "retrieval_done": 1,
             "answer_chunk": 575, "answer": 1, "done": 1},
  "answer_head": "国际先进技术应用推进中心（深圳）简称“国先中心（深圳）”，是在国家发展改革委、深圳市政府支持指导下设立…"
}
```

引用计数 6；SSE 里 `answer_chunk` 575 个（流式散文；降级路径不会出现这个事件序列，见 §3.6）。
原始 SSE 落盘：`docker compose exec app` 内 `/tmp/docker-rehearsal/`，并已复制到
`/var/tmp/mirothinker-docker-kit/state/logs/accept-rw/`（宿主机可见），证据副本见
`artifacts/`。

### 3.5 replay 回归门

第①②轮先踩了两个**驱动脚本**问题（不是镜像问题），修在 `rehearse.sh` 里：

1. `docker exec` 少了 `-i` ⇒ `python -` 读到空 stdin，探针静默无输出（已修）；
2. 任务书里那条 `cd apps/admin-console && uv run python scripts/replay_fix_round1.py` 在容器内
   **不可用**：它要求 admin-console 自己的 venv（其 `uv.lock` + dev 组），镜像刻意只带根 venv ⇒
   ```
   × Failed to download `pytest==9.0.3`
   ╰─▶ Network connectivity is disabled, but the requested data wasn't found in the cache for:
       `https://mirrors.sustech.edu.cn/pypi/web/packages/…/pytest-9.0.3-py3-none-any.whl`
   ```
   ⇒ 改用镜像内的 `mirothinker-replay`（同一脚本、同一断言，直接用 `/opt/mirothinker/.venv/bin/python`），
   等价写法 `cd /opt/mirothinker && uv run --frozen python apps/admin-console/scripts/replay_fix_round1.py`
   也已实测可用（离线）。

第②轮（受管配置为空）结果 —— **6/7**：

```
RESULT: 1 FAILURE(S)
  G1_framing: FAIL
  G2_bare_name: PASS    G3_person_pronoun: PASS    G4_patents: PASS
  G5_expansion: PASS    G6_anaphoric_opener: PASS  G7_enumeration: PASS
```

失败条目（`report.json`）：

```
session G1_framing / turn 3 「它有哪些布局和进展」/ 16.4 s / canonical_v2:A:answer
failures: ['subject not in first sentence: 国际先进技术应用推进中心']
answer_head: （以下为基于本地数据的简要信息）\n- 深圳国际先进技术应用推进中心；简介：…
```

第③轮（把 live 的 `config/managed/settings.json` 放进受管配置目录，其中 `serving.chat_llm_profile` 非空）
—— **7/7 全过**（16:23:15 → 16:26:04，169 s）：

```
RESULT: ALL PASS
  G1_framing: PASS   G2_bare_name: PASS   G3_person_pronoun: PASS   G4_patents: PASS
  G5_expansion: PASS G6_anaphoric_opener: PASS  G7_enumeration: PASS
```

### 3.6 两次结果的差别（机制，已用原始 SSE 验证）

失败那轮的 `G1_framing_r1_t3.sse`（已留档 `artifacts/G1_framing_r1_t3-failed.sse`）里，
`answer` 事件的 `answer_text` 以 `（以下为基于本地数据的简要信息）` 开头并带换行，
而断言取的是「第一句」（按 `。！？\n` 切分）⇒ 第一句只有那行降级提示。

⇒ 结论（对交付的含义）：**受管配置为空时答案走降级渲染路径**，
replay 门会红在 G1；把 `/admin` 该配的东西配上（P3 步骤）后门即全过。
这不是容器引入的问题（裸机同样依赖受管配置），但容器首启默认是空配置，更容易撞上。

## 4. 演练 ④：数据根只读挂载（`:ro`）

```
$ MIROTHINKER_HOST_PORT=18398 .agents/runs/delivery-docker/rehearse.sh ro
[entrypoint] 注意：/var/tmp/mirothinker-data-v2 不可写 —— 服务仍会正常启动，但无法写 mount-receipt，
[entrypoint]       每次启动都会重新全量哈希服务包与索引。要拿到 receipt 快路径：
[entrypoint]       把该目录改成可写，或指定 CANONICAL_V2_SERVING_RECEIPT_PATH 到可写路径。
[entrypoint] 预检通过，交给冻结生产启动脚本：…
…（启动相位正常走完）…
serving pack mount receipt could not be written: /var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound.mount-receipt.json
candidate_release_id=candidate-v2-20260916-r1
serving_pack=/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound
[16:23:23] 只读数据根：启动成功，boot_wall_clock=501s
INFO:     172.17.0.1:47532 - "GET /api/health HTTP/1.1" 200 OK
```

- **结论：只读挂载不会让启动失败**（与任务书的初始假设相反；与代码阅读一致：
  `_write_mount_receipt` 捕获 OSError 只打 warning，`serving_pack_loader.py:404-414`）。
- 代价 = 每次启动全量重新哈希；本次对照（rw）486 s vs（ro）501 s —— 差异里还混入了
  「两轮启动并行」的干扰，**不应**据此断言代价大小。
- receipt 文件未被改动：`/var/tmp/mirothinker-docker-data-v2/…mount-receipt.json` 的 mtime
  仍是 rw 启动写的 16:20。

## 5. 演练 ⑤：uid 不匹配（权限问题的真实症状）

入口预检（正常路径，退出码 78）：

```
$ .agents/runs/delivery-docker/rehearse.sh wronguid      # --user 405:405，数据属主 1004
[entrypoint] 预检失败：读不到 /var/tmp/mirothinker-data-v2/index-v3-v2/.canonical-v2-isolated-index-target.json（存在性/权限）：
    容器内 uid=405，而该文件的属主是 1004:1004（父目录）。
    一行修复：在 compose 里设 user: "${MIROTHINKER_UID}:…" = 数据属主的 uid:gid，
    或先在宿主机 chown 数据目录到容器用户。
容器状态：exited exit=78
```

绕过预检（`MIROTHINKER_SKIP_PREFLIGHT=1 --user 405:405`）后，**服务自己**的两条原文：

```
# 场景 A：服务包目录不可读（chmod 700）
PermissionError: [Errno 13] Permission denied: '/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound/manifest.json'
complete candidate runner failed: PermissionError: [Errno 13] Permission denied: '…/manifest.json'
→ exited exit=2

# 场景 B：服务包可读、索引根不可读（现状：pack 775 / index 700）
PermissionError: [Errno 13] Permission denied: '/var/tmp/mirothinker-data-v2/index-v3-v2/.canonical-v2-isolated-index-target.json'
complete candidate runner failed: PermissionError: [Errno 13] Permission denied: '…/.canonical-v2-isolated-index-target.json'
→ exited exit=2
```

⇒ **订正**：`current-state.md` §2.5 原按代码阅读预测是 `… is missing or unsafe: manifest.json`。
实测不是 —— 本机 Python 3.12.3 下 `Path.is_file()` 对 EACCES **抛异常**而不是返回 False
（容器内实测：`file.is_file() -> PermissionError: [Errno 13] …`），所以看到的是原生 traceback
+ `complete candidate runner failed: PermissionError`。README §3 的表已按实测改写。
唯一的坑是「这看起来像崩溃而不是配置问题」，入口预检负责把它翻译成人话。

## 6. 收尾与未触碰项

- 演练容器全部 `docker compose down` / `docker rm`（数据与状态目录保留在宿主机）。
- 活线：`ps -o pid,rss,etime -p 519941` → pid 519941、RSS 18 168 708 KiB、未重启。
- 活线数据/状态目录未被写入：
  ```
  /var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound.mount-receipt.json  mtime 2026-09-21 02:12:56
  /var/tmp/mirothinker-canonical-v2-s12f/admin-initial-password.txt               mtime 2026-09-17 22:41:23
  ```
- 未触碰：`.worktrees/{canonical-v2-s11-consolidation,collection-line,data-rebuild,embedding-lane-f1f2}`、
  `/var/tmp/mirothinker-delivery-kit/`（另一路演练产物）。
  对 `.worktrees/data-rebuild` 只做了**只读**访问：`cp` 出两个账本小文件（4 K/0.3 K，非机密）。
- 演练用的数据面是活线数据面的**逐字节副本**（`/var/tmp/mirothinker-docker-data-v2`）：
  - 逐文件尺寸一致（manifest/lookup/relationships/catalog/marker 全部 OK）；
  - **内容一致由服务侧证明**：第①轮首启做了全量校验（无 receipt 路径）并成功
    （任何字节差异都会 fail-closed）—— 校验通过后才写出 receipt。

## 7. 口径与局限（别过度解读）

1. **启动 486 s vs 裸机 291 s**：291 s 出自 `docs/plans/2026-09-18-collection-line-log.md:1274`
   （「活线重启实测 421 s → 291 s」，重封 readerbound 包之后）。两者口径需要对齐：
   本次容器实测三次都是 482–486 s（无其它负载时 load average 2.3），且 receipt 有无只差 4 s
   ⇒ 差异不在 receipt。**必须与另一路（裸机）演练在同一台机器上背靠背对比后再下结论**，
   否则会误判成「容器慢」。已知的可能来源：容器 vs 宿主的文件系统路径（代码/venv 走 overlayfs）、
   `uv run` 的启动开销、当时机器的竞争负载；本次未能排除。
2. **构建耗时**：`build_seconds: 99` 是**增量构建**（BuildKit 命中缓存层）。全新构建未单独测，
   README §10 给出的 5–8 min 是按分层实测的估算，不是测量值。
3. **镜像 ID 不可复现**：层等价、ID 不等（§1.1）。以 tar 为准。
4. **未覆盖**：PostgreSQL（本次不装，`console_database=unconfigured`，`/seeds` `/upload` 相应降级）；
   管理面登录/改密的人工点击（首启口令文件已确认生成在状态目录）；并发/压测；
   Chromium tier-1 抓取的功能级验证（只验证了浏览器可执行文件存在于全局可读路径）。
5. **只读挂载的代价**未单独测量（见 §4 说明）；`CANONICAL_V2_SERVING_RECEIPT_PATH` 这条替代
   路径本次只做了代码定位，未实测。

---

# 追加：PostgreSQL 进栈（Task A）与启动耗时归因（Task B）

## 状态块（as of 2026-09-21T18:45+08:00）

- **commits**：`9ea3a931`（容器路径 v1）→ **`6216c5d7`**（PG 进栈 + 归因 + 解释器版本修复）。
- **done（已实测）**：
  - Task A：PG 进 compose 栈，`console_database=configured`；登录/采集面/`pg_dump`+restore
    行数对账/`/admin` 面板/`down`+`up` 幂等与持久化 —— 全部有原始数字（见下）；
  - Task B：同机同数据根背靠背归因完成并**修复**——根因是解释器补丁版本；
    容器启动 466 s → **276 s**（裸机 275 s），digest 与包记录逐字节一致。
- **not done（未验）**：
  - `bind mount` 版 pgdata（我只验了具名卷；bind 需要 `chown 999:999`，症状表里是代码侧推断）；
  - 中断前后的最后一轮"最终镜像快速确认"在跑（本文件末尾会补一段确认输出）；
  - `--env-file` 分支（我的设计不依赖它，未实测）；
  - 203/8 进程级并发、PG 备份的物理卷还原、pg_upgrade 路径。
- **next command（接手者第一条）**：
  ```bash
  cd /home/longxiang/MiroThinker/.worktrees/delivery-docker
  .agents/runs/delivery-docker/rehearse-pg.sh up     # 起栈（含 PG）→ 自动跑验收
  .agents/runs/delivery-docker/rehearse-pg.sh restart # 幂等 + 持久化复验
  ```
  原始日志都在 `/var/tmp/mirothinker-docker-logs/`（pg-acceptance*.json、pg-dump.sql、
  pg-restore-check.log、attribution-*.log、boot-timing-*.jsonl）。

## Task A · PG 验收（镜像 `09f0a1c4` 上完成；最终镜像 `b4efc4bd` 只差解释器/pyc）

组合：`docker compose -p mirothinker-docker-pg -f <kit>/compose.yaml`，端口 18298，
uid 1004:1004，pgdata 走具名卷 `mirothinker-pgdata-rehearsal`，凭据 `secrets/postgres.env`（0600，未入 git）。

| 验收项 | 结果（原始） |
|---|---|
| db 健康 | `healthy`（up + 2 s） |
| 迁移（首次，空库） | `{"head": "V042", "revision": "V042", "revision_before": "", "tables": 42, "waited_seconds": 0.196}` |
| 迁移（二次） | `{"revision_before": "V042", "revision": "V042", "tables": 42}` ⇒ 幂等 |
| 迁移（三次，restart 后） | `{"revision_before": "V042", "revision": "V042", "tables": 42, "waited_seconds": 0.075}` |
| 库身份标记 | `identity marker ok (miroflow:destructive-target:v1:disposable:miroflow_collection_v1)` |
| app 启动（带 PG + 迁移） | **479 s**（首次）/ **481 s**（restart 轮）——与无 PG 的 482–486 s 同档，迁移 ≈0.2 s 不进关键路径 |
| `console_database` | `[canonical-v2] console_database=configured`（原来是 `unconfigured`） |
| 登录 | `POST /api/auth/login` → **200**；`GET /api/auth/me` → 200 `{username: admin, role: admin}` |
| 页面 | `/seeds` `/upload` `/jobs` `/browse` `/logs` `/admin` 全 **200** |
| 采集面 API | `seeds` 200（决策前 `list[0]`）；`uploads` 200（`postgres: {available: true, source: "DATABASE_URL"}`，3 个域）；`jobs` 200（storage available） |
| **preview 采集（第 1 次触发）** | 202 → run `failed`，1.2 s，`seed_status: adapter_missing`（我用的是 `sz.gov.cn`，没有对应 school adapter）⇒ **web_search 配额花费 0** |
| **preview 采集（第 2 次触发，唯一一次真跑）** | 202 → run `succeeded`，**443 s**，`items_processed=1 / items_failed=0`，`seed_status=success`；`run_scope`: `run_kind=roster_crawl`、`trigger_mode=preview`、`written_profile_count=0`、`diagnostic_profile_count=995`（预演模式 = 抓取+抽取但不落库） |
| 页面抓取量（quota 代理指标） | `logs/debug/professor_fetch_cache` 新增 **996** 个文件（995 个画像 + 1 个名录页）；Bocha/Serper 的 API 调用数**没有可读计数器**（作业 summary 只记配额上限 200/500），按抓取缓存与 `run_kind=roster_crawl` 判断本次以直连抓取为主 |
| `/jobs` 有 run 行 | `GET /api/canonical-v2/admin/jobs` 200；`pipeline_run` 3 行（1 条迁移内建占位行 + 1 failed + 1 succeeded） |
| `/admin` 面板（原 `unavailable`） | `GET /api/canonical-v2/admin/system-status` 200：`freshness.state=ok`（`pack_build_age_seconds=414619`，`per_domain.company.record_count=7086`…）、`collection={enabled:{company,paper,patent,professor}, max_web_searches_per_run:200, max_llm_calls_per_run:500}` |
| `pg_dump` | **114 871 B**（`pg_dump --no-owner --no-acl`，从 db 容器内出，5432 不暴露宿主） |
| restore 对账 | 灌到 `miroflow_collection_restorecheck`：`tables 42/42`、`professor_seed 2/2`、`pipeline_run 3/3`、`seed_registry 0/0`、`alembic V042/V042`、`run_digest md5=60dcca3404018ad4156348278aa679e4` 两侧相同；**42 张表逐表行数 diff 全等** |
| `down` + `up` | 迁移幂等（见上）+ 数据仍在：`professor_seed=2 pipeline_run=3`（具名卷 `mirothinker-pgdata-rehearsal` 保留） |

复现命令（每次都会重新跑一遍迁移，是幂等的）：

```bash
cd <kit 目录>
export MIROTHINKER_DATA_ROOT=/var/tmp/mirothinker-docker-data-v2 \
       MIROTHINKER_STATE_DIR=/var/tmp/mirothinker-docker-state-v1 \
       MIROTHINKER_SECRETS_DIR=./secrets MIROTHINKER_MANAGED_DIR=./state/config-managed \
       MIROTHINKER_LOG_DIR=./state/logs MIROTHINKER_UID=1004 MIROTHINKER_GID=1004 \
       MIROTHINKER_HOST_PORT=18298 MIROTHINKER_PG_ENV_FILE=./secrets/postgres.env
docker compose up -d
docker compose exec -T app mirothinker-migrate --status
```

## Task B · 启动耗时归因（同机、同数据根、背靠背、热缓存）

条件：两侧都读**同一个宿主目录** `/var/tmp/mirothinker-data-v2`（容器 `:ro` 挂到冻结路径），
都用**同一份预热 receipt**（`CANONICAL_V2_SERVING_RECEIPT_PATH` 指向 scratch，pack_dir 相同故可绑定），
都开 `CANONICAL_V2_SERVING_TIMING_PATH`，启动前各自 `cat` 6.5 GB 数据进页缓存（实测 1 s = 本来就在缓存里）。

| 轮 | 环境 | 数据根 | receipt | 启动（up→/api/health 200） |
|---|---|---|---|---|
| ① | 裸机（3.12.12，本 worktree 的 .venv，ext4） | live 根 | 预热 | **275 s** |
| ② | 容器（3.12.3 = Ubuntu 24.04 自带） | live 根 :ro | 同一份 | **466 s** |
| ③ | 容器（3.12.3 + 预编译字节码） | live 根 :ro | 同一份 | **466 s**（pyc 不是主因） |
| ④ | 容器（**3.12.12**，与封印解释器一致） | live 根 :ro | 同一份 | **276 s** ✅ |
| （对照） | 容器（3.12.3，早前轮次） | **数据副本** | — | 482–486 s（与 ② 同档 ⇒ 副本不是主因） |

相位（`boot-timing-*.jsonl`，单位 s）：

| 相位 | 裸机 ① | 容器 ②（3.12.3） |
|---|---|---|
| pack.mount_identity | 0.000 | 0.000 |
| pack.mount（receipt_used） | True | True |
| pack.relationships_read | 37.714 | 28.655 |
| snapshot.lookup_docs / lookup_points | 16.432 / 1.920 | 16.009 / 2.012 |
| snapshot.open | 19.828 | 19.628 |
| bound_documents.read | 6.168 | 6.732 |
| vector.snapshot.open / npz_load / index_build | 4.992 / 1.341 / 5.680 | 5.075 / 1.290 / 5.545 |
| **命名相位合计** | **94.1** | **84.9** |
| **未记账段（>5 s 间隙求和）** | **120.1** | **305.4** |
| 其中最大一段（snapshot.open → bound_documents.read） | 59.3 | **239.0** |

⇒ 数据面读路径**两侧一致**（容器甚至略快）；差异 100% 在未记账段。

定性证据链：
1. **原始 CPU/内存基准两侧相同**：纯 python 循环 0.578 vs 0.633 s；json 300k dicts 0.911 vs 0.969 s；
   分配+触碰 2 GB 1.120 vs 1.119 s；sha256 256 MB 0.269 vs 0.270 s；numpy matmul 0.030 vs 0.030 s。
2. **Chromium 启动**（tier-1 抓取）：容器 0.60 s / 裸机 0.50 s；`--shm-size` 无影响。
3. **出网**：6 个 provider/LLM 主机（deepseek/bocha/serper/star.sustech/dashscope/ark）在容器与宿主机都通 ⇒ 不是网络等待。
4. **SIGABRT + `PYTHONFAULTHANDLER=1` 抓栈**：卡点在
   `serving_pack_loader.py:1021 open_serving_pack_authority` → `_canonical_sha256`（整张对象图重放）。
5. **摘要对账（决定性，逐字节）**：
   - 包 manifest 记录：`reader_contract_sha256 = ebc22047cc9bef912201da5292809935c619705a2b8d8eb718cfec081b0da362`
   - 裸机（3.12.12）：`ebc22047…` **相同** ⇒ 跳过重放；
   - 容器（3.12.3）：`8b4b69de…` **不同** ⇒ 每次启动重放 ≈190 s；
   - `reader_contract_digest()` 的实现：`sha256(python=3.12.x + pydantic 版本 + canonical_v2 包的 .py 字节)`
     —— 补丁版本进摘要，所以 3.12.3 与 3.12.12 不等。
6. **修复后**：容器 `reader_contract_digest == ebc22047…`（逐字节一致），启动 **276 s**。

**结论（写进 runbook 的口径）**：容器与裸机在**同数据根**下应当给出同档启动时间
（本机 275–276 s；带 PG 迁移的 compose 启动 479–481 s 是另一件事——那是首次带迁移的完整栈）。
前提是**镜像解释器 = 封印该包的解释器补丁版本（当前 3.12.12）**；不满足时会静默多花 ≈190 s
（不会报错、不会拒载，只是"变慢"）—— 这是本切片发现的最有价值的一条交付契约，
两条交付路径都要钉住解释器版本。

## Task A · 最终镜像（`b4efc4bd`）上的快速确认

目的：证明**最终镜像**（解释器改成 3.12.12 + pyc 预编译后）与上一轮验收镜像在采集面上行为一致；
本轮**没有再触发采集**（沿用既有的 run 行）。命令与原始输出：

```bash
# 起栈（compose：app + postgres:16，端口 18298，pgdata 具名卷 mirothinker-pgdata-rehearsal）
.agents/runs/delivery-docker/rehearse-pg.sh up
python3 .agents/runs/delivery-docker/pg_confirm.py 18298 /var/tmp/mirothinker-docker-state-v1 \
        /var/tmp/mirothinker-docker-logs/pg-confirm-final.json
```

```
迁移（本次启动）：{"head": "V042", "revision": "V042", "revision_before": "V042", "tables": 42, "waited_seconds": 0.075}
[canonical-v2] console_database=configured
登录 200（admin/admin）；页面 /seeds /upload /jobs /admin 全 200
4 个 admin API 全 200；uploads.postgres = {"available": true, "source": "DATABASE_URL"}
既有 preview run（job run e9fbc5ce…）= succeeded，444 275 ms（/jobs 能看到这一跑）
/admin 面板：state=ok、freshness=ok、collection.enabled={company,paper,patent,professor}
pg_dump 116 484 B → 灌进 miroflow_collection_restorecheck → ALL 42 TABLES MATCH
  非空表：alembic_version=1、professor_seed=3、pipeline_run=4、pipeline_issue=2
```

### preview 触发与配额账（如实记录）

| # | 触发时间 | seed | 结果 | 花费 |
|---|---|---|---|---|
| 1 | 17:03 | 1 · `sz.gov.cn` | `failed`，1.2 s，`adapter_missing`（无匹配 school adapter） | 0（未抓取） |
| 2 | 17:06 | 2 · `sustech.edu.cn/zh/letter` | **`succeeded`，443 s**，`diagnostic_profile_count=995`、`written_profile_count=0` | 996 次页面抓取（995 画像 + 1 名录页）；Bocha/Serper 无可读计数器 |
| 3 | 18:41 | 4 · `szu.edu.cn/szdw` | `failed`，≈1 s，`parser_low_quality: no_professor_entries_found` | 0（页面未解析出条目） |
| 4 | （本轮确认） | — | **未触发** | 0 |

> 第 3 次是**驱动脚本自己的**问题：18:37 那轮 `rehearse-pg.sh up` 在健康后会再跑一遍
> `pg_acceptance.py`，它按候选列表新建 seed 并触发一次 preview；该脚本没有"已有 seed 就跳过"
> 的守卫（`pg_confirm.py` 才是本轮用的只读确认脚本）。**这是本切片的一个已知粗糙点**，
> 建议下一步给 `pg_acceptance.py` 加 `--no-trigger` 或复用已有 seed。
