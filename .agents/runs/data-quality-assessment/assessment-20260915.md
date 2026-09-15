# Data-quality assessment of the live serving corpus (run15 sealed pack)

- Date: 2026-09-15
- Scope: **read-only** assessment of the pack currently served by the canonical-v2 line
- Pack: `/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/`
  (release `candidate-v2-20260913-r1`, `generator_run_id=p4-pack-20260914-v1`, `generated_at=2026-09-14T15:21:16Z`)
- Request: user requirement **R21** — "local-first only works if data quality is good enough; it needs systematic assessment and cleaning."
- This run performed **no cleaning and no writes** to any data directory. All artifacts live under
  `.agents/runs/data-quality-assessment/`.

---

## 1. Method

### 1.1 Access pattern

`sqlite3` CLI is not installed; all access went through the Python `sqlite3` module with an
immutable read-only URI, which cannot create journals or take write locks:

```python
sqlite3.connect('file:/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/lookup.sqlite3?mode=ro&immutable=1', uri=True)
```

`relationships.json` (3.4 GB, single line, no newlines) was **not** loaded whole. It was accessed
with `mmap` + C-level `bytes.find` / `re.finditer`, then the 10,897-element `candidates` array
(21.0 MB, offsets 2,277,657,285 → 2,298,663,179) was sliced out and parsed with `json.loads`.

`index-v2/milvus.db` was **never opened** (live service 18188 holds its single-writer lock).
`index-v2/vector_matrix.npz` was read through `zipfile` member headers only — no array data was
loaded. Only 4.4 MB (`point_ids.npy`) was read in full.

### 1.2 Reproducible commands

```bash
cd /home/longxiang/MiroThinker
D=.agents/runs/data-quality-assessment

# 1) field inventory per domain (outer doc keys, inner lookup_content keys)
python3 $D/scripts/probe_fields.py

# 2) extract compact per-domain JSONL (gzip), resolving {reference_id,name} refs to labels
python3 $D/scripts/extract_domains.py

# 3) per-domain metric scripts
python3 $D/scripts/analysis_company.py
python3 $D/scripts/analysis_professor.py
python3 $D/scripts/analysis_paper.py
python3 $D/scripts/analysis_patent.py

# 4) relationships.json: relationship-type / candidate inventory + edge dump
#    (mmap scan, see relationships-edges-report.txt for the inline script)
# 5) GT coverage against the 41-row workbook
.venv/bin/python ...   # see gt-coverage2.txt, category-support.txt
```

Raw outputs for every step are listed in §5.

### 1.3 Data model discovered (needed to read the metrics correctly)

`lookup_document.document_json.lookup_content` is a JSON **string**. Domain fields are either:

| shape | example | meaning |
|---|---|---|
| scalar | `"name": "深圳市普渡科技股份有限公司"` | literal value |
| reference object | `"industry": {"reference_id":"source-reference:85a1…","name":"物联网"}` | controlled-vocabulary ref; `name` is the label |
| list of reference objects | `"tech_tags": [{"reference_id":"…","name":"具身智能公司"}]` | ref list |
| list of sub-objects | `"applicants": [{"company_name":…,"canonical_company_id":…}]` | structured sub-records |

**A naive completeness scan over the raw JSON overstates completeness**, because most
non-null fields are ref-objects whose `name` may itself be a placeholder string.
Every metric below distinguishes **key-present**, **structurally-filled**, and **effectively-filled
(placeholder text excluded)**.

Reference integrity check: over `industry` / `geography` / `legal_representative` /
`institution` refs (5,257 distinct `reference_id`s) and 4,945 `tech_tags` refs, **zero**
`reference_id → name` collisions and **zero** `name → reference_id` collisions. The reference
layer itself is clean — the dirt is in the labels it points at.

### 1.4 Limits (what this run did NOT measure)

| Not measured | Why | Impact |
|---|---|---|
| Recall against the true world (how many Shenzhen robotics companies *should* be in the pack) | needs an external universe/registry; only a 41-row GT workbook is available | Recall can only be stated for GT entities, not population coverage |
| Vector-space quality (duplicate/near-duplicate vectors, norm distribution, embedding drift) | `matrix.npy` is 1.67 GB and the instruction forbids loading it; only the header was read | Point count and dimensionality are verified; semantic redundancy is not |
| Milvus collection internals (index type, per-collection counts, deleted rows) | `index-v2/milvus.db` is locked by the live service and must not be opened | Index-vs-pack parity is taken from the manifest's `release_verification` (accepted=true, 0 missing/extra/stale points), not independently re-verified |
| Live answer path (which store the runtime actually reads for company→patent) | out of read-only scope; would need to run the service | A finding is raised as "conflict", not as "confirmed runtime bug" |
| Professor→paper attribution correctness (are the 10,773 links the *right* professor?) | needs ground truth per link | Only link *coverage* and duplication are measured |
| Semantic equivalence between `industry=生产制造` and `industry=先进制造` | needs domain taxonomy decision | Reported as overlap counts, not resolved |

---

## 2. Corpus baseline

