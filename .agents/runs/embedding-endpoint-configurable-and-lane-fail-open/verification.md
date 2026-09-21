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

---

# Round 2 (2026-09-21): the wait-cap row, the identity check, and the build-suite comparison

Commits: `c9340cfb` (#2), `ce3c0b3f` (#3), plus this evidence commit. Same
worktree/branch as above; the live service on 18188 was not touched (up 17h34m
at the start of this round).

## ⑤ The `test_knowledge_build_isolated.py` comparison (the round-1 gap)

The file has 143 tests, two of which are extremely slow
(`test_unrecoverable_or_quarantined_input_records_typed_gap_without_placeholder_fact`
takes **543.74 s / 9 min** on its own — measured in isolation, and it *passes*).
That is why the earlier 25-minute budgets never finished the file: it was not
stuck, it was slow.

Two runs, one per side (`-v --tb=no -rf`, scratch worktree
`/var/tmp/embedlane-base2` at `36df47b8` for "before"), interrupted at the same
point after ~14.5 minutes so both sides cover exactly the same 128 tests:

| Side | Result | Failure ids |
|---|---|---|
| before (base `36df47b8`) | **14 failed, 114 passed in 878.12 s** | 14 (see below) |
| after (`fix/embedding-lane-f1f2`) | **14 failed, 114 passed in 873.65 s** | 14 — **identical set** (`diff` empty) |

The 14 pre-existing failures are the Postgres/boundary fixtures of this box:
`test_real_boundary_rejects_nonfresh_database_before_source_read[…]` (9
parameters), `test_real_boundary_rejects_live_schema_fingerprint_drift_before_row_probe`,
`test_four_domain_mapper_normalizes_restored_source_shapes`,
`test_customer_company_patent_relationship_unions_direct_applicant_scan`,
`test_complete_build_uses_verified_copies_landing_authority_projections_registry_index_and_verify`.
Both sides fail them identically, including the two slow ones.

Tail (tests 129–143, the ones the interrupted runs never reached) is run as an
explicit selection on both sides; results appended below when the runs finish.

## ⑥ #2 — the wait cap is a managed row

`serving.vector_lane_timeout_seconds` — default 8.0, bounds 0.1–120, env
`CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS`, one row in `FIELD_CATALOG`
(order 22, group `serving`), projected at startup by `managed_runtime` and read
in exactly one place (`knowledge_read._vector_lane_outer_wait_seconds`, whose
default constant is pinned to the schema default by a test).

New tests: `apps/admin-console/tests/test_vector_lane_timeout_knob.py` — **12
passed** (catalogue row + bounds + default; the single-reader invariant; save →
projection → reader round-trip; default-equal value stays a no-op; service-unit
env wins; 0 / negative / 121 / 1000 refused with the path in the message; the
page payload row; a save through the PATCH route).

Regression: the whole managed-config surface re-run green (catalogue, settings
store, runtime bootstrap, single channel, page shell, model roles, admin config
API, admin secrets API) — **138 passed**, and the full admin suite comparison in
§⑦.

## ⑦ #3 — the identity check, calibrated on real data

Raw results: `probe/identity-calibration.json` (produced by
`probe_embedding_identity_calibration.py`, which drives the production
`verify_embedding_identity` against three endpoints). Cosines:

| Endpoint under test | Arm | Measured cosine | Threshold | Verdict |
|---|---|---|---|---|
| real `100.64.0.27:18005/v1` vs its own index | `index` | **0.999933** (798 sampled rows, sample max = the target) | 0.99 | pass |
| local gateway forwarding to the real endpoint, reference = recorded address | `reference` | **1.000000** | 0.999 | pass |
| dim-4096 token-hash space, reference = recorded address | `reference` | **-0.007435** | 0.999 | fail |
| dim-4096 token-hash space vs the index | `index` | **0.004543** (sample max 0.038052) | 0.99 | fail |

Noise on the accept side: 15/15 pairs of repeated live calls measured exactly
1.0; one cold-start pair measured 0.9999676 (the first request after boot). The
thresholds sit ~1000× above every rejected value and below every accepted one.

**What the wrong-space endpoint actually was.** No second embedding *model* is
reachable from this box — `GET /v1/models` on 18005 lists only
`Qwen/Qwen3-Embedding-8B`, on 18006 only `qwen3-reranker-8b` (read with the
repository key, never printed). So the wrong-space stand-in is a local
OpenAI-compatible server that answers 200 with 4096-element vectors from the
repository's own token-hash embedding algorithm
(`index_projection_isolated.RecordedEmbeddingAdapter`,
`canonical-v2-token-hash-l2-v1`). It is a *different vector source with the right
dimension and protocol* — exactly the shape of the failure the check exists to
catch — but it is not a real second model, so the calibration cannot rule out
that some *other* real model lands closer than 0.99 to this index's vectors.
Given the measured separation (≈0.99 vs ≈0.005) that would need a model whose
vectors are nearly collinear with Qwen3-8B's for the probe document; the check
re-tests against the record endpoint first when one exists, which is the arm
that would catch that case.

**Cost per click** (measured): index arm 1.37 s wall, peak RSS 174 MB (the row
reader seeks inside `vector_matrix.npz`, so the 1.68 GB matrix is never
materialized); reference arm 64 ms. Both arms are read-only and touch no bundle,
pack or index file.

**What the operator sees.** The page sends `identity_check: true` for the
embedding connection and renders the verdict as part of the connection-test line:
`· 向量身份通过（索引比对，cos=0.999933）与索引同源：…`, or, on a failure,
`· 向量身份不通过（对照端点，cos=-0.007435）该端点与索引记录的端点不在同一嵌入空间…：
不要切换到这个端点，换来的排序会整体失真`. A probe that cannot run renders
`· 向量身份未校验（未跑）未校验：未配置服务包目录（CANONICAL_V2_SERVING_PACK）…` and
never a pass.

New tests: `apps/admin-console/tests/test_embedding_identity_probe.py` — **17
passed** (matrix row reader pinned against `np.load`; arm reference pass/fail/
dimension-change; arm index pass/fail/dimension-change; no-assets → not verified;
unreachable reference → index arm; a raising embedder never escapes; the real
HTTP embedder against a loopback endpoint; the route: verdict present, absent
without the flag, absent for other connections, skipped after a failed transport
check; the page asks for the check and renders the verdict).

## ⑧ Regression, round 2

| Run | Result |
|---|---|
| admin-console **full suite, after** (round 2) | **25 failed, 105 errors, 1519 passed, 31 skipped** (222 s) |
| admin-console **full suite, before** (base `36df47b8`) | 25 failed, 105 errors, 1481 passed, 31 skipped |
| failure-id diff | **130 entries on both sides, zero differences**; +38 passes = round-1 and round-2 tests |
| managed-config surface (11 files) | 138 passed |
| new files (knob + identity) | 29 passed |
