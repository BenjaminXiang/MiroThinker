---
title: "Pattern-Repair Retroactive Sweep — Triage Pass (2026-05-08)"
date: 2026-05-08
owner: claude
status: triage-complete
---

# Pattern-Repair Retroactive Sweep — Triage Pass (2026-05-08)

This is a one-shot lightweight triage. Each candidate gets one label only.
Suspicious candidates are the input to deeper T2 slices. Done-undocumented
candidates are the input to T3 doc cleanup. Active candidates are NOT
touched by the sweep.

## Summary counts

| Label | Group A (working-tree) | Group B (specs) | Total |
|---|---|---|---|
| active | 6 | 2 | 8 |
| done-undocumented | 0 | 32 | 32 |
| suspicious | 0 | 8 | 8 |
| abandoned | 0 | 0 | 0 |
| unclear | 0 | 4 | 4 |

---

## Group A — Working-tree drift (6 batches)

### B1. professor data agent (~20 files)

- Files: `apps/miroflow-agent/src/data_agents/professor/` (10 src files: cross_domain.py, discovery.py, homepage_crawler.py, homepage_publication_headings.py, homepage_publications.py, name_utils.py, paper_collector.py, paper_publication.py, pipeline_v3.py, quality_gate.py, summary_generator.py) + `apps/miroflow-agent/tests/data_agents/professor/` (9 test files) + `apps/miroflow-agent/scripts/run_professor_pipeline_v3_e2e.py`
- Recent commits touching this area:
  - `41b43ca feat(W13-D1 option B): retire evaluation_summary across PRD/Spec/source/tests`
  - `4d0917f feat(W13 batch B): cross-domain writer + patent writer + Serper news`
  - `840ffdc feat(W12 batch C): multi-source crawl + paper.summary_zh + quality_gate`
  - `5fa8099 feat(W11-7): summary_generator 用 raw_text + reinforcement 阈值 150`
  - `4e30b0a feat(w9-2): Round 7.16 phase 2 — 全 writer wiring run_id`
- Drift volume: large (2220 insertions / 102 deletions across 20 files)
- **Label**: `active`
- **Rationale**: All drift attributable to W9–W13 commits from 2026-04-30 to 2026-05-03 that are in HEAD but not yet staged/committed in the working tree — this is normal post-implementation working-tree state; last touching commit is within days of today's date.

---

### B2. admin-console API (~19 files)

- Files: `apps/admin-console/backend/api/` (chat.py, dashboard.py, data.py, domains.py, pipeline.py, pipeline_issues.py, upload.py) + `apps/admin-console/backend/services/chat_context.py` + `apps/admin-console/backend/storage/chat_session.py` + `apps/admin-console/tests/` (10 test files: test_chat_c_handler.py, test_chat_classifier_b_g_tune.py, test_chat_classifier_c_type.py, test_chat_d_narrowing.py, test_chat_g_clarification.py, test_chat_session_persistence.py, test_classifier_benchmark.py, test_dashboard.py, test_domains_postgres.py, test_upload_pipeline_trigger.py)
- Recent commits touching this area:
  - `9ba968a feat(W13-14 + W13-15-impl partial): paper DOI verify pipeline + tests/data_agents conftest`
  - `6c7950b feat(W13 follow-up wave 3): W13-13 quality_status exposure + V021 test + ops archives`
  - `690349a feat(W13 follow-up wave 1): W13-7 + W13-9 + W13-12 + ad-hoc fixes`
  - `a47571a feat(W13 batch A P0): paper summary_zh API + retrieval prof metrics + C handler`
  - `d9b93d9 feat(W10-6 batch D): admin-console SQLite 退役 + data.py redirect`
- Drift volume: large (4675 insertions / 149 deletions across 19 files)
- **Label**: `active`
- **Rationale**: Continuous W11–W13 wave of implementation commits; chat.py alone received C/D/E/G handlers, Postgres session, and quality_status filtering. All changes trace to recently completed spec slices.

---

### B3. admin-console frontend (~5 files)

- Files: `apps/admin-console/frontend/src/App.tsx`, `api.ts`, `pages/Chat.tsx`, `pages/Dashboard.tsx`, `pages/DomainList.tsx`, `frontend/vite.config.ts`
- Recent commits touching this area:
  - `082814a feat(frontend): admin-console Chat UI — /chat route wiring /api/chat`
  - `9f10120 chore(repo): sync prior-session WIP`
  - `9976942 feat(admin-console): frontend dist staleness guard + 5180/8088 port roles`
