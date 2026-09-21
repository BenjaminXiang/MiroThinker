# 命题 1 · `--force-recreate` 的反向实验（判决性）

**判定：原结论"只 restart 不够、必须 `up -d --force-recreate`"被实测**推翻**——
容器**重启**（`docker compose restart app`）就会按**路径**重新建立 bind mount ⇒
换 key 文件后 `restart` 足够；`--force-recreate` 不是必须的。**
（同时实测出：文档给的操作命令本身会引入 root 属主 —— 比 inode 更会咬人的坑，见 D3/D7。）

## 实验设计（全部结论都有观测量，不靠推理）

容器内 `/opt/mirothinker/.sglang_api_key` 是宿主 `secrets/.sglang_api_key` 的只读 bind。
三个观测量：

| 观测 | 手段 | 说明 |
|---|---|---|
| 文件级：容器**当前**看到的字节 | `docker compose exec -T app sha256sum /opt/mirothinker/.sglang_api_key`（只取前 12 位） | `Permission denied` 也是信息（说明挂的是新文件、但属主不对） |
| 文件级：宿主 | `sudo sha256sum` + `stat -c %i`（inode） | 确认"文档命令"到底换不换 inode |
| 功能级：服务真的用哪份凭据 | 管理员连接测试 `POST /api/canonical-v2/admin/connections/test {"connection":"embedding"}` | 响应里带 `api_key_source` / `http_status`；换错 key 时端点回 401 |

## 实测（原始输出在 `raw/03-force-recreate.log`，逐段 JSON 在 `raw/03-*.json`）

**A. 基线（01:27:41）**

```
host: inode=22576207157 hash=0ed2420f3164
container hash=0ed2420f3164
连接测试：ok=true, http_status=200, latency_ms=29, api_key_source=legacy-file:.sglang_api_key
```

**B. 用**文档原文**命令换成一个故意错的 key**

```bash
printf 'deliberately-wrong-key-for-inode-experiment\n' | sudo install -m 600 /dev/stdin secrets/.sglang_api_key
```

```
host: inode 22576207157 -> 22578793892  (inode 变了)
host: hash=3a8e2874223c（= 新内容）
B1 运行中的容器（未重启）看到的：hash=0ed2420f3164     ← 挂载仍绑在**旧 inode**：容器看到的是旧内容
B2 docker compose restart app（01:27:41）→ health OK after 281s
   重启后容器内看到的：sha256sum: /opt/mirothinker/.sglang_api_key: Permission denied   ← 已经是**新文件**了
B3 连接测试：ok=false, http_status=401, api_key_source=none,
   runtime_note=「运行期不可用：本地凭据缺失（API_KEY/OPENAI_API_KEY/SGLANG_API_KEY/.sglang_api_key 全空）」
```

逐步对照：

| 步骤 | 容器看到的文件 | 服务用的凭据 | 结论 |
|---|---|---|---|
| 换文件后、**未重启** | 旧 inode 的字节（`0ed2420f…`） | 旧 key（服务只在启动时读一次） | bind 绑 inode：**不重启，容器看不到新文件** |
| `docker compose restart app` 之后 | **新文件**（`Permission denied`：新文件是 `sudo install` 造的 root:root 0600） | **旧 key 已不在**（`api_key_source=none`，401） | **restart 已经让容器改挂到新文件** ⇒ "只 restart 不够"不成立 |

关键点：`restart` 前后**没有任何 `--force-recreate`**，而容器看到的文件从"旧 inode"变成了"新文件"，
功能级也从 200 变成 401 —— 这就是"restart 够不够"的**判决性观测**。

**C. `mv`（真换 inode）+ `--force-recreate`（对照）**

```
host: inode 22578793892 -> 21896584924  (mv 换了 inode)
C1 运行中的容器（未重启）看到的：Permission denied（旧 inode 的内容已不可读；仍是旧文件）
C2 docker compose up -d --force-recreate app → 容器内 hash=Permission denied（= 新文件，但 root 属主）
```

`--force-recreate` 当然也能让容器看到新文件（等价结论），但**不是必要条件**。

**D. 复原**：`sudo install -m 600 <真 key> secrets/.sglang_api_key` + `up -d --force-recreate app`
（这一步暴露了 **D7**：文档命令把 key 写成 root:root 0600 ⇒ 容器 uid 1004 读不到 ⇒ 复原后
连接测试仍是 401/凭据缺失；补一次 `chown 1004:1004` 后**只 `restart`** 即恢复
`ok:true / 200 / api_key_source=legacy-file:.sglang_api_key`，且 restart 后容器内 hash 立刻
等于宿主 hash —— `raw/03b-restore.log`。）

## 结论（对文档的动作）

1. `CONFIG-GUIDE.md §3`「换 key 之后怎么生效」里的
   “**文件方式**：要 `docker compose up -d --force-recreate app` —— **只 restart 不够**”
   **与实测不符**。实测：`docker compose restart app` 就会重新按路径挂载新文件并生效。
   ⇒ 文档改为 `docker compose restart app`（同等启动耗时 ≈280 s，且不动容器本体）。
2. 真正会让"换了 key 却没用"的**不是** inode，而是**属主**：
   `sudo install -m 600 /dev/stdin …` 造出来的文件是 `root:root 0600`，容器里 uid=数据属主
   （本机 1004）**读不到**——服务把凭据当"缺失"（`api_key_source=none`）。
   ⇒ 文档必须补一句：后补/更换 key 之后要么重跑一次 `sudo ./install-site.sh`
   （它会把属主归一给数据属主，见 D3 的修复），要么 `sudo chown <数据属主> secrets/.*_api_key`。
3. `--force-recreate` 仍可保留为"保险做法"，但不应再写成"必须"。
