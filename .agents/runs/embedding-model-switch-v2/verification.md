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
| same route, same text, **60 repeats × 5 texts** (own measurement, §5.1) | discrete: 1.000000 or a rounded-mode cluster at 0.9980–0.9988; pooled min **0.998002** over 8,850 pairs, **0.997556** in an earlier run |
| `dimensions` param on the compatible route | 1024 → 200, 512 → 200, **4096 → HTTP 400** |

**One live finding, and a fix.** The native route's answer rows are
`['embedding', 'index', 'type']` — the gateway says `index` where DashScope's
documentation says `text_index`. Slice 1's native client was built from the
plan's description of that shape and therefore rejected every live answer with
"malformed embedding row": the native adapter could not have embedded anything.
Both spellings are now accepted (the row is placed by whichever index key it
carries), verified against a live call, and covered by tests. The compatible
route needed no such fix — it is the OpenAI shape our client already spoke.

Consequence: the switch **can ship with no new client** — the compatible route is
byte-compatible with `company/vectorizer.EmbeddingClient` — so a second candidate
bundle variant freezes that route as an authority of its own (§3), and the native
adapter is kept as the fallback. Live calls were made in this session for the
measurement in §5.1 and for the row-key finding above: the key was read from
`/var/tmp/mirothinker-qianwen-api-key` (the file the orchestrator placed there),
was never printed, logged, written into any artifact, or embedded in an argument
list, and no key was created or rotated. An earlier check of the same path during
slice 1 found it absent — this run found it present.

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
| `batch_size` / `max_workers` / `timeout_seconds` | `25` / `32` / `180` |
| `content_sha256` | `81a536916053106114aa4c70ff43983bf6a12c8ecb0b5c562b43f9f02409b46a` |

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
| `batch_size` / `max_workers` / `timeout_seconds` | `25` / `32` / `180` |
| `content_sha256` | `2db8f03b255e138a13081566c6196db06d7af1a8a83c12cec2cbfaea00b22e3d` |

Constants: `_QWEN_FLASH_EMBEDDING_BUNDLE_SHA256` (native hash),
`_QWEN_FLASH_OPENAI_COMPAT_EMBEDDING_BUNDLE_SHA256` (compatible hash),
`_QWEN_FLASH_EMBEDDING_DIMENSION = 1024`; both pairs join
`_ACCEPTED_EMBEDDING_AUTHORITIES` (so the rebuild can produce a receipt with
either) while every crossed pair — candidate hash with 4096, live hash with 1024 —
stays absent. Each hash is the `_canonical_sha256` of the document without its
`content_sha256` field, verified against the module's own function; the same
function reproduces the live bundle's `05473fab…`, so all identities are computed
the same way.

### 3.1a The batch cap the bundles must respect

Both routes refuse a batch larger than **25** — measured directly 2026-09-21:

| probe | compatible route | native route |
|---|---|---|
| batch 25 | **200**, 25 rows, index 0…24 complete, 1024 dims | **200**, 25 rows |
| batch 26 | **400** `batch size is invalid, it should not be larger than 25.: input.contents` | — |
| batch 32 | **400** (same message) | **400** `InvalidParameter` (same message) |

The cap is identical on the two routes, so one number covers both variants, and
both bundles were re-frozen at `batch_size: 25` (hashes above, recomputed). At 32
the rebuild would have failed on its first call, and on the serving path F1's
contract turns a 4xx into lane *degradation* — silent recall loss instead of an
error. 25 rather than a rounder 16: the rebuild is token-bound (1M TPM), not
request-bound, so a smaller batch only adds requests (2,041 calls at 25 versus
3,190 at 16 for 51,026 points, same tokens). The live authority keeps
`batch_size: 32` — this is the gateway's cap, not a policy for the self-hosted
endpoint. A test pins the declared value to the measured cap so an edit cannot
silently reintroduce it; the precheck's `--batch-probe` (currently hard-coded to
a 32-text batch) should be retargeted to the declared 25.

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
(56 tests, local `ThreadingHTTPServer` stand-in for the gateway — no key, no
network), one parametrized test in
`apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py` (which owns
the real pack/index fixture), and the tuned-floor cases in
`apps/admin-console/tests/test_embedding_identity_probe.py`.

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
| index-key spellings | 2 | the gateway's measured `index` and DashScope's documented `text_index` both place rows; a row with neither is refused |
| F1/F2 seam after merge | 3 | F2's address override reaches both candidate bundles; F1's pass-through keeps the gateway client's transport builtins builtins (and still fails closed on a wrong answer); F1's breaker opens after two gateway transport failures |
| rebuild-audit floor (C.1) | 7 | the measured repeat band (1.0 … 0.997556) passes the real audit; 0.932903 / 0.86 / 0.241886 / 0.0 / −0.03 and a wrong dimension are still refused; the constant is 0.99 |
| identity-check floor (C.2, admin) | 9 | the measured repeat band passes the reference arm; the wrong-answer band still fails with the operator message; the floor's bounds are pinned |

