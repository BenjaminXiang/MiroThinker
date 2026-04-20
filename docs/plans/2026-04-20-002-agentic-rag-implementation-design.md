---
title: Agentic RAG 技术实现设计（落地蓝本）
date: 2026-04-20
status: active
owner: claude (technical research mode)
extends:
  - docs/plans/2026-04-20-001-system-capability-audit-and-agentic-rag-gaps.md
origin:
  - docs/Agentic-RAG-PRD.md
  - docs/Professor-Data-Agent-PRD.md
  - 实测 miroflow_real DB (2026-04-20)
  - Web 研究：OpenAlex / arxiv / Serper / pgvector 技术选型
---

# Agentic RAG 技术实现设计（落地蓝本）

> 本文档是 `2026-04-20-001` 审计文档的**技术配套**。审计讲 *做什么、为什么*，本文讲 *怎么实现*——表结构、API 调用、算法、模块边界、验收标准。
>
> 目标读者：接下来要动手写代码的人（Claude / Codex subagent / 人）。
>
> 原则：**每个技术选型都有引用 + 权衡理由 + 回退方案**，避免"凭感觉决定"。

## 0. 技术栈总览

| 层 | 技术选型 | 选型理由 |
|---|---|---|
| DB | PostgreSQL 16 + pgvector | 已有。规模 < 5M 向量时 pgvector 足够，零新运维 |
| HTTP | httpx (sync + async) | 已有。`trust_env=False` 避免代理污染 |
| HTML | BeautifulSoup + lxml | 已有。`selectolax` 不要（之前踩过 deps 坑）|
| PDF | pdfminer-six | 已有，dep 里 |
| LLM | gemma4 (local) + gpt-4o (fallback) | 已有 `llm_profiles.resolve_professor_llm_settings` |
| Web Search | Serper.dev | $0.3-1/1k，速度 1.8s，free 2500 searches（[参考](https://scrapfly.io/blog/posts/google-serp-api-and-alternatives)） |
| Paper 元数据 | OpenAlex > Semantic Scholar > arXiv（三级 fallback）| 前两者免费无鉴权；arXiv 作为全文源 |
| Embedding | BGE-M3 via sentence-transformers（本地）| 中英双语 SOTA |
| Queue | 无（同步脚本）→ 未来 Redis Streams | 当前数据规模无需 |

---

## 1. 目标架构 L0–L7 细化

> 审计文档 §3.2 给了分层图。本节给每一层的**接口签名 + 输入输出 schema + 文件位置**。

### L0. 入口层

```python
# apps/admin-console/backend/api/chat.py
@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, session_id: str = Cookie(...), conn = Depends(...)) -> ChatResponse:
    agent = ChatAgent(conn=conn, session_store=session_store)
    return agent.run(payload.query, session_id)
```

**单一职责**：HTTP 编解码 + cookie + 调 Agent。当前 chat.py 1100 行 →  目标 **< 80 行**。

### L1. Session Manager

**模块** `apps/admin-console/backend/chat/session.py`（**新**）

```python
@dataclass
class Entity:
    kind: Literal["professor", "company", "paper", "patent"]
    id: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    pinned_at: float = 0.0

class SessionContext:
    session_id: str
    entities: deque[Entity]         # maxlen=10, 多类型
    turns: deque[Turn]              # maxlen=10
    last_topic: str | None          # 话题边界检测用
    def latest(self, kind: str) -> Entity | None: ...
    def on_topic_switch(self, new_topic: str) -> bool: ...  # 返回 True 表示切换
```

**话题切换检测启发式**（规则优先，LLM 兜底）：
- 新 query 没有代词 AND 新 topic 与 last_topic 无词重叠 → 切换
- 显式关键词："新问题" / "换个话题" / "另外" → 强切换
- 切换时清空 entities stack，保留 turns

### L2. Query Understanding

**模块** `apps/admin-console/backend/chat/query_understanding.py`（**新**）

```python
@dataclass
class ParsedQuery:
    original: str
    rewritten: str                  # 经代词消解/别名归一后的版本
    intent: Literal["A","B","C","D","E","F","G","UNKNOWN"]
    entities: dict[str, str]        # {"name": "丁文伯", "institution": "清华", ...}
    slots: dict[str, Any]           # {"filter_city": "深圳", "year_range": (2020,2024)}
    ambiguous: bool
    confidence: float
    rewrite_reason: str             # 可解释性

class QueryUnderstanding:
    def parse(self, query: str, session: SessionContext) -> ParsedQuery:
        # Step 1: 代词消解（规则）
        rewritten, rewrite_reason = self._resolve_pronouns(query, session)
        # Step 2: 别名归一（机构/公司别名表 + LLM 兜底）
        rewritten = self._normalize_aliases(rewritten)
        # Step 3: LLM 一次调用抽出 intent + entities + slots
        parsed = self._llm_parse(rewritten, session.summarize_turns())
        # Step 4: 歧义检测（同名 prof/company 多个）
        parsed.ambiguous = self._detect_ambiguity(parsed)
        return parsed
```

**LLM parse prompt 设计**（对比当前一次只返回 type+topic，这里一次拿齐所有槽位）：

```json
{
  "intent": "A|B|C|D|E|F|G",
  "entities": {
    "name": "丁文伯",           // 教授名或公司名
    "institution": "清华",      // 限定机构（粗粒度，后续别名表归一）
    "company": "",
    "paper_title": "",
    "patent_number": ""
  },
  "slots": {
    "filter_city": "深圳",      // 地域过滤
    "filter_role": "企业家",     // 身份过滤
    "education_school": "早稻田",// 毕业学校（Q13 关键）
    "year_range": null,
    "industry": "机器人",
    "must_include": ["技术路线"],
    "tone": "summary"            // 或 "list" / "detail"
  },
  "confidence": 0.92,
  "reasoning": "用户问深圳的、机器人行业的、毕业早稻田的企业家——这是复合过滤"
}
```

**关键点**：一次 LLM 调用搞定 intent + slot filling。当前版本的 classifier 只返回 `{type, topic, name}`，丢失了大量信息。

### L3. Agent Orchestrator（**核心新增**）

**模块** `apps/admin-console/backend/chat/orchestrator.py`（**新**）

```python
@dataclass
class Plan:
    sub_tasks: list[SubTask]    # 顺序或并行
    max_steps: int = 3          # 反思上限
    fallback_to_web: bool = False

@dataclass
class SubTask:
    tool: Literal["db_lookup", "db_filter", "hybrid_search", "web_search", "paper_fulltext", "rerank"]
    args: dict[str, Any]
    depends_on: list[int] = field(default_factory=list)

class AgentOrchestrator:
    def run(self, parsed: ParsedQuery, session: SessionContext) -> ChatResponse:
        plan = self._plan(parsed)                      # LLM 生成 Plan
        context = ExecutionContext()
        for step in range(plan.max_steps):
            results = self._execute_plan(plan, context)
            if self._sufficient(results, parsed):      # 结果够 → 出结果
                break
            plan = self._refine(plan, results, parsed) # 不够 → 扩大/换工具
        return self._synthesize(results, parsed, session)
```

**Planning heuristic（不需要超强 LLM）**：

```python
def _plan_rules(parsed: ParsedQuery) -> Plan:
    if parsed.intent == "A" and parsed.entities.get("name"):
        return Plan([SubTask("db_lookup", {...})])
    if parsed.intent == "B":
        return Plan([SubTask("hybrid_search", {...})], fallback_to_web=True)
    if parsed.intent == "D":
        return Plan([
            SubTask("db_filter", {"domain":"professor", ...}),
            SubTask("db_filter", {"domain":"company", ...}),
            SubTask("db_filter", {"domain":"patent", ...}),
            SubTask("rerank", {...}, depends_on=[0,1,2]),
        ])
    if parsed.intent == "E":
        return Plan([
            SubTask("web_search", {...}),
            SubTask("paper_fulltext", {...}),  # 若查本地论文库能补则用
        ])
    if parsed.intent == "G":
        return Plan([SubTask("db_lookup", {...})])  # 多结果 → ambiguous response
    # UNKNOWN 或复合：用 LLM planner
    return self._llm_plan(parsed)
```

**反思策略**：
- `db_lookup` 返回 0 行 AND `intent in (A, B)` → 加 `web_search` 子任务
- `hybrid_search` 返回 < 3 行 → 降低过滤条件重跑
- `web_search` 返回噪声 → 加 `paper_fulltext` 约束

### L4. Tools

#### L4a. DB Tools (`apps/admin-console/backend/chat/tools/db.py`)

已有查询逻辑从 chat.py 抽出来：
```python
class DbTool:
    def lookup_professor(self, *, name, institution=None, name_en=None) -> list[Prof]: ...
    def search_professor_by_topic(self, topic, institutions=None) -> list[Prof]: ...
    def lookup_company(self, *, name=None, fuzzy=False) -> list[Company]: ...
    def search_company_by_industry(self, industry, filters=None) -> list[Company]: ...
    def lookup_paper(self, *, title=None, doi=None, arxiv_id=None) -> list[Paper]: ...
    def lookup_patent(self, *, patent_number=None, applicant=None) -> list[Patent]: ...
    def fetch_prof_papers(self, prof_id, link_status='verified', limit=20) -> list[Paper]: ...
```

#### L4b. Hybrid Retrieval (`.../chat/tools/hybrid.py`)

```python
class HybridRetriever:
    def __init__(self, conn, embedder: Embedder):
        self.conn = conn
        self.embedder = embedder      # BGE-M3

    def search(self, query: str, domain: str, k: int = 20) -> list[RetrievalHit]:
        # Step 1: BM25 via Postgres tsvector
        bm25_hits = self._bm25_search(query, domain, k*3)
        # Step 2: Embedding via pgvector
        query_vec = self.embedder.encode(query)
        vec_hits = self._vector_search(query_vec, domain, k*3)
        # Step 3: Reciprocal Rank Fusion (RRF)
        fused = self._rrf(bm25_hits, vec_hits, k=60)
        # Step 4: Cross-encoder rerank top 20
        return self._rerank(query, fused[:k*2])[:k]
```

Schema（pgvector 新增）：
```sql
ALTER TABLE professor ADD COLUMN search_vector vector(1024);    -- BGE-M3 dim
ALTER TABLE company ADD COLUMN search_vector vector(1024);
ALTER TABLE paper ADD COLUMN search_vector vector(1024);

CREATE INDEX idx_prof_vec ON professor USING hnsw (search_vector vector_cosine_ops);
CREATE INDEX idx_company_vec ON company USING hnsw (search_vector vector_cosine_ops);
CREATE INDEX idx_paper_vec ON paper USING hnsw (search_vector vector_cosine_ops);
```

**规模评估**：~800 prof + ~1000 company + ~7k paper ≈ 9k 向量 × 1024 dim × 4 byte ≈ 37 MB —— pgvector 完全 carry 住（pgvector 实用区间到 5M 向量，[source](https://medium.com/@vhrechukha/i-spent-a-week-researching-what-to-use-instead-of-pgvector-heres-the-honest-answer-d6a2ce0a0613)）。

#### L4c. Web Search Tool (`.../chat/tools/web.py`)

```python
class WebSearchTool:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.Client(
            base_url="https://google.serper.dev",
            headers={"X-API-KEY": api_key},
            timeout=10.0,
            trust_env=False,   # 用户明确要求不走代理
        )

    def search(self, query: str, num: int = 10) -> list[WebHit]:
        resp = self.client.post("/search", json={"q": query, "num": num, "hl": "zh"})
        return [WebHit(**r) for r in resp.json()["organic"]]

    def fetch_page(self, url: str) -> str | None:
        """用 httpx + BeautifulSoup 获取正文，用于 E 类深度引用"""
        ...
```

**Serper 选择理由**（[参考](https://scrapfly.io/blog/posts/google-serp-api-and-alternatives)）：
- $0.30-1.00/1k queries，free 2500
- 1.8s 平均延迟
- 返回 Google 搜索结果（对中文支持好于 DDG）
- 回退：Brave Search API ($3-5/1k, 2000 free)，完全独立索引

**环境变量**：`SERPER_API_KEY=xxx`。无 key 时 WebSearchTool 抛 `WebSearchUnavailable`，Agent Orchestrator 降级回 DB-only。

#### L4d. Paper Fulltext Tool (`.../chat/tools/paper_fulltext.py`)

```python
class PaperFulltextTool:
    def get(self, paper_id: str) -> str | None:
        """读 paper_full_text 表的 arxiv 全文，供 E 类 + profile reinforcement 用"""
        row = self.conn.execute(
            "SELECT plaintext FROM paper_full_text WHERE paper_id = %s",
            (paper_id,),
        ).fetchone()
        return row["plaintext"] if row else None

    def search_by_topic(self, topic: str, k: int = 5) -> list[tuple[str, str]]:
        """通过 pgvector 查相关全文段落 —— E 类问答深度依据"""
        ...
```

### L5. Context Packer + Reranker

```python
class ContextPacker:
    def pack(
        self,
        retrieval_hits: list[RetrievalHit],
        web_hits: list[WebHit],
        paper_chunks: list[PaperChunk],
    ) -> tuple[str, dict[str, str]]:
        # Step 1: Dedup by id
        # Step 2: Rerank by information gain (cross-encoder or heuristic)
        # Step 3: Truncate to fit in LLM context window (gemma4 = 32k)
        # Step 4: Assign [N] citation markers
        return (evidence_text, citation_map)
```

### L6. Answer Synthesizer

已有（chat.py 中的 `_call_gemma_synthesis`）。**改动**：
- Prompt 模板从 intent 决定：A/B/D/E/G 各有适配的 prompt
- 加 **幻觉检测**：正则 `\[(\d+)\]` 抓所有 marker → 每个 claim sentence 必须引用；无引用的句子打红旗

### L7. Response Shaper

```python
class ResponseShaper:
    def shape(self, synth: SynthesisResult, plan: Plan, parsed: ParsedQuery) -> ChatResponse:
        return ChatResponse(
            query=parsed.original,
            query_type=f"{parsed.intent}_{plan.label}",
            answer_text=synth.text,
            citations=synth.citations,
            structured_payload=synth.payload,
            answer_style=synth.style,
            citation_map=synth.citation_map,
            # 新增：追问引导
            follow_up_suggestions=self._suggest_followups(parsed, synth),
        )

    def _suggest_followups(self, parsed, synth):
        """根据 intent 生成 3 个可能的下一问"""
        if parsed.intent == "A" and "professor" in synth.payload:
            return [
                f"他的论文",
                f"他参与创立的公司",
                f"{parsed.entities['institution']}还有哪些做{parsed.slots.get('industry', '相关')}的教授",
            ]
        ...
```

---

## 2. Paper Ingest — Homepage-Authoritative 管线

### 2.1 HTML 抽取设计

**模块** `apps/miroflow-agent/src/data_agents/paper/homepage_publications.py`（**新**）

```python
# 锚点识别：中英文双语 + 常见变体
_PUBLICATION_ANCHORS = [
    # 英文
    r"Publications?\b", r"Selected Publications",
    r"Journal Articles?", r"Conference Papers",
    r"Recent Publications", r"Publication List",
    r"Papers\b", r"Research Papers",
    # 中文
    r"论文\b", r"学术论文", r"代表性论文",
    r"主要论文", r"发表论文", r"学术成果",
    r"期刊论文", r"会议论文", r"近年论文",
    r"代表作", r"研究成果",
]
_PUB_ANCHOR_RE = re.compile("|".join(_PUBLICATION_ANCHORS), re.IGNORECASE)

def extract_publications_section(soup: BeautifulSoup) -> list[RawPublication]:
    """
    策略:
      1. 找到所有包含 publication 锚点的 h1-h4 / div.title / strong 节点
      2. 从锚点起收集到下一个同级 heading 或 section 结束
      3. 在该区块内识别"论文条目":
         - <li> / <p> / <div.paper-item>
         - 以数字编号开头: "1. ", "[1]", "(1)", "①"
         - 包含年份 YYYY 或期刊名模式
      4. 对每条提取标题（通常最长的引用/斜体块，或以 "." 结尾前的主体）
    """
    candidates = []
    for anchor in _find_anchors(soup):
        section = _collect_section_body(anchor)
        for item_node in _iter_item_nodes(section):
            title = _extract_title(item_node)
            if title and len(title) >= 10:
                candidates.append(RawPublication(
                    title_raw=title,
                    full_citation=item_node.get_text(" ", strip=True),
                    year_hint=_extract_year(item_node),
                    venue_hint=_extract_venue(item_node),
                    source_anchor=anchor.get_text(" ", strip=True),
                ))
    return _dedup_by_title(candidates)
```

### 2.2 标题清洗（编码 / HTML entity / Unicode）

```python
def clean_title(raw: str) -> str:
    """Normalize a scraped title — user explicitly flagged encoding cleanup."""
    if not raw:
        return ""
    # 1. HTML entities: &nbsp; &amp; &quot; ...
    cleaned = html.unescape(raw)
    # 2. Unicode NFC normalize
    cleaned = unicodedata.normalize("NFC", cleaned)
    # 3. UTF-8 误读 Latin-1 的典型 mojibake
    if any(marker in cleaned for marker in ("â€", "Ã¤", "Ã©", "â‚¬")):
        try:
            cleaned = cleaned.encode("latin-1").decode("utf-8")
        except UnicodeDecodeError:
            pass
    # 4. 空白规范
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 5. 去除前后残留标点
    cleaned = cleaned.strip(".,;:!? \"'")
    # 6. 剥离前缀编号
    cleaned = re.sub(r"^\s*(?:\[?\d+\]?|\(\d+\)|[①-⑳])[\.、\)]?\s*", "", cleaned)
    return cleaned
```

### 2.3 Title → 权威元数据（三级 fallback）

**模块** `apps/miroflow-agent/src/data_agents/paper/title_resolver.py`（**新**）

```python
@dataclass
class ResolvedPaper:
    title_clean: str
    authors_display: str | None
    year: int | None
    venue: str | None
    abstract: str | None
    doi: str | None
    openalex_id: str | None
    semantic_scholar_id: str | None
    arxiv_id: str | None
    citation_count: int | None
    source: Literal["openalex", "semantic_scholar", "arxiv", "none"]
    confidence: float   # 标题相似度 + 作者 intersect 验证

class TitleResolver:
    def resolve(self, raw_title: str, hint_author: str | None = None,
                hint_year: int | None = None) -> ResolvedPaper:
        """
        三级 fallback：
            1. OpenAlex: 覆盖最广，免费无 auth
            2. Semantic Scholar: OpenAlex miss 时补
            3. arXiv: 最后 fallback + 全文源
        """
        for source in ["openalex", "semantic_scholar", "arxiv"]:
            result = self._query_source(source, raw_title, hint_author, hint_year)
            if result and result.confidence >= 0.85:
                return result
        return ResolvedPaper(title_clean=raw_title, source="none", confidence=0.0)

    def _query_openalex(self, title: str, hint_author, hint_year) -> ResolvedPaper | None:
        """
        https://api.openalex.org/works?search="<title>"
        Doc: https://docs.openalex.org/api-entities/works/search-works
        Rate limit: 10/sec polite; 100k/day free
        """
        resp = httpx.get(
            "https://api.openalex.org/works",
            params={"search": f'"{title}"', "per_page": 5},
            timeout=10.0, trust_env=False,
            headers={"User-Agent": "MiroThinker/1.0 (mailto:admin@example.com)"},
        )
        data = resp.json()["results"]
        # 验证：标题 Jaccard ≥ 0.8，若有作者/年份提示进一步校验
        for hit in data:
            conf = _title_similarity(title, hit["title"])
            if hint_author and hint_author.lower() not in str(hit["authorships"]).lower():
                conf *= 0.7
            if hint_year and hit.get("publication_year") != hint_year:
                conf *= 0.8
            if conf >= 0.85:
                return _normalize_openalex(hit, conf)
        return None

    def _query_arxiv(self, title: str, hint_author, hint_year) -> ResolvedPaper | None:
        """
        http://export.arxiv.org/api/query?search_query=ti:"<title>"
        Rate limit: 1 req / 3s (强制)
        Doc: https://info.arxiv.org/help/api/user-manual.html
        """
        with _arxiv_rate_limiter:  # 全局 3s 节流
            resp = httpx.get(
                "http://export.arxiv.org/api/query",
                params={"search_query": f'ti:"{title}"', "max_results": 5},
                timeout=15.0, trust_env=False,
            )
        entries = _parse_atom(resp.text)
        ...
```

**Rate limit 合规性**：
- arXiv 官方规定 **1 req / 3s**（[arXiv TOU](https://info.arxiv.org/help/api/tou.html)）→ 全局 threading.Lock + time.sleep(3) 严格节流
- OpenAlex 建议 10 req/s，加 `mailto:` header 获"polite pool"
- Semantic Scholar 免费 tier 100 req / 5min，可加 api-key 拿 1000

### 2.4 arXiv 全文入库

**新表** `paper_full_text`：

```sql
-- V011 migration
CREATE TABLE paper_full_text (
    paper_id       text PRIMARY KEY REFERENCES paper(paper_id) ON DELETE CASCADE,
    arxiv_id       text,
    source_url     text NOT NULL,
    plaintext      text NOT NULL,
    abstract       text,
    char_length    int  GENERATED ALWAYS AS (char_length(plaintext)) STORED,
    pdf_sha256     text,
    fetched_at     timestamptz NOT NULL DEFAULT now(),
    run_id         uuid REFERENCES pipeline_run(run_id) ON DELETE SET NULL,
    CONSTRAINT ck_paper_full_text_nonempty CHECK (char_length(plaintext) > 500)
);
CREATE INDEX idx_paper_full_text_arxiv ON paper_full_text (arxiv_id);
-- 全文检索（Postgres tsvector）
ALTER TABLE paper_full_text
    ADD COLUMN search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', plaintext)) STORED;
CREATE INDEX idx_paper_full_text_tsv ON paper_full_text USING gin(search_tsv);
```

**抓取脚本** `scripts/run_arxiv_fulltext_backfill.py`（**新**）：

```python
# 流程：
#  1. 选 paper WHERE arxiv_id IS NOT NULL AND NOT EXISTS (paper_full_text)
#  2. 按 arxiv API 的 3s 节流下载 PDF
#  3. pdfminer 抽文本 → 清理 (去参考文献 / 去页眉页脚)
#  4. sha256 去重
#  5. 写 paper_full_text，设 run_id
```

**预估**：假设 homepage Publications 抽出 5000 篇论文，arxiv 命中率 30-40% → **1500-2000 篇全文入库**。下载 + 抽文 总耗时 ~2h（主要受 3s 节流限制）。

### 2.5 整合入库流程

```
homepage URL
  ├→ httpx GET (no proxy, trust_env=False)
  ├→ BeautifulSoup(html, "lxml")
  ├→ extract_publications_section()   [L2.1]
  ├→ for each raw_pub:
  │    ├→ clean_title()                [L2.2]
  │    ├→ TitleResolver.resolve()      [L2.3]
  │    ├→ if arxiv_id:
  │    │    └→ download PDF + extract text → paper_full_text  [L2.4]
  │    └→ upsert_paper(...) + upsert_paper_link(
  │           professor_id=X,
  │           link_status='verified',         # 不走 gate!
  │           evidence_source_type='homepage_publication_list',
  │           author_name_match_score=1.00,
  │           is_officially_listed=true)
  └→ file pipeline_issue for "miss" (title resolver 找不到)
```

---

## 3. Identity Gate v2（fallback 路径加固）

### 3.1 双语 + ORCID 调用签名

```python
# apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py

@dataclass(frozen=True, slots=True)
class ProfessorContext:
    professor_id: str
    name_zh: str                    # 当前 'name'
    name_en: str | None
    name_pinyin: list[str]          # ["Jianquan Yao", "Yao Jianquan"] 自动生成
    orcid: str | None
    institution: str
    institution_aliases: list[str]  # 已有 institution_registry 可复用
    research_directions: list[str]

def _build_professor_context(conn, prof_id: str) -> ProfessorContext:
    ...
    # 自动派生 pinyin 变体
    pinyin_variants = _cjk_to_pinyin_variants(prof_row["canonical_name"])
    return ProfessorContext(..., name_pinyin=pinyin_variants, ...)
```

### 3.2 LLM Prompt 改造

```python
_BATCH_GATE_PROMPT = """
你是学术身份验证助手。判断下列论文是否属于目标教授。

# 目标教授
- 中文名: {name_zh}
- 英文名: {name_en}
- 拼音变体: {name_pinyin}（作者列表里可能出现的写法，如 "Jianquan Yao"、"J. Yao"、"Yao J."）
- 机构: {institution}（别名: {institution_aliases}）
- ORCID: {orcid}
- 研究方向: {research_directions}

# 候选论文
{candidates_rendered}

# 判断规则（重要）
1. 首选信号：若 candidate.authors_raw 中含匹配的 ORCID → 直接 is_same_person=true, confidence=1.0
2. 次选信号：作者列表含任一拼音变体（大小写无关、缩写兼容 "J.Q. Yao" = "Jianquan Yao"）→ confidence >= 0.9
3. 机构亲和：作者 affiliation 含 institution 或其别名 → +0.1 confidence
4. 主题一致：topic_consistency 独立打分（0-1）
5. **特别注意**：不要因为"作者列表没有中文名"就拒绝——英文作者串匹配拼音就够了
"""
```

### 3.3 ORCID 集成

**新增 professor 字段**：

```sql
-- V012 (part of V011 group)
ALTER TABLE professor ADD COLUMN orcid text;
CREATE INDEX idx_prof_orcid ON professor (orcid) WHERE orcid IS NOT NULL;
```

**抓取**：ORCID 通常在教授主页某处出现（`orcid.org/0000-0001-...` pattern）。homepage rescrape 重扫时用正则 `\b\d{4}-\d{4}-\d{4}-\d{4}\b` 提取。

**使用**：gate v2 一旦看到候选 paper 的 `authors_raw` 含任一作者的 `orcid = prof.orcid` → 瞬间 verify。这是**最强证据**，覆盖大多数理工科教授。

### 3.4 拼音变体生成

```python
# 已有 pypinyin 或 可加 dragonmapper
from pypinyin import lazy_pinyin, Style

def _cjk_to_pinyin_variants(name_zh: str) -> list[str]:
    if not re.search(r"[\u4e00-\u9fff]", name_zh):
        return []
    parts = lazy_pinyin(name_zh, style=Style.NORMAL)
    # 三字名: surname + given(2)
    if len(parts) == 3:
        surname, given = parts[0], "".join(parts[1:])
    elif len(parts) == 2:
        surname, given = parts
    else:
        return ["".join(parts).title()]
    cap_surname = surname.capitalize()
    cap_given = given.capitalize()
    return [
        f"{cap_given} {cap_surname}",           # "Jianquan Yao" (Western order)
        f"{cap_surname} {cap_given}",            # "Yao Jianquan" (Chinese order)
        f"{cap_given[0]}. {cap_surname}",        # "J. Yao"
        f"{cap_given[0]}.{cap_given[1] if len(cap_given)>1 else ''} {cap_surname}",
        f"{cap_surname}, {cap_given}",          # citation format
        f"{cap_surname}, {cap_given[0]}.",
    ]
```

---

## 4. Web Search 工具（Serper.dev）

### 4.1 API 调用封装

```python
# apps/admin-console/backend/chat/tools/web_search.py
import httpx
from pydantic import BaseModel

class SerperHit(BaseModel):
    title: str
    link: str
    snippet: str
    position: int
    date: str | None = None

class WebSearchTool:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise WebSearchUnavailable("SERPER_API_KEY not set")
        self._client = httpx.Client(
            base_url="https://google.serper.dev",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            timeout=10.0,
            trust_env=False,  # 不走代理（用户要求）
        )

    def search(self, query: str, *, num: int = 10, country: str = "cn",
               hl: str = "zh-cn") -> list[SerperHit]:
        resp = self._client.post("/search", json={
            "q": query, "num": num, "gl": country, "hl": hl,
        })
        resp.raise_for_status()
        data = resp.json()
        return [SerperHit(**h) for h in data.get("organic", [])]

    def fetch_page_text(self, url: str, max_chars: int = 8000) -> str | None:
        """抓取并抽取正文 — 供 E 类答案引用"""
        try:
            r = httpx.get(url, timeout=10.0, trust_env=False,
                          headers={"User-Agent": "Mozilla/5.0 MiroThinker"})
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "lxml")
            # 移除脚本/样式
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())
            return text[:max_chars]
        except Exception:
            return None
```

### 4.2 Rate limit + 缓存策略

```python
# 避免同一 query 重复调用
_WEB_SEARCH_CACHE_TTL = 60 * 60 * 24   # 1 day

class CachedWebSearchTool(WebSearchTool):
    def search(self, query: str, **kwargs) -> list[SerperHit]:
        cache_key = f"websearch:{hashlib.sha256(query.encode()).hexdigest()}"
        cached = self._cache.get(cache_key)
        if cached and cached["expires_at"] > time.time():
            return [SerperHit(**h) for h in cached["hits"]]
        hits = super().search(query, **kwargs)
        self._cache.set(cache_key, {
            "hits": [h.dict() for h in hits],
            "expires_at": time.time() + _WEB_SEARCH_CACHE_TTL,
        })
        return hits
```

简单起见，cache 用 `pipeline_issue` 或新建 `web_search_cache` 表；生产可升级 Redis。

### 4.3 配额管理

- 开发期：Serper 2500 free / month → 够用
- 生产：假设 100 QPS 峰值 × 20% 走 web fallback = 20 search/s = 1.7M/day → 需 paid tier ($300/mo)
- **配额 hit 兜底**：降级到 LLM-only 回答 + "LLM 推理，未补充 Web 搜索"

---

## 5. Query Rewriter + NER

### 5.1 代词消解（规则）

```python
_PRONOUN_PATTERNS = [
    (re.compile(r"他的|她的|这位(教授|老师|学者)的"),
     lambda session: f"{session.latest('professor').label}的"),
    (re.compile(r"这家(公司|企业)的"),
     lambda session: f"{session.latest('company').label}的"),
    (re.compile(r"这篇论文|这论文|该论文|上述论文"),
     lambda session: f"《{session.latest('paper').label}》"),
    (re.compile(r"上述企业|上面(的)?企业|那些公司"),
     lambda session: "|".join(e.label for e in session.recent_entities("company"))),
]
```

### 5.2 别名归一化

```python
class AliasNormalizer:
    """把 '智航无界' 归一到 '无界智航'（若两个变体都是已知公司候选），或加入模糊匹配候选"""
    def __init__(self, conn):
        self.conn = conn
        self.company_aliases = self._load_company_aliases()  # 缓存
        self.institution_aliases = INSTITUTION_ALIASES      # 已有

    def normalize(self, query: str) -> tuple[str, list[Substitution]]:
        subs = []
        # 用 pg_trgm 模糊匹配公司名
        for match in _COMPANY_NAME_MENTION_RE.finditer(query):
            candidates = self._find_fuzzy_company(match.group())
            if len(candidates) == 1 and candidates[0].similarity > 0.6:
                query = query.replace(match.group(), candidates[0].canonical_name)
                subs.append(Substitution(match.group(), candidates[0].canonical_name, "fuzzy_company"))
        return query, subs

    def _find_fuzzy_company(self, text: str) -> list[CompanyCandidate]:
        return self.conn.execute(
            """
            SELECT canonical_name, similarity(canonical_name, %s) AS sim
            FROM company WHERE is_shenzhen=true
              AND similarity(canonical_name, %s) > 0.4
            ORDER BY sim DESC LIMIT 5
            """, (text, text),
        ).fetchall()
```

**前置 migration**：
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_company_canonical_trgm ON company USING gin (canonical_name gin_trgm_ops);
```

### 5.3 NER — 槽位抽取

```python
# 与 L2 的 QueryUnderstanding._llm_parse 合并
# LLM 一次返回 {intent, entities{}, slots{}}
# 不需要单独的 NER 模型

_SLOT_SCHEMA = {
    "filter_city": {"description": "城市过滤", "examples": ["深圳", "北京"]},
    "filter_role": {"description": "身份", "examples": ["企业家", "教授", "创始人"]},
    "education_school": {"description": "毕业学校", "examples": ["早稻田", "MIT"]},
    "industry": {"description": "行业", "examples": ["机器人", "AI"]},
    "year_range": {"description": "时间范围", "examples": [[2020, 2024], None]},
    "must_include": {"description": "必须出现的关键词", "examples": [["电梯", "机械臂"]]},
}
```

---

## 6. 画像反哺闭环

### 6.1 触发条件

当以下之一发生时，重新合成某位教授的 `profile_summary`：
- 首次拿到 arxiv 全文（N ≥ 3 篇）
- verified papers 数 从 0 → > 10（通过 gate v2 或 homepage-first）
- 距上次合成 > 90 天 AND paper_count 增长 > 30%

### 6.2 合成 Prompt

```python
_PROFILE_SUMMARY_PROMPT = """
你是学术档案写作助手。为下面这位教授生成一份 300-500 字的研究画像。

# 教授基本信息
- 姓名: {name_zh} ({name_en})
- 机构: {institution}
- 职位: {title}
- 官网简介: {profile_raw_text_excerpt}    # 取前 800 字

# 教授声明的研究方向
{research_directions}

# 该教授代表性论文（前 5-8 篇，含年份+期刊+摘要）
{papers_rendered}

# 该教授有全文的论文摘录（若有）
{fulltext_excerpts_rendered}         # 每篇前 500 字

# 写作要求
1. 开头一句话总括其研究领域。
2. 中间 2-3 段描述具体研究方向，引用代表作。
3. 若 h-index / 引用数 / 获奖可得，加一段学术影响力。
4. 不编造信息。不确定的用"据公开资料"而非"据称"。
5. 结尾不加"欢迎联系""以上为 AI 生成"等客套话。
"""
```

### 6.3 反哺脚本

**新脚本** `scripts/run_profile_summary_reinforce.py`：

```python
# 遍历所有满足触发条件的教授
# 对每位：
#   1. 拉 profile_raw_text + research_directions + top-5 verified papers + fulltext excerpts
#   2. 调 gemma4（或 gpt-4o 高质量路径）
#   3. 写入 professor.profile_summary
#   4. file pipeline_issue (stage='profile_reinforcement', severity='low', audit)
```

### 6.4 扩展研究方向（正反馈）

另一个反哺：当一位教授有 50+ verified papers，可从论文 title/abstract 聚类/抽取出更细的子方向：

```python
# scripts/run_topic_expansion_from_papers.py (新)
# 对每位教授，拉他所有 verified papers 的 titles
# 用 gemma4 分层聚类 → 输出 15-30 个细粒度子方向
# 把新方向写入 professor_fact (fact_type='research_topic', confidence=0.7)
# 下次 identity_gate 跑时，topic_consistency 判断有更全面的参考
```

---

## 7. 数据库 Migration 路线

按顺序：

| # | Migration | 内容 | 可回滚 |
|---|---|---|---|
| V011 | `create_paper_full_text.py` | 新表 paper_full_text | ✓ |
| V012 | `add_professor_orcid.py` | professor.orcid + index | ✓ |
| V013 | `enable_pg_trgm_and_vector.py` | CREATE EXTENSION pg_trgm, vector; 加 vector 列到 prof/company/paper | ✓（DROP EXT 需人工）|
| V014 | `add_search_tsvector.py` | 添加 BM25 用 tsvector 列（prof.search_tsv, company.search_tsv）| ✓ |
| V015（延后）| `paper_link_run_id_not_null.py` | 把 7.16 phase 2 后 run_id 设 NOT NULL | 需全部 writer 先 wire |

---

## 8. 模块拆分 / 文件布局

当前 chat.py 1100 行 → 拆成：

```
apps/admin-console/backend/chat/
├── __init__.py
├── api.py              # FastAPI endpoint (~80 行)
├── schemas.py          # Pydantic models (~100 行)
├── session.py          # SessionContext, session store
├── query_understanding.py  # ParsedQuery, LLM parse + pronoun + alias
├── orchestrator.py     # AgentOrchestrator (plan + execute + reflect)
├── response_shaper.py  # L7: follow-up suggestions, answer_style shaping
├── tools/
│   ├── __init__.py
│   ├── db.py           # DbTool
│   ├── hybrid.py       # HybridRetriever (BM25 + vector + rerank)
│   ├── web_search.py   # WebSearchTool (Serper)
│   └── paper_fulltext.py
├── synthesis/
│   ├── __init__.py
│   ├── packer.py       # ContextPacker
│   ├── synthesizer.py  # LLM answer synthesis
│   └── prompts.py      # 按 intent 组织的 prompt 模板
└── validators/
    ├── citation_validator.py    # 幻觉检测 + marker validate
    └── output_shape_check.py
```

**miroflow-agent 侧**（新增）：

```
apps/miroflow-agent/src/data_agents/paper/
├── homepage_publications.py   # HTML 抽取（新）
├── title_resolver.py          # 三级 API fallback（新）
├── title_cleaner.py           # 已有
├── arxiv_fulltext.py          # 下载 PDF + 抽文本（新）
├── canonical_writer.py        # 已有，加 from_homepage=True 参数
└── paper_identity_gate.py     # 已有，v2 改造
```

---

## 9. 测试策略

### 9.1 单元测试

- `test_homepage_publications.py`: 对 10 个已抓的 html fixture，断言能抽出 publications 且无多抽
- `test_title_cleaner.py`: 给 30 种 mojibake / HTML entity / 编号前缀变体
- `test_title_resolver.py`: mock 3 个 API，验证 fallback 顺序
- `test_cjk_pinyin_variants.py`: "姚建铨" → 6 种变体
- `test_query_understanding.py`: 20 个 query，验证 parse 结果

### 9.2 集成测试（需要 DB）

- `test_homepage_pipeline_e2e.py`: 喂一份 prof html → 完整跑 homepage extract + resolver + upsert → 验 paper/paper_link 入库
- `test_agent_orchestrator.py`: 25 个 sample question → 每个验 answer 字段 + query_type

### 9.3 可回放的评测集

把 `docs/测试集答案.xlsx` 的 25 题 + 预期关键词 做成：

```python
# tests/eval/test_sample_25.py
SAMPLE_QUESTIONS = [
    ("介绍清华的丁文伯", ["丁文伯", "清华", "副教授"]),
    ("他是否参与企业创立", ["无界智航", "联合创始人"]),
    ...
]

@pytest.mark.parametrize("q, keywords", SAMPLE_QUESTIONS)
def test_answer_contains_keywords(q, keywords):
    resp = client.post("/api/chat", json={"query": q}).json()
    for kw in keywords:
        assert kw in resp["answer_text"], f"{q} → missing {kw}"
```

每个 Sprint 结束前跑一次，记录 pass rate。

---

## 10. 风险清单

| # | 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | Homepage 排版千差万别，锚点识别漏抓多 | 高 | 中 | 先抽前 100 个 prof 人工抽样；漏抓率 > 30% 时加 LLM 兜底抽取（one-shot + title list） |
| R2 | arxiv 3s 节流太慢，回填 2000 篇要 ~2h | 中 | 低 | 后台异步跑；不影响用户查询 |
| R3 | OpenAlex title 精确匹配失败率（标题里的标点差异）| 中 | 中 | 加 Jaccard 软匹配 + 作者/年份辅助验证 |
| R4 | pg_trgm 公司模糊匹配太慢（每 query 全表扫）| 低 | 低 | gin 索引够；10k 公司无压力 |
| R5 | gemma4 本地推理速度不稳定（E 类 5s）| 中 | 中 | E 类超时 3s 降级到"本地数据不足"；Agent 超时 10s 强制返回 |
| R6 | Serper API 配额超限 | 低 | 高 | 每日监控 usage + Brave Search 备用 |
| R7 | pgvector 升级到 HNSW 需重建索引（停机）| 低 | 低 | dev DB 测试后再 prod；索引 CONCURRENTLY 构建 |
| R8 | Agent Orchestrator 死循环（反思上限漏了）| 中 | 高 | 硬编码 max_steps=3 + 每 step 超时 5s |
| R9 | 画像反哺 LLM 幻觉（编造论文）| 中 | 中 | Prompt 里强约束只用提供的证据；post-process 每句引 [N] 检测 |
| R10 | CJK↔Pinyin 变体生成错（多音字、姓名位错）| 中 | 低 | 加单元测试覆盖 30 个常见姓；LLM gate 作为最后 sanity check |

---

## 11. Sprint 执行明细

### Sprint 1 (7 工作日) — 管线倒置 + 数据补齐

| Day | 任务 | 交付 | 验收 |
|---|---|---|---|
| D1 | V011/V012 migration + paper_full_text + ORCID 字段 | 迁移应用；schema ready | `SELECT ... FROM paper_full_text` 不报错 |
| D1-2 | `homepage_publications.py` + `title_cleaner.py` + 单测 | 模块 + 20 单测 | pytest pass |
| D2-3 | `title_resolver.py`（OpenAlex + SS + arxiv 三级）+ 单测 + mock | 模块 + 15 单测 | mock resolver 三级 fallback 都走到 |
| D3-4 | `arxiv_fulltext.py`（下 PDF + 抽文本）+ 小样本实跑 | 脚本 + 运行日志 | 10 篇 arxiv 全文入库 |
| D4 | `run_homepage_paper_ingest.py` E2E 脚本 | 脚本 | 对 50 位 prof 实跑，≥ 1500 verified paper 入库 |
| D5 | chat 论文检索 handler（`<title>` 精查 + "这论文的链接"）+ 多轮 paper entity | chat.py 小改动 | Q11/Q12 样例 pass |
| D5 | 专利 xlsx 导入脚本 | 脚本 + DB | Q24/Q25 样例 pass |
| D6 | `paper_identity_gate.py` v2（双语 + ORCID）+ 回放 363 prof | 脚本 + 更新 | 全拒 profs 从 363 → < 80 |
| D7 | 全量 homepage_paper_ingest on all 775 prof + 监控 | 运行日志 + 报告 | verified paper 总数 > 12000 |

**Sprint 1 验收**：
- `SELECT count(*) FROM professor_paper_link WHERE link_status='verified'` ≥ 12000
- `SELECT count(*) FROM paper_full_text` ≥ 2000
- 25 题样例 18/25 pass

### Sprint 2 (10 工作日) — 画像反哺 + Agentic 初形

| Day | 任务 |
|---|---|
| D1-2 | `profile_summary` 反哺脚本 + Prompt 调优 |
| D2-3 | 全量 run：对 775 prof 生成 profile_summary |
| D3-4 | Web Search 工具（Serper）+ caching 层 |
| D5-6 | Chat.py 拆分：L1-L7 模块边界 |
| D7-8 | Query Rewriter（代词 + 别名 + LLM 改写） |
| D9 | 更新 `_llm_parse` 到完整 slot filling |
| D10 | 25 题回归测试 + fix bugs |

**验收**：profile_summary 覆盖 95%+；Query 能解析多条件；Q3/Q8/Q14/Q17 pass

### Sprint 3 (10 工作日) — 真 Agentic RAG

| Day | 任务 |
|---|---|
| D1-3 | Agent Orchestrator (planner + reflection loop + 超时) |
| D4-6 | Hybrid Retrieval（pgvector + embedding + RRF + rerank）|
| D7 | V013/V014 migration 应用 |
| D8 | 实体 NER + slot filling 集成 |
| D9 | 公司域 G 消歧 + topic switch detection |
| D10 | 25 题回归 + 性能测试 |

**验收**：22/25 样例 pass；每 query 平均 latency < 3s

---

## 12. 可执行的"第一个 PR"

给接手人一个**立即可以开始动手**的起点：

```
PR 标题：feat(round-12/sprint-1-day-1): V011 paper_full_text schema + homepage publications scaffold

文件变更：
  + apps/miroflow-agent/alembic/versions/V011_add_paper_full_text.py
  + apps/miroflow-agent/src/data_agents/paper/homepage_publications.py  (skeleton)
  + apps/miroflow-agent/tests/data_agents/paper/test_homepage_publications.py (4 fixtures)
  + apps/miroflow-agent/tests/fixtures/homepage_html/{tsinghua_sigs_ding.html, sustech_yao.html, ...}

验收命令：
  cd apps/miroflow-agent && \
    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
    uv run alembic upgrade V011
  uv run pytest tests/data_agents/paper/test_homepage_publications.py -n0 -q
```

之后的 PR 按 Sprint 1 明细的 Day 粒度。

---

## 13. 与审计文档的对应关系

| 审计文档章节 | 本文档对应章节 |
|---|---|
| §1 PRD 12 能力 | §1 L0-L7 每层的接口映射 |
| §2 当前完成度矩阵 | §8 模块拆分（指出哪些文件需新建/拆分）|
| §3 Agentic RAG 架构缺口 | §1 L3 Orchestrator + §5 Rewriter + §4 Web Search |
| §4 论文验证 + 管线倒置 | §2 Homepage-authoritative 管线 + §3 gate v2 |
| §4.5 画像反哺 | §6 画像反哺闭环 |
| §6 路线图 | §11 Sprint 执行明细 |
| §7 总结 | §12 第一个 PR |

---

## 14. 参考资料

- [OpenAlex Works Search API](https://docs.openalex.org/api-entities/works/search-works)
- [arXiv API User Manual](https://info.arxiv.org/help/api/user-manual.html) + [Terms of Use](https://info.arxiv.org/help/api/tou.html)
- [Serper.dev vs SerpAPI vs Brave — Scrapfly 2026](https://scrapfly.io/blog/posts/google-serp-api-and-alternatives)
- [pgvector 实用容量分析（5M 向量前足够）](https://medium.com/@vhrechukha/i-spent-a-week-researching-what-to-use-instead-of-pgvector-heres-the-honest-answer-d6a2ce0a0613)
- [pgvector vs Milvus vs Qdrant 2026 对比](https://dev.to/linou518/choosing-the-foundation-for-your-rag-system-pgvector-vs-qdrant-vs-milvus-2026-4i5o)
- 内部：`docs/plans/2026-04-20-001-system-capability-audit-and-agentic-rag-gaps.md`
- 内部：`docs/Agentic-RAG-PRD.md` §2 / §E
- 内部：`docs/Professor-Data-Agent-PRD.md`

---

## 15. 未解决问题（留给下一轮讨论）

1. **多语言文档 Embedding 模型**：BGE-M3 vs MiniLM vs e5-mistral — 先用 BGE-M3，后续基准测试再调
2. **Rerank 模型**：LLM-as-judge vs bge-reranker-v2 vs Cohere — Sprint 3 决定
3. **E 类 Web Search 引用质量**：Serper 返回前 10 条的 snippet 是否足够？需不需要对每个结果 fetch_page？成本权衡
4. **Profile reinforcement 周期策略**：每 90 天重跑 vs 事件驱动（新 paper 入库触发）— Sprint 2 末讨论
5. **多租户 / 数据隔离**：当前全部 miroflow_real 单库；如果加 read-only user 给端用户查询，权限模型？
