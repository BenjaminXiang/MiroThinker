---
title: Professor Pipeline V3 — 三层采集 + 跨域关联 重设计方案
date: 2026-04-06
owner: codex
status: reference
superseded_by: docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md
---

# Professor Pipeline V3 — 三层采集 + 跨域关联 重设计方案

## 问题现状

当前 Pipeline V2 产出 3274 条教授数据，质量极差：
- 仅 200 条 (6%) 达到 `ready` 标准
- 90% 教授缺 title，80% 缺 research_directions，40% 缺 department
- research_directions 经常混入课程名、教育经历（regex 提取 bug）
- company_roles / patent_ids / top_papers 全部为空（0 条有值）
- 个人简介和评估摘要是模板废话（已清除）

根因：Pipeline V2 只做了一层采集（官网名录 regex），后续 Stage 2b/2c/3 实际很少触发或效果差。

## 设计目标

重新设计三层采集管线，完成标准：
- **教授核心字段填充率 > 80%**（institution, department, title, email, research_directions）
- **教授-企业关联**：确认后双向写入
- **精度优先**：宁可漏掉（false negative），不要误关联（false positive）

## 架构总览

```
Layer 1: 官网名录              Layer 2: 个人主页深度           Layer 3: Web Search 扩展
┌────────────────┐     ┌────────────────────┐     ┌──────────────────────┐
│ roster discovery│     │ homepage recursive  │     │ web search + crawl   │
│ + regex extract │────▶│ crawl + LLM extract │────▶│ + identity verify    │
│                │     │                    │     │ + cross-domain link  │
└────────────────┘     └────────────────────┘     └──────────────────────┘
     已有 ✅                  新建 🔨                    新建 🔨

                    ┌─────────────────────┐
                    │  Post-processing    │
                    │ • 研究方向清洗       │
                    │ • LLM 摘要生成      │
                    │ • 质量评估          │
                    │ • 向量化 + 发布      │
                    └─────────────────────┘
```

## 数据流：以于赐龙为例

```
Layer 1 输出:
  name=于赐龙, institution=深圳大学, department=机电与控制工程学院
  email=yu@szu.edu.cn, homepage=https://cmce.szu.edu.cn/info/1431/3809.htm
  research_directions=["机器视觉","图像处理","机器学习","微流控 主讲本科课程..."]  ← 脏数据
  title=null, education=[], company_roles=[]

Layer 2 输出 (爬取 homepage):
  title=副教授
  education=[{school:"华中科技大学", degree:"博士", field:"光学工程", ...}]
  research_directions=["机器视觉","图像处理","机器学习","微流控"]  ← 清洗后
  awards=["深圳市海外高层次人才"]

Layer 3 输出 (web search "于赐龙 深圳大学"):
  搜索结果 → 企名片页面提到 "深圳点联传感科技有限公司"
    → 爬取企名片/天眼查页面
    → LLM 验证：该公司法人/股东是否为于赐龙？院校是否匹配？
    → 确认关联 → company_roles=[{company_name:"深圳点联传感科技有限公司", role:"创始人"}]
    → 双向写入：教授记录写入 company_roles，企业记录写入 professor_ids
```

---

## Layer 1: 官网名录（现有，微调）

### 现状
- `discovery.py` (918行): 递归爬取7所深圳高校名录页
- `profile.py`: regex 提取 email/title/研究方向
- 输出: `MergedProfessorProfileRecord`

### 需要修复
1. **研究方向清洗** — 新建 `direction_cleaner.py`
   - 去除课程名（匹配"主讲"、"课程"、"教材"等关键词后截断）
   - 去除教育经历泄漏（匹配"教育背景"、年份范围 `20\d{2}[-–]20\d{2}`）
   - 去除过长项（>20字的通常不是研究方向）
   - 拆分复合项（"机器视觉与图像处理" → ["机器视觉", "图像处理"]）

2. **profile.py regex 加固** — 研究方向提取时，遇到"主讲"/"课程"/"教育背景"立即截止

### 输入/输出不变
- 输入: `docs/教授 URL.md` 种子文件
- 输出: `list[MergedProfessorProfileRecord]`

---

## Layer 2: 个人主页深度爬取（新建）

### 模块: `homepage_crawler.py`

