---
title: Dashboard 数据与展示缺口补齐 (Round 7.19 + Round 9.1)
date: 2026-04-19
status: planned
owner: claude + codex (hybrid)
origin:
  - docs/plans/2026-04-18-001-user-chat-interface-plan.md
  - docs/Professor-Data-Agent-PRD.md
  - user observations 2026-04-19 14:00 (6 issues spotted on /browse)
---

# Dashboard 数据与展示缺口补齐

## 0. 缘起

用户 2026-04-19 浏览 `/browse` 后提出 6 条观察，两层问题混在一起：

| # | 观察 | 根因定位 | 归属 |
|---|---|---|---|
| 1 | Jianwei Huang 无中文名"黄建伟" | **数据**：canonical_name 只有英文 | Round 7.19a |
| 2 | UNKNOWN_INSTITUTION 仍然存在 | **数据**：机构归一化别名表缺 | Round 7.19b |
| 3 | 学科是英文 code（computer_science） | **展示**：前端缺 i18n 映射 | Round 9.1a |
| 4 | 官网原文简介没展示 | **数据 + 展示**：字段存在性待确认 | Round 7.19c / 9.1b |
| 5 | LLM 画像 profile_summary 没渲染 | **展示**：字段有，前端没渲染 | Round 9.1b |
| 6 | "展开全部数据"按钮 | **展示**：UX 详情抽屉 | Round 9.1c |

数据层问题（1/2/4 部分）合并为 **Round 7.19**（三个子任务 a/b/c），展示层问题（3/5/6/4 部分）合并为 **Round 9.1**（三个子任务 a/b/c）。

## 1. Round 7.19a — 中英名互补回扫

### 问题
`professor.canonical_name` 在部分行只有英文（如 `Jianwei Huang` 应为 `黄建伟`）或只有中文。V3 enriched 合并时没有强制保证中英双填。
当前 787 位教授中，`canonical_name_en IS NOT NULL` 的占 48%（379 / 787 — 已回滚 4 条 inactive）。

### 设计
新建 `scripts/run_name_bilingual_backfill.py`：

1. 扫所有 `identity_status='resolved'` 教授，分三类：
   - **A. 只有中文**（canonical_name 是中文，canonical_name_en IS NULL）：调 gemma4 + source_page 抓取的官网页面，找到英文名（LastFirst / pinyin）→ 填 canonical_name_en，经 `name_identity_gate` 校验。
   - **B. 只有英文**（canonical_name 是英文拉丁字符）：调 gemma4 + 搜索抓中文名 → 可能新增一列 `canonical_name_zh`，或者 swap（canonical_name ← 中文，canonical_name_en ← 原英文）。
   - **C. 双填缺一**：忽略。
2. 所有结果走 `name_identity_gate.verify_name_identity`（confidence ≥ 0.8 才入库）。
3. 过不了 gate 的 → pipeline_issue severity=medium reported_by='round_7_19a_name_bilingual'。

### 开放问题
- schema：是否需要新增 `canonical_name_zh` 列，或复用 canonical_name + canonical_name_en？
  - 简洁方案：canonical_name 永远存"人看起来更自然的那个"（中国人默认中文，外国人默认英文），canonical_name_en 只存拉丁字符
  - 复杂方案：加 canonical_name_zh 显式分开
  - 推荐简洁方案 + 在 Round 7.19a 做一次 swap 清理
- 对 Jianwei Huang 这类港中大深圳的教授：canonical_name 用哪个？看院系风格——CUHK-SZ 用英文名为主，所以允许 canonical_name=英文；同时 canonical_name_zh='黄建伟'（如果补字段）

### 交付
- `scripts/run_name_bilingual_backfill.py`
- 可能的 alembic V009（加 canonical_name_zh）
- 验证：Jianwei Huang 的详情页能同时看到中英文

## 2. Round 7.19b — 机构归一化扩展 + UNKNOWN_INSTITUTION 回溯

### 问题
- 至少 2 条 UNKNOWN_INSTITUTION（Jianwei Huang, 陈伟津 — 从 `run_institution_cleanup` 的 duplicate detection 得出）
- 爬虫层有 CUHK-Shenzhen 的子页面识别失败 → institution 归一化表缺"CUHKSZ"、"港中大深圳"、"香港中文大学深圳分校" 变体
- 深圳技术大学、SUSTech 等也有类似老数据

### 设计
1. **扩展 `institution_registry.py` 的别名表**：
   ```python
   _INSTITUTION_ALIAS_CANONICAL = {
       "香港中文大学（深圳）": [
           "CUHKSZ", "CUHK-Shenzhen", "CUHK(SZ)",
           "港中大深圳", "港中深", "中大香港（深圳）",
           "香港中文大学(深圳)", "香港中文大学深圳分校",
           "The Chinese University of Hong Kong, Shenzhen",
       ],
       "南方科技大学": ["SUSTech", "SUSTech University", "南科大"],
       ... # 8 所 SZ 高校 × 4-5 别名各
   }
   ```
