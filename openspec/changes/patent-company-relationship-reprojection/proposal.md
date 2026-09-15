# Proposal: patent-company-relationship-reprojection (C1)

> Human context: `docs/plans/2026-09-15-c1-relationship-log.md` (data-line log) and
> `docs/plans/2026-09-15-requirements-gap-plan.md` §10 C1 (user ruling) on the
> functional line. Evidence base: `.agents/runs/data-quality-assessment/assessment-20260915.md`
> §2 F-01.

## Why

The run15 sealed pack publishes two disagreeing views of the same fact
"this patent has this applicant company":

| store | measure | run15 |
|---|---|---|
| document layer (`applicants[].canonical_company_id` on the patents' field assertions) | rows / patents / companies | **7,614 / 7,042 / 960** |
| relationship layer (`relationships.json` → `patent_has_applicant`) | edges / patents / companies | **123 / 123 / 49** |

The document layer is the service-period authority (user ruling 2026-09-15: the
G3-simple direct scan `_direct_patent_applicant_scan` stays as-is). The
relationship layer is a data-line product and is wrong by a factor of ~62.

The projection layer is **not** the culprit: run15's
`relationship_projection_result` shows `patent_has_applicant`
`admitted = 123, rejected = 0` — it projected every candidate it received. The
loss is one stage earlier, in seed generation (`design.md` §1).

## What Changes

1. **Seed universe fix** (`knowledge_build_isolated.py`): `_typed_relationship_seeds`
   must build its object universe from the **mapped admitted objects**
   (`_map_public_authority`'s `row_by_object`, which already contains the
   released-object shape synthesized for every P4/backfill supplemental object)
   instead of from the raw `source_rows` — only the `s12a-released-objects-full-v1`
   rows of which carry a released-object payload. Raw supplemental rows remain
   the input for the `professor_company_role` source-purpose lane.
2. **Anti-drift reconciliation (D0)**: a build-time
   `PATENT_COMPANY_BINDING_LEDGER` line plus a fail-closed invariant that every
   document-layer applicant binding pair is either seeded or explicitly counted
   as unindexed. This closes the "7,042 → 123 silently ships" hole permanently.
3. **Sibling scope**: the same universe fix covers the `professor_company_role`
   lane (run15: 1 edge). `patent_has_inventor` / `paper_has_author` /
   `paper_references_paper` have a *different* root cause (run15 ships
   `person_projections = 0`) and are reported, not fixed.

## What Does Not Change

- Service-period behaviour: no serving read path, pack loader, index projection
  or answer path is touched.
- No rebuild is run in this slice; the fix takes effect with run16.
- The relationship model, its registry, evidence assertions and
  `applicant_supporting_assertion_ids` semantics are unchanged — the fix reuses
  the existing typed-seed → typed-assertion → decision path.

## Impact

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`
  (seed universe, reconciliation ledger + invariant).
- New tests under `apps/miroflow-agent/tests/canonical_v2/`.
- `patent_applicant_linking.py` module docstring (the release-only universe
  claim it documents).

## Measured Outcome (expected, run16 verification pending)

`patent_has_applicant` edges `123 → 7,611` (one per distinct document binding
pair), companies `49 → 960`, with `unexplained_missing = 0`.
