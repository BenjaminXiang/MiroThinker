# star 域名耦合安全退役 · 执行日志（只追加）

> 计划在 [退役计划](./2026-10-15-star-couplings-retirement.md)；本文件只记"实际做了什么、发现了什么、怎么验证的"。
> 每轮一条，不改历史条目。

---

## 第 1 轮 · 2026-10-15 · 本机默认值去 star（同模型换自建端点）+ 目标机 shim 退役；入口按约定只登记

**背景**：用户判定"有关 star 这个域名的服务要安全退役"。先做了全链路取证（见计划 §1），
再按用户四项决策（计划 §2）执行本轮。

**做了什么（三条线）**：

1. **本机（gpu01）休眠默认值收口**（测试先行：守卫测试 4 红 → 改 3 个文件 → 全绿）：
   - `llm_profiles.py`：`gemma4` 档本地端点 star → `http://100.64.0.27:1231/v1`（**实测同一模型
     `qwen3.6-35b-a3b`**）。一处改，12 个采集/种子脚本 + `ADMIN_SEED_LLM_PUBLICATION_PROFILE`
     + 月度 `miroflow-medium-rescan` guard 的默认值全部离开 star。
   - `providers/rerank.py`：默认 URL star → `http://100.64.0.27:18006`（`POST /rerank` 探到 400
     = 路由存在）。
   - `scripts/run_professor_enrichment_v2_e2e.py`：默认档 `qwen35`（其 star 路径**已是死路**）→ `gemma4`。
   - `deploy/preflight.sh`（s11 树，kit 探针回落）：star → `http://100.64.0.27:1231/v1`。
   - 新守卫测试：`tests/data_agents/test_star_domain_retirement.py`（4 条：gemma4 / rerank /
     脚本默认档扫描 / star 档案 allowlist）＋ `tests/test_star_coupling_defaults.py`（种子提取器默认档）。
   - **不发散**：`canonical_v2/*.py` 零改动（`git diff --name-only` 证明）⇒ 封印包 reader 指纹不变，
     不需要重封、不触发 137–190 s 慢启动。

2. **目标机（100.64.0.96）**：`miro-embed-shim.conf`（`100.64.0.27:18005` → star embedding；**上线至今
   0 次请求**）与死配置 `gxzx-origin-map.conf`（无任何引用）→ 时间戳备份 + `.disabled` 改名 → `nginx -t`
   → reload。

3. **登记（按 D2 不执行）**：`deploy/retire-star-entry.sh`（dbg21 `/guoxian` 一键摘除：备份 → 删 6 个
   location 块 → `nginx -t` → reload → 三方验证 + 回滚指令）；`deploy/README.md` 入口段标注退役中。

**发现**：

1. **star 域名的后端就是 dbg21（100.64.0.34）**：校网关 172.18.24.245 → dbg21:3001 的 nginx；
   star 的模型路径（qwen36/embedding/rerank → `172.18.41.222`）与我们的 `/guoxian` 入口在同一份
   `sustech-ai.conf` 里，另有若干非本项目应用（zs-ai 等，今天仍活跃）。
2. **模型流量在 10-12/13 断崖归零**（418–456/天 → 157 → 45 → 29 → 今天仅 3 次只读探针）：
   节律与客户旧线 run-9 的 keepwarm（144 轮/天）吻合；run-9 的冻结嵌入包 base_url = star、
   `run.sh` hedge 默认 gemma4（注释 "star 网关"）；其 `serve.log` 停在 **10-12 16:41**。
   残余 45/29 次未完全归因（含 `/mirothinker` 探针）→ 列为向校网关方索取客户端 IP 的核对项。
3. **自建模型机只服务一个模型**（`100.64.0.27:1231` → `qwen3.6-35b-a3b`）；star 的 `qwen35` /
   `mirothinker` 两条路径**已返回 HTML（模型 API 已不在）** ⇒ 这两个档位不是"可用选项"，本就是死档；
   `ark`（与 gemma4 同 URL）仍 401 活着。
4. **执行期间目标机有一次"别人的部署"**（16:48 起 `miro-fullstack-v2` 以新包
   `serving-pack-fembed-v2-aliasfoothold` 重启，属"片②"工作流）——与本轮 nginx 改动无关；
   验收因此以 health/chat/nginx 三方为准，未插入真实提问。

**怎么验证（原始数字）**：

- 守卫测试 **RED 4 failed**（改前）→ 改后 `test_star_domain_retirement + test_llm_profiles + test_rerank`
  = **31 passed**；控制台 `test_star_coupling_defaults + test_canonical_v2_runtime_sources + test_seeds_api`
  = **16 passed / 28 skipped**（既有条件跳过）。
- 新进程实测：`gemma4 → http://100.64.0.27:1231/v1`、`rerank → http://100.64.0.27:18006`；
  剩余 star 档案 = `['ark','mirothinker','qwen35']`（allowlist 锁定，均非默认值）。
