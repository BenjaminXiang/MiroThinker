---
title: Paper Requirement Review — 决策快照（2026-05-10）
date: 2026-05-10
status: active
type: requirement_review_decisions
calibrates:
  - docs/Paper-Data-Agent-PRD.md
  - docs/Paper-Collection-Multi-Source-Design.md
related:
  - docs/Professor-Requirement-Review-2026-05-10.md (Theme 7.1 / 5.4 / meta-原则 自动适用 Paper 域)
  - docs/Data-Agent-Shared-Spec.md (§4.2.1 summary_text / §5.3 多源)
  - docs/audits/paper-requirement-code-reconciliation-2026-05-10.md (read-only audit; 本 review 在其基础上锁定决策)
  - docs/index.md
covers_domains:
  - paper (full domain)
governance:
  authority_layer: |
    PRD (Paper-Data-Agent-PRD.md) is canonical for behavior contract.
    MSD (Paper-Collection-Multi-Source-Design.md) is a phasing-implementation
    attachment to PRD; conflicts resolve in PRD's favor (per P5 decision).
    This Review is canonical for *decisions on top of those docs*, exactly
    paralleling docs/Professor-Requirement-Review-2026-05-10.md.
  precedence_when_conflict_with_prd_or_msd: |
    This Review overrides PRD / MSD where the user explicitly decided
    differently on 2026-05-10. Examples: §3.2 fallback is RUN-TIME-ONLY
    (does not write local DB); §5.2 source list rewritten to
    discovery=prof-page + enrichment-only OpenAlex priority; summary_zh
    is a Chinese paragraph (PRD §4.2 JSON shape decision overridden).
review_session: 2026-05-10 (PRD §三–§十一 + MSD §1–§12 walk-through)
---

# Paper Requirement Review — 决策快照（2026-05-10）

> 这份文档是 2026-05-10 与项目所有者完成的 Paper 域需求 review。所有决策已锁定，作为后续 OpenSpec spec / plan 起草的输入。
>
> **不是新需求文档**——需求口径仍在 PRD + MSD（关系见 §3.2 P5）。本文档只记录"对每条需求做了什么决策"。
>
> 与 `docs/Professor-Requirement-Review-2026-05-10.md` 平行；二者共享相同的 meta-原则与跨域决策（特别是 Theme 7.1 离线论文 discovery 范围）。

---

## 0. 文档定位

| 维度 | 说明 |
|---|---|
| 作用 | 把 PRD + MSD 的需求条目逐条 review，记录 user 决策；下游 OpenSpec spec 直接照搬本文档结论 |
| 与 PRD 的关系 | PRD = canonical for behavior contract；本 Review 已对若干表述给出更具体或修订口径，沉淀回 PRD 是后续独立 OpenSpec change 的事 |
| 与 MSD 的关系 | MSD = PRD 的 phasing 实施附件（P5 锁定）；冲突时 PRD 胜 |
| 与 Audit 的关系 | Audit (`docs/audits/paper-requirement-code-reconciliation-2026-05-10.md`) 只做读-only drift 分析；本 Review 在其结论上推进到决策层 |
| 与 Professor Review 的关系 | 共享 meta-原则；论文 discovery 范围（Professor Theme 7.1）决定本 Review 的 §3.1 P7 重写方向 |

---

## 1. Meta-原则（与 Professor Review §1 等同；不重复）

> **本系统是科创检索系统，不对数据真实性兜底。Identity gate 仅验证"同人 vs 同名"，不验证"内容真假"。**

派生到 Paper 域的额外解读：
- 教授页面声明的论文 = 系统采信的事实表达（即便 OpenAlex 查不到，preprint 场景）
- OpenAlex / Crossref / S2 / arXiv / DBLP / Web Search 是"补 metadata 工具"，不承担"这篇论文真实存在"的认证责任
- DOI / Arxiv ID 仅作为去重与 enrichment 索引，不作为"是否真实存在"的判断
- "数据错了"是教授自己页面的责任，不是 Paper 域的责任

---

## 2. 关键架构图（Paper 域版）

