# Source Links

## User Requirements

- The user accepted a separate `professor-dataset-quality-closure` change to
  handle the remaining dataset-level blockers after the named baseline cases
  passed.
- The Professor core chain remains: university roster page -> official
  Professor profile -> Professor-seeded papers -> external paper enrichment.
- Runtime user answers may perform multi-source recall across Professor,
  Company, News, Paper, and Patent data, but Professor core readiness must not
  depend on hidden company or startup roles.
- The user wants fixes grounded in current code and current data evidence, not
  one-off patches.

## Current Evidence

- `professor-core-profile-paper-quality` completed with Ahmed Elazab, Ding
  Wenbo, and pFedGPA passing against the real database and API.
- The final audit for that change still reports dataset-level blockers:
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`

## Code Surfaces To Inspect During Implementation

- `apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py`
- `apps/miroflow-agent/src/data_agents/professor/core_profile_paper_quality_audit.py`
- `apps/miroflow-agent/scripts/run_professor_quality_re_eval.py`
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- `apps/miroflow-agent/src/data_agents/professor/profile_summary_contract.py`
- `apps/miroflow-agent/scripts/run_professor_research_overview_backfill.py`
- `apps/miroflow-agent/src/data_agents/professor/profile_sections.py`
- `apps/miroflow-agent/src/data_agents/professor/output_summaries.py`
- `apps/miroflow-agent/scripts/run_paper_title_enrichment_backfill.py`
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
- `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py`
- `apps/admin-console/backend/api/admin_professors.py`
- `apps/admin-console/backend/api/domains.py`
- `apps/admin-console/frontend/src/pages/ProfessorWorkbench.tsx`

## Related Specs

- `openspec/changes/professor-core-profile-paper-quality/`
- `openspec/specs/professor-post-full-quality-audit/spec.md`
- `openspec/specs/professor-summary-fields/spec.md`
- `openspec/specs/professor-final-validation/spec.md`
- `openspec/specs/professor-seed-management/spec.md`
- `openspec/specs/paper-homepage-enrichment-completion/spec.md`
