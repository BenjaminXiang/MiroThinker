# S11A Release-Bound Chat HTTP Adapter Dependency Audit — 2026-07-20

## Outcome

The smallest honest first consumer slice is to replace only the registered `POST /api/chat` entry
with one release-bound adapter over the already-designed Canonical V2 planner, reader, answerer, and
typed answer-session contracts. The V2 HTTP contracts, route, and application-state dependencies
live in V2-only modules that do not import the 6,932-line comparison oracle or legacy dependency
factories. The HTTP route owns only cookies, exact typed selection translation, bounded HTTP error
translation, and returning an already validated response. The private adapter maps the validated
plan/evidence/result outcome to `ChatResponse` before atomically committing session/checkpoint state.
Neither layer may classify locally, query Postgres, choose evidence, construct claims, or fall back
to the legacy fixed-handler implementation.

S11A is **revalidated and Ready** at `2026-07-20T17:43:17Z` after returning to Specified at
`2026-07-20T17:32:44Z` for the later Accepted S8X successor-handoff correction. The historical Ready
state at `2026-07-20T14:31:57Z` remains superseded. A fresh lean review of exact Specified hashes
audit `0a7e0bcd6bd49c6a9eaef15103ef2b539bdaf351f067e2a62f8d635ab6a05310`, plan
`99ab2e060a0bf2202182034e0cb7d4c506383ef175255eca33e9a3d1d64e23ea`, and contract
`5894be2329ffc22d8f8797e2db6b445f4032d8209e98fa542c4d210954ad1bc2` reported
`Critical=0/Important=0/Minor=1/YAGNI=0`. The Minor is a non-blocking plan-prose shorthand for the
otherwise exact failure/error/skipped signature schema; it does not change the frozen payload or
gate. S8C and S9I remain the Accepted capability owners, while Accepted S8X is the
authority for the current Read/Answer producer-consumer handoff and live module bytes. Its receipt
and contract SHA-256 values are
`b00e3fd9594b821d5df13a2c0e012f86f9f468c6d66dda8777b4d889fa3100ac` and
`b9e0ca287ad1b8efa530c95e48bad6c77ab2501728f16efa67872e27e685e0db`; live Read, Answer,
dedicated-owner, and physical-owner hashes are respectively
`a28488c400a8e1dea66b3ad9f87fc048895b4f96f0da15548bcc9590e85b86fc`,
`386ce550f9b3f1c47c76f854307d9461cb8177bf44968dd7f4f51678ee104d9e`,
`29191a15c875cf95f4d2c6c432a2c6136c3f4cd9571369ef00306a4767b79d01`, and
`61c9ec362e39d7e4eca9a3db7e02d9bf5ebde095e4acb0f02c989437baed147f`.

S10O remains Accepted. Its receipt is SHA-256
`e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246` and freezes the first-writer
`backend/canonical_v2_deps.py` bytes at
`367f75f6876bc0ae7cff92b085ca3ecab9869d7509720689e256f99fedd9b08d`. The S10O writer is complete,
so the sequential shared-file gate remains satisfied. The historical Ready artifact hashes before
this transition were audit `c65c640aa7d9cd1f9b9ee8157eecfb86daa52bca26984a2d695f28ac50aafd6a`,
plan `567aff842fc2acfd68396c014b5f9fd284fce267bc8b387d21e27bb284ff7181`, and contract
`39cdddd283134f4a09db442622e84442ca43da2f8c55f563de217caeeee5326f`.

S11A closes no OpenSpec task. It is the chat-HTTP predecessor for Task 11.1. Its HTTP/interface
tests, non-SQL route proof, and targeted checks provide partial evidence for Tasks 11.2, 11.3, and
11.4, but those broad tasks and Task 11.5 remain owned by the later aggregate S11C acceptance slice.
The formal task ledger therefore has no S11A delta.

## Current consumer audit

### Registered route is the legacy implementation

