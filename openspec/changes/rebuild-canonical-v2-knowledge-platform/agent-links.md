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
