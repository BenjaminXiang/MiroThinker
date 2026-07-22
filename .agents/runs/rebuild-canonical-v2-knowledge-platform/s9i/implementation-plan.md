# S9I Grounded Assessment/Session Implementation Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use
> superpowers:test-driven-development for every RED/GREEN cluster and
> superpowers:verification-before-completion before Candidate/Accepted claims. Steps use checkbox
> (`- [ ]`) syntax for tracking. One writer owns the production module and all answer owner edits.
> Do not Commit.

**Goal:** Close OpenSpec Tasks 9.2, 9.4, and 9.6 through one evidence-bound answer/assessment/session
vertical slice while preserving the already-Accepted S9 mechanics.

**Architecture:** Deepen the existing `knowledge_answer.py` module rather than introducing another
service. Strengthen proposal validation and sanitized rendering, add observable selector traces and
typed answer-side directives, then prove a real public `KnowledgeRead.execute` result flows into the
same answer seam. Keep all state ephemeral and all safety rendering server-owned.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan is **Ready** at `2026-07-20T11:07:04Z`. S8C is Accepted, and the fresh five-owner
KnowledgeAnswer baseline is `14 passed` with only three pre-existing hostile-`model_construct`
serializer warnings. Independent review of the corrected dependency audit, plan, contract, relevant
OpenSpec requirements, and live answer seam reports `Critical=0/Important=0/Minor=0/YAGNI=0`.
Reviewed Specified hashes are audit
`16b3e4b5fddd24964d1eb962fc7780368ae06de1b50b916cc55fe66674ad20cd`, plan
`fd515998e2f1d1470fcbeef6659a249f25e94f3cdd0355cf565f1155dba7b320`, and contract
`4db71e71725f744aa2cef2e5e94c6adc2ea82f4d9de18859afe3ff5c5d831b4a`. The review explicitly closes
the three Important findings and ordinal Minor without changing the exact six-test-function owner
or authorized scope. No Commit, Push, PR, Cutover, or ledger edit is authorized.

This plan reached **Candidate** at `2026-07-20T11:58:44Z`. The initial exact six-group RED, review
counterexample RED, final focused/complete verification, frozen package/source evidence, and final
independent `Critical=0/Important=0/Minor=0/YAGNI=0` disposition are recorded in
`s9i/verification-receipt.json`. Candidate does not check Tasks 9.2/9.4/9.6 or modify any formal
acceptance/status ledger; Task 9.8 remains open and excluded.

## File map

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`: strengthened claim
  gate, sanitized rendering, selector traces, assessment evidence relevance/degradation, typed
  session directives/release binding, and bounded safety rendering.
- Create `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`:
  exactly six S9I RED/GREEN groups, including the real KnowledgeRead-to-Answer vertical owner.
- Modify only as mechanically necessary:
  `test_knowledge_answer_atomic_green_contract.py`, `test_knowledge_answer_interface.py`,
  `test_knowledge_answer_assessment_contract.py`, `test_knowledge_answer_grounding_contract.py`, and
  `test_knowledge_answer_multiturn_contract.py` for new required proposal metadata, exact assessment
  bindings, typed directives, and complete structured claim fixtures.
- Update S9I receipt/evidence and existing status ledgers only after Candidate review. Do not edit
  another production/test file, create a new OpenSpec change, or touch Task 9.8.

## Task 1: Freeze the Ready gate

**Files:**
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s9i/dependency-audit.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s9i-grounded-assessment-session-implementation-closure.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s9i/implementation-plan.md`

- [x] **Step 1: Verify the runtime predecessor**

Read the live S8 contract/receipt/verification evidence and confirm the designated aggregate S8
real-read runtime predecessor is `Accepted`, not merely Ready/In Progress/Candidate. Under the
current convergence plan this is S8C after S8R4/S8R5. If it is not Accepted, leave S9I `Specified`
and continue the S8 critical path; do not edit S9 production/tests.

- [x] **Step 2: Capture the live baseline**

From `apps/miroflow-agent`, run:

