# Acceptance: patent-company-relationship-reprojection (C1)

## Acceptance criteria

| # | criterion | evidence source | status |
|---|---|---|---|
| AC1 | Every document-layer applicant binding pair whose both endpoints are admitted objects produces a `patent_has_applicant` seed | unit test `test_raw_landing_rows_are_not_a_seed_universe` + replay: pre-fix 122 / post-fix **7,611** = the 7,611 document pairs | met |
| AC2 | A binding that cannot be seeded fails the build unless it is classified as `unindexed` (target company has no admitted object) | unit tests `test_reconciliation_raises_when_a_document_binding_is_unseeded` / `test_reconciliation_counts_an_unindexed_company_as_explainable`; replay: pre-fix state **rejected**, post-fix accepted with `unexplained_missing = 0` | met |
| AC3 | One machine-readable `PATENT_COMPANY_BINDING_LEDGER` line per build, carrying document/relationship counts by seeding lane and `unexplained_missing` | `knowledge_build_isolated._reconcile_patent_company_bindings` (prints next to `APPLICANT_BINDING_LEDGER`); both replay ledger lines in `replay-run15-stdout.txt` | met |
| AC4 | `professor_company_role` uses the same universe (no lane reads a released-only universe) | one shared helper `_relationship_seed_object_rows` feeds every lane and the reconciliation; seeds-lane test asserts the universe contents | met |
| AC5 | No service-period behaviour change: no serving/pack-loader/index-projection file in the diff; serving + relationship contract suites green | `git diff --name-only 1ee824a7` touches only `knowledge_build_isolated.py`, `patent_applicant_linking.py` (docstring) and tests; regression suites see `verification.md` §② | met |
| AC6 | Expected run16 outcome stated and testable: edges `123 → 7,611`, companies `49 → 960`, `unexplained_missing = 0` | run16 `PATENT_COMPANY_BINDING_LEDGER` line | pending (run16) |

## Acceptance evidence at Candidate

1. `.agents/runs/c1-relationship-reprojection/verification.md` — layered report
   (① new tests ② pre-existing suites ③ replay).
2. `.agents/runs/c1-relationship-reprojection/replay-run15.json` +
   `replay-run15-stdout.txt` — replay counts and raw ledger lines.
3. `docs/plans/2026-09-15-c1-relationship-log.md` — human-readable log;
   `docs/plans/index.md` entry.
4. Zero-write statement: `/var/tmp/mirothinker-data-v2/` was opened read-only;
   the replay copied the staged released-objects DB into
   `/tmp/c1-relationship-scratch/`. The 18188 service was not restarted or
   touched; no other worktree was modified.

## Not accepted as evidence

- "The projection admits everything" — true on the baseline too.
- A count-only comparison without the classified difference list.
- Any change to the serving-period direct scan (`_direct_patent_applicant_scan`).
