## ADDED Requirements

### Requirement: Implausible-title rejection via rule-based scan

The system SHALL transition `paper.identity_status` to `rejected` for a `prof_page_only` paper whose `title_clean` is flagged by `paper/title_quality.is_clearly_garbage_paper_title` (a new high-precision classifier in the same module; the broad `is_plausible_paper_title` is reused unchanged by W0b), via a dedicated title-cleanup scan that does NOT invoke an LLM. The scan SHALL NOT reject papers with plausible titles (left to the W0b identity gate) NOR papers already `identity_status in {rejected, merged}`.

#### Scenario: Garbage-title prof-page-only paper is rejected
- **WHEN** a `prof_page_only` paper's `title_clean` is flagged by `is_clearly_garbage_paper_title` (e.g. "Co-supervised PhD student", "011 (IF: 26.8") and `identity_status NOT IN {rejected, merged}`
- **THEN** the title-cleanup scan transitions `paper.identity_status` to `rejected`

#### Scenario: Plausible-title paper is not touched
- **WHEN** a `prof_page_only` paper's `title_clean` is NOT flagged by `is_clearly_garbage_paper_title`
- **THEN** the title-cleanup scan leaves `identity_status` unchanged (the W0b identity gate handles it)

#### Scenario: Already rejected or merged paper is skipped
- **WHEN** a paper already has `identity_status in {rejected, merged}`
- **THEN** the title-cleanup scan skips it (no double-processing)

#### Scenario: Scan uses no LLM
- **WHEN** the title-cleanup scan runs
- **THEN** it invokes only the rule-based `is_clearly_garbage_paper_title` classifier and makes no LLM calls

### Requirement: Title-cleanup rejection evidence and traceability

For each applied title-cleanup rejection, the system SHALL file a `pipeline_issue` row at stage `title_cleanup` (distinguished from W0b's `identity_gate` stage), `reported_by='paper_title_cleanup_scan'`, with `run_id` and the implausible-title reason recorded in `evidence_snapshot`. The rejection SHALL set `identity_status='rejected'` only and MUST NOT mutate `quality_status`.

#### Scenario: Applied rejection files a distinct pipeline_issue
- **WHEN** the title-cleanup scan rejects a paper via `--apply`
- **THEN** a `pipeline_issue` row exists at stage `title_cleanup` / `reported_by='paper_title_cleanup_scan'` with `run_id`, distinct from any W0b `identity_gate` issue on the same paper

#### Scenario: Rejection does not mutate quality_status
- **WHEN** the title-cleanup scan sets `identity_status='rejected'`
- **THEN** `paper.quality_status` is unchanged

### Requirement: Rejected and merged papers are excluded from retrieval

The system SHALL exclude rejected (and merged) papers from Milvus retrieval via the existing `paper/milvus_backfill._is_indexable_paper` filter (`identity_status in {rejected, merged}`), unchanged. A re-backfill MUST follow an applied rejection for it to take effect on already-indexed rows.

#### Scenario: Milvus backfill skips title-cleanup-rejected papers
- **WHEN** a Milvus backfill selects candidate papers after a title-cleanup apply
- **THEN** rows rejected by the title-cleanup scan are excluded from the index

### Requirement: Admin paper list default-excludes rejected and merged

The admin `/paper` list SHALL default-exclude `identity_status in {rejected, merged}` so that W0b-rejected, title-cleanup-rejected, and merged papers do not appear by default. The list SHALL expose `identity_status` in its response and SHALL allow admins to explicitly include `rejected`/`merged` via the existing filter UI for review/restore.

#### Scenario: /paper default view hides rejected and merged
- **WHEN** the admin `/paper` list is requested without an explicit `identity_status` filter
- **THEN** papers with `identity_status in {rejected, merged}` are excluded from the response

#### Scenario: Admin can opt in to review rejected papers
- **WHEN** an admin requests the `/paper` list with an `identity_status` filter including `rejected`
- **THEN** rejected papers appear in the response for review/restore

### Requirement: Title-cleanup scan is dry-run by default behind an independent flag

The system SHALL provide a title-cleanup scan that is dry-run by default (no writes unless `--apply`), records each per-row decision to a JSONL archive, and reports counts. The scan SHALL be gated by an independent environment flag `PAPER_TITLE_CLEANUP_ENABLED` (default off), separate from `PAPER_IDENTITY_GATE_ENABLED`.

#### Scenario: Default invocation performs no writes
- **WHEN** the title-cleanup scan is run without `--apply`
- **THEN** no `paper.identity_status` value is changed and a JSONL of would-be decisions plus counts is produced

#### Scenario: Flag disabled skips the scan
- **WHEN** `PAPER_TITLE_CLEANUP_ENABLED` is set to a falsy value
- **THEN** the scan exits without writing

#### Scenario: Apply writes only implausible-title rejections
- **WHEN** the scan is run with `--apply` and `PAPER_TITLE_CLEANUP_ENABLED` enabled
- **THEN** only `prof_page_only` papers flagged by `is_clearly_garbage_paper_title(title_clean)` have `identity_status` set to `rejected`