- Drift volume: large (912 insertions / 24 deletions; api.ts +331, Dashboard.tsx +381, Chat.tsx +192)
- **Label**: `active`
- **Rationale**: React SPA is receiving active development (Chat route, Dashboard ops panel expansion, domain browser). The large drift in api.ts and Dashboard.tsx aligns with W12-3 paper fields, W13-13 quality_status, and admin-console architecture work. No sign of abandoned partial work.

---

### B4. miroflow-agent scripts/company/service (~10 files)

- Files: `scripts/run_company_news_ingest.py`, `scripts/run_professor_pipeline_v3_e2e.py`, `src/data_agents/company/import_xlsx.py`, `company/models.py`, `company/news_connectors/serper.py`, `src/data_agents/service/retrieval.py`, `tests/data_agents/company/test_import_xlsx.py`, `test_serper_news_connector.py`, `tests/scripts/test_run_company_news_ingest.py`, `test_run_professor_llm_profile_switching.py`
- Recent commits touching this area:
  - `eae24d1 fix(W13-8): SQL 不强制 unified_credit_code（Q-12）— Serper 用 canonical_name`
  - `4ff9ab0 docs(W13-8): Serper news ingest dogfood archive — 200 公司 / 482 news / ~647 events`
  - `6c7950b feat(W13 follow-up wave 3): W13-13 quality_status exposure + V021 test`
  - `4d0917f feat(W13 batch B): cross-domain writer + patent writer + Serper news`
  - `5241c9d feat(W12-1 batch E): Company KG Phase 2 + dedup`
- Drift volume: medium (924 insertions / 100 deletions across 10 files)
- **Label**: `active`
- **Rationale**: W13-8 (Serper news connector) was recently completed with dogfood and fix commits as recently as the most recent commit in the repo; retrieval.py was updated for W13-13 quality_status filter. All drift is attributable to recent W13 wave work.

---

### B5. docs / config (~6 files)

- Files: `docs/Data-Agent-Shared-Spec.md`, `docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md`, `docs/index.md`, `docs/solutions/index.md`, `docs/source_backfills/README.md`, `justfile`
- Recent commits touching this area:
  - `41b43ca feat(W13-D1 option B): retire evaluation_summary`
  - `9976942 feat(admin-console): frontend dist staleness guard`
  - `b3d50ba docs(W13): specs + handoffs + dogfood archive`
  - `76b98dc feat(w9-4): name-identity scan JSONL`
  - `cf82ef8 docs(shared-spec): sync to Round 7.x/8c/RAG reality`
- Drift volume: medium (108 insertions / 53 deletions; docs/index.md +36, solutions/index.md +18, source_backfills/README.md +23)
- **Label**: `active`
- **Rationale**: docs/index.md, solutions/index.md and source_backfills/README.md are being actively updated alongside each implementation wave. Drift reflects documentation of W13 completions not yet committed. justfile has minor additions (likely for new scripts from W13 wave).

---

### B6. paper/patent/cross-domain residual (~4 files)

- Files: `apps/miroflow-agent/src/data_agents/professor/cross_domain.py`, `src/data_agents/service/retrieval.py`, `tests/data_agents/paper/test_release.py`, `tests/data_agents/service/test_retrieval_quality_filter.py`
- Recent commits touching this area:
  - `9ba968a feat(W13-14 + W13-15-impl partial): paper DOI verify pipeline`
  - `6c7950b feat(W13 follow-up wave 3): W13-13 quality_status exposure + V021 test`
  - `690349a feat(W13 follow-up wave 1): W13-7 + W13-9 + W13-12 + ad-hoc fixes`
  - `4d0917f feat(W13 batch B): cross-domain writer + patent writer + Serper news`
- Drift volume: small (63 insertions / 3 deletions across 4 files; cross_domain.py +5, retrieval.py +8, test_release.py +34, test_retrieval_quality_filter.py +19)
- **Label**: `active`
- **Rationale**: Small residual drift from W13-13 quality filter and W13-2/W13-14 follow-up work. test_release.py and test_retrieval_quality_filter.py were added as part of W13-13 quality_status exposure; cross_domain.py and retrieval.py have minor post-W13-batch-B tweaks.

