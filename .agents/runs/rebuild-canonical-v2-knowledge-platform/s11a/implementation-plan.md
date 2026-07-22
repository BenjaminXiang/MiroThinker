# S11A Release-Bound Chat HTTP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` only after this plan becomes Ready. Use
> `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. Steps use checkbox
> syntax for tracking. One writer owns the HTTP adapter seam. Do not Commit.

**Goal:** Make the registered `POST /api/chat` route execute one explicitly installed,
release-bound Canonical V2 planning/read/answer/session pipeline while retaining the existing HTTP
request/response envelope.

**Architecture:** Add one admin-console-private adapter that validates one release across
`planner.plan -> KnowledgeRead.execute -> KnowledgeAnswer.answer`, expose it only through V2-only
route/contracts/dependency modules, and retain an immutable read-only feedback checkpoint for S11B.
The adapter owns one committed `KnowledgeAnswer` per HTTP session and forks it through an explicit
`answer_session_fork` port before each turn. It privately maps the candidate outcome to an exact
`ChatResponse` and atomically swaps the candidate answer instance plus public session/checkpoint
state only after mapping and response validation succeed. FastAPI owns only cookie/selection and bounded
HTTP error translation plus returning that already validated response. The legacy fixed-handler
function remains temporarily available as an unregistered comparison oracle and is never a route
fallback or import dependency of the candidate application.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Canonical V2 deep-module contracts, pytest,
TestClient, uv, Ruff, Pyright, OpenSpec.

---

## State gate

Implementation reached Candidate at `2026-07-20T19:44:36Z` and Accepted at
`2026-07-20T19:56:07Z`. All S11A-specific, frozen legacy, predecessor, static, package/source,
protected-target, complete Canonical V2, and strictly guarded Admin checks are complete. Two
independent final reviews and two exception audits report zero open Critical/Important findings.
The guarded Admin suite has zero S11A-related unexpected failures; its one unrelated pre-existing
`backend/api/domains.py`/quality-status-test call-order mismatch is recorded separately. The earlier
dotenv-restored real-data attempt is invalid evidence and was safely interrupted.

This plan is **revalidated and Ready** at `2026-07-20T17:43:17Z` after returning to Specified at
`2026-07-20T17:32:44Z` because Accepted S8X superseded the live Read/Answer handoff. The historical
Ready transition at `2026-07-20T14:31:57Z` remains superseded. Task 2 or later may execute only from
this post-S8X Ready checkpoint.

- [x] The S8C Slice Contract and verification receipt both say Accepted.
- [x] The S9I Slice Contract and verification receipt both say Accepted.
- [x] The S10O Slice Contract and verification receipt both say Accepted; its receipt binds the
  exact first-writer bytes of `backend/canonical_v2_deps.py`, and no S10O writer remains active.
- [x] The S8X Slice Contract and receipt say Accepted; its receipt and live Read, Answer, dedicated
  owner, and physical owner hashes match exactly.
- [x] Fresh Admin hashes, schema, route/import graph, operations dependency surface, ledger, and
  exact 260-case legacy baseline match the frozen checkpoint.
- [x] One fresh lean review of these post-S8X Specified artifacts reports zero open
  Critical/Important findings.
- [x] Reviewed post-S8X Specified hashes and a UTC timestamp are recorded in a new Ready transition.

The fresh lean review reported `Critical=0/Important=0/Minor=1/YAGNI=0` on exact Specified hashes
audit `0a7e0bcd6bd49c6a9eaef15103ef2b539bdaf351f067e2a62f8d635ab6a05310`, plan
`99ab2e060a0bf2202182034e0cb7d4c506383ef175255eca33e9a3d1d64e23ea`, and contract
`5894be2329ffc22d8f8797e2db6b445f4032d8209e98fa542c4d210954ad1bc2`. The non-blocking Minor
records that one later plan sentence says “failure and skip” although the exact schema immediately
specifies failure/error/skipped and error-count equality; it is recorded without another review loop.

The earlier Specified review and Ready hashes are historical only. The exact historical Ready
artifact hashes immediately before this transition were audit
`c65c640aa7d9cd1f9b9ee8157eecfb86daa52bca26984a2d695f28ac50aafd6a`, plan
`567aff842fc2acfd68396c014b5f9fd284fce267bc8b387d21e27bb284ff7181`, and contract
`39cdddd283134f4a09db442622e84442ca43da2f8c55f563de217caeeee5326f`.

S2C is not a Ready gate for this deterministic consumer wiring slice. No Commit, Push, PR, Archive,
promotion, production-like Cutover, original-source write, admin migration, or legacy writer removal
belongs to this plan.

Read-only preflight verified Accepted S8C/S9I capability receipts, Accepted S10O's shared Admin
seam, and Accepted S8X's superseding Read/Answer handoff, with the live formal ledger `65/80`.
S8X receipt/contract hashes are
`b00e3fd9594b821d5df13a2c0e012f86f9f468c6d66dda8777b4d889fa3100ac` /
`b9e0ca287ad1b8efa530c95e48bad6c77ab2501728f16efa67872e27e685e0db`; its live Read, Answer,
dedicated-owner, and physical-owner hashes are
`a28488c400a8e1dea66b3ad9f87fc048895b4f96f0da15548bcc9590e85b86fc`,
`386ce550f9b3f1c47c76f854307d9461cb8177bf44968dd7f4f51678ee104d9e`,
`29191a15c875cf95f4d2c6c432a2c6136c3f4cd9571369ef00306a4767b79d01`, and
`61c9ec362e39d7e4eca9a3db7e02d9bf5ebde095e4acb0f02c989437baed147f`.
The S10O receipt freezes `backend/canonical_v2_deps.py` at SHA-256
`367f75f6876bc0ae7cff92b085ca3ecab9869d7509720689e256f99fedd9b08d`, and no S10O writer remains
active. The HTTP envelope, 59-route/15-legacy-plus-8-V2 import graph, exact root helper, and fresh
260-case `250 passed, 7 failed, 3 skipped, 4 warnings` legacy chat baseline are refreshed in the
dependency audit with zero delta. The lean review and new reviewed Ready hashes above close that
gate.

## File map

- Create `apps/admin-console/backend/services/canonical_v2_chat.py`: one private release-bound
  planner/read/answer orchestration adapter, bounded validated outcome, private compatibility
  mapper, atomic commit boundary, and immutable read-only `ChatFeedbackCheckpoint` surface.
- Create `apps/admin-console/backend/api/chat_contracts.py`: move the existing HTTP request/response
  envelope models unchanged so V2 consumers do not import the legacy handler module.
- Create `apps/admin-console/backend/api/canonical_v2_chat.py`: own the V2-only chat/reset router,
  cookie/selection and bounded HTTP error translation, already-mapped response return, and no
  legacy imports.
- Modify Accepted S10O's `apps/admin-console/backend/canonical_v2_deps.py`: preserve its exact lazy
  operations getter and four explicit `CANONICAL_V2_*` configuration names, then append only an
  explicitly installed chat-adapter getter that fails closed and performs no environment fallback.
- Modify `apps/admin-console/backend/api/chat.py`: import/re-export the moved HTTP contracts, remove
  the legacy chat/reset route decorators, retain the legacy callable/feedback operations as a
  comparison oracle, and include the V2 router only for the pre-S11B development application.
- Create `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`: exact RED/GREEN route,
  release, compatibility, fail-closed, and observable multi-turn vertical owners.
- Add `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11a/verification-receipt.json` only
  after Candidate evidence exists.
- Update only S11A/status/verification evidence after implementation. Do not check any OpenSpec task.

`apps/admin-console/frontend`, `backend/main.py`, `backend/deps.py`, Canonical V2 production modules, schemas,
migrations, provider implementations, admin/domain writers, and OpenSpec behavior artifacts are not
implementation files for S11A.

## Task 1: Revalidate dependencies and freeze post-S8X Specified

- [x] Read the final S8C, S9I, S10O, and S8X contracts and receipts directly. Stop if any status is
  not Accepted. Treat S8C/S9I as capability evidence, S8X as the superseding live Read/Answer
  handoff/hash authority, and S10O as the exact shared Admin dependency owner.
- [x] Reinspect the live predecessor signatures and public shapes of:

```text
create_isolated_release_query_planner
create_isolated_release_knowledge_read
create_ephemeral_knowledge_answer
QueryPlanningRequest / RetrievalPlan / EvidenceSet
TurnRequest / SessionDirective / ContinuationSelection / TurnResult
```

  Separately verify that the planned `ChatFeedbackCheckpoint` and
  `CanonicalV2ChatAdapter.get_feedback_checkpoint` shapes still match this reviewed S11A contract;
  they do not exist as live code before implementation.

- [x] Confirm S8C still owns the release-bound seven-lane/fusion/sufficiency composition, S9I still
  owns structured claims/session/rendering, S8X owns the live successor materialization and
  current-turn/traversal authorization guards, and S10O owns the operations getter/configuration
  surface. Do not compensate for a regressed predecessor inside S11A.
- [x] Capture the live OpenSpec ledger count. Record that S11A will make no ledger change.
- [x] Before any RED or production/test edit, capture the exact 260-case legacy JUnit baseline and
  canonical failure/skip plus terminal-count signature; require the frozen seven node IDs and zero
  count delta. The pre-RED signature is
  `de88a0b8a64bba955d80fe06b8e54a1783a46fda36549f43c9cb11ac192bc959`.
- [x] Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
```

