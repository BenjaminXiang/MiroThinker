# Slice Contract: F — index-parity

## Status

Specified — blocked until Slice E is Accepted

## Parent

- OpenSpec change: `openspec/changes/close-retrieval-generation-contract/`
- Depends on: accepted `slices/e-type3-traversal.md`

## Goal

Make derived paper eligibility observations, chunk manifests/version drift, lane progress, failures,
and two-level Postgres-Milvus parity durable and replayable through a reversible audit ledger and
bounded desired-state reconciliation without creating a second readiness authority.

## Non-goals

- Automatically enriching or indexing the full production backlog during implementation.
- Auto-resolving `needs_review`, changing rejected/merged identity decisions, or rewriting canonical
  paper content.
- Rewriting historical migrations or replacing the embedding provider.
- Removing the prior index/alias before acceptance and observation.

## Allowed scope

- One additive reversible migration; non-authoritative paper audit ledger; exact chunk manifest/
  version storage; candidate-row or cryptographically linked sidecar metadata; sole derived
  `index_eligibility` readiness plus separate non-admitting `enrichment_lane_membership` rules;
  source/chunk-hash logic; two-level desired-state inspector; reconciler/checkpoints/bounded runner;
  and index-alias rollback hooks.
- Read-only live preflight only when explicitly approved; mutation initially targets a named
  non-production collection/index.
- Slice-owned migration/storage/reconciler/retrieval/eval artifacts and status documents.

## Forbidden changes

- Production/business canonical paper updates without explicit lane authorization.
- Counting rejected/merged records as active backlog or desired index coverage.
- Reading persisted ledger eligibility or enrichment-lane membership as retrieval admission instead
  of recomputing canonical `index_eligibility`.
- Marking success before the target vector write/version is confirmed.
- Paper-ID/count-only parity, treating legitimate multi-chunk papers as duplicates, trusting
  unverifiable ledger-only vector versions, silent review promotion, destructive unbounded deletes,
  or non-resumable one-shot backfill.
- Production alias cutover or bulk provider spend without explicit approval.
- Weakening accepted retrieval/citation/semantic/latency gates to accommodate a candidate index.

## Expected unchanged behavior

- Accepted chat and Type1-Type4 semantics remain unchanged.
- The initial migration is additive; canonical paper schema/rows and existing index remain usable.
- Dry-run and test/rehearsal modes perform no production data/index mutation.
- Current successful chunks remain stable when eligibility and full content/chunker/model/index
  manifests match.

## Required checks

- Migration upgrade/downgrade on a disposable/test database and storage-model validation.
- Index-eligibility versus enrichment-lane-membership matrix covering ready, partial-rich,
  title-only, needs-enrichment, needs-review, rejected, merged, inactive, and version/content
  transitions.
- Ledger tests for recomputed rule-version eligibility, full-manifest confirmed success, provider/
  write failure, content/chunker/model/index drift, retry, history, and no-call current tuple.
- Reconciler tests for paper coverage and exact missing/unexpected/stale/conflicting/unverifiable
  chunks, legitimate multiple chunks, equal-paper-count/different-chunk IDs, and terminal entries.
- Interrupted-job resume and repeated-run idempotency with checkpoint evidence.
- Dry-run safety and bounded non-production rehearsal; exact paper coverage plus chunk manifest/
  version parity.
- Read-only active-production paper/chunk parity and residual lane report, with mechanism-only versus
  production-parity status explicit.
- Candidate-index frozen Type1-Type4 retrieval/citation/semantic/zero-regression/latency gates.
- Prior index alias/version rollback demonstration.
- Focused lint/type plus strict OpenSpec/diff checks.

## Evidence to update

- Slice F/Epic sections in `verification.md` and `acceptance.md`, including migration outputs,
  snapshot worklists/counts/ID hashes, ledger/parity artifacts, dry-run plan, bounded rehearsal,
  retrieval gates, spend/latency, review, immutable hash, and rollback target.
- Tasks/change log/portfolio and final Epic dependency status.

## Stop conditions

- Slice E is not Accepted.
- Migration is irreversible, conflicts with active schema contracts, or lacks synchronized model and
  test updates.
- Worklist membership or terminal handling is ambiguous.
- The target is production or can affect the active alias without explicit authorization.
- Dry run shows unexpected deletions, unresolved lifecycle states, excessive provider cost, or an
  unsafe rollback gap.
- Candidate index fails parity or an accepted retrieval/citation/semantic/latency gate.

## Done means

- Every paper in the declared reconciliation snapshot has a non-authoritative rule-versioned ledger
  observation and expected chunk manifest; full success covers every current chunk.
- Separate worklists exclude terminal records and preserve needs-review for audit.
- Reconciliation proves distinct-paper and exact verifiable chunk/version state; replay is bounded,
  idempotent, and resumable.
- A non-production candidate passes frozen retrieval gates and rollback is demonstrated.
- Active-production gaps and residual enrichment lanes are reported; no production parity or
  overall-retrievability claim is made without an authorized run and confirming active-index report.
- All Slice F gates pass; independent review, immutable diff/artifact hash, and Accepted status are
  recorded; an isolated commit is linked only when explicitly authorized. Production promotion
  remains a separate explicit decision.

## Rollback

Point the alias/config back to the recorded prior index version, stop lane jobs, and downgrade the
additive migration only if the ledger itself must be removed. Never rewrite canonical paper data to
roll back index state.
This real rollback invalidates F parity/promotion and Epic cutover under the central matrix while
leaving A-E evidence intact; the prior alias remains available through the observation window.
