---
title: Agentic RAG 执行计划（按 Sprint 拆解、可直接动手写代码）
date: 2026-04-20
status: active
owner: claude (architect) + codex (builder)
extends:
  - docs/plans/2026-04-20-001-system-capability-audit-and-agentic-rag-gaps.md
  - docs/plans/2026-04-20-002-agentic-rag-implementation-design.md
grounded_in:
  - docs/api.md（Qwen3-Embedding-8B / Qwen3-Reranker-8B / Serper / Gemma4 真实 endpoint）
  - apps/miroflow-agent/src/data_agents/professor/vectorizer.py（已存在的 Milvus+Qwen 管线）
  - apps/miroflow-agent/src/data_agents/providers/web_search.py（已存在的 Serper provider）
  - apps/admin-console/backend/api/chat.py v3.1（已存在的 A/B/D/E/F/G 分类路由）
---

# Agentic RAG 执行计划

> 001 讲 *做什么*、002 讲 *怎么设计*、**本文讲 *按顺序干什么*——每个 PR 的文件、接口、验收、测试**。
>
> 原则：
> 1. **先用已有的**。`vectorizer.py` 已经在跑 Qwen3-Embedding-8B 4096d + Milvus，**不引入 pgvector**（002 的假设需修正）。
> 2. **一件事一个 PR**。每个 Sprint 的每个 milestone 对应一个可独立 ship 的 commit。
> 3. **每行代码有 acceptance 和 test**。无 test 不合并。
> 4. **遵循 CLAUDE.md 的 Hybrid Flow**：每个 milestone 都要走 Stage 1→5。

---

## 0. 现状对账（Existing Reality Check）

| 组件 | 位置 | 状态 | 说明 |
|---|---|---|---|
| Qwen3-Embedding-8B 客户端 | `vectorizer.py::EmbeddingClient` | ✅ 已实现 | 4096-dim，默认 `100.64.0.27:18005` |
| Milvus professor 集合 | `ProfessorVectorizer` | ✅ 已跑通 | dual-vector: profile + direction |
| Serper Web Search | `providers/web_search.py::WebSearchProvider` | ✅ 已实现 | `trust_env=False`，fallback curl |
| Gemma4 LLM 调用 | `llm_profiles.resolve_professor_llm_settings("gemma4")` | ✅ 已在用 | chat.py 的 classifier 已在用 |
| Qwen3-Reranker-8B 客户端 | — | ❌ **缺失** | api.md 给了 endpoint `100.64.0.27:18006`，需新增 `providers/rerank.py` |
| Paper identity gate v2 (CJK+pinyin) | `paper_identity_gate.py` | ⚠️ **有 bug** | 47% 误拒，因为只传 Latin name 不传 CJK/拼音 |
| Homepage-authoritative paper 管线 | — | ❌ **缺失** | 用户 pipeline inversion 洞见的落地方案没写 |
| arxiv / OpenAlex 全文抓取 | `paper/openalex.py` 只拿元数据 | ⚠️ **部分** | 需新增 `paper_full_text` 表 + 抓取器 |
| `chat.py` B 类语义检索 | 目前是 SQL LIKE | ⚠️ **占位** | 应调 Milvus + Reranker |
| `chat.py` 证据接 Milvus | 目前直接查 Postgres | ⚠️ **占位** | 需要检索服务层 |
| `paper` 域的 Milvus 集合 | — | ❌ **缺失** | 目前只有 prof profile 向量，没有 paper 向量 |
| `company/patent` 域的 Milvus 集合 | — | ❌ **缺失** | 跨域 D 类查询需要 |
| D 类跨域聚合 `_lookup_companies_by_topic` | `chat.py:148` | ⚠️ **LIKE 粗查** | 需要统一走 Milvus |
| 画像反向增强（arxiv→summary） | `batch_reprocess.py` 部分能力 | ⚠️ **半成品** | paper 全文没接入 |

**核心约束**：
- 本地 Qwen embed/rerank 的 key 是 `k8#pL2@mN9!qjfkew87@#$0204`，通过 `API_KEY` / `.sglang_api_key` 文件或 `resolve_professor_llm_settings` 读取（**不要硬编码**）
- Serper 的 key 已在 api.md：`cba96f08451642c404770b65ab2d4494b7f61e2e`；读取用 `SERPER_API_KEY` 环境变量
- 所有 HTTP 调用必须 `trust_env=False` 或 `proxy=None`（历史踩过代理坑，memory 有记录）

---

## 1. 里程碑总览

> **⚠️ 顺序调整（2026-04-20 eng-review 决议）**：原 M1 → M2 反转为 **M2 先**。理由：用户 pipeline inversion 洞见——主页权威论文命中率 100%，identity gate v2 只对非主页路径（OpenAlex 搜索，约 10-20% 论文）有价值；先 M2 能最大幅度降低论文缺口，M1 留到 M2 完成后评估 OpenAlex 路径实际缺口再决定是否全量做。

| M | 名称 | 目标问题 | CC 时长估计 | 依赖 |
|---|---|---|---|---|
| **M0** | 基础设施 | 补齐 Reranker client + 统一 LLM 配置、httpx 统一 | 1-2 小时 | — |
| **M2** | 主页权威论文管线 | 每个教授主页 papers 100% 收录 + arxiv 全文 | 6-8 小时 | M0 |
| **M1** | Identity Gate v2 | 补齐 OpenAlex 路径的 CJK+pinyin+ORCID（M2 未覆盖的 10-20%） | 3-4 小时 | M0 + M2 数据 |
| **M3** | 多域向量化 + 检索服务 | paper/company/patent Milvus 集合 + 统一 RetrievalService | 4-6 小时 | M0 |
| **M4** | Chat B/D 换成语义检索 | B 类用向量召回+rerank，D 类跨域合并 | 3-4 小时 | M3 |
| **M5** | Web Search 兜底 + 引用 | E 类查知识问答，低置信度触发 Serper | 2-3 小时 | M0 |
| **M6** | 画像反向增强闭环 | arxiv 全文 + 会议履历 → 更丰富的 profile_summary | 4-5 小时 | M2 |

**关键路径**：M0 → **M2** → M1 → M3 → M4（M5、M6 并行可行）