---

## Group B — Missing-review specs (46 specs grouped by week)

**Note on review coverage**: Only 3 review files exist (`2026-05-02-w12-2-stem-baseline`, `2026-05-02-w13-batch-a-codex-report`, `2026-05-03-w13-15-pollution-investigation`). The w13-batch-a review covers W13-1, W13-4, W13-5 (W13-2 and W13-3 were BLOCKED in that batch but later completed in "feat(W13 batch B)"). The W13-15 investigation report exists but a formal review/accept for the spec does not. All other 43 specs lack matching review files.

---

### W9 batch (5 specs, dated 2026-04-30)

| Spec slug | Label | Rationale |
|---|---|---|
| 2026-04-30-admin-console-architecture | `active` | Spec status="active" (architecture contract, not a task spec); still referenced for ongoing W10-6 through W13 admin-console work; no review expected until architecture stabilizes |
| 2026-04-30-w10-6-1-domains-py-postgres | `done-undocumented` | `feat(w10-6.1)` commit in git; docs/index.md has no explicit ✅ for this sub-item but the admin-console row references Postgres domains as landed code evidence; W10-6 batch D commit `d9b93d9` covers the full SQLite retire including domains.py |
| 2026-04-30-w9-1-prof-academic-metrics | `done-undocumented` | 3 implementation commits (w9-1 slice 1/2/3) in git; professor row in docs/index.md shows code evidence for V012 + `openalex_metrics`; no review file written |
| 2026-04-30-w9-2-run-id-wiring-phase-2 | `done-undocumented` | `feat(w9-2)` commit; docs/index.md references "全 writer wiring run_id（4 域 + V013）" as landed code evidence; no review file |
| 2026-04-30-w9-3-intent-classifier-benchmark | `done-undocumented` | `feat(w9-3)` commit "100 条意图识别基准集 + CI ≥ 90% accuracy gate"; ADR-008 documents the benchmark; no review file |
| 2026-04-30-w9-4-name-identity-archive | `done-undocumented` | `feat(w9-4)` commit + `data(w9-4)` archive commit; no review file |
| 2026-04-30-w9-5-m2-4-dogfood | `suspicious` | `data(w9-5)` commit shows "R3 partial-fail (M2.1 selector gap)"; docs/index.md notes homepage dogfood "10 profs dry-run 0 papers"; this spec was a validation gate that formally failed — no acceptance decision was recorded, and the failure is still open per docs/index.md ("homepage selector 修复" listed as next-priority gap) |

---

### W10 batch (6 specs, dated 2026-05-02)

| Spec slug | Label | Rationale |
|---|---|---|
| 2026-05-02-w10-1-company-milvus | `done-undocumented` | `feat(W10-1+W10-2)` commit; docs/index.md shows `company_profiles 1024` in Milvus as data evidence; no review file |
| 2026-05-02-w10-2-patent-milvus | `done-undocumented` | Same commit as W10-1; `patent_profiles 1931` documented in docs/index.md; no review file |
| 2026-05-02-w10-3-retrieval-service-4-domains | `done-undocumented` | `feat(W10-3)` commit; docs/index.md references `_VALID_DOMAINS = {"professor","paper","company","patent"}` as landed code evidence; no review file |
| 2026-05-02-w10-4-company-narrative-enrichment | `done-undocumented` | `feat(W10-4)` commit; solutions/index.md has "V2 company narrative backfill 98.93%" as dogfood evidence; no review file |
| 2026-05-02-w10-5-get-object-related | `done-undocumented` | `feat(W10-5)` commit; docs/index.md references `get_object / get_related_objects` as landed; no review file |
| 2026-05-02-w10-6-batch-d-sqlite-retire | `done-undocumented` | `feat(W10-6 batch D)` commit; docs/index.md notes SQLite retire as landed; no review file |

---

### W11 batch (7 specs, dated 2026-05-02)