| artifact | measured | note |
|---|---|---|
| `lookup.sqlite3` documents | **47,068** | company 7,086 · paper 24,520 · patent 11,504 · professor 3,958 |
| `relationships.json` candidates | **10,897** | matches manifest `relationship_set.record_count=10,897` exactly |
| `index-v2/vector_matrix.npz` | **51,026 × 4,096 float64** | Qwen3-Embedding-8B; 43,110 doc points + 7,916 professor points (3,958 × 2 projections) |
| eligibility | all 47,068 `admitted`; 14,130 papers carry the sole limitation `paper_unanchored` | |
| empty index projections | `person`, `technology_concept`, `technology_route` all have `content_sha256 = e3b0c442…98fc1c14` = **SHA-256 of the empty string** | three declared index projections ship zero points by design |

---

## 3. Per-domain metrics

Legend: **KP** = key present in every document (100% of docs carry the key);
**F** = structurally filled (non-null / non-empty); **E** = effective (placeholder text excluded).

### 3.1 company (n = 7,086)

| field | F | rate | E | placeholder hits | note |
|---|---|---|---|---|---|
| name | 7,086 | 100.0% | 7,086 | 0 | 0 duplicate names, 0 duplicate `normalized_name` |
| normalized_name | 7,086 | 100.0% | 7,086 | 0 | |
| aliases | 6,727 | 94.9% | 6,727 | 0 | 6,879 distinct alias strings; 9 aliases shared by >1 company |
| industry | 6,517 | 92.0% | 6,516 | 1 | 41 distinct labels |
| industry_tags | 5,480 | 77.3% | 5,479 | 1 | **100% redundant with `industry`** (see F-09) |
| tech_tags | 5,485 | 77.4% | 5,484 | 1 | 4,945 distinct labels; **max 1 tag per company** |
| geography | 5,491 | 77.5% | 5,491 | 0 | 4,887 are literally `广东省` |
| founded_at | 5,486 | 77.4% | 5,486 | 0 | all parseable, 1980–2025, 0 out-of-range |
| legal_representative | 5,486 | 77.4% | 5,485 | 1 | |
| website | 5,340 | 75.4% | 5,339 | 1 | 12 are bare domains without scheme; 15 are `weibo.com` |
| registered_address | 6,506 | 91.8% | 6,506 | 0 | |
| product_description | 5,368 | 75.8% | 4,419 | 949 | 860 exact `未找到` + 88 glued + 1 prefix |
| profile_summary | 7,086 | 100.0% | 6,377 | 709 | 631 exact `未找到` + 76 glued + 2 prefix |
| technology_route_summary | 7,086 | 100.0% | 5,466 | 1,620 | 326 exact `未找到` + 23 glued + **1,271 English placeholder prefix** |
| team_description | 5,518 | 77.9% | 5,518 | 0 | |
| key_personnel | 851 | 12.0% | 851 | 0 | 1,293 person-rows total |
| credit_code | 0 | **0.0%** | 0 | — | key exists, value is `NoneType` in all 7,086 docs |
| registered_capital | 0 | **0.0%** | 0 | — | same |
| patent_count | 0 | **0.0%** | 0 | — | same |
| products | 0 | **0.0%** | 0 | — | key exists, value is `[]` in all docs |
| business_scenarios | 0 | **0.0%** | 0 | — | same |
| capabilities | 0 | **0.0%** | 0 | — | same |
| financing_events | 0 | **0.0%** | 0 | — | same |
| latest_public_updates | 0 | **0.0%** | 0 | — | same |
| personnel_education | 0 | **0.0%** | 0 | — | same |
| personnel_work_experience | 0 | **0.0%** | 0 | — | same |

Completeness of prose: **76.4% of profiles (5,412 / 7,086) are ≤ 150 characters**;
**48.0% (3,399)** are under 50 characters. With `thin := (profile_summary ≤ 150 chars) OR
(no tech_tags AND no product_description)`, **5,917 / 7,086 = 83.5% of companies are thin.**

`industry` — full 41-label distribution (top 12):

| label | n | | label | n |
|---|---|---|---|---|
| 人工智能 | 1,297 | | 科研及技术服务 | 66 |
| 硬件 | 1,193 | | VR/AR | 62 |
| 生产制造 | 931 | | 大数据 | 56 |
| 先进制造 | 881 | | 电子商务 | 56 |
| 企业服务 | 555 | | 批发零售 | 42 |
| 物联网 | 351 | | 能源电力 | 40 |
| 汽车交通 | 251 | | 教育培训 | 38 |
| 医疗健康 | 249 | | **机器人** | **8** |
| 硬科技 | 72 | | 电子制造 | 3 |
| 金融 | 67 | | `-` (placeholder) | 1 |

`tech_tags` — suffix anatomy over 5,485 labels (70.4% carry a merchandising suffix):

| suffix | n | suffix | n |
|---|---|---|---|
| 研发商 | 1,284 | 生产商 | 485 |
| 服务商 | 777 | 制造商 | 320 |
| 提供商 | 741 | 供应商 | 198 |
| 运营商 | 34 | 方案商 | 16 |
| 集成商 | 8 | | |

Normalization test: case-folding + full-width→half-width + whitespace collapsing merges
**0** `industry_tags` labels and **0** `tech_tags` labels, i.e. the 4,945-variant vocabulary is
not a case/full-width artifact — the labels are genuinely distinct strings.

### 3.2 professor (n = 3,958)

