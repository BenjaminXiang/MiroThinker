# Slice Contract: B — grounded-answer

## Status

Specified — blocked until Slice A is Accepted

Internal checkpoints after unblocking: B0 foundation -> B1 grounding -> B2 consumers/rollout. Only
one may be Ready/In Progress; each requires Candidate review and Accepted evidence before the next.

## Parent

- OpenSpec change: `openspec/changes/close-retrieval-generation-contract/`
- Depends on: accepted `slices/a-oracle-red.md`

## Goal

Create one canonical evidence-to-claim-to-citation contract across backend API, synthesis, and UI,
with truthful typed outcomes, derived legacy fields, shadow comparison, and immediate rollback.

## Non-goals

- Changing Type1/Type2/Q004/Q017 retrieval semantics (Slice C).
- Adding Type4 hybrid retrieval/ranking (Slice D), Type3 traversal (Slice E), or index/data lifecycle
  changes (Slice F).
- Removing legacy API fields or implementation during this slice.
- Rewriting non-paper domain ranking.

## Allowed scope

- Chat response/Pydantic models, evidence assembly, synthesis prompt/output schema, validator,
  deterministic renderer, outcome mapping, compatibility projection, and rollout/shadow config.
- Reversible 30-minute session-owned immutable result-set/item and
  `chat_clarification_action` stores, signed cursor codec, golden JSON/OpenAPI fixtures,
  response-integrity signature, privacy-safe clarification nonce/selection TTL state, and minimized
  redacted feedback metadata.
- An additive chat-owned retrieval port/new method plus internal adapter status propagation: typed
  candidate/lane status/error/timing/snapshot/trace envelopes, while the shared legacy list method,
  candidate selection, and ranking remain unchanged.
- React and deployed static `/chat` API types/rendering (or explicit tested static-route redirect/
  deprecation), citation/result rendering, feedback, and quality/provenance presentation.
- Slice-owned tests/fixtures and evaluation adapters required by the accepted Slice A oracle.
- OpenSpec/run/portfolio evidence for Slice B.

## Forbidden changes

- Retrieval query classification, paper SQL/vector/lexical ranking, company traversal, paper
  eligibility, unrelated migrations, canonical/business data, or Milvus writes. Only the explicit
  reversible IDs/sort-tuples-only result-set/item and minimized `chat_clarification_action`
  migrations are allowed.
- A second citation list or model-owned numeric citation identity.
- Silently dropping invalid claims while still returning `success` without the required-intent gate.
- Treating retrieval/synthesis failures as `no_result`.
- Canonical external cutover without accepted shadow evidence.

## Expected unchanged behavior

- In `legacy` and `shadow` modes, public legacy response behavior remains compatible.
- Retrieved candidate sets, ordering, and domain routing remain unchanged.
- Existing supported non-paper answers remain semantically stable, except additive canonical fields
  and truthful error/degradation metadata when canonical mode is explicitly exercised.
- The additive result-set and clarification-action tables do not rewrite existing chat sessions or
  feedback; no raw canonical response store or unauthenticated detailed evidence surface is added.

## Internal checkpoint contracts

### B0 — foundation

- **Status:** Specified; becomes Ready only after Slice A Accepted and before B1/B2 edits.
- **Goal:** freeze the complete old/new public schema and provenance feasibility, then introduce only
  the additive typed retrieval-status port plus reversible IDs/sort-tuples result store/cursor and
  minimized `chat_clarification_action` replay state.
- **Non-goals:** evidence composition, synthesis/verifier behavior, external canonical fields,
  frontend/feedback/shadow behavior, or any candidate-selection/ranking change.
- **Allowed scope:** provenance preflight; Pydantic/OpenAPI/golden fixtures; additive port/adapters;
  result-set/item plus `chat_clarification_action` migrations, cursor/action codecs, TTL, and cleanup.
