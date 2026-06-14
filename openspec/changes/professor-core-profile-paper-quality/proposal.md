## Why

The current Professor-to-Paper chain can persist partially cleaned teacher and
paper data as user-visible records, and the existing quality gate can mark those
records as `ready` even when Chinese research descriptions, output summaries,
paper deduplication, and paper links are incomplete. This now blocks the
Professor detail UI and the test-set questions that expect complete teacher
profiles and paper links.

## What Changes

- Add an end-to-end quality contract for the Professor core profile and paper
  chain: university roster seed -> official teacher profile -> profile sections
  -> homepage-listed papers -> external paper enrichment -> quality promotion
  -> admin/chat presentation.
- Persist a Chinese research overview for teacher profiles, with LLM
  translation allowed when the official profile only provides English text.
- Strengthen Professor `ready` eligibility so it reflects user-facing quality,
  not only the presence of minimal identity fields.
- Require canonical paper deduplication and merge traceability for professor
  homepage papers before those papers are used in Professor output summaries or
  user-facing lists.
- Chain the post-seed follow-up work that is currently scattered across paper
  ingest, title enrichment, paper summary generation, Professor output
  summaries, quality re-evaluation, and index refresh.
- Make paper titles in Professor detail surfaces navigable to
  `/paper/<paper_id>` and require chat citations to use the same page route.
- Keep Professor-company/news association out of this core readiness contract;
  those links may be filled by runtime multi-source recall or downstream
  cross-domain evidence, but they are not required for Professor core data to be
  ready.

## Capabilities

### New Capabilities

- `professor-core-profile-paper-quality`: Defines the end-to-end quality
  contract for Professor core profile fields, homepage-derived papers, paper
  enrichment/deduplication, Professor output summaries, and user-facing paper
  links.

### Modified Capabilities

- None. Existing Professor seed, summary, detail, audit, and Paper enrichment
  capabilities remain local building blocks. This change adds the cross-stage
  release contract that coordinates them.

## Impact

- Affected schemas and migrations:
  - `professor` or an equivalent section table for durable Chinese research
    overview storage.
  - Paper merge/alias traceability if the existing paper table cannot express
    the resolved canonical target for merged page-only rows.
- Affected pipeline code:
  - Admin seed follow-up orchestration in `apps/admin-console/backend/api/seeds.py`.
  - Professor seed write and homepage recursion handling in
    `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`.
  - Homepage paper ingest and canonical upsert paths in
    `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` and
    `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py`.
  - Paper title enrichment, summary generation, Professor output summary
    generation, quality re-evaluation, and vector refresh scripts.
- Affected APIs and UI:
  - Admin Professor detail API and React Professor workbench.
  - Chat answer/citation generation for paper detail links.
- Affected tests and acceptance:
  - Regression cases for Ahmed Elazab, Ding Wenbo, and the pFedGPA paper from
    `docs/测试集答案.xlsx`.
  - Matrix tests for summary quality, paper deduplication, paper link routing,
    and post-seed follow-up sequencing.
