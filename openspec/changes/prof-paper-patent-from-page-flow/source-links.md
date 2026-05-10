# Source Links: prof-paper-patent-from-page-flow

## Canonical sources (read by this change)

- `docs/Paper-Requirement-Review-2026-05-10.md` — locked decisions:
  - **§3.1 P2** summary_zh shape (Chinese paragraph 200-400 chars)
  - **§3.1 P3** summary_text contract (= summary_zh; admin API fix
    deferred to separate change `paper-summary-text-contract-fix`)
  - **§3.1 P4** preprint minimum fields (title + year + venue + authors)
  - **§3.1 P7** PRD §5.2 source list rewrite (discovery=prof-page;
    enrichment=OpenAlex priority + Crossref + S2 + arXiv)
  - **§3.1 P9** attribution: full trust pages, no multi-signal validation
  - **§3.1 P10** enrichment merge priority (DOI-match → OpenAlex primary
    + field-level fallback)
  - **§3.1 P11** dedup chain (DOI > Arxiv > title-fuzzy + author Jaccard)
  - **§3.1 P15** quality_status 6 enum values
  - **§3.1 P16** §7.4 freshness signal as core requirement
  - **§3.2 C1-C7** carry-overs from Professor Review (Theme 7.1, etc.)
- `docs/Professor-Requirement-Review-2026-05-10.md` — Theme 7.1
  (discovery scope), Theme 4.5/4.6 (paper_summary / patent_summary —
  but those are `prof-summary-fields` change, not this one), Theme
  9.1 (boilerplate detection)
- `docs/Paper-Data-Agent-PRD.md` — §3.1 周期性采集范围 (locked-decision-
  consistent), §4.1 minimum fields, §5.1-5.6 (post Paper Review P7
  rewrite), §6 dedup, §7 反哺, §8.1 quality, §11 acceptance KPIs
- `docs/Paper-Collection-Multi-Source-Design.md` — §2 enrichment
  field priority, §6 contract status (per Paper Review P6 already
  acknowledged as Phase B form)
- `docs/Patent-Data-Agent-PRD.md` — §4 fields, §5 ingest, used as
  patent-side reference for the from-prof-page sub-flow (full Patent
  review still TBD; only the from-prof-page sub-flow is locked here)
- `docs/Data-Agent-Shared-Spec.md` — §4.2.1 summary_text semantics,
  §4.5 evidence shape, §5.3 multi-source ordering
- `docs/audits/paper-requirement-code-reconciliation-2026-05-10.md` —
  audit drift items: paper-prd-source-list-stale-001,
  paper-prd-summary-zh-schema-shape-001 (resolved by this change's
  spec)

## Existing code consulted (read but mostly unchanged in this spec
— implementation slice will modify)

- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` —
  498 lines; **canonical discovery path** per this change's spec.
  Codified, not greenfielded. May need minor additions for
  evidence.source_type and pipeline_issue filing.
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py` — 182 lines;
  **refactored** by this change's spec from discovery role to
  enrichment-only role
- `apps/miroflow-agent/src/data_agents/paper/pipeline.py` — 129
  lines; **deprecated** by this change's spec (S2-as-discovery)
- `apps/miroflow-agent/src/data_agents/paper/identity_gate.py` —
  verified by this change's spec; minor refinements (page-only
  short-circuit) per T5
- `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py` —
  140 lines; produces summary_zh, aligned to spec by T6
- `apps/miroflow-agent/src/data_agents/paper/release.py` — 252 lines;
  may host the new quality-promotion state machine
- `apps/miroflow-agent/src/data_agents/paper/openalex.py` — 590
  lines; existing OpenAlex client. Refactored T1.
- `apps/miroflow-agent/src/data_agents/paper/crossref.py` — existing
  Crossref client. Refactored T1.
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py` —
  363 lines; existing S2 client. Refactored T1.
- `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py` —
  paper canonical upsert helpers
- `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
  — existing Publications HTML parser. Reused by spec.
- `apps/miroflow-agent/src/data_agents/patent/release.py` — 253 lines;
  patent canonical writer (xlsx ingest path)
- `apps/miroflow-agent/src/data_agents/patent/canonical_writer.py` —
  236 lines; patent upsert helpers (extended by T4 for prof-page path)
- `apps/miroflow-agent/src/data_agents/contracts.py` — 403 lines;
  PaperRecord / PatentRecord shapes (V019 already has quality_status
  enum 6 values; no contract change in this spec)
- `apps/miroflow-agent/alembic/versions/V004_init_paper_patent_domain.py`
  — patent canonical schema (relevant for T4 NOT NULL check)
- `apps/miroflow-agent/alembic/versions/V005a_init_professor_paper_link.py`
  — `professor_paper_link` table
