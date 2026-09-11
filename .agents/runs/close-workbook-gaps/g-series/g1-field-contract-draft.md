# G1 检索关键字段契约草案（四域）

> 状态：**草案**（G 系列只读分析产物；供主上下文评审，后续由 C1 落地为 gate-at-import、由 G3 消费类目锚定）
> 日期：2026-09-11 ｜ 流：close-workbook-gaps / G1
> 数据源：`/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3`（只读，未碰 serving worktree）
> 　release `candidate-v2-20260819-r1`；sha256 `c392d559f403da928f3baeed8092c19717059b3bd1e8339fcde07fa2b7970c91`；665,395,200 B；mtime 2026-09-08 23:47
> 规模：company 7,089 / paper 24,520 / patent 11,504 / professor 3,958（合计 47,071 public_domain 文档；与 d05、主计划 §2 的 47,071 一致）
> 脚本（可重跑，位于本目录）：
> - `g1_probe_fields.py` — 字段覆盖 + 占位普查 + industry 分布 + 类目词×字段矩阵（全量约 18s）
> - `g1_probe_derived.py` — union 覆盖 / 最坏组合 / 占位污染率
> - `g1_probe_samples.py` — 可疑字段值分布（professor.canonical_name_en / email / title）
> 复现：`python3 .agents/runs/close-workbook-gaps/g-series/g1_probe_fields.py <DB> [all|coverage|words]`
>
> **计数口径**：`usable`（可用）= 非 null、非空串、非占位值；`raw`（原始非空）= usable + placeholder。
> d05 §3.2 的"填充数"是 raw 口径，可逐字段换算（例：company.tech_tags raw 5,485 = usable 5,484 + ph 1）。
> 下表 `n`=null、`e`=empty（空串/空列表/dict 无值）、`p`=placeholder。
>
> **代码锚点**（主仓当前 rev 行号。d05 文档里的 `:8147`/`:8166-8184` 是其 worktree rev（commit 04e15966）行号，指同一逻辑）：
> - `content_terms` = `_normalized_scalar_values(projection.model_dump(mode="json"))`——投影**全部标量字符串递归入词表**（定义 `knowledge_read_isolated.py:7978-7993`，使用点 `:7950`）
> - exact 车道（`:7996-8030`）：整条查询等于 display/identifier 词或保护槽指名；content_terms 仅用于排他过滤（`:8016`）
> - structured 车道（`:8033-8046`）：仅按 displayed_entity_ids 重查；空展示集直接短路返回空（`serving_pack_loader.py:950-951`）；content_terms 仅排他（`:8045`）
> - lexical 车道（`:8049-8075`）：**整条查询短语**是任意 content 词的子串（`:8068`）；exact_identifier 槽绑定 `:8131-8161`
> - 结论：句子级类目查询（"中国有哪些…机器人供应商"）按构造在三条确定性车道全空转（d05 §3.1 trace 实证）；类目治理的目标是让类目词成为**结构化字段取值的一部分**，并给 G3 提供"词→字段"的匹配素材。

---

## 1. 四域字段覆盖表（实测）

### 1.1 company（N=7,089）

| 字段 | usable | 空值结构 | 典型值样例 |
|---|---|---|---|
| name | 7,089（100.0%） | — | 深圳市尚锐科技有限公司 |
| normalized_name | 7,089（100.0%） | — | 与 name 同值（本包样例无差异） |
| aliases | 342（4.8%） | e 6,747 | 新华鹏激光 / 深圳思博睿 |
| credit_code | 0（0.0%） | n 7,089 | — |
| founded_at | 5,486（77.4%） | n 1,603 | 2006-05-18 |
| geography | 5,491（77.5%） | n 1,598 | 广东省 / 广东省-深圳市 |
| industry | 6,516（91.9%） | n 572；p 1 | 硬件 / 人工智能 |
| industry_tags | 5,479（77.3%） | e 1,609；p 1 | 硬件 / 人工智能 |
| key_personnel | 851（12.0%） | e 6,238 | 宫俊 |
| latest_public_updates | 0（0.0%） | e 7,089 | — |
| legal_representative | 5,485（77.4%） | n 1,603；p 1 | 朱秀珍 |
| patent_count | 0（0.0%） | n 7,089 | — |
| product_description | 4,507（63.6%） | n 1,721；p 861 | SuperHawk3110、SuperHawk3002SA |
| profile_summary | 6,456（91.1%） | p 633 | GPS跟踪器供应商 |
| registered_address | 6,506（91.8%） | n 583 | 深圳市南山区粤海街道…大冲商务中心3栋2925H |
| registered_capital | 0（0.0%） | n 7,089 | — |
| team_description | 5,518（77.8%） | n 1,571 | 胡峻浩，创始人&CEO，华中科技大学电子系学士… |
| tech_tags | 5,484（77.4%） | e 1,604；p 1 | GPS跟踪器供应商 / 机器人视觉和深度学习机器视觉技术服务商 |
| technology_route_summary | 5,489（77.4%） | p 1,600 | 石油管道、舰船金属结构…表面应变在线监测 |
| website | 5,339（75.3%） | n 1,749；p 1 | http://www.thinkrace.cn |
| business_scenarios / capabilities / financing_events / personnel_education / personnel_work_experience / products | 0（0.0%） | e 全空 | —（来源未供，与 d05 §3.2 一致） |
| quality_status | 7,089（100.0%） | — | 全库单一值 `partial` |

