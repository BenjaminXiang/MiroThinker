# Design: Migrate Company Data Agent from API to Qimingpian Export

**Date:** 2026-03-27
**Status:** Draft
**Scope:** `apps/company-data-agent/` + `docs/Company-Data-Agent-PRD.md`

---

## 1. Background and Motivation

The original Company-Data-Agent PRD assumed two enterprise data sources:

1. A "Shenzhen company master list" providing skeleton data (name, credit code, address, industry)
2. Qimingpian API for real-time structured enrichment (business registration, financing, legal risk)

**Problem:** Qimingpian does not offer an API. However, enterprise data can be exported from Qimingpian as xlsx files. These exports contain 42 columns of rich structured data, including much of what the PRD expected from the API (financing rounds, investors, registered capital, legal representative, patent counts, team info, etc.).

**Decision:** Replace both the "master list" concept and the "Qimingpian API enrichment" phase with a single Qimingpian export xlsx as the enterprise list source.

---

## 2. Key Design Decisions

### 2.1 Deduplication Key: Company Name (not Credit Code)

Qimingpian exports do not contain unified social credit codes (统一社会信用代码). The deduplication key changes from `credit_code` to `name` (公司名称).

- Formally registered Chinese company names are unique within the registration system
- Name normalization: strip whitespace, full-width to half-width conversion
- `company_id` format changes from `COMP-{credit_code_hash}` to `COMP-{name_hash}`
- `credit_code` becomes optional in `CompanyRecordBase`

### 2.2 Rich Field Extraction at Import Time

The import phase extracts all available fields from the xlsx into `CompanyRecord`, eliminating the separate "Qimingpian API enrichment" phase.

### 2.3 Web Crawling Retained for Data Updates

Web Crawling is preserved but repurposed: it is no longer a mandatory first-pass enrichment step but a mechanism for subsequent data updates and keeping records fresh.

### 2.4 Qimingpian API Phase Removed

- No `qimingpian` config section (api_key, endpoint, cache_ttl, rate_limit)
- `CompanySource.QIMINGPIAN` renamed to `CompanySource.QIMINGPIAN_EXPORT`
- Phase 0 simplifies from 4 steps to 3: import full data -> Web Crawling updates -> LLM profile generation

---

## 3. Qimingpian Export xlsx Format

### 3.1 File Structure

- **Row 1:** Merged title cell ("专辑项目导出") -- must be skipped
- **Row 2:** Actual column headers (42 columns)
- **Row 3+:** Data rows

### 3.2 Multi-Row Companies

Some companies span multiple rows when they have multiple financing rounds:

- The first row contains all company fields + the latest/primary financing entry
- Continuation rows have empty 序号 and 公司名称 fields, with only financing columns populated (投资轮次, 投资时间, 投资金额, 投资方)

**Merge strategy:**

- Detect continuation rows: 序号 is None AND 公司名称 is None
- Aggregate investors across all rows (deduplicated)
- Use the first row's financing data as the primary record (it typically has the latest round)

### 3.3 Column-to-Field Mapping

| xlsx Column | CompanyRecord Field | Processing |
|---|---|---|
| 公司名称 | `name` | **Required**, dedup key |
| 项目名称 | (stored in extra) | Contains HYPERLINK with qimingpian ID; stored as-is, not parsed |
| 行业领域 | `industry` | Direct map |
| 子领域 | `industry_tags` | Append to tags list |
| 业务 | `product_description` | Short business description |
| 地区 | (fallback for `registered_address`) | Coarse-grained, e.g. "广东省-深圳市" |
| 投资轮次 | `financing_round` | From primary row |
| 投资金额 | `financing_amount` | From primary row |
| 参考转化金额（万人民币） | (new: `financing_amount_cny_wan`) | Normalized amount for sorting |
| 投资方 | `investors` | Aggregated from all rows, deduplicated |
| 注册资金 | `registered_capital` | Direct map |
| 高新企业 | `tech_tags` | If "是", add "高新技术企业" tag |
| 简介 | `product_description` (long form) | Overrides 业务 field if longer |
| Logo链接 | (ignored or stored in extra) | |
| 星级 | (ignored or stored in extra) | |
| 状态 | (ignored or stored in extra) | |
| 成立日期 | `establishment_date` | Parse to date |
| 网址 | `website` | Direct map |
| 法人代表 | `legal_representative` | Direct map |
| 团队 | `team_description` + `key_personnel` | Parse structured team entries |
| 注册地址 | `registered_address` | Overrides 地区 (more precise) |
| 企业联系电话 | (stored in extra) | |
| 联系邮箱 | (stored in extra) | |
| 成立年限 | (derived from establishment_date, ignored) | |
| 参保人数 | (stored in extra) | |
| 股东数 | (stored in extra) | |
| 投资数 | (stored in extra) | |
| 专利数 | `patent_count` | Parse to int |
| 商标数 | (stored in extra) | |
| 著作权 | (stored in extra) | |
| 招聘数 | (stored in extra) | |
| 新闻数 | (stored in extra) | |
| 机构方数量 | (stored in extra) | |
| 融资总次数 | (stored in extra or new field) | |
| 融资总额 | (stored in extra or new field) | |
| 估值 | (stored in extra or new field) | |