- `apps/miroflow-agent/alembic/versions/V005b_init_cross_domain_relations.py`
  — `professor_patent_link` table (under `cross_domain_relations`)

## Cross-references to existing artifacts

- `docs/index.md` — doc-layering tree + status matrix; minor update
  after this change ships (Paper PRD row note)
- `docs/data-agent-domain-index.md` — Phase 1A inventory; this change
  is Phase 1B+ work
- `openspec/specs/` — currently empty; this change creates
  `paper-patent-from-prof-page/` capability on archive (per `openspec
  archive` workflow without `--skip-specs`)
- `openspec/debt-register.md` — relevant entries:
  - `paper-prd-source-list-stale-001` → decision-locked; spec ↔ doc
    rewrite is `paper-prd-source-list-rewrite` change
  - `paper-prd-summary-zh-schema-shape-001` → decision-locked; PRD
    rewrite is part of `paper-prd-source-list-rewrite`
  - `paper-summary-text-contract-drift-001` → decision-locked; admin
    API fix is `paper-summary-text-contract-fix`
  - `paper-companion-design-relationship-001` → decision-locked
  - `paper-prd-msd-phase-a-rule-stale-001` → decision-locked
  - `paper-prd-config-surface-001` → decision-locked

## Cross-references to related changes

- `archive/2026-05-10-resolve-professor-canonical-baseline/` — resolved
  Professor canonical pivot
- `prof-seed-admin-console` (active, Phase A complete) — provides the
  per-row trigger button + cron entry that will eventually drive
  `run_for_single_seed` (Phase B). Phase B integration is OUT of this
  spec's scope but the spec's Requirements about discovery flow
  describe what Phase B's pipeline integration will invoke.
- `prof-summary-fields` (planned) — depends on this change (paper /
  patent canonical with summary_zh + cross-domain links must exist
  before educator-side aggregation can compute paper_summary /
  patent_summary)
- `prof-double-milvus-collection` (planned) — depends on this change
  (research vector embeds paper_summary + patent_summary)
- `prof-school-adapter-framework` (partly already implemented) — not
  blocking this change. Patents extraction here is heuristic, not
  per-school adapter

## Code paths touched by implementation (reference, not by this spec
change itself)

### Refactored
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py` — discovery →
  enrichment-only
- `apps/miroflow-agent/src/data_agents/paper/pipeline.py` — S2
  discovery deprecated
- `apps/miroflow-agent/src/data_agents/paper/identity_gate.py` —
  page-only short-circuit added
- `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py` —
  prompt aligned + boilerplate judge added

### Created (greenfield)
- `apps/miroflow-agent/src/data_agents/professor/homepage_patents.py`
- `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
- `apps/miroflow-agent/src/data_agents/patent/identity_gate.py`
- `apps/miroflow-agent/src/data_agents/paper/quality_promotion.py`
  (or extend `paper/release.py`)

### Verified or extended (existing, may need minor additions)
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` —
  add evidence.source_type tagging if missing
- `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py` —
  add 3-level dedup fallback if missing

## Code paths NOT touched

- `apps/miroflow-agent/src/data_agents/paper/openalex.py` — kept
  intact; just renamed entry function (T1)
- `apps/miroflow-agent/src/data_agents/paper/crossref.py` — kept
  intact; just renamed entry function (T1)
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py` —
  kept intact; just renamed entry function (T1)
- `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
  — reused as-is
- `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py` — xlsx
  ingest path untouched
- `apps/miroflow-agent/src/data_agents/contracts.py` — no contract
  changes in this spec (V019 already added quality_status)
- `apps/miroflow-agent/alembic/versions/` — no new migration
- `apps/admin-console/backend/api/chat.py` — chat fallback handling is
  separate change
- `apps/admin-console/backend/api/domains.py:753` — admin API fix is
  separate change `paper-summary-text-contract-fix`

## Out-of-scope artifacts (explicitly NOT changed)

- Existing scripts under `apps/miroflow-agent/scripts/` — they will
  emit deprecation warnings (per T2) but continue to work. A
  `paper-pipeline-cleanup` follow-up change removes `run_paper_pipeline`
  and migrates these scripts.
- Existing `apps/miroflow-agent/tests/data_agents/paper/test_*.py` —
  some tests for `discover_*` paths will need updates as part of T1.5,
  but this is mechanical renaming + minor fixture refactor.

## Originating user instructions

- 2026-05-10 walk-through with user; Theme 7.1 + Paper Review P1-P16
  decisions captured in
  `docs/Paper-Requirement-Review-2026-05-10.md`. This change is
  Paper Review §6 priority list item #1.