```bash
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_answer_interface.py \
  tests/canonical_v2/test_knowledge_answer_assessment_contract.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
```

Expected: the live five-owner matrix passes with no fail/error/skip/xfail/XPASS. Record the actual
count; do not assume the historical `14 passed` after concurrent Accepted work.

- [x] **Step 3: Obtain one lean independent contract/plan review**

Review exact task coverage, trace ownership, assessment relevance, session release semantics,
safety predicate bounds, real-read test integrity, and allowed scope. Repair Critical/Important
only; record Minor/YAGNI without adding gates.

- [x] **Step 4: Mark Ready**

After zero open Critical/Important findings, record UTC timestamp plus exact Specified contract/plan
hashes, mark both Ready, and run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`. No Commit/Push/PR/Cutover.

## Task 2: RED/GREEN complete claim binding, sanitized rendering, and answer trace

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py:148-242,382-526,740-930`
- Modify as required: five existing answer owners listed in the file map

- [x] **Step 1: Add all six owner groups before any production edit**

Create the complete new owner with these exact groups before changing `knowledge_answer.py`:

1. `test_material_claim_requires_complete_binding_and_filtered_draft_never_leaks`;
2. `test_answer_selector_trace_binds_model_prompt_schema_run_and_visible_rejection`;
3. `test_assessment_replays_evidence_relevance_and_degrades_visibly`;
4. `test_typed_session_directive_owns_referents_topic_switch_and_release_boundary`;
5. `test_safety_guidance_is_server_owned_bounded_and_official_snapshot_grounded`;
6. `test_real_knowledge_read_result_flows_to_grounded_answer_and_assessment`.

Tasks 2-6 below define every fixture and assertion. Finish all six groups now so the initial RED
receipt covers the whole slice rather than adding a nominal integration test after its implementation
already exists.

The first group submits one exact bound claim plus missing-subject, missing-predicate, missing-value,
mismatched-binding, and unknown-evidence traps. Give every trap a unique poison token and put all
tokens in `proposal.answer_text`. Assert the result contains only the exact claim; every admitted
claim/mapping has a non-empty subject/predicate/value/evidence tuple; citations use only the admitted
ID; and no rejected token or raw draft appears anywhere in `result.model_dump_json()`.

In that same first group, retain one material `EvidenceConflict` whose evidence items share the
claim subject/predicate but preserve different values/statuses. Admit a complete conflicting proposal
whose evidence IDs exactly match that conflict and whose existing legal proposal value is
`"conflicting"`; do not require that sentinel value or one status to equal every cited binding. Add
in-test traps for a partial triple, subject/predicate mismatch, non-exact conflict evidence IDs, and
flattened/equalized conflict evidence. Supported claims continue to require exact full binding.

The second group requires accepted answer metadata and a public server-owned trace:

```python
AnswerSelectionProposal(
    selection_input_sha256=request.content_sha256,
    schema_version="answer-selection-v1",
    decision_id="answer-selection:s9i:valid",
    model_id="recorded-answer-selector",
    prompt_version="answer-selector-prompt-v1",
    decision_run_id="answer-selector-run:s9i:valid",
    answer_text="NON_AUTHORITATIVE_RAW_DRAFT",
    claims=(valid_claim,),
)
```

Assert the accepted trace exactly binds those fields and the request hash. Exercise wrong input,
wrong schema, and schema-invalid `model_construct` output in one ordinary loop inside this exact test
function; do not use pytest parameterization. Add a `TimeoutError` selector subcase in the same
function. Every hostile subcase must produce a degraded answer-stage trace and
`answer_selection_rejected` limitation, no claims/session mutation, and no untrusted metadata/draft
echo. Timeout visibly returns the deterministic grounded fallback rather than escaping the public
answer seam.