| field | F | rate | E | placeholder hits | note |
|---|---|---|---|---|---|
| name / canonical_name_zh | 3,958 | 100.0% | 3,958 | 0 | 18 duplicate-name groups / 37 entities |
| institution | 3,958 | 100.0% | 3,958 | 0 | only **9 distinct values**, 8 contain 深圳 (2,998 entities) |
| department | 3,958 | 100.0% | **2,770** | 1,188 | 30.0% are `Not supplied by the historical source.` |
| title | 3,958 | 100.0% | **1,443** | 2,515 | 63.5% placeholder; 313 distinct real values |
| email | 3,958 | 100.0% | **2,707** | 1,251 | 31.6% placeholder |
| homepage | 3,958 | 100.0% | 3,940 | 0 | **18 records have `javascript:;`** |
| research_directions | 1,969 | 49.7% | 1,969 | 0 | 10,238 tags, 9,099 distinct (88.9% singletons) |
| profile_summary | 3,958 | 100.0% | 3,956 | 2 | the only substantive professor prose field |
| paper_summary | 3,958 | 100.0% | **0** | 3,958 | **100% placeholder → dead field** |
| patent_summary | 3,958 | 100.0% | **0** | 3,958 | **100% placeholder → dead field** |
| canonical_name_en | 278 | 7.0% | 278 | 0 | |
| paper_count | 235 | 5.9% | 235 | 0 | |
| citation_count | 125 | 3.2% | 125 | 0 | |
| h_index | 123 | 3.1% | 123 | 0 | |
| patent_ids | 0 | 0.0% | 0 | — | key present, always `[]` |
| projects / awards / company_roles / education_history / work_history / affiliation_history / metric_snapshots / contacts / aliases | 0 each | 0.0% | 0 | — | all always `[]` |
| phone / office / lifecycle_state / manual_override | 0 | 0.0% | 0 | — | all always `None` |

`research_directions` junk classification over 10,238 tag instances:

| defect | instances | worst example |
|---|---|---|
| web-nav / boilerplate | 140 | `主讲本科课程： 主讲研究生课程： 教育背景： 工作履历： 主持项目： 代表期刊论文 ： … 上一篇： 没有了 下一篇： 没有了 微信公众…` (×23 identical) |
| sentence fragment (contains clause punctuation) | 294 | `不同取食策略生物的耐热性，仍缺乏系统验证` (×43), `智能控制与先进制造领域的研究及应用，主要研究方向包括学习控制` (×10) |
| truncated with trailing `等` | 121 | `蛹等）` (×43), `多模态图像理解等` (×10), `半导体制造系统等` (×10) |
| too short (≤ 2 chars) | 126 | `1` (×16), `仿生`, `催化`, `精密` |
| too long (> 40 chars) | 313 | embedded work-history blocks |

### 3.3 paper (n = 24,520)

| field | F | rate | note |
|---|---|---|---|
| title | 24,520 | 100.0% | 24,514 distinct after normalization; only 6 duplicate groups (12 rows) |
| year | 24,520 | 100.0% | range 1908–2027; **1 paper dated 2027**; 28 pre-1990 |
| venue | 24,520 | 100.0% | **5,204 distinct labels**; 121 normalization groups spanning 244 labels / **1,979 rows** |
| authors | 24,520 | 100.0% | 156,092 author rows, 59,821 distinct names, avg 6.37/p; **0 rows carry affiliations**; no author IDs |
| doi | 23,976 | 97.8% | **all 23,976 well-formed `10.NNNN/…`, zero duplicates** |
| summary_zh | 17,894 | 73.0% | |
| summary_text | 12,358 | 50.4% | |
| abstract | 11,795 | 48.1% | |
| citation_count | 8,185 | 33.4% | |
| arxiv_id | 499 | 2.0% | |
| professor_ids | 0 | **0.0%** | key present, always `[]` — see F-03 |
| fields_of_study / keywords / references / reference_count / full_texts / identifiers / publications / enrichment_sources / summaries / funders | 0 each | 0.0% | all always `[]` or `None` |
| title_zh / publication_date / tldr / license / oa_status / pdf_path | 0 each | 0.0% | all always `None` |

`paper_unanchored` limitation: **14,130 / 24,520 = 57.6%**.

### 3.4 patent (n = 11,504)

| field | F | rate | note |
|---|---|---|---|
| patent_number | 11,504 | 100.0% | all `CN` + 9–13 digits; **11,504 distinct, 0 duplicates** |
| title | 11,504 | 100.0% | 10,563 distinct; **463 duplicate-value groups covering 1,404 rows** |
| applicants | 11,504 | 100.0% | 12,565 applicant rows; see binding table below |
| publication_date | 11,504 | 100.0% | **only 3 distinct years: 2023 (2,886), 2024 (4,364), 2025 (4,254)** |
| summary_text | 11,504 | 100.0% | 104–280 chars, hard-truncated (see F-11) |
| abstract | 9,573 | 83.2% | |
| technology_effect | 9,359 | 81.4% | |
| patent_type | 9,573 | 83.2% | only `发明` (6,321) and `实用新型` (3,252); **no 外观设计** |
| filing_date | 1,931 | 16.8% | complementary to `patent_type`/`abstract` — two disjoint source families |
| company_ids | 0 | **0.0%** | key present, always `[]` |
| inventors | 0 | **0.0%** | always `[]` |
| ipc_codes | 0 | **0.0%** | always `[]` — no classification available |
| grant_date / title_en / technical_summaries / milestones | 0 each | 0.0% | always `None` / `[]` |

