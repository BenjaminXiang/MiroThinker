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

## Round 2 decisions

### D6 — the wait cap is a catalogue default, not another "unset means code"

`serving.vector_lane_timeout_seconds` carries `default=8.0` in the schema (unlike
`rerank_timeout_seconds`, whose default is `None` with the code owning the
number). Reason: this knob has exactly one meaningful default and the page must
be able to show "the serving line waits 8 s", not a blank. The two places that
name 8.0 — the schema default and
`knowledge_read._VECTOR_LANE_OUTER_WAIT_DEFAULT_SECONDS` — are pinned to each
other by a test
(`apps/admin-console/tests/test_vector_lane_timeout_knob.py::test_the_row_exists_with_bounds_and_the_serving_default`),
so neither can drift. Bounds `0.1 .. 120`: a zero/negative cap would remove the
protection the cap exists for, and anything above the client's own timeout is
not a cap. A file value equal to the default is not projected into the
environment (the managed-runtime rule for "differs from the default"), which
keeps the reader's fallback the single source for the unset case.

### D7 — the identity probe is an explicit extra step, not part of the one call

`test_connection` documents "exactly one bounded call per invocation" and its
tests assert `len(transport.calls) == 1`. The identity probe needs two calls (or
one call plus a pack read), so it lives beside that contract, not inside it: the
request carries `identity_check: true` (the embedding card always sends it),
and the route composes the verdict into the same response. Consequences worth
naming: the transport check can stay hermetic in every existing test, the probe
can be exercised with an injected embedder, and a caller that only wants to know
"does this address answer" still gets exactly one call.

### D8 — arms, thresholds and why the row read is done by hand

* **reference** (`cosine ≥ 0.999`): the strongest cheap signal when the recorded
  endpoint is still reachable — the same model served from two addresses returns
  the same vector. Measured: 1.000000 through a forwarding gateway, and 15/15
  pairs exactly 1.0 on the live endpoint (one cold-start pair 0.9999676).
* **index** (`cosine ≥ 0.99`): the fallback that is correct at a customer site
  that has left the school network. Query = a document's verbatim
  `embedded_content` (deterministic: `ORDER BY point_id`, 200–1200 chars), target
  = the vector the index stored for that document. Measured 0.999933.
  A wrong space measured 0.004543 (arm index) and -0.007435 (arm reference), so
  the thresholds sit ~1000× above the rejected values and just below the
  accepted ones.
* The parent's phrasing for the index arm was "the nearest neighbour is that same
  document". The full matrix is 1.68 GB and `np.load` materializes it (measured
  1.6 GB RSS — this code runs inside the serving process, so that is not
  acceptable per click). The `.npz` members are uncompressed, so one row can be
  read by seeking to `header + i*row_bytes` in `matrix.npy`; the probe reads the
  target row plus a strided 798-row sample (~26 MB, 0.04 s) and requires both
  `cosine ≥ 0.99` and "no sampled row beats the target". The first version of the
  reader forgot the header offset and produced a *plausible-looking* wrong row
  (norms ≈ 1, ~0.02 cosine against the right vector), which is why the reader is
  pinned against `np.load` in a test.
* A probe that cannot measure (no pack configured, unreachable reference, silent
  endpoint) reports `passed = null` with the reason — never a pass. The route
  wraps the call so an advisory check can never turn into a 5xx.
