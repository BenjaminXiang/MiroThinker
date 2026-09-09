# Slice Contract: S11A Release-Bound Chat HTTP Adapter

## Status

Accepted at `2026-07-20T19:56:07Z`. The complete release-bound HTTP vertical, focused and
predecessor checks, package/source/protected gates, guarded Admin and complete Canonical V2 suites,
two independent final reviews, and two Admin-exception audits are complete with zero open
Critical/Important findings. The guarded Admin result has zero S11A-related unexpected failures;
its one unrelated pre-existing `backend/api/domains.py`/quality-status-test call-order mismatch is
recorded separately. The unsafe dotenv-restored real-data attempt is explicitly not acceptance
evidence. No OpenSpec task or acceptance checkbox changed, so the ledger remains `65/80`.

Revalidated and Ready at `2026-07-20T17:43:17Z` after returning to Specified at
`2026-07-20T17:32:44Z` because Accepted S8X superseded the live Read/Answer handoff. The historical
Ready state at `2026-07-20T14:31:57Z` remains superseded. A fresh lean review of exact Specified
hashes audit `0a7e0bcd6bd49c6a9eaef15103ef2b539bdaf351f067e2a62f8d635ab6a05310`, plan
`99ab2e060a0bf2202182034e0cb7d4c506383ef175255eca33e9a3d1d64e23ea`, and contract
`5894be2329ffc22d8f8797e2db6b445f4032d8209e98fa542c4d210954ad1bc2` reported
`Critical=0/Important=0/Minor=1/YAGNI=0`. The recorded Minor is non-blocking plan prose; the exact
signature schema and SHA are unchanged. S8C/S9I remain the Accepted capability owners, while
Accepted S8X is authoritative for the current successor handoff.
Its receipt/contract hashes are `b00e3fd9594b821d5df13a2c0e012f86f9f468c6d66dda8777b4d889fa3100ac`
and `b9e0ca287ad1b8efa530c95e48bad6c77ab2501728f16efa67872e27e685e0db`; the exact live
Read/Answer/dedicated-owner/physical-owner hashes are
`a28488c400a8e1dea66b3ad9f87fc048895b4f96f0da15548bcc9590e85b86fc`,
`386ce550f9b3f1c47c76f854307d9461cb8177bf44968dd7f4f51678ee104d9e`,
`29191a15c875cf95f4d2c6c432a2c6136c3f4cd9571369ef00306a4767b79d01`, and
`61c9ec362e39d7e4eca9a3db7e02d9bf5ebde095e4acb0f02c989437baed147f`. The Accepted S10O receipt SHA-256 is
`e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246`; it freezes
`backend/canonical_v2_deps.py` at
`367f75f6876bc0ae7cff92b085ca3ecab9869d7509720689e256f99fedd9b08d`, and no S10O writer remains
active. The shared-file dependency gate is satisfied. The historical Ready artifact hashes before
this transition were audit `c65c640aa7d9cd1f9b9ee8157eecfb86daa52bca26984a2d695f28ac50aafd6a`,
plan `567aff842fc2acfd68396c014b5f9fd284fce267bc8b387d21e27bb284ff7181`, and contract
`39cdddd283134f4a09db442622e84442ca43da2f8c55f563de217caeeee5326f`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirements:
  - `design.md` Decision 6 — HTTP is an adapter around the deep modules;
  - `specs/evidence-first-query-orchestration/spec.md` — validated release-scoped planning/read,
    complete traceability, evidence-bound handles, and no unsupported operations;
  - `specs/grounded-progressive-answer/spec.md` — grounded claims/citations, typed multi-turn
    context, conditional executable `ContinuationOffer`, and visible degradation.
- OpenSpec tasks: predecessor evidence for `11.1`-`11.5`; this slice checks none.
- Direct capability owner: chat HTTP subset of Task `11.1`.
- Partial evidence only: HTTP/interface tests for `11.2`, registered-route direct-SQL/fixed-handler
  removal for `11.3`, and targeted checks for `11.4`.
