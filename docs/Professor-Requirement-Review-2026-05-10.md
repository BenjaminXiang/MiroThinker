---
title: Professor Requirement Review — 决策快照（2026-05-10）
date: 2026-05-10
status: active
type: requirement_review_decisions
calibrates:
  - docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md
related:
  - docs/Data-Agent-Shared-Spec.md (§4.2, §5.2)
  - docs/index.md
  - openspec/changes/archive/2026-05-10-resolve-professor-canonical-baseline/
covers_domains:
  - professor
  - paper (only the from-prof-page discovery sub-flow; full Paper review pending)
  - patent (only the from-prof-page discovery sub-flow + 2-source clarification)
governance:
  authority_layer: |
    Audit doc is canonical for Professor-domain *needs* (what we want).
    This Review is canonical for *decisions on top of those needs* (how the
    spec will express them). Together they replace the legacy Professor PRD
    for purposes of OpenSpec spec / plan drafting.
  precedence_when_conflict_with_audit: |
    This Review overrides Audit for any item where the user explicitly
    decided differently on 2026-05-10. Examples: Theme 1 institution
    whitelist (out-of-scope here, listed in Audit §1); discipline_tag enum
    (dropped here, listed in Audit §2.6); Theme 7.1 paper discovery scope
    (narrowed here, broader in Audit §5.2).
review_session: 2026-05-10 (Audit-driven walk-through)
---

# Professor Requirement Review — 决策快照（2026-05-10）

> 这份文档是 2026-05-10 与项目所有者完成的 Professor 域 + Paper-from-prof-page 子流 + Patent-from-prof-page 子流的需求 review。所有决策均已锁定，作为后续 OpenSpec spec / plan 起草的输入。
>
> **不是新需求文档**——需求口径仍在 Audit doc。本文档只记录"对每条需求做了什么决策"。

---

## 0. 文档定位

| 维度 | 说明 |
|---|---|
| 作用 | 把 Audit doc 的需求条目逐条 review，记录 user 决策；下游 OpenSpec spec 直接照搬本文档结论 |
| 与 Audit doc 的关系 | Audit = needs（用户想要什么）；本文档 = decisions（这些 needs 在 spec 里怎么落） |
| 与 PRD 的关系 | PRD legacy；不再使用 |
| 与未来 OpenSpec specs 的关系 | 每条 spec 的 Requirement / Scenario 应该回引本文档的 Theme 编号 + Audit 编号双指针 |
| 跨域 spillover 处理 | Paper 域全量 review 仍待做（本次只动 paper-from-prof-page）；Patent 域两个来源（prof page + xlsx）已明确 |

---

## 1. Meta-原则（spec 顶层不变量）

> **本系统是科创检索系统，不对数据真实性兜底。Identity gate 仅验证"同人 vs 同名"，不验证"内容真假"。**

这条原则在 Theme 4.3 / 5.2 / 5.3 / 5.4 / 9.6 / Paper Q1-Q4 / Patent Q3 上反复贯穿，必须写入每一份新 spec 的顶层"非目标 / 不变量"段。

派生规则：
- 教授官网 / 个人主页声明的 = 系统采信的事实表达
- 论文 / 专利 / 项目 在外部 DB 找不到 → 仍可入库，trust 页面
- "数据错了"是教授自己的责任（应通过页面下架 / 修改），不是系统的责任

---

## 2. 三域 prof page 集成 crawl 流（最终架构）

```text
Per-school adapter 解析 Tier 2 / Tier 3 教授页面
  ├─ 教授基础字段 → professor 表
  │   ├─ 基础（name/title/email/...）→ V003/V010
  │   ├─ 画像 (profile_summary) → LLM 生成
  │   ├─ paper_summary (NEW) → LLM 生成（长度自适应）
  │   └─ patent_summary (NEW) → LLM 生成（长度自适应）
  │
  ├─ Publications 区段
  │   └─ 每条 → paper-from-prof-page flow：
  │       ├─ 匹配 paper canonical（DOI 优先；title+year+first_author fallback）
  │       │   ├─ 命中 → 建/更 professor_paper_link
  │       │   └─ 不命中 → 新建 paper（trust 页面，preprint / accepted-not-published 场景）
  │       ├─ paper_identity_gate ≥0.8（仅同人/同名）
  │       └─ enrichment 后续异步：OpenAlex / Crossref / S2 补 DOI / abstract / citation_count
  │
  └─ Patents 区段（如有）
      └─ 每条 → patent-from-prof-page flow：
          ├─ 匹配 V004 patent canonical（patent_id 硬匹配）
          │   ├─ 命中 → 建/更 professor_patent_link
          │   └─ 不命中 → 新建 patent（trust 页面，等 xlsx 后续合并或留 needs_enrichment）
          └─ patent_identity_gate ≥0.8（仅同人/同名）
```