Expected: exit `0`.

- [x] Complete one lean read-only review of the S11A audit/plan/contract. Repair only open Critical/
  Important findings; record Minor/YAGNI as non-blocking.
- [x] Freeze reviewed hashes and mark S11A Ready. Do not change production, tests, `tasks.md`, or
  `acceptance.md` in this task.

## Task 2: Write and observe the exact route RED

**Test:** `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`

- [x] Add a dynamic seam loader with a named `_MissingS11AChatAdapter` sentinel. Before importing
  fixtures, constructing the app client, opening a connection, or invoking a provider, require:

```text
backend.services.canonical_v2_chat.CanonicalV2ChatAdapter
backend.services.canonical_v2_chat.ChatFeedbackCheckpoint
backend.canonical_v2_deps.get_canonical_v2_chat_adapter
backend.api.canonical_v2_chat.router
one registered POST /api/chat endpoint that is not backend.api.chat.chat
```

- [x] Add one strict-xfail owner named:

```python
def test_s11a_post_chat_uses_release_bound_canonical_v2_without_legacy_sql(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

This is the only S11A test function and RED target. Before any production edit, author in that same
function the complete three-turn vertical sequence plus every Task 6 negative/compatibility/
checkpoint subcase. Do not parameterize it or defer first authorship of those subcases until after
implementation. The leading seam sentinel prevents fixture, app-client, SQL, or provider effects
while preserving the exact one-owner RED count.

- [x] Run normal RED:

```bash
cd apps/admin-console
ROOT_HELPER=/home/longxiang/MiroThinker
test "$(sha256sum "$ROOT_HELPER/openai_client_compat.py" | awk '{print $1}')" = \
  95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a
