# Verification contract — `patent-company-relationship-reprojection` (C1)

Change: `openspec/changes/patent-company-relationship-reprojection/`
Human log: `docs/plans/2026-09-15-c1-relationship-log.md`
Baseline: `data/p4-serving-pack-rebuild@1ee824a7` (run15 build `p4-build-20260913-v1`,
release `candidate-v2-20260913-r1`, sealed pack `serving-pack-run15-sealed`).

Scope: **build-time relationship projection only**. The serving-period
document-layer authority (`_direct_patent_applicant_scan`, G3-simple) is not
touched (user ruling 2026-09-15, requirements-gap plan §10 C1). No rebuild is
run in this slice; the fix takes effect with run16.

## RED assertions (must fail on the baseline, pass after the change)

### R1 — the seed universe must cover every admitted object (defect reproduction)

Given the run15 staged sources, `_typed_relationship_seeds` must be able to seed
every `patent_has_applicant` edge whose **both endpoints are admitted objects**
(`row_by_object`), not only those whose endpoints happen to be
`s12a-released-objects-full-v1` rows.

- Baseline evidence (measured, see `verification.md`): the seed function builds
  its object universe from `row.payload["id"]`
  (`knowledge_build_isolated.py:6485-6489`); only the released-objects source
  carries a released-object payload (`:9354-9361`). The 12 supplemental sources
  keep their raw domain shape (`p4-patent-full-v1.jsonl` keys the identity as
  `patent_id`, `p4-company-full-v1.jsonl` as `company_name`), so every
  supplemental object is invisible to the seed function — although
  `_merge_p4_created_rows` has already synthesized the released-object payload
  for each of them (`:4938`).
- RED unit test: a patent and a company that exist **only** as supplemental
  objects (present in the mapped object universe, absent from the raw released
  rows) with a resolved applicant binding must produce exactly one
  `patent_has_applicant` seed.
  Fixture: real run15 applicant-binding sample
  (`PAT-002AF039E85C` ← 中建钢构股份有限公司 / `company-c-be3bebaa74536edff6e2a879`).
- Expected post-fix count (computed from the run15 pack, see replay below):
  `application`/`applicant` binding pairs `7,611` → `patent_has_applicant`
  candidates `7,611` (+ `company_ids`-lane edges), versus **123** on the baseline.

### R2 — no document-layer applicant binding may be silently dropped

After the seed stage, the build must reconcile the **document layer**
(`applicants[].canonical_company_id` on the patents' field assertions — the
service-period authority) against the **relationship layer** (the accepted
`patent_has_applicant` edges) and fail closed:

- `INVARIANT-1`: `document_pairs − seed_pairs − unindexed_pairs = ∅`, where
  `document_pairs` = distinct (patent canonical, company canonical) pairs from
  the applicants bindings, `seed_pairs` = the typed seeds, and `unindexed_pairs`
  = pairs whose target company has no admitted object (counted, reported).
- Violation ⇒ `IsolatedKnowledgeBuildError` naming the counts and a sample of
  the missing pairs. This is the D0 anti-drift guard: the 7,042 → 123 regression
  can never ship silently again.
- The reconciliation emits one machine-readable ledger line
  `PATENT_COMPANY_BINDING_LEDGER {...}` per build (alongside the existing
  `APPLICANT_BINDING_LEDGER`), with `document_binding_pairs`,
  `relationship_binding_candidates`, `unindexed_pairs`, `extra_seed_pairs`
  (by seeding lane) and `unexplained_missing`.
- RED unit test: a document binding pair that produces no seed and has no
  explainable reason must raise; a fully projected document layer must not raise.

### R3 — sibling `professor_company_role` lane shares the defect

The same object universe feeds the `professor_company_role` lane
(`:6503-6517` `professor_ids_by_name`/`company_ids_by_name`), so the run15
1-edge result for that type must be re-counted after the fix. Assertion: the
lane's company/professor name indexes are built from the **same** universe as
R1 (no lane reads a released-only universe).

### R4 — no service-period behaviour change

No file under the serving read path (`knowledge_read_isolated.py`,
`serving_pack_loader.py`, `index_projection_isolated.py`,
`release_publication_isolated.py`) changes. Assertion: `git diff` on the slice
touches only `knowledge_build_isolated.py` + tests + `patent_applicant_linking.py`
docstring, and the existing serving/relationship contract suites stay green.

## GREEN evidence required

1. New unit tests: R1 (both-endpoints-supplemental seeding), R2 (reconciliation
   raise + pass), plus a `professor_company_role` universe assertion.
2. Pre-existing suites green: `tests/canonical_v2/test_knowledge_build_isolated.py`,
   `test_applicant_binding_relationship_seeds.py`,
   `test_relationship_projection_contract.py`,
   `test_serving_pack_loader.py`, `test_patent_applicant_linking.py`.
3. Replay against the run15 copies (staged sources + sealed pack, read-only,
   copied to scratch): pre-fix vs post-fix `patent_has_applicant` count with the
   difference list classified. No write to `/var/tmp/mirothinker-data-v2/`.

## Out of scope

- Running a real rebuild (run16 owns that).
- Changing the serving-period authority to read the relationship store.
- `patent_has_inventor` / `paper_has_author` / `paper_references_paper`
  (0 edges in run15) — different root cause: run15 ships
  `internal_reference_projection_result.person_projections = 0`, so there is no
  person graph to project from. Reported as a sibling finding, not fixed here.