`apps/admin-console/backend/api/chat.py` is currently a 6,932-line legacy module. The registered
`POST /api/chat` function begins near line 5,730 and receives `conn=Depends(get_pg_conn)`. Its body
owns all of the following instead of delegating to the Canonical V2 deep modules:

- rule and LLM A-G classification;
- query rewriting and legacy `SessionContext` mutation;
- direct Postgres lookup helpers and SQL-backed relationship traversal;
- the legacy retrieval service, old Milvus assumptions, reranking, and Web fallback;
- answer synthesis, citation mapping, clarification, and followup generation;
- fixed per-query handlers and multiple caller-specific response branches.

This is exactly the implementation coupling that the active design rejects: HTTP is supposed to be
an adapter around `KnowledgeAnswer.answer`, not the owner of query planning, retrieval, evidence,
session, and rendering behavior.

The same file also exposes `/chat/session/reset` and `/chat/feedback`. S11A does not migrate admin
feedback operations or Canonical V2 gap storage; those belong to S10/S11B. The reset endpoint may
continue to issue an opaque cookie, but it must not make the legacy `SessionContext` authoritative
for the V2 route.

### Existing HTTP shape can be preserved

The current request and response types provide a usable compatibility envelope:

```text
ChatRequest
  query: str
  entity_id_hint: str | None

ChatResponse
  query, query_type, answer_text, citations, evidence, clarification,
  structured_payload, answer_style, citation_map, suggested_followups
```

The React chat page consumes those same fields. Candidate selection submits the previous query plus
the selected `CandidateOption.id` as `entity_id_hint`. That existing behavior can carry a V2
`ContinuationOption.option_id` without interpreting prose. No frontend change is needed for S11A.

Compatibility means retaining the request fields and complete response field/type envelope. It does
not mean preserving legacy handler names, V042 IDs, legacy `query_type` subcodes, direct SQL order,
old citation construction, or the old fixed-handler outputs. Those are pre-launch implementation
details and are explicitly non-goals of the active design.

### Existing tests are implementation-coupled evidence

The nearest chat tests call `backend.api.chat.chat(...)` directly and monkeypatch private lookup,
classifier, SQL, session, synthesis, or retrieval helpers. They remain useful as historical behavior
evidence, but they do not prove that the registered HTTP route uses Canonical V2. Rewriting all of
them in S11A would broaden this slice into Task 11.2/S11C.

S11A should instead add one new HTTP/interface owner and leave the legacy callable temporarily
available only as an unregistered comparison oracle. A later S11B/S11C slice can quarantine or
delete that code and retire/replace its implementation-coupled tests. The S11A owner must prove the
actual FastAPI route does not reach the comparison oracle or `get_pg_conn`.

### Frozen HTTP/import/test baselines

Read-only preflight at `2026-07-20T12:23:59Z` captured this exact current checkpoint before S10O
creates the shared dependency module:

- `backend/api/chat.py` is 6,932 lines with SHA-256
  `b589541cd5d0bb454af8ff8f23eaafe60d0a9ceb1b398267b83b0b429dbd476d`;
  `backend/main.py` is 165 lines with SHA-256
  `f869d493e7714c4223091d32bc116d5e17b9cecbb1e0b9ff45b8fb15912d4582`; and
  `backend/deps.py` is 134 lines with SHA-256
  `4167144d469d20d362929a0676b87361095055ab0de2bb7c56391773789d36b7`.
- The combined canonical Pydantic JSON-schema SHA-256 for `ChatCitation`, `CandidateOption`,
  `ClarificationPayload`, `ChatRequest`, `ChatResponse`, `ChatFeedbackRequest`,
  `ChatFeedbackResponse`, and `ChatSessionResetResponse` is
  `04584086d12ca5c56e5fd28f702d2fe5f71a20038be84f0dbdcc45524edcbd94`. `ChatRequest` fields are
  exactly `query,entity_id_hint`; `ChatResponse` fields are exactly
  `query,query_type,answer_text,citations,evidence,clarification,structured_payload,answer_style,citation_map,suggested_followups`.
