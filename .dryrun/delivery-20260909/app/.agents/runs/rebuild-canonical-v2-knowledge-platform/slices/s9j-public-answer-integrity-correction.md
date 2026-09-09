# Slice Contract: S9J Public Answer Integrity Correction

## Status

Candidate at `2026-07-21T09:48:56Z`; Accepted at `2026-07-21T09:57:11Z` with the formal ledger
unchanged at `65/80`. The initial
contract review closed four Important ambiguities. The implementation review then exposed one
escaped Important branch where `suppress_claims` retained the typed material gap but omitted its
public sentence. Exact RED plus sibling coverage for blocking ambiguity, unresolved Web traversal,
and selector degradation closed that class. Final independent spec and code/test-integrity reviews
report zero open Critical/Important findings; Minor/YAGNI are non-blocking. No OpenSpec task
checkbox changed.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
- Requirements: grounded-progressive-answer “Every material answer claim maps to evidence”, “LLM
  failure degrades by stage”, “Continuation offers are conditional, structured, and executable”,
  and “Online work obeys explicit budgets and progress behavior”.
- Corrects the Accepted S9 answer-composition mechanics and the Accepted S11A recorded adapter
  fixture before S11B acceptance.
- Depends on: Accepted S9I and historical Accepted S11A. The current in-progress S11B candidate
  fixture owner is an affected successor consumer, not an Accepted dependency; it resumes only
  after binding the Accepted S9J receipt and corrected chat hashes.
- Plan: `../s9j/implementation-plan.md`.

## Goal

Guarantee that machine/audit identifiers remain in structured trace fields but never become public
answer copy, and that every material `missing` or `conflicting` sufficiency outcome becomes both a
typed `AnswerLimitation` and a deterministic user-facing gap sentence.

For the exact reproduced turn, the public result must say that Robotics Co is represented by the
accepted local profile evidence and that the 2026 current-revenue request lacks retained supporting
evidence. The response must not expose the lookup SHA, evidence/continuation IDs, or raw execution
enums. The structured trace must retain those exact audit values and the executable continuation
operation.

## Non-goals

- Do not invent or recollect 2026 revenue.
- Do not change evidence bindings, release/index manifests, retrieval admission, provider policy,
  session semantics, or continuation execution operations.