### 逻辑
```python
async def crawl_homepage(profile: MergedProfessorProfileRecord) -> HomepageCrawlResult:
    """递归爬取教授个人主页，提取结构化信息。"""
    homepage_url = profile.homepage or profile.profile_url
    
    # Step 1: 抓取主页 HTML
    main_html = await fetch_html(homepage_url)
    
    # Step 2: 发现子页面链接（同域名内）
    sub_links = extract_sub_links(main_html, homepage_url)
    # 过滤：只保留同域名、看起来像简历/论文/项目的链接
    # 例如: /publications, /research, /cv, /projects, /students
    relevant_links = filter_relevant_links(sub_links)
    
    # Step 3: 爬取子页面（最多5个，避免过度爬取）
    all_html = [main_html]
    for link in relevant_links[:5]:
        sub_html = await fetch_html(link)
        all_html.append(sub_html)
    
    # Step 4: LLM 结构化提取（将所有页面内容合并，一次调用）
    extracted = await llm_extract_from_pages(
        profile_context=profile,  # 已有信息作为锚点
        html_pages=all_html,
        output_schema=HomepageExtractOutput,
    )
    
    return HomepageCrawlResult(
        profile=merge_homepage_data(profile, extracted),
        pages_crawled=len(all_html),
        evidence_urls=[homepage_url] + relevant_links[:5],
    )
```

### 输出模型: `HomepageExtractOutput`
```python
class HomepageExtractOutput(BaseModel):
    title: str | None = None               # 职称
    department: str | None = None           # 院系（可能更精确）
    research_directions: list[str] = []     # 研究方向
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    awards: list[str] = []
    academic_positions: list[str] = []
    projects: list[str] = []
    publications_summary: str | None = None  # 论文概况
```

### LLM Prompt 设计要点
- 给出已有信息作为锚点（姓名、院校），避免从页面中错误提取他人信息
- 明确指示从 HTML 中提取，禁止编造
- 教育经历要求：学校+学位+专业+年份，缺少的字段留 null
- 研究方向：仅提取明确列出的方向，不从论文标题推断

### 子页面链接过滤规则
```python
RELEVANT_PATH_KEYWORDS = {
    "publication", "paper", "research", "project", "cv", "resume",
    "student", "group", "lab", "award", "honor",
    "论文", "发表", "研究", "项目", "简历", "荣誉", "获奖", "课题组",
}

def filter_relevant_links(links: list[str]) -> list[str]:
    """只保留看起来和学术简历相关的子页面。"""
    return [
        link for link in links
        if any(kw in link.lower() for kw in RELEVANT_PATH_KEYWORDS)
    ]
```

---

## Layer 3: Web Search + 身份验证 + 跨域关联（新建）

### 3.1 搜索策略: `web_search_enrichment.py`

```python
async def search_and_verify(
    profile: EnrichedProfessorProfile,
    search_provider: WebSearchProvider,
) -> WebSearchEnrichmentResult:
    
    # Step 1: 构造搜索查询
    queries = build_search_queries(profile)
    # 主查询: "{姓名} {院校}"
    # 补充查询: "{姓名} {院校} {研究方向[0]}" (如有)
    # 企业查询: "{姓名} {院校} 创业 OR 创始人 OR 公司"
    
    # Step 2: 执行搜索，收集候选结果
    candidates: list[SearchCandidate] = []
    for query in queries:
        results = search_provider.search(query)
        for item in results.get("organic", []):
            candidates.append(SearchCandidate(
                title=item["title"],
                url=item["link"],
                snippet=item.get("snippet", ""),
                query=query,
            ))
    
    # Step 3: 去重 + 过滤（去掉已有的官网URL、学术搜索引擎结果页）
    candidates = deduplicate_and_filter(candidates, profile)
    
    # Step 4: 对每个候选页面 → 爬取 + 身份验证 + 信息提取
    verified_results: list[VerifiedWebResult] = []
    for candidate in candidates[:8]:  # 最多爬8个页面
        result = await verify_and_extract(candidate, profile)
        if result.is_same_person:
            verified_results.append(result)
    
    # Step 5: 合并已验证信息
    return merge_web_results(profile, verified_results)
```

### 3.2 身份验证: `identity_verifier.py`

核心：LLM 判断搜索结果是否属于同一教授，精度优先。

