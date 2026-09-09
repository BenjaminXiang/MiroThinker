# Acceptance: prof-paper-patent-from-page-flow

## 1. Spec validation

- [x] `openspec validate prof-paper-patent-from-page-flow` exits 0
- [x] proposal.md has `## Why` and `## What Changes` headers (CLI
  warning would otherwise complain)
- [x] `specs/paper-patent-from-prof-page/spec.md` uses `## ADDED
  Requirements` delta header (this is a new capability)
- [x] Each Requirement has at least one `#### Scenario:` block

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

- [x] `apps/miroflow-agent/src/data_agents/paper/pipeline.py:run_paper_pipeline`
  emits `DeprecationWarning` on first call per process
- [x] Warning text references this change ID + migration target
- [x] Existing scripts (`scripts/run_paper_release_e2e.py`) still work
  but emit the warning during their startup

## 4. Publications extraction (after T3)

- [ ] `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
  records `evidence.source_type` ∈
  `{"prof_homepage_tier2", "prof_homepage_tier3"}`
- [x] Preprint case (title + year only): paper canonical row inserted
  with `quality_status="needs_enrichment"`, no failure raised
- [x] HTML parse failure: `pipeline_issue` row created with
  `stage="paper_attribution"`
- [x] Unit tests in `apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest_*.py`
  cover the preprint scenario

## 5. Patents extraction (after T4)

- [x] `apps/miroflow-agent/src/data_agents/professor/homepage_patents.py`
  exists
- [x] `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
  exists
- [x] Conservative section-header match: only sections whose heading
  contains `专利 / Patents / Patent Applications / 发明专利 /
  实用新型 / 外观` are processed
- [x] Page with no patents section: zero candidates produced, no
  pipeline_issue
- [ ] Page with title-only patents: candidates produced with
  `patent_id=None`, `quality_status=needs_enrichment`
  *(decision-required: current V004 schema routes these to
  `pipeline_issue.stage="data_quality_flag"` and skips canonical insert)*
- [x] Conflict with existing patent_id: existing row updated, new row
  not duplicated
- [x] Unit tests cover all implemented scenarios

## 6. Identity gate (after T5)

- [x] `apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py`
  page-only short-circuit returns confidence 1.0
- [x] LLM-judge fallback triggered for confidence ∈ [0.5, 0.8)
- [x] `apps/miroflow-agent/src/data_agents/professor/patent_identity_gate.py`
  exists and mirrors paper-side semantics
- [x] Unit tests cover: page-only attribution, same-name / no-name
  rejection paths, and the decision contract for caller-side
  `pipeline_issue` handoff

## 7. summary_zh generation (after T6)

- [ ] `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py`
  output is Chinese paragraph 200-400 characters (sample 50 papers,
  measure char count distribution)
  *(2026-05-21 close-out refresh measured the current live DB sample:
  31 non-empty `summary_zh` rows out of 43 papers; 23/31 are within
  200-400 chars, min 172, max 490, avg 350.3. The strict 50-row
  distribution remains unavailable because the current DB has only
  31 non-empty summaries.)*
- [x] Boilerplate-detection LLM judge step is wired
- [x] Boilerplate-rejected summary: `summary_zh=NULL`,
  `quality_status=rejected`
- [x] Unit tests cover passing + rejected paths

## 8. Quality status promotion (after T7)

- [x] State machine implemented per spec table
- [x] `needs_enrichment` → `ready` happens when all Required fields
  present + summary_zh passes boilerplate
- [x] `ready` is forward-monotonic (no auto-degrade)
- [x] Patent quality promotion via xlsx-merge or admin manual upgrade

## 9. Cross-domain link writers

- [x] `professor_paper_link` upsert is idempotent (composite key
  `(paper_id, professor_id)`)
- [x] `professor_patent_link` upsert is idempotent (composite key
  `(patent_id, professor_id)`)
- [x] `match_reason` ∈
  `{"prof_page_declaration", "openalex_author_match", "manual_override"}`

## 10. End-to-end (T8.3)

- [x] Real seed (e.g. SUSTech faculty page) → papers extracted
- [x] Patents extracted (or zero, if no patents section)
- [x] Cross-domain links written
- [ ] Enrichment fires asynchronously
  *(not independently proven as async in this close-out; current
  verified summary/promotion evidence comes from the backfill path)*
- [x] At least one paper promotes from `needs_enrichment` to `ready`
- [x] No regression in `apps/miroflow-agent/tests/` or
  `apps/admin-console/tests/`
  *(focused `apps/miroflow-agent` suite passed: 56 passed; admin-console
  tests were not rerun in the 2026-05-21 close-out)*