Regression suites re-run after this session's work, results as run
(`--no-cov`):

| command | result |
|---|---|
| `pytest tests/canonical_v2/test_embedding_model_switch_v2.py` (alone, gateway stand-in, no key) | **56 passed** |
| the eight embedding/pack files: `test_serving_pack_loader`, `test_fast_boot`, `test_serving_pack_no_milvus`, `test_embedding_model_switch_v2`, `test_embedding_endpoint_resolution`, `test_embedding_lane_breaker`, `test_embedding_lane_fail_open`, `test_embedding_transport_classification` at `-n 2` | **144 passed, exit 0** |
| `pytest apps/admin-console/tests -n 4` (mine vs `release/v1.1`, both with `PYTHONPATH=<their>/apps/miroflow-agent`) | **identical failure sets**: 130 entries (25 failed, 105 errors), 127 distinct `file::function` ids with identical status and counts. The red set is pre-existing and environment-driven (DB-dependent tests). |
| `pytest tests/canonical_v2/test_embedding_identity_probe.py` (admin) | **26 passed** |
| the same eight files at `-n 8` | flaky: the milvus-lite fixtures abort with `Assert "init_flag_ == true" => Mmap manager has not been init` under 8 concurrent workers (pymilvus-lite init race, unrelated to this diff). Use `-n 2` for this set. |
| `pytest tests/canonical_v2/test_knowledge_build_isolated.py -k "embedding or adapter"` (this branch **and** a pristine `delivery-v1` worktree) | **3 passed** on both — identical |

### The merge with `release/v1.1` (Task B)

`git merge 82dc8f61`: two conflicts, both in `knowledge_build_isolated.py`, both
the interaction predicted when the candidate slice was written.

1. **Provider/credential-slot block vs F2's resolver.** Kept both: F2's
   `EMBEDDING_BASE_URL_ENV` + `resolve_embedding_base_url` stay module-level, the
   gateway credential slot and the accepted-authority table sit beside them.
1. **The `openai-compatible` loader vs F2's "the address is not part of the frozen
   identity".** Kept the table-driven dispatch; F2's rule now lives once in
   `_matches_frozen_authority` (both sides drop `base_url`) and is applied to the
   new branches too — the native loader resolves its effective address through
   `resolve_embedding_base_url`, so the candidate no longer pins its host while
   the live authority moves. The recorded address stays pinned by the content
   hash, which F2's own `test_a_resealed_bundle_with_another_address_is_still_refused`
   still asserts.

Auto-merged without conflict, and verified by the suites above: F1's lane breaker
now wraps **every** provider (the breaker field, its pre-cache check and its
outcome recording landed inside the shared `_BatchingEmbeddingAdapter`), F1's
transport pass-through in `_ValidatingEmbeddingAdapter`, the managed lane-wait
knob, and the compatible client's transport normalisation in
`company/vectorizer.py`.

One of F2's tests had to adapt to the refactor: its
`test_the_address_is_not_part_of_the_frozen_identity_comparison` sniffed the
loader's source for a literal `expected = {` block, which the table dispatch no
longer has. It now asserts the guarantee behaviourally (a bundle differing only
in the recorded address still loads and uses its own address) plus the structural
seam both branches share. Three new integration tests cover the seam the merge
created: F2's override reaches both candidate bundles, F1's pass-through covers
the gateway client (transport builtins still pass, a wrong answer still fails
closed), and F1's breaker opens after two gateway transport failures.

