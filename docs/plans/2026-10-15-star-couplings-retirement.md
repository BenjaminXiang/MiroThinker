# star 域名耦合安全退役（计划）

> 2026-10-15 立项。Agent 侧契约：`openspec/changes/retire-star-domain-couplings/`；
> 执行明细见 [日志](./2026-10-15-star-couplings-retirement-log.md)；索引见 [index](./index.md)。
> 本文件回答：**退役什么、为什么、怎么算退干净、怎么回滚**。

## 0. 一句话结论（立项时的现状）

两个域名的耦合是两个方向同时存在的：**我们调用 star 的模型服务**（今天已无在用，只剩休眠默认值）
与 **star 域名后面挂着我们的入口**（`/guoxian` → dbg21 → gpu01:18188，仍在服务，仅剩扫描器流量）。

**关键发现（2026-10-15 实测）**：`star.sustech.edu.cn` 的后端就是 **dbg21（100.64.0.34）这台
我们能管的 nginx**（校网关 172.18.24.245 → dbg21:3001）：它同时承载 star 的模型路径
（`qwen36`/`embedding`/`rerank` → 校园模型机 `172.18.41.222`）、我们的 `/guoxian` 入口，
以及若干非本项目应用（`/zs-ai`、`/major-ai`、`/sucai` …）。

## 1. 谁在用（退役窗口的依据）

| 对象 | 10-01~11 | 10-12 | 10-13 | 10-14 | 10-15（今天） |
|---|---|---|---|---|---|
| star 模型路径（次/天） | 418–456，**24h 均匀** | 157 | 45 | 29 | **3（只读探针）** |
| 我们的 `/guoxian` | 2–31/天（含安全扫描器） | 22 | 22 | 0 | 3（只读探针） |

- 模型流量归因：均匀节律 ↔ 客户**旧线 run-9** 的 keepwarm（144 轮/天）；其冻结嵌入包
  `base_url` 就是 star、`run.sh` 的 hedge 默认 `gemma4`（注释写明 "star 网关"）；
  run-9 `serve.log` 停在 **10-12 16:41**，与断崖时间吻合。
- 未完全归因：10-13/14 残余 45/29 次（含 `/service/model/mirothinker/*` 探针）——
  dbg21 只记到网关 IP，**已列为向校网关方索取客户端 IP 的核对项**。
- 两个在跑的服务线（gpu01:18188 / 100.64.0.96:18188）**实测零 star 调用**：一轮真实提问的
  出站只有 DeepSeek / Serper / Bocha（+ 本机）；目标机 3.5 分钟被动抓包同样为 0。

## 2. 用户决策（2026-10-15）

| # | 问题 | 决定 |
|---|---|---|
| D1 | 范围 | **只退我们的耦合**；不碰校园模型机（172.18.41.222 / 100.64.0.27）与 dbg21 上其它项目 |
| D2 | 入口 `/guoxian` | **与校方约时间后摘**；今天只登记 + 备好一键脚本 |
| D3 | 目标机旧线 run-9 | **随 star 一起退役**（删 shim + 文档登记旧线不再可用） |
| D4 | 本机休眠默认值 | **改默认值 + 回归测试**（走 OpenSpec change） |

## 3. 改动清单

### 3.1 本机（gpu01）默认值 —— 同模型、去 star、零行为变化

| 文件 | 改前 | 改后 |
|---|---|---|
| `professor/llm_profiles.py`（gemma4 档） | `https://star.sustech.edu.cn/service/model/qwen36/v1` | `http://100.64.0.27:1231/v1`（实测同一模型 `qwen3.6-35b-a3b`） |
| `providers/rerank.py` | star `rerank/v1` | `http://100.64.0.27:18006` |
| `scripts/run_professor_enrichment_v2_e2e.py` | 默认档 `qwen35`（star 路径**已是死路**，返回 HTML） | 默认档 `gemma4`（= 自建机） |
| `deploy/preflight.sh`（s11 树，kit 探针回落） | star `qwen36/v1` | `http://100.64.0.27:1231/v1` |

一处改、全局收口：12 个采集/种子脚本、`ADMIN_SEED_LLM_PUBLICATION_PROFILE`、月度
`miroflow-medium-rescan` guard 的默认值都经 `gemma4` 档解析 ⇒ 全部随之离开 star。
**改动不落在 `canonical_v2/*.py`** ⇒ 封印包的 reader 指纹不变（**不需要重封**、不触发慢启动）。

