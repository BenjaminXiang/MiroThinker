# Source Links: prof-fact-extraction-expansion

## Parent and specs

- `openspec/changes/prof-admin-workbench/` — Epic parent contract.
- `openspec/changes/prof-quality-status-rework/` — re-evaluation entry
  point consumed after backfill.
- `docs/Data-Agent-Shared-Spec.md` — canonical fact provenance and data
  quality expectations.

## Code to inspect before implementation

- `apps/miroflow-agent/src/data_agents/professor/summary_generator.py`
  — existing professor summary generation.
- `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py`
  — current `professor_fact` writes.
- `apps/miroflow-agent/src/data_agents/professor/profile.py` —
  profile raw-text extraction.
- `apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py` —
  proxy-safe LLM backfill pattern to reuse where appropriate.
- `apps/miroflow-agent/tests/data_agents/professor/test_summary_generator.py`
  — nearest summary tests.
- `apps/miroflow-agent/tests/professor/test_canonical_writer.py` —
  fact persistence tests.
