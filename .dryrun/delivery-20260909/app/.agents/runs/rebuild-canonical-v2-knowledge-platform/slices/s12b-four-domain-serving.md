# Slice Contract: S12B Four-Domain Candidate Serving

## Status

Candidate.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `12.2`
- Dependency: Accepted S12A r12 Candidate builder.

## Goal

Extend the isolated Candidate path so one fresh build produces non-zero Professor, Company, Paper,
and Patent projections, the evidence-backed Professor/Company, Professor/Paper, and Company/Patent
paths supported by the admitted restored source, matching lookup/vector projections, and one
content-addressed read-only serving bundle consumed by the normal chat API/UI.

## Non-goals

- No workbook-as-runtime-data, hardcoded workbook answers, or acceptance from historical prose.
- No Task 12.3 full 17-conversation/25-turn benchmark replay.
- No active-release pointer change, production cutover, source cleanup, migration, or original-source
  access.
- No human-label, dual-review, calibration, or retired `/review` gate.

## Allowed scope

- The S12A isolated builder, its focused tests, and the single-call runner.
- Canonical V2 isolated read/serving adapters and focused tests needed for the three relationship
  paths and real chat binding.
- This slice contract, its implementation plan, serving bundle, envelope, and existing OpenSpec
  task/acceptance/verification ledgers after evidence exists.

## Forbidden changes

- Original PostgreSQL or Milvus, active aliases/pointers, accepted backup bytes, or production data.
- Public schema/migrations, unrelated legacy consumers, and benchmark definitions.
- Secrets or credentials in the serving bundle; provider credentials remain environment-only.
- Broad refactors or full-suite verification without a concrete regression signal.

## Expected unchanged behavior

- S12A source isolation, fail-before-effect validation, content hashes, typed gaps, exact index parity,
  and no-promotion guarantees remain intact.
- Evidence remains source-grounded and missing material evidence remains a visible limitation.
- The normal `/api/chat` and `/chat` interfaces remain the user-facing entry points.

## Required checks

1. Focused builder tests prove representative restored shapes project into all four domains and the
   three supported relationship types without inventing endpoints.
2. One fresh isolated build reports non-zero four-domain counts and matching lookup/vector parity.
3. Focused serving tests prove bundle hash validation, environment-only provider configuration,
   single-build runtime composition, and no active-pointer write.
4. One real `/api/chat` smoke through the Candidate app returns a structured response from the bound
   release; Task 12.3 owns broader answer-quality replay.
5. Changed-file Ruff/Pyright, strict OpenSpec validation, and `git diff --check` run once at closure.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12b/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

## Stop conditions

- The admitted restored copy cannot support a required relationship without inference.
- A public schema or migration change becomes necessary.
- Implementation would require reading original sources or moving an active pointer.
- Provider configuration cannot remain secret-free and environment-bound.

## Done means

The fresh Candidate, serving bundle, and normal chat path satisfy Task 12.2 evidence. Task 12.2 is
checked only then; Task 12.3 remains open.
