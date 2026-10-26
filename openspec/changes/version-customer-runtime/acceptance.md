# Acceptance: version-customer-runtime

| # | Criterion | Evidence |
|---|---|---|
| A1 | The deployed `apps/` tree is reproducible from one git ref | `hotfix/customer-20261026` @ `82047a7b` (33 modified + 4 added files); `prod-snapshot/manifest.sha256` (37 entries); `run.sh` `sha256 fd17c4e6…`; 49 residue files listed in `excluded-patch-residue.txt` |
| A2 | Drift is machine-detectable | `check_runtime_drift.py --ref hotfix/customer-20261026 --remote root@100.64.0.96:…` → `no drift`, 697 files compared, exit 0; 7 unit tests; synthetic-tree test proves non-zero exit on drift |
| A3 | Cache gate keeps local-grounded answers and rejects web-only ones | `test_validate_candidate_accepts_mixed_local_and_web_citations` (≈1.7k-char mixed envelope accepted), `…_rejects_web_citation`, `…_rejects_marker_and_allows_coverage_tail`; the pre-adoption tests fail 4/9 against the adopted gate |
| A4 | Topic-professor queries never resolve a company anchor | `test_topic_professor_query_does_not_anchor_a_company` + `…_does_not_swallow_named_relations`; disabling the guard reproduces `浙江灵巧智能科技有限公司` |
| A5 | Generic appellations never anchor | `test_entity_name_forms_generic_names.py` (4 tests); emptying the blocklist makes `教授` indexable |
| A6 | Dev debug artefacts are archived, not silently accumulating | 26 MB / 1,683 files archived to `/tmp/turn-debug-archive/`; 75 untracked lane-watch files removed; 1,608 tracked files kept; the writer stays on until the 1.6 restart (`CANONICAL_V2_TURN_DEBUG_DIR` recorded) |
| A7 | The dev line is identified honestly | plan §1 + log round 2 record the corrected cause (same launcher, process frozen since 2026-10-16); restart blockers (managed secrets, manual-recall data) recorded — **restart itself still open (task 1.6)** |
| A8 | The snapshot tree is coherent, not only byte-identical | `import backend.main` → FastAPI app with 72 routes |

Evidence: `.agents/runs/version-customer-runtime/verification.md`.

Status: candidate — tasks 1.1–1.5 and 1.7 done; 1.6 open (blocked on a config/data-copy
decision).

Test totals this slice: 48 admin-console tests (4 modules) + 4 entity-form tests + 9
alias-foothold sibling tests, all green. Full admin-console suite: 1607 passed / 31 failed
/ 105 errors — none in touched files; 105 errors are the conftest "refusing to run against
a real-data database" guard (needs `DATABASE_URL_TEST`), and three sampled failures are
deployed-code vs branch-test contract mismatches, i.e. exactly the divergence this change
exists to expose.