- Runtime route enumeration without starting the application lifespan reports 57 total routes.
  The three chat POST routes occur in order at indexes 29–31:
  `/api/chat/session/reset -> backend.api.chat.reset_chat_session`,
  `/api/chat/feedback -> backend.api.chat.create_chat_feedback`, then
  `/api/chat -> backend.api.chat.chat`.
- The cookie name is exactly `miroflow_chat_session`; TTL/`Max-Age` is 1,800 seconds; both reset and
  first-chat issuance set `HttpOnly=true` and `SameSite=lax` with Starlette's default path `/` and
  no explicit `Secure` flag. Reset returns only `ChatSessionResetResponse(session_id: str)`.
- Importing `backend.main` currently loads 15 filtered legacy chat/dependency/provider modules and
  zero Canonical V2 modules. The direct path is `backend.main -> backend.api.chat -> backend.deps`,
  `backend.services.chat_context`, `backend.services.web_search_cache`,
  `backend.storage.chat_session`, `src.data_agents.professor.llm_profiles`, and
  `src.data_agents.service.retrieval`; `backend.deps` then imports legacy vectorizer, Web/provider,
  reranker, and retrieval surfaces.
- `frontend/src/api.ts` and `frontend/src/pages/Chat.tsx` SHA-256 values are respectively
  `6edf7cec416a8ab5f2f17f57d17bd6deb57ee10f99a88c553da31e040aae6a91` and
  `203f71c488299534800457f74792afc6a3f93f41fc0e54c7e8bbdd23ced8295b`. The React selection path
  sends the previous response query plus the exact selected `CandidateOption.id` as
  `entity_id_hint`. The built-in `backend/static/chat.html` is a separate 297-line simple consumer
  with SHA-256 `5b7877a104130b549e3e69f8f60bed4eb599a41749a1b7d69d8807eba2395476`;
  it reads only the compatible answer/citation subset and is not modified by S11A.
- The worktree does not contain tracked `openai_client_compat.py`. The supported root helper for
  this worktree is
  `/home/longxiang/MiroThinker/openai_client_compat.py`, SHA-256
  `95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a`. Without that root on
  `PYTHONPATH`, current admin pytest collection exits `4` before any S11A sentinel. With that exact
  helper, the 21 `test_chat_*.py` files collect 260 cases.
- The supported root-helper command currently returns exactly `250 passed, 7 failed, 3 skipped,
  4 warnings`; the three skips are the no-Postgres `test_chat_session_store.py` cases. The frozen
  failure set is these exact seven node IDs:
  - `tests/test_chat_context_helpers.py::test_lookup_company_uses_jsonb_alias_lookup`;
  - `tests/test_chat_v1.py::test_chat_v1_profile_uses_llm_synthesis_and_returns_citation_map`;
  - `tests/test_chat_v1.py::test_chat_profile_accepts_introduce_once_professor_variant`;
  - `tests/test_chat_v1.py::test_chat_profile_accepts_name_institution_research_and_papers_query`;
  - `tests/test_chat_v1.py::test_chat_profile_accepts_institution_prefixed_research_direction_query`;
  - `tests/test_chat_v1.py::test_chat_v1_patent_falls_back_to_template_and_files_pipeline_issue`;
  - `tests/test_chat_v1.py::test_chat_v1_dangling_marker_falls_back_for_ambiguous_professors`.

These seven failures are pre-existing implementation-coupled legacy evidence, not S11A repair
scope. S11A must preserve the exact failure set/count with zero new failure, error, skip, xfail, or
XPASS delta; it must not weaken or broadly repair those owners.

Read-only post-S10O refresh at `2026-07-20T13:37:12Z` confirms:

