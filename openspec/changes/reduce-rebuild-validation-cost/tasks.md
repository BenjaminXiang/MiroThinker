# Tasks: reduce-rebuild-validation-cost

## Step 1 — trigger / validator hot paths (do first, biggest win)

- [ ] 1.1 Sibling sweep: enumerate every per-row deferred constraint trigger and
      every per-entity full-scan validator on the build path; record N and the
      cost model per site (no single-site fix).
- [ ] 1.2 Identity validators: index assertions once (`assertions_by_source`,
      `(source_id, field_path)`); error messages and fail-closed semantics stay
      byte-identical.
- [ ] 1.3 `validate_field_human_review_binding`: release-level guard + the
      expression/partial index + statement-level or batched trigger; prove the
      guard is a no-op when reviews exist.
- [ ] 1.4 Same repair for `domain_inclusion_decision_assertion` (≈418k) and
      `relationship_decision_assertion` (≈21.5k).
- [ ] 1.5 Regression tests: inserting an assertion onto a reviewed field still
      raises ERRCODE 23514; the ancestor-release and per-field alignment branches
      still reject. RED before the change, GREEN after.
- [ ] 1.6 Rebuild measurement: decision-batch `COMMIT` and the identity-resolution
      phase drop from hours to minutes; per-phase before/after recorded.

## Step 2 — envelope / authority contract

- [ ] 2.1 Decide the split shape (manifest + content-addressed parts + one-time
      verification token) and the migration path for already-sealed envelopes.
- [ ] 2.2 Implement in the runner sink + readback and in
      `s12c/build_serving_pack.py`; document what `envelope_sha256` now means.
- [ ] 2.3 Equivalence evidence: identical inputs ⇒ byte-comparable envelope (or
      equal projection digests + row counts); pack dogfood still passes.
- [ ] 2.4 Measure `phase=envelope_validate` (today 2071s) and the runner readback
      after the change.
