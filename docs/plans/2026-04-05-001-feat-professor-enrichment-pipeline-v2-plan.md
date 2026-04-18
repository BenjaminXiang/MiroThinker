---
title: "feat: Professor Enrichment Pipeline v2 — LLM-Powered Agent-Driven Data Collection"
type: feat
status: reference
date: 2026-04-05
origin: docs/superpowers/specs/2026-04-05-professor-enrichment-pipeline-v2-design.md
superseded_by: docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md
---

# feat: Professor Enrichment Pipeline v2

## Overview

Replace the pure regex professor data pipeline with an LLM-powered, agent-driven system that produces searchable, fact-dense professor profiles for the Shenzhen Sci-Tech Innovation Platform. The pipeline follows a paper-first principle: official websites anchor identity, academic papers drive research profiles, and an agent loop fills remaining gaps. Papers collected during professor enrichment simultaneously feed the paper domain ("一鱼两吃").

## Problem Frame

The v1 pipeline uses `profile.py` (HTMLParser + regex) to extract professor data from university websites. It produces sparse records: `research_directions` are coarse labels from outdated official pages, `education_structured` / `work_experience` / `h_index` / `citation_count` / `top_papers` / `company_roles` / `patent_ids` are all hardcoded empty. `release.py` generates template summaries filled with meta-information ("已整理N条可追溯来源") instead of substantive content about the professor. The result: profiles are unsearchable by research topic and useless for answering user questions like "深圳哪些教授在做大模型？".

## Requirements Trace

From `docs/Professor-Data-Agent-PRD.md` and `docs/Data-Agent-Shared-Spec.md`:

- **R1**: LLM-driven extraction for unstructured web pages (PRD §3.1)
- **R2**: Scholar / Semantic Scholar as auxiliary sources (PRD §3.2)
- **R3**: `education_structured`, `work_experience` populated from real data (PRD §4)
- **R4**: `h_index`, `citation_count` from academic platforms (PRD §4)
- **R5**: `top_papers` with title, venue, citation count (PRD §4)
- **R6**: `company_roles`, `patent_ids` cross-domain links (PRD §4, Shared Spec §5)
- **R7**: `profile_summary` 200-300 chars with specific research terms (PRD §5)
- **R8**: `evaluation_summary` 100-150 chars, factual only (PRD §5)
- **R9**: Evidence traceability for every extracted field (Shared Spec §3)
- **R10**: Paper-first `research_directions` from recent publication analysis (origin §1.1)
- **R11**: Paper staging records feed paper domain (origin §1.2, "一鱼两吃")
- **R12**: Milvus vector storage with real embeddings for semantic search (origin §8)

## Scope Boundaries

**In scope:**
- Stage 2a: regex pre-extraction (preserve existing `profile.py`)
- Stage 2b: paper collection from Semantic Scholar, DBLP, arXiv (scrape-first, API fallback)
- Stage 2c: agent-driven gap filling (education, work, company, patent)
- Stage 3: LLM summary generation replacing template summaries
- Stage 4: quality gate + real embedding vectorization + Milvus storage
- Cross-domain link models (`PaperLink`, `CompanyLink`, `PatentLink`, `PaperStagingRecord`)
- DashScope provider for LLM escalation tier
- E2E script for real crawling with resume/retry

**Out of scope:**
- Changes to `discovery.py`, `roster.py`, `parser.py`, `name_selection.py`, `validator.py`
- Cross-domain ID backfill automation (deferred to post-MVP)
- Reranker integration (Phase 2)
- Admin console integration (separate plan)

## Context & Research

### Relevant Code Patterns

| Pattern | Location | Reuse Strategy |
|---------|----------|----------------|
| Structured output agent loop | `src/data_agents/runtime.py` → `run_structured_task()` | Reuse for per-professor agent tasks (Stage 2c) |
| OpenAI-compat provider | `src/data_agents/providers/qwen.py` → `QwenProvider` | Clone pattern for DashScope provider |
| Web search | `src/data_agents/providers/web_search.py` → `WebSearchProvider` | Reuse in agent tool box |
| HTML fetch with fallback | `src/data_agents/professor/discovery.py` → `fetch_html_with_fallback()` | Reuse for academic page scraping |
| Evidence building | `src/data_agents/evidence.py` → `build_evidence()`, `merge_evidence()` | Reuse for all evidence tracking |
| JSONL publishing | `src/data_agents/publish.py` → `publish_jsonl()` | Reuse for all output files |
| Pydantic contracts | `src/data_agents/contracts.py` → `ProfessorRecord`, `Evidence` | Extend; `ProfessorRecord` already has `h_index`, `citation_count`, `awards`, etc. |
| Milvus store | `src/data_agents/storage/milvus_store.py` → `MilvusVectorStore` | Replace hash-embedding with real Qwen3-Embedding |
| Test factories | `tests/data_agents/professor/test_release.py` → `_merged_record()` | Follow pattern for new test factories |
| E2E script | `scripts/run_professor_crawler_e2e.py` | Extend for v2 pipeline |

### Key Architectural Decisions