### The floors (Task C)

Both floors are **0.99** with derivations and RED/GREEN evidence in §5.2–§5.3,
and the build line's port patch is verified in §5.4.

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

## 5. The measured noise, and the two floors derived from it

Both floors were re-tuned against a measured distribution, not a single sample.
Evidence: `.agents/runs/embedding-model-switch-v2/repeat-noise-measurement.json`
(raw pair values, generated by `measure_repeat_noise.py`, key never printed).

### 5.1 The measurement (compatible route, `qwen3.7-text-embedding-flash`)

**Long sample** (2026-09-21, `--repeats 60`, five text shapes; raw pairs in
`repeat-noise-measurement-long.json`): 60 calls per text, pairwise cosine among
the repeats:

| text | calls | pairs | min | p1 | p5 | median | max | mean | stdev | latency (median) |
|---|---|---|---|---|---|---|---|---|---|---|
| zh-short | 60 | 1,770 | 0.998002 | 0.998002 | 0.998139 | 0.998829 | 1.000000 | 0.999278 | 0.000682 | 0.208 s |
| en-short | 60 | 1,770 | 0.998772 | 0.998772 | 0.998772 | 1.000000 | 1.000000 | 0.999420 | 0.000613 | 0.205 s |
| zh-medium | 60 | 1,770 | 0.998308 | 0.998308 | 0.998308 | 0.998308 | 1.000000 | 0.999140 | 0.000846 | 0.205 s |
| en-medium | 60 | 1,770 | 0.998655 | 0.998655 | 0.998655 | 0.998655 | 1.000000 | 0.999323 | 0.000673 | 0.207 s |
| zh-document (long) | 60 | 1,770 | 0.998004 | 0.998004 | 0.998004 | 0.998004 | 1.000000 | 0.998986 | 0.000998 | 0.205 s |
| **pooled** | 300 | **8,850** | **0.998002** | — | — | 0.998829 | 1.000000 | — | — | — |

Nothing in 8,850 pairs fell below 0.998: **0 pairs below 0.9985 / 0.998 / 0.9975
/ 0.995 / 0.99**. An earlier 25-repeat run saw the low mode at **0.997556**, which
remains the lowest repeat ever observed across ~10.5k pairs in four runs.

Mode structure: the distribution is **discrete, not a continuum** — each text's
pairs take two to four exact values, one identical (1.000000) and a small cluster
of rounded modes that depends on the text and moves between runs (zh-short
showed 0.998002 / 0.998139 / 0.998829 in this sample, 0.997556 in the first).
That is why a floor in the third decimal cannot hold and why the floors were
derived from the *minimum*, not from the median.

Earlier sample (30 repeats × 3 texts, `repeat-noise-measurement.json`, for
continuity): pooled min 0.998004 over 1,305 pairs, same shape.

Controls:

| control | this sample |
|---|---|
| cross-route, same text (compatible vs native) | 0.8608–0.8640 (zh-short), 0.9294–0.9295 (en-short), 0.8659–0.8678 (zh-medium), **0.9584–0.9594** (en-medium), 0.9319–0.9327 (zh-document) |
| two different texts (zh-short vs en-short) | 0.2366–0.2434 |
| `dimensions: 512` (3 calls, informational) | repeat cosines 0.998790/0.998790/1.000000, dims 512 |

So a healthy endpoint's repeat cosine lands in **0.9976–1.0** (worst single value
ever observed: 0.997556), and a *wrong* answer lands at ≤**0.9594** (the closest
measured cross-route agreement, a long English text; short texts are as low as
0.8608).

**Do the 0.99 floors still hold?** Yes, with margin on both sides:

- below: the pooled minimum 0.998002 is **0.008002 above 0.99** on this sample —
  **4.0× the whole observed spread** (1 − 0.998002) — and with the historical
  worst pair (0.997556) the margin is 0.007556, still 3.8× the spread. Nothing
  observed comes within 0.0075 of the floor.
