---
title: User-Facing Chat Interface (ChatGPT-Style) Plan
date: 2026-04-19
status: v0-shipped-v1-planning
owner: claude
extends:
  - docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
origin:
  - docs/Agentic-RAG-PRD.md
  - docs/Multi-turn-Context-Manager-Design.md
---

# User-Facing Chat Interface Plan

## 0. 一句话目标

给**深圳科创生态的端用户**（投研、政府、高校、创业团队）提供一个 **ChatGPT 风格的 web 对话入口**，自然语言提问→系统路由到 canonical graph 检索和（必要时）online web search，返回**结构化、带引用、可追溯**的答案。

## 1. 与现有工作的关系

| 层 | 状态 | 本计划用到 |
|---|---|---|
| `docs/Agentic-RAG-PRD.md` | 已完成（产品层需求） | 用户场景、查询类型（A-G）、范围边界 |
| `docs/Multi-turn-Context-Manager-Design.md` | 已完成（上下文设计） | 指代消解、跨模块跳转、话题切换 |
| plan 005 §7（Retrieval Architecture） | 已规划未实现 | MVP 用 entity_lookup + graph_traversal 两模式 |
| plan 005 §8（Dashboard W1-W4） | 已规划未实现 | **不冲突**：admin console 是运维视图，chat 是端用户视图，分属不同应用 |
| Phase 1 canonical（company domain） | ✅ 已落地 | chat v0 直接查询 |
| Phase 3 canonical（professor/paper） | 表已建，pipeline hook 待做 | chat v0 可先只支持 company；professor 落地后扩展 |
| existing MiroThinker agent runtime | ✅ 已存在 | chat v1+ 用它做答案合成和 taxonomy 归类 |

## 2. Non-Goals

1. ❌ 通用 AI 助手（闲聊、天气、翻译）——按 PRD §1.3
2. ❌ 数据可视化大屏——PRD §1.3
3. ❌ 用户注册登录体系（v0-v2 匿名访问）——WeChat 走公众号身份
4. ❌ 深度行业研究报告生成——Type E 只出简明综述
5. ❌ 多租户 / 组织管理
6. ❌ 文件上传 / 多模态输入（一期纯文本）
7. ❌ 历史会话云端持久化（v0 用 localStorage，v3+ 再讨论 backend session store）
8. ❌ 复用 admin console 的 DataList/EntityDetail 页面 UI——chat 是独立应用

## 3. MVP 进阶：v0 → v4

每一级都是**可验收、可演示**的独立 milestone。不要跳级。

### v0 — 端到端打通 ✅ 已发布（Round 8 完成）

**状态**：2026-04-19 发布，单轮、模板答案、直查 canonical。原先因数据质量被 BLOCKED，现已解锁并上线。

**实现证据**：
- 后端 `/api/chat` 端点：commit `8e2f297`
- 前端 `chat.html` UI：commit `9a0617b`
- Codex 交叉验证发现并修复 3 处缺陷：commit `47745a2`
  - 正则 institution 捕获：消除贪婪匹配越界
  - 同名教授消歧：`A_prof_profile_ambiguous` 分支返回候选列表
  - LIMIT 引起的 count 虚报：分离 count 查询，不再用 `len(rows)` 谎报总数

**代码位置**：
- 落点在 `apps/admin-console/backend/api/chat.py`（务实 v0 宿主；v1+ 会迁出至独立 `apps/chat-app/`）
- 前端为 vanilla HTML，挂载于 `/chat`，**不需要 React build**

**支持的查询模式**：
| pattern_id | 含义 |
|---|---|
| `A_prof_profile` | 单个教授画像（姓名 + 可选机构） |
| `A_prof_profile_ambiguous` | 同名教授消歧（多候选） |
| `A_prof_list_by_topic` | 按机构/主题的教授列表 |
| `A_patent_by_applicant` | 按申请人的专利列表 |

**Golden-path 测试结果**（3 条典型 query）：
- ✅ "丁文伯教授的简介" → 返回真实 profile（canonical 命中）
- ✅ "清华大学做 AI 的教授有哪些" → 返回教授列表
- ❌ "云鲸智能的专利" → 0 结果。**原因**：`patent` 表为空（0 rows），非代码缺陷

**答案生成**：规则模板，格式 `{answer_text, citations, structured_payload}`，**不调 LLM**。

