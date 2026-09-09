# S8E1 Release-bound KnowledgeRead Composition Implementation Plan

> Execute against the active OpenSpec and Slice Contract with strict RED -> GREEN discipline. Keep
> one writer for the shared physical owner. Do not commit.

**Goal:** Replace test-owned exact/structured wiring with one package-internal, fail-closed,
release-bound `KnowledgeRead` composition root while retaining the existing public execute seam.

**Architecture:** Deepen `knowledge_read_isolated.py`. A small release-bound wrapper validates the
execution-relevant release identity before delegating to the existing deep execution
module. The factory owns exact/structured physical adapters and exposes only the actual Web port and
bounded policies; it does not expose a local adapter map or add another execution interface.

## Task 1: Freeze the exact RED

**Files:**

- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Add `_MissingIsolatedReleaseKnowledgeReadFactory` and a lazy exact-symbol resolver.
- [x] Add one strict-xfail vertical test whose symbol lookup occurs before physical fixture access.
- [x] Specify construction without caller local adapters, exact+structured physical execution,
  Universal Web invocation/trace, content-addressed snapshot admission/rejection, collision-free
  fused lineage, per-binding-axis mutations, and physical/Web spy-proven fail-before-effect cases.
- [x] Run focused normal and record exactly `1 xfailed`.
- [x] Run focused `--runxfail` and record exactly one direct missing-symbol failure.
- [x] Run unchanged S8L1/S8L2/S8P1/S8P2 focused groups before production edits.

## Task 2: Add the release-bound composition root

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

- [x] Import only the existing `KnowledgeRead`, Web policy/snapshot types, and ephemeral factory
  needed for composition.
- [x] Add a package-internal wrapper that exact-revalidates plans and checks bound release,
  publication state/hash/evidence, manifest hash, and index-result hash before delegation.
- [x] Reject missing/mismatched release binding and lanes outside exact/structured/Web before any
  physical or Web call.
- [x] Add `create_isolated_release_knowledge_read` that exact-validates inputs, requires a bounded
  Universal-Web policy and snapshot policy, owns exact/structured factories, and injects only the
  explicit Web port/clock into the existing execution module.
- [x] Do not change the public `KnowledgeRead.execute` signature or any existing factory behavior.

## Task 3: Make GREEN and harden the boundary

- [x] Remove only the new strict-xfail marker after the production symbol exists.
- [x] Run focused GREEN; expect exactly `1 passed`.
- [x] Prove no local adapter mapping is accepted by the factory signature.
- [x] Prove cross-release, absent/mismatched binding, unsupported lane, and candidate publication
  reject before captured exact/structured/Web effects; mutate every execution-relevant binding axis.
- [x] Prove bounded Universal-Web policy rejection and exact WebSnapshotPolicy forwarding with
  accepted, oversize, and missing-payload receipts.
- [x] Re-run S8L1/S8L2/S8P1/S8P2 focused owners and the complete shared physical owner.

## Task 4: Proportional verification and acceptance

- [x] Run all KnowledgeRead owners and complete no-external Canonical V2.
- [x] Run Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec, and
  `git diff --check`.
- [x] Build one locked offline wheel, verify source/package parity and exclusions, then clean only
  owned disposable output after recording the receipt.
- [x] Recheck scope/secret/cache, original Milvus, paused PostgreSQL, recovery-lab, and frozen targets.
- [x] Obtain independent review, repair every Critical/Important finding, and rerun affected checks.
- [x] Record Minor/YAGNI without blocking unless it proves an explicit Spec/safety/model-valid bypass.
- [x] Create the secret-free content-bound receipt, mark S8E1 Accepted, synchronize existing evidence,
  keep Task 8.3 open at `56/80`, and name the next real-lane Slice.
