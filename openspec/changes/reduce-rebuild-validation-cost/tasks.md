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
      single-pass `assertion_ids_by_source`, and the same-shape per-verdict scans in
      `validate_identity_resolution_result`); 60 contract tests green; RED/GREEN
      iteration counts and a 1.17×/1.53×/1.95× time benchmark in
      `python-scan-before-after.md` / `bench-identity-validation.txt`.
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
- [x] 1.7 Merge-integration guard: the C2_0014 migration landed without moving
      `_EXPECTED_ALEMBIC_REVISION`, so the run16 launcher (`alembic upgrade head`
      then `validate_fresh_targets` → `_assert_fresh_database`, exact equality)
      would have aborted the build. Constant bumped to C2_0014 and pinned to the
      migration head by a new test (data-line merge commit `10b646ac`).
      → `tests/canonical_v2/test_canonical_revision.py`
      (`test_build_expected_revision_matches_the_migration_head`, RED before /
      GREEN after; file 8 passed); verification.md §9.

- [x] 1.8 Launch-gate coupling: C2_0014 also invalidates the **frozen live-schema
      catalog expectations** (`_EXPECTED_LIVE_SCHEMA_CATALOG_COUNTS.index`
      168 → 174, and `_EXPECTED_LIVE_SCHEMA_CATALOG_SHA256`), which
      `_assert_fresh_database` compares against a freshly migrated candidate
      database — found when the first run16 launch aborted in preflight. Both
      values recomputed and proved stable across **two independently migrated
      scratch databases** (`8a738964…`); updated in the data-line commit that
      relaunched run16. Lesson: every migration must move all three frozen
      expectations (revision constant, catalog counts, catalog sha256).

## Step 2 — envelope / authority contract (not started)

- [ ] 2.1 Decide the split shape (manifest + content-addressed parts + one-time
      verification token) and the migration path for already-sealed envelopes.
- [ ] 2.2 Implement in the runner sink + readback and in
      `s12c/build_serving_pack.py`; document what `envelope_sha256` now means.
- [ ] 2.3 Equivalence evidence: identical inputs ⇒ byte-comparable envelope (or
      equal projection digests + row counts); pack dogfood still passes.
- [ ] 2.4 Measure `phase=envelope_validate` (today 2071s) and the runner readback
      after the change.

## Step 2b — the read side: read the receipt, do not recompute (slice B, round 20)

Boot-cost attribution (docs/plans/2026-09-20-boot-cost-attribution.md) measured 71%
of a 690 s boot as pydantic dump + JSON encode + sha256, and the reader audit
(docs/plans/2026-09-20-boot-hash-reader-audit.md) showed the same pair of hashes
recomputed four times with only the comparison itself as a reader, while the
handoff already carries `authority.manifest.*` (runner:1023/1026).

- [x] 2b.1 Equivalence, measured: a probe opened the real sealed pack and proved
      every value slice B stops computing byte-equal to its manifest receipt —
      including the dump WITHOUT `exclude_unset` that the planner and the receiver
      used, which is not the expression the loader's own check verifies.
      → 8/8 rows EQUAL (probe + output in `.agents/runs/reduce-rebuild-validation-cost/`).
- [x] 2b.2 `create_serving_pack_query_planner` and `_compose_pack_consumer_runtime`
      read `authority.manifest.index_projection_request_sha256`.
      → the receipt lives on `ServingPackAuthority.manifest` (`ServingPackManifest`);
      `bundle.manifest` is a `BuildManifest` and has no such field — caught by
      `test_serving_pack_loader.py` on the first attempt.
- [x] 2b.3 `create_serving_pack_knowledge_read` reads
      `authority.manifest.relationship_request_sha256`.
- [x] 2b.4 The checks that make the receipts trustworthy stay untouched: per-file
      hashes plus the two "reproduce its recorded hash" comparisons at
      `serving_pack_loader.py:921/:1002`.
- [x] 2b.5 Contract tests: `test_serving_pack_loader` + `test_knowledge_read_isolated`
      + `test_knowledge_serving_isolated` → 357 passed, 1 failed, the failure being
      this deployment worktree's own `config/managed/settings.json` pinning
      `chat_llm_profile` (reproduced with the change stashed).
