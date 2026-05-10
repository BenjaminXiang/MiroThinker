---
title: Professor Data Agent — 需求确认与代码差距快照（2026-05-09）
date: 2026-05-09
status: active
owner: claude
type: requirements_audit
calibrates:
  - docs/Professor-Data-Agent-PRD.md
  - docs/index.md (教授行)
related:
  - docs/Data-Agent-Shared-Spec.md (§5.2、§4.3)
  - docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md
  - docs/plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md
  - docs/plans/2026-04-17-003-professor-stem-issue-closure-plan.md
  - docs/plans/2026-04-23-001-m1-identity-gate-v2.md
evaluation_commit: 4858404
governance:
  change_id: resolve-professor-canonical-baseline
  canonical_for: professor-data-agent-domain
  canonical_status: temporary
  declared_by: user
  declared_on: 2026-05-10
  superseded_target: docs/Professor-Data-Agent-PRD.md
  next_step: merge §1–§7 back into PRD (deferred to future change)
  tracked_in_git_on: 2026-05-10
---

# Professor Data Agent — 需求确认与代码差距快照（2026-05-09）

> 本文档是 2026-05-09 与项目所有者 25 步交互式确认得到的「教授域采集需求」快照，并对照当前代码（commit `4858404`）做差距评估。
>
> **优先级**：在沉淀回正式 PRD 之前，本文档对教授域采集需求的解释优先于 `Professor-Data-Agent-PRD.md`；不改变 `Data-Agent-Shared-Spec.md` 的共享强制规则。
>
> **用途**：作为下一阶段教授域演进的需求基线 + 排期基础。
>
> **范围限制**：评估只看「**代码是否实现该能力**」（有 module / 有 endpoint / 有迁移），**不看 E2E 数据 / 不看准确率 / 不看真实环境跑通与否**。

---

## 0. 文档定位与使用方式

- 这是一次需求 **对齐 + 校准**，不是新设计。原 PRD 主体保留，仅对若干表述给出更具体口径或新增字段。
- 若与 `Professor-Data-Agent-PRD.md` 冲突，**临时**以本文档为准；下一步动作是把本文档 §1–§7 沉淀回 PRD 后撤掉本文档。
- 25 步原始问答见**附录 A**，可追溯每条需求的来源原话。

## 1. 采集对象定义（Step 1–2）

### 1.1 机构范围（Step 1）

确认口径：**PRD §3.1 默认**。

- 深圳本地高校：SZU / SUSTech / HITSZ / SZTU / SZUPL 等
- 异地高校在深实体研究机构：清华深研院 / 北大深圳 / CUHK 深圳 / SYSU 深圳 / HIT 深圳 / BIT 深圳 等
- 在深独立科研机构：中科院深圳先进院 / 鹏城实验室 / 深圳湾实验室 等

### 1.2 角色 / 用工形式（Step 2）

确认口径：**不预定义角色 filter**。

- 采集对象 = §1.1 机构在 seed 页面所展示的所有教师，**不再额外按职称或在编与否过滤**
- 「教授 / 副教授 / 助理教授 / 讲师 / 研究员 / 双聘 / 兼职 / 博士后」从 seed / Tier 2 信息中读出，作为属性字段而非入口判断

## 2. Seed 机制（Step 3–9）

### 2.1 颗粒度（Step 3）

- **院系级为主**：1 个 seed = 1 个院系教师列表页
- **特例**：学校全校统一一个教师页（如南科大）→ 学校级 seed，parser 优先 STEM 老师，全爬可接受（STEM 是主体）
- 即 seed 颗粒度有两种：`dept` / `school`（隐式由 `department` 是否为空推断）

### 2.2 学科范围（Step 4）

- **配置驱动 + 人工选取阶段保证 STEM**
- 院系级 seed 时人工只选 STEM 院系
- 学校级 seed 时优先 STEM 老师；非 STEM 占比小可全爬

### 2.3 维护方式（Step 5）

- **人工收集**

### 2.4 形态（Step 6）⚠️

- **Admin Console Web 页面**（不是 YAML、不是 Markdown 文件、不是代码常量）
- 当前代码现状：seed 信息散落在 `professor/discovery.py`、`professor/pipeline.py`、`scripts/e2e_seed_*.md` 等多处；**没有**统一的 `apps/miroflow-agent/config/professor_seed_urls.yaml`（PRD §9 该示例文件实际不存在）
- 需新增：DB 表 + FastAPI CRUD endpoints + React 页面

