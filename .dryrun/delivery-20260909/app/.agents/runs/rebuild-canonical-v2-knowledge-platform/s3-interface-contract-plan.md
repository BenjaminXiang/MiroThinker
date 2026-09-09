# Canonical V2 Deep Module RED Interface Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one intentional RED public-interface contract for each of the five Canonical V2 deep
modules without implementing production behavior or touching a database.

**Architecture:** Each module keeps one small public seam and hides future adapters/implementation.
Tests dynamically import the future module, construct its typed request/results, and use a local
recording adapter to prove caller-visible behavior. `pytest.mark.xfail(strict=True)` preserves a
green normal suite while `--runxfail` records genuine RED; the strict marker turns future accidental
XPASS into a failure until the RED marker is deliberately removed.

**Tech Stack:** Python 3.12, Pydantic v2 contracts, `typing.runtime_checkable` protocols, pytest 8,
Ruff, Pyright, OpenSpec.

---

### Task 1: EvidenceLanding ingest/stream contract

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_evidence_landing_interface.py`

- [x] Dynamically import `src.data_agents.canonical_v2.evidence_landing` inside one strict-xfail test.
- [x] Construct `IngestEvidenceRequest` with `run_id`, `source_batch_id`, `source_kind`,
  `source_locator`, byte `content`, and `observed_at`.
- [x] Implement a local recording adapter satisfying `EvidenceLanding.ingest/stream`; return a
  typed `LandingReceipt` plus typed `SourceRecord` values.
- [x] Assert SHA-256 byte identity, byte count, accepted status, batch/run lineage, no active-release
  mutation, and replayable record locator/parse outcome through only the public interface.
- [x] Run normal and `--runxfail`; expected normal result is one xfail, expected forced result is one
  `ModuleNotFoundError` for the future module.

### Task 2: KnowledgeBuild isolated-candidate contract

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_interface.py`

- [x] Dynamically import `src.data_agents.canonical_v2.knowledge_build` inside one strict-xfail test.
- [x] Construct `BuildCandidateRequest` with run/candidate IDs, source batches, parser versions,
  policy versions, and model versions.
- [x] Use a local recording adapter satisfying `KnowledgeBuild.build` and return typed
  `CandidateRelease`.
- [x] Assert the candidate retains input/version lineage, has a manifest SHA, reports typed
  object/relationship counts, remains `candidate`, and does not change the active release.

### Task 3: KnowledgeRead traceable evidence contract

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_interface.py`

- [x] Dynamically import `src.data_agents.canonical_v2.knowledge_read` inside one strict-xfail test.
- [x] Construct a typed `RetrievalPlan` retaining original query, A-G class, accepted release,
  domains, exact protected slot, exact/vector/Web lanes, and candidate budget.
- [x] Use a local recording adapter satisfying `KnowledgeRead.execute`; return typed local/Web
  `EvidenceItem`, `RetrievalTrace`, and `EvidenceSet` values.
- [x] Assert original query/protected slot/release survive, evidence keeps source nature/locator,
  every lane is traceable, and no caller-visible storage/collection detail is required.

### Task 4: KnowledgeAnswer claim-evidence contract

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_interface.py`

- [x] Dynamically import both future `knowledge_read` types and
  `src.data_agents.canonical_v2.knowledge_answer` inside one strict-xfail test.
- [x] Construct a typed `EvidenceSet` and `TurnRequest` with session/turn/release identity.
- [x] Use a local recording adapter satisfying `KnowledgeAnswer.answer`; return typed
  `MaterialClaim` and `TurnResult` with local/Web disclosure and no unsupported follow-up.
- [x] Assert every material claim references retrieved evidence, source natures remain distinct,
  release/session/turn identity survives, and unsupported limitations/followups are not invented.

### Task 5: ReleasePublication verify/promote/rollback contract

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_release_publication_interface.py`

- [x] Dynamically import `src.data_agents.canonical_v2.release_publication` inside one strict-xfail
  test.
- [x] Use a local stateful recording adapter satisfying `verify`, `promote`, and `rollback`.
- [x] Return typed `ReleaseVerification` and `PublishedRelease` values.
- [x] Assert promotion occurs only after accepted exact parity, canonical/publish/index release IDs
  remain one version, and rollback returns the prior accepted release without rewriting evidence.

### Task 6: Verify and record Task 3.1

**Files:**
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s3a-deep-module-interface-red.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-interface-contract-plan.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

- [x] Run normal focused pytest with `-n0`; require exit `0`, five xfails, zero failures/errors/XPASS.
- [x] Run the same files with `--runxfail`; require exit `1`, five expected missing-module failures,
  and no collection/syntax/setup error.
- [x] Run Ruff, Pyright, strict OpenSpec, `git diff --check`, and source-invariant hash/pause checks.
- [x] Mark task 3.1 and the slice Accepted, record exact RED/normal commands, stage only this task,
  and create one task-level commit. Do not start task 3.2 in the same commit.

## Self-review

- Spec coverage: all five methods from design decision 6 have one independently named contract;
  landing/release/query/answer outcomes trace to their owning capability specs.
- Placeholder scan: no production placeholder or unreviewed factual behavior is introduced;
  intentional missing modules are the explicit RED condition.
- Type consistency: release IDs, run IDs, source batches, protected slots, evidence IDs, and
  claim-evidence references retain one name and direction across the five contracts.
