# S8X Read-to-Answer Successor Handoff Audit — 2026-07-20

## Status and outcome

Accepted at `2026-07-20T17:26:45Z`; S8X closes no OpenSpec task and leaves the ledger at `65/80`.
The final implementation/test-integrity and Candidate-artifact reviews reported
`Critical=0/Important=0`. The traversal replan
review reported `Critical=0/Important=0`; reviewed hashes were audit
`940c94f5a1cfa48e1073ea7d4577c47f49e19505ccb9f7a85dcd24e06786a956`, plan
`faf42b9e456f55f36cd8a954a796a3cd3e55c48ae177334c92b1ade78415a0d8`, and contract
`6c70e29069951c50e7420e9b8330e8c03cbdbe892eb06103b3d9fee0e89044fe`. The first two siblings reached focused GREEN, but S11A preflight exposed one additional
producer-to-consumer sibling before acceptance. This remains a minimal pattern repair inside the
existing change, closes no OpenSpec task, and leaves the formal ledger at `65/80`.

The historical initial lean Specified review reported `Critical=0/Important=0`. Reviewed hashes were
audit `765024c5fa453f512682b560f3fcf9036a13eff112d4d14c1a281b87070a4a6b`, plan
`54950a4080398c4d9a45388bac1283c990036de0767d1c2daef221e071435d87`, and contract
`08ed4ae5e1b02e8cdb2e5311440fcdab216d78837c357319eab6348625730ea3`.

The defect class is **L4 + C1**: `KnowledgeRead` and `KnowledgeAnswer` share typed fields, but the
real producer never materializes the three successor shapes the real consumer uses. Accepted
`KnowledgeRead` returns `continuation_reasons` while `KnowledgeAnswer._candidate_offer` consumes
`continuation_candidates`. The planner returns planning-shape `AmbiguityDecision`; the answer
session consumes successor-shape `AmbiguityDecision`. The planner produces a public
`RelationshipPathProposal`, while Answer consumes `EvidenceSet.requested_traversal`; tests had
supplied that field by hand.

## Frozen dependencies

- `knowledge_read.py`: `466578bf0336c41f48dd271aeb5eb71fa2de36e3c46b96a4c39ecb412383169d`
- `knowledge_answer.py`: `8dec205620854910eadc3301b8a63da03d937bb53dd622c5280a0651f7e400de`
- Accepted S8C receipt: `9e912de80fad1d82c6b6e27d71f04b458a0c78799c104ff6ca0e659e0f43ebca`
- Accepted S9I receipt: `658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366`
- `tasks.md`: `87eb7c1e6d9e5b80e535cb94398f42798cdf4f3c83fb818011d0948519e32e54`
- `acceptance.md`: `1943943ee6fbc50b33357db1cceb987af93eba129042e6e4d6edfb68c9d5261f`

## Sibling search

- Admin consumer: S11A exposes the missing handoff but does not own its semantics.
- Canonical producer/consumer: exactly three confirmed siblings exist: continuation, blocking
  ambiguity, and public traversal. `EvidenceSet` already owns all successor fields; no addition is
  required.
- Tests: Read tests stop at reason/planning shapes and Answer tests construct successor shapes by
  hand. No owner executes the real public Read factory into the real public Answer factory.
- Docs/migrations/scripts: active OpenSpec already requires executable continuation, blocking
  clarification, and four public traversal directions; no schema, migration, provider, storage, or
  script change is required.

## Locked invariant and mapping

Real `KnowledgeRead` SHALL materialize only typed successor values that are provable from its exact
validated handles, evidence, coverage, sufficiency, and planner trace. Missing, duplicated,
cross-wired, or incomplete authority SHALL produce no executable option.

`KnowledgeAnswer` owns the second half of this one cross-seam invariant because it alone knows the
current selector outcome and the result set created during the current turn. Its candidate-offer
boundary SHALL validate only current-turn handles, current-turn item evidence, and a non-empty
current-turn result set. It SHALL NOT authorize a candidate from accumulated session evidence or
reuse a previous result set.