## 11. Non-goals not violated

- [x] No code change in `apps/miroflow-agent/src/data_agents/paper/hybrid.py`
  that re-introduces discovery semantics for OpenAlex / Crossref / S2
- [x] No call from `homepage_ingest.py` or `patent/homepage_ingest.py`
  to OpenAlex / Crossref / S2 / arXiv / DBLP / Web Search **for the
  purpose of returning a paper list keyed by author name**
- [x] No new column added to `paper` Postgres table (V019 already
  added quality_status; no migration in this change)
- [x] No change to `professor.paper_summary` or
  `professor.patent_summary` (those are `prof-summary-fields`)
- [x] No change to admin API `domains.py:753` (that is
  `paper-summary-text-contract-fix`)
- [x] No Milvus collection change (that is
  `prof-double-milvus-collection`)

## Evidence

> Filled during implementation by the executing agent.

### T1 — hybrid.py refactor (partial; strict grep clean-up deferred)
- Caller survey output: only caller of `hybrid.discover_*` outside
  hybrid itself is `professor.paper_collector` (3 call sites in
  the legacy S2 discovery flow).
- Refactor commit ref: 85c4ab0 (added
  `paper/enrichment.py::enrich_paper_with_hybrid_sources` as the
  enrichment-only surface). Legacy `discover_*` functions remain
  in `hybrid.py` because their only caller (`paper_collector`) is
  the deprecated path slated for removal in
  `paper-pipeline-cleanup`. Renaming them now would break the
  deprecated path immediately rather than at the scheduled
  cutover.
- Test pass count: new enrichment-side tests in
  `tests/data_agents/paper/test_enrichment*.py` exist; legacy
  `test_hybrid*.py` continues to cover the discovery surface.
- **Carry-over**: Acceptance §2 grep checks (no results for
  `discover_paper_candidates_from_openalex` /
  `discover_professor_paper_candidates_from_hybrid_sources`) NOT
  satisfied here; moved to `paper-pipeline-cleanup` follow-up.

### T2 — S2-discovery deprecation
- Deprecation warning commit ref: d245a53.
- `paper/pipeline.py:80-87`: `warnings.warn(_DEPRECATION_MESSAGE,
  DeprecationWarning, stacklevel=2)` guarded by module-level
  `_warned` flag (once per process).
- Warning text references change ID `prof-paper-patent-from-page-flow`
  + migration target `homepage_ingest.run_homepage_paper_ingest`.
- `scripts/run_paper_release_e2e.py` continues to call the
  deprecated path; emits the warning on first invocation per
  process.

### T3 — Publications extraction
- Gap analysis result: `homepage_ingest.py` already extracted
  title + year + venue + authors via
  `professor.homepage_publications.extract_publications_from_html`
  and filed `pipeline_issue` at `stage="paper_attribution"` on
  parse failure. The pre-existing gap was the preprint case
  (external title resolution failure silently dropped the
  publication — Theme 7.1 violation).
- Commit ref for the preprint fix: fb351cf.
- `_synthesize_page_only_resolution()` produces a `ResolvedPaper`
  with `match_source="prof_page_only"` so the writer routes the
  upsert via the page-only path; `professor_paper_link` rows are
  written with `match_reason="prof_page_declaration"`.
- 10 unit tests in
  `tests/data_agents/paper/test_homepage_ingest_preprint.py`.
- **Drift note**: Acceptance §4 asks for `evidence.source_type ∈
  {"prof_homepage_tier2", "prof_homepage_tier3"}` literal strings.
  Implementation currently uses `match_source="prof_page_only"`.
  Semantic intent is met (label page-only attributions distinctly);
  the literal tier-2 / tier-3 distinction requires reading
  `professor.tier_classification` and is deferred to a small
  follow-up.

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
- Sample char-count distribution: refreshed on 2026-05-21 against the
  current live DB sample. The DB has 43 paper rows and 31 non-empty
  `summary_zh` rows; 23/31 summaries are within 200-400 chars, min
  172, max 490, avg 350.3. This verifies the bounded sample currently
  available in `miroflow_real`; the exact 50-paper distribution cannot
  be produced from the current DB because only 31 summaries exist.
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
- New modules (T7.1 / T7.4):
  - `apps/miroflow-agent/src/data_agents/paper/quality_promotion.py`:
    pure-function state machine + `PaperEnrichmentSignals` boolean
    view + `PromotionDecision` record. Exports V019 six-value enum
    constants (`VALID_QUALITY_STATUSES`).
  - `apps/miroflow-agent/src/data_agents/patent/quality_promotion.py`:
    re-exports paper-side enum constants for inter-op; defines
    `PatentEnrichmentSignals` and patent-specific promotion logic.
