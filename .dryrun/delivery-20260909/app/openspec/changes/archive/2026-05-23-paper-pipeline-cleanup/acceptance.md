# Acceptance: paper-pipeline-cleanup

## 2026-05-23 T1 caller survey

Commands:

- `rg -n "discover_professor_paper_candidates|discover_best_hybrid|_discover_official_linked|run_paper_pipeline|enrich_paper_with_hybrid_sources" apps/miroflow-agent/src apps/miroflow-agent/scripts -g '*.py'`
- `rg -n "discover_professor_paper_candidates|discover_best_hybrid|_discover_official_linked|run_paper_pipeline" apps/miroflow-agent/tests -g '*.py'`
- `rg -n "def enrich_paper_with_hybrid_sources|enrich_paper_metadata_from_|discover_professor_paper_candidates_from_" apps/miroflow-agent/src/data_agents/paper -g '*.py'`

Production callers that must be cleaned up:

- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
  imports and invokes
  `discover_professor_paper_candidates_from_hybrid_sources`.
  `_discover_best_hybrid_result()` calls it three times. `enrich_from_papers()`
  calls `_discover_best_hybrid_result()` on every run before preferring
  official page papers, so this is an active production discovery path.
- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
  imports and invokes
  `discover_professor_paper_candidates_from_orcid`,
  `discover_professor_paper_candidates_from_google_scholar_profile`, and
  `discover_professor_paper_candidates_from_cv_pdf` through
  `_discover_official_linked_*` helpers. These are linked-profile discovery
  paths and must either be removed from production candidate-list discovery or
  converted into allowed metadata-only enrichment under the page-first
  contract.
- `apps/miroflow-agent/src/data_agents/paper/pipeline.py` still defaults to
  `semantic_scholar.discover_professor_paper_candidates` inside
  `run_paper_pipeline()`. The module is documented as legacy and emits a
  warning, but it remains a runnable discovery path until T3 retires or
  rewrites it.
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py` still implements
  hybrid OpenAlex/Semantic Scholar/Crossref candidate discovery. It should
  become a compatibility wrapper or be removed from production import paths.

Legacy or operator scripts:

- `apps/miroflow-agent/scripts/run_paper_release_e2e.py` imports hybrid,
  OpenAlex, Semantic Scholar discovery functions and exposes
  `--source {hybrid,openalex,semantic_scholar}`. This directly violates the
  release-script requirement and must be retired or rewritten in T3.
- `apps/miroflow-agent/scripts/run_professor_phase_a_machine_audit.py`
  imports `_discover_best_hybrid_result()` and uses it for audit scoring. It
  is a legacy audit helper, not the current release path, but it is still a
  non-test script caller and should be covered by the guard allowlist or
  rewritten.

Allowed enrichment surfaces that must remain available:

- `apps/miroflow-agent/src/data_agents/paper/enrichment.py` provides
  `enrich_paper_with_hybrid_sources()` for DOI-based metadata enrichment of
  already discovered papers.
- `apps/miroflow-agent/src/data_agents/paper/crossref.py` provides
  `enrich_paper_metadata_from_crossref()`.
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py` provides
  `enrich_paper_metadata_from_semantic_scholar()`.
- `apps/miroflow-agent/src/data_agents/paper/openalex.py` continues to provide
  DOI/metadata enrichment support used by the enrichment fallback chain.
- `apps/miroflow-agent/src/data_agents/paper/doi_enrichment.py` is an
  enrichment helper and may remain available when not used for author-name
  candidate discovery.
- `apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py` imports
  `enrich_paper_with_hybrid_sources()` only for DOI metadata enrichment during
  summary backfill; this is allowed under the current design.

Test-only references:

- `apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py`
  patches the retired discovery functions and tests existing behavior that
  T2 will need to rewrite.
- `apps/miroflow-agent/tests/data_agents/paper/test_hybrid.py`,
  `test_pipeline.py`, `test_crossref.py`, `test_semantic_scholar.py`,
  `test_openalex.py`, `test_openalex_picker_integration.py`, `test_orcid.py`,
  `test_cv_pdf.py`, and `test_google_scholar_profile.py` exercise retired
  discovery modules or their enrichment counterparts. These should be allowed
  in tests or rewritten as production cleanup proceeds.
