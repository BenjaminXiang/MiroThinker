# 高校教师→论文 数据清理 · 缺口分析（需求 ↔ 代码 ↔ spec）

> 2026-06-16. Organized by the two-part requirement (Part 1 教师收集 / Part 2 论文收集), reconciled against current code and OpenSpec specs. Companion to `2026-06-16-dirty-data-gap-closure-portfolio.md` (which is organized by root-cause waves); this doc is organized by product structure + the code reality.

## 0. 需求结构（用户定义）

- **Part 1 — 教师数据收集**：覆盖 `/seeds` 的 **37 个 seed URL**，每个 seed 有定制化爬虫（院系列表页 + 教师个人维护主页，通常挂在学校官网教师主页上），爬取 + 清洗 + 结构化。
- **Part 2 — 论文数据爬取与清洗**：从教师主页拿到发表的论文 → 进一步爬取/清洗相关论文 → 摘要翻译。

## ⚠️ 关键纠偏（必须先对齐认知）

> **"37 个 seed 每个都要有定制爬虫" 这一前提，在 roster（教师名单）层已经满足。** 实测：37 个 seed **全部已有定制 adapter**（18 个不同 custom crawler，`roster.py:2424-2515`），全部 `last_run_status=success`，**3,439 位教师 100% 有主页 URL**。Roster 层基本无缺口。
>
> **真正的缺口在 Part 2 的"主页论文抽取"**：主页声明了论文数，但结构化标题抽取返回 0（`publication_source_sparse_count_only`，`homepage_ingest.py:1964-1984`）。这就是各校大量"0 论文教师"的来源——不是没有爬虫，是**论文抽取解析器没认出该校的引用模板**。
>
> 所以：**不要再造 37 个 roster 爬虫**；要修的是 (a) Part 2.1 各校论文引用模板的抽取 + (b) Part 1.2 画像数据质量。

---

## Part 1 — 教师数据收集

### 1.1 Roster 采集（seed → 教师列表 + 主页 URL）— ✅ 基本完成

| 项 | 现状 | 证据 |
|---|---|---|
| 37 seed 覆盖 | **全部有 adapter，status=success** | `professor_seed` 表（V022），37 行 |
| 定制爬虫 | **18 个 distinct custom adapters**，0 个 `adapter_missing` | `roster.py:2424`，`adapter_resolution.py:11` |
| 教师主页 URL | **100% 覆盖**（3,439/3,439） | affiliation 匹配 |
| 相关 spec | `professor-seed-management`；archived `prof-seed-adapter-coverage`、`prof-seed-admin-console`、`prof-seed-ops-hardening` | `openspec/specs/` |

**残留小缺口**：PKUSZ（`pkusz.edu.cn/szdw.htm`）无命名 adapter，靠通用 fallback（历史 `adapter_missing`，见 archived `prof-seed-adapter-coverage`）。这是 roster 层唯一已知边角缺口，不影响主体。

### 1.2 教师个人主页爬取 + 画像结构化 — 🟡 有数据质量缺口

主页爬取本身在跑（`homepage_crawler.py`），画像已结构化；缺口是**画像字段质量**（即之前排查的脏数据 E2/E4/name-identity）：

| 缺口 | 量级 | 根因 | 代码 | 相关 spec / change |
|---|---|---|---|---|
| `profile_summary` 过短/样板（<200） | 441 ready / 1,435 广义 | fallback 允许 <200 + COALESCE 粘性 | `summary_generator.py:123-199`，`canonical_writer.py:968-1004` | `professor-summary-fields`（archived）；portfolio W0c |
| 缺 `research_overview_zh` | 2,510 | 提取器 13-label 太窄 + 英文页无 translator | `profile_sections.py:32-46,161-197` | portfolio W2b |
| 教授 `paper_summary` 缺失 | 2,200 | 不在默认 ingest + precision 过滤 | `output_summaries.py`，`canonical_writer.py:990` | portfolio W2d |
| 姓名-身份污染（canonical_name_en） | 历史 41% | 页面 prominence 取名欠定；规则层追不上 | `name_selection.py:362-418`，`name_identity_gate.py` | archived name-identity-gate rounds |
| COALESCE 粘性（脏值不覆盖） | — | upsert 不覆盖短/空 | `canonical_writer.py:968-1004` | portfolio W0c（E2） |

相关 spec：`professor-summary-fields`、`professor-fact-extraction`、`professor-profile-field-extraction-integrity`、`professor-post-full-quality-audit`、`professor-list-summary-visibility`、`professor-detail-readability`。

---

## Part 2 — 论文数据爬取与清洗

### 2.1 主页论文抽取（homepage → 发表论文）— 🔴 最大缺口（C1）

这是整个清理的**核心缺口**。主页声明了论文计数，但结构化标题抽取返回 0 → 教师被记为"0 论文"。

**各 seed 0-论文率（最严重的，C1 目标）**：

| seed | 院系 | adapter | 教授 | 0-论文率 |
|---|---|---|---|---|
| 24 | 深圳信息职业技术大学/中德机器人 | suit-sziit | 14 | **100%** |
| 5 | 深圳大学/计算机与软件 | szu-csse-teacher-team | 79 | **97.5%** |
| 44 | 深圳技术大学/人工智能 | sztu-teacher-family | 60 | 78.3% |
| 11 | 深圳大学/物理与光电 | szu-cpoe | 265 | 73.2% |
| 27 | 电子科技大学(深圳)/软件工程 | uestc-yjsjy | 7 | 71.4% |
| 43 | 深圳技术大学/中德智能制造 | sztu | 32 | 68.8% |
| 26/25/28 | 电子科技大学(深圳) 计/电/机 | uestc-yjsjy | — | 54–66% |
| 15 | 深圳大学/材料 | szu | 100 | 47.0% |
| 19/20 | 哈尔滨工业大学(深圳) 计/集成 | hitsz | — | 42–45% |

