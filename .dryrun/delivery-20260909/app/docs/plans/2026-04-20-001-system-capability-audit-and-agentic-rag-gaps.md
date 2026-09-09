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

**四个核心判断：**

1. **PRD 要求的 12 项核心能力中，完成度约 40.8%**——数据层基本到位，检索层和答案生成层刚起步，**Agentic RAG 的"Agentic"部分（规划、反思、多工具、重写、rerank）几乎为零**。

2. **[管线方向错了] 论文管线应该倒置**：当前"从 OpenAlex 抓候选 → LLM 审核"导致 47% 的教授 100% 被拒。根因是 **信任方向错了**——真正的权威源是教授自己官网 Publications 区块，外部库只是补元数据。目标：homepage 直接 verified 入库 + arxiv 全文下载供 LLM 画像反哺。

3. **`paper_identity_gate` 的 CJK↔Latin 失配** 是当前候选路径的系统性 bug（`姚建铨` vs `Jianquan Yao`），但 **homepage-first 管线可以绕开它**。Gate v2 修复（双语 + ORCID）仍然要做，作为少数 fallback 情况的加固。

4. **代码层级设计合理但执行链路单薄**：chat.py 一个文件 1100 行，把意图识别 + 检索 + 合成混在一起。需要拆出 agent / retriever / reranker / synthesizer 分层，才能叫 Agentic。

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

## 4. 论文验证过度拒绝——根因与**管线倒置**修复

> 用户反馈 A："绝大部分老师的论文都没有通过验证，这个问题出在哪里"
>
> 用户反馈 B（更深层，2026-04-20 补充）："如果教师自己高校官网主页或自己维护的主页列出的论文，**一定是没有错的**，需要做的只是 web search / API 拿到论文摘要即可，如果能在 arxiv 上找到同名论文把全篇爬下来，放在论文库用于后续 LLM 画像的材料也很好"

用户反馈 B 是一个**架构性的根因纠正**，不只是参数调优。它否定了当前整个"从 OpenAlex/S2 抓候选 → LLM 审核"的设计前提。

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

### 4.4 [重大] 管线倒置：Homepage-Authoritative Paper Ingest

**当前管线（错的方向）**：
```
OpenAlex / Semantic Scholar
  └─ 按教授姓名 + 机构做模糊检索 → 得到大量候选 papers
       └─ paper_identity_gate LLM 逐条审核
            └─ 姓名对比（CJK ↔ Latin 失配）→ 47% 全拒
```

**用户指出的正确方向**：

```
教授官方主页的 Publications 区块 (权威源, 无需验证)
  └─ 简单 HTML 提取标题（只处理乱码 / HTML entity / Unicode）
       └─ 标题 → 外部 API / Web Search 查摘要 / 作者 / 年份 / venue / DOI
            └─ 若命中 arxiv → 下载全文 PDF 入库（供 LLM 画像使用）
```

**两种管线的本质差别**：

| 维度 | 当前（候选审核式）| 目标（权威源优先）|
|---|---|---|
| 信任方向 | 不信任任何源，用 LLM 当裁判 | **教授自己列的 = 权威**，外部库做元数据补全 |
| 错误模式 | 假拒绝（FN 47%）| 假接受（若教授手抄错）— 罕见 |
| CJK-Latin 问题 | 根本问题 | 完全绕开（不需要名字匹配）|
| 招回率 | ~53% | 预计 **>95%** |
| LLM 成本 | 每篇候选一次 identity gate | **零**（homepage 已列的不走 gate）|
| 延迟 | 慢（大量 LLM 调用）| 快（HTML 抽 + HTTP API 补）|
| 数据质量 | 精度高但覆盖烂 | 精度同样高（权威源），覆盖跃升 |

**现在的 profile_raw_text 已经抓下来了，但没拆出 Publications 区块**——这是一个关键的错失。Round 7.19c 的 bio rescrape 只提取了 bio 段落，没特别识别"论文列表"。需要 **Round 12.1 专项重扫**。

### 4.4.1 Homepage Publications 抽取 — 工程设计

**阶段 1: 扫描 + 抽取（1-2 天）**