- [x] **Step 2: Observe the exact six-group RED, then focus the first cluster**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k 'material_claim_requires_complete_binding or answer_selector_trace_binds'
```

Expected: the complete owner is exactly six intended failures, one per named current gap, with no
collection/import/fixture error; the focused command is exactly two intended failures because
partial claims/raw draft survive and selector trace/metadata fields are absent. Store both outputs
before the first production edit. Do not use xfail wrappers.

Recorded before the first production edit and persisted at `2026-07-20T11:31:27Z`:

- complete command exited `1` with exact `6 failed in 2.04s` and no collection/import/fixture
  error: partial claims survived; answer-selector metadata fields were absent;
  `AssessmentEvidenceBinding`, `SessionDirective`, and `SafetyGuidanceDirective` were absent; and
  the real-read group completed its public `KnowledgeRead.execute` trace/item/current-Web snapshot
  assertions before failing only on the strengthened answer selector model/prompt/run fields;
- focused group-1/group-2 command exited `1` with exact `2 failed, 4 deselected in 0.40s`, at partial
  claim survival and the three absent answer-selector identity fields respectively;
- collection was exact `6 tests collected`, and pre-RED Ruff/`py_compile` passed for the new owner.

- [x] **Step 3: Add the minimal public records and claim gate**

Implement these shapes in `knowledge_answer.py`:

```python
class SelectorDecisionTrace(ContractModel):
    stage: Literal["answer_selection", "assessment_selection"]
    schema_version: str
    selection_input_sha256: str
    outcome: Literal["accepted", "degraded"]
    decision_id: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    decision_run_id: str | None = None
    failure_kind: str | None = None

class AnswerSelectionProposal(ContractModel):
    # Retain existing fields.
    model_id: str
    prompt_version: str
    decision_run_id: str

class TurnResult(ContractModel):
    # Retain existing fields.
    selector_traces: tuple[SelectorDecisionTrace, ...] = ()
```

Use `Literal` from `typing`. Require a complete triple and exact evidence binding for factual
claims, applying exact full binding to supported claims and the retained-material-conflict rule to
conflicting claims; keep the existing inference and unsupported-Product semantics exactly as frozen
in the Slice Contract. Build normal `answer_text` from the admitted claim set and server-owned
messages; never copy or retain `proposal.answer_text`. Move the answer-selector call inside its
validation/degradation boundary and catch `TimeoutError` there. Construct accepted/degraded traces
on the server. Give `_default_proposal` explicit `server-deterministic` / `answer-default-v1` /
turn-bound run identities so selector-free assessment/session calls remain valid without pretending
an external model ran.

- [x] **Step 4: Mechanically update existing proposal fixtures**

Add stable recorded `model_id`, `prompt_version`, and `decision_run_id` to all valid/hostile proposal
factories. Upgrade the S9M claim helper to derive the exact first retained `EvidenceClaimBinding`
for each claim rather than emitting an unstructured claim. Do not remove any Accepted hostile case
or loosen exact assertions.

- [x] **Step 5: Prove GREEN and compatibility**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k 'material_claim_requires_complete_binding or answer_selector_trace_binds'
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_answer_interface.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
```

Expected: `2 passed` focused; all selected predecessor owners pass with no hidden outcome.

## Task 3: RED/GREEN evidence-relevant AssessmentFrame and visible degradation

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_assessment_contract.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py:179-262,529-600,861-900`

- [x] **Step 1: Focus the already-recorded third RED group**

Add exact group `test_assessment_replays_evidence_relevance_and_degrades_visibly`.

Use exact bound evidence for one arbitrary LLM-selected dimension, an unrelated current-turn item
for a poison conclusion, a retained material conflict for one user criterion, and model-memory for
one missing criterion. Require answer-stage and assessment-stage traces. Assert:

- explicit criteria remain ordered; unprescribed dimensions do not displace them;
- a supported dimension replays its exact evidence binding;
- conflicting evidence is accepted only with the matching `EvidenceConflict`;
- unrelated/model-memory evidence becomes `insufficient_evidence` or is omitted;
- poison conclusion/synthesis is absent;
- wrong assessment input/schema/shape leaves base grounded claims intact but adds a visible
  assessment limitation and degraded assessment trace;
- assessment-selector `TimeoutError` is another subcase of this same test function, preserves the
  grounded answer, and adds `assessment_selection_rejected` plus a degraded assessment-stage trace;
- free dimension names remain allowed, at most three, with no registry/score/weights.

- [x] **Step 2: Observe exact RED**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k assessment_replays_evidence_relevance
```

