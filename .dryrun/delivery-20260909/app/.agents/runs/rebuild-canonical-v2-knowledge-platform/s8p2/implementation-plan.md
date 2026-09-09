# S8P2 Planning Taxonomy and Assessment Intent Implementation Plan

> Execute with the active OpenSpec contract and strict RED -> GREEN discipline in the current
> authorized Canonical V2 worktree. Shared public-type edits require one writer. Do not commit.

**Goal:** Complete Task 8.2 by making recorded planning proposals machine-valid and by preserving a
lightweight assessment intent/user rubric through the existing release-bound planner.

**Architecture:** Deepen `knowledge_read.py`, where recorded proposals already enter the trusted
planning seam. Use finite Pydantic fields plus one cross-field matrix, normalize malformed provider
output at that boundary, and copy one shared optional `AssessmentIntent` into the resulting plan.
`knowledge_answer.py` re-exports that same type; no new module, planner, runtime propagation, or
assessment registry is introduced.

**Tech stack:** Python 3.12, Pydantic v2 immutable contracts, pytest strict-xfail RED/GREEN, Ruff,
Pyright, OpenSpec.

## Task 1: Freeze and prove the exact two-group RED

**Files:**

- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Add `_MissingS8P2ProposalTaxonomyValidation` and one strict-xfail synthetic owner that proves
  all five valid planning forms before enumerating every hostile taxonomy/cross-field payload from
  the Slice Contract. Same-class `model_construct` output must be among the hostile inputs.
- [x] Add `_MissingS8P2AssessmentIntentContract`, resolve the exact read-side symbol before fixture
  acquisition, and add one strict-xfail release-bound owner over the existing S8P1 physical fixture.
- [x] Keep all legacy hashes and existing assertions intact; do not add production symbols or edit
  any other test owner during RED.
- [x] Run the combined focused normal command and record exactly `2 xfailed, 52 deselected`.
- [x] Run it with `--runxfail` and record exactly `2 failed, 52 deselected`, one direct exact sentinel
  per test.
- [x] Run the unchanged query owner excluding the taxonomy RED and the shared physical owner excluding
  the assessment RED; prove no pre-existing regression.

## Task 2: Add the canonical lightweight intent and legacy omission

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`

- [x] Define `AssessmentIntent` once in `knowledge_read.py`: open trimmed non-empty `kind`, ordered
  tuple of trimmed non-empty unique `user_criteria`.
- [x] Add optional `assessment_intent` to `RecordedPlanningProposal` and `RetrievalPlan`.
- [x] Add wrap serializers that omit only absent intent (and continue omitting absent release binding)
  so pre-S8P2 payloads and hashes are byte/value identical.
- [x] Import/re-export the read-side type from `knowledge_answer.py`; remove the duplicate definition
  without changing `TurnRequest` behavior or answer logic.
- [x] Run the existing answer assessment owner, S9 atomic answer owner, S8P1 owners, and legacy hash
  assertions immediately after this edit.

## Task 3: Enforce finite proposal taxonomy and cross-field safety

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py`

- [x] Narrow schema, behavior, interaction, enumeration, internal-reference, and Web-mode fields to
  the finite values in the Slice Contract.
- [x] Extend `RecordedPlanningProposal` validation with the five valid cross-field forms; reject
  proposal-supplied blocking clarification and intent on non-information behavior.
- [x] Keep `AssessmentIntent.kind` open; do not infer an assessment kind from query text.
- [x] Call the provider outside the validation try block, then revalidate its returned value even when
  it is already the same class. Normalize returned-value validation errors to exact
  `InvalidRetrievalPlanError("invalid_planning_proposal")` without swallowing provider failures.
- [x] Extend the `RetrievalPlan` validator only for planner-owned/new-intent plans. Permit only the
  corresponding normalized forms plus server-derived no-lane blocking clarification. Preserve
  direct legacy KnowledgeRead plans without planner trace/release binding/intent.

## Task 4: Propagate intent through the existing release-bound planner

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Copy the validated proposal intent unchanged into the returned `RetrievalPlan`.
- [x] Prove its proposal trace and plan content identity change with the intent while release binding,
  institution resolution, Person filters, Technology route resolution, enumeration, lane order, and
  public/internal boundaries remain exact.