env -u DATABASE_URL -u DATABASE_URL_TEST \
  PYTHONPATH="$ROOT_HELPER${PYTHONPATH:+:$PYTHONPATH}" \
  uv run pytest -o addopts='' -p no:cacheprovider \
  tests/test_canonical_v2_chat_http_adapter.py \
  -k s11a_post_chat_uses_release_bound_canonical_v2_without_legacy_sql -q
```

Expected: exactly `1 xfailed`, zero failures/errors/XPASS.

- [x] Run forced RED:

```bash
cd apps/admin-console
ROOT_HELPER=/home/longxiang/MiroThinker
test "$(sha256sum "$ROOT_HELPER/openai_client_compat.py" | awk '{print $1}')" = \
  95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a
env -u DATABASE_URL -u DATABASE_URL_TEST \
  PYTHONPATH="$ROOT_HELPER${PYTHONPATH:+:$PYTHONPATH}" \
  uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/test_canonical_v2_chat_http_adapter.py \
  -k s11a_post_chat_uses_release_bound_canonical_v2_without_legacy_sql -q
```

Expected: exactly `1 failed`, caused only by `_MissingS11AChatAdapter` before any database,
provider, legacy handler, or runtime effect.

### Post-RED fixture corrections that preserve the vertical contract

The complete owner assertions were retained. Focused diagnosis found four fixture-composition
details that made the authored vertical unreachable under the Accepted live contracts; they were
corrected without changing the adapter/HTTP algorithm or replacing any real predecessor:

- Accepted planner validation requires every information-retrieval proposal to use Universal Web.
  The exact branch therefore uses `("exact", "web")`, `web_mode="universal"`, and the same bounded
  recorded empty Web port. The observable lane assertion changed to those exact validated lanes.
- The route exposes the private `_utc_now` clock seam and the owner binds it to `NOW`; this makes
  the server-authored checkpoint turn time deterministic without deriving it from source
  `observed_at`.
- The initial fixture query uses typed explicit-name punctuation around `Robotics Co`, so the real
  isolated exact adapter can resolve the accepted Company while preserving the current-revenue
  material question. No HTTP/query mapper extracts or guesses that entity.
- The owner follows the Accepted S8C/S8R2 caller-owned composition precedents over each real planner
  result: exact `RetrievalPlan` revalidation binds the server-owned `SupplementalBudget`; and only a
  plan that already contains exactly one supported typed public relationship path, non-empty
  displayed canonical IDs, and no enumeration policy receives the representative
  `EnumerationPolicy` with `fixture_owner.S8R2_SCOPE`. These controls are applied before any fault
  transform and before capture. The real release-bound planner still runs exactly once, and the
  real release-bound Read and Answer implementations remain unchanged.

These are recorded post-RED contract corrections, not assertion weakening. The exact pre-edit RED
sentinel evidence remains the required RED proof; final review must include this owner delta.

## Task 3: Implement the private release-bound adapter

**Create:** `apps/admin-console/backend/services/canonical_v2_chat.py`

- [x] Define one private immutable validated outcome that carries only the public stage results:

```python
@dataclass(frozen=True)
class _CanonicalV2ChatOutcome:
    query: str
    plan: RetrievalPlan
    evidence_set: EvidenceSet
    turn_result: TurnResult
