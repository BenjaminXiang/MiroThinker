# Design: switch-embedding-model-to-qwen37-flash

## 1. The identity chain that has to move together

The embedding identity is not one field; it appears in seven places, and every
pair is checked fail-closed at a different boundary. The switch moves all of them
in one rebuild, and the checks are what make a partial move impossible.

| # | Where | Field / check |
|---|---|---|
| 1 | embedding bundle (build + serve input) | `schema_version`, `provider`, `model_id`, `dimension`, `base_url`, `api_key_source`, `batch_size`/`max_workers`/`timeout_seconds`, `content_sha256` |
| 2 | accepted authorities | `_ACCEPTED_EMBEDDING_AUTHORITIES` holds the `(content_sha256, dimension)` pair; a crossed pair is absent by construction |
| 3 | index request | `request.embedding_model == adapter.model_id` (`index_projection_isolated.py:257-262`) |
| 4 | persisted matrix | `vector_matrix.npz` meta `{embedding_model_id, dimension, point_count}`; read-back validates model + dimension + point-set + norms (`index_projection_isolated.py:681-735`) |
| 5 | pack manifest | `manifest.embedding_model_id` vs the adapter and the index policy (`serving_pack_loader.py:755-758`, `957`) |
| 6 | serving bundle | `RecordedServingBundle.embedding_model_id` (`serving-bundle-run16.json` records the live model today) |
| 7 | serving boot | the same pack/matrix pair checks run at boot; a mismatch is `ServingPackIntegrityError`, not a degrade |

Consequence: the switch cannot be done by editing a config value — every one of
these is derived from the rebuild, and a half-move fails closed at boot rather
than silently mixing vector spaces.

## 2. Route choice: two frozen bundles, one used

The gateway serves the model on two wire shapes, both measured:

| Route | Probe (2026-09-21) | Bundle |
|---|---|---|
| OpenAI-compatible | `POST /compatible-mode/v1/embeddings` → **HTTP 200, 1024 dims, 0.311 s** (single text; usage 20 prompt tokens) | `…-embedding-bundle-v1-openai-compat.json` (`45e45855…`) |
| DashScope-native | `POST /api/v1/services/embeddings/text-embedding/text-embedding` → 401 without a key; 1024 dims / 400 on `dimension: 4096` (plan §2) | `…-embedding-bundle-v1.json` (`cdddcdfd…`) |

**Decision: use the OpenAI-compatible bundle** (no new client in the serving
path; `_GatewayOpenAICompatibleEmbeddingAdapter` is the existing OpenAI client on
the gateway credential slot). The native bundle stays frozen as the fallback.

**Constraint that makes this a decision and not a preference**: the two routes are
*not* the same pipeline — the same text embedded through both scores cosine
0.808–0.920 (measured, slice 2), so mixing them would silently degrade similarity.
The route is therefore part of the frozen bundle identity: **exactly one route for
both the rebuild and serving.** A route flip later is a new rebuild.

### 2.1 Measured gateway characteristics that shape the checks

From the lane's repeat measurement (`.agents/runs/embedding-model-switch-v2/repeat-noise-measurement.json`,
30 calls on the compatible route, 2026-09-21) and this slice's probe:

| Characteristic | Value | Consequence for this change |
|---|---|---|
| Same text, same route, repeated | repeat cosine **min 0.9988** over 30 calls — the gateway is **stochastic** | never compare vectors for byte equality; every identity check in §1 compares model id, dimension and point-set, and the recall gate is the only thing that can bound the semantic effect |
| Per-call latency (compatible route) | **median 0.204 s, p95 0.232 s** over 30 calls; first cold call 0.311 s | the rebuild's latency is not the bottleneck — the TPM ceiling is (runbook §estimates) |
| Cross-route cosine | **0.86 (zh-short), 0.929 (en-short), 0.932 (zh-document)** | confirms the one-route rule above; the earlier single-text probe read 0.808–0.920 |
| `dimensions` parameter | honoured: `dimensions: 512` returned 512-dim rows | 1024 is a *chosen* width, not a constraint; a 512 variant would be a new bundle **and** a new rebuild — explicitly out of scope |

## 3. Verification surface

