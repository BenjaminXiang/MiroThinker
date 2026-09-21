# 验收探针（`mirothinker-verify`）的嵌入断言：改成断言**站点真正在用的身份**（2026-09-22，第四轮）

**为什么做**：镜像里烘着一份 **v1 时代的账本**（`Qwen/Qwen3-Embedding-8B` / 4096 维 / 自建地址 /
OpenAI 兼容形状），而 `mirothinker-verify` 拿它当**期望身份**去打——v2 站点（候选网关：
`qwen3.7-text-embedding-flash` / 1024 维 / `dashscope-native` 原生路由）会被我们**自己的验收**
判红（"端点不可达"或"维度不符"），而甲方唯一的判断依据就是这个验收。

## 1. 谁读那份账本（带行号）

| 读取方 | 位置 | 读它做什么 |
|---|---|---|
| **运行期（服务线）** | 冻结命令文件传 `--recorded-embedding-bundle <该路径>`；加载器 `knowledge_build_isolated.py:8155 load_content_addressed_embedding_adapter(path)` 在 `:8186-8203` 把文档**逐字段**与冻结 `expected` 比对（schema/provider/`model_id`/`dimension`=`_QWEN_EMBEDDING_DIMENSION`=4096/`base_url`/`content_sha256`=`_QWEN_EMBEDDING_BUNDLE_SHA256`=`05473fab…`）→ 不符即 `release embedding bundle differs from frozen authority` | **它不是"给 verify 用的期望"，而是运行期的冻结嵌入权威**（所以不能随手换内容：内容与代码常量必须同一次改） |
| **验收（本轮改的对象）** | `deploy/docker/verify.sh:12`（旧）读同一个路径当期望 | 探针断言 HTTP 200 + 维度 == 该账本的 dimension |
| 镜像构建 | `deploy/docker/Dockerfile:143-146` COPY `deploy/docker/ledger/s12c/qwen-embedding-bundle-v1.json` → 冻结绝对路径 | 把账本烘进镜像 |
| 站点包 | `<site-bundle>/bundles/qwen-embedding-bundle-v1.json`（与镜像账本**字节相同**：sha256 `9b840145…`） | 安装器探针（上一轮已改成从它取 model/维度） |
| 其它 | `replay.sh` / `migrate.py` / `entrypoint.sh` / `build-*.sh`：**零命中**（`grep` 过） | — |

⇒ 结论：账本是**运行期**的记录文件（不是"给 verify 用的期望"），所以修法必须是**让验收去读运行期
那份**，而不是给 verify 另配一张表。

## 2. 修法与"站点身份从哪来"

新增 `deploy/docker/verify_embedding.py`（`Dockerfile:153` COPY 成
`/usr/local/bin/mirothinker-verify-embedding`，`verify.sh` 调它）。身份来源**不猜**：

1. **运行中的服务进程 argv** 的 `--recorded-embedding-bundle`（运行期就是按它加载并逐字段比对的）；
2. 退一步：冻结命令文件（`…/s12g/serve-18188-command.sh`，compose 把交付的覆盖件挂在那里）里的同一参数；
3. 都没有 ⇒ **报 FAIL 让人查**，不回落到任何写死的路径。

地址：**服务进程环境**里的 `CANONICAL_V2_EMBEDDING_BASE_URL`（受管/页面覆盖，
`resolve_embedding_base_url` 的优先级；注意 `docker compose exec` 看不到这一层，必须读
`/proc/<pid>/environ`）→ 本进程环境 → 账本记录的 `base_url`。
身份：账本的 `model_id` + `dimension`；**并与服务包 `<pack>/manifest.json` 的 `embedding_model_id`
对照**，不一致即 FAIL（索引身份 ≠ 嵌入权威身份）。

**请求形状：镜像页面身份校验的规则，不发明第二套**
（`apps/admin-console/backend/services/canonical_v2_embedding_identity.py`，v2 分支：
`EMBEDDINGS_PATH`/`PROVIDER_*`/`NATIVE_EMBEDDINGS_PATH`/`ROUTE_ABSENT_STATUSES`）：

* 先讲 OpenAI 兼容形状 `{地址}/embeddings`；
* **只有** HTTP 404/405（该路线不存在）才改讲 DashScope 原生形状
  `{地址}/services/embeddings/text-embedding/text-embedding`；
* 原生调用带 `text_type`（角色是调用方的属性：这里探服务线**查询侧**，取账本的
  `query_text_type`，缺省 `query`）；