### 3.2 目标机（100.64.0.96）

- 禁用 `miro-embed-shim.conf`（监听 `100.64.0.27:18005` → star embedding；**从上线至今 0 次请求**）
  与死配置 `gxzx-origin-map.conf`：带时间戳备份 → `nginx -t` → reload → 三方验证。
- run-9 线（disabled）随 star 退役：其冻结嵌入包 = star、hedge = gemma4，**不再作为可用回滚线**，
  交付文档登记。

### 3.3 登记（不执行）

- `deploy/retire-star-entry.sh`：dbg21 `/guoxian` 一键摘除（备份 → 删 6 个 location 块 →
  `nginx -t` → reload → 三方验证 + 回滚指令）。按 D2，等校方日期再跑。
- `deploy/README.md`：入口段落标注"退役中（等校方日期）"。

## 4. 验收（详见 acceptance.md）

- 新增守卫测试**先红后绿**：gemma4/rerank/脚本默认档全部非 star；star 档案allowlist =
  `{qwen35, mirothinker, ark}`（三者非任何默认值）。
- 相邻套件绿：`test_llm_profiles` / `test_rerank` / `test_canonical_v2_runtime_sources` / seeds 面。
- 新进程实测：`gemma4 → http://100.64.0.27:1231/v1`、`rerank → …:18006`。
- 目标机：`18005` 无监听、`nginx -T` 无 star、站点 health/chat 200。
- `git diff` 零 `canonical_v2` 改动。

## 5. 回滚

- 本机：还原 5 个文件的 diff（或保留改动、把 gemma4 指回 star）。
- 目标机：`mv miro-embed-shim.conf.disabled-20261015 miro-embed-shim.conf && nginx -t && systemctl reload nginx`。
- dbg21：脚本自带 `cp -a` 备份与一行回滚命令。

## 6. 遗留 / 待办（不含在本次改动内）

| # | 项 | 触发条件 |
|---|---|---|
| L1 | `qwen35` / `mirothinker` / `ark.local` 三个档位仍指 star（**无自建等价端点、且非任何默认值**） | 校方给出关闭日期后重指或删除；allowlist 测试定义目标集合 |
| L2 | `canonical_v2/*.py` 里 `CHAT_LLM_PROFILE` 回落常量 `gemma4`（6 处） | 随下一次重封顺带改（改它必须重封，否则每次启动慢 137–190 s） |
| L3 | star 网关侧 `/guoxian` 规则、gpu01 防火墙对 100.64.0.34 的放行 | 与校方摘入口同一天 |
| L4 | 10-13/14 残余 45/29 次模型请求的客户端归属 | 校网关方提供客户端 IP 后核对 |
| L5 | 校园模型机（172.18.41.222 / 100.64.0.27）本身的寿命 | 不在本范围；一旦校方也要退它，本机 legacy 路径（rerank 默认、采集脚本、preflight）与目标机 shim 均需再评估 |
| L6 | **目标机代码树**里同一组默认值（12 个文件含 star 引用；本轮只改了本机两棵活线树） | 目标机无 `.sglang_api_key` 且采集从未跑过 ⇒ 当前无可达路径；下次给目标机打代码补丁时一并同步（同 5 个文件 + 2 个测试） |

## 7. 已知取舍

- 目标机的 run-9 回滚线**不再可用**（其嵌入 = star）。这是 D3 的直接代价；v2 线已过
  replay 7/7 + 8 题时延/准确率验收，回滚到 v2 的上一个包仍可行，回滚到 run-9 不可行。
- 本机缓存中的旧默认值：**运行中的进程要等下一次重启**才加载新代码；由于这些路径全部休眠，
  行为无差异（新默认值由测试 + 新进程实测证明）。如要立刻生效，重启 18188 即可（约 5 分钟停机）。
  **（第 2 轮已执行：19:36 重启，290 s 起来，health/chat 200，star 入口 200，重启后一轮真问 star=0。）**
- 目标机旧线（唯一持有 star 密钥、且代码/包指向 star 的资产）：**第 2 轮已做防呆**——密钥改名
  `.disabled-20261015`、unit 挂 `/dev/null` mask（`systemctl start` 实测被拒），v2 线不受影响。
