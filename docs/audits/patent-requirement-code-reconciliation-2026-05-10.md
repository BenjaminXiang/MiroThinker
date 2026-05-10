---
title: Patent Data Agent — Requirement-Code Reconciliation
date: 2026-05-10
status: active
type: requirement_code_reconciliation
domain: patent
canonical_sources:
  - docs/Patent-Data-Agent-PRD.md
  - docs/Data-Agent-Shared-Spec.md
evaluated_commit: e101294
related:
  - docs/data-agent-domain-index.md
  - openspec/debt-register.md
  - docs/solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md
---

# Patent Requirement-Code Reconciliation

## 1. Scope

This report compares the canonical requirement sources for the Patent data-agent domain against the current implementation as of commit `e101294`. Patent is the cleanest of the four domains per Phase 1A inventory: single-source PRD, no in-flight OpenSpec change, no audit, and W13-3 dogfood produced gold-standard E2E (1931/1931 ready, summary_text 100%, 0 fallback, 76 company-patent links, chat HTTP 200). The report distinguishes "automated test coverage" from "dogfood validation" so the maturity picture is not overstated. No behavior change, code change, or PRD rewrite is performed. Acceptance gaps are surfaced in §5; only documents-and-requirements debt is recorded in §7.

## 2. Canonical Sources

| Source | Role | Status |
|---|---|---|
| `docs/Patent-Data-Agent-PRD.md` | Primary domain requirement source | canonical |
| `docs/Data-Agent-Shared-Spec.md` | Cross-domain shared requirements | shared baseline |
| `docs/quality-status-compatibility.md` | reference | reference only |

## 3. Code Entry Points

