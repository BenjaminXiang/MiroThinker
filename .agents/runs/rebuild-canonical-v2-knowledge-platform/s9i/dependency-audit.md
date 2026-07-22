# S9I Grounded Assessment/Session Implementation Closure Dependency Audit — 2026-07-20

## Outcome

One minimal vertical implementation slice can close OpenSpec Tasks `9.2`, `9.4`, and `9.6` over
the already-Accepted `knowledge_answer.py` mechanics. The designated aggregate S8 real-read runtime
predecessor is S8C, whose accepted receipt now closes the runtime dependency after S8R4/S8R5. S9I
may become Ready only after its live five-owner baseline and an independent review of the corrected
contract/plan report zero open Critical/Important findings.

S2C3C2/S2C3C3 still gate only Task `9.8` claim-level acceptance-oracle execution. They do not block
this deterministic implementation slice, its synthetic owner matrix, or one bounded real
`KnowledgeRead.execute -> KnowledgeAnswer.answer` integration owner.

## Accepted predecessors already available

- S3A: public `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` interface RED.
- S7: release/index substrate and release-bound identity authority.
- S8P2: typed planning taxonomy and `AssessmentIntent` capture.
- S8RG plus subsequent Accepted S8 corrections: typed `EvidenceSet`, local/current-Web evidence,
  claim bindings, handles, conflicts, coverage, limitations, traversal requests, and read traces.
- S9G/Task 9.1: grounded-claim, Product-capability, Industry-Brief, coverage, conflict, inference,
  citation, and prose-fallback RED owners.
- S9A/Task 9.3: user-criteria and LLM-selected per-turn AssessmentFrame RED owners.
- S9M/Task 9.5: typed-handle/session, ambiguity, traversal, topic-switch, and continuation RED
  owners.
- S9AG: Accepted atomic synthetic `knowledge_answer.py` mechanics GREEN.
- S9C1/Task 9.7: Accepted server-owned executable `ContinuationOffer` policy.

## Current implementation gaps

The existing module proves the accepted synthetic mechanics, but inspection identifies seven
concrete implementation-closure gaps:

1. `_ground_claim` checks an exact `EvidenceClaimBinding` only when all of `subject_id`, `predicate`,
   and `value` happen to be present. A material proposal with a partial or absent structured triple
   can currently survive on evidence-ID membership alone.
2. `TurnResult.answer_text` normally copies `AnswerSelectionProposal.answer_text`. If one valid claim
   and one rejected claim are proposed together, rejected prose can still leak through that draft.
3. Answer and assessment selector proposals bind schema and input, but do not expose the selector
   model, prompt, decision run, and accepted/degraded decision trace together in the result.
4. `_build_assessment_frame` checks only that evidence IDs exist. It does not prove that each cited
   item has the exact structured evidence binding used by a supported/conflicting conclusion, and
   invalid selector output degrades silently to `None` without a visible stage limitation.
5. `_advance_session` recognizes `"换个话题"`, `"第二家"`, `"这些"`, and `query.startswith("它")`.
   These Chinese wording heuristics are neither typed nor language-independent.
6. The answer seam has no typed safety-guidance directive or bounded server-owned renderer; the read
   layer can produce a valid `safety_guidance` result, but answer behavior is not closed.
7. All five current KnowledgeAnswer owners construct `EvidenceSet` fixtures directly. No owner
   proves that an actual public `KnowledgeRead.execute` result, including its retrieval trace and
   current-Web snapshot, flows unchanged into claim/assessment selection and citations.

## Pre-Ready contract corrections

The implementation contract must preserve conflict rather than flatten it. A supported claim still
requires exact full `subject_id/predicate/value/status` equality against every cited binding. A
conflicting claim instead requires a complete proposal triple, evidence IDs that exactly match one
retained material `EvidenceConflict`, and cited evidence whose subjects and predicates match the
proposal while their values/statuses retain the material difference. The existing legal proposal
value `"conflicting"` remains valid and is not required to equal each conflicting evidence value.

