# C1 入库质量门契约 v1 提案（gate-at-import）

> 状态：**提案 / 草案（待主上下文与用户裁定）** ｜ 2026-09-11 ｜ 流：close-workbook-gaps / C1 的前置契约稿。
> 本稿把 G1/G2/G3 三份只读分析产物收口为**一份可分派的门契约**：字段阈值 + 类目锚定 + 身份合并边界 + 执行形态 + KPI + 实施顺序。
> **不含实现代码**；不改任何代码、不动 serving worktree、未 commit。
>
> **依据（本文数字的唯一来源，引用给「文档 + 节号」）**
>
> | 别名 | 文件 |
> |---|---|
> | G1 | `.agents/runs/close-workbook-gaps/g-series/g1-field-contract-draft.md` |
> | G2 | `.agents/runs/close-workbook-gaps/g-series/g2-identity-audit.md` |
> | G3 | `.agents/runs/close-workbook-gaps/g-series/g3-category-anchoring.md`（附录 `g3-appendix-tables.md` 记 G3-A） |
> | plan | `docs/plans/2026-09-10-system-completion-plan.md` |
> | d05 | `.worktrees/canonical-v2-s11-consolidation/.agents/runs/close-workbook-gaps/d0-probe/d05-findings.md` |
> | ADR | `docs/architecture-decisions/ADR-2026-09-11-stable-identity-and-two-line-contract-home.md`（本稿的身份侧指针） |
>
> 数据基线：run14 封印包 `release candidate-v2-20260819-r1`，company 7,089 / paper 24,520 / patent 11,504 /
> professor 3,958 = **47,071** public_domain 文档（G1 §1、G3 §2.1）；d05 §3.2 的"填充数"为 raw 口径
> （usable + placeholder），本文一律用 G1 的 usable 口径（G1 卷首计数口径）。

---

## 1. 范围与原则

1. **"库内可穷尽"是不变式**：本地库定位 = 代表性 + 引导 + **在库内尽量穷尽**；入库治理的目标是
   "库内实体可被检索穷尽"（如 `industry=机器人` 的 8 家必须全部可召回），**不做库外穷尽**（plan §0）。
2. **库外实体走 web 补全或如实告知**：不静默遗漏（plan §0④）；无锚定分支必须带明确语义（§3.3）。
3. **占位不入词表**：占位值按空处理，且**不得进入 content_terms**（lexical 车道语料）——否则在
   100% 的 professor 文档、30.3% 的 company 文档里制造跨实体假语料（G1 §4.1 P1–P8、§4.2 R9 注、
   §1.5 占位污染率）。
4. **取证在入库、不在服务期**：入库质量门是"证据优先"的落地形态（plan §5 用户 2026-09-11 再定义）；
   服务期的深复现证明链不属于该定义，归 S2/S3 清退范围。
5. **禁增证明层**：缺口补齐期间不新增证明层机制；本门的产出是"脚本 + 对账报告"，不是常驻服务
   （plan §5「新代码规则」）。
6. **门只做能做的事**：数据不够 → 拒绝/告警/登记缺口；**不发明数据**（缺字段先登记、不设门禁，
   避免"用不存在的字段拒绝一切"，G1 §2.1 级定义）。
7. **职责边界**：本门管"数据够不够好"（字段/锚定/身份登记）；封印器管"两线契约一致不一致"
   （C2 四道门，ADR §1.1）。两者同挂 C6 但**不重复设闸**（§5.3）。

---

## 2. 字段契约表（四域，两级 + 两档阈值）

**分级定义（G1 §2.1）**：**必填** = 缺失/占位使该记录不可可靠检索或不可展示 → 记录级拒绝或整包级拒绝线；
**高价值** = 类目锚定/语义召回主力 → 整包级告警/拒绝双线；**观测/缺口** = 先登记不设门禁。
**用途列（G1 §2.1 口径）**：D = exact 车道展示名、I = 标识词、T = 语料词（其余字段全部递归进 content_terms，
定义点 `knowledge_read_isolated.py:7978-7993`、使用点 `:7950`；d05 §3.2 同述）。

口径警告：G1 §2.2 给"单值建议阈值"，§4.3 给"告警线/拒绝线"双档，二者多处数值不同
（如 tech_tags 70 vs 75/65）——**本契约表以 §4.3 双线为准**，差异清单见 §8-1。

### 2.1 company（N=7,089）