对所有 775 resolved 教授重新 fetch primary_official_profile_page，专项抽 Publications 段：

```python
# 识别 Publications 锚点（中文/英文/混合）
_PUB_ANCHOR_RE = re.compile(
    r"(Publications|Selected Publications|Journal Articles|"
    r"Recent Publications|Publication List|Papers|"
    r"论文|学术论文|代表性论文|主要论文|发表论文|学术成果|"
    r"期刊论文|会议论文)",
    re.IGNORECASE,
)

# 从锚点节点起抽到下一个同级 heading 或 section
def extract_publications_section(soup) -> list[str]:
    """Return list of paper-title strings scraped from the publications section."""

# 乱码 / 编码清理
def clean_title(raw: str) -> str:
    raw = html.unescape(raw)  # &nbsp; &amp; 等
    raw = unicodedata.normalize("NFC", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    # 常见乱码修复：UTF-8 误读成 Latin-1 的典型 pattern
    if "â€" in raw or "Ã¤" in raw:
        try:
            raw = raw.encode("latin-1").decode("utf-8")
        except UnicodeDecodeError:
            pass
    return raw
```

**阶段 2: 标题 → 权威元数据（1-2 天）**

每个抽到的标题走三级 fallback：

```
1. OpenAlex API:  GET /works?search=<title>  (精确 title match + 作者年份软验证)
   - 命中 → 拿 doi / openalex_id / authors_raw / year / venue / abstract / citations
2. Semantic Scholar API: /graph/v1/paper/search?query=<title>
   - 命中 → 补 S2 paper_id / tldr / references
3. arXiv API:  /api/query?search_query=ti:"<title>"
   - 命中 → 拿 arxiv_id + 全文 PDF URL
   - 下载 PDF → pdfminer 抽全文 → 存到 source_page.clean_text_path
```

都 miss 的情况下也留下来——至少有标题，后面可以手动补。

**阶段 3: 无 identity gate 直写入库**

这些来自 homepage 的论文直接落 `professor_paper_link` 表：

```python
upsert_paper(conn, title_clean=cleaned_title, ..., canonical_source="official_page")
# link_status = 'verified'  # 不走 gate
# evidence_source_type = 'homepage_publication_list'
# author_name_match_score = 1.0  # homepage 权威
# topic_consistency_score = NULL  # 不适用
# is_officially_listed = true
```

**阶段 4: arxiv 全文论文库（为 LLM 画像）**

新增 `paper_full_text` 表：

```sql
CREATE TABLE paper_full_text (
    paper_id text PRIMARY KEY REFERENCES paper(paper_id),
    arxiv_id text,
    source_url text,
    plaintext text NOT NULL,   -- pdfminer 抽的全文
    abstract text,              -- 首段或 arxiv metadata
    char_length int GENERATED ALWAYS AS (char_length(plaintext)) STORED,
    fetched_at timestamp,
    run_id uuid
);
```

有了全文以后，`profile_summary` 的生成 prompt 可以喂：
- 教授官网简介（profile_raw_text）
- 教授 verified 论文 **全文**（前 5-10 篇的 abstract + intro）
- 教授 research_directions（已有）

LLM 合成的画像立刻从"基于 3-5 行官网简介的泛泛描述"跃升到"**基于真实研究成果的深度画像**"。

### 4.4.2 兼容现有 pipeline

原有 `paper_collector`（OpenAlex/S2 → identity_gate）**保留但降级为 fallback**：

```
Primary:  homepage Publications 抽取 → 直写 verified (99%+ 教授能抓到)
Fallback: OpenAlex/S2 候选 → gate v2（双语名 + ORCID）筛选（剩下的 1%）
```

Fallback 的 gate 质量问题（§4.2）仍然要修，因为 45%+ 的老师官网其实 publications 块不完整或没维护，还是要从 OpenAlex 补；但 gate 的压力大大降低——主工作量从"审核 1 万条候选"变成"审核极少数 fallback 候选"。

### 4.4.3 对样例问题的影响

