# embedding-model-switch (v2), slice 1 — endpoint adapter + the candidate's identities

Branch: `v2/embedding-model-switch` (base tag `delivery-v1` = `36df47b8`).
Plan of record: `docs/plans/2026-09-21-embedding-model-switch-plan.md` §3 steps 1–2.

Scope of this slice, stated as a contract:

- **Goal** — prepare, without selecting, everything the switch needs on the
  endpoint side: a provider implementation for the gateway's DashScope-native
  wire shape, and the candidate's frozen embedding identity on **both** of the
  gateway's routes (the compatible one turned out to need no new code).
- **Done when** — shape conversion works where a client is needed, failures are
  classified the way the serving layer already fails open, the declared dimension
  is guarded, every candidate `(sha256, dimension)` pair is accepted as an
  authority while a mismatched pair is refused, and the candidate can never read
  the live endpoint's credential slot. Nothing on the live 4096 path changes.
- **Out of scope** — the rebuild, the recall non-regression gate, cutover,
  credentials provisioning, and anything that selects a new bundle.

## 1. OpenAI-compatibility probe, and the authenticated measurements

Unauthenticated `POST https://maas.qianwenaiapi.com<path>`, probed 2026-09-21T13:37Z:

| path | status | body |
|---|---|---|
| `/v1/embeddings` | **404** (0.29 s) | empty — no such route |
| `/compatible-mode/v1/embeddings` | **401** (0.18 s) | `{"error":{"message":"No API-key provided.", ...}}` |
| `/api/v1/services/embeddings/text-embedding/text-embedding` | **401** (0.18 s) | `{"code":"InvalidApiKey", ...}` |
| `/compatible-mode/v1/models` (GET) | **401** | OpenAI-shaped error body |

404 vs 401 separates "no route" from "route needs auth", so an OpenAI-compatible
route exists. Authenticated calls (made by the orchestrator, 2026-09-21; treated
as fact here) then settled what the probe could not:

| measurement | result |
|---|---|
| `POST /compatible-mode/v1/embeddings` (`{"model":"qwen3.7-text-embedding-flash","input":[…]}`) | **200**, **1024 dims**, 0.29 s, fully OpenAI-shaped body (`data[]` rows carry `embedding`/`index`/`object`, plus `usage` and `model`) |
| `GET /compatible-mode/v1/models` | 200, 261 models, includes `qwen3.7-text-embedding-flash` |
| `POST /api/v1/services/embeddings/text-embedding/text-embedding` (native) | 200, 1024 dims |
| same text, compatible route vs native route | cosines **0.839 / 0.920 / 0.808** ⇒ the two routes are **not** the same pipeline |
| same route, same text, twice | cosine **0.99914** (not 1.0) ⇒ this endpoint is slightly **stochastic** (the live 8B endpoint measured 1.000000, 15/15) |
| `dimensions` param on the compatible route | 1024 → 200, 512 → 200, **4096 → HTTP 400** |

Consequence: the switch **can ship with no new client** — the compatible route is
byte-compatible with `company/vectorizer.EmbeddingClient` — so a second candidate
bundle variant freezes that route as an authority of its own (§3), and the native
adapter is kept as the fallback. No live call was made from this worktree:
`/var/tmp/mirothinker-qianwen-api-key` does not exist on this host (`ABSENT`), and
no key was created, read, or printed.

## 2. What was built

`apps/miroflow-agent/src/data_agents/providers/dashscope_embeddings.py`
(`DashScopeTextEmbeddingClient`)

- request `{"model": ..., "input": {"texts": [...]}}` to
  `{base_url}/services/embeddings/text-embedding/text-embedding`;
- answer read from `output.embeddings[].{text_index, embedding}`, rows placed back
  by `text_index`; a set that is not exactly `0..n-1` (or a wrong row count, or an
  empty vector) raises `ValueError` — an unusable *answer*, not a transport fault;
- `dimension` is deliberately **not** sent (the candidate model answers 1024 and
  rejects 4096 with HTTP 400, measured in the plan): the declared dimension is
  enforced on the response instead;
