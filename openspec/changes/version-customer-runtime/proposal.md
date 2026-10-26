# Proposal: version-customer-runtime

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md`.

## Why

The customer runtime (`100.64.0.96:/root/deploy/fullstack-v2/code`) is not a git
checkout. Between 2026-10-21 and 2026-10-26 it received **31 changed Python
files** plus a rewritten `run.sh`. Comparing those files against every local
branch shows the deployed tree is a **union of at least three lineages**
(`switch/embedding-model-to-qwen37-flash` for serving/chat, the Oct-23 snapshot
of `codex/canonical-v2-s12a-ready` for Excel upload / seeds / jobs, and the
October hot patches made only on the server):

- 9 files byte-identical to the serving branch,
- 18 files different from it,
- 4 files absent from it entirely, present only in the Oct-23 snapshot branch.

The local instance on `:18188` does not mitigate this either, though not for the
reason it first appears: it runs the **same** launcher as the customer site
(`serve_s12e_port.py` → `complete_candidate_runner` → `import backend.main`),
but its process started on 2026-10-16, so Python froze that tree's imports at
start. It serves the 2026-10-16 code and environment — no answer cache, no
exact-name resolver or patent counter attached, the older SSE envelope — and
therefore cannot validate any behaviour changed after that date.

Consequence: the newest behaviour (answer cache gates, professor claim
rendering, topic-professor guard, generic-name blocklist, local patent count
path) exists **only** as bytes on one customer machine. Any re-seal, re-deploy
or rebuild silently reverts it, and no test can detect the regression.

## What Changes

1. **Versioned snapshot.** Create branch `hotfix/customer-20261026` whose
   `apps/` tree is a byte-faithful copy of the customer runtime, committed with
   a `sha256` manifest of every file and a snapshot of `run.sh`.
2. **Adopted-behaviour tests.** Add focused regression tests for the four
   behaviours that were hot-patched without tests: answer-cache envelope
   validation, manual-recall professor claim fields, the topic-professor anchor
   guard, and the generic-person-name blocklist.
3. **Drift detection.** Add `scripts/check_runtime_drift.py`: compare a
   deployed tree (local copy or `ssh` host) against a git ref by file hash and
   exit non-zero on any difference. This replaces "remember to sync" with a
   machine check that can gate every future deploy.
4. **Debug surface off.** Stop writing turn-debug JSON on the dev runtime and
   remove the accumulated artefacts (1,683 files / 26 MB in
   `.agents/runs/close-workbook-gaps/turn-debug/`); the customer runtime flag
   is recorded for the next deployment window rather than flipped mid-flight.
5. **Dev line tells the truth.** Record that `:18188` serves a process frozen at
   its 2026-10-16 import, and restart it on the versioned tree with the same
   launcher, so "verified on dev" means something. Changing the launcher or the
   pack is explicitly out of scope here.

## Impact

- Customer site: **no file is changed** by this proposal; the snapshot is read
  only.
- Local: new branch + worktree, one new script, tests, debug artefacts removed.
- No public API, schema, retrieval or answer behaviour changes. The adopted
  behaviours are already live and are now covered by versioned tests instead of
  memory.

## Out of scope

- Merging the three lineages into one branch (a real convergence project).
- Rebuilding the serving pack or touching customer data.
- Switching the customer site to the new branch (needs a restart window and the
  replay gate; separate change).
