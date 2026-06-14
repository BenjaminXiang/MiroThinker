# Change Ledger

Per CLAUDE.md §14 / AGENTS.md §15. Every OpenSpec change is registered here. Status workflow: `proposed` → `in-implementation` → `in-verification` → `tasks-complete-not-archived` → `archived`. Weight follows CLAUDE.md §8 (Tiny / Standard / Epic).

## Active and pending

| Change ID | Type | Capability | Source | Status | Weight | Risk | Agent Run | PR | Archive |
|---|---|---|---|---|---|---|---|---|---|
| prof-admin-workbench-ui | feat (admin API + workbench UI + action log) | professor-admin-workbench-ui | `prof-admin-workbench` child 3 | proposed | Standard | medium-high | — | n/a | no |

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
