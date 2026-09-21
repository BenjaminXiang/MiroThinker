# Spec delta (reading copy): switch-embedding-model-to-qwen37-flash

The machine-validated deltas live in
`specs/canonical-v2-embedding-identity/spec.md` (new capability
`canonical-v2-embedding-identity`; `openspec validate --strict` is the check).
This file is the one-screen summary for a reader who wants the *what must hold*
without the scenarios.

## Added capability: `canonical-v2-embedding-identity`

| # | Requirement (short form) | Enforced by |
|---|---|---|
| R1 | One embedding authority governs a release, its index and its boot: model + dimension + bundle hash + route + credential slot agree everywhere; crossed pairs are refused | `_ACCEPTED_EMBEDDING_AUTHORITIES`, index-request guard, matrix read-back, pack manifest check, serving-bundle check |
| R2 | The gateway route is part of the frozen identity — one route for rebuild *and* serving; the address may be configured, the identity may not | the two frozen bundles; `resolve_embedding_base_url` (F2) excludes only `base_url` |
| R3 | The cutover requires the calibrated recall non-regression gate: run twice, judge the second, FAIL blocks, REVIEW is a recorded human decision, debug/trace dirs mandatory | `apps/admin-console/scripts/eval_recall_canonical_v2.py` + `protocol.md` |
| R4 | The switch is reversible from artifacts on disk: pre-switch pack/index/bundle stay byte-identical; rollback = restore the command file + restart | rollback anchor checks in the runbook + precheck |
| R5 | The gateway credential is its own slot (`env:CANONICAL_V2_EMBEDDING_API_KEY`); the local slot never travels to a third-party host; no secret in artifacts or logs | bundle `api_key_source` + `_GatewayOpenAICompatibleEmbeddingAdapter` |
| R6 | The switch changes the embedding identity only: same source manifest, same restore root, same objects and row counts | runner's manifest-hash gate + the post-rebuild inventory comparison (T6.4) |

## What this delta deliberately does not claim

* Nothing about rank quality inside the vector top-k (the harness observes
  membership only — `protocol.md` §6 "honest approximation").
* Nothing about latency SLOs on the switched line beyond recording the measured
  per-call cost (0.28–0.31 s remote) — latency is not a gate here.
* Nothing about the third-party gateway's retention/stability policy — that is an
  operator/compliance decision recorded in the plan (§3 step 5), not a spec
  requirement.