applicant binding (the in-document store):

| metric | value |
|---|---|
| applicant rows total | 12,565 (avg 1.09 / patent) |
| rows with `canonical_company_id` | **7,614** (60.6%) |
| rows whose `company_name` is `null` | 4,951 |
| distinct `canonical_company_id` | **960** |
| distinct applicant `company_name` strings | 961 |
| patents with ≥1 bound company | **7,042** (61.2%) |
| patents whose applicant rows have **zero** binding | **4,462** (38.8%) |

### 3.5 Cross-domain relationships (`relationships.json` → `candidates`, 10,897 records)

| relationship type | edges | distinct sources | distinct targets | distinct pairs |
|---|---|---|---|---|
| `professor_attributed_to_paper` | 10,773 | 1,019 professors (25.7% of 3,958) | 10,390 papers (42.4% of 24,520) | 10,742 (**31 duplicate pairs**) |
| `patent_has_applicant` | **123** | 123 patents | **49 companies** | 123 |
| `professor_company_role` | **1** | 1 professor | 1 company | 1 |

Papers-per-professor distribution over the attributed links: 1 → 108 professors, 2 → 79,
3 → 87, 4 → 104, 5 → 76, …; maximum 217 papers for a single professor.
Every edge carries exactly 1 `evidence_binding`; `observed_at` is `2026` for all 10,897.

Three further relationship types are declared in the type registry but ship **no** candidate
records: `paper_has_author`, `patent_has_inventor`, `paper_references_paper` (plus the
infrastructure types `company_in_industry`, `company_located_in_geography`,
`patent_has_ipc_classification`, … each with exactly 1 occurrence, which is the registry
declaration itself, not an instance).

---

## 4. Reconciliation with previously recorded numbers

| prior figure | this run | verdict |
|---|---|---|
| `research_directions` fill rate 37% | **49.7%** structurally filled (1,969 / 3,958) | **changed** — the 37% figure presumably counted differently (possibly pre-placeholder-filter on a wider denominator, or an older run). Under any reading, ≤ 50%. |
| 嘉立创 / 一博 `tech_tags = None` | confirmed: `tech_tags=[]` for 深圳嘉立创科技集团股份有限公司 **and** 深圳市一博科技股份有限公司; `product_description` is empty for 嘉立创 and **3 chars** for 一博 | **consistent** |
| 4,945 distinct `tech_tags` spellings | **4,945** distinct labels over 5,485 instances | **exact match** |
| 2,771 tech_tags ending in `研发商` | **1,284** | **not reproducible** — under any of these matchers: exact `endswith('研发商')` = 1,284; `研发商|研发企业|研发公司|研制商` ≈ 1,350. No matcher found that yields 2,771. The all-suffix total is 3,863. |
| placeholder report professor = 12,872 | **12,872** | **exact match** |
| placeholder report company = 3,097 | **3,097** = 3,092 (prefix/exact/glued families) + 5 lone `-` values in `aliases`/`industry`/`industry_tags`/`legal_representative`/`tech_tags`/`website` | **exact match** (the 5-value gap is fully explained) |
| whole-value `未找到` exact = 1,817 | **1,817** (all in company) | **exact match** |
| whole-value `未找到` prefix = 2 | **2** | **exact match** |
| glued runs = 189 | **189** (company: product_description 88, profile_summary 76, technology_route_summary 23; patent: abstract 1, summary_text 1) | **exact match** |
| 普渡 has 3 identities, industries contradict | confirmed: 成都市普渡机器人有限公司 (`industry=None`), 深圳市普渡科技股份有限公司 (`物流运输`), 深圳市普渡科技有限公司 (`机器人`) | **consistent** |
| company→patent bindings = 7,078 | in-document bindings: **7,614 rows / 7,042 patents / 960 companies**. Relationship-layer bindings: **123 edges / 49 companies** | **not reproducible as stated** — 7,078 matches neither store. 7,042 (patents) is closest; the 7,078 figure likely predates the current projection. The 123-edge relationship-layer number is the actionable discrepancy. |
| professor→company = 1 | **1** (`professor_company_role`) | **exact match** |
| `industry=机器人` covers only 8 companies | **8** | **exact match** |
| 4 GT companies provably absent | **4**: 鼎纪电子, 穿山甲机器人, 广东瓦力科技有限公司, 灵启万物（深圳）科技有限公司 | **exact match** |
| 2 GT companies "thin" | ≥ 4 confirmed thin: 嘉立创 (profile 103 chars, no tech_tags/geo/founded_at), 一博 (98 chars, product_description 3 chars), 深南电路 (77 chars, no geo/founded_at), 深圳无界智航科技 (`technology_route_summary` = 16 chars) | **consistent, understated** — see §5 F-02 for the population-level number |
| `paper_unanchored` 14,130 | **14,130 / 24,520 = 57.6%** | **exact match** |

---

## 5. Findings, ordered by impact on user-visible correctness / recall

### F-01 — The relationship layer publishes 1.7% of the patent↔company bindings the patent documents already contain (critical)

- **Symptom**: `relationships.json` carries only **123** `patent_has_applicant` edges covering
  **49** companies. The patent documents themselves carry **7,614** applicant rows with a
  `canonical_company_id`, covering **7,042** patents and **960** companies. The graph store and
  the document store disagree by a factor of ~60 on edges and ~20 on companies.