### 2.5 功能（Step 7）

- **纯 CRUD**：列出 + 新增 + 编辑 + 删除 + URL 格式校验
- 不做：运行状态展示、一键采集触发、批量 Excel 导入

### 2.6 字段 schema（Step 8）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `school` | str | 是 | 高校 / 机构标准化名称 |
| `department` | str | 否 | 院系；学校级 seed 时为空 |
| `seed_url` | URL | 是 | 教师列表页 URL |
| `discipline_tag` | enum | 是 | `STEM` / `HSS` / `MIXED` |

`granularity`（dept / school）由 `department` 是否为空隐式推断，不显式存。

### 2.7 抓取完整性（Step 9）

- **目标 100%**：seed 页上每个教师都要被识别
- **失败可见**：抽取数 < 页面候选数时差额写入 `pipeline_issue` 表（V006 已建），admin console 可见
- 允许人工兜底补登

## 3. 三层采集级联（Step 10–12）

```
Tier 1：seed 页面（院系/学校教师列表页）
  ↓ 解析教师列表
Roster 输出：name + school + dept + 可能含 homepage_url + 基础信息（职称/照片等）

  ↓ 点 Tier 1 给的链接进入
Tier 2：学校官网教师主页
  ↓ 解析：简介 / 研究方向 / 项目 / 近期论文
  ↓ 可能含：个人维护主页链接

  ↓ 递归 1 跳
Tier 3：教师个人维护主页
  ↓ 信息最丰富

兜底：Tier 1 没有 Tier 2 链接时，走 Web Search 找 Tier 2 / Tier 3
```

### 3.1 Roster 输出 / 缺主页 URL 处理（Step 10）

- Roster 一条记录最低字段：`name + school + dept`，`homepage_url` 可空
- 缺 `homepage_url` 时打 `missing_homepage` 入 `pipeline_issue`
- per-prof agent 拉起后调 search agent 找 Tier 2；找不到不跳过该老师，走「姓名 + 院系 + 外部补足」简化路径

### 3.2 Tier 3 递归边界（Step 11）

- **根 + 1 跳子页**
- 1 跳含的常见类型：Publications / CV / Bio / Group / Research / Teaching / Awards / Projects

### 3.3 Web Search 身份验证（Step 12）

- **强信号自动通过**：候选页同时命中 `name + 学校 + 院系` → 自动接受
- **弱信号 LLM 终审**：缺一项 / 学校院系部分匹配 / 同名 → 调 LLM 看候选页全文与 Tier 1 已知信息对比 yes/no

## 4. Per-prof 字段范围与摘要字段（Step 13–15）

### 4.1 字段优先级

| 类别 | 字段 | 优先级 | 备注 |
|---|---|---|---|
| 基础 | `name` / `name_en` / `institution` / `department` / `title` / `homepage` / `email` | **MUST** + 必须验证 | 科创问答价值有限，但**不可缺**；从官网抓基本准确，仍要走身份验证 |
| 画像 | `profile_summary` / `research_directions` | **重点** | 必须结合 paper 信号 |
| 指标 | `h_index` / `citation_count` / `paper_count` | best-effort | 采集，不做强验证 |
| 跨域 | `company_roles` / `patent_ids`（patent 反向派生） | **MUST** | |
| **新字段** | `paper_summary`（教授侧）| **MUST** | 该教授所有 verified 论文的 LLM 汇总，PRD / schema 都没有 |
| **新字段** | `patent_summary`（教授侧）| **MUST** | 该教授所有专利的 LLM 汇总，PRD / schema 都没有 |

### 4.2 论文链接与教授摘要的关系

- 论文由 `professor_paper_link` 表派生展示，**不作为 professor 表字段**
- 但教授侧需要 `paper_summary` 字段，对该老师所有 verified 论文做 LLM 汇总（不同于 `profile_summary` 的画像总摘要）

### 4.3 教授侧 paper_summary / patent_summary 实现方式（Step 15）