1. **Dataclass → Pydantic migration for internal models**: Current `models.py` uses frozen dataclasses. New `EnrichedProfessorProfile` uses Pydantic `BaseModel` for JSON schema generation (needed by `runtime.py` → `schema_text_for_model()`). Old dataclasses remain for Stage 1 compatibility.

2. **Append-mode JSONL for resume**: `enriched.jsonl` and `paper_staging.jsonl` use append writes with professor-ID-based dedup on restart. This follows the pattern in the design spec §9.4.

3. **Sync scraping, async agent loop**: Paper scraping (Stage 2b) is synchronous HTTP with `requests` + Playwright fallback (matching `fetch_html_with_fallback`). Agent tasks (Stage 2c) use `asyncio` via `run_structured_task()`.

4. **`ProfessorRecord` contract is the target**: The final output must validate against the existing `ProfessorRecord` in `contracts.py`. The `EnrichedProfessorProfile` is an intermediate model that maps to `ProfessorRecord` at release time.

## High-Level Technical Design

```
                         ┌─────────────────────────────────┐
                         │         pipeline_v2.py           │
                         │  run_professor_pipeline_v2()     │
                         └──────┬────────────────────────┬──┘
                                │                        │
              ┌─────────────────▼──┐         ┌───────────▼──────────┐
              │  Stage 1 (existing) │         │  resume_checkpoint() │
              │  discover_seeds()   │         │  load enriched.jsonl │
              └─────────┬──────────┘         └───────────┬──────────┘
                        │                                │
              ┌─────────▼──────────────────────────────────┐
              │              Per-Professor Loop             │
              │  ┌────────────┐  ┌───────────┐  ┌────────┐ │
              │  │ Stage 2a   │→ │ Stage 2b  │→ │Stage 2c│ │
              │  │ regex_pre  │  │ papers    │  │ agent  │ │
              │  │ extract    │  │ collect   │  │ fill   │ │
              │  └────────────┘  └─────┬─────┘  └────────┘ │
              │                        │                    │
              │            paper_staging.jsonl (append)     │
              └────────────────────┬───────────────────────┘
                                   │
              ┌────────────────────▼───────────────────────┐
              │  Stage 3: Summary Generation               │
              │  (LLM for professors that skipped agent)   │
              └────────────────────┬───────────────────────┘
                                   │
              ┌────────────────────▼───────────────────────┐
              │  Stage 4: Quality Gate → Release → Milvus  │
              └────────────────────────────────────────────┘
```

## Implementation Units

### Unit 1: Cross-Domain Link Models and `EnrichedProfessorProfile`

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/cross_domain.py` (new)
- `apps/miroflow-agent/src/data_agents/professor/models.py` (modify)
- `apps/miroflow-agent/tests/data_agents/professor/test_cross_domain.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_models_v2.py` (new)

**What:**
Create Pydantic models for cross-domain links and the enriched professor profile.

**Interface contracts:**

```python
# cross_domain.py
from pydantic import BaseModel

class PaperLink(BaseModel):
    paper_id: str | None = None       # PAPER-xxx, backfilled later
    title: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    doi: str | None = None
    source: str                        # "semantic_scholar" | "dblp" | "arxiv" | "web_scrape"

class CompanyLink(BaseModel):
    company_id: str | None = None      # COMP-xxx, backfilled later
    company_name: str
    role: str                          # "联合创始人" | "首席科学家" | "董事" | ...
    evidence_url: str | None = None
    source: str                        # "web_scrape" | "web_search" | "company_domain"

class PatentLink(BaseModel):
    patent_id: str | None = None       # PAT-xxx, backfilled later
    patent_title: str
    patent_number: str | None = None
    role: str = "发明人"
    source: str                        # "web_scrape" | "web_search" | "patent_domain"

class PaperStagingRecord(BaseModel):
    title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    keywords: list[str] = []
    source_url: str
    source: str                        # "semantic_scholar" | "dblp" | "arxiv"
    anchoring_professor_id: str
    anchoring_professor_name: str
    anchoring_institution: str

# models.py — add EnrichedProfessorProfile
class EnrichedProfessorProfile(BaseModel):
    name: str
    name_en: str | None = None
    institution: str
    department: str | None = None
    title: str | None = None
    email: str | None = None
    homepage: str | None = None
    office: str | None = None
    research_directions: list[str] = []
    research_directions_source: str = ""     # "paper_driven" | "official_only" | "merged"
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    h_index: int | None = None
    citation_count: int | None = None
    paper_count: int | None = None
    top_papers: list[PaperLink] = []
    awards: list[str] = []
    academic_positions: list[str] = []
    projects: list[str] = []
    company_roles: list[CompanyLink] = []
    patent_ids: list[PatentLink] = []
    profile_summary: str = ""
    evaluation_summary: str = ""
    enrichment_source: str                   # "regex_only" | "paper_enriched" | "agent_local" | "agent_online"
    evidence_urls: list[str] = []
    field_provenance: dict[str, str] = {}
    profile_url: str
    roster_source: str
    extraction_status: str