- **Q11** (pFedGPA 论文) — 如果该论文出现在某位教授的 homepage publications 中，直接 verified。
- **Q16** (王学谦是否大牛) — homepage 列了 50+ 篇顶会论文 + 引用 5000+ → "大牛"判断有据。
- **Q18-Q23** (具身智能综述) — Web Search + LLM 知识；但若本地有深圳做具身智能的教授的真实论文全文，LLM 合成时可以**引用本地权威论文**作为论据。

**这个改动是 Sprint 1 的核心，必须优先于 gate v2 的 CJK/EN 修补**——因为 gate v2 只是在错误管线上打补丁，homepage-first 才是正确管线。

### 4.5 论文→画像 反哺机制

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

### 6.1 核心判断：**Sprint 1 重新排序**

用户反馈 B 让 Sprint 1 的重心从"修 gate"转为"**重写论文管线源头**"。原因：
- 修 gate 只能救回已被爬进来的 OpenAlex/S2 候选中的部分（预计 +2000 篇）
- 而 homepage-first 管线直接从**权威源**起步，**不需要** gate（预计 +5000-10000 篇，且有全文）
- gate 修复仍然要做，但作为 fallback 的加固，不是主攻

### 6.2 完整优先级表

| Priority | 工作项 | 工期 | 解锁的样例问题 | 为什么这么排 |
|---|---|---|---|---|
| **P0** | **Homepage Publications 抽取 + 标题→API 补元数据 + arxiv 全文库** | 3-4 天 | Q1/Q11/Q16 从单薄变深度，解锁画像反哺 | **用户反馈 B：管线方向纠正** |
| **P0** | **chat 接论文检索 pattern** (`<title>` 精查 + "这论文的链接") | 半天 | Q11/Q12 | 简单必要，样例必考 |
| **P0** | **专利数据采集**（xlsx 已有） | 1 天 | Q24/Q25 | 数据就在那，导入即可 |
| **P1** | **论文 gate v2 (CJK/EN/pinyin 双语 + ORCID 优先)** | 2 天 | OpenAlex fallback 路径的论文 | Gate 仍然是 fallback，但不能一直烂着 |
| **P1** | **Web Search 工具 (Serper / DDG)** | 2-3 天 | Q3/Q5/Q8/Q14/Q17/Q18-23 | PRD §1.3 + §E 窄例外明确要求 |
| **P1** | **教授画像反哺闭环（verified papers 全文 → expanded topics + profile_summary）** | 3-5 天 | 全库画像质量跃升 | 建立在 P0 homepage + arxiv 全文之上 |
| **P2** | **Query Rewriter (LLM 改写：代词/上下文/别名/字序)** | 2 天 | Q2/Q4/Q8/Q12 | 多轮质量 40% → 85% |
| **P2** | **Agent Orchestrator (planner + reflection loop)** | 1-2 周 | Q13/Q21 复杂查询 | 真正 Agentic 的核心 |
| **P3** | **Hybrid Retrieval (embedding + rerank, Milvus/pgvector)** | 1 周 | Q3/Q9 语义质量 | ILIKE 兜底 90% 情况够用，这是锦上添花 |
| **P3** | **实体 NER + slot filling** | 3 天 | Q13 多条件 | 单条件能跑，多条件缺 |
| **P3** | **公司域歧义消解 G** | 1 天 | Q7 | 小改动 |
| **P4** | **产品能力表 + 采集**（Q5 机械臂按电梯）| 2 周 | Q5 | 需全新数据源 |
| **P4** | **市场评价数据源**（news/analyst 接入）| 2 周 | Q14/Q17 | 需新数据源 |
| **P4** | **Topic 切换检测 + Session boundary** | 3 天 | 长对话 | 锦上添花 |

### 6.3 建议的 3 个 Sprint（修订版）

**Sprint 1 (1 周) — 论文管线倒置 + 数据补齐**：
- **P0 Homepage Publications 抽取管线**（~4 天，核心）
  - 专项重扫 775 个 prof homepage，抽 Publications 区块
  - 标题 → OpenAlex / S2 / arxiv 三级 fallback 补元数据
  - arxiv 命中的下 PDF → pdfminer → paper_full_text 新表
  - 直接写 verified，**不过 gate**
