# Verification contract: embedding-switch-delivery-blockers

Slice: the two facts that kept the `/admin` embedding card from going green on
the switched line, both of them **delivery-promise** failures ("只填一个 key，
其它都不用手动改" — `deploy/docker/CONFIG-GUIDE.md`, and the customer-site
delivery plan):

1. **the model identity was a literal** (`Qwen/Qwen3-Embedding-8B`) in the
   console's embedding resolution, so the card tested the switched endpoint with
   a model the gateway refuses (404 `Model not exist` on both routes);
2. **the page's `embedding.api_key` filled `SGLANG_API_KEY`** while the candidate
   (gateway) bundle reads `CANONICAL_V2_EMBEDDING_API_KEY`, so a site that filled
   the key once starved the switched lane.

Branch `v2/admin-identity-native`, worktree `.worktrees/v2-admin-identity-native`
(own; the running build's worktree, the live service, the live pack/index and the
live state dirs are untouched).

RED set captured **before** the implementation edits (this file was committed
with the slice; the RED output is quoted verbatim in `verification.md`).

## Facts that fixed the blast radius (step 1)

| question | answer (evidence) |
|---|---|
| who reads the model literal? | only the admin console: `resolve_embedding` (via `resolve_connections`) and the embedding `ConnectionSpec.default_model`. `grep -rn "Qwen/Qwen3-Embedding-8B" apps/ --include=*.py` → console (2) + the agent tree's frozen bundle literal and the legacy per-domain vectorizers |
| does the **serving** process read it? | no. `resolve_embedding` is called only from `canonical_v2_admin_config.py` (`/connections/presets`, `/connections/test`). The lane's identity comes from the release embedding bundle (`model_id`), which the loader checks against the pack manifest |
| is 4096 a gate on the card? | no. The only `4096` on the console path are comments; `_VECTOR_DIM = 4096` lives in the legacy collection/domain vectorizers |
| does the fix change the pack seal? | the model fix: **no** (console files are outside the digest). The credential fix: **yes** — `reader_contract_digest()` hashes every `apps/miroflow-agent/src/data_agents/canonical_v2/*.py`, and `managed_secrets.py` is one of them. Digests: before `4ab79cdf882ed1522fa1f911ff05f35d44b92bb7f50d36395234547d3e24f1be`, after `c260d0546e5c9f148727853dadbc78e073044d82fdfac389f78c432a6928cc10` |

Consequence recorded for the parent: **the credential change must be merged into
the switch line before the pack is sealed.** A sealed pack whose recorded digest
differs from the running code re-runs the reconstruction the seal exists to skip
(≈285 s per boot, per the switch's own measurement; a mismatch is a slowdown, not
a refusal).

## RED assertions (fail before, pass after)

Cluster A — the model identity follows the record:

| # | RED assertion | fixture |
|---|---|---|
| A1 | `resolve_embedding(...).model` equals the model in the mounted pack's `manifest.json` (`embedding_model_id`) | scratch pack dir + constructed environ |
| A2 | without a pack (or with a missing / malformed / non-string / blank record) the recorded authority's literal stands, and nothing raises | scratch pack dirs, four broken shapes |
| A3 | `/connections/presets` reports the record's model and its provenance | FastAPI client over scratch managed files |
| A4 | the card's identity probe is called with the record's model | route graph + faked probe |

Cluster B — one page field fills both credential slots:

| # | RED assertion | fixture |
|---|---|---|
| B1 | `embedding.api_key` projects into `SGLANG_API_KEY` **and** `CANONICAL_V2_EMBEDDING_API_KEY` | real store over a scratch managed file |
| B2 | the whole chain: page write → managed file → `apply_managed_runtime_config` → `_load_gateway_embedding_api_key()` and `load_local_api_key()` both resolve the value | same, plus the real readers |
| B3 | an existing environment value wins in **either** slot; the receipt carries names only | constructed target environ |
| B4 | the spec's mirror name is the loader's own constant (drift pin) | import comparison |
| B5 | the secrets payload exposes the mirror list, and the page names both variables | API client + static read |
| B6 | preservation: the gateway slot stays the **only** slot a candidate bundle may read — no fallback to the self-hosted key (this is why the fix is on the write side) | monkeypatched environ |

## Out of contract

- The serving lane's own credential resolution (`_load_gateway_embedding_api_key`
  reads its declared slot and nothing else) — deliberately unchanged.
- Widening the page's ability to *choose* a model id or a dimension: the identity
  stays frozen and read-only; only its *source* changed (pack record).
- The docker **file** route (`secrets/.sglang_api_key` mounted as a file): the
  candidate slot has no file carrier, so that route still needs a deploy-side
  mapping (reported, not changed here — it cannot be verified in this
  environment).
- Anything under `docs/plans/`.