- [x] Reject blank kind, blank criterion, duplicate criterion, same-class hostile intent, and intent
  on non-information proposals.
- [x] Remove only the two strict-xfail marks after both previously missing behaviors are implemented.
- [x] Run focused GREEN; expect exactly `2 passed, 52 deselected`.

## Task 5: Close Candidate review findings with exact regressions

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Extend the existing query S8P2 owner, then prove Candidate RED for arbitrary model-authored
  `official_only` domains, negative/unbounded Web result limits, zero information provider calls,
  server policy max-provider-calls zero, and refusal/safety/control queries containing an ambiguous
  institution label.
- [x] Extend the existing physical S8P2 owner, then prove Candidate RED because the proposal cannot
  yet represent expected material answer parts.
- [x] Add an optional, server-owned official-Web allowlist to `QueryPlanningPolicy`; omit it when empty
  so existing policy hashes stay exact. Require every proposal allowlist to be a subset before plan
  construction.
- [x] Make `max_web_results` nonnegative, reject zero effective information-Web budgets, bound result
  counts by server policy, and never coerce a zero policy budget upward.
- [x] Reuse `MaterialQuestionPart` on `RecordedPlanningProposal`, require unique IDs, omit an empty
  legacy value, and copy non-empty parts unchanged into `RetrievalPlan`.
- [x] Derive ambiguity-based `blocking_clarification` only from validated information proposals;
  preserve refusal, safety, and interface-control interaction policy regardless of incidental entity
  strings.
- [x] Re-run the same two focused owners, S8P1 hashes, query/read/answer/physical owners, and broad
  checks. Obtain targeted re-review with zero open Critical/Important findings.
- [x] Record but do not block on the review's Minor request for two additional Literal-axis cases.

## Task 6: Proportional integration verification

**Files:**

- Test all changed owners and directly affected read/answer owners.
- Update evidence only after commands finish.

- [x] Run the complete query-planning owner (`5 passed`).
- [x] Run S8P1 focused (`2 passed`) and complete shared physical/release owner (`47 passed, 2 skipped`).
- [x] Run the complete KnowledgeRead owner matrix (`17 passed`).
- [x] Run answer assessment and complete KnowledgeAnswer owner matrix to prove the shared-type import
  did not change existing answer behavior.
- [x] Run complete no-external Canonical V2; expected `336 passed, 141 skipped, 0 xfailed`, recording
  actual counts and any known non-failing warnings.
- [x] Run Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec, and
  `git diff --check`.
- [x] Build one locked offline wheel in a disposable `/var/tmp` directory, inspect its entries, and
  compare packaged production source hashes with the worktree. Confirm no tests or `.agents` files.
- [x] Re-run package-entry, scope/secret/cache, original Milvus hash, recovery-lab state, and frozen-
  source/target gates. Clean only owned disposable package output after recording the receipt.

## Task 7: Review, repair, and accept

**Files:**

- Update: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p2/verification-receipt.json`
- Update: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Update: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Update: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Update: `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- Update: `.agents/portfolio.md`
- Update: `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`

- [x] Ask one independent reviewer to inspect current production/test/artifact diffs against the
  finite matrix, ADR-020, ADR-022, legacy compatibility, same-class bypass, and scope boundary.
- [x] Repair every Critical/Important finding and re-run affected checks; record Minor/YAGNI without
  blocking unless it proves a Spec/safety violation or model-valid bypass.
- [x] Create a secret-free content-bound receipt with exact hashes, commands, outcomes, external-state
  proofs, review disposition, and rollback.
- [x] Mark this contract Accepted only after all Required checks are current and review has zero open
  Critical/Important findings.
- [x] Check only Task 8.2, moving the ledger from `55/80` to `56/80`; keep `acceptance.md` unchanged.
- [x] Synchronize verification/change-log/agent-links/portfolio/mainline plan and identify the next
  independent Ready slice. Do not Commit, Push, PR, Archive, promote, or Cutover.
