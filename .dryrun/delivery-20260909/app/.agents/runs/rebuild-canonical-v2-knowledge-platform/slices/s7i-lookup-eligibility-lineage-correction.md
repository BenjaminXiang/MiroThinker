# Slice Contract: s7i-lookup-eligibility-lineage-correction

## Status

Accepted at `2026-07-16T04:55:58Z`. An S8L1 design gate found that Accepted S7 lookup documents admit
both eligible and limited exact-path objects but persist only the policy version, so a read adapter
cannot preserve the required visible limitation. This is a narrow correction/reacceptance slice;
S7 remains historically Accepted and no OpenSpec task checkbox changes.

Acceptance evidence: the focused RED failed exactly once on the missing
`eligibility_decision_id`; the same group then passed, the complete shared S7 file returned
`42 passed, 2 skipped`, and complete no-external Canonical V2 returned
`330 passed, 141 skipped, 0 xfailed`. S7 sibling owners, Ruff check/format, `py_compile`, complete
Canonical V2 Pyright, strict OpenSpec, `git diff --check`, wheel/source parity, cache/secret/scope,
and frozen-source checks passed. The merged independent review reported zero Critical, Important,
Minor, and YAGNI findings. The secret-free receipt is
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s7i/verification-receipt.json`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Corrects Accepted Task 7.5/S7E lookup projection metadata under the existing Canonical V2 path-
  eligibility and release requirements
- Depends on: Accepted Task 6.7 path decisions and Accepted S7E/S7F/S7H projection, physical
  readback, parity, publication, and rollback behavior
- Successor: S8L1 may become Ready only after this correction is Accepted

## Goal

Preserve the exact lookup `PolicyDecision` effect in every public `LookupProjectionDocument`:

- `eligibility_decision_id`;
- `eligibility_outcome` restricted to the two publishable outcomes `admitted` or `limited`;
- sorted unique `eligibility_limitations`, including limitations that accompany an admitted result.

Require a non-empty decision ID for public-domain documents. Internal auxiliary documents retain
their existing evidence-anchor admission as `admitted` with no public path decision or limitation.
Make each lookup manifest content hash sensitive to the complete normalized document envelope so an
outcome, limitation, decision, owner, version, or source-lineage change cannot preserve parity by
leaving `lookup_content_sha256` unchanged.

## Non-goals

- No path-policy re-evaluation at query time, new eligibility semantics, policy registry, score/
  ranking change, hard-exclusion change, document-ID change, database migration, provider, S8 read
  adapter, consumer, publication/pointer operation, or production-like rebuild.
- No rewrite of historical S7 evidence. The correction records a new reacceptance checkpoint while
  retaining the original acceptance record.
- No Commit, Push, PR, archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection.py` for the additive document
  fields, exact builder mapping, validators, and complete-document manifest hashing.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  focused public-behavior regression plus the smallest helper option needed to produce an exact-path
  quality limitation from an existing typed assertion.
- This Slice Contract and its implementation plan. Existing verification/change-log/agent-links,
  portfolio, and mainline plan may be updated only after Candidate review. `tasks.md` and
  `acceptance.md` remain unchanged.

## Forbidden changes

- Any other production/shared-contract/migration/provider/read/answer/gap/admin/chat file, existing
  Accepted assertion value, S7 public method, physical target, original source, or active pointer.
- Defaulting a public document to admitted when its decision is unavailable; synthesizing a
  limitation; accepting `limited` without a visible limitation; publishing an excluded/review
  decision; hashing only lookup projection JSON while ignoring eligibility metadata.
- Weakening, deleting, xfail/skip-masking, or merging existing S7 assertions to make the correction
  pass.

## Expected unchanged behavior

- Public/internal lookup document populations, IDs, projection contents, source evidence, policy
  versions, deterministic ordering, SQLite/Milvus materialization, physical readback, release parity,
  and rollback behavior remain unchanged apart from the additive eligibility metadata and the
  resulting content-bound manifest/result/receipt hashes.
- The existing S7E real readback still validates exact equality between built and physical lookup
  documents. The four public domains and three internal auxiliary owners remain exactly unchanged.
- Complete no-external Canonical V2 gains one passing correction group; S8/S9/S10 behavior and the
  55/80 ledger remain unchanged.

## Required checks

- RED: the new focused group fails exactly once because lookup documents lack the exact eligibility
  decision/outcome/limitations and their manifest hash is not mutation-sensitive to those values.
- GREEN: the focused group passes for all four public documents, proves an exact-path quality
  limitation survives, rejects a `limited` document without limitations, keeps internal auxiliaries
  decision-free/admitted, and proves manifest content changes when eligibility metadata changes.
- The complete shared S7 file is expected to be `42 passed, 2 skipped` in the current no-disposable-
  database environment; index/release owner regressions have zero real failures.
- Complete no-external Canonical V2 is expected to be `330 passed, 141 skipped, 0 xfailed` absent
  concurrent work; actual counts are recorded rather than forced.
- Scoped Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, package content, scope/secret/cache, and frozen-source checks pass.
- One merged independent review ends with zero open Critical/Important findings. Minor/YAGNI is
  recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md` and `agent-links.md`.
- `.agents/portfolio.md` and the current code-grounded mainline plan.
- A secret-free receipt under `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7i/`.

## Stop conditions

- The correction requires changing path-policy semantics, a public S7 method, schema/migration,
  document population/IDs, release pointer, or a production-like target.
- A limited/admitted decision cannot be mapped exactly from the already replay-validated S7 input,
  physical readback cannot retain the fields, or manifest parity cannot bind them.
- Any existing S7 owner regresses or a Critical/Important finding remains open.

## Done means

- The focused regression proves the missing metadata, turns GREEN through one additive S7 mapping,
  and affected S7/readback/static/strict/package/source checks pass.
- One independent review reports zero open Critical/Important findings and correction evidence is
  persisted without rewriting historical S7 acceptance.
- S7I is Accepted with the formal ledger still 55/80; S8L1 may then be revised against the corrected
  document and `IsolatedReleaseBundle` boundary.

## Rollback note

Remove the three document fields, builder assignments, complete-document manifest hashing, focused
test/helper option, and S7I evidence. Existing physical/candidate/original targets and task
checkboxes require no rollback.