```

- [x] Define one immutable validated feedback checkpoint and expose only a read-only getter:

```python
class ChatFeedbackCheckpoint(ContractModel):
    session_id: str
    turn_id: str
    release_id: str
    query_trace_id: str
    answer_trace_id: str
    evidence_ids: tuple[str, ...]
    affected_domains: tuple[str, ...]
    affected_paths: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    observed_at: datetime
    content_sha256: str

def get_feedback_checkpoint(self, session_id: str) -> ChatFeedbackCheckpoint | None:
    ...
```

  Derive trace IDs and `content_sha256` from canonical JSON over server-validated public data. The
  caller cannot supply lineage, mutate a returned checkpoint, set a checkpoint, or reach the
  adapter's private session map.

- [x] Define one concrete `CanonicalV2ChatAdapter` initialized with exactly one explicit
  `release_id`, the accepted release-bound planner, a `KnowledgeRead`, a server-owned
  `answer_factory`, and an `answer_session_fork`. The candidate composition uses
  `copy.deepcopy` for the fork; tests may inject a deterministic equivalent.
  Keep any structural typing private to this file; do not add a new package/public runtime API.
- [x] Retain only a bounded map from HTTP session ID to its committed isolated `KnowledgeAnswer`
  plus the last validated public `ContextReceipt`/active `ContinuationOffer`/displayed IDs needed
  for the next request. Fork before `answer`; atomically swap the fork with public state/checkpoint
  only after exact `ChatResponse` validation. Discard it on every failure. Do not inspect private
  answer state, copy its algorithms, add replay machinery, or persist this map.
- [x] Implement one public method with explicit inputs:

```python
def answer(
    self,
    *,
    query: str,
    session_id: str,
    option_id: str | None,
    as_of: datetime,
) -> ChatResponse:
    ...
```

- [x] If `option_id` is supplied, require an active offer for the same session and exact option ID.
  Build `ContinuationSelection` from the retained server offer ID and option ID. Reject stale,
  unknown, cross-session, or consumed values before planner/provider effects. Never match labels or
  query wording.
- [x] Build `QueryPlanningRequest` with the explicit adapter release, query, UTC `as_of`, and only
  the displayed canonical IDs/accepted context allowed by the prior public receipt. Do not feed an
  undisplayed candidate, unresolved Web handle, raw URL, legacy V042 ID, or inferred relation.
- [x] Call the accepted modules exactly once in this order:

```python
plan = planner.plan(planning_request)
evidence_set = knowledge_read.execute(plan)
turn_result = knowledge_answer.answer(turn_request)
```

  Construct `TurnRequest.evidence_set` from the exact returned `EvidenceSet`; never reconstruct or
  copy evidence by hand.
- [x] Derive any answer-side `SessionDirective` only from the prior validated context plus the
  validated plan/typed option operation. Query strings such as "these", "the second", or "switch
  topic" have no special meaning in the adapter. A new conversation uses the reset endpoint/new
  cookie instead of a hidden text-based reset rule.
- [x] Revalidate every stage and require:

```text
adapter.release_id
  == planning_request.release_id
  == plan.release_id
  == evidence_set.release_id
  == turn_request.release_id
  == turn_result.release_id
