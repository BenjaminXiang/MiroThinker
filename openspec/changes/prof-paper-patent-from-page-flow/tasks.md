# Tasks: prof-paper-patent-from-page-flow

This change ships the SPEC. Implementation is sliced into discrete
sub-changes so the keystone change doesn't itself become Epic. Each
sub-task can land independently once this spec is archived; suggested
order is 1 → 2 → 3 → 4 → 5.

## 1. Refactor hybrid.py to enrichment-only

- [ ] T1.1: Survey all callers of `discover_*_from_*` in
  `apps/miroflow-agent/src/data_agents/paper/hybrid.py` and
  `paper/openalex.py` / `paper/crossref.py` /
  `paper/semantic_scholar.py`. Record findings in
  `acceptance.md` Evidence section.
- [ ] T1.2: Rename `discover_paper_candidates_from_openalex` →
  `enrich_paper_with_openalex`. Update signature: input is
  `PaperRecord` (or paper canonical row dict with at least `doi` or
  `title+year`); output is `dict[str, Any]` of enrichment fields.
- [ ] T1.3: Repeat for Crossref / Semantic Scholar / arXiv variants.
- [ ] T1.4: Replace
  `discover_professor_paper_candidates_from_hybrid_sources` with
  `enrich_paper_with_hybrid_sources(paper)`. Implement field-level
  fallback per spec Requirement "Async enrichment workflow".
- [ ] T1.5: Update tests under
  `apps/miroflow-agent/tests/data_agents/paper/test_hybrid*` to use
  the new function names. Adjust fixtures from "fake author" to
  "fake paper canonical row".
- [ ] T1.6: Run full pytest suite under `apps/miroflow-agent/tests/`
  and verify no regressions. Update any callers that still expect
  discovery-mode return shape.

## 2. Mark S2-discovery path deprecated

- [ ] T2.1: Add `DeprecationWarning` emission at top of
  `apps/miroflow-agent/src/data_agents/paper/pipeline.py:run_paper_pipeline`.
  Use the once-only pattern (`warnings.warn(..., stacklevel=2)`)
  guarded by a module-level `_warned` flag.
- [ ] T2.2: Add docstring linking to this change ID + the migration
  target `homepage_ingest.run_homepage_paper_ingest` (or the
  successor entry point introduced by Phase B of
  `prof-seed-admin-console`).
- [ ] T2.3: Verify that `scripts/run_paper_release_e2e.py` and other
  call sites still work but emit the warning. Document migration
  TODOs in those scripts.

## 3. Wire Publications extraction into the canonical seed-run path

- [ ] T3.1: Verify `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
  satisfies the spec Requirement "Publications-section extraction
  from prof Tier 2/3 pages":
  - Extracts `title + year + venue + authors` minimum
  - Records `evidence.source_type = prof_homepage_tier2/tier3`
  - Tolerates missing abstract / DOI / arxiv_id
  - Files `pipeline_issue` on extraction failure with
    `stage="paper_attribution"`
- [ ] T3.2: If gaps exist, add the missing behaviors. Likely small
  additions: `evidence.source_type` enrichment, pipeline_issue
  filing on parse failure.
- [ ] T3.3: Add unit tests covering preprint case (title + year only,
  no DOI / no abstract).

## 4. Implement Patents-section extraction (greenfield)

- [x] T4.1: Create
  `apps/miroflow-agent/src/data_agents/professor/homepage_patents.py`
  parallel to `homepage_publications.py`. Implement
  `extract_patents_from_html(html: str) -> list[PatentEntry]` using
  conservative section-header matching (`专利 / Patents / Patent
  Applications / 发明专利 / 实用新型 / 外观`).
- [x] T4.2: Define `PatentEntry` dataclass (or reuse existing patent
  models): `title` (required), `patent_id` (optional),
  `application_date` / `grant_date` (optional), `inventors`
  (optional, list of strings).
- [x] T4.3: Create
  `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
  parallel to `paper/homepage_ingest.py`:
  - Calls `extract_patents_from_html` per Tier 2 / Tier 3 page
  - Performs canonical upsert via patent_id hard match (per spec
    Requirement "Patent canonical upsert")
  - Writes `professor_patent_link` rows
  - Files `pipeline_issue` with `stage="data_quality_flag"` on
    V004 NOT NULL constraint conflicts. Concretely: V004 makes
    `patent_number` NOT NULL UNIQUE, so candidates without a
    registration number are recorded as `data_quality_flag`
    pipeline_issues rather than inserted as canonical rows. The
    spec scenario "prof-page patent without patent_id" remains
    aspirational pending a V004 relaxation in a future change.