### v1 — LLM 答案合成（下一轮）

**范围**：在 v0 检索结果之上叠加 LLM 自然语言合成，保留 citation。

**设计原则**：复用 v0 的 entity retrieval + graph traversal，**不改检索层**，只替换 synthesis 层。

#### 1) 检索层保持不变

与 v0 完全相同：`entity_lookup` + `graph_traversal`，得到结构化 rows（教授 / 论文 / 专利 / 公司）。

#### 2) Evidence Block 组装

将检索到的结构化 rows 打包成带引用标记的 context block，喂给 LLM：

```
[1] (professor) 丁文伯，清华大学深圳国际研究生院，研究方向：XXX
    prof_id=PROF-abc123, identity_status=verified
[2] (paper) "Title...", 2024, venue=ICML, authors=[丁文伯, ...]
    paper_id=PAPER-xyz789, verification_confidence=0.92
[3] (patent) 申请号 CN2024..., 申请人=...
    patent_id=PAT-000001
...
```

每个 evidence block 形如 `[N] (type) summary ... id=<ID>`，`[N]` 即 LLM 产出时要引用的标记。

#### 3) LLM Prompt 骨架

沿用项目现有本地 gemma4 模型（与 `name_identity_gate` / `paper_identity_gate` / `medium_rescan` Phase B 一致）。

```python
SYSTEM = """你是深圳科创检索助手。基于给定的证据块回答用户问题。
要求：
1. 只使用证据块中的事实，禁止编造。
2. 在每个事实后用 [N] 标记引用的证据块编号。
3. 若证据不足以回答，明确说"当前库中暂无相关信息"。
4. 输出简洁的中文 markdown，不超过 300 字。
"""

USER = {
  "question": "<原始 query>",
  "evidence_blocks": [
    {"marker": "[1]", "type": "professor", "summary": "...", "id": "PROF-abc123"},
    {"marker": "[2]", "type": "paper", "summary": "...", "id": "PAPER-xyz789"},
    ...
  ],
  "citation_format_spec": "每个事实后紧跟对应的 [N]；末尾不需要单独列参考文献。"
}
```

LLM 输出解析：正则提取 `[\d+]` 标记，与 evidence_blocks 的 id 建立映射。

#### 4) 响应契约扩展

`ChatResponse` 新增字段：

```python
class ChatResponse(BaseModel):
    # ... v0 既有字段
    answer_style: Literal["template", "llm_synthesized"]
    citation_map: dict[str, str]  # "[1]" -> "PROF-abc123"
```

**返回 BOTH**：
- `structured_rows`：v0 原样的结构化 rows（前端仍可渲染实体卡片）
- `answer_text`：LLM 合成的自然语言答案（含 `[N]` inline markers）
- `citation_map`：`[N]` → evidence ID 的映射

#### 5) 降级策略

LLM 调用失败（超时 / 返回格式非法 / 网络错误）时：
- 回退到 v0 规则模板答案
- `answer_style="template"`
- 写一条 `pipeline_issue` 记录：`stage='chat_synthesis'`, `severity='low'`
- **用户侧无感知**：仍返回可用答案，不抛 500

#### 6) 延迟预算

| 路径 | 目标 p95 |
|---|---|
| LLM 合成成功 | ≤ 3s |
| 模板降级 | ≤ 100ms |

LLM 超过 3s 视为慢调用，触发 issue 记录（但不强制打断，以 timeout 为准）。

#### v1 成功指标

- **LLM 合成率 ≥ 80%**：其余 20% 允许降级到模板（应为长尾错误，非常态）
- **Citation 准确性**：合成文本中每个 `[N]` 必须在 `citation_map` 中存在，且对应真实的 evidence row——**零悬空引用**
- **事实保真度**：人工抽检 20 条 query 的答案，**不得虚构任何证据块之外的事实**（precision=1.0 的硬要求；recall 软指标）

### v0 已知 gap（部分影响 v1 覆盖面，但不是 v1 的阻断项）

明确列出，以免在 v1 实施过程中混淆责任边界：

