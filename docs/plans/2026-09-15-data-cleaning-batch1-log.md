# D0-a 数据清洗第一批（规则化清洗 + 构建门）执行日志

> 日期：2026-09-15　|　需求：R21（本地优先的前提是数据质量可度量/可达标/可回归）
> 计划：`docs/plans/2026-09-15-requirements-gap-plan.md` §8（D0）§9（R9）
> 依据：`docs/plans/2026-09-15-data-quality-assessment.md`（首遍评估，只读）
> 分支：`chore/data-cleaning-batch1`（worktree `.worktrees/data-cleaning-batch1`，基线 `1ee824a7`）
> **生效时间：随 run16 重建生效；本次未改任何生产数据、未重建、未碰 18188。**

## 做了什么

把首遍评估里"机器能确定"的四项规则化清洗做成了**代码 + 测试 + 构建门**，
清洗发生在**投影层**（`domain_projection` 把决策选中的源值变成 typed 投影的
那一个点），所以 lookup 文档、向量内容、Postgres 投影同时干净；源断言（证据）
保持原样不动。

| # | 规则 | 结果（run15 副本实测） |
|---|---|---|
| 1 | 占位符归一（整值/前缀/无信息句/构建侧英文 fallback） | 15,976 处 → **0**；其中整值 `未找到` 1,817 → 0、前缀 2 → 0 |
| 2 | 粘连修复 | 189 条含 `未找到` 的粘连值 → **177 条判为"标识符/版本号被替换"→ 不发布并留档**、3 条无信息句 → 置空、**9 条属正常句子 → 保持原样并计数**（逐条列出可复核） |
| 3 | geography 补市 | 只到"广东省"的 4,887 条 → 4,885 条从 `registered_address` 规则补出城市；2 条无地址保持原样并计数；市级 601 → **5,486** |
| 4 | research_directions 垃圾隔离 | 10,238 条中 796 条垃圾（版式块 154 / 句子片段 333 / 尾部等 118 / ≤2 字 126 / 带年份履历 65）→ **不进检索字段**，全部进 side report 留档 |

## 发现了什么

1. **粘连不是"格式脏"，是内容被替换**：`DM-7未找到未找到C`、`CN2未找到2121412424.未找到`、
   `1未找到亿颗` —— `未找到` 顶替掉了原来的字符。**原字符不可恢复**，所以规则选择
   "不猜"：整值不发布、原文完整留档（`quarantine.jsonl`），不给出"看起来对"的假型号。
2. **同一批数据里有真句子**：189 里有 9 条是正常行文（如专利摘要
   "…或未找到最终目标节点的过程内…"），另有 3 条是"根据现有信息，未找到…信息。"这类
   整句无信息值（→ 置空）。两者必须分开，否则会误删真数据。
3. **首遍评估的"294 条句子片段"等类目**与我本次的规则口径略有差异（我：333），此外
   新增一类"带年份的履历/论文 dump"（65）。原因是首遍的类目只列了 4 类、且没有说死
   阈值；本次把每条规则写成了可执行定义，所以能逐族对账。
4. **验证中推翻了一条自己写错的规则**：最初用"长度 > 40 字"判"段落倾倒"，跑出来
   182 条被误判的是**合法双语研究方向**（`基于图神经网络的电路表示学习 (GNN-based Circuit
   Representation Learning)`）。已改为"含 4 位年份"这一精确信号 —— 这一条如果没做重放，
   会静默删掉真数据。
5. **对账**：整值 1,817 / 前缀 2 / 粘连 189 / 只到省 4,887 / 深圳市 554 / 方向条目 10,238
   与首遍报告**完全一致**；占位符家族总数 15,976（首遍 15,969）差 7，原因是扫描口径：
   本次遍历所有嵌套字符串（多算 `paper.venue` 5 条与专利域 2 条粘连），并按"无信息句"
   家族计入 3 条；首遍报告自身的分字段说明与其复核表在 `technology_route_summary`
   上本来就差 23。属账本口径差，不是数据差。

## 怎么验证

- 单元测试 **53 条全绿**（正/负样本均取自 run15 真值，fixtures 在
  `.agents/runs/data-cleaning-batch1/fixtures/run15-samples.json`）；
