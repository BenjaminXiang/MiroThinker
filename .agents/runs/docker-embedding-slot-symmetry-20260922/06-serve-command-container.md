# 宿主命令草案 → **容器命令文件**：产出通道与校验（2026-09-22 · 第六轮）

v2 出包清单里发现的第二个集成缺口。第一个是"文件路线喂不到候选嵌入槽位"（已修，见 `01-`/`03-`）。
这一个更容易漏、后果更硬：**宿主的裸机切换命令草案与容器命令文件是两种东西**，中间历来只有
`build-site-bundle.sh:160` 一处 `sed`（把 `serving-pack-*` 两个 token 中的旧包名换成新包名，
默认值在 `:67-68`，替换前后还有一次 diff 校验 `:162`）。照抄草案 = 容器起不来或 import 到错的树。

| 产物 | 位置 |
|---|---|
| 工具（新增） | `deploy/docker/serve-command-container.py`（`convert` + `check`，只读、stdlib、从不打印密钥） |
| 测试（新增 9 条） | `apps/miroflow-agent/tests/canonical_v2/test_serving_command_container.py` |
| 演示脚本 | `.agents/runs/docker-embedding-slot-symmetry-20260922/12-serve-command-demo.sh`、`12b-pytest-mutation-demo.sh` |
| 原始证据 | `raw/12-serve-command-container.txt`、`raw/12b-pytest-mutation.txt` |
| 未动 | 宿主草案 `serve-18188-command-fembed.DRAFT.sh` 与他的校验器 `check-cutover-command.sh`（宿主侧归母 agent） |

**真调用计数 = 0**：本轮只做只读检查（`docker run --rm` 的 `test -e` / `cat`）与本地演示，没有任何外呼。

---

## 1. 差异表的复核：结论（有错直说）

母 agent 那张表**四项都对**，我补两处没列的、一处必须澄清的。

| 项 | 表里说的 | 复核 | 依据 |
|---|---|---|---|
| launcher | 宿主用 switch 线的 `s12e/serve_s12e_port.py`；容器用 `canonical-v2-s11-consolidation` 那条 | **对** | `Dockerfile:138` 把 `canonical-v2-s11-consolidation` 符号链接到 `/opt/mirothinker`，即镜像自己那棵树；容器内实测该文件存在 |
| `src` 树钉法 | 宿主必须 `PYTHONPATH=<switch>/apps/miroflow-agent`；容器不需要 | **对，且理由是硬的** | 镜像 venv 的三个 editable `.pth`（`_editable_impl_{miroflow_agent,admin_console,miroflow_tools}.pth`）分别指向 `/opt/mirothinker/apps/miroflow-agent`、`/opt/mirothinker/apps/admin-console`、`/opt/mirothinker/libs/miroflow-tools/src`。宿主侧为什么必须钉：switch 线**没有 `.venv`**，`uv run` 不构成钉法 —— 这正是他自己 `check-cutover-command.sh:36-42` 在断言的事 |
| `--recorded-embedding-bundle` | 宿主指候选 bundle；容器指镜像账本 | **对**，补全：容器那份 = `deploy/docker/ledger/s12c/qwen-embedding-bundle-v1.json`，由 `Dockerfile:145` COPY 到 data-rebuild 树下的 s12c 路径。两者**不是同一个身份**：v1 账本 `Qwen/Qwen3-Embedding-8B`/4096/`openai-compatible`/`http://100.64.0.27:18005/v1`；候选 `qwen3.7-text-embedding-flash`/1024/`dashscope-native`/`https://maas.qianwenaiapi.com/api/v1` |
| 数据面 | `/var/tmp/mirothinker-data-v2`、`/var/tmp/mirothinker-canonical-v2-s12f` 由挂载提供 | **对** | 两个挂载点由 `Dockerfile:129` `mkdir -p` 造出来，内容随后挂进去 |

表里没列、但**同样决定"起不起来"**的两条，我按同一重量级处理：

1. **密钥**：宿主 `CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)"`；
   容器里这条**必须不存在**（由挂载的 key 文件 + `entrypoint.sh` 投影，见前几轮 `raw/05-*`）。
   顺带一个坑：这条赋值按空白会被切成 `NAME="$(cat` 与 `/path)"` 两段，转换时只丢前一段会留下
   一个莫名的 token —— 第一版 `convert` 就栽在这里（已修，测试锁住）。
2. **两个占位符**：`__STEP7_INDEX_MARKER_SHA256__`（step 7 填）、`__STEP10_SERVING_BUNDLE_SHA256__`
   （step 10 填）。宿主机上留着占位符是**中间态**；进容器的文件必须是具体 64-hex。