- transport failures normalized as in `company/vectorizer.py` (F1's contract):
  `httpx.TimeoutException → TimeoutError`; `httpx.HTTPError`/`OSError` (any non-2xx
  status, refused connection, DNS) → `ConnectionError`; non-JSON body →
  `ConnectionError`. `trust_env=False`, so no ambient proxy behaviour.

`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`

- `_BatchingEmbeddingAdapter` — the existing batching/caching/thread-pool/vector
  validation moves to a shared base; a provider subclass supplies only
  `_resolve_api_key()` and `_provider_client(api_key)`. The live
  `_OpenAICompatibleEmbeddingAdapter` becomes such a subclass with byte-identical
  behaviour (same messages, same batching, same credential slot).
- `_DashScopeNativeEmbeddingAdapter` — the candidate provider on the gateway's
  native route. Its credential slot is `CANONICAL_V2_EMBEDDING_API_KEY`
  (`_load_gateway_embedding_api_key`), **not** `load_local_api_key()`: the local
  slot holds the self-hosted endpoint's key and must never travel to a
  third-party host. A bundle that points at the gateway therefore cannot be
  handed the local key — by construction, not by convention.
- `_GatewayOpenAICompatibleEmbeddingAdapter` — the compatible-route variant of the
  same rule: the live OpenAI client and wire shape, but the gateway's credential
  slot only. It exists so the zero-code route still cannot be loaded through the
  live endpoint's key.
- `load_content_addressed_embedding_adapter` dispatches on the bundle's `provider`
  field (`dashscope-native` → the native adapter); within `openai-compatible` the
  document is matched against `_OPENAI_COMPATIBLE_EMBEDDING_AUTHORITIES`, a table
  of frozen documents each paired with the adapter that reads *its* slot — the
  live authority keeps `_OpenAICompatibleEmbeddingAdapter` +
  `load_local_api_key`, the candidate gets the gateway class + gateway slot.
  Anything else is refused. Each branch validates its own `schema_version`, so a
  bundle cannot claim one provider and carry another's identity, and a document
  cannot be loaded through a credential slot it does not name.

## 3. The new identities

Both candidate variants are frozen; **exactly one of them may be used, and the
same one must be used for the rebuild and for serving** (see §3.2).

### 3.1 The two bundles

`.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json`
(native — needs the adapter)

| field | value |
|---|---|
| `schema_version` | `canonical-v2-dashscope-native-embedding-bundle-v1` |
| `provider` | `dashscope-native` |
| `model_id` | `qwen3.7-text-embedding-flash` |
| `dimension` | `1024` |
| `base_url` | `https://maas.qianwenaiapi.com/api/v1` |
| `api_key_source` | `env:CANONICAL_V2_EMBEDDING_API_KEY` |
| `batch_size` / `max_workers` / `timeout_seconds` | `32` / `32` / `180` |
| `content_sha256` | `cdddcdfd998e6c9e6147f735fd71370f209045636f3b2f3efa15e7e73a8e96ad` |

`.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1-openai-compat.json`
(compatible — **recommended**, needs no new client)

| field | value |
|---|---|
| `schema_version` | `canonical-v2-openai-compatible-embedding-bundle-v1` |
| `provider` | `openai-compatible` |
| `model_id` | `qwen3.7-text-embedding-flash` |
| `dimension` | `1024` |
| `base_url` | `https://maas.qianwenaiapi.com/compatible-mode/v1` |
| `api_key_source` | `env:CANONICAL_V2_EMBEDDING_API_KEY` |
| `batch_size` / `max_workers` / `timeout_seconds` | `32` / `32` / `180` |
| `content_sha256` | `45e458552e7031c6ca50b2ab5af225fbc5197a60c2d402b7b8b4e1fe3535029c` |

Constants: `_QWEN_FLASH_EMBEDDING_BUNDLE_SHA256` (native hash),
`_QWEN_FLASH_OPENAI_COMPAT_EMBEDDING_BUNDLE_SHA256` (compatible hash),
`_QWEN_FLASH_EMBEDDING_DIMENSION = 1024`; both pairs join
`_ACCEPTED_EMBEDDING_AUTHORITIES` (so the rebuild can produce a receipt with
either) while every crossed pair — candidate hash with 4096, live hash with 1024 —
stays absent. Each hash is the `_canonical_sha256` of the document without its
`content_sha256` field, verified against the module's own function; the same
function reproduces the live bundle's `05473fab…`, so all identities are computed
the same way.

### 3.2 Route selection: one route, for the rebuild **and** for serving

There is no config in the pipeline that compares the routes; the choice is made
**once, by which bundle is passed to the build and to the serve command**
(`--recorded-embedding-bundle <path>`, already an explicit CLI argument). The same
route must be used on both sides, because the routes are not one space: the same
text through the compatible and native routes measures cosine **0.808–0.920**, so
an index built through one route and served through the other would rank with a
space offset that no integrity check would catch — it would look like a slightly
worse model, not like a mistake.

Recommendation: **the compatible route** (`…-openai-compat.json`).
It is fully OpenAI-shaped, so it reuses the client the rebuild and serving already
use (no adapter, no new failure classification), the model is visible in
`/compatible-mode/v1/models`, and the route already answered 1024 dims in 0.29 s.
The native variant stays frozen and tested because a gateway may change the shape
of its compatible facade while keeping the native API, and because the plan's
earlier measurements were taken there; if it is ever used, it must be used on both
sides too (its own hash, not the compatible one).

The `dimensions` parameter is supported on the compatible route (1024 and 512 →
200, 4096 → 400). **The bundles do not send it** — the declared dimension is
enforced on the response — so a server-side default change fails closed instead of
silently resizing the space. If the rebuild harness wants to pin it explicitly,
that is a request-shape decision to make deliberately, on both sides.

## 4. Verification (this slice)

New tests: `apps/miroflow-agent/tests/canonical_v2/test_embedding_model_switch_v2.py`
(43 tests, local `ThreadingHTTPServer` stand-in for the gateway — no key, no
network) plus one parametrized test in
`apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py` (which owns
the real pack/index fixture).

| cluster | tests | locks |
|---|---|---|
| wire shape + ordering | 1 | `input.texts`, exact path, bearer header; rows returned reversed are placed back by `text_index` |
| unusable answers | 5 | wrong row count, duplicate/out-of-range `text_index`, empty vector, missing `output` envelope → `ValueError` |
| error classification | 7 | HTTP 400/401/429/500 → `ConnectionError`; non-JSON → `ConnectionError`; stall → `TimeoutError`; refused port → `ConnectionError` |
| adapter | 5 | batching (2/2/1) and cache reuse, cross-batch order, credential-slot separation (local key set, gateway key unset ⇒ `ValueError`, zero HTTP calls), dimension guard (4096 answer ⇒ refused), zero-vector refusal, a transport failure staying a builtin through the adapter |
| identity, both variants | 16 | self-hash == constant, correct adapter class per variant, 1024/`qwen3.7-…`, credential slot recorded as the env form; native-vs-compatible bundles differ in route, address and hash while sharing model/dimension/slot; the authority pair is a unit for both hashes |
| mutations, both variants | 16 | dimension, model, base_url, native-vs-compatible address swap, credential slot, provider swap, unknown provider, schema version — all refused |
| credential slot, compatible variant | 1 | loaded through the real loader with a recording client: the local slot's key is never used (no key ⇒ `ValueError`, zero calls), the gateway key reaches `…/compatible-mode/v1` and only it |
| inertness | 2 | the live bundle still loads to `_OpenAICompatibleEmbeddingAdapter` with 4096/`Qwen/Qwen3-Embedding-8B` and the provider is never called at load time |
| pair mismatch, real fixtures | 2 | the real pack refuses either candidate adapter (`ServingPackIntegrityError: embedding model differs`); the real `vector_matrix.npz` refuses the candidate identity, and refuses a matching model with the wrong dimension |

Regression suites re-run, results as run this session (`--no-cov`):

| command | result |
|---|---|
| `pytest tests/canonical_v2/test_embedding_model_switch_v2.py` (alone) | **43 passed** |
| `pytest test_serving_pack_loader.py test_fast_boot.py test_serving_pack_no_milvus.py test_embedding_model_switch_v2.py -n 2` | **102 passed, exit 0** |
| the same four files with `-n 8` | flaky: the milvus-lite fixtures abort with `Assert "init_flag_ == true" => Mmap manager has not been init` under 8 concurrent workers (pymilvus-lite init race, unrelated to this diff — it hits `test_serving_pack_loader`'s fixture before any embedding code runs). Use `-n 2` for this set. |
| `pytest tests/canonical_v2/test_knowledge_build_isolated.py -k "embedding or adapter"` (this branch **and** a pristine `delivery-v1` worktree) | **3 passed** on both — identical |

`test_knowledge_build_isolated.py` as a whole cannot reach a summary on this host
today, on **either** tree: the `test_real_boundary_*` / `test_complete_build_uses_*`
family needs a reachable Postgres/serving environment and hangs waiting for an
unreachable database address (both worktrees stop at the same point with the same
three failures beside it). That family is pre-existing red, not this slice's: an
earlier recorded run of the same suite
(`.agents/runs/c1-relationship-reprojection/regression-final-stdout.txt`) lists
exactly 12 failures, all of them `test_real_boundary_*` (10 params +
schema-fingerprint drift) and `test_complete_build_uses_verified_copies_…`. Both
trees fail the same tests, so nothing in this slice's diff is implicated; a run
with the real database up is what would settle it (see §7).

## 5. Required tuning before the switch: cosine thresholds vs this gateway's noise

**This gateway is slightly stochastic; our live endpoint is not.** Same route,
same text, two calls: cosine **0.99914**. The live Qwen3-Embedding-8B endpoint
measured **1.000000** (15/15). Two independent places compare vectors across
time and both use a floor that today's code tuned for a deterministic endpoint.
Neither is in this worktree's diff — this is a flag, not a fix.

### 5.1 `REFERENCE_COSINE_FLOOR = 0.999` — margin ≈ 0.1 % above the noise floor

`apps/admin-console/backend/services/canonical_v2_embedding_identity.py:59`
(F1/F2 branch `fix/embedding-lane-f1f2`, **not** in this worktree) — the
embedding card's identity probe, arm `reference`: it embeds one fixed probe
string against the *recorded* address and against the *configured* one and
requires cosine ≥ 0.999. When the operator has not overridden the address
(the normal case) both calls go to the **same** endpoint, so the comparison is a
same-endpoint repeat — and against this gateway that lands at **0.99914**,
i.e. **0.00014 above the floor**. The threshold was calibrated for 1.000000
determinism, where any margin is infinite; here the margin is inside the noise,
so the probe can fail intermittently on a perfectly healthy endpoint.

Options, for the switch slice to choose (it is that slice's code, not this
branch's):

1. **Lower the reference floor to ≈0.995** — still far above a different space
   (the orthogonal case measured −0.03) and above the cross-route distance
   (0.808–0.920, §3.2), so it keeps its discriminating power while clearing the
   measured noise floor. Cheapest, smallest change.
1. **Require the index arm too** (`INDEX_COSINE_FLOOR = 0.99`, same file:63) and
   treat a marginal reference arm as inconclusive rather than failed. The index
   arm compares a document's stored vector against a fresh embedding — the same
   kind of repeat comparison, so it carries the same noise, but its 0.99 floor
   has ~0.9 % of headroom and is comfortable.
1. **Take a multi-sample median** (e.g. 3 calls per address, compare medians /
   require the median ≥ floor). Slowest, most robust to a single bad sample, and
   it also protects against a spiky endpoint.

Any of these also needs a comment saying the endpoint is stochastic — the
current calibration note ("same space, tight bar … measured 1.000000") is true
only of the *live* address.

### 5.2 `_MIN_VECTOR_COSINE_SIMILARITY = 0.999` — a second 0.999, on the **rebuild** path

`apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py:56`,
used at `…:1177-1189` (`_validate_physical_point_rows`). The full rebuild writes
each point's vector and then **reads it back and re-embeds the same
`embedded_content`**, requiring cosine ≥ 0.999 against the stored vector
(`index_projection_isolated.py:306` — `_read_points_with_client(…, embedding_adapter=…)` inside the rebuild). This is on the switch's critical
path, and it is a *per-point* comparison: at 0.99914 noise per comparison and
~51k points, the lower tail crossing 0.999 is not a tail risk, it is the
expected outcome — a rebuild that fails with `isolated Milvus vector differs from its bound embedding`, which reads like data corruption but is the
endpoint's stochasticity.

Before the rebuild rehearsal, measure the repeat distribution properly (e.g. 20
repeats of one text through the chosen route) and either lower this floor the
same way, or make the audit accept a small shortfall fraction. The v2 (no-Milvus)
serving path does not re-embed for verification — it loads `vector_matrix.npz`
and checks model/dimension/norms only — so the serving side has no equivalent
comparison.

One sample of the repeat cosine is not a distribution; the 0.99914 figure is a
single measurement. Treat both floors as "must be re-calibrated against a
measured distribution" rather than adjusting them by guesswork.

## 6. Runbook lines (copy verbatim into the switch's runbook)

**One route only.**

> The embedding gateway is reachable through two routes that are **not** the same
> pipeline: `POST /compatible-mode/v1/embeddings` (OpenAI shape) and
> `POST /api/v1/services/embeddings/text-embedding/text-embedding` (DashScope
> native). The same text measures cosine 0.808–0.920 between them. Use **one**
> route for the rebuild **and** for serving — pass the same
> `--recorded-embedding-bundle` to the build and to the serve command
> (`…-openai-compat.json` **or** `…-v1.json`, never one each). Recommended:
> the **openai-compatible** variant (`…-openai-compat.json`,
> `base_url=https://maas.qianwenaiapi.com/compatible-mode/v1`,
> `content_sha256=45e458552e7031c6ca50b2ab5af225fbc5197a60c2d402b7b8b4e1fe3535029c`),
> because it needs no new client; it is also the bundle whose client the live
> line already runs. The native variant
> (`content_sha256=cdddcdfd998e6c9e6147f735fd71370f209045636f3b2f3efa15e7e73a8e96ad`)
> stays as the fallback if the compatible route's shape changes. Mixing the two
> is undetectable by any integrity check and looks like a slightly worse model,
> so it is a runbook rule, not a code guarantee. Both routes' bundles read the
> same credential slot: `CANONICAL_V2_EMBEDDING_API_KEY`.

**Thresholds before the switch.**

> The gateway endpoint is **stochastic**: the same text through the same route
> measures cosine **0.99914** between two calls (the live 8B endpoint measures
> 1.000000, 15/15). Two floors in today's code were calibrated for a
> deterministic endpoint and must be re-tuned **before** the rebuild:
> `canonical_v2_embedding_identity.REFERENCE_COSINE_FLOOR = 0.999` (arm
> `reference` compares two calls against the recorded/configured address — the
> same address in the normal case, i.e. a same-endpoint repeat) sits 0.00014
> above the noise floor and can fail on a healthy endpoint; and
> `index_projection_isolated._MIN_VECTOR_COSINE_SIMILARITY = 0.999`, which the
> **rebuild** applies per point (~51k comparisons) when it re-embeds a point's
> content and compares it against the vector it just wrote, will hit the lower
> tail and abort the rebuild with an integrity error that looks like corruption.
> The index arm (`INDEX_COSINE_FLOOR = 0.99`) has ~0.9 % headroom and is fine.
> Preferred order: measure the repeat distribution (≈20 repeats through the
> chosen route), then lower the reference floor to ≈0.995 and/or require the
> index arm and a small shortfall allowance on the per-point audit. Do not
> change them by guesswork from the single 0.99914 sample.

## 7. Not verified, and what the switch still needs

- **No live call from this worktree** (the key file is absent here): the shape,
  ordering rule and 1024 dimension rest on the orchestrator's authenticated
  measurements plus the mock in these tests. What is still unmeasured *by us*:
  the repeat-cosine distribution (§5), the `dimensions` parameter's effect on
  the returned vectors (only status codes were measured), and the gateway's
  batch-size limits for the rebuild's 32-row batches.
- **The lane's fail-open hop**: this branch does not contain F1
  (`fix/embedding-lane-f1f2`), whose `_ValidatingEmbeddingAdapter` lets
  `TimeoutError`/`ConnectionError` pass through to the read engine's fail-open
  hook. Here that validator still wraps every provider failure into an integrity
  error, so the adapter's classification is correct but reaches the fail-open
  path only once F1 merges. The classification itself is asserted at the client
  boundary in these tests.
- **F2 (`base_url` override)**: this branch compares the whole bundle document,
  `base_url` included, exactly as `delivery-v1` does. F2's branch excludes
  `base_url` from the comparison and resolves it through
  `resolve_embedding_base_url`; when it merges, that exclusion/resolution must be
  applied to **both** candidate branches (the native loader and the
  `_OPENAI_COMPATIBLE_EMBEDDING_AUTHORITIES` table), or the candidate bundles
  will pin the gateway host while the live one does not.
- **The rebuild** (plan §3 steps 3–6): re-embedding ~51k documents, the recall
  non-regression gate, credential provisioning for the new slot
  (`CANONICAL_V2_EMBEDDING_API_KEY`; the managed secrets page's
  `embedding.api_key` currently writes `SGLANG_API_KEY`), and the cutover.
- **`test_knowledge_build_isolated.py` end to end**: the 124 tests outside the
  DB-boundary family could not be brought to a summary here (they hang on the
  unreachable database, on both this branch and pristine `delivery-v1`). Re-run
  them, with the disposable Postgres up, before the switch is scheduled.
- **OpenSpec**: no active change covers this work (checked
  `openspec/changes/`). This slice is inert — it adds a provider that nothing
  selects and an identity that nothing loads — so it was built under the explicit
  slice instruction; the switch itself is behaviour-affecting and needs its own
  change (Standard, with the recall gate as acceptance) before the rebuild
  starts.
- **Human docs**: `docs/plans/` was out of scope by instruction; the index and
  round-log entry for this slice are still to be written by the orchestrator.