| 字段 | 级 | 用途 | 告警线 | 拒绝线 | run14 实测 | 出处 |
|---|---|---|---|---|---|---|
| name | 必填 | D+T | — | <100% | 100.0% ✅ | G1 §2.2、§4.3 G-C1 |
| industry | 必填 | T | <92% | <85% | 91.9% ⚠️**告警** | G1 §4.3 G-C2 |
| profile_summary(usable) | 必填 | T | <85% | <75% | 91.1% ✅（占位 633） | G1 §4.3 G-C5 |
| tech_tags | 高价值 | T | <75% | <65% | 77.4% ✅ | G1 §4.3 G-C3 |
| industry_tags | 高价值 | T | <75% | <65% | 77.3% ✅ | G1 §4.3 G-C4 |
| technology_route_summary(usable) | 高价值 | T | <75% | <60% | 77.4% ✅（占位 1,600） | G1 §4.3 G-C6 |
| team_description | 高价值 | T | <70% | <55% | 77.8% ✅ | G1 §4.3 G-C8 |
| product_description(usable) | 高价值 | T | <60% | <45% | 63.6% ✅（占位 861） | G1 §4.3 G-C7 |
| registered_address | 高价值 | T | <90% | <80% | 91.8% ✅ | G1 §4.3 G-C9 |
| website | 高价值 | T | <70% | <55% | 75.3% ✅ | G1 §4.3 G-C10 |
| geography / founded_at / legal_representative | 高价值 | T | <70% | <55% | 77.4–77.5% ✅ | G1 §4.3 G-C11 |
| aliases | 观测 | I+T | 不设门禁 | — | 4.8%（342 条） | G1 §2.2 |
| key_personnel | 观测 | T | 不设门禁 | — | 12.0% | G1 §2.2 |
| credit_code | **缺口** | I | 不设门禁 | — | **0.0%**（exact identifier 词表含它） | G1 §2.2、§4.4 T-5 |
| business_scenarios / capabilities / financing_events / personnel_education / personnel_work_experience / products | **缺口** | T | 不设门禁 | — | 0.0%（来源未供） | G1 §1.1、§2.2 |

记录级：无类目锚（industry∪industry_tags∪tech_tags 全空）**568 = 8.0%** → 告警（G1 §4.2 R3、§1.5）。

### 2.2 paper（N=24,520）

| 字段 | 级 | 用途 | 告警线 | 拒绝线 | run14 实测 | 出处 |
|---|---|---|---|---|---|---|
| title | 必填 | D+T | — | <100% | 100.0% ✅ | G1 §4.3 G-P1 |
| authors / venue / year | 必填 | T | — | <100% | 100.0% ✅ | G1 §4.3 G-P1 |
| doi | 必填 | I+T | <97% | <90% | 97.8% ✅（缺 544） | G1 §4.3 G-P2 |
| 语义并集 abstract∪summary_text∪summary_zh | 必填 | T | <99% | <95% | **99.5%** ✅（129 篇全空） | G1 §4.3 G-P3 |
| summary_zh | 高价值 | T | <70% | <55% | 73.0% ✅ | G1 §4.3 G-P4 |
| abstract | 高价值 | T | <45% | <35% | 48.1% ✅ | G1 §4.3 G-P5 |
| summary_text | 高价值 | T | <45% | —（§4.3 无行） | 50.4% | G1 §2.3 |
| citation_count | 高价值 | T | <30% | —（§4.3 无行） | 33.4% | G1 §2.3 |
| identifier 并集 doi∪arxiv_id∪identifiers | 高价值 | I | <98% | <95% | 98.8% ✅（297 篇无标识） | G1 §4.3 G-P6 |
| title_zh / keywords / fields_of_study | **缺口** | I/T | 不设门禁 | — | 0.0% → **G3 盲区**（14 词中 13 个只在 summary_zh） | G1 §2.3、G3 §0.1、§3.2 |

记录级：无语义语料 129 = 0.5% → 告警（G1 §4.2 R4）。

### 2.3 patent（N=11,504）

