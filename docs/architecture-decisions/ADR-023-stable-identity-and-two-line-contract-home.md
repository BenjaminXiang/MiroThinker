---
id: ADR-023
title: 稳定身份（stable_uid）与两线契约唯一源（single contract home）
status: proposed
date: 2026-09-11
plan: docs/plans/2026-09-10-system-completion-plan.md
---

# ADR：稳定身份（stable_uid）与两线契约唯一源（single contract home）

> **状态：proposed（草案）｜最终由用户拍板，本稿不改 status。** 2026-09-11 ｜ 流：close-workbook-gaps / C 系列收口。
> 本稿是主计划 §5「新设计 · 两线契约家规（single contract home）」决策项的 ADR 草案：只做决策记录，
> **不含实现、不改任何代码、不动 serving worktree**。
>
> **依据（本文数字的唯一来源，一切引用给「文档 + 节号」）**
>
> | 别名 | 文件 |
> |---|---|
> | G2 | `.agents/runs/close-workbook-gaps/g-series/g2-identity-audit.md` |
> | G1 | `.agents/runs/close-workbook-gaps/g-series/g1-field-contract-draft.md` |
> | G3 | `.agents/runs/close-workbook-gaps/g-series/g3-category-anchoring.md`（附录 `g3-appendix-tables.md`） |
> | plan | `docs/plans/2026-09-10-system-completion-plan.md` |
> | d05 | `.worktrees/canonical-v2-s11-consolidation/.agents/runs/close-workbook-gaps/d0-probe/d05-findings.md`（行号锚 commit `04e15966`） |
> | C2 现场 | `.agents/runs/close-workbook-gaps/{c2-scratch-boot-failure,c2-reseal-blocked,c2-seal-blocked,c2-boot-blocked-supplementary}.md`、`verification-c2.md` |
>
> 关联产物：入库质量门契约 v1 提案 `.agents/runs/close-workbook-gaps/c1-gate-contract-v1-proposal.md`（字段阈值/锚定/gate 形态）。
> 本 ADR 与目录既有 ADR-012 ~ ADR-022（canonical-v2 各项约定）并列；不覆盖、不修改其中任何一条。

---

## 1. 背景与问题

### 1.1 症状：C2 的四道门是「两线契约漂移」的四种表现

C2（run14 数据薄加载上线）路径上连续出现四次 fail-closed / 阻塞，每一次都被单独定位为"某处代码或契约脱节"，
合看则同源：**数据线（构建）与 serving 线（加载/服务）各自演化，没有任何"唯一契约源"约束二者**（plan §5 立项）。

| # | 门（表现） | 实测事实 | 出处 |
|---|---|---|---|
| ① | 半封印包 manifest 索引语义绑定陈旧 | manifest 的索引绑定仍是 p4 铸包值（2026-08-26，绑定 2026-08-25 索引 36,899 points / 32,941 docs），包内实际是 2026-09-08 run14 物化（51,029 points / 47,071 docs）→ `ServingPackIntegrityError` | `c2-scratch-boot-failure.md` |
| ② | relationships.json candidate 段旧契约 | 单数组世代，部署线模型不可 parse（20 条 pydantic 错误） | `c2-reseal-blocked.md` |
| ③ | 真身信封与 serving 线两处代差 | ③a `IndexProjectionRequest.supplementary_field_values` 字段缺失（契约级，封印器第一步 fail-closed）；③b 信封校验器**内嵌完整 build 重放**，要求 build 级对等（`_public_embedded_content` / `_vector_points` / `_lookup_documents` 的 enrichment 消费，4 hunk 共 47 行） | `c2-seal-blocked.md`（含追加节）、`verification-c2.md` §1 |
| ④ | `_supplementary` 剥键块缺失 | sealed 包 903 篇（company 899 / professor 4）lookup_content 烘入 `_supplementary` 键；serving 线读侧无剥键块 → 启动在**查询/加载路径** fail-closed（前三个在封印/loader/索引模型） | `c2-boot-blocked-supplementary.md` |

口径说明：`verification-c2.md` §1 记「三个阻塞」（其中第三个含 ③a/③b 两面），主计划 §3（C6 行）与 §5 称
「C2 的四层阻塞类 / C2 四道门」——同一组事实的两种计数口径，本 ADR 按四行计。

代价形状：四次都是**环境链路上的时间与注意力损耗**（包被拒绝 → 停下 → 定根因 → 移植 → 重跑），
而不是线上故障；封印器与加载器的 fail-closed 本身是**保护**（plan §5「保留」清单），坏的是每次都要人肉重新发现漂移。

