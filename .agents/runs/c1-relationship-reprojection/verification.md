# Verification — `patent-company-relationship-reprojection` (C1)

- Worktree/branch: `.worktrees/c1-relationship-reprojection` / `chore/c1-relationship-reprojection`
  (baseline `data/p4-serving-pack-rebuild@1ee824a7`)
- Slice commit: `d5e1828d` (implementation + tests + OpenSpec change)
- Contract: `verification-contract.md` (same directory)
- Scope guard: no serving read path touched; no rebuild run; zero writes under
  `/var/tmp/mirothinker-data-v2/` (replay opens the sealed pack and the staged
  released-objects DB read-only and copies the DB to `/tmp/c1-relationship-scratch/`).

## ① New tests written this slice

7 tests, all green (`uv run pytest tests/canonical_v2/test_patent_company_binding_reconciliation.py
tests/canonical_v2/test_applicant_binding_relationship_seeds.py -q` → `7 passed`).

| cluster | tests | what it locks | fixture source |
|---|---|---|---|
| seed universe (R1, R3) | `test_resolved_binding_seeds_patent_applicant_relationship`, `test_without_binding_mapping_no_applicant_seed_for_p4_patent`, `test_raw_landing_rows_are_not_a_seed_universe` | a binding whose endpoints arrive only through the mapped universe seeds exactly one edge with `match_kind=resolved_binding`; raw supplemental payloads (`patent_id` / `company_name`) are **not** a universe; a missing binding mapping seeds nothing | constructed scenario in released-object shape (same shape `_p4_*_record` synthesizes) |
| reconciliation / D0 (R2) | `test_reconciliation_accepts_a_fully_projected_document_layer`, `test_reconciliation_raises_when_a_document_binding_is_unseeded`, `test_reconciliation_counts_an_unindexed_company_as_explainable`, `test_seed_object_universe_indexes_the_mapped_object_rows` | fully projected document layer ⇒ no raise + exact ledger counts (`document_binding_pairs=1`, `seed_lanes={"resolved_binding": 1}`); an indexed-but-unseeded binding ⇒ `IsolatedKnowledgeBuildError` naming the pair; an unindexed company ⇒ counted, not fatal | run15 verbatim identifiers (`PAT-002AF039E85C`, 中建钢构股份有限公司, `company-c-be3bebaa74536edff6e2a879`) |

Pre-existing tests updated for the signature change (not weakened):
`test_applicant_binding_relationship_seeds.py` (2 call sites),
`test_knowledge_build_isolated.py::test_patent_applicant_links_seed_from_exact_company_names`
and `::test_patent_applicant_links_abstain_on_ambiguous_names` — assertions unchanged.

## ② Pre-existing regression suites

`uv run pytest tests/canonical_v2/test_knowledge_build_isolated.py
tests/canonical_v2/test_relationship_projection_contract.py
tests/canonical_v2/test_serving_pack_loader.py
tests/canonical_v2/test_patent_applicant_linking.py -q -p no:randomly`
→ (result recorded in the run log below; see "Regression run").

## ③ Replay / data-level evidence (run15 copies, read-only)

Command (from `apps/miroflow-agent`):

```bash
uv run python <worktree>/.agents/runs/c1-relationship-reprojection/replay_patent_applicant_bindings.py \
  --pack /var/tmp/mirothinker-data-v2/serving-pack-run15-sealed \
  --released-objects-db /var/tmp/mirothinker-data-v2/staging-v2/7dd904de3cf6bc1aaaef54b1be4658d7320061a096d203d156b4f5d640bf951e.source \
  --json-out <worktree>/.agents/runs/c1-relationship-reprojection/replay-run15.json
```

Result (`replay-run15.json`; raw stdout with both ledger lines in
`replay-run15-stdout.txt`):

| measure | pre-fix universe (released rows only) | post-fix universe (mapped objects) |
|---|---|---|
| `patent_has_applicant` edges seeded | **122** | **7,611** |
| document binding pairs | 7,611 | 7,611 |
| missing document pairs | 7,489 | **0** |
| seeding lanes | `resolved_binding: 122` | `resolved_binding: 7,611` |
| D0 reconciliation | **rejected** (`IsolatedKnowledgeBuildError`) | accepted, `unexplained_missing = 0` |

Cross-checks against the sealed pack itself:

- the pack ships **123** `patent_has_applicant` edges; **122** of them carry
  `evidence_metadata.match_kind = "resolved_binding"` and 1 carries
  `source_field = "core_facts.company_ids[0]"` — i.e. the replay's pre-fix
  number reproduces the shipped lane-1 population exactly;
- the 122 equals the number of document binding pairs whose **both** endpoints
  are `s12a-released-objects-full-v1` rows (patents 1,681 of 7,042 bound
  patents; companies 113 of 960 bound companies; both-endpoint intersection = 122);
- the replay's pre-fix universe is 5,561 objects; the mapped universe is 47,072
  (the pack's `source_identity_assignments` length), which is also the number of
  admitted objects;
- the replay reconstructs the objects' `core_facts` from the pack's field
  assertions, so its patent lane sees no `core_facts.company_ids` values (the
  pack retains none) — that is the only reason the replay's pre-fix figure is
  122 and not 123, and it is why the replay's post-fix figure is 7,611 =
  distinct document binding pairs.

## Documentation of the root cause

See `openspec/changes/patent-company-relationship-reprojection/design.md` §1 for
the full causal chain with `file:line` references and the sibling analysis.

## Regression run

Command:

```bash
cd apps/miroflow-agent
uv run pytest tests/canonical_v2/test_knowledge_build_isolated.py \
  tests/canonical_v2/test_relationship_projection_contract.py \
  tests/canonical_v2/test_serving_pack_loader.py \
  tests/canonical_v2/test_patent_applicant_linking.py \
  tests/canonical_v2/test_patent_company_binding_reconciliation.py \
  tests/canonical_v2/test_applicant_binding_relationship_seeds.py \
  -q -p no:randomly --no-header -o addopts=
```

Baseline comparison (this worktree detached at `1ee824a7`, same selection narrowed
to the relationship-related tests):

| revision | selection | result |
|---|---|---|
| `1ee824a7` (baseline) | `-k "relationship or applicant or seed or reconcile"` | 14 passed, **1 failed** |
| `58405450` (slice) | same selection | 14 passed, **1 failed** (same test) |

The single failure in both revisions is
`test_knowledge_build_isolated.py::test_real_boundary_rejects_nonfresh_database_before_source_read[knowledge.relationship_projection_run]`:
the test simulates alembic revision `C2_0012` (test line 1734) while
`knowledge_build_isolated.py:324` declares `_EXPECTED_ALEMBIC_REVISION = "C2_0013"`,
so `_assert_fresh_database` raises "candidate database migration revision differs
from the live single head" before the "fresh" error the test matches. It is a
**pre-existing** mismatch unrelated to this slice (no relationship/seed code on
that path) and is part of the known pre-existing failure set noted on the
functional line.

Full-selection result: `REGRESSION_FINAL` (see below).

## Gaps / not verified in this slice

- No full rebuild was run: the counts above are replay-computed on run15 data,
  not a run16 measurement. run16's `PATENT_COMPANY_BINDING_LEDGER` line is the
  acceptance artifact (AC6).
- `professor_company_role` end-to-end count after the fix is not measurable
  without a rebuild; only the shared-universe property is unit-locked (R3).
- `patent_has_inventor` / `paper_has_author` remain empty (different root cause:
  `person_projections = 0`).
