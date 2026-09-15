# Acceptance: data-cleaning-batch1

Baseline pack: `serving-pack-run15-sealed` (`lookup.sqlite3`, 668,884,992 bytes),
copied read-only to `/tmp/dq-batch1-scratch/lookup.sqlite3`.  Every number below
comes from `.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py`
(`out/counts.json`, `out/quarantine.jsonl`, `out/kept-legit-prose.jsonl`).

| # | Criterion | Target | Measured | Status |
|---|---|---|---|---|
| AC1 | Whole-value `未找到` published | 0 (baseline 1,817) | 1,817 -> 0 | pass |
| AC2 | `未找到` prefix values published | 0 (baseline 2) | 2 -> 0 | pass |
| AC3 | Glue-damaged values published | 0 of 189 glue runs | 177 withheld -> 0 published | pass |
| AC4 | Glue values kept as legitimate prose | enumerated, not silently dropped | 9 kept, listed in `kept-legit-prose.jsonl` | pass |
| AC5 | Placeholder-family values published (company+professor) | 0 (baseline 15,976 by full-nested walk / 15,969 by the sealer's field scope) | 15,976 -> 0 | pass |
| AC6 | Company geography province-only | 0 of 4,887 derivable | 4,887 -> 2 (both have no address; kept as-is) | pass (with 2 documented exceptions) |
| AC7 | Company geography city-level | >= baseline 601 (554 `广东省-深圳市` + 47 others) | 601 -> 5,486 | pass |
| AC8 | Research-direction junk published | 0 (796 identified: 154 layout / 126 short / 65 dated / 333 sentence / 118 truncated) | 796 -> 0 | pass |
| AC9 | Quarantined values traceable | rule + verbatim value + source `reference_id` | `quarantine.jsonl`, 1,060 records | pass |
| AC10 | Build gate fails closed on dirty output | gate tests | `test_gate_refuses_*` (2 tests) + wiring test | pass |
| AC11 | New tests | all green | 53/53 pass | pass |
| AC12 | Existing related suites | no unexplained regressions | 5 pinned-expectation tests updated for the new behaviour; related suites green (see verification.md) | pass |
| AC13 | No production data touched | zero writes under `/var/tmp/mirothinker-data-v2/` | pack opened `mode=ro&immutable=1`; only a scratch copy was used | pass |
| AC14 | Effective from run16 | stated | cleaning runs at build time; run15 pack and 18188 untouched | pass |

## Reconciliation with the first assessment (2026-09-15)

| Assessment number | This batch | Note |
|---|---|---|
| whole-value `未找到` exact 1,817 | 1,817 | exact |
| whole-value `未找到` prefix 2 | 2 | exact |
| glued runs 189 | 189 (177 damage + 3 no-information + 9 legit prose) | exact split now explicit |
| geography province-only 4,887 | 4,887 | exact |
| geography `广东省-深圳市` 554 | 554 (inside a 601 city-level total; the assessment counted only the Shenzhen subset) | explained |
| research_directions entries 10,238 (1,969 professors) | 10,238 | exact |
| research-direction junk: nav >=140 / sentence 294 / truncated 121 / <=2 chars 126 | 154 / 333 / 118 / 126 | my marker/rule sets differ slightly; two extra rules (`dated_dump` 65) were added after verification rejected a length-based rule |
| placeholder family total 15,969 (company 3,097 + professor 12,872) | 15,976 over the full nested walk | +7 scanner scope: the audit walks every nested string (adds `paper.venue` 5 and patent's 2 glue values, which the sealer's field scope excluded) and counts the 3 no-information sentences as a placeholder family. The assessment's own per-field note and its recount table already differ by 23 on `technology_route_summary`, so the residual is a baseline bookkeeping artefact, not a data difference. |

## Not verified here

* run16 rebuild and its real gate run (needs the packing pipeline; out of slice).
* Retrieval-level effect (recall/TTFT) - this slice changes stored content only.
* The withheld glue values' reconstruction - deliberately not attempted.