```

  Reject a mismatch before invoking the next downstream stage. Do not catch it and call the legacy
  implementation.
- [x] After validating the complete stage outcome, invoke the private compatibility mapper defined
  in Task 5 and exact-revalidate the resulting `ChatResponse`. Only after that succeeds, atomically
  swap the forked answer instance together with the new public context/offer and feedback checkpoint,
  then return the validated response. A planning/read/answer/release/mapping/response-validation
  exception discards the fork and leaves the prior answer instance, adapter state, and checkpoint
  byte-identical. The checkpoint contains only displayed evidence IDs, affected
  domains/paths, and typed limitation codes from that exact result. Do not add a public prepare,
  commit, rollback, acknowledgement, or checkpoint setter API.
- [x] Add no SQL, storage, active-release discovery, provider client, lane adapter map, retry
  framework, global session manager, write path, or compatibility fallback.

## Task 4: Install one explicit FastAPI dependency and V2 route

**Create:**

- `apps/admin-console/backend/api/chat_contracts.py`
- `apps/admin-console/backend/api/canonical_v2_chat.py`

**Modify:**

- `apps/admin-console/backend/api/chat.py`
- Accepted S10O `apps/admin-console/backend/canonical_v2_deps.py`

- [x] Append `get_canonical_v2_chat_adapter(request: Request)` to the exact Accepted S10O
  `backend/canonical_v2_deps.py`. It reads one exact adapter from
  `request.app.state.canonical_v2_chat_adapter`. Missing or wrong-type state returns an
  `HTTPException(503)` with a stable `canonical_v2_chat_runtime_unavailable` detail. This chat getter
  does not inspect or call the S10O operations dependency, environment DSNs, Milvus paths, aliases,
  global readiness, or the legacy retrieval service. Preserve the existing S10O operations getter,
  its four explicit configuration names, and the module's no-`backend.deps` import invariant.
- [x] Move the existing `ChatRequest`, `ChatResponse`, clarification, citation, and related envelope
  models unchanged into `backend/api/chat_contracts.py`; import/re-export them from legacy
  `backend/api/chat.py` so direct-call compatibility tests retain the same public shapes.
- [x] Preserve the existing `ChatRequest` fields. Interpret `entity_id_hint` only as the exact
  active V2 option ID described in Task 3; it is not a canonical entity ID lookup shortcut.
- [x] Register `@router.post("/chat", response_model=ChatResponse)` and the reset route only in
  `backend/api/canonical_v2_chat.py`. Keep the legacy `chat(...)` function temporarily importable for
  historical direct-call tests but unregistered and clearly marked as a comparison oracle.
- [x] Give the V2 endpoint only these responsibilities:

```text
trim/validate query
obtain or issue opaque cookie session ID
call the injected CanonicalV2ChatAdapter
return the adapter's already validated ChatResponse
set the same HttpOnly/SameSite/Max-Age cookie attributes
```

  Its signature must not contain `conn=Depends(get_pg_conn)`, the legacy retrieval service, an LLM
  client, a Web provider, or a canonical/index writer.
- [x] Generate a new opaque session ID locally when the cookie is absent. Preserve
  `/api/chat/session/reset` response/cookie compatibility by making a reset issue another opaque ID;
  the V2 adapter treats the new ID as a fresh session. Do not make legacy `SessionContext` state
  authoritative for the V2 route.
- [x] Map invalid/stale option IDs and release/session contract violations to a bounded 4xx response.
  Map absent runtime to `503`. Valid V2 partial/degraded answers remain HTTP `200` with their typed
  limitations. No failure path invokes the legacy chat function.
- [x] For S11A development compatibility, legacy `backend/api/chat.py` may include the V2 router
  after removing its own chat/reset decorators. Assert route enumeration contains exactly one POST
  `/api/chat` endpoint and it is the V2 endpoint. Do not modify `backend/main.py`; S11B will register
  the V2 router directly and quarantine the legacy module from the candidate import graph.

## Task 5: Implement the compatibility and trace mapper inside the adapter prepare stage

**Modify:** `apps/admin-console/backend/services/canonical_v2_chat.py`

- [x] Build and exact-revalidate `ChatResponse` only from the private validated outcome before the
  adapter commits any public session/offer/checkpoint state. Retain every existing field and type.
  Use a stable `canonical_v2:` prefix plus plan behavior/response mode for `query_type`; do not
  preserve legacy subcode values as a compatibility promise.
- [x] Set `answer_text` from sanitized `TurnResult.answer_text`. Set `answer_style` to
  `llm_synthesized` only for an accepted prose-renderer mode; deterministic/fallback output is
  `template`.
- [x] Serialize retained `EvidenceItem` records into `evidence`. Do not expose raw provider input,
  unbounded snapshots, secrets, or evidence absent from the validated result.
- [x] Derive public `ChatCitation` cards only for Professor, Company, Paper, and Patent from admitted
  result citations plus matching validated evidence/handles. Keep internal auxiliary citations in
  the structured V2 mapping without forging a public-domain type.
- [x] Put this bounded observable trace under `structured_payload["canonical_v2"]`:

```text
release_id
plan_id / plan_version / behavior_class / interaction_mode / lanes
retrieval traces and coverage/sufficiency receipts
retained evidence IDs and source natures
grounded claims and exact claim-evidence mappings
limitations/conflicts/selector traces
context/traversal receipts
interpretation notice and ContinuationOffer
```

  The response must visibly prove `release -> plan -> lanes -> evidence -> claims` without copying
  a full candidate manifest or raw selector draft.
- [x] Map at most three available V2 offer options into existing `clarification`/`suggested_followups`
  affordances. `CandidateOption.id` is the exact `ContinuationOption.option_id`; label/hint come from
  the validated option; domain is derived only from a bound public handle. Options that cannot fit
  the public candidate-card shape remain in structured payload and are not invented as cards.
- [x] If there is no dominant ambiguity, serialize `ClarificationPayload.default_id` as the required
  empty string `""`. Only an actually dominant, nonblocking option may populate it with that exact
  option ID.
- [x] Build `citation_map` deterministically from the displayed citation order. Never use model
  citation numbers to select evidence.
- [x] Return the exact validated `ChatResponse` to the route only after the same adapter call commits
  the forked answer instance and state/checkpoint. A mapper or response-validation failure returns
  nothing, discards the fork, and leaves the previous answer/context/checkpoint byte-identical; the
  route performs no second compatibility mapping.

## Task 6: Complete the HTTP contract and observable vertical owners

**Test:** `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`

- [x] Remove the strict-xfail only after the adapter and route seam exist. Make both the legacy
  `chat(...)` callable and `get_pg_conn` raise if reached, then POST through the real FastAPI router.
  A valid response proves neither legacy path was executed.
- [x] Compose the installed adapter from the actual Accepted S8C release-bound planner/read and
  Accepted S9I answer entry points through the Accepted S8X final live handoff, using one explicit
  isolated candidate fixture and
  recorded provider ports. A compact fixture builder may live in this test file; it must construct
  accepted production models/factories rather than implement a fake planner, reader, or answerer.
- [x] Execute the three-step observable demo through one `TestClient` cookie jar:

```text
turn 1: canonical query -> release/plan/lanes/evidence/claims/offer
turn 2: same query + returned option_id -> exact offer/operation selection receipt
turn 3: typed relationship follow-up -> same release + relationship evidence/claim/traversal receipt
```

  Assert the response remains valid against `ChatResponse`, the option count is at most three, and
  no unsupported claim, stale option, or undisplayed handle enters the result.
- [x] Execute and complete the focused negative groups already authored in the exact RED owner for:

```text
missing app-state adapter -> 503, zero legacy/SQL/provider effects
wrong-type app-state adapter -> 503
plan release mismatch -> rejected before reader
EvidenceSet release mismatch -> rejected before answerer
TurnResult release mismatch -> rejected before response/session commit
unknown/stale/cross-session option -> 4xx before planner/provider effects
blocking clarification -> no unsupported primary claim
simple complete answer -> no fabricated continuation
no dominant ambiguity -> clarification.default_id == ""
successful displayed turn -> immutable checkpoint matches release/turn/evidence/limitations
failed or mismatched turn -> prior feedback checkpoint remains byte-identical
mapper or ChatResponse validation failure -> prior adapter state/checkpoint remains byte-identical
unknown session -> get_feedback_checkpoint returns None
```

- [x] Assert existing response fields are present with their exact compatible types and no frontend
  schema change is required. Assert raw selector drafts and injected sentinel secrets do not appear
  anywhere in response JSON.
- [x] Inject one mapper/response-validation failure after the candidate answer has advanced. Assert
  the committed answer instance, adapter state, and checkpoint remain byte-identical, then execute
  the next turn and prove it resolves exactly from the last displayed turn rather than the discarded
  candidate transition.
- [x] Run focused GREEN:

```bash
cd apps/admin-console
ROOT_HELPER=/home/longxiang/MiroThinker
env -u DATABASE_URL -u DATABASE_URL_TEST \
  PYTHONPATH="$ROOT_HELPER${PYTHONPATH:+:$PYTHONPATH}" \
  uv run pytest -o addopts='' -p no:cacheprovider -W error \
  -W 'ignore::DeprecationWarning:backend.main' \
  -W 'ignore::DeprecationWarning:fastapi.applications' \
  tests/test_canonical_v2_chat_http_adapter.py -q