Only these existing meanings are mapped:

1. `evidence_gap` may become one `ContinuationCandidate` only when unresolved material parts bind
   one exact existing handle whose non-empty evidence IDs all exist in the returned evidence set.
2. `budget_exhausted` may become one result-set candidate only when the exact reason, exhausted
   receipt, exhaustion axis, and typed limitation agree and at least one returned handle has
   non-empty retained evidence. Enumeration coverage may be copied as `coverage_state` when present,
   but is not a trigger: non-enumeration queries may also exhaust budget. The candidate has
   `target_handle_ids=()`; `KnowledgeAnswer` requires non-empty current-turn selected IDs and a
   result set newly created from those exact IDs before it emits the option.
3. A real planning-shape blocking ambiguity always has `lanes=()` and reaches `_empty`. It becomes
   successor `outcome="blocked"` with deterministic decision/trace IDs, no candidates, and no
   options. It SHALL make the real answer path `clarification_only` with no primary claim. Planner
   traces SHALL NOT be converted into handles or evidence. Evidence-backed clarification choices
   remain an external-input/future residual and are not implemented by S8X.
4. Exactly one planner-owned relationship path becomes `requested_traversal` only when its exact
   `(relationship_type, direction, source_domain, target_domain)` tuple is one of the four Accepted
   company-to-patent, patent-to-company, professor-to-paper, or paper-to-professor public paths.
   Zero, multiple, unknown, or technology paths materialize no traversal request.

When `clarification_only` has no offer options, Answer uses a conservative request for one
distinguishing detail. It SHALL NOT claim that evidenced candidates are available. The existing
"select one of the evidenced candidates" wording is retained only when an actual ambiguity offer
contains at least one validated option.

For continuation, handle IDs must match exactly and uniquely. Candidate evidence is non-empty and a
subset of both the matched handle evidence and returned `EvidenceSet.items`. A Web handle additionally
requires an exact non-empty session binding, unexpired time, and retained snapshot authority. Missing,
duplicate, cross-wired, expired, or multiple unresolved-subject mappings produce no candidate.
Candidate IDs and order are deterministic and content-bound. Constraint pairs may copy only explicit
validated `ProtectedSlot` values; query prose, result order, and a guessed first handle are forbidden.

At the answer boundary, a `current_handle` candidate is valid only when every target ID belongs to
the current turn's handles and its evidence is a non-empty subset of both current items and the
target handles. It need not be displayed: an evidence-backed ambiguity switch may legally target a
viable alternative returned during the current turn. A `current_result_set` candidate keeps empty
target IDs and is valid only when the
current selector created a non-empty result set and candidate evidence is a non-empty subset of both
current items and the current displayed handles. Prior-turn handles, evidence, and result sets never
satisfy result-set authority; accumulated state never satisfies current-handle authority.

For physical traversal, Answer preserves the existing synthetic claim-binding fallback only when an
item has no physical trace and performs no string parsing or stripping. Traced evidence accepts only the exact path-specific content-bound
`LocalCanonicalRelationshipTrace`, `LocalPatentCompanyRelationshipTrace`,
`LocalProfessorPaperRelationshipTrace`, or `LocalPaperProfessorRelationshipTrace`, with exact public
source/target IDs, path tuple, and an item whose object and claim binding exactly match the trace.
Every cross-wired trace class, endpoint, path, claim, or item defaults to no traversal target.

The S8R2 vertical proves source authority through the public session boundary. The same real Answer
instance first receives a public `answer()` setup turn that displays evidence-bound
`company-robotics` as `active_anchor`. A second turn uses
`SessionDirective(referent="active_anchor")` and the unchanged real S8R2 `EvidenceSet`. The expected
receipt is exactly source `("company-robotics",)`, target `("patent-ada",)`, path
`company_to_patent`. Tests and production SHALL NOT mutate `_sessions`, infer source from the target
or claim, or add a source handle to the traversal turn.

