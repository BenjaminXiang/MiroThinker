# Acceptance: patent-company-relationship-reprojection (C1)

## Acceptance criteria

| # | criterion | evidence source | status |
|---|---|---|---|
| AC1 | Every document-layer applicant binding pair whose both endpoints are admitted objects produces a `patent_has_applicant` seed | unit test R1 + replay count comparison | pending |
| AC2 | A binding that cannot be seeded fails the build unless it is classified as `unindexed` (target company has no admitted object) | unit test R2 (raise + pass) | pending |
| AC3 | One machine-readable `PATENT_COMPANY_BINDING_LEDGER` line per build, carrying document/relationship counts by seeding lane and `unexplained_missing` | build-time print at the same site as `APPLICANT_BINDING_LEDGER` | pending |
| AC4 | `professor_company_role` uses the same universe (no lane reads a released-only universe) | unit test R3 | pending |
| AC5 | No service-period behaviour change: no serving/pack-loader/index-projection file in the diff; serving + relationship contract suites green | `git diff --stat`, test runs | pending |
| AC6 | Expected run16 outcome is stated and testable: edges `123 → 7,611` (one per distinct document pair), companies `49 → 960`, `unexplained_missing = 0` | run16 `PATENT_COMPANY_BINDING_LEDGER` line | pending (run16) |

## Acceptance evidence required at Candidate

1. Layered verification report in `.agents/runs/c1-relationship-reprojection/verification.md`:
   ① new tests written (count, cluster, fixture provenance),
   ② pre-existing suites (count, all-pass),
   ③ replay evidence (pre/post counts on the run15 copy, difference list).
2. Replay command + raw output preserved next to the report.
3. Statement that the serving line was not restarted/touched and
   `/var/tmp/mirothinker-data-v2/` had zero writes.

## Not accepted as evidence

- "The projection admits everything" (already true on the baseline).
- A count-only comparison without the classified difference list.
- Any change to the serving-period direct scan.
