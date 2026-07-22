# Slice Contract: S8X Successor Handoff Materialization

## Status

Accepted at `2026-07-20T17:26:45Z`; S8X closes no OpenSpec task and leaves the ledger at `65/80`.
The final implementation/test-integrity and Candidate-artifact reviews reported
`Critical=0/Important=0`. The traversal replan
review reported `Critical=0/Important=0`; reviewed hashes were audit
`940c94f5a1cfa48e1073ea7d4577c47f49e19505ccb9f7a85dcd24e06786a956`, plan
`faf42b9e456f55f36cd8a954a796a3cd3e55c48ae177334c92b1ade78415a0d8`, and contract
`6c70e29069951c50e7420e9b8330e8c03cbdbe892eb06103b3d9fee0e89044fe`. The historical initial review reported `Critical=0/Important=0`. Reviewed hashes were audit
`765024c5fa453f512682b560f3fcf9036a13eff112d4d14c1a281b87070a4a6b`, plan
`54950a4080398c4d9a45388bac1283c990036de0767d1c2daef221e071435d87`, and contract
`08ed4ae5e1b02e8cdb2e5311440fcdab216d78837c357319eab6348625730ea3`.

## Parent

- Existing OpenSpec change: `rebuild-canonical-v2-knowledge-platform`.
- Corrects the Accepted S8C producer boundary consumed by Accepted S9I and future S11A.
- Closes no OpenSpec task and changes no ledger checkbox.

## Goal

Make the real public `KnowledgeRead` output directly consumable by the real public
`KnowledgeAnswer` for the three already-specified successor behaviors: validated continuation,
blocking ambiguity, and typed public traversal.

## Required behavior

- Existing `continuation_reasons` remain unchanged.
- `evidence_gap` materializes only when every unresolved material part binds the same exact unique
  returned handle. Its evidence is non-empty and belongs to both that handle and returned items.
- `budget_exhausted` materializes only when the exact reason, exhausted receipt, exhaustion axis,
  and typed limitation agree and at least one returned handle has non-empty retained evidence.
  Enumeration coverage is optional metadata, not a trigger.
- Existing operation/target pairs remain exact:
  `evidence_gap -> targeted_evidence_search/current_handle` and
  `budget_exhausted -> resume_bounded_search/current_result_set`.
- Continuation candidate IDs/order are canonical-content-bound. Constraint pairs copy only explicit
  validated protected-slot values. No query-prose or first-result inference is allowed.
- Canonical handle IDs must match exactly and uniquely. Web handles additionally require exact live
  session and retained snapshot authority. Missing, duplicate, cross-wired, expired, or multiple
  unresolved-subject authority produces no candidate.
- Planning-shape blocking ambiguity reaches `_empty` and becomes successor `outcome="blocked"` with
  deterministic IDs, no candidates, and no options. The real answer returns
  `clarification_only` and empty claims. With zero options its text conservatively asks for a
  distinguishing detail and does not claim evidenced candidates are available. Planner traces never
  manufacture handles/evidence.
- Every applicable Read return path uses the same boundary helper and returns exact validated models.
- Exactly one planner-owned path becomes `requested_traversal` only for these Accepted tuples:
  `company_has_patent/company_to_patent/company/patent`,
  `company_has_patent/patent_to_company/patent/company`,
  `professor_authored_paper/professor_to_paper/professor/paper`, and
  `professor_authored_paper/paper_to_professor/paper/professor`. Zero, multiple, unknown, or
  technology paths remain `None`.
- `KnowledgeAnswer` authorizes `current_handle` only against current-turn handles/items and target
  handle evidence; display is not required for a current-turn viable ambiguity alternative. It
  authorizes `current_result_set` only against non-empty current-turn selected IDs, the result set
  newly created from them, current-turn items, and current displayed-handle evidence. Accumulated
  state never authorizes `current_handle`; prior-turn evidence/result sets never authorize
  `current_result_set`.
- Answer preserves the synthetic traversal fallback and performs no string parsing/stripping.
  Physical targets require the exact path-specific content-bound local relationship trace, public
  source/target IDs and path tuple, plus exact item object and trace claim-binding equality.
  Cross-wiring defaults to no target.
