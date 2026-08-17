# S8L3 Release-scoped Lexical Lookup Implementation Plan

> Execute against the active OpenSpec and Slice Contract with strict RED -> GREEN discipline. Keep
> one writer for the shared physical owner. Do not commit.

**Goal:** Add the smallest real missing Task 8.3 lane: bounded release-scoped lexical phrase recall
through the Accepted S8E1 composition root.

**Architecture:** Deepen `knowledge_read_isolated.py` beside its exact/structured physical adapters.
Reuse the guarded lookup reader and typed projection mapping, add only a narrow normalized-phrase
predicate, and extend the existing lane-bound trace identity. S8E1 owns the adapter; callers still
see only `KnowledgeRead.execute` and no local adapter map.

## Task 1: Freeze the exact RED

- [x] Add `_MissingIsolatedLexicalLookupAdapter` and a lazy exact-symbol resolver before fixture use.
- [x] Add one strict-xfail physical vertical group covering no-protected-slot proper substring recall, S8E1
  composition, collision-free exact+lexical lineage, bounds/exclusions, and fail-closed request/
  release/target cases.
- [x] Change S8E1's unsupported successor lane from lexical to vector without weakening the check.
- [x] Run normal RED (`1 xfailed`) and forced RED (one direct exact sentinel).
- [x] Run unchanged S8L1/S8L2/S8E1 focused groups before production edits.

## Task 2: Implement the lexical physical adapter

- [x] Extend `LocalProjectionTrace.execution_lane` with lexical while preserving exact/structured
  serialized identities and hashes.
- [x] Add `create_isolated_lexical_lookup_adapter` with exact release/publication/request validation,
  marker/quote normalization, empty-query short-circuit, guarded document read, typed public-only
  projection validation, phrase match, excluded terms, deterministic order, and candidate bound.
- [x] Reuse `_candidate_from_document` with one lexical adapter version; add no ranking framework.
- [x] Add the lexical adapter to S8E1 and permit only exact/structured/lexical/Web lanes.

## Task 3: Make GREEN and verify compatibility

- [x] Remove only the new xfail marker after the exact symbol exists.
- [x] Run focused GREEN (`1 passed`).
- [x] Run S8L1/S8L2/S8E1/S8P1/S8P2 focused groups and the complete physical owner.
- [x] Run all KnowledgeRead owners and complete no-external Canonical V2.
- [x] Run complete Ruff/format, changed-file compile, complete Pyright, strict OpenSpec, and
  `git diff --check`.

## Task 4: Package, review, and accept

- [x] Build one locked offline wheel, verify source/package parity and exclusions, then clean only
  owned disposable output after the receipt.
- [x] Recheck scope/secret/cache, original Milvus, paused PostgreSQL, recovery-lab, and frozen targets.
- [x] Obtain independent review; repair every Critical/Important and rerun affected checks.
- [x] Record Minor/YAGNI without blocking unless it proves a Spec/safety/model-valid bypass.
- [x] Create the secret-free receipt, mark S8L3 Accepted, synchronize existing evidence, keep Task
  8.3 open at `56/80`, and name the next real-lane Slice.