| Gap | 影响 | 是否阻断 v1 |
|---|---|---|
| 47% 教授没有 verified paper | 教授相关 list / 文献查询召回率受限 | ❌ 不阻断 v1 LLM 合成，纯数据缺口，由 paper pipeline 补齐 |
| `patent` 表空（0 rows） | 专利查询返回 0 结果 | ❌ 不阻断 v1，由 patent pipeline 补齐 |
| 多轮上下文未实现 | 无法指代消解 | ❌ 不阻断 v1（v1 保持单轮），在 v2 交给 context manager |
| 软删除（`identity_status='inactive'`）行 | 已在 v0 的 chat 查询里过滤 ✓ | 已处理 |

### v2 — 多轮上下文（Round 10）

**范围**：实现 `docs/Multi-turn-Context-Manager-Design.md` 定义的会话状态。

- 前端：session_id + 对话历史在 localStorage；支持"他""这家公司"这类指代
- 后端：SessionContext（active_entities 栈、current_module、turn history）
- 指代消解 + 跨模块跳转
- 验收：典型多轮场景（"介绍丁文伯"→"他参与的公司"→"这家公司的专利"）正确

### v3 — 新鲜度补丁 + 时间敏感查询（Round 11）

**范围**：加入 plan 005 §4.2 定义的 online_freshness_patch。

- Query Understanding 识别时间敏感 token（"最近"/"今天"/"本周"）
- 触发**单次** web search（google/bing/sougo）
- 结果进 `offline_enrichment_queue`，同时作为本次答案的 `live_citation`
- 明确 UI 标注"截至 T 从网络检索，未入库"
- 验收：问"公司 X 最近有融资吗"能用 web search 补齐

### v4 — WeChat 公众号接入（Round 12+）

**范围**：把 chat 后端接微信公众号 webhook。

- WeChat webhook 适配器（XML 协议）
- 鉴权（AppID/AppSecret）
- 简化输出（不能用富 HTML，降级成 markdown/纯文本）
- 验收：公众号能收发消息

## 4. 后端架构

### 4.1 应用边界

**新建独立应用**：`apps/chat-app/`

理由：
- 端用户 vs 运维用户，auth 模型不同
- 公开访问 vs 内部访问，部署安全边界不同
- admin-console 保留为纯运维工具，不增负担

目录结构：

```
apps/chat-app/
├── backend/
│   ├── main.py                      # FastAPI app
│   ├── deps.py                      # psycopg pool（复用 storage.postgres.connection）
│   ├── api/
│   │   ├── chat.py                  # POST /api/chat
│   │   └── health.py
│   ├── retrieval/
│   │   ├── planner.py               # Query Understanding + Plan
│   │   ├── entity_lookup.py         # v0+
│   │   ├── graph_traversal.py       # v0+
│   │   ├── lexical.py               # v2+
│   │   ├── semantic.py              # v2+
│   │   ├── event_query.py           # v2+
│   │   └── online_freshness_patch.py # v3+
│   ├── synthesis/
│   │   ├── template_answer.py       # v0
│   │   └── llm_answer.py            # v1+
│   ├── session/
│   │   ├── context_store.py         # v2+ (in-memory dict, TTL)
│   │   └── coref_resolver.py        # v2+
│   └── wechat/                      # v4
│       └── adapter.py
├── frontend/
│   └── (see §5)
├── tests/
│   ├── test_chat_api.py
│   ├── test_entity_lookup.py
│   ├── test_planner.py
│   └── test_synthesis.py
└── pyproject.toml
```

### 4.2 POST /api/chat 契约

**Request**:

```json
{
  "query": "云鲸智能做什么?",
  "session_id": "sess-abc123",    // 客户端生成；v2+ 用于上下文关联
  "turn_index": 0,                 // 从 0 开始递增；v2+
  "freshness_required": false,     // v3+ 客户端可强制触发 live search
  "stream": true                   // v1+ SSE；v0 忽略
}
```

**Response (non-streaming)**:

```json
{
  "session_id": "sess-abc123",
  "turn_index": 0,
  "answer": {
    "text": "云鲸智能是一家服务机器人公司，总部位于深圳...",
    "format": "markdown",
    "generated_by": "rule_template" | "llm",   // v1+ 可能是 llm
    "generated_at": "2026-04-18T10:30:00Z"
  },
  "citations": [
    {
      "cite_id": 1,
      "source_kind": "canonical.company",
      "entity_type": "company",
      "entity_id": "COMP-abc123",
      "excerpt": "云鲸智能，服务机器人，深圳",
      "fetched_at": "2026-04-17T..."
    }
  ],
  "retrieval_meta": {
    "query_type": "A",           // PRD Type A-G
    "retrieval_modes": ["entity_lookup", "graph_traversal"],
    "latency_ms": 45,
    "used_live_search": false
  },
  "structured_payload": {
    // 供前端渲染实体卡片；v0 只出 company；v1+ 按实体类型
    "type": "company",
    "company": {
      "company_id": "COMP-abc123",
      "canonical_name": "云鲸智能",
      "industry": "服务机器人",
      "team_members": [...],
      "funding_events": [...]
    }
  }
}
```