### 1.2 G2 实测：身份（identity）契约与下游假设错配

- **跨 release id 100% 换血**：s12f→run14，四域所有可匹配自然键（company 精确名 1,733 对、professor 姓名 1,391 对、
  paper DOI 494 对、patent 号 1,931 对）的 `canonical_object_id` **无一保留（0 对相同）**（G2 §3.1）。
- **33% 是纯损耗**：上述 1,733 对 company 中，575 对（33%）16 字段快照逐字段一致、仍换了 id（G2 §3.2）；
  没有任何一对保住 id。
- **机制已定位（行号锚点）**：`apps/miroflow-agent/src/data_agents/canonical_v2/canonical_identity_resolution.py:2219-2237`
  的 `id = {entity_type}-c- + sha256({release_id, entity_type, sorted(source_identity_ids), generation_key})[:24]`——
  **`release_id` 进了铸造哈希**，且两代之间没有任何持久身份状态承接，换发布必换 id（G2 §3.3）。
- **代内自洽、跨代即断**：包内绑定引用完整性是好的（run14 专利→公司 7,650 条 / 963 个公司 id、dangling 0），
  但跨代全断——优必选绑定 58→450 条围绕全新 id（G2 §3.5、§3.6#4）。
- **下游把它当持久主键用**：serving 引用/答案、关系产物、对话记忆、缓存、评测夹具都存 `canonical_identity_id`——
  内容寻址 + 代际作用域的 id 被当成持久主键，是**契约错配**（G2 §3.3、§3.6#5）。
- **碎片化使合并必须同时发生**：company 品牌核口径 72 簇 / 146 文档（97% 为 2 文档簇），其中 30 簇（42%）
  强证据互斥（地址+法代；如华芯、海思、顺丰科技 vs 顺丰控股）**禁止自动合并**；`credit_code`/`registered_capital`
  全库 7,089 篇全空，没有统一社会信用代码可作合并锚点（G2 §1.1、§2.2、§2.3#3）。

### 1.3 为什么必须现在决定

- **C6 依赖本决定**：主计划 §3 C6 已把「两条线契约一致性检查纳入封印步骤（漂移即拒封）」写进验收；
  plan §5 明确「这是 C6 周期更新能否轻量的前提」——契约唯一源不定，C6 就只能靠每代全量重指 + 现场排障。
- **执行序列定位**：plan §5「B3+B2 验收 → 两线契约家规 ADR（主上下文起草）→ S2 解耦 → S3 删减」——本 ADR 在 S2/S3 之前。
- **代价随代际累积**：不修复则每代都要对全部下游引用做一次重指/失效处理（G2 §3.6#5）；碎片化随规模放大
  （run14 较 s12f 新增公司 5,356 档 = 4.1×，同品牌多档更多；G2 §3.1、§3.6#4）。

### 1.4 问题陈述：两个正交问题族

| 问题族 | 内容 | 证据 | 可选方案 |
|---|---|---|---|
| **I · 契约漂移**（code/interface drift） | 同一逻辑（索引投影、信封、加载契约）在两线各有一份实现，任何一侧领先即 fail-closed | C2 四道门（§1.1） | 案 A / 案 B（§2） |
| **II · 身份不连续**（identity continuity） | 版本化 id 被当持久主键；换 release 即换身份，跨代引用、对话记忆、夹具全断 | G2 §3（§1.2） | 案 C（§2） |

两族**可分别决策**（实现路径不同、验收 KPI 不同），但共享同一条原则：
**"跨代/跨线存活的产物，只能锚定显式契约声明的东西，不能锚定实现细节或作用域内标识。"**
多数场景下 I 与 II 同时成立——本 ADR 因此把两族放在同一份记录里，但**推荐意见与待裁项分开列**（§3、§5）。

---

## 2. 选项分析

### 2.0 坐标系

- 案 A、案 B 回答问题族 I（契约住在哪里、谁来闸门）。
- 案 C 回答问题族 II（身份怎么跨代连续）；其中 C-1（interim）与 C-2（ledger）是**同一方案的过渡态与目标态**，
  而不是互斥选项。
- 下述每案的「对 C6 的意义」按 plan §3 C6 验收口径（换一版包 + 回滚一次；更新后四轴证据不降）评估。

### 2.A 案 A：合并两线为一线（single code line）