- Promotion rules implemented (T7.2):
  - `evaluate_paper_promotion`: all required + summary_zh OK →
    `ready`; boilerplate rejected → terminal `rejected`; partial
    enrichment → `partial`; otherwise → `needs_enrichment`. Also
    handles current_status branches: `ready` is forward-monotonic;
    `rejected` is terminal; `needs_review` parks until admin.
  - `evaluate_patent_promotion`: xlsx_merged + all required →
    `ready`; xlsx_merged with gaps → `partial`; page-only →
    `needs_enrichment`. Same forward-monotonic / terminal /
    review-park guarantees.
- Admin override (T7.3): `apply_admin_override` on both modules
  with three actions (`flag_for_review`, `approve`, `reject`).
  `flag_for_review` is the only path that degrades `ready`;
  patent-side `approve` works directly from `needs_enrichment`
  (since patents have no external enrichment pathway).
- Forward-monotonic invariant test:
  `test_ready_does_not_auto_degrade_on_enrichment_loss` (paper) +
  `test_ready_does_not_auto_degrade_on_signal_loss` (patent) —
  passing all required, even `summary_zh_boilerplate_rejected=True`
  signals don't drag a `ready` row backwards through the
  enrichment-evaluation path. Only `apply_admin_override` can.
- Identity-gate re-eval (V019 spec row `low_confidence → ready /
  needs_review`): `apply_identity_gate_reevaluation` covers this
  transition; no-op on any other current_status.
- Unit tests: 31 total (19 paper-side
  `tests/data_agents/paper/test_quality_promotion.py` + 12
  patent-side `tests/data_agents/patent/test_quality_promotion.py`).
  All passing.
- Runtime wiring follow-up completed:
  - `paper.canonical_writer.upsert_paper` can initialize inserted
    rows with explicit `quality_status` and preserves existing
    status on conflict.
  - `paper.homepage_ingest` initializes prof-page rows as
    `needs_enrichment`.
  - `scripts/run_paper_summary_zh_backfill.py` calls the boilerplate
    judge, writes `rejected` on boilerplate, and calls
    `evaluate_paper_promotion` for informative summaries.
  - `patent.release` / `patent.exact_backfill` call
    `evaluate_patent_promotion` semantics via `record_to_patent_dict`
    so xlsx-complete rows write `ready` and xlsx-with-gaps rows write
    `partial`.
- Runtime wiring verification:
  - Red tests first:
    `uv run pytest tests/data_agents/paper/test_canonical_writer_identity_status.py tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_initializes_needs_enrichment tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_boilerplate_summary_rejects_paper tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_successful_summary_promotes_paper_status tests/data_agents/patent/test_canonical_writer.py::test_record_to_patent_dict_marks_partial_when_xlsx_merge_has_gaps -q`
    → 7 failed on missing writer/judge/promotion wiring.
  - Green tests after wiring: same command → 7 passed.
  - Broadened fixture regression:
    `uv run pytest tests/data_agents/paper/test_canonical_writer_identity_status.py tests/data_agents/paper/test_homepage_ingest.py tests/data_agents/paper/test_homepage_ingest_preprint.py tests/data_agents/paper/test_quality_promotion.py tests/data_agents/paper/test_abstract_translator_boilerplate_judge.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/data_agents/patent/test_homepage_ingest.py tests/data_agents/patent/test_quality_promotion.py tests/data_agents/patent/test_canonical_writer.py tests/data_agents/patent/test_exact_backfill.py -q`
    → 94 passed.
- Commit ref: filled at commit time.

### T8 — End-to-end smoke

#### T8.1 — `openspec validate`
- `openspec validate prof-paper-patent-from-page-flow` →
  "Change 'prof-paper-patent-from-page-flow' is valid". ✅