class EducationEntry(BaseModel):
    school: str
    degree: str | None = None
    field: str | None = None
    start_year: int | None = None
    end_year: int | None = None

class WorkEntry(BaseModel):
    organization: str
    role: str | None = None
    start_year: int | None = None
    end_year: int | None = None
```

**Decisions:**
- `EducationEntry` and `WorkEntry` are new Pydantic models in `models.py`, separate from the existing `EducationExperience` in `contracts.py` (which has stricter validation). Mapping happens at release time.
- `field_provenance` maps field names to source strings for auditability.
- `EnrichedProfessorProfile` deliberately duplicates some fields from `MergedProfessorProfileRecord` — it's a superset, not a subclass.

**Test scenarios:**
1. Construct `EnrichedProfessorProfile` with all fields populated → validates
2. Construct with only required fields → validates with defaults
3. `PaperLink` with `paper_id=None` → validates (pre-backfill state)
4. `PaperStagingRecord` serializes to JSON matching expected schema
5. Round-trip: `model_dump_json()` → `model_validate_json()` preserves all fields

---

### Unit 2: Academic Source Scrapers (`academic_tools.py`)

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/academic_tools.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_academic_tools.py` (new)

**What:**
Scrape-first paper collection from Semantic Scholar, DBLP, and arXiv. Each source has a scrape function and an API fallback. Includes three-source merge with DOI-based dedup and author disambiguation.

**Interface contracts:**

```python
# academic_tools.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AcademicAuthorInfo:
    """Author-level metrics from academic platforms."""
    h_index: int | None
    citation_count: int | None
    paper_count: int | None
    source: str                # "semantic_scholar" | "dblp" | "arxiv"

@dataclass(frozen=True)
class RawPaperRecord:
    """Single paper from any academic source."""
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    abstract: str | None
    doi: str | None
    citation_count: int | None
    keywords: list[str]
    source_url: str
    source: str                # "semantic_scholar" | "dblp" | "arxiv"

@dataclass(frozen=True)
class PaperCollectionResult:
    """Aggregated result of multi-source paper collection."""
    papers: list[RawPaperRecord]
    author_info: AcademicAuthorInfo | None
    disambiguation_confidence: float    # 0.0-1.0
    sources_attempted: list[str]
    sources_succeeded: list[str]

def collect_papers(
    *,
    name: str,
    name_en: str | None,
    institution: str,
    institution_en: str | None,
    existing_directions: list[str],
    fetch_html: Callable[[str, float], str],
    timeout: float = 30.0,
    crawl_delay: tuple[float, float] = (1.0, 3.0),
) -> PaperCollectionResult: ...

def scrape_semantic_scholar(
    name: str, institution: str, *, fetch_html: ..., timeout: float
) -> tuple[list[RawPaperRecord], AcademicAuthorInfo | None]: ...

def scrape_dblp(
    name: str, *, fetch_html: ..., timeout: float
) -> list[RawPaperRecord]: ...

def scrape_arxiv(
    name: str, *, fetch_html: ..., timeout: float
) -> list[RawPaperRecord]: ...

def merge_papers(
    *paper_lists: list[RawPaperRecord],
) -> list[RawPaperRecord]: ...
    # DOI-based dedup, title+year fuzzy match fallback

def disambiguate_author(
    candidates: list[RawPaperRecord],
    *,
    target_name: str,
    target_institution: str,
    existing_directions: list[str],
) -> tuple[list[RawPaperRecord], float]: ...
    # Returns (filtered_papers, confidence)
```

**Decisions:**
- Scrape functions use `fetch_html_with_fallback` from `discovery.py` (requests → Playwright → Jina Reader).
- Each scrape function handles its own HTML parsing. Semantic Scholar returns JSON-LD in `<script>` tags; DBLP uses structured `<li>` lists; arXiv search results are standard HTML.
- API fallback is attempted only when scraping fails (connection error, CAPTCHA, parse failure).
- Disambiguation uses three signals: institution affiliation match, co-author overlap with known professors, research direction consistency. All three failing → confidence < 0.3 → skip.
- `crawl_delay` adds random sleep between requests to avoid rate limiting.

**Test scenarios:**
1. `scrape_semantic_scholar` with mock HTML containing known structure → extracts papers + h_index
2. `scrape_dblp` with mock DBLP author page HTML → extracts papers with venue/year
3. `scrape_arxiv` with mock search results HTML → extracts papers with abstracts
4. `merge_papers` deduplicates by DOI → keeps record with most fields
5. `merge_papers` deduplicates by title+year when DOI missing → fuzzy match works
6. `disambiguate_author` with matching institution → high confidence
7. `disambiguate_author` with no matching signals → low confidence, papers filtered
8. `collect_papers` with one source failing → gracefully degrades to remaining sources
9. API fallback triggered when scrape returns empty → returns API results

---

### Unit 3: Paper-Driven Research Direction Generation

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py` (new)

**What:**
Orchestrates paper collection (delegates to `academic_tools.py`), generates paper-driven `research_directions` via LLM clustering, selects top papers, and writes `PaperStagingRecord`s.

**Interface contracts:**

```python
# paper_collector.py
from dataclasses import dataclass