- **做法**：数据线与 serving 线的 `canonical_v2/` 收敛为同一份代码、同一发布节奏（同一工作区 / 同分支),
  不再各自演化；"两线"概念取消。
- **代价（有实测）**：两线 `canonical_v2/` 现有 **16 项文件差异**（`verification-c2.md` §2），其中
  `knowledge_build_isolated.py` 1,295 行、`canonical_decision_postgres.py` 969 行、`knowledge_read_isolated.py` 338 行、
  `knowledge_serving_isolated.py` 306 行等 **14 个文件"代差未核"**；另有数据线私货的 dev 后门
  `SERVING_PACK_SKIP_HASH_VERIFY=1`（哈希校验环境旁路 18 行，serving 线正确地没有）。数据线依赖
  postgres/milvus/embedding 全链与重构建（封印相位 `envelope_validate` 实测 2,124.3s，`verification-c2.md` §3），
  serving 线只要 pack + 只读薄加载、且受"无 GPU / 单索引锁 / 端口硬钉"运行约束（plan §4.1）；合并会把两套约束绑在一起。
- **迁移**：一次性把 16 项差异全部收敛 + 全链回归（hermetic pack 21 + B1 聚焦 96/26 + fast_boot/embedded_content 14，
  `verification-c2.md` §1 的回归清单）；此后所有改动同时触及两条线。
- **回滚**：**难**。合并是代码历史级决策，回滚 = 重新分叉到今天的形态，代价等同重做一次；
  可借助分支/开关降低单次风险，但"两线"一旦取消没有局部回退面。
- **对 C6 的意义**：漂移类故障结构性消失（"一致性检查"这个机制不再需要）；但 C6 的更新流水线将被迫与
  serving 发布共用同一节奏与同一回归成本——与"轻量更新"的目标方向相反。
- **注**：A 案不解决问题族 II（身份不连续）；选 A 也仍需在 C 案上单独决策。

### 2.B 案 B：共享契约模块 + 封印器唯一闸门（现状加强版）

- **做法**：抽出**唯一契约源**（两线共同依赖的 `canonical_v2/contracts` 或等价模块：Pydantic 模型 +
  被"重放"的投影/索引语义函数），封印器作为**唯一闸门**在封印时做契约一致性检查；两线其余实现
  （如 postgres 持久化侧、构建管线主体）允许继续差异演化。plan §5 的诊断即"漂移即拒封已具备，
  缺『契约唯一源』"——本方案补的正是这一块。
- **契约源范围（由 C2 教训界定）**：③b 证明**封印路径要求 build 级对等**（信封校验器内嵌完整索引投影重放，
  `c2-seal-blocked.md` 追加节），故契约源至少要覆盖被重放的文件（`index_projection.py`、
  `domain_projection_models.py` 这一层）；`knowledge_build_isolated.py` 1,295 行差异**不在**本方案要求内
  （它不出现在"封印所需重放"里）。
- **代价**：需要一次性界定"什么进契约源"（清单制，见 §5 Q2）；被纳入的文件须接受"两线逐字节一致"的约束，
  双侧改动流程变长（一方改、另一方同步）。
- **迁移**：**已有可复制的成功样例**——C2.1p/q 后 `diff` 两线 `index_projection.py`、`domain_projection_models.py`
  均无输出（零漂移，`verification-c2.md` §1）；把该模式从两个文件扩大到一个显式清单即可，清单可增量生长。
- **回滚**：**易**。契约源清单可增可减；某文件重新分叉 = 退出清单（同时放弃其跨线兼容保证），不触发全链返工。
- **对 C6 的意义**：封印步骤的"契约一致性检查"成为 C6 的天然一环（plan §3 C6 行已写"漂移即拒封"）；
  本方案把"事后发现漂移"升级为"结构上不产生漂移"。轻量更新的前提（少一次人肉排障）在此达成。

### 2.C 案 C：interim（铸造哈希去 release_id）+ 长期 ledger stable_uid

**C-1 interim（一行改动 + 重铸一版）**

- **做法**：把 `release_id` 从铸造哈希输入中移除（G2 §3.3 代码锚点），全量重铸一版。
- **收益上界**：最受益面 = 575/1,733（**33%**）"内容零变化仍换 id"的对（G2 §3.2），
  且前提是 source 集合与 `generation_key` 也不变（G2 §4.3 备选段）。
- **代价**：一次全量重铸 + 关系重指（本来每代都发生）+ 打破"id 是 release 作用域"的隐性约定；
  **不解决跨代引用承接问题本体**（G2 §4.3 备选段）。