- above: the floor keeps **0.031** of separation from the highest measured
  wrong answer (0.9594, up from 0.9329 in the previous sample), i.e. the two bands
  remain separated by a factor of ~26 in distance from the floor.

Both floors are 0.99 (§5.2, §5.3) and the derivation still stands: no
re-derivation is needed. If a future sample ever drops below 0.99, the proposal
is already written down — lower the floor to the measured minimum minus 3–4× the
spread, or switch the audit to a fraction-based rule — but the data does not call
for either today.

### 5.2 Rebuild path: `_MIN_VECTOR_COSINE_SIMILARITY` 0.999 → **0.99**

`apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py:56`,
used in `_validate_physical_point_rows` at `…:1177-1189`. The rebuild writes each
point's vector and then reads it back and re-embeds the same `embedded_content`,
comparing against the stored vector (`_read_points_with_client(…, embedding_adapter=…)` at `…:306`). Per point, ~51k times per rebuild.

Derivation: the measured lowest repeat is 0.997556 (long sample: 0.998002), so
any floor at or above it
false-fails a healthy endpoint — and a per-point audit over ~51k comparisons
reaches the tail of the distribution, so "usually above" is not enough.
**0.99** sits **0.0076 below the lowest repeat ever measured** — 3.2× the whole
observed spread (1 − 0.997556) — while keeping **0.06 above the highest measured
wrong answer** (0.9329, the sibling route) and far above another space (≈ −0.03).
The guard's power is not in the third decimal: a vector bound to the wrong point
measures 0.24 (unrelated documents) or up to 0.93 (near-duplicate or sibling
route), dimension and norm are checked separately beside the cosine.

A shortfall-fraction rule (e.g. "≤0.5 % of points may sit below 0.998") was
considered and **not** adopted: the hard floor already clears the measured tail
with 3× the observed spread, and the corruption this audit catches is
systematic, so an allowance would only add a knob that can hide a real fault.

Evidence (RED before, GREEN after), driving the real audit function with vectors
placed at exact cosines (`.agents/runs/.../test_embedding_model_switch_v2.py`,
`test_rebuild_audit_*`):

```
floor 0.999: RED  — "isolated Milvus vector differs from its bound embedding" at cosine 0.997556
             and again at 0.998002 (the long sample's minimum)
floor 0.99 : GREEN — the whole measured band (1.0, 0.998829, 0.998772, 0.998308, 0.998004, 0.997556) passes
floor 0.99 : still refuses 0.932903 / 0.86 / 0.241886 / 0.0 / −0.03 and a wrong dimension
```

### 5.3 Identity check: `REFERENCE_COSINE_FLOOR` 0.999 → **0.99**

`apps/admin-console/backend/services/canonical_v2_embedding_identity.py:59`. Arm
`reference` embeds the fixed probe text against the *recorded* address and the
*configured* one; with the operator's setting unset both calls go to the same
address, so this arm compares exactly the repeat-distribution measured in §5.1.
At 0.999 the margin above the noise floor was **0.00014** — inside the noise.

Derivation: **0.99**, the same number and the same reasoning as §5.2: 0.0076
below the lowest repeat ever measured, 0.06 above the highest wrong answer, far
above another space. `INDEX_COSINE_FLOOR` stays **0.99** (it has ~0.9 % headroom
against the same noise, and the two arms now share one rule). Making the verdict
require *both* arms was considered; not done, because the index arm is a
fallback for when the recorded endpoint is unreachable, not a second opinion —
changing that semantics is the switch slice's call, not a threshold fix.

Evidence (RED before, GREEN after), driving the real probe with stub endpoints
(`apps/admin-console/tests/test_embedding_identity_probe.py`):

```
floor 0.999: FAILS a healthy repeat at cosine 0.998829 (the measured band)
floor 0.99 : passes the whole measured band (1.0, 0.998829, 0.998772, 0.998004, 0.997556)
floor 0.99 : still rejects 0.932903 / 0.86 / 0.241886 with "不要切换到这个端点"
floor 0.99 : test_the_reference_floor_is_derived_from_the_measured_noise_band pins both bounds
```

### 5.4 Port patch for the build line (the rebuild runs there)