- Aggregate owner: S11C retains task closure and Task `11.5` consumer acceptance.
- Depends on: Accepted S8C/S9I capability receipts, Accepted S8X's superseding live
  Read/Answer/handoff receipt and owners, plus sequential Accepted S10O ownership/frozen hash for
  the shared `backend/canonical_v2_deps.py` seam.
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11a/dependency-audit.md`.
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11a/implementation-plan.md`.

## Goal

Make the actual registered endpoint execute this path:

```text
POST /api/chat + opaque session cookie + exact typed option selection
  -> one explicitly installed accepted-release adapter
  -> QueryPlanningRequest
  -> accepted release-bound planner.plan
  -> accepted release-bound KnowledgeRead.execute
  -> TurnRequest with the exact EvidenceSet and typed session directive
  -> accepted KnowledgeAnswer.answer
  -> adapter-private compatibility mapping and exact ChatResponse validation
  -> atomic adapter session/checkpoint commit
  -> existing ChatResponse compatibility envelope returned unchanged by the route
```

The response must expose a bounded observable V2 trace from release through plan, lanes, evidence,
claims, limitations, and session/continuation receipts. The registered route must not depend on a
database connection, fixed handler, legacy retrieval service, or silent fallback. Its route,
HTTP contracts, and dependency getter must be loadable without importing the legacy chat or legacy
dependency modules. Each successful displayed turn also freezes an immutable typed feedback
checkpoint for S11B's read-only feedback operation.

## Required behavior

- One admin-console-private `CanonicalV2ChatAdapter` is bound to exactly one explicit accepted
  release and composes the Accepted planning, read, answer, and typed answer-session interfaces.
- Release identity is revalidated at planning request, plan, evidence set, answer request, and
  answer result boundaries. A mismatch fails before the next downstream effect and does not update
  HTTP session state.
- The registered `POST /api/chat` route has no `get_pg_conn`, direct SQL, old `RetrievalService`,
  fixed A-G handler, legacy `SessionContext`, provider client, or write dependency.
- No adapter installed means a stable typed `503`; no implicit DSN, Milvus path, active alias,
  environment fallback, legacy route, or global readiness discovery is allowed.
- Accepted S10O remains the owner of the shared dependency module's lazy operations getter and its
  four explicit `CANONICAL_V2_*` configuration names. S11A appends only an application-state chat
  getter; that getter never reads/calls the operations configuration or fallback surfaces, and it
  does not overwrite, rename, or weaken the Accepted S10O behavior.
- The existing `ChatRequest.query` and `entity_id_hint` fields remain accepted. `entity_id_hint`
  binds only an exact currently active V2 `ContinuationOption.option_id` for the same cookie session.
  It is not a direct legacy/canonical lookup shortcut.
- Unknown, stale, consumed, or cross-session option IDs fail before planning/provider effects. The
  adapter never infers an option from query text or a displayed label.
- Any answer-side session directive is derived only from the prior validated public context plus
  the validated plan/typed option operation. User wording has no hidden session-control meaning.
- Session state retained by the HTTP adapter is minimal, in-process, and non-authoritative: only the
  previous validated public context/offer/displayed IDs needed to prepare and bind the next turn.
  `KnowledgeAnswer` remains the authority for claim admission and session transitions.
- The adapter owns one committed isolated `KnowledgeAnswer` per HTTP session. Each turn uses an
  explicit `answer_session_fork` port (candidate default: `copy.deepcopy`) and calls `answer` only on
  the copy-on-write candidate. A successful result atomically swaps that candidate together with
  session/offer/checkpoint state only after the private mapper returns an exactly validated
  `ChatResponse`. Failed planning, reading, answering, release validation, mapping, or response
  validation discards the candidate and leaves the prior answer instance, adapter state, and
  checkpoint byte-identical. No replay engine, prepare/commit handshake, rollback API, or public
  setter is added.
- The adapter exposes `get_feedback_checkpoint(session_id) -> ChatFeedbackCheckpoint | None` and no
  setter/private-map escape hatch. The immutable checkpoint contains the session/turn/release,
  canonical-JSON-derived query/answer trace IDs, displayed evidence IDs, affected domains/paths,
  typed limitation codes, observation time, and content hash. Caller data cannot author lineage.
- Existing `ChatResponse` fields and types remain present. The adapter-private mapper uses only
  validated `RetrievalPlan`, `EvidenceSet`, and sanitized `TurnResult` values; the route returns its
  already validated response without remapping.