- **迁移**：一次重铸即完成；**回滚**：恢复含 `release_id` 的旧实现（但已发出的 id 不会退回）。
- **对 C6 的意义**：**不改变**更新流水线的重指负担，只是把它变小一点；每代仍要全库重指（G2 §3.6#5）。

**C-2 长期 ledger + stable_uid（G2 §4.3 协议骨架）**

- **做法**：`stable_uid` 实体级稳定号，一次分配、永不重铸（opaque，建议 `company-uid-<ULID>`），由
  **identity ledger**（起步 SQLite 表即可）唯一持有；`canonical_identity_id` 保留为"当代版本 id"
  （内容寻址、审计可复现不变）；ledger 存 `stable_uid ↔ (release_id, canonical_identity_id)` 全代映射 +
  事件日志（merge / split / rename，含 decision id、生效 release、survivor 规则），历史 canonical id
  一律保留为 alias；所有跨 release 存活的产物（关系边、专利申请人绑定、对话记忆、缓存、评测夹具、看板）
  **只写 stable_uid**；pack 构建时由 ledger join 出当代 canonical id 写入 lookup 文档（新增 `stable_uid` 字段），
  读侧对内解析当代 id、对外输出 stable_uid（G2 §4.3#1–#4）。
- **家规条文（直接进本 ADR 的 R1–R4，G2 §4.3#5 原文）**：
  - **R1（引用面）**：跨 release 存活的产物禁止存 `canonical_identity_id`，只允许 stable_uid 或自然键。
  - **R2（构建面）**：pack 必须携带 stable_uid 映射；所有绑定产物必须可 join 回当代 canonical id，dangling 必须为 0。
  - **R3（变更面）**：identity 合并/拆分必须产生 ledger 事件（含 decision id），禁止静默重铸。
  - **R4（验证面）**：相邻 release 的 stable_uid 保持率进入发布门（KPI 见 §4）。
- **代价（G2 §4.4）**：新增持久状态（备份/回滚/幂等校验义务；ledger 损坏 = 全库身份不可解析，高 blast radius
  ⇒ 只增日志 + checksum + 双备份）；**公开契约变更**（lookup schema、关系/绑定产物、serving 读路径、评测夹具）
  ⇒ 需 OpenSpec change + 迁移/回滚方案，兼容期双写→双读→切换约两个 release 周期；未建 ledger 的历史代
  只能按自然键尽力映射（不保证 100%）；人工复核成本（宽口径候选 42% 互斥，需裁决队列；自动合并负样本必须为 0）；
  merge/split 的 survivor 规则、别名历史、事件写入方（构建器）都要定死。
- **迁移**：分阶段双写→双读→切换；历史代回填依据是自然键跨代命中率 98.7%–100%（G2 §3.1、§3.6#3）。
- **回滚**：ledger 只增不改，回滚 = 读侧退回只认 `canonical_identity_id`（`stable_uid` 字段保留、无人读），
  不丢数据但失去已积累的承接能力；ledger 本体需备份/恢复演练（§5 Q6）。
- **对 C6 的意义**：**这是让 C6 轻量的关键**——跨代引用不断，更新不必每代全量重指（KPI §4 #1/#3）。

### 2.4 三案对照

| 维度 | A 合并两线 | B 共享契约源 + 封印闸门 | C-1 interim | C-2 ledger |
|---|---|---|---|---|
| 解决问题族 | I | I | II（部分） | II |
| 实测成本面 | 16 文件差异（14 未核）+ build 链形态冲突 | 被重放文件层（当前 2 个已零漂移） | 一行 + 一次全量重铸 | 新持久状态 + 公开契约变更 + 约两个 release 兼容期 |
| 迁移难度 | 高（一次性全清） | 低-中（清单增量） | 低 | 中-高（双写/双读/切换） |
| 回滚难度 | 难（不可局部回退） | 易（清单减项） | 易（恢复旧实现） | 中（读侧退版；ledger 保留） |
| 对 C6 的意义 | 漂移消失但更新变重 | 漂移结构上不产生（C6 前提达成） | 重指负担略减 | 跨代引用不断（C6 真正轻量） |
| 前置条件 | 接受两线同节奏 | 界定契约源清单 | — | OpenSpec change + 产品/架构裁定（§5） |

---

## 3. 推荐（建议，**最终由用户拍板**）

**推荐组合：B（问题族 I） + C-2 ledger（问题族 II）；C-1 interim 作为独立小决策另裁。**