外部数据源角色：
- OpenAlex / Crossref / Semantic Scholar / arXiv / DBLP / Web Search → **仅 Paper enrichment**，不做 discovery
- 外部 patent DB API / Web Search → **明确不在系统能力内**
- xlsx import → Patent 第二条 ingest 路径（已实现，V004 + `run_patent_import_e2e.py`）；与 prof-page 发现的 patent 通过 `patent_id` 硬匹配合并

---

## 3. 锁定决策（按域）

### 3.1 Professor 域

#### Theme 1 ⛔ out of scope
- ~~机构白名单（深圳本地高校 / 异地分校 / 独立科研机构）~~
- ~~角色 / 用工形式 filter~~
- 决策：admin 在 seed UI 添加什么 seed URL 就采什么；系统不做"机构是否在深圳"前置校验
- 蕴含：Audit §7.3 质量门 1 "institution 必须属于深圳高校范围" 失去前提
- 代码侧：`institution_registry.py` 白名单功能 obsolete；名称归一化用途独立保留

#### Theme 2 Seed 表 + Admin Console（最终 schema）

| 列 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `school` | str | 人工填 | 学校名 |
| `department` | str (nullable) | 人工填 | 院系名；全校统一 roster 时为空 |
| `seed_url` | URL | 人工填 | 教师 roster 页面 URL |
| `last_run_at` | timestamp | auto | 最近一次抓取完成时间 |
| `last_run_status` | enum (5 值) | auto | `success` / `failure` / `in_progress` / `never_run` / `adapter_missing` |

**MVP 功能**：5 CRUD（list / add / edit / delete / URL 格式校验）+ **运行状态展示** + per-row "立即爬取" 按钮 → `POST /api/seeds/<id>/trigger` → 异步 pipeline → upsert 语义（已在 → update；新发现 → insert）

**砍掉**：~~`discipline_tag` enum~~（admin 看 school+department 已能识别）、~~`granularity` 显式字段~~（不区分学校 vs 院系级）、~~用户登录 / 权限~~（MVP 不做）、~~批量 Excel 导入~~（Phase 2 决定）

**cron**：cron 月度全量 re-crawl + admin 手动按钮 双轨；现阶段月度自动可能产生批量 needs_review，admin 需事后审。

#### Theme 3 三层采集级联

| 子点 | 决策 |
|---|---|
| 3.3 Tier 3 边界 | **per-school/per-dept 定制 adapter** 架构（取代 Audit "1-跳" 通用规则）；adapter 决定 Tier 3 深度（个人主页子树深度由 adapter 内逻辑决定） |
| 3.3 follow-up | **新 seed 无 adapter → 阻断**；`last_run_status = adapter_missing`；admin UI 直接显示需要联系开发；新学校上线节奏 = adapter 编写节奏 |
| 3.4 Web Search 身份验证 | 强 / 弱信号分流：强（name + 学校 + 院系 三者全命中）自动；弱信号 LLM 终审 |

#### Theme 4 教授字段

| 子点 | 决策 |
|---|---|
| 4.1 基础字段 | 默认 trust 页面；只有 `name_en` 走 LLM 双语门 confidence ≥0.8（Audit §7.3） |
| 4.3 指标字段 | h_index / citation_count / paper_count 全部保留，best-effort，不强验证 |
| 4.5 `paper_summary`（新字段） | 独立列；长度自适应；目标 = 简洁清晰画像、retrieval 友好；输入 = 该教授所有 verified paper |
| 4.6 `patent_summary`（新字段） | 独立列；长度自适应；输入 = 该教授所有 linked patent（含 prof-page 发现 + xlsx 命中） |
| 4.7 论文链接 | 仍以 `professor_paper_link` 派生，不作为 professor 主表字段（沿用 Audit） |

#### Theme 5 跨域关联

| 子点 | 决策 |
|---|---|
| 5.2 教授↔公司 | trust 页面（不分权威性等级）；Audit 优先级矩阵（企业 ID match → 公开网页证据 → Web Search）保留作为 LLM judge 提示，非硬规则 |
| 5.3 教授↔专利同名 | **完全 trust，不消歧** |
| 5.4 项目（funding） | 不外采；trust Tier 2/3 页面；`projects` 字段保留 |

#### Theme 6 多源融合

| 子点 | 决策 |
|---|---|
| 6.1 / 6.2 / 6.3 priority matrix | 保留 Audit §5.1 优先级语义（身份 = Tier 2 优先；学术 = Tier 3 + paper 优先；指标 = OpenAlex/Scholar 优先）；实现侧 `canonical_writer.py` 隐式合并继续，不强行抽独立模块 |

