# Change Ledger

Per CLAUDE.md §14 / AGENTS.md §15. Every OpenSpec change is registered here. Status workflow: `proposed` → `in-implementation` → `in-verification` → `tasks-complete-not-archived` → `archived`. Weight follows CLAUDE.md §8 (Tiny / Standard / Epic).

## Active and pending

| Change ID | Type | Capability | Source | Status | Weight | Risk | Agent Run | PR | Archive |
|---|---|---|---|---|---|---|---|---|---|
| sigs-official-publications-to-paper-domain | feat (parse SIGS author-prefixed publications → paper domain + bridge + rollout) | sigs-official-publications-to-paper-domain | portfolio 2026-05-27 | in-verification (116/116; bounded progress, not all-school) | Epic | medium | `.agents/runs/sigs-official-publications-to-paper-domain/` | n/a | no |
| professor-core-profile-paper-quality | feat (end-to-end quality contract: prof profile → homepage papers → enrichment → dedup → summary → promotion → presentation) | professor-core-profile-paper-quality | portfolio 2026-06-13 | in-verification (41/41; 5 dataset gates pending) | Standard/Epic | medium-high | `.agents/runs/professor-core-profile-paper-quality/` | n/a | no |
| professor-dataset-candidate-generation | feat (source-grounded candidate layer for 4 closure lanes + gate + closure) | professor-dataset-candidate-generation | portfolio 2026-06-14 | in-verification (90/90; production write-mode not complete) | Standard→Epic | medium | `.agents/runs/professor-dataset-candidate-generation/` | n/a | no |
| professor-dataset-quality-closure | feat (controlled dataset closure: bucketing + dry-run gates + batch writes + residual-risk) | professor-dataset-quality-closure | portfolio 2026-06-13 | in-verification (37/37; real write-mode not executed) | Standard | medium | `.agents/runs/professor-dataset-quality-closure/` | n/a | no |
| paper-source-gap-remediation-lanes | feat (split missing summary_zh/abstract_clean into 5 remediation lanes) | paper-homepage-enrichment-completion + paper-fulltext-from-prof-page + paper-pipeline-cleanup (modified) | portfolio 2026-06-15 | tasks-complete-not-archived (27/27; acceptance Passed) | Standard | medium | `.agents/runs/paper-source-gap-remediation-lanes/` | n/a | no |
| ingest-dedup-anchor-before-insert | feat (content-anchor dedup before INSERT: DOI > arxiv > title+year, link-attach on hit; removed author-overlap gate) | paper-ingest-dedup | portfolio 2026-06-22 Phase 2 | in-implementation (fix applied + 194 tests GREEN; close-out pending) | Standard | medium | — | n/a | no |
| title-resolver-web-attribution-gate | feat (W1a: web tier gate — DOI/arxiv OR title≥0.85+author-Jaccard≥0.3, fail-closed) | paper-web-attribution-gate | portfolio 2026-06-22 Phase 3 | archived 2026-06-23 (gate applied + 88 tests GREEN; spec migrated to openspec/specs/paper-web-attribution-gate) | Standard | medium | — | n/a | yes (2026-06-23-title-resolver-web-attribution-gate) |
| abstract-web-reader-fallback | feat (W2a: 4-empty → Jina reader fetches row pdf_url/landing_page → paper_full_text) | paper-source-acquisition | portfolio 2026-06-22 Phase 3 (blocked by W1a) | proposed | Standard | medium | — | n/a | no |
| duplicate-paper-review-workflow | feat (W2e: human/LLM review for no-DOI dup groups; merge_alias on confirm) | paper-dedup | portfolio 2026-06-22 Phase 4 | proposed | Standard | medium | — | n/a | no |
| homepage-cms-selector-coverage | feat (W2c: per-seed citation-template extraction fixes) | paper-homepage-extraction | portfolio 2026-06-22 Phase 5 | proposed | Standard | medium | — | n/a | no |
| professor-profile-field-completion-pipeline | feat (4-layer template-agnostic professor field completion + gate + closure) | professor-profile-field-completion | cleanup gap-analysis 2026-06-16 | proposed | Epic | medium | — | n/a | no |
| professor-fact-cross-format-dedup | feat (format-normalizing semantic dedup key + universal keep-richest writer; route all 7 professor_fact insert paths; no schema change) | professor-fact-extraction (modified) | cleanup gap-analysis 2026-06-23 | in-verification (impl done + self-review accept; 42 touched tests GREEN, 25 pre-existing unrelated failures; not committed) | Standard | medium | `.agents/runs/professor-fact-cross-format-dedup/` | n/a | no |

## Notes