- **落库 + LLM 生成 + 类域更新后增量刷新**
- 落 Postgres `professor` 表两个新列（或独立表）
- LLM 从该教授的 verified 论文集 / 专利集生成 200–300 字摘要
- 触发：paper / patent 域有新变化 → 增量刷新受影响教授

## 5. 多源融合 / 反哺 / 摘要生成（Step 16–18）

### 5.1 字段优先级矩阵（Step 16）

| 字段类别 | 权威源 | 备注 |
|---|---|---|
| 身份字段（institution / department / title / email / homepage） | **Tier 2 学校官网优先** | 不冲突时 Tier 3 / Scholar 不替换 |
| 学术字段（research_directions / awards / projects / publications） | **Tier 3 + paper 反哺优先** | 个人主页与论文反映最新研究 |
| 指标字段（h_index / citation_count / paper_count） | **OpenAlex / Scholar 优先** | 学术平台是权威源 |

### 5.2 论文反哺细节（Step 17）

- 范围：**近 5 年 verified 论文**（过 `paper_identity_gate`，confidence ≥ 0.8）
- 信号：每篇论文的 `title` + `abstract` + `keywords`
- LLM 归纳 **3–7 个精细 `research_directions`**
- 同时刷新 `profile_summary` + 生成 `paper_summary`

### 5.3 profile_summary 综合生成（Step 18）

- 输入：Tier 2 文本 + Tier 3 文本 + 近 5 年 verified 论文 abstracts + `company_roles` + 专利信号
- LLM 生成 **200–300 字中文**，覆盖 身份 / 方向 / 代表成果 / 重要背景
- 与 PRD §4.2 一致

## 6. 向量化（Step 19）

### 6.1 双 collection 形态

- 1 位教授 = 2 条 Milvus 记录
- **identity 向量**：embed 身份字段（`name + institution + dept + title + email`）
- **research 向量**：embed `research_directions + paper_summary`
- Retrieval 时按 query 类型选 collection
  - 名字 / 机构查询 → identity collection
  - 技术词 / 研究方向查询 → research collection（避免被 profile_summary 稀释）

### 6.2 与代码 audit 差距 #3 的关系

- `professor/vectorizer.py` 字段层已支持双向量
- 但当前 Milvus 是单一 `professor_profiles` collection；plan 001 §Proposed Collections 提的拆分 **未做**
- 需新建 `professor_identity_profiles` + `professor_research_profiles`（或单 collection 多 vector field），并改 `service/retrieval.py` 让其按 query 类型选 collection

### 6.3 Path 2 的存在并不豁免双 collection

- 「用户问具体技术词 → 找做该方向的教授」也可以走 paper 域 `paper_chunks` collection（已建 17K chunks）→ 通过 `professor_paper_link` 反推教授
- 但 paper_chunks 当前是旧文本，`summary_zh` 未 rebackfill 进 chunks（属于 paper 域待办）
- 教授侧自身的 retrieval 仍需双 collection 提供精度

## 7. 运维 / 操作（Step 20–25）

### 7.1 更新节奏（Step 20）

- 月度 seed 全量 re-crawl → 发现新增 / 流失教授
- paper / patent 域有更新 → 增量反哺受影响教授
- **新需求**：admin console 提供 **「周期设置 + 选择哪些域重采」** 的 UI

### 7.2 教授–公司关联（Step 21）

- 信号优先级（PRD §7.1）：
  1. 企业域 ID match → **自动接受**
  2. 公开网页证据（`source_url` 必须可点击）→ LLM 终审
  3. Web Search → LLM 终审
- Timing：**异步回填**，教授 release 不阻塞

### 7.3 质量门（Step 22）

- `canonical_name_zh` 必填；`canonical_name_en` 过 LLM 双语门 confidence ≥ 0.8 才赋值，否则 NULL
- `professor_paper_link` confidence ≥ 0.8 才 verified；不过为 candidate + 入 `pipeline_issue`
- `profile_summary` 过 STEM/HSS 学科敏感门（不能是 boilerplate）
- 三项全过 → `quality_status = ready`

### 7.4 流失 / 转校（Step 23）

- **流失**：seed re-crawl 不见某教授 → 标 `archived`，不删除，保留与 paper / patent 的历史关联
  - 当前 `quality_status` 4 值（`ready` / `needs_review` / `low_confidence` / `needs_enrichment`）**不含** `archived`
  - 需新增状态值，或独立 `is_active` / `lifecycle_state` 字段