**根因（按频率）**：
1. **引用模板未被识别** — `extract_publications_from_html` 对该校引用格式返回空（SIGS `.sudy-tab` 就是先例，archived `prof-sigs-tab-template-extraction` / `sigs-official-publications-to-paper-domain`）。**主导原因。**
2. **论文子页未抓取** — LLM follow-link 没选到 publications 子页，只看到 bio（有计数无标题）。
3. **sitewide 过滤误杀** — `_looks_like_sitewide_publication_page` 把合法标题当全校成就页滤掉。
4. 解析 splitting 军备竞赛（C2/C3，~25 splitter，垃圾标题）。

**代码**：`homepage_publications.py`（`extract_publications_from_html`、`_split_title_authors_venue:1142-1451`）、`homepage_ingest.py:1964-1984`（sparse-count-only 登记）、`llm_publication_extractor.py`（contain vs boundary 守卫）。
**相关 spec / change**：`paper-homepage-enrichment-completion`、`professor-sigs-tab-template-extraction`；active `sigs-official-publications-to-paper-domain`、`paper-source-gap-remediation-lanes`；portfolio W1b（解析器边界守卫）、W2c（CMS 覆盖）。

> 注：SIGS 已修（6.6% 0-论文）。模板是**逐校**的——每个高 0-论文率的 seed，基本都要一份针对其引用模板的抽取修复（这才是"每个 seed 定制"的真正落点：**论文抽取模板**，不是 roster 爬虫）。

### 2.2 论文富集 / 清洗 — 🟡 多个缺口

| 缺口 | 根因 | 代码 | spec / portfolio |
|---|---|---|---|
| provider 静默吞错 → 缺摘要/标识符（B1） | OpenAlex/arXiv/S2 失败 → [] | `openalex.py:210-251`，`arxiv.py:34-35` | portfolio W0a |
| 标题解析 web_search 污染（D1，从未被修） | Jaccard≥0.85 放过他文 | `title_resolver.py:337-356,1319-1401` | portfolio W1a |
| DOI 污染（D2，gate 未提交/只查格式） | — | `doi_quality.py`，`title_resolver.py:648-655` | portfolio W0d |
| 重复论文组未消解 | title+year-only 正确地 needs_review | `dataset_candidate_generation.py:903-960` | portfolio W2e |
| 身份门（E1） | ✅ **W0b 已完成**（plausible-title 守卫，119 行已 apply） | `identity_status_writer.py`，`run_paper_identity_scan.py` | change `wire-paper-identity-gate-rejection` |

### 2.3 摘要翻译（summary_zh）— 🟡 大缺口

- **~29,030 篇仍缺 summary_zh**（49,814 中 39,433 缺）；74% 残差是 `skipped_no_abstract`（主页无可用摘要 → 源限制）。
- **代码**：`abstract_translator.py`，`run_paper_summary_zh_backfill.py`（5 lanes），`source_text_quality.py`。
- **相关 spec / change**：`paper-homepage-enrichment-completion`；active `paper-source-gap-remediation-lanes`；用户提议的 Jina-reader fallback（portfolio W2a，前置 W1a+W0a）。

---

## 跨切面

| 缺口 | 说明 | 代码 / 位置 |
|---|---|---|
| **A1 收口闭环**（登记≠修复） | pipeline_issue 永不 resolved；write-lane 不动真缺口 | `dataset_quality_closure.py:492-522` | portfolio W3a |
| **F1 治理滞后** | change-ledger 无 6 月行；index 矩阵停 5/4 | `change-ledger.md`，`docs/index.md` | portfolio W3b |
| 论文侧脏数据在收口报告里隐形 | source_gap 6-lane 未接 pipeline_issue | `source_gap_audit.py:13-19` | portfolio W3a |

---

## 结论：缺口的真实形状

1. **Part 1 roster 层完成**（37 adapter、100% 主页）——**不要再造 roster 爬虫**。
2. **核心缺口 = Part 2.1 各校论文引用模板抽取**（C1）：逐 seed 的 0-论文率修复。这是"每个 seed 定制化"的真正落点——定制**论文抽取模板**，不是名单爬虫。优先级最高的 seed：24（深圳信息 100%）、5（深大计软 97.5%）、44（SZTU AI 78%）、11（深大物光 73%）、25–28（UESTC 54–66%）、19/20（HIT-SZ 42–45%）。
3. **Part 1.2 画像质量** + **Part 2.2 富集**（B1/D1/D2）+ **Part 2.3 摘要翻译**（含 Jina fallback）是并行的次级缺口。
4. **跨切面 A1/F1** 不修则任何采集改进都会被重新堆积/隐形。

> 建议的执行单元：以 **"seed × 论文抽取模板"** 为单位（不是以 root-cause 波次），逐个高 0-论文率 seed 修抽取 + 验证该 seed 的 0-论文率下降。这与 portfolio 的 W2c（CMS 覆盖）+ W1b（解析器）合并为"逐 seed 论文抽取修复"工作流。