@dataclass(frozen=True)
class PaperEnrichmentResult:
    """Result of Stage 2b for one professor."""
    research_directions: list[str]
    research_directions_source: str  # "paper_driven" | "official_only" | "merged"
    h_index: int | None
    citation_count: int | None
    paper_count: int | None
    top_papers: list[PaperLink]     # Top 5 by citation
    staging_records: list[PaperStagingRecord]
    disambiguation_confidence: float

async def enrich_from_papers(
    *,
    name: str,
    name_en: str | None,
    institution: str,
    institution_en: str | None,
    official_directions: list[str],
    professor_id: str,
    fetch_html: Callable[[str, float], str],
    llm_client: Any,                # OpenAI-compat client
    llm_model: str,
    timeout: float = 30.0,
) -> PaperEnrichmentResult: ...

async def generate_research_directions(
    *,
    papers: list[RawPaperRecord],
    official_directions: list[str],
    llm_client: Any,
    llm_model: str,
) -> tuple[list[str], str]: ...
    # Returns (directions, source_type)
    # LLM prompt: cluster paper titles+abstracts+keywords → 3-7 fine-grained labels
    # Merge with official_directions, remove overly generic labels

def select_top_papers(
    papers: list[RawPaperRecord],
    *,
    limit: int = 5,
) -> list[PaperLink]: ...

def build_staging_records(
    papers: list[RawPaperRecord],
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
) -> list[PaperStagingRecord]: ...
```

**Decisions:**
- `generate_research_directions` uses a single LLM call with a Chinese prompt. Input: concatenated titles + abstracts (truncated to 4000 chars). Output: JSON list of 3-7 direction labels.
- Top papers selected by `citation_count DESC`, with at least one from the last 2 years if available.
- `PaperStagingRecord` construction is a pure mapping from `RawPaperRecord` + professor anchoring info.

**Test scenarios:**
1. `enrich_from_papers` with mock papers → produces `PaperEnrichmentResult` with directions
2. `generate_research_directions` with papers having clear themes → LLM returns specific labels (mock LLM)
3. `generate_research_directions` merges with official_directions, removes duplicates
4. `generate_research_directions` with no papers → falls back to `official_directions` only
5. `select_top_papers` returns top 5 by citation, includes at least one recent paper
6. `select_top_papers` with fewer than 5 papers → returns all
7. `build_staging_records` produces valid `PaperStagingRecord` for each paper
8. Empty paper list → `PaperEnrichmentResult` with empty lists, `research_directions_source = "official_only"`

---

### Unit 4: Completeness Evaluator and Agent Trigger

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/completeness.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_completeness.py` (new)

**What:**
Evaluates field gaps after Stage 2a+2b and decides whether to trigger the agent loop (Stage 2c).

**Interface contracts:**

```python
# completeness.py
from dataclasses import dataclass

AGENT_TARGET_FIELDS: dict[str, float] = {
    "education_structured": 0.6,
    "work_experience": 0.6,
    "awards": 0.5,
    "academic_positions": 0.4,
    "projects": 0.4,
    "company_roles": 0.8,
    "patent_ids": 0.5,
    "department": 0.8,
    "title": 0.8,
}
AGENT_TRIGGER_THRESHOLD: float = 0.5

@dataclass(frozen=True)
class CompletenessAssessment:
    missing_fields: list[str]
    gap_weighted_sum: float
    should_trigger_agent: bool
    priority_fields: list[str]   # Fields sorted by weight, descending

def assess_completeness(
    profile: EnrichedProfessorProfile,
) -> CompletenessAssessment: ...
```

**Decisions:**
- A field is "missing" if it's empty/None/`[]`. For `department` and `title`, missing means `None`.
- `company_roles` has the highest weight (0.8) because users frequently ask about professor-company connections.
- Threshold 0.5 means: if ~60% of high-weight fields are missing → trigger agent.

**Test scenarios:**
1. Profile with all fields filled → `should_trigger_agent = False`, `gap_weighted_sum ≈ 0.0`
2. Profile with only regex fields (no education, no company) → `should_trigger_agent = True`
3. Profile at threshold boundary (gap_weighted_sum = 0.5) → `should_trigger_agent = True`
4. Profile just below threshold (gap_weighted_sum = 0.49) → `should_trigger_agent = False`
5. `priority_fields` ordered by weight: `company_roles` before `projects`

---

### Unit 5: DashScope LLM Provider

**Files:**
- `apps/miroflow-agent/src/data_agents/providers/dashscope.py` (new)
- `apps/miroflow-agent/tests/data_agents/providers/test_dashscope.py` (new)

**What:**
OpenAI-compatible provider for Alibaba DashScope (qwen3.6-plus), following `QwenProvider` pattern.

**Interface contracts:**

```python
# dashscope.py
class DashScopeProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: str = "",
        model: str = "qwen3.6-plus",
        timeout: float = 120.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None: ...

    def create_client(self) -> Any: ...

    def build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> dict[str, Any]: ...
```

