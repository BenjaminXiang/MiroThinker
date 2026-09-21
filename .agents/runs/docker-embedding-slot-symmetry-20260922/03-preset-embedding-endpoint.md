# 交付预置里的 v1 时代嵌入端点/模型（R1 修复 + R2 措辞）

2026-09-22，分支 `delivery/docker`。上一轮报的 R1/R2，本轮做掉。

## 1. 事实核实：两个字段各自会不会影响候选路由

先给结论，再给行号（**镜像内**（= 交付代码，`/opt/mirothinker`）与 switch 线各查一遍）：

| 字段 → 环境变量 | 有读者吗 | 会不会影响候选（`provider=dashscope-native`，`model_id=qwen3.7-text-embedding-flash`，1024 维） |
|---|---|---|
| `extraction_endpoints.embedding_base_url` → `CANONICAL_V2_EMBEDDING_BASE_URL` | **有，且是"覆盖"语义** | **会**。受管值覆盖候选 bundle 记录的网关地址 ⇒ 拿网关的 key 打自建端点 |
| `extraction_endpoints.embedding_model` → `CANONICAL_V2_EMBEDDING_MODEL` | **没有**（全代码库只出现在"字段→变量"映射与一个测试的 scrub 列表里） | **不会**。候选适配器的模型来自 bundle：`model_id=document["model_id"]`；旧模型 id 只会在页面上显示 |

行号证据：

* 映射（两处同源）：`managed_config.py:74-75`（镜像内同）
  ```python
  "extraction_endpoints.embedding_base_url": "CANONICAL_V2_EMBEDDING_BASE_URL",
  "extraction_endpoints.embedding_model":    "CANONICAL_V2_EMBEDDING_MODEL",
  ```
* 投影（启动一次，env > file）：`managed_runtime.apply_managed_runtime_config()`（`managed_runtime.py:104-146`）。
* **地址的消费点**：`knowledge_build_isolated.resolve_embedding_base_url(recorded)` =
  `override or recorded`（switch 线 `:8328-8345`；镜像内 `:8187`），调用点镜像内 `:8262`
  （recorded/自有适配器）、switch 线 `:8479` 与 `:8559`（两条候选适配器）⇒ 两个权威都吃这个覆盖。
* **模型没有消费点**：`grep -rn CANONICAL_V2_EMBEDDING_MODEL /opt/mirothinker/apps /opt/mirothinker/deploy`
  → 只有 `managed_config.py:75` + `apps/admin-console/tests/test_canonical_v2_model_discovery_api.py:54`
  （一个"环境变量必须不影响结果"的 scrub 列表）。候选/自有适配器的 model 一律来自 bundle
  （`document["model_id"]`，switch 线 8314/8476/8556 → `_provider_client` 用 `self.model_id`，`:8139`）。
* 镜像内还确认：v1.1 交付代码里**没有**候选路由（`dashscope` / `_GATEWAY_EMBEDDING_API_KEY_ENV` 均 0 命中）
  —— 候选随 v2 进来，但"地址覆盖"这条**现在就成立**（v1.1 的自有/采集适配器就在吃它）。

**容器实测（修复前）**：运行中实例的连接测试：

```
"base_url": "http://100.64.0.27:18005/v1",
"endpoint_origin": "managed-file(env:CANONICAL_V2_EMBEDDING_BASE_URL)"   ← 预置覆盖生效（不是 bundle）
```

## 2. 预置怎么改、为什么

`deploy/docker/site-config/managed-settings.json`：把 `extraction_endpoints` 里的
**`embedding_base_url` 与 `embedding_model` 两个键删掉（缺席）**，其余不动
（`llm_base_url`/`llm_model` = 采集 LLM 端点，仍与 `chat_llm_profile=deepseekv4flash` 一致；
`collection.*`、`paths.access_log_retention_days`、`serving.chat_llm_profile` 保留）。

为什么选"缺席"：