2. **新 guard `institution_normalize.py`**：输入 institution 字符串，返回 canonical 或 `UNKNOWN_INSTITUTION`。
3. **新脚本 `scripts/run_unknown_institution_rescue.py`**：
   - 找所有 `institution='UNKNOWN_INSTITUTION'` 的 affiliation 行
   - 从 3 个来源反推：(a) 关联 paper 的 authors_raw 里的 affiliation 字段，(b) 这个 professor 的 source_page URL 域名，(c) 关联 company 的机构
   - 用 `institution_normalize` 归一化候选 → 如果 ≥1 个有 ≥0.8 一致度 → UPDATE affiliation.institution + 走 name_identity_gate 二次验证
   - 否则 file pipeline_issue severity=medium
4. **爬虫层防再流入**：在 `roster_loader` 或 `discovery` 写 affiliation 之前调用 `institution_normalize`。UNKNOWN 的行在写入前 pipeline_issue 阻断。

### 交付
- `src/data_agents/professor/institution_registry.py` 别名表扩展
- `src/data_agents/professor/institution_normalize.py` 新 guard
- `scripts/run_unknown_institution_rescue.py`
- 爬虫 hook（discovery.py 或 roster_loader.py）调用新 guard

## 3. Round 7.19c — 官网简介（profile_raw_text）字段与回填

### 问题
官网页面原文长介绍（如杜尚波的整段 bio）应该作为 "原始档案文本" 存起来，但不确定：
- `EnrichedProfessorProfile` 有没有 `profile_raw_text` 字段
- `professor` 或 `source_page` 表有没有存
- V3 enriched 合并时是否保留

### 动作（按顺序）
1. **先确认字段存在性**（半小时）：
   ```bash
   grep -rn "profile_raw_text\|raw_text\|biography" apps/miroflow-agent/src/data_agents/professor/models.py
   ```
   再看 `EnrichedProfessorProfile` 的定义、`professor` 表的 schema、`source_page.clean_text_path` 是否被用到
2. **如果字段不存在 / 没存**：
   - 加 alembic V010：`professor` 表增 `profile_raw_text TEXT NULL`
   - 改 `canonical_writer._upsert_professor_row` 接 `profile_raw_text` 参数
   - `enrichment.py` 从 source_page 抽原文段落（最大 2000 字符）
   - 回填：新 `scripts/run_profile_raw_text_backfill.py` 从 `source_page.clean_text_path` 读取对应 prof 的原文
3. **如果字段存在但 migration 时没关联**：
   - 回填脚本，跨 `source_page → professor_id` 查回来

### 交付
- 确认文档（短 check 回帖 / plan 更新）
- 可能的 V010 migration + backfill script

## 4. Round 9.1a — 学科 code → 中文展示

### 问题
`discipline_family='computer_science'` 在列表和详情直接显示英文。应该显示"计算机科学"。

### 设计
- `Taxonomy` 种子表里已有 78 学科 code + 中英对照
- 前端加 `discipline_i18n.ts` 映射：
  ```typescript
  const DISCIPLINE_LABEL: Record<string, string> = {
    computer_science: "计算机科学",
    electrical_engineering: "电气工程",
    materials: "材料科学",
    biomedical: "生物医学",
    mathematics: "数学",
    physics: "物理",
    chemistry: "化学",
    mechanical_engineering: "机械工程",
    interdisciplinary: "交叉学科",
    other: "其他",
  };
  ```
- 筛选器 UI 展示中文，value/query 参数仍用英文 code（契约不变）
- 同样处理在 `/browse` 和 React SPA `DomainList.tsx`

### 交付
- browse.html 加 `DISCIPLINE_LABEL` 映射 + 列渲染
- frontend/src 加映射 .ts 文件 + 引用
- 不动 API、不动 DB

## 5. Round 9.1b — AI 画像（profile_summary）+ 官网简介 展示

### 问题
- `EnrichedProfessorProfile.profile_summary`（LLM 生成的教授画像）字段有内容但 `/api/data/professors/{id}` 没返回，前端没渲染
- 官网简介（Round 7.19c 产出的字段）也没渲染

### 设计
1. **后端：扩展 `/api/data/professors/{id}` 返回**：
   - 新字段 `profile_summary: str | None`（读 `professor.profile_summary` 或相邻表）
   - 新字段 `profile_raw_text: str | None`（Round 7.19c 落后）
2. **前端：`browse.html` 详情抽屉新增两块卡片**：
   - **AI 画像**（3-4 段，蓝色 accent 背景）
   - **官网简介**（长文本，折叠/展开）
