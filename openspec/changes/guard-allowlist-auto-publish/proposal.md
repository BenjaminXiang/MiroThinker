# Proposal: guard-allowlist-auto-publish

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.9.

## Why

Gate 4 closed the refresh loop (weekly job + hot-swap), but publishing was manual:
without it the job produces an artefact nobody reads. Turning it on unattended
needs two invariants, otherwise one bad refresh silently removes professor
evidence from every answer (the overlay hot-reloads).

## What Changes

1. The weekly job publishes the allowlist automatically (`--publish-allowlist`).
2. Before publishing it refuses when the new allowlist has fewer than 300 records
   or shrinks by more than 10% against the live one (exit 4, no write).
3. The previous generation is kept as `<allowlist>.prev` for rollback.

## Impact

- Behaviour can change weekly without a human; the guard bounds the blast radius
  to "roughly the same size".
- Rollback: copy `.prev` back (the overlay reloads it on the next claim).
