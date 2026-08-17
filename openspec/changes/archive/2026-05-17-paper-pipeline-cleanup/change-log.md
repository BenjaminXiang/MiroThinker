# Change Log: paper-pipeline-cleanup

## 2026-05-15 - Initial scope

- Expanded the ledger placeholder into a full OpenSpec change.
- Scoped cleanup to retiring active legacy discovery callers while
  preserving enrichment helpers.

## 2026-05-15 - Implementation evidence

- Removed active legacy discovery callers from `professor.paper_collector`,
  the old paper pipeline default backend, and the release E2E script.
- Replaced `paper.hybrid` active fallback logic with a retired
  compatibility wrapper that warns and raises before external discovery
  can run.
- Added a production-source guard test and recorded red/green evidence
  in `acceptance.md`.
