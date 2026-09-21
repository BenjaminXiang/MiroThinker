# embedding-model-switch (v2), slice 1 — endpoint adapter + new identity

Branch: `v2/embedding-model-switch` (base tag `delivery-v1` = `36df47b8`).
Plan of record: `docs/plans/2026-09-21-embedding-model-switch-plan.md` §3 steps 1–2.

Scope of this slice, stated as a contract:

* **Goal** — prepare, without selecting, the two things the switch needs: a
  provider implementation that speaks the candidate gateway's DashScope-native
  wire shape, and the candidate's frozen embedding identity (bundle + constants).
* **Done when** — the adapter converts shape, classifies failures the way the
  serving layer already fails open, guards the declared dimension, and the
  candidate `(sha256, dimension)` pair is accepted as an authority while a
  mismatched pair is refused. Nothing on the live 4096 path changes.
* **Out of scope** — the rebuild, the recall non-regression gate, cutover,
  credentials provisioning, and anything that selects the new bundle.

## 1. OpenAI-compatibility probe (no key, not re-derived)

`POST https://maas.qianwenaiapi.com<path>`, empty-ish JSON body, no auth header,
probed 2026-09-21T13:37Z:

| path | status | body |
|---|---|---|
| `/v1/embeddings` | **404** (0.29 s) | empty — no such route |
| `/compatible-mode/v1/embeddings` | **401** (0.18 s) | `{"error":{"message":"No API-key provided.", ...}}` |
| `/api/v1/services/embeddings/text-embedding/text-embedding` | **401** (0.18 s) | `{"code":"InvalidApiKey", ...}` |
| `/compatible-mode/v1/models` (GET) | **401** | OpenAI-shaped error body |

Reading: 404 vs 401 separates "no route" from "route needs auth", so the gateway
**does expose an OpenAI-compatible route** (`/compatible-mode/v1/...`, the same
prefix DashScope uses for its compatible mode). That route's *behaviour for this
model* is unverified: whether `qwen3.7-text-embedding-flash` is served there, and
whether that route accepts a `dimension` parameter, needs one authenticated call.
The DashScope-native path is the shape measured in the plan (1024 dims, 4096 → 400),
so the adapter below is built for it; if the compatible route turns out to serve
the model, the switch reduces to `provider: openai-compatible` + a `base_url` of
`https://maas.qianwenaiapi.com/compatible-mode/v1` and no new code at all.

No live call was made: `/var/tmp/mirothinker-qianwen-api-key` does not exist on
this host (`ABSENT`), and no key was created, read, or printed.

## 2. What was built

`apps/miroflow-agent/src/data_agents/providers/dashscope_embeddings.py`
(`DashScopeTextEmbeddingClient`)

* request `{"model": ..., "input": {"texts": [...]}}` to
  `{base_url}/services/embeddings/text-embedding/text-embedding`;
* answer read from `output.embeddings[].{text_index, embedding}`, rows placed back
  by `text_index`; a set that is not exactly `0..n-1` (or a wrong row count, or an
  empty vector) raises `ValueError` — an unusable *answer*, not a transport fault;
* `dimension` is deliberately **not** sent (the candidate model answers 1024 and
  rejects 4096 with HTTP 400, measured in the plan): the declared dimension is
  enforced on the response instead;
