# Source Links: paper-summary-text-contract-fix

## Canonical sources

- `docs/Paper-Requirement-Review-2026-05-10.md §3.1 P3` — locked
  decision: fix admin API to align with contract
- `docs/Data-Agent-Shared-Spec.md §4.2.1` — defines `summary_text`
  contract: equals concatenation of `summary_zh` four-段 sections
  (per Paper Review P2 simplified to "= summary_zh content")
- `docs/Paper-Data-Agent-PRD.md §4.3` — same contract, paper-domain
  perspective
- `docs/audits/paper-requirement-code-reconciliation-2026-05-10.md` —
  identified the drift as `paper-summary-text-contract-drift-001`

## Code touched

- `apps/admin-console/backend/api/domains.py:753` — 1-line fix
- `apps/admin-console/tests/test_data_api_paper_v011.py` — 2 test
  updates

## Related debts

- `openspec/debt-register.md` entry
  `paper-summary-text-contract-drift-001` → moves to Resolved on
  archive

## Code paths NOT touched

- `apps/miroflow-agent/src/data_agents/paper/release.py` — already
  correctly assigns `PaperRecord.summary_text = summary_zh` at
  release boundary
- `apps/miroflow-agent/alembic/versions/V018_add_paper_summary_zh.py`
  — schema unchanged
- Milvus `paper_chunks` collection — embedding pipeline reads from
  `PaperRecord.summary_text` (which equals `summary_zh`); no
  rebackfill needed