* **地址**：F2 的设计原则是"**冻身份，不冻地址**"，而 bundle 已经把网关地址记录为默认值
  ⇒ 缺席 = "默认用 bundle 记录的地址"，"只填 key"开箱即用；要换入口的操作者**在页面上显式写**，
  那时它才是"操作者的决定"。
* **模型**：没有读者，留着只会让页面显示一个 v1 时代（4096 维）的模型 id，误导现场对"在用什么模型"的判断。
* 不选"塞一个新值"：那等于用交付预置替操作者拍板（同样的越权），而且 v2 的地址属于候选网关，
  把它写死会让"自建端点"这条对照线失去可配置性。

出包路径已核对（源码，不是生成副本）：`build-site-bundle.sh:224`
`place "${DEPLOY_DIR}/site-config/managed-settings.json" "${OUT_DIR}/state/config-managed/settings.json"`；
安装器只在 `settings.json` 不存在时落位（`install-site.sh` 第 6 步）。

## 3. 测试（新增 5 条，先 RED 后 GREEN）

`apps/miroflow-agent/tests/canonical_v2/test_delivery_preset_embedding_endpoint.py`
（RED：改前 3 failed / 1 passed / 1 skipped → GREEN：**4 passed / 1 skipped**）：

| 测试 | 钉住 |
|---|---|
| `test_the_packer_ships_this_exact_preset_file` | 改的是出包脚本真正复制的那份源（不是副本） |
| `test_preset_omits_the_v1_embedding_address_and_model` | 两个键缺席、且旧值（`100.64.0.27`/`Qwen3-Embedding-8B`）不在文件里 |
| `test_preset_projection_leaves_the_embedding_endpoint_to_the_bundle` | 用**真**投影（`apply_managed_runtime_config`）跑一遍：`CANONICAL_V2_EMBEDDING_BASE_URL/MODEL` 都不出现；同时 `LOCAL_LLM_BASE_URL`/`CHAT_LLM_PROFILE`/`paths.serving_pack_dir` 照旧被投影（预置没被弄残缺） |
| `test_effective_view_reports_the_embedding_fields_as_unset` | 页面读到的 `source` 不是 `file`，值都是 `None` |
| `test_candidate_bundle_address_wins_once_the_v2_line_is_merged` | **条件**（本分支还没有 `resolve_embedding_base_url`，skip 并写明留给 v2）：生效地址 == bundle 记录的网关地址 |

## 4. 容器内证据（"生效地址来自哪里"可判）

`raw/06-preset-fix.txt`（同一实例、只换预置 + `restart`）：

| | 生效端点来源 | base_url | 连接测试 |
|---|---|---|---|
| 旧预置（基线） | `managed-file(env:CANONICAL_V2_EMBEDDING_BASE_URL)` | `http://100.64.0.27:18005/v1` | ok:true / HTTP 200 |
| 新预置（本轮） | **`release-bundle-default`** | `http://100.64.0.27:18005/v1`（v1.1 的发布包记录的就是它；v2 的候选 bundle 记录的是网关地址） | ok:true / HTTP 200 |

管理面配置视图（`/api/canonical-v2/admin/config`，同一实例）：

```
extraction_endpoints.embedding_base_url | value=None | source=default | editable=True  | env_var=CANONICAL_V2_EMBEDDING_BASE_URL
extraction_endpoints.embedding_model    | value=None | source=default | editable=False | env_var=CANONICAL_V2_EMBEDDING_MODEL
```

⇒ 与 R2 的新措辞一一对应：**地址可写、身份只读**；两者当前都"未设置/默认"，即由发布包决定。
（注意：`/proc/<pid>/environ` 只反映**进程启动时**的环境，服务启动后 Python 侧投影的变量不会出现在里面——
上一轮查候选槽位能查到，是因为那一份是**容器入口脚本 export** 的。受管路线的投影要看 `origin`/`source` 字段。）

