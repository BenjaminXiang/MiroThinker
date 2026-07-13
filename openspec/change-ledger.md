# Change Ledger

Per CLAUDE.md §14 / AGENTS.md §15. Every OpenSpec change is registered here. Status workflow: `proposed` → `in-implementation` → `in-verification` → `tasks-complete-not-archived` → `archived`. Weight follows CLAUDE.md §8 (Tiny / Standard / Epic).

## Active and pending

| Change ID | Type | Capability | Source | Status | Weight | Risk | Agent Run | PR | Archive |
|---|---|---|---|---|---|---|---|---|---|
| rebuild-canonical-v2-knowledge-platform | breaking Epic (evidence landing → typed Canonical V2 → versioned release/index → evidence-first query/answer) | recovery-evidence-landing + canonical-v2-knowledge + canonical-v2-release + evidence-first-query-orchestration + grounded-progressive-answer + knowledge-gap-feedback | user-confirmed logical rebuild 2026-07-11; sole-mainline and aggregate-S6 Git promotion decisions 2026-07-13 | in-implementation (35/75; S5G and Tasks 6.1-6.7 Accepted; Task 6.8/Aggregate S6 next; Git `main` fast-forward only after aggregate S6 Accepted) | Epic | high | `.agents/runs/rebuild-canonical-v2-knowledge-platform/` | n/a | no |
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
| unify-data-quality-gating | feat (paper write-path gate wire + Milvus rebackfill coupling + batch reconciliation; company cut 0-delta; patent out-of-scope source-data) | data-quality-gating | cross-domain audit 2026-06-26 (DB-grounded) | tasks-complete-not-archived (code+tests + DB apply done: real gate delta **25** papers promoted partial/needs_enrichment→ready [not heuristic 66; 22 already-rejected + 19 already-needs_review unchanged], **0 ready degraded**, 25 indexed in paper_chunks [51 chunks], 5/5 retrieval spot-check self@rank0) | Standard | medium | `.agents/runs/unify-data-quality-gating/` | n/a | no |
| infer-patent-type-from-patent-number | feat (infer patent_type from CN patent_number kind-code A/B/U/Y/S/D + relax gate date-signal to accept publication_date → 11,408 partial→ready→retrievable; applied + Milvus rebackfilled; inventors deferred data-blocked) | patent-type-inference | cross-domain audit 2026-06-26 (DB-grounded, feasibility-verified) | tasks-complete-not-archived (11,408 applied+indexed; 5/5 retrieval spot-check; 1 pre-existing unrelated test_release failure) | Standard | medium | `.agents/runs/infer-patent-type-from-patent-number/` | n/a | no |
| recover-paper-shells-via-realtime-resolution | feat (realtime re-resolution of prof_page_only shells; staged A-D) | paper-shell-recovery | brainstorming 2026-06-28 (DB+empirical grounded) | tasks-complete-not-archived (Stage A: 1,902 resolved/merged [228 new + ~1,615 attribution-merges]; Stage B: 228 summary_zh; Stage C: indexed 1,287, 5/5 retrieval spot-check; Stage D: residual marked. Honest outcome: ~224 NEW retrievable (ready 23,208→23,432) + ~1,615 attribution-merges; ingest-fix dropped — None-default already realtime; residual ~1,607+ bounded, not faked) | Epic | medium | `.agents/runs/recover-paper-shells-via-realtime-resolution/` | n/a | no |
| merge-paper-exact-title-duplicates | feat (Tier 2 auto-merge: exact-title + identical-author-list groups → 1 canonical + migrated links; reuses Stage-A merge pattern; pilot-gated with adversarial title-match; Tier 1 empty/constraint-enforced; Tier 3 review-gated separate) | paper-dedup | first-principles dedup 2026-06-29 (post-Stage-A grounded) → APPLIED 2026-06-29: implemented candidate SQL (excludes merged/rejected from HAVING) = **921 groups / 1,857 rows** (strict superset of the 804/2,135 grounding; DB verified stable); **936 merges**, 936 aliases (+933 net, 3 repointed), 0 false-merges, ready_degraded=15 (bounded/reversible/self-healing; 644/921 canonicals ready), retrieval spot-check clean, 6/6 unit tests green | in-verification | Standard | medium | `.agents/runs/merge-paper-exact-title-duplicates/` | n/a | no |
| correct-paper-tier2-overmerge-view-b | fix (View B canonical-correction: flip conf→journal over-merge #1 + Tier-3 DOI-conflict exclusion in Tier-2 candidate SQL; #7 human-review, #13 deferred) | paper-dedup (modified) | post-acceptance audit 2026-06-30 (DB-grounded; 13 DOI-conflict groups, 7 conf↔journal over-merges) → APPLIED 2026-06-30: #1 flipped (journal PAPER-64D7A39FC25B now canonical/ready/retrievable, conf hidden; alias reversed, links un-reject/reject, no attribution loss; online /api/chat spot-check J returned / C absent; no Milvus refresh needed); #7 verified same-work dual-publication (near-identical abstracts + 5 authors) → no flip; #13 deferred (no retrieval impact); Tier-3 DOI-conflict exclusion added (prospective); 14 unit tests green | in-verification | Standard | medium | `.agents/runs/correct-paper-tier2-overmerge-view-b/` | n/a | no |
| fix-chat-retrieval-recall-gaps | feat (hybrid RRF + cross-filter professor routing; re-truthed to measured 58% baseline; candidate_limit raise reverted as eval-NEUTRAL; web-augment split to add-web-augment; FM3 data-blocked; FM1a ingest gated) | agentic-rag-retrieval | first-principles diagnosis 2026-06-29 (DB+Milvus-grounded) → re-measured 2026-07-01: recall 58% (11/19, no-web, Serper 403 → web dead); 74% commit claim non-reproducible (depended on now-dead Serper key); RRF rescues broad-profile (普渡); precision/latency oracles built (准/快 axes); FM1a ingest gated (6 absent entities, 67% miss = data not retrieval); openspec validate --strict 0 | in-verification | Standard | medium | `.agents/runs/retrieval-generation-alignment/` | n/a | no |
| add-web-augment | feat (web-search augmentation: Serper 403 fix + web behavior contract + provenance + precision audit; SKELETON/proposed, not implemented) | agentic-rag-retrieval (modified) | Phase-1 measurement 2026-07-01: Serper 403 -> web dead (0 contribution to 58% recall); 74% commit claim non-reproducible; split out of recall change so recall contract not hostage to dead credential; skeleton records defect + contract obligations | proposed | Standard | medium | `.agents/runs/retrieval-generation-alignment/` | n/a | no |
| add-synthesis-timeout | fix (synthesis timeout 3s->60s default + CHAT_SYNTHESIS_TIMEOUT env override; answers taking 4-59s now complete vs time out; behavior-affecting) | agentic-rag-retrieval (modified) | delivered 0572d06 + test 8da9053; contracts it as behavior-affecting per §8 (not a behavior-preserving refactor) | in-verification | Tiny | low | — | n/a | no |

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
- Governance refresh 2026-06-26 (read-only `miroflow_real` scan, proxy unset): the 6/22
  counts were materially wrong for company/patent. Real: company **6,514/6,514 ready
  (100%)** (was 1,013/1,024); patent **11,408 / 0 ready (all `partial`)** (was 1,931/1,931)
  because `patent_type` is NULL on every row → gate returns `partial` → 0 retrievable;
  `professor_patent_link` **0 rows** (R17 not wired; `release.py:60 inventors=[]`
  hardcoded + no `upsert_professor_patent_link` in canonical_writer); `summary_text` 100%
  `fallback_template`; professor `canonical_name_en` missing **77** (portfolio's "3,314
  missing" inverted present/missing); paper `unverified` **28,403** (was 53,165; W0b 7,193 +
  title-cleanup 528 applied), ready-worthy-but-not-ready **66** (gate bypass residual).
  `docs/index.md` got a 2026-06-26 correction block + matrix fixes. New highest-leverage
  retrieval gap surfaced: **patent 0/11,408 retrievable** (separate `patent_type` ingest
  fix, not the gating change). Cross-domain structural changes 2026-06-26:
  `unify-data-quality-gating` registered (downgraded Epic→Standard after 66/0 real delta;
  company cut, patent out-of-scope as source-data). `harden-entity-normalization`
  **withdrawn** — its premise (person-name matching for inventor links) was invalidated by
  the same scan: `inventors_parsed` is empty `[]` for all 11,408 patents (no xlsx inventor
  column alias; R20), so there is no inventor data to link. A `wire-professor-patent-
  inventor-linking` (R17) change is **not viable** until patent inventor data is sourced
  (separate patent-sourcing change) — pivot pending user decision.

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
