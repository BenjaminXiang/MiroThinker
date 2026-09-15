# Tasks: patent-company-relationship-reprojection (C1)

Status legend: `[ ]` pending, `[x]` done.

## T1 — diagnosis

- [x] Read run15 `relationships.json`: `patent_has_applicant` `candidates=123`,
      `admitted=123`, `rejected=0` (projection is not the filter).
- [x] Read run15 `typed_relationship_assertions=124` + the `:7127` completeness
      guard ⇒ seed stage produced 124 seeds.
- [x] Classify the 123 edges by seeding lane: 122 `resolved_binding`, 1
      `core_facts.company_ids[0]`.
- [x] Locate the universe filter: `rows_by_object` from `payload["id"]`
      (`knowledge_build_isolated.py:6485-6489`) vs raw supplemental payloads
      (`patent_id` / `company_name`) and the synthesized rows in `row_by_object`
      (`:4938`, `:3816`, `:5609`).
- [x] Quantify on run15 data: 122 == pairs whose both endpoints are released
      objects (see `design.md` §1.2 table).
- [x] Enumerate edge consumers (design.md §1.3).
- [x] Sibling sweep: `professor_company_role` same cause; `patent_has_inventor` /
      `paper_has_author` different cause (`person_projections = 0`).

## T2 — repair

- [x] Pass `row_by_object` from `_map_public_authority` → `_logical_graph` →
      `_relationship_authority`.
- [x] `_typed_relationship_seeds(object_rows_by_id=…, supplemental_rows=…)`: object
      universe from the mapped admitted objects; raw rows kept for the
      `professor_company_role` source-purpose lane.
- [x] Reconciliation helper + `PATENT_COMPANY_BINDING_LEDGER` line.
- [x] `INVARIANT-1` fail-closed check for unseeded document bindings.
- [x] Update `patent_applicant_linking.py` module docstring (release-only
      universe claim).
- [x] Update existing call sites/tests for the new signature.

## T3 — verification

- [x] New unit tests (R1/R2/R3 per `verification-contract.md`).
- [x] Replay script over run15 copies: pre-fix vs post-fix counts, classified
      difference list.
- [ ] Existing canonical_v2 suites green.
- [ ] `verification.md` with layered evidence (new tests / pre-existing suites /
      replay).
- [ ] No writes to `/var/tmp/mirothinker-data-v2/` (proof: script reads only;
      scratch under `/tmp/c1-relationship-scratch/`).

## T4 — docs

- [x] `docs/plans/2026-09-15-c1-relationship-log.md` (Chinese, human log).
- [x] `docs/plans/index.md` one-line entry.
- [x] `openspec/change-ledger.md` row.

## Deferred (not this slice)

- [ ] O1 run16 re-measure of the three counts (`patent_has_applicant` edges,
      companies, `unexplained_missing = 0`).
- [ ] O2 `_ApplicantBindingMergeStats.patents_bound` counter semantics.
- [ ] O1-owner: `person_projections` (patent_has_inventor / paper_has_author)
      separate change.