- **重放**：把 run15 的 `lookup.sqlite3` 复制到 `/tmp/dq-batch1-scratch/`（只读打开），
  用新规则在副本上重跑，前后计数对照见 `openspec/changes/data-cleaning-batch1/acceptance.md`；
  脚本 `.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py`；
- **既有套件**：`tests/canonical_v2` 全量（结果见 verification.md）；有 5 条测试因为
  钉住了旧行为（"投影里应该带着占位符"）而更新为断言新行为（占位符不发布），
  另有 1 条 `test_canonical_scope_founder_red` 在**基线分支上就已失败**（与本次无关）；
- **发行门**：`IndexProjectionBuilder.build` 在写出包之前审计，发现已发布的占位符/
  粘连/方向垃圾即 fail-closed（阈值写在 design.md），市民级 geography 比例门槛 90%。

## 影响哪些问题

- 直接兑现 **R21/D0-1~D0-4**（评估报告 §D0 表格）；
- 消除**用户可见缺陷**：公司答案文本里会出现 `简介：未找到` / `技术路线：根据现有信息，未找到…`，
  这条路径没有兜底过滤（教授路径有，公司路径没有）；
- 为 **D1（LLM 复核）** 留了接口：`out/quarantine.jsonl`（973 条，含规则、原文、
  源 reference_id）；带年份履历类另见同文件；
- 未做（留给 D0-b/D1）：venue 合并、边去重、空行清理、死字段 schema、
  `广东省-珠海`/`苏州市`/`-开曼群岛` 3 个脏值、1,595 家完全无地域的公司、
  以及"把 side report 写进构建产物"（当前由离线脚本产出，debt 已记在 design.md）。

---

## 轮次追加（2026-09-16）：run16 第三次发射被发布门拦下 → 补上"补充通道"

**做了什么**：修 `_supplementary_field_values`（补充通道）——它把**非选中断言值**（原文、未过清洗）
直接喂给发布的向量内容与 lookup 文档；现在该通道与投影缝用**同一套规则**
（`clean_text` + 研究方向规则）。同时让发布门在失败时**点名违规值**（每类最多 4 条；
`PublicationQualityReport.*_examples`，仅诊断、不进 `as_dict`）。

**发现了什么**：run16（09-15 22:53 发射）跑到 09-16 00:32 被自家发布门拦下：
`placeholder values published: 5`。数据侧取证：run16 库四个域的**投影表里逐字符串扫
`placeholder_family` = 0 命中**（说明投影缝是干净的），5 条只能从补充通道进来——它们正是
构建自己写的兜底句（`_P4_COMPANY_PROFILE_FALLBACK` = "No dedicated summary was supplied
by the full-column workbook source." 等）与被扣下的粘连损坏值。分类器早就覆盖这些文案
（`PLACEHOLDER_PREFIX_VALUES`），只是这些值从没经过它。

**怎么验证**：新测试 `test_supplementary_publication_filter.py`（RED：兜底句与粘连值都被
发布 → 修复后 GREEN）+ `test_gate_failure_names_its_offenders`；D0-a/D1-a 相关 6 个套件
**132 passed**；修复提交 `3a9f9149`；随后 run16 第 4 次发射（09-16 11:01）。

**影响哪些问题**：① 解除 run16 第三次发射的阻断（构建期发布门第一次真实生效，抓到的正是
"未过清洗的通道"这类缺陷）；② 发布门从此可诊断（失败即点名，不用再花 1.5h 复跑定位）。

### 轮次追加续（2026-09-16 下午）：attempt 4 也是同一道门，但这次门点了名

**发现了什么**：attempt 4（11:01 发射，含补充通道修复）在 14:40 前又被发布门拦下，
错误消息第一次**点名违规值**：`placeholder values published: 5 (e.g.
paper.venue.name: 未提供期刊出处 ×4, +1)`。根因＝`_p4_paper_record` 在 P4 论文缺 venue 时
落一条**兜底 venue 引用**（`_P4_PAPER_VENUE_FALLBACK`），而 `venue` 是唯一不在
`CLEANED_REFERENCE_FIELDS` 里的引用型字段——venue 合并只做标签归一，从不跑占位分类器。
（attempt 3 的 5 条就是这 5 条；`3a9f9149` 修掉的是另一条真实泄漏，并让这一轮**可诊断**。）

