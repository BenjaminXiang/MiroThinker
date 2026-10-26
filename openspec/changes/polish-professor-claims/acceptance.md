# Acceptance: polish-professor-claims

| # | Criterion | Evidence |
|---|---|---|
| A1 | Overlay count says "local" | dry run: 白冠华 → `本地收录论文：4 篇`; unit test |
| A2 | Pack count keeps the old label | dry run: 曲强 → `论文数：5`; unit test |
| A3 | Repetition collapses | 白冠华's template sentence appears once; 4 unit tests |
| A4 | No regression on the golden set | 27-turn gate against the customer site |
| A5 | Reversible | restart with the previous two files from `backups/overlay-20261027/` |

Status: **accepted** (2026-10-26 24:05 CST). Live verification: 白冠华 renders
`本地收录论文：4 篇` with the template sentence once; 曲强 keeps `论文数：5`.
27-turn gate: **pass**, required 77→76 (one fluctuation, q25 4→3), product 26→26,
0 forbidden / 0 refusal / 0 errors.