**一处必须澄清（否则会把两份文件搞成一回事）**：**同一份文件不可能同时过两边的检查**。
他的 `check-cutover-command.sh` §2 要求**必须有** `PYTHONPATH=<switch>/apps/miroflow-agent`、
§5 要求**必须有** `CANONICAL_V2_EMBEDDING_API_KEY`；容器这两条都禁止（镜像 venv 已钉树、密钥走挂载）。
所以出包**必须**有转换这一步，"把宿主草案直接当站点包的命令文件"永远错。

### 顺带发现（宿主侧，只报告，未改任何宿主文件）

草案引用的两个宿主路径**当前不存在**（2026-09-22 04:00 实测）：

| 草案里的路径 | 实况 |
|---|---|
| `<data-rebuild>/.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json` | **不存在**。候选 bundle 实际在 `<embedding-switch-line>/.agents/runs/embedding-model-switch-v2/`。**而且这个名字在 5 棵 worktree 里有 3 种内容**（见下） |
| `<embedding-switch-line>/.agents/runs/rebuild-…/s12g/serving-bundle-fembed.json` | **不存在**（step 10 才封存；同目录只有 run14/15/16 三份旧 bundle） |

影响：这两个路径只被宿主脚本引用，**容器侧不受影响**（我们映射到镜像账本）。但宿主脚本若真跑，
`load_recorded_serving_inputs` 会在读取阶段就抛错（fail-closed，不会静默）。⇒ 出包时"候选 bundle
的内容出处"必须写清（见 §3），别依赖这两条路径。

### 候选 bundle 在 5 棵 worktree 里有 3 种内容（出包前必须点名是哪一份）

同名文件 `qwen3.7-text-embedding-flash-embedding-bundle-v1.json` 的实测 sha256：

| worktree | sha256 | 与 switch 线那份的字段差异 |
|---|---|---|
| `embedding-switch-line`（+ `v2-boot-log-noise`、`v2-admin-identity-native`，三份**字节相同**） | `35104c06…` | —— 基准（`query_text_type=query`、带 `query_instruct`、`batch_size=20`、`content_sha256 67927ea0…`，与 `launch-record.md:19` 记的构建用 bundle 一致） |
| `embedding-model-switch` | `b6eae2fd…` | 少了 `query_instruct`/`query_text_type`（= 文档侧），`batch_size=25`，`content_sha256 81a5369…` |
| `embedding-switch-docs` | `1dc43dc2…` | 同上（文档侧），`batch_size=32`，`content_sha256 cdddcdfd…` |

即**四个身份字段（model/dimension/provider/base_url）三份完全相同**，差别只在角色字段与实际内容。
所以容器侧的比对改成**逐字段比全文**（§2 第 4 点、§4.1 ⑥），并新增第 7 条测试锁住这个陷阱。
出包时必须**点名**用哪棵树的那一份（当前应为 `embedding-switch-line` 那份 `35104c06…`），
并把它 COPY 进账本 —— "名字一样"不等于"内容一样"。 

---

## 2. 选的形状：**转换脚本 + 逐项断言**（`convert`，不是另写模板）

`deploy/docker/serve-command-container.py` 两个子命令：

* `convert --host-command <宿主草案> --image <ref> --out <容器命令文件> --map HOST=CONTAINER …`：
  1. 丢掉 `PYTHONPATH=` 与任何 `*_API_KEY=`（含它的取值碎片）；
  2. 只替换**显式映射**过的 token（含两个占位符 → 具体值），其余 token 逐字保留；
  3. **断言**：除显式映射的路径参数外，identity 旗标逐字不变（`--candidate-release-id`/
     `--run-id`/`--source-manifest-sha256`/`--index-marker-sha256`/`--recorded-serving-bundle-sha256`
     …）—— 想"顺手改一个身份"在这里就会被拦住；
  4. 可选 `--host-embedding-bundle <候选 bundle>`：它必须被映射到容器路径，且容器那份与候选
     **全文逐字段相同**（不只 `model_id/dimension/provider/base_url` —— 同名 bundle 在不同
     worktree 里有 3 种内容，差别在 `query_instruct`/`query_text_type`/`batch_size`，
     只比四个身份字段会放它过去）；
  5. 对写出的文件**自动跑一遍 `check`**（产出即校验）。
* `check --image <ref> --command <文件>`：只读六条规则（下面 §4）。