- **转校识别**：A 校失踪 + B 校出现 → 多信号匹配（`canonical_name_zh + canonical_name_en + ORCID + paper history`）高置信判同人 → 更新 `institution / dept` + `evidence` 记转校来源

### 7.5 Admin 操作面（Step 24）

- 查看 + 标注 + **字段人工编辑**
- 人工编辑写 `manual_review` evidence
- 标记被人工编辑的字段，**下轮 pipeline 不刷掉**（需 `manual_override` 之类的字段标记机制）

### 7.6 敏感字段（Step 25）

- `email` / `phone` / `office` 全采 + 全展示
- 数据来源是公开 .edu.cn 页面 + B2B 场景需要联系方式

---

## 8. 代码 vs 需求评估

> **评估时点**：commit `4858404`（2026-05-09）。仅看代码是否实现，不看准确率 / E2E。

### 8.1 评估表

| Step | 需求要点 | 代码现状 | 满足度 | 关键文件 / 缺口 |
|---|---|---|---|---|
| 1 | 机构范围（本地 + 分校 + 科研机构） | `professor/institution_registry.py` (4 KB) + `institution_names.py` (5 KB) 有机构白名单 | 🟡 | 需核 3 类机构是否分类覆盖；目前主要是 SZU / SUSTech / HITSZ / SZTU / 清华深研院 / CUHK 深 等 STEM-leaning 列表 |
| 2 | 角色委托 seed | `roster.py` (50 KB) 不预定义角色 filter | ✅ | |
| 3 | Seed 颗粒度 dept + school 特例 | seed 信息散落在 `discovery.py` / `pipeline.py` / `scripts/e2e_seed_*.md`；无 granularity 字段 | 🟡 | 需扩 schema |
| 4 | Seed 学科 STEM 优先 | `quality/threshold_config.py` 有 STEM/HSS 桶；seed 层不打 `discipline_tag` | 🟡 | 需扩 seed schema |
| 5 | Seed 维护 = 人工 | 现状是人工，但散落多处 | ✅ | 维护方式对，形态另议 |
| **6** | **Seed Admin Web 页面** | ❌ admin console 无 seed UI（`backend/api/` 下无 seed/seeds endpoint） | ❌ | **新工程** |
| **7** | **Seed CRUD** | 同上 | ❌ | |
| **8** | **Seed schema 含 discipline_tag** | 当前无统一 seed 表/文件 | ❌ | |
| 9 | 抓取完整性目标 100% + 差额入 issue | `pipeline_issue` 表（V006）在；seed 抓取层「应抓 vs 实抓」差异检测 + 自动写 issue 待核 | 🟡 | 解析失败可入 issue，但「页面候选 vs 已抽取」对比逻辑需核 |
| 10 | 三层级联 + 缺主页标 issue + Web Search 兜底 | `roster.py` (50 KB, T1) + `homepage_crawler.py` (64 KB, T2/T3) + `web_search_enrichment.py` (31 KB, 兜底) | ✅ | 主体在 |
| 11 | Tier 3 递归 = 根 + 1 跳 | `homepage_crawler.py` 有递归；边界是否锁 1 跳待核 | 🟡 | 加配置 / 显式断言 |
| 12 | Web Search 身份验证强 / 弱信号分流 | `name_identity_gate.py` (5 KB, 双语门) + `identity_verifier.py` (6 KB) | 🟡 | 「强信号自动 + 弱信号 LLM」分流是否显式存在待核 |
| 13a | 基础字段（name / inst / dept / title / email / homepage） | V003 / V010 schema 全有 | ✅ | |
| 13b | 画像字段（profile_summary + research_directions） | V010 schema + `summary_generator.py` (11 KB) | ✅ | |
| 13c | 指标字段（h_index / citation_count / paper_count） | V012 schema + `openalex_metrics.py` (6 KB) | ✅ | |
| 13d | 跨域字段（company_roles + patent_ids） | V005b `cross_domain_relations` + `cross_domain_linker.py` (13 KB) | ✅ | |
| 14 | 指标 best-effort（不强验证） | 现状无强验证 | ✅ | |
| **15** | **教授侧 paper_summary / patent_summary 字段** | ❌ schema 不存在；generator 不存在 | ❌ | **新工程** |
| 16 | 多源字段优先级矩阵 | `canonical_writer.py` (36 KB) 有合并；无显式 priority matrix 模块 | 🟡 | 隐式存在，建议集中显式化 |
| 17 | 论文反哺近 5 年 + LLM | `summary_reinforcement.py` (6 KB) + `paper_collector.py` (42 KB) + `scripts/run_profile_summary_reinforcement.py` | 🟡 | 5 年窗口配置化、参数化待核 |
| 18 | profile_summary 综合生成 | `summary_generator.py` + `summary_reinforcement.py` | ✅ | 综合源 + LLM 都在 |
| **19** | **双 Milvus collection** | `vectorizer.py` (8 KB) 字段层支持；Milvus 仅 `professor_profiles` 单 collection | 🟡 | 与 plan 001 §Proposed Collections 对齐缺口 |
| 20a | 月度 seed + 增量反哺 | `scripts/run_*` 脚本 + `summary_reinforcement.py` | 🟡 | 调度 ad-hoc，无统一 scheduler |
| **20b** | **Admin Scheduling UI** | ❌ | ❌ | **新工程** |
| 21 | 公司关联 PRD §7.1 + 异步 | `company_linker.py` (4 KB) + `cross_domain_linker.py` + V005b | ✅ | |
| 22 | 三道质量门 | `name_identity_gate.py` + `paper_identity_gate.py` (12 KB) + `quality_gate.py` (13 KB) | ✅ | 三门齐全 |
| **23a** | **流失 archived 自动化** | `quality_status` 4 值不含 `archived`；seed 月度对比 → 自动 archived 的逻辑无 | ❌ | 需加状态值 / 字段 + 对比逻辑 |
| **23b** | **转校识别 / 自动 merge** | ❌ 无专用模块 | ❌ | **新工程** |
| 24 | Admin 字段人工编辑 + manual_override 锁 | `apps/admin-console/backend/api/review.py` 部分；字段编辑 + manual_override 待核 | 🟡 | |
| 25 | 敏感字段全采全展示 | V003 schema 有 `email` 字段；admin / chat API 暴露 | ✅ | |