- `backend/api/chat.py`, `backend/deps.py`, the HTTP schema hash, both frontend hashes, static chat
  hash, root-helper hash, request/response field sets, cookie behavior, chat route indexes, and all
  seven legacy failure node IDs remain exact.
- `backend/main.py` is now 167 lines with Accepted S10O SHA-256
  `b10a7aa6cc7cc0c73b576d2268360e6107238f390c9e0fe75f247a736b91a8e0`; the only relevant delta is
  S10O's bounded V2 operations router.
- Runtime enumeration now reports 59 total routes. The three chat POST routes remain indexes 29-31
  and still point to the same legacy reset, feedback, and chat callables before S11A RED/GREEN.
- Importing `backend.main` still loads the same 15 filtered legacy chat/dependency/provider modules.
  Accepted S10O additionally loads exactly eight V2 operations modules:
  `backend.api.canonical_v2_operations`, `backend.canonical_v2_deps`, the Canonical V2 package,
  `canonical_revision`, `contracts`, `knowledge_gap_feedback`, `knowledge_gap_postgres`, and
  `rebuild_write_gate`.
- The exact supported root-helper command still collects 260 cases and returns `250 passed,
  7 failed, 3 skipped, 4 warnings`; `-rf` confirms the identical seven node IDs already listed
  above. Thus the post-S10O baseline has zero chat-test delta.
- The formal OpenSpec ledger is `65/80`; `tasks.md` and `acceptance.md` hashes are respectively
  `87eb7c1e6d9e5b80e535cb94398f42798cdf4f3c83fb818011d0948519e32e54` and
  `1943943ee6fbc50b33357db1cceb987af93eba129042e6e4d6edfb68c9d5261f`. S11A changes neither.

Read-only post-S8X refresh at `2026-07-20T17:32:44Z` confirms:

- S8C, S9I, S10O, and S8X remain Accepted. Their receipt SHA-256 values are respectively
  `9e912de80fad1d82c6b6e27d71f04b458a0c78799c104ff6ca0e659e0f43ebca`,
  `658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366`,
  `e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246`, and the S8X value above.
  S8C/S9I receipt hashes remain historical capability evidence; S8X alone binds the superseding
  live Read/Answer bytes and successor-handoff owners.
- The frozen Admin hashes remain exact: `backend/api/chat.py`
  `b589541cd5d0bb454af8ff8f23eaafe60d0a9ceb1b398267b83b0b429dbd476d`, `backend/main.py`
  `b10a7aa6cc7cc0c73b576d2268360e6107238f390c9e0fe75f247a736b91a8e0`, `backend/deps.py`
  `4167144d469d20d362929a0676b87361095055ab0de2bb7c56391773789d36b7`, and
  `backend/canonical_v2_deps.py` `367f75f6876bc0ae7cff92b085ca3ecab9869d7509720689e256f99fedd9b08d`.
  The schema SHA remains `04584086d12ca5c56e5fd28f702d2fe5f71a20038be84f0dbdcc45524edcbd94`;
  request/response fields are unchanged.
- Runtime inspection still reports 59 routes, chat POST indexes 29-31, 15 filtered legacy imports,
  and the same eight S10O V2 imports. The operations dependency still exposes only its four exact
  `CANONICAL_V2_*` settings and lazy getter; its cache remained untouched during inspection.
- The root helper remains `95aad03fd4fb8cd0a6491af91842e2a729e7861aed398f0dce4624cbe5d1916a`.
  A fresh exact legacy run collected 260 cases and
  returned `250 passed, 7 failed, 3 skipped, 4 warnings` with the identical seven node IDs and no
  error/xfail/XPASS delta. Canonical JSON contains `outcomes`, the sorted
  `(failure|error|skipped, classname, name)` tuples, plus `terminal_counts` with exact
  `collected/errors/failed/passed/skipped/warnings/xfailed/xpassed` values. It is serialized with
  `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")`; its SHA-256 is
  `de88a0b8a64bba955d80fe06b8e54a1783a46fda36549f43c9cb11ac192bc959`. Two independently
  generated JUnit files produced byte-identical canonical payloads. This is the pre-RED comparison
  baseline; it is not a passing suite claim.