**Decisions:**
- Mirrors `QwenProvider` but with DashScope defaults (higher max_tokens for enrichment tasks, stream=False for structured output).
- API key loaded from `DASHSCOPE_API_KEY` env var.
- No `extra_body` fields — DashScope doesn't support them the same way.

**Test scenarios:**
1. `build_request` produces valid OpenAI-format request dict
2. `create_client` with mock factory → returns client
3. API key from env var → used in client construction

---

### Unit 6: Agent Enrichment Loop (Stage 2c)

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/agent_enrichment.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_agent_enrichment.py` (new)

**What:**
Per-professor agent task that fills remaining fields using web search and scraping. Uses `runtime.py`'s `run_structured_task()` with LLM tiering (local Qwen first, DashScope escalation).

**Interface contracts:**

```python
# agent_enrichment.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AgentEnrichmentResult:
    profile: EnrichedProfessorProfile
    enrichment_source: str          # "agent_local" | "agent_online"
    llm_calls: int
    tool_calls: int

async def run_agent_enrichment(
    *,
    profile: EnrichedProfessorProfile,
    missing_fields: list[str],
    html_text: str,                  # Official page text (truncated to 4000 chars)
    local_llm_client: Any,
    local_llm_model: str,
    online_llm_client: Any | None,
    online_llm_model: str,
    web_search: WebSearchProvider,
    fetch_html: Callable[[str, float], str],
    timeout: float = 300.0,
) -> AgentEnrichmentResult: ...

def build_agent_prompt(
    profile: EnrichedProfessorProfile,
    missing_fields: list[str],
    html_text: str,
) -> str: ...
    # Returns the structured prompt per design spec §5.3

class AgentOutputModel(BaseModel):
    """Schema for agent structured output — only gap fields."""
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    awards: list[str] = []
    academic_positions: list[str] = []
    projects: list[str] = []
    company_roles: list[CompanyLink] = []
    patent_ids: list[PatentLink] = []
    department: str | None = None
    title: str | None = None
```

**Decisions:**
- The agent prompt includes the professor's already-known fields (identity, research directions, papers) so the LLM has full context.
- LLM tiering: try local Qwen3.5-35B first. If Pydantic validation fails OR core fields remain empty → retry with DashScope qwen3.6-plus.
- If both tiers fail → return profile as-is with `enrichment_source = "agent_local"` (best-effort).
- The agent uses `web_search` and `fetch_html` as tools, but does NOT re-collect papers (that's Stage 2b's job).
- Execution: for v1, the agent prompt is a single LLM call with structured output (not a multi-turn agent loop). This is simpler and sufficient for the gap-filling task. Multi-turn can be added later if single-call quality is insufficient.

**Test scenarios:**
1. `build_agent_prompt` includes all known fields and lists only missing fields
2. Agent with mock LLM returning valid JSON → profile updated with new fields
3. Local LLM fails validation → escalates to online LLM → succeeds
4. Both LLM tiers fail → returns original profile with `enrichment_source` set
5. Agent fills `company_roles` from web search results → `CompanyLink` validated
6. Agent fills `education_structured` from page text → `EducationEntry` validated
7. Agent does not overwrite existing non-empty fields

---

### Unit 7: LLM Summary Generator (Stage 3)

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/summary_generator.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_summary_generator.py` (new)

**What:**
Replaces template summaries with LLM-generated `profile_summary` and `evaluation_summary` following the spec's generation rules.

**Interface contracts:**

```python
# summary_generator.py
from dataclasses import dataclass

@dataclass(frozen=True)
class GeneratedSummaries:
    profile_summary: str
    evaluation_summary: str

async def generate_summaries(
    *,
    profile: EnrichedProfessorProfile,
    llm_client: Any,
    llm_model: str,
) -> GeneratedSummaries: ...

def build_profile_summary_prompt(
    profile: EnrichedProfessorProfile,
) -> str: ...

def build_evaluation_summary_prompt(
    profile: EnrichedProfessorProfile,
) -> str: ...

def validate_profile_summary(summary: str) -> bool: ...
    # 200-300 chars, no template boilerplate keywords

def validate_evaluation_summary(summary: str) -> bool: ...
    # 100-150 chars, no subjective evaluation
```

**Decisions:**
- Professors who went through Stage 2c agent loop should already have summaries generated as part of the agent task. Stage 3 only handles professors who skipped the agent (gap_weighted_sum < threshold).
- Validation checks: length bounds, absence of boilerplate keywords ("暂未获取", "持续补全", "仍在完善"), presence of at least one specific research term.
- If LLM summary fails validation → retry once with explicit feedback in prompt → if still fails, use rule-based fallback from existing `release.py` (better than no summary).
- LLM tiering same as Stage 2c: local first, online escalation.

