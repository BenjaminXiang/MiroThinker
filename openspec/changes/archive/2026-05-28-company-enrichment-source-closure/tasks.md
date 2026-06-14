## 1. OpenSpec And Baseline

- [x] 1.1 Create design and spec deltas for Company enrichment source closure.
- [x] 1.2 Validate the OpenSpec change with `openspec validate company-enrichment-source-closure --strict`.
- [x] 1.3 Record baseline gaps from current Company contracts, release, Yiou site-filter path, and product-capture absence.

## 2. Release Contract And Key-Person Structure

- [x] 2.1 Add RED tests for optional publish fields on `CompanyRecord` and released `core_facts`.
- [x] 2.2 Add RED tests for key-person `description`, `education_structured`, and `work_experience` preservation from XLSX team raw text.
- [x] 2.3 Extend Company Pydantic contracts and release builder without making optional fields required.
- [x] 2.4 Implement deterministic key-person background promotion and conservative education/work hint extraction.

## 3. Yiou Source Adapter

- [x] 3.1 Add tests for a named Yiou adapter using `data.iyiou.com` fixture/search results.
- [x] 3.2 Implement the Yiou adapter wrapper with source-specific provenance, diagnostics, and no canonical overwrite.
- [x] 3.3 Wire the adapter into an existing or new company enrichment script option.

## 4. Official Product Capture

- [x] 4.1 Add tests for bounded official-site URL discovery and same-host crawl limits.
- [x] 4.2 Add tests for product extraction from official HTML with evidence spans and reviewable quality status.
- [x] 4.3 Add additive product storage/writer support if existing tables cannot represent product-level evidence.
- [x] 4.4 Wire a script path for official product capture by company ID, limit, or XLSX-derived company set.

## 5. E2E And Acceptance

- [x] 5.1 Run focused Company unit/contract tests.
- [x] 5.2 Run an E2E validation with `docs/专辑项目导出1768807339.xlsx`.
- [x] 5.3 Run Yiou and official product live checks when credentials/network allow; otherwise record blockers and fixture-backed confidence.
- [x] 5.4 Run release or retrieval smoke checks proving the new fields/enrichments are consumable.
- [x] 5.5 Update `acceptance.md` and `.agents/runs/company-enrichment-source-closure/verification.md` with commands, results, skipped checks, and remaining risks.
