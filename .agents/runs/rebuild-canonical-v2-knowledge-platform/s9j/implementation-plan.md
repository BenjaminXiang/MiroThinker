# Public Answer Integrity Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep audit identifiers structured-only while rendering grounded supported facts and every
material sufficiency gap as useful public answer copy.

**Architecture:** Deepen the existing `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` module.
The module validates selector copy and owns sufficiency-to-limitation/prose projection; HTTP and UI
remain adapters. The recorded S11A selector supplies semantic fixture copy without changing the
binding triple, and the built-in UI only localizes a known continuation operation.

**Tech Stack:** Python 3.12, Pydantic, pytest, FastAPI TestClient, static DOM-safe JavaScript, Ruff,
Pyright, agent-browser.

**Status:** Candidate at `2026-07-21T09:48:56Z`; Accepted at `2026-07-21T09:57:11Z`; formal ledger
unchanged at `65/80`.

---

### Task 1: Freeze public-copy and material-gap RED

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`

- [x] Add a KnowledgeAnswer scenario with a supported semantic claim and a validated
  `MaterialQuestionPart(text="核实 Robotics Co 的 2026 年当前营收", ...)` whose sufficiency outcome
  is `missing`; assert exact code `material_evidence_missing`, one typed material limitation, and a
  public gap sentence derived from predicate/year rather than `MaterialQuestionPart.text`.
- [x] Add `conflicting` coverage for exact code `material_evidence_conflicting`, plus a duplicate
  case proving an existing specialized material limitation for the same part ID wins.
- [x] Add hostile part text containing an invented fact/internal ID; assert no byte from that text is
  copied into the public answer.
- [x] Add a parameterized public-copy matrix for digest-valued `canonical_projection` and
  `semantic_recall` bindings plus canonical/reference relationship values. Assert the structured
  value remains admitted but never appears in `MaterialClaim.text` or `TurnResult.answer_text`.
- [x] Strengthen the exact S11A first-turn HTTP assertions: public strings contain `Robotics Co` and
  the 2026 revenue evidence gap, contain no 64-hex digest/typed ID/raw enum, while trace binding,
  sufficiency, and continuation operation remain exact.
- [x] Add a hostile `ProseRenderer` case that returns an audit digest and omits the gap sentence;
  assert deterministic fallback, exact `prose_synthesis_failed/unsafe_output`, and retained
  server-owned material-gap copy.
- [x] Preserve honest RED evidence: the original pre-implementation terminal output was not retained,
  so it is not invented here. The acceptance audit reproduced an exact four-failure escaped-branch
  RED plus three mutation-sensitivity failures before the shared repair; all are recorded in the
  receipt.

### Task 2: Implement the deep-module correction

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`

- [x] Add one private predicate/value-aware check that rejects the unsafe selector proposal before
  claim admission when public text contains an exact internal binding value for digest projection
  predicates or `canonical:`/`reference:` values. Do not rewrite the unsafe claim.
- [x] Convert every material `missing` or `conflicting` sufficiency part into one stable
  `AnswerLimitation(material=True, stage="sufficiency", material_part_id=...)` with exact codes
  `material_evidence_missing` / `material_evidence_conflicting`; suppress it when a specialized
  material limitation already owns the same part ID.
- [x] Append deterministic public sentences from a narrow server-owned label helper: only exact
  four-digit `current_revenue` values receive a year-specific label; other predicates receive a
  generic localized material-part label. Never render caller/planner `part.text`.
- [x] Treat prose output as untrusted final copy: reject structured-only values/IDs/raw enums to the
  deterministic fallback with `prose_synthesis_failed/unsafe_output`; append required gap sentences
  after safe prose unless the exact sentence is already present.
- [x] Run Task 1 core nodes. Expected: pass; then run the affected answer/session owner files.

### Task 3: Correct the recorded selector and public continuation copy

**Files:**
- Modify: `apps/admin-console/backend/services/canonical_v2_chat.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`
- Modify: `apps/admin-console/backend/static/chat.html`
- Modify: `apps/admin-console/tests/test_canonical_v2_consumer_migration.py`

- [x] Replace the recorded selector's `binding.value` interpolation with a private fixture helper
  that parses the already-validated local snippet, binds the entity handle, and emits semantic
  profile or typed relationship text while preserving subject/predicate/value/evidence/status.
- [x] Map `targeted_evidence_search` to the public label `继续检索针对性证据` in the built-in UI;
  keep the structured operation and option ID unchanged.
- [x] In the S11A HTTP adapter, map all six accepted continuation reason/operation pairs to bounded
  server-owned public prompt/label/hint strings; keep raw reasons/operations only in the structured
  trace and next-turn selection contract.
- [x] Render typed sufficiency limitations with user-facing labels; never synthesize a missing fact.
- [x] Run the exact S11A and S11B owner nodes. Expected: both pass with the new public-copy
  assertions; run the S10O UI owner to prove compatibility.

### Task 4: Verify and accept the correction

**Files:**
- Create after evidence: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s9j/verification-receipt.json`
- Modify after review: this contract/plan and the existing S11A/S11B verification pointers/hashes
  required by the correction.

- [x] Run Ruff check/format, `py_compile`, changed-scope Pyright, inline JavaScript parse,
  `openspec validate rebuild-canonical-v2-knowledge-platform --strict`, and `git diff --check`.
- [x] Start a replacement disposable Candidate on a separate port. The exact synthetic public-copy
  fixture remained owned by the S11A test; the browser replay used manifest-selected real entities
  per the user's no-fake-data requirement, covering two turns, desktop/mobile, API trace, and clean
  console before stopping the verifier without replacing ports `18188/18189`.
- [x] Obtain independent spec-compliance review, then independent code-quality review. Repair only
  Critical/Important findings and re-review those repairs.
- [x] Record Candidate/Accepted evidence and synchronize affected hashes. Do not Commit, Push, PR,
  Cutover, promote, archive, or touch original sources.

## Rollback checkpoint

Revert only the S9J answer, fixture, static renderer, tests, and S9J evidence bytes. The currently
running port-18188 preview stays available until the replacement is proven.
