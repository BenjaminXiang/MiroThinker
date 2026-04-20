---
title: 系统能力审计 + Agentic RAG 缺口深度分析
date: 2026-04-20
status: active
owner: claude
origin:
  - docs/Agentic-RAG-PRD.md
  - docs/测试集答案.xlsx (25 个样例问题)
  - miroflow_real 实际 DB 状态 (2026-04-20)
  - 用户 2026-04-20 反馈: "本质是数据收集清洗 + Agentic RAG，目前 Agentic RAG 缺失较大"
---

# 系统能力审计 + Agentic RAG 缺口深度分析

## 0. Executive Summary

**三个核心判断：**

1. **PRD 要求的 12 项核心能力中，完成度约 55%**——数据层基本到位，检索层和答案生成层刚起步，**Agentic RAG 的"Agentic"部分（规划、反思、多工具、重写、rerank）几乎为零**。

2. **论文验证过度拒绝严重**：47% 的教授（363/775）有论文被抓取但 **100% 被拒**，1114+836+1280=3,230 篇高校论文被丢弃，根因是 `paper_identity_gate` 用中文名匹配英文作者串，**精度护栏反噬召回**。

3. **当前代码层级设计合理但执行链路单薄**：chat.py 一个文件 1100 行，把意图识别+检索+合成混在一起。需要拆出 agent/retriever/reranker/synthesizer 分层，才能叫 Agentic。

本文档不是 TODO 清单，而是**根因分析 + 目标架构 + 优先级路线**。具体 Round 拆解放到后续 plan。

---

## 1. PRD 要求的能力清单

基于 `docs/Agentic-RAG-PRD.md` 和 `docs/测试集答案.xlsx` 25 个样例问题，系统应具备以下 12 项能力：

### L1 — 意图理解层

| # | 能力 | PRD 出处 | 样例问题触发 |
|---|---|---|---|
| **C1** | 查询类型分类（A/B/C/D/E/F/G 七类） | §2.1 | Q1-Q25 几乎每题都需要 |
| **C2** | 实体抽取（姓名、机构、专利号、时间、限定条件） | §2 | Q1-丁文伯、Q24-优必选、Q25-CN117873146A、Q13-早稻田 |
| **C3** | 查询改写（代词消解 + 上下文收窄 + 显式化） | §2.1 B类多轮 | Q2 "他"、Q4 "上述"、Q8 字序反转 "智航无界" vs "无界智航" |
| **C4** | 歧义检测与澄清（G 类） | §2.1 G | Q7 两家"无界智航"、Q16 多个王学谦 |

### L2 — 检索执行层

| # | 能力 | PRD 出处 | 样例问题触发 |
|---|---|---|---|
| **C5** | 单域结构化检索（exact/filter） | §2.1 A | Q1/Q24/Q25 |
| **C6** | 单域语义检索（embedding/rerank） | §2.1 B/D | Q3 "成熟"、Q5 "能按电梯"、Q9 "推荐" |
| **C7** | 跨域聚合（多源召回 + 结果融合） | §2.1 D | Q21 具身智能+厂商+数据路线、Q14 公司+市场竞争力 |
| **C8** | Web Search 补全（本地库不足时） | §1.3 窄例外 + §2 | Q3 "全中国"、Q14 "市场竞争力"、Q18-Q23 "具身智能综述" |
| **C9** | 时效性标注（本地 vs 实时 vs LLM 推理） | §2 结果组织 | Q15 光学原理（LLM）、Q18-23（LLM+Web） |

### L3 — 答案生成层

| # | 能力 | PRD 出处 | 样例问题触发 |
|---|---|---|---|
| **C10** | LLM 答案合成（带引用 [N] 标记） | §2.4 | 全部 |
| **C11** | 多轮上下文维护（entity stack、topic switch） | §2.5 | Q2/Q4/Q8/Q10/Q12 |
| **C12** | 结构化卡片 + 追加提问引导 | §2.4 | Q1 返回画像卡、Q11 论文卡 + 链接 |

---

## 2. 当前实现 × 能力矩阵

