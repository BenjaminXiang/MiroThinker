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
| same route, same text, **30 repeats × 3 texts** (own measurement, §5.1) | bimodal: 1.000000 or 0.998004–0.998829; pooled min **0.998004** over 1305 pairs, **0.997556** in an earlier run |
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

30 repeats per text, three text shapes (short Chinese entity line, short English
technical line, document-length block); pairwise cosine among the repeats:

| text | repeats | pairs | min | p1 | p5 | median | max | mean | stdev | latency (median) |
|---|---|---|---|---|---|---|---|---|---|---|
| zh-short | 30 | 435 | 0.998829 | 0.998829 | 0.998829 | 1.000000 | 1.000000 | 0.999461 | 0.000584 | 0.204 s |
| en-short | 30 | 435 | 0.998772 | 0.998772 | 0.998772 | 0.998772 | 1.000000 | 0.999376 | 0.000615 | 0.207 s |
| zh-document | 30 | 435 | 0.998004 | 0.998004 | 0.998004 | 1.000000 | 1.000000 | 0.999082 | 0.000996 | 0.211 s |
| **pooled** | 90 | **1305** | **0.998004** | — | — | — | 1.000000 | — | — | — |

An earlier run (25 repeats, same route) saw the low mode at **0.997556** for the
short Chinese text, so the *lowest repeat cosine ever observed here is
0.997556*. The distribution is **bimodal, not a continuum**: each text's pairs
take exactly two values — the identical answer (1.000000) and one slightly
rounded mode (~0.998004–0.998829) — and which share each side gets moves between
runs, i.e. the mode itself drifted ~0.0013. Nothing was observed below 0.9975 in
~1.6k pairs.

Controls, same run:

| control | cosine |
|---|---|
| cross-route, same text (compatible vs native) | 0.8598–0.8639 (zh-short), 0.9287–0.9295 (en-short), 0.9319–0.9329 (zh-document) |
| two different texts (zh-short vs en-short) | 0.2366–0.2434 |
| `dimensions: 512` (3 calls, informational) | repeat cosines 1.000000/1.000000/1.000000, dims 512 |

So the band a **healthy** endpoint lands in is ≈0.9976–1.0, and the band a
**wrong** answer lands in is ≤0.933 (sibling route) down to ≈0 (another space).

### 5.2 Rebuild path: `_MIN_VECTOR_COSINE_SIMILARITY` 0.999 → **0.99**

`apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py:56`,
used in `_validate_physical_point_rows` at `…:1177-1189`. The rebuild writes each
point's vector and then reads it back and re-embeds the same `embedded_content`,
comparing against the stored vector (`_read_points_with_client(…, embedding_adapter=…)` at `…:306`). Per point, ~51k times per rebuild.

Derivation: the measured lowest repeat is 0.997556, so any floor at or above it
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
floor 0.99 : GREEN — the whole measured band (1.0, 0.998829, 0.998772, 0.998004, 0.997556) passes
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
> credential slot: `CANONICAL_V2_EMBEDDING_API_KEY`. If the operator overrides
> `CANONICAL_V2_EMBEDDING_BASE_URL`, the override must point at the *same* route
> — the probe will (correctly) report "不在同一嵌入空间" if it does not.

**Thresholds: already tuned on this branch — carry them to the rebuild host.**

> The gateway endpoint is **stochastic**: same route, same text, 30 repeats:
> answers are bimodal (identical, or a slightly rounded mode at 0.9980–0.9988),
> pooled minimum **0.998004** over 1305 pairs and **0.997556** in an earlier
> run, with the mode itself moving ~0.0013 between runs. Both cosine floors were
> therefore re-derived from that distribution and are **0.99**:
>
> - `index_projection_isolated._MIN_VECTOR_COSINE_SIMILARITY` (rebuild path,
>   per point, ~51k comparisons) — 0.99 is 0.0076 below the lowest repeat ever
>   measured (3× the observed spread) and 0.06 above the highest measured wrong
>   answer (0.9329). At the old 0.999 it aborted the audit on a healthy
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