### Candidate import graph must be separable before S11A acceptance

Leaving the V2 endpoint or dependency getter inside `backend/api/chat.py` or `backend/deps.py` would
make S11B's candidate-import quarantine impossible even when no legacy callable executes. Both
modules import legacy SQL/retrieval/provider/session surfaces at module load. S11A therefore owns
the following narrow separation now:

- `backend/api/chat_contracts.py` owns the existing `ChatRequest`, `ChatResponse`, citation,
  clarification, feedback, and reset envelopes. The legacy module re-exports these names so
  historical direct-import tests remain valid.
- `backend/api/canonical_v2_chat.py` owns the V2 `POST /api/chat` and reset endpoints and imports no
  legacy chat/retrieval/writer module.
- Accepted S10O owns the initial `backend/canonical_v2_deps.py`, including its exact lazy operations
  getter and four explicit `CANONICAL_V2_*` configuration names. S11A later adds only an
  application-state chat-adapter getter. That chat getter performs no environment, DSN, Milvus,
  provider, index, or fallback discovery and must not overwrite, rename, or weaken the S10O surface.
- The legacy `backend/api/chat.py` keeps the comparison callable and legacy feedback route for the
  S11A checkpoint, removes its `/chat` and reset decorators, and includes the V2 router only for the
  pre-S11B development app. S11B can register the V2 router directly without importing the legacy
  module.

This is an import-seam correction, not a second public chat framework. `backend/main.py` need not
change in S11A; S11B owns the V2-only candidate application registration.

## Accepted Canonical V2 inventory

### Planning and reading

The existing accepted entry points are:

```python
create_isolated_release_query_planner(...).plan(QueryPlanningRequest) -> RetrievalPlan
create_isolated_release_knowledge_read(...).execute(RetrievalPlan) -> EvidenceSet
```

Both are bound to an exact `IsolatedReleaseBundle` plus a serviceable `PublishedRelease`. The
planner validates protected slots, supported operations, A-G behavior, budgets, relationship paths,
enumeration, ambiguity, and release identity. After S8C acceptance, the reader composition also
owns all seven physical/current-Web lanes plus the accepted fusion, rerank, sufficiency,
supplemental, and Web-handle ports. Accepted S8X supersedes only the live Read-to-Answer handoff:
continuation candidates, blocking ambiguity, and typed traversal must use its final live hashes and
owners rather than the historical `knowledge_read.py` hash stored in the S8C receipt.

S11A must consume those factories. It must not assemble local lane adapters directly, use the old
`RetrievalService`, infer release identity from an environment DSN/collection name, or create a
second query/runtime framework.

### Answer and session

The existing answer entry point is:

```python
create_ephemeral_knowledge_answer(...).answer(TurnRequest) -> TurnResult
```

After S9I acceptance, `TurnRequest` includes typed session and safety directives while `TurnResult`
contains sanitized grounded claims, claim-evidence mappings, citations, limitations, assessment,
context/traversal receipts, conditional `ContinuationOffer`, interpretation notices, selector
traces, and deterministic degradation. The answer module, not HTTP, owns final claim admission and
session transitions. Accepted S8X is authoritative for the live answer-side current-turn candidate
and exact physical-traversal authorization guards; the historical S9I module hash is not a live-byte
freeze after that accepted correction.

S11A may retain only the minimal prior public receipt/active-offer state required to prepare the
next planning request and bind an HTTP selection. It must not reproduce the answer module's handle,
claim, ambiguity, traversal, or continuation rules. HTTP session persistence, cross-process state,
and durable TTL policy remain outside this first adapter slice.