- 目标机：`18005` 监听 **0**、`nginx -T` star 行 **0**、`app /api/health` **200**、`app /chat` **200**、
  经 nginx `/chat` **200**；备份两份留在 `/etc/nginx/conf.d/*.bak-20261015`。
- 本机活线未动（未重启）：一轮真实提问出站仍只有 DeepSeek/Serper/Bocha（上一轮已实测，star=0）。

**影响哪些问题**：

- 关闭了"star 域名退役后我们被带崩"的主要休眠面（采集/种子/守卫/rerank/kit 探针）；入口与校方的
  时间表解耦（脚本就绪即可一键摘）。
- 新增两条待办：目标机代码树的同类默认值（本轮只改了本机两棵活线树；目标机无 `.sglang_api_key`
  且从未跑过采集，无实际可达路径）、`canonical_v2` 的 `gemma4` 回落常量（随下次重封）。

**未验证 / 如实记录**：本机运行中的进程尚未加载新默认值（休眠路径，等下次重启；要立刻生效需重启
18188 ≈5 分钟）；目标机未做"删 shim 后向量道端到端"（v2 线用 maas，不经该 shim）；dbg21 摘除与
防火墙收紧未执行（等校方日期）。

---

## 第 2 轮 · 2026-10-15 · 用户要求"确定不再使用"→ 两处残留清零（本机重启 + 目标机防呆）并用活体复测确认

**背景**：用户问"国先·问渠无论本地还是目标机，是否确定不再使用 star 的服务"。第 1 轮的结论是
"生产路径确定不用、但有两处非自动残留"（本机进程内存旧表 / 目标机旧线持有可用 star 密钥）。
用户拍板：本机现在就重启、目标机做防呆。

**做了什么**：

1. **本机 18188 重启**（19:36 发起）：`systemctl --user restart canonical-v2-backend` →
   **290 s 起来**、health 200、`/chat` 200；新进程（pid 256767，19:41:56 启动）加载的正是改后代码
   （`llm_profiles.py:81 → http://100.64.0.27:1231/v1`、`rerank.py:13 → http://100.64.0.27:18006`）。
   重启后 star 入口（`https://star.sustech.edu.cn/guoxian/chat`）仍 **200**，不受影响。
2. **目标机防呆**：
   - 旧线密钥改名：`/root/deploy/fullstack/code/.sglang_api_key` → `.sglang_api_key.disabled-20261015`
     （全机已无同名可用密钥，`find` 计数 0）。
   - `systemctl mask miro-fullstack` 第一次被"真实 unit 文件在 /etc"挡住 → 标准做法：unit 文件
     改名为 `.disabled-20261015`（另留 `.bak-20261015`）+ 挂 `/dev/null` 符号链接 + `daemon-reload`。
     现在 `is-enabled = masked`，实测 `systemctl start` 被拒（"Unit miro-fullstack.service is masked."）。
   - v2 线全程未受影响（active、health 200、`/chat` 200）。

**复测（"确定"的当场证据）**：

| 对象 | 方法 | 结果 |
|---|---|---|
| 本机 18188（新进程） | 一轮真实提问 19.6 s / 2167 帧 + 1 s 粒度抓包 | 出站 = 银联国际页面、腾讯云 CDN、一个阿里云占位证书站点（**均为 web 车道抓取目标**，证书已核实）+ 本机；**star 命中 0** |
| 目标机 18188（新包 `fembed-v2-aliasfoothold`） | 4 分钟被动抓包（覆盖 keepwarm） | 出站 = DeepSeek/Serper/Bocha + 银联国际/西电（抓取目标）+ 本机；**star 命中 0**；`serve.log` star 命中 0 |
| 目标机进程环境 | 逐个变量核对 | `CHAT_LLM_PROFILE=deepseekv4flash` ✓；`CHAT_LLM_HEDGE_PROFILE=gemma4` 是 **空转**（v2 代码里 grep 无 hedge 读者，那是旧线实现） |
| star 侧 | dbg21 访问日志 | 今天只有我方 3 次只读探针；模型路径无常态流量 |

**结论（可对外口径）**：国先·问渠两处实例（本机 dev 线 + 目标机线上）**不再使用 star 域名下的任何
模型服务**；对 star 的最后两处"可被人工触发"的残留（本机进程内存旧表、目标机旧线密钥）已在本轮清零。
仍如实记录三处**非默认、需显式选择**的 star 引用：`qwen35`/`mirothinker`/`ark` 三个档位定义（本机
点它们的"测试"会发一次请求；目标机无密钥会 401）、`canonical_v2` 里的 `gemma4` 回落常量（随下次重封）、
目标机 v2 代码树的同类默认值（无密钥、不可达）。

**未验证 / 如实记录**：抓包仍是分钟级窗口（非长期审计）；目标机 `mask` 是运维层防呆，若将来要回滚
旧线需 `rm` 符号链接 + 把 `.disabled`/`.bak` 两个 unit 文件还原 + 恢复密钥名。