- [x] T4.4: Add unit tests for: zero-patents-on-page (no issue);
  page with title-only patents; page with full patent_id; conflict
  with existing canonical patent_id.

## 5. Identity gate refinement

- [x] T5.1: Verify
  `apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py`
  (current location for the paper gate; spec referenced
  `paper/identity_gate.py` but the implementation has always lived
  under `professor/` and is imported by `professor.paper_collector`)
  satisfies spec Requirement "Identity gate semantics":
  - Returns ≥ 0.8 → auto-accept ✅ (`CONFIDENCE_THRESHOLD = 0.8`
    enforced in `_verify_single_batch` and via
    `identity_verifier.CONFIDENCE_THRESHOLD`)
  - Returns ∈ [0.5, 0.8) → LLM judge fallback ✅ (the LLM call is
    the only judge; design.md §4 accepts the single-tier
    implementation as functionally equivalent to the spec's
    layered-judge framing)
  - Returns < 0.5 → reject + pipeline_issue ⚠️ rejects via
    `accepted=False`; the pipeline_issue write is a caller
    responsibility (gate stays DB-less). Documented in the
    `PaperIdentityDecision` docstring.
  - Page-only attribution → confidence 1.0 unconditionally ❌ → fixed
    in T5.2.
- [x] T5.2: Added `accept_page_only_attribution(candidate)` to
  `professor/paper_identity_gate.py`. Returns a pure
  `PaperIdentityDecision(accepted=True, confidence=1.0,
  reasoning="prof_page_declaration")` with no LLM call. The
  short-circuit is now an explicit, testable surface; existing
  `homepage_ingest` page-only flow does not yet call it (page-only
  papers bypass the gate entirely there), but the function exists
  so future code paths can be uniform with the gate contract.
- [x] T5.3: Created
  `apps/miroflow-agent/src/data_agents/professor/patent_identity_gate.py`
  with `PatentIdentityCandidate`, `PatentIdentityDecision`,
  `accept_page_only_attribution`, and `verify_xlsx_attribution`.
  Patent-side has no LLM step (design.md §8 — patents have no
  external enrichment); `verify_xlsx_attribution` is a deterministic
  name-intersection helper for the future xlsx-merge path. Scoring:
  single inventor exact match → 1.0; multi-inventor with one match →
  0.9 (accept); same-name collision (multiple matches) → 0.5
  (uncertain reject); no match → 0.0 (reject + caller pipeline_issue).
- [x] T5.4: Unit tests added — 3 in
  `tests/data_agents/professor/test_paper_identity_gate_page_only.py`
  (page-only path; ORCID-irrelevant; index preserved) + 12 in
  `tests/data_agents/professor/test_patent_identity_gate.py`
  (page-only, xlsx exact match, name-variant matching across
  scripts, same-name collision, no-inventors reject, no-name-match
  reject, substring-collision protection, blank-canonical-name
  reject, decision-contract assertion for pipeline_issue handoff).

## 6. summary_zh generation alignment

- [x] T6.1: Audited
  `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py`.
  Current prompt explicitly targets `200-400 字 中文 paraphrase`,
  matching spec P2. Validation band is 150-500 (lenient tolerance
  around the 200-400 target) — outputs outside the tolerance are
  rejected via `_validate_summary_zh`. Prompt already enforces no
  Markdown / bullet, retains terminology, no direct translation. No
  prompt drift; no changes needed.
