# Verification: embedding-endpoint-configurable-and-lane-fail-open

Worktree `.worktrees/embedding-lane-f1f2`, branch `fix/embedding-lane-f1f2`,
base `36df47b8`. Contract:
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

## ① New tests written this slice (52 tests, all green)

| Cluster | File | Tests | What it locks | Fixture source |
|---|---|---|---|---|
| A — transport ≠ integrity | `apps/miroflow-agent/tests/canonical_v2/test_embedding_transport_classification.py` | 5 | `httpx.TimeoutException`→builtin `TimeoutError`; transport fault / non-2xx→builtin `ConnectionError` with `__cause__`; the validating adapter passes both through and still fails closed on wrong dimension / non-finite / model mismatch / non-determinism | **constructed scenario driven against real loopback sockets** (a server that never answers, a refused port, a 503 responder) + stub delegates |
| B — lane fail-open at the trace | `apps/miroflow-agent/tests/canonical_v2/test_embedding_lane_fail_open.py` | 6 | `connection_failure` / `timeout` trace rows with `status="unavailable"` while the turn returns an `EvidenceSet`; integrity failures still propagate; the 8 s cap bounds a hung adapter (wall clock asserted); the cap notifies the lane adapter; an unparsable cap falls back to the default | **constructed scenario** on the real `KnowledgeRead.execute` lane machinery (mirrors `test_knowledge_read_universal_web_contract.py`) |
| C — breaker | `apps/miroflow-agent/tests/canonical_v2/test_embedding_lane_breaker.py` | 7 | 2 consecutive failures open the breaker; the 300 s window re-opens it as a probe; success closes/reset; an outer-wait expiry counts; open breaker = **zero HTTP requests** (counting loopback server); healthy provider stays closed | class-level: injected clock; adapter-level: real `_OpenAICompatibleEmbeddingAdapter` + counting HTTP server |
| D — endpoint resolution | `apps/miroflow-agent/tests/canonical_v2/test_embedding_endpoint_resolution.py` | 11 | env wins over the recorded address; blank/unset → recorded; strip + path kept; non-http(s) refused (both sources); identity gates still reject model/dimension/foreign-hash; a resealed bundle is still refused; the loader's expected document carries no `base_url` literal; only one module reads the variable | **bundle-document fixture written to a temp file**: the verbatim frozen qwen document (self-hash verified inside the test) |
| E — admin effective endpoint | `apps/admin-console/tests/test_embedding_effective_endpoint.py` | 8 | resolver reports the effective address + origin (`managed-file(env:…)` / `env:…` / `release-bundle-default`); the presets payload reports it and never claims the address is frozen; the connection spec's default is "runtime-resolved"; the page copy is honest | real resolver + real FastAPI route graph over scratch managed files + shipped spec table |
| Regressions updated (pre-existing files whose expectations encoded the old behavior) | `apps/admin-console/tests/test_managed_config_catalogue.py`, `test_canonical_v2_runtime_sources.py`, `test_admin_model_roles_page.py`, `test_admin_config_page_shell.py` | — | address row editable / model row display-only; origin label renamed; page copy | shipped tests |

## ② Pre-existing suites (targeted runs, before/after)

| Run | Command | Result |
|---|---|---|
| admin-console **full suite, after** | `uv run pytest -q` (244 s) | **25 failed, 105 errors, 1490 passed, 31 skipped** |
| admin-console **full suite, before** (base `36df47b8`, scratch worktree) | `uv run pytest -q` (170 s) | **25 failed, 105 errors, 1481 passed, 31 skipped** |
| — failure-set diff | `comm` on the sorted `FAILED`/`ERROR` ids | **130 entries on both sides, zero differences**; the +9 passes are this slice's new tests |
| miroflow-agent targeted (touched modules + new files) | `uv run pytest tests/canonical_v2/test_knowledge_read_universal_web_contract.py test_fast_boot.py test_serving_pack_loader.py test_knowledge_serving_isolated.py test_index_projection_embedded_content.py test_manual_recall_points.py test_embedding_*.py -q` | **1 failed, 376 passed** |
| admin-console targeted (touched files) | `uv run pytest tests/test_managed_config_catalogue.py test_canonical_v2_model_discovery_api.py test_canonical_v2_runtime_sources.py test_canonical_v2_connection_tests.py test_admin_config_single_channel.py test_admin_model_roles_page.py test_admin_config_page_shell.py test_managed_runtime_bootstrap.py test_managed_settings_store.py test_canonical_v2_admin_config_api.py tests/test_embedding_effective_endpoint.py -q` | **168 passed** |

**Named pre-existing red** (verified on the base commit `36df47b8` in a scratch
worktree `/var/tmp/embedlane-base`, same file selection):

- `tests/canonical_v2/test_manual_recall_points.py::test_release_bound_vector_validator_exempts_manual_traces`
  — fails identically on the base (`1 failed, 7 passed` there too). Not caused by
  this change; the negative control expects an `IsolatedKnowledgeReadIntegrityError`
  for a tampered manual vector trace and nothing raises.

The admin-console suite's 25 failures / 105 errors are all pre-existing and
environmental (Postgres-backed APIs and seeds/jobs routes on this box); the set is
identical to the base, which is the comparison that matters here.

`tests/canonical_v2/test_knowledge_build_isolated.py` (the heavy build suite that
also covers the bundle loaders) was **started but not completed within its
1800 s budget** — see the residual gap below.

## ③ Scenario probe — real serving instance, real `/api/chat/stream`

