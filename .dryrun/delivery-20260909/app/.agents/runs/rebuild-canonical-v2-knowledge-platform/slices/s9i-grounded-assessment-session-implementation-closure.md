# Slice Contract: S9I Grounded Assessment/Session Implementation Closure

## Status

Accepted at `2026-07-20T12:03:04Z`; Candidate was reached at `2026-07-20T11:58:44Z` and Ready at
`2026-07-20T11:07:04Z`. The exact six-group
pre-production RED failed only at the intended implementation seams (`6 failed in 2.04s`), and the
post-review counterexample RED failed five of six groups before the four Important findings and one
Minor were repaired. Final evidence is `6 passed` in the exact owner, `20 passed` in the complete
answer matrix, `11 passed` in the relevant read matrix, and `357 passed, 141 skipped` in the complete
no-external Canonical V2 regression; the three retained warnings are intentional hostile-model
serializer probes. Static, strict, locked-offline package/source parity, scope, and frozen-source
gates pass. Final independent frozen-hash review reports
`Critical=0/Important=0/Minor=0/YAGNI=0`; all original review findings are closed. Acceptance checks
exactly Tasks 9.2/9.4/9.6 and moves the formal ledger `59/80 -> 62/80`. Task 9.8 remains out of scope
and aggregate S9 remains open.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec tasks to close after acceptance: `9.2`, `9.4`, and `9.6`
- OpenSpec task explicitly excluded: `9.8`
- Requirements: every material answer claim maps to evidence; Product capability requires direct
  Product binding; assessment is compact, evidence-based, per-turn, and answer-scoped; relationship
  exploration is typed and user-directed; session state preserves Canonical/Web handle types;
  safety guidance is conservative and bounded; intermediate LLM decisions are structured and
  traceable; LLM failure degrades visibly by stage.