**怎么验证**：`test_paper_venue_placeholder_reference_is_not_published`（RED→GREEN）＋
新不变量测试 `test_every_build_fallback_literal_is_recognized_by_the_cleaner`（构建模块里
每个 `*_FALLBACK` 字面量都必须被占位分类器覆盖，防再犯）；D0-a/D1-a 六套件 **134 passed**；
修复 `fee2fc85`；**attempt 5（14:45）**发射。

**机制（本轮新增）**：watchdog 升级为**失败报告器**——runner 一消失就落
`run16-failure-report-<ts>.md`（日志尾 + 产物体征 + triage 清单）；另设 10 分钟 cron
唤醒会话巡检（运行中/成功/失败/CPU 冻结 四态判定）。本次正是它把"hours-late 发现"变成
"立即定位"。

### 轮次追加（2026-09-16 傍晚）：venue 清洗撞上投影模型（修复后 attempt 6）

**发现了什么**：attempt 5 过了占位门，却在**类型化投影**处倒下：
`PaperProjection.venue input_value=None`——venue 清成"缺省"是对的，但模型里
`venue` 仍是必填，两者对"兜底值非法"的落点本来就不一致。修复＝把该字段改为可空
（沿用 D0-a 对教授/公司字段的同一手法）。

**怎么验证**：RED/GREEN `test_paper_projection_accepts_an_absent_venue`；
D0-a/D1-a 六套件 **135 passed**；服务线同步（run16 包会带 `venue: null`）：
`feat/serving-model-sync` `c1c17ad5` + 预合树 `c2d2c246`（**78 passed**）。
修复提交 `41a8d96e`；**attempt 6（16:13）**发射。

### 轮次追加（2026-09-16 晚）：模型放宽撞上数据库 NOT NULL（修复后 attempt 7）

**发现了什么**：attempt 6 **首次走到落库阶段**（越过了投影缝/发布门/关系播种），在
`_persist_owners` 处倒下：`NotNullViolation: null value in column "technology_route_summary"`——
D0-a 把 9 个投影字段改成可空、venue 追加为第 10 个，但 **PG 的 `current_projection` 列仍是
NOT NULL**：模型与库schema对"占位值→缺省"的落点不一致，只有真正落库才暴露。

**怎么验证**：迁移 **C2_0015** 放宽评审过的 10 列（company 2 + paper venue + professor 7；
`paper.title`/`patent.title` 保持 NOT NULL，因为清洗规则永远不会把它们清空）；冻结的
live-schema 目录 sha 在两个独立迁移的临时库上复算（`08aa5c3f…`，计数不变）；迁移范围由新
测试逐列钉住。**跨线核查（已验证非假设）**：服务线能容忍更新的库而无需同步迁移——现役服务
正在跑 **C2_0013** 的库，而它自己的链止于 C2_0012（版本检查只存在于构建侧 store）。

修复 `ca50ae68`；**attempt 7（19:06）**发射。

### 轮次追加（2026-09-16 深夜）：NOT NULL 之后的形状约束（修复后 attempt 8）

**发现了什么**：attempt 7 再次走到落库（断言 62.7 万、决策 42.3 万已写入），在 paper 投影插入处
倒下：`CheckViolation: ck_paper_current_projection_venue_shape`。C2_0015 只解了 NOT NULL，
形状约束 `COALESCE(is_valid_..., false)` 对 NULL 判**假**——同一耦合的下半层。

**怎么验证**：C2_0016 把 venue 与 department 两条形状约束改为 `(X IS NULL) OR ...`；
**同类穷举**：四个域里其余所有"无守卫 COALESCE 形状约束"都落在 NOT NULL 列上（15/15 核实），
被放宽列上的 `*_nonempty` 检查对 NULL 本来就放行（`btrim(NULL) <> ''` 求值为 NULL，CHECK 通过），
子对象表（paper.publication / professor.affiliation_history）原本就带 `IS NULL` 守卫。冻结目录
sha 双库复算（`b9befa25…`）+ 范围测试（10 passed）。修复 `84100331`；**attempt 8（22:06）**发射。

### 轮次追加（2026-09-17 凌晨）：attempt 8 全程通过 —— run16 构建成功，封印启动

