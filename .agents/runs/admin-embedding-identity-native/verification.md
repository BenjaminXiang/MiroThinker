# Verification: admin-embedding-identity-native

Slice: the `/admin` embedding card validates the **DashScope-native** route (and
the OpenAI-compatible one) — branch `v2/admin-identity-native`, worktree
`.worktrees/v2-admin-identity-native`, off `ac44b404` (the switch line's head at
the time of writing). Contract: `verification-contract.md` (this directory),
written before the production edits.

Nothing outside this worktree was touched: the running build
(`.worktrees/embedding-switch-line`), the live service on 18188, the current
pack/index and the live state dirs are untouched, and the credential file was
read into the process environment only (never echoed, never logged).

## Commits

| commit | files |
|---|---|
| `39878a21` feat(admin): the embedding identity check speaks the native shape too | `apps/admin-console/backend/services/canonical_v2_embedding_identity.py`, `apps/admin-console/tests/test_embedding_identity_probe.py` |
| `825ba5ce` fix(admin): the embedding card's test reaches the native route | `apps/admin-console/backend/services/canonical_v2_connection_tests.py`, `apps/admin-console/tests/test_canonical_v2_connection_tests.py` |

## The rule (how the provider is selected)

**Asked of the address, per address, and held for the rest of the check.** The
probe speaks one shape per address: the compatible shape first, and the native
(DashScope) shape only when that address answers the compatible route with
**404/405** (absent route). Every other answer — 401, 403, 500, a timeout, a
dimension change — is that route's own answer, is reported as such, and is never
retried on the other route. The shape used for the *endpoint under test* travels
with the verdict as `checks.provider` + `checks.provider_evidence`.