`.worktrees/data-rebuild/.../index_projection_isolated.py` is an **older
generation** of the same file (no `serving_timing`, no `lookup-sqlite` point
store), so the branch's diff does not apply textually — but its audit site is
the same rule, at line 52 (`_MIN_VECTOR_COSINE_SIMILARITY = 0.999`) and line 942
(`cosine_similarity < _MIN_VECTOR_COSINE_SIMILARITY`). A one-hunk port patch
against that file's own context is committed at
`.agents/runs/embedding-model-switch-v2/rebuild-line-cosine-floor.patch`
(0.999 → 0.99 plus the derivation comment).

```
$ git -C .worktrees/data-rebuild apply --check \
    .agents/runs/embedding-model-switch-v2/rebuild-line-cosine-floor.patch
Checking patch apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py...
(exit 0 — applies cleanly; that worktree was NOT modified)
```

The rebuild's launcher must apply it (or carry the tuned value) before the run;
the audit itself needs no other change, since the comparison reads the constant.

## 6. Runbook lines (copy verbatim into the switch's runbook)

**One route only.**

> The embedding gateway is reachable through two routes that are **not** the same
> pipeline: `POST /compatible-mode/v1/embeddings` (OpenAI shape) and
> `POST /api/v1/services/embeddings/text-embedding/text-embedding` (DashScope
> native). The same text measures cosine 0.860–0.933 between them (measured,
> 3 texts). Use **one** route for the rebuild **and** for serving — pass the same
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
> so it is a runbook rule, not a code guarantee. Both variants read the same
> credential slot: `CANONICAL_V2_EMBEDDING_API_KEY`, and both declare
> `batch_size: 25` (the gateway rejects more than 25 on either route: 25 → 200,
> 26 → 400). If the operator overrides
> `CANONICAL_V2_EMBEDDING_BASE_URL`, the override must point at the *same* route
> — the probe will (correctly) report "不在同一嵌入空间" if it does not.

**Thresholds: already tuned on this branch — carry them to the rebuild host.**

> The gateway endpoint is **stochastic**: same route, same text, 60 repeats ×
> 5 text shapes: answers are discrete (identical, or a two-to-four-value cluster
> of rounded modes at 0.9980–0.9988), pooled minimum **0.998002** over 8,850
> pairs and **0.997556** in an earlier run, with the low mode depending on the
> text and moving ~0.0013 between runs. Both cosine floors were therefore
> re-derived from that distribution and are **0.99**:
>
> - `index_projection_isolated._MIN_VECTOR_COSINE_SIMILARITY` (rebuild path,
>   per point, ~51k comparisons) — 0.99 is 0.0080 below the long sample's
>   minimum (4.0× the observed spread) and 0.031 above the highest measured
>   wrong answer (0.9594). At the old 0.999 it aborted the audit on a healthy
>   endpoint: RED evidence in §5.2.
> - `canonical_v2_embedding_identity.REFERENCE_COSINE_FLOOR` (admin identity
>   check) — same number, same derivation; `INDEX_COSINE_FLOOR` stays 0.99.
> - **The build host must carry the rebuild-path floor.** The rebuild runs in
>   `.worktrees/data-rebuild`, whose copy of that file is an older generation:
>   apply `.agents/runs/embedding-model-switch-v2/rebuild-line-cosine-floor.patch`
>   there (`git apply --check` verified clean, §5.4) before launching, or the
>   rebuild will false-fail its own audit.
>   Do not tighten either floor without a fresh measurement of the same kind
>   (`measure_repeat_noise.py` in this directory).

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

## 8. Gate round (2026-09-22) — two silent integration defects, closed before any verdict was read

### 8.1 The candidate layer was empty because `backend` came from the main tree

Attempt 1 of the recall gate (16:02–16:18) returned REVIEW for 37/37 cases with
`candB = -` against `candA = Y` for every row, while the answer layer (`ansA/ansB`) and
the vector lane (`vecA/vecB`) were identical row for row. The turn-debug directory stayed
empty and the boot log had **zero** `turn debug dump failed` lines — so nothing had failed
to write: the code that writes it was not loaded.

Root cause, proved not inferred:

