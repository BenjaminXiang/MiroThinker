---
change_id: prof-paper-patent-from-page-flow
type: feat (codify existing path) + refactor (deprecate old discovery) + new patent extraction
weight: Standard
behavior_change: true
code_change: spec only at this stage; implementation follows
adds_requirements: true (new capability: paper-patent-from-prof-page)
created: 2026-05-10
canonical_input:
  - docs/Paper-Requirement-Review-2026-05-10.md (16 locked decisions, especially P4 / P9 / P10 / P11 / P15 / P16)
  - docs/Professor-Requirement-Review-2026-05-10.md (Theme 7.1 carry-over: discovery 仅来自教授页面 + enrichment-only)
  - docs/Paper-Data-Agent-PRD.md (§3 / §4 / §5 / §6 / §7)
  - docs/Paper-Collection-Multi-Source-Design.md (§2 enrichment 优先级 / §6 contract status)
  - docs/Patent-Data-Agent-PRD.md (§4 / §5 — patent-side coverage of prof-page discovery sub-flow)
---

# Proposal: prof-paper-patent-from-page-flow

## Why

The 2026-05-10 user reviews (Professor + Paper) locked a critical
architectural shift: **论文 / 专利 discovery 仅来自教授学校官网 / 个人主页**。
External databases (OpenAlex / Crossref / Semantic Scholar / arXiv /
DBLP / Web Search) are now relegated to **enrichment-only** roles.
Patent has exactly two sources: prof page + xlsx import (already
implemented).

The current code is partially aligned and partially mis-aligned with
this stance:

- ✅ `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
  (498 lines) already implements the prof-page → paper canonical path.
  Theme 7.1 effectively **codifies this path as the canonical
  discovery flow** rather than introducing it.
- ❌ `apps/miroflow-agent/src/data_agents/paper/pipeline.py:run_paper_pipeline`
  uses Semantic-Scholar-as-discovery — **must be deprecated**.
- ❌ `apps/miroflow-agent/src/data_agents/paper/hybrid.py` calls
  `discover_*_from_openalex / from_crossref / from_semantic_scholar`
  for discovery — **must be refactored to enrichment-only**.
- ❌ Patent extraction from prof pages is **greenfield**; current
  patent ingest is xlsx-only.

This change codifies the contract for paper / patent extraction from
professor pages (Tier 2 / Tier 3), formalizes the enrichment role for
external databases, mandates the `paper_identity_gate` and
`patent_identity_gate` semantics (same-person vs same-name only —
**not** content-truth verification), and specifies the cross-domain
link writers (`professor_paper_link`, `professor_patent_link`).

This is the highest-leverage P1 change in the Paper Review §6 priority
list. It unblocks #2 (`prof-summary-fields`) and #3
(`prof-double-milvus-collection`).

## What Changes

### ADDED capability

`openspec/specs/paper-patent-from-prof-page/` (created from this
change's `specs/` on archive).

### Spec deltas (in `specs/paper-patent-from-prof-page/spec.md`)

- ADDED Requirement: Publications 区段 extraction from Tier 2/Tier 3 pages
- ADDED Requirement: Patents 区段 extraction from Tier 2/Tier 3 pages
- ADDED Requirement: Paper canonical upsert (DOI primary + 3-level fallback)
- ADDED Requirement: Patent canonical upsert (patent_id hard match)
- ADDED Requirement: Identity gate semantics (paper + patent; same-person
  vs same-name only)
- ADDED Requirement: Async enrichment workflow (paper only; OpenAlex
  primary + Crossref/S2/arXiv supplements; field-level fallback)
- ADDED Requirement: summary_zh generation (Chinese paragraph 200-400
  chars; from abstract or title-only fallback)
- ADDED Requirement: Quality status promotion logic (needs_enrichment →
  ready / partial / rejected per LLM judge)
- ADDED Requirement: Cross-domain link writers (professor_paper_link,
  professor_patent_link upsert idempotency)
- ADDED Requirement: Deprecation of S2-as-discovery path
  (`paper/pipeline.py:run_paper_pipeline`)
- ADDED Requirement: Refactor hybrid.py to enrichment-only role

### Implementation footprint (planned, NOT done in this change)

This change writes the spec only. Subsequent slices implement:

- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` —
  already exists, 498 lines; treat as the canonical discovery entry
  point. Minor refactor: extract enrichment hand-off into a separate
  module so `hybrid.py` can be invoked post-discovery rather than as
  discovery.
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py` — refactor to
  remove discovery paths, expose only enrichment functions
  (`enrich_paper_with_openalex`, `enrich_paper_with_crossref`, etc.).
- `apps/miroflow-agent/src/data_agents/paper/pipeline.py` — mark
  `run_paper_pipeline` deprecated (will be removed in subsequent change
  after callers migrate); add deprecation warning.
- New module `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
  — patents extraction from prof Tier 2/3 pages. Calls into a new
  helper in professor module (`homepage_patents.py`) for HTML parsing
  heuristics (parallel to existing `homepage_publications.py`).
- `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py`
  (140 lines) — already produces 200-400 char Chinese summaries;
  align prompt + acceptance to Paper Review P2.