| Property | How it is verified | Why not otherwise |
|---|---|---|
| Identity moves as one unit | unit + real-fixture tests (already green on the lane, `test_embedding_model_switch_v2.py`, 31 tests + the real pack/index refusal test) | a mismatch is a deterministic refusal, so unit-level evidence is sufficient |
| The new release's vectors come from the candidate | build-time guard (index request vs adapter) + matrix meta read-back + a probe of the persisted matrix (`dimension=1024`, `point_count=51026`) | deterministic |
| **Recall did not regress** | **scenario eval**: the frozen recall harness run twice against a scratch boot of the new pack, judged by `--diff` against the frozen pre-switch `baseline.json` **and** `control.json` | a vector-lane regression keeps the answer shape and only loses entities; unit tests and the behavioural replay gate cannot see it (`protocol.md` §2) |
| The pack boots on the fast path | `mount-receipt` `verification: receipt` + `mount_seconds` in the ~120 s class vs ~285 s when the reconstruction is replayed (`fastpath-check.py`) | the reader digest (interpreter + pydantic + `canonical_v2/*.py`) is what decides it |

Oracle strength (honest boundaries, from `protocol.md` §6/§9): the gate observes
**membership** of the recalled candidate set and the presence of labeled entities
in answers/citations. It does **not** observe rank movement inside the vector
top-k, answer precision, or multi-turn referent resolution. A regression that
keeps every expected entity but ranks the wrong evidence first passes this gate —
that risk is accepted and recorded, not hidden.

Mock boundaries: the rebuild uses the real gateway (the only external party);
the recall gate uses the real serving stack with the real web providers (that is
where its noise comes from). No part of the acceptance is a mocked provider.

## 4. The gate (plan §4, calibrated)

Artifacts frozen on `feat/recall-regression`
(sha256 in `acceptance.md`; if these bytes change, the calibration is invalid):

| Artifact | Role |
|---|---|
| `.agents/runs/embedding-model-switch/baseline.json` | pre-switch capture, 37/37 turns (`7af37a34…`) |
| `.agents/runs/embedding-model-switch/control.json` | second capture of the identical pre-switch configuration — the **measured noise floor** (`54a695ac…`) |
| `protocol.md` §6 / `noise-floor.md` §6 | the verdict rules after calibration |
| `apps/admin-console/scripts/eval_recall_canonical_v2.py` | the harness (`ed80f818…`) |

Rules that decide the switch:

* **FAIL (blocks cutover)**: a labeled entity that was in the candidate set *and*
  the answer before and is gone from both after; or the median vector-lane
  candidate count dropping > 30 % (measured run-to-run noise on this metric: 0).
* **REVIEW (human decision, recorded)**: candidate-only or answer-only entity
  loss, concept-string flips, probe GT loss, any case losing > 50 % of its vector
  candidates with an anchor ≥ 8, or a coverage gap (missing candidate layer).
* `--strict-concepts` restores the plan's literal reading (concept strings as hard
  assertions) — the control run shows that reading fires on noise alone, so it is
  a paper trail, not the gate.

Protocol: the pass is run **twice** and the **second** pass is judged; the first
only fills the web cache. Measured effect: 94 live provider calls / 0 timeouts
(warm) vs 323 / 17 (cold) — the cold condition is what injected 6 answer-layer
flips between two identical pre-switch runs.

## 5. Rebuild shape (ordered commands in the runbook)

`.agents/runs/embedding-model-switch-v2/rebuild-runbook.md` — derived from the
scripts that actually produced run16 and v1.1:

| Stage | Command source | Measured cost |
|---|---|---|
| fresh index marker | `build-run16.sh:66-87` (`prepare_isolated_index_target`) | seconds |
| disposable Postgres | `build-run16.sh:92-135` + alembic | minutes |
| full build (re-embed 51k, matrix, milvus, envelope) | `build-run16.sh:145-184` (the official `complete_candidate_runner.py`) | **≈6.5 h** wall clock for run16 (22:05:52→04:35:35, watchdog log); plan's planning figure 8 h. The candidate's embedding pass adds a TPM-limited remote phase (runbook §estimates) |
| v1 → v2 index conversion (drop Milvus, points into `lookup.sqlite3`) | `convert_index_to_v2.py` (thin CLI over `convert_isolated_index_to_v2`) | ≈5 min for 51k points (run16: `index-v3-v2-convert.log`) |
| pack seal (v2 contract, copies + manifest + dogfood open) | `build_serving_pack.py --pack-schema-version canonical-v2-serving-pack-v2` from **the serving tree** | **≈42 min** (v1.1 wall clock 42.08 min; run16 phases: `envelope_validate` 1926 s + `dogfood_open` 312 s, sum 40.4 min) |
| new serving bundle | `generate_run16_serving_bundle.py` pattern (`embedding_model_id` changes) | seconds |
| pack identity + fast path | `fastpath-check.py` + mount receipt | ≈120 s boot (fast path) |
| recall gate | `protocol.md` §3 (two passes + two diffs) | 2 × ~8–12 min + boots |
| cutover / rollback | serve-command file + restart | minutes |