**industry 分布复核**（与父上下文一致）：人工智能 1,297 / 硬件 1,193 / 生产制造 931 / 先进制造 881 / **null 572** / 企业服务 555 / 物联网 351 / 汽车交通 251 / 医疗健康 249 / 硬科技 72 / 金融 67 / 科研及技术服务 66 / VR/AR 62 / 电子商务 56 / 大数据 56 / 批发零售 42 / 能源电力 40 / 教育培训 38 / 房产家居 37 / 物流运输 34 / 工具软件 29 / 生活服务 29 / 区块链 22 / 文娱传媒 21 / 农业 19 / 餐饮业 18 / 新基建 18 / 建筑 16 / 体育健身 12 / 旅游户外 11 / 环保 8 / **机器人 8** / 消费升级 7 / 社交社区 6 / 游戏 4 / 电子制造 3 / 政务及公共服务 2 / 食品饮料 2 / 服装纺织 1 / 信息安全 1 / 开采 1 / `-` 1。40 个真实类目值 + `-` 占位 1（d05 §3.2 记 "41 个 distinct"，口径差 1，为 `-` 计/不计之差）。

### 1.2 paper（N=24,520）

| 字段 | usable | 空值结构 | 典型值样例 |
|---|---|---|---|
| title | 24,520（100.0%） | — | A Spectral Reconstruction Algorithm of Miniature Spectrometer… |
| title_zh | 0（0.0%） | n 24,520 | — |
| abstract | 11,795（48.1%） | n 12,725 | The miniaturization of spectrometer can broaden… |
| arxiv_id | 499（2.0%） | n 24,021 | 1706.02510 |
| authors | 24,520（100.0%） | — | Shang Zhang |
| citation_count | 8,185（33.4%） | n 16,335 | 50 / 0 |
| doi | 23,976（97.8%） | n 544 | 10.3390/s18020644 |
| enrichment_sources / fields_of_study / funders / keywords / full_texts / identifiers / publications / references / summaries | 0（0.0%） | e 全空 | — |
| license / oa_status / pdf_path / professor_ids / publication_date / reference_count / tldr | 0（0.0%） | n 或 e 全空 | — |
| summary_text | 12,358（50.4%） | n 12,162 | 与 abstract 多为同文（英文） |
| summary_zh | 17,894（73.0%） | n 6,626 | 光谱仪的微型化对于拓展光谱分析的应用范围… |
| venue | 24,520（100.0%） | — | Sensors |
| year | 24,520（100.0%） | — | 2018 |
| quality_status | 100.0% | — | 全库单一值 `partial` |

### 1.3 patent（N=11,504）

| 字段 | usable | 空值结构 | 典型值样例 |
|---|---|---|---|
| title | 11,504（100.0%） | — | 数字电平信号的检测电路、检测方法及相关装置 |
| title_en | 0（0.0%） | n 11,504 | — |
| abstract | 9,573（83.2%） | n 1,931 | 本发明公开了一种水下清洁机器人及其停机方法… |
| applicants | 11,504（100.0%） | — | 深圳市海柔创新科技有限公司 |
| company_ids / inventors / ipc_codes / milestones / technical_summaries | 0（0.0%） | e 全空 | —（ipc_codes 是专利域唯一标准类目锚，全空） |
| filing_date | 1,931（16.8%） | n 9,573 | 2023-09-11 |
| grant_date | 0（0.0%） | n 11,504 | — |
| patent_number | 11,504（100.0%） | — | CN117207251A |
| patent_type | 9,573（83.2%） | n 1,931 | 发明 / 实用新型 |
| professor_ids | 0（0.0%） | e 11,504 | — |
| publication_date | 11,504（100.0%） | — | 2023-12-12 |
| summary_text | 11,504（100.0%） | — | 该专利围绕"…"展开。…（**生成式模板文**，含全部摘要信号） |
| technology_effect | 9,359（81.4%） | n 2,145 | 使得用户可以轻易地寻找打捞水下清洁机器人… |
| quality_status | 100.0% | — | 全库单一值 `partial` |

### 1.4 professor（N=3,958）