#### Theme 7 反哺机制

| 子点 | 决策 |
|---|---|
| 7.1 反哺基准 | `paper.publication_date` 在 [today−5y, today]；论文 discovery **仅来自教授学校官网/个人主页**，不外部搜索 |
| 7.2 abstract 缺失 | 仍参与反哺，仅用 title + keywords |
| 7.3 反哺产出 | LLM 归纳 3-7 个 `research_directions`（Audit 默认）；同时刷新 `profile_summary` + 生成 `paper_summary` |
| 7.4 反哺触发 | paper / patent 域有新变化 → 增量；24 小时窗口内合并去抖（实现细节，可后置） |

#### Theme 8 摘要生成 + 向量化

| 子点 | 决策 |
|---|---|
| 8.1 输入预算 | 默认最多 50 篇 paper / token 预算 ~30k；超长时按时间倒序截断 |
| 8.2 boilerplate 检测 | LLM judge "是否套话"；不通过则 `quality_status = needs_review` |
| 8.3 paper_summary vs profile_summary | 独立两个字段，生成逻辑分离；profile_summary = 总画像；paper_summary = 论文聚合 |
| 8.4 双 Milvus collection | ✅ **拆**：`professor_identity_profiles` (embed `name + institution + dept + title + email`) + `professor_research_profiles` (embed `research_directions + paper_summary + patent_summary`)；retrieval 按 query 类型选 |

#### Theme 9 验收 / 运维

| 子点 | 决策 |
|---|---|
| 9.1 三道质量门 | 实际是 4 项（`canonical_name_zh` 必填 + `canonical_name_en` ≥0.8 + `professor_paper_link` ≥0.8 + `profile_summary` 过 boilerplate 检测）；spec 时清理"三道门"的提法 |
| 9.2 archived | 独立 `lifecycle_state` enum (`active / archived / merged_to_other_school`)；与 `quality_status` 正交；archived → active 自动转回（再次出现就刷新） |
| 9.3 转校识别 | **MVP 不做**；仅靠 archived 表达；后续人工 / Round N 发现同人再 merge |
| 9.4 cron | cron 月度 + 手动按钮 双轨 |
| 9.5 manual_override | 永久锁；admin 下次编辑同字段时可点"释放锁"按钮取消 |
| 9.6 opt-out | MVP 不做；走"页面下架"路径 |

### 3.2 Paper-from-prof-page 子流（Paper 域全量 review 待做）

| # | 决策 | 来源 |
|---|---|---|
| B1 | Discovery 仅来自教授学校官网 / 个人主页 | Theme 7.1 |
| B2 | OpenAlex / Crossref / Semantic Scholar / arXiv / DBLP = **enrichment-only**，不做 discovery | Paper Q2 |
| B3 | prof 页列了但外部 DB 查不到 → 创建新 paper 记录，trust 页面（preprint / accepted-not-published 场景） | Paper Q1 |
| B4 | `paper_identity_gate` 仅验证"同人/同名"；阈值 ≥0.8 沿用 | Paper Q4 |
| B5 | Paper 匹配逻辑（默认）：DOI 优先；fallback (title + year + first_author) | spec 起草默认 |
| B6 | summary_zh 生成：仍尝试，输入仅 title 也接受 | spec 起草默认 |
| B7 | `quality_status` for prof-page-only paper：minimum fields 齐全则 ready；否则 needs_enrichment | spec 起草默认 |

### 3.3 Patent-from-prof-page 子流

| # | 决策 | 来源 |
|---|---|---|
| C1 | Patent 来源 **= 2 路**：(1) 教授页面 discovery + (2) xlsx 导入；外部 API / web search **不在系统范围** | 用户 2026-05-10 澄清 |
| C2 | prof 页列了但 V004 查不到 → 创建新 patent 记录，trust 页面 | Patent Q3 |
| C3 | `patent_identity_gate` 仅验证"同人/同名"；阈值 ≥0.8 | Q4 |
| C4 | 同名发明人 **不消歧** | Theme 5.3 |
| C5 | xlsx 与 prof-page patent 合并：`patent_id` 硬匹配；MVP 不做模糊合并 | spec 起草默认 |
| C6 | Patent 不存在外部 enrichment 路径（OpenAlex/S2/Crossref 与专利无关） | Patent Q4 + 用户澄清推论 |

---

## 4. 跨域 spillover（待独立处理）