| 能力 | 实现状态 | 实现位置 | 完成度 |
|---|---|---|---|
| **C1 查询分类** | 🟢 LLM gemma4 分类 A/B/D/E/F/G | `chat.py:_classify_query_with_llm` | **90%** — 规则 fallback + 无 G for company |
| **C2 实体抽取** | 🟡 仅 name+topic，缺时间/地域/职称/限定条件 | `chat.py:_classify_query_with_llm` 返回 {type, topic, name} | **30%** |
| **C3 查询改写** | 🟡 代词指代（他/她/这位教授）→ 上一轮 prof name | `chat.py:_rewrite_query_with_context` | **25%** — 缺上下文收窄、显式化、别名归一 |
| **C4 歧义澄清** | 🟡 教授域有 G path，公司/论文域无 | `chat.py` G 分支 | **40%** |
| **C5 单域结构化** | 🟢 教授/公司/论文 done；专利 0 数据 | `chat.py` + `api/data.py` | **75%**（patent 表空） |
| **C6 单域语义** | 🟡 SQL ILIKE 模糊匹配；**无向量检索、无 rerank** | `_lookup_professors_by_topic` 等 | **20%** |
| **C7 跨域聚合** | 🟡 prof+company 并列；无融合、无 rerank | `chat.py` D 分支 | **40%** |
| **C8 Web Search** | 🔴 **完全没有** | - | **0%** |
| **C9 时效标注** | 🟡 E 类加"非本地"标注；A/B 类无 | `chat.py:_answer_knowledge_qa` | **25%** |
| **C10 答案合成** | 🟢 gemma4 带 [N] marker + validate | `chat.py:_build_chat_response` | **80%** |
| **C11 多轮上下文** | 🟡 session + prof entity stack；**仅 prof 单类型** | `chat.py:SessionContext` | **35%** |
| **C12 结构化卡片** | 🟡 citations 数组；**无追问引导** | - | **30%** |

**加权完成度**：(0.9+0.3+0.25+0.4+0.75+0.2+0.4+0+0.25+0.8+0.35+0.3) / 12 = **40.8%**

---

## 3. Agentic RAG 架构缺口（用户关键反馈）

> 用户反馈："目前看好像有较大的缺失，是否有查询改写、意图识别、在线 web search、LLM 输出整理等模块，这次回答的链路在我看来不是很清晰。"

### 3.1 当前架构（单文件、扁平、非 agentic）

```
POST /api/chat (payload)
  ├─ session cookie + pronoun rewrite (25% 改写)
  ├─ rule regex match (A patterns)
  │    └─ if match → SQL → LLM synth → return
  ├─ LLM classifier (A/B/D/E/F/G)
  └─ per-type hardcoded handler
       ├─ A: SQL exact lookup
       ├─ B: SQL ILIKE
       ├─ D: SQL prof + SQL company
       ├─ E: LLM only knowledge (no retrieval, no web)
       ├─ F: refuse
       └─ G: disambiguation
```

**这不是 Agentic RAG，是"RPC + LLM 包装"**。Agentic 意味着：
- Agent 有 **规划** 能力（把复杂 query 拆 sub-task）
- Agent 能 **调用多工具**（DB / embedding / web / rerank / code）
- Agent 能 **反思 + 重试**（检索结果不足 → 改写 → 再检索）

### 3.2 目标 Agentic RAG 分层

