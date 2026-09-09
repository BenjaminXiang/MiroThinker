# Slice Contract: S8P2 Planning Taxonomy and Assessment Intent

## Status

Accepted at `2026-07-19T07:28:02Z`. Initial and review-driven RED/GREEN, proportional verification,
and two independent re-reviews are complete with zero open Critical/Important findings. S8P1 and
every S7/S6R dependency are Accepted. S2C3C2 is an external reviewed-oracle gate for later S8/S9
calibration and aggregate acceptance only; it did not block this deterministic local Task 8.2
completion slice. Task 8.2 alone is checked and the formal OpenSpec ledger is `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.2`
- Accepted predecessors: S8Q1, S8RG, S8L1, S8L2, and S8P1
- Accepted design authority: ADR-020 and ADR-022
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p2/implementation-plan.md`

## Goal

Complete the remaining Task 8.2 planning contract through the existing `QueryPlanner.plan` seam:

1. make the recorded-provider proposal schema finite and machine-valid for behavior, interaction,
   enumeration, internal-reference, and Web modes;
2. reject invalid behavior/interaction/Web/safety cross-field combinations before a plan can execute;
3. capture one lightweight, open-ended assessment intent plus explicit ordered user criteria in the
   recorded proposal and resulting release-bound retrieval plan;
4. capture expected material answer parts in the recorded proposal and resulting plan; and
5. canonicalize that intent type at the read/planning seam while preserving the existing answer-side
   import surface.

This is the smallest remaining observable Task 8.2 behavior. It deepens the existing planner rather
than adding another planner, policy registry, or translation layer.

## Non-goals

- Do not build `AssessmentFrame`, select evidence-dependent dimensions, weights, thresholds, scores,
  conclusions, or a global assessment policy/type registry. Those remain Task 9.4/S9 ownership.
- Do not propagate intent through `KnowledgeRead.execute`, `EvidenceSet`, `TurnRequest`, session
  state, HTTP/chat/admin consumers, or provider/runtime adapters in this slice.
- Do not implement or claim Tasks 8.1, 8.3, 8.5, 8.7, 8.8, or any S9 aggregate behavior.
- Do not calibrate ambiguity thresholds or run the reviewed claim-level acceptance oracle.
- Do not add a second planner/factory, proposal adapter, safety object, or redundant assessment type.
- Do not change retrieval execution, fusion, rerank, answer rendering, persistence, schemas,
  migrations, database/index contents, release pointers, source data, or production-like targets.

## Allowed scope

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` for:
  - one shared `AssessmentIntent` value type;
  - one optional server-owned official-Web-domain allowlist on `QueryPlanningPolicy`, omitted from
    legacy serialization when empty;
  - finite proposal field types and proposal/plan cross-field validation;
  - optional intent and expected-material-part capture on `RecordedPlanningProposal` and
    `RetrievalPlan`;
  - nonnegative and server-bounded Web budgets without zero-budget escalation;
  - malformed recorded-proposal normalization to
    `InvalidRetrievalPlanError("invalid_planning_proposal")`;
  - legacy omission serializers for absent intent; and
  - exact unchanged legacy manual-plan behavior outside the planner-owned validation boundary.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` only to import and
  re-export the canonical read-side `AssessmentIntent`; keep `TurnRequest` and answer behavior
  otherwise unchanged.
- Modify exactly these two existing test owners:
  - `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py`
  - `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
- Update this contract, the S8P2 receipt/evidence, existing verification/change-log/agent-links,
  portfolio, and mainline-plan artifacts after Candidate review.
- Check only Task 8.2 in `tasks.md` after all S8P2 checks and independent review pass. Keep
  `acceptance.md` unchanged because its remaining gates are aggregate/runtime/calibration gates.

## Forbidden changes

- No `AssessmentFrame`, dimension catalog, fixed assessment-kind taxonomy, numeric score, weighting,
  registry, prompt service, or model-selected evidence-dependent dimensions.