| 字段 | 级 | 用途 | 告警线 | 拒绝线 | run14 实测 | 出处 |
|---|---|---|---|---|---|---|
| title | 必填 | D+T | — | <100% | 100.0% ✅（类目主锚） | G1 §4.3 G-T1 |
| patent_number | 必填 | I+T | — | <100% | 100.0% ✅（四域最可靠自然键） | G1 §4.3 G-T1、G2 §1.3 |
| publication_date | 必填 | T | — | <100% | 100.0% ✅ | G1 §4.3 G-T1 |
| summary_text | 必填 | T | — | <100% | 100.0%（**生成式模板文**，全部以"该专利围绕…展开"开头） | G1 §4.3 G-T1、§1.3 |
| applicants | 必填 | T | — | <100% | 100.0%（**§4.3 无双线行**，见 §8-5） | G1 §2.4 |
| 摘要并集 abstract∪technology_effect | 必填 | T | <85% | <78% | 83.2% ⚠️**告警** | G1 §4.3 G-T5 |
| abstract | 高价值 | T | <85% | <75% | 83.2% ⚠️**告警** | G1 §4.3 G-T2 |
| technology_effect | 高价值 | T | <80% | <70% | 81.4% ✅ | G1 §4.3 G-T3 |
| patent_type | 高价值 | T | <80% | <65% | 83.2% ✅ | G1 §4.3 G-T4 |
| filing_date | 观测 | T | <15% | — | 16.8% ✅ | G1 §4.3 G-T6 |
| ipc_codes / inventors / company_ids / professor_ids / grant_date / milestones / technical_summaries / title_en | **缺口** | I/T | 不设门禁 | — | 0.0%；**ipc_codes 缺失 = 专利域无标准类目锚** | G1 §2.4、§3.3、G3 §4.5-4 |

记录级：无摘要类内容 1,931 = 16.8% → 告警；无 ipc/inventors 100%；无任何日期（filing∪grant）83.2%（G1 §1.5、§4.2 R5）。

### 2.4 professor（N=3,958）

| 字段 | 级 | 用途 | 告警线 | 拒绝线 | run14 实测 | 出处 |
|---|---|---|---|---|---|---|
| name / canonical_name_zh | 必填 | D+T | — | <100% | 100.0% ✅ | G1 §4.3 G-R1 |
| institution | 必填 | T | — | <100% | 100.0% ✅ | G1 §4.3 G-R1 |
| homepage | 必填 | T | <95% | <85% | 100.0% ✅ | G1 §4.3 G-R7 |
| profile_summary(usable) | 必填 | T | <95% | <85% | 99.9% ✅（占位 2） | G1 §4.3 G-R6 |
| research_directions | 高价值 | T | <48% | <35% | 49.7% ✅（贴线；**教授域类目主锚**） | G1 §4.3 G-R2、§2.5 |
| department(usable) | 高价值 | T | <65% | <50% | 70.0% ✅（占位 1,188） | G1 §4.3 G-R3 |
| email(usable) | 高价值 | T | <60% | <45% | 68.4% ✅ + **值形校验**（样例含电话粘连 `0755-88010580zhaoyp@…`） | G1 §4.3 G-R4、§1.4 |
| title(usable) | 高价值 | T | <35% | <25% | 36.5% ✅（贴线；占位 2,515） | G1 §4.3 G-R5 |
| paper_summary / patent_summary | **目标态** | T | 先告警（目标 ≥50%） | **禁止开拒绝** | 0.0%（100% 占位，schema 必填被占位填满） | G1 §4.4 T-1、§1.4 |
| canonical_name_en | **目标态** | T | 值形通过率 ≥90%（先告警） | **禁止开拒绝** | 7.0% 且多为导航碎屑（"About Us"/"View More"…；230 distinct 中仅少数像人名） | G1 §4.4 T-2、§1.4 |
| citation_count / h_index / paper_count | 观测 | T | 目标 ≥20%（先告警） | — | 3.1–5.9% | G1 §4.4 T-9、§1.4 |
| aliases / awards / office / phone / company_roles / patent_ids / projects / affiliation_history / contacts / education_history / metric_snapshots / work_history | **缺口** | T | 不设门禁 | — | 0.0%（来源未供；`lifecycle_state` 归 G2 治理） | G1 §2.5 |

记录级：无方向信号 2；无称谓/院系 **1,023 = 25.8%** → 告警（G1 §4.2 R6/R7、§1.5）。

### 2.5 记录级规则（入库即检，G1 §4.2）

| 规则 | 触发 | 动作 |
|---|---|---|
| R1 显示名缺失 | company.name / paper.title / patent.title / professor.name 空或占位 | **拒绝该记录** |
| R2 标识缺失 | patent.patent_number 空或占位 | **拒绝该记录**；paper.doi 空 → 告警（保留 shell） |
| R3 无类目锚 | company industry∪industry_tags∪tech_tags 全空（568 = 8.0%） | 告警 |
| R4 无语义语料 | paper abstract∪summary_text∪summary_zh 全空（129 = 0.5%） | 告警 |
| R5 无摘要类内容 | patent abstract∪technology_effect 全空（1,931 = 16.8%） | 告警 |
| R6 无方向信号 | professor research_directions∪profile_summary 全空（2） | 告警 |
| R7 无称谓/院系 | professor title∪department 全空（1,023 = 25.8%） | 告警 |
| R8 值形可疑 | professor.canonical_name_en 导航碎屑形；email 电话粘连/多 @ | 值置空 + 告警 |
| R9 占位句入库 | 任何字段写入 P1–P8 字面值 | **拒绝该值（写 null）**；不得进入 content_terms |