- Depends on: Accepted S3A/S7/S8P2/S8RG lineage, Accepted S9G/S9A/S9M RED, Accepted S9AG mechanics,
  Accepted S9C1 continuation hardening, and the future Accepted aggregate S8 runtime predecessor.
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s9i/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s9i/implementation-plan.md`

## Goal

Close the three deterministic S9 implementation tasks through the existing public seam:

```python
evidence_set = knowledge_read.execute(validated_plan)
result = knowledge_answer.answer(
    TurnRequest(
        session_id="session:s9i:example",
        turn_id="turn:s9i:example",
        query=validated_plan.original_query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
        session_directive=SessionDirective(referent="none"),
        safety_guidance=None,
        assessment_intent=AssessmentIntent(kind="technical_strength"),
    )
)
```

Every rendered supported/conflicting/inference material claim must have a complete structured
subject/predicate/value/evidence mapping. Rejected claims and raw selector answer drafts must not
leak into output. Answer and assessment selection must expose model/prompt/schema/run/input traces;
assessment conclusions must consume exact relevant evidence bindings and degrade visibly. Session
resolution must use typed directives rather than query-language heuristics. Safety guidance must be
brief, server-owned, and optionally grounded only in bounded official snapshots.

## Non-goals

- Do not implement or accept Task 9.8, aggregate S9, reviewed corpus replay, unsupported-claim-rate
  calibration, real provider quality, TTFT/progress, latency, cost, or production response-contract
  acceptance.
- Do not implement S8 runtime work, edit `knowledge_read.py`, create retrieval evidence, or treat a
  synthetic `EvidenceSet` as proof of the real vertical owner.
- Do not add HTTP/chat/admin adapters, a public/durable SessionManager, TTL/persistence, cross-process
  state, durable HTTP session semantics, database/index/source writes, or S11 consumer migration.
- Do not create a global assessment registry, fixed dimension list, weights, numeric score,
  canonical quality label, prompt framework, provider hierarchy, or general workflow engine.
- Do not persist Product capability, Industry Brief, assessment, session relation, Web fact,
  safety answer, or selector decision as canonical knowledge.
- Do not reopen Accepted S9C1 option policy or add new continuation reasons.

## Allowed scope

- Production:
  `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`.
- New six-group owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`.
- Existing owners only for mechanically adopting strengthened proposal metadata, complete structured
  claim fixtures, assessment evidence bindings, typed session directives, and exact new result
  traces without weakening their Accepted assertions:
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py`
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_interface.py`
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_assessment_contract.py`
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_grounding_contract.py`
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py`
- This S9I contract/plan/run evidence and, only after Candidate acceptance, existing
  `verification.md`, OpenSpec `tasks.md`/`acceptance.md`/`change-log.md`/`agent-links.md`, portfolio,
  and mainline status summaries.

## Forbidden changes

- Any other production/test/shared-contract/migration/database/index/provider/chat/admin/gap/source
  file or any Accepted fixture assertion unrelated to the strengthened S9 contract.
- A new OpenSpec change, competing spec/design, second public answer/assessment/session/safety seam,
  or change to S8 evidence semantics.
- Test-local production implementation, manually constructed `EvidenceSet` in the real vertical
  group, assertion weakening, exception swallowing, `importorskip`, runtime `pytest.xfail`, live
  network/credentials, or reference prose/model memory as truth.
- Caller/model-authored final evidence membership, citations, claim status, selector trace outcome,
  assessment outcome, session state, handle resolution, safety text, or continuation availability.
- Commit, Push, PR, archive, promotion, Cutover, original-source writes, or destructive cleanup.

## Material claim and rendering contract

For every admitted supported/conflicting/model-inference `MaterialClaimProposal`:

1. `subject_id`, `predicate`, and `value` are non-empty;
2. `evidence_ids` is non-empty, unique, and references current-turn `EvidenceItem` records;
3. a supported factual claim replays exact `subject_id/predicate/value/status` bindings from every
   retained evidence item;
4. a conflicting factual claim has a complete proposal triple, cites evidence IDs that exactly
   match one retained material `EvidenceConflict`, and replays matching `subject_id/predicate` from
   every cited item while preserving the conflicting evidence values/statuses as different; the
   existing proposal value `"conflicting"` is valid and need not equal each evidence value;
5. a model inference retains complete structured fields and bound evidence but is accepted only as
   `synthesis=True`, `answer_scoped=True`, `confirmed=False`, with non-empty uncertainty;
6. `ClaimEvidenceMapping` exactly repeats the admitted claim triple/status/evidence IDs, and
   citations are derived only from those admitted IDs.

The existing server-generated unsupported Product-capability record remains a typed, unconfirmed
`outcome="unsupported"` insufficiency result with complete subject/predicate/value, an empty
evidence mapping, and the named material limitation. It is not a confirmed factual claim. A
supported Product-capability claim still requires direct named-Product evidence and exact status.
Industry Brief remains release-scoped derived output over the admitted claim/mapping/citation set.

`AnswerSelectionProposal.answer_text` remains accepted as non-authoritative compatibility input but
is never copied into `TurnResult` and is not retained in result traces. Default rendering is built
only from admitted claim texts and server-owned limitations/clarifications. Thus a proposal that
mixes one valid claim with rejected claim prose cannot leak the rejected prose. A prose renderer
receives only the sanitized `TurnResult`; raw selection output is never passed to it. Real prose
provider quality and claim-level rendered-oracle evaluation remain Task 9.8.

## Selector trace contract

Valid answer and assessment proposals add non-empty `model_id`, `prompt_version`, and
`decision_run_id` alongside their existing schema, decision, and input hash. `TurnResult` exposes a
tuple of server-constructed `SelectorDecisionTrace` records with:

```python
stage: Literal["answer_selection", "assessment_selection"]
schema_version: str
selection_input_sha256: str
outcome: Literal["accepted", "degraded"]
decision_id: str | None
model_id: str | None
prompt_version: str | None
decision_run_id: str | None
failure_kind: str | None
```

An accepted trace has every optional identity field populated and binds the exact `TurnRequest`
hash. A rejected/invalid selector output or selector `TimeoutError` creates a server-owned degraded
trace and named stage limitation; it does not trust or echo unvalidated model/prompt/run fields. The
answer selector invocation is inside this degradation boundary. An answer timeout returns only the
deterministic grounded fallback; an assessment timeout preserves that grounded answer and adds an
assessment-stage degradation. No trace stores proposal answer text or model-authored final evidence/
session state. When no answer selector is configured, the existing deterministic default proposal
uses explicit server-owned identities
`model_id="server-deterministic"`, `prompt_version="answer-default-v1"`, and a turn-bound default run
ID; it does not impersonate an external LLM call.

## Assessment contract

Each proposed supported/conflicting dimension pairs every `evidence_id` positionally with an exact
`AssessmentEvidenceBinding` copied from that item's non-null `EvidenceClaimBinding`. The server
replays subject/predicate/value/status equality before admitting the dimension.

- `supported` requires at least one exact relevant binding, a non-empty conclusion and uncertainty,
  and no matching material conflict.
- `conflicting_evidence` requires exact bound evidence plus a matching retained material conflict,
  a conditional conclusion, and uncertainty.
- `insufficient_evidence` has no factual conclusion and cannot promote model-memory evidence.
- Explicit user criteria remain in user order. Without criteria, the selector may freely choose up
  to three non-empty per-turn dimension names from the question/evidence; there is no registry,
  score, fixed taxonomy, or weight.

Invalid schema/input/relevance/outcome combinations and assessment-selector `TimeoutError` do not
erase an otherwise grounded answer. They produce `assessment_selection_rejected` or
`assessment_dimension_rejected`, a degraded selector trace, and an absent/insufficient dimension as
appropriate. Rejected conclusion/synthesis prose is not rendered. `conditional_synthesis` is a
bounded server-owned summary of admitted dimension outcomes and remains answer-scoped/non-canonical.

## Typed session directive contract

Add one immutable answer-side directive bound by `TurnRequest.content_sha256`:

```python
class SessionDirective(ContractModel):
    transition: Literal["continue", "topic_switch"] = "continue"
    referent: Literal[
        "none", "active_anchor", "displayed_result_set", "displayed_member"
    ] = "none"
    displayed_ordinal: int | None = None  # one-based; required iff referent is displayed_member
