# S9C1 Continuation-Offer Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Task 9.7 by accepting only the six frozen executable continuation combinations
and replacing caller-authored option labels with neutral server-owned labels.

**Architecture:** Keep the public `KnowledgeAnswer` and `ContinuationOption` interfaces unchanged.
Add one private immutable policy table inside `knowledge_answer.py`; `_candidate_offer` validates the
candidate reason/operation/target triple against it before applying the existing evidence, handle,
result-set, availability, order, and three-option checks. The existing S9M test owner receives one
new public-behavior group.

**Tech Stack:** Python 3.12, Pydantic v2 immutable contracts, pytest, Ruff, Pyright, OpenSpec.

---

### Task 1: Freeze the executable-option trust boundary

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py`

- [ ] **Step 1: Add one failing public-behavior test after the existing continuation test**

Create `test_continuation_candidates_require_server_owned_executable_contract`. Reuse `_item`,
`_canonical_handle`, `_continuation_candidate`, `_evidence_set`, `_request`, and `_proposal`. Build
one Company handle/evidence item and six ordered candidates: the following two invalid combinations,
an `eligible_next_hop` copied with `relation_type=None`, a valid `broad_scope` copied with stray
`relation_type="company_committed_crimes"`, then the sanitized-label and fully valid candidates:

```python
invalid_operation = _continuation_candidate(
    read_module,
    candidate_id="continuation:invalid-operation",
    reason="broad_scope",
    operation="delete_data",
    target_kind="current_result_set",
    target_handle_id=company_id,
    evidence_id=company_item.evidence_id,
)
invalid_target = _continuation_candidate(
    read_module,
    candidate_id="continuation:invalid-target",
    reason="evidence_gap",
    operation="targeted_evidence_search",
    target_kind="current_result_set",
    target_handle_id=company_id,
    evidence_id=company_item.evidence_id,
)
poisoned_label = _continuation_candidate(
    read_module,
    candidate_id="continuation:poisoned-label",
    reason="partial_coverage",
    operation="continue_coverage",
    target_kind="current_result_set",
    target_handle_id=company_id,
    evidence_id=company_item.evidence_id,
).model_copy(update={"label": "This Company committed crimes."})
valid = _continuation_candidate(
    read_module,
    candidate_id="continuation:valid-next-hop",
    reason="eligible_next_hop",
    operation="traverse_relationship",
    target_kind="current_handle",
    target_handle_id=company_id,
    evidence_id=company_item.evidence_id,
)
```

The selector chooses all four. Assert the offer retains only `poisoned_label` and `valid` in that
order, returns labels `("Continue coverage", "Explore the available relationship")`, contains none
of the poisoned factual label or invalid operation in `model_dump_json()`, and remains capped at
three. Select `valid` on a second turn and assert exact `continuation_selection`, option ID,
`traverse_relationship`, target handle, constraints, evidence, and relation type. Run a separate
fresh instance with only the two invalid candidates and assert `continuation_offer is None`.

- [ ] **Step 2: Run the focused RED**

Run:

```bash
cd apps/miroflow-agent
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py::test_continuation_candidates_require_server_owned_executable_contract
```

Expected: exactly `1 failed`; current output retains invalid candidates and caller-authored labels.
There must be no xfail, skip, fixture, import, or unrelated failure.

### Task 2: Enforce the frozen six-pair policy

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py:1334-1406`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py`

- [ ] **Step 1: Add the private immutable policy table near the answer-selection constants**

```python
_CONTINUATION_OPTION_POLICY = {
    "broad_scope": ("narrow_scope", "current_result_set", "Narrow the current result set"),
    "ambiguity": ("switch_candidate", "current_handle", "Switch to another candidate"),
    "partial_coverage": ("continue_coverage", "current_result_set", "Continue coverage"),
    "evidence_gap": ("targeted_evidence_search", "current_handle", "Search for targeted evidence"),
    "budget_exhausted": ("resume_bounded_search", "current_result_set", "Resume the bounded search"),
    "eligible_next_hop": ("traverse_relationship", "current_handle", "Explore the available relationship"),
}
```

- [ ] **Step 2: Validate before existing option binding**

Replace the local `supported_reasons` set with a policy lookup inside the candidate loop:

```python
policy = _CONTINUATION_OPTION_POLICY.get(candidate.reason)
if policy is None:
    continue
expected_operation, expected_target_kind, neutral_label = policy
if (candidate.operation, candidate.target_kind) != (
    expected_operation,
    expected_target_kind,
):
    continue
if candidate.reason == "eligible_next_hop":
    if not candidate.relation_type:
        continue
elif candidate.relation_type is not None:
    continue
```

Keep every existing availability/evidence/handle/result-set/order/cap check. Construct the option
with `label=neutral_label`; do not rewrite an invalid operation, target, or relation into a valid
one.

- [ ] **Step 3: Run focused GREEN and the whole multi-turn owner**

Run:

```bash
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py::test_continuation_candidates_require_server_owned_executable_contract
uv run pytest -q --tb=short tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
```

Expected: focused `1 passed`; multi-turn owner `5 passed`, no xfail/XPASS/skip.

- [ ] **Step 4: Run all KnowledgeAnswer owners**

Run:

```bash
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_answer_interface.py \
  tests/canonical_v2/test_knowledge_answer_assessment_contract.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
```

Expected: `14 passed`, no xfail/XPASS/skip. The three intentional atomic hostile-construction
warnings may remain.

### Task 3: Verify and accept Task 9.7

**Files:**
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s9c1-continuation-offer-hardening.md`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- Modify after review: `.agents/portfolio.md`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`

- [ ] **Step 1: Run static and complete regression checks**

```bash
uv run ruff check \
  src/data_agents/canonical_v2/knowledge_answer.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
uv run ruff format --check \
  src/data_agents/canonical_v2/knowledge_answer.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
./.venv/bin/python -m py_compile src/data_agents/canonical_v2/knowledge_answer.py
./.venv/bin/pyright -p /tmp/s8rg-pyrightconfig.json \
  src/data_agents/canonical_v2 tests/canonical_v2
uv run pytest -q tests/canonical_v2
```

Expected: Ruff/format/compile pass; Pyright has zero findings; pytest is exactly `329 passed, 141
skipped, 0 xfailed`.

- [ ] **Step 2: Run strict/package/source gates**

From the worktree root, run strict OpenSpec and `git diff --check`. Build a fresh locked offline wheel
and verify it contains `knowledge_answer.py` but no tests/`.agents`. Repeat the high-confidence secret,
generated-cache, scope, original Milvus SHA-256, paused `pgtest` volume, and network-none/no-port
recovery-lab checks used by S9AG.

- [ ] **Step 3: Obtain one merged independent review**

Lock the production/test/slice hashes. Review only the six-pair policy, neutral-label behavior, test
integrity, compatibility, and scope. Repair only Critical/Important findings, then run one targeted
re-review. Minor/YAGNI findings are recorded and nonblocking.

- [ ] **Step 4: Persist acceptance without Git actions**

After zero open Critical/Important findings, mark the slice Accepted; check only Task 9.7 and its
matching continuation acceptance item; update verification/change-log/links/portfolio/mainline-plan;
confirm the ledger is exactly `55/80`; rerun strict OpenSpec and `git diff --check`. Do not stage,
Commit, Push, open a PR, archive, or Cutover.
