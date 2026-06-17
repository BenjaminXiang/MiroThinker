# 统一教师采集对齐方案 — Unified Professor Crawl (UPC)

> 2026-06-17. Deep-design alignment for merging **professor field-completion (Part 1.2)** and **paper collection (Part 2.1)** into **one crawl per professor** — fetch the homepage once, extract fields + collect papers in the same pass, no half-finished artifacts. Grounded in best-practices research (Playwright stealth anti-412; LLM structured publication extraction; OpenAIRE-style dedup) and the existing codebase.

## 0. 目标与原则

- **目标**:对每位教师,一次抓取主页 → 同时产出 (a) 教授结构化字段(研究方向/教育/职务/工作经历/邮箱/中文简介,英文→双语)+ (b) 该教师的论文(解析→去重→富集→摘要翻译→入库 + professor_paper_link)。
- **核心原则(用户)**:**识别到论文信息时同时起论文收集任务,不留半成品**(不缓存待处理、不拆成两个独立 pass)。
- **覆盖**:37 seed / 10 校 / ~3,386 有主页的教师(+ HIT 走 L4 Playwright)。

## 1. 现状对齐(已建 vs 缺口)

| 组件 | 已有 | 在 UPC 中的角色 | 缺口 |
|---|---|---|---|
| 静态抓取 `paper/homepage_http.fetch_homepage_html` | ✅(已 follow_redirects) | 主抓取路径 | 412/反爬未解 |
| Playwright 渲染 `professor/hit_playwright_profile.render_hit_profile_html` | ✅(HIT 专用) | 通用渲染 fallback 的原型 | 需**通用化 + stealth**(反 412) |
| L2 字段抽取 `scripts/run_professor_llm_field_extract.py` | ✅(gemma4,双语,gap-skip) | 字段子管线 | 不抓论文 |
| 论文管线 `scripts/run_homepage_paper_ingest.py --prof-id` | ✅(主页→论文→resolve→enrich→publish) | 论文子管线(按教授) | 与 L2 是分离 pass;412 同样未解 |
| 标题解析 `paper/title_resolver.py`(OpenAlex→Crossref→S2→DBLP→arXiv→web) | ✅ | 论文去重/富集锚点 | web 层污染(D1,需归因门) |
| 富集 `paper/enrichment.py` + `abstract_translator` | ✅ | 摘要/字段富集 + summary_zh | provider 静默吞错(B1) |
| L4 HIT 适配器 | ✅(已 commit) | HIT(JS 渲染)专用 | — |
| **统一编排(按教授 fetch-once→fields+papers)** | ❌ | **本方案要建的** | — |
| **通用 Playwright-stealth fetch 层** | ❌ | 412/反爬解法 | — |

## 2. UPC 架构(按教授,fetch once → fields + papers)

```
For each professor (seed-driven, 10 schools + HIT):
  1. FETCH (shared, once)
     static = fetch_homepage_html(url, realistic headers)
     if static raises 4xx-anti-scrape (412/403) OR len(text)<60:
        html = render_with_playwright_stealth(url)   # ← 通用化 L4 的渲染 + stealth
     cache_html_in_pass(professor_id, html)           # 仅本次 pass 内复用,非"待处理缓存"
  2. FIELD EXTRACTION (L2, gemma4) — from the fetched text
     extract research_directions/education/academic_position/work_experience/contact/profile_summary
       + bilingual EN→中文 → professor_fact (source=llm_extraction/homepage_section + run_id)
  3. PUBLICATION EXTRACTION (in-pass) — from the SAME fetched text
     LLM structured extract → list[Publication{title,authors,year,venue,doi}]   (Pydantic schema)
  4. PAPER COLLECTION (triggered simultaneously) — for each Publication:
     resolve via title_resolver cascade (OpenAlex→Crossref→S2→DBLP→arXiv→web, + D1 归因门)
       → dedup anchor (DOI > arXiv > title+year) → paper_merge_alias / existing paper row
       → enrich abstract (resolved source; 4-provider-empty → Jina reader fallback W2a, gated on W1a)
       → translate abstract → summary_zh
       → write paper canonical + professor_paper_link(link_status=verified, is_officially_listed=true)
  5. WRITE (one transaction per professor): professor_fact + paper rows + links, all carry run_id
```