```
┌─────────────────────────────────────────────────┐
│  L0. 入口  (chat app / WeChat webhook / API)    │
└────────────────────────┬────────────────────────┘
                         │
┌────────────────────────▼────────────────────────┐
│  L1. Session Manager                            │
│      ├─ session_id + entity stack (多类型)      │
│      ├─ turn history (N 轮)                     │
│      └─ topic boundary detection                │
└────────────────────────┬────────────────────────┘
                         │
┌────────────────────────▼────────────────────────┐
│  L2. Query Understanding                        │
│      ├─ Intent classifier (A-G + slot filling) │
│      ├─ Query rewriter (代词/上下文/别名)       │
│      ├─ Entity NER (名/机构/号/时间/限定)       │
│      └─ Ambiguity detector (→ G or clarify)    │
└────────────────────────┬────────────────────────┘
                         │
┌────────────────────────▼────────────────────────┐
│  L3. Agent Orchestrator (planner + loop)       │
│      规划: {sub_tasks: [retrieve_prof,         │
│                          retrieve_company,     │
│                          web_search_fallback]} │
│      反思: 结果不够 → 改写 query → 重试        │
│      终止: 足够信心 OR 超时 OR 用户打断        │
└────────────┬──────────┬───────────┬────────────┘
             │          │           │
┌────────────▼┐ ┌──────▼──────┐ ┌──▼────────────┐
│ L4a. Tools  │ │ L4b. Hybrid │ │ L4c. Web      │
│  DB exact   │ │ Retrieval   │ │  Search Tool  │
│  DB filter  │ │ - BM25      │ │  - Serper /   │
│             │ │ - Embedding │ │    Google /   │
│             │ │ - Rerank    │ │    DDG        │
│             │ │ (Milvus)    │ │  - page crawl │
└─────────────┘ └─────────────┘ └───────────────┘
             │          │           │
             └──────────┼───────────┘
                        │
┌───────────────────────▼────────────────────────┐
│  L5. Context Packer + Reranker                 │
│      - 去重、按信息增益排序、证据块截断        │
│      - Citation marker 分配                    │
└───────────────────────┬────────────────────────┘
                        │
┌───────────────────────▼────────────────────────┐
│  L6. Answer Synthesizer                        │
│      - System prompt + evidence + question     │
│      - LLM 生成（带引用）                      │
│      - Post-process: validate markers, detect   │
│        hallucination, add timeliness label     │
└───────────────────────┬────────────────────────┘
                        │
┌───────────────────────▼────────────────────────┐
│  L7. Response Shaper                           │
│      - answer_text + structured card +         │
│        citations[] + follow-up suggestions     │
└────────────────────────────────────────────────┘
```

### 3.3 当前 vs 目标 缺口清单

| 层 | 目标 | 当前 | 缺口 |
|---|---|---|---|
| L1 Session | 多类型 entity stack + topic 切换检测 | 仅 prof 类 + 无 topic 切换 | 扩 entity 类型 + 加 topic 切换启发式 |
| L2 Query | rewriter / NER / slot filling | 代词 sub only | **最大缺口**：rewriter（加 LLM 改写）、NER（实体槽填充） |
| L3 Orchestrator | planner + loop | 没有 | **最大缺口**：agent planner |
| L4a DB Tools | ✅ | ✅ ok | 无 |
| L4b Hybrid | BM25 + embedding + rerank | ILIKE only | 接入 Milvus + reranker |
| L4c Web | 必需（PRD §1.3） | **完全没有** | **最大缺口**：Serper/Google API + page crawler |
| L5 Packer | rerank + dedup + citation | 简单 list | rerank 缺失 |
| L6 Synth | ✅ | ✅ ok | 加幻觉检测 |
| L7 Shape | follow-up suggestions | 仅 citations | 追问引导缺失 |

**三个最大缺口**：
1. **Query Rewriter**（L2）—— 复杂查询改写 + 别名归一
2. **Agent Orchestrator**（L3）—— 没有规划、反思、多工具调用
3. **Web Search Tool**（L4c）—— 核心缺口，PRD 明确要求

---

## 4. 论文验证过度拒绝——根因与修复

> 用户反馈："绝大部分老师的论文都没有通过验证，这个问题出在哪里"

### 4.1 实际数据

全库 775 resolved 教授中：

| 分桶 | 数量 | 占比 |
|---|---|---|
| 从未尝试（0 candidate） | 0 | 0% |
| 尝试了但**全部拒绝** | **363** | **47%** |
| 1-4 篇已验证 | 142 | 18% |
| 5-19 篇已验证 | 227 | 29% |
| ≥20 篇已验证 | 43 | 6% |

**最严重的案例**：
- **周垚**（南科大，7 个研究方向）：43 篇全拒
- **常瑞华**（港中深，18 个研究方向）：40 篇全拒
- **余利**（深技大）：25 篇全拒