The setup turn has one narrow fixture exception: it may use a fresh, fully Pydantic-validated
`EvidenceSet` with the same release, exactly one evidence-aligned `company-robotics` item and handle,
no traversal, and a selector that displays the company with `claims=()`. It need not come from real
Read. This fixture SHALL NOT copy, complete, or mutate the real traversal result; the second turn
still receives the untouched real planner/Read S8R2 output.

TDD is staged so no assertion masks the consumer defect: RED-A is the four real physical Read nodes
returning `requested_traversal=None`, followed only by the Read whitelist GREEN-A. RED-B then uses
the legal prior setup turn plus unchanged real S8R2 output and must observe a present traversal
receipt with `target_handle_ids=()` before the Answer physical-trace matcher is implemented.

No new reason, operation, label policy, planner decision, candidate, relationship, or evidence is
invented. Ambiguity choices, non-blocking ambiguity, eligible-next-hop generation, and broader policy
reconciliation are outside this correction.

## Pattern-fix report

- Reported cases: real S11A continuation cannot produce a selectable offer, blocking output cannot
  drive truthful clarification, and real public traversal cannot produce a `TraversalReceipt`.
- Defect class: L4 + C1.
- Fix level: Level 4 boundary materialization with a Level 5 three-sibling regression matrix.
- Shared fix: one Read successor-materialization boundary plus Answer current-turn offer and exact
  physical-traversal authorization guards, with one truthful zero-option clarification text branch.
- Remaining risk: future successor fields require a real producer-to-consumer owner, not isolated
  constructor tests.

The first two siblings have production/test changes and fresh GREEN evidence. This replan changed no
additional production code. No database, index, source, provider, task checkbox, Commit, Push, PR,
promotion, or Cutover was changed.

## Candidate evidence — 2026-07-20T17:20:26Z

- The final Read/Answer hashes are
  `a28488c400a8e1dea66b3ad9f87fc048895b4f96f0da15548bcc9590e85b86fc` and
  `386ce550f9b3f1c47c76f854307d9461cb8177bf44968dd7f4f51678ee104d9e`.
- The six-test dedicated owner and physical traversal owner hashes are
  `29191a15c875cf95f4d2c6c432a2c6136c3f4cd9571369ef00306a4767b79d01` and
  `61c9ec362e39d7e4eca9a3db7e02d9bf5ebde095e4acb0f02c989437baed147f`.
- The final dedicated owner passed `6 passed in 0.41s`; the final complete Canonical V2 suite passed
  `363 passed, 148 skipped, 3 warnings in 327.91s`. The three warnings are the retained hostile
  Pydantic serialization probes.
- Complete Canonical V2 Ruff and format checks, `py_compile`, Pyright, strict OpenSpec,
  `git diff --check`, and locked-offline lock validation passed. Pyright reported zero findings.
- A fresh 278-entry offline wheel matched both final production source hashes, included each module
  exactly once, and included no tests or `.agents` entry. Its SHA-256 was
  `72c07e7334acfa53ba8aa5a49923bf6ac5fb362f9257802603c60ae9fa13ec2e`.
- Frozen original PostgreSQL/Milvus/forensic sentinels remained exact under read-only inspection.
  The historical aggregate forensic manifest identity remained consistently recorded but was not
  claimed as independently recomputed because its original generator was not retained.
- Final reviews, including the post-Pyright explicit-value narrowing, reported zero Critical,
  Important, Minor, or YAGNI findings. The ledger remains `65/80`; Tasks 8/9, S11A, OpenSpec
  acceptance, portfolio, and status pointers were not changed.
- A separate Candidate-artifact review reported `Critical=0/Important=0/Minor=0/YAGNI=0`, permitting
  the mechanical Accepted transition at `2026-07-20T17:26:45Z`. Acceptance changed only these S8X
  evidence artifacts; code, tests, task/acceptance ledgers, portfolio, S11A, and remote Git remained
  untouched.
