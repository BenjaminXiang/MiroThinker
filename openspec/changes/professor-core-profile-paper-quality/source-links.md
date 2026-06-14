# Source Links

## User Requirements

- User clarified that the Professor core chain is university roster page ->
  official teacher profile -> Professor-seeded papers -> paper enrichment.
- User clarified that company/news associations may be recovered by runtime
  multi-source retrieval and should not be required inside Professor core data.
- User provided `docs/测试集答案.xlsx` as sample question/answer evidence,
  especially Ding Wenbo and pFedGPA rows.

## Current Code Surfaces Reviewed

- `apps/admin-console/backend/api/seeds.py` - admin seed trigger and post-seed
  homepage paper ingest follow-up.
- `apps/miroflow-agent/src/data_agents/professor/seed_runner.py` - Professor
  seed write path and homepage recursion source persistence.
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` - homepage
  publication extraction, title resolution, paper upsert, and
  `professor_paper_link` writes.
- `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py` - paper id
  construction and upsert conflict behavior.
- `apps/miroflow-agent/scripts/run_paper_title_enrichment_backfill.py` - current
  repair path for page-only paper title enrichment and link migration.
- `apps/miroflow-agent/src/data_agents/paper/quality_promotion.py` - paper
  `ready` promotion requirements.
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` - persisted
  Professor quality-state evaluation.
- `apps/miroflow-agent/src/data_agents/professor/output_summaries.py` - current
  Professor paper/patent summary generation.
- `apps/admin-console/backend/api/admin_professors.py` - Professor detail API
  and raw research-overview extraction.
- `apps/admin-console/frontend/src/pages/ProfessorWorkbench.tsx` - Professor
  detail UI paper table.
- `apps/admin-console/frontend/src/App.tsx` - existing `/:domain/:id` route.

## Existing Contracts And Docs

- `docs/Professor-Data-Agent-PRD.md` - legacy but still useful
  `profile_summary` quality requirement and Professor collection flow.
- `docs/Agentic-RAG-PRD.md` - runtime multi-source retrieval and multi-turn
  behavior.
- `openspec/changes/archive/2026-05-23-prof-paper-patent-from-page-flow/specs/paper-patent-from-prof-page/spec.md`
  - official Professor page discovery and paper deduplication contract.
- `openspec/specs/professor-summary-fields/spec.md` - existing durable
  Professor `paper_summary` and `patent_summary` contract.
- `openspec/specs/professor-detail-readability/spec.md` - current Admin detail
  research overview behavior.
- `openspec/specs/paper-homepage-enrichment-completion/spec.md` - current paper
  homepage enrichment completion surface.

## Baseline Data Snapshot

Read-only database audit from the review phase:

- 3,387 Professors total; 1,407 marked `ready`.
- 928 Professors have `profile_summary` shorter than 150 characters; 230 of
  those are marked `ready`.
- 2,202 Professors have verified papers; 2,202 are missing `paper_summary`.
- 49,484 verified Professor-paper links.
- 6,563 verified duplicate normalized title/year groups, affecting 994
  Professors; 6,315 groups include an enriched row.
- Ahmed Elazab and Ding Wenbo are currently `ready` while missing
  `paper_summary`.
- pFedGPA is currently `prof_page_only`, `needs_enrichment`, and lacks arXiv/PDF
  data in the audited database snapshot.