S11B also needs one server-owned feedback authority without inspecting that private session map or
trusting client response JSON. S11A therefore exposes one immutable, read-only
`ChatFeedbackCheckpoint` containing only the last successfully displayed turn's session/turn,
release, content-addressed query/answer trace IDs, admitted evidence IDs, affected public domains/
paths, limitation codes, observed time, and content hash. The adapter exposes
`get_feedback_checkpoint(session_id) -> ChatFeedbackCheckpoint | None`. The adapter owns one
committed isolated `KnowledgeAnswer` instance per HTTP session, created by a server-owned
`answer_factory`. Before each turn it uses an explicit `answer_session_fork` port (the candidate
composition uses `copy.deepcopy`) to create a copy-on-write candidate, runs `answer` only on that
candidate, and performs compatibility mapping plus exact `ChatResponse` validation. Only full
success atomically swaps the candidate answer instance together with adapter state and checkpoint;
any planning/read/answer/mapping/response failure discards the fork, so the next turn cannot observe
an undisplayed answer-session transition. It has no mutation method and grants no canonical or
traversal authority.

## Selected minimal adapter seam

Add one admin-console-private service with this call flow:

```text
explicit accepted release runtime
  + HTTP query/cookie/typed option selection
  -> QueryPlanningRequest
  -> release-bound planner.plan
  -> release-bound KnowledgeRead.execute
  -> TurnRequest with the exact returned EvidenceSet
  -> fork the session's committed KnowledgeAnswer
  -> candidate KnowledgeAnswer.answer
  -> adapter-private compatibility mapper and exact ChatResponse validation
  -> atomic answer-instance/session/checkpoint swap
  -> validated ChatResponse returned to the route
```

The adapter is constructed through one local composition function that calls the Accepted S8C/S9I
factories through the Accepted S8X live Read/Answer boundary. The already-constructed adapter is
installed explicitly on FastAPI application state by
an isolated candidate/demo composition. The V2-only route resolves it through the chat-specific
getter that S11A appends to Accepted S10O's `backend/canonical_v2_deps.py` and fails closed with a
typed `503` when no adapter is installed. The chat getter never calls or derives configuration from
the S10O operations getter, imports the legacy dependency module, or discovers a database, active
index, release, provider, or fallback implicitly.

The adapter validates release continuity at every boundary:

```text
adapter release == planning request release == plan release
                == EvidenceSet release == TurnRequest release == TurnResult release
```

A mismatch is rejected before the next downstream effect. There is no catch-all fallback to the
legacy route.

The registered `POST /api/chat` function should have no `get_pg_conn` dependency. To keep S11A
small, the legacy `chat(...)` implementation may remain temporarily callable by historical unit
tests, but it must no longer carry the FastAPI route decorator. Exactly one registered POST route
must exist, and it must point to the V2 endpoint.

## HTTP compatibility and observability mapping

The private adapter mapper retains the existing HTTP envelope and uses only validated
plan/evidence/result values. It completes exact `ChatResponse` validation before any adapter
session/offer/checkpoint commit; the route does not remap the result.

| Existing field | Canonical V2 source |
| --- | --- |
| `query` | original HTTP query / `EvidenceSet.original_query` |
| `query_type` | stable V2 prefix plus validated plan behavior class/response mode |
| `answer_text` | sanitized `TurnResult.answer_text` |
| `citations` | grouped public-domain cards derived from admitted result citations and matching evidence/handles |
| `evidence` | serialized retained `EvidenceItem` records used by the result |
| `clarification` | blocking clarification or selectable V2 offer options that bind exact option IDs |
| `structured_payload` | bounded V2 release, plan, lanes, trace, coverage, claims, mappings, limitations, context, traversal, and continuation data |
| `answer_style` | deterministic/template versus validated prose-renderer mode |
| `citation_map` | displayed citation number to retained evidence/object identity |
| `suggested_followups` | at most three validated offer labels; no invented relationship claim |

