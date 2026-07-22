# S8V2 Professor Typed Vector-view Selection Implementation Plan

> Execute against the active OpenSpec and Slice Contract with strict RED -> GREEN discipline. Keep
> one writer for shared planning/read owners. Do not commit.

**Goal:** Carry one finite Professor vector-view selector from the recorded planning boundary to the
audited release-scoped vector adapter, enabling identity/research/both execution without adding an
intent framework or changing raw candidate budgets.

**Architecture:** Deepen the existing `KnowledgeRead` module. An optional omission-preserving
`professor_vector_view` field is validated at proposal, plan, and vector-request seams. The S8V1
adapter filters already-Accepted Professor points by that selector, derives display names from the
same audited public lookup snapshot, and the release authority seam checks the returned view.

## Task 1: Freeze the exact vertical RED

- [x] Before any production edit, add and run a non-xfail literal-baseline test for full JSON and
  SHA identities of one absent-selector Proposal, unbound Plan, and LaneRequest.
- [x] Add `_MissingProfessorVectorViewSelection` and an exact model-field resolver before fixture
  acquisition.
- [x] Add one strict-xfail physical vertical group covering identity/research/both planning,
  propagation, direct vector execution, release-bound fusion, lookup-derived display identity,
  exact identity/research/mixed scenario queries, cross-field invalid combinations, wrong-view/
  forged-display authority rejection, and absent-field legacy hashes.
- [x] Add the optional helper input and explicit `research` selector to the existing valid D-taxonomy
  and Professor-vector institution-planning fixtures without changing other behavior/assertions.
- [x] Run normal RED (`1 xfailed`) and forced RED (one direct exact sentinel).
- [x] Run unchanged S8V1, S8P1/S8P2, S8E1, and S8L3 focused predecessors before production edits.

## Task 2: Add the finite omission-preserving selector

- [x] Add optional `professor_vector_view: Literal["identity", "research", "both"] | None` to
  recorded proposal, retrieval plan, and lane request; omit only `None` from JSON/content identity.
- [x] Require it for every Professor+vector recorded proposal and every planner-owned/release-bound
  plan; forbid stray selectors everywhere. Preserve missing-selector compatibility only for legacy
  unbound synthetic plans/requests, which the isolated adapter must still reject before effects.
- [x] Copy it unchanged proposal -> non-blocking plan -> vector request; blocking clarification and
  non-vector lane requests carry no selector. Do not inspect `QueryViewProposal.kind` or query text.
- [x] Preserve all legacy absent-field proposal/plan/request payloads and hashes.

## Task 3: Enable audited Professor point views

- [x] Replace the S8V1 Professor hard refusal with validated selector admission before effects.
- [x] Filter Professor points to identity, research, or both before the existing embedding/scoring
  batch; keep non-Professor default-view behavior and raw `max_candidates` truncation unchanged.
- [x] Derive one Professor display name from the unique public lookup document in the audited
  snapshot and require exact release/object/source-projection hash continuity through the validated
  `ProfessorProjection`, identity lookup view, and Professor lookup manifest projection ID; reject
  missing/duplicate/cross-wired authority.
- [x] Extend release-bound post-delegate validation so returned Professor point views must be allowed
  by the plan selector and returned fused-candidate/canonical-handle names must equal the same lookup
  authority; keep full S8V1 lineage/query/cosine validation.

## Task 4: Make GREEN and verify compatibility

- [x] Remove only the S8V2 xfail after the exact selector field exists; run focused GREEN (`1
  passed`).
- [x] Run S8V1 and S8 planning/execution predecessors, complete physical/release owner, query/
  KnowledgeRead owners, and complete no-external Canonical V2.
- [x] Run complete Ruff/format, changed-file compile, complete Pyright, strict OpenSpec, and
  `git diff --check`.

## Task 5: Package, review, and accept

- [x] Build one locked offline wheel, prove source/package parity and exclusions, then clean only the
  owned output after the receipt.
- [x] Recheck scope/secret/cache, original Milvus, paused PostgreSQL, recovery lab, and frozen target.
- [x] Obtain one independent review; repair every Critical/Important and rerun affected checks.
  Record Minor/YAGNI without blocking unless it proves a Spec/safety/model-valid bypass.
- [x] Create the secret-free receipt, mark S8V2 Accepted, synchronize existing evidence, keep Task
  8.3 open at `56/80`, and name the next independent real-lane Slice.