```python
class IdentityVerification(BaseModel):
    is_same_person: bool
    confidence: float        # 0-1
    matching_signals: list[str]   # 匹配的信号
    conflicting_signals: list[str]  # 冲突的信号
    reasoning: str           # 判断理由

VERIFY_PROMPT = """## 身份验证任务
判断以下网页内容是否描述的是目标教授本人。

## 目标教授（已确认信息）
姓名: {name}
院校: {institution}
院系: {department}
邮箱: {email}
研究方向: {directions}

## 待验证网页
URL: {url}
内容:
{page_content}

## 判断规则
- 必须满足：姓名完全匹配 + 院校匹配（或有明确的任职关系）
- 加分信号：邮箱匹配、研究方向重叠、照片描述一致
- 减分信号：院校不同且无调动证据、研究方向完全无关、年龄/性别矛盾
- 同名不同人很常见，有任何疑问就判定为 false
- confidence < 0.8 时 is_same_person 必须为 false

输出 JSON:
"""
```

### 验证阈值
- `confidence >= 0.8` 且 `is_same_person == true` → 采纳
- 否则 → 丢弃（宁可漏掉）

### 3.3 企业关联确认: `company_linker.py`

当搜索结果涉及企业时的专门处理流程：

```python
async def verify_company_link(
    professor: EnrichedProfessorProfile,
    company_mention: CompanyMention,  # 从搜索结果中发现的企业提及
    store: SqliteReleasedObjectStore,
) -> CompanyLinkResult | None:
    """验证教授与企业的关联，确认后双向写入。"""
    
    # Step 1: 爬取企业信息页面（天眼查/企查查/企名片/公司官网）
    page_content = await fetch_and_clean(company_mention.evidence_url)
    
    # Step 2: LLM 验证关联
    verification = await verify_professor_company_link(
        professor_name=professor.name,
        professor_institution=professor.institution,
        company_name=company_mention.company_name,
        page_content=page_content,
    )
    
    if not verification.is_confirmed or verification.confidence < 0.8:
        return None
    
    # Step 3: 构造 CompanyLink
    link = CompanyLink(
        company_name=company_mention.company_name,
        role=verification.role,  # "创始人" | "首席科学家" | "股东" | ...
        evidence_url=company_mention.evidence_url,
        source="web_search",
    )
    
    # Step 4: 查找数据库中是否已有该企业记录
    company_obj = find_company_by_name(store, company_mention.company_name)
    if company_obj:
        link = link.model_copy(update={"company_id": company_obj.id})
    
    return CompanyLinkResult(
        company_link=link,
        company_obj=company_obj,  # None if company not in our database
        verification=verification,
    )
```

### 3.4 双向关联写入: `cross_domain_linker.py`

```python
def write_bidirectional_link(
    store: SqliteReleasedObjectStore,
    professor_id: str,
    company_link: CompanyLink,
) -> None:
    """确认关联后，双向写入教授和企业记录。"""
    
    # 1. 教授侧：写入 company_roles
    prof_obj = store.get_object("professor", professor_id)
    if prof_obj:
        roles = prof_obj.core_facts.get("company_roles", [])
        # 避免重复
        if not any(r.get("company_name") == company_link.company_name for r in roles):
            roles.append(company_link.model_dump())
            updated_facts = {**prof_obj.core_facts, "company_roles": roles}
            patched = prof_obj.model_copy(update={"core_facts": updated_facts})
            store.update_object(patched)
    
    # 2. 企业侧：写入 professor_ids
    if company_link.company_id:
        comp_obj = store.get_object("company", company_link.company_id)
        if comp_obj:
            prof_ids = comp_obj.core_facts.get("professor_ids", [])
            if professor_id not in prof_ids:
                prof_ids.append(professor_id)
                updated_facts = {**comp_obj.core_facts, "professor_ids": prof_ids}
                patched = comp_obj.model_copy(update={"core_facts": updated_facts})
                store.update_object(patched)
```

---

## Pipeline V3 执行流程

