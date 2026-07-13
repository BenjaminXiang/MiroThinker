# Agent and Slice Links

## Ownership

- OpenSpec owns behavior, scope, acceptance, and verification intent.
- Each slice has one active writer.
- Independent review owns Candidate-to-Accepted promotion.
- The primary agent may delegate bounded work to subagents. Parallel writers use isolated
  branches/worktrees and separately named disposable resources; subagents do not approve an entire
  task, push, promote, or mutate shared active pointers.
- Each final Accepted OpenSpec task is integrated, verified, and committed separately by the
  primary agent.

## Slice dependency DAG

S1 through S5 are Accepted. Remaining work follows interface/data dependencies rather than task
number alone:

- S6 typed domain/relationship/eligibility production work consumes the Accepted S5 assertion,
  identity, review, and history seams.
- S7 release/index RED contracts may start once their public release seams are frozen; candidate
  construction, typed projections, and index builders consume Accepted S6 catalogs/policies.
- S8 query trace RED contracts may start against frozen interfaces and corpora; executable local
  retrieval consumes an Accepted release, typed relationship/eligibility catalog, and index seam.
- S9 answer/session RED contracts may start against typed evidence fixtures; production answer and
  session behavior consumes the Accepted S8 evidence/trace result.
- S10 gap RED contracts may start against shared typed gap/trace fixtures; operational closure and
  admin migration consume accepted build/release/query/answer evidence.
- S11 consumer migration depends on the replacement deep modules it migrates to being Accepted.
- S12 candidate construction and final acceptance depend on all required build, release, index,
  query, answer, gap, and consumer seams being Accepted.

Two or more tasks may be In Progress when their dependencies are Accepted or their consumed
interfaces are frozen, their writers and resources do not overlap, and each remains independently
testable and commit-scoped. If a shared contract, migration head, database, Milvus release, output
directory, or active pointer would have multiple writers, that seam returns to serial integration.

## Git mainline promotion gate

The user selected aggregate S6 acceptance as the checkpoint for moving Git `main` to Canonical V2.
Promotion is fast-forward-only and requires all of the following in the execution session:

1. Task 5.7/S5G and Tasks 6.1-6.8 are Accepted with linked review/verification evidence.
2. The V2 integration worktree is clean and contains no untracked implementation/evidence required
   by the accepted checkpoint.
3. Every Canonical V2 side branch has been integrated, proven redundant, or explicitly abandoned;
   no unique accepted patch remains outside the integration line.
4. The root worktree's unrelated dirty files are preserved and reconciled without overwrite.
5. `git merge-base main <v2-integration>` still equals `main`; ahead/behind inspection proves a pure
   fast-forward, with no merge or rebase.
6. Strict OpenSpec, aggregate S6 checks, frozen-source safety, and diff/secret/scope checks pass on
   the exact promotion commit.

Meeting this gate does not authorize database/index promotion, production-like cutover, push, PR, or
archive. If any condition fails, Git `main` remains unchanged.
