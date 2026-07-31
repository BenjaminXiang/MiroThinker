# S12D Relation-Aware Answer Scope Implementation Plan

> **For agentic workers:** Execute inline in the existing isolated worktree. TDD RED/GREEN evidence
> is required before each production-code change; no subagent or additional worktree is required.

**Goal:** Correct headquarters and direct Product-capability follow-ups systemically while preserving
one final LLM call and committing only answer-selected entities to the next turn.

**Architecture:** Keep `KnowledgeAnswer` as the external deep-module seam. The serving adapter derives
a small deterministic question frame and types current-Web relation evidence. The existing prose LLM
receives numbered candidates and returns answer text plus selected indexes; `KnowledgeAnswer`
validates and atomically applies that selection before the chat adapter commits the session.

**Tech Stack:** Python 3.12, Pydantic, OpenAI-compatible Qwen client, pytest, FastAPI.

---

### Task 1: Freeze relation semantics and provider subject scope

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`

- [x] Add a parameterized RED matrix for headquarters versus registered/office/branch/service/name
  geography and for Product-capability conjunction.
- [x] Add a RED provider-query test proving both Bocha and Serper retain compact displayed-entity
  anchors for headquarters and capability follow-ups.
- [x] Run the focused tests and confirm the expected semantic failures.
- [x] Implement the minimum deterministic question frame and relation-aware Web binding/query views.
- [x] Re-run the focused tests to GREEN.

### Task 2: Make one prose call own validated answer selection

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`

- [x] Add a RED test where the LLM selects one of two Company entities and only that entity becomes
  the next-turn displayed set; selected claim indexes alone retain answer citations.
- [x] Add RED malformed-index and plain-text compatibility cases.
- [x] Run the focused tests and confirm the expected session-scope failure.
- [x] Add one internal structured prose result, numeric-index validation, claim/citation filtering,
  and atomic post-prose session narrowing.
- [x] Re-run the focused tests to GREEN without adding another model call.

### Task 3: Verify the real serving path

**Files:**
- Modify after evidence exists: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify after evidence exists: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify after evidence exists: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify after evidence exists: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

- [x] Run the complete serving module, Admin HTTP adapter, public UI/privacy, Ruff, Pyright, strict
  OpenSpec, and `git diff --check` commands.
- [x] Restart the read-only Candidate on `0.0.0.0:18188`.
- [x] Replay supplier -> Shenzhen headquarters -> mechanical-arm elevator -> access-card/door in one
  session, record each turn's complete HTTP time, and inspect only official public citations.
- [x] Re-check the original Milvus hash and Candidate active-pointer count.
- [x] Mark tasks and acceptance only for conditions demonstrated by fresh evidence.

Rollback is a source-code revert plus restart of the prior Candidate process. No database, index,
source artifact, active pointer, public response schema, or provider-call budget changes.