Setup: one scratch serving instance per phase on port **18285** (never 18188),
command `.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/serve-18285-command.sh`
— the live run16 command with only the port, `PYTHONPATH`, scratch state dirs
(`/var/tmp/embedlane-285/`) and `CANONICAL_V2_EMBEDDING_BASE_URL` changed. Same
serving pack (`serving-pack-run16-readerbound`), index root (`index-v3-v2`),
release `candidate-v2-20260916-r1`, and the same committed
`serving-bundle-run16.json` (sha256 `671c838a…`, identical to the live tree's
copy). Boot wall clock ≈ 350 s (phase 1), ≈ 615 s (phase 2, cold receipt reuse).

Raw evidence: `probe/phase-1-blackhole-stream.txt` (verbatim SSE),
`probe/phase-1-blackhole-summary.json`, `probe/phase-1-blackhole-sync.json`,
`probe/phase-2-real-stream.txt`, `probe/phase-2-real-summary.json`,
`/var/tmp/embedlane-285/turn-debug/*.json`, `/var/tmp/embedlane-285/access-logs.sqlite3`.

### Phase 1 — `CANONICAL_V2_EMBEDDING_BASE_URL=http://10.255.255.1:9/v1` (black hole)

`POST /api/chat/stream {"query":"深圳有哪些芯片设计企业"}` → HTTP 200, wall **39.8 s**:

```
event: plan_done
data: {"lanes":["exact","structured","lexical","vector","web"],"domains":["company"], ...}
event: progress
data: {"detail":"✓ 语义检索：0 个结果","lane":"vector","count":0}
event: retrieval_done
data: {"lanes":[{"lane":"exact","status":"succeeded","candidates":0},
                {"lane":"structured","status":"succeeded","candidates":0},
                {"lane":"lexical","status":"succeeded","candidates":128},
                {"lane":"vector","status":"unavailable","candidates":0},
                {"lane":"web","status":"succeeded","candidates":18},
                {"lane":"supplemental","status":"succeeded","candidates":6}], ...}
event: answer
data: {"query":"深圳有哪些芯片设计企业","query_type":"canonical_v2:A:answer","answer_text":"（以下为基于本地数据的简要信息）…"}
event: done
```

- SSE event names: `answer, done, plan_done, progress, retrieval_done, stage` — **no `event: error` frame**, exactly one `done`.
- The **vector lane is `unavailable`** while every other lane served, and the user got a normal answer.
- Second turn through the synchronous `/api/chat` (same phase): 36.2 s, answer 2,894 chars.
- Access log (`turns` table): both turns `status='completed'`, `error_detail=NULL`, `latency_ms` 39,736 / 36,190 — the normal status is kept, **no red bubble**.
- Turn-debug dumps: `evidence_items.by_lane` = `{lexical: 111, web: 17}` — no vector evidence, as expected for a degraded lane.
- The black-hole address being the *effective* one is itself the end-to-end proof that `CANONICAL_V2_EMBEDDING_BASE_URL` is the resolution point: with the bundle's real address still recorded, the lane failed because the environment value won.

### Phase 2 — no override (bundle-recorded address, real endpoint)

`POST /api/chat/stream` with the same query → HTTP 200, wall **29.8 s**:

```
event: retrieval_done
data: {"lanes":[..., {"lane":"vector","status":"succeeded","candidates":128}, ...]}
```

- `error_events: []`, `done` once, answer 2,779 chars.
- Turn-debug dump: `evidence_items.by_lane` = `{lexical: 110, vector: 36, web: 18}`; `lane_timings` includes `["vector", 0.873]` — the lane made a real embedding call through the resolved address and served evidence.
- Access log: `status='completed'`, `error_detail=NULL`, `latency_ms` 29,791.

Both phases together exercise both precedence branches live: env set (phase 1) and
env unset → bundle (phase 2).

### Scratch-instance hygiene

- Port **18285 only**; `18188` was never bound — the live listener
  (`pid 519941`) was observed untouched before, between and after the phases.
- The scratch servers were stopped (`pkill`, then SIGKILL after a 8 s grace) and
  port 18285 was verified released.
- No bundle, pack, index or database file was modified: the served bundle is the
  committed file (byte-identical to the live tree's copy), and the pack/index were
  mounted read-only from the live paths.

## Residual gaps and honest limits

- The SSE `retrieval_done` row carries `status` but not `failure_kind`; the
  `failure_kind` mapping (`timeout` / `connection_failure`) is asserted on the
  real engine in cluster B, and the transport classification in cluster A. The
  probe therefore proves *status* end-to-end and *kind* at the engine seam.
- The breaker's live effect (a third turn inside the window issuing no provider
  call) was not driven end-to-end; it is covered by cluster C including a
  real-HTTP request count of zero while open. Reason: each probe turn costs an
  LLM answer call and the observable difference is only `failure_kind` plus a
  ~8 s lane wait, neither visible in the SSE frame.
- Boot wall clock is ~350 s here (the parent brief said ≈291 s); treated as
  machine load, not a behavior change — nothing in this slice touches boot.
- `tests/canonical_v2/test_knowledge_build_isolated.py` did not finish inside its
  1800 s budget (it was still at ~55 % after ~18 min; the suite builds release
  fixtures). Its coverage of the changed code is the bundle loaders, which the
  new cluster D tests exercise directly against the verbatim frozen document, so
  the confidence impact is bounded but real: **the base-vs-after comparison for
  that file is missing.** Next best command (≈30–40 min, both sides):
  `uv run pytest tests/canonical_v2/test_knowledge_build_isolated.py -q` in this
  worktree and in a `36df47b8` worktree, then `comm` the failure sets.
