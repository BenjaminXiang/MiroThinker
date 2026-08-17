# Acceptance: paper-pipeline-cleanup

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

## Implementation Evidence

### Caller survey and classification

Command:

```bash
rg -n "discover_professor_paper_candidates_from_hybrid_sources|discover_professor_paper_candidates_from_crossref|discover_professor_paper_candidates_from_openalex|discover_professor_paper_candidates_from_orcid|discover_professor_paper_candidates_from_google_scholar_profile|discover_professor_paper_candidates_from_cv_pdf|discover_professor_paper_candidates\\(" apps/miroflow-agent/src apps/miroflow-agent/scripts
```

Final output contains only compatibility module definitions:

```text
apps/miroflow-agent/src/data_agents/paper/hybrid.py
apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py
apps/miroflow-agent/src/data_agents/paper/orcid.py
apps/miroflow-agent/src/data_agents/paper/cv_pdf.py
apps/miroflow-agent/src/data_agents/paper/openalex.py
apps/miroflow-agent/src/data_agents/paper/crossref.py
apps/miroflow-agent/src/data_agents/paper/google_scholar_profile.py
```

Removed active callers:

- `src/data_agents/professor/paper_collector.py` no longer imports or
  invokes hybrid, ORCID, Google Scholar profile, CV PDF, or legacy
  `collect_papers()` author/database discovery.
- `src/data_agents/paper/pipeline.py` no longer imports Semantic
  Scholar author discovery as its default backend; callers must inject a
  compatibility discovery function explicitly.
- `scripts/run_paper_release_e2e.py` now delegates to
  `run_homepage_paper_ingest.py` and no longer exposes `hybrid`,
  `openalex`, or `semantic_scholar` release modes.

Retained compatibility modules:

- `paper/hybrid.py` now warns and raises with a migration message before
  any external backend can run.
- `paper/{crossref,openalex,semantic_scholar,orcid,google_scholar_profile,cv_pdf}.py`
  still define legacy discovery helpers for compatibility tests only.
- `paper/enrichment.py` and DOI/metadata enrichment helpers remain
  importable; the full paper test suite still passes.

### TDD red checks

- `test_pipeline_cleanup_guard.py` failed before cleanup because
  `paper_collector.py` and the release script still contained forbidden
  discovery symbols.
- `test_enrich_from_papers_ignores_legacy_fallback_flag` failed while
  `allow_legacy_fallback` still invoked `collect_papers()`.
- `test_hybrid.py` retired-wrapper tests failed while `paper/hybrid.py`
  still executed external discovery fallback logic.
- A temporary `src/_paper_cleanup_guard_probe.py` containing
  `discover_professor_paper_candidates_from_hybrid_sources` made
  `test_pipeline_cleanup_guard.py` fail and identify the injected file;
  the probe was removed immediately after the red check.

### Green verification

```bash
PYTHONPATH=/home/longxiang/MiroThinker/.worktrees/paper-pipeline-cleanup/apps/miroflow-agent \
UV_PROJECT_ENVIRONMENT=/home/longxiang/MiroThinker/apps/miroflow-agent/.venv \
uv run --no-sync pytest -n0 apps/miroflow-agent/tests/data_agents/paper -q
```

Result: `303 passed, 1 warning in 48.93s`.

```bash
PYTHONPATH=/home/longxiang/MiroThinker/.worktrees/paper-pipeline-cleanup/apps/miroflow-agent \
UV_PROJECT_ENVIRONMENT=/home/longxiang/MiroThinker/apps/miroflow-agent/.venv \
uv run --no-sync pytest -n0 apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py -q
```

Result: `21 passed in 3.71s`.

```bash
PYTHONPATH=/home/longxiang/MiroThinker/.worktrees/paper-pipeline-cleanup/apps/miroflow-agent \
UV_PROJECT_ENVIRONMENT=/home/longxiang/MiroThinker/apps/miroflow-agent/.venv \
uv run --no-sync pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_pipeline_cleanup_guard.py -q
```

Result: `1 passed in 0.10s`; standalone coverage warnings are expected
because this guard scans files without importing `src`.

```bash
openspec validate paper-pipeline-cleanup
```

Result: `Change 'paper-pipeline-cleanup' is valid`.
