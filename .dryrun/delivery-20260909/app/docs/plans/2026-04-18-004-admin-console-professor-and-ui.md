---
title: Admin Console — 教授 / 论文 / 专利域可视化 + 前端 UI
date: 2026-04-18
status: active
owner: claude
extends:
  - docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
  - docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md
---

# Admin Console 教授 / 论文 / 专利域可视化计划

## 0. 当前缺口

Round 4 只做了 company 域的 backend API + tests。教授、论文、专利三域**可入库但不可通过 web 浏览**，只能 psql SQL 查询。前端（DataList / EntityDetail UI）整体缺失。

**真实数据量已经就位**（miroflow_real）：
- 823 教授 + 3523 任职 + 15587 事实（含 6652 研究方向 / 2459 奖项 / 2700 工作经历）
- 7384 论文 + 1550 verified 链 + 7026 candidate 链
- 1024 企业 + 1302 团队 + 575 融资事件 + 3690 专利池（pending patent 域补齐）

## 1. Rounds 分解

### Round 8a — 后端 API 扩展到教授/论文/专利（~1 文件集）

**交付**：`apps/admin-console/backend/api/data.py` 扩展三组新端点，或拆成三个子模块：

```
# Professors
GET  /api/data/professors                 list + filter
     query: q, institution, discipline_family, has_verified_papers, page, page_size
GET  /api/data/professors/{id}            detail
     returns: professor + affiliations + facts (grouped by fact_type) +
              verified_papers (top 20 by citation) + candidate_papers (top 20)
GET  /api/data/facets/professor-institutions    institution counts
GET  /api/data/facets/research-topics           top 50 research_topic values by count

# Papers
GET  /api/data/papers                     list + filter
     query: q, year_min, year_max, has_verified_professor, min_citations, page
GET  /api/data/papers/{id}                detail
     returns: paper + linked_professors (verified + candidate) + canonical_source

# Patents (reserves tables for Phase 4 patent xlsx import; endpoints return empty until data lands)
GET  /api/data/patents
GET  /api/data/patents/{id}

# Cross-entity search
GET  /api/search?q=...&types=company,professor,paper,patent
     unified keyword search across entity canonical_names + aliases
```

**Pydantic 响应模型**：`ProfessorListItem`、`ProfessorDetail`、`PaperListItem`、`PaperDetail`，复用 `src.data_agents.canonical` 已有。

**测试**：`apps/admin-console/tests/test_professor_api.py` + `test_paper_api.py`，覆盖：
- 列表分页 + 按机构过滤
- 丁文伯 detail 返回 ≥ 19 research_topic + 30 papers 中 top 20
- 跨实体搜索 "优必选" 同时命中 company 和（后续）patent applicant

### Round 8b — 前端 UI（React + TypeScript，复用 admin-console 技术栈）

交付目录：

```
apps/admin-console/frontend/src/
├── App.tsx                              路由 + 顶栏
├── pages/
│   ├── Home.tsx                         总览：4 域 count card + 最近活动时间线
│   ├── CompanyList.tsx                  继承现 DomainList 但读新 /api/data/companies
│   ├── CompanyDetail.tsx                三栏：身份 / 字段+证据 / 关系
│   ├── ProfessorList.tsx                过滤栏（机构 / 研究方向 / 论文状态）+ 分页表
│   ├── ProfessorDetail.tsx              身份 / affiliations / 按 fact_type 分组的事实 / verified+candidate 论文
│   ├── PaperList.tsx                    过滤栏 + 表
│   ├── PaperDetail.tsx                  标题 / venue / year / 作者 / 关联教授
│   ├── GlobalSearch.tsx                 顶栏搜索输入 → 结果聚合
│   └── (Patent 页面占位 Phase 4)
├── components/
│   ├── EvidenceBadge.tsx                每条 fact 旁边 source + fetched_at chip
│   ├── LinkStatusPill.tsx               verified/candidate/rejected 颜色徽章
│   ├── FactGroup.tsx                    按 fact_type 折叠渲染
│   ├── PaperCard.tsx                    标题 / 引用 / DOI / 状态 pill
│   └── FilterBar.tsx                    复用 CompanyList 的过滤组件
└── api.ts                                fetch helpers with typed returns
```

**核心设计点**：
- 每条事实必须可点开看 **source_page + fetched_at + evidence_span**（plan 005 §8.7 Evidence Viewer 硬约束）
- 教授详情页**左侧** fact_type 导航（research_topic / education / award / work_experience / contact）
- 教授详情页**右侧** verified papers 和 candidate papers 分两栏，方便人工审核升降级
- 论文详情页反向显示"这篇论文被哪些教授声称"——对于 candidate 比 verified 更有用（暴露污染）

**验收**：
- 浏览器打开 `/data/professors/{id}` for 丁文伯 → 19 research_topic 分组展示 + 30 论文按引用排序
- "研究方向"筛选支持 `research_topic ILIKE '%TENG%'` → 返回丁文伯及同领域人

### Round 8c — Query Readiness 自测 tab（Monitor 子页）

把 `docs/测试集答案.xlsx` 的 17 道题变为定期跑的断言：

```
GET /api/monitor/query-readiness
  - question_id, question_family, status (pass/fail/missing_data), blocking_gap
  - daily/nightly run hooked via APScheduler
  - 首版手动触发 OK
```

前端 `/monitor/readiness` 页展示 pass/fail 矩阵。失败 → 点开看具体 blocking_gap 定位采集缺口。

## 2. 预计工期

| Round | 重点 | 预估 |
|---|---|---|
| 8a | Backend endpoints + tests（Codex 可独立承接） | 1-2 小时 |
| 8b | Frontend pages + components | 2-3 小时（或 Codex 分两批） |
| 8c | Readiness tab + APScheduler | 1 小时 |

## 3. 不在此计划内

- Chat frontend（独立 plan 001）
- company_product V008 + 抓取（独立 plan 003）
- Patent xlsx 导入（专利域 xlsx seed 前置工作）

## 4. 并发/顺序

- Round 8a / 8b 可并行（Codex 分别承接）
- 8c 依赖 8a 的 API
- 与 Round 8（Chat v0）独立——admin console 是运维视图，Chat 是端用户视图
- 与 Phase 3 pipeline_v3 完善平行（不同代码路径）

## 5. 立即可看的数据（过渡期）

在 Round 8a/8b 未完成前，通过 psql 直查 miroflow_real：

```sql
-- 某教授的完整画像
SELECT p.canonical_name, pa.institution,
       array_agg(DISTINCT f.value_raw) FILTER (WHERE f.fact_type='research_topic') AS topics,
       array_agg(DISTINCT f.value_raw) FILTER (WHERE f.fact_type='education') AS education,
       (SELECT array_agg(title_clean ORDER BY citation_count DESC NULLS LAST)
        FROM professor_paper_link ppl JOIN paper ON paper.paper_id=ppl.paper_id
        WHERE ppl.professor_id=p.professor_id AND ppl.link_status='verified' LIMIT 10) AS top_verified_papers
FROM professor p
LEFT JOIN professor_affiliation pa ON pa.professor_id=p.professor_id AND pa.is_primary=true
LEFT JOIN professor_fact f ON f.professor_id=p.professor_id
WHERE p.canonical_name = '丁文伯'
GROUP BY p.canonical_name, pa.institution, p.professor_id;
```