**占位清单 P1–P8（G1 §4.1，全量）**：P1 `Not supplied by the historical source.`（professor.title 2,515 /
email 1,251 / department 1,188）；P2 `Not supplied by the full-column workbook source.`（company.route 713）；
P3 `Not supplied by the backfill source.`（company.route 561）；P4 `No dedicated summary was supplied by the
full-column workbook source.`（professor.paper_summary 2,530 / patent_summary 2,530）；P5 `No dedicated summary
was supplied by the historical source.`（professor 1,428×2 / profile_summary 2 / company.profile_summary 1）；
P6 `未找到`（含粘连变体；company.product_description 861 / profile_summary 632 / route 326）；P7 `暂无`（company.website 1）；
P8 `-`（单字符；company 四字段各 1）。合计 professor **12,872** / company **3,099** / paper、patent **0**。
匹配规则按**模式**（句首前缀 + 中文 {未找到, 暂无, 未知, 无, 待补充} + 单字符 `-`）实现，不按字面枚举
（G1 §5-4）。**占位不入词表**是硬规则（§1-3），P1–P8 为当前全量、随新来源扩展。

---

## 3. 类目锚定规则（G3）

### 3.1 锚定四级（G3 §2.3）

| 规则 | 触发条件 | 可命中字段 | 置信度 | 实测证据 |
|---|---|---|---|---|
| **R1 强锚定（粗标签）** | 类目词 ∈ `industry.name` / `industry_tags[].name`（41 个值） | industry、industry_tags | 高 | 30 词里 **2/30** 命中；人工智能 1,297/7,089 = 18.3%；机器人仅 8 家 |
| **R2 中锚定（企业标签）** | 类目词 ∈ `tech_tags[].name` 子串 | tech_tags | 中（单标签、覆盖窄） | **26/30** 词命中；机器人 414/7,089 = 5.8%；具身智能 11/7,089 = 0.16% |
| **R3 弱锚定（文本）** | 类目词 ∈ product_description / profile_summary / 专利摘要 / 论文摘要 | 文本字段 | 低（**需打分与阈值**） | **28/30** 词命中；具身智能结构化覆盖率 14.5%、PCB 7.7% |
| **R4 无锚定** | 全库零命中 | 无 | — | 酒店送餐机器人（9 轮）、PCB打板（6 轮）命中 **0** 文档 |

tier 判据（G3 §2.3 注）：结构化覆盖率 = 命中的公司文档里类目词落在 industry/industry_tags/tech_tags 的比例；
**S ≥ 20%**、0 < 覆盖率 < 20% 为 **T**、全库 0 命中为 **N**。注意覆盖率是条件概率（分母 = 命中的公司文档），
召回侧看绝对数（如 tech_tags 机器人 414/7,089 = 5.8%）——两者不可混读（G3 §6-4）。

字段覆盖汇总（G3 §2.2）：tech_tags 26/30、product_description 28/30、profile_summary 28/30、
professor.research_directions 15/30、industry 2/30、industry_tags 1/30；专利 title/abstract/summary_text 22/23/24、
论文 title/abstract/summary_text 2/2/21。**结构性结论**：细类目的唯一结构化锚点是 `tech_tags`，
且必须声明为"子串匹配 + 单标签 + 每公司 ≤1 条"，不能当集合命中（G3 §4.5-1、§2.1）。
离线验证（G3 §3）：机器人 33.5%、人工智能 85.9%、芯片 33.0%、传感器 24.1%、灵巧手 20.8% 可做确定性过滤；
具身智能 14.5%、PCB 7.7%、送餐机器人 0%、视触觉 0% 必须走文本打分（或判无锚定）。

### 3.2 低置信白名单（答案层必须带置信声明，G3 §4.5-2）

G3 §4.1（语料确认的缺口词 6 个）与 §4.2（包内词表缺口语 17 个）中的词**必须显式标注"仅文本/摘要锚定"**，
否则答案层会把具身智能的 48 条摘要命中当成 1,297 条 industry 命中那样的强度（G3 §4.5-2）。
典型：具身智能（158 文档 / tech_tags 11）、送餐机器人（20）、PCB（252）、视触觉（11）、储能（588）、
机械臂（729）、人形机器人（290）、边缘计算（199）、自动驾驶（255）、生物医药（50）……
`g3-vocabulary.json.vocabulary` 共 110 个词条，§4.1/§4.2 是其中需白名单标注的子集（G3 §4.4 注）。

