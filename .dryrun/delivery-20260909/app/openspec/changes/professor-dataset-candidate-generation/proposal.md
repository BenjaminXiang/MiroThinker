## Why

The dataset-quality closure runner can now audit blockers, gate writes, run
post-write verification, and classify residual risk, but the real remediation
lanes still depend on pre-existing candidate values. The next blocking gap is a
source-grounded candidate-generation layer that produces those values safely for
profile summaries, Chinese research overviews, Professor paper summaries, and
duplicate Paper canonical merge plans.

## What Changes

- Add a bounded candidate-generation contract for the four existing Professor
  dataset-quality closure lanes.
- Generate Chinese `candidate_profile_summary` values from official Professor
  evidence and linked output evidence only.
- Extract Chinese `research_overview` candidates directly from official profile
  text, or translate English official overview text with source-hash keyed LLM
  evidence.
- Generate Professor `candidate_paper_summary` values only from deduplicated
  verified Professor-seeded Paper links.
- Generate duplicate Paper canonical merge candidates from DOI/arXiv matches or
  stronger title/year/author/venue evidence, and reject ambiguous fuzzy groups.
- Emit bounded dry-run evidence that the existing dataset closure writer can
  consume without inventing fields.
- Preserve the user-confirmed domain boundary: do not discover a Professor's
  offline paper list by querying external providers with only a Professor name,
  and do not treat hidden company/startup roles as Professor core blockers.

## Capabilities

### New Capabilities

- `professor-dataset-candidate-generation`: Defines source-grounded candidate
  generation for the four Professor dataset-quality closure lanes before
  write-mode remediation.

### Modified Capabilities

- None. Existing Professor summary-field, dataset-quality closure, final
  validation, and retrieval/index capabilities remain downstream consumers of
  the generated candidates.

## Impact

- Affected code:
  - `apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py`
  - candidate generator modules under `src/data_agents/professor/`
  - the `run_professor_dataset_quality_closure.py` CLI
  - Professor summary/output helper modules and duplicate-paper planning helpers
  - targeted Professor/Paper tests and script tests
- Affected data:
  - dry-run evidence JSON for `profile_summary_repair`
  - dry-run evidence JSON for `research_overview_backfill`
  - dry-run evidence JSON for `professor_paper_summary_generation`
  - dry-run evidence JSON for `duplicate_paper_merge`
- This change is behavior-affecting. The new
  `professor-dataset-candidate-generation` capability owns the behavior
  contract for generating remediation candidates before existing write-mode
  closure batches.