* the deployment venv `.venv` carries **two** editable `.pth` entries pointing at the main
  checkout — `_editable_impl_admin_console.pth` (`apps/admin-console`) and
  `_editable_impl_miroflow-agent.pth`;
* the command file pinned only `PYTHONPATH=<switch line>/apps/miroflow-agent`, so `src`
  resolved to the switch line while `backend` resolved through the `.pth` to the **main tree**;
* the runner's own fallback insert (`complete_candidate_runner.py:958-967`) fires only on
  `ModuleNotFoundError`, and `import backend.main` *succeeded* — so nothing complained;
* the main tree's `canonical_v2_chat.py` has no `_maybe_dump_turn_debug` at all
  (`grep -c` = 0 there, and the two files differ by 314 lines).

Live proof on the booted scratch instance: `GET /api/auth/me` → **404** and
`GET /api/canonical-v2/admin/chat-gaps` → **404** (both routes exist only on the serving
tree) while `/api/health` → 200.

Fix and re-verification:

* `PYTHONPATH` now carries **both** roots, admin-console first:
  `…/apps/admin-console:…/apps/miroflow-agent`;
* after the restart the same probes return **401** (route present, session required), the
  admin store is created under the scratch state dir (`/var/tmp/fembed-296/logs/admin-auth.sqlite3`,
  not the live one), and one probe turn wrote `turn-debug-tdbg1-01.json` (kept as
  `/var/tmp/fembed-296/probe-turn-identity-fix-debug.json`);
* gate pass 1 then reported `cand=yes` on all 37 cases.

Compounding, not just patching: `check-package-resolution.sh` (new) resolves `backend` and
`src` through a command file's own python + `PYTHONPATH`; the cutover checker gained three
items (both roots pinned, plus the semantic resolution probe) and now reports 32 checks. The
**same defect was present in the step-12 cutover draft** and the new items caught it before
any install — without them the live line would have come up on the main tree's admin console.

### 8.2 The host cutover could not have booted: a shell substitution inside a quote-free-only file

The live line is a user unit whose `ExecStart` is `<live tree>/deploy/start-canonical-v2.sh`;
that script ends with `exec env $(cat "$COMMAND_FILE")` — **no shell evaluation**. The fembed
draft carried `CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)"`,
which word-splits into the argv tokens `CANONICAL_V2_EMBEDDING_API_KEY="$(cat` and
`/var/tmp/mirothinker-qianwen-api-key)"`, after which `env(1)` tries to execute the second
one. Proved with a synthetic file of the same shape:
`env: '/tmp/some-key)"': No such file or directory` — i.e. the unit would crash-loop. The
live run16 command file is quote-free (0 `"`, 0 `$(`) for exactly this reason.

Fix and proof:

* the key travels in a systemd `EnvironmentFile` (0600) named by a drop-in; the **installed**
  command file stays quote-free. Proved end-to-end with a temporary oneshot unit whose
  `ExecStart=/usr/bin/env` printed `CANONICAL_V2_EMBEDDING_API_KEY=sk-ws-…` (probe unit removed
  afterwards);
* checker: item 5 refuses the shell form and — with `--expect-key-file <path>` — requires that
  file to exist and define the variable; item 5b requires the host file to be quote-free.
  The host draft scores **32 ok / 0 fail** with the key file named, and fails `EMBEDDING_KEY`
  without it (by design: the checklist must name the key file).

Two further cutover facts established while checking this (both in the runbook §12):

