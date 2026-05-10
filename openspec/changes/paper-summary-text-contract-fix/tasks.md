# Tasks: paper-summary-text-contract-fix

- [ ] T1: Edit `apps/admin-console/backend/api/domains.py:753` —
  change `"summary_text": row.get("abstract_clean")` to
  `"summary_text": row.get("summary_zh")`
- [ ] T2: Update
  `apps/admin-console/tests/test_data_api_paper_v011.py::test_domains_paper_detail_returns_summary_zh_column_value`
  to assert `summary_text == summary_zh value` (was `abstract_clean`)
- [ ] T3: Update
  `apps/admin-console/tests/test_data_api_paper_v011.py::test_domains_paper_detail_returns_none_for_missing_summary_zh`
  to assert `summary_text is None` when `summary_zh is None`
  (previously fell back to abstract_clean)
- [ ] T4: Run `uv run pytest apps/admin-console/tests/test_data_api_paper_v011.py`
  — expect all paper tests pass
- [ ] T5: Run full `uv run pytest` in `apps/admin-console/` to confirm
  no other tests regressed (admin-console may have ~100+ tests; this
  catches incidental dependents on the old alias)
- [ ] T6: `openspec validate paper-summary-text-contract-fix` exits 0
- [ ] T7: Archive via `openspec archive --skip-specs --yes
  paper-summary-text-contract-fix`; update change-ledger.md
- [ ] T8: Resolve debt
  `paper-summary-text-contract-drift-001` in `openspec/debt-register.md`
  (move from Open to Resolved with back-reference to this change)