1. **问题族 I 推荐案 B**。理由：A 的代价集中在 14 个未核差异与 build 链形态冲突上，且不可局部回滚；
   B 已有 C2.1p/q 的可复制成功样例（两个文件零漂移），渐进、可回滚，并且与现状"封印器唯一闸门"兼容
   （只补契约唯一源）。**若选 A**，前置条件是先完成 14 个未核差异的定性与两线节奏统一方案（§5 Q12）。
2. **问题族 II 推荐 C-2（ledger + stable_uid）**。理由：C-1 的收益上界只有 33%（575/1,733，G2 §3.2）
   且不解决跨代承接本体；ledger 正是当前缺失的"持久身份状态"（G2 §4.3 末段）。**C-1 是否单独先做**
   （换一次全量重铸换 33% 的止血）建议作为独立小决策——若判定"再破一次 id 作用域约定的成本 > 33% 收益"，
   则跳过 interim 直接做 ledger（**本节为建议，需拍板**，见 §5 Q3）。
3. **两族推荐终态叠加为**："B 的契约源内两线逐字节一致（C2.1q 形态即样板）" + "R1–R4 家规生效、
   stable_uid 进发布门"。
4. **适用条件**：① 契约源清单可界定且清单内文件的两线同步成本可接受；② ledger 的公开契约变更获得
   OpenSpec change 与迁移/回滚方案；③ §5 的产品类裁定（论文版本档、同名同机构、行业词表、展示名）先有结论——
   ledger 的 merge/split 语义依赖它们。
5. **本 ADR 不定稿**：`status: proposed`，接受前不改动任何代码路径；C1 入库质量门实施（plan §3 C1）在
   身份侧只做"占位过滤 + 告警"，不做自动合并（见 C1 提案 §4）。

---

## 4. 验收 KPI（引 G2 §4.5；数字唯一源 = G2，本文不另设）

| # | 指标 | 当前基线 | 目标 | 出处 |
|---|---|---|---|---|
| 1 | stable_uid 跨代保持率（排除真 merge/split） | 0%（id 全换） | 100% | G2 §4.5#1 |
| 2 | 绑定 dangling（包内可解析） | 0（两代均 0） | 保持 0 | G2 §4.5#2 |
| 3 | 跨代引用解析率（对话/缓存中旧引用在新代可解析） | 不可解析 | 100%（ledger 期内） | G2 §4.5#3 |
| 4 | 合并实体字段冲突的 resolution 覆盖率 | 无机制 | 100%，抽检 ≥95% 合格 | G2 §4.5#4 |
| 5 | 强证据互斥簇的自动合并数（负样本 30 簇） | 无机制 | 0 | G2 §4.5#5 |

**建议新增（问题族 I 侧；本 ADR 提出、待裁，§5 Q11）**：

| # | 指标 | 当前 | 目标 |
|---|---|---|---|
| 6（建议） | 契约源清单内文件的两线 diff | 已纳入 2 个 = 0；14 个未核未纳入 | 清单内恒 0 |
| 7（建议） | 因契约漂移导致的封印/启动 fail-closed 次数 | 4 次（C2 记录在案的阻塞事件，§1.1） | 0（漂移在设计期被拦截，不作为现场故障出现） |

字段/类目侧 KPI（字段阈值、类目锚定、覆盖目标）唯一数字源在 C1 提案 §6，本 ADR 不复制。

---

## 5. 待裁清单（需用户 / 主上下文决定）