- No new public planner/factory or caller-injected final plan; no post-merge of independent Pydantic
  results; no `model_construct` trust; no broad exception fallback; no assertion weakening.
- No proposal-supplied `blocking_clarification`; it remains a server-derived outcome of validated
  ambiguity/institution state.
- No ordinary F refusal or safety-guidance plan may acquire general Web retrieval. Safety guidance
  may use Web only as an explicit, bounded, official-source-only lane.
- No assessment intent on refusal, safety, interface-control, or any other non-information proposal.
- No provider/network credentials, persistence writes, schema/migration changes, original/recovery/
  production-like target writes, Commit, Push, PR, Archive, promotion, or Cutover.

## Expected unchanged behavior

- S8P1 release-graph/catalog/policy binding and its two accepted tests remain exact.
- Plans/proposals with `assessment_intent=None` omit that key and retain their pre-S8P2 serialized
  content identity. In particular, the S8P1 legacy plan remains
  `c89a484f9a7fb39ff604859545d98ee76daac77346ab12b589b68d06b45d5675` with serialized JSON SHA-256
  `e25a67563bd026475affcfc5a7bc20938c860a65dfb764f4da54a5a36bb0fefb`.
- Planning policies with no official-Web allowlist and proposals with no material-part decomposition
  omit the new optional keys, preserving prior policy/proposal/plan identities.
- Existing A-E/G information proposals, ordinary F refusal, interface control, default safety
  guidance, explicit official-only safety lookup, protected-slot/institution resolution, ambiguity,
  enumeration, Person, and Technology behavior stay GREEN when their fields are valid.
- Direct legacy `RetrievalPlan` values without planner trace/release binding/assessment intent keep
  the Accepted KnowledgeRead compatibility boundary; normalized taxonomy checks apply to planner-
  owned plans and any plan that carries the new intent.
- `knowledge_answer.AssessmentIntent` remains importable and is the exact same class as
  `knowledge_read.AssessmentIntent`; existing explicit `TurnRequest.assessment_intent` callers stay
  compatible.
- Original PostgreSQL/Milvus/forensic sources, recovery lab, release/index pointers, and all external
  state remain byte/state unchanged.

## Finite planning matrix

`RecordedPlanningProposal` accepts only:

- schema: `retrieval-plan-proposal-v1`;
- behavior: `A`, `B`, `C`, `D`, `E`, `F`, `G`, or `control`;
- proposal interaction: `information_retrieval`, `ordinary_refusal`, `safety_guidance`, or
  `interface_control`;
- Web mode: absent, `disabled`, `universal`, or `official_only`;
- enumeration mode: absent, `exhaustive_bounded`, `required_members`, or `representative`;
- internal reference target: `person` or `technology_route`.

The valid cross-field forms are:

1. `information_retrieval`: behavior A-E/G, non-empty public domains, a `web` lane, a positive
   provider-call budget, a positive explicit or candidate-derived result budget, absent or
   `universal` Web mode, optional expected material answer parts, and optional `AssessmentIntent`;
2. `ordinary_refusal`: behavior F, no domains/lanes/Web execution, and no assessment intent;
3. `interface_control`: behavior `control`, no domains/lanes/Web execution, and no assessment intent;
4. default `safety_guidance`: behavior F, no domains/lanes/Web execution, and no assessment intent;
5. official-only `safety_guidance`: behavior F, no public domains, exactly the `web` lane,
   `official_only`, a non-empty allowlist wholly contained in the server-owned planning policy,
   positive server-bounded provider/result limits, and no assessment intent.

The planner may derive `blocking_clarification` only after validating an information proposal. That
derived plan has no execution lane and disabled Web, and may retain the already-recorded assessment
intent so the selected clarification can resume the same user goal.

`AssessmentIntent.kind` is trimmed, non-empty, and deliberately open-ended. `user_criteria` is a
trimmed, non-empty-per-item, duplicate-free tuple whose input order is retained. Explicit criteria
are captured, not interpreted into dimensions in S8P2.