- P0 chat 论文检索 handler（半天）
- P0 专利 xlsx 导入（1 天）
- P1 gate v2 CJK/EN 修补（1 天）— 对剩余 OpenAlex-only 论文起作用
- 验证：
  - Verified paper 总数从 4190 → 预期 12000+
  - 有 full_text 的论文 ≥ 2000（arxiv 命中率保守估 20-30%）
  - 25 题中能答对 20-22 题

**Sprint 2 (2 周) — 画像与 Agentic 初形**：
- P1 教授画像反哺：基于 homepage publications + arxiv 全文重生成 profile_summary
- P1 Web Search 工具 (Serper API 或 DDG)
- P2 Query Rewriter (LLM)
- 验证：
  - profile_summary 覆盖率 0.1% → 95%+（775/820）
  - 画像质量从 "~75 字泛化"→ "基于真实论文的 300-500 字深度画像"
  - Q3/Q8/Q14/Q17/Q18-23 解锁（Web Search）

**Sprint 3 (2 周) — 真 Agentic RAG**：
- P2 Agent Orchestrator（planner + reflection loop + 多工具）
- P3 Hybrid Retrieval (embedding + rerank)
- P3 实体 NER + 多条件 slot-filling
- P3 公司域 G
- 验证：
  - 25 题中 22-23 题可答（含 Q13 复合过滤）
  - 平均响应链路清晰：Intent → Plan → Retrieve (N tools) → Rerank → Synthesize

---

## 7. 总结

**用户的 4 个直觉都对（前 3 个在 §0 已提，第 4 个是 2026-04-20 补充的深层反馈）：**

1. **"Agentic RAG 有较大缺失"** — 对。当前是"LLM 包装的 RPC"，不是 Agent。缺 planner / rewriter / web search / rerank。完成度 40.8%。

2. **"回答链路不清晰"** — 对。chat.py 1100 行单文件 + 多个 if 分支。目标架构 L0-L7 七层，当前压缩到 3-4 层。

3. **"论文验证过度拒绝"** — 对且根因明确。

4. **"教师官网列的论文一定是对的"** — 这是最深的洞察，直接推翻了当前"候选+审核"管线的前提。真正的正解是**权威源优先 + 外部库补元数据 + arxiv 全文抓取供画像反哺**。

**系统评估：** 扎实的"数据清洗管线 + LLM 包装的查询 API"，距离 PRD 要求的 Agentic RAG 还有 **4-5 周工程**：

```
W1: Sprint 1  论文管线倒置 (homepage-first + arxiv 全文) + 专利 xlsx + 论文 chat handler
             => verified paper 4k → 12k+，其中 arxiv 全文 ~2k 供 LLM 画像用
W2-3: Sprint 2 画像反哺闭环（基于论文全文重生成 profile_summary）
              + Web Search 工具 + Query Rewriter
              => 画像覆盖率 <1% → 95%+，E 类样例 Q18-23 全解锁
W4-5: Sprint 3 Agent Orchestrator + Hybrid Retrieval + NER slot-filling
              => 真正的 Agentic，Q13 复合过滤可答
```

**执行顺序建议（修订版）：**

1. **Sprint 1 Day 1-4**: homepage Publications 抽取 + arxiv 全文库（管线纠正，最大 ROI）
2. **Sprint 1 Day 5**: 专利 xlsx 导入 + chat 论文 handler（快速补齐）
3. **Sprint 1 Day 6-7**: gate v2 CJK/EN/pinyin 修补（fallback 路径加固）
4. **Sprint 2**: Web Search + Query Rewriter + **基于论文全文的画像反哺**
5. **Sprint 3**: Agent Orchestrator + Hybrid Retrieval

**里程碑检查点：**
- Sprint 1 末：25 样例题 20-22 可答，/browse 详情抽屉显示深度论文列表 + 代表作全文引用
- Sprint 2 末：25 样例题 22-23 可答；profile_summary 基于真实论文的深度画像
- Sprint 3 末：复杂查询（Q13 多条件、Q21 跨域+技术栈）可答；架构分层清晰
