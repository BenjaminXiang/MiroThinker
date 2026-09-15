# Tasks: data-cleaning-batch1

- [x] 1. Read the D0 inputs (`docs/plans/2026-09-15-data-quality-assessment.md`,
      `.agents/runs/data-quality-assessment/`, plan §8/§9) and extract the
      baseline numbers this batch must reconcile with.
- [x] 2. Write the verification contract (RED assertions = the before/after
      table) in `.agents/runs/data-cleaning-batch1/verification-contract.md`.
- [x] 3. Extract verbatim run15 fixtures for the four rules
      (`.agents/runs/data-cleaning-batch1/fixtures/run15-samples.json`).
- [x] 4. Implement `canonical_v2/publication_cleaning.py`: placeholder families
      (exact/prefix/no-information), glue damage vs legitimate prose, geography
      city derivation, research-direction junk rules, publication audit + gate.
- [x] 5. Wire the cleaning into `domain_projection.project_identity` (single
      choke point, source evidence untouched).
- [x] 6. Re-type the nine placeholder-bearing projection-model fields as
      optional; leave the hash-pinned domain catalog unchanged.
- [x] 7. Add the publication gate to `IndexProjectionBuilder.build` and delete
      the now-unreachable local professor-fallback guard in the index layer.
- [x] 8. Tests: positive/negative unit tests per rule, model-contract tests,
      audit/gate tests, wiring test (53 tests).
- [x] 9. Replay counter over a read-only copy of the run15 `lookup.sqlite3`
      (`.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py`), emit
      `quarantine.jsonl` / `kept-legit-prose.jsonl`, reconcile against the
      assessment numbers.
- [x] 10. Update the pinned-expectation tests that asserted the old behaviour
      (professor backfill projection carries the fallback; index-layer
      placeholder constant).
- [x] 11. Run the affected existing suites and record the result layer by layer.
- [x] 12. Human log (`docs/plans/2026-09-15-data-cleaning-batch1-log.md`) +
      `docs/plans/index.md` line + ledger entry.

## Follow-ups (not this slice)

- [ ] run16 rebuild to make the cleaning effective (no production data was
      touched here); re-run the counter on the new pack and expect an empty
      quarantine.
- [ ] D0-b: venue merge, relationship-edge dedup, empty-row cleanup, dead-field
      schema, dirty geography labels, companies with no geography.
- [ ] D1: LLM review of `quarantine.jsonl` (177 glue-damaged values) and of the
      retained no-information sentences; wire the side report into the build.