**完整时长**：~25-32 小时 CC 工作量（按用户 tech doc 的 3-Sprint 15 工作日节奏展开）

---

## 2. M0 — 基础设施补齐

### M0.1 新增 Reranker 客户端（`providers/rerank.py`）

**Why**：M3/M4 需要；api.md 第 179-305 行有样例代码；**没有现成实现**。

**文件**（新建）：
- `apps/miroflow-agent/src/data_agents/providers/rerank.py`
- `apps/miroflow-agent/tests/providers/test_rerank.py`

**接口**：
```python
# providers/rerank.py
from __future__ import annotations
import httpx
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int                 # 原始文档序号
    score: float               # relevance_score ∈ [0, 1]
    document: str              # 原始文本（便于 trace）

class RerankerClient:
    def __init__(
        self,
        *,
        base_url: str = "http://100.64.0.27:18006/v1",
        api_key: str = "",
        model: str = "qwen3-reranker-8b",
        timeout: float = 60.0,
    ) -> None: ...

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """POST /rerank. Returns sorted by score desc, top_n truncated.
        trust_env=False 已内置。JSON decode 错抛 httpx.HTTPStatusError。"""
```

**Acceptance**：
- `RerankerClient.rerank("如何重排序", ["reranker 说明", "天气不相关"])` 返回按 score 降序
- 内部使用 `httpx.Client(trust_env=False)` 避免代理污染
- 空 `documents` → 返回空 list，不报错
- 缺 API key → raise `RuntimeError` with 清晰消息
- Top_n > len(documents) → 自动截断为 len

**测试**（`test_rerank.py`）：
- `test_rerank_returns_sorted_results` — mock httpx 返回 3 个 score，断言按 score 降序
- `test_rerank_handles_empty_documents` — 空输入返回空，不发请求
- `test_rerank_missing_api_key_raises` — 缺 key 时抛清晰异常
- `test_rerank_proxy_bypass` — 断言 `httpx.Client` 的 `trust_env=False`

**TDD 顺序**：先写 4 个测试 → 跑都 RED → 实现 class → GREEN → commit。

---

### M0.2 统一本地 API key 解析（`providers/local_api_key.py`）

**Why**：api.md 的样例都用 `API_KEY / OPENAI_API_KEY / .sglang_api_key` 三层回退。现在 `vectorizer.py` 的 `EmbeddingClient` 和新增的 `RerankerClient` 都需要同一套，**不要复制粘贴**。

**文件**（新建）：
- `apps/miroflow-agent/src/data_agents/providers/local_api_key.py`

**接口**：
```python
# local_api_key.py
from pathlib import Path

def load_local_api_key(repo_root: Path | None = None) -> str:
    """Read key from env (API_KEY / OPENAI_API_KEY / SGLANG_API_KEY)
    then from <repo_root>/.sglang_api_key. Returns '' if nothing found.
    Callers decide whether empty is fatal."""
```

**Acceptance**：
- 按 env 优先级查（3 个变量）
- Fallback 到 repo root 的 `.sglang_api_key` 文件
- 全部为空返回 `""`（不 raise，由调用方决定）

**测试**：monkeypatch env，断言 3 个优先级 + 文件 fallback + 空字符串。

---

### M0.3 扩展 EmbeddingClient 支持 reuse session（`vectorizer.py`）

**Why**：当前每次调用都新建 httpx 请求，批量时会浪费 handshake。生产场景需 reuse 连接池。

**改动**（不破坏现有接口）：
- `EmbeddingClient.__init__` 接受 `client: httpx.Client | None = None`（None 时内部建一个 `trust_env=False`）
- 加 `__enter__` / `__exit__` 和 `close()` 支持 context manager

**Acceptance**：
- 旧调用 `EmbeddingClient(base_url=...)` 不变
- `with EmbeddingClient(...) as client: ...` 自动 close
- 默认内部 `trust_env=False`（之前没显式设，借此机会补上）

**测试**：
- `test_embedding_client_trust_env_false` — 检查默认 httpx.Client 配置
- `test_embedding_client_as_context_manager` — with 块结束后 httpx.Client.close() 被调用

---

### M0.4 移除 002 里的 pgvector 假设

**Why**：002 设计文档 §8 和 §9 规划了 V013 pgvector 迁移。但现实是 Milvus 已用于 prof，**新增 pgvector 要再做一次运维 + 同步双写**，不值得。

**改动**：
- 编辑 `docs/plans/2026-04-20-002-agentic-rag-implementation-design.md`：§0 技术栈表把 pgvector 改成 Milvus；§8 删 V013；§9 把 `chat/retrieval/` 里的 pgvector SQL 换成 Milvus
- 在 002 顶部加一句：`updates: 本文档 V013 被 003 执行计划废弃，改用现有 Milvus`

**Acceptance**：002 不再提 pgvector，CI 里不会出现 `CREATE EXTENSION vector`。

---

### M0.5 httpx 统一（eng-review Q1 决议）

**Why**：`providers/web_search.py` 用 `requests`，`vectorizer.py` 和新 `rerank.py` 用 `httpx`。两个 HTTP 库共存=2MB install + 心智负担。`httpx` 已是主要选择（deps 里有），**统一到 httpx**。

**改动**：
- 改：`providers/web_search.py::WebSearchProvider` 的 `requests` → `httpx`（保留 `trust_env=False`、curl fallback）
- 保留 public API（`search(query) → dict`）不变，避免调用方修改
- 本次不动 `requests` 的卸载（其他模块还在用），等到 grep 出零引用后再清理

**Acceptance**：
- `uv run pytest -k test_web_search` 全过
- `uv run pytest -k test_web_search_fallback_curl` 过
- `grep -rn "import requests" apps/miroflow-agent/src/data_agents/providers/` 返回空

**测试**：`test_web_search_httpx_migration_preserves_behavior` — 旧 mock 响应依然 parse OK。

---

## 3. M1 — Identity Gate v2（CJK + pinyin + ORCID）

### M1.1 名字变体解析器

**Why**：001 §4.2 说 47% prof 的 paper 被全拒。Root cause：`paper_identity_gate._build_prompt` 只传 `context.name`（通常是 Latin），但候选论文的 `authors` 是中文或拼音，LLM 看不出是同一人。