Expected material answer parts use the existing `MaterialQuestionPart` shape, retain provider order,
require unique part IDs, participate in proposal/plan content identity, and are copied unchanged into
the plan. Empty parts remain a serialized legacy-compatible/default representation for a query that
does not require decomposition; S8P2 does not perform the Task 8.7 sufficiency decision.

## Candidate review repair contract

The first independent Candidate reviews at `2026-07-17T09:46Z` reported zero Critical and four
Important findings. Before any acceptance, augment the same two S8P2 owner groups and prove a
review-driven RED for all four:

1. a model-proposed `official_only` domain outside a server-owned allowlist currently reaches the
   executable Web policy;
2. a negative/unbounded Web result count and a zero provider-call budget currently bypass the
   intended server budget; and
3. a recorded assessment proposal cannot currently carry its expected material answer parts into the
   retrieval plan; and
4. an institution/identity ambiguity can currently replace a valid refusal, safety, or control
   proposal with blocking clarification even though blocking is server-derived only for information.

The repair SHALL add no third public planner or new test owner. The query owner proves arbitrary
official domains and all Web-budget bypasses fail closed. The existing release-bound assessment owner
proves two ordered material parts survive proposal/plan serialization and content binding while the
legacy empty form stays byte/hash identical. Re-run all affected and broad checks after repair, then
obtain a targeted independent re-review with zero open Critical/Important.

Observed review-driven RED at `2026-07-19T07:12Z`: exactly `2 failed, 52 deselected`. The query
failure listed arbitrary official domain, zero/negative/unbounded Web budgets, and all three
non-information ambiguity replacements; the physical failure was the exact absent material-parts
sentinel before fixture acquisition. After the four repairs, the same command returned exactly
`2 passed, 52 deselected`.

## RED contract

Add exactly two strict-xfail test groups and no production edit before both failures are observed.

1. `test_s8p2_planning_proposal_taxonomy_and_safety_matrix_is_machine_validated` in the synthetic
   query-planning owner first proves the five valid forms above. It then requires
   `InvalidRetrievalPlanError("invalid_planning_proposal")` for wrong schema, behavior H, unknown
   interaction, model-proposed blocking clarification, unknown Web mode, F+information, A+refusal,
   control+information, information without Web, refusal with public/Web execution, safety with a
   public domain, safety+Universal Web, official-only outside safety, official safety with an empty
   allowlist or zero bound, and one same-class `model_construct` safety cross-wire. Before GREEN it
   raises exactly `_MissingS8P2ProposalTaxonomyValidation` with the accepted hostile case names.
2. `test_s8p2_release_bound_planner_captures_open_assessment_intent_and_user_criteria` resolves
   `knowledge_read.AssessmentIntent` before acquiring the physical fixture. Before GREEN its exact
   absence raises `_MissingS8P2AssessmentIntentContract`. After GREEN it uses the existing S8P1
   release-bound factory and real combined S7 graph to preserve kind `route_scale_readiness` and
   criteria `("公开部署规模", "维护成本")` unchanged through proposal trace, plan, release binding,
   institution/Person/Technology resolution, serialization, and content identity. It also rejects
   blank/duplicate/hostile intents, intent on non-information proposals, and proves absent-intent
   omission/legacy hashes.

Exact pre-GREEN outcomes, absent unrelated concurrent changes:

- combined focused normal: `2 xfailed, 52 deselected`;
- combined focused `--runxfail`: `2 failed, 52 deselected`;
- failures terminate directly at the two exact S8P2 sentinels;
- the assessment test resolves its sentinel before physical fixture acquisition.

Observed at `2026-07-17T08:38Z` exactly as specified. The unchanged query owner was `4 passed,
1 deselected`; the unchanged shared physical owner was `46 passed, 2 skipped, 1 deselected`.

Remove only the two xfail marks after production closes both exact missing behaviors.

## Required checks