- Do not localize every product string or introduce a global i18n framework.
- Do not modify the reference-only React tree in S9J.
- Do not broaden into Task 9.8 aggregate claim-level acceptance or S12 full-candidate construction.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`
- Focused Canonical V2 answer tests.
- `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`
- `apps/admin-console/backend/services/canonical_v2_chat.py`
- `apps/admin-console/tests/test_canonical_v2_consumer_migration.py`
- `apps/admin-console/backend/static/chat.html`
- This contract/plan and S9J verification receipt/evidence.
- Existing S11A/S11B receipt/hash pointers only after Candidate review proves the correction.

## Forbidden changes

- No schema, migration, storage, identity, relationship, release, index, source, provider, or active
  pointer change.
- No weakening of grounding, claim-binding, session, continuation, or candidate-runtime checks.
- No UI-only masking of an API answer that still contains the opaque material claim.
- No translation of structured operation/reason/ID fields; public labels may be localized while
  the structured values remain exact.
- No original Postgres/Milvus/forensic access or write.
- No Commit, Push, PR, Cutover, promotion, archive, or destructive cleanup.

## Expected unchanged behavior

- Exact `EvidenceClaimBinding`, claim-evidence map, evidence IDs, release IDs, and continuation
  operation/option binding remain unchanged.
- Supported semantic claims remain grounded through the existing `_ground_claim` checks.
- Product-capability, enumeration, ambiguity, safety, assessment, session, and deterministic
  degradation behavior remains unchanged except that opaque binding values are rejected from public
  copy and ordinary material gaps become explicit limitations.
- The live preview on port 18188 remains available until a replacement process is verified.

## TDD RED contract

1. Add a focused KnowledgeAnswer test that supplies a semantic supported claim plus one `missing`
   material part and proves current code omits the typed limitation/gap sentence.
2. Parameterize opaque-copy rejection for:
   - `canonical_projection` with a 64-hex lookup digest;
   - `semantic_recall` with a 64-hex projection digest; and
   - a relationship binding whose value is a `canonical:*` or `reference:*` identifier.
   The RED must show those exact machine values currently survive in public claim text.
3. Strengthen the real S11A HTTP owner so the exact first turn fails while the public strings expose
   a digest/raw enum and omit the 2026 revenue gap, while the structured trace remains exact.

## Required behavior

- A selector proposal whose public `text` copies an internal projection digest or exact
  `canonical:`/`reference:` binding value is rejected before admission. S9J does not rewrite an
  unsafe claim in place and does not preserve its claim ID as admitted. The recorded selector is
  separately corrected to emit semantic text; that corrected proposal retains and admits the exact
  original subject/predicate/value/evidence/status binding and claim-evidence map.
- The answer-composition module, not a UI caller, maps every material non-supported sufficiency part
  to at most one typed limitation. `missing` uses exact code `material_evidence_missing`;
  `conflicting` uses exact code `material_evidence_conflicting`. Both bind the material part ID,
  `stage="sufficiency"`, the accepted report rationale, and `material=True`.
- A pre-existing material limitation with the same non-null `material_part_id` owns that part and
  suppresses the generic S9J limitation/sentence. This preserves the specialized
  `direct_product_capability_evidence_missing` result and prevents duplicates.
- Material-gap public copy never renders `MaterialQuestionPart.text` directly. A narrow server-owned
  display rule renders `current_revenue` only when `requested_value` is an exact four-digit year:
  Chinese queries use `<year> 年当前营收`; non-Chinese queries use `<year> current revenue`. Every
  other predicate uses a generic localized “material part of the question” label. No registry or
  caller-authored display string is introduced.
- Deterministic answer text appends one bounded server-owned sentence per unspecialized unresolved
  part. It never turns the requested value into a confirmed fact.
- The optional `ProseRenderer` is not the final authority. Its string is rejected when it contains
  any structured-only binding value, evidence/claim/continuation ID, or raw execution enum from the
  turn. Rejection returns the deterministic safe text and an exact material limitation
  `prose_synthesis_failed` with `stage="prose"` and `failure_kind="unsafe_output"`.
- Server-owned material-gap sentences are appended after a safe prose result unless already present
  byte-for-byte, so prose cannot omit them. A hostile-renderer RED proves both identifier fallback
  and mandatory gap retention.
- The recorded S11A selector derives supported public text from the trusted projection/handle or
  typed relationship semantics while retaining the original binding triple for audit.
- The first-turn public envelope contains `Robotics Co`, states that retained evidence does not
  support the 2026 current-revenue request, and contains no 64-hex digest, evidence/continuation ID,
  `evidence_gap`, or `targeted_evidence_search`.
- Structured trace continues to retain the lookup digest, incomplete sufficiency report, exact
  missing material part, and `targeted_evidence_search` operation.
- The built-in candidate UI renders the server answer and typed limitations, and maps the known
  continuation operation to a concise Chinese public label without changing its operation.
- The S11A HTTP adapter maps the six already-accepted continuation reasons/operations to bounded
  server-owned public prompt/label/hint copy. The trace retains the exact reason, operation, option
  ID, targets, constraints, and evidence IDs; no new continuation behavior is introduced.

## Required checks

- Exact RED is observed for every new test before implementation.
- RED covers `material_evidence_missing`, `material_evidence_conflicting`, specialized-limitation
  precedence/no-duplicate behavior, hostile `MaterialQuestionPart.text`, and a hostile prose
  renderer that tries to reintroduce structured-only values or omit the gap sentence.
- Focused KnowledgeAnswer GREEN and affected S9 answer/session owners pass.
- Exact Accepted S11A HTTP owner proves the recorded missing-revenue gap, semantic public copy,
  preserved structured audit, and executable continuation data.
- Exact S11B candidate owner executes the built-in continuation-label mapping, and the Accepted
  S10O UI owner passes.
- A fresh manifest-selected real-data browser/API replay proves two useful turns, current-Web
  evidence, no opaque public strings or operational meta copy, responsive desktop/mobile layout,
  bound session state, and a clean console. It does not substitute a fake entity merely to trigger
  the recorded missing-revenue fixture; that exact branch remains owned by the S11A HTTP test.
- Ruff check/format, `py_compile`, changed-scope Pyright, inline-JS parse, strict OpenSpec, and
  `git diff --check` pass.
- Independent spec review then code-quality review report zero open Critical/Important findings.

## Evidence to update

- This contract and `../s9j/implementation-plan.md`.
- `../s9j/verification-receipt.json` after Candidate evidence exists.
- Existing S11A/S11B hashes and verification pointers only after acceptance.

## Stop conditions

- Correct public copy would require weakening structured grounding or changing an evidence binding.
- The material-part text cannot be trusted under the existing validated planning interface.
- A fix requires schema, migration, provider, source, release/index, or production-like changes.
- An unresolved Critical/Important review finding has no safe in-scope repair.

## Done means

- Required RED/GREEN and sibling matrix evidence exists.
- The reproduced first and second turns are useful, grounded, and contain no internal identifier as
  prose; the first explicitly names the revenue evidence gap.
- Structured audit and executable continuation data remain exact.
- S11A/S11B affected owners and static/browser checks pass.
- Independent review has zero open Critical/Important findings.
- S9J is Accepted and S11B may resume; no OpenSpec task checkbox changes at S9J.

## Rollback note

Restore the pre-S9J answer module, recorded selector fixture, static renderer, and focused tests.
No database, index, release pointer, source, or remote Git state requires rollback.