### 3.3 无锚定分支（**不是摘要兜底问题**，G3 §4.3、§4.5-3）

- `酒店送餐机器人`（9 轮，tier N）= **组合粒度**问题：`送餐机器人` 有 20 个文档命中、`酒店` 场景另有描述，
  但两者从未连成一个短语（G3 §4.3）。
- `PCB打板`（6 轮，tier N）= **动作/工艺词**而非类目词：`PCB` 本身有 11 家 tech_tags（G3 §4.3）。
- 因此这两类**不能靠"多召回几个摘要命中"掩盖**；契约要求明确语义分支：**数据侧无该类目 → web 补全 +
  如实告知，不伪装**（不返回相近企业后不声明），并与 plan §0④"库外实体 → web 补全或如实告知，不静默遗漏"
  一致；答案侧的具体表述形态建议并入 S4 引导式交互切片（plan §5 S4，§8-8）。

### 3.4 G3 交给契约的四条输入（G3 §4.5 原文，已吸收于上文）

1. 锚定字段按 R1→R4 优先级声明；`tech_tags` 声明为"子串 + 单标签 + ≤1 条"（§3.1）。
2. 低置信白名单 + 答案置信声明（§3.2）。
3. 无锚定分支的明确语义（§3.3）。
4. 字段治理诉求（数据侧，非本切片）：`patent.ipc_codes`（0/11,504）、`paper.keywords`/`fields_of_study`
   （0/24,520）为空；`industry`/`industry_tags` 需细类目扩展（当前 `机器人` 只有 8 家）——即 §2 的缺口项与 §6 的 T-3/T-8。

---

## 4. 身份合并与 stable_uid（引 G2，规则指针到 ADR）

1. **碎片化规模**：company 品牌核（T3）**72 簇 / 146 文档**（97% 为 2 文档簇；精确同名 T1 = 0）；
   professor 姓名 18 簇 / 37 文档；paper 标题归一 6 簇 / 12 文档；patent 专利号 0 簇（最可靠自然键）（G2 §1.1）。
2. **合并证据门（三档）**（G2 §4.2）：
   - **自动合并**：核心名相等（T2 或"实体更名"证据）**且**强证据不互斥（address/法代/成立时间/官网域
     至少一项相等或单边缺失）。
   - **人工复核队列**：仅品牌核（T3）相同。
   - **禁止合并**：强证据互斥——本轮 **30/72（42%）**；红线样本：华芯、海思、中智科创、顺丰科技 vs 顺丰控股。
   即：**42 簇为非互斥候选（自动合并资格）/ 30 簇互斥（人工裁决抽样）**。KPI 要求自动合并的负样本 = 0、
   冲突 resolution 覆盖率 100% 且抽检 ≥95% 合格（G2 §4.5#4/#5）。
3. **合并前必做**：字段级 quality flag——占位符永远不覆盖真值、"产品清单冒充简介"降权；
   `credit_code`/`registered_capital` 全空**不得作合并锚点**（列数据回填最高优先）（G2 §2.3-6、§2.2、§4.2）。
   `normalized_name` 现 72/72 全冲突，须由合并器统一重算、不信源字段；`last_updated` 全体被重盖为构建戳，
   **当前不可作新鲜度依据**（G2 §2.2、§4.1-3）。
4. **产品类前置裁定**：论文"预印本 vs 期刊版"是否同一实体（6 对全属此类，DOI 各不相同）；
   professor 同名同机构 9 簇是否同人（另 9 簇跨机构 = 同名不同人，**不应合并**）；
   行业分类统一词表（机器人 vs 物流运输，属产品决策）；合并后展示名规则（G2 §1.3、§4.4）。
5. **stable_uid 与家规 R1–R4**：协议骨架、代价、KPI 全部收敛到 **ADR 产物**（ADR §2.C、§4）——
   本提案不复制，避免两处数字漂移。**落地上顺序**：stable_uid 生效前，本门在身份侧只做
   "占位过滤 + 值形校验 + 登记缺口"，**不做自动合并**（ADR §3-5）。

---

## 5. gate 执行形态

### 5.1 三层结构

| 层 | 时机 | 内容 | 失败动作 |
|---|---|---|---|
| 值级 | 写库前 | 占位按空（P1–P8 模式匹配）；值形校验（R8） | 写 null + 告警 |
| 记录级 | 入库即检 | R1–R9（G1 §4.2） | 拒绝记录 / 告警 |
| 整包级 | 发布前对账 | §2 各域双线阈值；目标态 T-1..T-9 | 告警（首版）/ 拒绝入库（定稿后） |