Expected: one failure because the current helper accepts ID membership without exact relevance and
silently returns `None` on selector rejection.

- [x] **Step 3: Implement exact evidence-use records and degradation**

```python
class AssessmentEvidenceBinding(ContractModel):
    evidence_id: str
    subject_id: str
    predicate: str
    value: str
    status: str | None = None

class AssessmentDimensionProposal(ContractModel):
    # Retain name/rationale/evidence_ids/outcome/conclusion/uncertainty.
    evidence_bindings: tuple[AssessmentEvidenceBinding, ...] = ()

class AssessmentSelectionProposal(ContractModel):
    # Retain existing fields.
    model_id: str
    prompt_version: str
    decision_run_id: str
```

Return assessment frame, limitations, and selector trace from one private helper result rather than
silently returning only `None`. Replay each binding positionally against the exact `EvidenceItem`;
apply supported/conflicting/insufficient rules from the contract. Catch assessment-selector
`TimeoutError` in the same visible degradation boundary as invalid output. Build bounded conditional
synthesis only from admitted outcomes.

- [x] **Step 4: Upgrade S9A fixtures without narrowing dimension freedom**

Give each supported/conflicting assessment item an exact `EvidenceClaimBinding`, populate
`AssessmentEvidenceBinding` plus stable selector metadata, preserve arbitrary Chinese dimension
names, and retain the model-memory negative. Do not add a global catalog or exact dimension list.

- [x] **Step 5: Prove GREEN**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k assessment_replays_evidence_relevance
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_assessment_contract.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py
```

Expected: `1 passed` focused; assessment and grounding owners pass unchanged in intent.

## Task 4: RED/GREEN typed session directives and release/session fail-closed behavior

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py:107-146,697-737,932-1216`

- [x] **Step 1: Focus the already-recorded fourth RED group**

Add exact group
`test_typed_session_directive_owns_referents_topic_switch_and_release_boundary`.

Prove an opaque query plus `displayed_member/2`, `displayed_result_set`, and `active_anchor`
directives resolve exact stored handles. Prove Chinese trigger text with no matching directive does
not resolve or reset state. Then prove typed topic switch clears old state; same-session cross-release
continuation returns `session_release_mismatch`; a typed topic switch can rebind cleanly; and a Web
handle with absent/wrong `session_id` cannot enter state.

- [x] **Step 2: Observe exact RED**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k typed_session_directive_owns
```

Expected: one failure because `SessionDirective` is absent and current resolution is driven by
Chinese substrings.

- [x] **Step 3: Implement and content-bind the directive**

```python
class SessionDirective(ContractModel):
    transition: Literal["continue", "topic_switch"] = "continue"
    referent: Literal[
        "none", "active_anchor", "displayed_result_set", "displayed_member"
    ] = "none"
    displayed_ordinal: int | None = Field(default=None, ge=1)

class TurnRequest(ContractModel):
    # Retain existing fields.
    session_directive: SessionDirective | None = None
```

Validate the iff invariant: `displayed_member` requires an ordinal, and `none`, `active_anchor`, and
`displayed_result_set` require it to be absent. Replace every query-text branch in `_advance_session`
with the typed directive. Add private session-to-release binding and fail-closed typed limitation
behavior. Validate incoming Web handles against the exact request session.

- [x] **Step 4: Convert S9M accepted scenarios to typed inputs**

Pass explicit directives for the old second-member, displayed-set, active-anchor, and topic-switch
cases; give Web handles exact session IDs. Keep the original natural-language query text so the
tests still prove user-visible scenarios, then add wording traps showing text alone has no authority.

- [x] **Step 5: Prove GREEN**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k typed_session_directive_owns
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
```