**发现了什么**：attempt 8 首次穿越全部历史死点（paper 投影 24,520、四域投影提交、索引物化
3.2GB、release_continuity 校验、信封构造与回读），全程无阻断。时间线：22:06 发射 → 02:26
索引物化完成（lookup 668MB / vector_matrix.npz 1.68GB / milvus.db 1.08GB + 质量报告）→
02:30 起信封构造（内存峰值 RSS ~90GB，宿主 503GB 余量充足）→ **03:21 信封落盘
8,303,007,285 B** → 回读校验（读 8.3GB + 解析 + 逐字段比对，~70 分钟）→ 04:31 runner 正常
退出。

**怎么验证**：footer 四行齐全 —— `candidate_release_id=candidate-v2-20260916-r1`、
`receipt_sha256=331091a4…`、`handoff_sha256=ee218440…`、`envelope_sha256=a8440bdf…`；无
Traceback；无新 failure dossier（最近一份仍是 22:00 的 attempt 7）。监控三态留痕：cron 10
分钟巡检 + run16 专用 watchdog（utime 单调增长 / 信封出现 / 进程退出均被逐次记录）。另：
run10 遗留的 /tmp watchdog 把信封构造期（按设计零写盘）误报为"自旋"抓栈，反证了相位；
其一个卡死 py-spy 已清掉。

**后续**：04:34 封印发射（`build_run16_serving_pack.sh`，服务线预合树 `c2d2c246`、marker sha
`36305daf…` 两道 fail-closed 闸已过）；封印完成 → runbook §5 切包（bundle → 命令文件 → 活线
fast-forward → restart → replay 7/7 + 逐字探针 + 回滚演练）。

### 轮次追加（2026-09-17 清晨）：封印首跑失败 → 根因＝封印树缺构建线代码 → 两线合流修复 → 重发

**发现了什么**：04:34 从服务线预合树（`c2d2c246`）发射封印，sealer 在信封校验处失败：
`ValidationError: consumer_handoff.release_bundle — relationship publication authority cannot be replayed exactly`。
信封的 `IsolatedReleaseBundle` 校验会**重放**关系投影与候选投影（设计内的"一次证明"），而服务线树
缺构建线的投影代码（C1 修复、D0-a/D0-b 清洗、D1-a 等）→ replay 抛错。run15 能封是因为其信封
由合流前的旧代码产出。这不是"少一个字段"，是**两棵树不同源**——runbook 原文"封印从预合树跑"
的前提（服务线树足以重放）不成立。

**怎么修**：做真正的两线合流：新分支 `codex/canonical-v2-run16-serve`（`data/p4-serving-pack-rebuild`
→ `codex/canonical-v2-run16-ready`，worktree `.worktrees/run16-integration`），12 个冲突
（6 生产 + 4 测试 + 2 文档），逐项按"**保留服务线基线语义 + 采纳数据线已批准 change**"裁定：
- 读侧 F1 类目回退保留；数据线 identifier-token 回退**去掉调用点**（函数与单测保留，服务线自身
  的 PCB 触发机制覆盖该场景），恢复"无触发词不回退"不变量；
- `_public_citations` 采纳数据线已批准的 `fix-web-citations` + `local-citation-floor`（url-less
  本地归档卡 + current_web 来源卡），但**保留服务线的哈希公开 id**（内部 canonical id 不外泄）；
- 服务线标记机（B5.5/GAP-09 重放检测）保留；进度计时器是数据线已禁用的死代码，按服务线；
- 文档/账本按"保留双方行"。
合流提交 `4e2a3e0f`，修复提交 `8fc0fa7f`。

**怎么验证**：定向套件——miroflow-agent（serving 合同 + loader + read/serving isolated +
identifier 单测）：**384 passed**；admin-console（引用卡 + 相关契约）：**146 passed / 1 失败**，
该失败（s11a 措辞断言）**在数据线父提交上同样失败**（同点同因，既有红，非合流引入）。
05:20 从合流树发射封印（第 2 次）；封印成功后按 runbook §5 切包（活线 ff 到 `8fc0fa7f`）。

**影响哪些问题**：切包链路从"隐含假设两棵树同码"变成"显式合流一次"；此后 run17+ 的封印应直接
在合流线上跑（runbook §4/§5 的树引用需同步更新）。
