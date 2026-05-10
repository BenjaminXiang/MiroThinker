---
title: Data Agent Four-Domain Canonical Baseline Inventory (Phase 1A)
date: 2026-05-10
status: active
type: domain_canonical_baseline_inventory
phase: 1A
calibrates:
  - docs/index.md
related:
  - openspec/change-ledger.md
  - openspec/debt-register.md
  - CLAUDE.md (§14)
  - AGENTS.md (§15)
---

# Data Agent Four-Domain Canonical Baseline Inventory (Phase 1A)

> Read-only inventory. No code changes, no PRD merges, no archival, no deletions.
> Phase 1B / 1C will action the debt items listed in `openspec/debt-register.md`.

## Scope

For each of the four data collection domains (Company / Paper / Patent / Professor), declare:

1. Candidate requirement sources
2. Shared spec dependencies
3. Legacy `.agents/specs/` references
4. Active / stale OpenSpec changes
5. Active / partial plans
6. Solutions of record
7. Canonical baseline recommendation
8. Blockers / debt items (acceptance gaps stay out; doc debt enters `openspec/debt-register.md`)

Per user instruction 2026-05-10, the Professor canonical question is **resolved by user declaration**: `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` is canonical for Professor. The originally anticipated `resolve-professor-canonical-baseline` change is short-circuited; downstream cleanup (PRD legacy handling, stale OpenSpec change resolution, audit-doc tracking decision) becomes Phase 1B+ work tracked in `debt-register.md`.

## Cross-domain reference layer

| Document | Role | docs/index.md status | Phase 1A note |
|---|---|---|---|
| `docs/Data-Agent-Shared-Spec.md` | Top authoritative shared architecture and contracts (4 domains) | 🟡 contract layer ✅; full validation incomplete | CLAUDE.md §3 / §7 lists as outranking domain-local; remains canonical for shared layer |
| `docs/Multi-turn-Context-Manager-Design.md` | RAG multi-turn context management | 🟡 partial | Self-described "partial". Needs alignment with `apps/admin-console/backend/api/chat.py` SessionContext + Postgres `chat_session` (V015 / V016) — see debt `multi-turn-design-partial-001` |
| `docs/Agentic-RAG-PRD.md` | Service layer consuming 4-domain data (PRD) | 🟡 | Canonical for Agentic RAG behavior |
| `docs/Agentic-RAG-Operating-Guide.md` | Current online `/api/chat` operating posture | 🟡 | Operational supplement to PRD; relationship needs explicit declaration — see debt `agentic-rag-prd-vs-guide-001` |
| `docs/quality-status-compatibility.md` | `quality_status` field compatibility | ✅ reference | Reference, not authoritative behavior |

---

## Domain 1: Company

### Candidate requirement sources
- **Primary**: `docs/Company-Data-Agent-PRD.md`
- No replacement / audit / supersession candidates

### Shared spec dependencies
- `docs/Data-Agent-Shared-Spec.md` — contracts / evidence / normalization / linking
- `docs/quality-status-compatibility.md`

### Legacy `.agents/specs/` references (filename-classified)
- `2026-05-02-w10-1-company-milvus.md` — Milvus `company_profiles` collection
- `2026-05-02-w10-4-company-narrative-enrichment.md` — `profile_summary` / `technology_route_summary` enrichment
- `2026-05-02-w12-1-company-kg-batch-e.md` — knowledge graph batch
- `2026-05-02-w13-11-company-alias-normalize-improvement.md` — alias normalization
- `2026-05-02-w13-V2-company-milvus-dogfood.md` — Milvus dogfood
- `2026-05-02-w13-2-cross-domain-relation-writers.md` (cross-domain; touches company)

### Active / stale OpenSpec changes
- None

### Active / partial plans
- `docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md` — PARTIAL (canonical model + import code in; KG migration / relation backfill / Milvus search outstanding)
- `docs/plans/2026-04-18-003-company-product-capture.md` — OPEN (original V008 assumption invalidated; product schema / migration not in)

### Solutions of record
- `docs/solutions/integration-issues/v2-company-narrative-completed-2026-05-02.md` — 1013 / 1024 = 98.93% coverage
- `docs/solutions/integration-issues/v2-stage3-company-top5-eval-2026-05-02.md` — 50 / 50 retrieval results, manual labeling pending

### Canonical baseline recommendation
**Canonical: `docs/Company-Data-Agent-PRD.md`** (single source) + `docs/Data-Agent-Shared-Spec.md` (shared layer).
Plans / solutions are derivative (planning + retrospective), not authoritative for behavior.