**为什么不另写"容器模板"**：模板会有第二套 identity 需要同步，迟早漂移；而草案本身随 live 线演进。
从草案出发 + 逐项断言，"哪些字段必须一字不差、哪些字段允许且必须被替换"是**可 review 的白名单**，
比"再写一份文件"少一整类错误。这也是本次能顺带发现"草案两个宿主路径不存在"的原因 —— 断言过程
必须逐个 token 交代。

**风格**：`ruff check` 在两个版本下都通过（项目 `justfile` 钉的 `ruff@0.8.0`，与机器上的 0.15.10）；
**没有**跑 `just format` —— 实测这个仓库本身就有 51/111 个 Python 文件会被 `ruff@0.8.0 format` 改写
（而且它会把 `and '"' not in token` 拆成两行），按 "no drive-by formatting" 保持与邻居一致的手写风格。

---

## 3. 候选 bundle 在容器里从哪来：**账本模式**（`deploy/docker/ledger/` + Dockerfile COPY）

**实测依据（v1.1 镜像）**：候选 bundle **不在镜像里** —— 两条可能路径都不存在：
`/home/…/data-rebuild/.agents/runs/embedding-model-switch-v2/…` ✗、
`/home/…/embedding-switch-line/.agents/runs/embedding-model-switch-v2/…` ✗。
镜像里能走的只有账本那条：`s12a/recorded-decision-bundle-v1.json` ✓、`s12c/qwen-embedding-bundle-v1.json` ✓
（`Dockerfile:143-146` 两次 COPY）。

**三条理由**：
1. **与既有约定一致**：s12a/s12c 两份账本本来就是这么进镜像的（Dockerfile 注释写明"解析期真正会读"）。
2. **`.dockerignore` 今天是"恰好"不排除 `.agents/`**（仓库根 `.dockerignore` 的注释甚至写着"不排除任何
   服务运行所需的代码或账本文件"），但那是构建上下文的偶然性 —— 取决于用哪棵树做上下文；
   账本 COPY 是**显式清单**，谁都能 review。
3. 直接引用 `.agents/runs/embedding-model-switch-v2/…` 只在"正好拿 switch 线那棵树当上下文构建"时成立
   —— 本次实测就破了。脆弱。

**v2 出包要做的动作**（三条，缺一即 §4 的检查会红）：
1. 把候选 bundle 放进 `deploy/docker/ledger/`（下一轮做 v2 重打时）；
2. `Dockerfile` COPY 到命令文件引用的**同一个**容器路径。建议**保留候选自己的 basename**
   （`s12c/qwen3.7-text-embedding-flash-embedding-bundle-v1.json`），这样路径自解释、与宿主草案的
   name token 一致；工具对映射目标没有命名要求，但"看到名字就知道是哪条路线"对后面维护的人值钱；
3. 如果运行期有写死的 bundle sha 常量（上一轮记的 `_QWEN_EMBEDDING_BUNDLE_SHA256` 一类），
   必须**同一次改**。

---

## 4. 新增检查 + 判红演示

### 4.1 `check` 的六条规则

| # | 规则 | 依据 |
|---|---|---|
| ① | 每个**运行期会读**的绝对路径必须在镜像里存在（`--recorded-decision-bundle`/`--recorded-embedding-bundle`/`--recorded-serving-bundle`/`--serving-pack`/`--index-root` + launcher） | 服务启动就打开它们 |
| ② | **数据面**路径（默认 `/var/tmp/mirothinker-data-v2`、`/var/tmp/mirothinker-canonical-v2-s12f`）不要求内容存在，但**挂载点**必须在镜像里 | 内容由 compose 挂载提供 |
| ③ | **惰性路径**（`--source-manifest`/`--envelope-output`/`--accepted-original-milvus-path`/`--candidate-staging-root`/`--accepted-backup-gate-root`）只提示不判红 | v1.1 交付件本身就有 3 条不在镜像里的文件，而服务正常起 —— "每条绝对路径都必须存在"要按"读不读"分类 |
| ④ | 禁止宿主构造：`PYTHONPATH=`、`$(…)`/反引号、`*_API_KEY=`（**只报名字，不回显取值**） | 容器里全部由镜像 venv / 挂载 key 文件提供 |
| ⑤ | 禁止未解析的 `__STEPn_…__`；identity 旗标齐全；`--index-marker-sha256`/`--source-manifest-sha256`/`--recorded-serving-bundle-sha256` 必须 64-hex；端口必须钉死 `18188` | 冻结命令文件的语义 |
| ⑥ | 记录的 serving bundle **自述字段**必须与对应旗标一致：`content_sha256`↔`--recorded-serving-bundle-sha256`、`release_id`↔`--candidate-release-id`、`database_name`↔`--expected-database`、`index_root`↔`--index-root`、`envelope_path`↔`--envelope-output`、`embedding_model_id`↔嵌入 bundle 的 `model_id`（另查 `index_target_id == index:<release_id>`、`database_target_kind == disposable`） | 这几条是运行期的 `ValueError`（`load_recorded_serving_inputs`，`knowledge_serving_isolated.py:6577-6594`），任一条不符服务**起不来**。这一条是复核 v1.1 时发现的"少了一层"：原以为只要 sha 是 64-hex 就够，其实 bundle 自述与旗标是逐条比对的 |