| 字段 | usable | 空值结构 | 典型值样例 |
|---|---|---|---|
| name / canonical_name_zh | 3,958（100.0%） | — | 曾翠兰 |
| canonical_name_en | 278（7.0%） | n 3,680 | **值不可信**：高频值为导航碎屑（"About Us"×11、"Job Openings Admission Alumni"×14、"View More"、"English String"、"Hong Kong"…；230 个 distinct 中仅少数像人名） |
| aliases / awards / company_roles / patent_ids / projects / affiliation_history / contacts / education_history / metric_snapshots / work_history | 0（0.0%） | e 全空 | — |
| citation_count | 125（3.2%） | n 3,833 | 8377 / 0 |
| department | 2,770（70.0%） | p 1,188 | 未来学部/体育部（深圳） / 理工学院 |
| email | 2,707（68.4%） | p 1,251 | liugp@sustech.edu.cn；样例含粘连脏值 `0755-88010580zhaoyp@sustech.edu.cn`、`075588010583247784542@qq.com` |
| h_index | 123（3.1%） | n 3,835 | 47 / 0 |
| homepage | 3,958（100.0%） | — | https://homepage.hit.edu.cn/cengcuilan |
| institution | 3,958（100.0%） | — | 哈尔滨工业大学（深圳） |
| lifecycle_state / manual_override / office / phone | 0（0.0%） | n 全空 | — |
| paper_count | 235（5.9%） | n 3,723 | 5 / 4 |
| paper_summary / patent_summary | 0（0.0%） | **p 3,958（100%）** | 全部占位句（schema 必填被占位值填满） |
| profile_summary | 3,956（99.9%） | p 2 | 曾翠兰现就职于哈尔滨工业大学（深圳）…（生成画像） |
| research_directions | 1,969（49.7%） | e 1,989 | 柔性钙钛矿太阳能电池 / 体育教育训练学 足球技… |
| title | 1,443（36.5%） | p 2,515 | 副教授 279 / 教授 182 / 助理教授 155 / 副教授、博士生导师 80 / … |
| quality_status | 100.0% | — | 全库单一值 `partial` |

### 1.5 跨域事实（gate 与盲区的量化依据）

**占位污染率**（文档含 ≥1 个占位字段值的比例，占位句会进入 content_terms 污染 lexical 车道语料）：
professor **3,958/3,958 = 100.0%** ｜ company **2,146/7,089 = 30.3%** ｜ paper 0/24,520 ｜ patent 0/11,504。

**最坏组合（全部字段不可用时计数）**：
- company 无任何类目锚（industry∪industry_tags∪tech_tags 全空）：**568 = 8.0%**；无任何描述语料（四个摘要字段全空）：34 = 0.5%
- paper 无语义语料（abstract∪summary_text∪summary_zh 全空）：129 = 0.5%；无任何标识（doi∪arxiv_id∪identifiers 全空）：297 = 1.2%
- patent 无摘要类内容（abstract∪technology_effect 全空）：**1,931 = 16.8%**；无 ipc/inventors：100%；无任何日期（filing∪grant）：83.2%
- professor 无方向信号（research_directions∪profile_summary 全空）：2；无称谓/院系：**1,023 = 25.8%**

**quality_status**：四域全部为单一值 `partial`（7,089 / 24,520 / 11,504 / 3,958），当前无区分信号。

---

## 2. 检索关键字段清单 + 建议阈值

### 2.1 分级定义

- **必填**：缺失/占位使该记录在对应域不可被可靠检索或不可展示 → 记录级拒绝或整包级拒绝线。
- **高价值**：类目锚定或语义召回的主力字段，缺失会造成系统性召回损失 → 整包级阈值（告警/拒绝双线）。
- **观测/缺口**：当前覆盖率极低或来源未供，先登记缺口、不设门禁（避免"用不存在的字段拒绝一切"）。
- 全部字段都进入 content_terms（全标量递归，见卷首代码锚点），因此"用途"列只标注它在 **exact 车道**中是否还扮演展示名（D）或标识词（I）角色；其余为语料词（T）。阈值理由以"检索用途 + 实测覆盖 + 本轮 rebuild 可达成性"为准。单点观测（run14）→ 阈值为首版，随 data-rebuild 复测校准。

### 2.2 company（N=7,089）

