# Tasks: reduce-rebuild-validation-cost

Branch: `perf/rebuild-trigger-fix` (worktree `.worktrees/rebuild-trigger-fix`).
Evidence: `.agents/runs/reduce-rebuild-validation-cost/` (`verification.md`,
`measure-before-after.jsonl`, `explain-analyze-*.txt`, `sweep-run15.json`,
`pytest-head-revision.txt`, `python-scan-before-after.md`).
Human log: `docs/plans/2026-09-15-rebuild-trigger-fix-log.md`.

## Step 1 — trigger / validator hot paths (candidate: implemented + verified on a DB copy)

- [x] 1.1 Sibling sweep: enumerate every per-row deferred constraint trigger and
      every per-entity full-scan validator on the build path; record N and the
      cost model per site (no single-site fix).
      → `sweep-run15.json` (36 deferred row-level mounts / 20 tables) +
      per-family measured cost in `verification.md` §1; three families share the
      defect, four do not (recorded with numbers).
- [x] 1.2 Identity validators: index assertions once (`assertions_by_source`,
      `(source_id, field_path)`); error messages and fail-closed semantics stay
      byte-identical.
      → `canonical_identity_resolution.py` (`_index_assertions_by_source_and_field`,
      single-pass `assertion_ids_by_source`); 58 contract tests green; RED/GREEN
      iteration counts in `python-scan-before-after.md`.
- [x] 1.3 `validate_field_human_review_binding`: release-level guard + the
      expression/partial index; prove the guard is a no-op when reviews exist.
      → C2_0014: guard + `ix_knowledge_canonical_decision_human_review_case` /
      `_decision`; reviewed-field rejection re-verified at head
      (`pytest-head-revision.txt`). Statement-level granularity **not** taken —
      see design §"Granularity decision" (data + reasons).
- [x] 1.4 Same repair for `domain_inclusion_decision_assertion` (≈418k) and
      `relationship_decision_assertion` (≈21.5k).
      → relationship: same defect, same repair (2,086 µs/row → 26 µs/row).
      domain inclusion: measured 1.67 µs/row — already index-backed, **not** the
      same disease; no change made (finding recorded instead of a speculative fix).
- [x] 1.5 Regression tests: inserting an assertion onto a reviewed field still
      raises ERRCODE 23514; the ancestor-release and per-field alignment branches
      still reject. RED before the change, GREEN after.
      → `test_canonical_decision_postgres.py` (reviewed-release fixtures) re-run at
      migration head via the evidence plugin: 7/7 of the review-provenance tests
      pass, including the origin-evidence immutability and the late-edge race;
      plus the new Python iteration-count test (RED 5/33 iterations → GREEN 1).
- [ ] 1.6 Rebuild measurement: decision-batch `COMMIT` and the identity-resolution
      phase drop from hours to minutes; per-phase before/after recorded.
      → copy-DB projection only (846,986 × 28.7 µs ≈ 24 s vs measured 12 h 40 m).
      **run16 must record the real per-phase timings** — not done in this slice.

## Step 2 — envelope / authority contract (not started)

- [ ] 2.1 Decide the split shape (manifest + content-addressed parts + one-time
      verification token) and the migration path for already-sealed envelopes.
- [ ] 2.2 Implement in the runner sink + readback and in
      `s12c/build_serving_pack.py`; document what `envelope_sha256` now means.
- [ ] 2.3 Equivalence evidence: identical inputs ⇒ byte-comparable envelope (or
      equal projection digests + row counts); pack dogfood still passes.
- [ ] 2.4 Measure `phase=envelope_validate` (today 2071s) and the runner readback
      after the change.

## Follow-ups opened by step 1 (not in this slice)

- [ ] F1 `validate_identity_resolution_release` re-derives release-level identity
      topology per inserted row (14 mounts, ≈500k events; copy-DB probe 1.65 s/row,
      not proven faithful against run15's phase timestamps). Instrument in run16,
      then decide the granularity change. No index fixes this.
- [ ] F2 `validate_field_temporal_binding` (1.27 M events × 153 µs ⇒ ≈54 min) —
      index-backed parts are already cheap; candidate for the same granularity
      workstream.