- **关键**:`run_homepage_paper_ingest --prof-id` 已经实现了 3+4(主页→论文→resolve→enrich→publish)。UPC 的编排 = **步骤 1(共享 fetch)+ 步骤 2(L2 字段)+ 调用论文管线(3+4)**,共享同一次抓取的 HTML。
- **不留半成品**:字段 + 论文在同一 pass 写入;论文 resolve/enrich 失败的记为 `needs_review` issue(可追溯),不留下"已抓未处理"的缓存。

## 3. 412 / 反爬解法(通用 Playwright-stealth fetch 层)

研究结论([Playwright stealth](https://scrapfly.io/blog/posts/playwright-stealth-bypass-bot-detection)、[Bright Data](https://brightdata.io/blog/how-tos/avoid-bot-detection-with-playwright-stealth)、[modern anti-bot](https://python.plainenglish.io/modern-anti-bot-systems-and-how-to-bypass-them-4d28475522d1)):
- 412 常见于**缺条件头(If-None-Match/ETag)或反爬 cookie/token 缺失**(Cloudflare/Akamai WAF)。真实浏览器天然带 cookie/session。
- **方案**:通用 `render_with_playwright_stealth(url)`:
  - `playwright-stealth` 补丁(navigator.webdriver、CDP 泄露等指纹)。
  - 真实 UA + Accept/Accept-Language/Referer;`wait_until=networkidle` + 4s(让反爬挑战/cookie 落地)。
  - 限流(人类化延迟)+ 可选住宅代理轮换。
  - 通用化 L4 的 `render_hit_profile_html`(去掉 HIT 专属 canonicalize,保留 stealth + wait)。
- **触发条件**:静态 fetch 抛 `HTTPStatusError`(412/403)或文本过短 → fallback。SZU csse 等即被覆盖。

## 4. 论文抽取(LLM 结构化,Pydantic schema)

研究结论([Simon Willison](https://simonw.substack.com/p/structured-data-extraction-from-unstructured)、[Instructor/Pydantic](https://python.useinstructor.com/learning/getting_started/first_extraction/)、[WebLists benchmark](https://arxiv.org/html/2504.12682v1)):
- 用 Pydantic 定义 `Publication{title, authors[], year, venue, doi, source_span}`,LLM(gemma4)输出 JSON 列表。
- 可与步骤 2(字段抽取)**合并为一次 LLM 调用**(同一 prompt 同时输出 fields + publications),省 token;或拆两次(更稳)。建议:**一次调用**(homepage 文本已读,合并省成本)。
- 现有 `homepage_publications.py`(规则解析器)+ `llm_publication_extractor.py`(LLM fallback)已存在;UPC 复用而非重写,但在统一编排里按教授调用。

## 5. 去重 / 富集 / 翻译(复用现有)

- **去重锚点**:`title_resolver` 级联 + `paper_merge_alias`(DOI>arXiv>source-supported-title-year>title-year-only→needs_review)。研究(OpenAIRE dedup、[OpenAlex authors](https://github.com/ourresearch/openalex-help/blob/main/how-it-works/authors.md))印证该分层。5,186 review-gated 组走 W2e review 工作流。
- **富集**:`enrichment.py`(OpenAlex→Crossref→S2→arXiv 级联);4 源全空 → W2a Jina-reader fallback(gated on W1a 归因门)。
- **摘要翻译**:`abstract_translator` → summary_zh。
- 这些都在 `run_homepage_paper_ingest` 内;UPC 复用。

## 6. 编排与数据流

- **驱动**:按 seed/学校批量,每校一个 worker(并行 9–10,同当前);每 worker 按教授串行(fetch once → fields + papers)。
- **共享 fetch**:步骤 1 的 HTML 同时喂给 L2(字段)和论文管线(论文),不二次抓取。
- **事务**:每教师一个 run_id;professor_fact + paper + professor_paper_link 同 run_id,可整教授回滚。
- **幂等/可续**:professor_fact ON CONFLICT DO NOTHING;paper 按 dedup 锚点;professor_paper_link 按 (professor,paper) 唯一。gap-skip 跳过已完整的教师(教授字段 + 论文都齐)。

## 7. 残差处理(到不了 100%)

- **未激活/空主页**:fetch 到的页面无内容 → 字段+论文都为空 → 记 `publication_source_sparse_count_only` / 字段缺失 issue,不伪造。
- **反爬持续失败**:Playwright-stealth 仍被挡 → 记 issue + 跳过(可重试/代理)。
- **论文 resolve 失败**:记 needs_review,不丢(可后续人工/LLM review)。
- 这些残差显式记为 `pipeline_issue`,不是"半成品缓存"。

## 8. 执行计划(切片顺序)

1. **通用 Playwright-stealth fetch 层**(通用化 L4 渲染 + stealth 补丁)→ 解 412。小、独立、先做。
2. **UPC 编排器**(`scripts/run_unified_professor_crawl.py`):按教授 fetch-once → L2 字段 + 调 `run_homepage_paper_ingest --prof-id`(共享 HTML)→ 写入。可先用"字段+论文抽取一次 LLM 调用"合并。
3. **试点**:1 校(如 SZU——既有 412 又有论文缺口)端到端跑通,验收字段+论文都进库、412 被 stealth 解掉。
4. **全量**:10 校并行(含 HIT 走 L4 变体)。
5. **闭环**:W3a(residual issue 关闭)+ 更新 acceptance/change-log。

## 9. 与现有 OpenSpec / 文档对齐

- 属 `professor-profile-field-completion-pipeline`(字段)+ paper 采集(Part 2.1,新起一个 `unified-professor-crawl` change 或扩展现有)。
- 复用:L2 脚本、L4 适配器、`run_homepage_paper_ingest`、`title_resolver`、`enrichment`、`abstract_translator`、W0b 身份门、W1a 归因门、W2a Jina fallback、W2e 重复 review。
- 不重写已有管线,只加**统一编排 + 通用 stealth fetch 层**。

## 10. 待确认(开放问题)

- **字段+论文一次 LLM 调用 vs 两次**:一次省成本,两次更稳。建议试点对比。
- **通用 stealth fetch 放哪**:`paper/homepage_http.py`(扩展现有)还是新模块?建议扩展 `homepage_http`(加 `fetch_homepage_html_or_render` + stealth)。
- **HIT(L4)如何并入 UPC**:HIT 用 Playwright 渲染(已是 stealth-like);UPC 编排器对 HIT host 直接用 L4 渲染路径,字段走 L4 mapper、论文走论文管线。
- **并发与 gemma4/DeepSeek 负载**:10 校并行 × (字段 LLM + 论文 resolve/enrich)负载较大;需限流 + 监控。

## 参考(研究)
- [Playwright Stealth – bypass bot detection (Scrapfly)](https://scrapfly.io/blog/posts/playwright-stealth-bypass-bot-detection)
- [Avoiding Bot Detection with Playwright Stealth (Bright Data)](https://brightdata.com/blog/how-tos/avoid-bot-detection-with-playwright-stealth)
- [Modern Anti-Bot Systems and How to Bypass Them](https://python.plainenglish.io/modern-anti-bot-systems-and-how-to-bypass-them-4d28475522d1)
- [Structured data extraction from unstructured content (Simon Willison)](https://simonw.substack.com/p/structured-data-extraction-from-unstructured)
- [Instructor + Pydantic structured LLM outputs](https://python.useinstructor.com/learning/getting_started/first_extraction/)
- [WebLists: extracting structured info from complex web pages (arXiv)](https://arxiv.org/html/2504.12682v1)
- [OpenAIRE – deduplication in scholarly infrastructure](https://www.openaire.eu/community/blogs/on-deduplication-in-the-openaire-infrastructure-1)
- [OpenAlex – how author profiles work](https://github.com/ourresearch/openalex-help/blob/main/how-it-works/authors.md)