- `refine-professor-data-agent-prd` was archived 2026-05-10 as `2026-05-10-refine-professor-data-agent-prd`. T3.1 verification (recorded in `resolve-professor-canonical-baseline` `acceptance.md`) found T1–T5 marked `[x]` but never landed in PRD body; combined with the user's 2026-05-10 canonical pivot demoting the PRD to legacy, retroactive application of T1–T5 had no value. CLI emitted a non-blocking `## Why` / `## What Changes` warning corresponding to debt `professor-prd-change-002` (resolved-by-archive).
- `resolve-professor-canonical-baseline` was the first Phase 1B change (CLAUDE.md §14.6). Doc-only governance, no `specs/`, no `design.md`. Bundled and resolved four Professor-domain debt entries (`audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002`). Archived 2026-05-10 as `2026-05-10-resolve-professor-canonical-baseline` after all four debts moved to Resolved in `debt-register.md`.
- Phase-0+ artifacts (`acceptance.md`, `change-log.md`, `source-links.md`, `agent-links.md`) were not present in `refine-professor-data-agent-prd` and are grandfathered — they are required only for new changes per CLAUDE.md §14.4.
- Follow-up rows registered on 2026-05-13 started as ledger placeholders.
  On 2026-05-15, `paper-pipeline-cleanup`, `prof-summary-fields`,
  `prof-double-milvus-collection`, `prof-lifecycle-state`,
  `patent-page-only-canonical`, and `paper-pdf-fulltext-ingest` were
  expanded into full OpenSpec directories so implementation can proceed
  without relying on informal carry-over notes. `prof-lifecycle-state`
  must model lifecycle separately from
  `quality_status`: quality answers whether data is trustworthy; lifecycle
  answers whether the person is still active at that school.
- `paper-pdf-fulltext-ingest` registered 2026-05-13. Builds on existing
  V011 `paper_full_text` + `paper/full_text_fetcher.py` +
  `paper/homepage_ingest.py` (already wired for arXiv-style PDF fetching).
  Scope: prof-page PDF link discovery, raw-PDF persistence by sha256,
  cap policy, `pdf_fetch` issue stage. Not greenfield.
- `prof-admin-workbench` registered 2026-05-14. Epic parent; carries
  Epic-level `proposal.md` + `design.md` only. Three child changes
  (`prof-quality-status-rework`, `prof-fact-extraction-expansion`,
  `prof-admin-workbench-ui`), sequenced quality-first and then
  data-first. Child 1 (`prof-quality-status-rework`) is archived as
  `archive/2026-05-23-prof-quality-status-rework/`; Child 2
  (`prof-fact-extraction-expansion`) and the parent workspace are also
  archived. Remaining active child work is Child 3
  (`prof-admin-workbench-ui`).

- `wire-paper-identity-gate-rejection` registered 2026-06-16. First change
  opened from `docs/plans/2026-06-16-dirty-data-gap-closure-portfolio.md`
  (W0b, Gap B). New capability `paper-identity-status`. Note: this ledger's
  active table is still missing the other active (un-archived) changes under
  `openspec/changes/` (paper-source-gap-remediation-lanes,
  professor-core-profile-paper-quality, professor-dataset-candidate-generation,
  professor-dataset-quality-closure, sigs-official-publications-to-paper-domain);
  full reconciliation is portfolio task W3b (`governance-ledger-index-reconcile`).

- Portfolio re-baseline 2026-06-22 (`docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md`):
  re-grounds the professor→paper gap-closure effort in a fresh `miroflow_real` scan.
  Several 6/15 "large" gaps are now small (profile_summary<200: 3; research_overview
  missing: 839; DOI pollution: 0; run_id: 0 null; education missing: 239). The
  `professor-profile-field-completion-pipeline` Epic is **downgraded** (real residual
  ~240, not "6/10 schools 0%"). `wire-paper-identity-gate-rejection` (Phase 1)
  re-baselined to 28,928 eligible (was 1,519 on 6/16; growth from fresh UPC/crawl
  output), 0 `ready` in the eligible set → moved to `in-implementation`. Phases 2–6
  registered above as `proposed` placeholders; Phase 6 field/link work reuses the
  downgraded `professor-profile-field-completion-pipeline` capability + a future
  D7 paper-link-verification change (not yet registered). Full W3b ledger/index
  reconcile **executed 2026-06-22 (Phase 0)**: 5 missing active changes added with
  accurate statuses; `prof-admin-workbench-ui` moved active→archived (it was archived
  2026-05-23 but stale in the active table); 18 missing archived rows added (archive
  dir 34/34 now covered); `docs/index.md` re-baselined to 2026-06-22.

## Archived