```

Model validation requires a positive `displayed_ordinal` when and only when `referent` is
`displayed_member`; every other referent forbids the field. The answer module does not parse query
wording to resolve session state. An explicit directive selects the active anchor, complete prior
displayed result set, or one displayed member. A typed
`topic_switch` clears the old anchor/result set/constraints/path before current-turn state is
installed. Existing exact `ContinuationSelection` remains the only continuation-option selection
input.

One ephemeral session ID is bound to one release. A continuing request on another release returns a
typed `session_release_mismatch` limitation without exposing or traversing old state; an explicit
typed topic switch may clear and rebind the ephemeral session to the new release. A Web handle with
a non-matching or absent `session_id` cannot enter session state. Canonical and Web handle types,
snapshot identity, resolution state, and display order remain unchanged. No durable lifecycle or
HTTP session policy is introduced.

Chinese/English trigger phrases in `query` have no special meaning in `knowledge_answer.py` once
this contract is implemented. Tests must prove both directions: an opaque query plus a typed
directive succeeds, while `"第二家"`, `"这些"`, `"它"`, or `"换个话题"` without the corresponding
directive cannot select or reset prior state.

## Safety-guidance contract

Add one optional directive bound by the complete `TurnRequest`:

```python
class SafetyGuidanceDirective(ContractModel):
    mode: Literal["static", "official_snapshot"]
    official_evidence_ids: tuple[str, ...] = ()