### 3.4 Team Field Parsing

The 团队 column contains structured text like:

```
王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。
杨馥诚，职务：董事长，介绍：杨馥诚，旭宏医疗董事长。
```

Parsing strategy:

- Split by newline (`\n`)
- Each entry: extract name (before first `，`), role (after `职务：`), description (after `介绍：`)
- Map to `KeyPersonnelRecord(name=..., role=...)`
- Concatenate all descriptions for `team_description`

---

## 4. Code Changes

### 4.1 Module: `identity/company_identity.py`

- Add `from_company_name(name: str) -> CompanyIdentity`
- Name normalization: strip, full-width to half-width, remove common suffixes for matching
- `company_id` generation: `COMP-{sha256(normalized_name)[:16]}`
- Keep `from_raw_credit_code()` as secondary method (for future use if credit codes become available)

### 4.2 Module: `models/company_record.py`

- `credit_code`: change from `Field(min_length=18, max_length=18)` to `str | None = None`
- Remove credit_code from required field validators (keep format validation when present)
- `CompanySource.QIMINGPIAN` -> `CompanySource.QIMINGPIAN_EXPORT`

### 4.3 Module: `ingest/master_list_parser.py`

- Extend `HEADER_ALIASES` with all 42 Qimingpian export column names
- Change `REQUIRED_CANONICAL_HEADERS` from `{"name", "credit_code"}` to `{"name"}`
- Add `_detect_header_row()`: skip merged title rows, find the actual header row
- Add multi-row merge logic: detect continuation rows, aggregate financing data
- Extend `ParsedMasterListRow` with new fields: `legal_representative`, `registered_capital`, `establishment_date`, `financing_round`, `financing_amount`, `investors`, `patent_count`, `website`, `description`, `team_raw`
- `credit_code` becomes optional in `ParsedMasterListRow`

### 4.4 Module: `importer/skeleton_import.py`

- Change dedup key from `credit_code` to `name`
- `_candidate_record()`: map new parsed fields to `PartialCompanyRecord`
- `_merge_records()`: extend merge logic for new fields (investors aggregation, etc.)

### 4.5 Module: `config/settings.py`

- Remove `qimingpian` API config section
- `company_list_path` remains (now points to Qimingpian export xlsx)

### 4.6 Document: `docs/Company-Data-Agent-PRD.md`

- Section 3 (数据来源): Replace "全深圳企业列表" + "企名片 API" with "企名片导出 xlsx"
- Section 5.2.2 (企名片 API 数据补充): Remove entirely
- Section 5.2.1 (企业列表批量导入): Update to describe rich import from Qimingpian export
- Section 8 (配置): Remove qimingpian API config
- Section 10 (验收标准): Remove "企名片数据覆盖率" metric, adjust others

---

## 5. Updated Pipeline Flow

```
Phase 0: Company Data Collection (Company-Data-Agent)
  Input  -> Qimingpian export xlsx (42 columns, ~1600 companies)
  Step 1 -> Parse xlsx: detect header row, merge multi-row companies, extract all fields
  Step 2 -> Skeleton import: dedup by company name, create PartialCompanyRecords
  Step 3 -> Web Crawling (for data updates, not first-pass enrichment)
  Step 4 -> LLM profile generation (profile_summary from collected data)
  Output -> companies.jsonl + raw/

Phase 0 complete -> Phase 1 (Professor collection) can start
```

---

## 6. Testing

### 6.1 Test Fixture

Create a minimal Qimingpian export xlsx fixture with:

- Merged title row
- 42-column header row
- 3-5 normal company rows
- 1 company with multi-row financing (2-3 continuation rows)
- 1 row with missing 公司名称 (error case)

### 6.2 Test Scenarios

| Test | Description |
|---|---|
| Parse header detection | Skip merged title row, find actual headers |
| Parse normal row | All 42 columns correctly mapped |
| Parse multi-row company | Continuation rows merged, investors aggregated |
| Parse team field | Structured team text parsed into KeyPersonnelRecord list |
| Dedup by name | Two rows with same 公司名称 merged correctly |
| Missing name error | Row without 公司名称 produces parse error |
| Identity from name | `CompanyIdentity.from_company_name()` generates stable ID |
| credit_code optional | CompanyRecord accepts None credit_code |
| Skeleton import integration | End-to-end: xlsx -> parsed rows -> PartialCompanyRecords |

---

## 7. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Company name collision (different companies, same name) | Low (formal registration prevents this) | Log warning, append district if collision detected |
| Qimingpian export format changes | Medium | Header detection is fuzzy-match based; parser validates required columns present |
| Team field parsing failures (inconsistent format) | Medium | Graceful degradation: store raw text in team_description if parsing fails |
| Multi-row detection false positives | Low | Require BOTH 序号 AND 公司名称 to be empty for continuation row |

---

## 8. Out of Scope

- Credit code lookup/enrichment (deferred to future if needed)
- Qimingpian HYPERLINK ID extraction (nice-to-have, not blocking)
- New fields beyond current CompanyRecord model (financing history as structured list, etc.)
- Web Crawling implementation changes (existing design preserved)