`structured_payload["canonical_v2"]` is the observable product checkpoint. It must expose enough
bounded data to see `release -> plan -> lanes -> evidence -> claims`, plus session/continuation
receipts, without exposing raw selector drafts, provider secrets, internal source bytes, or an
unbounded full manifest.

The legacy `ChatCitation.type` allows only Professor, Company, Paper, and Patent. Internal auxiliary
or source-only evidence therefore remains visible in `evidence` and the V2 claim/citation payload but
is not forged into a public-domain citation card. Public cards derive labels from validated entity
handles/fused candidates rather than snippets or model prose.

For selection, `entity_id_hint` must match an option ID from the active offer retained for the same
cookie session. The adapter reconstructs `ContinuationSelection(offer_id, option_id)` from that
exact server record. Unknown, stale, cross-session, or already-consumed option IDs fail before
planning/provider effects. The adapter never guesses a selection from user wording.

`ClarificationPayload.default_id` remains a required compatibility string. When the accepted V2
ambiguity result has no dominant candidate, the mapper sets `default_id=""`; it does not highlight
the first blocking choice as an implied default. A dominant non-blocking interpretation may use its
exact validated option ID.

## Post-RED fixture-composition audit

The frozen seam RED was valid, but the first executable owner exposed contract-invalid or
incomplete fixture composition rather than adapter defects. The corrected owner retains the full
HTTP assertions and uses only established Accepted composition patterns:

- `RecordedPlanningProposal` requires Universal Web for information retrieval, so the exact branch
  now combines the real isolated exact lane with one bounded recorded empty Web port.
- The deterministic owner binds the route-private clock seam to `NOW`; checkpoint `observed_at`
  records the successfully displayed turn time, while source observation time remains on each
  `EvidenceItem`.
- Curved explicit-name punctuation makes `Robotics Co` a typed protected slot for the real isolated
  exact lookup. Without it, that adapter correctly compares the complete natural-language lane
  query and returns no local handle.
- Accepted S8C already composes a server-owned `SupplementalBudget` by exact-revalidating a real
  planner result before calling the real Read. S11A uses the same boundary, with
  `1000 ms / 2 calls / 1 retry / 5.0 cost units`, so the real sufficiency and successor-handoff
  stages can materialize the conditional targeted-evidence candidate.
- Accepted S8R2 supplies caller-owned representative enumeration context for public relationship
  traversal. S11A equivalently exact-revalidates only a real plan that already contains one
  supported typed public relationship path, non-empty displayed canonical IDs, and no enumeration
  policy, binding `fixture_owner.S8R2_SCOPE` and the plan `as_of`. It does not inspect query wording.

The real release-bound planner still runs once before these server/caller-owned controls; the real
release-bound Read and Answer execute unchanged. The adapter and HTTP route neither mutate plans nor
synthesize continuation or enumeration behavior. These post-RED corrections require final
test-integrity review but do not authorize a predecessor change.

The legacy `backend/api/chat.py` baseline is also not Ruff format-clean. It remains a 6,932-line
comparison oracle during S11A, so whole-file formatting is explicitly out of scope. Verification
must run Ruff check and `py_compile` on it, compare the exact frozen legacy JUnit signature, and
review its small route/model re-export diff. Ruff format-check remains mandatory for every other
new or changed S11A file.

## Observable vertical demo

The S11A HTTP owner should install an adapter composed from the accepted release-bound planner/read
factory and accepted answer factory using one isolated candidate fixture and recorded provider ports.
Through `TestClient`, it should execute:

1. an initial canonical query returning HTTP `200`, one accepted release ID, plan/lane traces,
   evidence, grounded claims/citations, and any valid conditional continuation;
2. an exact option selection using the same cookie plus the returned option ID, proving the active
   offer and selected operation are bound without wording heuristics;
3. a typed relationship follow-up over the displayed canonical context, proving the same release
   reaches a new plan, relationship evidence, claims, and traversal/context receipt.