- `structured_payload["canonical_v2"]` exposes a bounded
  `release -> plan -> lanes -> evidence -> claims` trace plus coverage/sufficiency, limitations,
  context/traversal, interpretation, and continuation receipts. It exposes no raw selector draft,
  provider secret, unbounded source bytes, or full release manifest.
- Public citation cards are derived only for Professor, Company, Paper, and Patent. Internal
  auxiliary evidence remains in the V2 evidence/claim mapping and is never forged into a fifth
  public-domain card.
- Conditional continuation/clarification options remain capped at three. Any compatibility option
  ID is the exact V2 option ID and any relation hint comes from validated availability, not model
  prose or a guessed relationship.
- When no dominant ambiguity exists, the required compatibility field
  `ClarificationPayload.default_id` is the empty string. Only a dominant nonblocking option may put
  its exact option ID there.
- Valid deterministic degradation and best-supported partial answers remain HTTP `200` with typed
  limitations. Contract/runtime absence and invalid selection/release boundaries fail explicitly.
- Query/answer execution remains read-only with respect to canonical knowledge, source identity,
  release pointers, indexes, original sources, and forensic artifacts.

## Non-goals

- No admin API/UI, gap/review operation, domain-writer, upload pipeline, retrieval caller, script,
  or candidate-build CLI migration.
- No removal or broad quarantine of V042 writers, old collection names, global readiness, direct
  active-index mutation, legacy tests, or the 6,932-line comparison implementation. Those belong to
  S11B/S11C.
- No Task 11.1-11.5 closure, aggregate consumer acceptance, complete-candidate claim, S2C oracle
  execution, real-provider quality gate, latency/cost acceptance, or user acceptance.
- No frontend change, HTTP response-envelope redesign, new public module/runtime framework, second
  planner/read/answer service, provider registry, session database, cross-process session manager,
  or generalized workflow engine.
- No direct loading/discovery of a release from a generic environment DSN or old Milvus alias. S12
  owns complete candidate/runtime installation; S11A accepts only an explicitly composed adapter.
- No behavior compatibility promise for legacy query subtype strings, V042 IDs, fixed handler
  branching, direct SQL order, old ranking, old prose, or implementation-coupled tests.
- No schema, migration, database, index, source, provider, active pointer, promotion, Cutover,
  Commit, Push, PR, Archive, or destructive cleanup.

## Allowed scope

- Create `apps/admin-console/backend/services/canonical_v2_chat.py` for the one private adapter,
  validated public-stage outcome, private compatibility mapper, atomic commit boundary, and typed
  read-only feedback checkpoint/getter.
- Create `apps/admin-console/backend/api/chat_contracts.py` for the unchanged HTTP envelope models.
- Create `apps/admin-console/backend/api/canonical_v2_chat.py` for the V2-only chat/reset router,
  cookie/selection and bounded HTTP error translation, and return of the adapter's already validated
  response.
- Modify the exact Accepted S10O `apps/admin-console/backend/canonical_v2_deps.py` only to append an
  explicitly installed exact chat-adapter getter from FastAPI state. Preserve its operations getter
  and explicit configuration surface; the new chat getter fails closed without environment
  fallback, and the shared module still does not import `backend.deps`.
- Modify `apps/admin-console/backend/api/chat.py` only to import/re-export the moved contracts,
  remove the legacy chat/reset decorators, retain legacy comparison/feedback callables, and include
  the V2 router for the pre-S11B development app. S11B registers the V2 router directly.
- Create `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py` for the exact route,
  release, mapping, fail-closed, selection, and vertical HTTP owners.
- Update this contract, the S11A audit/plan, add an S11A receipt after Candidate evidence, and update
  existing verification/portfolio/mainline/agent-link status pointers after acceptance.

## Forbidden changes

- Any edit to `apps/miroflow-agent/src/data_agents/canonical_v2/*`, its Accepted tests/fixtures,
  shared contracts, schemas, migrations, storage, provider implementations, release manifests,
  source data, indexes, or original/forensic targets.
- Any edit to `apps/admin-console/frontend`, `backend/main.py`, admin/domain/upload/pipeline routes,
  domain writers, legacy scripts, or unrelated chat feedback operations.
