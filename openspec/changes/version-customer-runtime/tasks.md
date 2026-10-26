# Tasks: version-customer-runtime

- [x] 1.1 Snapshot the deployed `apps/` tree and `run.sh` into branch
      `hotfix/customer-20261026` (new worktree), commit with a `sha256`
      manifest of every changed file; record the three-lineage delta in the
      commit body.
- [x] 1.2 Add `scripts/check_runtime_drift.py` (compare a local or `ssh`-hosted
      tree against a git ref by file hash; non-zero exit on drift) plus a unit
      test over two synthetic trees.
- [x] 1.3 Run the drift check against `100.64.0.96` and the new branch; record
      the (expected) zero-difference result.
- [x] 1.4 Add regression tests for the adopted behaviours: answer-cache
      envelope gate, manual-recall professor claim fields, topic-professor
      anchor guard, generic-person-name blocklist. Prove each fails when its
      adopted hunk is reverted.
- [x] 1.5 Archive the debug artefacts and remove the untracked ones; keep the
      1,608 tracked files (deleting them would only add a 1,683-file noise commit).
      Switching the writer off is folded into 1.6 because it needs a restart.
- [ ] 1.6 Restart the dev instance (`:18188`) on the versioned tree with the same
      launcher, current pack and prod-shaped env; compare four probes with the
      customer site. Blocked on managed secrets + manual-recall data parity
      (recorded in the log).
- [x] 1.7 Human doc (plan + log), ledger row, index entry, and this change's
      acceptance evidence.