The test must make the legacy callable and `get_pg_conn` raise if invoked. A passing HTTP response
therefore demonstrates the V2 route rather than merely testing a mapper. Recorded fake Web/LLM
ports are allowed; test-local fake planner/read/answer implementations are not the vertical proof.
This is a runnable isolated demo, not complete-candidate, real-provider, quality-threshold, or
production-cutover acceptance.

## OpenSpec task mapping

- **Task 11.1:** S11A implements only the chat HTTP subset. Admin APIs/UI, domain writers, other
  retrieval callers, and scripts remain for S11B/S11C.
- **Task 11.2:** the new HTTP/interface/trace owner is partial replacement evidence. The broad
  legacy test migration remains open.
- **Task 11.3:** S11A removes direct SQL and fixed-handler routing from the registered chat entry
  only. Full V042 writer/script/global-readiness/collection-name quarantine remains open.
- **Task 11.4:** S11A runs targeted and proportional no-external checks only. Repository-wide
  candidate-target checks and the retired-failure ledger remain open.
- **Task 11.5:** S11A can reach its own Accepted slice state, but aggregate consumer acceptance and
  confirmation that no accepted behavior depends on a removed legacy detail remain open.

No task is checked by S11A. The live ledger is recorded before and after acceptance with no delta.

## Options considered

1. **One private release-bound adapter plus V2-only HTTP/contracts/dependency modules — selected.**
   This is the smallest route migration that also leaves a quarantine-safe import seam for S11B.
2. Rewrite the legacy 6,932-line module in place. This mixes implementation-coupled cleanup,
   admin/feedback behavior, and broad test migration into the first consumer slice.
3. Add a second public chat/runtime framework or let callers supply lane adapters. This duplicates
   the accepted deep modules and is rejected.
4. Leave the legacy route active behind a feature flag. That cannot prove which implementation
   served a response and permits silent SQL fallback, so it is rejected. The isolated candidate
   app either has an explicit V2 adapter or returns `503`.

## Ready and acceptance decision

Ready requires:

- S8C, S9I, S10O, and S8X Slice Contracts and verification receipts all say Accepted; S8X binds the
  superseding live Read/Answer and owner hashes, while S10O freezes the shared
  `backend/canonical_v2_deps.py` bytes;
- this audit, plan, and Slice Contract receive one lean review with zero open Critical/Important;
- strict OpenSpec and document/scope checks pass;
- the V2 route/contracts load without legacy chat/dependency surfaces; the shared dependency module
  retains only Accepted S10O's explicit operations configuration plus S11A's app-state chat getter,
  and the chat getter has no environment/DSN/provider/index fallback; and
- the reviewed Specified hashes are recorded in the Ready transition.

S11A acceptance requires the HTTP vertical demo, compatibility/release/session/fail-closed tests,
targeted/broad-enough no-external checks, static route proof, and one lean implementation review
with zero open Critical/Important. Minor/YAGNI findings are recorded and non-blocking. Acceptance
does not check Tasks 11.1-11.5 and does not authorize S11B, complete-candidate installation,
promotion, Cutover, Commit, Push, PR, Archive, or destructive cleanup.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/grounded-progressive-answer/spec.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/convergence-plan-remaining-24-2026-07-20.md`;
- the Accepted S8C and S9I capability contracts/receipts;
- the Accepted S8X contract/receipt and its superseding live Read/Answer/owner hashes;
- the Accepted S10O contract/receipt and frozen `backend/canonical_v2_deps.py`;
- `apps/admin-console/backend/api/chat.py`;
- `apps/admin-console/backend/deps.py`;
- `apps/admin-console/frontend/src/api.ts` and `frontend/src/pages/Chat.tsx`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`.

This audit changed no production code, test, OpenSpec task, acceptance artifact, existing slice,
database, index, source, provider, release pointer, Commit, Push, PR, Archive, promotion, or Cutover.