- **Scale**: 4,462 / 11,504 patents (38.8%) have zero company binding anywhere; **6,920** patents
  are bound *only* in the document store. Overlap check: 122 of the 123 relationship patents are
  also bound in-document; 1 relationship patent and 1 relationship company appear in the graph
  but not in any document binding. In-document distinct (patent, company) pairs = **7,611**
  (7,614 rows, i.e. 3 duplicate rows).
- **Evidence**: `.agents/runs/data-quality-assessment/relationships-edges-report.txt`
  (type × count table); `.agents/runs/data-quality-assessment/applicants-authors.txt`
  (in-document binding table).
- **Attribution guess**: projection drop, not collection loss. The registry declares the type
  `patent_has_applicant` but only produced 123 *typed relationship assertions*
  (`assertion_input_kind = "typed_relationship_assertion"`, n=124) while the professor→paper
  family uses `shared_source_relationship_assertion` (n=10,773). The applicant bindings live in
  `applicants[].canonical_company_id` and were never mapped into the relationship registry.
- **Suggested action**: decide the authoritative store, then either (a) project all in-document
  applicant bindings into relationship candidates, or (b) have the answer path read
  `applicants[].canonical_company_id` directly. Before changing anything, confirm which store
  the runtime reads today.

### F-02 — Prose is systemically thin: 83.5% of companies have no usable description (critical)

- **Symptom**: `profile_summary` is 100% present but **76.4% are ≤ 150 characters** and **48.0%
  are under 50 characters**. Combining with the empty-tech-tags case,
  **5,917 / 7,086 = 83.5% of companies are thin** under
  `thin := profile_summary ≤ 150 chars OR (tech_tags empty AND product_description empty)`.
- **Scale / example**: the GT-critical PCB trio —
  深圳嘉立创科技集团股份有限公司 (`profile_summary` 103 chars, `product_description` empty,
  `tech_tags=[]`, `geography=None`, `founded_at=None`),
  深圳市一博科技股份有限公司 (98 chars, `product_description` 3 chars, `geography=None`,
  `founded_at=None`), 深南电路股份有限公司 (77 chars, no geo/founded_at).
  None of the three can answer "when was it founded / where is it / what exactly does it make".
- **Evidence**: `.agents/runs/data-quality-assessment/thin-records-company.txt`
  (length histogram + per-entity dump).
- **Attribution guess**: collection gap. The `s12c-r7-company-workbook-supplement` batch only
  covers part of the base; the rest falls back to a generated one-line summary.
- **Suggested action**: prioritise backfill by (a) GT entities, (b) `industry=机器人`,
  (c) the top-N by `tech_tags` specificity. Treat "profile_summary ≥ 400 chars AND ≥ 1 of
  {product_description, team_description, tech_tags} non-empty" as the admission bar for
  a company to be answerable.

### F-03 — `paper.professor_ids` is empty for all 24,520 papers; the only professor↔paper link lives in one relationship family covering 42% of papers (high)

- **Symptom**: the paper document's own `professor_ids` field is `[]` in **100%** of records;
  author `affiliations` are empty in **0/156,092** rows. The only link is
  `professor_attributed_to_paper` (10,773 edges / 10,390 papers).
- **Scale**: 14,130 papers (57.6%) are unanchored; 2,939 professors (74.3%) have zero papers.
- **Evidence**: `.agents/runs/data-quality-assessment/paper-metrics.txt`,
  `relationships-edges-report.txt`.
- **Attribution guess**: projection drop (document) + collection gap (relationship). The
  `authors[]` rows carry no identity field at all, so authorship cannot be resolved from the
  document; it must come from the `p4-professor-paper-links-v1` batch.
- **Suggested action**: backfill `paper.professor_ids` from the relationship family so a single
  paper record answers "who wrote this"; investigate whether the 14,130 unanchored papers are
  legitimately out-of-scope (foreign authors, no Shenzhen professor) or a link-loss.

### F-04 — `tech_tags` is a single, near-unique, never-reusable label; it cannot support category retrieval (high)

- **Symptom**: 4,945 distinct labels for 5,485 filled companies → **90.2% are singletons** and
  **max 1 tag per company**. 70.4% carry a merchandising suffix
  (`研发商` 1,284, `服务商` 777, `提供商` 741, `生产商` 485, `制造商` 320, `供应商` 198, …).
- **Recall consequence**: the GT question "中国有哪些成熟的酒店送餐机器人供应商" —
  the string `送餐` appears in **0** tag/industry fields pack-wide (19 companies mention it in
  free text); `配送机器人` matches **1** company; `餐饮机器人` matches **1**. All 8 companies with
  `industry=机器人` have **empty `tech_tags`**.
- **Evidence**: `.agents/runs/data-quality-assessment/company-metrics.txt` (tech_tags section),
  `category-support.txt`.
- **Attribution guess**: vocabulary design — tags were generated per-company as a marketing
  phrase, never mapped onto a shared taxonomy. Normalization by case/full-width merges **0**
  labels, so this is not a formatting problem.
- **Suggested action**: derive a controlled technology taxonomy (e.g. `品类 × 产品形态 × 环节`)
  and project each company's `tech_tags` into it; keep the original string as an alias. Do **not**
  attempt to clean 4,945 free-text labels by rule.

