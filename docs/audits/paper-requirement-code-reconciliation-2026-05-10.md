---
title: Paper Data Agent — Requirement-Code Reconciliation
date: 2026-05-10
status: active
type: requirement_code_reconciliation
domain: paper
canonical_sources:
  - docs/Paper-Data-Agent-PRD.md
  - docs/Paper-Collection-Multi-Source-Design.md  # companion-design; see §2
  - docs/Data-Agent-Shared-Spec.md
evaluated_commit: e101294
related:
  - docs/data-agent-domain-index.md
  - openspec/debt-register.md
  - paper-companion-design-relationship-001 (existing debt)
---

# Paper Requirement-Code Reconciliation

## 1. Scope

This report compares the canonical requirement sources for the Paper data-agent domain against the current implementation as of commit `e101294` (`docs(governance): add data agent domain debt inventory`). The Paper domain is unique among the four data domains because it has a **companion-design doc** (`docs/Paper-Collection-Multi-Source-Design.md`, hereafter "MSD") whose pairing relationship with the PRD is not formally declared anywhere — see §2 and existing debt `paper-companion-design-relationship-001`.

No behavior change, code change, or PRD rewrite is performed. Acceptance gaps (e.g., the PRD's ≥90% `summary_zh` coverage target vs. the dogfood-observed 47% / 85.7%) are surfaced in §5; only documents-and-requirements debt is recorded in §7.

## 2. Canonical Sources

| Source | Role | Relationship | Status |
|---|---|---|---|
| `docs/Paper-Data-Agent-PRD.md` | Primary domain requirement source | canonical | canonical |
| `docs/Paper-Collection-Multi-Source-Design.md` | Companion design — deepens the multi-source professor-anchored collection phase (Phase A / Phase B), adds operational risk model (Chinese-name disambiguation), and contract-extension plan | PRD-extension (informally). The relationship is **not formally declared** in either document, in `docs/index.md`, or in `CLAUDE.md §3`. Tracked as debt `paper-companion-design-relationship-001`. | companion / authoritative for the multi-source-collection phase |
| `docs/Data-Agent-Shared-Spec.md` | Cross-domain shared requirements (contracts, evidence, quality, storage, ID rules, retrieval) | shared baseline | shared baseline |

**Companion-design treatment in this report**:

- Requirements drawn from MSD are listed in §4 alongside PRD requirements with explicit source attribution (`PRD §X`, `MSD §Y`, or `PRD §X / MSD §Y`).
- Where PRD and MSD describe the same capability with different specificity (e.g., PRD §5.2 candidate sources list vs. MSD §2 staged source-role table), this report uses the more specific/operational one and records a cross-reference in §5.6.
- Conflicts in **direction or precedence** (PRD says X, MSD says Y) are surfaced in §5.6 as documentation drift.
- Note: this report itself does **not** formalize the PRD↔MSD relationship; doing so requires the future change pointed to by `paper-companion-design-relationship-001`.

## 3. Code Entry Points

| Area | Path | Notes |
|---|---|---|
| Canonical Pydantic model (publish layer) | `apps/miroflow-agent/src/data_agents/contracts.py:273-339` | `PaperRecord` — superset of PRD §4.1 fields including MSD Phase B fields (`tldr`, `funders`, `license`, `oa_status`, `fields_of_study`, `reference_count`, `enrichment_sources`) |
| Canonical Postgres-row Pydantic model | `apps/miroflow-agent/src/data_agents/canonical/paper.py:20-43` | Mirrors V004/V008/V018/V019/V020 columns. **Does not store `summary_text`, `keywords`, `professor_ids` directly** — those live in `professor_paper_link` or are derived |
| Domain dataclasses (in-flight discovery) | `apps/miroflow-agent/src/data_agents/paper/models.py:1-69` | `DiscoveredPaper`, `PaperMetadataEnrichment`, `ProfessorPaperDiscoveryResult`, `AuthorPaperMetrics` |
| Multi-source hybrid orchestrator | `apps/miroflow-agent/src/data_agents/paper/hybrid.py:19-88` | OpenAlex → Semantic Scholar → Crossref (PRD §5.2 / MSD §4 Stage A1-A2) |
| OpenAlex client | `apps/miroflow-agent/src/data_agents/paper/openalex.py` (590 lines) | author search w/ `last_known_institutions.id` filter (MSD §4 Stage A1) |
| Semantic Scholar client | `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py` (363 lines) | discovery + DOI enrichment (MSD §4 Stage A2 + Phase B §4.1) |
| Crossref client | `apps/miroflow-agent/src/data_agents/paper/crossref.py` (350 lines) | author-search fallback + DOI enrichment (MSD §4 Stage A2 + Phase B §4.2) |
| ORCID client | `apps/miroflow-agent/src/data_agents/paper/orcid.py:22-280` | Wired via `professor/paper_collector.py:683` (MSD §3.2 Phase B) |
| arXiv client | `apps/miroflow-agent/src/data_agents/paper/title_resolver.py:80-300` (`_search_arxiv_by_title`, `_arxiv_entry_to_resolved`) | Used by title-resolver and DOI-verifier; standalone ingest is title-driven |
| DBLP client | `apps/miroflow-agent/src/data_agents/professor/academic_tools.py:296,482` (`scrape_dblp`) | Used by professor pipeline; not in MSD Phase A |
| Google Scholar client | `apps/miroflow-agent/src/data_agents/paper/google_scholar_profile.py:51-123` | Profile-linked only |
| Institution registry (9 schools) | `apps/miroflow-agent/src/data_agents/professor/institution_registry.py:20-84` | All 9 OpenAlex IDs filled (MSD §7) |
| DOI enrichment | `apps/miroflow-agent/src/data_agents/paper/doi_enrichment.py:16-55` | Crossref + Semantic Scholar enrichment (MSD §4 Phase B) |
| LLM author-id picker | `apps/miroflow-agent/src/data_agents/paper/author_id_picker.py:1-50` | LLM-first disambiguation, `CONFIDENCE_THRESHOLD=0.75` |
| Identity / DOI verify | `apps/miroflow-agent/src/data_agents/paper/doi_verifier.py:1-335` | `verify_paper_row` over cache → OpenAlex → arXiv. Thresholds: `_TITLE_SCORE_THRESHOLD=85`, `_AUTHOR_JACCARD_THRESHOLD=0.3` |
| Title cleaner / resolver / quality | `apps/miroflow-agent/src/data_agents/paper/title_cleaner.py`, `title_resolver.py:101-173`, `title_quality.py:94-111` | `_CONFIDENCE_THRESHOLD=0.85` for resolver |
| Citation parser (LLM) | `apps/miroflow-agent/src/data_agents/paper/citation_parser.py` (269 lines) | Round 7.15 — LLM-based citation string parsing |
| `summary_zh` generation (LLM, abstract→zh) | `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py:32-103` | 200-400 字 system prompt; rejects boilerplate |
| `summary_zh` template fallback (release path) | `apps/miroflow-agent/src/data_agents/paper/release.py:202-216` | Four-段 template: what/why/how/result — used by `build_paper_release` |
| Homepage paper extraction | `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py:173-220` (`extract_publications_from_html`) | Called from `paper/homepage_ingest.py:191` |
| Homepage HTTP fetch | `apps/miroflow-agent/src/data_agents/paper/homepage_http.py:36-58` | Per-host rate gate (0.5s) |
| Homepage paper ingest orchestrator | `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py:92-373` | Resume checkpointing + `pipeline_issue` integration |
| Full-text fetcher | `apps/miroflow-agent/src/data_agents/paper/full_text_fetcher.py:1-245` | PDF extraction via pdfminer; arXiv rate-gated 3.0s |
| CV PDF parser | `apps/miroflow-agent/src/data_agents/paper/cv_pdf.py` (321 lines) | Auxiliary PDF reader |
| Canonical Postgres writer | `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py:26-156` | `upsert_paper`; sets `identity_status` based on title-resolution source |
| Release / dedupe / build | `apps/miroflow-agent/src/data_agents/paper/release.py:41-252` | DOI → arXiv → title+year+author dedupe (PRD §6) |
| Pipeline (e2e batch) | `apps/miroflow-agent/src/data_agents/paper/pipeline.py:39-129` | `run_paper_pipeline`; threadpool over professors |
| Feedback to professor | `apps/miroflow-agent/src/data_agents/paper/feedback.py:19-106` | Updates `research_directions`, `h_index`, `citation_count`, `profile_summary`. Hard-coded topic regex |
| Paper-driven research direction (LLM) | `apps/miroflow-agent/src/data_agents/professor/paper_collector.py:983-1031` (`generate_research_directions`) | LLM clustering of titles/abstracts → `paper_driven` / `merged` / `official_only` source |
| Top papers selection | `apps/miroflow-agent/src/data_agents/professor/paper_collector.py:1034-` (`select_top_papers`) | Citation-count based with recency floor |
| Quality gate (paper title) | `apps/miroflow-agent/src/data_agents/paper/title_quality.py:94-111` | Rule-based plausibility check |
| Storage (RAG tables V011) | `apps/miroflow-agent/src/data_agents/storage/postgres/paper_full_text.py`, `title_resolution_cache.py` | Backed by V011 |
| Vectorization (Milvus paper_chunks) | `apps/miroflow-agent/src/data_agents/paper/milvus_backfill.py:26-156`, `chunker.py:1-133` | `_paper_embedding_abstract` prefers `summary_zh` → `abstract_clean` → `pft.abstract` |
| RAG service routing (paper) | `apps/miroflow-agent/src/data_agents/service/retrieval.py:20,34-42,312-318,349-382` | `_VALID_DOMAINS` includes `paper`; `professor_paper_link` join only returns `link_status='verified'` |
| Admin-console paper SELECT | `apps/admin-console/backend/api/domains.py:221-264,725-759` | `summary_text` is mapped to `abstract_clean`, **not** to canonical `summary_text` (see §5.6) |
| Online `/api/chat` paper branch | `apps/admin-console/backend/api/chat.py:49,55,318,1964-1971,3437-,3704-` | Uses `lookup_paper` + `answer_paper_profile` |
| Paper lookup (deterministic) | `apps/admin-console/backend/services/chat_context.py:144-156` | LIKE on `title_clean`, `paper_id`, `doi`; selects `abstract_clean` not `summary_zh` |
| Paper profile answer (template) | `apps/admin-console/backend/services/chat_context.py:189-193` | Title/year/venue only; no `summary_zh` rendered |
| Tests (paper unit) | `apps/miroflow-agent/tests/data_agents/paper/` (27 files, 5 608 lines) | covers translator, picker, chunker, citation parser, openalex/crossref/s2/arxiv/orcid clients, full-text fetcher, hybrid, milvus backfill, pipeline, release, title pipeline, doi verifier |
| Tests (paper scripts) | `apps/miroflow-agent/tests/scripts/test_run_homepage_paper_ingest.py`, `test_run_paper_doi_verify.py`, `test_run_paper_summary_zh_backfill.py` | integration-style |
| Tests (admin-console) | `apps/admin-console/tests/test_paper_api.py`, `test_data_api_paper_v011.py` | API contract tests |
| Migrations (paper-relevant) | `V004_init_paper_patent_domain.py`, `V005a_init_professor_paper_link.py`, `V008_relax_paper_title_not_null.py`, `V011_add_rag_tables.py`, `V018_add_paper_summary_zh.py`, `V019_add_quality_status_and_patent_summary.py`, `V020_add_identity_status_paper_patent.py` | V001–V021 history |
| Real-E2E scripts | `apps/miroflow-agent/scripts/run_homepage_paper_ingest.py`, `run_paper_release_e2e.py`, `run_paper_doi_verify.py`, `run_paper_summary_zh_backfill.py`, `run_real_e2e_paper_staging_backfill.py` | None claimed run in this session |

## 4. Requirement-Code Matrix

Status legend: ✅ implemented + covered · 🟡 partial / unclear · 🚧 implemented, no test/evidence · ❌ missing · ⛔ deprecated / out of scope. Source column: `PRD §X` or `MSD §Y` (or `PRD §X / MSD §Y` for both).

### A. Positioning, scope and goals

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R1 | Paper agent is professor-anchored, not an open crawler | PRD §一, §3.1 | Pipeline takes professor list as input: `paper/pipeline.py:39-54`; `homepage_ingest.py:_fetch_professors:420-475` only joins from `professor` table | `tests/data_agents/paper/test_pipeline.py` | ✅ | — |
| R2 | Roster input fields: id / name / institution / scholar-id (optional) | PRD §3.1 | `ProfessorRecord` consumed by `pipeline.py:42` provides id, name, institution; ORCID via `professor_orcid` (V011) | `tests/data_agents/paper/test_pipeline.py` | ✅ | — |
| R3 | Realtime external fallback when local miss on explicit title | PRD §3.2, §5.6 | `chat.py:1964-1971` uses `lookup_paper` (local-only); web search fallback exists for *knowledge QA* path (`chat.py:855-862`, `_answer_knowledge_qa_with_web_search`) but is not wired specifically to a "title-not-in-paper-table → external title resolve" branch. `title_resolver.resolve_paper_by_title` accepts a `web_search` argument but it is `None` from `homepage_ingest.py:221` | — | 🟡 | Whether the user-facing online path performs an external fallback for an unknown explicit-title query is unclear; deterministic rule at `chat.py:386-403` ("exact paper deterministic rule") matches title format but still queries the local DB. Acceptance gap, see §5.2 |
| R4 | Paper signals must update professor `research_directions` | PRD §3.3, §7.1 | LLM-driven `generate_research_directions` in `professor/paper_collector.py:983-1031`; lightweight regex-based merge in `paper/feedback.py:79-91` | Implicitly covered by `tests/data_agents/professor/test_paper_collector.py` | ✅ | — |
| R5 | Paper signals must update professor `top_papers` | PRD §3.3, §7.2 | `professor/paper_collector.py:1034-` (`select_top_papers`) | `tests/data_agents/professor/test_paper_collector.py` | ✅ | — |
| R6 | Paper signals must update professor `profile_summary` | PRD §3.3, §7.3 | `paper/feedback.py:94-106` appends near-term paper info to summary | implicit | 🚧 | Hard-coded Chinese template; no targeted test for the merge rule |
| R7 | Paper domain is freshness signal source for professor | PRD §7.4 | Same path as R6; relies on most-recent papers | — | 🟡 | No code-level "freshness scoring" layer; ordering happens by year/citation in `paper/feedback.py:34-38` |
| R8 | Bidirectional role: independent retrieval object + professor profile input | PRD §一, §2.1 | `RetrievalService.retrieve` supports `paper` domain (`service/retrieval.py:20`); feedback path supports professor enrichment (R4-R7) | `tests/data_agents/test_retrieval_service*` (paper branch) | ✅ | — |

### B. Data model and outward contract

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R9 | Required fields: id, title, authors, year, summary_zh, summary_text, evidence, last_updated | PRD §4.1 | `PaperRecord` declares them with `min_length=1` / `NonEmptyStr`: `contracts.py:274-298` | `tests/data_agents/test_contracts.py:81,207,368` | ✅ | — |
| R10 | Optional fields: title_zh, doi, arxiv_id, abstract, venue, professor_ids, keywords, citation_count, pdf_path | PRD §4.1 | `contracts.py:276-294` | `tests/data_agents/test_contracts.py`, `tests/data_agents/paper/test_release.py` | ✅ | — |
| R11 | `summary_zh` must be a four-section structure (what / why / how / result) | PRD §4.2 | Template path produces four-段 string: `paper/release.py:202-216`. LLM path (`abstract_translator.py`) produces a 200-400 字 paraphrase; system prompt at `abstract_translator.py:20-29` does **not** enforce four-段 schema | `tests/data_agents/paper/test_release.py` (template); `test_abstract_translator.py` | 🟡 | Inconsistent: template is four-段 ; LLM-generated `summary_zh` is paraphrase, not four-段 (boilerplate-rejection logic only). PRD lists JSON schema `{what, why, how, result}` but neither path stores it as JSON — both serialize to a single string |
| R12 | `summary_text` is concatenation of four `summary_zh` sections | PRD §4.3, Shared §4.2.1 | `release.py:79`: `summary_text=summary_zh` (assigned identical). Backfill script writes only `summary_zh` (`run_paper_summary_zh_backfill.py:138-145`) | `test_release.py:84` (`record.summary_text == record.summary_zh`) | 🟡 | The PRD says "concatenated" (which equals `summary_zh` for that path) but Postgres `paper` table has NO `summary_text` column — only `summary_zh` (V018). The contract field is materialized only at release-time and is not durably stored. Admin API at `domains.py:753` further re-aliases `summary_text` to `abstract_clean`, breaking the PRD §4.3 invariant. See §5.6 |
| R13 | Independent Postgres + Milvus storage | PRD §4.4, Shared §6 | Postgres `paper` (V004); Milvus `paper_chunks` (`storage/milvus_collections.py`, `paper/milvus_backfill.py`) | implicit | ✅ | — |
| R14 | Stable ID prefix `PAPER-*` | PRD §4.1, Shared §4.1 | `release.py:57-61` builds via `build_stable_id("paper", …)`; `canonical_writer._build_paper_id:133-148` keys off DOI / arXiv / title+year | `tests/data_agents/paper/test_release.py`, `test_canonical_writer_identity_status.py` | ✅ | — |
| R15 | `evidence` array with required structure | PRD §4.1, Shared §4.5 | `release.py:80-87` builds one `academic_platform` evidence entry per paper; structured in `evidence.py` | `tests/data_agents/test_evidence*` | ✅ | — |
| R16 | `quality_status` ∈ canonical 4 values | Shared §4.2 | `contracts.py:9` declares 6 values (adds `partial`, `rejected`); V019 enum check has 6 values too | `tests/data_agents/test_contracts.py` | 🟡 | Contract drift: Shared-Spec §4.2 says 4 canonical values but code+migration ship 6. Not paper-specific (cross-domain) but applies to paper publishing. Acceptance gap, §5.2 |
| R17 | `run_id` traceability | Shared §4.2 | `canonical/paper.py:42` `run_id`; `canonical_writer.upsert_paper:45` calls `require_real_run_id`; V007 trace migration | `tests/data_agents/paper/test_canonical_writer_identity_status.py` | ✅ | — |
| R18 | `identity_status` for paper (V020) | (V020 migration) | `canonical_writer:55-57,151-156` uses `_identity_status_for_title_resolution_source`; `doi_verifier.verify_paper_row` powers `run_paper_doi_verify.py` | `test_canonical_writer_identity_status.py`, `test_doi_verifier.py`, `test_run_paper_doi_verify.py` | ✅ | Behavior present in code; not described in PRD §4 (PRD silent on identity_status) — see §7 |

### C. Collection and cleansing pipeline

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R19 | Overall flow: roster → candidates → attribution → full-text/abstract → summary → publish → feedback | PRD §5.1 | `paper/pipeline.py:39-94`; `paper/homepage_ingest.py:92-373`; release at `release.py:41-111`; feedback at `feedback.py:19-60` | `test_pipeline.py`, `test_release.py`, integration scripts | ✅ | — |
| R20 | Candidate sources: Google Scholar, Semantic Scholar, DBLP, arXiv, Web Search | PRD §5.2 | OpenAlex (primary, not in PRD list — see §5.6), Semantic Scholar, Crossref (not in PRD list), arXiv (via title resolver), DBLP (via `professor.academic_tools`), Google Scholar profile (`google_scholar_profile.py`) | per-source unit tests | 🟡 | PRD lists "Google Scholar / Semantic Scholar / DBLP / Arxiv / Web Search". Code uses **OpenAlex** as the primary source (per MSD §2 Phase A) and DBLP only via the professor pipeline academic_tools, not the canonical paper hybrid path. PRD↔MSD divergence — see §5.6 |
| R21 | Professor-anchored ordering (identity → candidates → attribution) | PRD §5.2 | `hybrid.py:31-52` first calls OpenAlex with author-search; `homepage_ingest.py` uses `(canonical_name, homepage)` per professor | implicit | ✅ | — |
| R22 | Attribution signals: name, institution, scholar-id, co-author network, research-direction consistency | PRD §5.3 | OpenAlex picker uses name + institution match (`openalex.py:_select_exact_name_author`, `_institution_match_quality:324-336`); LLM `author_id_picker` adds research-topic and co-author signals; `professor_paper_link` records `topic_consistency_score` / `institution_consistency_score` (`canonical/paper.py:88-89`) | `test_author_id_picker.py`, `test_openalex_picker_integration.py` | ✅ | — |
| R23 | Confidence-gated `professor_ids` write (only when confident) | PRD §5.3 | `paper_identity_gate` in `professor/paper_identity_gate.py` (`CONFIDENCE_THRESHOLD=0.8`, Shared §5.2 Round 8c); homepage ingest writes verified link when title-resolution source is authoritative (`homepage_ingest.py:260-274`) | `tests/data_agents/professor/test_paper_identity_gate.py` | ✅ | — |
| R24 | Prefer full text over abstract for summary generation | PRD §5.4 | `full_text_fetcher.py` materializes abstract+intro into `paper_full_text` (V011); `milvus_backfill._paper_embedding_abstract:155-156` prefers `summary_zh` → `abstract_clean` → `pft.abstract`. **Summary backfill** (`run_paper_summary_zh_backfill.py:127`) reads only `abstract_clean` — does not use `paper_full_text.intro` | `test_full_text_fetcher.py`, `test_run_paper_summary_zh_backfill.py` | 🟡 | summary generation does not currently consume full text; only `abstract_clean`. The `paper_full_text` table is populated, but the summary path doesn't ingest it |
| R25 | Degraded summary from abstract when full text unavailable | PRD §5.4, §5.6 | `run_paper_summary_zh_backfill.py:127` filters by `abstract_clean IS NOT NULL`; template fallback in `release.py:202-216` | `test_run_paper_summary_zh_backfill.py` | ✅ | — |
| R26 | LLM owns summary, keywords, topics; Python owns DOI/arXiv/title/date/dedupe/authors | PRD §5.5 | LLM: `abstract_translator.py`, `citation_parser.py`, `author_id_picker.py`, `professor.paper_collector.generate_research_directions`. Python: `title_cleaner.py`, `release._dedupe_papers:124-180`, `_paper_identity_key:183-199`, `normalize_authors` in `doi_verifier.py:132-163` | per-module tests | ✅ | — |
| R27 | Degradation: PDF unavailable → abstract; summary failed → retry then mark low-quality; attribution unclear → skip professor_ids; local miss → realtime external | PRD §5.6 | PDF degradation: `full_text_fetcher.fetch_error` field; summary retry: `abstract_translator.py:51-58` (1 retry); attribution skip: `paper_identity_gate` candidate vs verified; realtime external: see R3 (🟡) | `test_abstract_translator.py`, `test_full_text_fetcher.py`, `test_paper_identity_gate.py` | 🟡 | Each sub-rule is implemented, but the realtime-external sub-rule is not concretely wired in the user-facing chat path — see R3 |

### D. Deduplication

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R28 | Dedupe priority: DOI > arXiv ID > title-similarity + author-overlap | PRD §六 | `release._paper_identity_key:183-199` falls through DOI → arXiv → `title|year|sorted-authors` | `test_release.py` | ✅ | — |
| R29 | Merge rules retain richest record | PRD §六 | `release._merge_paper:136-180` uses longer text / max year / max citation_count | `test_release.py` | ✅ | — |

### E. Feedback to professor profile

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R30 | Generate 3-7 fine-grained `research_directions` from recent 5y papers | PRD §7.1 | `professor/paper_collector.generate_research_directions:983-1031` (LLM, system prompt asks for 3-7) | `tests/data_agents/professor/test_paper_collector.py` | ✅ | No explicit "5y window" filter in code path — uses caller-provided papers list |
| R31 | `top_papers` selection by citation, recency, representativeness | PRD §7.2 | `select_top_papers` in `professor/paper_collector.py:1034-` | `test_paper_collector.py` | ✅ | — |
| R32 | `profile_summary` MUST include recent topics, fine-grained directions, representative-work support | PRD §7.3 | `paper/feedback._build_profile_summary_with_papers:94-106` appends 3 paper titles to summary; professor-domain summary generators (`professor/summary_generator.py`) also exist | implicit | 🟡 | The `feedback.py` path uses a fixed Chinese template "近期论文包括《...》, 论文信号已用于更新研究方向与代表成果字段。" — meets letter of PRD §7.3 minimally; PRD's "更细粒度的方向描述" (finer-grained direction description) is fulfilled separately by `generate_research_directions` |

### F. Quality assurance

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R33 | `title`, `authors`, `year` must be present | PRD §8.1, Shared §7.2 | `PaperRecord` constraints: `contracts.py:275-278` (title NonEmptyStr; authors min_length=1; year required int) | `tests/data_agents/test_contracts.py:368-389` | ✅ | — |
| R34 | `summary_zh` and `summary_text` not missing | PRD §8.1 | `contracts.py:295-296` `NonEmptyStr` | `test_contracts.py` (paper validation) | 🟡 | Postgres `paper.summary_zh` is `nullable=True` (V018:22); contract enforces non-null only at the release-time PaperRecord boundary. Many DB rows can violate; admin API publishes them anyway. See §5.6 |
| R35 | DOI / arXiv ID format validation when present | PRD §8.1 | `_normalize_optional` in `canonical_writer.py:158-162` only strips; `doi_verifier.external_id_from_resolved` accepts as-is. No regex format check at write time | — | 🟡 | No structural format check; only normalization. PRD says "存在则做格式校验" |
| R36 | If `professor_ids` set, attribution must be reasonable | PRD §8.1 | Enforced via `paper_identity_gate` (Round 8c, CONFIDENCE_THRESHOLD=0.8); link rows below 0.8 stay `candidate` | `test_paper_identity_gate.py` | ✅ | — |
| R37 | `title_quality` rule-based plausibility | Shared §7.2 (Round 7.x) | `title_quality.is_plausible_paper_title:94-111` | `test_title_quality.py` | ✅ | — |
| R38 | High-risk same-name authors must be reverified | PRD §8.2 | LLM picker (`author_id_picker.py`) plus `name_disambiguation_conflict` flag in `openalex.py`; `pipeline_issue` table records candidates | `test_author_id_picker.py` | ✅ | — |
| R39 | Recently-added professor papers prioritized for verification | PRD §8.2 | No explicit "recency-weighted reverify queue" found in code | — | ❌ | Not implemented as a pipeline; would be a re-verification scheduler |
| R40 | Top-paper candidates verified | PRD §8.2 | `select_top_papers` orders by citation; `paper_identity_gate` runs over all paper-professor links | implicit | 🟡 | No targeted "top-paper extra-verification" pass distinct from generic identity gate |
| R41 | Locally-uncovered popular explicit-titles surfaced for review | PRD §8.2 | `pipeline_issue` table can record `all_titles_unresolvable` (`homepage_ingest.py:298-304`); no separate "popular query" tracker | — | ❌ | No code path for "popular query miss → review queue" |

### G. Configuration and update strategy

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R42 | YAML config keys: `paper.professor_roster_path`, `paper.scholar_enabled`, `paper.semantic_scholar_enabled`, `paper.dblp_enabled`, `paper.arxiv_enabled`, `paper.full_text_preferred`, `paper.explicit_title_realtime_fallback` | PRD §九 | `grep` for these keys returns no hits in `apps/miroflow-agent/conf/`, `apps/miroflow-agent/src/`, `apps/admin-console/backend/` | — | ❌ | Configuration surface from PRD §九 is not implemented. Source-toggling is hard-coded in `hybrid.py`. Acceptance/scope question — see §5.4 |
| R43 | Periodic update follows roster updates | PRD §十 | E2E scripts re-fetch from `professor` table; no scheduler in code | — | 🟡 | "Periodic" is operational, not coded. PRD says "随教授 roster 更新而更新" — this is policy, not a deliverable |
| R44 | Local summary regenerates on paper insert/change | PRD §十 | `run_paper_summary_zh_backfill.py` operates by `--only-missing` flag (default) — no automatic trigger on insert | — | 🟡 | No insert/change trigger; backfill is operator-driven |
| R45 | Explicit-title fallback handled by online service in real-time, not offline | PRD §十 | See R3 — partial | — | 🟡 | Same as R3 |

### H. Acceptance metrics (PRD §十一)

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R46 | ≥30 professors with stable paper sets — manual sample | PRD §十一 | Solution doc `homepage-paper-ingest-dogfood-2026-05-02.md` reports 10-prof dry-run, 0 papers; integration scripts can target 9 schools | — | 🟡 | Acceptance not yet met (BL-Paper-001/003 in domain-index) |
| R47 | `summary_zh` completeness ≥ 90% (full corpus) | PRD §十一 | Solution: `v1-paper-summary-zh-completed-2026-05-02.md` reports 3412 / 3982 ≈ 85.7% (rejected 242, skipped 328); domain-index reports `3456 / 7297 = 47.4%` | `test_run_paper_summary_zh_backfill.py` | 🟡 | Acceptance gap. Code is in place; coverage still rising. §5.2 |
| R48 | `summary_text` completeness ≥ 90% | PRD §十一 | Equal to `summary_zh` per R12 logic at release-time; but Postgres has no `summary_text` column — completeness can only be measured at release export | — | 🟡 | Same as R12; effectively unmeasurable in DB |
| R49 | Attribution accuracy ≥ 90% (≥100 papers) | PRD §十一 | `paper_identity_gate` enforces ≥0.8 confidence; no human-labeled set archived in repo | — | 🟡 | BL-Paper-001 (identity verification incomplete) |
| R50 | Dedupe accuracy ≥ 95% (≥100 known dupes) | PRD §十一 | `release._dedupe_papers` covered by unit tests; no production-scale labeled set in repo | `test_release.py` | 🟡 | Acceptance set absent |
| R51 | Professor enrichment effectiveness — manual before/after | PRD §十一 | Code path R4-R6 in place; no archived before/after audit | — | 🟡 | Operational acceptance, not code |
| R52 | Top-5 retrieval relevance ≥ 85% (≥50 paper-class queries) | PRD §十一 | `RetrievalService` end-to-end; Agentic-RAG-PRD acceptance pending; domain-index notes `paper_chunks 17155` reachable but `summary_zh` rebackfill outstanding | — | 🟡 | BL-Paper-002 (`summary_zh` not rebackfilled into Milvus) |

### I. Multi-Source-Design (companion) — additional requirements not duplicated by PRD

| ID | Requirement (concise) | Source | Code evidence | Test evidence | Status | Gap |
|---|---|---|---|---|---|---|
| R53 | OpenAlex is the primary source, not just one of many | MSD §2, §1.2 | `hybrid.py:31-52` — OpenAlex is tried first | `test_hybrid.py` | ✅ | — |
| R54 | Semantic Scholar / Crossref are author-search fallbacks in Phase A; DOI enrichment in Phase B | MSD §2, §4 | A: `hybrid.py:53-88`; B: `doi_enrichment.py:16-55` (Crossref+S2 by DOI) | `test_hybrid.py`, `test_doi_enrichment.py`, `test_crossref.py`, `test_semantic_scholar.py` | ✅ | — |
| R55 | ORCID enters in Phase B as anchor signal (not Phase A blocking) | MSD §3.2, §2 | ORCID exists (`paper/orcid.py`) and is wired via `professor/paper_collector.py:683` rather than `paper/hybrid.py` (so it sits in the professor pipeline, not the paper hybrid path) | `test_orcid.py`, `tests/data_agents/professor/test_paper_collector.py` | ✅ | Wired but in a non-MSD-prescribed module placement; functionally consistent with "ORCID is enrichment, not blocking" |
| R56 | DBLP only conditionally in Phase B for CS / venue gaps | MSD §2 | `professor/academic_tools.scrape_dblp:296` exists; not invoked by `paper/hybrid.py` Phase A path | unit test in `tests/data_agents/professor/` | 🟡 | DBLP is reachable but the "conditional CS-only Phase B trigger" is not codified as a gate |
| R57 | Phase A: `name_en` extracted/inferred from homepage | MSD §3.1 step 1, §4 Stage A0 | `professor/homepage_crawler.py` already produces `name_en` (cited in MSD §0) | covered by professor tests | ✅ | — |
| R58 | Phase A: 9-school OpenAlex institution registry filled (blocking) | MSD §7 | All 9 entries with verified IDs in `professor/institution_registry.py:20-84` | implicit; module imported by `paper/openalex.py` | ✅ | MSD §7 demanded "no longer 待填" — fulfilled |
| R59 | Phase A: prefer `search=name_en + filter=last_known_institutions.id:<id>` | MSD §3.1 step 3, §4 Stage A1 | `paper/openalex.py:53-65` uses exactly this filter when `institution_id` is supplied | `test_openalex.py` | ✅ | — |
| R60 | Phase A: institution registry miss → alias scoring fallback | MSD §3.1 step 4, §7 | `openalex._select_exact_name_author` uses institution match scoring across `_ALIASES`; alias scoring lives in `professor/institution_names.py` | `test_openalex.py` (alias paths) | ✅ | — |
| R61 | Phase A: `confidence < 0.8` → no paper signal, professor stays `needs_enrichment` | MSD §3.2 | `paper_identity_gate` Round 8c with 0.8 threshold; downstream professor quality gate keeps low-confidence as `needs_enrichment` | `test_paper_identity_gate.py` | ✅ | — |
| R62 | Phase A: do not extend shared `Paper` contract | MSD §6.1, §6.3 | Code does ship Phase B fields on `PaperRecord` (`tldr`, `funders`, `license`, `oa_status`, `fields_of_study`, `reference_count`, `enrichment_sources`) at `contracts.py:286-292` | `test_contracts.py` | 🟡 | Contract has been extended ahead of Phase B sign-off (MSD §6.1 said "不扩共享 contract"). Either MSD is stale or the extension was conscious. See §5.6 |
| R63 | Phase A: do not introduce new shared `quality_status` values | MSD §3.1 last bullet, §6.3 | `QualityStatus` Literal in `contracts.py:9` includes `partial`/`rejected` (added beyond the canonical 4) | — | 🟡 | Two non-canonical values (`partial`, `rejected`) added; not paper-only — Shared-Spec drift (R16). See §5.6 |
| R64 | Phase B: contract extension for `funder` / `license` / `reference` / `fields_of_study` / `tldr` / `oa_status` / `enrichment_sources` | MSD §6.2 | All seven fields are on `PaperRecord` (`contracts.py:285-292`) and on `DiscoveredPaper` / `PaperMetadataEnrichment` (`models.py:7-19,22-42`) | `test_contracts.py`, `test_release.py` | ✅ | Already done — but ahead of Phase A→B transition gate |
| R65 | Phase B: ORCID identity verifier | MSD §10 step 7 | `paper/orcid.py` is a discovery client, not a separate identity verifier; existing identity gate is in `professor/identity_verifier.py` (LLM-based) | `test_orcid.py`, `test_identity_verifier*` | 🟡 | ORCID-as-identity-verifier (with weighted signals: ORCID 0.40, institution 0.25, topic 0.20, email 0.15 per MSD §3.2) is **not** implemented. The current identity verifier is single-LLM-decision-based |
| R66 | Phase B: Crossref DOI enrichment | MSD §10 step 8 | `crossref.enrich_paper_metadata_from_crossref` invoked from `doi_enrichment.py:25` | `test_crossref.py`, `test_doi_enrichment.py` | ✅ | — |
| R67 | Phase B: Semantic Scholar DOI enrichment / batch | MSD §10 step 9 | `semantic_scholar.enrich_paper_metadata_from_semantic_scholar` invoked from `doi_enrichment.py:27` | `test_semantic_scholar.py`, `test_doi_enrichment.py` | ✅ | Single-call only; batch endpoint not exercised |
| R68 | Phase B: DBLP conditional trigger | MSD §10 step 10 | Code present (`scrape_dblp`) but no Phase-B routing logic | — | ❌ | Not wired into paper hybrid flow |
| R69 | Phase B: real DOI-anchored merge across sources | MSD §5.2, §10 step 12 | `doi_enrichment._merge_discovered_paper:58-83` merges by DOI when present | `test_doi_enrichment.py` | ✅ | — |
| R70 | API-key policy: no Phase A blocking on key acquisition | MSD §11 | OpenAlex / Crossref / S2 all run keyless in Phase A code paths | per-source tests | ✅ | — |
| R71 | Acceptance: Phase A — paper-backed professor proportion stably above baseline; ready professors with `top_papers=[]` AND all metrics empty = 0 | MSD §1.2 | Quality gate enforces "no ready w/ empty paper signal" via professor `quality_gate.py` discipline-aware logic; `paper_count`/`h_index`/`citation_count` populated by `feedback.apply_paper_feedback_to_professors:51-54` | `test_quality_gate*` | 🟡 | Acceptance set/run not archived for current commit |
| R72 | Acceptance: Phase A — 50-100 prof manual sample, precision ≥ 95%, zero obvious mis-attribution | MSD §1.2, §9.2 | No archived 50-100 sample audit at this commit | — | 🟡 | Operational acceptance |

## 5. Findings

### 5.1 Implemented and covered (✅)

R1 (anchor model), R2 (roster fields), R4-R5 (research directions, top papers), R8 (bidirectional), R9-R10 (required/optional fields), R13 (storage), R14 (id), R15 (evidence), R17 (run_id), R18 (identity_status), R19 (overall flow), R21 (anchored ordering), R22 (attribution signals), R23 (confidence-gated link), R25 (degraded summary), R26 (LLM/Python split), R28-R29 (dedupe), R30 (3-7 directions), R31 (top papers), R33 (mandatory fields), R36 (link gate), R37 (title quality), R38 (same-name reverify hooks), R53-R54 (OpenAlex primary + fallback), R55 (ORCID Phase B placement), R57-R61 (homepage `name_en`, registry, OpenAlex filter, alias fallback, confidence policy), R64 (Phase B contract fields exist), R66-R67 (DOI enrichment), R69 (DOI merge), R70 (no-key Phase A).

These are correctly implemented and have unit/integration tests in `apps/miroflow-agent/tests/data_agents/paper/`.

### 5.2 Partially implemented (🟡)

- **R3 / R45 (realtime external fallback for explicit-title)**: `title_resolver.resolve_paper_by_title` accepts a `web_search` argument but production callers pass `web_search=None`. The user-facing chat path (`chat.py:1964-1971`) only queries the local `paper` table via `lookup_paper`. Acceptance gap.
- **R7 (freshness signal)**: implicit via citation/year ordering; no explicit freshness scoring.
- **R11 (`summary_zh` four-段 schema)**: PRD specifies a JSON `{what, why, how, result}` shape; release-template path produces a four-段 string, but the LLM backfill path produces a 200-400 字 paraphrase that is not four-段-structured. Outputs are stored as plain strings, not JSON.
- **R12 (`summary_text` definition)**: code assigns `summary_text = summary_zh` at release time. There is no Postgres column for `summary_text`; the admin API at `domains.py:753` aliases `summary_text` to `abstract_clean`, conflicting with PRD §4.3. (Also see §5.6.)
- **R16 (`quality_status` 4 vs 6)**: `contracts.py:9` declares 6 values; Shared-Spec §4.2 says 4. V019 migration ships 6. Cross-domain drift; not paper-specific. Acceptance/contract gap.
- **R20 (candidate sources list)**: PRD §5.2 lists Google Scholar / Semantic Scholar / DBLP / arXiv / Web Search; code uses OpenAlex (primary), Semantic Scholar, Crossref. PRD does not mention OpenAlex; MSD §2 explicitly promotes OpenAlex to primary. PRD↔MSD divergence (§5.6).
- **R24 (full text preferred for summary)**: `paper_full_text.intro` is populated but the summary backfill reads only `abstract_clean`.
- **R27 (degradation strategies, sub-rule realtime external)**: see R3.
- **R32 (`profile_summary` recent topics)**: hard-coded Chinese template appends 3 titles; meets the letter of PRD §7.3 minimally.
- **R34 (`summary_zh`/`summary_text` not missing)**: enforced at PaperRecord boundary, not at the Postgres column (V018 nullable=True). Real DB rows can violate.
- **R35 (DOI / arXiv format validation)**: only normalization, no format regex.
- **R39-R41 (recency reverify, top-paper extra verify, popular-query miss queue)**: not separately scheduled.
- **R43-R44 (periodic / on-change re-summary)**: operator-driven, no scheduler.
- **R46-R52 (acceptance metrics)**: code paths present; metrics not yet met or not archived for current commit. These are acceptance gaps, **not code gaps** — they belong to Paper PRD §十一 acceptance tracking, not §7 doc debt.
- **R56 (DBLP conditional trigger)**: client exists; no Phase-B router.
- **R62-R63 (Phase A do-not-extend rules)**: Phase B contract extensions and 2 extra `quality_status` values are already in `contracts.py`. Either MSD is stale or the extension was conscious; not formally declared.
- **R65 (ORCID weighted-signal identity verifier)**: ORCID present as a discovery source but the weighted-signal identity verifier (ORCID 0.40 / institution 0.25 / topic 0.20 / email 0.15 per MSD §3.2) is not implemented. Current identity verification is LLM-based, single decision.
- **R71-R72 (Phase A acceptance)**: not yet archived against current commit.

### 5.3 Implemented without test or evidence (🚧)

- **R6 (paper signals → `profile_summary`)**: implementation in `paper/feedback.py:94-106` uses a hard-coded Chinese template; no targeted unit test asserts the merge rule (only implicit via pipeline tests). Low risk but no direct coverage.

### 5.4 Missing or unclear (❌)

- **R39 (recency-weighted reverify queue)**: no implementation.
- **R41 (popular-but-uncovered explicit-title review queue)**: no code; only generic `pipeline_issue` for `all_titles_unresolvable`.
- **R42 (PRD §九 YAML config keys)**: `paper.scholar_enabled`, `paper.semantic_scholar_enabled`, `paper.dblp_enabled`, `paper.arxiv_enabled`, `paper.full_text_preferred`, `paper.explicit_title_realtime_fallback`, `paper.professor_roster_path` — none present in `apps/miroflow-agent/conf/`, `src/`, or admin-console. The PRD-specified configuration surface does not exist.
- **R68 (Phase B DBLP conditional trigger)**: code missing.

### 5.5 Test gaps

| Item | Location | Note |
|---|---|---|
| R6 — `paper/feedback._build_profile_summary_with_papers` | `apps/miroflow-agent/src/data_agents/paper/feedback.py:94-106` | No direct unit test for the summary-merge rule |
| R10 — `keywords` field downstream | `apps/admin-console/backend/api/domains.py:725-759` | `keywords` is set by `release._extract_keywords` but is **not selected** by `PAPER_SELECT_SQL` (`domains.py:221-264`) and not exposed in `core_facts` (`domains.py:727-746`) — would require Postgres `keywords` column or release-snapshot table |
| R12 — `summary_text` parity in admin API | `apps/admin-console/backend/api/domains.py:753` | Currently aliases `summary_text` to `abstract_clean`; no test asserts equivalence to release-time `summary_text` |
| R20 — paper-domain hybrid integration with OpenAlex+S2+Crossref+arXiv | `tests/data_agents/paper/test_hybrid.py` | covers happy path; no integration test that confirms the PRD §5.2 ordering claim ("Scholar / S2 / DBLP / arXiv / Web") |
| R65 — weighted-signal identity verifier | n/a | not implemented; no test |

### 5.6 Documentation drift (incl. PRD ↔ companion-design conflicts)

1. **PRD §5.2 candidate sources list does not match code (PRD↔MSD↔code)**. PRD §5.2 lists Google Scholar / Semantic Scholar / DBLP / Arxiv / Web Search. MSD §2 promotes **OpenAlex** to primary and demotes Scholar/DBLP. Code follows MSD (OpenAlex primary; Crossref added; DBLP only via professor pipeline). PRD is stale on this point. See R20.

2. **`summary_text` semantics (PRD ↔ Shared-Spec ↔ code ↔ admin API)**:
   - PRD §4.3 says `summary_text` = concatenation of `summary_zh`'s four sections — i.e., effectively equal to `summary_zh` in serialized form.
   - Shared-Spec §4.2.1 says the same.
   - `release.py:79` materializes `summary_text=summary_zh` at PaperRecord creation.
   - **Postgres has no `summary_text` column for `paper`** (only `summary_zh` via V018; V019 added `summary_text` to `patent`, not `paper`).
   - **Admin API `domains.py:753` aliases `summary_text` to `abstract_clean`** — i.e., the user-facing `/api/data/paper/...` returns the English abstract under the `summary_text` key, contradicting PRD §4.3. See R12, R34.

3. **`quality_status` 4 vs 6 (Shared-Spec ↔ code)**: Shared-Spec §4.2 declares 4 canonical values; `contracts.py:9` and V019 migration ship 6 (`partial`, `rejected` added). Cross-domain.

4. **Phase A "do not extend contract / quality_status" rule (MSD ↔ code)**: MSD §6.1, §6.3, §12 §3 require Phase A to **not** extend the shared Paper contract and **not** add new `quality_status` values. Code at `contracts.py:286-292` already includes 7 Phase B fields; `contracts.py:9` already has 2 extra `quality_status` values. Either MSD is stale or the rule was consciously broken without updating MSD. See R62-R63.

5. **PRD §九 configuration vs code**: PRD specifies a YAML config block under key `paper:` with 7 fields. None are present. See R42.

6. **PRD §3.2 "explicit-title realtime external fallback" vs `chat.py`**: PRD says "本地库未命中时，允许线上服务走实时外部 fallback". Chat path's "exact paper deterministic rule" (`chat.py:386-403`) does not call into a web-search-based external title resolver; the only external fallback is for knowledge-QA path. See R3.

7. **PRD↔MSD pairing not formally declared anywhere**: existing debt `paper-companion-design-relationship-001`. This report has not changed the severity assessment; ambiguity remains low-severity in practice (the codebase implicitly follows MSD where it conflicts with PRD), but contributes to most of the items in this section. **No new evidence to escalate severity.**

### 5.7 Deprecated / candidate-for-removal (⛔)

- None. `paper/cv_pdf.py`, `paper/feedback.py`, and `paper/release.py` could be slated for review when the homepage-ingest pipeline (V011) becomes the only path, but they are still referenced by `run_paper_release_e2e.py` and `professor/paper_publication.py`.

## 6. Recommended Follow-up

| Follow-up | Type | Suggested owner artifact |
|---|---|---|
| Formalize PRD ↔ MSD pairing — declare MSD as a phase-detail extension and define precedence | docs clarification / OpenSpec change later | `paper-companion-design-relationship-001` (existing); future Phase 1B+ change |
| Reconcile PRD §5.2 candidate-source list with actual hybrid (OpenAlex primary) | docs clarification | PRD §5.2 amendment (after OpenSpec touch-to-promote) |
| Reconcile `summary_text` semantics: either add Postgres `paper.summary_text` column **or** fix admin API `domains.py:753` to expose `summary_zh` instead of `abstract_clean` | code implementation needed later | Pair an OpenSpec change with an alembic migration or admin-API fix |
| Reconcile `quality_status` 4 vs 6 across Shared-Spec / contracts / V019 | docs clarification (Shared-Spec) **or** code/migration cleanup | Cross-domain — separate from paper audit |
| PRD §九 YAML config surface — implement the config keys, **or** strike them from PRD | docs clarification or code implementation | OpenSpec change for paper config |
| `summary_zh` four-段 JSON schema — decide whether code should produce structured JSON (PRD §4.2) or freeform paragraph (current LLM behavior) | docs clarification or code refactor | Future change |
| Realtime external fallback for explicit-title misses (PRD §3.2) — wire `web_search` arg in `homepage_ingest` and `chat.py` exact-paper path, **or** narrow PRD §3.2 to "offline-only" | code implementation or docs amendment | OpenSpec change |
| Phase B routing for DBLP (R68) and ORCID weighted-signal verifier (R65) | code implementation needed later | Phase B paper plan |
| Acceptance auditing for R46-R52 metrics | test/operational gap | Operating-Guide / dogfood log; **not §7 debt** |
| Update MSD §6.1/6.3 "Phase A do-not-extend" assertion to reflect that the contract has already been extended | docs clarification | future MSD revision |
| Add direct unit test for `paper/feedback._build_profile_summary_with_papers` (R6) | test coverage | unit test |
| Add `keywords` to admin API output **or** drop `keywords` from PRD §4.1 optional list | docs clarification | minor |

## 7. Debt Register Updates (proposed)

These are doc-debt, requirements-debt, or canonical-drift items only. Pure code gaps (R39, R41, R65, R68) and acceptance gaps (R46-R52) live in §5 and do not enter the debt register.

| Proposed / Existing Debt ID | Symptom | Source | Resolution Plan | Action |
|---|---|---|---|---|
| `paper-companion-design-relationship-001` | (existing) PRD ↔ MSD pairing not formally declared anywhere | `docs/Paper-Data-Agent-PRD.md`, `docs/Paper-Collection-Multi-Source-Design.md` | Phase 1B+ change `paper-companion-design-relationship`: declare in both docs + `docs/index.md` doc-layering diagram that MSD is a supplement / phase-detail attachment to the PRD. | **Review only — no severity change**. This audit confirms the relationship is the root cause of multiple §5.6 drift items (R20, R62-R63, sources list, "do not extend contract" rule), but the items themselves are individually low-severity. Severity stays `low`. Adding a note in the resolution plan that the pairing change should also reconcile R20 (sources list), R62-R63 (Phase-A scope), and the §5.6 list is recommended when the change is opened. |
| `paper-prd-config-surface-001` | PRD §九 declares a `paper:` YAML config block (7 keys: `professor_roster_path`, `scholar_enabled`, `semantic_scholar_enabled`, `dblp_enabled`, `arxiv_enabled`, `full_text_preferred`, `explicit_title_realtime_fallback`) that is not present in `apps/miroflow-agent/conf/`, `src/`, or admin-console. Source-toggling is hard-coded in `paper/hybrid.py`. Risk: PRD reads as authoritative for an interface that does not exist. | `docs/Paper-Data-Agent-PRD.md §九`, code grep shows zero hits for these keys | Phase 1B+ change: either implement the config surface (and route `hybrid.py` source toggles through it) or strike PRD §九 from the canonical list with a "not implemented" marker. Touch-to-promote into OpenSpec when changed. | New |
| `paper-prd-source-list-stale-001` | PRD §5.2 lists Google Scholar / Semantic Scholar / DBLP / arXiv / Web Search as candidate sources; actual implementation per MSD §2 promotes **OpenAlex** to primary and uses Crossref. PRD does not mention OpenAlex anywhere. Risk: agents reading PRD §5.2 may try to add a Scholar-first or DBLP-first path that contradicts the working MSD-driven hybrid. | `docs/Paper-Data-Agent-PRD.md §5.2`, `docs/Paper-Collection-Multi-Source-Design.md §2`, `apps/miroflow-agent/src/data_agents/paper/hybrid.py:19-88` | Phase 1B+ change `paper-prd-source-list-align` (or bundle into the `paper-companion-design-relationship` change): rewrite PRD §5.2 to align with MSD §2, OR move the source-priority statement into Shared-Spec §5.3 (which already lists the multi-source ordering correctly). | New |
| `paper-summary-text-contract-drift-001` | PRD §4.3 + Shared §4.2.1 say `summary_text` is concatenation of `summary_zh` four-段 sections. Code at `paper/release.py:79` honors this at the PaperRecord boundary (assigns identical). However: (a) Postgres `paper` has no `summary_text` column (only `summary_zh` from V018); (b) admin API `domains.py:753` aliases `summary_text` to `abstract_clean` (English), contradicting the contract. Risk: line-6 in §5.6 — user-facing API silently violates declared contract. | `docs/Paper-Data-Agent-PRD.md §4.3`, `docs/Data-Agent-Shared-Spec.md §4.2.1`, `apps/admin-console/backend/api/domains.py:753`, `apps/miroflow-agent/alembic/versions/V018_add_paper_summary_zh.py` | Phase 1B+ change `paper-summary-text-resolve`: choose one of (a) add `paper.summary_text` column + backfill from `summary_zh`; (b) update admin API to expose `summary_text` from `summary_zh`; or (c) amend PRD/Shared-Spec to clarify that `summary_text` is a release-time-only synthesized field. Pure docs amendment may suffice if (c) is chosen. | New |
| `paper-prd-msd-phase-a-rule-stale-001` | MSD §6.1, §6.3, §12.3 declare Phase A must NOT extend the shared Paper contract and must NOT introduce new `quality_status` values. Both rules have already been broken in code: `contracts.py:286-292` ships 7 Phase B fields (`tldr`, `funders`, `license`, `oa_status`, `fields_of_study`, `reference_count`, `enrichment_sources`); `contracts.py:9` ships 2 extra `quality_status` values (`partial`, `rejected`). Either MSD is stale or the rule was consciously broken without updating MSD. Risk: future contributors reading MSD literally may try to revert. | `docs/Paper-Collection-Multi-Source-Design.md §6.1, §6.3, §12.3`, `apps/miroflow-agent/src/data_agents/contracts.py:9,286-292` | Phase 1B+ change: amend MSD to acknowledge that Phase A → Phase B contract migration has already happened (and capture the rationale), OR roll back the extra contract fields if they are not yet justified. Preferred: docs amendment. | New |
| `paper-prd-summary-zh-schema-shape-001` | PRD §4.2 specifies `summary_zh` as a four-key JSON object `{what, why, how, result}`. Code paths produce strings: `release.py:202-216` produces a four-段 narrative string; `abstract_translator.py:20-29` produces a free-form 200-400 字 paraphrase. Neither path serializes structured JSON. Risk: PRD reads as if downstream consumers can rely on JSON shape; they cannot. | `docs/Paper-Data-Agent-PRD.md §4.2`, `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py`, `apps/miroflow-agent/src/data_agents/paper/release.py:202-216` | Phase 1B+ change: either (a) amend PRD to clarify that `summary_zh` is a Chinese paragraph (with optional internal four-段 markers) rather than JSON; or (b) refactor both paths to emit structured JSON and update Postgres column type. Preferred: (a) docs amendment. | New |

## 8. Notes for the orchestrator

- This report treats `docs/Paper-Collection-Multi-Source-Design.md` as a **PRD-extension** for the multi-source-collection phase, but **the relationship is not formally declared** (existing debt `paper-companion-design-relationship-001`). Consumers of this report should be aware that any §4 entry tagged `MSD §...` has lower formal authority than entries tagged `PRD §...` until that debt is resolved.
- All six §7 entries (1 existing, 5 proposed new) are documents-and-requirements debt. None require code changes by themselves. The three "code reconciliation" choices (config surface, summary_text storage, contract-and-quality-status retroactive sign-off) are presented as docs-vs-code options, not as code obligations.
- Acceptance gaps for R46-R52 are explicitly excluded from §7 per CLAUDE.md §14 / domain-index Phase 1A guidance — they belong to PRD §十一 acceptance auditing.
- Real E2E was **not run** in this session; all conclusions are based on code reading and existing solution-doc/dogfood archives. Where solution docs report numeric coverage (e.g. 47.4% / 85.7% `summary_zh`), those numbers are reproduced in §4 / §5.2 only as evidence of the acceptance gap, not as a fresh measurement.
- Existing debt `paper-companion-design-relationship-001` severity remains `low` after this audit. Resolution-plan note recommended (not a severity escalation): when the change is opened, scope should explicitly cover R20 (sources list) and R62-R63 (Phase-A scope) reconciliation in the same change.
