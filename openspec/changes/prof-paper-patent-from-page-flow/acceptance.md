# Acceptance: prof-paper-patent-from-page-flow

## 1. Spec validation

- [ ] `openspec validate prof-paper-patent-from-page-flow` exits 0
- [ ] proposal.md has `## Why` and `## What Changes` headers (CLI
  warning would otherwise complain)
- [ ] `specs/paper-patent-from-prof-page/spec.md` uses `## ADDED
  Requirements` delta header (this is a new capability)
- [ ] Each Requirement has at least one `#### Scenario:` block

## 2. hybrid.py refactor (after T1)

- [ ] `grep "discover_paper_candidates_from_openalex" apps/miroflow-agent/src/`
  returns no results (renamed to enrich_paper_with_openalex)
- [ ] `grep "discover_professor_paper_candidates_from_hybrid_sources"
  apps/miroflow-agent/src/` returns no results (replaced by
  enrich_paper_with_hybrid_sources)
- [ ] All paper-domain tests pass after refactor
- [ ] No caller of `paper.hybrid.discover_*` exists outside of tests
  (which themselves should be migrated or removed)

## 3. S2-discovery deprecation (after T2)

- [ ] `apps/miroflow-agent/src/data_agents/paper/pipeline.py:run_paper_pipeline`
  emits `DeprecationWarning` on first call per process
- [ ] Warning text references this change ID + migration target
- [ ] Existing scripts (`scripts/run_paper_release_e2e.py`) still work
  but emit the warning during their startup

## 4. Publications extraction (after T3)

- [ ] `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
  records `evidence.source_type` ∈
  `{"prof_homepage_tier2", "prof_homepage_tier3"}`
- [ ] Preprint case (title + year only): paper canonical row inserted
  with `quality_status="needs_enrichment"`, no failure raised
- [ ] HTML parse failure: `pipeline_issue` row created with
  `stage="paper_attribution"`
- [ ] Unit tests in `apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest_*.py`
  cover the preprint scenario

## 5. Patents extraction (after T4)

- [ ] `apps/miroflow-agent/src/data_agents/professor/homepage_patents.py`
  exists
- [ ] `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
  exists
- [ ] Conservative section-header match: only sections whose heading
  contains `专利 / Patents / Patent Applications / 发明专利 /
  实用新型 / 外观` are processed
- [ ] Page with no patents section: zero candidates produced, no
  pipeline_issue
- [ ] Page with title-only patents: candidates produced with
  `patent_id=None`, `quality_status=needs_enrichment`
- [ ] Conflict with existing patent_id: existing row updated, new row
  not duplicated
- [ ] Unit tests cover all three scenarios

## 6. Identity gate (after T5)

- [ ] `apps/miroflow-agent/src/data_agents/paper/identity_gate.py`
  page-only short-circuit returns confidence 1.0
- [ ] LLM-judge fallback triggered for confidence ∈ [0.5, 0.8)
- [ ] `apps/miroflow-agent/src/data_agents/patent/identity_gate.py`
  exists and mirrors paper-side semantics
- [ ] Unit tests cover: page-only attribution, OpenAlex same-name
  conflict, low-confidence reject

## 7. summary_zh generation (after T6)

- [ ] `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py`
  output is Chinese paragraph 200-400 characters (sample 50 papers,
  measure char count distribution)
- [ ] Boilerplate-detection LLM judge step is wired
- [ ] Boilerplate-rejected summary: `summary_zh=NULL`,
  `quality_status=rejected`
- [ ] Unit tests cover passing + rejected paths

## 8. Quality status promotion (after T7)

- [ ] State machine implemented per spec table
- [ ] `needs_enrichment` → `ready` happens when all Required fields
  present + summary_zh passes boilerplate
- [ ] `ready` is forward-monotonic (no auto-degrade)
- [ ] Patent quality promotion via xlsx-merge or admin manual upgrade

## 9. Cross-domain link writers

- [ ] `professor_paper_link` upsert is idempotent (composite key
  `(paper_id, professor_id)`)
- [ ] `professor_patent_link` upsert is idempotent (composite key
  `(patent_id, professor_id)`)
- [ ] `match_reason` ∈
  `{"prof_page_declaration", "openalex_author_match", "manual_override"}`

## 10. End-to-end (T8.3)

- [ ] Real seed (e.g. SUSTech faculty page) → papers extracted
- [ ] Patents extracted (or zero, if no patents section)
- [ ] Cross-domain links written
- [ ] Enrichment fires asynchronously
- [ ] At least one paper promotes from `needs_enrichment` to `ready`
- [ ] No regression in `apps/miroflow-agent/tests/` or
  `apps/admin-console/tests/`

## 11. Non-goals not violated

- [ ] No code change in `apps/miroflow-agent/src/data_agents/paper/hybrid.py`
  that re-introduces discovery semantics for OpenAlex / Crossref / S2
- [ ] No call from `homepage_ingest.py` or `patent/homepage_ingest.py`
  to OpenAlex / Crossref / S2 / arXiv / DBLP / Web Search **for the
  purpose of returning a paper list keyed by author name**
- [ ] No new column added to `paper` Postgres table (V019 already
  added quality_status; no migration in this change)
- [ ] No change to `professor.paper_summary` or
  `professor.patent_summary` (those are `prof-summary-fields`)
- [ ] No change to admin API `domains.py:753` (that is
  `paper-summary-text-contract-fix`)
- [ ] No Milvus collection change (that is
  `prof-double-milvus-collection`)

## Evidence

> Filled during implementation by the executing agent.

### T1 — hybrid.py refactor
- Caller survey output:
- Refactor commit ref:
- Test pass count:

### T2 — S2-discovery deprecation
- Deprecation warning commit ref:

### T3 — Publications extraction
- Verification result for `homepage_ingest.py` gap analysis:
- Commit ref (if changes needed):

### T4 — Patents extraction (greenfield)
- New module commit ref:
- Unit test pass count:

### T5 — Identity gate
- Paper gate verification:
- Patent gate creation commit ref:

### T6 — summary_zh
- Sample char count distribution (50 papers):
- Boilerplate judge commit ref:

### T7 — Quality status promotion
- State machine commit ref:

### T8 — End-to-end smoke
- Real seed used:
- Papers / patents discovered (counts):
- Promotion observed: yes/no
- Pytest summary:

## Failure modes that block archive

- T1 leaves `discover_*` calls active anywhere in src/ — refactor
  incomplete; do not archive
- T4 patent extraction unconditionally fires for all sections (false
  positives) — heuristic too loose; tighten before archive
- T7 forward-monotonic invariant violated (a `ready` paper auto-
  degrades after enrichment failure) — bug; fix before archive
- T8 smoke test produces zero papers from a real seed that obviously
  has many — extraction broken; investigate before archive
