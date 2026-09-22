# Verification contract: admin-identity-native (the embedding card speaks both shapes)

Slice: the `/admin` embedding card's identity check (and its one-call transport
check) can validate a **DashScope-native** endpoint, not only an
OpenAI-compatible one. Branch `v2/admin-identity-native` off `ac44b404` (the
switch line), own worktree `.worktrees/v2-admin-identity-native`.

Written **before** production edits, per AGENTS §4 (TDD boundary).

## The gap, measured

The probe's only client speaks the OpenAI shape (`{base}/embeddings`). Against
the route the switch ships — `https://maas.qianwenaiapi.com/api/v1/services/embeddings/text-embedding/text-embedding`
— that shape answers **HTTP 404** (measured live 2026-09-22, empty body), so the
card reports 未校验 and validates nothing. The **connection test** speaks the same
shape, so it fails first and the card then *skips* the identity check outright
(`端点未通过连通性检查`), i.e. two layers block the same route.

## RED artifacts (must fail before the fix, pass after)

Each RED is named as `test file::test name` with its fixture source.

### Cluster A — the identity probe speaks the endpoint's shape

| # | RED assertion | Fixture source |
|---|---|---|
| A1 | against a native-only endpoint (compatible route 404, native route 200) the **index arm** passes, `checks["provider"] == "dashscope-native"`, and the native call carried **no** `text_type` (document role) | local mock endpoint (real HTTP, loopback), constructed pack |
| A2 | a native endpoint whose vectors are in another space still **fails** with `不要切换` | same mock, orthogonal vectors |
| A3 | a native route that rejects the credential (401) is 未校验 (`passed=None`), never a pass and never an exception | same mock: compatible 404, native 401 |
| A4 | the **reference arm** against two native endpoints sends `text_type="query"` on both calls and passes | two loopback mock endpoints |
| A5 | `checks` name the arm's role and the route: `role` = `document` (index) / `query` (reference), `provider` + `provider_evidence` present | same mocks |
| A6 | an endpoint that answers the compatible shape is **not** retried on the native route and its `checks["provider"]` is `openai-compatible` | mock answering only the compatible route |
| A7 | the console's native path literal equals the merged client's (`src.data_agents.providers.dashscope_embeddings`) | import comparison |

Failure mode before the fix: A1–A6 report 未校验 with `端点返回 HTTP 404` (the
probe never reaches the native route); A7 has no literal to compare.

### Cluster B — the card's one-call transport check reaches the native route

| # | RED assertion | Fixture source |
|---|---|---|
| B1 | the embedding connection test falls back to the native path when the compatible route answers 404/405, reports `ok=True` with the native status, and its detail names both statuses | fake transport returning 404 then 200 |
| B2 | an endpoint that answers the compatible route still costs **exactly one** call (no native probe) | fake transport, one recorded call |
| B3 | a 401 (credential) on the compatible route does **not** trigger the native attempt | fake transport: 401, one call |
| B4 | non-embedding kinds never retry a 404 (rerank/llm keep one call) | fake transport: 404, one call |

Failure mode before the fix: B1 returns `ok=False, http_status=404` after one
call, and the identity check is skipped by the API route's `result["ok"]` guard.

## Preservation (must not change)

- Both arms keep their roles: index = document, reference = query (existing
  tests `test_the_index_arm_embeds_the_stored_document`,
  `test_the_reference_arm_probes_the_query_side`).
- The OpenAI-compatible shape keeps its exact one-call-per-address behaviour and
  its `{model, input}` payload (existing `test_the_http_embedder_reads_an_openai_compatible_response`).
- No credential in any report, no upstream body echoed, floors unchanged.

## GREEN evidence beyond unit tests

AGENTS §6: this is retrieval-critical config surface, so a unit test alone is not
the whole story.

1. **Live route confirmation** (allowed once, `maas.qianwenaiapi.com`, credential
   read from the file, never printed): the probe's native call path returns 200 /
   1024 dims, and the query-vs-document separation reproduces — i.e. a wrong role
   would still be caught by the 0.99 floor. (Measured on the committed code, same
   probe text: **0.90083** with the role selector alone. The switch's own probe
   measured 0.912177 with the frozen `query_instruct` as well; this probe sends no
   instruct, because the console holds no bundle and therefore no frozen wording —
   the arm's claim is about the retrieval *side*.)
2. **A full live identity verdict is not reachable yet**: the mounted pack's
   vectors are the 4096-dim Qwen3-Embedding-8B index, while the candidate route
   answers 1024 dims, so the index arm correctly reports a dimension mismatch
   until the rebuilt (candidate-model) pack exists. Recorded as such, not
   claimed as a pass.
3. **The card's end-to-end path stays blocked by two facts outside this slice**
   (recorded for the parent's runbook, measured 2026-09-22):
   `resolve_embedding` still pins the model id `Qwen/Qwen3-Embedding-8B`, which
   the candidate gateway answers with 404 `Model not exist` on *both* routes, and
   the managed secrets page writes `embedding.api_key` into `SGLANG_API_KEY`
   while the bundle reads `CANONICAL_V2_EMBEDDING_API_KEY` (the switch's own
   open item).

### Cluster B, after the fact

B1 was the RED (the fallback did not exist). **B2–B4 were green before the fix
and are preservation pins**, not REDs: they hold the "one call per route, and only
for the embedding kind" rule that the fallback must not break.

## Regression baseline

`apps/admin-console/tests/test_embedding_identity_probe.py`,
`apps/admin-console/tests/test_canonical_v2_connection_tests.py` and the rest of
the admin-console suite, with the pre-existing (DB-driven) reds named by file.

## Out of contract

- Multimodal / non-text embedding routes, and any third wire shape.
- Reading the embedding bundle from the console process (it holds no bundle
  path): the shape is asked of the endpoint, never declared here.
- The gateway model id (`resolve_embedding`) and the credential slot wiring.
- Any edit to the bundle, the serving pack, the index, the live service, or the
  running build's worktree.
