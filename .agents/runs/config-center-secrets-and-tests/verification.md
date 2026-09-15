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

## ④a Follow-up verification — runtime-source alignment (2026-09-15)

**Trigger**: the user-approved five-connection acceptance (each connection called once
against the live endpoints) reported embedding `401` and rerank `401` while embedding is
demonstrably used by the running serving line and rerank is not enabled there at all.
Root cause: three of the five connection specs resolved a page-local guess instead of the
runtime chain (`EMBEDDING_API_KEY` — read by nothing; an invented rerank endpoint copied
from the task text; the collection-side `llm_base_url` — unset).

**Runtime truth established (file:line)**

| connection | runtime source | evidence |
|---|---|---|
| embedding endpoint | frozen release-bundle authority `http://100.64.0.27:18005/v1` + `Qwen/Qwen3-Embedding-8B` | `knowledge_build_isolated.py:6720-6728` (bundle table), used at `6570-6583` |
| embedding credential | `load_local_api_key()`: `API_KEY` → `OPENAI_API_KEY` → `SGLANG_API_KEY` → `.sglang_api_key` | `providers/local_api_key.py:8-31`; call site `knowledge_build_isolated.py:6570`; HTTP shape `company/vectorizer.py:22,40-53` (`{base}/embeddings`, `Authorization: Bearer`) |
| rerank enablement | enabled **only** with `CANONICAL_V2_RERANK_BASE_URL`; `configured_reranker()` returns `None` otherwise; endpoint `{base}/v1/rerank`; key `CANONICAL_V2_RERANK_API_KEY` / `*_API_KEY_FILE` | `canonical_v2/rerank_client.py:33-38,132-150,224-236` |
| LLM endpoint/model/credential | active chat profile: `CHAT_LLM_PROFILE` (live: `deepseekv4flash`) → `resolve_professor_llm_settings(..., apply_endpoint_env_overrides=False)` → `https://api.deepseek.com` / `deepseek-v4-flash` / `DEEPSEEK_API_KEY` (+ `.deepseek_api_key`) | `knowledge_serving_isolated.py:2087-2096` (also 5972, 6070), `llm_judgments.py:304`; `professor/llm_profiles.py:14-20,55-66,130-136,244-288` |
| web search | pinned provider host + env→repository key file | `providers/bocha_search.py:12-33,61`; the Serper provider follows the same pattern |

Grounding for the live process (read-only, names only): pid 1886109 env carries
`CHAT_LLM_PROFILE=deepseekv4flash` and **no** credential variables, so every credential
comes from the repository key files — which is exactly what the aligned resolution now
reports.

**Change**: new `apps/admin-console/backend/services/canonical_v2_runtime_sources.py`
(resolution + `RuntimeConnection` value-free public view), `test_connection(...,
disabled_reason=...)` short-circuit with `called` in the result, API wiring for
`/secrets` and `/connections/test`, credential metadata in
`managed_secrets.SECRET_SPECS`, page runtime pills/notes. Behaviour of the serving path
itself is untouched.

**Suite re-run after the follow-up** (`full-suite-after-followup.txt`): **96 failed / 1250 passed /
30 skipped / 122 errors** — the `FAILED`/`ERROR` set is **identical** to the baseline
(`diff` of the sorted lists: no output), and the pass count rose by **+58** = the 38 cases
from the first slice plus the 19 added here (the 20th difference is the preview-UI case that
flaked in run 1 and passed this time).

**New tests (this follow-up): 19** — `test_canonical_v2_runtime_sources.py` 13 (disabled
rerank reporting, frozen-bundle embedding endpoint + local credential, `EMBEDDING_API_KEY`
ignored, chat-profile LLM incl. profile switch, pinned hosts, env-over-file, pending vs
adopted, credential-free public view, anti-drift cross-check against the official
resolver), plus 6 added to the connection/API/store/bootstrap suites (no-call gate, chat
path `/chat/completions`, runtime state in `/secrets`, supplied-endpoint probe, precise
credential targets, profile-driven projection). Ambient credential variables are scrubbed
and recorded values redacted in the API recorder so no host key can enter a failure
message. Suite: 106 passed in the affected clusters.

**Acceptance re-run (real endpoints, scratch process on 18297, live env, 18188 untouched)**

| connection | verdict | latency | endpoint | credential origin |
|---|---|---|---|---|
| bocha | ✅ HTTP 200 | 287 ms | pinned `api.bochaai.com` | `legacy-file:.bocha_api_key` |
| serper | ✅ HTTP 200 | 1855 ms | pinned `google.serper.dev` | `legacy-file:.serper_api_key` |
| rerank | ➖ **未启用** (0 calls) | — | none configured | local-key fallback reported |
| embedding | ✅ HTTP 200 | 30 ms | `http://100.64.0.27:18005/v1` (bundle-frozen) | `legacy-file:.sglang_api_key` |
| llm | ✅ HTTP 200 | 234 ms | `https://api.deepseek.com` (profile `deepseekv4flash`) | `legacy-file:.deepseek_api_key` |

Real calls this round: 4 (one per enabled connection); rerank 0. Transcript:
`e2e-real-connections.md`. Leakage sweep with exact-value matching over all four real
credentials: **0 hits** in `/secrets`, `/config`, `/admin` and the server log; the only
credential-shaped string in `/secrets` is the intended 8-character mask (`k8#…0204`).

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