- **Forbidden scope:** raw response/evidence persistence, retrieval semantics, model prompting,
  consumer changes, or making canonical mode externally selectable.
- **Required checks/evidence:** provenance matrix; old/new required/null/empty/absent fixtures for
  every current `ChatRequest`/`ChatResponse` field, including bare hint and signed clarification
  selection; port projection tests; migration upgrade/downgrade, TTL, session/cursor/privacy tests;
  rollback proof; review and immutable diff/artifact hash.
- **Stop/rollback:** stop on an ungroundable P0 field, non-additive API need, auth boundary, or ranking
  change. After TTL drain, downgrade only result-set/action tables and codec changes and revert the
  B0 diff; no response data export is expected because no raw response is stored.

### B1 — grounding

- **Status:** Specified; becomes Ready only after B0 Accepted.
- **Goal:** make canonical evidence, typed supports, result/lane assertions, outcomes, validation,
  rendering, and compatibility projection one closed server-owned contract.
- **Non-goals:** frontend/static consumer rollout, feedback storage, shadow traffic, cutover, or
  Type1-Type4 retrieval-semantic changes.
- **Allowed scope:** evidence ID/composer, structured synthesis, bounded verifier, required-intent
  validation, canonical serialization/signature, typed outcomes, and compatibility derivation.
- **Forbidden scope:** a second citation/evidence list, model-owned markers, silent unsupported-claim
  dropping, raw canonical persistence, or changing candidate selection/order.
- **Required checks/evidence:** professor+paper dropped-evidence RED, citation identity, support and
  full-set/lane proof tests, evidence/result-set-backed clarification facts/counts, verifier failure/
  malformed/timeout fixtures, outcome matrix, old/new API golden fixtures, semantic gates, rollback
  proof, review, and immutable diff/artifact hash.
- **Stop/rollback:** stop if required claims cannot be grounded under B0 provenance, validation must
  be weakened, or a retrieval behavior change is needed. Disable canonical construction behind the
  internal flag and revert B1 while retaining accepted B0 schema/store primitives.

### B2 — consumers and rollout

- **Status:** Specified; becomes Ready only after B1 Accepted.
- **Goal:** migrate both real chat consumers, add minimized signed feedback, prove failure-isolated
  shadow behavior, and leave an immediate tested legacy rollback.
- **Non-goals:** removing legacy mode/fields, durable raw review UI, auth changes, or retrieval/data
  behavior changes.
- **Allowed scope:** React and deployed static `/chat` (or tested redirect), renderer selection,
  signed-echo feedback, rollout mode, redacted shadow diffs, sampling, and observability.
- **Forbidden scope:** mixed renderers, canonical-field leakage in shadow, critical-path shadow
  execution, raw query/snippet/URL/provider persistence, or cutover before accepted evidence.
- **Required checks/evidence:** actual-route browser proof, consumer fixtures for every retained
  field and hint+token selection/no-default-auto-selection, feedback tamper/replay/key/minimization
  tests, external shadow identity, stratified frozen
  sampling, overhead/SLO evidence, rollback drill, review, and immutable diff/artifact hash.
- **Stop/rollback:** stop on consumer incompatibility, privacy/auth expansion, legacy response drift,
  or latency breach. Set mode to `legacy`, stop shadow workers, revert B2 consumer/feedback changes,
  and retain Accepted B0/B1 internals unused externally.

## Required checks

- RED-before-GREEN model/unit tests for stable evidence IDs, ordered evidence, claim validation,
  typed outcomes, compatibility derivation, and deterministic rendering.
- Deterministic typed support tests for entity/field/relation/set/count/absence claims plus
  cited-span entailment and fail-closed verifier tests for derived material claims.
- `/api/chat` integration fixtures for professor+paper composition, cross-domain budgets, unknown
  evidence IDs, unsupported claims, malformed model output, retrieval failure, and synthesis failure.
- Shared-source-contract, local/Web lane, relation-tier, result-set/page/cursor, clarification,
  unsupported-query, and retrieval-lane status/error integration coverage.