- Any import from a V2-only route/contracts/dependency module to `backend.api.chat` or
  `backend.deps`, or use of the legacy chat/dependency import graph by a candidate entry point.
- Removing, replacing, renaming, or weakening Accepted S10O's
  `backend/canonical_v2_deps.py` operations getter, explicit configuration names, error behavior, or
  import boundary; parallel writing of that shared file is forbidden.
- Caller-provided lane adapters, a second release/runtime factory, a public chat framework, implicit
  active-release lookup, global feature flag selecting legacy/V2 per request, or silent fallback to
  legacy SQL.
- Test-local planner/read/answer implementations as the vertical proof, private call-order
  assertions, reference prose/model memory as truth, broad exception swallowing, `importorskip`,
  runtime `pytest.xfail`, live credentials/network access, or assertion weakening.
- Treating `entity_id_hint`, URL equality, query wording, displayed labels, or an undisplayed result
  as identity/session/relationship authority.
- A mutable feedback checkpoint, caller-supplied trace/evidence lineage, public setter, or access to
  the adapter's private session/checkpoint map.
- Checking any OpenSpec task, changing acceptance criteria, claiming aggregate S11 acceptance, or
  changing the ledger count for S11A.
- Commit, Push, PR, Archive, promotion, Cutover, source writes, or destructive cleanup.

## Expected unchanged behavior

- Accepted S1-S10 deep-module, release, retrieval, answer, session, gap, operations dependency, and
  verification contracts remain unchanged. S11A consumes them and does not repair or reinterpret
  them.
- The existing HTTP request fields and full response field/type envelope remain compatible with the
  current React caller. No frontend build is required to parse a valid S11A response.
- Legacy imports of `ChatRequest`/`ChatResponse` remain compatible through re-export even though the
  owning definitions move to the V2-safe contracts module.
- `/api/chat/session/reset` still issues a fresh opaque HttpOnly/SameSite cookie and
  `ChatSessionResetResponse`; `/api/chat/feedback` remains outside this route migration.
- Existing legacy chat unit tests may continue to call the unregistered comparison function until
  S11C replaces/retires them. They are not evidence that the registered endpoint is V2.
- S8C/S9I capability semantics plus S8X's successor materialization, current-turn offer authority,
  exact typed traversal, four public domains, Product-capability non-propagation, grounding,
  Web-handle type safety, conditional continuation, and no-online-write invariants remain exact.
- Original PostgreSQL/Milvus/forensic sources, candidate/index bytes, active pointers, provider
  state, remote Git state, and task ledger remain unchanged.

## TDD RED contract

Add one exact-target owner:

```python
def test_s11a_post_chat_uses_release_bound_canonical_v2_without_legacy_sql(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

Before acquiring a release fixture, constructing `TestClient`, or invoking SQL/provider effects,
its seam check requires `CanonicalV2ChatAdapter`, `ChatFeedbackCheckpoint`, the V2-only
`get_canonical_v2_chat_adapter`, the V2-only router, and one registered POST `/api/chat` endpoint
distinct from the legacy `chat` callable. Normal RED is exactly one strict
xfail. Forced RED is exactly one `_MissingS11AChatAdapter` failure naming the absent seam. No
production edit may precede the observed RED.

This single function is the complete S11A owner: its three-turn demo and all missing/wrong runtime,
release mismatch, selection, ambiguity, continuation, compatibility, secret-exclusion, and
feedback-checkpoint subcases SHALL be authored before the first production edit, behind the leading
sentinel. No second test function or parametrized expansion changes the exact one-owner RED count.
Because current admin collection imports the legacy app from `conftest.py`, RED/GREEN commands SHALL
first verify and add `/home/longxiang/MiroThinker` to `PYTHONPATH` for the exact root
`openai_client_compat.py` SHA-256
`95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a`; otherwise collection fails
before the contracted sentinel. GREEN may ignore only the two frozen pre-existing FastAPI
`on_event` DeprecationWarning module surfaces while treating every other warning as an error.

GREEN must install an adapter composed from the actual Accepted S8C release-bound planner/read and
Accepted S9I answer entry points through the Accepted S8X final live handoff over one explicit
isolated candidate fixture with recorded ports. The test must force the legacy callable and
`get_pg_conn` to fail if reached,
then prove the real FastAPI endpoint returns the bounded V2 trace.

Post-RED diagnosis preserved that owner while correcting unreachable fixture composition. The
information-retrieval exact proposal now includes its required bounded Universal Web lane; the
route clock seam is bound to the deterministic owner time; the initial Company name is one typed
explicit-name span; and exact `RetrievalPlan` revalidation applies the Accepted S8C server-owned
supplemental budget plus the Accepted S8R2 caller-owned representative enumeration policy. The
enumeration policy is added only when the real plan already exposes exactly one supported typed
public relationship path, non-empty displayed canonical IDs, and no policy. No query wording is
used to infer it. Fault transforms and capture occur after those controls, while the real planner,
Read, and Answer each remain the vertical implementation under test. Final review SHALL audit these
post-RED corrections as test-contract preservation rather than silently treating the original
unreachable fixture as executable.

## Observable demo contract

One `TestClient` cookie jar executes:

```text
turn 1: canonical query
  -> HTTP 200, one release, validated plan/lanes, evidence, grounded claim/citation,
     and only a conditionally valid offer