### 8.2 满足度汇总

| 满足度 | 数量 | 占比 |
|---|---|---|
| ✅ 已满足 | 10 | 36% |
| 🟡 部分实现 | 12 | 43% |
| ❌ 缺失 | 6 | 21% |

> 28 项中（含 Step 13a–d 拆 4 项 + 20a/20b 拆 + 23a/23b 拆 + 6/7/8 拆）

---

## 9. 工程量分级

### 9.1 新工程项（4 大项）

| # | 项 | 涉及 Step | 工作量 | 优先级 | 备注 |
|---|---|---|---|---|---|
| 1 | **Seed Admin Web 页面 CRUD + DB 表 + 数据迁移** | 6 / 7 / 8 + 3 / 4（schema 升级合并）+ 9（差额入 issue 触发点） | 中（3–5 天） | **P1** | 阻塞 seed 维护流程升级；含散落 seed 信息收敛到表 |
| 2 | **教授侧 paper_summary / patent_summary 字段 + LLM generator** | 15 + 17（反哺触发联动） | 中（2–3 天 + LLM prompt 调优） | **P1** | 用户在 Step 13 强调；直接改善画像质量 |
| 3 | **Admin Scheduling UI（周期设置 + 选择重采域）** | 20b + 20a（月度 / 增量调度收敛） | 中–大（5–7 天） | P2 | 调度可靠性是难点 |
| 4 | **流失 archived + 转校识别 / 智能 merge** | 23a / 23b | 大（5–10 天） | P2 | 转校 merge 涉及风险，需人工 confirm 兜底；含 `quality_status` 状态扩展或新增 `lifecycle_state` |

### 9.2 部分实现需补强（小工作量但关系到契约 / 配置 / 模块边界）

建议在 §9.1 新工程项之间穿插：