```

Expected: every S11A owner passes with no fail/error/skip/xfail/XPASS.

## Task 7: Run proportional consumer and predecessor verification

- [x] Rerun existing chat contract tests to prove moving the route decorator did not silently alter
  retained comparison-oracle fixtures:

```bash
cd apps/admin-console
ROOT_HELPER=/home/longxiang/MiroThinker
test "$(sha256sum "$ROOT_HELPER/openai_client_compat.py" | awk '{print $1}')" = \
  95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a
env -u DATABASE_URL -u DATABASE_URL_TEST \
  PYTHONPATH="$ROOT_HELPER${PYTHONPATH:+:$PYTHONPATH}" \
  uv run pytest -o addopts='' -p no:cacheprovider tests/test_chat_*.py \
  -q --tb=short -rf --junitxml=/tmp/s11a-legacy-chat-baseline.xml
```

Frozen post-S8X Specified baseline: exit `1` with exactly
`250 passed, 7 failed, 3 skipped, 4 warnings`
over 260 collected cases and the exact seven node IDs frozen in the dependency audit. Parse the
JUnit file with Python's `xml.etree.ElementTree`, sort `(outcome, classname, name)` for every failure
and skip into `outcomes`, combine it with `terminal_counts` containing
`collected/errors/failed/passed/skipped/warnings/xfailed/xpassed`, serialize with
`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")`, and
record its SHA-256 in the S11A receipt before and after implementation. The exact pre-RED SHA is
`de88a0b8a64bba955d80fe06b8e54a1783a46fda36549f43c9cb11ac192bc959`. At S11A Candidate require byte-
equal canonical baseline JSON and the same SHA, with zero new
failure/error/skip/xfail/XPASS/warning delta. S11A does not broadly rewrite, weaken, or claim to pass
those legacy owners.