### F-05 — `industry` has no discriminative power: 41 overlapping labels, and identical businesses land in different buckets (high)

- **Symptom**: `人工智能` (1,297), `硬件` (1,193), `生产制造` (931) and `先进制造` (881) absorb 61% of
  companies while the genuinely informative categories are near-empty: **`机器人` = 8**,
  `电子制造` = 3, `信息安全` = 1, `服装纺织` = 1, `开采` = 1.
- **Consistency evidence**: within the PCB cluster — 深圳嘉立创 `电子制造`, 深圳市一博 `电子制造`,
  深南电路 `电子制造`, but 深圳市兴森快捷 `生产制造`, 崇达技术 `生产制造`, 深圳市星河电路 `生产制造`,
  深圳市顺易捷 `生产制造`. Same business, three labels. Conversely 普渡科技 is filed under
  `物流运输` while its own `tech_tags` says `室内外配送机器人研发商`.
- **Evidence**: `.agents/runs/data-quality-assessment/company-metrics.txt` (full 41-label table),
  `category-support.txt` (PCB cluster dump).
- **Attribution guess**: the label comes from the upstream source's own categorisation, recorded
  without normalisation; `industry_tags` was projected as a copy rather than a secondary axis.
- **Suggested action**: re-derive `industry` from a fixed taxonomy, or stop using it as a filter
  and rely on the new technology taxonomy (F-04). At minimum, split the four dominant buckets.

### F-06 — Two professor fields are 100% placeholder text: a naive completeness metric reports them as complete (high)

- **Symptom**: `paper_summary` = `No dedicated summary was supplied by the full-column workbook
  source.` in **3,958 / 3,958** records; `patent_summary` identical. `title` is placeholder in
  **2,515** (63.5%), `email` in **1,251** (31.6%), `department` in **1,188** (30.0%).
- **Scale**: professor placeholder total **12,872** value hits; company **3,097**.
- **Evidence**: `.agents/runs/data-quality-assessment/placeholder-recount.txt`
  (per-field family counts, exact match with the sealer report).
- **Attribution guess**: projection/pipeline artifact — an upstream backfill wrote an English
  sentence into a field instead of `null`. Because the pipeline treats the string as a value,
  downstream "is this field filled?" checks pass.
- **Suggested action**: normalize all four placeholder *families* to `null` at ingest, and make
  any completeness metric placeholder-aware. This is a pure rule-based clean with an exact
  expected count — the ideal first D0 change.

### F-07 — `geography` is stored at province granularity for 89% of companies (high for a Shenzhen product)

- **Symptom**: of 5,491 filled `geography` values, **4,887 are exactly `广东省`** and only **554** are
  `广东省-深圳市`. 1,595 companies have no geography at all.
- **Format inconsistency inside the 556 specific values**: `广东省-珠海` (missing 市),
  `苏州市` (missing province), `-开曼群岛` (leading dash).
- **Evidence**: `.agents/runs/data-quality-assessment/company-detail.txt` (geography section).
- **Attribution guess**: collection — the source workbook only recorded province for most rows.
- **Suggested action**: normalize to `省-市` (or a single `city` field) and backfill city from
  `registered_address`, which is **91.8% filled** and already contains a full district-level
  address. This is rule-based and high-leverage: it turns 4,887 unusable province values into
  usable city values.

### F-08 — Patent coverage is a 3-year window, with two disjoint source families (medium-high)

- **Symptom**: `publication_date` has only **3 distinct years — 2023, 2024, 2025**. `filing_date`
  is present for only 1,931 records and `patent_type`/`abstract` for 9,573 — exactly
  complementary, so the corpus is a union of two source shapes.
- **Scale**: any "专利 in 2020" query returns nothing; there is no 外观设计 patent type and no
  IPC classification (`ipc_codes` empty in 100%).
- **Evidence**: `.agents/runs/data-quality-assessment/patent-metrics.txt`.
- **Attribution guess**: collection scope — the source batch (`p4-patent-full-v1`) ingested a
  bounded window; the two families come from different upstream exports.
- **Suggested action**: state the coverage window in the product's answer templates
  ("本地专利库覆盖 2023–2025"), and treat patent recall outside the window as a web-search
  fallback trigger rather than a local miss.

### F-09 — `industry_tags` duplicates `industry` exactly; 46 declared fields are always empty (medium)

- **Symptom A**: for all 5,480 companies that have both, `industry_tags[0] == industry` —
  **0 disagreements, 0 extra information**. 1,037 companies have `industry` without
  `industry_tags`.
- **Symptom B**: 46 fields are declared in every document but never populated:
  `credit_code`, `registered_capital`, `patent_count`, `products`, `business_scenarios`,
  `capabilities`, `financing_events`, `latest_public_updates`, `personnel_education`,
  `personnel_work_experience` (company, 10 fields — all `NoneType`, or `[]` in 7,086/7,086);
  `phone`, `office`, `patent_ids`, `projects`, `awards`, `company_roles`, `education_history`,
  `work_history`, `affiliation_history`, `metric_snapshots`, `contacts`, `aliases`,
  `lifecycle_state`, `manual_override` (professor, 14);
  `title_zh`, `reference_count`, `professor_ids`, `fields_of_study`, `keywords`, `tldr`,
  `identifiers`, `publications`, `references`, `full_texts`, `license`, `oa_status`, `pdf_path`,
  `publication_date` (paper, 14);
  `title_en`, `inventors`, `company_ids`, `professor_ids`, `ipc_codes`, `grant_date`,
  `technical_summaries`, `milestones` (patent, 8).
