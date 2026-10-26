# Acceptance: materialize-professor-paper-projection

| # | Criterion | Evidence |
|---|---|---|
| A1 | Overlay is invisible when not configured | `_semantic_text` without the env var renders no `论文数` / `代表作`; unit test `test_semantic_text_is_unchanged_without_overlay` |
| A2 | Pack values are never overwritten | unit test `test_apply_never_overwrites_pack_values` (pack 3 vs overlay 90 → 3) |
| A3 | Ambiguous identities are excluded | unit test `test_duplicate_name_records_are_ignored`; the real allowlist drops 3 of 536 |
| A4 | Allowlisted claims gain count and representative papers | unit test `test_semantic_text_adds_count_and_representative_papers`; dry run `overlay-preview.md` |
| A5 | Broken/missing overlay does not break answers | unit tests for missing file, invalid JSON, non-object payload |
| A6 | Pack files stay byte-identical | overlay is read-only; no write path in the module |
| A7 | Customer-site enablement is reversible | flip the environment variable; documented in tasks 1.6–1.7 |

Status: candidate for code (tasks 1.1–1.4 done); deployment tasks 1.5–1.6 open.