- [x] Rerun the Accepted S8C release-bound vertical, relevant S9I behavior owners, the final S8X
  dedicated/physical handoff owners, and the Accepted S10O operations dependency/API owner that
  freezes `backend/canonical_v2_deps.py`. Expected: exit `0`, no xfail/XPASS and no predecessor or
  S10O getter/configuration/hash regression.
- [x] Run the complete no-external admin-console suite and complete no-external Canonical V2 suite
  with the final dependency-receipt commands. Expected: zero unexpected failures. External provider
  skips are recorded and are not S11A evidence.

  The Canonical V2 suite exited `0` with `363 passed, 148 skipped` and three retained hostile-
  serializer warnings. The Admin suite required strict guards because repository dotenv otherwise
  restored a forbidden real-data DSN: all sensitive environment names were held empty, TCP and
  psycopg were blocked, and only AF_UNIX remained available. That guarded run completed 579
  collected / 578 executed with `440 passed, 130 skipped, 8 failed, 1 deselected, 12 warnings, 0
  errors`. Seven failures are the exact frozen legacy set; the eighth is one unrelated pre-existing
  `test_data_api_quality_status.py` call-order mismatch in tracked git-diff-clean files. S11A-
  related unexpected failures are zero. The earlier unguarded run was interrupted and is not
  evidence.
- [x] Run static checks:

```bash
cd apps/admin-console
uv run ruff check \
  backend/api/chat.py backend/api/chat_contracts.py backend/api/canonical_v2_chat.py \
  backend/canonical_v2_deps.py backend/services/canonical_v2_chat.py \
  tests/test_canonical_v2_chat_http_adapter.py
uv run ruff format --check \
  backend/api/chat_contracts.py backend/api/canonical_v2_chat.py \
  backend/canonical_v2_deps.py backend/services/canonical_v2_chat.py \
  tests/test_canonical_v2_chat_http_adapter.py
uv run python -m py_compile \
  backend/api/chat.py backend/api/chat_contracts.py backend/api/canonical_v2_chat.py \
  backend/canonical_v2_deps.py backend/services/canonical_v2_chat.py \
  tests/test_canonical_v2_chat_http_adapter.py
```

Expected: every command exits `0`. The frozen pre-S11A `backend/api/chat.py` baseline is not Ruff
format-clean. Running Ruff format on that 6,932-line comparison oracle would create an unrelated
whole-file rewrite, so S11A deliberately excludes only that file from `ruff format --check`.
`ruff check`, `py_compile`, the exact legacy JUnit signature, and a surgical diff review remain
required for it; all newly created and otherwise changed S11A files stay format-clean.

- [x] Run Pyright for the changed admin-console scope plus the imported Canonical V2 public models
  using the established repository configuration. Expected: `0 errors`.
- [x] Run route/static guards:

```text
exactly one registered POST /api/chat route
registered endpoint is not the legacy chat callable
registered endpoint has no get_pg_conn/direct-SQL/retrieval-service dependency
V2 route/contracts/shared-dependency modules import neither backend.api.chat nor backend.deps
S11A chat getter preserves the Accepted S10O operations getter/env surface and never calls it
new service imports no legacy canonical writer, V042 writer, active-index mutator, or offline writer
no exception path invokes the legacy chat callable
feedback checkpoint is immutable/read-only and commits atomically with the displayed turn
```

- [x] Run repository gates:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`.

- [x] Run the established scope, secret, generated-cache, fresh locked-offline wheel/package-content,
  source parity, and frozen original PostgreSQL/Milvus/forensic hash checks from the Accepted S8X
  protected-target evidence plus the Accepted S10O Admin receipt. Expected: all protected state
  remains exact.
- [x] Perform one lean implementation/test-integrity review. Repair open Critical/Important only;
  record Minor/YAGNI without another review loop. Rerun the smallest affected checks after repair.

## Task 8: Candidate and Accepted without ledger closure

- [x] Record S8C/S9I/S10O/S8X receipt and contract bindings, S8X live Read/Answer/owner hashes, the
  authority split, canonical legacy-baseline JSON/SHA before and after implementation, exact
  RED/GREEN commands/results, changed-file hashes, HTTP demo
  response invariants, compatibility mapping, route/static guards, regression/static/gate results,
  protected-source hashes, and review disposition in `s11a/verification-receipt.json`.
- [x] Mark the S11A contract Candidate only after all required evidence exists. Do not check any
  task at Candidate.
- [x] Recheck the final diff is limited to the five implementation modules, one test file, plus authorized S11A/
  status/evidence files. Confirm no frontend, Canonical V2 predecessor, schema, migration, source,
  provider, admin/domain-writer, or OpenSpec behavior artifact changed.
- [x] With zero open Critical/Important findings, mark S11A Accepted and record it as a dependency
  checkpoint for S11B/S11C. Record the live ledger before/after with no delta and leave Tasks
  11.1-11.5 unchecked.
- [x] Update only existing verification/portfolio/mainline/convergence/agent-link evidence needed to
  point at the Accepted S11A receipt. Do not claim aggregate consumer migration or product Cutover.
- [x] Run strict OpenSpec and `git diff --check` once more. Expected: both exit `0`.

## Rollback checkpoint

If S11A cannot reach Candidate, unregister the V2 POST endpoint, restore the legacy route decorator,
remove the private adapter, V2-only contracts/route modules and S11A test, remove only S11A's chat
getter/import additions from `backend/canonical_v2_deps.py`, and restore the prior reset-cookie
helper if it changed. Do not remove or rewrite Accepted S10O's shared module, operations getter, or
configuration surface. Remove only S11A run/status evidence. The legacy comparison oracle remains
intact, and no
database, index, source, provider, release pointer, task ledger, Commit, Push, PR, Archive,
promotion, or Cutover state requires rollback.