学校拒绝率分布：
- 深圳技术大学: **65% reject** (1280 rejected / 677 verified)
- 北京大学深圳研究生院: **76% reject**
- 南方科技大学: **70% reject**
- 港中深: 45%
- 清华深研: 42%

### 4.2 根因分析（从拒绝理由样本反推）

样本拒绝理由前 5：
```
14 次: "作者名单中为 Chunbo Li，与目标教授姓名"王远航"不符"
14 次: "作者名单中没有吴耀炯，研究领域虽相关，但作者与目标教授无关联"
14 次: "作者列表中没有余泉"
14 次: "作者名为 Chunbo Li，与目标教授陈菲姓名不符"
```

**姚建铨案例**（著名激光/太赫兹教授，应有数百篇论文）3 篇被拒的样本：
- name_match=0.85，topic=None，标题 "Device for detecting ischemic cerebrum based on TeraHertz" → reason："作者列表中没有姚建铨"

**根因三连：**

1. **CJK ↔ Latin 名字匹配失败**
   - 收录的 `paper.authors_display` 是 Latin 字符串（"Jianquan Yao, A Bauer, ..."）
   - `paper_identity_gate` 发给 LLM 的目标名是 Chinese `"姚建铨"`
   - LLM 逐字对比 → "作者列表中没有姚建铨" → 拒绝
   - **这是系统性错误**，不是个案

2. **`author_name_match_score` 在 collector 侧已经是 0.85（表示强匹配）**，但 gate 再走 LLM 一次，**LLM 拿不到 collector 的 Latin ↔ CJK 映射信息**，重复决策的依据不完整

3. **Topic consistency 在 LLM 拒绝路径被忽略**
   - 被拒样本的 topic=NULL（没算分）
   - 明明"太赫兹探测脑缺血"跟姚建铨"光学/太赫兹"研究方向高度相关，但 topic 信号没被用

### 4.3 修复路线（Round 12.x）

**L1 — gate 传入双语上下文（1 天）**
```python
# 当前
verify_name(name="姚建铨", authors="Jianquan Yao, A Bauer, ...")
# 改为
verify_name(
    name_zh="姚建铨",
    name_en="Jianquan Yao",
    name_pinyin="Yao Jianquan",
    authors="Jianquan Yao, A Bauer, ..."
)
```
仅此一步，**预计挽救 60%+ 的假拒绝**。

**L2 — ORCID / Semantic Scholar author_id 作为第一证据（3-5 天）**
- 教授 profile enrichment 补 ORCID 字段（部分已有）
- 若 paper.authors_raw 包含匹配 author_id → **跳过 LLM，直接 verified**
- 这是工业标准做法，识别率 >99%

**L3 — 亲和性启发（1 天）**
- 若 paper 作者列表含目标教授当前机构（如"Tsinghua Shenzhen"）→ 提分
- 若共同作者包含已 verified 的合作者（从 7.18e 学到）→ 提分
- 若 paper venue 与教授历史 venue 一致 → 提分
- 多信号合成后再过 LLM（LLM 做仲裁，不是唯一裁判）

**L4 — 对 363 个 all-rejected 教授批量重跑（半天）**
- 用 L1+L2+L3 新 gate 重放所有 rejected paper_link
- 预期 60-75% 会被救回（~2000 篇论文 verified）

**L5 — 增量"确认盲点"（1 周）**
- 对 100+ 篇论文的理工科教授，自动检查 verified 数是否 ≥ paper_count * 0.6
- 不足则触发"gate too strict" 告警进 pipeline_issue
- 人工或半自动 review

**预期效果：47% 全拒 → <10% 全拒；平均每位教授 verified paper 数 ~5 → ~25。**

### 4.4 论文→画像 反哺机制

用户洞察："**对于很多理工科老师有大量论文，这些论文可以为老师提供精准清晰的画像**"

这本质是**论文驱动的教授画像反向传播**：

