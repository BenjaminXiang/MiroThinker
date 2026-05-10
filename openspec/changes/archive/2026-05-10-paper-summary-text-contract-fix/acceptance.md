# Acceptance: paper-summary-text-contract-fix

## Completion criteria

- [ ] `domains.py:753` returns `summary_zh` value, not `abstract_clean`
- [ ] When `summary_zh` is null, `summary_text` is null (not falling
  back to `abstract_clean`)
- [ ] `apps/admin-console/tests/test_data_api_paper_v011.py` 4 tests
  pass
- [ ] Full admin-console pytest suite passes (no regressions)
- [ ] `openspec validate paper-summary-text-contract-fix` exits 0
- [ ] `openspec/debt-register.md` `paper-summary-text-contract-drift-001`
  moved from Open to Resolved with back-reference to this change

## Non-goals not violated

- [ ] No Postgres schema change (no migration added)
- [ ] No PRD / Shared-Spec doc body edit
- [ ] No Milvus paper_chunks rebackfill

## Evidence

> Filled during execution.

- Fix commit ref:
- Test pass count for `test_data_api_paper_v011.py`:
- Full admin-console pytest summary:
- openspec validate output:
- debt-register status:
