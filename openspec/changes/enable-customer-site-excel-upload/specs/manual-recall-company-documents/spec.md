# Spec delta: manual-recall-company-documents (XLSX structure + ingest)

## ADDED Requirements

### Requirement: Excel uploads are analysed before ingest

The company-document upload SHALL detect the header row and map columns to one of the four public
domains (company, professor, patent, paper) before writing anything. The preview SHALL return the
detected domain, confidence, column mapping and row count. The structured-ingest endpoint SHALL
write the mapped rows into the corresponding raw collection table with review status.

#### Scenario: Detect a company workbook

- **WHEN** an operator previews a workbook with `公司名称/统一社会信用代码/网址/简介`
- **THEN** preview returns `analysis.domain="company"`, `confidence="high"`
- **AND** the mapping includes `company_name`, `credit_code`, `website`, `description`

#### Scenario: Detect other domains

- **WHEN** the workbook has professor, patent or paper headers
- **THEN** preview returns `professor`, `patent` or `paper` respectively

#### Scenario: Structured ingest

- **WHEN** the operator calls `POST /company-documents/structured` with the workbook
- **THEN** company rows upsert into `company` by credit code, professor rows into `professor`,
  patent rows into `patent`, paper rows into `paper`
- **AND** the response reports `rows_inserted`, `rows_updated`, `rows_skipped`
- **AND** all rows carry `quality_status='needs_review'`

#### Scenario: Unsupported or invalid content

- **WHEN** the file is not valid XLSX or no domain can be detected
- **THEN** preview/structured ingest returns 422 and nothing is persisted

#### Scenario: Manual recall fallback

- **WHEN** the structured endpoint succeeds and the manual-recall store is mounted
- **THEN** a sidecar document is also written so the upload appears in the admin document list
- **AND** chat evidence retention remains a separate, known limitation