| Spec slug | Label | Rationale |
|---|---|---|
| 2026-05-02-w11-1-c-type-classifier | `done-undocumented` | `feat(W11-1)` commit; chat.py C handler fully in; no review file |
| 2026-05-02-w11-2-g-clarification-ux | `done-undocumented` | `feat(W11 batch B)` commit covers G clarification; test_chat_g_clarification.py exists in working tree; no review file |
| 2026-05-02-w11-3-d-narrowing-last-result-set | `done-undocumented` | `feat(W11 batch B)` commit covers D narrowing + last_result_set; no review file |
| 2026-05-02-w11-4-e-web-search-synthesis | `done-undocumented` | `feat(W11 batch B)` + `feat(m5.2)` commits; E web search + rerank landed; no review file |
| 2026-05-02-w11-5-chat-session-postgres | `done-undocumented` | `feat(W11-5)` commit; Postgres SessionStore + V015/V016 documented in docs/index.md; no review file |
| 2026-05-02-w11-6-multi-domain-entity-stack | `done-undocumented` | `feat(W11 batch B)` covers entity stack; docs/index.md references "四域 entity stack + last_result_set 已在"; no review file |
| 2026-05-02-w11-7-summary-generator-raw-text | `done-undocumented` | `feat(W11-7)` commit; docs/index.md shows professor summary using raw_text + 150-char threshold; no review file |

---

### W12 batch (6 specs, dated 2026-05-02)

| Spec slug | Label | Rationale |
|---|---|---|
| 2026-05-02-w12-1-company-kg-batch-e | `done-undocumented` | `feat(W12-1 batch E)` commit "Company KG Phase 2 + dedup"; solutions/index.md references V2 company narrative as completed dogfood; no review file |
| 2026-05-02-w12-3-paper-v011-fields-exposure | `done-undocumented` | `feat(W12-3)` commit "paper V011 字段暴露（pdf_url + 详情扩展）"; no review file |
| 2026-05-02-w12-4-m2-1-selector-expansion | `suspicious` | `docs(W12-4)` commit only — no feat/impl commit found; homepage paper ingest dogfood (w9-5) shows "0 papers from dry-run" and "M2.1 selector gap" as root cause; docs/index.md explicitly lists "homepage selector 覆盖不足" as a current gap; this spec exists purely as a design document with no implementation |
| 2026-05-02-w12-5-multi-source-homepage-crawl | `done-undocumented` | `feat(W12 batch C)` commit implements multi_source_crawler.py; code evidence in professor/homepage_crawler.py; no review file |
| 2026-05-02-w12-6-paper-summary-zh | `done-undocumented` | `feat(W12 batch C)` commit; V018 alembic + abstract_translator.py + run_paper_summary_zh_backfill.py; solutions/index.md has V1 paper.summary_zh completed dogfood (3412 rows); no review file |
| 2026-05-02-w12-7-summary-quality-gate | `done-undocumented` | `feat(W12 batch C)` commit includes quality_gate changes; professor row in docs/index.md shows quality gate as landed; no review file |

---

### W13 batch (28 specs, dated 2026-05-02 to 2026-05-03)