Expected: `1 passed` focused; complete multi-turn owner passes with no xfail/XPASS/skip.

## Task 5: RED/GREEN bounded safety guidance

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py:107-146,359-380,740-930`

- [x] **Step 1: Focus the already-recorded fifth RED group**

Add exact group
`test_safety_guidance_is_server_owned_bounded_and_official_snapshot_grounded`.

Use one default safety `RetrievalPlan` executed by real `KnowledgeRead` and one official-only plan
whose recorded Web lane contains an accepted official snapshot plus an unverified trap. Supply a
hostile answer selector that tries to name venues and give evasion instructions; assert it is never
called. Static output must be brief lawful risk/official-help guidance. Official output may add only
at most three exact whitelisted binding values and citations from accepted official snapshots. No
snippet, unverified locator, venue/district/business allegation, evasion content, factual
continuation, or general-Web effect may survive.

- [x] **Step 2: Observe exact RED**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k safety_guidance_is_server_owned
```

Expected: one failure because the answer-side typed directive/renderer does not exist.

- [x] **Step 3: Implement the bounded directive and renderer**

```python
class SafetyGuidanceDirective(ContractModel):
    mode: Literal["static", "official_snapshot"]
    official_evidence_ids: tuple[str, ...] = ()

class TurnRequest(ContractModel):
    # Retain existing fields.
    safety_guidance: SafetyGuidanceDirective | None = None
```

Validate static/official shape and cap. Before invoking selectors, render a server-owned static
sentence. For official mode, admit only current-Web, official, snapshotted evidence with one of the
three contract predicates; deterministically append binding values and derive mappings/citations.
Return `response_mode="safety_guidance"` with no continuation offer.

- [x] **Step 4: Prove GREEN and read-side compatibility**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k safety_guidance_is_server_owned
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_read_universal_web_contract.py \
  tests/canonical_v2/test_knowledge_read_atomic_green_contract.py
```

Expected: `1 passed` focused; existing read owners remain GREEN.

## Task 6: Prove the real KnowledgeRead-to-KnowledgeAnswer vertical

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`

- [x] **Step 1: Use the already-recorded sixth RED group without constructing EvidenceSet**

```python
def test_real_knowledge_read_result_flows_to_grounded_answer_and_assessment() -> None:
    read = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_500,
            max_results=3,
        ),
        lane_adapters={"web": recorded_web_adapter},
    )
    evidence_set = read.execute(validated_plan)
    request = answer_module.TurnRequest(
        session_id="session:s9i:vertical",
        turn_id="turn:s9i:vertical",
        query=validated_plan.original_query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
        assessment_intent=answer_module.AssessmentIntent(kind="technical_strength"),
    )
    result = answer.answer(request)
    assert result.selector_traces[0].selection_input_sha256 == request.content_sha256
    assert result.claims[0].evidence_ids == (evidence_set.items[0].evidence_id,)
    assert result.claim_evidence_map[0].evidence_ids == result.claims[0].evidence_ids
    assert result.citations[0].evidence_id == result.claims[0].evidence_ids[0]
```

Use recorded bounded adapters and an exact current-Web snapshot/claim binding accepted by the real
read path. Assert the pre-answer `EvidenceSet` has the expected retrieval trace/snapshot; selector
trace input equals `request.content_sha256`; output claim/map/citation and arbitrary assessment
dimension use the same evidence ID/binding; and no manual `EvidenceSet`, live network, or write is
present.

- [x] **Step 2: Verify the pre-implementation RED receipt, then prove the handoff GREEN**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py \
  -k real_knowledge_read_result_flows
```

The stored Task 2 receipt must show this exact group failed before any production edit at the
strengthened proposal/assessment trace or relevance boundary, never at read fixture validity. The
current command must now pass after Tasks 2-5. If the pre-implementation receipt is missing or shows
a fixture failure, do not claim TDD or Candidate; repair the owner and re-establish a clean RED from
the recorded Ready inputs without resetting or overwriting the dirty worktree.

- [x] **Step 3: Run the complete new owner**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -W error -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py
```