- `apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py` and
  `apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py`
  cover allowed enrichment use.
- `apps/miroflow-agent/tests/scripts/test_run_professor_phase_a_machine_audit.py`
  covers the legacy audit script.

## 2026-05-23 T2-T5 cleanup evidence

Implementation changes:

- `src/data_agents/professor/paper_collector.py` no longer imports or
  calls hybrid, OpenAlex, Crossref, Semantic Scholar, ORCID, Google
  Scholar, CV-PDF, or legacy academic-tool discovery to generate paper
  candidates. It consumes usable official page publications only, keeps
  official page counts, and leaves metrics from external author profiles
  unset.
- `src/data_agents/paper/hybrid.py` is now a compatibility wrapper that
  emits `DeprecationWarning` and returns an empty result.
- `src/data_agents/paper/pipeline.py` emits `DeprecationWarning` and
  raises before any author-discovery or release work can run.
- `scripts/run_paper_release_e2e.py` is a retired wrapper and no longer
  accepts `--source hybrid`, OpenAlex, or Semantic Scholar discovery
  modes.
- `scripts/run_professor_phase_a_machine_audit.py` records
  `legacy_paper_discovery_retired` instead of invoking hybrid paper
  discovery.

RED checks:

- `uv run --no-sync pytest tests/data_agents/paper/test_pipeline_cleanup_guard.py -q`
  failed before cleanup with forbidden production references in
  `scripts/run_paper_release_e2e.py`,
  `scripts/run_professor_phase_a_machine_audit.py`, and
  `src/data_agents/professor/paper_collector.py`.
- `uv run --no-sync pytest tests/data_agents/paper/test_hybrid.py tests/data_agents/paper/test_pipeline.py -q -n0`
  failed before T3 implementation because `hybrid.py` did not warn and
  `paper.pipeline.run_paper_pipeline()` did not raise.

GREEN checks:

- `uv run --no-sync pytest tests/data_agents/paper/test_hybrid.py tests/data_agents/paper/test_pipeline.py tests/data_agents/paper/test_pipeline_cleanup_guard.py tests/data_agents/professor/test_paper_collector.py tests/scripts/test_run_professor_phase_a_machine_audit.py -q -n0`
  passed: 28 passed.
- `uv run --no-sync pytest tests/scripts/test_run_paper_release_e2e.py -q -n0`
  passed: 2 passed.
- `uv run --no-sync pytest tests/data_agents/paper -q -n0`
  passed: 302 passed.
- `uv run --no-sync pytest tests/scripts/test_run_homepage_paper_ingest.py -q -n0`
  passed: 8 passed.
- `uv run --no-sync python scripts/run_homepage_paper_ingest.py --help`
  exited 0 and displayed the page-first homepage ingest CLI.
- `PYTHONPATH=tests uv run --no-sync python - <<'PY' ... _forbidden_discovery_references(REPO_ROOT) ... PY`
  printed no violations.
- `uv run --no-sync ruff check ...`
  passed for all cleanup source and test files.

## Spec validation

- [x] `openspec validate paper-pipeline-cleanup` exits 0.

## Caller cleanup

- [x] No production caller imports or invokes
  `discover_professor_paper_candidates_from_hybrid_sources`.
- [x] No production caller generates a paper candidate list from
  OpenAlex, Crossref, Semantic Scholar, ORCID, Google Scholar, or CV PDF
  author-profile discovery.
- [x] Page-first `paper/homepage_ingest.py` remains the active discovery
  path.
- [x] DOI/metadata enrichment helpers remain available.

## Guardrails

- [x] A test or lint rule fails on forbidden discovery imports in
  production source.
- [x] The guard has a narrow allowlist for compatibility modules and
  tests.

## Scripts

- [x] Legacy release scripts no longer present hybrid/S2 author
  discovery as the release path.
- [x] Any retained legacy wrapper emits `DeprecationWarning`.