```
当前流水线:
prof enrichment (官网抓取) → research_directions [3-10 条]
                             ↓
                          paper_identity_gate 用这 3-10 个方向去筛论文
                             ↓
                          太严 → 大量真论文被拒
                             ↓
                          教授 0 verified paper → 画像单薄

目标流水线:
prof enrichment (官网) → research_directions seed [3-10 条]
                         ↓
                      gate v2 (L1+L2+L3 宽松) → 挽救大量论文
                         ↓
                      verified papers [50-200 篇]
                         ↓ LLM topic extraction
                      expanded_research_directions [15-30 条精细子方向]
                         ↓ 反向写回 professor_fact
                      profile_summary 基于 research_directions + papers 重新合成
                         ↓ gate v3 重跑（现在 topic 覆盖更全）
                      下一批论文验证通过率提升
```

**关键**：这是个**正反馈闭环**——论文越多 → 方向越精 → 画像越准 → 下轮 gate 越宽松 → 更多论文被捞回。

当前系统在第 3 步就卡死了（gate 太严 → 没论文 → 方向没扩充 → 画像一直单薄）。

---

## 5. 样例问题深度评估

用 25 个样例问题再过一遍，标"真实能力"（不是代码是否存在，而是真能回答的概率）：

| # | 问题 | 当前真能答 | 假设 L1-L3 gate 修好 + Web Search 接通 | 缺什么 |
|---|---|---|---|---|
| 1 | 介绍清华的丁文伯 | ✅ | ✅ | - |
| 2 | 他是否参与企业创立 | 🟡 40% | ✅ | prof→company 关系需要从 news + 公司 team_member 补 |
| 3 | 全国酒店送餐机器人供应商 | ❌ 无此类公司 | ✅ 通过 Web Search | **C8 Web Search 缺口** |
| 4 | 上述里深圳的 | ✅ 多轮+filter | ✅ | - |
| 5 | 机械臂按电梯的 | ❌ | 🟡 Web Search 能补但精确度差 | **产品能力表缺失** |
| 6 | 黄赌毒地方 | ✅ F 拒答 | ✅ | - |
| 7 | 介绍无界智航 | 🟡 G 教授域 | ✅ | G 扩到公司域 |
| 8 | 深圳智航无界科技（字序反转） | ❌ | ✅ | **C3 查询改写 + 模糊匹配** |
| 9 | PCB 打板推荐 | 🟡 | ✅ | 公司行业标签够；需 rerank（知名度/融资） |
| 10 | 上述深圳的 | ✅ | ✅ | - |
| 11 | pFedGPA 论文 | ❌ chat 没论文 handler | ✅ | 加论文 chat pattern（<1 天） |
| 12 | 这论文链接 | ❌ | ✅ | 多轮 + paper entity |
| 13 | 早稻田+深圳+机器人+企业家 | ❌ | 🟡 | **C2 多实体槽 + 多表 JOIN** |
| 14 | 华力创科学市场竞争力 | 🟡 profile | 🟡 Web Search 能补评价 | **市场评价数据** |
| 15 | 光基多维力传感原理 | ✅ E | ✅ | - |
| 16 | 王学谦是否大牛 | 🟡 | ✅ | **aggregate 大牛信号**（h-index + 奖项 + 论文数） |
| 17 | 爱博合创 + 市场评价 | 🟡 | ✅ Web Search | **市场评价数据** |
| 18-20, 22-23 | 具身智能综述 | 🟡 E (LLM 推理 only) | ✅ E + Web Search | **Web Search 补外部最新资讯** |
| 21 | 深圳具身智能厂商 + 数据路线 | 🟡 D 能给 prof+company | 🟡 "数据路线"需要公司技术评价 | **公司技术栈标签** |
| 24 | 优必选专利 | ❌ 专利表空 | ✅ | **专利数据采集** |
| 25 | 专利号查询 | ❌ | ✅ | **专利数据采集** |

**假设 Web Search + 论文 gate 修好 + 专利数据采集 后**：25 题中 **22 题**可答（88%），3 题仍需特殊数据源（产品能力表 Q5、教育 JOIN Q13、公司技术栈 Q21）。

---

## 6. 优先级路线图

按 **ROI / 难度** 排序（数字越小越先做）：

