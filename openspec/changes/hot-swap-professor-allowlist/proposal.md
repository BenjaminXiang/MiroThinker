# Proposal: hot-swap-professor-allowlist

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.8.

## Why

The weekly refresh publishes a new allowlist, but the serving process loaded the
file once and kept it forever: picking up a refresh required a restart, which
turns an unattended job into a manual chore and a 10-minute outage.

## What Changes

1. `active_overlay()` caches on `(path, mtime_ns, size)` and reloads when the file
   changes (under a lock); an unreadable file still means "disabled".
2. The refresh wrapper publishes with `os.replace`, so a reader never sees a
   half-written allowlist. Publishing the allowlist stays opt-in
   (`--publish-allowlist`), because a refresh should not silently change answers.

## Impact

- Swap takes effect on the next claim instead of the next restart.
- No pack, schema or API change; disabling is still `unset` the variable.

## Out of scope

- Automatically enabling `--publish-allowlist` in cron (a policy decision).
