# Tasks: data-cleaning-batch2

- [x] 1. Read the D0-b inputs (`openspec/changes/data-cleaning-batch1/`,
      assessment D0-6..D0-10) and measure each item on the run15 pack.
- [x] 2. Write the verification contract
      (`.agents/runs/data-cleaning-batch1/verification-contract-batch2.md`).
- [x] 3. Venue rules: grouping key, canonicalisation, deterministic winner,
      map computed once per build; applied at the projection cleaning point.
- [x] 4. Edge de-duplication in the link assembly (smallest id wins) plus a
      fail-closed uniqueness assertion in the relationship projection.
- [x] 5. Geography repair: separator strip, prefecture-city suffix, province
      recovery from the company address; unmappable values counted.
- [x] 6. Applicant audit + two gates; decision (keep + explicit unbound marker)
      recorded in design.md §4.
- [x] 7. Dead-declaration metric in the publication audit + the 49-row decision
      table (design.md §5).
- [x] 8. Build quality report written by the isolated materializer (audit +
      quarantine re-derived from source selections).
- [x] 9. Tests: 26 new batch-2 tests; batch-1 expectations updated where the
      batch-2 rules supersede them.
- [x] 10. Replay counter (`count_cleaning_batch2.py`) over the sealed pack,
      emitting `out2/counts-batch2.json`.
- [x] 11. Related existing suites re-run; failures classified against the base
      commit.
- [x] 12. Human log appended + `docs/plans/index.md` line + ledger entry.

## Follow-ups (not this slice)

- [ ] run16 rebuild: the venue merge, edge dedup, applicant gates and the
      quality report all take effect there; re-run the counter on the new pack.
- [ ] Catalog revision to actually retire the 22 dead declarations (decision
      table in design.md §5) - a deliberate release-identity change.
- [ ] Persist the dropped duplicate-link ids into the build quality report.
- [ ] D1: bind the 4,951 unbound applicant names to companies; fill the 27
      keep-with-fill-path fields; the 1,595 companies with no geography.