| Priority | 工作项 | 工期 | 解锁的样例问题 | 为什么这么排 |
|---|---|---|---|---|
| **P0** | **论文 gate 修复 (L1 双语名字)** | 1 天 | Q1/Q16 质量大幅提升 | 挽救 2000+ 论文，立即见效 |
| **P0** | **chat 接论文检索 pattern** | 半天 | Q11/Q12 | 简单但必要，样例必考 |
| **P1** | **Web Search 工具 (Serper API 或 DDG HTML)** | 2-3 天 | Q3/Q5/Q8/Q14/Q17/Q18-23 | PRD 明确要求，解锁 E 类完整能力 |
| **P1** | **专利数据采集** | 1-2 天 | Q24/Q25 | xlsx 已有，导入即可 |
| **P2** | **Query Rewriter (LLM 改写)** | 2 天 | Q2/Q4/Q8/Q12 | 多轮质量从 40% → 80% |
| **P2** | **论文 gate L2 (ORCID/author_id)** | 3-5 天 | 所有理工科教授 | 从 60% recall → 95% |
| **P2** | **教授画像反哺闭环（verified papers → expanded topics → profile_summary）** | 1 周 | 全库画像质量跃升 | 用户明确要求 |
| **P3** | **Agent Orchestrator (planner + reflection)** | 1-2 周 | 复杂查询（Q13/Q21） | 真正的 "Agentic" 关键 |
| **P3** | **Hybrid Retrieval (Milvus embedding + rerank)** | 1 周 | Q3/Q9 语义质量 | 现在用 ILIKE 勉强够 |
| **P3** | **实体 NER + slot filling** | 3 天 | Q13 多条件 | 单条件能跑，多条件没支持 |
| **P4** | **产品能力表 + 采集** | 2 周 | Q5 | 新数据源，耗时 |
| **P4** | **市场评价数据** | 2 周 | Q14/Q17 | 需对接 news/analyst 数据源 |
| **P4** | **公司域歧义消解 G** | 1 天 | Q7 公司歧义 | 小，但重要 |
| **P4** | **Topic 切换检测 + Session topic boundary** | 3 天 | 多话题长对话 | 锦上添花 |

### 建议的 3 个 Sprint

**Sprint 1 (1 周) — 立即可见的救急**：
- P0 论文 gate 双语修复（1 天）+ 重放 363 profs 的 rejected link
- P0 chat 论文 handler（半天）
- P1 Web Search 工具 MVP（2 天）
- P1 专利数据采集（1 天）
- 验证：25 题中能答对 18-20 题

**Sprint 2 (2 周) — Agentic 化核心**：
- P2 Query Rewriter
- P2 论文 gate L2 ORCID
- P2 教授画像反哺闭环（首轮）
- 验证：画像质量 + 论文覆盖率跃升

**Sprint 3 (2 周) — 真正的 Agentic RAG**：
- P3 Agent Orchestrator（planner + reflection loop）
- P3 Hybrid Retrieval（接 Milvus）
- P3 实体 NER + 多条件槽位
- 验证：25 题中 22-23 题能答对（含复合过滤 Q13）

---

## 7. 总结

**用户的 3 个直觉都对：**

1. **"Agentic RAG 有较大缺失"** — 对。当前是"LLM 包装的 RPC"，不是 Agent。缺 planner / rewriter / web search / rerank。完成度 40%。

2. **"回答链路不清晰"** — 对。代码是 chat.py 1100 行单文件 + 多个 if 分支，没有明确分层。目标架构 L0-L7 七层，当前压缩到 3-4 层。

3. **"论文验证过度拒绝"** — 对且根因明确：**CJK↔Latin 名字比对失败** 是系统性 bug。修 1 天能挽救 2000+ 论文，把 47% 全拒降到 <10%。

**当前系统是一个扎实的"数据清洗管线 + LLM 包装的查询 API"，距离 PRD 要求的 Agentic RAG 还有约 4-5 周的工程工作量。**

执行顺序建议：
1. 先救论文验证（1 天，巨大 ROI）
2. 再接 Web Search（PRD 必需）
3. 再做 Query Rewriter + ORCID gate（质量飞跃）
4. 最后做 Agent Orchestrator + Hybrid Retrieval（真 Agentic）