### 5.2 首版执行策略（防抖 + 防止误伤自己）

- **对 run14 的告警只通报不阻断**——run14 当前落在告警带的是 `company.industry`（91.9% vs 92%）与
  patent 摘要（83.2% vs 85%），恰是应当被通报的两处空洞（G1 §2.5 阈值总原则、§4.4 落地建议）。
- 阈值 = 实测值向下留 5–10pp 余量；**单包（run14）首版**，data-rebuild 后必须复测校准再定稿（G1 §5-4）。
- **目标态 T-1..T-9 先告警、禁止直接开拒绝**（G1 §4.4 表头），以"周报量表"方式跟踪（§6）。
- 判定纪律：不看文档自述、关键词命中不算通过（plan §1 判定纪律，GAP-10 教训）。

### 5.3 与 C6 更新流水线的挂点

- C6 流水线 = 「源数据重建 → 官方封印 → 版本化切换 → 回滚」，**两条线契约一致性检查纳入封印步骤
  （漂移即拒封）**（plan §3 C6 行）。
- 本门挂在**封印前的数据侧**：整包阈值对账（§5.1 第三层）= 封印的前置清单项；封印器仍只管契约一致性
  （C2 四道门，ADR §1.1）。**不重复设闸**、不新增证明层（§1-5）。
- 验收口径对齐 C6：换一版包 + 回滚一次；更新后四轴（准/快/全/好）证据不降（plan §0、§3 C6）。
- 具体挂点形态（封印前置清单 vs 封印脚本内步骤）待裁（§8-12）。

---

## 6. 目标态 KPI 表（G1 §4.4 九项 + G3 覆盖目标 + G2 身份 KPI，合并去重）

**去重规则**：字段阈值数字的唯一源 = 本文 §2（G1 §4.3）；身份 KPI 数字的唯一源 = ADR §4（G2 §4.5）；
本表只列"目标 + 当前基线"，不重复阈值表与 ADR 的完整口径。

| # | KPI | 目标 | 当前基线 | 出处 |
|---|---|---|---|---|
| T-1 | professor.paper_summary / patent_summary(usable) | ≥50% | 0.0%（100% 占位） | G1 §4.4 T-1 |
| T-2 | professor.canonical_name_en 值形通过率 | ≥90% | 7.0% 填充中多数为导航碎屑 | G1 §4.4 T-2 |
| T-3 | patent.ipc_codes | ≥50% | 0.0%（专利唯一标准类目锚） | G1 §4.4 T-3、G3 §4.5-4 |
| T-4 | patent.inventors | ≥30% | 0.0% | G1 §4.4 T-4 |
| T-5 | company.credit_code | ≥50% | 0.0%（exact identifier 词表字段） | G1 §4.4 T-5 |
| T-6 | company.aliases | ≥30% | 4.8% | G1 §4.4 T-6 |
| T-7 | company.key_personnel | ≥30% | 12.0% | G1 §4.4 T-7 |
| T-8 | paper.keywords / fields_of_study | ≥50% | 0.0%（论文域类目锚） | G1 §4.4 T-8、G3 §4.5-4 |
| T-9 | professor.citation_count / h_index / paper_count | ≥20% | 3.1–5.9% | G1 §4.4 T-9 |
| G3-1 | 类目 tier 判据（结构化覆盖率 S ≥ 20% / T 0–20% / N 全库 0） | S 档词可确定性过滤、T 档词须带置信声明、N 档词走无锚定分支 | 30 词分布见 G3 §2.2/§3 | G3 §2.3 注、§4.5 |
| G3-2 | 缺口词治理（具身智能 14.5%、储能 3.0%、机械臂 6.7%、人形机器人 13.9%、PCB 7.7%、送餐机器人 0%、酒店送餐机器人 0、PCB打板 0） | **数值目标待裁**（G3 未给目标值；建议最小值 = 脱离 tier N / 提升一档） | 见左 | G3 §4.1、§4.2、§4.3（§8-7） |
| G3-3 | 结构化锚字段覆盖面（tech_tags 26/30 词、product_description 28/30、profile_summary 28/30、research_directions 15/30、industry 2/30、industry_tags 1/30） | 补采 `ipc_codes` / `keywords` / `fields_of_study`；`industry`/`industry_tags` 细类目扩展（机器人 8 家） | 见左 | G3 §2.2、§4.5-4（= T-3/T-8） |
| G2-1..5 | stable_uid 跨代保持率 / dangling / 跨代引用解析率 / resolution 覆盖率 / 互斥簇自动合并数 | 数字唯一源 = **ADR §4**（引 G2 §4.5），本表不复制 | 同上 | G2 §4.5、ADR §4 |
| G-契约 | 契约源清单内两线 diff、漂移 fail-closed 次数（建议新增） | 见 ADR §4 建议行 | 14 个文件"代差未核" | ADR §4、`verification-c2.md` §2 |

