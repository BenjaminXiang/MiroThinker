# Tasks: paper-pipeline-cleanup

## 1. Caller survey

- [x] T1.1: Run `rg` for legacy `discover_*` functions and record
  callers in `acceptance.md`.
- [x] T1.2: Classify each caller as production, legacy script, or test.
- [x] T1.3: Confirm enrichment helpers that must remain available.

## 2. Production cleanup

- [x] T2.1: Remove external DB discovery calls from
  `src/data_agents/professor/paper_collector.py`.
- [x] T2.2: Ensure page-extracted paper candidates remain the only
  production discovery source.
- [x] T2.3: Preserve DOI/metadata enrichment through
  `paper/enrichment.py`.
- [x] T2.4: Update tests that currently patch legacy discovery callers.

## 3. Legacy modules and scripts

- [x] T3.1: Convert `paper/hybrid.py` discovery surface into a
  compatibility wrapper that warns or remove it if no caller remains.
- [x] T3.2: Retire or rewrite `paper/pipeline.py` so it cannot be used
  as a live release path.
- [x] T3.3: Retire or rewrite `scripts/run_paper_release_e2e.py` so it
  no longer offers `hybrid` or Semantic Scholar author discovery modes.
- [x] T3.4: Keep enrichment-only Crossref/Semantic Scholar/OpenAlex
  helpers importable.

## 4. Guardrails

- [x] T4.1: Add a grep-style pytest or lint check forbidding retired
  discovery imports in production source.
- [x] T4.2: Add an allowlist for compatibility modules and tests only.
- [x] T4.3: Verify the guard fails when a forbidden import is injected.

## 5. Verification

- [x] T5.1: Run paper/professor tests touched by cleanup.
- [x] T5.2: Run the forbidden-import guard test.
- [x] T5.3: Run `openspec validate paper-pipeline-cleanup`.
- [x] T5.4: Record grep output proving no active production caller
  remains.
