# S8V1 Release-scoped Vector Retrieval Implementation Plan

> Execute against the active OpenSpec and Slice Contract with strict RED -> GREEN discipline. Keep
> one writer for the shared physical/read owner. Do not commit.

**Goal:** Add the next real Task 8.3 lane: audited release-scoped vector recall through the Accepted
S8E1 composition and corrected S7J point lineage.

**Architecture:** Deepen the existing `KnowledgeRead` module. The isolated adapter takes one explicit
embedding port, audits the complete accepted physical snapshot, and performs deterministic bounded
cosine recall over those exact vectors. A path-discriminated trace union reuses the existing JSON
key and trust seam; callers still see only `KnowledgeRead.execute` and no lane map or Milvus client.

## Task 1: Freeze the exact RED

- [x] Add `_MissingIsolatedVectorRecallAdapter` and a lazy exact-symbol resolver before fixture use.
- [x] Add one strict-xfail physical vertical group covering direct vector recall, exact+vector
  composition/fusion, exact trace formulas, bounds/filters/order, Professor refusal, the complete
  embedding-output matrix, every snapshot/bundle comparison axis, hostile trust mutations, and no-
  embedding S8E1 refusal.
- [x] Freeze legacy exact/structured/lexical local trace serialization and identities through the
  existing predecessor assertions plus explicit before/after payload checks in the group.
- [x] Run normal RED (`1 xfailed`) and forced RED (one direct exact sentinel); run unchanged S7J and
  S8L1/S8L2/S8E1/S8L3 predecessors before production edits.

## Task 2: Add the vector trace and physical adapter

- [x] Add content-bound `LocalVectorTrace` and a `path`-discriminated union under the existing
  `local_projection_trace` key. Branch locator/item validation by path without changing legacy JSON/
  IDs/hashes; retain common candidate trust validation.
- [x] Add a validating embedding wrapper for frozen model/dimension, exception/cardinality/
  dimension/non-Boolean numeric/finite/non-zero rules, and exact-text vector memoization with drift
  refusal; add exact trailing marker removal, empty/zero short-circuit, Professor refusal,
  exact-revalidated complete `audit_isolated_index_snapshot` comparison to every bundle axis, public/
  filter selection, clamped cosine scoring, deterministic ordering, and bounded candidates.
- [x] Emit vector-specific evidence/candidate identity, claim, score, S7J limitation, query/model,
  source/publication, and physical release trace. Add no ranking/threshold/client framework.
- [x] Add the adapter to S8E1 only when the optional embedding port is supplied; keep vector fail-
  before-effects when absent and never expose a caller local lane map.

## Task 3: Make GREEN and verify compatibility

- [x] Remove only the S8V1 xfail after the exact factory exists; run focused GREEN (`1 passed`).
- [x] Run S7J and S8L1/S8L2/S8E1/S8L3/S8P1/S8P2 focused predecessors, complete physical/release
  owner, all KnowledgeRead owners, and complete no-external Canonical V2.
- [x] Run complete Ruff/format, changed-file compile, complete Pyright, strict OpenSpec, and
  `git diff --check`.

## Task 4: Package, review, and accept

- [x] Build one locked offline wheel, prove changed production source/package parity and exclusions,
  then clean only the owned disposable output after receipt creation.
- [x] Recheck scope/secret/cache, original Milvus, paused PostgreSQL, recovery lab, and frozen target.
- [x] Obtain independent review; repair every Critical/Important and rerun affected checks. Record
  Minor/YAGNI without blocking unless it proves a Spec/safety/model-valid bypass.
- [x] Create the secret-free receipt, mark S8V1 Accepted, synchronize existing evidence, keep Task
  8.3 open at `56/80`, and name the next real-lane Slice.