- **Evidence**: `.agents/runs/data-quality-assessment/company-detail.txt`
  (industry/industry_tags consistency, `_supplementary` keys).
- **Attribution guess**: the catalog schema declares fields that no source batch writes;
  `industry_tags` is a projection echo.
- **Suggested action**: split into "schema-declared but unpopulated" (decide: populate or stop
  declaring — the model may be hallucinating availability) vs "genuine duplicate". `credit_code`
  in particular is the natural join key for company identity and is 100% absent.

### F-10 — Professor `research_directions` contains scraped page boilerplate and truncated fragments (medium)

- **Symptom**: of 10,238 tag instances, **140 are verbatim website navigation blocks**
  (`主讲本科课程：…上一篇：没有了 下一篇：没有了 微信公众号…`), **294 are sentence fragments**
  (e.g. `不同取食策略生物的耐热性，仍缺乏系统验证` ×43), **121 are truncated with a trailing `等`**
  (e.g. `蛹等）` ×43 — almost certainly a mangled "…（如蛹等）"), and **126 are ≤ 2 characters**
  (`1` ×16).
- **Scale**: 9,099 distinct values for 10,238 instances — 88.9% singletons, so there is no
  reusable vocabulary to fall back on.
- **Evidence**: `.agents/runs/data-quality-assessment/identity-and-vocab.txt`
  (`== professor research_directions junk patterns ==`).
- **Attribution guess**: parse error — the homepage scraper captured layout text as if it were
  a research-direction list, without a delimiter or length guard.
- **Suggested action**: rule-based length/pattern quarantine (drop tags matching the nav-block
  pattern, drop ≤ 2 chars, strip trailing `等`/`等）`), then manual re-extraction for the affected
  professors. Pair with a scraper fix so the defect does not return.

### F-11 — Structural defects made visible by the shape checks (medium/low, all rule-based)

| id | defect | count |
|---|---|---|
| a | `filing_date > publication_date` inversions | 0 (clean) |
| b | professor `homepage = "javascript:;"` | 18 |
| c | company `website` without `http` scheme | 12 |
| d | company `website` pointing at `weibo.com` | 15 |
| e | 4,951 patent applicant rows with `company_name = null` | 4,951 |
| f | patent `summary_text` hard-truncated to ≤ 280 chars ending mid-sentence | 11,504 |
| g | `title` duplicated across distinct patents (generic short titles) | 463 groups / 1,404 rows |
| h | `venue` label variants for one journal (worst: `arXiv (Cornell University)` 418 vs `arXiv` 242) | 121 groups / 1,979 rows |
| i | paper `year` in the future (2027) | 1 |
| j | alias string shared by > 1 company | 9 |
| k | duplicate `professor_attributed_to_paper` (professor, paper) pairs | 31 |
| l | duplicate-name professor entities | 18 groups / 37 entities |
| m | `_supplementary` present on only 899 / 7,086 companies and 4 / 3,958 professors | 903 |

---

## 6. Cleaning backlog

### 6.1 Rule-based — belongs in code with a test (D0 candidates, highest value first)

Every item below has an **exact expected count** measured this run, so the acceptance assertion is
a regression test, not an eyeball check.

| # | clean | expected effect | acceptance assertion |
|---|---|---|---|
| D0-1 | Normalize placeholder families to `null` | company **3,097** hits across 9 fields; professor **12,872** hits across 5 fields | after clean, `count(value matches placeholder family) == 0` for all domains; `professor.paper_summary` effective fill drops from 3,958 to 0 and must be re-typed as optional |
| D0-2 | Repair `未找到` glue damage | **189** runs (`company.product_description` 88, `company.profile_summary` 76, `company.technology_route_summary` 23, `patent.abstract` 1, `patent.summary_text` 1); whole-value `未找到` **1,817** all in company | after clean, `未找到` appears only inside legitimate text; the 1,817 whole-value cases are `null`; a sample of 30 repair candidates is human-reviewed |
| D0-3 | Drop `industry_tags` as a duplicate axis | 5,480 redundant values | projection test asserts `industry_tags` is either absent or semantically distinct from `industry` |
| D0-4 | Quarantine junk `research_directions` tags | ≥ 140 nav-block, 126 too-short, 121 trailing-`等` instances | after clean, no tag matches the nav-block regex, no tag ≤ 2 chars; the 43 `蛹等）` instances are re-extracted manually |
| D0-5 | Normalize professor `homepage` | 18 `javascript:;` → `null` | `count(homepage not matching ^https?://) == 0` |
| D0-6 | Normalize company `website` | 12 without scheme → `https://`; 15 `weibo.com` flagged as `social` not `official` | scheme-prefix test passes; social-vs-official flag added |
| D0-7 | Normalize `geography` to `省-市` and backfill city from `registered_address` | 4,887 province-only values; also 3 malformed values (`广东省-珠海`, `苏州市`, `-开曼群岛`) | after backfill, `count(geography == '广东省') == 0`; ≥ 90% of companies resolve to a city |
| D0-8 | Merge paper `venue` label variants | 121 groups / 244 labels / **1,979** rows | `count(distinct venue-label after norm) <= 5,083`; arXiv variants collapse to one label |
| D0-9 | Deduplicate `professor_attributed_to_paper` pairs | 31 duplicate pairs | edge count drops 10,773 → 10,742 |
| D0-10 | Drop semantically-empty fields from the published schema | 46 always-empty fields: company 10, professor 14, paper 14, patent 8 | a schema test asserts every declared field is populated in ≥ 1 record of the release |
| D0-11 | De-duplicate `patent.applicants[].company_name = null` rows | 4,951 rows | `count(applicant rows with company_name is null) == 0` |
| D0-12 | Prompt/parse guard against the `未找到` substitution | prevents recurrence | the ingest test feeds a source value containing literal `未找到` and asserts no mid-string substitution occurs |