| 字段 | 级 | 用途 | 实测可用 | 建议阈值 | 理由 |
|---|---|---|---|---|---|
| name | 必填 | D+T | 100.0% | 100%（缺→拒绝记录） | exact 车道显示名 |
| industry | 必填 | T | 91.9% | ≥90%（发布双线 <92% 告警 / <85% 拒绝，见 §4.3） | 类目路由主锚；572 条空（8.1%）是当前最大类目空洞 |
| profile_summary | 必填 | T | 91.1% | ≥85% | 公司级语义语料；占位 633 |
| tech_tags | 高价值 | T | 77.4% | ≥70% | 结构化类目最强锚（机器人 414、芯片 242、人工智能 139） |
| industry_tags | 高价值 | T | 77.3% | ≥70% | industry 的别名集合 |
| technology_route_summary | 高价值 | T | 77.4% | ≥70% | 技术叙述语料（占位 1,600） |
| team_description | 高价值 | T | 77.8% | ≥70% | 团队语料 |
| product_description | 高价值 | T | 63.6% | ≥55% | 产品语料（占位 861） |
| registered_address | 高价值 | T | 91.8% | ≥90% | 地域问答/展示 |
| website | 高价值 | T | 75.3% | ≥70% | 补全入口/展示 |
| geography / founded_at / legal_representative | 高价值 | T | 77.4–77.5% | ≥70% | 展示与约束过滤 |
| aliases | 观测 | I+T | 4.8% | 暂不设门禁；目标 ≥30%（G2 定） | exact 词表含 aliases，近空影响别名召回 |
| key_personnel | 观测 | T | 12.0% | 暂不设 | 人名召回素材 |
| credit_code | 缺口 | I | 0.0% | 不设门禁；登记缺口 | exact identifier 词表含 credit_code，当前信用代码不可查 |
| business_scenarios 等 6 个 0% 字段 | 缺口 | T | 0.0% | 不设门禁；接入后定标 | 来源未供 |

### 2.3 paper（N=24,520）

| 字段 | 级 | 用途 | 实测可用 | 建议阈值 | 理由 |
|---|---|---|---|---|---|
| title | 必填 | D+T | 100.0% | 100%（缺→拒绝记录） | exact 车道显示名 |
| authors / venue / year | 必填 | T | 100.0% | 100% | schema 必填 + 检索身份 |
| doi | 必填 | I+T | 97.8% | ≥95%（发布双线 <97% 告警 / <90% 拒绝） | 标识锚；544 缺失 |
| abstract∪summary_text∪summary_zh（并集） | 必填 | T | **99.5%** | ≥98%（发布双线 <99% 告警 / <95% 拒绝） | 论文域唯一语义语料组；129 篇全空 |
| summary_zh | 高价值 | T | 73.0% | ≥70% | 中文检索主语料 |
| abstract | 高价值 | T | 48.1% | ≥45% | 英文侧语料 |
| summary_text | 高价值 | T | 50.4% | ≥45% | 多数与 abstract 同文 |
| citation_count | 高价值 | T | 33.4% | ≥30%（告警） | 展示/排序信号 |
| identifier 并集（doi∪arxiv_id∪identifiers） | 高价值 | I | 98.8% | ≥98%（告警） | 297 篇无任何标识 |
| title_zh / keywords / fields_of_study | 缺口 | I/T | 0.0% | 不设门禁；**G3 盲区登记** | 类目锚字段全空（见 §3.2） |

### 2.4 patent（N=11,504）

| 字段 | 级 | 用途 | 实测可用 | 建议阈值 | 理由 |
|---|---|---|---|---|---|
| title | 必填 | D+T | 100.0% | 100%（缺→拒绝） | exact 显示名 + 类目主锚 |
| patent_number | 必填 | I+T | 100.0% | 100%（缺→拒绝） | 唯一稳定标识 |
| publication_date | 必填 | T | 100.0% | 100% | 展示/时间约束 |
| summary_text | 必填 | T | 100.0% | 100% | 生成模板语料；注意"套话化"（全部以"该专利围绕…展开"开头） |
| applicants | 必填 | T | 100.0% | 100% | 申请人实体链接素材 |
| abstract∪technology_effect（并集） | 必填 | T | 83.2% | ≥80%（发布双线 <85% 告警 / <78% 拒绝） | 1,931 条（16.8%）无摘要类内容 |
| abstract | 高价值 | T | 83.2% | ≥80%（发布双线 <85% 告警 / <75% 拒绝） | — |
| technology_effect | 高价值 | T | 81.4% | ≥75% | — |
| patent_type | 高价值 | T | 83.2% | ≥80% | 类型过滤 |
| filing_date | 观测 | T | 16.8% | ≥15%（告警） | 当前极低 |
| ipc_codes / inventors / company_ids / professor_ids / grant_date / milestones / technical_summaries / title_en | 缺口 | I/T | 0.0% | 不设门禁；接入后定标 | **ipc_codes 缺失=专利类目无标准锚**（见 §3.3） |

### 2.5 professor（N=3,958）