- Exact RED outcomes above and unchanged existing owners GREEN while the two new groups remain RED.
- Focused GREEN: `2 passed, 52 deselected`.
- Query-planning owner: expected `5 passed`.
- Complete shared physical/release file: expected `47 passed, 2 skipped`.
- S8P1 focused owners: `2 passed`.
- Complete KnowledgeRead owner matrix: expected `17 passed`.
- Complete no-external Canonical V2: expected `336 passed, 141 skipped, 0 xfailed`, with actual counts
  recorded and no real failure.
- Ruff check/format for changed Python files, `py_compile`, complete Canonical V2 Pyright, strict
  OpenSpec validation, `git diff --check`, locked offline wheel/source parity, scope/secret/cache,
  package-entry, and frozen-source/target checks pass.
- One independent review ends with zero open Critical/Important findings. Minor/YAGNI is recorded and
  nonblocking unless it proves an explicit Spec/safety violation or current model-valid bypass.

## Acceptance evidence

- Query owner: `5 passed`; S8P1 focused: `2 passed`; shared physical/release owner: `47 passed,
  2 skipped`; KnowledgeRead owner matrix: `17 passed`; KnowledgeAnswer owner matrix: `13 passed`.
- Complete no-external Canonical V2: `336 passed, 141 skipped, 0 xfailed`, with the same three
  intentional hostile-answer serializer warnings.
- Complete Canonical V2 Ruff, changed-file format/compile, complete Pyright (`0/0/0`), strict
  OpenSpec, and `git diff --check` pass.
- Fresh offline wheel has 276 entries, no tests/`.agents`, and exact packaged/source parity for
  `knowledge_read.py` and `knowledge_answer.py`; frozen Milvus/Postgres/recovery-lab state matches
  S8P1 evidence.
- Initial independent review: zero Critical, four Important; all four have exact regression coverage
  and are repaired. Targeted re-review and a fresh final independent review each report zero
  Critical/Important and verdict `Accept`. Their Minor/YAGNI notes are recorded in the receipt and
  are nonblocking.
- The content-bound acceptance receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p2/verification-receipt.json`. Task 8.2 is
  checked at `56/80`; `acceptance.md` remains byte-identical to its pre-acceptance hash. The next
  slice-selection target is the smallest independently testable release-bound Task 8.3 execution
  slice.

## Evidence to update

- This Slice Contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p2/verification-receipt.json`.
- Existing `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- Existing OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` after acceptance; keep
  `acceptance.md` unchanged.
- Existing `.agents/portfolio.md` and code-grounded mainline plan after acceptance.

## Stop conditions

- Correct validation requires changing an Accepted public/storage/release contract, introducing a
  new product semantic absent from OpenSpec/ADR-020/ADR-022, or taking S8 runtime/S9 ownership.
- A valid Accepted S8 planner behavior cannot be represented by the finite matrix without a product
  decision, or legacy omission/hash compatibility cannot be preserved.
- Invalid same-class provider output reaches an executable plan; safety/general-Web boundaries can
  be bypassed; a provider can mint official domains or exceed/raise a server Web budget; material
  parts cannot reach the plan; non-information behavior is replaced by ambiguity clarification;
  assessment becomes fixed taxonomy/evidence judgment; existing owners regress; or a Critical/
  Important finding remains.
- The work requires provider credentials, reviewed S2C calibration, persistence, original/
  production-like state, or unauthorized Git/cutover actions.

## Done means

- Both exact REDs are observed, then become GREEN through the existing planner and one canonical
  lightweight intent type.
- Focused/sibling/full/static/strict/package/source checks and independent review satisfy every
  Required check with zero open Critical/Important findings.
- S8P2 is Accepted, Task 8.2 alone is checked, the formal ledger becomes `56/80`, acceptance.md stays
  unchanged, and the next independent Ready slice is named without treating S2C3C2 as a global goal
  blocker.

## Rollback note

Remove the shared intent type/import, optional proposal/plan fields and serializers, finite validators,
malformed-proposal normalization, two S8P2 test groups, and S8P2-only evidence; restore Task 8.2 to
open. S8P1 and earlier Accepted behavior, external state, and all release/source assets require no
rollback.