### 6.2 Needs collection or human decision (cannot be rule-cleaned)

| # | item | scale | what is needed |
|---|---|---|---|
| D1-1 | company prose backfill | **5,917 / 7,086 thin** | new source batches; prioritise GT entities and `industry=机器人`; set the admission bar per F-02 |
| D1-2 | patent↔company graph projection | 6,920 patents bound only in-document; 123 vs 7,611 edges | product decision (F-01) + rebuild of the relationship projection |
| D1-3 | paper↔professor linkage for the unanchored 57.6% | 14,130 papers | decide whether unanchored papers are in scope; if yes, a new attribution batch |
| D1-4 | controlled technology taxonomy | 4,945 free-text labels | domain expert defines the taxonomy; then map, keep originals as aliases |
| D1-5 | `industry` re-categorisation | 41 labels, 4 labels absorb 61% | product decision on whether `industry` is a filter at all |
| D1-6 | patent coverage window | 2023–2025 only | source expansion, or accept + surface the window in answers |
| D1-7 | IPC classification for patents | 11,504 records, 0 codes | new enrichment source |
| D1-8 | professor metrics (citation/h-index/paper_count) | 3.1–5.9% coverage | new enrichment source |
| D1-9 | company `credit_code` / `registered_capital` | 0% | authoritative registry source — also unlocks company identity dedup |
| D1-10 | professor identity splits | 18 name-duplicate groups / 37 entities, at least 2 confirmed same-person splits (胡君杰 CUHK-SZ ×2, 黄宪达 CUHK-SZ ×2) | human review of the 37 entities; needs a durable person-identity key |
| D1-11 | GT entities missing from the corpus | 4 companies (鼎纪电子, 穿山甲机器人, 广东瓦力科技有限公司, 灵启万物（深圳）科技有限公司) + 2 professors (许晋诚 — the GT answer to 问题7, 穆世龙 — 无界智航 legal rep) | targeted collection |
| D1-12 | paper author identity | 156,092 author rows, 59,821 distinct names, 0 affiliations, no IDs (`Lei Wang` ×255) | ORCID/Scopus-level source; without it author-based retrieval cannot be trusted |
| D1-13 | patent `summary_text` truncation | all 11,504 cut at ≤ 280 chars | regenerate summaries without the hard cap |

---

## 7. Artifacts produced

All under `.agents/runs/data-quality-assessment/`:

| file | content |
|---|---|
| `assessment-20260915.md` | this report |
| `scripts/dqlib.py` | shared loaders + placeholder classifier |
| `scripts/probe_fields.py` | field-key inventory per domain |
| `scripts/extract_domains.py` | pack → compact per-domain JSONL (gzip) |
| `scripts/analysis_company.py` | company metrics |
| `scripts/analysis_professor.py` | professor metrics |
| `scripts/analysis_paper.py` | paper metrics |
| `scripts/analysis_patent.py` | patent metrics |
| `scripts/scan_relationships_keys.py` | superseded by the mmap approach; kept for reference |
| `field-keys-probe.txt` | full key lists per domain |
| `company-metrics.txt` / `company-detail.txt` | company fill/vocab/category analysis |
| `professor-metrics.txt` / `professor-dup-detail.txt` | professor fill/vocab/identity analysis |
| `paper-metrics.txt` | paper fill/vocab/duplication analysis |
| `patent-metrics.txt` / `patent-summary-quality.txt` | patent fill/binding analysis |
| `applicants-authors.txt` | patent applicant binding + paper author analysis |
| `ref-stability.txt` | `reference_id ↔ name` integrity check |
| `placeholder-recount.txt` | independent placeholder recount vs the sealer report |
| `relationships-candidates.txt` | relationship type / candidate inventory |
| `relationships-instances.txt` | parsed `candidates` array analysis |
| `relationships-edges-report.txt` | edge dump + coverage report |
| `index-projection-plan.txt` | manifest index/object/relationship plan |
| `vector-matrix-header.txt` | npz header + point-id count (no array data) |
| `gt-coverage.txt` / `gt-coverage2.txt` | GT coverage checks |
| `thin-records-company.txt` | thin-record definition + per-entity dump |
| `identity-and-vocab.txt` | identity spread, venue variants, tag junk |
| `category-support.txt` | category query support |
| `data/*.jsonl.gz` | extracted per-domain records (company 3.5 MB, paper 14.4 MB, patent 3.7 MB, professor 1.5 MB) |
| `data/relationship_edges.jsonl.gz` | 10,897 relationship edges |

Intermediates under `data/` are regenerable in ~20 s from `extract_domains.py` and can be deleted
once the cleaning work is planned.