- [x] 2b.6 Boot measurement, same protocol before/after (scratch 18199, same argv,
      isolated state dirs, py-spy 25 Hz): duration start→first 200 and per-site
      sample shares.
      → before 610 s (watcher) / 706.9 s of samples; after: see verification.md §2b.

## Step 2a — the read side: the seal names its reader (slice A, round 21)

Boot re-derived two request hashes to prove the reconstruction reproduces what the
seal recorded: 137 s of a 440 s boot, and only meaningful when the reading code may
differ from the sealing code. So the pack now records which reader sealed it.

- [x] 2a.1 Manifest field `reader_contract_sha256` (optional; every existing pack
      parses as `None` = "unknown reader").
- [x] 2a.2 The identity is **derived, not hand-maintained**:
      `reader_contract_digest()` folds the whole `canonical_v2` package plus the
      interpreter and pydantic versions, ~6 ms for 55 files / 8.8 MB. Any edit that
      can change a dump — including a pydantic upgrade — invalidates the receipt.
- [x] 2a.3 The skip needs all three: the mount receipt binds this manifest, the
      pack names a reader, and that reader is this code. `verify_reconstruction=True`
      (the seal's own dogfood open) refuses unconditionally, because the seal is the
      earliest layer and must prove what it is about to record a digest for.
- [x] 2a.4 When the replay is skipped, relationships.json is hashed instead
      (~14 s against the ~137 s it displaces). The receipt path previously hashed no
      file at all and relied on the reconstruction to vouch for this one, so the fast
      path becomes stronger than before rather than weaker.
- [x] 2a.5 The seal writes the digest (`s12c/build_serving_pack.py`) and keeps
      proving its own reconstruction.
- [x] 2a.6 Tests: the rule table; a second boot that re-derives exactly two fewer
      times; a receipt path that still refuses a tampered relationships.json; the
      pre-existing tamper test now exercises the "unbound manifest" arm.
      → `test_serving_pack_loader.py` 31 passed.
- [ ] 2a.7 Measure on a pack that carries the digest (the next seal): expect
      `open_serving_pack_authority` to drop from ~286 s to ~150 s on the live line.
      Today's pack records nothing, and the live boot is unchanged (291 s in-process
      against 295 s before; live restart measured in the round-21 log).

## Step 2c — the object grain: stop re-deriving the projection graph's hashes (slice C, round 22)

Instrumented count of self-hashing validator calls during one boot: **401,449**,
every one re-checking a value the sealed pack already carries (PaperAuthor 308k,
PaperProjection 48k, Company 14k, PatentApplicant 12.5k, Patent 11.5k, Professor 4k).

- [x] 2c.1 The loader parses the pack's projection graph with
      `allow_unbound_projection_hash` — an existing validation context the build
      path already uses — because it has vouched for those bytes by the time it
      returns (relationships.json hashed, or the reconstruction reproduced the
      request hashes that cover the graph; either mismatch raises).
- [x] 2c.2 Covered 180k of the 401k; measured 450 s → 421 s on a clean scratch boot,
      reproduced instrumented and uninstrumented.
- [x] 2c.3 The three suites stay at 360 passed / 1 failed (this worktree's own
      `config/managed/settings.json` pinning `chat_llm_profile`); every tamper test
      in `test_serving_pack_loader.py` still green.
- [ ] 2c.4 **C2, located but not done**: the remaining ~221k validations come from
      `knowledge_read_isolated._validated_public_projection` (:8399) re-validating
      projections out of the lookup store. That means vouching for `lookup.sqlite3`
      (855 MB; today only the receipt's size/first-and-last-block fingerprint), which
      is a separate decision — named in the comment, not claimed by 2c.

## Follow-ups opened by step 1 (not in this slice)

- [ ] F1 `validate_identity_resolution_release` re-derives release-level identity
      topology per inserted row (14 mounts, ≈500k events; copy-DB probe 1.65 s/row,
      not proven faithful against run15's phase timestamps). Instrument in run16,
      then decide the granularity change. No index fixes this.
- [ ] F2 `validate_field_temporal_binding` (1.27 M events × 153 µs ⇒ ≈54 min) —
      index-backed parts are already cheap; candidate for the same granularity
      workstream.