```text
                        Professor 域 prof page crawl
                                    │
                                    │  Publications 区段抽取
                                    ▼
        ┌─────────────────────────────────────────────────────┐
        │  Discovery：仅来自教授学校官网 / 个人主页（Theme 7.1）│
        │   ├─ title + year + venue（min set，preprint OK）   │
        │   └─ paper_identity_gate ≥0.8（仅同人/同名）         │
        └─────────────────────────────────────────────────────┘
                                    │
                                    ▼
                        匹配 paper canonical
                  ┌───────────┴───────────┐
                  ▼                       ▼
           已存在 → 更新                新建 paper
           professor_paper_link        evidence.source=prof_page
                  │                       │
                  └───────────┬───────────┘
                              ▼
                   异步 enrichment（best-effort）
                   ┌──────────┬──────────┐
                   │ OpenAlex │ Crossref │  S2 / arXiv 兜底
                   └──────────┴──────────┘
                              │
                  补 DOI / abstract / citation_count / fields_of_study
                              │
                              ▼
                  summary_zh 生成（中文段落 200-400 字）
                              │
                              ▼
                  quality_status 提升 needs_enrichment → ready
                              │
                              ▼
                  写 Postgres + Milvus paper_chunks
                              │
                              ▼
                  反哺 Professor research_directions / profile_summary /
                  paper_summary（Professor Review 已锁）

┌─────────────────────────────────────────────────────────────┐
│  独立路径：chat 用户面 §3.2 实时 fallback                    │
│   user 给显式标题 → 本地未命中 → OpenAlex/Crossref 实时拉   │
│   metadata → 仅运行时返回，**不写本地**                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 锁定决策

### 3.1 本次 review 锁定的 16 条主决策

#### P1 §3.2 实时外部 fallback（chat 路径）
- **决策**：保留 §3.2。user 给显式标题、本地未命中 → chat 服务调 OpenAlex/Crossref 实时返回 metadata。这与"discovery 仅来自教授页面"不冲突，因为 §3.2 是运行时 chat fallback，不进入离线 paper 表。
- **回引**：PRD §3.2

#### P2 summary_zh 形态
- **决策**：改 PRD §4.2 为"中文段落 200-400 字，可选含内部 4-段 markers"。Postgres `summary_zh` 列继续 text 类型。
- **回引**：PRD §4.2；audit `paper-prd-summary-zh-schema-shape-001`

#### P3 summary_text contract drift
- **决策**：修 admin API（`apps/admin-console/backend/api/domains.py:753`），让 `summary_text` 字段实际返回 Postgres `summary_zh`，与 PRD §4.3 + Shared-Spec §4.2.1 契约对齐。Postgres 不加列。
- **回引**：PRD §4.3；audit `paper-summary-text-contract-drift-001`

#### P4 教授页面发现的"薄信息"论文最低字段
- **决策**：`title + year + venue + authors`（authors 可推断为"<教授名> et al."）四项必填；其余 12 项 optional，由后续 enrichment 补齐。
- **回引**：PRD §4.1；与 Professor Review §3.2 B3 一致（"创建新 paper 记录，仅用 prof 页数据"）

#### P5 PRD ↔ MSD 关系
- **决策**：MSD 是 PRD 的 phasing 实施附件。PRD = canonical for behavior contract；MSD = how-to 阶段书，仅描述 Phase A/B 实施顺序。冲突时 PRD 胜。
- **debt 关闭**：`paper-companion-design-relationship-001` decision-locked；待沉淀到 PRD/MSD frontmatter 是后续动作

#### P6 MSD §6.1 "Phase A 不扩 contract" 规则
- **决策**：承认 contract 已进 Phase B 形态。MSD §6.1 改为"Phase A 完成；contract 已扩展为 Phase B 形态"。不回滚已添加的 7 个 Phase B 字段（`tldr / funders / license / oa_status / fields_of_study / reference_count / enrichment_sources`）。
- **debt 关闭**：`paper-prd-msd-phase-a-rule-stale-001` decision-locked

#### P7 PRD §5.2 source list 重写
- **决策**：PRD §5.2 重写为"候选论文发现仅从教授 Tier 2/Tier 3 页面 publications 区段抽取"。同时另起一节列 enrichment 源按优先级：OpenAlex（主）> Crossref > S2 / arXiv（兜底）。与 Theme 7.1 一致。
- **debt 关闭**：`paper-prd-source-list-stale-001` decision-locked

#### P8 PRD §九 7-key YAML config
- **决策**：标 §九 为"Phase 2 候选 · 当前不实现"。本身的 toggle 逻辑（`scholar_enabled / dblp_enabled / explicit_title_realtime_fallback` 等）随 Theme 7.1 改变后需重新设计；不在 Phase A 实现。
- **debt 关闭**：`paper-prd-config-surface-001` decision-locked

#### P9 §5.3 归属与消歧
- **决策**：完全 trust 页面。教授官网 / 个人主页声明的论文 = 该教授发表 → 直接加 `professor_paper_link`，不用多信号验证。仅当 OpenAlex enrichment 后多作者中出现同名冲突时，`paper_identity_gate` 才介入判定"同人/同名"。
- 与 Professor Review §3.2 B3（trust 页面）+ Theme 5.3（patent 完全 trust）一致。

#### P10 enrichment 多源融合优先级
- **决策**：DOI 命中后 OpenAlex 优先 + 其他源补缺字段。具体字段级 fallback：
  - `abstract`：OpenAlex → Crossref → S2 → arXiv（first available）
  - `citation_count`：OpenAlex（唯一）
  - `venue / year`：OpenAlex publication_date / venue
  - `authors`：OpenAlex 作者列表（带 ORCID 优先）
  - `doi / arxiv_id`：所有源都该一致；不一致写 pipeline_issue
- 与 MSD §2 实际实现一致

#### P11 去重优先级
- **决策**：保留 PRD §6 三级 fallback 链：DOI > Arxiv ID > 标题高相似 (近似匹配阈值 0.85+) + 作者高重叠 (Jaccard ≥0.5)。具体阈值进 spec。

#### P12 验收 KPIs（PRD §11）
- **决策**：7 项全保留，仅调整样本集范围：
  - "summary_zh 完整率 ≥90%" 限定为 `quality_status=ready` 集合
  - "summary_text 完整率 ≥90%" 与 P3 修复后等同于 summary_zh 完整率
  - preprint case 在 `needs_enrichment` 不进入验收样本
  - 其他指标（关联覆盖 / 归属准确 / 去重 / 反哺 / Top-5）保持

#### P13 §3.2 chat fallback 是否回写本地 paper 表
- **决策**：不写本地。fallback 纯运行时使用，结果不写 paper canonical，不进 Milvus，不进 pipeline_issue。下次同 user 问同一篇论文仍走 fallback。这保持 "discovery 仅来自教授页面" 边界严格。

#### P14 PRD §4.1 canonical 16 字段裁剪
- **决策**：`pdf_path / title_zh / keywords` 全保留作为 optional。
- 备注：能抓 PDF 仍可抓（不否决 enrichment 抓 PDF），但不强制；不过度设计。其余 13 字段保持原有 must/optional 标注。

#### P15 paper.quality_status enum 6 值（V019 加了 partial + rejected）
- **决策**：保留 6 值。语义：
  - `ready`：minimum fields + summary_zh 已生成 + 通过 boilerplate 检测
  - `needs_review`：人工标注 / 异常需复核
  - `low_confidence`：identity_gate 未达阈值的 candidate
  - `needs_enrichment`：preprint case 等待 OpenAlex/Crossref 补 metadata
  - `partial`：enrichment 部分成功（如 abstract 补了但 citation 没补）
  - `rejected`：LLM judge 判定 boilerplate / 不表达实质内容 / 不应入库

#### P16 §7.4 新鲜度信号
- **决策**：保留作核心需求（不降级为软描述）。论文是教授画像的持续新鲜度信号源；反哺触发去抖窗口 24h（与 Professor Review Theme 7.4 一致）。

### 3.2 自动 carry-over 自 Professor Review（无需重新决策）

| # | 决策 | 来源 |
|---|---|---|
| C1 | 论文 discovery 仅来自教授学校官网 / 个人主页 | Professor Theme 7.1 |
| C2 | OpenAlex / Crossref / S2 / arXiv / DBLP / Web Search = enrichment-only | Professor Theme 7.1 |
| C3 | `paper_identity_gate ≥0.8` 仅验证"同人 vs 同名" | Professor Review §3.2 B3 |
| C4 | 反哺窗口 = `publication_date` 在 [today−5y, today] | Professor Theme 7.1 |
| C5 | 教授页面发现的论文不在 OpenAlex 查不到时仍创建新 paper（preprint 场景） | Professor Review §3.2 B2 |
| C6 | 反哺产出 = LLM 归纳 3-7 个 `research_directions` + 刷新 `profile_summary` + 生成教授侧 `paper_summary` | Professor Theme 7.3 |
| C7 | 反哺触发：paper / patent 域有新变化 → 增量；24h 窗口去抖 | Professor Theme 7.4 |

---

## 4. 仍未拍板（spec 起草时直接采用 default）

| 主题 | 默认值 | 在哪个 change 落地 |
|---|---|---|
| paper 匹配 fallback 算法（无 DOI 时） | `title + year + first_author` 模糊匹配，相似度阈值 0.85 | `prof-paper-patent-from-page-flow` |
| 去重 title-fuzzy 相似度阈值 | 0.85（取 SequenceMatcher 或 token-set ratio） | `prof-paper-patent-from-page-flow` |
| 去重 authors Jaccard 阈值 | 0.5 | `prof-paper-patent-from-page-flow` |
| summary_zh 输入仅 title 时的最小生成质量 | LLM 自由发挥；不达 boilerplate 标准就 needs_review | `prof-paper-patent-from-page-flow` + `prof-summary-fields` |
| boilerplate 检测算法 | LLM judge "是否套话 / 不表达实质内容" | `prof-paper-patent-from-page-flow` |
| 反哺触发去抖窗口 | 24 小时 | `prof-paper-patent-from-page-flow` |
| 多 prof 共享同一 paper canonical | upsert by (paper_id, professor_id) on professor_paper_link | `prof-paper-patent-from-page-flow` |
| paper.quality_status 在 ready 后又收到 enrichment 失败 | quality_status 不降级；写 pipeline_issue | spec 起草时 |
| OpenAlex 调用速率 / 重试 | 1 RPS, 3 retries with exponential backoff | spec 起草时 |
| §3.2 chat fallback 超时阈值 | 5s；超时返回"无法获取" | spec 起草时 |

---

## 5. 跨域 spillover

### 5.1 已识别 + 已锁的 spillover

无新的跨域 spillover。Paper Review 的所有决策已与 Professor Review / Patent-from-prof-page 子流一致。

### 5.2 待 Phase B / 后续 changes 处理的派生工作

| 项 | 状态 | 行动 |
|---|---|---|
| Patent 域全量 review | ⏳ 待做 | Patent 仅 from-prof-page 子流已在 Professor Review 锁定；其他 patent ingest 路径（xlsx）已实现 |
| Company 域全量 review | ⏳ 待做 | 不影响 Phase B；可独立排期 |
| Multi-turn-Context-Manager-Design vs SessionContext 现状对齐 | ⏳ 待做 | debt `multi-turn-design-partial-001` 单独 change |
| Agentic-RAG-PRD ↔ Operating-Guide 关系 | ⏳ 待做 | debt `agentic-rag-prd-vs-guide-001` 单独 change |

---

## 6. P1 OpenSpec change 起草建议（结合 Professor Review 已有清单）

| 顺序 | Change ID | 与本 Review 的关系 | 估期 |
|---|---|---|---|
| 已完成 | `prof-seed-admin-console` Phase A | 不依赖 Paper review | 完成 |
| 1（next） | `prof-paper-patent-from-page-flow` | **本 Review 是必读输入**：Publications 区段解析、preprint 入库、enrichment 异步触发、summary_zh 生成、professor_paper_link upsert、识别 gate 同人/同名 | 中（4-6 天 + LLM 调优） |
| 2 | `prof-summary-fields` | 教授侧 paper_summary / patent_summary；输入 = 该教授所有 verified paper / patent。本 Review §3.2 C6 锁定 | 中（2-3 天 + LLM 调优） |
| 3 | `prof-double-milvus-collection` | identity + research collection 拆分；research vector embed `research_directions + paper_summary + patent_summary` | 中（3-4 天） |
| 4 | `paper-prd-source-list-rewrite` | PRD §5.2 + §九 + §4.2 三处文档级重写；纯 doc change | 小（半-1 天） |
| 5 | `paper-summary-text-contract-fix` | 修 admin API `domains.py:753` 让 `summary_text` 返回 Postgres `summary_zh` | 小（半天 + 测试） |
| 6 | `paper-msd-phase-b-status-acknowledge` | 修 MSD §6.1 承认 contract 已进 Phase B；纯 doc change | 小（半天） |
| 7 | `prof-school-adapter-framework`（增量） | adapter registry 形式化（实际已大部分实现）；增加 adapter_missing 路径写 pipeline_issue | 小（1-2 天） |

每个 change 都需要：
- 顶层"非目标 / 不变量"段写入 Meta-原则
- spec 的 Requirement 回引本 Review §3.1 + 对应 PRD/MSD 章节双指针
- acceptance.md 含可执行验证

---

## 7. 与现有 debt-register 的关系

本 Review 锁定的决策对应的 debt 项处理：

| Debt ID | 状态变化 | 备注 |
|---|---|---|
| `paper-companion-design-relationship-001` | open → decision-locked | P5 决策；待 PRD/MSD 体内实际改动后转 resolved |
| `paper-prd-config-surface-001` | open → decision-locked | P8 决策（Phase 2 候选） |
| `paper-prd-source-list-stale-001` | open → decision-locked | P7 决策（重写 §5.2） |
| `paper-summary-text-contract-drift-001` | open → decision-locked | P3 决策（修 admin API） |
| `paper-prd-msd-phase-a-rule-stale-001` | open → decision-locked | P6 决策（承认 Phase B） |
| `paper-prd-summary-zh-schema-shape-001` | open → decision-locked | P2 决策（中文段落） |

这 6 项实质性 doc/code 修复仍需要后续 OpenSpec change 执行；本 Review 只是把"决策"持久化下来，避免下次 spec 起草时再问一遍。

---

## 8. 引用约定

任何引用本 Review 的地方应使用：

> "Per Paper Review 2026-05-10 §3.1 Pn（回引 PRD §X 或 MSD §Y）"

而不是只引 PRD / MSD 或只引 Review，以保证 needs ↔ decisions 双层 traceability。

跨 review 引用使用：

> "Per Professor Review §3.1 Theme 7.1 + Paper Review §3.2 C1"

---

## 9. 简明决策总览（机器可读速查）

```yaml
paper_review_2026_05_10:
  meta_principle: "system is a 科创检索 system; does not vouch for data truth"

  discovery:
    sources: [prof_school_homepage, prof_personal_homepage]
    external_dbs_role: enrichment_only
    realtime_fallback:
      chat_path: enabled  # P1
      writes_local: false  # P13

  schema:
    summary_zh:
      shape: chinese_paragraph_200_to_400_chars  # P2
      optional_internal_4_section_markers: true
    summary_text:
      contract: "= summary_zh content (no separate column)"  # P3
      admin_api_alias_fix_required: true
    canonical_fields_minimum_for_preprint:
      required: [title, year, venue, authors]  # P4
      authors_inferred_default: "<professor_name> et al."
    canonical_fields_optional:
      kept_optional: [pdf_path, title_zh, keywords]  # P14
    quality_status_enum:
      values: [ready, needs_review, low_confidence, needs_enrichment, partial, rejected]  # P15

  attribution:
    page_trust: full_trust  # P9
    identity_gate_role: "verify same_person vs same_name only"
    no_multi_signal_validation: true

  enrichment:
    source_priority_when_doi_match: openalex_first_others_supplement  # P10
    field_level_fallback:
      abstract: [openalex, crossref, s2, arxiv]
      citation_count: openalex_only
      venue_year: openalex
      authors: openalex_with_orcid_priority
      doi_arxiv_id: cross_check_all_sources_warn_on_mismatch

  dedup:
    priority_chain: [doi, arxiv_id, title_fuzzy_plus_authors]  # P11
    title_fuzzy_threshold: 0.85
    authors_jaccard_threshold: 0.5

  acceptance_kpis:
    keep_all_7: true  # P12
    sample_set_scoping:
      summary_zh_completeness: quality_status_ready_only
      summary_text_completeness: same_as_summary_zh_after_p3
      preprint_excluded_from_acceptance_until_enriched: true

  reinforcement:
    freshness_signal_role: core_requirement  # P16
    debounce_window: 24h
    paper_publication_date_window: 5y

  prd_msd_relationship:
    prd_canonical_for: behavior_contract  # P5
    msd_role: phasing_implementation_attachment
    conflict_resolution: prd_wins
    phase_a_contract_extension_acknowledged: true  # P6 (msd §6.1 broken in code, accepted)

  config:
    prd_section_9_yaml: phase_2_candidate_not_implemented  # P8
```