- [x] T6.2: Added `judge_summary_boilerplate(summary, *, llm_client,
  llm_model, extra_body=None) -> bool` in `abstract_translator.py`.
  Separate LLM call with a binary classifier prompt
  (`_JUDGE_SYSTEM_PROMPT`); returns True only when the LLM emits the
  literal `BOILERPLATE` token. Fails open on transport / parse errors
  (returns False) so transient outages don't mass-reject. Empty /
  whitespace inputs skip the LLM call entirely. Callers MUST set
  `summary_zh=NULL` and `quality_status="rejected"` when this
  returns True — caller-responsibility contract documented in the
  function docstring (T7 wires this into the promotion logic).
- [x] T6.3: Unit tests added — 13 tests total. 5 pre-existing
  translator tests still pass; 13 new judge tests cover:
  parse_judge_verdict (exact / case-insensitive / verbose /
  co-occurrence / unknown), judge end-to-end
  (boilerplate-true / substantive-false / fail-open / blank-input
  short-circuit / markdown-fenced reply / temperature=0 invariant /
  extra_body plumbing).

## 7. Quality status promotion logic

- [ ] T7.1: Implement promotion state machine in
  `paper/release.py` or a new `paper/quality_promotion.py`. States
  per spec table.
- [ ] T7.2: Wire enrichment success → promotion check. If all
  Required fields present + summary_zh passes boilerplate → promote
  to `ready`.
- [ ] T7.3: Wire post-`ready` admin override (manual flag) →
  back to `needs_review`. Forward-monotonic invariant tested.
- [ ] T7.4: Symmetric implementation for patent quality promotion
  (simpler: no enrichment, so `needs_enrichment` → `ready` only on
  admin manual upgrade or xlsx merge).

## 8. Acceptance + close-out

- [ ] T8.1: Run `openspec validate prof-paper-patent-from-page-flow`;
  resolve any errors.
- [ ] T8.2: Run full pytest suite: both `apps/miroflow-agent` and
  `apps/admin-console`. All green.
- [ ] T8.3: Manual E2E: run a small batch with a real seed (e.g.
  SUSTech faculty page) and verify:
  - Papers extracted from publications section
  - Patents extracted (or zero, if no patents section)
  - Cross-domain links written
  - Enrichment fires asynchronously
  - quality_status promotion observed for at least one paper
- [ ] T8.4: Update
  `openspec/changes/prof-paper-patent-from-page-flow/acceptance.md`
  with execution evidence (commit refs + test output).
- [ ] T8.5: After T1-T7 complete, archive via `openspec archive
  --skip-specs prof-paper-patent-from-page-flow`. The
  `--skip-specs` flag is appropriate because spec/ contains the
  capability content that should remain in `openspec/specs/` after
  archive (verify CLI behavior at archive time).
- [ ] T8.6: Update
  `openspec/changes/prof-paper-patent-from-page-flow/source-links.md`
  with final code refs (file paths + commit refs).

## Out of this change's tasks

- `prof-summary-fields` (separate change #2): educator-side
  paper_summary / patent_summary aggregation columns + LLM generator
- `prof-double-milvus-collection` (separate change #3): Milvus
  collection split + retrieval routing
- `paper-summary-text-contract-fix` (separate change #5): admin API
  `domains.py:753` 1-line fix
- `paper-prd-source-list-rewrite` (separate change #4): PRD doc edits
  for §5.2 / §九 / §4.2
- `paper-msd-phase-b-status-acknowledge` (separate change #6): MSD
  §6.1 doc edit
- `paper-pipeline-cleanup` (follow-up): remove the deprecated
  `paper.pipeline.run_paper_pipeline` after all callers migrate
- chat realtime fallback (Paper Review P1 §3.2): admin-console
  chat.py change; not in paper_collector
