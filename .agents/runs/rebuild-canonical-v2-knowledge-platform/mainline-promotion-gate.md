# Git Mainline Promotion Gate: Canonical V2

## Status

Completed at `2026-07-13T15:00:36Z`. Aggregate S6 was Accepted at
`2026-07-13T14:48:01Z`; local Git `main` fast-forwarded to the exact Accepted commit `f0e6224` after
the recorded exact-commit checks. This historical development-mainline move did not push, publish,
promote product data/indexes, or authorize a production-like cutover.

Post-gate implementation status: S11A and its S9J successor correction were Accepted at the
historical `65/80` OpenSpec ledger with receipts
`b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3` and
`ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`. S11B is also Accepted at the
same historical ledger with receipt `cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945`.
S11C subsequently accepted Tasks 11.1-11.5 atomically at `70/80`; receipt
`281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`. S12A is next. These
uncommitted checkpoints do not move Git
`main`, reopen this historical gate, or authorize Push, PR, product promotion, or Cutover.

## Goal

Fast-forward Git `main` to the accepted Canonical V2 integration checkpoint after the complete S6
typed domain, relationship, inclusion, and path-eligibility foundation is Accepted.

## Required predecessor state

- Task 5.7/S5G Accepted.
- Tasks 6.1-6.8 Accepted, including independent reviews and aggregate S6 evidence.
- S7-S12 may remain unstarted; this gate changes repository development authority, not product or
  database/index release state.

## Preflight

1. Record exact `main`, V2 integration, side-branch, worktree, and OpenSpec hashes.
2. Prove `main` is still the merge base and the operation is a pure fast-forward.
3. Require a clean V2 integration worktree and account for every untracked/staged file.
4. Inventory all `canonical-v2-*` and `codex/canonical-v2-*` branches; integrate, deduplicate, or
   explicitly abandon every unique patch.
5. Preserve the root worktree's unrelated dirty state; do not switch, reset, checkout, clean, stash,
   or overwrite it implicitly.
6. Re-run the aggregate S6 verification contract, strict OpenSpec, frozen-source checks, and focused
   secret/diff/scope checks on the exact intended target commit.

## Recorded preflight evidence

- Before the Aggregate S6 commit: `main=191ed9236575528bc6c6cf046afd7515108a09c7`, integration
  predecessor `9b300222338e24e8faac661cf7154ef7f7fb19b8`, merge base exactly `main`, divergence `0/149`.
- The root worktree is on `feat/professor-retrievability`, not `main`; its status hash is
  `466173c313705e582867ca2b5ad2edc5b9cbd257a6c33e8fe0fe893205028ff5`, tracked-diff hash is
  `c42579bfc747f9d9429d54ab53a406df9fd64026a77d056175c0be8f2f8331ce`, and cached diff is empty.
  The same hashes must remain after the ref move.
- `canonical-v2-s1-safety` has no missing patch. The S6c branch is superseded by the non-conflicting
  C2_0009 implementation and larger test matrix; all 9 S6d and all 5 S6f RED groups are present and
  strengthened on the integration line. The Task 6.1 preparation-only files explicitly defer now-
  accepted Task 5.5/5.6 policy and are abandoned untouched. Exact details are in
  `s6-aggregate-review.md`.
- Fresh aggregate evidence: focused pure S6 `54 passed`; no-external Canonical V2 `211 passed, 137
  skipped, 4 xfailed`; focused C2_0009/C2_0010 persistence `26 passed`; corrected complete real
  PostgreSQL `338 passed, 4 xfailed` plus fixed-name S4C `10 passed`.
- Cleanup/source evidence: no S6H/S4C disposable remains; the S6c base has zero user tables;
  `pgtest` is paused; original Milvus SHA-256 is
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.

The final execution resolves the target with `git rev-parse HEAD`, rechecks that `main` is its
strict ancestor and the integration worktree is clean, runs the exact-commit gates, then updates the
unattached local `refs/heads/main` only if its old object is still the recorded value. Completion is
proved by Git topology and unchanged root hashes; no post-move evidence commit is created because
`main` must end at the exact Aggregate S6 Accepted commit.

## Forbidden operations

- Merge commit, rebase, force update, reset, destructive checkout, worktree clean, automatic stash,
  push, PR, archive, database/index promotion, or production-like cutover.
- Treating uncommitted Task 6.3 work or expected RED-only branches as accepted promotion inputs.

## Done means

- All preflight evidence is recorded and current.
- Git `main` moves by fast-forward only to the exact aggregate-S6 Accepted commit.
- V2 becomes the repository development mainline for S7 onward.
- Root/user changes remain intact, no remote state changes, and no data/index state changes.

## Abort / rollback

Abort before moving the ref if any preflight condition is false. After a successful local
fast-forward, do not rewrite history automatically; if the checkpoint itself is later rejected,
follow the accepted revert/forward-fix policy and preserve audit history.
