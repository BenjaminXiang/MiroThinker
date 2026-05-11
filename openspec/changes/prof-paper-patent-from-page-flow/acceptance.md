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
- New modules:
  - `apps/miroflow-agent/src/data_agents/professor/homepage_patents.py`
    (T4.1 / T4.2 — `PatentEntry` + `extract_patents_from_html`)
  - `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
    (T4.3 — `run_homepage_patent_ingest` +
    `_ingest_patents_for_professor` + `_build_patent_row` +
    SQL upserts for `patent` and `professor_patent_link`)
- Unit tests added (T4.4): 21 tests total — 11 in
  `tests/data_agents/professor/test_homepage_patents.py`
  (extractor) + 10 in
  `tests/data_agents/patent/test_homepage_ingest.py`
  (ingest helpers). Scenarios covered: zero-patents section, page
  with title-only patents (→ `data_quality_flag` pipeline_issue,
  no canonical insert), page with full patent_id (→ canonical
  upsert + link), conflict with existing canonical patent_id (→
  `ON CONFLICT (patent_number) DO UPDATE` without auto-degrading
  `quality_status`).
- Caveat surfaced to spec: V004 makes `patent.patent_number` NOT
  NULL UNIQUE; spec scenario "prof-page patent without patent_id"
  cannot be satisfied as written in V004. T4.3 routes such
  candidates to a `data_quality_flag` pipeline_issue. A future
  change must relax V004 (or add a placeholder column) to satisfy
  the spec scenario literally.
- Pre-existing test failure outside this slice:
  `tests/data_agents/patent/test_release.py::test_build_patent_release_generates_summary_and_company_links`
  fails on `main` already (company_ids linkage); not introduced
  by T4.
- Commit ref: filled at commit time.

### T5 — Identity gate
- Paper gate verification (T5.1):
  Audited `professor/paper_identity_gate.py` (current location; spec
  referenced `paper/identity_gate.py` but the gate has always lived
  under `professor/` and is consumed by `professor.paper_collector`).
  - ≥ 0.8 → auto-accept: ✅ (`CONFIDENCE_THRESHOLD = 0.8` in
    `_verify_single_batch`).
  - [0.5, 0.8) → LLM judge fallback: ✅ implicit (LLM is the only
    judge; design.md §4 accepts single-tier as equivalent).
  - < 0.5 → reject + pipeline_issue: ⚠️ rejects via
    `accepted=False`; pipeline_issue write is caller responsibility
    (gate stays pure / DB-less). Documented in `PaperIdentityDecision`
    docstring.
  - Page-only attribution → 1.0: ❌ pre-T5; fixed in T5.2.
- Paper gate short-circuit (T5.2): added
  `accept_page_only_attribution(candidate)` in
  `professor/paper_identity_gate.py`. Pure function, no LLM call,
  returns `PaperIdentityDecision(accepted=True, confidence=1.0,
  reasoning="prof_page_declaration")`. New constant
  `PAGE_ONLY_REASONING` exported for caller use.
- Patent gate creation (T5.3): new module
  `professor/patent_identity_gate.py` with:
  - `PatentIdentityCandidate` (index, title, patent_id, inventors)
  - `PatentIdentityDecision` (index, accepted, confidence, reasoning)
  - `accept_page_only_attribution(candidate)` — page-only short-circuit
    parallel to paper side
  - `verify_xlsx_attribution(candidate, *, professor_canonical_name,
    name_variants=None)` — deterministic name-intersection scoring
    for the future xlsx-merge path. No LLM step (design.md §8 forbids
    external patent enrichment).
- Unit tests added (T5.4): 15 tests total — 3 in
  `tests/data_agents/professor/test_paper_identity_gate_page_only.py`
  (paper-side page-only short-circuit) + 12 in
  `tests/data_agents/professor/test_patent_identity_gate.py`
  (patent-side page-only, xlsx exact match, name-variant matching
  across scripts, same-name collision uncertain-reject, no-inventors
  reject, no-name-match reject, substring-collision protection,
  blank-canonical-name reject, decision-contract assertion for
  pipeline_issue handoff).
- Caveat surfaced: spec asked for files at `paper/identity_gate.py`
  and `patent/identity_gate.py`; both gates actually live at
  `professor/*_identity_gate.py` to stay aligned with the existing
  callers (`paper_collector`, future `patent.exact_backfill`). No
  rename done — moving the paper gate would force import surgery in
  3+ files for no functional benefit. design.md §4 implies the
  current location is acceptable.
- Pre-existing failure outside slice:
  `tests/data_agents/patent/test_release.py::test_build_patent_release_generates_summary_and_company_links`
  continues to fail on `main`; not introduced by T5.
- Commit ref: filled at commit time.

### T6 — summary_zh
- Audit (T6.1): current
  `paper/abstract_translator.py` prompt explicitly targets `200-400 字
  中文 paraphrase`. Validation band 150-500 (lenient tolerance).
  Outputs outside the band are rejected via `_validate_summary_zh`.
  Existing 17-entry regex catalog `BOILERPLATE_KEYWORDS` continues to
  catch known failure modes cheaply. No prompt drift detected; no
  changes needed at this layer.
- Boilerplate judge (T6.2): new
  `judge_summary_boilerplate(summary, *, llm_client, llm_model,
  extra_body=None) -> bool`. Separate LLM call with a binary
  classifier prompt (`_JUDGE_SYSTEM_PROMPT`). Returns True only when
  the LLM emits the `BOILERPLATE` token. Fail-open on
  transport / parse errors (returns False). Blank inputs skip the LLM
  call. Caller contract documented: callers MUST set
  `summary_zh=NULL` and `quality_status="rejected"` on True
  (T7 wires this).
- Sample char-count distribution (50 papers): not yet measured — that
  is an E2E task (T8.3) that requires running the pipeline against
  a real seed. The prompt + validation band targets 200-400 by
  construction; distribution verification will be filled at T8.
- Unit tests added (T6.3): 13 new tests in
  `tests/data_agents/paper/test_abstract_translator_boilerplate_judge.py`.
  Scenarios: parse_judge_verdict (exact / case / verbose /
  co-occurrence prefer BOILERPLATE / unknown-defaults-to-INFORMATIVE),
  judge end-to-end (boilerplate-true, substantive-false, fail-open
  on LLM error, blank-input short-circuit without LLM call,
  markdown-fenced reply, temperature=0 invariant, extra_body
  plumbing). 5 pre-existing translator tests still pass.
- Commit ref: filled at commit time.

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