| 字段 | 级 | 用途 | 实测可用 | 建议阈值 | 理由 |
|---|---|---|---|---|---|
| name / canonical_name_zh | 必填 | D+T | 100.0% | 100%（缺→拒绝） | exact 显示名 |
| institution | 必填 | T | 100.0% | 100% | 展示/组织过滤 |
| homepage | 必填 | T | 100.0% | ≥95% | 展示与补全入口 |
| profile_summary | 必填 | T | 99.9% | ≥95% | 画像语料（注：主计划记 54.3% 套话，属文风质量，非本报覆盖口径） |
| research_directions | 高价值 | T | 49.7% | ≥45% | **教授域类目主锚**；1,989 空 |
| department | 高价值 | T | 70.0% | ≥65% | 占位 1,188 |
| email | 高价值 | T | 68.4% | ≥60% + 值形校验 | 占位 1,251；样例含电话粘连值 |
| title | 高价值 | T | 36.5% | ≥35% | 占位 2,515 |
| paper_summary / patent_summary | 目标态 | T | **0.0%** | 先告警；目标 usable ≥50% | schema 必填被占位句 100% 填满（禁止以当前值开拒绝闸） |
| canonical_name_en | 目标态 | T | 7.0%（且多为导航碎屑） | 值形校验通过率 ≥90%（先告警） | 样例："About Us"/"View More"/"Job Openings…" |
| citation_count / h_index / paper_count | 观测 | T | 3.1–5.9% | 目标 ≥20% | 学术影响力信号 |
| aliases / awards / office / phone / company_roles / patent_ids / projects / affiliation_history / contacts / education_history / metric_snapshots / work_history / lifecycle_state | 缺口 | T | 0.0% | 不设门禁；接入后定标 | 来源未供（lifecycle_state 归 G2 治理） |

**阈值总原则**：阈值 = 实测值向下留 5–10pp 余量（防抖），出现系统性回归才触发；当前 run14 在"立即生效"档整体通过，仅 industry（91.9% vs 告警门槛 92%）与 patent 摘要（abstract / 并集均为 83.2% vs 85%）落在告警带——恰是应当被通报的两处空洞。数值为单包首版，data-rebuild 后复测定稿。

---

## 3. 类目词→字段锚定草案（输入给 G3）

方法：14 个高价值类目词 × 每域字段桶，全包统计"词出现在该字段/字段组"的文档数；`structure_rate = 结构化桶命中 / 任意桶命中`。结构化桶：company={name, industry, industry_tags, tech_tags}；paper={title, keywords, fields_of_study}；patent={title, ipc_codes}；professor={research_directions}。

### 3.1 company（N=7,089）

| 词 | 结构化命中 | 摘要类命中（profile/route/prod/team 等） | structure_rate | 锚定建议 / 盲区 |
|---|---|---|---|---|
| 机器人 | tech_tags 414, name 235, industry 8 | profile 696, route 553, prod 365, team 266 | 42% | 主锚 tech_tags+name；industry 仅 8，**不可**当唯一锚 |
| 具身智能 | tech_tags 11, name 2 | profile 48, route 31, prod 23, team 5 | 16% | 结构锚弱（近盲区） |
| PCB | tech_tags 12 | route 101, profile 52, prod 31 | 8% | **盲区**：信号主要在技术叙述 |
| 人工智能 | industry 1297, industry_tags 851, tech_tags 139, name 41 | profile 617, route 141, team 76 | 86% | 锚最强；industry 主锚 + industry_tags |
| 储能 | tech_tags 7, name 6 | route 197, profile 54, prod 33 | 3% | **盲区**：几乎全在摘要 |
| 半导体 | name 114, tech_tags 84 | route 277, profile 205, team 128, prod 67 | 32% | 双锚 name+tech_tags |
| 芯片 | tech_tags 242, name 17 | profile 490, route 235, prod 243, team 80 | 33% | tech_tags 主锚，摘要仍是大头 |
| 新能源 | tech_tags 48, name 48 | route 404, profile 122, team 42, prod 24 | 15% | **盲区**：route 是最大信号 |
| 无人机 | tech_tags 109, name 10 | route 221, profile 98, prod 63, team 39 | 31% | tech_tags 主锚 |
| 激光雷达 | tech_tags 7, name 1 | route 37, profile 24, prod 19 | 11% | **盲区** |
| 大模型 | tech_tags 4 | profile 69, route 27, prod 25 | 4% | **盲区** |
| 自动驾驶 | tech_tags 6, name 1 | route 65, profile 28, team 12, prod 10 | 6% | **盲区** |
| 生物医药 | name 4, tech_tags 2 | route 16, profile 10, prod 3 | 19% | 近盲区 |
| 低空经济 | tech_tags 2 | route 11, profile 4, prod 3 | 12% | 近盲区 |

### 3.2 paper（N=24,520）

