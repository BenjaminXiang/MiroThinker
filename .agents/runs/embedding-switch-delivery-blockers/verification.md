# Verification: embedding-switch-delivery-blockers

Slice: the two facts that kept the `/admin` embedding card from validating the
switched endpoint, both of them delivery-promise failures (one key, no manual
edits). Branch `v2/admin-identity-native`, worktree
`.worktrees/v2-admin-identity-native`. Contract: `verification-contract.md` next
to this file. RED set captured before the implementation edits.

Untouched: the running build (`PID 2077915`, its worktree), the live service on
18188, `/var/tmp/mirothinker-data-v2/{staging-v4,index-v4}`, the live pack (read
only, see below), other agents' scratch, `docs/plans/`.

## ① Step 1 — who reads the hardcoded identity, and does the seal move

**`Qwen/Qwen3-Embedding-8B` is console-only.** `grep -rn` over `apps/` gives the
console (`canonical_v2_runtime_sources.py:312`, the embedding
`ConnectionSpec.default_model`) plus, in the agent tree, the *frozen bundle
literal* the loader compares against and the legacy per-domain vectorizers. The
only callers of `resolve_embedding` are the admin page's two paths
(`canonical_v2_admin_config.py`: `/connections/presets`, `/connections/test`); the
serving lane never calls it. The lane's own identity comes from the release
embedding bundle (`model_id`), which the loader binds to the pack manifest's
`embedding_model_id`.

**The dimension is not a gate on this card.** Every `4096` on the console path is
a comment; `_VECTOR_DIM = 4096` lives in the legacy collection/domain vectorizers.
The card's dimension comes from the probe's answer and from the index matrix.

**The seal moves for the credential fix, and only for it.**
`serving_pack_loader.reader_contract_digest()` = sha256 over the interpreter,
pydantic and **every** `apps/miroflow-agent/src/data_agents/canonical_v2/*.py`:

```
before 4ab79cdf882ed1522fa1f911ff05f35d44b92bb7f50d36395234547d3e24f1be
after  c260d0546e5c9f148727853dadbc78e073044d82fdfac389f78c432a6928cc10
```

The model-identity fix is console-only (`apps/admin-console/**`) → no digest
impact. The credential fix edits `canonical_v2/managed_secrets.py` → **it must be
merged into the switch line before the pack is sealed**, otherwise the sealed
pack's recorded digest differs from the running code and every boot re-runs the
reconstruction the seal exists to skip (a slowdown, not a refusal — the
docstring's ≈137 s of a 440 s boot, the parent's figure ≈285 s per boot).

Read-only check against the live **sealed** pack (no writes, no service touch):
it records `Qwen/Qwen3-Embedding-8B`, i.e. **today's live behaviour is unchanged**
by the model fix; the card only follows the record once the rebuilt candidate
pack is mounted. Cost of reading that record: 77 ms for the 11 MB manifest, on
the operator-initiated card paths only.

## ② Changes

| commit | files | what |
|---|---|---|
| A | `backend/services/canonical_v2_runtime_sources.py`, `backend/api/canonical_v2_admin_config.py` | the embedding model identity is resolved from the mounted pack's record (`_recorded_embedding_model`, fail-open, never invented), with the recorded authority's literal (`FROZEN_EMBEDDING_MODEL`) only as the no-pack fallback; the note reports the provenance. The page still cannot set it |
| B | `src/data_agents/canonical_v2/managed_secrets.py`, `backend/static/admin.js` | one page field now occupies **both** credential slots the fleet's two embedding authorities read (`SGLANG_API_KEY` for the recorded line, `CANONICAL_V2_EMBEDDING_API_KEY` for the candidate bundle's declared `api_key_source`), under the same "existing value wins" rule; the secrets payload and the page name both variables. The **read side is unchanged**: a bundle still reads only the slot it declared |
| C | the four test files + `tests/canonical_v2/test_embedding_credential_projection.py` (new) | see ③ |

## ③ Tests

New this round (13): 5 in the agent tree (the chain and its guards), 2 in
`test_managed_secrets_store.py`, 6 in `test_embedding_effective_endpoint.py`, 1 in
`test_embedding_identity_probe.py`; one existing test extended
(`test_secrets_payload_exposes_runtime_state_per_connection`). Fixtures: scratch
managed files, scratch pack manifests (four broken shapes), the real store, the
real startup projection, the real readers, the route graph with a faked probe.

RED before the fix (verbatim):