**文件**（新建 + 修改）：
- 新：`apps/miroflow-agent/src/data_agents/professor/name_variants.py`
- 改：`apps/miroflow-agent/src/data_agents/professor/identity_verifier.py::ProfessorContext`（加 `name_variants: tuple[str, ...]` 字段）
- 改：`paper_identity_gate.py::_build_prompt`（渲染所有变体）

**接口**：
```python
# name_variants.py
@dataclass(frozen=True, slots=True)
class NameVariants:
    """All plausible spellings/forms the target prof's name could take."""
    zh: str | None           # 姚建铨
    en: str | None           # Jianquan Yao
    pinyin: str | None       # jian quan yao
    initials: list[str]      # ["J. Yao", "J.Q. Yao"]
    all_lower: list[str]     # ["jianquan yao", "j yao", ...]

def resolve_name_variants(
    canonical_name: str | None,
    canonical_name_zh: str | None,
    canonical_name_en: str | None,
) -> NameVariants:
    """Build all variants by:
      - CJK → pinyin (via pypinyin — **NEW DEP**, add to pyproject.toml)
      - en name → initials (first initial + surname)
      - normalize to lowercase for matching"""
```

**Acceptance**：
- `resolve_name_variants("Jianquan Yao", "姚建铨", None)` → 返回含拼音 "jian quan yao" + initials "J. Yao"
- `resolve_name_variants(None, "陈伟津", None)` → 拼音 "wei jin chen"，en 为空
- 全空输入 → 所有字段空/空 list（不崩）

**测试**（5 个以上 case 覆盖中→拼音、英→initials、all-None、单字姓、复姓）：
- `test_cjk_to_pinyin_full_name`
- `test_en_to_initials`
- `test_both_provided`
- `test_all_none_returns_empty`
- `test_compound_surname`（欧阳、诸葛 等）

---

### M1.2 identity gate 提示词升级

**改动**：
- `paper_identity_gate._build_prompt`：用 `context.name_variants` 渲染一个完整的 "候选姓名列表" 段落
- 提示词加 "Rule 7: 中英拼音为同一人；若候选论文 authors 包含任意一个变体，视为名字匹配"

**新提示词片段**：
```text
## 目标教授的已知姓名变体
- 中文：姚建铨
- 英文：Jianquan Yao
- 拼音：jian quan yao
- 缩写：J. Yao, J.Q. Yao

判断候选论文时，若 authors 列表中出现以上任意一个变体（或其 token 子集），视为名字匹配。
```

**Acceptance**：
- eval set（见 M1.4）上，误拒率从 47% → <10%
- 同名冤假错案（不同领域的 "Jianquan Yao"）仍被拒，即**不牺牲精度**

**⚠️ 测试前置**（eng-review 强规）：**先写回归测试复现 47% 误拒行为**（用真实 case：姚建铨/陈伟津的候选论文），跑 RED → 再写 fix → 跑 GREEN。不许先实现再补 test。

**测试**：
- `test_paper_identity_gate_rejects_chinese_authors_with_latin_query_FIXME` — 标 xfail；**fix 前必先跑红**
- `test_paper_identity_gate_accepts_chinese_author_list_with_latin_query_name` — fix 后变绿
- `test_paper_identity_gate_rejects_topic_mismatch_even_with_name_match` — 名字匹配但研究方向完全无关，断言仍拒

---

### M1.3 ORCID 双保险

**Why**：ORCID 是不会同名的全局唯一 ID。如果 prof 有 ORCID，可以跳过 LLM 裁决，直接 accept。

**现状**：`paper/orcid.py` 已经有基础 fetch 能力；`paper_identity_gate` 没用到。

**改动**：
- **注意**：`professor_orcid` 表 **由 V011 迁移创建**（和 M2.3 的 `paper_full_text` 合并在一个迁移里，随 M2 一起 ship；见下文 §V011 决议）
  ```sql
  CREATE TABLE professor_orcid (
      professor_id UUID PRIMARY KEY REFERENCES professor(professor_id),
      orcid VARCHAR(32) NOT NULL UNIQUE,
      source VARCHAR(64) NOT NULL,    -- homepage/openalex/manual
      confidence DECIMAL(3,2) NOT NULL,
      verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  ```
- 改：`paper_identity_gate.batch_verify_paper_identity`：如果候选论文的 `authors_orcid` 包含 prof 的 ORCID，直接标 accepted=True confidence=1.0，**跳过 LLM**
- 改：`paper/openalex.py::discover_professor_paper_candidates` 在 meta 中带上 author ORCID

**Acceptance**：
- 有 ORCID 的 prof，candidate 论文里匹配上 ORCID → 100% accept
- 无 ORCID 的 prof，走原 LLM 路径
- `professor_orcid` 表的 insert 通过 E2E 脚本 `scripts/backfill_professor_orcid.py`（OpenAlex author page 解析）

**测试**：
- `test_identity_gate_orcid_shortcut_accepts` — prof 有 ORCID，候选含 ORCID，断言不调 LLM
- `test_identity_gate_no_orcid_falls_back_to_llm` — 无 ORCID，走原路径

---

### M1.4 Eval set + 离线回测脚本

**Why**：没有量化就无法回答 "降到 5% 没降？"

**文件**（新建）：
- `apps/miroflow-agent/tests/data/paper_identity_eval.jsonl`（手工 100 条 ground truth：prof_id + title + should_accept）
- `apps/miroflow-agent/scripts/eval_paper_identity_gate.py`（跑 eval set，报 precision/recall/F1）

**Acceptance**：
- eval set 覆盖 5 类典型：CJK 正名、CJK 反拒（同名不同人）、拼音、ORCID、主题漂移
- 脚本输出：`accuracy=0.95 precision=0.94 recall=0.96 rejected_of_real=3%`
- 指标达标：precision ≥ 0.93，recall ≥ 0.90

**测试**：脚本本身有 smoke test（`test_eval_script_runs`）

---

## 4. M2 — 主页权威论文管线（Homepage-Authoritative Papers）

### M2.1 主页 Publications 区抽取器