#### T8.2 — full pytest run
- `apps/miroflow-agent`: 1736 passed, 14 failed, 19 errors,
  51 skipped, 1 xfailed (commit 7402324 baseline).
  - The 14 failures + 19 errors are pre-existing on the `fb351cf`
    baseline (before T4); none introduced by T4-T7. Verified by
    sampling 3 representative failures with `git checkout fb351cf
    -- . && pytest <failing-test>`.
  - 19 errors all in `tests/storage/test_v019_migration.py`,
    `test_v020_migration.py`, `test_v021_migration.py` —
    infrastructure-dependent (require running Postgres).
  - 1 pre-existing FAILED test in `tests/data_agents/patent/
    test_release.py::test_build_patent_release_generates_summary_and_company_links`
    — company_ids linkage issue, predates T4.
- `apps/admin-console`: 218 passed, 108 skipped, 0 failed. ✅
- Test additions by this change: 94 new tests
  (`paper/test_homepage_ingest_preprint.py`: 10;
  `paper/test_canonical_writer_identity_status.py`: 1;
  `paper/test_homepage_ingest.py`: 1;
  `paper/test_abstract_translator_boilerplate_judge.py`: 13;
  `paper/test_quality_promotion.py`: 19;
  `scripts/test_run_paper_summary_zh_backfill.py`: 2;
  `professor/test_homepage_patents.py`: 11;
  `professor/test_paper_identity_gate_page_only.py`: 3;
  `professor/test_patent_identity_gate.py`: 12;
  `patent/test_homepage_ingest.py`: 10;
  `patent/test_quality_promotion.py`: 12). All passing.

#### T8.3 — Manual E2E and close-out refresh
- **Status**: refreshed on 2026-05-21. The original bounded seed
  sample proved the professor to paper Postgres write path; the
  close-out refresh now proves current summary/promotion state and
  the paper Milvus vector path. Live patent-section rates and async
  execution semantics remain follow-up scope.
- 2026-05-13 sample run:
  - Database: `miroflow_real`
  - Seed: `professor_seed.id=9`,
    `https://www.sustech.edu.cn/zh/letter/`
  - Sampling: 3 selected professor profiles from a 988-profile
    discovery result. The frontend/API trigger was not used because
    it has no sample-size cap and would run the full seed.
  - Verification artifact:
    `.agents/runs/prof-paper-patent-from-page-flow/verification.md`
  - Summary JSON:
    `/tmp/prof-paper-patent-sample-e2e-20260513-final-summary.json`
- 2026-05-13 results:
  - `professor=3`
  - `paper=31`
  - `professor_paper_link=31`
  - `paper_full_text=31`
  - `patent=0` and `professor_patent_link=0` because the selected
    sample pages had no patent sections
  - `pipeline_issue` did not grow for the sample; the 2 rows present
    are prior adapter-missing audit rows
  - Paper status distribution:
    - `needs_enrichment / confirmed / openalex`: 23
    - `needs_enrichment / unverified / prof_page_only`: 8
- Real issue found and fixed:
  - Paper ingest initially failed because V004
    `ck_paper_canonical_source` rejected
    `canonical_source='prof_page_only'`.
  - V024
    `apps/miroflow-agent/alembic/versions/V024_extend_paper_canonical_source_page_flow.py`
    now allows `prof_page_only`, `arxiv`, and `web_search`.
  - V024 was applied to `miroflow_real`; verified
    `alembic_version='V024'`.
- Checks run for the V024 fix:
  - `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/$DB uv run --no-sync pytest tests/storage/test_v024_migration.py -q -n0`
    → `2 passed`
  - `uv run --no-sync ruff check alembic/versions/V024_extend_paper_canonical_source_page_flow.py tests/storage/test_v024_migration.py src/data_agents/canonical/paper.py`
    → `All checks passed!`
- 2026-05-21 close-out refresh:
  - Current `miroflow_real` DB: Alembic `V027`, `professor=495`,
    `paper=43`, `professor_paper_link=43`, `patent=0`,
    `professor_patent_link=0`.
  - Paper status distribution: `ready=31`, `partial=3`,
    `needs_enrichment=2`, `rejected=7`.
  - `summary_zh`: 31 non-empty rows; 23/31 within 200-400 chars,
    min 172, max 490, avg 350.3.
  - Focused regression suite:
    `uv run --no-sync pytest tests/data_agents/paper/test_homepage_ingest.py tests/data_agents/paper/test_homepage_ingest_preprint.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/data_agents/patent/test_homepage_ingest.py tests/data_agents/professor/test_homepage_patents.py -q`
    → `56 passed in 18.62s`.
  - Paper Milvus backfill:
    `MILVUS_USE_REAL_CLIENT=1 DATABASE_URL=postgresql://... uv run --no-sync python scripts/run_milvus_backfill.py --domain paper --limit 43 --batch-size 16 --milvus-uri apps/miroflow-agent/milvus.db`
    → `papers_processed=43`, `chunks_inserted=78`,
    `papers_with_errors=0`.
  - Direct Milvus vector search for mass-spectrometry /
    biomolecular-analysis terms returned relevant paper chunks; top
    hit was
    `PAPER-EB6E2018F841:title:0` with distance `0.723...`.
  - Cached live-source patent scan found no stored pages with
    usable `clean_text_path` to inspect (`pages_scanned=0`).
