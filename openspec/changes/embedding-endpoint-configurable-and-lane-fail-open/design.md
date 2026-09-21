# Design: embedding-endpoint-configurable-and-lane-fail-open

## Classification

**Standard work**, two coupled fixes on one lane. Behavior-affecting (RAG
retrieval lane policy + public config surface) → OpenSpec change + verification
contract required before production edits.

## Verification surface

| Claim | Verification surface |
|---|---|
| transport ≠ integrity classification | unit (adapter-level) + integration (lane trace) |
| genuine integrity failures still fail closed | unit (adapter-level) |
| outer wait cap | unit (hung delegate, wall clock) |
| breaker open/close/reset | unit (injected clock) |
| base-url precedence | unit (env on/off) + integration (adapter construction) |
| frozen identity check relaxed exactly at `base_url` | unit (bundle document fixtures) |
| admin reports/tests the effective address | contract test on the presets payload + settings-store test |
| the whole thing on a real box | **scenario probe**: scratch serving instance, real `/api/chat/stream`, black-hole endpoint vs real endpoint |

Oracle strength: strongest available is the scenario probe (real stack, real
Milvus-free serving pack, real SSE stream). Unit tests alone are explicitly not
sufficient for a RAG-lane claim (AGENTS §6), so the probe is mandatory for the
GREEN claim.

Mock boundary: tests replace only the *embedding delegate* (a fake object that
raises or blocks) — never the lane, the read engine, the trace assembly or the
HTTP client's own classification (that is exercised with real httpx exceptions
raised from a real `httpx` call against an unreachable address where possible).

## Design decisions

### D1 — normalize at the HTTP seam, not at every caller

`company/vectorizer.py::EmbeddingClient.embed_batch` is the only place on the
serving path that speaks HTTP for embeddings (`knowledge_build_isolated.py:47,8039`
uses it as `_OpenAIEmbeddingClient`). Normalizing there fixes the serving lane,
the admin connection test and the build paths in one edit, and keeps the
classification next to the calls that actually raise those exceptions.

`httpx.HTTPStatusError` is included in the transport class. Rationale: a
non-2xx answer from the provider is a provider-availability failure, not
corruption of the vector data — and a 503 while the customer's embedding server
boots would otherwise reproduce exactly the turn-killing defect this change
exists to remove. This is the one deliberate extension beyond the literal
`httpx.TransportError`/`OSError` list; it is recorded here for review.

### D2 — the launderer keeps laundering, but not transport

`_ValidatingEmbeddingAdapter` exists so that *integrity* failures fail closed.
Its `except Exception` is correct for that purpose and wrong for transport. The
fix is an explicit pass-through of the two builtins, not a weakening of the
wrapper: every other exception still becomes
`IsolatedKnowledgeReadIntegrityError`.

`knowledge_read.py::_invoke_lane` already has the fail-open hook for exactly
those two builtins, so no change is needed there — that is the existing seam the
defect was hiding behind.

### D3 — the cap is an outer wait, like web

`execute()` already waits per-lane with `futures[lane].result(timeout=...)`; the
`vector` lane passed `None`. The cap reuses that mechanism
(`_vector_lane_outer_wait_seconds()` reading
`CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS`, default 8.0 s). `knowledge_read.py`
already reads `os.environ` for an env-gated debug probe (line 49), so an env knob
here follows the module's existing idiom rather than introducing one.

The abandoned future keeps running in its thread (the executor is shut down with
`wait=False`), bounded by the adapter's own request timeout. The breaker is what
keeps that cost to roughly one attempt per window.

### D4 — the breaker belongs to the vector lane, the state is process-scoped

New module `canonical_v2/embedding_lane_resilience.py` holding a
consecutive-failure breaker with states `closed → open → probe` (mirroring
`web_lane_resilience.WebLaneBreaker`, which is web-specific and therefore not
reused) plus a process-scoped singleton.

- The **vector lane** consults it in `create_isolated_vector_recall_adapter`
  before calling the delegate, records success/failure around the call, and
  raises builtin `ConnectionError` when the breaker is open — which the existing
  `_invoke_lane` hook turns into `unavailable` + a transport `failure_kind`.
- The **outer wait expiry** is reported by `execute()` through an optional
  `note_outer_timeout()` hook on the lane adapter (the same
  `getattr(x, "warm", None)` idiom the serving module already uses for the page
  fetcher). Without it a black-holed route would only accumulate failures when
  the abandoned thread finally fails (~180 s later), so the breaker would take
  minutes to engage instead of two turns.
- The **keep-warm** path in `knowledge_serving_isolated.py` consults the same
  singleton: when the breaker is open the warm call is skipped instead of
  attempted; when allowed, the outcome is recorded like a lane attempt.

A new module rather than a field on an existing object because the two consumers
(the isolated read engine and the serving bootstrap) construct different objects
and only share process state.

### D5 — F2 resolution point

`load_content_addressed_embedding_adapter` is the single resolution point. It
already owns the bundle document and already builds the adapter, so the change is
`base_url = env or document["base_url"]` with an `http(s)` validation — no new
parameter, no new plumbing in the runner CLI, no bundle change. The managed field
is already projected into the environment at startup (`_FIELD_ENV_VARS`), so no
projection work is needed either.

The frozen check becomes: every field compared as before **except** `base_url`,
plus `content_sha256 == _QWEN_EMBEDDING_BUNDLE_SHA256` and the identity fields
(model/dimension) as before. The address is not part of the vector identity: the
vectors were produced by that model at that dimension, and the *matrix binding*
(`vector_matrix.npz` + `content_sha256`) is what proves the released vectors.

Admin side: `resolve_embedding` mirrors the same precedence using the same
`_first_env` helper the other resolvers use, so the connection test probes the
effective address; `PAGE_READONLY_FIELDS` drops the address row (it now has a
runtime reader) and keeps the model row with honest copy; the `/connections/presets`
payload keeps its key but describes the runtime-resolved address instead of a
frozen one; the page's own copy strings are updated to match.

## Rollback

Each fix is independently revertable: F1's breaker/cap are additive (a revert
restores "attempt every turn, no cap"), F2's resolution is a one-line precedence
(a revert restores "bundle address always wins"). Neither touches persisted data,
the bundle, or the index, so rollback is `git revert` plus a restart.