3. **覆盖率检查**：
   ```sql
   SELECT
     count(*) FILTER (WHERE profile_summary IS NOT NULL AND char_length(profile_summary) > 50) AS with_summary,
     count(*) FILTER (WHERE profile_raw_text IS NOT NULL AND char_length(profile_raw_text) > 100) AS with_raw,
     count(*) AS total
   FROM professor WHERE identity_status='resolved';
   ```
   如果 `with_summary / total < 0.5` → 补跑一次 `scripts/run_profile_summary_generate.py`

### 交付
- data.py 扩展 ProfessorDetailResponse
- browse.html 详情面板新增 2 块卡片
- 覆盖率报告 + 可选的补跑脚本

## 6. Round 9.1c — "展开全部数据" 详情页

### 问题
列表行只展示摘要（姓名、机构、职称、前几个研究方向），用户要求详细展开。

### 设计
在 `/browse` 的教授详情面板（已有）加以下区块。大部分字段 `/api/data/professors/{id}` 已返回，只是前端没渲染：

- **基本档案**：姓名（中英文）、机构、院系、职称、学位、国籍、入职年份 [大部分已有]
- **官网简介** [Round 7.19c + 9.1b 新]
- **AI 画像** [Round 9.1b 新]
- **研究方向全量**（不截断） [已有，去掉截断]
- **教育履历**（education_structured） [已有 fact_type='education'，改渲染]
- **工作履历**（work_experience） [已有 fact_type='work_experience'，改渲染]
- **获奖**（awards） [已有 fact_type='award'，改渲染]
- **主持项目**（selected_projects） [检查：是否有对应 fact_type]
- **社会任职**（professional_services） [检查：字段存在性]
- **论文列表**：verified/candidate/rejected 三桶 + 分页 [已有，检查分页]
- **专利列表**：如果有 [Round 7.20：专利采集]
- **指导学生与学生获奖** [字段存在性待确认]
- **来源页面**：source_pages + URL + fetched_at + 点击跳转原始官网 [已有 data.py，检查渲染]
- **Provenance**：canonical_source、confidence、last_refreshed_at、source_url 列表 [已有]

### 设计形式
- 列表行右侧加"详情"按钮
- 点击 → 侧栏抽屉（overlay drawer）或跳到独立路由 `/browse#professor/{id}`
- 抽屉顶部有"新窗口打开"+"导出 JSON"按钮

### 交付
- browse.html 详情抽屉重做（可能 ~300 行新增 JS/CSS）
- `/api/data/professors/{id}` 返回上面列出的全部字段（可能需要 JOIN 其他表或增 selected_projects/professional_services 字段）
- 可能与 Agent-E（Round 8c 人机协同审核台）复用 provenance 可视化组件

## 7. 依赖与排序

```
Round 7.19 数据层
  ├─ 7.19a  中英名互补  ──── 依赖 source_page 爬取历史
  ├─ 7.19b  机构归一化  ──── 独立，最快做
  └─ 7.19c  profile_raw_text 字段 ──── 确认 → 可能 migration
     │
     └─► Round 9.1 展示层
           ├─ 9.1a  学科中文展示  ──── 独立，15 分钟
           ├─ 9.1b  profile_summary + raw_text 渲染 ── 依赖 7.19c 完成
           └─ 9.1c  详情页"展开全部"  ── 吸收前面的所有字段
```

## 8. 执行策略

- **优先级 P0**（立即）：7.19b 机构归一化 + 9.1a 学科中文 → 最省力 + 最可见
- **优先级 P1**（本周）：7.19a 中英名 + 9.1c 详情抽屉
- **优先级 P2**（下周）：7.19c profile_raw_text + 9.1b AI 画像展示

Subagent 映射（可以再来一波 Agent-A ~ F 并行派发）：
- Agent-A: 7.19b 机构归一化扩展 + UNKNOWN_INSTITUTION 回溯（Codex）
- Agent-B: 9.1a 学科中文 + 9.1c 详情抽屉（frontend-design / design-iterator）
- Agent-C: 7.19a 中英名互补 TDD + impl（Codex）
- Agent-D: 7.19c profile_raw_text 字段存在性确认 + 回填（general-purpose）
- Agent-E: 9.1b profile_summary 后端扩展 + 前端渲染（Codex + design-iterator）
- Agent-F: 文档：现有 Taxonomy 78 学科码中英对照的文件位置 + 导出 .ts 映射（general-purpose）

## 9. 验收指标

- **7.19a**：Jianwei Huang 的详情页同时显示 "黄建伟" 和 "Jianwei Huang"
- **7.19b**：`SELECT count(*) FROM professor_affiliation WHERE institution='UNKNOWN_INSTITUTION'` = 0
- **7.19c**：787 位教授 with_raw_text / total ≥ 0.8
- **9.1a**：列表页和筛选器中"工程/材料/计算机科学"等用中文显示
- **9.1b**：详情抽屉同时展示 AI 画像 + 官网简介两块卡片
- **9.1c**：详情抽屉显示列表里提到的 14 个字段区块，支持独立 URL `/browse#professor/{id}`
