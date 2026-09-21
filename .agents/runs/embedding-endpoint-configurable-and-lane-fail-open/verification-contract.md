# Verification contract: embedding-endpoint-configurable-and-lane-fail-open

Change: `openspec/changes/embedding-endpoint-configurable-and-lane-fail-open/`.
Written **before** production edits, per AGENTS §4 (TDD boundary).

## RED artifacts (must fail before the fix, pass after)

Each RED is named as `test file::test name` with its fixture source.

### Cluster A — transport is not integrity (F1.1 + F1.2)

| # | RED assertion | Fixture source |
|---|---|---|
| A1 | `company.vectorizer.EmbeddingClient.embed_batch` raises builtin `TimeoutError` (with `__cause__` an `httpx.TimeoutException`) when the endpoint times out | constructed scenario: real `httpx` call to a local socket that accepts and never answers, timeout=0.2 s |
| A2 | `EmbeddingClient.embed_batch` raises builtin `ConnectionError` (with `__cause__` an `httpx.TransportError`) when the endpoint refuses the connection | constructed scenario: real `httpx` call to a closed loopback port |
| A3 | `EmbeddingClient.embed_batch` raises builtin `ConnectionError` for a non-2xx provider answer | constructed scenario: local HTTP server returning 503 |
| A4 | `_ValidatingEmbeddingAdapter.embed_batch` re-raises builtin `TimeoutError` / `ConnectionError` unchanged | constructed scenario: stub delegate raising the builtin |
| A5 | the same wrapper still raises `IsolatedKnowledgeReadIntegrityError` for a wrong-dimension vector, a non-finite vector, a wrong `model_id` delegate and a non-deterministic delegate | constructed scenario: stub delegate |

Failure mode before the fix: A1–A3 raise `httpx.ConnectTimeout` / `httpx.ConnectError`
/ `httpx.HTTPStatusError` instead of the builtins; A4 raises
`IsolatedKnowledgeReadIntegrityError` instead of passing through.

### Cluster B — lane fail-open observed at the retrieval trace (F1.2 + F1.3)

| # | RED assertion | Fixture source |
|---|---|---|
| B1 | a vector-lane adapter whose delegate raises builtin `ConnectionError` yields a trace row with `status="unavailable"`, `failure_kind="connection_failure"`, `candidate_count=0`, and the turn returns an `EvidenceSet` (no exception) | constructed scenario: isolated read engine with a stub vector adapter, mirroring `tests/canonical_v2/test_knowledge_read_universal_web_contract.py` |
| B2 | the same for builtin `TimeoutError` → `failure_kind="timeout"` | constructed scenario |
| B3 | a vector-lane delegate that blocks longer than the cap yields `failure_kind="timeout"` and the call returns within cap + 1.5 s wall clock | constructed scenario: delegate sleeping 30 s, cap configured to 1 s via `CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS` |
| B4 | an `IsolatedKnowledgeReadIntegrityError` from a genuine integrity failure still propagates out of the lane | constructed scenario: delegate returning a wrong-dimension vector through the real validating wrapper |

Failure mode before the fix: B1/B2/B3 never produce those rows because the
laundering raises `IsolatedKnowledgeReadIntegrityError` (B1/B2/B4) or block for
the delegate's full duration (B3).

### Cluster C — breaker (F1.4)

| # | RED assertion | Fixture source |
|---|---|---|
| C1 | 2 consecutive transport failures open the breaker; the 3rd attempt issues **no** delegate call and yields `status="unavailable"` with a transport `failure_kind` | constructed scenario: counting stub delegate + injected clock |
| C2 | after the 300 s window a probe attempt is allowed; success closes the breaker and a subsequent attempt calls the delegate again | injected clock |
| C3 | a success resets the consecutive-failure count (1 failure → success → 1 failure does not open) | injected clock |
| C4 | an outer-wait expiry also counts as a transport failure (2 expired waits open the breaker) | constructed scenario: blocking delegate + `note_outer_timeout` |
| C5 | the keep-warm path skips the embedding call while the breaker is open and calls it once more after the window | constructed scenario: serving-level warm function with a counting delegate |

Failure mode before the fix: no breaker exists; every attempt calls the delegate.

### Cluster D — effective endpoint resolution (F2.1 + F2.2)

| # | RED assertion | Fixture source |
|---|---|---|
| D1 | with `CANONICAL_V2_EMBEDDING_BASE_URL` set, the loaded adapter embeds against that address even though the bundle records another | bundle-document fixture: the frozen qwen document with its recorded `base_url`, copied in-test (never a file edit) |
| D2 | with the variable unset or empty, the adapter uses the bundle's recorded address | same fixture |
| D3 | a changed `base_url` in the bundle document no longer fails the load, while a changed `model_id`, `dimension` or `content_sha256` still does | same fixture with one field mutated |
| D4 | an empty or non-`http(s)` effective address is rejected | same fixture + env value |
| D5 | the effective address carries no trailing-space surprise (`strip`) and keeps its path (e.g. `/v1`) | same fixture + env value |

Failure mode before the fix: D1 fails (env has no reader), D3 fails (whole-document
equality rejects a changed `base_url`).

### Cluster E — admin reports the effective address (F2.3 + F2.4)

| # | RED assertion | Fixture source |
|---|---|---|
| E1 | `resolve_embedding(environ={"CANONICAL_V2_EMBEDDING_BASE_URL": X})` reports `base_url == X` and an `endpoint_origin` naming the environment | constructed environ mapping |
| E2 | with the variable absent it reports the bundle-recorded default address | constructed environ mapping |
| E3 | `extraction_endpoints.embedding_base_url` is editable in the settings store and `extraction_endpoints.embedding_model` is not; neither reason claims the *address* is frozen | settings-store test with a tmp managed file |
| E4 | the `/connections/presets` payload's embedding entry reports the effective address and a note that does not claim the endpoint is frozen | admin API test client |

Failure mode before the fix: E1 fails (reports the frozen default), E3 fails
(the address row is refused as display-only), E4 fails (note says 冻结).

## GREEN evidence required beyond unit tests

AGENTS §6: for RAG/chat work a unit test alone is not sufficient. This change
additionally requires the **scenario probe** (AC8): a scratch serving instance
(boot ≈291 s) driven once with `CANONICAL_V2_EMBEDDING_BASE_URL=http://10.255.255.1:9/v1`
and once with the real endpoint, through the real `/api/chat/stream` entry, with
raw SSE frames + trace lines + wall clock recorded in `verification.md`.

## Regression baseline

Targeted suites only (time discipline): the new test files, plus
`apps/miroflow-agent/tests/canonical_v2/` files touching the read engine,
`knowledge_build_isolated` and the serving runtime, plus the touched
`apps/admin-console` tests. Before/after failure counts are recorded with the
pre-existing reds named.

## Out of contract

- Changing the served answers' content or lane planning.
- Any edit to the embedding bundle, the serving pack, or the index.
- Hot reload of the endpoint without a restart.
