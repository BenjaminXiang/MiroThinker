# Acceptance: embedding-endpoint-configurable-and-lane-fail-open

## Acceptance criteria

| # | Criterion | Evidence required | Status |
|---|---|---|---|
| AC1 | A transport failure of the embedding provider leaves the vector lane `unavailable` with `failure_kind ∈ {timeout, connection_failure}` and **no** `IsolatedKnowledgeReadIntegrityError` reaches the caller | unit test at the adapter seam + integration test on the lane trace | pending |
| AC2 | Genuine integrity failures (wrong dimension, non-finite vector, model-id mismatch, non-determinism) still raise `IsolatedKnowledgeReadIntegrityError` | unit test | pending |
| AC3 | A vector-lane attempt against a hung provider is bounded by the configured outer wait (default 8 s) and the turn completes | unit test with wall-clock assertion | pending |
| AC4 | After 2 consecutive transport failures the lane is skipped for 300 s (no provider call) and is reported `unavailable`; the breaker closes again after the window; the keep-warm path consults the same state | unit tests with injected clock | pending |
| AC5 | Effective embedding base URL = `CANONICAL_V2_EMBEDDING_BASE_URL` when set, bundle address otherwise; a non-`http(s)` value is rejected | unit tests | pending |
| AC6 | The frozen bundle check still rejects a changed `model_id` / `dimension` / `content_sha256` and now accepts a changed `base_url`; **the bundle file and the serving pack are unmodified** | unit tests with bundle-document fixtures + `git status` clean on the bundle path | pending |
| AC7 | `resolve_embedding` reports the effective address and matching origin; the admin config page presents the address row as editable and the model row as frozen | resolver unit test + settings-store/catalogue tests + presets payload test | pending |
| AC8 | On a real scratch serving instance with a black-hole embedding endpoint, one real `/api/chat/stream` question ends with a normal answer, no `event: error`, and the trace shows the vector lane unavailable; with the real endpoint the lane succeeds again | probe evidence: raw SSE frames, trace lines, wall clock | pending |
| AC9 | Regression: touched suites show no new failures versus the pre-change baseline; pre-existing reds are named | before/after pytest counts | pending |

## Not accepted by this change

- Improving answer quality on any lane (no retrieval-policy change).
- Making the endpoint hot-reloadable without a restart.
- Any change to the serving pack, the embedding bundle, the index or Postgres.
- Multi-host / multi-provider embedding fallback (single effective address only).
