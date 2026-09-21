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