| 词 | 结构化命中 | 摘要类命中 | structure_rate | 判定 |
|---|---|---|---|---|
| 机器人 | 0 | summary_zh 535 | 0% | **盲区**（词 100% 只在中文摘要） |
| 具身智能 | 0 | summary_zh 10 | 0% | 盲区 |
| PCB | title 11 | abstract 22, summary_text 27, summary_zh 23 | 23% | 仅 title 有弱锚 |
| 人工智能 | 0 | summary_zh 144 | 0% | 盲区 |
| 储能 | 0 | summary_zh 245 | 0% | 盲区 |
| 半导体 | 0 | summary_zh 308 | 0% | 盲区 |
| 芯片 | 0 | summary_zh 288 | 0% | 盲区 |
| 新能源 | 0 | summary_zh 13 | 0% | 盲区 |
| 无人机 | 0 | summary_zh 113 | 0% | 盲区 |
| 激光雷达 | 0 | summary_zh 40 | 0% | 盲区 |
| 大模型 | 0 | summary_zh 25 | 0% | 盲区 |
| 自动驾驶 | 0 | summary_zh 117 | 0% | 盲区 |
| 生物医药 | 0 | summary_zh 3 | 0% | 盲区 |
| 低空经济 | 0 | summary_zh 2 | 0% | 盲区 |

> paper 域 14 词中 13 个的类目信号**只存在于 summary_zh**，唯一例外（PCB）也主要靠 abstract/summary 文本。`keywords`/`fields_of_study` 100% 空 → G3 无法在论文域做字段级类目锚定；给 G3 的结论是"论文域类目召回要么走摘要全文，要么先补 keywords/fields_of_study"。

### 3.3 patent（N=11,504）

| 词 | 结构化命中 | 摘要类命中 | structure_rate | 锚定建议 / 盲区 |
|---|---|---|---|---|
| 机器人 | title 6402 | abstract 7230, summary_text 7961, effect 4081 | 79% | title 主锚（55.7% 专利题名含"机器人"） |
| 具身智能 | title 14 | abstract 13, summary_text 18 | 78% | title 主锚 |
| PCB | title 16 | abstract 45, summary_text 58 | 27% | 近盲区 |
| 人工智能 | title 51 | summary_text 231, abstract 164 | 22% | **盲区**（摘要为主） |
| 储能 | title 39 | summary_text 64, abstract 57 | 57% | title 有效 |
| 半导体 | title 10 | summary_text 19, abstract 13 | 50% | 样本小 |
| 芯片 | title 33 | summary_text 94, abstract 67 | 34% | 近盲区 |
| 新能源 | title 11 | summary_text 21, abstract 15 | 52% | 样本小 |
| 无人机 | title 40 | summary_text 87, abstract 72, effect 46 | 43% | title+effect |
| 激光雷达 | title 73 | summary_text 209, abstract 164 | 33% | 近盲区 |
| 大模型 | title 19 | summary_text 42 | 44% | — |
| 自动驾驶 | title 4 | summary_text 20, abstract 8 | 16% | **盲区** |
| 生物医药 | 0 | effect 2 | 0% | **盲区** |
| 低空经济 | 0 | 0 | — | 库内无该词专利 |

> patent 域无 IPC 分类锚（ipc_codes 0%），类目信号集中在题名与生成式 summary_text；`summary_text` 100% 覆盖但为模板文，词面命中可用、语义区分度存疑（属 G3 验证范围）。

### 3.4 professor（N=3,958）

| 词 | 结构化命中（research_directions） | 画像命中（profile_summary） | structure_rate | 判定 |
|---|---|---|---|---|
| 机器人 | 150 | 200 | 63% | 主锚有效 |
| 具身智能 | 46 | 35 | 85% | 主锚有效 |
| PCB | 2 | 2 | 100% | 样本 2 |
| 人工智能 | 153 | 272 | 50% | 画像补足一半 |
| 储能 | 35 | 37 | 79% | 有效 |
| 半导体 | 84 | 91 | 82% | 有效 |
| 芯片 | 29 | 42 | 64% | 有效 |
| 新能源 | 27 | 32 | 73% | 有效 |
| 无人机 | 24 | 23 | 92% | 有效 |
| 激光雷达 | 4 | 3 | 100% | 样本 4 |
| 大模型 | 61 | 45 | 87% | 有效 |
| 自动驾驶 | 27 | 16 | 100% | 有效 |
| 生物医药 | 4 | 16 | 24% | **盲区**（画像为主） |
| 低空经济 | 7 | 6 | 88% | 样本小 |

### 3.5 治理盲区清单（信号只在摘要类字段的词）

- **company**：储能（96.6% 仅摘要）、PCB（91.8%）、大模型（95.7%）、自动驾驶（93.5%）、激光雷达（89.4%）、低空经济（88.2%）、新能源（85.1%）、具身智能（83.7%）——这 8 个词若按"industry/tech_tags 精确类目"治理将系统性漏召（生物医药 80.6% 贴线，见表内"近盲区"）。
- **paper**：14 词中 13 个 100% 仅在 summary_zh；PCB 亦仅 23% 有题名锚。
- **patent**：生物医药（100%）、自动驾驶（84%）、人工智能（78%）、PCB（73%）仅摘要类；全域名册无 IPC 锚。
- **professor**：生物医药（76% 在画像）。
- 交叉结论（供 G3）：**词表锚定必须允许"多字段、分层"映射**——同域中同一类目词对必填摘要字段的依赖普遍 >50%（company 14 词中 8 个 >80%）；只做结构化字段映射会复现 d05 §3.1 的类目空转。稳定的结构化锚目前只有：company.tech_tags/industry、patent.title、professor.research_directions 三个字段组（外加 company.name 的弱锚）。

