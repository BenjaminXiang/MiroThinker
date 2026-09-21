# Tasks: embedding-endpoint-configurable-and-lane-fail-open

## 0. Gate

- [x] 0.1 Read the live tree at `36df47b8` and confirm each seam named in the
  proposal (`verify`: file:line reads recorded in `proposal.md`).
- [x] 0.2 Create this change + ledger row (`verify`: row present in
  `openspec/change-ledger.md`).
- [x] 0.3 Write `.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`
  before any production edit (`verify`: file exists with RED assertions and
  fixture sources).

## 1. F1 — lane fail-open

- [x] 1.1 Normalize transport failures at the HTTP seam
  (`company/vectorizer.py::EmbeddingClient.embed_batch`)
  (`verify`: unit test asserting `TimeoutError` for a timeout and
  `ConnectionError` for a transport error / non-2xx, with `__cause__` kept).
- [x] 1.2 Pass builtin `TimeoutError` / `ConnectionError` through
  `_ValidatingEmbeddingAdapter.embed_batch`
  (`verify`: unit test — transport passes through, wrong-dimension /
  non-finite / model-mismatch still raise `IsolatedKnowledgeReadIntegrityError`).
- [x] 1.3 Outer wait cap for the `vector` lane in `KnowledgeRead.execute`,
  env `CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS`, default 8 s
  (`verify`: unit test with a blocking delegate; asserts the lane row is
  `unavailable` / `timeout` and the call returns within the cap).
- [x] 1.4 Consecutive-failure breaker (2 failures / 300 s window) + trace
  visibility + keep-warm consultation
  (`verify`: unit tests for open/close/reset with an injected clock; a test that
  an open breaker issues no provider call; a test that the keep-warm skips).
- [x] 1.5 No user-visible red error for this case (trace + access log only)
  (`verify`: probe evidence in `verification.md`; the existing stream error path
  is unchanged and no `KnowledgeReadIntegrityError` is raised).

## 2. F2 — endpoint resolution

- [x] 2.1 Effective base URL precedence in
  `load_content_addressed_embedding_adapter` (env wins, bundle is the fallback)
  (`verify`: unit tests — env set overrides bundle; env empty → bundle).
- [x] 2.2 Frozen check compares every field except `base_url`; `base_url` only
  has to be a non-empty `http(s)` URL; `content_sha256`/model/dimension gates
  kept (`verify`: unit tests — changed `base_url` accepted; changed `model_id`,
  `dimension`, `content_sha256`, empty/non-http `base_url` rejected).
- [x] 2.3 `resolve_embedding` reports the effective address + correct origin
  (`verify`: unit tests on the resolver).
- [x] 2.4 Page copy stops claiming the endpoint is frozen; the address row
  becomes editable, the model row stays read-only
  (`verify`: settings-store + catalogue tests updated, presets payload test).
- [x] 2.5 Bundle on disk untouched
  (`verify`: `git status` shows no bundle file changed; the probe boots the
  unmodified `run16-readerbound` pack).

## 3. Verification

- [x] 3.1 New tests from the contract run green
  (`verify`: targeted `pytest -q` runs recorded in `verification.md`).
- [x] 3.2 Regression: the touched suites' before/after failure counts recorded
  (`verify`: `verification.md` — named pre-existing reds).
- [x] 3.3 Scenario probe: scratch serving instance, real `/api/chat/stream`,
  black-hole `CANONICAL_V2_EMBEDDING_BASE_URL` → normal answer + vector lane
  `unavailable`; then the real endpoint → lane healthy again
  (`verify`: raw SSE frames, trace lines, wall clock in `verification.md`).
- [x] 3.4 Scratch server stopped; port 18188 untouched
  (`verify`: process check recorded in `verification.md`).
- [x] 3.5 `verification.md` written with layered evidence and residual gaps
  (`verify`: file exists).

## 4. Report

- [x] 4.1 Log-ready Chinese summary handed to the parent (parent owns
  `docs/plans/`) (`verify`: final report section).

## 5. Round 2 (2026-09-21)

- [x] 5.1 Managed row `serving.vector_lane_timeout_seconds` (default 8, bounds
  0.1–120) + env projection + one reader (`verify`: catalogue/round-trip/bounds
  tests, 12 green).
- [x] 5.2 Embedding identity probe: reference arm + index arm, thresholds
  calibrated on live data (`.agents/runs/…/probe/identity-calibration.json`)
  (`verify`: 17 green tests + calibration run).
- [x] 5.3 Route wiring behind `identity_check` and page rendering of the verdict
  (`verify`: route tests + page assertions).
- [x] 5.4 Base-vs-branch comparison of `tests/canonical_v2/test_knowledge_build_isolated.py`
  (`verify`: failure-id `comm` in `verification.md` §⑤).
- [x] 5.5 Regression: admin-console full suite before/after, failure sets
  compared (`verify`: `verification.md` §②).