## 6. Task split: one merged switch line

The switch needs code from three branches in the **same tree**, so the first
implementation task is a merge, not an edit:

* `v2/embedding-model-switch` — the candidate identities and their loaders (slice
  1 + 2, inert);
* `fix/embedding-lane-f1f2` — F1 (transport failures reach the lane's fail-open
  hook instead of being laundered into an integrity error) and F2 (`base_url` is
  resolved and excluded from the frozen comparison);
* the build line that carries the runner, the p4 source manifest and the gate root
  (`data/p4-serving-pack-rebuild`), and the serving line that carries the s12g
  launcher, the v2 sealer and the converter (both already contain `delivery-v1`).

Two interactions must be checked *after* the merge, because both branches touched
the same loader (`knowledge_build_isolated.py`):

1. F1's pass-through must cover the **new** provider branch: a transport failure
   from the gateway (compatible route) or the native client must surface as the
   builtin `TimeoutError`/`ConnectionError` to the lane, not as an integrity error;
2. F2's exclusion + `resolve_embedding_base_url` must apply to **both** new
   authorities (the gateway OpenAI-compatible one *and* the native one), and must
   not silently start treating `api_key_source` as configurable.

Both are testable in the merged tree (`test_embedding_lane_fail_open.py`,
`test_embedding_transport_classification.py`, `test_embedding_endpoint_resolution.py`,
`test_embedding_model_switch_v2.py`) — see `tasks.md` T2.4/T2.5. The pack's reader
digest is `sha256(python + pydantic + every canonical_v2/*.py)`, so the sealer must
run **from the merged serving tree with the deployment interpreter**
(3.12.12 / pydantic 2.12.5), or every later boot pays the ~285 s replay.

## 7. Cutover / rollback shape

New artifacts (all additive): new release id, new database, new index root (build
form + converted form), new sealed pack, new serving bundle, new serve-command
file. Untouched: `candidate-v2-20260916-r1`, `index-v3-v2`,
`serving-pack-run16-readerbound`, `serving-bundle-run16.json`, and the current
serve command (kept as the rollback copy, the way
`serve-18188-command.pre-run16.20260917-065458.sh` was kept).

* **Cutover** = write the new command file (new pack, index root + marker sha,
  embedding bundle, `--model-version embedding=qwen3.7-text-embedding-flash`, new
  serving bundle, new database, `CANONICAL_V2_EMBEDDING_API_KEY` supplied from the
  key file), restart 18188, confirm `/api/health` + one smoke query.
* **Rollback** = restore the previous command file, restart. Minutes. The new
  artifacts stay on disk; nothing about the old release was modified, so the
  rollback does not depend on the new build being correct.
* **Data-level rollback is not a thing** (the index is the data): that is why the
  old index root and pack must not be deleted or rewritten during the window.

## 8. Risks

| Risk | Mitigation / where it lands |
|---|---|
| flash recalls worse than Qwen3-8B | the gate (§4) blocks; the old pack remains the answer |
| gateway down / rate-limited mid-build | no checkpoint inside the embedding pass (`_BatchingEmbeddingAdapter`: in-memory cache, no retries) — a transport error aborts the build; plan the window with the TPM budget (runbook estimates) and re-run |
| per-request batch cap on the gateway route (DashScope's native route documents ≤25 texts; the compatible route is unverified at batch 32) | precheck `--batch-probe` (one extra call) before the window; a smaller `batch_size` in the bundle changes `content_sha256` ⇒ new bundle + constants update (T2.6) |
| third-party data retention / stability | plan §3 step 5; recorded as an operator decision, not an engineering gate |
| credential leakage to the third party | separate credential slot enforced by construction (§1 note 2 + R5); key rotation of the leaked slot is the operator's step |
| reader digest drift ⇒ 285 s boots | seal from the serving tree with the deployment interpreter; verified in T6 |
| recall-gate noise read as signal | the gate is calibrated against the measured noise floor and judged on a warm second pass (§4) |