---

## 4. gate-at-import 规则草案

### 4.1 占位值清单（初版，按"整值归一 + 长度≤140"匹配）

| # | 占位值（字面） | 出现位置（字段实例数） |
|---|---|---|
| P1 | `Not supplied by the historical source.` | professor.title 2,515 / email 1,251 / department 1,188 |
| P2 | `Not supplied by the full-column workbook source.` | company.technology_route_summary 713 |
| P3 | `Not supplied by the backfill source.` | company.technology_route_summary 561 |
| P4 | `No dedicated summary was supplied by the full-column workbook source.` | professor.paper_summary 2,530 / patent_summary 2,530 |
| P5 | `No dedicated summary was supplied by the historical source.` | professor.paper_summary 1,428 / patent_summary 1,428 / profile_summary 2 / company.profile_summary 1 |
| P6 | `未找到`（含粘连变体 `未找到未找到1(光纤收发器),POE-1未找到1A(POE分离器)`） | company.product_description 861 / profile_summary 632 / technology_route_summary 326 |
| P7 | `暂无` | company.website 1 |
| P8 | `-`（单字符） | company.legal_representative / industry / industry_tags / tech_tags 各 1 |

合计：professor 12,872 处、company 3,099 处、paper/patent 0 处。匹配规则：句首 `Not supplied` / `No dedicated summary` 前缀（含 `by the … source.` 变体）+ 中文 {未找到, 暂无, 未知, 无, 待补充} + 单字符 `-`；命中即**按空处理**（覆盖统计与必填校验都不得为占位值放行）。

### 4.2 记录级规则（入库即检）

| 规则 | 触发 | 动作 |
|---|---|---|
| R1 显示名缺失 | company.name / paper.title / patent.title / professor.name 空或占位 | **拒绝该记录** |
| R2 标识缺失 | patent.patent_number 空或占位 | **拒绝该记录**；paper.doi 空 → 告警（保留 shell） |
| R3 无类目锚 | company industry∪industry_tags∪tech_tags 全空（当前 568=8.0%） | 告警 |
| R4 无语义语料 | paper abstract∪summary_text∪summary_zh 全空（129=0.5%） | 告警 |
| R5 无摘要类内容 | patent abstract∪technology_effect 全空（1,931=16.8%） | 告警 |
| R6 无方向信号 | professor research_directions∪profile_summary 全空（2） | 告警 |
| R7 无称谓/院系 | professor title∪department 全空（1,023=25.8%） | 告警 |
| R8 值形可疑 | professor.canonical_name_en 命中导航碎屑形（禁用值表 + 非人名正则）；email 拒电话粘连/多 @ | 值置空 + 告警 |
| R9 占位句入库 | 任何字段写入 P1–P8 字面值 | **拒绝该值**（写 null）；占位句不得进入 content_terms（lexical 车道语料） |

> R9 的理由：lexical 车道以 content_terms 为子串语料（`:8068`），占位句会在 100% 的 professor 文档、30.3% 的 company 文档里制造跨实体假语料（任意含 "supplied" 的词面查询会全体命中），同时也污染排他过滤（`:8016/:8045/:8066`）。

### 4.3 整包级阈值（发布前对账，失败→拒绝入库/发布）