**Test scenarios:**
1. `generate_summaries` with full profile → produces valid summaries (mock LLM)
2. `validate_profile_summary` rejects summary < 200 chars
3. `validate_profile_summary` rejects summary > 300 chars
4. `validate_profile_summary` rejects summary containing "暂未获取"
5. `validate_evaluation_summary` rejects summary with subjective language ("优秀", "杰出" without factual basis)
6. `validate_evaluation_summary` accepts summary with h-index and citation facts
7. `build_profile_summary_prompt` emphasizes paper-driven research content in the prompt
8. Fallback: LLM fails twice → rule-based summary generated

---

### Unit 8: Quality Gate (Stage 4)

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py` (new)

**What:**
Three-level quality validation per design spec §8.1.

**Interface contracts:**

```python
# quality_gate.py
from dataclasses import dataclass

@dataclass(frozen=True)
class QualityResult:
    passed_l1: bool
    quality_status: str           # "ready" | "incomplete" | "shallow_summary" | "needs_enrichment"
    l1_failures: list[str]        # Which L1 checks failed
    l2_flags: list[str]           # Which L2 conditions triggered

@dataclass(frozen=True)
class QualityReport:
    total_count: int
    released_count: int
    blocked_count: int
    ready_count: int
    incomplete_count: int
    shallow_summary_count: int
    needs_enrichment_count: int
    alerts: list[str]             # L3 statistical alerts

def evaluate_quality(
    profile: EnrichedProfessorProfile,
    *,
    shenzhen_keywords: tuple[str, ...] = SHENZHEN_INSTITUTION_KEYWORDS,
) -> QualityResult: ...

def build_quality_report(
    results: list[tuple[EnrichedProfessorProfile, QualityResult]],
) -> QualityReport: ...
```

**Decisions:**
- L1 blocks release entirely (not written to `professor_records.jsonl`).
- L2 marks quality_status but still publishes (better to have an incomplete profile than none).
- L3 is aggregate-level: ready < 70% → alert, per-institution coverage gap > 20% → alert.
- Boilerplate detection: a set of known template keywords that the old `release.py` used.

**Test scenarios:**
1. Profile with all L1 fields → passes L1
2. Profile with empty name → fails L1
3. Profile with non-Shenzhen institution → fails L1
4. Profile with no official_site evidence → fails L1
5. Profile with boilerplate summary → fails L1
6. Profile with empty research_directions → L2 flags "incomplete"
7. Profile with regex_only enrichment → L2 flags "needs_enrichment"
8. `build_quality_report` with 60% ready → generates alert
9. `build_quality_report` with all ready → no alerts

---

### Unit 9: Real Embedding Vectorizer

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/vectorizer.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_vectorizer.py` (new)

**What:**
Replaces the hash-based `_embed_text` in `milvus_store.py` with real embeddings from local Qwen3-Embedding-8B. Creates professor-specific Milvus collection with dual vectors.

**Interface contracts:**

```python
# vectorizer.py
import httpx

class EmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str = "http://172.18.41.222:18005/v1",
        timeout: float = 60.0,
    ) -> None: ...

    def embed_batch(
        self, texts: list[str], *, model: str = "qwen3-embedding-8b"
    ) -> list[list[float]]: ...
        # POST /embeddings, returns list of 4096-dim vectors

class ProfessorVectorizer:
    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        milvus_uri: str,
        collection_name: str = "professor_profiles",
    ) -> None: ...

    def ensure_collection(self) -> None: ...
        # Creates collection with schema per spec §8.3

    def vectorize_and_upsert(
        self, professors: list[tuple[str, EnrichedProfessorProfile, str]],
        # (professor_id, profile, quality_status)
    ) -> int: ...
        # Batch embed profile_summary + research_directions
        # Upsert to Milvus, returns count

    def search_by_profile(
        self, query: str, *, limit: int = 10, institution: str | None = None,
    ) -> list[str]: ...

    def search_by_direction(
        self, query: str, *, limit: int = 10, institution: str | None = None,
    ) -> list[str]: ...
```

**Decisions:**
- Uses `httpx` for HTTP embedding calls (async-capable, but sync usage here is fine for batch).
- Milvus collection schema matches spec §8.3 exactly: dual vectors (`profile_vector`, `direction_vector`), both HNSW with COSINE.
- Batch size: 50 profiles per embedding call.
- The existing `MilvusVectorStore` in `storage/milvus_store.py` is NOT modified — this is a separate, professor-specific vectorizer. The generic store remains for other domains.

**Test scenarios:**
1. `EmbeddingClient.embed_batch` with mock HTTP → returns correct shape (mock httpx)
2. `ensure_collection` creates collection with correct schema (mock MilvusClient)
3. `vectorize_and_upsert` embeds profiles and upserts → correct count (mock embedding + milvus)
4. `search_by_profile` returns professor IDs ranked by similarity (mock)
5. `search_by_direction` with institution filter → filters results (mock)
6. Empty input → returns 0, no Milvus calls

---