### 4.1 判决性一条：**"交付预置 + 候选 bundle 记录地址" ⇒ 生效地址 == 网关地址**

用**镜像内的交付代码 + 服务自己的解释器**（`/opt/mirothinker/.venv/bin/python3`，走真的
`apply_managed_runtime_config` → `resolve_embedding_base_url`），把候选 bundle 记录的地址
（`https://maas.qianwenaiapi.com/api/v1`，取自 switch 线的 qwen3.7 bundle）喂进去，
分别配"旧预置（备份）"与"新预置（本轮交付件）"：

```
旧预置（备份 .pre-r1-fix） 生效地址 = http://100.64.0.27:18005/v1            ← 被 v1 时代预置覆盖（bug 复现）
旧预置（备份 .pre-r1-fix） 预置贡献的 embedding 字段 = ['extraction_endpoints.embedding_base_url',
                                                      'extraction_endpoints.embedding_model']
新预置（本轮交付件）       生效地址 = https://maas.qianwenaiapi.com/api/v1    ← 网关地址，来自 bundle ✓
新预置（本轮交付件）       预置贡献的 embedding 字段 = ['（预置里没有 embedding 字段）']
```

⇒ ①②③ 要的"**生效地址 == bundle 记录的网关地址（不是 100.64.0.27）**"在本轮就有判决性证据；
v2 只剩"真候选路由 + 真网关打一次请求"的端到端（见 `02-v2-handoff.md`）。
**模型那一侧**：镜像内 `CANONICAL_V2_EMBEDDING_MODEL` 的全部命中 = `managed_config.py:75`（映射）
+ 一个测试的 scrub 列表；适配器的 model 来自 bundle（`model_id=document["model_id"]`，镜像 :8173）
⇒ 旧模型 id 进不了请求；改后它还从预置里消失了（`raw/07-effective-address-check.txt`）。

## 5. R2 改后的措辞（`CONFIG-GUIDE.md §4`）

* 标题从"唯一一处配置"改为"还会用到的配置"；开头"（不需要填地址）"→"（**默认不需要填任何地址**：地址来自随包的发布包）"。
* 嵌入端点一行：**"地址可改；身份（模型 + 维度）不可改"**；说明里写清
  ① 地址不填就用发布包记录的地址，要换入口（自建 ↔ 网关 ↔ 代理）就改地址 → 测试 → 重启；
  ② 模型 id 与维度是冻结身份（索引就是用这个身份建的，换了不是同一个向量空间 ⇒ 必须我方重建索引出新数据面包）；
  ③ 点"测试"会真发一次请求并给向量身份校验结论。
* 表下新增一段"**为什么这么分：冻身份，不冻地址**"：身份钉在发布包与索引的封印里、地址只是"从哪里取"；
  并写明**交付预置里不预置嵌入地址/模型**的理由（预置过自建端点会把走网关的站点指到错误入口），
  以及"页面上 `embedding_base_url` 可写、`embedding_model` 只读"。

## 6. 其它 v1 时代遗留值清单（**只列，不改**；改不改由你判断）