```

`static` admits no evidence IDs. `official_snapshot` admits at most three current-turn evidence
items, each with `source_nature="current_web"`, `source_authority="official"`, a retained bounded
`WebEvidenceSnapshot`, and an exact claim binding whose predicate is one of the finite official-help
surface (`official_help_contact`, `official_reporting_channel`, or `official_policy_reference`).

Safety rendering is server-owned and bypasses answer/assessment selectors. It is brief and limited
to lawful risk avoidance plus official help/reporting direction. It never renders item snippets,
unverified sources, venues/districts/business allegations, discovery/evasion instructions, or
unrelated lifestyle content. Official details are rendered deterministically from admitted binding
fields with claim mappings/citations. The result uses `response_mode="safety_guidance"`, omits an
unsupported primary answer and continuation offer, and performs no retrieval itself.

## Real vertical owner

The new owner must call the real public `create_ephemeral_knowledge_read` factory and its
`execute(plan)` method, then
pass that returned validated `EvidenceSet` into `TurnRequest`; it must not instantiate or copy an
`EvidenceSet` by hand. The test uses bounded recorded local/current-Web adapters only, asserts the
retrieval trace and snapshot before answer execution, and proves:

- selector input hash binds the complete real read result;
- one exact structured claim produces its claim map and citation from the same evidence ID;
- one free per-turn assessment dimension uses the same exact evidence binding;
- model/prompt/schema/run/input traces are visible;
- no provider/network/source/database/index write occurs.

This is implementation evidence, not Task 9.8 corpus/provider/latency acceptance evidence.

## Expected unchanged behavior

- Accepted S1-S8 and S10 behavior, public `KnowledgeRead.execute`, release/candidate/index semantics,
  query planning, S9C1 continuation policy, Product direct-binding, Industry Brief derivation,
  enumeration/ambiguity/handle/traversal mechanics, and deterministic prose-timeout fallback remain
  GREEN.
- The five existing KnowledgeAnswer owner groups remain observable through the same public seam;
  fixture changes add required metadata/bindings/directives without removing hostile cases.
- Session state remains private to one ephemeral `KnowledgeAnswer` instance. No global/durable
  registry, score, session, write, or canonical mutation is added.
- Task 9.8 and aggregate S9 remain unchecked. S2C remains the gate only for reviewed
  acceptance-oracle execution.
- Original PostgreSQL/Milvus/forensic sources, candidate state, active pointers, recovery lab, and
  external providers remain untouched.

## Required checks

- Before GREEN, each of the six exact new owner groups is observed failing for its intended current
  implementation gap, not import/setup/fixture drift. Do not hide RED with xfail wrappers.
- After GREEN, the new owner is exactly `6 passed`, with no fail/error/skip/xfail/XPASS.
- The five existing owners plus the new owner pass together; the pre-S9I five-owner baseline is
  captured at Ready, and the only count delta is exactly six new test functions. The three hostile
  answer-selector shapes execute in one in-test loop rather than pytest parameterization; answer and
  assessment timeout regressions remain subcases of their existing groups.
- Relevant real-read planning/universal-Web/atomic owners pass unchanged.
- Complete no-external Canonical V2 passes with zero unexpected failures/xfails; capture and
  reconcile the actual count after the Accepted S8 predecessor rather than copying a stale count.
- Ruff check/format, `py_compile`, and complete Canonical V2 Pyright pass for changed/applicable
  scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, fresh locked-offline wheel,
  package-content/source parity, and frozen-source checks pass.
- At least one merged independent implementation/test-integrity review reports zero open Critical/
  Important findings. Repair only those severities and run one targeted re-review. Minor/YAGNI are
  recorded and nonblocking.

## Evidence to update

- This Slice Contract and the S9I implementation plan/verification receipt.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- After acceptance only: check exactly Tasks `9.2`, `9.4`, and `9.6`; update the matching
  `acceptance.md` evidence, `change-log.md`, `agent-links.md`, `.agents/portfolio.md`, and current
  mainline/convergence status.
- Keep Task `9.8` and aggregate S9 open; compute the exact ledger from live `tasks.md`.

## Stop conditions

- The designated S8 runtime predecessor is not Accepted, or the real vertical owner needs a
  Specified/Ready/In-Progress/Candidate S8 artifact as accepted runtime authority.
- Correct behavior requires changing `knowledge_read.py`, an S8 evidence/public contract, HTTP or
  durable session semantics, provider/storage/source/index behavior, or product semantics absent
  from the active OpenSpec.
- A partial material claim, mismatched evidence binding, rejected draft, invalid assessment
  conclusion, query wording heuristic, cross-release/session handle, unverified safety source, or
  selector-authored final state survives the public result.
- Product direct-binding, Industry Brief derivation, ContinuationOffer policy, ambiguity suppression,
  unresolved-Web traversal refusal, or deterministic fallback regresses.
- Any owner is weakened/hidden, a real network/write is required, or Critical/Important findings
  remain unresolved.

## Done means

- All six S9I groups turn GREEN through only the allowed module/test scope after exact RED proof.
- Every rendered supported/conflicting/inference material claim has a complete structured evidence
  map; filtered claims and raw proposal drafts cannot leak.
- Answer/assessment selector traces are complete when accepted and visibly degraded when rejected;
  assessment dimensions are evidence-relevant and remain per-turn/answer-scoped.
- Typed directives, not text heuristics, own referent/topic-switch behavior; release and Web-handle
  session boundaries fail closed.
- Static/official-snapshot safety guidance is bounded and server-owned.
- A real `KnowledgeRead.execute -> KnowledgeAnswer.answer` path proves the vertical handoff.
- Required checks and independent review pass with zero open Critical/Important findings, and exactly
  Tasks 9.2/9.4/9.6 are checked. Task 9.8 remains open.

## Rollback note

Before acceptance, remove the new owner and revert only S9I-owned additions in
`knowledge_answer.py` plus mechanical fixture changes in the five existing owners. Remove S9I run
artifacts. After acceptance, also restore exactly Tasks 9.2/9.4/9.6 and matching evidence entries.
There is no migration, store, provider, source, index, release, pointer, or durable session state to
roll back.
