# Canonical V2 Shared Typed Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a storage-independent Pydantic interface for all shared Canonical V2 domain
concepts named by OpenSpec task 3.3.

**Architecture:** `src.data_agents.canonical_v2.contracts` is the single caller-facing seam. It
contains frozen, extra-forbid Pydantic values and semantic validators, but no repository methods or
physical schema knowledge. Known workflow states are enums; extensible catalog identifiers such as
source kind, field path, relationship type, role, policy ID, and scenario family remain validated
opaque strings.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, Ruff, Pyright.

---

### Task 1: Add RED evidence and assertion contracts

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_shared_contracts.py`

- [x] Add valid chain-of-custody cases for `EvidenceArtifact`, typed `SourceError`, replayable
  `SourceRecord`, append-only `SourceAssertion`, and `RelationshipAssertion`.
- [x] Require timezone-aware observation/acquisition times, exact SHA-256, parser/version/locator,
  and source identity/evidence links.
- [x] Prove invalid record outcomes without typed errors and reversed validity intervals fail.

### Task 2: Add RED decision, identity, and relationship contracts

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_shared_contracts.py`

- [x] Cover selected and unresolved `CanonicalDecision` histories without deleting assertions.
- [x] Cover `SourceIdentity`, `CanonicalIdentity`, and create/link/merge/split/reversal
  `IdentityDecision` lineage.
- [x] Cover extensible `RelationshipType` endpoint/direction/role/evidence/time/path metadata.
- [x] Prove canonical/derived/session layer distinctions and accepted/unresolved relationship
  decisions retain the correct evidence.

### Task 3: Add RED policy and knowledge-gap contracts

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_shared_contracts.py`

- [x] Cover versioned inclusion and named-path `PolicyReference`/`PolicyDecision` values.
- [x] Prove limited decisions require visible limitations and excluded decisions require named hard
  invariants while ordinary incompleteness remains representable as admitted/limited.
- [x] Cover every required `GapClass`, demand/PRD impact, evidence, review state, and remediation.
- [x] Prove resolved gaps require an accepted release plus verification evidence.

### Task 4: Add RED release and manifest contracts

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_shared_contracts.py`

- [x] Cover `CandidateRelease`, projection/index manifests, `BuildManifest`, release verification,
  publication, and rollback identities.
- [x] Require counts/hashes and source/parser/policy/model/decision/eligibility/publication/index
  version lineage.
- [x] Prove mixed projection release IDs and accepted parity with unexplained deviations fail.
- [x] Verify JSON-mode dumps preserve all IDs/versions and contain no physical table/collection
  contract.

### Task 5: Implement the shared contract seam

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/contracts.py`

- [x] Add shared constrained scalars, enums, frozen base model, temporal/hash validators, and the
  evidence/assertion family.
- [x] Add canonical/identity/relationship decision families with evidence and reversal lineage.
- [x] Add policy/gap families with soft limitation and named hard-exclusion semantics.
- [x] Add release/manifest families with one-release and exact-parity invariants.
- [x] Keep extensible identifiers open and domain business facts out of the shared assertion seam.

### Task 6: Verify, accept, and commit Task 3.3

**Files:**
- Modify: this plan and its slice contract.
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

- [x] Record focused RED caused only by the absent contracts module.
- [x] Run focused GREEN, Task 3.1/3.2 regression, S1, S2/S2B, Ruff, Pyright, strict OpenSpec, and
  diff checks.
- [x] Re-check original/candidate identities without writing either database or Milvus.
- [x] Mark Task 3.3 Accepted, stage only this task, and make one task-level commit. Do not begin
  Task 3.4 in the same commit.

## Design review

- Deep module: one import seam hides validation and cross-family consistency from every later
  adapter/builder/reviewer.
- Domain language: evidence, assertions, decisions, identities, relation layers, eligibility, gaps,
  releases, and manifests remain separate values rather than overloaded status/JSON fields.
- Extensibility: catalog identifiers are open strings; workflow invariants use closed states.
- Effect-first strictness: hard contradictions fail, while missing enrichment/conflict/uncertainty
  remain explicit valid states instead of disappearing behind gates.
