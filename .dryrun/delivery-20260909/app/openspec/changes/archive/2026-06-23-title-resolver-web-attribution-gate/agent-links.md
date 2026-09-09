# Agent Links

- `.agents/runs/title-resolver-web-attribution-gate/verification-contract.md`
  will define the RED/GREEN evidence boundary before production-code edits: the
  RED artifact is unit tests for the gate predicate and the fail-closed path;
  GREEN is the gate passing accepted hits and returning `None` for rejected
  hits with the DB tiers unchanged.
- `.agents/runs/title-resolver-web-attribution-gate/verification.md` will record
  executed commands, the real-evidence dry-run reject rate, inspected rejected
  samples, skipped checks, and handoff state.
- `openspec/changes/title-resolver-web-attribution-gate/tasks.md` is the
  implementation checklist for apply mode.

## Related changes

- Portfolio 2026-06-22 Phase 3: W1a is the web-tier attribution gate. W2a
  (abstract-web-reader-fallback) is blocked on W1a because W2a consumes
  web-reader abstracts that must first pass attribution; without W1a, W2a would
  enrich wrong-paper web hits.
- Archived `wire-paper-identity-gate-rejection` (W0b): the identity gate that
  DEFERRED garbage titles to title-cleanup. W1a prevents the web-tier pollution
  at the source by gating acceptance, complementing W0b's deferred-rejection
  posture.

## Depends on

- None. W1a is self-contained in `title_resolver.py`; the page-only fallback
  consumer already exists in `homepage_ingest.py` and requires no change.