- Read-only per-domain/field shared-provenance coverage report and negative tests forbidding
  synthesized DOI/ID URLs, row timestamps, and table locators as source evidence.
- Frontend lint/type/test/build checks available in the current workspace.
- Browser walkthrough of the actual served `/chat` route and any retained React route proving a
  marker resolves exact canonical evidence and displays result/partial/Web/secondary metadata.
- Golden API/OpenAPI compatibility, result-set source-mutation/TTL/cross-session/invalid-cursor, and
  signed-echo/minimized feedback tests including lossy Web/relation IDs and tamper/replay/key cases.
- Cross-process/backend-frontend golden vectors for `result-manifest-v1`,
  `response-integrity-v1`, `cursor-v1`, and `clarification-token-v1`, including Unicode/number/empty/odd-tree, canonical
  encoding, proof, key rotation, expiry, session binding, and tamper cases.
- Migration upgrade/downgrade, TTL cleanup, cascade/retention, and existing chat-session/feedback
  compatibility tests for the allowed IDs/sort-tuples-only result store and hashed/minimized
  clarification-action store, including atomic same-ID retry versus different-ID conflict.
- Legacy/shadow/canonical mode tests and immediate legacy rollback.
- Field-absence-is-legacy/one-renderer compatibility matrix, lossy Web/relation projection guard,
  failure-isolated off-critical-path shadow, 50 ms p95/100 ms p99 overhead, and privacy-safe
  stratified cutover gate whose sampling frame/window/seed/dedupe/hash was frozen before output.
- Frozen Slice A retrieval/citation/semantic/regression gates and synthesis-on p95 <=15s by bucket.
- Strict OpenSpec validation and diff check.

## Evidence to update

- Slice B section in `verification.md` and `acceptance.md`, including response examples with
  non-secret raw artifacts, browser evidence, shadow diffs, latency, review, immutable hashes, and
  rollback.
- Completed Slice B tasks and change log.
- Portfolio status; make Slice C Ready only after Slice B Accepted.

## Stop conditions

- Slice A is not Accepted or its oracle/snapshot must change.
- A public-field removal, non-additive contract change, or retrieval semantic change is needed.
- Prompt budget cannot preserve required-domain coverage without a new product trade-off.
- A required P0 fact lacks joinable shared source evidence and repair needs canonical schema/data or
  auth/trust-boundary expansion outside this slice.
- Frontend and backend require incompatible evidence identity/order.
- Semantic/citation GREEN depends on weakening the canonical validator or judge rubric.
- Scope spreads into Slice C-F.

## Done means

- One atomic evidence list is the only prompt/validator/API/UI citation source.
- Typed claims and server rendering reject unsupported/unknown references; derived material claims
  fail closed when cited-span entailment cannot be established.
- Outcomes distinguish success, partial, absence, retrieval error, and synthesis error.
- Legacy output is derived, shadow evidence is accepted, rollback works, and UI identity is proven.
- All Slice B gates pass; independent review, immutable diff/artifact hashes, and Accepted status
  are recorded; isolated commits are linked only when explicitly authorized.
- B0, B1, and B2 each have their own immutable diff/artifact hash, review, checkpoint rollback, and
  Accepted decision; partial B work is never a dependency of Slice C.

## Rollback

Set `CHAT_GROUNDED_ANSWER_MODE=legacy`, stop shadow workers, expire/clean the minimized feedback
tokens/records under their retention rule, downgrade the additive IDs/sort-tuples-only result-set
and minimized clarification-action tables after TTL drain if removal is required, and revert the relevant B checkpoint diff (or an
explicitly authorized isolated commit). No raw canonical-response export and no Milvus rollback
belongs to this slice. A real B0/B1/B2 rollback applies the Epic matrix and invalidates the listed
downstream checkpoints; the initial chat-legacy switch alone is only external safety rollback.