- **3/4/8**：Seed schema 加 `discipline_tag` + 隐式 `granularity`（与 §9.1 #1 一并做）
- **9**：Seed 抓取「应抓 vs 实抓」差异检测 + 自动写 `pipeline_issue`
- **11**：Tier 3 递归深度锁 1 跳（加配置 / 显式断言）
- **12**：Web Search 身份验证强 / 弱信号显式分流
- **16**：多源字段优先级矩阵集中模块化（从 `canonical_writer.py` 抽出独立 module）
- **17**：论文反哺 5 年窗口参数化
- **19**：双 Milvus collection 拆分 + retrieval 端 collection 选择逻辑（兑现 plan 001 §Proposed Collections）
- **20a**：月度 + 增量调度从脚本上升为统一 scheduler（与 §9.1 #3 一并做）
- **24**：字段人工编辑 + `manual_override` 字段标记机制 + UI 表单

### 9.3 已满足项（10）

Step 1 / 2 / 5 / 10 / 13a / 13b / 13c / 13d / 14 / 18 / 21 / 22 / 25 — 不需要新工程；如有微调按 maintenance 走。

---

## 10. 与现有 PRD / 计划 / Spec 的关系

| 文档 | 关系 |
|---|---|
| `docs/Professor-Data-Agent-PRD.md` | 本快照在若干口径上比 PRD 更具体或新增字段；典型差异：seed 形态从 PRD §9 的 YAML 配置改为 admin web 页面、新增教授侧 `paper_summary` / `patent_summary`、向量化双 collection、`archived` 状态、转校识别。沉淀回 PRD 后撤本文档 |
| `docs/Data-Agent-Shared-Spec.md` | §5.2 教授强制规则不变；§4.3 教授字段需补 `paper_summary` / `patent_summary`；§4.5 evidence 增加 `manual_review` source_type（已有该枚举） |
| `docs/index.md` | 教授行的实现状态矩阵需重新校准 |
| `docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md` | §Proposed Collections（双 collection）= 本快照 §6；§Serving Projection 与 §7.4 archived 相关；该计划仍 OPEN |
| `docs/plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md` | School adapter 集中化与本快照相容（§9.2 未列） |
| `docs/plans/2026-04-23-001-m1-identity-gate-v2.md` | M1 已实现，覆盖 Step 22 三道门的部分（Round 7.17 + Round 8c） |

---

## 11. 推荐下一步

1. **本文档 review + 更正**：项目所有者过一遍 §1–§7（需求口径）和 §8（评估），有口径不准的地方在评论里指出
2. **沉淀回 PRD**：把本文档 §1–§7 合入 `docs/Professor-Data-Agent-PRD.md`，更新 `docs/index.md` 教授行
3. **拆分 4 个新工程项为独立计划**（按 §9.1 优先级）：
   - `docs/plans/2026-05-09-prof-seed-admin-console-crud.md`（P1，与 schema 升级合并）
   - `docs/plans/2026-05-09-prof-paper-patent-summary.md`（P1）
   - `docs/plans/2026-05-09-prof-admin-scheduling-ui.md`（P2，与 20a 调度统一合并）
   - `docs/plans/2026-05-09-prof-archived-and-transfer-merge.md`（P2）
4. **§9.2 11 项需补强**作为 maintenance backlog 跟进
5. **类似流程跑 paper / company / patent**：分别产出对应的 `Requirements-Audit` 文档

---

## 附录 A：原始确认问答（25 步）

为可追溯，记录 2026-05-09 一次确认中用户的原始回答。问题由 AskUserQuestion 工具提出。

### Step 1：机构范围
**问**：哪些机构的教师纳入采集池？
**答**：PRD 默认口径 (推荐) — 深圳本地高校 + 异地高校在深实体研究机构 + 在深独立科研机构

### Step 2：角色 / 用工形式
**问**：哪些「教师身份」纳入采集？
**答**（custom）：通过 seed 页面能访问到的，就是各个学校院系官网展示的有哪些老师，作为老师发现的源头

### Step 3：Seed 颗粒度
**问**：一个 seed 页面是什么层级？
**答**：院系级教师列表页 (推荐)

### Step 4：Seed 学科范围
**问**：每个学校要覆盖哪些院系的 seed？
**答**（custom）：配置驱动，但是由于 Seed 页面是人工选的，所以一定只选 STEM 的页面，如果像是南科大那样全校统一一个老师页面，优先爬取 STEM 学科的老师（不过南科大主要就是 STEM 只有少量文科类老师，全爬了问题不大）

### Step 5：Seed 维护
**答**（follow-up）：seed 页面是人工收集，以某种格式填在文档中