| # | 位置 | 遗留值 | 影响 |
|---|---|---|---|
| L1 | `site-config/managed-settings.json`（本轮**未改**的部分） | `paths.serving_pack_dir = /var/tmp/mirothinker-data-v2/serving-pack-run16-v11` | `CANONICAL_V2_SERVING_PACK` **有读者**（pack loader；admin-console 的 status/identity 页）。v2 换包名后，这条会指向 v1.1 的包目录（服务线的 `--serving-pack` CLI 参数若优先则只影响页面显示，需在 v2 核对优先级） |
| L2 | `install-site.sh:233` | 安装器嵌入探针写死 `"model":"Qwen/Qwen3-Embedding-8B"`（地址/维度**已经**取自 `bundles/qwen-embedding-bundle-v1.json`） | v2 站点会拿旧模型 id 打网关 ⇒ 404/维度 0，**假红**（`[warn] 嵌入端点探针未过`），现场会误以为 key/网络有问题。修法一行：随包 bundle 里本来就有 `model_id`（见 `bundles/qwen-embedding-bundle-v1.json`），照 `verify.sh` 的读法取它即可 |
| L3 | `deploy/docker/verify.sh:4/29`（`Dockerfile:150` 把它 COPY 成容器内 `mirothinker-verify`） | **只是措辞**："断言 HTTP 200 + 维度 4096"（实际断言是 `bundle["dimension"]`/`bundle["model_id"]`，bundle 驱动 ✓） | v2 站点上断言仍然正确，但打印出来的期望值文字会与新包不符。建议出包时把这两处文字改成"按随包 bundle" |
| L4 | `entrypoint.sh:23` / `build-site-bundle.sh:67-68` / `build-data-face-kit.sh:22` / `build-image.sh:135` / `install-site.sh:130-152` | 服务包名 `serving-pack-run16-readerbound` → `serving-pack-run16-v11` 写死在多处（`OLD/NEW_PACK_TOKEN` 支持环境变量覆盖 ✓） | v2 换包名时是一组"必须同步改"的点；好消息是覆盖件生成器已有 token 断言，改名时它会拒绝出包 |
| L5 | `CONFIG-GUIDE §6/§7/§8`、`README.md §…`、`README-FIRST` 生成文本 | `100.64.0.27:18005`、"维度 4096"、"serving-pack-run16-readerbound"、`delivery-v1` commit 等**按本包写死的数字/名字** | 对 v1.1 是正确描述；v2 出包时这些数字要随包更新（建议出包脚本加一条"文档数字 vs 包内 bundle"的自检） |
| L6 | admin-console `canonical_v2_runtime_sources.resolve_embedding`（镜像内与 switch 线皆有） | `model = "Qwen/Qwen3-Embedding-8B"` 硬编码 + `EmbeddingClient().base_url` 作为 recorded 回落 | 页面"嵌入端点"卡片在 v2 站点上仍会显示 v1 的模型身份（切换线已给地址加了 override 显示，模型这条还是 v1 常量） |
| L7 | `Dockerfile`/`entrypoint` 冻结的 repo 链接与 `/opt/mirothinker` 代码副本 | 无版本断言 | v2 重打镜像时若代码副本与发布包版本不匹配，只有"读者摘要/解释器补丁"那套校验会兜底（历史已验证），但**没有**针对"包名/模型"的一致性自检 |

## 7. 没验到 / 留给 v2

* **真候选路由 + 真网关**的端到端（v2 冷装："只给文件 → 向量道可用"）不归本轮：本轮的容器是 v1.1
  发布包，没有候选路由代码（镜像内 `dashscope`/`_GATEWAY_EMBEDDING_API_KEY_ENV` 均 0 命中）。
  本轮能给出的是：① 凭据到位（上一轮的槽位投影）；② **生效地址 == bundle 记录的网关地址**
  （§4.1，用交付代码 + 候选 bundle 的记录值做的判决性检查）；③ 页面语义（§4）。
  v2 要补的那一条是"用真候选 bundle 打真网关 → HTTP 200 + 1024 维"，判据见 `02-v2-handoff.md`。
* L2/L3 两条"假红/文案"建议没改（本轮边界：预置 + 指南措辞 + 测试）：L2 会让**安装器探针**
  在 v2 站点上给出错误的黄灯（拿旧模型 id 打网关），建议 v2 出包前一行改掉（bundle 里本来就有
  `model_id`）；L3 只是打印措辞。
* 本轮的容器实例状态：`/var/tmp/mirothinker-fourth-verify-20260922` + 端口 18298；受管预置已换成
  新版本（旧版留在 `<包>/state/config-managed/settings.json.pre-r1-fix` 作为对照）。