| Area | Path | Notes |
|---|---|---|
| Canonical contract model | `apps/miroflow-agent/src/data_agents/contracts.py:342-403` | `PatentRecord` Pydantic model (id, title, applicants min_length=1, patent_type required, summary_text required, evidence min_length=1, identity_status, quality_status). Validator enforces `filing_date OR publication_date`. |
| Import (XLSX) | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:23-300` | Header alias resolver, multi-applicant `; ；\n` token split, patent_number normalization (uppercase + strip whitespace), Chinese patent-type mapping, Excel-date parser. `_REQUIRED_COLUMNS = ("title", "applicants")`. |
| Release (in-memory) | `apps/miroflow-agent/src/data_agents/patent/release.py:35-113` | Builds `PatentRecord`s from import rows, calls `link_company_ids`, `link_professor_ids`, `build_summary_text`, `build_stable_id("pat", patent_number or title|applicants)`. |
| Quality status (release) | `apps/miroflow-agent/src/data_agents/patent/release.py:228-237` | `ready` iff `title` AND first applicant AND `filing_date`; else `needs_review`. |
| Identity status | `apps/miroflow-agent/src/data_agents/patent/release.py:186-189` | `confirmed` iff `patent_number` is non-empty; else `unverified`. |
| Postgres writer | `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:49-143` | `upsert_patent` — `INSERT ... ON CONFLICT (patent_id) DO UPDATE`; refuses dry-run sentinel run_id; writes `applicants_parsed` / `inventors_parsed` as JSONB; writes `summary_text_method` and `identity_status`. |
| Company-patent link writer | `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:146-212` | `upsert_company_patent_link` — validates `link_role`, `evidence_source_type`, `link_status`, `verified_by`; bounded `match_reason`. Idempotent on `(company_id, patent_id, link_role)`. |
| Applicant linkage (3-tier) | `apps/miroflow-agent/src/data_agents/patent/linkage.py:30-91` | Exact name → normalized name → alias map; tagged `patent_xlsx_applicant_exact_match` vs `patent_xlsx_applicant_normalized_match`; bounded match_reason ≤ 200 chars. |
| Professor linkage | `apps/miroflow-agent/src/data_agents/patent/linkage.py:94-101` | `link_professor_ids` via `normalize_person_name`; produces `professor_ids` list (not yet written to `professor_patent_link` table). |
| LLM summary | `apps/miroflow-agent/src/data_agents/patent/summary_llm.py:25-59` | OpenAI-compatible client, gemma4 settings, system prompt "150-300 字 / 问题背景, 核心方法, 技术效果"; `_MIN_LLM_SUMMARY_LENGTH=50`, `_MAX_LLM_SUMMARY_LENGTH=300`; falls back to template on failure or short output. |
| Fallback summary template | `apps/miroflow-agent/src/data_agents/patent/summary_llm.py:62-75` | Deterministic template using title + abstract + technology_effect + patent_type. |
| Storage (Milvus) | `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py:362-422` | `ensure_patent_profiles_collection` — fields id (PK 64), patent_number 64, title 512, abstract 2048, technology_effect 1024, patent_type 32, ipc_codes 512, profile_vector 4096-dim COSINE AUTOINDEX. |
| Vectorization | `apps/miroflow-agent/src/data_agents/patent/vectorizer.py:62-114` | `PatentVectorizer.vectorize_and_upsert` composes title + abstract (or technology_effect fallback). |
| RAG service routing | `apps/miroflow-agent/src/data_agents/service/retrieval.py:20`, `:52-60`, `:554-568`, `:572-579` | `_VALID_DOMAINS` includes patent; `_PATENT_OUTPUT_FIELDS = id, patent_number, title, abstract, technology_effect, patent_type, ipc_codes`; `_row_to_evidence` snippet = title + "\n" + abstract[:500]. |
| Cross-domain SQL (related) | `apps/miroflow-agent/src/data_agents/service/retrieval.py:414-472` | `_professor_patents_sql` / `_patent_professors_sql` (via `professor_patent_link`); `_company_patents_sql` / `_patent_companies_sql` (via `company_patent_link`); both filter `link_status IN ('verified', 'candidate')`. |
| Quality-status filter (retrieval) | `apps/miroflow-agent/src/data_agents/service/retrieval.py:61-66`, `:581-637` | Patent rows looked up in `patent.quality_status`; `ready`-only filter via `FILTER_BY_QUALITY_STATUS` env. |
| Admin browse | `apps/admin-console/backend/api/domains.py:299-326` | `PATENT_SELECT_SQL` exposes patent columns including quality_status, summary_text, summary_text_method, run_id, ipc_codes. |
| Chat lookup (A_patent_profile) | `apps/admin-console/backend/services/chat_context.py:159-174`, `:196-200` | `lookup_patent` (patent_id / patent_number / title_clean ILIKE); `answer_patent_profile` template. |
| Chat lookup (A_patent_by_applicant) | `apps/admin-console/backend/api/chat.py:1539-1554`, `:1722-1742` | `_lookup_patents_by_applicant` (applicants_raw ILIKE), `_answer_patent_list` template. |
| Chat classifier (patent rules) | `apps/admin-console/backend/api/chat.py:311-333`, `:367-377`, `:389-395` | A by patent number (`_CLASSIFIER_CN_PATENT_RE`), A by ambiguous patent title (G), G fallback for "X 是 哪一件 专利". |
| Migrations | `apps/miroflow-agent/alembic/versions/V004_init_paper_patent_domain.py:101-146`, `V005b_init_cross_domain_relations.py:193-348`, `V019_add_quality_status_and_patent_summary.py`, `V020_add_identity_status_paper_patent.py` | V004 base patent table; V005b professor_patent_link + company_patent_link; V019 quality_status + summary_text + summary_text_method; V020 identity_status. |
| Tests (unit) | `apps/miroflow-agent/tests/data_agents/patent/` (10 files) | import_xlsx, release, summary_llm, vectorizer, canonical_writer, canonical_writer_identity_status, canonical_writer_company_patent_link, linkage_alias_match, linkage_multi_applicant, exact_backfill. |
| Tests (scripts / e2e harness) | `apps/miroflow-agent/tests/scripts/test_run_patent_release_e2e.py`, `test_run_patent_release_e2e_pg.py`, `test_run_milvus_backfill_patent.py` | Mock-Postgres release E2E + Milvus backfill harness. |
| Tests (cross-domain) | `apps/miroflow-agent/tests/data_agents/service/test_retrieval_company_patent.py`, `test_retrieval_get_object.py`, `test_retrieval_get_related.py`, `test_retrieval_quality_filter.py`; `apps/miroflow-agent/tests/data_agents/test_run_id_wiring.py` | Patent retrieval / get_object / get_related / quality filter; sentinel-run_id rejection. |
| Tests (chat) | `apps/admin-console/tests/test_chat_v1.py:146-193`, `test_chat_g_clarification.py:257-348`, `test_chat_multi_domain_entity_stack.py:103-154`, `test_data_api_quality_status.py:88-139`, `test_domains_postgres.py:141-170` | Chat patent A_by_applicant fallback; G clarification; entity stack; quality_status exposure; admin detail SQL. |

## 4. Requirement-Code Matrix

Status legend: ✅ implemented + covered by automated test · 🟡 partial / unclear · 🚧 implemented (incl. dogfood-validated) but no automated test · ❌ missing · ⛔ deprecated / out of scope.

| ID | Requirement (concise) | PRD section | Code evidence | Test evidence (note: automated test, dogfood, or none) | Status | Gap |
|---|---|---|---|---|---|---|
| R1 | Stable ID with `PAT-` prefix | §四.4.1 / Shared §4.1 | `apps/miroflow-agent/src/data_agents/patent/release.py:66-69` (`build_stable_id("pat", ...)`); `apps/miroflow-agent/src/data_agents/normalization.py:35-39` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_release.py:65` (`record.id.startswith("PAT-")`) | ✅ | — |
| R2 | `title` required, non-empty | §四.4.1 / §七.7.1.1 | `apps/miroflow-agent/src/data_agents/contracts.py:344` (`title: NonEmptyStr`); `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:158-160` (`return "missing_title"`) | automated: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:163` (skip_reasons["missing_title"]) | ✅ | — |
| R3 | `applicants` required, non-empty list | §四.4.1 / §七.7.1.2 | `apps/miroflow-agent/src/data_agents/contracts.py:348` (`Field(min_length=1)`); `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:161-163` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:164` (skip_reasons["missing_applicants"]) | ✅ | — |
| R4 | `summary_text` required (user-readable) | §四.4.1 / §四.4.2 / §七.7.1.3 / Shared §4.3 patent block | `apps/miroflow-agent/src/data_agents/contracts.py:359` (`summary_text: NonEmptyStr`); `apps/miroflow-agent/src/data_agents/patent/release.py:56-59` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_release.py:69` (assert summary_text); dogfood: `docs/solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md` 1931/1931 = 100% | ✅ | — |
| R5 | LLM-generated summary 150–300 字 (3-axis: 问题背景 / 核心方法 / 技术效果); falls back deterministically | §四.4.2 / §五.5.5 | `apps/miroflow-agent/src/data_agents/patent/summary_llm.py:19-22, :25-59, :62-75` (`_MIN_LLM_SUMMARY_LENGTH=50`, `_MAX_LLM_SUMMARY_LENGTH=300`, system prompt) | automated: `apps/miroflow-agent/tests/data_agents/patent/test_summary_llm.py:41-89` (5 cases: valid, truncate, short, raise, prompt content); dogfood: 0 fallback in 1931 records | ✅ | — |
| R6 | `summary_text_method` ∈ `{llm, fallback_template}` recorded | §四.4.2 (implicit, evidence-traceable) / Shared §7.2 | `apps/miroflow-agent/src/data_agents/contracts.py:11`; `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:46, :220-222`; `apps/miroflow-agent/alembic/versions/V019_add_quality_status_and_patent_summary.py:55-63` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_summary_llm.py:47, :63, :74` (method assertions) | ✅ | — |
| R7 | `patent_number` normalization (CN + digits + letter; uppercase, no whitespace) | §四.4.1 (note) | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:232-236` (`text.replace(" ", "").upper()`) | automated: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:156` (`"cn12345a" → "CN12345A"`) | 🟡 | Normalization is uppercase + whitespace strip only; the documented `CN`+digits+letter format is not validated/enforced (no regex check, foreign or non-CN strings pass through unchanged). |
| R8 | `patent_type` standardization (发明 / 实用新型 / 外观设计) | §四.4.1 / §五.5.3 | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:239-249`; canonical normalize: `apps/miroflow-agent/src/data_agents/patent/release.py:124-143` (`_PATENT_TYPE_CANONICAL = {发明, 实用新型, 外观, PCT, 其他}`); migration check `apps/miroflow-agent/alembic/versions/V004_init_paper_patent_domain.py:39, :138-141` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:55, :159` (实用新型 / 发明) | 🟡 | Two distinct domains: (a) import normalizes to {发明, 实用新型, 外观设计, raw}; (b) canonical writer remaps to {发明, 实用新型, 外观, PCT, 其他} (V004 enum). PRD says 外观设计; canonical column stores 外观. Behavior is correct end-to-end but the PRD term and the canonical enum disagree. |
| R9 | Date fields parsed (`filing_date`, `publication_date`) | §四.4.1 / §五.5.3 / §七.7.1.4 | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:273-299` (Excel serial + ISO + slash) | automated: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:53-54` (date(2025,8,8)/date(2024,8,8)) | ✅ | — |
| R10 | At least one date present (filing_date OR publication_date) | §七.7.1.4 / Shared §7.2 patent block | `apps/miroflow-agent/src/data_agents/contracts.py:365-369` (`validate_patent_dates`) | automated: indirectly via `apps/miroflow-agent/tests/data_agents/patent/test_release.py` (records construct) — direct negative assertion missing | 🟡 | Validator exists but no test asserts the ValueError on `filing_date=None AND publication_date=None`. |
| R11 | Multi-applicant token split & dedup | §四.4.1 (列表) / §五.5.3 / §六.6.1 | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:21, :252-270` (`_TOKEN_SPLIT_RE = [;；\n]+`); `apps/miroflow-agent/src/data_agents/patent/release.py:216-225` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:64-72` (split into 2); `apps/miroflow-agent/tests/data_agents/patent/test_linkage_multi_applicant.py:8-19` | ✅ | — |
| R12 | De-duplication by patent_number (primary) | §五.5.4 priority 1 | `apps/miroflow-agent/src/data_agents/patent/release.py:67-69` (stable id rooted on patent_number); canonical writer ON CONFLICT on `patent_id`; V004 `uq_patent_patent_number` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer.py:47-58` (idempotent upsert); `apps/miroflow-agent/tests/data_agents/patent/test_exact_backfill.py:23-54` (merge by id across workbooks) | ✅ | — |
| R13 | De-duplication by title-similarity + applicant overlap (secondary) | §五.5.4 priority 2 | _none_ — `_merge_models_by_id` only merges on stable id; no fuzzy title/applicant overlap dedup | none | ❌ | Title-similarity + applicant-overlap dedup path not implemented. Stable-id collision (when patent_number is missing) collapses identical title+applicants concatenations only. |
| R14 | Company linkage (3 tiers: exact → normalized → alias) | §六.6.1 | `apps/miroflow-agent/src/data_agents/patent/linkage.py:30-91` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_linkage_alias_match.py:6-65` (3 cases); `test_linkage_multi_applicant.py:22-31` | ✅ | — |
| R15 | Company-patent link Postgres writer with evidence_source_type, match_reason, link_role, link_status | §六.6.3 / Shared §6.1 layer 3 | `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:146-212`; `V005b_init_cross_domain_relations.py:278-348` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer_company_patent_link.py:10-74` (idempotent, invalid role/source/empty reason); dogfood: 76/76 = 100% writes | ✅ | — |
| R16 | Professor linkage by inventor name | §六.6.2 | `apps/miroflow-agent/src/data_agents/patent/linkage.py:94-101`; `apps/miroflow-agent/src/data_agents/patent/release.py:84` | none (no patent-side test for `link_professor_ids`); dogfood: not exercised because `inventors=[]` is hardcoded (R20) | 🚧 | Helper exists but is unreachable in the release pipeline because inventors are hardcoded `[]` (see R20). No automated test directly invokes `link_professor_ids` on patent input. |
| R17 | `professor_patent_link` Postgres writer / persistence | §六.6.2 / §六.6.3 / Shared §4.3 patent block | `V005b_init_cross_domain_relations.py:193-276` (table + indexes + FKs exist); read SQL `apps/miroflow-agent/src/data_agents/service/retrieval.py:414-442` | none | ❌ | Schema and read path exist, but no `upsert_professor_patent_link` writer is defined and no ingestion path writes to the table. `professor_ids` field on PatentRecord is never persisted into a relation row. |
| R18 | Cross-domain identity status (V020 patent) | Shared §5.5 (hallucination prevention; cross-domain w13-12) | `apps/miroflow-agent/src/data_agents/patent/release.py:186-189`; `apps/miroflow-agent/alembic/versions/V020_add_identity_status_paper_patent.py:40-54` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer_identity_status.py:37-56` (confirmed/unverified); `apps/miroflow-agent/tests/storage/test_v020_migration.py` | ✅ | — |
| R19 | Confidence-gated relation write (link_status candidate vs verified) | §六.6.3 | canonical writer defaults `link_status="candidate"` (`apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:154`); release-time pipeline writes `candidate` (`apps/miroflow-agent/scripts/run_patent_release_e2e.py:271`); promotion to `verified` not implemented in release path | automated: `apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer_company_patent_link.py:23` (default candidate); dogfood: 76 candidate links | 🟡 | Writes default to `candidate`. No code path promotes to `verified` for patent links. PRD asks "置信度足够才落正式关联" — current behavior is "always candidate". |
| R20 | Inventors extracted and linked | §四.4.1 (`inventors`) / §六.6.2 | `apps/miroflow-agent/src/data_agents/patent/release.py:55, :84` (`inventors: list[str] = []` hardcoded) | none | ❌ | Inventors are intentionally hardcoded to `[]` regardless of source — current xlsx export has no inventors column header alias defined (no entry in `_COLUMN_HEADER_ALIASES`). Professor linkage (R16) is unreachable as a result. |
| R21 | IPC codes parsed and persisted | §四.4.1 (`ipc_codes`) / §五.5.3 (IPC parsing) | `apps/miroflow-agent/src/data_agents/patent/release.py:82` (`ipc_codes=[]` hardcoded); table column exists `V004:120-124`; vectorizer serializes ipc_codes (`apps/miroflow-agent/src/data_agents/patent/vectorizer.py:133-140`) | none (no patent-side IPC parsing test) | ❌ | IPC codes never extracted from xlsx (no header alias for "IPC 分类" in `_COLUMN_HEADER_ALIASES`); always written as `[]`. Schema/vectorizer/Milvus field carry IPC but population is missing. |
| R22 | Structured 4-axis summary (`what / problem / method / effect`) — optional Phase 1 | §四.4.2 (optional structured) | _none_ | none | ⛔ | Explicitly optional in PRD ("一期最小要求是稳定的 `summary_text`"). Out of Phase-1 scope. |
| R23 | Evidence array per row (xlsx_import source_type, source_file, fetched_at, snippet, confidence) | Shared §4.5 | `apps/miroflow-agent/src/data_agents/contracts.py:361` (`evidence: list[Evidence] = Field(min_length=1)`); `apps/miroflow-agent/src/data_agents/patent/release.py:87-95` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_release.py:72` (any source_type==xlsx_import) | ✅ | — |
| R24 | `last_updated` timestamp | §四.4.1 / Shared §4.2 | `apps/miroflow-agent/src/data_agents/patent/release.py:96`; canonical writer uses `record.last_updated` | implicit via release tests (`apps/miroflow-agent/tests/data_agents/patent/test_release.py:53-77`) | ✅ | — |
| R25 | `run_id` traceability (V007 + non-sentinel guard) | Shared §4.2 / Shared §7.2 | `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:55, :138`; `apps/miroflow-agent/src/data_agents/storage/postgres/pipeline_run.py` (require_real_run_id); `apps/miroflow-agent/scripts/run_patent_release_e2e.py:239-294` (open/close pipeline_run) | automated: `apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer.py:61-71` (sentinel rejection); `apps/miroflow-agent/tests/data_agents/test_run_id_wiring.py:33-143` (writer requires run_id, rejects sentinel) | ✅ | — |
| R26 | `quality_status` ∈ canonical 4 values, set on release | Shared §4.2 / Shared §7.2 / `quality-status-compatibility.md` | `apps/miroflow-agent/src/data_agents/patent/release.py:228-237`; check constraint `apps/miroflow-agent/alembic/versions/V019_add_quality_status_and_patent_summary.py:21-47` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_canonical_writer.py:74-83` (ready / needs_review); `apps/miroflow-agent/tests/storage/test_v019_migration.py`; dogfood: 1931/1931 ready | ✅ | Note: V019 enum allows 6 values (`needs_review, ready, low_confidence, needs_enrichment, partial, rejected`) while shared spec lists only 4 canonical values (`partial, rejected` not in shared spec); release-side computation only emits `ready` or `needs_review` so this is a latent column-type / spec drift in V019, not a behavior gap. |
| R27 | Quality-status filter in retrieval (`ready`-only default) | Shared §7.2 / Agentic-RAG | `apps/miroflow-agent/src/data_agents/service/retrieval.py:138-141, :581-637` | automated: `apps/miroflow-agent/tests/data_agents/service/test_retrieval_quality_filter.py` | ✅ | — |
| R28 | Milvus `patent_profiles` collection populated, COSINE 4096-dim | Shared §6.2 | `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py:362-422`; `apps/miroflow-agent/src/data_agents/patent/vectorizer.py:62-114`; `apps/miroflow-agent/scripts/run_milvus_backfill.py:393-485` | automated: `apps/miroflow-agent/tests/data_agents/patent/test_vectorizer.py:49-115`; `apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_patent.py:42-122`; dogfood: 1931/1931 backfilled in 32.92s | ✅ | — |
| R29 | RAG service routes patent semantic queries | §二.2.2 / Shared §4.6 | `apps/miroflow-agent/src/data_agents/service/retrieval.py:20, :52-60, :554-568, :572-579` | automated: `apps/miroflow-agent/tests/data_agents/service/test_retrieval_company_patent.py:111-145` (retrieve patent + metadata); `test_retrieval_get_object.py`, `test_retrieval_get_related.py` | ✅ | — |
| R30 | Cross-domain related: company ↔ patent | §六.6.1 / §二.2.2 | `apps/miroflow-agent/src/data_agents/service/retrieval.py:343-345, :444-472` | automated: `apps/miroflow-agent/tests/data_agents/service/test_retrieval_get_related.py:53-54` ((company,patent) and (patent,company) cases) | ✅ | — |
| R31 | Cross-domain related: professor ↔ patent | §六.6.2 / §二.2.2 | `apps/miroflow-agent/src/data_agents/service/retrieval.py:341-342, :414-442` | automated: `apps/miroflow-agent/tests/data_agents/service/test_retrieval_get_related.py:53-54` (professor,patent cases — read path only) | 🟡 | Read SQL is unit-tested but no rows are ever written into `professor_patent_link` (R17) — the path is structurally there but always returns `[]` in production. Test asserts SQL shape, not end-to-end behavior. |
| R32 | A_patent_by_applicant chat path ("X 有什么专利") | §二.2.2 (企业关联跳转) / Agentic-RAG A | `apps/admin-console/backend/api/chat.py:1539-1554, :1722-1742, :3335-3358, :415-423` | automated: `apps/admin-console/tests/test_chat_v1.py:146-193` (template fallback + pipeline_issue); dogfood: `docs/solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md` (chat HTTP 200, 广和通 query) | ✅ | — |
| R33 | A_patent_profile chat path (by patent_number) | §二.2.2 / Agentic-RAG A | `apps/admin-console/backend/api/chat.py:311-317, :367-377`; `apps/admin-console/backend/services/chat_context.py:159-200` | automated: `apps/admin-console/tests/test_chat_g_clarification.py:308-348` (entity_id_hint bypasses G); `test_chat_multi_domain_entity_stack.py:103-130` | ✅ | — |
| R34 | G clarification for ambiguous patent title | §二.2.2 / Agentic-RAG G | `apps/admin-console/backend/api/chat.py:389-395` | automated: `apps/admin-console/tests/test_chat_g_clarification.py:257-305` | ✅ | — |
| R35 | Admin-console patent browse / detail with quality_status, summary_text, run_id | §二.2.2 / Shared §4.2 | `apps/admin-console/backend/api/domains.py:299-326` | automated: `apps/admin-console/tests/test_data_api_quality_status.py:88-139`; `test_domains_postgres.py:141-170` | ✅ | — |
| R36 | XLSX import-coverage acceptance ≥ 95% | §十 (acceptance) | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:79-89` produces import_report; W13-3 e2e shows 1931/1931 = 100% post-import | none (no automated coverage threshold test); dogfood: `docs/solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md` | 🚧 | Coverage met by dogfood. No CI assertion that future runs maintain ≥95%. |
| R37 | summary_text 完整率 ≥ 90% acceptance | §十 (acceptance) | `apps/miroflow-agent/src/data_agents/patent/release.py:56-59`; `_calculate_quality_status` requires non-empty summary path | dogfood: 1931/1931 = 100% (W13-3 doc); none automated | 🚧 | Met by dogfood. No automated coverage assertion. |
| R38 | Company-link 准确率 ≥ 90% (manual labeled set ≥ 100) | §十 (acceptance) | applicant linkage path produces evidence-tagged links | dogfood: 76/1931 = 3.9% multi-applicant hit rate (W13-3 §4 explicitly defers normalize follow-up); no manual-labeled precision yet | ❌ | Acceptance precision not measured. BL-Patent-001 (applicant normalize follow-up) and BL-Patent-002 (link precision) per `docs/data-agent-domain-index.md`. |
| R39 | Professor-link 准确率 ≥ 85% (manual labeled set ≥ 50) | §十 (acceptance) | _none_ — inventors/professor_ids never populated end-to-end (R17, R20) | none | ❌ | Cannot measure: writer/parsing absent. |
| R40 | Dedup 准确率 ≥ 95% (≥ 100 known dup pairs) | §十 (acceptance) | `_merge_models_by_id` collapses by stable id only | none (no labeled dup-pair set or test) | ❌ | No labeled dup test set; secondary dedup (R13) absent. |
| R41 | Top-5 相关率 ≥ 85% on patent retrieval test set (≥ 50 queries) | §十 (acceptance) | `apps/miroflow-agent/src/data_agents/service/retrieval.py` retrieval pipeline | none (no patent Top-5 eval CSV; company has one, patent does not per `docs/Data-Agent-Shared-Spec.md:100-101` and `docs/data-agent-domain-index.md`) | ❌ | No patent Top-5 eval test set produced. Company has 50-query CSV pending labeling; patent has dogfood (`广和通` HTTP 200) but no labeled relevance set. |
| R42 | Sample patent file `2025-12-05 专利.xlsx` parses cleanly | §三.3.1 | path referenced from `apps/miroflow-agent/scripts/run_patent_release_e2e.py:40-42`; `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:16-18` | automated: `test_import_patent_xlsx_reads_real_rows_despite_broken_read_only_dimensions` (1930/1930 records_parsed; `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py:34-40`) | ✅ | — |
| R43 | Phase-1 default = full import (no narrow pre-filter) | §三.3.2 | `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py:117-124` only requires title + applicants; no IPC / robotics / company-linked pre-filter | release tests admit all rows that meet title+applicants | ✅ | — |
| R44 | Web Search / public-page auxiliary supplement | §三.3.3 / §五.5.6 | _none specific to patent_; shared `providers/web_search.py` available; chat E-type uses Serper. No patent-specific auxiliary backfill code path. | none | 🟡 | Shared capability exists but is not invoked by patent ingest. PRD says "辅助补充, 不是主流程" — no production patent-side use. |
| R45 | Configuration keys (`require_summary_text`, `company_link_enabled`, `professor_link_enabled`, `web_search_enabled`, `import_full_export`) | §八 | _none in code_ — no Hydra/YAML or constants file enumerates these toggles for patent | none | 🟡 | The PRD documents config knobs that are not surfaced as runtime configuration; behavior is hardcoded (full import; company linking always on; professor linking effectively disabled by R20; web search not wired). Likely an aspirational PRD section. |
| R46 | Monthly update cadence; key-stable updates | §九 | `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py:91-114` (ON CONFLICT updates); `apps/miroflow-agent/src/data_agents/patent/exact_backfill.py` supplemental workbooks | automated: `apps/miroflow-agent/tests/data_agents/patent/test_exact_backfill.py:23-54`; `test_canonical_writer.py:47-58` (idempotent) | 🚧 | Re-import is idempotent and key-stable. No automated test specifically asserts monthly cadence behavior, and no schedule is in CI/cron. |

## 5. Findings

### 5.1 Implemented and covered by automated tests (✅)

R1, R2, R3, R4, R5, R6, R9, R11, R12, R14, R15, R18, R23, R24, R25, R26, R27, R28, R29, R30, R32, R33, R34, R35, R42, R43 — 26 of 46 requirements.

The contract layer (`PatentRecord`), import (`import_xlsx.py`), release (`release.py`), Postgres canonical writer (`canonical_writer.py`), 3-tier company linkage, summary LLM + fallback, identity_status, quality_status, run_id sentinel guard, Milvus `patent_profiles` collection (4096-dim COSINE), retrieval-service patent branch, A_patent_by_applicant + A_patent_profile + G chat paths, and admin-console browse are all unit/integration-tested. The W13-3 e2e (1931/1931 ready, 0 fallback, chat HTTP 200) corroborates real production behavior, but the green-tick status above relies on the unit tests, not the e2e log.

### 5.2 Partially implemented (🟡)

- **R7 — patent_number format validation**: `_normalize_patent_number` only uppercases and strips whitespace; PRD's `CN`+digits+letter format is not regex-enforced. Foreign or malformed numbers pass through. Low risk for current corpus (xlsx export is uniform), but contract is weaker than PRD.
- **R8 — `patent_type` canonical drift**: import normalizes 外观→外观设计 (`import_xlsx.py:246`), but the canonical Postgres enum (V004) and the writer-side normalizer (`release.py:_PATENT_TYPE_CANONICAL`) use 外观. PRD lists 外观设计. End-to-end behavior is consistent (writer maps 外观设计 → 外观 before insert), but PRD vs canonical-enum vocabulary disagrees. Doc-fix candidate.
- **R10 — date validator negative test**: `validate_patent_dates` exists but no automated test covers the failure path. Low-risk but a small test gap.
- **R19 — link_status verified promotion**: All `company_patent_link` rows default to `candidate`. PRD §六.6.3 ("置信度足够才落正式关联") requires a confidence-driven promotion to `verified`, which is not implemented. Dogfood passes only because chat surfaces both `candidate` and `verified`.
- **R26 — V019 enum vs shared spec drift**: V019 allows 6 values; shared spec lists 4 canonical values. Release pipeline only emits `ready` / `needs_review`, so behavior is correct. Doc-fix candidate (mention `partial, rejected` are migration-only legacy values).
- **R31 — professor↔patent end-to-end**: read SQL is tested, write side is missing (see §5.4 R17/R20).
- **R44 — web search auxiliary**: shared infrastructure exists; patent ingest never invokes it.
- **R45 — config knobs**: PRD lists `import_full_export`, `require_summary_text`, `company_link_enabled`, `professor_link_enabled`, `web_search_enabled` but no runtime toggle is wired. Behavior is hardcoded.

### 5.3 Dogfood-validated but no automated test (🚧)

- **R36 — import coverage ≥ 95%**: 1931/1931 = 100% per W13-3, but no automated assertion that future imports maintain the threshold.
- **R37 — summary_text completeness ≥ 90%**: 100% per W13-3; no automated assertion.
- **R46 — monthly update cadence**: idempotency is unit-tested; cadence itself is operational and uncovered by tests.

### 5.4 Missing or unclear (❌)

- **R13 — secondary dedup (title-similarity + applicant overlap)**: not implemented; only stable-id collapse on patent_number-or-(title|applicants) hash works.
- **R17 — `professor_patent_link` Postgres writer**: schema and read SQL exist, but no `upsert_professor_patent_link`. The relationship is permanently empty in production.
- **R20 — inventors extracted from xlsx**: hardcoded `inventors=[]` because no inventor column header alias is registered. Cascades to R16 (professor linkage) and R39 (professor-link precision).
- **R21 — IPC codes parsed**: hardcoded `ipc_codes=[]`. Schema/vectorizer/Milvus carry the field but it is never populated.
- **R38 — company-link precision ≥ 90%**: no labeled set; corresponds to inventory blocker BL-Patent-001 / BL-Patent-002.
- **R39 — professor-link precision ≥ 85%**: cannot measure (depends on R17/R20).
- **R40 — dedup precision ≥ 95%**: no labeled dup-pair set.
- **R41 — Top-5 retrieval ≥ 85%**: no labeled query set; only 1-query dogfood validation.

### 5.5 Test gaps

In addition to the 🚧 entries above, three small unit-test gaps would round out the suite without any code change:

- Negative test for `PatentRecord.validate_patent_dates` (R10).
- Direct test of `link_professor_ids` on the patent code path (R16).
- Constructive test that `_merge_models_by_id` correctly collapses two same-`patent_number` workbook rows (R12 has indirect coverage via `test_exact_backfill.py`).

These are not blockers; recording them so the suite mirrors the matrix.

### 5.6 Documentation drift

- **`patent_type` vocabulary** (R8): PRD says 外观设计; V004 enum and `_PATENT_TYPE_CANONICAL` say 外观. Either align PRD vocabulary with the canonical enum or expand V004 enum. Doc-debt candidate (§7).
- **V019 enum vs shared §7.2** (R26): V019 allows `partial, rejected`; shared spec lists 4. Document the migration-only legacy values or trim the enum. Doc-debt candidate (§7).
- **Config knobs (§八)** (R45): PRD lists toggles that have no runtime equivalent. Either wire them (code change, out of scope) or trim PRD §八 (doc change).
- **W13-3 solutions doc references `.agents/specs/2026-05-02-w13-12-paper-patent-identity-status.md`** which is per Phase 1A inventory a frozen legacy spec; the cross-domain debt entry already covered by `agents-specs-frozen-but-uncategorized-001` and the cross-domain Paper-Patent identity-status status quo in `paper-companion-design-relationship-001`. No new debt needed here.

### 5.7 Deprecated / candidate-for-removal (⛔)

- **R22 — structured 4-axis summary** (`what / problem / method / effect`): explicitly optional in PRD; not implemented; no plan to land. Out of Phase 1.

## 6. Recommended Follow-up

| Follow-up | Type | Suggested owner artifact |
|---|---|---|
| Implement `_merge_models_by_id` with title-similarity + applicant-overlap secondary dedup (R13) | code implementation | new OpenSpec change `patent-secondary-dedup` |
| Add inventor xlsx column alias + parsing; remove `inventors=[]` hardcode (R20) | code implementation | new OpenSpec change `patent-inventor-extraction` (prerequisite for R16/R17/R39) |
| Implement `upsert_professor_patent_link` writer + wire into release pipeline (R17) | code implementation | same change as R20 (or sequel) |
| Add IPC code xlsx column alias + parsing + write `ipc_codes` (R21) | code implementation | new OpenSpec change `patent-ipc-extraction` |
| Add link_status promotion path (candidate → verified) using applicant-match-tier confidence (R19) | code implementation | new OpenSpec change `patent-link-status-promotion` |
| Add patent Top-5 retrieval evaluation set (R41) | test gap | mirrors company Top-5 CSV approach |
| Add patent-domain dedup labeled set (R40) | test gap | acceptance test data |
| Add patent_number format validation (CN + digits + letter) (R7) | code implementation | low-risk, can ride a tiny change |
| Add unit tests for `validate_patent_dates` failure path (R10) | test gap | tiny test addition |
| Resolve `patent_type` vocabulary 外观 vs 外观设计 (R8 / DOC-Patent-001) | docs clarification | new debt entry below |
| Reconcile V019 enum vs shared §7.2 4-canonical statuses (R26) | docs clarification | covered by existing `agentic-rag-prd-vs-guide-001`-class debt? — leave as latent until Phase 1B+ |
| Trim or wire PRD §八 config knobs (R45) | docs clarification | tiny PRD edit, out of this audit |

Acceptance gaps BL-Patent-001 (applicant normalize follow-up) and BL-Patent-002 (patent-company / patent-inventor link precision) per the inventory remain in §5; not promoted to debt-register.

## 7. Debt Register Updates (proposed)

These are doc-debt, requirements-debt, or canonical-drift items only. Pure code gaps live in §5.

| Proposed Debt ID | Symptom | Source | Resolution Plan | New / Existing |
|---|---|---|---|---|
| patent-patent-type-vocabulary-001 | PRD §四.4.1 lists `patent_type ∈ {发明, 实用新型, 外观设计}`; V004 `PATENT_TYPES` enum stores `{发明, 实用新型, 外观, PCT, 其他}` and `release.py:_PATENT_TYPE_CANONICAL` matches the enum, not the PRD. End-to-end behavior is correct (writer normalizes 外观设计 → 外观 before insert) but the PRD term and the canonical column vocabulary disagree, and PRD does not mention `PCT` / `其他`. Risk: future readers / agents trust PRD vocabulary, write `外观设计` directly to canonical and hit the check constraint. | `docs/Patent-Data-Agent-PRD.md §四.4.1`, `apps/miroflow-agent/alembic/versions/V004_init_paper_patent_domain.py:39, :138-141`, `apps/miroflow-agent/src/data_agents/patent/release.py:124-143` | Tiny PRD edit: align §四.4.1 patent_type vocabulary with the canonical V004 enum (`发明 / 实用新型 / 外观 / PCT / 其他`), or document the input→canonical mapping (外观设计 → 外观). Not a code change. | new |

That is the only doc-or-requirements drift unique to Patent. The V019 6-value-vs-4-value drift (R26) is shared-spec-level, not patent-specific, and would land cleanly under the existing `agentic-rag-prd-vs-guide-001` / a new shared-spec debt rather than a per-domain entry; deferred to Phase 1B+ owner. The `agents-specs-frozen-but-uncategorized-001` umbrella already covers `.agents/specs/2026-05-02-w13-3-*` and `2026-05-02-w13-12-*` per the inventory.

## 8. Notes for the orchestrator

- Patent's automated coverage is the strongest of the four domains, but five "real" requirements (R13, R17, R20, R21, R41) are entirely missing rather than dogfood-only. They feed the BL-Patent-001 / BL-Patent-002 acceptance blockers indirectly: applicant-normalize follow-up needs better evidence (R41 + a labeled set), and patent-company / patent-inventor link precision is unmeasurable today because R20/R17 leave `professor_patent_link` empty and BL-Patent-002 is therefore untestable.
- The W13-3 solutions doc is gold-standard for company-side dogfood but does not by itself substitute automated tests. The 🚧 entries (R36, R37, R46) are phrased honestly to reflect that.
- One new debt entry proposed: `patent-patent-type-vocabulary-001`. No other patent-specific doc-debt found.
- No changes to `openspec/debt-register.md` were made; that is for the orchestrator to merge.