### 4.2 判红演示（`raw/12-serve-command-container.txt`，四段 + `raw/12b-pytest-mutation.txt`）

| 段 | 输入 | 期望 | 实得 |
|---|---|---|---|
| ① | **v1.1 交付件**（已是容器命令文件）打真镜像 | 0 | **exit 0**：运行期会读的镜像内路径 4 个（缺 0）；数据面 5 个；serving bundle 自洽 6 条 |
| ② | **宿主草案**打真镜像 | 1 | **exit 1**：`PYTHONPATH=`、`$(…)`、`CANONICAL_V2_EMBEDDING_API_KEY=…`、两个未解析占位符、两个 sha 非 64-hex、5 条宿主路径不在镜像里（launcher / 宿主 python / switch 线 src 树 / 候选 bundle / serving-bundle-fembed） |
| ③ | `convert`（真 v1.1 镜像）：把草案的 identity 搬进容器 | 1 | **exit 1**，两条独立原因：容器账本与候选**不是同一份内容**（`model_id/dimension/provider/base_url/schema_version/api_key_source/batch_size/query_instruct`… 8 个字段都不同，打印时按字段列出）；serving bundle 是上一版封的包（`release_id`/`database_name`/`index_root` 三项不符）⇒ 正是"光换路径不够，账本内容要按本发布重封" |
| ④ | `convert`（构造的"v2 出包后镜像形状"树，`--probe-root`） | 0 | **exit 0**：identity 逐字保留、占位符 2 个已解析、宿主构造已丢、候选 bundle 与容器账本**全文逐字段一致（12 个字段）**、serving bundle 自洽 6 条 |

**测试有没有牙（变异测试，`raw/12b-pytest-mutation.txt`）**：基线 9/9 绿；把"路径存在性检查"拆掉 ⇒
3 条路径类测试红（`fake_path`/`data_plane_mount`/`host_constructs`）；把"bundle 读取"拆成永远 None
（= 身份比对静默跳过，正是我第一版的真 bug）⇒ 5 条身份类测试红。两轮变异后工具 sha256 与变异前一致
（脚本 `trap` 还原并核对：`37e81246…`）。

9 条测试各自的锁：`a_fake_path_is_red`（假路径必红）、`a_fully_present_tree_is_green`（全存在必绿 +
数据面内容可以不建）、`a_missing_data_plane_mount_point_is_red`（挂载点必须在）、
`host_constructs_and_unresolved_placeholders_are_red`（宿主构造 4 类 + 不回显密钥取值）、
`convert_keeps_identity_and_only_replaces_mapped_tokens`（identity 逐字 + 占位符解析 + 碎片不留）、
`convert_is_red_when_the_container_bundle_is_another_identity`（跨向量空间必红）、
`convert_is_red_when_the_container_bundle_is_the_other_role_twin`（同身份、异角色内容必红 —— 锁住
"5 棵 worktree 3 种内容"那个陷阱）、`a_serving_bundle_from_another_release_is_red`（跨发布必红）、
`convert_is_red_when_the_candidate_bundle_is_not_mapped`（候选 bundle 没进账本必红）。
夹具全部是**构造场景**（`--probe-root` 假镜像树 + 自造草案），不需要 docker、无网络。

---

## 5. 与宿主草案的**身份字段对齐**

同一件事的两个 checker，分工不是二选一：

| | 宿主侧 `check-cutover-command.sh`（他的） | 容器侧 `serve-command-container.py check`（这个） |
|---|---|---|
| 树钉法 | 必须有 `PYTHONPATH=<switch>/apps/miroflow-agent` | **必须有**镜像 venv 的 editable 钉法（即：**不许**有 PYTHONPATH） |
| launcher | 必须指向 switch 线 | 必须指向 `canonical-v2-s11-consolidation`（镜像里 = `/opt/mirothinker`） |
| 凭据 | 必须有 `CANONICAL_V2_EMBEDDING_API_KEY` | **不许**有（挂载 key 文件 + entrypoint 投影） |
| 两个 sha | 填完后必须 64-hex（§6） | 同左，且 `content_sha256` ↔ `--recorded-serving-bundle-sha256` 必须相符 |
| 嵌入路线 | 必须点名 native bundle、不得点名 `-openai-compat` | 容器路径存在 + 与候选 bundle **全文逐字段一致**（12 个字段；只比 4 个身份字段会漏掉角色孪生） |
| 数据面/惰性路径 | 不查 | 分类查（运行期会读的必须在镜像里） |
| 包名/发布身份 | 必须带 `serving-pack-fembed-v1`/`index-v4-v2`/`candidate-v2-20260922-r1` | 原样继承，且与 serving bundle 自述一致 |