* 401/500 之类是那条路线自己的回答 ⇒ 不换形状、如实报红。
* **防漂移**：镜像里若已有身份模块/原生客户端，把上述字面量读出来逐个比对，不一致即 FAIL；
  v1.1 镜像只有兼容形状常量 ⇒ 打 `[note]` 说明（不假装校验过）。

## 3. 为什么不破坏 v1.1（核实结论）

推理成立，且逐条核实过：

* 账本是**烘进镜像**的（`Dockerfile` COPY），镜像是**按发布**打的 ⇒ v1.1 镜像（已打好、不动）
  继续带 v1 账本，v2 镜像带 v2 账本；
* **没有共享**：`grep -rn ledger deploy/docker/*.sh` = 0 命中（出包脚本不会重建/改写它）；
  站点包里的同名 bundle 是**复制**（不是链接）；
* **不会自动改到 v1.1**：`verify.sh`/`verify_embedding.py` 只进镜像（`Dockerfile` COPY），
  站点包里没有这两个文件（BUNDLE-MANIFEST 可核对）；
* 本轮的探针**对 v1.1 也是向后兼容的**：它在 v1.1 真站点上跑出 `[OK]`（见 §4 A），因为身份是从
  站点自己的账本读的 —— 旧行为（v1 期望）正好等于新行为（站点身份）。
* 唯一"必须同一次改"的耦合点：**账本内容 ↔ 代码常量**（`_QWEN_EMBEDDING_BUNDLE_SHA256` 等）；
  v2 切包时由 switch 线负责（本分支不碰），而出包自检新增的硬检查会拦住"只改一边"。

## 4. 证据

* **判红演示**（假候选网关，兼容 404 / 原生 200·1024 维；`raw/10-verify-identity-red.txt`）：
  * 旧断言（HEAD 版 `verify.sh` 里的那段 python，逐字提取）：
    `[FAIL] 嵌入端点不可达：HTTPError: HTTP Error 404` → `exit=1`
    ⇒ **旧验收会在一个装对了的 v2 站点上报红**；
  * 新探针：`[OK] …（形状 dashscope-native，角色 query）HTTP 200，维度 1024` → `exit=0`。
* **真容器**（v1.1 实例、真端点；`raw/11-verify-probe-container.txt`）：
  * A. 真站点身份：`[OK]` 三条（身份来源 / 包身份一致 / 端点 200·4096·compatible）+ 防漂移 `[note]` → `exit=0`；
  * B. 人为把期望身份换成一版候选身份：`[FAIL] 身份不一致…` + `[FAIL] 探针未过…` → `exit=1`。
* **真调用次数（本轮）**：嵌入端点请求 **4 次**（第一次容器验收 A 1 次 + B 2 次；防漂移修正后重跑
  A 1 次 + B 2 次 = 3 次，加上第一次 A 的 1 次共 4 次；每次都是单条文本的小请求）。无其它外呼。

## 5. 出包自检新增（顺手，不扩大改动面）

`check-delivery-consistency.py` 加了一条**硬检查**：镜像账本的身份
（`model_id`/`dimension`/`base_url`/`provider`）必须与**站点包里的某个嵌入 bundle**一致，
否则拦包（v2 换身份时最容易只改一边）。`_IGNORED_TOKENS` 里那条
`qwen-embedding-bundle-v1.json` 只是文档扫描时忽略**文件名**（它会被"org/model"形状的正则误命中），
不涉及身份值；真正的不一致由这条硬检查负责（`raw/09-packaging-check.txt` 的 A/B/C 三段仍适用，
新增用例见测试）。

## 6. 没验到 / 留给 v2 重打

* **v2 镜像里探针的真实表现**（原生网关、1024 维、`dashscope-native`）只能在 v2 冷装时看：
  本轮的证据是"本地假原生网关 + 真容器上的身份链路"两段，**没有**真的拿候选网关打过（省配额）。
  冷装时的期望输出：`[OK] …（形状 dashscope-native，角色 query）HTTP 200，维度 1024`，exit 0。
* 防漂移只比对**字面量**（路线、状态码集合、角色选择），不比对整模块逻辑；v2 合并后若身份模块
  的规则再变（例如再引入第三条形状），探针不会自动跟上 —— 那时要同一次改两边（测试里有一条
  钉住"字面量不一致 ⇒ 红"）。
* `mirothinker-verify` 的**其它**断言（`/api/health`、`/chat`、`/main`、内存）与方法无关，未动。
* 账本本身**没有**换成候选内容（理由见 §3：内容与代码常量耦合，属 switch 线的切包动作）；
  本轮只保证"验收读的是站点在用的那一份"。
