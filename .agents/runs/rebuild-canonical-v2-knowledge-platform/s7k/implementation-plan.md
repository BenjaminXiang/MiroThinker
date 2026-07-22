# S7K Release-scoped Relationship Publication Authority Correction Implementation Plan

> Execute against the active OpenSpec and Slice Contract with strict RED -> GREEN discipline. Keep
> one writer for the shared S7 publication owner. Do not commit.

**Goal:** Bind one exact non-empty S6 relationship projection to the immutable S7 release bundle so
the later S8 relationship lane has a release authority it can verify rather than infer.

**Architecture:** Deepen `IsolatedReleaseBundle`; do not change `CandidateProjectionResult`, create a
new repository, or implement query behavior. The bundle replays the existing pure relationship
projector, reconstructs the already-defined seven candidate projections from the relationship
request's internal graph, and compares those artifacts to the manifest. The release-publication
factory revalidates the complete bundle before effects.

## Task 1: Review and freeze the contract

- [x] Obtain independent contract/design and feasibility reviews against OpenSpec, S6 relationship
  ownership, S7 publication seams, and S8R1 needs.
- [x] Repair all six Important findings; the initial reviews reported zero Critical/Minor/YAGNI.
- [x] Mark the Slice Ready after both targeted reviews report zero open Critical/Important; the
  contract review also reports zero Minor/YAGNI.

## Task 2: Add the exact RED

- [x] Add `_MissingS7KRelationshipPublicationAuthority` and one exact strict-xfail group that
  checks for the two bundle fields before fixture or external-target acquisition.
- [x] Extend the existing S7 physical release helper minimally to produce a real combined-registry
  request/result with three accepted Technology semantic-state current relationships and a
  relationship manifest derived from that exact result.
- [x] Cover round-trip authority plus pair, release/as-of, replay, manifest, seven-projection graph,
  combined-registry/internal-pair, authoritative-zero, and model-construct/cross-wire negatives;
  instrument every backup/target/index/PostgreSQL seam and prove all effect counters remain zero.
- [x] Run normal RED (`1 xfailed`) and forced RED (one direct exact sentinel), then unchanged
  predecessor checks before production edits.

## Task 3: Implement the narrow publication authority

- [x] Add optional both-or-neither `relationship_projection_request` and
  `relationship_projection_result` fields to `IsolatedReleaseBundle`.
- [x] Preserve absent-pair compatibility only for zero-count relationship manifests.
- [x] Require a present authority to carry a combined-registry request with its internal-reference
  pair; replay the installed relationship projector and require exact result equality; reconstruct
  candidate projections from that graph and require exact seven-manifest parity.
- [x] Bind relationship manifest section ID/release/projection-schema version/count/hash to the
  replayed result; keep registry identity bound by replay/result content rather than section version.
- [x] Make `_validate_bundle_pair` return fresh typed copies, replace both factory inputs with those
  copies before every external seam, reject non-exact bundle types, and recompute each complete
  manifest hash before effects. Remove only the S7K xfail after the exact fields exist.

## Task 4: Verify compatibility and review

- [x] Run focused GREEN (`1 passed`), S6 relationship owners, S7 candidate/index/publication owners,
  S8 physical successors, and the complete no-external Canonical V2 suite.
- [x] Run Ruff/format, changed-file compile, complete Pyright, strict OpenSpec,
  `git diff --check`, and the frozen-source/target checks.
- [x] Build one locked offline wheel; prove changed production source parity and exclusions, create
  the secret-free receipt, then remove only the owned disposable wheel output.
- [x] Obtain independent implementation review; repair every Critical/Important finding and rerun
  affected checks. Record Minor/YAGNI without blocking unless it exposes a real contract bypass.

## Task 5: Accept and return to the outer loop

- [x] Mark S7K Accepted only after required evidence and zero open Critical/Important findings.
- [x] Synchronize verification/change-log/agent-links/portfolio/mainline plan, keep Task 8.3 open at
  `56/80`, and select S8R1 release-scoped relationship retrieval next.