| 项 | 状态 | 行动 |
|---|---|---|
| Paper 域全量 review（discovery 范围 / OpenAlex 角色 / hybrid.py 现状） | ⏳ 待做 | 独立跑一次 Paper Requirement Review；输出 `docs/Paper-Requirement-Review-<date>.md` |
| Paper-Collection-Multi-Source-Design 与本 Review 的冲突 | 已识别 | 在 Paper review 中明确 OpenAlex 从 primary discovery 降级为 enrichment-only |
| `paper-summary-text-contract-drift-001` / `paper-prd-source-list-stale-001` | 已在 debt-register | Paper review 时一并处理 |
| Patent 域全量 review（xlsx 路径 + V004 schema 现状） | ⏳ 待做 | 优先级低；prof-page 子流已明确即可推进 P1 work |

---

## 5. P1 OpenSpec change 起草顺序（依赖图）

```
#3 prof-seed-admin-console (Standard, 3-5 天)
   │
   ├─ schema: professor_seed 表
   ├─ backend: /api/seeds CRUD + /api/seeds/<id>/trigger
   ├─ frontend: /admin/seeds React 页
   ├─ pipeline: 异步触发 + status 更新
   └─ cron: 月度 + 手动 双轨
        │
        ▼
#2 prof-school-adapter-framework (Standard, 4-6 天)
   │
   ├─ adapter registry interface
   ├─ adapter_missing 检测点
   └─ 1 个参考 adapter 实现
        │
        ▼
#1 prof-paper-patent-from-page-flow (Standard, 3-5 天)
   │
   ├─ Publications 区段解析
   ├─ Patents 区段解析
   ├─ identity gate（仅同人/同名）
   └─ paper / patent canonical upsert（trust 页面）
        │
        ▼
#4 prof-summary-fields (Standard, 2-3 天 + LLM 调优)
   │
   ├─ professor.paper_summary 列（长度自适应）
   ├─ professor.patent_summary 列
   ├─ LLM generator
   └─ 反哺触发去抖
        │
        ▼
#5 prof-double-milvus-collection (Standard, 3-4 天)
   │
   ├─ professor_identity_profiles collection
   ├─ professor_research_profiles collection
   └─ retrieval 端 routing

#6 prof-lifecycle-state (Lite+, 1-2 天) — 与 #1-5 解耦，可任意时机插
   │
   ├─ professor.lifecycle_state enum 字段
   ├─ archived 自动 + 复活逻辑
   └─ admin UI 显示
```

总估期：~17-25 工作日（单人）；可并行项见依赖图。

每个 change 都需要：
- 顶层"非目标 / 不变量"段写入 §1 meta-原则
- spec 的 Requirement 回引本 Review §3 + Audit 编号
- acceptance.md 含可执行验证

---

## 6. 仍未拍板（spec 起草时再决定的 default）

下列项可在每个 change 起草 spec 时直接采用默认值；不阻塞 P1 推进。

| 主题 | 默认值 | 在哪个 change 落地 |
|---|---|---|
| paper 匹配 fallback 算法（无 DOI 时） | `title + year + first_author` 模糊匹配 | #1 |
| summary_zh 输入仅 title 时的最小生成质量 | LLM 自由发挥；不达 boilerplate 标准就 needs_review | #1 + #4 |
| paper_summary 输入预算 token 上限 | 30k tokens | #4 |
| boilerplate 检测算法 | LLM judge | #4 |
| 反哺触发去抖窗口 | 24 小时 | #4 |
| Paper canonical 多人共享时的 `professor_paper_link` 写入幂等性 | upsert by (paper_id, professor_id) | #1 |
| Patent xlsx-prof-page 合并的 patent_id 缺失场景 | MVP 不合并；保留双记录直到下轮 cron | #1 |

---

## 7. 与现有 debt-register 的关系

新 spec 起草过程中，下列已登记 debt 会被部分 / 全部消解：

| Debt ID | 与本 Review 的关系 | 预计在哪个 change 中解决 |
|---|---|---|
| `paper-prd-source-list-stale-001` | 本 Review B1/B2 已隐含决策（OpenAlex 降级 enrichment-only）；需在 Paper review 时正式处理 | Paper review 后的 Paper-side change |
| `paper-companion-design-relationship-001` | 同上 | Paper review |
| `paper-summary-text-contract-drift-001` | Paper review 处理 | Paper review |
| `multi-turn-design-partial-001` | 与本 Review 无直接关系 | 单独 change |
| `agentic-rag-prd-vs-guide-001` | 与本 Review 无直接关系 | 单独 change |
| `agents-specs-frozen-but-uncategorized-001` | Professor 相关 specs 在 P1 起草时回头 triage | 跨 change |

---

## 8. 引用约定

任何引用本 Review 的地方应使用：

> "Per Professor Review 2026-05-10 §3.1 Theme N（回引 Audit §X.Y）"

而不是只引 Audit 或只引 Review，以保证 needs ↔ decisions 双层 traceability。