**Why**：001 §4.4、002 §2 的 pipeline inversion 洞见——**prof 主页列出的论文是权威的，不需要 identity gate 再裁决**，只需匹配到 arxiv/OpenAlex 拿全文。

**文件**（新建 + 改）：
- 新：`apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
- 改：`apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`（加 publications 分段抽取）

**接口**：
```python
# homepage_publications.py
@dataclass(frozen=True, slots=True)
class HomepagePublication:
    raw_title: str               # 主页原始文本（可能脏）
    clean_title: str             # 去编号/引号/年份后的标题
    authors_text: str | None     # 原始 author 字符串
    venue_text: str | None
    year: int | None
    source_url: str              # 主页 URL
    source_anchor: str | None    # DOI/arxiv 链接（如果主页直接给了）

def extract_publications_from_html(
    html: str,
    *,
    page_url: str,
    professor_name_variants: NameVariants,
) -> list[HomepagePublication]:
    """Find Publications / 论文 / Selected Works 段落。
    Strategies in order:
      1. <h2>Publications</h2> 后的 <ol>/<ul>/<p> 序列
      2. 找出含 prof name variant 的段落
      3. 按年份锚点（20XX）倒推
    Clean title 规则：去除编号 [1]/1./[J]、引号、作者列表前缀。"""
```

**Acceptance**：
- 输入南科大 X 教授主页 HTML → 返回 ≥20 条 publication（手工对比主页）
- 每条 `clean_title` 长度合理（10-300 字符）
- `authors_text` 或 `venue_text` 至少一个非空（用于后续链接）

**测试**（fixture 5 所学校的真实主页 HTML）：
- `test_extract_tsinghua_sigs_format` — 清华 SIGS 主页
- `test_extract_sustech_format` — 南科大主页
- `test_extract_cuhksz_format` — 港中深主页
- `test_extract_hitsz_format` — 哈工深主页
- `test_extract_szu_format` — 深大主页

---

### M2.2 标题 → OpenAlex / arxiv 匹配

**Why**：主页只有标题字符串，需要 round-trip 到 API 拿结构化数据 + 全文 PDF。

**文件**（新建）：
- `apps/miroflow-agent/src/data_agents/paper/title_resolver.py`

**接口**：
```python
# title_resolver.py
@dataclass(frozen=True, slots=True)
class ResolvedPaper:
    title: str
    doi: str | None
    openalex_id: str | None
    arxiv_id: str | None
    abstract: str | None
    pdf_url: str | None
    authors: list[str]              # 规范化后的姓名
    year: int | None
    venue: str | None
    match_confidence: float          # 0.0-1.0
    match_source: str                # "openalex" | "arxiv" | "web_search"

def resolve_paper_by_title(
    clean_title: str,
    *,
    author_hint: str | None = None,
    year_hint: int | None = None,
    web_search: WebSearchProvider | None = None,
) -> ResolvedPaper | None:
    """Cascade：
      1. OpenAlex `/works?search="exact title"` → 若 Jaccard(title) > 0.9 return
      2. arxiv API `search_query=ti:"..."` → Jaccard > 0.9 return
      3. web_search → 从 top-5 里挑 title 最接近的（LLM 仲裁 or Levenshtein）
    Returns None if no match ≥ 0.85 confidence.
    Rate limits: OpenAlex 10/s, arxiv 1 req / 3s, web_search 按 WebSearchProvider。"""