**Response (streaming, SSE)** — v1+：

```
event: token
data: {"text": "云鲸智能"}

event: citation
data: {"cite_id": 1, "source_kind": "canonical.company", ...}

event: structured_payload
data: {"type": "company", ...}

event: done
data: {"latency_ms": 2345}
```

### 4.3 Retrieval Planner（核心组件）

```python
@dataclass
class RetrievalPlan:
    query_type: Literal["A","B","C","D","E","F","G"]
    modes: list[str]              # 执行模式组合
    entity_candidates: list[dict] # 从 Query Understanding 识别的实体词
    needs_freshness_patch: bool
    needs_clarification: bool     # Type G 歧义

def plan(query: str, session_ctx: SessionContext | None) -> RetrievalPlan:
    # 1. rule-based 关键词分类（"最近"、"是谁"、"有哪些专利"）
    # 2. NER：匹配 company/professor/paper/patent 的 canonical_name + aliases
    # 3. 兜底：LLM 分类（v1+）
    ...

def execute(plan: RetrievalPlan, conn) -> RetrievalResult:
    results = {}
    if "entity_lookup" in plan.modes:
        results["entities"] = entity_lookup(plan.entity_candidates, conn)
    if "graph_traversal" in plan.modes:
        results["graph"] = graph_traversal(results["entities"], depth=1, conn)
    ...
    return RetrievalResult(...)
```

MVP 规则：

| Query 特征 | query_type | retrieval_modes |
|---|---|---|
| 含已知公司/教授/论文/专利名 | A | entity_lookup + graph_traversal |
| "有哪些 X"、多条件筛选 | B | lexical（v2+）/ fallback entity |
| "X 的 Y（跨域）" | C | entity_lookup + graph_traversal(深度 2) |
| "深圳做 X 的公司和教授" | D | entity_lookup × 多域 + aggregation |
| "X 技术路线有哪些" | E | taxonomy facet + online_freshness_patch（v3+） |
| 无法识别任一实体 | G 或 F | clarification 提示 |

## 5. 前端架构

### 5.1 技术选型

- **框架**：React 18 + TypeScript + Vite（复用 admin-console 技术栈，降低维护成本）
- **状态**：本地 `useReducer` 管 session；localStorage 持久化
- **样式**：Tailwind CSS 或简版 CSS module（v0 选简单的）
- **SSE**：原生 `EventSource`；Vite dev proxy 转后端
- **路由**：v0 单页；v2+ 加会话切换

### 5.2 页面组成

```
apps/chat-app/frontend/
├── src/
│   ├── App.tsx                       # 顶栏 + 主 chat 区
│   ├── components/
│   │   ├── ChatComposer.tsx          # 输入框 + 发送按钮（回车+Shift+Enter 换行）
│   │   ├── MessageBubble.tsx         # user / assistant 消息
│   │   ├── AnswerRenderer.tsx        # markdown + inline citation
│   │   ├── CitationCard.tsx          # 引用卡片（source_kind 分色）
│   │   ├── EntityCard.tsx            # company/professor/paper/patent 结构化渲染
│   │   ├── EventTimeline.tsx         # v1+ company 融资/事件时间线
│   │   ├── SessionSidebar.tsx        # v2+ 左侧会话列表
│   │   └── FreshnessBadge.tsx        # v3+ "数据截至 T" 标签
│   ├── hooks/
│   │   ├── useChat.ts                # SSE + 状态管理
│   │   └── useSession.ts             # v2+
│   ├── api.ts                        # fetch helper
│   └── types.ts
├── index.html
├── vite.config.ts
└── package.json
```

### 5.3 关键 UX 规则

