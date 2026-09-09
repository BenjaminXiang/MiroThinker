# Agent Links — paper-implausible-title-cleanup

- Depends on: `wire-paper-identity-gate-rejection` (W0b) — introduces the
  `paper-identity-status` capability, the `rejected` status, the Milvus exclusion, and
  `identity_status_writer.apply_identity_status_rejection` / `restore_identity_status`
  reused here. W0b should archive before (or alongside) this change.
- Related: portfolio `docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md`
  Phase 5 / W1b (`homepage-parser-boundary-guards`) — the PREVENTION complement (stops
  new garbage at ingest); this change is the REMEDIATION of existing garbage.
- Run workspace: `.agents/runs/paper-implausible-title-cleanup/` (verification-contract,
  eligibility-baseline, dry-run/apply artifacts — to be created in task 1.1/1.2/6.x).
- Surfaced from: user report 2026-06-22 (garbage titles on `/paper`, e.g.
  "Co-supervised PhD student", "011 (IF: 26.8"); connected to the W0b dry-run
  `implausible_title` `no_change` population.