| # | 待裁项 | 背景 | 归属 |
|---|---|---|---|
| Q1 | **问题族 I 选 A 还是 B**（本 ADR 推荐 B） | §3.1 | 用户 |
| Q2 | 契约源的物理形态与归属：`canonical_v2/contracts` 子包 / 独立 lib / 生成物；谁拥有、如何版本化 | plan §5"缺契约唯一源"；§2.B | 主上下文 + 用户 |
| Q3 | C-1 interim 是否单独先做（33% 止血 vs 再破一次作用域约定）；若做，与 ledger 的先后 | G2 §4.3 备选段、§3.2 | 用户 |
| Q4 | stable_uid 编号策略（ULID vs 顺号） | G2 §4.4-4 | 用户 |
| Q5 | ledger 归属：数据线构建器 vs 独立治理服务 | G2 §4.4-4 | 用户 |
| Q6 | ledger 的爆炸半径运维口径：备份/checksum/双备份的保护强度与演练要求（"只增不改"是否加审计写保护） | G2 §4.4 代价段 | 主上下文 |
| Q7 | 论文"预印本 vs 期刊版"是否同一实体（6 对全属此类，DOI 各不相同） | G2 §4.4-1、§1.3 | 用户（产品） |
| Q8 | professor 同名同机构 9 簇是否同人（建议人工确认后写死判定规则） | G2 §4.4-2、§1.3 | 用户（产品） |
| Q9 | 行业分类统一词表（`机器人` vs `物流运输` 等）——合并时不做单值覆盖，映射表归谁 | G2 §4.4-3、§2.3-2、§4.2 | 用户（产品） |
| Q10 | 碎片化实体的"合并后展示名"规则（法定名 vs 品牌短名） | G2 §4.4-5 | 用户（产品） |
| Q11 | 是否采纳 §4 的两条建议 KPI（契约源 diff、漂移 fail-closed 次数）及其计量方式 | §4 | 主上下文 + 用户 |
| Q12 | 14 个"代差未核"文件是否要求全面零漂移（`verification-c2.md` §2 注：本切片只动 `index_projection.py`，其余是"新的决策点"） | §2.A、§2.B | 主上下文 |
| Q13 | 本 ADR 的编号与文件名：目录约定为 `ADR-NNN-short-slug.md`（`docs/architecture-decisions/README.md` Conventions），本稿按日期命名并**未登记 README 索引**——是否改为 ADR-023 并补索引行 | 目录约定 | 主上下文 |

---

## 6. 边界与未决

1. **不改代码、不动 serving worktree、未 commit**：本稿是决策草案；所有实测数字引自 G1/G2/G3、C2 现场记录、plan 与 d05，未新做实验。
2. **未覆盖**：pack 可移植性/端口硬钉等 P2 交付阻断项（plan §4.1）不在本 ADR 范围；
   契约源的具体接口清单（哪些模型/函数进、哪些不进）留待 Q2 落地时的设计文档。
3. **口径冲突提示**：G 系列文档间已知口径差（如 `company.industry` usable 6,516 vs 6,517 的 `-` 计数差）
   集中在 C1 提案 §8「待裁」统一报出，本 ADR 不重复。
4. **与既有 ADR 的关系**：ADR-012 ~ ADR-022 定义的 canonical-v2 行为约定继续有效；本 ADR 只新增
   "契约源唯一 + 身份持久化"两条上层约束，不修改既有条目语义；R3（变更面）是新增义务。

---

## 7. 主上下文裁定（2026-09-11，先做后报；用户可改）

| Q | 裁定 |
|---|---|
| Q1 | **采纳案 B + 案 C-2**：问题族 I 以"共享契约模块 + 封印器唯一闸门"为形态目标；问题族 II 采纳 ledger stable_uid 协议 |
| Q2 | 契约源物理形态 = `canonical_v2` 内共享契约子包（单源，禁复制）；版本化随 release；C1 实施时细化 |
| Q3 | **不单独做 C-1 interim**（避免二次换血）；C-2 并入 C6 周期更新流水的建设推进 |
| Q4 | stable_uid = **ULID**（可排序、免协调） |
| Q5 | ledger 归属 = **数据线构建器持有**（不新建独立服务）；ledger 文件随构建产物并哈希绑定进包 |
| Q6 | ledger 保护 = 只增不改 + 校验和 + 双备份；备份/恢复演练纳入 C6 手册 |
| Q11 | 两条建议 KPI（契约源 diff 次数、漂移 fail-closed 次数）**采纳**，随周报度量 |
| Q12 | 不要求 14 个"代差未核"文件全面零漂移；要求**启动路径文件零漂移**（index_projection 已达成；serving_pack_loader 以"无后门"形态保持）；其余列入 S3 评估清单 |
| Q13 | 已改名 `ADR-023-stable-identity-and-two-line-contract-home.md` 并登记 README 索引 |

**产品级项（Q7–Q10）先做后报的默认值**（用户可改）：
- Q7 论文版本档：预印本/期刊版 = 同一 stable_uid 的**版本组**，展示按偏好去重（期刊优先），两条溯源都保留；
- Q8 professor 同名同机构 9 簇：进**人工裁决抽样**（与 30 个强互斥簇同批），判定规则定稿后再自动化；
- Q9 行业统一词表：归 C1 数据治理持有，**只做映射不覆盖单值**；
- Q10 合并后展示名：**法定名为主**、品牌短名入 aliases。