```python
async def run_professor_pipeline_v3(
    seed_path: str,
    store: SqliteReleasedObjectStore,
    config: PipelineV3Config,
) -> PipelineV3Report:
    
    # ── Stage 1: 名录发现 (Layer 1, 现有) ──
    seeds = discover_rosters(seed_path)
    
    # ── Stage 2: Regex 提取 (Layer 1, 现有 + 清洗修复) ──
    profiles = await extract_profiles(seeds)
    profiles = [clean_research_directions(p) for p in profiles]  # 新：方向清洗
    
    # ── Stage 3: 个人主页深度爬取 (Layer 2, 新建) ──
    for profile in profiles:
        if profile.homepage:
            homepage_result = await crawl_homepage(profile)
            profile = homepage_result.profile
    
    # ── Stage 4: 学术数据 (现有 paper_collector) ──
    for profile in profiles:
        paper_result = await collect_papers(profile)
        profile = merge_paper_data(profile, paper_result)
    
    # ── Stage 5: Web Search 扩展 (Layer 3, 新建) ──
    for profile in profiles:
        ws_result = await search_and_verify(profile, search_provider)
        profile = ws_result.profile
        
        # 企业关联双向写入
        for company_link in ws_result.confirmed_company_links:
            write_bidirectional_link(store, profile.professor_id, company_link)
    
    # ── Stage 6: LLM 摘要生成 (现有，用 LLM 版) ──
    for profile in profiles:
        summaries = await generate_summaries(profile, llm_client)
        profile = merge_summaries(profile, summaries)
    
    # ── Stage 7: 质量评估 + 发布 ──
    release_result = build_professor_release(profiles)
    store.upsert_released_objects(release_result.released_objects)
```

---

## 新建模块清单

| 模块 | 文件 | 职责 | 依赖 |
|------|------|------|------|
| 研究方向清洗 | `direction_cleaner.py` | 去除课程/教育泄漏，拆分复合项 | 纯逻辑 |
| 个人主页爬取 | `homepage_crawler.py` | 递归爬取主页子页面 + LLM 提取 | fetch_html, LLM |
| Web Search 富化 | `web_search_enrichment.py` | 构造查询 + 搜索 + 调度验证 | WebSearchProvider |
| 身份验证 | `identity_verifier.py` | LLM 判断搜索结果是否同一人 | LLM |
| 企业关联 | `company_linker.py` | 验证教授-企业关系，确认后写入 | LLM, Store |
| 跨域写入 | `cross_domain_linker.py` | 双向写入教授↔企业关联 | Store |

## 可复用的现有模块

| 模块 | 复用方式 |
|------|----------|
| `discovery.py` | 直接用，Stage 1 不变 |
| `profile.py` | 修复 regex 截止逻辑后继续用 |
| `paper_collector.py` + `academic_tools.py` | 直接用，Stage 4 不变 |
| `summary_generator.py` | 用 LLM 版 `generate_summaries()`，弃用 rule-based fallback |
| `quality_gate.py` | 调整 L2 标准后继续用 |
| `release.py` | 去掉 evaluation_summary 必填后继续用 |
| `WebSearchProvider` | 直接用，已有 Serper 集成 |
| `discovery.py::fetch_html_with_fallback` | Layer 2/3 爬取时复用 |

## 关键决策

1. **精度优先**：身份验证 confidence < 0.8 一律丢弃
2. **Layer 2 爬取限制**：每个教授最多爬 5 个子页面，避免过度
3. **Layer 3 搜索限制**：每个教授最多 2-3 条查询，最多爬 8 个结果页
4. **企业关联需要双重确认**：搜索结果提到 + LLM 验证 role 和 evidence_url
5. **evaluation_summary 移除**：不再生成，不影响 RAG 检索
6. **profile_summary 仅用 LLM 生成**：不使用 rule-based fallback，没有 LLM 就留空

## 工作量估算

| 模块 | 新代码量 | 难度 |
|------|---------|------|
| `direction_cleaner.py` | ~100 行 | 低 |
| `homepage_crawler.py` | ~250 行 | 中 |
| `web_search_enrichment.py` | ~300 行 | 高（调度逻辑复杂） |
| `identity_verifier.py` | ~150 行 | 中（prompt 设计关键） |
| `company_linker.py` | ~200 行 | 中 |
| `cross_domain_linker.py` | ~100 行 | 低 |
| `profile.py` 修复 | ~30 行改动 | 低 |
| `release.py` 修复 | ~20 行改动 | 低 |
| Pipeline V3 主流程 | ~200 行 | 中 |
| 测试 | ~500 行 | 中 |
| **合计** | **~1850 行** | |