- `apps/admin-console/backend/api/domains.py:753` — fix admin API
  `summary_text` aliasing (covered by separate change
  `paper-summary-text-contract-fix` per Paper Review §6 #5).

### Migration / rollback

- No new schema (V022 already added professor_seed; this change is
  contract-only, no Postgres migration). The existing paper /
  paper_full_text / professor_paper_link / patent /
  professor_patent_link tables already cover the writes.
- Rollback = revert deprecation comment on `pipeline.py`; restore
  `hybrid.py` discovery paths. No data needs migrating.

## Out of scope

- **`prof-summary-fields`** (separate change #2): the educator-side
  `professor.paper_summary` / `professor.patent_summary` aggregation
  fields. This change covers per-paper `summary_zh`, not the
  per-professor aggregated summary.
- **`prof-double-milvus-collection`** (separate change #3): splitting
  Milvus into identity + research collections. This change writes
  paper / patent data via existing single-collection paths.
- **`paper-summary-text-contract-fix`** (separate change #5): the
  1-line admin API fix (`domains.py:753`). Decoupled from this
  pipeline change; safe to ship in parallel.
- **`paper-prd-source-list-rewrite`** (separate change #4): PRD §5.2 /
  §九 / §4.2 doc edits. Documents the same architecture this change
  implements, but separate from code path.
- **`paper-msd-phase-b-status-acknowledge`** (separate change #6):
  MSD §6.1 doc edit. Separate.
- **chat path realtime fallback** (Paper Review P1 §3.2): handled in
  `apps/admin-console/backend/api/chat.py`, not in paper_collector.
  Separate small change; this spec only carries the constraint that
  chat fallback **does not write local paper table** (P13).
- **Per-school adapter for Patents HTML parsing**: heuristic-based
  parser is acceptable for MVP since most prof pages don't list
  patents. Per-school adapters can be added incrementally if a school
  uses a non-standard Patents-section layout.
- **Async job scheduling for enrichment**: Phase A enrichment fires
  inline (synchronous within the seed run) is acceptable. Phase B
  may move enrichment to APScheduler / Celery; not in this spec.

## Risk

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Refactoring `hybrid.py` breaks existing callers | medium | medium | Search for all callers of `discover_*` from hybrid; deprecation warning first, removal in follow-up change |
| `homepage_publications.py` heuristics fail on new schools' Publications HTML | medium | low | Extraction-failure → write `pipeline_issue` row with `kind='paper_attribution'` (existing V006 stage); admin reviews |
| Patents heuristic parser produces false positives (e.g. publications mistaken for patents) | medium | low | Conservative heuristics: only match when section header explicitly says 专利 / Patents / Patent Applications; default no-match |
| Identity gate at ≥0.8 rejects legitimate papers due to OpenAlex author-ID quirks | low | medium | Gate has well-tested code (`identity_gate.py`); spec mandates LLM fallback judge for low-confidence cases |
| OpenAlex / Crossref / S2 enrichment latency degrades end-to-end seed-run time | medium | low | Enrichment is async (fire-and-forget into background task); seed `last_run_status` flips success when discovery completes, even before enrichment finishes |
| `summary_zh` generation prompt produces inconsistent quality | medium | medium | Quality gate via boilerplate detection (LLM judge); failures → `quality_status=needs_review` |
| Patent canonical fields from prof page (often only title + maybe grant_date) violate V004 NOT NULL constraints | medium | medium | Spec mandates trust-page semantics + V004 column nullability check during implementation; if NOT NULL conflicts, file pipeline_issue and skip insert |

## Weight rationale

**Standard** (CLAUDE.md §8). Reasoning:

- Behavior-affecting (deprecates old discovery path; mandates new
  enrichment role; introduces new patent-from-prof-page sub-flow)
- Touches 4 modules (paper / patent / professor / admin pipeline glue)
- Estimated 4-6 person-days for implementation (per Paper Review §6)

Weight is **not Epic** because:

- Most paper-side logic already exists (homepage_ingest.py, identity_gate,
  enrichment helpers); this change codifies + refactors rather than
  greenfields
- No schema migration; no Pydantic contract changes (V019 already
  added quality_status)
- Behavior is well-bounded by Paper Review 16 locked decisions

## Source-of-truth alignment

- Paper Review §3.1 P4 (preprint min fields) / P9 (trust pages) / P10
  (enrichment merge priority) / P11 (dedup chain) / P15
  (quality_status 6 enum) / P16 (freshness signal)
- Professor Review Theme 7.1 (discovery scope) / Theme 7.2 (signal
  selection) / Theme 7.3 (3-7 directions output)
- Paper PRD §3.1 / §4.1 / §4.2 / §5.1-5.6 / §6 / §7 / §8.1 / §11
  (some of these are decision-locked but not yet rewritten in PRD body —
  this spec is the operational source until the PRD-rewrite changes
  ship)
- MSD §2 (enrichment field priority) / §6 (contract status; per Paper
  Review P6 already accepted as Phase B form)
- Audit `docs/audits/paper-requirement-code-reconciliation-2026-05-10.md`
  §5.6 for documented drift items
- Shared-Spec §4.2.1 (`summary_text` semantics) / §5.3 (multi-source
  ordering) / §4.5 (`evidence` shape)
- Existing code: `paper/homepage_ingest.py`, `paper/hybrid.py`,
  `paper/pipeline.py`, `paper/identity_gate.py`,
  `paper/abstract_translator.py`, `paper/release.py`,
  `paper/canonical_writer.py`, `paper/openalex.py`,
  `paper/crossref.py`, `paper/semantic_scholar.py`,
  `professor/homepage_publications.py`, `patent/canonical_writer.py`,
  `patent/release.py`, `patent/import_xlsx.py`