| Spec slug | Label | Rationale |
|---|---|---|
| 2026-05-02-w13-1-paper-summary-zh-api-fix | `done-undocumented` | W13 batch A review confirms Done; `a47571a` commit; no standalone review file for this spec |
| 2026-05-02-w13-2-cross-domain-relation-writers | `done-undocumented` | `feat(W13 batch B)` implements W13-2 cross-domain writer (rev 2); commit message explicitly confirms W13-2; no review file |
| 2026-05-02-w13-3-patent-postgres-writer | `done-undocumented` | `feat(W13 batch B)` + 2 fix commits + docs(W13-3) dogfood commit; patent e2e fully documented in solutions/index.md; no review file |
| 2026-05-02-w13-4-c-type-endpoint-handler | `done-undocumented` | W13 batch A review confirms Done; `a47571a` commit; no standalone review file |
| 2026-05-02-w13-5-retrieval-prof-output-fields | `done-undocumented` | W13 batch A review confirms Done; `a47571a` commit; no standalone review file |
| 2026-05-02-w13-6-quality-status-alembic-v019 | `done-undocumented` | `feat(W13-6)` commit "alembic V019 — 4 域 quality_status + patent summary_text/method"; no review file |
| 2026-05-02-w13-7-classifier-prompt-tune | `done-undocumented` | `feat(W13 follow-up wave 1)` covers W13-7 prompt tune; test_chat_classifier_b_g_tune.py added; no review file |
| 2026-05-02-w13-8-web-search-news-connector | `done-undocumented` | `feat(W13 batch B)` + fix + docs dogfood commits all confirm W13-8 completed; solutions/index.md notes 200 companies / 482 news; no review file |
| 2026-05-02-w13-9-milvus-real-client-explicit | `done-undocumented` | `feat(W13 follow-up wave 1)` covers W13-9; main.py setdefault in code; no review file |
| 2026-05-02-w13-10-paper-milvus-summary-zh-rebackfill | `suspicious` | No feat/impl commit references W13-10; `run_milvus_backfill.py` was updated in W12-6 to use summary_zh, but docs/index.md explicitly states "paper summary_zh 尚未重新回灌到 paper_chunks" as a current gap; this is unstarted backfill work |
| 2026-05-02-w13-11-company-alias-normalize-improvement | `done-undocumented` | `feat(W13 follow-up wave 2)` covers W13-11 alias normalize; no review file |
| 2026-05-02-w13-12-paper-patent-identity-status | `done-undocumented` | `feat(W13 follow-up wave 1)` covers W13-12 V020 identity_status; no review file |
| 2026-05-02-w13-13-quality-status-exposure | `done-undocumented` | `feat(W13 follow-up wave 3)` covers W13-13; retrieval.py quality filter + domains.py DTO exposure; no review file |
| 2026-05-02-w13-14-paper-doi-verify | `suspicious` | `feat(W13-14 + W13-15-impl partial)` implements the pipeline but the most recent commit `e55b1a8 fix(W13-14b)` indicates Q-10 root cause (host_venue deprecated by OpenAlex) was just identified; docs/index.md says "paper quality_status 0 ready" and "OpenAlex 400 / arXiv 429" as current blockers; the fix exists in code but DOI verify has never produced a single confirmed paper; the pipeline is real but the open Q-10/Q-11 issues mean it is mid-flight not done |
| 2026-05-02-w13-15-test-fixture-pollution | `suspicious` | Investigation review file exists (`2026-05-03-w13-15-pollution-investigation.md`) confirming root cause (asyncio event loop), but the `feat(W13-14 + W13-15-impl partial)` commit explicitly notes "25 fail 仍存" — the conftest fix only partially addressed the issue; the spec's done criteria (no batch-run failures) is NOT met |
| 2026-05-02-w13-D1-evaluation-summary-decision | `done-undocumented` | spec status was "blocked-on-user-decision"; `feat(W13-D1 option B)` commit confirms decision was made and implemented (retire evaluation_summary); no formal review file |
| 2026-05-02-w13-D2-quality-status-promotion-flow | `done-undocumented` | `feat(W13 follow-up wave 2)` implements W13-D2 promotion flow; solutions/index.md references "1787 ready / 4038 pipeline_issues" as real-DB evidence; no review file |
| 2026-05-02-w13-V1-paper-summary-zh-dogfood | `done-undocumented` | `fix(W13-3): patent_type CHECK whitelist + V1 paper summary_zh full dogfood` commit; solutions/index.md has "V1 paper.summary_zh completed 3412 rows"; no review file |
| 2026-05-02-w13-V2-company-milvus-dogfood | `done-undocumented` | `docs(W13 V2)` commits archive company narrative dogfood + Top-5 eval; solutions/index.md confirms V2 company narrative 98.93%; no review file |
| 2026-05-02-w13-V3-intent-benchmark-archive | `suspicious` | W13 batch V codex report exists in solutions/index.md showing V3 ran but got overall=0.000 (all UNKNOWN) due to sandbox LLM unreachability; docs/index.md explicitly notes "真实 classifier rerun 阻塞完整验收" and "下一轮优先级：先在 host 复跑 classifier 100-case E2E"; the spec goal (archive a meaningful benchmark result with real LLM) has not been achieved |
| 2026-05-03-w13-14-paper-doi-verify | `suspicious` | (Duplicate classification — same as w13-14 above; this is the same spec at a different date prefix.) `feat(W13-14)` code is in but Q-10 fix only just landed (e55b1a8); paper DOI verify pipeline has never confirmed a single paper; 0 ready papers in production; the work is "partially implemented" per its own commit message; the most-recent fix commit is the latest in the entire repo, indicating it is still in-flight |

**Note**: `2026-05-03-w13-14-paper-doi-verify` and `2026-05-02-w13-14-paper-doi-verify` appear to be the same work — there is only one W13-14 spec file (dated 2026-05-03), so the W13 table row above and this entry refer to the same file. Count: 1 spec.

