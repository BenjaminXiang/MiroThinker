# Slice Contract: s7h-isolated-release-rehearsal-green

## Status

Accepted at `2026-07-14T12:46:02Z`. All three Accepted S7G scenarios are GREEN on fresh explicitly
marked isolated resources, owned resources are cleaned, and two independent final reviews report
zero Critical/Important findings. Task 7.7 and aggregate S7 are Accepted at 46/80.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.7` (GREEN and aggregate S7 acceptance)
- Depends on: Accepted S7A-S7G/Tasks 7.1-7.6 plus the S7G RED contract

## Goal

Make the three Accepted S7G scenarios GREEN with one package-internal adapter that composes the
existing S7F `ReleasePublication` over complete physical S7E index audits and one identity-checked,
atomic pointer row in a fresh disposable PostgreSQL database. Prove isolated promotion and rollback
without authorizing or touching any production-like target.

## Non-goals

- No migration/schema change, public release interface, production alias/cutover, production
  authorization, consumer wiring, S8 behavior, live provider, 2PC/concurrency framework, release
  retirement, generalized repository layer, commit, push, PR, archive, or cutover.
- No expansion beyond the three Accepted S7G scenarios. Physical missing/stale/cross-release
  variants already proven by S7F are not duplicated as new integration cases.

## Allowed scope

- Add a complete, read-only isolated snapshot audit to
  `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py`. It must enumerate
  the physical Milvus collection rather than trusting receipt-listed point IDs and must revalidate
  lookup documents/manifests/receipt, embeddings, release identity, and marked target identity.
- Add package-internal
  `apps/miroflow-agent/src/data_agents/canonical_v2/release_publication_isolated.py` containing only:
  the typed release bundle; explicit disposable-database target preparation/identity verification;
  isolated active-release read; an atomic three-key PostgreSQL state mapping; and composition that
  reuses S7F `verify/promote/rollback` while re-auditing the selected physical target at the
  verification/promotion/rollback boundaries.
- Remove only the three S7G strict-xfail wrappers when their scenarios are truly GREEN. Focused
  helper/test corrections are allowed only if execution exposes an error in the frozen test contract,
  not to weaken it.
- Update this contract, Task 7.7, the single rollback acceptance item, verification evidence,
  change log, agent links, mainline plan, and portfolio only after acceptance.

## Forbidden changes

- Any Accepted S7F reconciliation/public interface behavior, BuildManifest/index point contract,
  migration, schema, generic `DATABASE_URL` fallback, durable candidate/recovery database, original
  `pgtest`, original Milvus, retained S7E acceptance target, active production-like pointer, or
  landing evidence.
- Receipt-only Milvus reads presented as complete inventory; a pointer update split across more than
  one committed transaction; promotion after physical drift; rollback to an unaudited/mixed prior
  release; database or Milvus open before static release/target continuity checks.
- New public alias semantics, production authorization flags, retries, locks beyond the existing
  single-row database transaction, or cleanup/retirement policy.

## Expected unchanged behavior

- S7E construction/readback and S7F deterministic manifest/point reconciliation retain their
  Accepted interfaces and evidence. The isolated module is an adapter, not a competing publication
  engine.
- Candidate verification remains evidence-producing and pointer-neutral; rejected verification or
  post-verification physical drift leaves the prior pointer unchanged.
- Promotion and rollback update canonical/published/index release IDs together, retain immutable
  release/build/landing evidence, and append caller-owned publication history.
- The four public domains plus three internal auxiliary projection owners remain unchanged. No new
  query, answer, provider, or consumer behavior is introduced.

## Required checks

- On one fresh marked disposable PostgreSQL target and two fresh marked physical index roots, the
  three S7G scenarios return exactly `3 passed`: accepted verify -> explicit promote -> serving
  physical read -> rollback; one unreceipted extra point produces `extra_points == 1` and no pointer
  change; malformed/cross-wired targets cause zero PostgreSQL/Milvus opens and zero pointer writes.
- The database pointer always has one canonical/published/index release identity. Promotion and
  rollback each use one guarded SQL transaction; release/build-manifest and landing evidence hashes
  plus both physical index hashes remain unchanged.
- Complete physical audit enumerates the Milvus collection independently of the receipt and validates
  every point payload/vector plus the complete lookup/receipt/manifests. The candidate is audited
  again immediately before promotion and the prior target before rollback.
- Existing S7F owner is `6 passed`; no-external S7E/S7F ownership has no real failure; the active-
  release mixed-pointer/transaction invariant passes on the same disposable database; complete
  no-external Canonical V2 has only the two KnowledgeRead/KnowledgeAnswer expected REDs.
- Complete Canonical V2 Ruff check, focused format, complete Canonical V2 Pyright, import/wheel
  inclusion, strict OpenSpec, `git diff --check`, scope/secret/cache, original-target hash/pause, and
  owned-resource cleanup checks pass.
- At least two independent final read-only reviews report zero open Critical/Important findings.
  Minor/YAGNI is recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- A secret-free execution receipt under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7h/` recording exact commands/results,
  disposable target identities, pre/post pointer states, immutable-evidence/index hashes, original
  frozen-target checks, cleanup, and reviewer conclusions.
