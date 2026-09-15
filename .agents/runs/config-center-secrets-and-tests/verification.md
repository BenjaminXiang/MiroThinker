# Verification — config-center-secrets-and-tests (P13)

Baseline: `codex/canonical-v2-s12a-ready` @ `2fe4c16c`. Worktree `.worktrees/config-center-secrets`
(branch `feat/config-center-secrets`). Commits: `29d89887` (contract + OpenSpec), `79bf9072`
(implementation + tests + E2E). Live 18188 never started, restarted or reconfigured.

## ① New tests written in this slice — 38 cases, all green

| File | Cases | What each cluster locks | Fixture source |
|---|---|---|---|
| `apps/admin-console/tests/test_managed_secrets_store.py` | 11 | mask ≤3 head + 4 tail and ≤12 chars; missing/corrupt file = not configured; **0600 + atomic replace + no temp residue**; overwrite/clear; **audit carries tails only, never plaintext**; whitelist rejection; `env > managed file > legacy key file`; `apply_to_environ` never overrides an existing env var; `describe()` is value-free | locally generated fake keys |
| `apps/admin-console/tests/test_managed_runtime_bootstrap.py` | 5 | file-owned values projected; **env already set ⇒ skipped**; **defaults never projected** (including a page save that rewrites the whole document); receipt carries no values; corrupt file is fail-open; "no key in the process environment before startup" (no hot read) | fakes + tmp dirs |
| `apps/admin-console/tests/test_canonical_v2_connection_tests.py` | 8 | one minimal request per connection (5 connections); success reports status + latency only; 401 reported as reachable-but-rejected **without the body**; transport error/timeout are results, not exceptions; missing required key makes **no call**; unsafe endpoints rejected; rate limiter (interval + per-minute + per-connection/per-client scopes) | injected fake transport |
| `apps/admin-console/tests/test_canonical_v2_admin_secrets_api.py` | 11 | **response never returns plaintext**; audit + health-check value-free; **restart required / not hot-read**; clear + overwrite; whitelist/blank-body 422; **test-before-save uses the unsaved value, calls exactly once, persists nothing**; fallback to the stored value; **429 + Retry-After and no second call**; connection-name/endpoint validation; `serving.*` editable fields + read-only 422; `/admin` renders the credentials card | `TestClient` + monkeypatched transport/limiter |

## ② Pre-existing suites (regression)

`cd apps/admin-console && uv run pytest -q` in two trees:

| Run | Result | Evidence file |
|---|---|---|
| before (detached worktree at `2fe4c16c`) | **96 failed / 1192 passed / 30 skipped / 122 errors** (184 s) | `.agents/runs/.../full-suite-before.txt` |
| after, run 1 (this branch) | **97 failed / 1229 passed / 30 skipped / 122 errors** (235 s) | `.agents/runs/.../full-suite-after.txt` |
| after, run 2 (this branch, flake check) | **96 failed / 1230 passed / 30 skipped / 122 errors** (199 s) | `.agents/runs/.../full-suite-after-run2.txt` |

**Verdict: zero new failures.** Run 2's `FAILED`/`ERROR` set is **byte-identical** to the baseline set
(`diff` of the sorted lists: no output), and the pass count rose by exactly **+38** — the 38 cases added by
this slice. Run 1 showed one extra failure,
`tests/test_canonical_v2_real_preview_ui.py::test_s12g_task8_real_terminal_evidence_follows_citations[hidden-…]`
(assertion `report["checks"]["streaming_controls_actionable"] is True` in a Playwright/SSE preview test;
the captured stderr for that run shows Milvus gRPC `ENHANCE_YOUR_CALM / too_many_pings` noise). That case
passes in isolation in both trees (5/5 each), passes when the whole preview-UI file runs alone in this
branch (220 passed) and passes when that file runs together with all four new test files (258 passed), and
it does not fail in run 2. Classification: pre-existing flakiness under full-suite load (repo gap G31
"三套件环境失败 / replay 抖动"), not attributable to this slice — this slice touches no preview/UI code.
Within the touched areas nothing regressed: `test_managed_settings_store.py`,
`test_canonical_v2_admin_config_api.py`, `test_canonical_v2_admin_status_repair.py` are green (45 cases),
and `ruff check` / `ruff format --check` pass on every file this slice added or modified.