turn 2: same query + returned option_id
  -> exact offer/option binding and selected-operation context receipt

turn 3: typed relationship follow-up over the selected/displayed context
  -> same release, validated relationship lane/evidence/claim, and traversal/context receipt
```

The JSON must make the V2 path visually distinguishable from the legacy handler. This demo is an
isolated runnable consumer proof only; it is not the S12 complete candidate, a real-provider gate,
or production-like Cutover.

## Required checks

- S8C, S9I, S10O, and S8X contracts and receipts are Accepted before RED or production/test edits;
  the S8X live Read/Answer/owner hashes and S10O shared dependency hash match exactly.
- Focused normal RED is exactly `1 xfailed`, with zero fail/error/XPASS.
- Focused forced RED is exactly one `_MissingS11AChatAdapter` failure before any effect.
- Focused GREEN passes every S11A owner with warnings as errors and no skip/xfail/XPASS.
- Route enumeration proves exactly one registered POST `/api/chat`, owned by the V2 endpoint.
- Import guards prove the V2 route/contracts/dependency modules load without `backend.api.chat` or
  `backend.deps` and expose no legacy SQL/retrieval/provider dependency.
- The V2 endpoint succeeds when legacy `chat` and `get_pg_conn` raise, and no failure path calls
  them.
- Missing/wrong runtime, plan/evidence/result release mismatch, and stale/cross-session selection
  fail before the next downstream effect and before session commit.
- Successful displayed results atomically publish the forked answer instance and immutable feedback
  checkpoint; failed results including mapper/response-validation failures discard the fork and
  preserve prior answer/adapter/checkpoint state byte-for-byte. A following turn proves no hidden
  transition; unknown sessions return `None`; no setter or prepare/commit handshake exists.
- No-dominant-ambiguity responses use `clarification.default_id == ""`; only an actual dominant
  nonblocking option may use its exact ID.
- The complete existing HTTP envelope validates; raw selector drafts/secrets are absent; the
  bounded structured payload exposes release/plan/lanes/evidence/claims/session receipts.
- The three-turn observable demo uses the same accepted release and exact typed option binding.
- Existing `test_chat_*.py` comparison evidence retains the exact post-S8X Specified baseline with
  zero delta: 260 collected, `250 passed, 7 failed, 3 skipped, 4 warnings`. Those seven named
  implementation-coupled legacy failures are recorded as exact node IDs in the audit and are not
  repaired/weakened by S11A. The canonical JUnit payload has `outcomes` sorted as
  `(failure|error|skipped, classname, name)` and `terminal_counts` with
  `collected/errors/failed/passed/skipped/warnings/xfailed/xpassed`; it uses
  `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")` and
  has SHA-256 `de88a0b8a64bba955d80fe06b8e54a1783a46fda36549f43c9cb11ac192bc959`
  before S11A and must have the same canonical bytes/SHA after S11A.
- Final Accepted S8C/S9I capability owners, Accepted S8X handoff owners, and the Accepted S10O
  shared-dependency/operations API owners pass unchanged.