* ~~the page's key field **cannot** feed the serving lane today~~ — **corrected 2026-09-23, the claim
  was wrong**: the R16 adoption is called by `serving_pack_loader.open_serving_pack_authority`
  ("R16: the serving process adopts the operator's managed configuration here — once, at startup,
  never on a request path"), which the `--serve-existing` boot runs **before** any serving input is
  built. Measured: a command file with the key token removed booted with the key already in its
  initial environment (from `config/managed/secrets.json`) and its vector lane served 128
  candidates. The `EnvironmentFile` is still what the unit supplies without page interaction, and
  an environment value always wins over the store;
* the switch is safe for the admin login: both trees' `admin_auth.py` are byte-identical and
  the accounts DB + signing key resolve from `CANONICAL_V2_ACCESS_LOG_DB`'s parent, which the
  cutover keeps unchanged.

### 8.3 Gate result (attempt 2, the valid one) — the switch is recall-neutral

```
warm-up exit=0    (37 cases, all cand=yes)
judged  exit=0
VERDICT_BASELINE_EXIT=2   VERDICT: REVIEW — 0 fail-level, 3 review-level
VERDICT_CONTROL_EXIT=2    VERDICT: REVIEW — 0 fail-level, 3 review-level
```

Counts and the one zero-noise metric (baseline ↔ after, `--diff`):

| line | baseline | after | Δ |
|---|---|---|---|
| candidate-layer hits | 22 | **29** | **+7** |
| candidate-layer checked | 37 | 37 | +0 (the attempt-1 coverage gap is gone) |
| llm-synthesized turns | 35 | 35 | +0 |
| **vector median (all / shared / testset / probes)** | 61.0 / 61.0 / 61.0 / 72.0 | **same, all four** | **+0** |
| vector coverage (n) | 34 | 34 | — |
| citation local / web | 239 / 80 | 158 / 125 | known web-lane noise |
| wall seconds | 698.7 | 355.6 | — |

`control ↔ after` (same question with the web-lane noise removed) is the same shape: candidate
hits 29 → 29, all four vector medians +0, `REVIEW — 0 fail-level, 3 review-level`.

Reading it against the calibration already recorded (`noise-floor.md`, protocol §6): a
same-configuration pair scores REVIEW with 0 fail-level, so **REVIEW with 0 fail-level is the
expected shape of a healthy switch**, and the only hard-FAIL tripwire (`vector median` drop
> 30 %) does not even move. The three review-level items are all `rule1(concept)` *wording*
drift (`真实数据`, `物理仿真引擎生成`, `基于规则生成`, `真机实测`, `遥操作`) — the class this
gate declares as non-entity drift. **Verdict: recall did not regress; the switch is eligible.**

### 8.4 The apples-to-apples capture (same answer model) — and the three console gaps it exposed

The first after run was confounded: the live line's answer model comes from
`<tree>/config/managed/settings.json` (`serving.chat_llm_profile = deepseekv4flash`), the switch
line had no such file, so the after arm wrote its prose with the default `gemma4`
(`qwen3.6-35b-a3b`). The difference is large and perfectly reproducible within each model:

| case | deepseek ×2 (baseline, control) | gemma4 ×2 (after, after2) |
|---|---|---|
| q2t3 local citations | 26 / 25 | **1 / 1** |
| s10 | 8 / 10 | **0 / 0** |
| s01 | 21 / 21 | **12 / 12** |
| totals local / web | 239/80, 228/128 | 158/125, 165/124 |
| answer all-hit | 20/20, 20/20 | 18/20, 18/20 |

With the settings carried over, the third capture (`afterB`, same stack + same model) closes it:

| pairing | answer hits | all-hit | cand. hits | vector median | local/web | wall s | verdict |
|---|---|---|---|---|---|---|---|
| baseline ↔ afterB | 31 → 28 | 20 → 17 | 22 → **24** | **+0** (61/61/61/72) | 239/80 → **225**/92 | 698.7 → 666.4 | REVIEW, 0 fail |
| control ↔ afterB | 31 → 28 | 20 → 17 | 29 → 24 | **+0** | 228/128 → **225**/92 | 489.8 → 666.4 | REVIEW, 0 fail |
| after ↔ afterB (model contrast) | 29 → 28 | 18 → 17 | 29 → 24 | **+0** | 165/124 → **225**/92 | 431.3 → 666.4 | REVIEW, 0 fail |

Every review-level row in every pairing is in a class the calibration already tolerates: `concept`
wording (the same-configuration pair baseline↔control produced 3 of them too) plus one
`CANDIDATE-only` miss on `q6t2` whose answer still names the arXiv id. **No fail-level item anywhere;
the vector median never moves; the citation density lands 225 against 239/228 — inside the measured
same-configuration band (239↔228 and 158↔165).** The model contrast is an order larger than the
migration's effect (+60 local citations for deepseek over gemma4 on the same stack), which is why the
confounded first comparison looked like a regression at all.

**Behavioural parity, both lines, same day**: `replay_fix_round1.py` — new stack 37/37 requests,
**RESULT: ALL PASS** (27 turns, 7/7 sessions); live 18188 the same day: **RESULT: ALL PASS** (27
turns, 0 failures). Artifacts: `replay-fix-round1-18296/`, `replay-fix-round1-18188/`.

**Three operator-surface gaps found while checking this (all fixed and measured, runbook §12)**:
`settings.json` not carried over (answer model); `paths.serving_pack_dir` unset (the page named the
old model); `extraction_endpoints.embedding_base_url` unset + the page's credential slot empty (the
connection test probed the old endpoint, then 401). After all three, on the scratch instance:

```
chat_profile    = deepseekv4flash
frozen model    = qwen3.7-text-embedding-flash
frozen base_url = https://maas.qianwenaiapi.com/api/v1
conn_test       = ok, 347 ms (compatible 404 → dashscope-native 200)
```

### 8.5 "Unverified items" pass (2026-09-23) — what was actually checked, and one correction

**Correction first.** §8.2 recorded "the page's key field cannot feed the serving lane" as a gap. That was
wrong: the R16 adoption is called by `serving_pack_loader.open_serving_pack_authority` ("R16: the serving
process adopts the operator's managed configuration here — once, at startup, never on a request path"),
and a `--serve-existing` boot opens the pack *before* any serving input is built. Measured: with the key
token deleted from the command file (`serve-fembed-gate-18296-nokey-command.sh`, 0 quotes, 0 `$(`), the
process's initial environment already carried `CANONICAL_V2_EMBEDDING_API_KEY` (projected from
`config/managed/secrets.json`) and the vector lane served **128 candidates** on a live turn. The
runner-side patch written for that phantom gap was reverted (it was purely additive: `git checkout`
restores it; the runner is not part of any sealed identity). The `EnvironmentFile` stays — the unit is
the authority, and an env value wins over the store.

**Suites, with the live tree as the baseline** (same environment, same fixtures, 2026-09-23):

| suite | switch line | live tree (s11-consolidation) | shared red |
|---|---|---|---|
| console (127 files) | 68 failed / 1579 passed / 61 errors | 66 failed / 1486 passed / 61 errors | **127 of 129 items identical** |
| agent, 6-file subset | 73 red | 73 red | **73 of 73 identical** |
| agent, 17-file subset | 28 red | 18 red | 18 shared; the 10 extra were 8 isolation artefacts + 2 config-leak items (below) |
| agent, full | 98 failed / 5527 passed / 299 skipped | (subsets above) | pre-existing / DB-bound |

Environment repairs that made the runs meaningful: a dedicated `miroflow_test_mock` with the
destructive-target marker comment, and the console's real-data XLSX fixture symlinked into the worktree.

**Two isolation defects found and fixed (test-side, both suites)**: `apply_managed_runtime_config()`
projects the machine's managed files into `os.environ` for the whole process, so a *configured* machine
flipped tests that assert defaults — 5 console items and the two `test_parse_args_default_has_no_serving_pack`
/ `…_skips_envelope_ownership` items. Both suites now pin `CANONICAL_V2_MANAGED_SETTINGS` /
`CANONICAL_V2_MANAGED_SECRETS` to empty tmp files for the session. Console: 129 → 124 red, **0 new**.
Also fixed: two stale embedding-loader fakes in `s12a/test_complete_candidate_runner.py` that predated the
`role=` parameter (red at HEAD too, now 7/7 green).

**Concurrency**: a new `load-probe.py` (8 parallel turns, 8 lanes-mixed queries) — new stack: 8/8 HTTP 200,
0 errors, vector lane 16–128 candidates, web lane `unavailable` on 5–6 turns and 2 turns with 0 citations.
The **live line shows the same shape** (same queries, same unavailable/zero-citation turns, ok=6/8) ⇒ a
pre-existing load characteristic, not a switch regression.

**Rollback preconditions** verified read-only: `serving-pack-run16-readerbound` and `index-v3-v2` untouched
(and currently being served by the live line, which is the strongest possible proof a rollback boots).