### Blockers
Acceptance-gap items (do **not** enter `debt-register.md`; they belong to Company PRD's acceptance section):
- BL-Company-001: 11 records `quality_status: needs_review` outstanding
- BL-Company-002: Top-5 retrieval ≥ 85% manual confirmation pending
- BL-Company-003: alias normalization precision unverified

---

## Domain 2: Paper

### Candidate requirement sources
- **Primary**: `docs/Paper-Data-Agent-PRD.md`
- **Companion design (relationship not formally declared)**: `docs/Paper-Collection-Multi-Source-Design.md` (Phase A in code + tests; Phase B not started)

### Shared spec dependencies
- `docs/Data-Agent-Shared-Spec.md`
- `docs/quality-status-compatibility.md`

### Legacy `.agents/specs/` references
- `2026-05-02-w12-3-paper-v011-fields-exposure.md`
- `2026-05-02-w12-4-m2-1-selector-expansion.md` — homepage selector
- `2026-05-02-w12-5-multi-source-homepage-crawl.md`
- `2026-05-02-w12-6-paper-summary-zh.md`
- `2026-05-02-w13-1-paper-summary-zh-api-fix.md`
- `2026-05-02-w13-10-paper-milvus-summary-zh-rebackfill.md`
- `2026-05-02-w13-12-paper-patent-identity-status.md` (cross-domain paper / patent)
- `2026-05-02-w13-V1-paper-summary-zh-dogfood.md`
- `2026-05-03-w13-14-paper-doi-verify.md`
- `2026-05-09-w12-4-stage-b-shenzhen-archetypes.md` — homepage selector Stage B (Shenzhen archetypes)

### Active / stale OpenSpec changes
- None

### Active / partial plans
- `docs/plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md` — PARTIAL (Phase A in; Phase B queued)
- `docs/plans/2026-04-21-001-m2.1-homepage-publications-extractor.md` — PARTIAL
- `docs/plans/2026-04-21-002-m2.2-paper-title-resolver.md` — PARTIAL
- `docs/plans/2026-04-21-003-m2.3-paper-full-text-fetcher.md` — PARTIAL
- `docs/plans/2026-04-21-004-m2.4-homepage-paper-ingest-orchestrator.md` — PARTIAL

### Solutions of record
- `docs/solutions/integration-issues/v1-paper-summary-zh-completed-2026-05-02.md` — 3456 / 7297 = 47.4%
- `docs/solutions/integration-issues/paper-summary-zh-dogfood-2026-05-02.md`
- `docs/solutions/integration-issues/homepage-paper-ingest-dogfood-2026-05-02.md` — 10 profs dry-run, 0 papers
- `docs/solutions/workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md`

### Canonical baseline recommendation
**Canonical: `docs/Paper-Data-Agent-PRD.md`** (primary requirement source) + `docs/Paper-Collection-Multi-Source-Design.md` (companion design, treated as PRD-extension for the multi-source phase) + `docs/Data-Agent-Shared-Spec.md`.

Note: the PRD–design pairing is not explicitly declared anywhere. See debt `paper-companion-design-relationship-001`.

### Blockers
Acceptance-gap items:
- BL-Paper-001: paper `quality_status` 0 ready (identity verification incomplete)
- BL-Paper-002: `summary_zh` not rebackfilled into Milvus `paper_chunks`
- BL-Paper-003: homepage selector coverage gap
- BL-Paper-004: OpenAlex 400 / arXiv 429 errors operationally outstanding

Document debt:
- DOC-Paper-001 → debt `paper-companion-design-relationship-001`

---

## Domain 3: Patent

### Candidate requirement sources
- **Primary**: `docs/Patent-Data-Agent-PRD.md`
- No replacement / audit / supersession candidates

### Shared spec dependencies
- `docs/Data-Agent-Shared-Spec.md`
- `docs/quality-status-compatibility.md`

### Legacy `.agents/specs/` references
- `2026-05-02-w10-2-patent-milvus.md` — Milvus `patent_profiles`
- `2026-05-02-w13-3-patent-postgres-writer.md`
- `2026-05-02-w13-12-paper-patent-identity-status.md` (cross-domain)

### Active / stale OpenSpec changes
- None

### Active / partial plans
- No patent-specific entry in `docs/plans/index.md` "🟢 当前活跃"; patent has progressed via the W13-3 wave without a dedicated active plan.

### Solutions of record
- `docs/solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md` — 1931 / 1931 ready, 1931 / 1931 `summary_text`, chat HTTP 200 (gold-standard reference for the four domains)

### Canonical baseline recommendation
**Canonical: `docs/Patent-Data-Agent-PRD.md`** + `docs/Data-Agent-Shared-Spec.md`.
Cleanest of the four domains: single source, no audit, no OpenSpec change in flight.

### Blockers
Acceptance-gap items:
- BL-Patent-001: applicant normalize follow-up
- BL-Patent-002: patent–company / patent–inventor link precision unverified

No document debt for Patent.

---

## Domain 4: Professor

### User declaration (2026-05-10)
> "这个文档是我昨天刚确认的教授数据采集域的需求文档，关于教授数据采集域可以以这个为准 docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md"

### Candidate requirement sources
- **Canonical (declared)**: `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`
- **Legacy / superseded for behavior**: `docs/Professor-Data-Agent-PRD.md` (Phase 1B+ cleanup target)
- **Stale OpenSpec change**: `openspec/changes/refine-professor-data-agent-prd/` (premise was "modify PRD"; now PRD is no longer canonical)

### Shared spec dependencies
- `docs/Data-Agent-Shared-Spec.md`
- `docs/quality-status-compatibility.md`

### Legacy `.agents/specs/` references (filename-classified, partial)
- `2026-04-30-w9-1-prof-academic-metrics.md`
- `2026-04-30-w9-4-name-identity-archive.md`
- `2026-05-02-w13-5-retrieval-prof-output-fields.md`

(Many additional Professor-related specs exist whose filenames don't include `professor`; complete touch-time triage deferred to Phase 1B+ — see debt `agents-specs-frozen-but-uncategorized-001`.)

### Active / stale OpenSpec changes
- **Stale**: `openspec/changes/refine-professor-data-agent-prd/` — tasks T1–T5 marked `[x]`; targets the now-superseded PRD; needs decision (re-target to Audit / abandon / archive-as-historical). Already logged in `debt-register.md` as `professor-prd-change-001`; the user's canonical declaration adds the "premise invalidated" angle (`professor-prd-change-001` updated).

### Active / partial plans
- `docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md` — OPEN
- `docs/plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md` — OPEN
- `docs/plans/2026-04-17-003-professor-stem-issue-closure-plan.md` — PARTIAL (Wave 1 closed; Wave 2 in progress)
- `docs/plans/2026-04-17-003-professor-official-anchor-first-paper-disambiguation-plan.md` — OPEN
- `docs/plans/2026-04-23-001-m1-identity-gate-v2.md` / `docs/plans/2026-04-23-002-m1-orcid-backfill.md` — PARTIAL
- `docs/plans/2026-04-18-007-name-identity-gate.md` — COMPLETE per index

### Solutions of record (selected; many more in subdirs)
- `docs/solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md`
- `docs/solutions/data-quality/professor-paper-prd-gap-assessment-2026-05-04.md`
- `docs/solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md`
- `docs/solutions/workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md`

### Canonical baseline recommendation
**Canonical: `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`** (per user declaration 2026-05-10) + `docs/Data-Agent-Shared-Spec.md`.

Downstream cleanup (Phase 1B+):
- Track audit doc into git or formally consolidate into a tracked location (currently untracked) — debt `audit-doc-untracked-001`
- Decide PRD's status (legacy reference / archive / replace) — debt `professor-canonical-pivot-001`
- Re-target / abandon / archive the stale OpenSpec change — debt `professor-prd-change-001`

### Blockers
Acceptance-gap items:
- BL-Professor-001: STEM / HSS quality sampling
- BL-Professor-002: real Web Search fallback validation
- BL-Professor-003: professor–company / professor–paper link precision

Document debt:
- DOC-Professor-001 → `audit-doc-untracked-001`
- DOC-Professor-002 → `professor-canonical-pivot-001`
- DOC-Professor-003 → `professor-prd-change-001` (existing entry; updated)

---

## Cross-domain / infrastructure `.agents/specs/`

These specs are not single-domain. Listed for inventory completeness; per-spec frontmatter triage deferred to Phase 1B+ (debt `agents-specs-frozen-but-uncategorized-001`).

| Spec | Topic | Touches |
|---|---|---|
| `2026-04-30-admin-console-architecture.md` | Admin console structure | infra (admin) |
| `2026-04-30-w9-2-run-id-wiring-phase-2.md` | run_id contract field | shared (Data-Agent-Shared-Spec §4.2) |
| `2026-04-30-w9-3-intent-classifier-benchmark.md` | RAG classifier benchmark | Agentic RAG |
| `2026-04-30-w9-5-m2-4-dogfood.md` | M2.4 dogfood | Agentic RAG |
| `2026-05-02-w10-3-retrieval-service-4-domains.md` | Retrieval service across 4 domains | shared (service layer) |
| `2026-05-02-w10-5-get-object-related.md` | Cross-domain object linkage | shared |
| `2026-05-02-w10-6-batch-d-sqlite-retire.md` | SQLite retirement | infra (storage) |
| `2026-05-02-w10-6-1-domains-py-postgres.md` | domains.py Postgres | infra (admin) |
| `2026-05-02-w11-1-c-type-classifier.md` | C-type classifier | Agentic RAG |
| `2026-05-02-w11-2-g-clarification-ux.md` | G clarification UX | Agentic RAG (front-end) |
| `2026-05-02-w11-3-d-narrowing-last-result-set.md` | D narrowing | Agentic RAG |
| `2026-05-02-w11-4-e-web-search-synthesis.md` | E web search | Agentic RAG |
| `2026-05-02-w11-5-chat-session-postgres.md` | Chat session storage | Agentic RAG |
| `2026-05-02-w11-6-multi-domain-entity-stack.md` | Multi-domain entities | Agentic RAG |
| `2026-05-02-w11-7-summary-generator-raw-text.md` | Summary generator | shared (LLM) |
| `2026-05-02-w12-7-summary-quality-gate.md` | Summary quality gate | shared (quality) |
| `2026-05-02-w13-13-quality-status-exposure.md` | quality_status exposure | shared |
| `2026-05-02-w13-15-test-fixture-pollution.md` | Test fixture | infra (tests) |
| `2026-05-02-w13-2-cross-domain-relation-writers.md` | Cross-domain relations | shared |
| `2026-05-02-w13-4-c-type-endpoint-handler.md` | C endpoint handler | Agentic RAG |
| `2026-05-02-w13-6-quality-status-alembic-v019.md` | quality_status migration | shared (storage) |
| `2026-05-02-w13-7-classifier-prompt-tune.md` | Classifier prompt tune | Agentic RAG |
| `2026-05-02-w13-8-web-search-news-connector.md` | Serper news connector | shared (search) |
| `2026-05-02-w13-9-milvus-real-client-explicit.md` | Milvus client | infra (storage) |
| `2026-05-02-w13-D1-evaluation-summary-decision.md` | Eval summary | shared (eval) |
| `2026-05-02-w13-D2-quality-status-promotion-flow.md` | quality_status flow | shared |
| `2026-05-02-w13-V3-intent-benchmark-archive.md` | Intent benchmark archive | Agentic RAG |

---

## Phase 1A summary

| Domain | Canonical declared? | Source | Document-debt count |
|---|---|---|---|
| Company | ✅ | `docs/Company-Data-Agent-PRD.md` | 0 |
| Paper | ✅ | `docs/Paper-Data-Agent-PRD.md` + `Paper-Collection-Multi-Source-Design.md` (companion) | 1 (relationship not formally declared) |
| Patent | ✅ | `docs/Patent-Data-Agent-PRD.md` | 0 |
| Professor | ✅ | `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` (per user declaration 2026-05-10) | 3 (audit untracked + PRD pivot + stale OpenSpec change) |

Cross-domain debts surfaced:
- `multi-turn-design-partial-001` — Multi-turn design vs current code
- `agentic-rag-prd-vs-guide-001` — PRD vs Operating-Guide relationship
- `agents-specs-frozen-but-uncategorized-001` — 47 frozen specs need touch-time triage

All document-debt entries are recorded in `openspec/debt-register.md`.

## Phase 1B / 1C scope (out of this inventory)

The following actions are out of Phase 1A scope and will require their own OpenSpec changes:

- ~~`audit-doc-untracked-001`: track `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` into git~~ — **resolved 2026-05-10** by `resolve-professor-canonical-baseline` T1
- ~~`professor-canonical-pivot-001`: PRD legacy handling decision~~ — **resolved 2026-05-10** by `resolve-professor-canonical-baseline` T2
- ~~`professor-prd-change-001`: re-target / abandon / archive the stale OpenSpec change~~ — **resolved 2026-05-10** by `resolve-professor-canonical-baseline` T3 (archived as `2026-05-10-refine-professor-data-agent-prd`)
- ~~`professor-prd-change-002`: rewrite spec into proper Requirement / Scenario form~~ — **resolved 2026-05-10** transitively (resolved-by-archive)
- `multi-turn-design-partial-001`: align design doc with current SessionContext code
- `agentic-rag-prd-vs-guide-001`: formalize PRD ↔ Operating-Guide relationship
- `paper-companion-design-relationship-001`: formalize Paper PRD ↔ Multi-Source-Design relationship
- `agents-specs-frozen-but-uncategorized-001`: per-spec frontmatter triage of 47 `.agents/specs/2026-*.md`
- `copilot-openspec-artifacts-001`: decide on `.github/` Copilot OpenSpec artifacts

Phase 1B / 1C may either bundle related items into a single OpenSpec change (e.g., all Professor pivot items into one) or split into focused changes. Decision deferred.

The four Professor items above were bundled into a single OpenSpec change `resolve-professor-canonical-baseline` (proposed + executed 2026-05-10; now archived at `openspec/changes/archive/2026-05-10-resolve-professor-canonical-baseline/`). The remaining five items are still open. Eleven additional doc-debt entries surfaced from the Company / Paper / Patent reconciliation audits (commit `b6057dd`) are tracked separately in `openspec/debt-register.md` and are not part of this Phase 1A inventory.