### Unit 10: Pipeline V2 Orchestrator

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/pipeline_v2.py` (new)
- `apps/miroflow-agent/tests/data_agents/professor/test_pipeline_v2.py` (new)

**What:**
Top-level orchestrator that wires all stages together. Manages concurrency, resume/checkpoint, and progress reporting.

**Interface contracts:**

```python
# pipeline_v2.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PipelineV2Config:
    seed_doc: Path
    output_dir: Path
    # LLM
    local_llm_base_url: str
    local_llm_model: str
    local_llm_api_key: str
    online_llm_base_url: str
    online_llm_model: str
    online_llm_api_key: str
    # Embedding
    embedding_base_url: str
    # Milvus
    milvus_uri: str
    # Web search
    serper_api_key: str
    # Concurrency
    max_concurrent_paper_crawl: int = 8
    max_concurrent_agents: int = 8
    max_concurrent_summary: int = 16
    embedding_batch_size: int = 50
    # Timeouts
    crawl_timeout: float = 30.0
    agent_timeout: float = 300.0
    # Domain
    official_domain_suffixes: tuple[str, ...] = ("sustech.edu.cn",)

@dataclass(frozen=True)
class PipelineV2Report:
    # Stage 1
    seed_count: int
    discovered_count: int
    unique_count: int
    # Stage 2a
    regex_structured_count: int
    regex_partial_count: int
    # Stage 2b
    paper_enriched_count: int
    papers_collected_total: int
    paper_staging_count: int
    avg_disambiguation_confidence: float
    # Stage 2c
    agent_triggered_count: int
    agent_local_success_count: int
    agent_online_escalation_count: int
    agent_failed_count: int
    # Stage 3
    summary_generated_count: int
    summary_fallback_count: int
    # Stage 4
    l1_blocked_count: int
    released_count: int
    quality_distribution: dict[str, int]
    vectorized_count: int
    alerts: list[str]

@dataclass(frozen=True)
class PipelineV2Result:
    report: PipelineV2Report
    output_files: dict[str, Path]

async def run_professor_pipeline_v2(
    config: PipelineV2Config,
) -> PipelineV2Result: ...
```

**Decisions:**
- Stage 1 reuses `run_professor_pipeline()` from existing `pipeline.py` to get `MergedProfessorProfileRecord` list.
- The per-professor loop (Stage 2a→2b→2c) runs with `asyncio.Semaphore` for concurrency control.
- Resume: on start, reads existing `enriched.jsonl` and builds a set of completed professor IDs. Skips professors already processed.
- Output files written to `config.output_dir` (default: `logs/data_agents/professor/`).
- Progress logged to stderr every 50 professors.

**Test scenarios:**
1. Full pipeline with 3 mock professors → produces all output files
2. Resume: pre-existing `enriched.jsonl` with 2 professors → only processes 3rd
3. Paper collection failure for one professor → continues with remaining
4. Agent escalation path: local fails → online succeeds → correct `enrichment_source`
5. Quality gate blocks 1 professor → `released_count` = `total - 1`
6. Config validation: missing API keys → raises early error
7. Concurrency: with `max_concurrent_paper_crawl=2` → at most 2 concurrent scrapes

---

### Unit 11: Hydra Configuration Extension

**Files:**
- `apps/miroflow-agent/conf/data_agent/default.yaml` (modify)
- `apps/miroflow-agent/conf/data_agent/professor_v2.yaml` (new)

**What:**
Add v2 pipeline configuration under Hydra config system.

**Config structure:**

```yaml
# professor_v2.yaml
professor_pipeline_v2:
  output_dir: "../../logs/data_agents/professor"
  stage2a:
    max_concurrent_regex: 16
  stage2b:
    max_concurrent_paper_crawl: 8
    crawl_delay_range: [1, 3]
    crawl_timeout: 30.0
  stage2c:
    max_concurrent_agents: 8
    agent_timeout: 300.0
    trigger_threshold: 0.5
  stage3:
    max_concurrent_summary: 16
  stage4:
    embedding_batch_size: 50
    milvus_collection: "professor_profiles"

# default.yaml — add to providers section:
providers:
  dashscope:
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: "qwen3.6-plus"
    timeout: 120.0
    api_key_env: "DASHSCOPE_API_KEY"
  embedding:
    base_url: "http://172.18.41.222:18005/v1"
    model: "qwen3-embedding-8b"
    timeout: 60.0
  milvus:
    uri: "logs/data_agents/professor/milvus.db"
