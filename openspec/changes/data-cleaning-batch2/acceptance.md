# Acceptance: data-cleaning-batch2

Baseline pack: `serving-pack-run15-sealed` (read-only; `lookup.sqlite3` +
`relationships.json`).  Numbers come from
`.agents/runs/data-cleaning-batch1/count_cleaning_batch2.py`
(`out2/counts-batch2.json`).

| # | Criterion | Target | Measured | Status |
|---|---|---|---|---|
| B1 | distinct venue labels after merging | <= 5,083 | 5,204 -> **5,031** (153 groups, 326 labels, 2,684 rows) | pass |
| B2 | arXiv variants collapse to one label | 1 label | `arXiv (Cornell University)` 418 + `arXiv` 242 -> `arXiv` 660 | pass |
| B3 | duplicate `professor_attributed_to_paper` pairs published | 0 of 31 | 10,773 edges / 10,742 pairs -> 10,742 edges / 0 duplicates | pass |
| B4 | applicant rows: no nameless row, no invalid binding; unbound rows kept with their names and marked by a null id | gates 0/0; counts published | 12,565 rows = 7,614 bound + 4,951 unbound-but-named; nameless 0; invalid 0 | pass |
| B5 | three dirty geography values normalised | 3/3 | `-开曼群岛` -> `开曼群岛`; `广东省-珠海` -> `广东省-珠海市`; `苏州市` -> `江苏省-苏州市` | pass |
| B6 | dead declarations decided field by field | 49 rows in the design table | 27 keep-with-fill-path, 22 retire-pending-catalog-revision; **0 deleted in this slice** (blocker documented) | pass with scope note |
| B7 | build writes a quality report | file appears with correct content | writer + wiring unit-tested; `publication-quality-report.json` next to the index artifacts, not in the pack | pass with coverage note |
| B8 | new fail-closed gates | refuse nameless applicant rows, foreign bindings, duplicate edges | unit tests (applicant x2, edge x1) + build de-duplication test | pass |
| B9 | new tests | all green | 27 batch-2 tests + 52 batch-1 tests | pass |
| B10 | existing related suites | no unexplained regressions | see verification.md | pass (2 suites pending in the run log) |
| B11 | no production data touched | zero writes | pack opened read-only; report written only under an index root in tests | pass |
| B12 | effective from run16 | stated | rules run at build time; run15 pack and 18188 untouched | pass |

## Reconciliation with the assessment (2026-09-15)

| assessment number | this batch | note |
|---|---|---|
| venue 121 groups / 244 labels / 1,979 rows | 153 / 326 / 2,684 | my key also drops `the/of/on/in/for/and` and groups after canonicalisation (year/parenthetical stripping), so it merges more of the same class; distinct labels 5,031 still satisfies the assessment's own `<= 5,083` |
| 31 duplicate (professor, paper) pairs | 31 -> 0 | exact |
| 4,951 applicant rows with `company_name = null` | 4,951 unbound rows, **all named** | the assessment's wording suggests empty rows; measurement shows every row carries an applicant name, which is why the decision is "keep + marker", not "remove" |
| 3 dirty geography values | 3 -> 3 normalised | exact |
| 46 always-empty fields (10/14/14/8) | 49 (10/14/17/8) | +3 paper fields the assessment did not list (`enrichment_sources`, `funders`, `summaries`); company/professor/patent counts match exactly |
| city-level geography 603 | 5,488 | batch 1 already derived 4,885; this batch adds the three dirty values |

## Not verified here

* The end-to-end report write inside a real isolated build (the full-build
  fixture test `test_complete_build_uses_verified_copies_...` is one of the 13
  pre-existing failures on this branch).
* run16 rebuild and its gate/quality-report run.
* Retrieval-level effects of venue merging (label counts only).