```

**Acceptance**：
- 10 条手工测试标题中，至少 9 条能命中 OpenAlex/arxiv
- OpenAlex rate-limit 遵守（本地加 `token bucket`）
- arxiv 的 3s 间隔遵守

**测试**：mock httpx 模拟 3 类 API 响应；测 cascading + confidence 阈值。

---

### M2.3 全文抓取 + PDF 解析

**Why**：M6 的 profile reinforcement 需要 paper abstract / intro，元数据不够。

**文件**（新建 + 改）：
- 新：`apps/miroflow-agent/src/data_agents/paper/full_text_fetcher.py`
- 新：`V011_add_rag_tables.py`（**合并了 M1.3 的 `professor_orcid` + 本节的 `paper_full_text` + M2.2 的 `paper_title_resolution_cache`，三表一迁移；随 M2 PR 一起 ship**）

**新表 1**：
```sql
CREATE TABLE paper_full_text (
    paper_id VARCHAR(64) PRIMARY KEY REFERENCES paper(paper_id) ON DELETE CASCADE,
    abstract_clean TEXT,
    intro_clean TEXT,                -- 第一章（≤3000 字符）
    pdf_url TEXT,
    pdf_sha256 VARCHAR(64),          -- 去重
    source VARCHAR(32) NOT NULL,     -- arxiv | openalex | publisher | failed
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fetch_error TEXT                 -- null = 成功
);
CREATE INDEX paper_full_text_source_idx ON paper_full_text(source);
```

**新表 2**（M1.3 的）：
```sql
CREATE TABLE professor_orcid (
    professor_id UUID PRIMARY KEY REFERENCES professor(professor_id),
    orcid VARCHAR(32) NOT NULL UNIQUE,
    source VARCHAR(64) NOT NULL,    -- homepage/openalex/manual
    confidence DECIMAL(3,2) NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**新表 3**（M2.2 的 title-resolution cache，eng-review Q2 决议新增）：
```sql
CREATE TABLE paper_title_resolution_cache (
    title_sha1 VARCHAR(40) PRIMARY KEY,   -- sha1(normalized clean_title)
    clean_title_preview VARCHAR(500),      -- human-readable debug
    resolved JSONB NOT NULL,               -- ResolvedPaper | null
    match_source VARCHAR(32),              -- openalex | arxiv | web_search | miss
    match_confidence DECIMAL(3,2),
    cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX paper_title_cache_recent_idx ON paper_title_resolution_cache(cached_at DESC);
-- TTL: 30 days. Cleanup via cron: DELETE WHERE cached_at < NOW() - INTERVAL '30 days'
```
**省 API 预算**：8000 papers × 3 API（OpenAlex/arxiv/Serper）= 24000 calls；30 天 cache 命中可省 ~90%。

**接口**：
```python
# full_text_fetcher.py
@dataclass(frozen=True, slots=True)
class FullTextExtract:
    paper_id: str
    abstract: str | None
    intro: str | None
    pdf_url: str | None
    source: str
    error: str | None

async def fetch_and_extract_full_text(
    paper: ResolvedPaper,
    *,
    arxiv_rate_limiter: AsyncLimiter,
) -> FullTextExtract:
    """Priority:
      arxiv (if arxiv_id) → download PDF → pdfminer.six extract first 4 pages
      → split into abstract/intro via heuristic (regex 'Abstract', 'Introduction')
    Fallback: OpenAlex.abstract_inverted_index → rebuild abstract string"""
```

**Acceptance**：
- 随机 10 篇 arxiv 论文 → 9 篇能拿到 abstract；至少 7 篇能拿到 intro
- PDF 下载去重（同一 sha256 不重复存储）
- 失败时写 `fetch_error` 字段，不 raise 打断 batch

**测试**：fixture 2 个 arxiv PDF；测 abstract 分割正则；测 OpenAlex inverted_index 重建。

---

### M2.4 Orchestrator：homepage_publications → resolve → full_text → upsert

**Why**：把 M2.1/M2.2/M2.3 串起来，写一个 E2E 脚本。

**文件**（新建）：
- `apps/miroflow-agent/scripts/run_homepage_paper_ingest.py`

**逻辑**：
```python
# 伪代码
for prof in iter_professors_with_homepage():
    html = fetch(prof.homepage_url, trust_env=False)
    pubs = extract_publications_from_html(html, ...)
    for pub in pubs:
        resolved = resolve_paper_by_title(pub.clean_title, author_hint=prof.name)
        if resolved:
            paper_id = upsert_paper(resolved)
            link_prof_to_paper(prof.id, paper_id, source="homepage_authoritative")
            if not paper_full_text_exists(paper_id):
                full = await fetch_and_extract_full_text(resolved)
                upsert_paper_full_text(paper_id, full)
```

**Acceptance**：
- 10 个 prof 的 homepage → 平均每人 ≥15 篇论文被链接（对比之前 0 篇/人的 47% 空窗）
- 脚本有 `--dry-run` / `--limit=N` / `--resume`
- `logs/data_agents/paper/homepage_ingest_runs.jsonl` 记录每次运行 stats

**测试**：
- 1 个集成 test 用 fixture HTML + mocked title_resolver + mocked full_text
- 断言 Postgres 出现 professor_paper_link 新增
- 断言 paper_full_text 表有对应行

---

## 5. M3 — 多域向量化 + 统一 RetrievalService

### M3.1 新增 Milvus 集合：paper / company / patent

**Why**：目前只有 `professor_profiles` 集合。B 类查 prof 没问题，D 类跨域（公司 + 专利）靠 SQL LIKE，不够。

**文件**（新建）：
- `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py`（集合 schema 定义集中地）

**集合设计**：
| 集合 | 主键 | 向量字段 | 其他字段 |
|---|---|---|---|
| `professor_profiles` | `id (uuid)` | `profile_vector`, `direction_vector` | name, institution, department, title, quality_status |
| `paper_chunks` | `chunk_id` | `content_vector (4096)` | paper_id, professor_ids (json), year, venue, chunk_type (title/abstract/intro) |
| `company_profiles` | `company_id` | `profile_vector` | name, industry, tags_json |
| `patent_profiles` | `patent_id` | `claims_vector` | applicant, inventors, year, classification |

**Acceptance**：
- 4 个集合通过 `ensure_all_collections()` 一键创建
- 所有集合用 COSINE + AUTOINDEX
- 有 Drop+Recreate 的开发脚本（`scripts/reset_milvus_collections.py`）

**测试**：
- 单元测试用 in-memory Milvus-Lite（已 dep）
- `test_ensure_collections_idempotent`
- `test_search_by_profile_vector`

---

### M3.2 统一 RetrievalService（合流 SQL + Milvus + Rerank）

**Why**：`chat.py` 目前直接查 Postgres；002 §4 设计的 L5 Context Packer 需要一个拉取证据的统一入口。legacy `service/search_service.py` 是基于 SQLite + 老 Milvus（4 路向量集合），**弃用**，新写一个 clean 实现。

**位置决议（2026-04-20 eng-review）**：核心 `RetrievalService` 放在 **`apps/miroflow-agent/src/data_agents/service/retrieval.py`**——理由：
- 已有 `data_agents/service/` 目录（存放 legacy search_service.py，替换原有实现）
- 不只 chat 用，**reindex 脚本 / eval 脚本 / 未来其他消费者**都要用（Milvus+rerank+embed 三件套是共享基础能力）
- backend 通过现有 `deps.py::get_retrieval_service()` 注入，不重复搭架子
- chat 层如果需要 per-request 包装（session filter / citation tracking），放一个薄 adapter 在 `backend/chat/retrieval_client.py`

**文件**（新建）：
- 核心：`apps/miroflow-agent/src/data_agents/service/retrieval.py`
- 接入：`apps/admin-console/backend/deps.py`（新增 `get_retrieval_service()` 单例）
- 可选薄壳：`apps/admin-console/backend/chat/retrieval_client.py`（如果需要请求级包装）

**接口**：
```python
# apps/miroflow-agent/src/data_agents/service/retrieval.py
@dataclass(frozen=True, slots=True)
class Evidence:
    object_type: str           # "professor" | "paper" | "company" | "patent"
    object_id: str
    score: float               # 混合打分（rerank 后）
    snippet: str               # 用来拼 context 的片段
    source_url: str | None
    metadata: dict[str, Any]   # 额外字段（venue/year/department）

class RetrievalService:
    def __init__(
        self,
        pg_conn_factory: Callable[[], psycopg.Connection],
        milvus_client,
        embedding_client: EmbeddingClient,
        reranker: RerankerClient,
    ) -> None: ...

    def retrieve(
        self,
        query: str,
        *,
        domains: tuple[str, ...],         # ("professor",) 或 ("professor", "company", "paper")
        filters: dict[str, Any] | None = None,   # {"institution": "南科大"}
        candidate_limit: int = 30,         # 每个域先拉 30
        final_top_k: int = 10,             # rerank 后截断
    ) -> list[Evidence]:
        """步骤：
          1. query → embed（EmbeddingClient）
          2. 对每个 domain 做 Milvus ANN 取 candidate_limit
          3. 如果有 filters（institution/year/…），SQL 二次筛
          4. merge → documents（每个 evidence 取 snippet）
          5. RerankerClient.rerank(query, documents, top_n=final_top_k)
          6. 返回 Evidence 按 rerank score 降序"""
```

**Acceptance**：
- `retrieve("机器人", domains=("professor",))` 返回 ≤10 条，每条有 snippet
- `retrieve("深圳 AI 生态", domains=("professor","company","patent"))` 返回混合类型
- 过滤器 `{"institution": "南科大"}` 生效
- P50 延迟 < 1.5s（靠 concurrent Milvus 调用）

**测试**：
- `test_retrieve_single_domain_professor`
- `test_retrieve_cross_domain`
- `test_retrieve_respects_filters`
- `test_retrieve_rerank_reorders_candidates` — mock reranker 返回反向顺序，断言最终 order

---

### M3.3 反向索引 backfill 脚本

**Why**：paper_chunks / company_profiles / patent_profiles 目前是空集合。上线前要批量灌数据。

**文件**（新建）：
- `apps/miroflow-agent/scripts/run_milvus_backfill.py --domain=paper|company|patent [--limit=N]`

**Acceptance**：
- paper backfill：每条 paper 生成 1-3 个 chunk（title / abstract / intro），共约 25000 条（目前 ~8000 paper × 3）
- company backfill：每个 company 1 个 profile chunk，约 1000 条
- patent backfill：每个 patent 1 个 claims chunk
- 有 `--resume` 读 checkpoint 文件，断点续跑
- 批量 embedding 调用，batch_size=32

**测试**：smoke test 跑 `--limit=10`，断言 Milvus count 增加 30+。

---

## 6. M4 — Chat 端接入检索服务

### M4.1 B 类：语义检索 prof（替换 SQL LIKE）

**改动**：
- `chat.py::_lookup_professors_by_topic` 从直接 SQL 改为 `retrieval_service.retrieve(query, domains=("professor",), filters={"institution": inst})`
- 新增 `backend/deps.py::get_retrieval_service()` 单例

**Acceptance**：
- B 类 5 个典型 query 的命中率从 < 50% 提升到 > 85%（手工 eval）
- 结果包含 reranker 打分（用户 UI 看到相关度条）

**测试**：
- `test_chat_b_route_uses_retrieval_service` — mock service，断言 chat 调用它
- 集成 test（真 Milvus）：`test_chat_b_finds_robotics_profs_at_sustech`

---

### M4.2 D 类：跨域聚合

**改动**：
- `chat.py::_lookup_companies_by_topic` 删除 SQL LIKE，改为 `retrieve(domains=("company", "patent"))`
- `_answer_cross_domain` 的证据区按 domain 分区渲染

**Acceptance**：
- "深圳做具身智能的教授和企业" → prof + company + patent 三块结果
- 每块至少 3 条，整体不超过 15 条
- 回答合成保留 [N] 引用

**测试**：
- `test_chat_d_route_merges_three_domains`
- `test_chat_d_cites_each_domain_at_least_once`

---

### M4.3 E 类：知识问答 + Web Search 兜底

**改动**：
- `_answer_knowledge_qa` 加一个前置：先在 paper_chunks 里检索；若 top-3 score 都 < 0.5，调 `WebSearchProvider.search(query)` 拿 Serper 结果
- 合成时标注来源：`[本地论文]` / `[Web: example.com]`

**Acceptance**：
- "大模型蒸馏原理" → 命中本地 paper_chunks（2-3 条），不调 web
- "DeepSeek V3 发布" → 本地空，触发 Serper → 回答带 [Web] 引用

**测试**：
- `test_e_route_uses_local_chunks_when_confident`
- `test_e_route_falls_back_to_web_search_when_low_confidence`

---

### M4.4 引用校验 + 低置信度降级

**Why**：002 §3 要求 citation 必须对得上 evidence index。

**改动**：
- `_build_chat_response` 在返回前做 `validate_citations(answer_text, evidence_count)`：匹配所有 `[N]`，确保 N ≤ evidence_count；否则剥离 `[N]` 标记
- 若 reranker top-1 score < 0.3，强制答案前置 "根据检索结果置信度较低，以下仅供参考："

**Acceptance**：
- 伪引用（`[99]` 超出范围）被自动剔除
- 低置信度回答有显式提示

**测试**：
- `test_citation_validator_strips_out_of_range`
- `test_low_confidence_prefix_added`

---

## 7. M5 — Web Search 整合

### M5.1 `WebSearchProvider` 接 chat 层

**Why**：目前 provider 已实现但 chat 层没用。M4.3 触发。

**改动**：
- `backend/deps.py::get_web_search_provider()` — 读 `SERPER_API_KEY` env
- 把 `E_LOW_CONFIDENCE` 分支接上

**Acceptance**：
- 返回 organic 前 5 条；title + snippet + link 拼成 Evidence（object_type="web"）
- 失败（429 / quota）降级到 "未查到相关结果"，不 500

**测试**：
- `test_web_search_provider_integration` — 实际命中 Serper（requires_api_key 标记）
- `test_web_search_quota_exceeded_graceful`

---

### M5.2 Web Search 结果的 rerank

**Why**：Serper 返回前 10 条，query→organic 的相关性可能不够，用 rerank 再洗一遍。

**改动**：
- `WebEvidenceBuilder` 把 10 条 organic 的 `title + snippet` 拼成 documents，调 `RerankerClient.rerank(query, docs, top_n=3)`
- 最终输出只保留 top-3

**Acceptance**：
- rerank 后 top-3 相关度明显优于 Serper 原始顺序（人工 spot check 10 条）

**测试**：`test_web_evidence_rerank_improves_order`

---

## 8. M6 — 画像反向增强

### M6.1 Paper 全文 → profile_summary 补强

**Why**：001 §3.5 说 `profile_summary` 只有 1 个 prof 有值。有了 M2 的 `paper_full_text` 后，可以跑 gemma4 综合生成。

**文件**（改）：
- `apps/miroflow-agent/src/data_agents/professor/summary_generator.py`

**改动**：
- `generate_profile_summary(prof, papers, full_texts)`：
  - 拼 prompt：prof 基本信息 + 代表 5-10 篇论文 title+abstract+intro
  - 调 gemma4 生成 200-400 字 profile_summary + research_directions (list)
  - 写回 Postgres `professor.profile_summary + research_directions`

**Acceptance**：
- 随机抽 20 个 prof，手工评估 summary 质量（相关性 + 事实性）≥ 80%
- 没 paper_full_text 的 prof 跳过，不报错

**测试**：
- `test_summary_generator_uses_full_text`
- `test_summary_generator_skips_when_no_papers`

---

### M6.2 Backfill 脚本

**文件**（新建）：
- `apps/miroflow-agent/scripts/run_profile_summary_backfill.py`

**Acceptance**：
- `--limit=50` 跑 50 个 prof
- 写 `logs/data_agents/professor/summary_backfill_runs.jsonl`
- 失败的 prof 进入 `pipeline_issue` 表（issue_type='summary_generation_failed'）

---

### M6.3 重新向量化（summary 改了就要更新 Milvus）

**改动**：
- `run_milvus_backfill.py --domain=professor` 支持 `--incremental`（只跑 profile_summary 有更新的 prof）

**Acceptance**：incremental run 5 分钟内完成 50 个 prof 的重嵌入。

---

## 9. 通用约束（所有 Milestone 适用）

### 9.1 代码规范
- 所有新模块遵循 `src/data_agents/` 目录约定
- 类型注解完整（`from __future__ import annotations` 开头）
- 没有 try/except Exception: pass
- 无 `print`，用 logging
- 没有硬编码 API key / URL（读 env 或 config）
- `ruff check` + `ruff format` 过

### 9.2 测试规范
- 每个 milestone 的 "测试" 小节列出的 case **必须全部实现**
- 单元测试用 `pytest`；requires external services 标 `@pytest.mark.integration`
- Mock httpx 用 `respx` 或 `MagicMock`
- 真 Milvus 测试用 Milvus-Lite (`milvus_uri=":memory:"`)

### 9.3 Git / PR 规范
- 一个 milestone = 一个 PR（commit 可多个但必须逻辑相关）
- Commit message 用本仓库的 conventional 格式：`feat(m2/homepage-ingest): ...` / `fix(identity-gate): ...`
- PR 描述带：goal / what changed / tests / acceptance check

### 9.4 回滚策略
- 新表（`professor_orcid`、`paper_full_text`）通过 alembic downgrade 可回滚
- 新 Milvus 集合可 `drop_collection` 清空（开发脚本）
- Feature flag：
  - `CHAT_USE_RETRIEVAL_SERVICE`（default off，切流量）
  - `PAPER_HOMEPAGE_INGEST_ENABLED`（default off）

---

## 9.5 性能注释（eng-review 决议）

| 里程碑 | 注意项 | 降级策略 |
|---|---|---|
| M0.1 | Reranker 100 docs TTFT 未实测；估 500-1500ms | 若 P50 > 1s → candidate_limit 降到 30 |
| M2.3 | arxiv 3s 限速 × 4000 篇 = ~3.3h 串行 | `asyncio`：arxiv/OpenAlex 两池独立调度；`--max-papers-per-hour` 节流 |
| M3.2 | 4 域 Milvus 并发 ANN | 用 `asyncio.gather()`；未达 1.5s budget 先调 candidate_limit |
| M4.3 | Serper free 2500/月 | 命中 cache 降低；超额退回 "本地证据不足" |

**M0.1 ship 后立即跑 benchmark**，结果写入 `docs/solutions/retrieval/qwen3-reranker-latency-2026-04.md`。

---

## 10. Parking Lot（明确推后）

- **多轮对话 L1 Session 升级**：当前 chat.py 已有 session cookie + entity stack，MVP 够用；深度代词消解（跨多轮）放到 M7
- **Agent Orchestrator L3 的工具链编排**：002 §4.3 的 step planner 暂不实现；M4 的 route handler 够用
- **微信公众号接入**：用户已明说优先级低
- **BGE-M3 引入**：Qwen3-Embedding-8B 够用；有 Chinese-English 跨语检索需求时再评估
- **pgvector 双写**：M0.4 已明确删除
- **专利 company_id 关联**：M2/M3 不做；专利只按 applicant/inventor 字符串匹配

---

## 11. 第一个 PR（M0.1 示范）

**标题**：`feat(providers/rerank): Qwen3-Reranker-8B client with trust_env=False`

**文件清单**：
```
A apps/miroflow-agent/src/data_agents/providers/rerank.py
A apps/miroflow-agent/tests/providers/__init__.py
A apps/miroflow-agent/tests/providers/test_rerank.py
M apps/miroflow-agent/src/data_agents/providers/__init__.py  (export RerankerClient)
```

**执行步骤**（CLAUDE.md Hybrid Flow）：
1. **Stage 1 /plan-ceo-review + /plan-eng-review**：审这份执行计划本身，锁定 M0-M6 优先级
2. **Stage 2 /ce:plan**：把 M0.1 拆成 4 个子步骤（write test → run RED → impl → run GREEN）
3. **Stage 3 /superpowers:test-driven-development**：写 4 个测试，跑 RED
4. **Stage 3 /codex**：委派 codex 写 impl
5. **Stage 4 交叉验证**：Claude Code 读 codex 产出的 `rerank.py`，对照本文 M0.1 接口定义逐行校验；类型注解 / trust_env / 空文档分支 / 错误消息都要对齐
6. **Stage 4 /ce:review**：多 agent 查 N+1、信任边界、并发
7. **Stage 5 /ce:compound**：如果有踩到坑，记入 `docs/solutions/providers/rerank-client-pitfalls.md`

---

## 12. 交叉引用

| 需求来源 | 执行计划对应 |
|---|---|
| 001 §4.2 Identity Gate 47% 误拒 | M1 整块 |
| 001 §4.4 Pipeline Inversion | M2 整块 |
| 001 §5 prof profile_summary 缺失 | M6 整块 |
| 001 §6 Roadmap Sprint 1 | M0 + M1 + M2 |
| 001 §6 Roadmap Sprint 2 | M3 + M4 |
| 001 §6 Roadmap Sprint 3 | M5 + M6 |
| 002 §0 技术栈 pgvector | **被 M0.4 废弃，改用现有 Milvus** |
| 002 §2 Homepage-Authoritative | M2.1-M2.4 |
| 002 §3 Identity Gate v2 | M1.1-M1.4 |
| 002 §4 L5 Context Packer | M3.2 RetrievalService |
| 002 §5 Web Search | M5 |
| 002 §6 Profile Reinforcement | M6 |

---

## 13. Open Questions

1. **Q**：Milvus 是单节点 Milvus-Lite 还是 standalone？<br>**A**：目前开发用 Lite（dep 里有 `milvus-lite`），生产 TBD。不影响 schema 设计。

2. **Q**：Qwen3-Embedding-8B 的 context window 是多少？paper chunk 要怎么切？<br>**A**：API 侧未限制；模型侧 8K token。策略：title 不切、abstract ≤ 500 字不切、intro > 500 字按 `。\n` 切 3 段，每段独立 embed。

3. **Q**：Reranker 的 latency？<br>**A**：需要 M0.1 完成后 benchmark；初步估计 100 candidates 约 800ms。若过慢，退化为只 rerank top-20。

4. **Q**：ORCID backfill 数据源？<br>**A**：OpenAlex author page 有 `display_name` 和 `orcid`；通过 `author_id_picker` 已经在用的逻辑扩展。

---

## 14. 进度追踪

使用本仓库的 `_bmad/bmm` + 自定义 journal：
- 每个 milestone 完成后更新 `docs/plans/2026-04-20-003-progress.md`（每日一次）
- 关键阻塞 → `docs/solutions/<category>/` 写经验帖

---

## 15. 下一步

**立刻**：执行 Stage 1 — ~~`/plan-ceo-review`~~（已跳过）+ `/plan-eng-review` 审本文，锁定 M0-M6 边界与优先级。

**审批过了**：开始 M0.1 — Reranker 客户端的 TDD 红绿循环（预计 1 小时 CC）。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | skipped | user skipped |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 9 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**Step 0 Scope Challenge (applied)**：
- Confirmed existing code reuse: vectorizer.py (Qwen3-Embedding-8B + Milvus), WebSearchProvider (Serper), llm_profiles.gemma4 resolver, paper_identity_gate (LLM path wired), paper/orcid.py
- Plan error caught: pypinyin is **not** in deps — M1.1 updated to add it
- Complexity: 30+ new files / 10+ new classes across 7 milestones — accepted because each milestone = 1 PR

**Decisions resolved (3/3)**：
1. **M1 ↔ M2 order**: **M2 first**, M1 deferred to after M2 coverage analysis
2. **Retrieval service location**: `apps/miroflow-agent/src/data_agents/service/retrieval.py` (core), `backend/deps.py` injects, optional thin adapter in `backend/chat/`
3. **V011 collision**: single V011 migration creating 3 tables: `professor_orcid` + `paper_full_text` + `paper_title_resolution_cache` (Q2 also added a title-cache table)

**Architecture findings** (6):
- A1 pypinyin dep — **APPLIED** to M1.1
- A2 M1/M2 overlap — **RESOLVED** (M2 first)
- A3 V011 collision — **RESOLVED** (merged)
- A4 Retrieval service location — **RESOLVED** (miroflow-agent/service/)
- A5 4-way Milvus collections — Accepted, noted
- A6 paper_identity_gate still needed for non-homepage — **APPLIED** doc clarification

**Code quality findings** (3):
- Q1 httpx standardization — **APPLIED** new M0.5 milestone
- Q2 title resolution cache — **APPLIED** new table in V011
- Q3 M1.2 prompt bloat — Accepted, minor cost

**Test findings**: 20 test gaps across M0-M6, all listed per milestone. **CRITICAL added**: regression-test-first rule for M1.2 (xfail → fix → green).

**Performance findings** (3): All have mitigations in new §9.5. M0.1 ships benchmark script to `docs/solutions/retrieval/` on completion.

**NOT in scope** (deferred, in Parking Lot):
- 多轮对话 L1 深度代词消解 (current MVP is good enough)
- Agent Orchestrator L3 step planner
- 微信公众号接入
- BGE-M3 (Qwen3-Embedding-8B suffices)
- pgvector double-write (M0.4 kill)
- 专利 company_id 关联

**What already exists** (reused in plan):
- `vectorizer.py::EmbeddingClient` (M0.3 extends, not rewrites)
- `providers/web_search.py::WebSearchProvider` (M5.1 reuses, M0.5 ports to httpx)
- `llm_profiles::resolve_professor_llm_settings("gemma4")` (chat.py already uses)
- `paper/orcid.py` (M1.3 extends)
- `name_utils.py` (M1.1 complements with CJK→pinyin)
- `chat.py` v3.1 classifier (M4.x extends B/D/E handlers)

**Worktree parallelization strategy**：

| Lane | Milestones | Modules | Notes |
|---|---|---|---|
| A | M0 → M2 → M1 | providers/, paper/, professor/ | Critical path. Sequential. |
| B | M3 (parallel w/ M2 tail) | storage/, service/ | Only depends on M0. |
| C | M4 (after M3) | backend/chat/ | Depends on B. |
| D | M5 (after M0) | backend/chat/, providers/web_search | Independent of A/B/C for core logic |
| E | M6 (after M2) | professor/summary_generator | Only depends on A. |

Lane A is mandatory serial (data agent chain). B/D can start in parallel after M0 lands. C merges after B. E merges after A.

**Failure modes flagged**:
- **Critical gap: none**. All new codepaths have tests + error handling in plan.
- Watch items: Qwen3-Reranker latency (M0.1 benchmark), arxiv rate limiting (M2.3 async), Serper free tier (M4.3 cache miss mitigation).

**Outside voice**: Skipped (user requested speed). Can be invoked later via `/codex review`.

**Unresolved decisions**: 0.

**VERDICT**: **ENG CLEARED — ready to implement**. All issues resolved or noted. Start with M0.1 (Reranker client TDD loop).