## ③ Scratch E2E (real HTTP, port 18297, mock transport 18298)

Transcript: `.agents/runs/config-center-secrets-and-tests/e2e-scratch-18297.md` (script is replayable).
Chain proven end to end: set fake key → **file 0600, mask `sk-…beef`, origin `managed-file`** → test before
saving (mock answered HTTP 200 in 1 ms, **mock logged exactly 1 call with the unsaved key**) → immediate retry
**429 with `retry_after_seconds`** (no second call) → 401 path reported as "reachable, credential rejected"
→ **one real-endpoint call** (embedding `100.64.0.27:18005/v1` → HTTP 401, 4 ms, no credential configured —
the endpoint requires one) → clear → set again → **restart**: `adopted_to_process_env false → true`
(startup read, not hot) → `serving.web_topical_floor=false` written from the page and effective after
restart as `CANONICAL_V2_WEB_TOPICAL_FLOOR=0`, while `CANONICAL_V2_RERANK_TIMEOUT_SECONDS=9.0` (env) beat
the file's `2.5` (env wins) → `serving.full_verify` rejected with 422 + reason.

**Plaintext leakage sweep** (fake sentinel `sk-fake-e2e-0000-1111-beef`): 0 hits in the server log, 0 in the
audit file, 0 in `/admin` HTML, 0 in `/secrets`, 0 in `/config`; 2 hits inside the managed file itself
(the carrier, mode 0600).

## ④ Real-endpoint calls (honest count)

| Endpoint | Calls | Result |
|---|---|---|
| `api.bochaai.com/v1/web-search` (pinned host, cannot be redirected) | **2** (implementation-time smoke + first E2E version, both with a fake key) | HTTP 401 — reachable, credential rejected; pay-per-call providers reject before billing |
| `100.64.0.27:18005/v1/embeddings` (LAN model box) | **1** | HTTP 401 — endpoint reachable in 4 ms, requires a credential |
| Serper / rerank | **0** (route exercised against the local mock instead) | — |

Automated tests make **zero** real calls (transport injected). The final E2E run performs exactly one real
call (embedding).

## ⑤ Open items / honest gaps

1. **Deployment to the live service is not done** — the new routes/page/startup hook take effect on 18188
   only after a restart, which needs the replay gate and the user's go-ahead. Not performed here, and the
   live service was never touched. This is the remaining step of the P13 exit criterion
   ("设置 → 测试 → 服务读取生效" must be observable on the deployed service).
2. **`serving_pack_loader` bootstrap call** is exercised by unit-level import and by the V2 shell startup
   path; the live serving runner (in another worktree, s12e script) was not started by design. If the
   operator wants the serving process to pick up the managed files, the call is already in
   `open_serving_pack_authority()` and takes effect on the next restart.
3. **Startup-adoption log line is not visible under uvicorn's default logging config** (no root handler, so
   an INFO from `backend.main` is dropped). The authoritative observable is the API's
   `applied_to_process_env` flag (names only), which the E2E uses. If operators want it in journald, the
   deployment should configure logging; not changed here.
4. **Legacy key files still resolve** (`.bocha_api_key`, `.serper_api_key`, `.sglang_api_key`): precedence is
   `env > managed file > legacy file`, and the page shows the winning origin. Retiring the legacy
   consumers is a separate slice (it changes the collection scripts' inputs).
5. **Real-endpoint call budget** — see §④; 3 real calls in total, all with fake credentials, none billable.
   Automated tests call nothing real, and the connection-test button is rate-limited to 6/minute per
   connection and per client.