**对齐机制**（同一窗口只填一次、两边同源）：
1. **占位符**：两边都从 step 7（索引 marker）与 step 10（serving bundle sha）取值。他的 §6 是"填完后
   正则查 64-hex"；我的 `convert --map __STEP7_…__=<值> --map __STEP10_…__=<值>` 是"填进去"，
   `check` 再查 64-hex。**同一次取值、同一份值**。
2. **identity 旗标**：`convert` 断言"除显式映射的路径参数外逐字不变" ⇒ 容器文件的
   `--candidate-release-id`/`--run-id`/`--source-manifest-sha256`/`--index-marker-sha256`
   与宿主草案**逐字节相同**（测试里就是按原字符串断言）。
3. **bundle 身份**：容器侧两份 bundle 必须与"这次发布"对得上（§4.1 ⑥）—— 宿主的候选 bundle 内容
   经账本 COPY 进镜像后，**全文逐字段**与宿主候选一致（工具里 `--host-embedding-bundle` 就是干这个；
   出包前先点名是哪棵 worktree 的那一份，见 §1 末）。

---

## 6. `install-site.sh` 的 token 校验：结论（只报告，未改）

问的"v2 换包名时是报错还是静默放过"——**两者都不是，是警告（warn），安装照样 exit 0**：

* `install-site.sh:128-137`：命令文件覆盖件里没有 `--serving-pack .*serving-pack-run16-v11` ⇒
  **warn**（`:133`），缺文件 ⇒ warn（`:136`）；
* `install-site.sh:138-156`：入口覆盖件里没有 `PACK_DIR="${DATA_ROOT}/serving-pack-run16-v11"` ⇒
  **warn**（`:142`），不可执行 ⇒ fail（`:145/:149`）。

`warn()` 只累加计数并进汇总（`:74`），退出码只看 `FAIL`（脚本尾 `exit 0`/`exit 14`）。所以：

* v2 换包名 ⇒ **必然两条假 warn**（噪音，甲方运维会学到"看到这两条可以不管"）；
* 真正危险的那种情况 —— **两份覆盖件各自指向不同的包**（改名做了一半）—— **不会被拦**：两条
  检查都只跟写死的 v1.1 名字比，彼此不交叉验证 ⇒ 装完、起服务时容器 exit 78。

**建议（由母 agent 定，未动手）**：把校验改成"两份覆盖件**彼此**必须同名"：
从命令文件取 `--serving-pack .*/(\S+)` 的 X、从入口覆盖件取 `PACK_DIR="${DATA_ROOT}/(\S+)"` 的 Y，
`X != Y` ⇒ **fail**；与 v1.1 冻结名相同只作提示（首次 v1.1 安装仍可保留 ok 文案）。

---

## 7. 没验到的、留给 v2

1. **真 v2 镜像上的绿**：本轮真镜像只有 v1.1（它绿），④ 的绿是**构造树**。v2 出包后要拿 `check` 打
   真镜像跑一次（命令文件指向的每条运行期路径都存在）。
2. **候选 bundle 进账本 + Dockerfile COPY + 运行期常量**：三件事必须同一次改（§3）；**并且要点名
   用哪一棵 worktree 的那一份**（同名文件 3 种内容，实测见 §1 末）—— 建议把候选那份的
   `content_sha256` 一并记进出包说明，后面的人一眼能核对。
3. **step 10 封的 serving bundle**：出包时字节一致 COPY 进镜像（不要重排 JSON、不要改字段），
   否则 `content_sha256` 与自己不符 ⇒ 运行期 `ValueError`（§4.1 ⑥ 会在打包前拦下）。
4. **宿主草案那两个不存在的路径**（§1 顺带发现）归宿主侧。
5. **`build-site-bundle.sh` 的转换点**：v2 出包建议把它从 `sed` 换成调用本工具（`convert` + `check`），
   把这个缺口焊死；本轮未改出包脚本（不在切片内）。
6. **install-site.sh 的两条 warn**（§6）建议的"互相校验"未实现。