- The physical mapping is exact: `LocalCanonicalRelationshipTrace` binds
  `displayed_company_id -> candidate_canonical_id` with company-to-patent and
  `patent_has_applicant` in typed inverse orientation; `LocalPatentCompanyRelationshipTrace` binds
  `displayed_patent_id -> candidate_canonical_id` with patent-to-company and that predicate in typed
  forward orientation; `LocalProfessorPaperRelationshipTrace` binds
  `displayed_professor_id -> candidate_canonical_id` with professor-to-paper and
  `professor_attributed_to_paper` in typed forward orientation; `LocalPaperProfessorRelationshipTrace`
  binds `displayed_paper_id -> candidate_canonical_id` with paper-to-professor and that predicate in
  typed inverse orientation. For traced evidence, fallback is forbidden: `item.object_id` must equal
  the target and its claim subject/predicate/value/status must exactly equal the trace claim fields.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` and
  `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`.
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_answer_successor_handoff.py`.
- Direct traversal-handoff assertions only in the existing S8R2/S8R5/S8R3/S8R4 nodes in
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`.
- S8X audit/plan/contract/receipt and existing status pointers after acceptance only.

## Forbidden changes

- Other planner/answer semantics, providers, storage, schema/migrations, public serialized fields,
  S11A code, OpenSpec tasks/acceptance, or any database/index/source target.
- New continuation reasons/operations, ambiguity choices, eligible-next-hop inference, fabricated candidates/evidence,
  copied test `EvidenceSet`, fake Read/Answer implementations, traversal inference from prose or
  string normalization, or option creation from query prose.
- Commit, Push, PR, promotion, Archive, Cutover, or destructive cleanup.

## Required checks

- Exact RED before production; focused GREEN through actual public planner/read/answer factories.
- Prior-turn poisoned evidence/result-set cannot create `resume_bounded_search`; a separately valid
  current-turn `targeted_evidence_search` option is not suppressed.
- Same-subject multi-part, deterministic candidate identity/order, authority-sensitive identity,
  and Canonical/Web missing/duplicate/cross-wire/session/snapshot/expiry matrices are covered.
- Zero-option blocking ambiguity has truthful conservative clarification text; selection wording
  requires at least one actual validated option.
- Existing S8R2/S8R5/S8R3/S8R4 nodes assert direct `requested_traversal`; that same S8R2 node passes
  its real `EvidenceSet` to a real Answer session and obtains an exact `TraversalReceipt` without
  copying the `EvidenceSet`.
- RED-A is four direct physical Read failures at `requested_traversal=None`; only after that does the
  Read whitelist reach GREEN-A. RED-B is separate: the same real Answer instance first receives a
  public `answer()` setup turn that displays evidence-bound `company-robotics` as active anchor, then
  receives the unchanged real S8R2 output with `SessionDirective(referent="active_anchor")`. Before
  the Answer matcher, the receipt exists with `target_handle_ids=()`; GREEN-B requires exact source
  `("company-robotics",)`, target `("patent-ada",)`, and path `company_to_patent`.
- Neither tests nor production may mutate `_sessions`, infer a source from target/claim, or add a
  source handle to the traversal turn.
- A narrow setup-only exception permits one fresh, fully Pydantic-validated same-release
  `EvidenceSet` with exactly one evidence-aligned `company-robotics` item/handle, no traversal, and
  selector `claims=()`. It exists only to establish prior public Answer state and may not copy,
  complete, or mutate the real S8R2 traversal output, which remains untouched on the second turn.
- Zero/multiple/unknown/technology paths and physical trace class/endpoint/path/claim cross-wires
  default to no traversal request or target.
- Accepted focused S8/S9 owners and complete no-external Canonical V2 suite.
- Ruff, format, py_compile, Pyright, strict OpenSpec, diff/scope/secret/cache guards.
- Fresh locked-offline wheel with source-entry hash parity and no tests/run artifacts packaged.
- Frozen original PostgreSQL/Milvus/forensic identities and hashes remain exact.
- Independent Candidate review reports `Critical=0/Important=0`.

## Stop conditions

- Correctness requires changing an existing public field, answer behavior outside the current-turn
  offer or exact physical traversal authorization guards, planner policy,
  provider/storage/schema, or S11A.
- Exact authority cannot be proven without inventing a handle, evidence, coverage, discriminator,
  operation, or relationship.
- Any unrelated Accepted predecessor regression or open Critical/Important finding remains.

## Done means

The real Read-to-Answer vertical produces executable typed continuation only from exact current-turn
authority, never reuses poisoned prior state, blocking ambiguity default-denies unsupported
answers/options, all four Accepted public traversal paths remain exact and every other path/trace
defaults to none, all required checks pass, and S8X stops at Candidate with Tasks 8/9/S11 and ledger
`65/80` unchanged. The historical S9I receipt remains untouched; the S8X receipt records the
superseding Read/Answer hashes and owners without changing the ledger. S11A resumes only after
Accepted S8X.

## Acceptance checkpoint

Candidate evidence and the separate zero-finding artifact review are recorded in
`s8x/verification-receipt.json`. Final source/test hashes are frozen there; all required behavior,
focused, complete-suite, static, package, source, hygiene, and independent-review gates passed. The
formal task ledger remains `65/80`. Before becoming Ready, S11A must return to Specified, bind the
final Accepted S8X receipt and live hashes, revalidate its baseline, and obtain one lean review.