Why not declared here (a config field, or the bundle's `provider`) or inferred
from the path: this console process holds **no embedding bundle** — the frozen
authority the serving process loads — so any declaration on this side would be a
second authority, and one that disagreed with the address would silently validate
the *other* route. Asking costs nothing on an endpoint that answers (the answer
is the call the card already made) and one bounded 404 on an endpoint that does
not.

Roles are preserved exactly (and passed into the native client, which is the
client that has a role dimension on the wire):

- index arm → `document` → the route's **absent** `text_type`;
- reference arm → `query` → `text_type="query"`.

## ① New tests written this slice (12)

`apps/admin-console/tests/test_embedding_identity_probe.py` (+9), fixtures: a
loopback endpoint whose *routes* are declared (so the shape a call used is
observable), plus the file's existing constructed mini pack
(`lookup.sqlite3` + `vector_matrix.npz` written by the repository's own writer).

| test | locks |
|---|---|
| `test_the_native_path_literal_matches_the_merged_client` | the console's native path == `dashscope_embeddings._TEXT_EMBEDDINGS_PATH` (drift would read as 未校验 on a healthy endpoint) |
| `test_the_index_arm_validates_a_native_only_endpoint` | the shipped route: compatible 404 → native 200 → index arm passes, cos ≈ 1.0, `provider=dashscope-native`, `role=document`, no `text_type` on the wire, credential sent |
| `test_a_compatible_endpoint_stays_one_call_per_address` | the shape in service today: one call, `provider=openai-compatible` |
| `test_a_native_endpoint_in_another_space_still_fails` | a native route is no easier to pass: orthogonal vectors → `passed=False`, `不要切换` |
| `test_a_native_route_that_rejects_the_credential_is_unverified` | route/credential problem → `passed=None`, 未校验, route named, no exception |
| `test_a_rejected_compatible_route_never_falls_through_to_the_native_one` | only an *absent* route selects native; a 401 stays one call |
| `test_the_reference_arm_probes_the_query_side_of_a_native_route` | both reference calls carry `text_type="query"` on a native route; `role=query` |

`apps/admin-console/tests/test_canonical_v2_connection_tests.py` (+3), fixture: a
recording transport answering a declared status per call.

| test | locks |
|---|---|
| `test_the_embedding_test_asks_the_native_route_when_the_compatible_one_is_absent` | second call goes to the native path with the same model + credential; `ok=True/http 200`; both statuses in the detail |
| `test_a_rejected_credential_never_moves_to_the_native_route` | 401 stays one call (preservation pin — green before and after) |
| `test_only_the_embedding_connection_has_a_second_route` | rerank 404 stays one call (preservation pin) |

RED before the fix: 8 of the 12 failed (A1–A6 + B1 above); A7 failed on the
missing constant; the two preservation pins passed before and after. Full RED
output: `8 failed, 43 passed` (the pre-fix run of the two files), recorded in the
contract.

## ② Regression suites

- `uv run pytest tests/test_embedding_identity_probe.py tests/test_canonical_v2_connection_tests.py -q`
  41 passed before the slice → **51 passed** after (26 → 35 identity, 15 → 16
  connection).
- `ruff@0.8.0 check` + `ruff@0.8.0 format` on the four touched files: clean
  (repo toolchain, scoped to the touched files — the whole-repo `just lint` was
  not run so nothing outside this slice could be rewritten).
- The full admin-console suite is recorded below with its pre-existing,
  DB-driven reds named.

## ③ Live evidence (2026-09-22, `maas.qianwenaiapi.com`)

Driven through the committed code, credential from
`/var/tmp/mirothinker-qianwen-api-key` (never printed). 5 live calls in total,
each a one-word embedding; no pack, index or state dir was read.

```
recorded (reference) address: http://100.64.0.27:18005/v1

① verify_embedding_identity(candidate address, no pack configured)
   arm None, passed None, cosine None
   detail 未校验：记录端点不可用（端点返回 HTTP 401）且 未配置服务包目录
          （CANONICAL_V2_SERVING_PACK），无法做索引比对
   wall clock 0.01s — the reference call to the recorded address was refused, and
   the index arm then refused before dialling the candidate address, which is why
   no provider is named in this report (the probe never asked it).

② the same transport, one call per role, against https://maas.qianwen.../api/v1
   document dims 1024 · query dims 1024 · document vs query cosine 0.90083
   provider dashscope-native · evidence "compatible route absent (HTTP 404);
   spoke the native route"

③ canonical_v2_connection_tests.test_connection (live, the card's first step)
   ok true · http_status 200 · latency 361 ms
   detail "HTTP 200（OpenAI 兼容路线 HTTP 404，改试 DashScope 原生路线）"
```

Readings:

- ② is the role claim on the wire: the native client is built with the arm's role,
  the route accepts `text_type="query"` **without** an instruct (200, 1024), and
  the two roles differ by **0.90083** — far below both 0.99 floors, so a guessed
  role would fail a healthy endpoint rather than hide. The switch's own probe
  measured 0.912177 for the same pair *with* the frozen `query_instruct`; this
  probe deliberately sends the role selector only, because the console holds no
  bundle and therefore no frozen instruct — the arm's claim is about the retrieval
  *side*, and the measurement shows the side is what the verdict turns on.
- ① is the honest end state on this host: until a pack built with the candidate
  model is mounted, the index arm cannot answer (and the live pack is the
  4096-dim one, which the reference arm's dimension gate refuses long before the
  floors do).
- ③ is the second gap of the report, closed: without it the card's transport check
  returned `ok=False, http_status=404` and the identity check was skipped
  outright (`端点未通过连通性检查`).

## Card end-to-end is still blocked by two facts outside this slice (measured)

The identity verdict cannot yet be produced through the page, and neither cause
is the wire shape:

1. **The model id.** `resolve_embedding` pins `Qwen/Qwen3-Embedding-8B`
   (`canonical_v2_runtime_sources.py`), which the candidate gateway refuses on
   **both** routes — native: `404 {"code":"InvalidParameter","message":"Model not
   exist."}`; compatible: `404 {"error": …}` — while the candidate model
   `qwen3.7-text-embedding-flash` answers `200` with `data[].{embedding,index,object}`
   on the compatible route and 200/1024 dims on the native one. With the pinned id
   the card's own first step reads (live, ④):

   ```
   ok false · http_status 404 · 277 ms
   detail HTTP 404：端点可达，但路径或方法不被接受（OpenAI 兼容路线 HTTP 404，
          改试 DashScope 原生路线）
   ```

   — accurate and both attempts named, but "路径或方法不被接受" is the generic 404
   wording while the real cause is the model id: fixing the row is what turns the
   card green, not another code path here.
2. **The credential slot.** The managed secrets page writes `embedding.api_key`
   into `SGLANG_API_KEY`, while the candidate bundle reads
   `CANONICAL_V2_EMBEDDING_API_KEY` (the switch's own open item, §7 of
   `.agents/runs/embedding-model-switch-v2/verification.md`).

Both are the switch's cutover items; this slice deliberately does not guess a
model name or a key slot.

## Not verified

- A **full live identity verdict** (index arm pass) on the candidate endpoint: no
  pack built with the candidate model exists yet; the local mock covers the arm,
  and the live pack is deliberately untouched.
- The **page rendering** of the new fields: `admin.js` was not changed (its
  `identityText` shows arm + cosine + detail as before); `checks.provider` /
  `provider_evidence` / `role` are in the JSON reply, asserted by the API-level
  test, and are not rendered on the card.
- The **native route's 4xx-vs-absent distinction**: the merged client normalizes
  every non-answer (4xx/5xx included) into `ConnectionError`, so a native *401*
  is reported as "原生路线没有可用回答（ConnectionError）" with `provider` named,
  rather than with a status code. No verdict is affected (未校验 either way); the
  connection test's own fallback keeps the status, which is why ③ shows 404/200.