Selector exception behavior is part of the same two selector owner groups. The answer selector call
must move inside its validation/degradation boundary, and both answer and assessment selectors must
treat `TimeoutError` as a visible stage degradation. Answer timeout returns the deterministic
grounded fallback plus `answer_selection_rejected` and a degraded answer trace. Assessment timeout
preserves the grounded answer and adds `assessment_selection_rejected` plus a degraded assessment
trace.

The new owner remains exactly six test functions. The wrong-input, wrong-schema, and schema-invalid
answer-selector cases execute as one in-test loop inside the second function; they are not pytest-
parameterized and therefore cannot inflate the exact `6 passed` contract. Likewise, timeout cases
remain subcases of the existing second and third functions.

`SessionDirective.displayed_ordinal` is an iff contract: `displayed_member` requires one positive
ordinal, while `none`, `active_anchor`, and `displayed_result_set` forbid it.

## Ready evidence

S8C is Accepted. At `2026-07-20T11:07:04Z`, the fresh five-owner KnowledgeAnswer baseline was
`14 passed` with only the three pre-existing hostile-`model_construct` serializer warnings and no
fail/error/skip/xfail/XPASS. Independent review of the corrected audit/plan/contract reported
`Critical=0/Important=0/Minor=0/YAGNI=0`. Reviewed Specified hashes were audit
`16b3e4b5fddd24964d1eb962fc7780368ae06de1b50b916cc55fe66674ad20cd`, plan
`fd515998e2f1d1470fcbeef6659a249f25e94f3cdd0355cf565f1155dba7b320`, and contract
`4db71e71725f744aa2cef2e5e94c6adc2ea82f4d9de18859afe3ff5c5d831b4a`. S9I may proceed to the exact
six-function RED owner; no production or test implementation existed when this gate was recorded.

## Chosen implementation boundary

Deepen the existing answer module and add one dedicated six-group implementation-closure owner:

- production: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` only;
- compatibility/owner fixtures: the five existing `test_knowledge_answer_*.py` owners only where
  the strengthened public proposal/request contract requires it;
- new owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`.

The deep module remains `KnowledgeAnswer`; there is no second assessment/session/safety service.
`TurnRequest` receives small typed answer-side directives, and the complete request hash binds them
along with the exact `EvidenceSet`. No `knowledge_read.py`, storage, HTTP, provider, or public
session-manager change is required.

## Alternatives considered

### Split claim, assessment, session, and safety into new modules

Rejected for this convergence round. Those behaviors already share one Accepted public answer seam
and one ephemeral state owner. Splitting them would add coordination interfaces and duplicate
validation without satisfying a current consumer or acceptance obligation.

### Leave current mechanics untouched and defer all gaps to Task 9.8

Rejected. Task 9.8 is an aggregate reviewed-corpus/provider/latency acceptance gate, not the owner
of deterministic missing implementation such as partial claim bindings, leaked rejected drafts,
silent assessment degradation, wording heuristics, or absent safety rendering.

### Chosen: one answer-module vertical closure

This is the smallest reversible slice that makes all three implementation tasks materially true,
reuses Accepted mechanics, and leaves real-provider quality/calibration to Task 9.8.

## Exact task boundary

S9I may check exactly Tasks `9.2`, `9.4`, and `9.6` after Candidate verification and independent
review. It must not check Task `9.8`, claim aggregate S9 acceptance, run the pending S2C oracle as
normative truth, or change Task `9.7`.

At acceptance, compute the ledger from the then-current `tasks.md`; do not reuse the current
`56/80` snapshot. The slice delta is exactly three checked tasks.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md` — Tasks 9.2/9.4/9.6/9.8.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/grounded-progressive-answer/spec.md`.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/convergence-plan-remaining-24-2026-07-20.md`.
- Accepted S9G, S9A, S9M, S9AG, and S9C1 Slice Contracts.
- Current `knowledge_answer.py`, its five owners, and public `KnowledgeRead.execute` contract.

No production code, test, OpenSpec checkbox, existing slice, source, database, index, provider,
pointer, Commit, Push, PR, archive, or Cutover changed during this audit.