- Existing OpenSpec task/acceptance/change-log/agent-links plus the code-grounded plan and portfolio
  only after Candidate verification and review.

## Stop conditions

- GREEN requires a new migration, public contract, production-like target, generic environment
  fallback, Accepted predecessor behavior change, or scope beyond the three RED scenarios.
- Complete physical inventory cannot be enumerated and validated with the installed Milvus client,
  or promotion/rollback cannot remain a one-row atomic transaction.
- A check exposes original/retained-target access, evidence mutation, an Accepted-slice regression,
  owned-resource leakage, or an unresolved Critical/Important finding.

## Done means

- The exact three S7G tests are GREEN on fresh owned isolated resources, all required checks and
  zero-Critical/Important reviews pass, and a secret-free receipt makes the rehearsal reproducible.
- Task 7.7 and only its isolated promotion/rollback acceptance item are checked; the ledger becomes
  46/80 and aggregate S7 is Accepted without production promotion or cutover.
- S2C is the next prerequisite before S8/S9 acceptance-oracle execution; no Commit, Push, PR,
  archive, or Cutover occurred.

## Plan

1. Implement complete isolated physical snapshot audit and prove it detects the S7G extra point.
2. Implement the explicit disposable-PostgreSQL pointer adapter and compose S7F publication with
   boundary re-audits.
3. Provision one fresh owned database, migrate it to the existing head, run the exact three GREEN
   scenarios plus sibling/invariant checks, then clean only owned resources.
4. Run static/package/strict/safety checks, obtain two independent reviews, persist evidence, and
   accept Task 7.7/S7 only if zero Critical/Important remain.

## Acceptance evidence

- A fresh network-none/no-port PostgreSQL target migrated to existing head `C2_0010`. The existing
  mixed-pointer/transaction invariant passed `1 passed`; the final current-code isolated rehearsal
  passed exactly `3 passed, 40 deselected in 20.45s` and restored all four release fields to
  `accepted-s7g-r0` while retaining `candidate-s7g-r1` as the rollback predecessor.
- Complete physical Milvus enumeration detects the unreceipted extra point and validates every point
  JSON/scalar/vector. SQLite readback validates exact lookup rows/manifests/receipt plus exactly one
  release and collection metadata pair. The review-discovered cross-release metadata counterexample
  now fails before Milvus open; its focused regression and the target-safety scenario pass.
- Final no-external evidence is S7F owner `6 passed`, S7E/S7F owner `47 passed, 2 skipped`,
  KnowledgeBuild plus ReleasePublication `9 passed`, shared contracts `16 passed`, and complete
  Canonical V2 `291 passed, 141 skipped, 2 xfailed`; only KnowledgeRead/KnowledgeAnswer remain RED.
- Complete Ruff, focused format, complete Canonical V2 Pyright, import, 272-entry wheel, strict
  OpenSpec, diff/scope/secret/cache, frozen-target, and cleanup gates pass. The final wheel SHA-256 is
  `aa9471c025dd129fe181e0fbb82823f57f93abb2420794e7736dcf0c4276136a`.
- The secret-free execution receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7h/isolated-release-rehearsal-receipt.json`;
  its database evidence SHA-256 is
  `f1d775f0dd24aad07500b48330a653f16f57d29c2c8a25978c2f1df263b08e18`.
- Two independent final read-only reviews report zero Critical and zero Important findings after
  closing the single build-metadata release-binding Important. Fixed fixture IDs, the large owner
  fixture, duplicate physical classification cases, and Milvus Lite timestamp-warning noise remain
  recorded nonblocking Minor/YAGNI.
- Original Milvus remains SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`; original `pgtest` remains
  paused on volume `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
  All S7H database/socket/index/container resources were removed. No Commit, Push, PR, production
  promotion, archive, or Cutover occurred.

## Rollback note

Remove the new isolated publication module, the additive audit surface, the three xfail-wrapper
removals, and S7H evidence/status deltas. Drop/remove only explicitly named S7H-owned disposable
resources. No existing release, migration, original database/index, retained S7E target, or public
interface requires rollback.
