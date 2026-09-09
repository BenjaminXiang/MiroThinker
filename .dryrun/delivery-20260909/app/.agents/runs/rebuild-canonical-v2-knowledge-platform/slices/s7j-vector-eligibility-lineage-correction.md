# Slice Contract: S7J Vector Eligibility Lineage Correction

## Status

Accepted at `2026-07-19T09:11:49Z`. S7/S7I and S8L1/S8L2/S8E1/S8L3 are Accepted. A code-grounded
S8V1 design gate found that the Accepted vector point envelope cannot preserve the exact semantic-
recall decision effect, so S7J is a mandatory narrow correction before any real vector read adapter.
The formal task ledger is `56/80` and remains unchanged by this Slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Corrects Accepted Tasks 7.5/7.6 vector point lineage and release inventory hashing under the
  existing path-eligibility, release-parity, and Task 8.3 traceability requirements
- Depends on: Accepted Task 6.7 path decisions, S7 vector construction/readback/publication, and
  S7I's already-Accepted lookup-lineage pattern
- Successor: S8V1 release-scoped vector retrieval may become Ready only after S7J is Accepted
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7j/implementation-plan.md`

## Goal

Preserve the exact `semantic_recall` `PolicyDecision` effect in every public
`IndexProjectionPoint`:

- `eligibility_decision_id`;
- `eligibility_outcome`, restricted to `admitted` or `limited`;
- sorted unique `eligibility_limitations`, including limitations attached to an admitted result.

Require a non-empty decision ID for public-domain points. Internal Person/Technology auxiliary
points remain decision-free `admitted` points with no public limitation. Map these fields only from
the already replay-validated S7 semantic decision; do not evaluate policy at read time.

Replace the duplicated partial vector-inventory hash in index construction and release verification
with one shared canonical full-point-envelope hash. Eligibility, owner/scope, view, schema/model/
policy, embedded content, and source-lineage changes must therefore change the owning
`IndexProjectionManifest.content_sha256` even when point ID and embedded-content hash stay fixed.

## Non-goals

- No vector query/search adapter, query embedding port, Milvus schema/collection/vector mutation,
  similarity metric, ranking/threshold/oversampling policy, candidate/evidence trace, or S8V1 code.
- No path-policy re-evaluation or semantic change, new policy registry, point population/ID,
  projection content, embedding, source evidence, public-domain, or internal-reference change.
- No database migration, provider, original/production-like rebuild, active pointer, Task checkbox,
  aggregate S7/S8 acceptance, Commit, Push, PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection.py` for the additive point
  fields, exact semantic-decision mapping, validators, and one shared canonical full-point hash.
- `apps/miroflow-agent/src/data_agents/canonical_v2/release_publication.py` only to consume that same
  shared point hash during release inventory verification.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact-symbol RED group and the smallest semantic-limitation fixture option.
- `apps/miroflow-agent/tests/canonical_v2/test_release_publication_interface.py` only for mechanical
  point-fixture compatibility: the default manifest hash must call the production shared point-hash
  function over the actual default point rather than copy canonical encoding in the test. The old-
  manifest/metadata-drift rejection may remain in the main S7J group or a narrow release companion.
- This contract/plan and S7J-only evidence. Existing verification/change-log/agent-links/portfolio/
  mainline-plan artifacts may be synchronized only after Candidate review. Keep `tasks.md` and
  `acceptance.md` unchanged.

## Forbidden changes

- Any `knowledge_read*`, query/answer/gap/planner/provider, migration, relationship, projection-
  source, publication-pointer, admin/chat, or unrelated test file.
- Inferring a decision from undifferentiated `source_evidence_ids`; defaulting a public point to
  admitted; inventing a limitation; accepting `limited` without a visible limitation; attaching a
  public decision/limitation to an internal point; or retaining separate builder/verifier hash rules.
- Hashing only point ID/release/embedded-content hash, weakening exact expected/actual point parity,
  altering point IDs to carry mutable eligibility state, or masking existing assertions with xfail/
  skip changes.

## Expected unchanged behavior

- Point populations, point IDs, projection IDs, public/internal ownership, projection views,
  embedded content and hashes, embedding vectors/model, source evidence, deterministic ordering,
  Milvus/SQLite materialization, active/rollback behavior, and every public S7 method remain
  unchanged apart from additive point metadata and resulting result/manifest/receipt hashes.
- Existing physical readback continues to return exact typed equality with the Accepted build.
  Original PostgreSQL/Milvus/forensic sources, candidate pointers, Task 8.3, and the `56/80` ledger
  remain unchanged.

## Required checks

- RED normal: exactly one strict xfail; forced `--runxfail`: exactly one direct
  `_MissingS7JSemanticEligibilityLineage` failure before candidate or physical build work.
- GREEN focused: exactly one pass. Every public point equals its corresponding semantic decision
  ID/outcome/limitations; `paper-ada` retains admitted `profile_incomplete`; every internal point is
  decision-free admitted with no limitation.
- The focused group rejects a public point without a decision, `limited` without limitations, and an
  internal point with public decision/limitations, plus duplicate/unsorted limitations. With point
  ID fixed, a compact valid-mutation matrix independently changes eligibility decision/outcome/
  limitations, canonical owner/domain/scope, projection view/version/schema, embedding model,
  eligibility policy, embedded content/hash, source-projection hash, and source evidence; every row
  must change the owning manifest hash. This prevents a partial extension of the old inventory hash
  from satisfying the test.
- Release verification rejects an exact expected/actual mutated point set paired with the old
  manifest, proving inventory hashing—not point inequality or manifest mismatch—detects eligibility
  drift. The group asserts expected and actual manifests are the same old tuple, expected and actual
  points are the same mutated tuple, all four discrepancy counts are zero, the discrepancy store is
  empty, expected and actual `index-inventory` evidence is present, and no `index-manifest` evidence
  exists.
- Complete shared S7 physical owner, release-publication owners, S8 physical successors, complete
  no-external Canonical V2, Ruff/format, changed-file compile, complete Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target gates pass with actual counts recorded.
- One independent review ends with zero open Critical/Important. Minor/YAGNI is recorded and does
  not block unless it proves a Spec/safety/model-valid bypass.

## Evidence to update

- This contract and `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7j/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan after acceptance. Do not
  change `tasks.md` or `acceptance.md`.

## Stop conditions

- The exact semantic decision cannot be mapped from the already validated S7 request/result pair;
  the correction changes policy semantics, point populations/IDs/vectors, Milvus schema, a public
  S7 method, or release pointers; or builder and verifier cannot share one canonical hash definition.
- Any existing S7/S8 owner regresses, original/production-like state changes, or a Critical/
  Important finding remains open.

## Done means

- One exact RED becomes one additive semantic-lineage and full-inventory-hash GREEN; all affected
  physical/release/static/package/frozen checks pass and independent review has zero open Critical/
  Important findings.
- S7J is Accepted as a correction checkpoint with Task 8.3 still open and the formal ledger still
  `56/80`; S8V1 may then start from the corrected point envelope.

## Rollback note

Remove the three point fields/validators/mappings, restore the two partial inventory hash call sites,
remove the focused fixture/tests and S7J evidence. No point ID, physical/original target, task
checkbox, or release pointer requires rollback.
