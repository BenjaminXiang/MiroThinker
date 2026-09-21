# Proposal: switch-embedding-model-to-qwen37-flash

## Why

**User decision (2026-09-21)**: the serving-side embedding model moves from the
self-hosted `Qwen/Qwen3-Embedding-8B` (4096-dim, `http://100.64.0.27:18005/v1`) to
`qwen3.7-text-embedding-flash` (1024-dim) on the third-party MaaS gateway
`maas.qianwenaiapi.com`. Plan of record:
`docs/plans/2026-09-21-embedding-model-switch-plan.md` (Chinese, human-side);
this change is its agent-side contract.

**Why this is a rebuild and not an address change** (measured 2026-09-21, plan §2):
the candidate's vectors are in a *different space* from ours — truncated to 1024
dimensions and normalized, our Qwen3-8B vectors score **cosine ≈ −0.03**
(orthogonal) against the candidate's, and the candidate rejects
`dimension: 4096` with HTTP 400. One index therefore cannot be read with the
other model: the whole 51,026-point index has to be re-embedded.

**Why do it anyway**: the vector matrix shrinks ≈4× (1,680 MB → ≈420 MB, measured
from the live `vector_matrix.npz`), the serving path stops depending on a
self-hosted GPU endpoint, and the model is a cheaper/higher-throughput tier
(TPM 1M / RPM 24K per the plan). The cost is a measured +0.28 s per query on the
embedding call and a **lightweight model, so recall may drop** — which is what
the acceptance gate below exists to decide.

**What is already done and inert** (`v2/embedding-model-switch`, commits
`d99ad726`, `11a29984`, `7ea495a8`, `17404d7a`; nothing selects or loads it):

| Frozen piece | Where |
|---|---|
| DashScope-native client (fallback route) | `apps/miroflow-agent/src/data_agents/providers/dashscope_embeddings.py` |
| Gateway-slot OpenAI-compatible adapter (recommended route) | `knowledge_build_isolated.py` (`_GatewayOpenAICompatibleEmbeddingAdapter`) |
| Candidate bundle, native route (`content_sha256 cdddcdfd…`, 1024) | `.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json` |
| Candidate bundle, compatible route (`content_sha256 45e45855…`, 1024) | `.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1-openai-compat.json` |
| Accepted `(sha256, dimension)` authorities + three-layer fail-closed pair guards | `knowledge_build_isolated.py` (`_ACCEPTED_EMBEDDING_AUTHORITIES`) |

So this change expects **no new embedding code**: it is an identity/data switch —
rebuild the index with the candidate, seal a new pack, prove recall did not
regress, cut over, keep the old artifacts for rollback.

## What changes

1. **The embedding identity the release is built with** — `embedding_model` in the
   release policy, the vectors in `vector_matrix.npz` (51,026 × 1024), and the
   `embedding_model_id` in the pack manifest and the serving bundle all become the
   candidate's.
2. **A new release triple on disk**: new disposable build database, new index root
   (v1 Milvus form for the build, converted to the v2 no-Milvus form for serving),
   new sealed serving pack. The pre-switch release (`candidate-v2-20260916-r1`,
   `index-v3-v2`, `serving-pack-run16-readerbound`) stays untouched as the
   rollback anchor.
3. **The credential slot**: the candidate's key is read from
   `env:CANONICAL_V2_EMBEDDING_API_KEY` (the local slot `load_local_api_key()` —
   `API_KEY`/`OPENAI_API_KEY`/`SGLANG_API_KEY`/`.sglang_api_key` — must never be
   handed to the gateway host). The admin config page's embedding card currently
   only publishes the local slot (`embedding.api_key` →
   `canonical_v2_runtime_sources.resolve_embedding`), so the new slot needs a
   delivery path (key file or managed-secret entry) before cutover.
4. **The acceptance gate**: the switch ships only if the calibrated recall
   non-regression gate (plan §4 — baseline/control frozen on
   `feat/recall-regression`, rules re-calibrated against a measured noise floor)
   passes on a scratch instance booted with the new pack. Any **FAIL blocks the
   cutover**; a **REVIEW** is a recorded human decision.
5. **Cutover and rollback**: the operator's serve-command file is repointed at the
   new pack/index/bundle and the process restarted; rollback is restoring the
   previous command file and restarting (minutes, no rebuild).

## Behavior-affecting

**Yes.** The answer shape, planner, fusion, prompts and citation contract are
unchanged, but the *semantic recall surface* behind them is rebuilt: the same
question may recall different companies/papers. The owning capability is the new
`canonical-v2-embedding-identity` (this change adds it); no existing capability's
requirements change. Verification surface = scenario eval (the recall harness's
before/after diff), **not** unit tests: a vector-lane regression shows up as
"same answer shape, fewer of the right entities" and is invisible to unit tests
and to the behavioural replay gate (`protocol.md` §2).

## Out of scope

- The **human-side plan/index/log** (`docs/plans/`) — owned by the orchestrator.
- **Route flips after the rebuild**: both gateway routes are frozen as bundles,
  but exactly one route must be used for rebuild *and* serving (the routes are
  not the same pipeline: same text, cosine 0.808–0.920 between them). Choosing
  the other route is a new rebuild, not a config change.
- **Any other model** in the serving path (planner, answer synthesis, rerank,
  web providers) and the pre-canonical Milvus/PG retrieval stack.
- **Data changes**: the rebuild consumes the same frozen source manifest and the
  same accepted restore root as run16; no source data, cleaning rule, projection
  or quality gate changes here.
- **Deployment automation**: no systemd/port change; the cutover is the operator's
  documented restart, and this change is prepared and gated — not deployed.
- **The key rotation of credentials that appeared in chat** (plan §3 step 5) is
  executed by the operator outside this change's artifacts.