- Complete no-external admin-console and Canonical V2 suites have zero unexpected failures.
- Ruff check, `py_compile`, changed-scope Pyright, strict OpenSpec, `git diff --check`, route/import/
  static guards, scope, secret, generated-cache, fresh locked-offline wheel/package-content, source
  parity, and frozen-source checks pass. Ruff format-check covers every new/changed S11A file except
  the frozen 6,932-line legacy `backend/api/chat.py` comparison oracle, whose pre-S11A bytes are not
  format-clean; that file instead requires the exact legacy JUnit signature plus a surgical diff
  review so formatting cannot create an unrelated whole-file rewrite.
- One lean implementation/test-integrity review reports zero open Critical/Important. Minor/YAGNI
  findings are recorded and non-blocking.

## Evidence to update

- This Slice Contract and the S11A audit/implementation plan.
- Their post-S8X Specified hashes and the canonical pre-RED legacy baseline signature before Ready.
- New `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11a/verification-receipt.json` after
  Candidate evidence exists.
- Existing `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- After acceptance only: `.agents/portfolio.md`, current mainline/convergence status, and existing
  agent-link/change-log status pointers needed to reference the S11A receipt.
- Do not change OpenSpec task checkboxes or acceptance claims for Tasks 11.1-11.5.

## Stop conditions

- S8C, S9I, S10O, or S8X is not Accepted, its receipt is missing/stale, S8X live handoff hashes or
  another Accepted predecessor regress, the shared dependency hash drifts, or another writer still
  owns that file.
- Correct wiring requires changing a Canonical V2 public contract/algorithm, schema, migration,
  provider framework, release manifest, index, or source.
- The route needs implicit active-release discovery, a database connection, direct SQL, legacy
  retrieval/fixed-handler behavior, or a fallback to return a valid answer.
- The response cannot preserve the existing HTTP field/type envelope without a frontend or public
  contract redesign absent from OpenSpec.
- Session/selection correctness would require query-wording heuristics, raw URLs, undisplayed
  candidates, unresolved handles as canonical anchors, or duplicated answer-session policy.
- The isolated HTTP vertical cannot use the Accepted S8C/S9I entry points and would require a
  test-local planner/read/answer implementation.
- Admin/writer/script removal, aggregate test migration, S12 candidate installation, real-provider
  thresholds, task closure, Cutover, or unresolved Critical/Important findings enter scope.

## Done means

- S8C, S9I, S10O, and S8X are Accepted; S8X's live handoff and S10O's shared dependency seam are
  frozen; reviewed S11A hashes move Specified to Ready; exact RED and minimal GREEN are recorded.
- The registered POST `/api/chat` has no direct SQL/fixed-handler/retrieval-service dependency and
  executes one explicit release-bound V2 adapter with no legacy fallback.
- The adapter maps and exact-validates `ChatResponse` before atomically committing session/checkpoint
  state; the route returns that response without a second mapper.
- The V2 route/contracts/dependency import graph is quarantined from legacy chat/deps, and the
  adapter exposes the typed immutable read-only feedback checkpoint required by S11B.
- Existing HTTP fields/types remain compatible and the bounded structured payload visibly proves
  release, plan, lanes, evidence, claims, limitations, and session/continuation receipts.
- Exact option IDs bind typed continuation/session selection; stale/cross-session values fail closed.
- The three-turn isolated HTTP demo passes over one accepted release while legacy SQL/callable
  sentinels remain untouched.
- Required checks and one lean review pass with zero open Critical/Important findings.
- S11A is Accepted as a dependency checkpoint, but Tasks 11.1-11.5 remain unchecked and the live
  ledger has no S11A delta.

## Rollback note

Remove the S11A test, private adapter, and V2-only contracts/route modules; unregister the V2
endpoint, restore the legacy POST decorator, remove only S11A's chat getter/import additions from
the shared dependency module, and restore the prior reset-cookie helper if it changed. Do not remove
or rewrite Accepted S10O's operations getter/configuration surface. Remove only S11A run/status
evidence. No database, index, source, provider, release pointer, task checkbox, Commit, Push, PR,
Archive, promotion, or Cutover state requires rollback.