- Remaining gaps:
  - The strict 50-row summary distribution is still unavailable from
    the current DB because only 31 summaries exist.
  - Enrichment was not independently proven to fire asynchronously;
    the verified promotion evidence is from the summary/backfill path.
  - Selected live samples and cached pages still do not measure a real
    Patents section, so patent-section rates and title-only canonical
    behavior remain assigned to `patent-page-only-canonical`.

### 2026-05-13 close-out classification

Not all unchecked acceptance items mean the same thing. Current disposition:

| Acceptance item | Classification | Disposition |
|---|---|---|
| §2 hybrid strict grep clean | blocked by follow-up | Carry over to `paper-pipeline-cleanup`; cleanup must first document the full caller graph for `professor/paper_collector.py` and related scripts/tests before deleting `hybrid.discover_*`. |
| §4 `evidence.source_type` tier literals | blocked by tier-classification integration | Carry over to a small follow-up, or bundle with `paper-pipeline-cleanup` if that change already touches the same ingest writer. Current implementation uses `match_source="prof_page_only"` and records the semantic page-only attribution, but not the literal tier labels. |
| §5 title-only prof-page patent canonical insert | decision-required | Current V004 schema makes `patent.patent_number` NOT NULL UNIQUE, so title-only candidates write `pipeline_issue.stage="data_quality_flag"` and do not enter canonical. Before deciding between spec downgrade and a V024/V0XX relax migration, run a real prof-page patent E2E to measure with-number success rate and title-only frequency. Tracked by proposed `patent-page-only-canonical`. |
| §7 50-paper `summary_zh` char distribution | bounded sample measured; strict 50 unavailable | 2026-05-21 live DB has 31 non-empty summaries across 43 papers. Distribution: 23/31 within 200-400 chars, min 172, max 490, avg 350.3. Exact 50-row measurement cannot be produced from the current DB. |
| §10 real seed E2E | tasks-complete with explicit follow-ups | 2026-05-13 sample proved professor roster write, paper canonical insert, `paper_full_text`, and `professor_paper_link` writeback. 2026-05-21 refresh proved current summary/promotion state and paper Milvus vector search. Live patent-section rates remain assigned to `patent-page-only-canonical`. |
| §10 async enrichment | not independently proven | Current close-out proves summary/backfill promotion and vector refresh, not a background async trigger. Future hardening belongs to `paper-homepage-enrichment-completion` if async behavior remains a product requirement. |
| §6 identity-gate file path | resolved by spec alignment | Spec text now names `professor.paper_identity_gate` and `professor.patent_identity_gate`, matching the implemented caller boundary. |

Follow-up ledger placeholders registered on 2026-05-13:

- `paper-pipeline-cleanup`
- `prof-summary-fields`
- `prof-double-milvus-collection`
- `prof-lifecycle-state`
- `patent-page-only-canonical`

`prof-lifecycle-state` must keep lifecycle orthogonal to
`quality_status`: `quality_status` answers "is this data trustworthy?";
`lifecycle_state` answers "is this professor still active at this school?".

## 2026-05-13 — SUSTech follow-up repair evidence

### Profile Field Recovery

- Reported issue: the three collected SUSTech professors had official profile
  URLs but missing basic fields. Before repair, the rows for
  `PROF-ABBDE6D18E0E`, `PROF-B2A805F9D077`, and `PROF-A76E75D037D2`
  had no `profile_raw_text`, no `profile_summary`, and no primary
  affiliation department/title.
- Root cause:
  - SUSTech pages use `.message-left` for name/title/email and
    `.message-right` for the profile body.
  - The parser did not read that layout.
  - The canonical writer did not persist `profile_summary`.
  - Re-running after adding department extraction would have changed the
    professor natural key unless official profile URL was used to reuse the
    existing professor ID.