| 规则 | 字段 | 告警门槛 | 拒绝门槛 | run14 实测 | 判定 |
|---|---|---|---|---|---|
| G-C1 | company.name | — | 低于 100% | 100.0% | 通过 |
| G-C2 | company.industry | 低于 92% | 低于 85% | 91.9% | **告警** |
| G-C3 | company.tech_tags | 低于 75% | 低于 65% | 77.4% | 通过 |
| G-C4 | company.industry_tags | 低于 75% | 低于 65% | 77.3% | 通过 |
| G-C5 | company.profile_summary(usable) | 低于 85% | 低于 75% | 91.1% | 通过 |
| G-C6 | company.technology_route_summary(usable) | 低于 75% | 低于 60% | 77.4% | 通过 |
| G-C7 | company.product_description(usable) | 低于 60% | 低于 45% | 63.6% | 通过 |
| G-C8 | company.team_description | 低于 70% | 低于 55% | 77.8% | 通过 |
| G-C9 | company.registered_address | 低于 90% | 低于 80% | 91.8% | 通过 |
| G-C10 | company.website | 低于 70% | 低于 55% | 75.3% | 通过 |
| G-C11 | company.geography / founded_at / legal_representative | 低于 70% | 低于 55% | 77.4–77.5% | 通过 |
| G-P1 | paper.title / authors / venue / year | — | 低于 100% | 100.0% | 通过 |
| G-P2 | paper.doi | 低于 97% | 低于 90% | 97.8% | 通过 |
| G-P3 | paper 语义并集(abstract∪summary_text∪summary_zh) | 低于 99% | 低于 95% | 99.5% | 通过 |
| G-P4 | paper.summary_zh | 低于 70% | 低于 55% | 73.0% | 通过 |
| G-P5 | paper.abstract | 低于 45% | 低于 35% | 48.1% | 通过 |
| G-P6 | paper.identifier 并集 | 低于 98% | 低于 95% | 98.8% | 通过 |
| G-T1 | patent.title / patent_number / publication_date / summary_text | — | 低于 100% | 100.0% | 通过 |
| G-T2 | patent.abstract | 低于 85% | 低于 75% | 83.2% | **告警** |
| G-T3 | patent.technology_effect | 低于 80% | 低于 70% | 81.4% | 通过 |
| G-T4 | patent.patent_type | 低于 80% | 低于 65% | 83.2% | 通过 |
| G-T5 | patent 摘要并集(abstract∪technology_effect) | 低于 85% | 低于 78% | 83.2% | **告警** |
| G-T6 | patent.filing_date | 低于 15% | — | 16.8% | 通过（观测） |
| G-R1 | professor.name / institution | — | 低于 100% | 100.0% | 通过 |
| G-R2 | professor.research_directions | 低于 48% | 低于 35% | 49.7% | 通过（贴线） |
| G-R3 | professor.department(usable) | 低于 65% | 低于 50% | 70.0% | 通过 |
| G-R4 | professor.email(usable) | 低于 60% | 低于 45% | 68.4% | 通过 |
| G-R5 | professor.title(usable) | 低于 35% | 低于 25% | 36.5% | 通过（贴线） |
| G-R6 | professor.profile_summary(usable) | 低于 95% | 低于 85% | 99.9% | 通过 |
| G-R7 | professor.homepage | 低于 95% | 低于 85% | 100.0% | 通过 |

### 4.4 目标态规则（当前 run14 不满足；**先告警，禁止直接开拒绝**）

| 规则 | 字段 | 目标阈值 | 当前实测 | 备注 |
|---|---|---|---|---|
| T-1 | professor.paper_summary / patent_summary(usable) | ≥50% | 0.0%（100% 占位） | 需先修来源/生成；否则固定告警 |
| T-2 | professor.canonical_name_en 值形通过率 | ≥90% | 大量导航碎屑（7.0% 填充中多数不可用） | 先出禁用值表/人名正则 |
| T-3 | patent.ipc_codes | ≥50% | 0.0% | 专利唯一标准类目锚 |
| T-4 | patent.inventors | ≥30% | 0.0% | 发明人链接 |
| T-5 | company.credit_code | ≥50% | 0.0% | exact identifier 词表字段 |
| T-6 | company.aliases | ≥30% | 4.8% | 别名召回 |
| T-7 | company.key_personnel | ≥30% | 12.0% | — |
| T-8 | paper.keywords / fields_of_study | ≥50% | 0.0% | 论文域类目锚（G3 依赖） |
| T-9 | professor.citation_count / h_index / paper_count | ≥20% | 3.1–5.9% | 影响力信号 |

> 落地建议（C1）：先启用 4.2 + 4.3（对 run14 的告警只通报不阻断），4.4 以"周报量表"方式跟踪；data-rebuild 完成后把 4.3/4.4 数值按新基线复核定稿，再切换为硬门。

---

## 5. 边界与未决

1. **d05 文档位置**：`d05-findings.md` 在主仓不存在，位于 worktree `.worktrees/canonical-v2-s11-consolidation/.agents/runs/close-workbook-gaps/d0-probe/`；本稿 company 数字与 d05 §3.2 已逐项换算对账（raw = usable + ph）。
2. **行号差异**：本稿行号为主仓当前 rev；d05 行号为其 worktree rev（commit 04e15966），语义一致（`:8147` = 全标量递归/词表逻辑、`:8166-8184` = `_normalized_scalar_values`）。
3. **未做**：canonical_name_en 导航碎屑未逐条分类（需先定义值形规则，归 G2/后续）；email 粘连仅样例级量化；vector 车道（远程 embedding）不可离线评估；relationships/身份链接字段（company_ids、professor_ids、patent_ids）属 G2 身份治理交界，本稿只登记 0% 缺口；s12f 老包未做同口径复核。
4. **风险提示**：4.3 阈值是单包（run14）首版校准，data-rebuild 后必须复测；占位匹配规则需随新来源扩展（P1–P8 为当前全量清单，但匹配器应按前缀/模式而非字面枚举实现）。
