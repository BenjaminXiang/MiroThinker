# Acceptance: embedding-endpoint-configurable-and-lane-fail-open

## Acceptance criteria

| # | Criterion | Evidence required | Status |
|---|---|---|---|
| AC1 | A transport failure of the embedding provider leaves the vector lane `unavailable` with `failure_kind ∈ {timeout, connection_failure}` and **no** `IsolatedKnowledgeReadIntegrityError` reaches the caller | unit test at the adapter seam + integration test on the lane trace | **passed** — clusters A1–A4 + B1/B2; live: phase-1 probe `retrieval_done` vector `unavailable` with no error frame |
| AC2 | Genuine integrity failures (wrong dimension, non-finite vector, model-id mismatch, non-determinism) still raise `IsolatedKnowledgeReadIntegrityError` | unit test | **passed** — cluster A5 + B4 |
| AC3 | A vector-lane attempt against a hung provider is bounded by the configured outer wait (default 8 s) and the turn completes | unit test with wall-clock assertion | **passed** — B3 (30 s delegate, 1 s cap, turn returns in < 3 s) + B6 (unparsable knob → 8.0 s) |
| AC4 | After 2 consecutive transport failures the lane is skipped for 300 s (no provider call) and is reported `unavailable`; the breaker closes again after the window; the keep-warm path consults the same state | unit tests with injected clock | **passed** — C1–C3 (injected clock), C4 (`note_lane_timeout`), C5 (open breaker = 0 HTTP requests on a counting server; the keep-warm calls the same adapter, so it reaches the same gate) |
| AC5 | Effective embedding base URL = `CANONICAL_V2_EMBEDDING_BASE_URL` when set, bundle address otherwise; a non-`http(s)` value is rejected | unit tests | **passed** — D1–D5, D7; live: phase 1 (env set, black hole → lane failed although the bundle records a working address) and phase 2 (env unset → bundle address used, lane succeeded) |
| AC6 | The frozen bundle check still rejects a changed `model_id` / `dimension` / `content_sha256`; **the bundle file and the serving pack are unmodified** | unit tests with bundle-document fixtures + `git status` clean on the bundle path | **passed, with a deviation the parent must review** — D6/D8/D9: the identity gates still reject. *"Accepts a changed `base_url` in the bundle document"* is not achievable while `content_sha256 ↔ _QWEN_EMBEDDING_BUNDLE_SHA256` is kept, because that constant **is** the self-hash of the document (recomputed in-test: `05473fab…` = sha256 of the document including `base_url`): any edited address forces a new `content_sha256` and is refused (locked by D9). The *operational* requirement is met and verified instead — the address is resolved from the managed setting at one point, the bundle stays byte-frozen (no reseal, no rebuild), and `base_url` is no longer part of the code's expected-document literal (D8) |
| AC7 | `resolve_embedding` reports the effective address and matching origin; the admin config page presents the address row as editable and the model row as frozen | resolver unit test + settings-store/catalogue tests + presets payload test | **passed** — cluster E1–E5 + the rewritten catalogue test; admin targeted suite 168 passed |
| AC8 | On a real scratch serving instance with a black-hole embedding endpoint, one real `/api/chat/stream` question ends with a normal answer, no `event: error`, and the trace shows the vector lane unavailable; with the real endpoint the lane succeeds again | probe evidence: raw SSE frames, trace lines, wall clock | **passed** — `verification.md` §③ (phase 1: vector `unavailable`, no error frame, access log `completed`; phase 2: vector `succeeded`, 128 candidates, 0.87 s) |
| AC9 | Regression: touched suites show no new failures versus the pre-change baseline; pre-existing reds are named | before/after pytest counts | **passed** — admin-console full suite before 25F/105E/1481P vs after 25F/105E/1490P with a byte-identical 130-entry failure set; targeted miroflow-agent 1F/376P where the single failure reproduces on the base commit |

## Not accepted by this change

- Improving answer quality on any lane (no retrieval-policy change).
- Making the endpoint hot-reloadable without a restart.
- Any change to the serving pack, the embedding bundle, the index or Postgres.
- Multi-host / multi-provider embedding fallback (single effective address only).

## Round 2 acceptance criteria

| # | Criterion | Evidence required | Status |
|---|---|---|---|
| AC10 | The vector-lane wait is a catalogue row with the serving default and explicit bounds; it round-trips page → managed file → startup environment → the single reader; invalid values are refused with the field named | `apps/admin-console/tests/test_vector_lane_timeout_knob.py` (12 tests) | **passed** |
| AC11 | The embedding connection test measures endpoint identity and reports arm + cosine + threshold + an actionable verdict; a probe that cannot run reports "not verified" | `apps/admin-console/tests/test_embedding_identity_probe.py` (17 tests) + `probe/identity-calibration.json` | **passed** |
| AC12 | The verdict separates the index's own space from a dim-4096 endpoint in another space | calibration: 1.000000 / 0.999933 accepted vs -0.007435 / 0.004543 rejected | **passed** |
| AC13 | The embedding card asks for the check and shows the verdict | page assertions in the same test file | **passed** |

### Not accepted by round 2

- Resealing the bundle or storing an identity digest inside it (out of the
  question for the delivered v1; the probe reads only what already exists).
- Re-enabling `_validate_release_bound_vector_evidence` (a serving-time
  comparison is a separate decision with its own latency cost).
- Automatic re-indexing when an operator switches to a different space.
