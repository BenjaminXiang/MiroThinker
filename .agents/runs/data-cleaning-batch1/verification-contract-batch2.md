# Verification contract: data-cleaning-batch2 (D0-b)

RED = measured on the run15 sealed pack (read-only;
`/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/`, lookup copy in
`/tmp/dq-batch1-scratch/lookup.sqlite3`).  GREEN = the same measurements re-run
through the new rules with
`.agents/runs/data-cleaning-batch1/count_cleaning_batch2.py`.

Contract is fixed before implementation (see `verification.md` §Honesty for the
git-ordering caveat).

## Contract

| ID | RED (before) | GREEN (after) | How verified |
|---|---|---|---|
| B1 | venue: 5,204 distinct labels; 129 rule-groups spanning 261 labels / 2,337 rows (assessment: 121 / 244 / 1,979 with a weaker key) | distinct labels <= 5,083; every group has one published label; unmapped labels counted | `out2/counts.json` venue section |
| B2 | venue: arXiv variants `arXiv (Cornell University)` 418 + `arXiv` 242 | one label (`arXiv`, 660 rows) | venue top-N + group table |
| B3 | edges: `professor_attributed_to_paper` 10,773 edges / 10,742 distinct (professor, paper) pairs = 31 duplicate pairs | 10,742 edges / 10,742 pairs, 0 duplicates; dropped link ids recorded | relationships.json recount + `relationship_projection` assertion test |
| B4 | applicants: 12,565 rows = 7,614 bound + 4,951 unbound-but-named; 0 nameless; 0 invalid bindings | rows kept (decision: keep + explicit unbound marker); counts published in the quality report; gate: nameless = 0 and invalid bindings = 0 | report section + gate tests |
| B5 | dirty geography: `广东省-珠海` 1, `苏州市` 1, `-开曼群岛` 1 | `广东省-珠海市`, `江苏省-苏州市`, `开曼群岛`; unmappable counted | geography section |
| B6 | dead declarations: 46 always-empty fields published on every document | decided set removed from the published surface, remainder kept with a documented fill path; published always-empty fields per domain = `46 - deleted` | design table + `out2/counts.json` |
| B7 | quarantined research directions / glue values only in the offline script output | build writes `publication-quality-report.json` next to the index artifacts (not in the pack, not in any content hash) containing the audit + quarantine records | file exists + content assertions (unit test) |
| B8 | - | a pack that would publish a duplicate edge, a nameless applicant row or an invalid binding cannot build | unit tests |

## Rule-level RED/GREEN pairs

Positive (must change) and negative (must survive) samples are verbatim run15
values in `.agents/runs/data-cleaning-batch1/fixtures/run15-samples.json`
(`batch2` section).

## Exit

* Counts reconciled against the assessment report; run16 is where the cleaning
  becomes effective (no production data touched).
* Evidence artifact: `out2/counts-batch2.json` from the **full** run
  (`--pack-dir <sealed pack>`, relationships pass included).  Do not commit a
  `--skip-relationships` run over it: that run now writes `{"skipped": true}`.