### Step 6：Seed 形态
**问**：人工收集的 seed 列表在哪里、用什么格式、谁维护？
**答**（custom）：这里最好做一个简单的 web 页面，列出具体的院系，和相应的 URL

### Step 7：Seed Admin Web 页面功能边界
**答**：纯 CRUD (推荐 — 符合「简单」)；并且可以添加或删除

### Step 8：Seed 字段 schema
**答**：+ discipline_tag (推荐) — school + department + seed_url + discipline_tag (STEM/HSS/MIXED)

### Step 9：抓取完整性
**答**：目标 100% + 失败可见 (推荐)

### Step 10：缺主页 URL 处理
**答**（custom）：一般学校官网的 seed 页面会列出所有老师，一般是有老师的姓名照片和基本信息（如职称教授、副教授等），然后点击老师名字或照片进入老师在学校官网的主页，老师学校官网主页一般会有更丰富的老师信息的介绍（通常包含简介、研究方向、项目、近期发表的论文等，也有可能有老师个人维护主页的链接，老师个人维护的主页一般信息更为丰富必须要递归爬取）如果学校官网的 roster 页面只有简单信息无法进一步点击先把这些信息收集了，然后走 web search（但必须确认 search 出来的老师就是之前官网的老师）

### Step 11：Tier 3 递归边界
**答**：根 + 1 跳子页 (推荐)

### Step 12：Web Search 身份验证
**答**：强信号自动过 + 弱信号 LLM 终审 (推荐)

### Step 13：Per-prof 字段范围
**答**（custom）：核心四件套 — 基础没问题，在科创问答中可能有相关需求的不多，这个 web search 能很好解决；画像是重点，因为在回答科创问题时，老师的画像会给提问者更丰富的信息，而且有些老师自己写在官网的简介并不全，而且不新，结合 paper 能给出老师更准确的画像；指标这里很难统计准确，实时性要求比较高，我目前不太清楚这个在科创问答中的作用；跨域重要可以帮助用户了解到哪个专利和某位老师相关，某位老师和某个专利相关，而且这些信息应该专门在老师信息这边有个专利的 summary。论文是画像重要的来源，其实可以单独有个字段是该老师论文的 summary。

### Step 14：指标态度
**答**（custom）：可以采集，不做强验证。此外，基础字段必须采集，我的意思是在当前场景下对用户提供的作用可能有限，但是这些基础信息是必要的而且要验证不过如果从官网抓取基本也是准确的

### Step 15：教授侧 paper / patent summary 实现
**答**：落库 + LLM 生成 + 类域更新后增量刷新 (推荐)

### Step 16：多源同字段冲突
**答**：字段优先级矩阵 (推荐、符 PRD §3.3)

### Step 17：论文反哺
**答**：近 5 年 verified 论文 + LLM (推荐、符 PRD §6.3)

### Step 18：profile_summary 生成
**答**：Tier2 + Tier3 + 论文反哺 + 跨域 → LLM (推荐)

### Step 19：向量化 collection（重问后）
**问（用户挑战）**：单 collection + 多字段融合是否会因为融合找不到相关信息？比如用户问了一个具体的具身智能的技术，通过教授的 paper summary 就能知道这个教授是做相关方向的，这个场景，单 collection + 多字段融合向量能否找到？
**答**（重问后）：双 collection (identity + research) (推荐)

### Step 20：更新节奏
**答**（custom）：月度 seed 全量 re-crawl 发现新增/流失教授 + paper/patent 域更新后增量反哺受影响教授 + 在 console 页面设置更新周期，或是指定哪些域重采

### Step 21：教授–公司关联
**答**：PRD 默认 + 异步回填 (推荐)

### Step 22：质量门
**答**：PRD + Round 7.17/8c 默认 (推荐)

### Step 23：流失 / 转校
**答**：Archived + 智能转校识别 (推荐)

### Step 24：Admin 操作面
**答**：+ 字段人工编辑 (推荐)

### Step 25：敏感字段
**答**：全采 + 全展示 (推荐)

---

**文档生成时间**：2026-05-09
**确认会话**：claude-opus-4-7（1M context）+ 项目所有者，25 步 AskUserQuestion 顺序确认
**评估代码版本**：commit `4858404`