Expected: exactly `6 passed`, no failure/error/skip/xfail/XPASS/warning.

## Task 7: Regression, review, and acceptance

**Files:**
- Update after Candidate review: S9I receipt/contract/plan and existing verification/status ledgers
- Update after acceptance only: OpenSpec `tasks.md`, matching `acceptance.md`, `change-log.md`, and
  `agent-links.md`

- [x] **Step 1: Run the complete answer owner matrix**

```bash
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_answer_interface.py \
  tests/canonical_v2/test_knowledge_answer_assessment_contract.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py
```

Expected: live Ready baseline plus exactly six new passes, no fail/error/skip/xfail/XPASS. Preserve
the three historical intentional hostile `model_construct` warnings only where the existing owner
already records them.

The new owner must contain exactly six test functions. Wrong-input/wrong-schema/schema-invalid answer
selector cases run in one loop inside group 2; answer and assessment `TimeoutError` cases stay inside
groups 2 and 3. Do not parameterize those cases or create extra test functions that change the exact
six-owner count.

- [x] **Step 2: Run relevant read and complete no-external regression**

```bash
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_query_planning_contract.py \
  tests/canonical_v2/test_knowledge_read_interface.py \
  tests/canonical_v2/test_knowledge_read_universal_web_contract.py \
  tests/canonical_v2/test_knowledge_read_atomic_green_contract.py
uv run pytest -q tests/canonical_v2
```

Expected: all relevant owners pass. Capture and reconcile the actual complete-suite count after the
Accepted S8 predecessor; require zero unexpected failures/xfails rather than copying a stale count.

- [x] **Step 3: Run static/strict/package/source gates**

```bash
uv run ruff check \
  src/data_agents/canonical_v2/knowledge_answer.py \
  tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_answer_interface.py \
  tests/canonical_v2/test_knowledge_answer_assessment_contract.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py \
  tests/canonical_v2/test_knowledge_answer_implementation_closure.py
uv run ruff format --check \
  src/data_agents/canonical_v2/knowledge_answer.py \
  tests/canonical_v2/test_knowledge_answer_*.py
./.venv/bin/python -m py_compile src/data_agents/canonical_v2/knowledge_answer.py
./.venv/bin/pyright -p /tmp/s8rg-pyrightconfig.json \
  src/data_agents/canonical_v2 tests/canonical_v2
```

From the worktree root, run strict OpenSpec and `git diff --check`; repeat the existing
high-confidence secret, generated-cache, scope, original Milvus hash, paused-`pgtest`, and
network-none/no-port recovery-lab checks. Build one fresh locked-offline wheel; verify it contains
`knowledge_answer.py`, excludes tests/`.agents`, and matches source bytes. Clean only the exact
generated wheel/cache paths created by these checks.

### Pre-Candidate verification receipt — `2026-07-20T11:54:44Z`

- The post-review-fix six-test owner passed with warnings denied: `6 passed in 3.41s`.
- The complete answer owner matrix passed: `20 passed, 3 warnings in 9.86s`; all three warnings are
  the retained hostile `model_construct` serialization probes owned by the atomic contract.
- The relevant read predecessor matrix passed: `11 passed in 7.10s`.
- The final no-external Canonical V2 regression passed: `357 passed, 141 skipped, 3 warnings in
  206.67s`; the skips are the existing external-environment gates and the warnings are the same
  three hostile serialization probes. There were zero failures, errors, xfails, or XPASSes.
- Complete Canonical V2 Ruff and format checks passed (`75 files already formatted`), `py_compile`
  passed, and complete Canonical V2 Pyright reported `0 errors, 0 warnings, 0 informations`.
- Strict OpenSpec validation passed, `git diff --check` produced no output, and
  `uv lock --check --offline` resolved the unchanged `194`-package lock in offline mode.
