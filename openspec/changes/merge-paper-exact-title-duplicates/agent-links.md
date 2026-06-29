# Agent Links — merge-paper-exact-title-duplicates

> Per CLAUDE.md §14.4.

## Roles
- **Claude (designer/reviewer):** the first-principles tiered strategy + this
  OpenSpec change; the operational dry-run/apply (localhost DB) + pilot review.
- **Codex (implementer):** the dedup script + shared helper + unit tests
  (sandbox-safe; no network).

## Related changes
- `duplicate-paper-review-workflow` (proposed, Tier 3) — the review-gated
  complement for divergent-author groups.
- `recover-paper-shells-via-realtime-resolution` (landed) — Stage A already
  merged identifier-bearing shells; this change handles remaining exact-title
  non-shell duplicates.

## Verification boundary (§14.7)
- New-code surface deterministic (canonical pick + link-migration order → unit
  tests). Operational merge verified by pilot adversarial title-match (the
  false-merge guard) + bounded apply + retrieval spot-check.

## Dispatch
- Codex: tasks 1.x (script + helper + tests).
- Claude: tasks 2.x–3.x (pilot → full apply → retrieval spot-check) + review.