---

## 7. 实施顺序建议

| 批 | 内容 | 依赖 | 成本 | 说明 |
|---|---|---|---|---|
| **批 0（先落，无需新数据）** | 占位过滤 P1–P8（模式匹配，命中按空/写 null）+ 记录级 R1–R9 告警 + 类目锚定声明 R1–R4 + 低置信白名单标注 | 无 | 低 | 直接消除"占位入 content_terms"的跨实体假语料（G1 §4.2 R9 注）；锚定声明是**声明式**配置，不动 serving 打分（G3 §6-3：精确召回需 agent-4 侧分词/打分） |
| **批 1** | 值形校验（canonical_name_en 禁用值表/人名正则；email 拒电话粘连/多 @）+ **字段级 quality flag** | 批 0 | 低-中 | quality flag 是身份合并的前置（G2 §2.3-6），也为 §2 的 usable 口径提供机制 |
| **批 2** | 整包级阈值切硬门（§2 双线复核定稿 + T-1..T-9 逐项转档） | data-rebuild 完成、单包首版复测 | 中 | 首版只通报不阻断（G1 §4.4）；阈值复测属契约义务（G1 §5-4） |
| **批 3** | 身份合并 + stable_uid 进发布门（R1–R4 家规生效） | ADR 拍板 + OpenSpec change + §8 产品裁定 | 高 | 兼容期双写→双读→切换约两个 release 周期（G2 §4.4） |
| **数据补采（需用户拍板）** | credit_code / ipc_codes / keywords / fields_of_study / inventors / aliases / key_personnel / paper_summary+patent_summary 来源修复 / 时间戳语义修复（last_updated 全被重盖为构建戳，G2 §4.1-3） | 用户 | 高 | 不补则 T-1/T-3..T-9 固定告警；**不补也不阻断 gate**（缺口字段不设门禁） |

排序原则：**低成本、无新数据的先落**（占位过滤 + 锚定声明 + 门告警）；依赖数据补采与产品裁定的押后。
本顺序与 plan §5 执行序列的关系：批 0/1 属 C1 本体；批 2 依赖 C6 的 data-rebuild；批 3 依赖两线契约家规 ADR 拍板。

---

## 8. 待裁清单（需用户 / 主上下文决定）

| # | 待裁项 | 事实与出处 | 归属 |
|---|---|---|---|
| 1 | G1 §2.2 单值阈值 vs §4.3 双线数值不一致（多处：industry 90 vs 92/85、tech_tags 70 vs 75/65、route 70 vs 75/60、product_description 55 vs 60/45、doi 95 vs 97/90、语义并集 98 vs 99/95、research_directions 45 vs 48/35） | 本契约表以 §4.3 双线为准 | 主上下文 |
| 2 | `company.industry` usable 6,516（G1 §1.1，含 1 条 `-` 占位）vs 6,517（G2 §2.2 非空非占位） | 差 1 条 = `-` 计/不计之差；影响 #4 的阈值分母口径 | 主上下文 |
| 3 | `industry` distinct 值计数：G1 §1.1 记 40 真实类目 + `-` 1（并注 d05 记 41）vs G3-A T7 列 41 行含 `-`（2 家） | `-` 计数口径不统一 | 主上下文 |
| 4 | G3 §2.1 `tech_tags` 标签数直方图"0 条 1,604 / 1 条 5 / 2 条 5,480"与同句"几乎每家只有 1 条"及总数 5,485 不自洽（疑 1 条/2 条行列互换） | G3 §2.1；影响"每公司 ≤1 条"声明的措辞 | 主上下文 |
| 5 | `patent.applicants` 在 G1 §2.4 为必填，但 §4.3 无双线阈值行 | 本表暂按"拒绝线 <100%"处理 | 主上下文 |
| 6 | 无双线行/仅单值的字段：`paper.summary_text`、`paper.citation_count`（§4.3 无行）与 `company.geography/founded_at/legal_representative`（G-C11 合并三项）——是否补行、是否拆行 | G1 §2.3/§4.3 | 主上下文 |
| 7 | "G3 覆盖目标"缺数值：G3 未给缺口词的目标覆盖率 | 建议口径 = 脱离 tier N / 提升一档，或直接引用 T-3/T-8（≥50%） | 用户 + 主上下文 |
| 8 | 无锚定分支的答案层表述形态与归属（如实告知 + web 补全 + 建议追问） | 建议并入 S4 引导式交互切片（plan §5 S4） | 用户 + 主上下文 |
| 9 | 低置信白名单的名单边界：G3 §4.1（6 词）+ §4.2（17 词）之外，probe 词（G3 §4.4，21 词，"不属于确定性导出"）是否入名单 | G3 §4.1/§4.2/§4.4 | 主上下文 |
| 10 | 身份合并的四项产品裁定（论文版本档 / 同名同机构 / 行业词表 / 展示名） | 指针到 ADR §5 Q7–Q10，本提案不重复列 | 用户 |
| 11 | data-rebuild 后阈值复核的责任方与节奏（单包首版 → 定稿的裁决点） | G1 §5-4；C6 节奏为周更/月更/按需（plan §3 C6） | 主上下文 |
| 12 | gate 与 C6 的挂点形态：整包对账作为"封印前置清单项"还是"封印脚本内步骤" | plan §3 C6 未细化；§5.3 | 主上下文 |
| 13 | 周报量表的形态与受众（面向用户还是内部日志） | §5.2、§6 | 用户 |
| 14 | 占位匹配规则的实现形态：前缀/模式匹配（G1 §5-4 要求）与 P1–P8 之外的新来源变体谁来扩表 | G1 §5-4、§4.1 | 主上下文 |