1. **引用强制可点开**：每条 citation 点开显示 source_url、抓取时间、原文摘录
2. **实体卡片 hover → 预览**：公司名/教授名作为链接，悬停显示迷你卡片
3. **降级提示明显**：当无匹配实体时，UI 清晰告知"暂无相关信息"，不要编造
4. **online search 的 UI 标注**：`live_citation` 必须视觉上与 canonical citation 区分（例如橙色 vs 蓝色）
5. **空白状态引导**：首次打开显示 4-6 个样例问题按钮（对应 PRD §1.2 典型场景）

## 6. Rounds 分解

| Round | 内容 | 依赖 | 状态 |
|---|---|---|---|
| **Round 8** | chat-app 骨架 + v0 retrieval planner（entity_lookup）+ 规则模板答案 + vanilla HTML 前端 | Phase 1 company canonical ✅ | ✅ 已发布（2026-04-19） |
| **Round 9** | LLM answer synthesis（gemma4 本地）+ citation markers + 模板降级 | Round 8 ✅ | 下一轮，见 v1 设计 |
| **Round 10** | 多轮上下文：SessionContext + 指代消解 + 跨模块跳转 | Round 9 | |
| **Round 11** | online_freshness_patch：web search + `offline_enrichment_queue` 回写 | Round 10 + Phase 5（retrieval 全套） | |
| **Round 12** | WeChat 公众号 webhook 适配 | Round 11 + 微信 AppID/Secret | |
| **平行 Round 7.5** | professor 域 chat 支持（需 Phase 3 pipeline_v2 hook 先做，即 Round 6 之后的集成） | Round 6 + pipeline_v2 bridge | |

## 7. 与 Phase 2 (company news) 的交互

Chat v3 依赖 `company_signal_event` 的实际新闻事件数据。那些数据来自 Phase 2 news_refresh。所以：

- Chat v0-v2 不需要 Phase 2；用 xlsx 导入的融资事件就够演示
- Chat v3+ 需要 Phase 2 news_refresh 跑起来；否则"公司 X 最近有什么动态"答不出投研级别细节

这决定了如果要并行推进，Phase 2 news 和 Chat v3 是耦合的。v0-v2 可以独立先做。

## 8. 首个 Round（Round 8）验收标准 ✅ 已达成

v0 MVP 可感知交付物（2026-04-19 验收）：

- [x] 浏览器 `/chat` 路径可访问 chat 页面（vanilla HTML，无 React build）
- [x] "丁文伯教授的简介" → 返回 canonical profile + citation
- [x] "清华大学做 AI 的教授有哪些" → 返回列表
- [ ] "云鲸智能的专利" → 0 结果（**数据缺口**：patent 表空，非代码 bug）
- [x] Codex 交叉验证通过，已修复 3 处缺陷（见 commit `47745a2`）
- [x] Golden-path 2/3 返回真实数据

## 9. 与 plan 005 的统一视图

```
┌─────────────────────────────────────────────────────────────┐
│                 深圳科创对话式检索平台                        │
├──────────────────┬──────────────────┬───────────────────────┤
│ apps/chat-app/   │ apps/admin-con.  │ apps/miroflow-agent/ │
│ (端用户 chat)     │ (运维 dashboard) │ (数据采集 + canonical │
│                  │                  │  + retrieval services)│
│ [Round 8 ✅ 宿于   │ [Round 4 ✅ +     │ [Phase 1-3 ✅ 主体    │
│  admin-console； │  未来 UI Round]  │  Phase 2 news 待做]   │
│  v1+ 迁出]        │                  │                       │
├──────────────────┴──────────────────┴───────────────────────┤
│            Postgres 16 + pgvector (canonical graph)          │
│  V001 source + V002 company + V003 prof + V004 paper/pat     │
│  V005a prof_paper_link + V005b 跨域关系 ✅                    │
└─────────────────────────────────────────────────────────────┘
```

## 10. 下一步行动

1. ✅ v0 已发布（Round 8 完成）——检索 + 模板答案 + Codex 交叉验证通过
2. **下一步**：启动 Round 9（v1 LLM synthesis），按本文档 §3 v1 设计：
   - 复用 v0 retrieval，不改检索层
   - 新增 `synthesis/llm_answer.py`，gemma4 本地调用
   - 扩展 `ChatResponse`（`answer_style`, `citation_map`）
   - 实现降级到模板 + `pipeline_issue` 记录
3. Round 9 与 Phase 3 pipeline 集成（professor 实际数据）可并行推进