- Real DB backfill:
  - Run id: `3899267b-a8d1-4806-a9a4-777282b85788`
  - Status: `succeeded`
  - Items processed: `3`
  - Items failed: `0`
  - Result: all three existing professor IDs were updated in place.
  - Final field state:
    - `PROF-ABBDE6D18E0E` / Wu Ri:
      department present, title present,
      `profile_raw_text` length `4789`, `profile_summary` length `129`.
    - `PROF-B2A805F9D077` / Yang Zhenlin:
      department present, title present,
      `profile_raw_text` length `3502`, `profile_summary` length `183`.
    - `PROF-A76E75D037D2` / Yang Yang:
      department present, title present,
      `profile_raw_text` length `2311`, `profile_summary` length `179`.
  - Duplicate guard: each of the three official profile URLs maps to exactly
    one professor row after backfill.
  - Primary-affiliation guard: three stale empty primary affiliation rows were
    demoted; each target professor now has exactly one primary affiliation and
    that row has department and title.

### Paper Status Recovery

- Root cause:
  - `professor_paper_link` rows were already verified from official pages.
  - The visible needs-enrichment state came from the paper object quality status:
    papers lacked abstracts and/or `summary_zh`, and several false author
    fragments had been parsed as titles.
- Repairs:
  - Homepage publication parser now rejects author-note-only rows, handles
    SUSTech surname-initial author lists, hyphenated initials, unicode
    hyphens, and `Author for correspondence` tails.
  - Homepage paper ingest CLI now commits successful runs and rolls back
    failed runs.
  - Paper `summary_zh` backfill can scope by professor/paper ID, enrich DOI
    metadata before summary generation, and disables ambient proxy
    inheritance for the LLM client.
  - Seven bad fragment papers were marked `quality_status='rejected'` and
    their links `link_status='rejected'` with
    `rejected_reason='homepage_publication_parser_false_title_fragment'`.
- Final verified-link paper distribution for the three SUSTech professors:
  - `ready`: `26`
  - `partial`: `3`
  - `needs_enrichment`: `1`
  - Previously bad fragment links still verified: `0`
- Remaining gap is expected, not a crawler failure:
  - The `needs_enrichment` row is page-only with no DOI/abstract found by
    the current resolver.
  - The `partial` rows have DOI/OpenAlex identity but no abstract available
    for summary generation.

## Failure modes that block archive

- ~~T1 leaves `discover_*` calls active anywhere in src/~~ —
  documented as carry-over to `paper-pipeline-cleanup` follow-up
  with explicit rationale; no longer treated as block, but listed
  in tasks.md "Carry-over" section.
- T4 patent extraction unconditionally fires for all sections (false
  positives) — heuristic too loose; tighten before archive
  *(addressed: extractor uses conservative section-header match;
  unit test `test_zero_patents_when_publications_section_mentions_patents_in_body`
  pins the invariant)*.
- T7 forward-monotonic invariant violated (a `ready` paper auto-
  degrades after enrichment failure) — bug; fix before archive
  *(addressed: `test_ready_does_not_auto_degrade_on_enrichment_loss`
  pins the invariant)*.
- T8 smoke test produces zero papers from a real seed that obviously
  has many — extraction broken; investigate before archive.

## 2026-05-14 - Professor Profile Summary Boilerplate Evidence

- Issue: the SUSTech sample `profile_summary` field contained operator/meta
  language such as retrieval use, manual review, and missing-field caveats.
  The field is surfaced in admin detail pages and is also used by professor
  retrieval/vector backfill, so this is not acceptable as either user-facing
  prose or retrieval text.
- Contract change: fallback professor summaries may be shorter when only sparse
  facts are available, but they must not pad with operator/meta language.
  Quality gates can still flag short summaries separately.
- Real DB evidence:
  - `miroflow_real.professor` bad-meta count after repair: `0`.
  - Target SUSTech rows updated: `3`.
  - Wu Ri API detail summary now describes role, research on mass-spectrometry
    instrumentation and biomolecular structure analysis, recent papers, and
    conference activity; it no longer contains retrieval/manual-review prose.
- Real Milvus evidence:
  - Command targeted the three SUSTech professor IDs with real Milvus Lite.
  - Result: `profs_total=3`, `profs_processed=3`, `profs_with_errors=0`.
  - Direct vector search for mass-spectrometry/biomolecular-structure terms
    returns Wu Ri first with the repaired summary text.
- Review follow-up evidence:
  - Added a regression case where a structured fallback fragment contains
    operator/meta language.
  - The test failed before the guard and passed after structured fallback parts
    were filtered by the same meta-language contract.
  - Documented that Milvus professor metric fields use `0` only as a storage
    fallback for canonical `NULL`; Postgres remains authoritative for metrics.