```
agent:   4 failed, 1 passed   ← the slot pin, the chain, the two-slot projection,
                                the env-wins rule; the trust-boundary pin passed
console: 6 failed, 75 passed  ← both model-resolution tests, the slot tests,
                                the payload's mirror list, the probe's model
```

GREEN after: agent `5 passed`; console `81 passed` in the four touched files;
`177 passed` across the eleven console files that touch the changed surface;
`16 passed` in the two agent files that import the changed modules.

Full admin-console suite (`-q -p no:randomly --tb=no -rf`):
**25 failed, 1575 passed, 31 skipped, 105 errors** — and the failing ids are
**byte-identical** to the pre-existing set recorded last round
(`diff` of the two sorted id lists: identical, 25 ids). Verbatim ids:
`admin-suite-after-failing-ids.txt` here; baseline:
`.agents/runs/admin-embedding-identity-native/admin-suite-failing-ids.txt`.

`ruff@0.8.0 check` + `format` on the touched files: clean.

## ④ Live evidence (2026-09-22, 3 network calls)

Driven through the committed code with a **scratch** pack record carrying the
candidate identity (a fabricated manifest: it proves the resolution, not the real
pack), the real managed store, and the real gateway key (read from the file,
never printed; only booleans and receipts are echoed):

```
① the card's resolved identity
   model: qwen3.7-text-embedding-flash | provenance clause present: True
   live test: {"ok": true, "latency_ms": 448, "http_status": 200,
               "detail": "HTTP 200（OpenAI 兼容路线 HTTP 404，改试 DashScope 原生路线）"}

② the page → service credential chain (values never printed)
   projection applied: ['SGLANG_API_KEY', 'CANONICAL_V2_EMBEDDING_API_KEY']
   candidate slot resolves the saved key: True
   recorded  slot resolves the saved key: True
   both are the key the page saved: True True
   receipt carries names only: True
   authenticated native call with the projected key: rows=1 dims=1024
```

Readings: with the identity taken from the record, the card's own first step now
answers 200 on the shipped route (before: 404 `Model not exist` on both routes
for the pinned id). The credential written through the store's page API reaches
both slots at startup and the candidate slot's value is accepted by the gateway
(200 / 1024 dims). No key, no masked tail and no upstream body was printed.

### ④b The card's verdict on the shipped route (2 more calls, 6 total)

The real index is the one being rebuilt (off-limits), so the pack was a **scratch**
one whose single stored vector is the live model's own answer for the probe
document (one call to store it, one by the probe itself). That exercises the same
comparison the arm makes against the rebuilt pack, minus its 51k rows:

```
arm: index | passed: True | cosine: 0.998833 | threshold: 0.99
provider: dashscope-native | role: document | dimension: 1024
evidence: compatible route absent (HTTP 404); spoke the native route
detail:   与索引同源：索引文档自比 cos=0.9988（阈值 0.99，抽样 0 行最近邻亦为本文档）
```

The cosine sits inside the measured repeat band (0.9980–1.0) and above the 0.99
floor the switch derived — a healthy gateway passes its own identity check. What
this does **not** claim: that the rebuilt pack's identity is right (it does not
exist yet); the arm's index here is scratch, not the pack under construction.

## ⑤ Not verified

- **The file (docker) route is still half-open**: the delivery mounts
  `secrets/.sglang_api_key` as a file
  (`deploy/docker/compose.yaml:144-145`) and the candidate reader is env-only, so
  a site that fills the key as a *file* does not reach the candidate slot. Closing
  it needs a deploy-side projection (mount the same file under the candidate name
  and export it in `deploy/docker/entrypoint.sh`, symmetric with the write-side
  rule above) — reported, not changed: it cannot be verified without building and
  running the image here.
- **The real index's verdict**: the mounted index is the old 4096-dim one, so a
  check against *it* would honestly report a dimension mismatch; and reading it
  would mean reading the live index the build is filling, which was out of bounds.
  The verdict above is the scratch-pack version.
- The **page hint** is pinned at string level (the repo's convention for
  `admin.js`), not by executing the page (`node --check` does parse the file).
- The **11 MB manifest read** per card interaction is measured (77 ms) but not
  cached; if the card ever becomes a polling surface that would need attention.

## ⑥ Honest judgement: can the customer fill one key?

**On the page route, yes** — with this slice, plus the two switch cutover items
that are not code: the switched pack must be mounted (that is what carries the
model identity now) and the pack must be sealed *after* this branch is merged.

**On the file route, not yet** — one deploy-side mapping is missing (⑤), and it is
the route `CONFIG-GUIDE.md` calls the "一次装完" path. Until it lands, the promise
holds only for operators who use `/admin`.