| Change ID | Archived as | Type | Capability | Status at archive | Weight | Risk | Archived on |
|---|---|---|---|---|---|---|---|
| refine-professor-data-agent-prd | `archive/2026-05-10-refine-professor-data-agent-prd/` | docs + architecture intent | professor data collection | premise-invalidated; T1–T5 marked but never shipped | Standard | low | 2026-05-10 |
| resolve-professor-canonical-baseline | `archive/2026-05-10-resolve-professor-canonical-baseline/` | doc-governance (no behavior, no code) | professor data collection — canonical baseline | tasks-complete (T1–T4 all executed; debts 4/4 resolved) | Lite+ | low | 2026-05-10 |
| paper-summary-text-contract-fix | `archive/2026-05-10-paper-summary-text-contract-fix/` | bugfix (admin API contract drift) | paper-canonical-api-projection | tasks-complete (1-line code + 2 test updates + spec delta); resolves debt paper-summary-text-contract-drift-001 | Lite | low | 2026-05-10 |
| paper-pipeline-cleanup | `archive/2026-05-23-paper-pipeline-cleanup/` | refactor (retire legacy paper discovery path) | paper-pipeline-cleanup | tasks-complete; verification artifact recorded and specs synced | Standard | medium | 2026-05-23 |
| paper-homepage-enrichment-completion | `archive/2026-05-23-paper-homepage-enrichment-completion/` | feat/refactor (page-flow enrichment + vector refresh contract) | paper-homepage-enrichment-completion | tasks-complete; T4/T5 summary-to-Milvus targeted refresh E2E verified and specs synced | Standard | medium | 2026-05-23 |
| paper-pdf-fulltext-ingest | `archive/2026-05-23-paper-pdf-fulltext-ingest/` | feat (prof-page PDF discovery + raw-PDF persistence + cap policy) | paper-fulltext-from-prof-page | tasks-complete; T1-T4 direct PDF/full-text/raw blob E2E verified and specs synced | Standard | medium | 2026-05-23 |
| prof-admin-workbench | `archive/2026-05-23-prof-admin-workbench/` | epic parent (quality-status rework + admin audit workbench + fact extraction) | professor-admin-workbench | parent workspace complete; remaining UI child stays active separately | Epic | medium-high | 2026-05-23 |
| prof-double-milvus-collection | `archive/2026-05-23-prof-double-milvus-collection/` | feat (split professor identity/research vectors) | professor-retrieval-index-split | tasks-complete; split-collection verification artifact recorded | Standard | medium-high | 2026-05-23 |
| prof-fact-extraction-expansion | `archive/2026-05-23-prof-fact-extraction-expansion/` | feat (structured facts + profile summary backfill) | professor-fact-extraction | tasks-complete; fact extraction/backfill verification artifact recorded | Standard | medium | 2026-05-23 |
| prof-lifecycle-state | `archive/2026-05-23-prof-lifecycle-state/` | feat (professor lifecycle separate from quality) | professor-lifecycle-state | tasks-complete; V030 lifecycle-state verification recorded | Standard | medium | 2026-05-23 |
| prof-quality-status-rework | `archive/2026-05-23-prof-quality-status-rework/` | feat/refactor (quality engine + canonical write + re-eval) | professor-quality-status | tasks-complete; real DB dry-run/write/idempotence evidence recorded | Standard | medium | 2026-05-23 |
| prof-paper-patent-from-page-flow | `archive/2026-05-23-prof-paper-patent-from-page-flow/` | feat (codify) + refactor (deprecate S2 discovery) + new patent extraction | paper-patent-from-prof-page | tasks-complete with explicit follow-up carry-overs | Standard | medium | 2026-05-23 |
| prof-seed-admin-console | `archive/2026-05-23-prof-seed-admin-console/` | feat (new admin UI + schema + endpoint + pipeline trigger) | professor-seed-management | tasks-complete; P1 close-out E2E reverified and specs synced | Standard | low-medium | 2026-05-23 |
| prof-seed-ops-hardening | `archive/2026-05-23-prof-seed-ops-hardening/` | feat/refactor (bounded trigger + failure taxonomy) | professor-seed-ops-hardening | tasks-complete; P3 sample E2E and browser walkthrough verified and specs synced | Standard | medium | 2026-05-23 |
| prof-summary-fields | `archive/2026-05-23-prof-summary-fields/` | feat (professor paper/patent aggregate summaries) | professor-summary-fields | tasks-complete; professor output summary verification artifact recorded | Standard | medium | 2026-05-23 |
| patent-page-only-canonical | `archive/2026-05-23-patent-page-only-canonical/` | feat (preserve title-only page patents) | patent-page-only-canonical | tasks-complete; title-only patent canonical/Postgres/migration verification recorded and specs synced | Standard | medium | 2026-05-23 |
| prof-admin-workbench-ui | `archive/2026-05-23-prof-admin-workbench-ui/` | feat | professor-admin-workbench-ui | tasks-complete (verification recorded) | Standard | medium | 2026-05-23 |
| prof-seed-adapter-coverage | `archive/2026-05-24-prof-seed-adapter-coverage/` | feat | professor-seed-adapter-coverage | tasks-complete (verification recorded) | Standard | medium-high | 2026-05-24 |
| prof-blocked-seed-source-remediation | `archive/2026-05-25-prof-blocked-seed-source-remediation/` | feat | professor-blocked-seed-source-remediation | tasks-complete (verification recorded) | Standard | medium | 2026-05-25 |
| prof-final-validation | `archive/2026-05-25-prof-final-validation/` | feat | professor-final-validation | tasks-complete (verification recorded) | Standard | medium-high | 2026-05-25 |
| prof-post-full-quality-audit | `archive/2026-05-25-prof-post-full-quality-audit/` | feat | professor-post-full-quality-audit | tasks-complete (verification recorded) | Standard | medium | 2026-05-25 |
| prof-publish-index-refresh | `archive/2026-05-25-prof-publish-index-refresh/` | feat | professor-publish-index-refresh | tasks-complete (verification recorded) | Standard | medium-high | 2026-05-25 |
| prof-seed-controlled-full-recollection | `archive/2026-05-25-prof-seed-controlled-full-recollection/` | feat | professor-seed-controlled-full-recollection | tasks-complete (verification recorded) | Standard | medium-high | 2026-05-25 |
| prof-seed-recollection-readiness | `archive/2026-05-25-prof-seed-recollection-readiness/` | feat | professor-seed-recollection-readiness | tasks-complete (verification recorded) | Standard | medium | 2026-05-25 |
| prof-title-contamination-repair | `archive/2026-05-25-prof-title-contamination-repair/` | bugfix | professor-profile-field-extraction-integrity | tasks-complete (verification recorded) | Standard | medium | 2026-05-25 |
| company-enrichment-source-closure | `archive/2026-05-28-company-enrichment-source-closure/` | feat (epic parent) | company-enrichment-source-closure | tasks-complete (verification recorded) | Epic | high | 2026-05-28 |
| company-enrichment-business-closure | `archive/2026-06-02-company-enrichment-business-closure/` | feat (epic parent) | company-enrichment-business-closure | tasks-complete (verification recorded) | Epic | high | 2026-06-02 |
| company-iyiou-site-search-live-fix | `archive/2026-06-02-company-iyiou-site-search-live-fix/` | bugfix | company-enrichment-source-closure (modified) | tasks-complete (verification recorded) | Standard | medium | 2026-06-02 |
| company-prd-acceptance-closure | `archive/2026-06-02-company-prd-acceptance-closure/` | feat (epic parent) | company-prd-acceptance-closure | tasks-complete (verification recorded) | Epic | medium-high | 2026-06-02 |
| company-scaleout-enrichment-hardening | `archive/2026-06-02-company-scaleout-enrichment-hardening/` | feat (epic parent) | company-scaleout-enrichment-hardening | tasks-complete (verification recorded) | Epic | high | 2026-06-02 |
| company-synthesis-enrichment-pipeline | `archive/2026-06-02-company-synthesis-enrichment-pipeline/` | feat (epic parent) | company-synthesis-enrichment-pipeline | tasks-complete (verification recorded) | Epic | high | 2026-06-02 |
| prof-sigs-tab-template-extraction | `archive/2026-06-02-prof-sigs-tab-template-extraction/` | feat | professor-sigs-tab-template-extraction | tasks-complete (verification recorded) | Standard | low | 2026-06-02 |
| professor-detail-readability | `archive/2026-06-02-professor-detail-readability/` | feat/refactor | professor-detail-readability | tasks-complete (verification recorded) | Standard | low | 2026-06-02 |
| professor-list-summary-visibility | `archive/2026-06-02-professor-list-summary-visibility/` | feat | professor-list-summary-visibility | tasks-complete (verification recorded) | Tiny | low | 2026-06-02 |
| wire-paper-identity-gate-rejection | `archive/2026-06-23-wire-paper-identity-gate-rejection/` | feat (LLM-gate rejection → paper identity_status → Milvus exclusion) | paper-identity-status | tasks-complete; full apply 7,193 reject / 21,779 links verified, 0 `ready` (AC3); Milvus delete 33,335 rejected/merged chunks; spec migrated to openspec/specs/ | Standard | medium | 2026-06-23 |
| paper-implausible-title-cleanup | `archive/2026-06-23-paper-implausible-title-cleanup/` | feat (reject implausible-titled prof_page_only via no-LLM high-precision scan + default-exclude rejected/merged from /paper) | paper-title-cleanup | tasks-complete; 528 high-precision garbage rejected, 0 `ready`; Milvus delete; spec migrated to openspec/specs/ | Standard | medium | 2026-06-23 |