```

**Decisions:**
- Separate YAML file for v2 config, loaded via Hydra config group.
- DashScope provider added to `default.yaml` since other domains may also need online LLM escalation.
- Embedding and Milvus config are professor-specific for now but structured for future sharing.

**Test scenarios:**
1. Load `professor_v2.yaml` via Hydra → all fields accessible
2. Missing `DASHSCOPE_API_KEY` env var → pipeline logs warning but doesn't crash (online tier unavailable)

---

### Unit 12: Release Pipeline Integration

**Files:**
- `apps/miroflow-agent/src/data_agents/professor/release.py` (modify)
- `apps/miroflow-agent/tests/data_agents/professor/test_release.py` (modify)

**What:**
Update `build_professor_release` to accept `EnrichedProfessorProfile` and map it to `ProfessorRecord`. Remove template summary generation (replaced by Stage 3 LLM summaries).

**Key changes:**
- Add `build_professor_release_v2()` function that takes `list[EnrichedProfessorProfile]` instead of `list[MergedProfessorProfileRecord]`.
- Map `EnrichedProfessorProfile` fields to `ProfessorRecord` fields: `EducationEntry` → `EducationExperience`, `CompanyLink` → `ProfessorCompanyRole`, `PaperLink.title` → `top_papers: list[str]`, `PatentLink.patent_number` → `patent_ids: list[str]`.
- Keep existing `build_professor_release()` unchanged for backward compatibility.
- Evidence building uses `field_provenance` to classify evidence sources.

**Test scenarios:**
1. `build_professor_release_v2` with enriched profile → valid `ProfessorRecord`
2. `ProfessorRecord` validates against `SHENZHEN_INSTITUTION_KEYWORDS`
3. Cross-domain links mapped correctly: `CompanyLink` → `ProfessorCompanyRole`
4. `top_papers` contains paper titles as strings
5. `patent_ids` contains patent numbers as strings
6. Evidence includes both official_site and academic_platform sources
7. Quality status from quality gate carried through to `ProfessorRecord.quality_status`

---

### Unit 13: E2E Script for Real Crawling

**Files:**
- `apps/miroflow-agent/scripts/run_professor_enrichment_v2_e2e.py` (new)

**What:**
End-to-end script that runs the full v2 pipeline against real URLs, storing results to JSONL + Milvus. Supports `--limit N` for partial runs, `--retry-failed` for re-processing failures, and `--institution` for single-university runs.

**Interface:**

```
usage: run_professor_enrichment_v2_e2e.py
    [--seed-doc PATH]
    [--output-dir PATH]
    [--limit N]
    [--institution NAME]
    [--retry-failed]
    [--skip-vectorize]
    [--dry-run]
```

**Decisions:**
- Reads API keys from environment variables (set in `.env` or shell).
- Default seed doc: `docs/教授 URL.md`.
- `--dry-run` runs Stage 1 only and prints discovery stats.
- `--limit 10` processes only the first 10 professors (for testing).
- Progress output to stderr, final report to stdout as JSON.

**Test scenarios:**
- Manual E2E verification against real URLs (not automated unit test).
- Verify output files exist and contain valid JSONL.
- Verify Milvus collection populated and searchable.

## Dependencies & Sequencing

```
Unit 1 (models)
  ├─→ Unit 2 (academic_tools)
  │     └─→ Unit 3 (paper_collector) ──→ Unit 10 (pipeline_v2)
  ├─→ Unit 4 (completeness) ─────────→ Unit 10
  ├─→ Unit 5 (dashscope) ────────────→ Unit 6, Unit 7, Unit 10
  ├─→ Unit 6 (agent_enrichment) ─────→ Unit 10
  ├─→ Unit 7 (summary_generator) ────→ Unit 10
  ├─→ Unit 8 (quality_gate) ─────────→ Unit 10
  └─→ Unit 9 (vectorizer) ──────────→ Unit 10
Unit 10 (pipeline_v2) ──→ Unit 11 (config) ──→ Unit 12 (release) ──→ Unit 13 (e2e)
```

**Critical path:** Unit 1 → Unit 2 → Unit 3 → Unit 10 → Unit 13

**Parallelizable:** Units 4, 5, 6, 7, 8, 9 can be developed in parallel after Unit 1.

## System-Wide Impact

- **Paper domain**: `paper_staging.jsonl` is a new data source. Paper Data Agent needs a consumer for this file (out of scope for this plan, but noted as downstream dependency).
- **Milvus**: New `professor_profiles` collection with 4096-dim vectors replaces the hash-based embeddings. Existing generic `MilvusVectorStore` remains for other domains.
- **Agentic RAG**: The RAG service layer can use `ProfessorVectorizer.search_by_profile()` and `search_by_direction()` for professor semantic search once v2 is deployed.
- **Cross-domain search**: `CompanyLink` and `PatentLink` in professor records enable the cross-domain query pattern described in `docs/Agentic-RAG-PRD.md`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Semantic Scholar anti-scraping blocks | Paper collection fails for most professors | API fallback built into `academic_tools.py`; rate limiting with configurable delay |
| Local Qwen3.5-35B produces poor structured output | Agent enrichment and summary quality low | LLM tiering to DashScope qwen3.6-plus; validation + retry loop |
| 3000-5000 professors × 3 academic sources = 10K+ HTTP requests | Slow runtime, potential IP blocking | Concurrent limit (8), per-host delay, HTML caching, resume/checkpoint |
| Author name disambiguation failures | Wrong papers associated with professors | Three-signal disambiguation (institution, co-authors, direction); low-confidence filtered |
| Milvus connection issues | Vectorization fails | Vectorization is the last step; JSONL outputs are still usable without it |

## Execution Posture

- **Execution target: external-delegate** for Units 1-9 (pure code generation, well-specified interfaces)
- Test-first for all units: write test stubs with scenarios listed above, then implement
- Unit 10 (orchestrator) and Unit 13 (E2E) require manual integration testing against real URLs
