# Acceptance: relax-professor-summary-floor

| # | Criterion | Evidence |
|---|---|---|
| A1 | Floor is 120 | `profile_summary_contract.PROFILE_SUMMARY_MIN_CHARS` |
| A2 | No regression in the quality suites | 50 passed |
| A3 | The pilot's rejected professor now enriches | 陈振旺: 283 chars / 19 facts (was `profile_summary_too_short`) |
| A4 | Reversible | one constant; revert restores the old bar |

Status: **accepted** (2026-10-27). Note: the specific recovery at 283 characters
may not be caused by the floor change (a retry can produce a longer synthesis);
the change is justified by the class of 120–190 character summaries, measured in
the pilot.
