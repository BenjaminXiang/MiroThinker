# Verification: paper-pipeline-cleanup

## 2026-05-23 T1 caller survey

Scope:
- Execute T1.1, T1.2, and T1.3 only.
- Classify legacy paper discovery callers before writing cleanup tests or
  production code.
- Do not mark cleanup acceptance items complete yet; this is survey evidence.

Commands and outcomes:

- `openspec status --change paper-pipeline-cleanup --json`
  - Result: schema `spec-driven`, all required artifacts present.

- `openspec instructions apply --change paper-pipeline-cleanup --json`
  - Result: 0/18 tasks complete before this survey; state `ready`.

- `rg -n "discover_professor_paper_candidates|discover_best_hybrid|_discover_official_linked|run_paper_pipeline|enrich_paper_with_hybrid_sources" apps/miroflow-agent/src apps/miroflow-agent/scripts -g '*.py'`
  - Result: production discovery callers found in
    `src/data_agents/professor/paper_collector.py`,
    `src/data_agents/paper/hybrid.py`, and `src/data_agents/paper/pipeline.py`.
  - Result: legacy/operator script callers found in
    `scripts/run_paper_release_e2e.py` and
    `scripts/run_professor_phase_a_machine_audit.py`.
  - Result: allowed enrichment use found in
    `scripts/run_paper_summary_zh_backfill.py`.

- `rg -n "discover_professor_paper_candidates|discover_best_hybrid|_discover_official_linked|run_paper_pipeline" apps/miroflow-agent/tests -g '*.py'`
  - Result: test references found in professor paper collector tests, paper
    hybrid/pipeline/provider tests, and legacy audit-script tests. These are
    not production callers but must be considered when rewriting T2/T3 tests.

- `rg -n "def enrich_paper_with_hybrid_sources|enrich_paper_metadata_from_|discover_professor_paper_candidates_from_" apps/miroflow-agent/src/data_agents/paper -g '*.py'`
  - Result: confirmed `paper.enrichment.enrich_paper_with_hybrid_sources`,
    Crossref metadata enrichment, Semantic Scholar metadata enrichment,
    OpenAlex metadata support, and DOI enrichment helpers that must stay
    available.

Task status updated:
- T1.1 complete.
- T1.2 complete.
- T1.3 complete.

Next implementation step:
- T2 should start with RED guard/tests proving
  `professor.paper_collector` and release scripts still violate the
  page-first discovery boundary before production cleanup.

## 2026-05-23 T2-T5 cleanup and guard verification

Scope:
- Complete T2 production cleanup.
- Complete T3 legacy module/script retirement.
- Complete T4 guardrails.
- Complete T5 focused validation, page-first CLI smoke, and OpenSpec
  validation.

RED commands and outcomes:

- `uv run --no-sync pytest tests/data_agents/paper/test_pipeline_cleanup_guard.py -q`
  - Result: failed before cleanup, as expected.
  - First reported violation:
    `scripts/run_paper_release_e2e.py:16:
    discover_professor_paper_candidates_from_hybrid_sources (import)`.
  - Violation classes also covered
    `scripts/run_professor_phase_a_machine_audit.py` and
    `src/data_agents/professor/paper_collector.py`.

- `uv run --no-sync pytest tests/data_agents/paper/test_hybrid.py tests/data_agents/paper/test_pipeline.py -q -n0`
  - Result: failed before T3 implementation, as expected.
  - Failure 1: `hybrid.py` did not emit `DeprecationWarning`.
  - Failure 2: `paper.pipeline.run_paper_pipeline()` did not raise and
    remained executable.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/data_agents/paper/test_hybrid.py tests/data_agents/paper/test_pipeline.py tests/data_agents/paper/test_pipeline_cleanup_guard.py tests/data_agents/professor/test_paper_collector.py tests/scripts/test_run_professor_phase_a_machine_audit.py -q -n0`
  - Result: passed, 28 passed.

- `uv run --no-sync pytest tests/scripts/test_run_paper_release_e2e.py -q -n0`
  - Result: passed, 2 passed.

- `uv run --no-sync pytest tests/data_agents/paper -q -n0`
  - Result: passed, 302 passed.

- `uv run --no-sync pytest tests/scripts/test_run_homepage_paper_ingest.py -q -n0`
  - Result: passed, 8 passed.

- `uv run --no-sync python scripts/run_homepage_paper_ingest.py --help`
  - Result: exited 0.
  - Output confirmed page-first options: `--dry-run`, `--limit`,
    `--institution`, `--prof-id`, `--resume`, and `--log-level`.

- `PYTHONPATH=tests uv run --no-sync python - <<'PY' ... _forbidden_discovery_references(REPO_ROOT) ... PY`
  - Result: exited 0 and printed no forbidden production references.

- `uv run --no-sync ruff check src/data_agents/paper/hybrid.py src/data_agents/paper/pipeline.py src/data_agents/professor/paper_collector.py scripts/run_professor_phase_a_machine_audit.py scripts/run_paper_release_e2e.py tests/data_agents/paper/test_hybrid.py tests/data_agents/paper/test_pipeline.py tests/data_agents/paper/test_pipeline_cleanup_guard.py tests/data_agents/professor/test_paper_collector.py tests/scripts/test_run_professor_phase_a_machine_audit.py tests/scripts/test_run_paper_release_e2e.py`
  - Result: passed, `All checks passed!`.

Task status updated:
- T2.1 complete.
- T2.2 complete.
- T2.3 complete.
- T2.4 complete.
- T3.1 complete.
- T3.2 complete.
- T3.3 complete.
- T3.4 complete.
- T4.1 complete.
- T4.2 complete.
- T4.3 complete.
- T5.1 complete.
- T5.2 complete.
- T5.3 complete.
- T5.4 complete.

Current validation boundary:
- No live database E2E was run because `DATABASE_URL` and
  `DATABASE_URL_TEST` are not set in this shell.
- The page-first CLI was smoke-verified with `--help`, and its scripted
  dry-run/dispatch behavior was verified through
  `tests/scripts/test_run_homepage_paper_ingest.py`.