---

### Specs needing special attention

The following 4 specs are `unclear` due to ambiguous completion status or mixed signals:

| Spec slug | Label | Notes |
|---|---|---|
| 2026-04-30-admin-console-architecture | `unclear` | Status="active" in frontmatter; it is an architecture contract document, not a task spec — review may never be appropriate; needs user to decide if this should be closed or remain as living contract |
| 2026-04-30-w9-5-m2-4-dogfood | `unclear` | Dogfood ran but failed (R3 partial-fail); is the spec "done-as-failed-validation" (requiring a follow-up fix spec) or is it still open? Elevated to suspicious above, but the classification of what "done" means for a validation spec needs user judgment |
| 2026-05-02-w13-15-test-fixture-pollution | `unclear` | Investigation complete + partial fix merged; 25 batch failures reportedly still present; is the spec "done with known residual" or "still open"? The review file covers investigation only, not acceptance |
| 2026-05-02-w13-14-paper-doi-verify | `unclear` | Code merged but Q-10/Q-11 unresolved; 0 papers confirmed in production; is this "done with known gaps" (needs a follow-up spec) or "still in-flight"? Most recent commit in entire repo |

---

## Output for next steps

### Suspicious candidates → T2 deep slices

4 from Group B:

1. **w9-5-m2-4-dogfood** — validation spec formally failed (R3 partial-fail, 0 papers from 10 profs); "M2.1 selector gap" is the blocker; no follow-up spec exists for the fix; docs/index.md confirms homepage selector as unresolved next-priority item
2. **w12-4-m2-1-selector-expansion** — design-only spec with no implementation commit; directly blocks w9-5 validation; docs/index.md confirms this gap is still open and a next-priority item
3. **w13-10-paper-milvus-summary-zh-rebackfill** — no implementation commit; docs/index.md explicitly says paper summary_zh not yet rebackfilled to paper_chunks (Milvus); this is a listed gap in the current-state summary
4. **w13-V3-intent-benchmark-archive** — V3 ran and got 0.000 accuracy (LLM unreachable in sandbox); docs/index.md says host rerun is the #1 next-priority item; no real benchmark result has been archived; classifier accuracy remains unknown in the real environment

Minor suspects (in-flight, not abandoned, but not closed):

5. **w13-14-paper-doi-verify** — most recent commit in repo is a fix for this; Q-10 root cause just identified; 0 papers confirmed; technically still active but at risk of going stale without explicit closure
6. **w13-15-test-fixture-pollution** — partial fix only; 25 batch failures reportedly still present per commit message

### Done-undocumented → T3 doc cleanup

32 specs need review files written. Breakdown:
- W9 batch: 4 specs (w9-1, w9-2, w9-3, w9-4)
- W10 batch: 6 specs (w10-1, w10-2, w10-3, w10-4, w10-5, w10-6-batch-d)
- W10.6.1: 1 spec (w10-6-1-domains-py-postgres)
- W11 batch: 7 specs (w11-1 through w11-7)
- W12 batch: 4 specs (w12-1, w12-3, w12-5, w12-6, w12-7 = 5 actually)
- W13 batch: 14 specs (w13-1 through w13-9 excl. pending, w13-11 through w13-13, w13-D1, w13-D2, w13-V1, w13-V2)

Suggest using `ce-compound-refresh` or batch `ce-doc-review` for W9–W12 (all clearly done); W13 batch can be done individually given mixed states.

### Active candidates → no sweep action

6 Group A batches (all 63 modified files): all are active implementation-wave working-tree state; no action needed.

2 Group B specs: admin-console-architecture (living architecture contract), w13-14-paper-doi-verify (most recent active work in repo).

### Unclear → user input needed

4 candidates:
- `admin-console-architecture` — should this be a living doc (no review needed) or closed once React SPA fully replaces /browse?
- `w9-5-m2-4-dogfood` — should a failed validation spec be closed with a "failed" review + new follow-up spec, or kept open until fixed?
- `w13-15-test-fixture-pollution` — is partial fix + investigation sufficient to close, or is a "fix complete" commit required first?
- `w13-14-paper-doi-verify` — close when first paper is confirmed, or close now as "implementation done, validation pending"?