* transport failures normalized as in `company/vectorizer.py` (F1's contract):
  `httpx.TimeoutException → TimeoutError`; `httpx.HTTPError`/`OSError` (any non-2xx
  status, refused connection, DNS) → `ConnectionError`; non-JSON body →
  `ConnectionError`. `trust_env=False`, so no ambient proxy behaviour.

`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`

* `_BatchingEmbeddingAdapter` — the existing batching/caching/thread-pool/vector
  validation moves to a shared base; a provider subclass supplies only
  `_resolve_api_key()` and `_provider_client(api_key)`. The live
  `_OpenAICompatibleEmbeddingAdapter` becomes such a subclass with byte-identical
  behaviour (same messages, same batching, same credential slot).
* `_DashScopeNativeEmbeddingAdapter` — the candidate provider. Its credential slot
  is `CANONICAL_V2_EMBEDDING_API_KEY` (`_load_gateway_embedding_api_key`), **not**
  `load_local_api_key()`: the local slot holds the self-hosted endpoint's key and
  must never travel to a third-party host. A bundle that points at the gateway
  therefore cannot be handed the local key — by construction, not by convention.
* `load_content_addressed_embedding_adapter` dispatches on the bundle's `provider`
  field: `openai-compatible` (unchanged frozen path) → `_OpenAICompatibleEmbeddingAdapter`;
  `dashscope-native` → `_DashScopeNativeEmbeddingAdapter`; anything else → refused.
  Each branch validates its own `schema_version`, so a bundle cannot claim one
  provider and carry another's identity.

## 3. The new identity

`.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json`

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

Constants: `_QWEN_FLASH_EMBEDDING_BUNDLE_SHA256` = the hash above,
`_QWEN_FLASH_EMBEDDING_DIMENSION` = `1024`; the pair joins
`_ACCEPTED_EMBEDDING_AUTHORITIES` (so the later rebuild can produce a receipt with
it) while both crossed pairs — candidate hash with 4096, live hash with 1024 —
stay absent. The hash is the `_canonical_sha256` of the document without its
`content_sha256` field, verified against the module's own function; the same
function reproduces the live bundle's `05473fab…`, so the two identities are
computed the same way.

## 4. Verification (this slice)

New tests: `apps/miroflow-agent/tests/canonical_v2/test_embedding_model_switch_v2.py`
(30 tests, local `ThreadingHTTPServer` stand-in for the gateway — no key, no
network) plus one test added to
`apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py` (which owns
the real pack/index fixture).

| cluster | tests | locks |
|---|---|---|
| wire shape + ordering | 1 | `input.texts`, exact path, bearer header; rows returned reversed are placed back by `text_index` |
| unusable answers | 5 | wrong row count, duplicate/out-of-range `text_index`, empty vector, missing `output` envelope → `ValueError` |
| error classification | 7 | HTTP 400/401/429/500 → `ConnectionError`; non-JSON → `ConnectionError`; stall → `TimeoutError`; refused port → `ConnectionError` |
| adapter | 4 | batching (2/2/1) and cache reuse, cross-batch order, credential-slot separation (local key set, gateway key unset ⇒ `ValueError`, zero HTTP calls), dimension guard (4096 answer ⇒ refused), zero-vector refusal |
| identity | 11 | bundle self-hash == constant, adapter loads with 1024/`qwen3.7-…`, authority pair atomic, seven mutations refused (dimension, model, base_url, credential slot, provider swap, unknown provider, schema version), candidate refused by a release expecting the live model |
| inertness | 2 | the live bundle still loads to `_OpenAICompatibleEmbeddingAdapter` with 4096/`Qwen/Qwen3-Embedding-8B` and the provider is never called at load time |
| pair mismatch, real fixtures | 1 | the real pack refuses the candidate adapter (`ServingPackIntegrityError: embedding model differs`); the real `vector_matrix.npz` refuses the candidate identity, and refuses a matching model with the wrong dimension |

Regression suites re-run, results as run this session (xdist `-n 8`, `--no-cov`):

| command | result |
|---|---|
| `pytest tests/canonical_v2/test_embedding_model_switch_v2.py` (alone) | **31 passed** |
| `pytest tests/canonical_v2/test_serving_pack_loader.py test_fast_boot.py test_serving_pack_no_milvus.py test_embedding_model_switch_v2.py` | **88 passed, exit 0** |
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
with the real database up is what would settle it (see §5).

## 5. Not verified, and what the switch still needs

* **No live call against the gateway** (no key on this host): the shape, the
  ordering rule and the 1024 dimension rest on the plan's 2026-09-21 measurement
  plus the mock in these tests. One authenticated call would settle it — and
  would also settle whether `/compatible-mode/v1/embeddings` serves this model,
  which would remove the need for the adapter entirely.
* **The lane's fail-open hop**: this branch does not contain F1
  (`fix/embedding-lane-f1f2`), whose `_ValidatingEmbeddingAdapter` lets
  `TimeoutError`/`ConnectionError` pass through to the read engine's fail-open
  hook. Here that validator still wraps every provider failure into an integrity
  error, so the adapter's classification is correct but reaches the fail-open
  path only once F1 merges. The classification itself is asserted at the client
  boundary in these tests.
* **F2 (`base_url` override)**: this branch compares the whole bundle document,
  `base_url` included, exactly as `delivery-v1` does. F2's branch excludes
  `base_url` from the comparison and resolves it through
  `resolve_embedding_base_url`; when it merges, that exclusion/resolution must be
  applied to the `dashscope-native` branch as well, or the candidate bundle will
  pin the gateway host while the live one does not.
* **The rebuild** (plan §3 steps 3–6): re-embedding ~51k documents, the recall
  non-regression gate, credential provisioning for the new slot
  (`CANONICAL_V2_EMBEDDING_API_KEY`; the managed secrets page's
  `embedding.api_key` currently writes `SGLANG_API_KEY`), and the cutover.
* **`test_knowledge_build_isolated.py` end to end**: the 124 tests outside the
  DB-boundary family could not be brought to a summary here (they hang on the
  unreachable database, on both this branch and pristine `delivery-v1`). Re-run
  them, with the disposable Postgres up, before the switch is scheduled.
* **OpenSpec**: no active change covers this work (checked
  `openspec/changes/`). This slice is inert — it adds a provider that nothing
  selects and an identity that nothing loads — so it was built under the explicit
  slice instruction; the switch itself is behaviour-affecting and needs its own
  change (Standard, with the recall gate as acceptance) before the rebuild
  starts.
* **Human docs**: `docs/plans/` was out of scope by instruction; the index and
  round-log entry for this slice are still to be written by the orchestrator.