---

## 9. 边界与未决

1. 本稿是**契约提案**，不含实现；批 0 的落地仍需挂 OpenSpec change（行为影响面：入库拒绝/告警语义）——
   C1 实施切片（plan §3 C1）是承接方。
2. 未覆盖：s12f 老包同口径复核（G1 §5-3 未做）、`canonical_name_en` 导航碎屑逐条分类（需先有值形规则，
   G1 §5-3）、email 粘连的样例级量化之外的全量统计、vector 车道（远程 embedding 不可离线评估，G1 §5-3、d05 §4）。
3. 口径提醒：G3 的覆盖率是**条件概率**（分母为命中的公司文档），召回侧看绝对数（G3 §6-4）；
   子串匹配无中文分词，所有覆盖数为**上界**（G3 §6-3）；G3 流量语料是测试/评估流量（9 个流量词，
   其中"深圳有哪些做具身智能的公司"一句占 115 轮），词表同时给"独立问句数"以防把复读当流量（G3 §6-1/6-2）。
4. 未做同口径复核的还有：d05 行号锚 commit `04e15966`（其 worktree rev）与本稿引用的主仓行号差异
   （G1 §5-2 已说明：指同一逻辑）。

---

## 10. 主上下文裁定（2026-09-11，先做后报；用户可改）

| # | 裁定 |
|---|---|
| 1 | 阈值口径**以 §4.3 双线为准**；G1 §2.2 单值表作历史稿（C1 实施时修订为同口径） |
| 2 | usable 口径统一 = **非空且非占位** → industry = **6,516**；阈值分母按此 |
| 3 | distinct(industry) = 41 值含 "-"、**真实类目 40**（统一从 G1） |
| 4 | G3 直方图已勘误：**0 条 1,604 / 1 条 5,485 / 无 2 条**（有值公司恰 1 条） |
| 5 | patent.applicants 拒绝线暂定 **<100%**（实施前复核） |
| 6 | v1.1 补行：paper.summary_text / paper.citation_count；company.geography / founded_at / legal_representative 拆行 |
| 7 | 覆盖目标：高流量词目标 = **进入 R1/R2**（结构化可锚）；无法达成 → 白名单 + 无锚定分支。T-3/T-8 类 ≥50% 暂定，实施时校准 |
| 8 | 无锚定分支形态**并入 S4**（如实告知 + web 补全 + 建议追问） |
| 9 | probe 21 词**不进**确定性白名单，作第二档词表管理 |
| 10 | 四个产品裁定指针 ADR-023 §7（默认值已给） |
| 11 | 阈值定稿责任 = **C1 实施切片**（data-rebuild 后重跑 G1 探针出定稿） |
| 12 | gate 挂点 = **封印脚本内显式步骤 + 报告输出**（单挂点、可审计） |
| 13 | 周报 = 内部日志周度摘要（不面向用户） |
| 14 | 占位匹配器 = 前缀/模式实现（C1 实施切片）；新来源变体经同一模式文件扩展 |