- A fresh disposable offline wheel had SHA-256
  `1f343aa65654caa5c5bee6cf471b4c4534bdb39c9de6001f30abe08a4d1a1628`, exactly `276`
  entries, one `src/data_agents/canonical_v2/knowledge_answer.py`, and zero test or `.agents`
  entries. Source and packaged module bytes both had SHA-256
  `8dec205620854910eadc3301b8a63da03d937bb53dd622c5280a0651f7e400de`; the disposable wheel
  directory was removed.
- The exact six-test owner SHA-256 was
  `74534d5103588d8c75961c80f66aaf556c3d8d9fa3de1f429fdfea79bc80636c`. The implementation
  owner contains exactly six `test_` functions and no xfail marker.
- Original Milvus remained hash-only at
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`; `pgtest` remained
  paused/running on volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`, restart `no`, port
  `15432`; the recovery lab remained running with network `none`, no ports, and restart `no`.
- Branch/HEAD remained `canonical-v2-s2-baseline` /
  `f0e6224e1c675c6d6c58993676783b2fbe0cd8f6`; the nine S9I-owned files had zero high-confidence
  credential assignments, conflict markers, or missing final newlines. No S9I wheel temp directory
  remained.
- This receipt was pre-Candidate verification evidence. Final frozen-hash review subsequently
  closed every finding, permitting the Candidate transition without any OpenSpec task, acceptance
  ledger, or portfolio status change.

- [x] **Step 4: Obtain one merged independent implementation review**

Lock production/test/contract hashes. Review claim binding/filtering, selector trace trust boundary,
assessment relevance/degradation, typed directive/release handling, safety bounds, real-read test
integrity, and scope. Repair only Critical/Important findings; rerun affected checks and one targeted
re-review. Record Minor/YAGNI as nonblocking.

The final read-only targeted re-review at production SHA-256
`8dec205620854910eadc3301b8a63da03d937bb53dd622c5280a0651f7e400de` and exact-owner SHA-256
`74534d5103588d8c75961c80f66aaf556c3d8d9fa3de1f429fdfea79bc80636c` reports
`Critical=0/Important=0/Minor=0/YAGNI=0`. It reran the four direct counterexamples, the warnings-as-
errors exact owner (`6 passed in 3.41s`), the six-owner answer matrix (`20 passed` plus three
intentional hostile-Pydantic warnings in `3.51s`), focused Ruff, and diff-check. No assertion
weakening, skip, or xfail pattern was found.

- [x] **Step 5: Accept exactly the implementation tasks**

After zero open Critical/Important findings, mark S9I Accepted; check exactly Tasks `9.2`, `9.4`,
and `9.6`; update matching acceptance/verification/change-log/links/portfolio/mainline evidence;
confirm the live ledger delta is exactly `+3`; and leave Task `9.8` plus aggregate S9 open. Rerun
strict OpenSpec and `git diff --check`.

Accepted at `2026-07-20T12:03:04Z` after the parent revalidated every Candidate receipt binding,
the exact `59/80` predecessor ledger, strict OpenSpec, diff cleanliness, and frozen Milvus/pgtest
state. Exactly Tasks 9.2/9.4/9.6 are checked, producing `62/80`; Task 9.8 remains unchecked.

Do not stage, Commit, Push, open a PR, archive, promote, Cutover, or write any original/production-
like source.

## Invariants

- Evidence membership, claim status, citations, selector trace outcome, assessment state, session
  state, safety text, and continuation state remain server-owned.
- Product capability remains direct and answer-scoped; Industry Brief remains derived.
- Canonical/Web handle type, Web snapshot, ambiguity, traversal, coverage, and ContinuationOffer
  semantics remain unchanged.
- No global registry/score, durable session, HTTP consumer, provider framework, canonical mutation,
  or new OpenSpec mainline is introduced.

## Rollback note

Revert only S9I additions in `knowledge_answer.py`, remove the new owner, restore mechanical fixture
changes in the five existing owners, and remove S9I evidence. If already accepted, uncheck exactly
Tasks 9.2/9.4/9.6 and restore their matching status evidence. No external state rollback exists.
