# S7J Vector Eligibility Lineage Correction Implementation Plan

> Execute against the active OpenSpec and Slice Contract with strict RED -> GREEN discipline. Keep
> one writer for the shared S7 physical/release owners. Do not commit.

**Goal:** Preserve exact semantic-recall decision effects in every vector point and make builder/
release parity sensitive to the complete typed point envelope.

**Architecture:** Extend the existing `IndexProjectionPoint`; do not add a second artifact or a
query-time policy evaluator. `_vector_points` copies the already replay-validated semantic decision.
One package-owned canonical point-inventory hash is reused by both index manifests and release
verification so their parity definition cannot drift.

## Task 1: Freeze the exact RED

- [x] Add `_MissingS7JSemanticEligibilityLineage` and check the three exact model fields before any
  candidate/physical fixture acquisition.
- [x] Add `semantic_limitation_identity_id` to the existing path/index fixture helpers without
  changing default calls; emit one existing `profile_incomplete` signal for semantic recall only.
- [x] Add one strict-xfail vertical group covering exact public decision mapping, admitted visible
  limitation, internal decision-free semantics, validator negatives, a compact full-envelope
  mutation matrix, and release-verifier old-manifest rejection with equal mutated point sets and
  zero point/manifest discrepancies.
- [x] Run normal RED (`1 xfailed`) and forced RED (one direct exact sentinel).
- [x] Run unchanged S7I and release-publication focused predecessors before production edits.

## Task 2: Add vector eligibility lineage and shared hashing

- [x] Add decision ID/outcome/limitations to `IndexProjectionPoint`, sorted-unique validation, public
  decision requirement, internal decision-free admission, and limited-without-limitations refusal.
- [x] Copy exact values from the replay-validated `semantic_recall` decision into public points;
  retain internal points as `None`/`admitted`/`()`. Change no point ID/content/vector/source value.
- [x] Define one canonical full-point-envelope inventory hash in `index_projection.py`; use it in
  `build_index_projection_manifests` and import the same definition in `release_publication.py`.
- [x] Update only the release-publication test point helper with explicit valid semantic lineage;
  derive its default manifest content hash by calling the production shared hash over the actual
  default point, never by copying the canonical encoding or retaining the old partial-hash constant.

## Task 3: Make GREEN and verify compatibility

- [x] Remove only the S7J xfail after the exact model fields exist; run focused GREEN (`1 passed`).
- [x] Run S7I, complete shared physical/release owners, and S8L1/S8L2/S8E1/S8L3 successors.
- [x] Run complete no-external Canonical V2 and record actual counts.
- [x] Run complete Ruff/format, changed-file compile, complete Pyright, strict OpenSpec, and
  `git diff --check`.

## Task 4: Package, review, and reaccept

- [x] Build one locked offline wheel, prove changed production source/package parity and exclusions,
  then clean only the owned disposable output after receipt creation.
- [x] Recheck scope/secret/cache, original Milvus, paused PostgreSQL, recovery lab, and frozen target.
- [x] Obtain independent review; repair every Critical/Important and rerun affected checks. Record
  Minor/YAGNI without blocking unless it proves a Spec/safety/model-valid bypass.
- [x] Create the secret-free receipt, mark S7J Accepted, synchronize existing evidence, keep Task
  8.3 open at `56/80`, and return to S8V1.
