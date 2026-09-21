# Proposal: embedding-endpoint-configurable-and-lane-fail-open

## Why

A customer-site deployment must serve from a network that **cannot reach the
school's internal embedding machine**. On that box every ordinary question dies
with a red failure bubble instead of being answered from the four healthy lanes.
This is the migration blocker for the serving stack; it is two separate defects
that happen to meet on the same lane.

Verified by code reading on the live tree `.worktrees/canonical-v2-s11-consolidation`
(HEAD `36df47b8`):

| Seam | Observed behavior | Consequence |
|---|---|---|
| `knowledge_serving_isolated.py:663` | ordinary questions always plan `("exact","structured","lexical","vector","web")` | the vector lane runs on **every** ordinary turn |
| `company/vectorizer.py:50` (`EmbeddingClient.embed_batch`) | the address is the hardcoded default `http://100.64.0.27:18005/v1`; `load_content_addressed_embedding_adapter` pins the same literal in the bundle | unreachable from the customer network |
| `knowledge_read_isolated.py:325-331` | `_ValidatingEmbeddingAdapter.embed_batch` wraps `except Exception` into `IsolatedKnowledgeReadIntegrityError` | a TCP connect failure is laundered into an **integrity** failure (the two are not the same thing) |
| `knowledge_read.py:7546-7562` | `_invoke_lane` already fails open on builtin `TimeoutError` → `"timeout"` and `ConnectionError` → `"connection_failure"` | the hook exists but never fires: httpx raises `httpx.ConnectError` / `httpx.ReadTimeout`, which are not the builtins, and the laundering above replaces them anyway |
| `knowledge_read.py:7690-7698` | non-web lanes get `timeout_seconds=None` (no outer cap) | a black-holed route holds the turn until the client's 180 s timeout |
| `apps/admin-console/backend/services/canonical_v2_runtime_sources.py:281-330` | `resolve_embedding` constructs `EmbeddingClient()` (the frozen default) and reports `endpoint_origin="release-bundle-frozen"` | the operator connection test probes an address the operator cannot change; `CANONICAL_V2_EMBEDDING_BASE_URL` has **no reader** |
| `managed_config.py:107-112` | the field is listed in `PAGE_READONLY_FIELDS` with copy stating "no runtime reader; saving changes nothing" | the page tells the operator the endpoint is frozen |

User-level statement of the goal: **a customer box whose embedding endpoint is
unreachable must still answer from the other four lanes, and an operator must be
able to point the embedding endpoint at the customer's own address without
rebuilding or resealing the serving pack.**

## What changes

Two independent fixes (`F1`, `F2`) that meet on the same lane.

### F1 — the vector lane must degrade, not kill the turn

Behavior-affecting. Owner capability: `canonical-v2-serving-runtime`.

1. **Transport failures are normalized at the layer that speaks HTTP.**
   `company/vectorizer.py` (`EmbeddingClient.embed_batch`) translates
   `httpx.TimeoutException` → builtin `TimeoutError` and
   `httpx.TransportError` / `OSError` / `httpx.HTTPStatusError` → builtin
   `ConnectionError`, preserving `__cause__`. Nothing else is reclassified:
   integrity and validation errors keep their own types.
2. **The validating adapter stops laundering transport failures.**
   `_ValidatingEmbeddingAdapter.embed_batch` lets builtin `TimeoutError` /
   `ConnectionError` pass through unchanged and keeps wrapping everything else as
   `IsolatedKnowledgeReadIntegrityError`, so a genuine integrity failure still
   fails the turn closed.
3. **The vector lane gets an outer wait cap.** `KnowledgeRead.execute` applies an
   outer wait to the `vector` future the way it already does for `web`
   (wall-clock cap `CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS`, default 8 s). A
   black-holed endpoint must not hold a turn for 180 s.
4. **A short consecutive-failure breaker.** After 2 consecutive vector-lane
   transport failures the lane is skipped for a 300 s window and is reported in
   the retrieval trace as `status="unavailable"` with a transport `failure_kind`
   instead of being attempted on every turn. The provider keep-warm path
   (`knowledge_serving_isolated.py` idle warm cycle) consults the same state so a
   down endpoint costs one skipped warm call, not one failure per 5-minute cycle.

Degradation is **visible but not alarming**: the trace lane row records
`status="unavailable"` + `failure_kind`, the access log keeps its normal
`succeeded`-class status, and the user receives a normal answer built from the
remaining lanes. No red error is surfaced to the user for this case.

### F2 — freeze the embedding identity, not the address

Behavior-affecting. Owner capability: `canonical-v2-serving-runtime` (+ the
admin config surface, `admin-config-console`).

1. **One resolution point for the effective base URL.**
   `load_content_addressed_embedding_adapter` resolves the effective endpoint as
   `CANONICAL_V2_EMBEDDING_BASE_URL` (the managed field
   `extraction_endpoints.embedding_base_url`, projected into the process
   environment at startup by `managed_runtime`) when set, otherwise the address
   recorded in the embedding bundle. No new managed-config field.
2. **The frozen check keeps the identity and drops the address.**
   `load_content_addressed_embedding_adapter` still requires
   `content_sha256 == _QWEN_EMBEDDING_BUNDLE_SHA256`, the frozen `model_id`, and
   `dimension == _QWEN_EMBEDDING_DIMENSION`; the bundle document's remaining
   fields stay compared field-by-field. `base_url` is accepted from the resolved
   source if it is a non-empty `http(s)` URL. **No bundle edit, no reseal, no
   rebuild.** The matrix binding (`content_sha256`) is untouched.
3. **The admin surface reports and tests the effective address.**
   `resolve_embedding` resolves the same precedence, reports the matching
   `endpoint_origin`, and therefore the connection test probes what serving will
   actually use. The page copy no longer claims the endpoint is frozen, and the
   managed field becomes editable (it now has a runtime reader).
4. **Boring.** No new abstraction layer; the existing managed-config plumbing
   (`_FIELD_ENV_VARS` → `apply_managed_runtime_config`) is the only mechanism.

## Out of scope / invariants

- **No serving-pack, bundle or index change.** `run16-readerbound` and its
  `content_sha256` values are untouched; nothing is resealed.
- **Integrity failures still fail closed.** Wrong dimension, non-finite vector,
  model-id mismatch, non-determinism, matrix/point drift and the frozen-hash
  comparison are unchanged; only *transport* failures degrade the lane.
- **No new managed-config field**, no new dependency, no new service.
- The collection/build scripts' own `EMBEDDING_BASE_URL` override is untouched.
- Other lanes' behavior (exact/structured/lexical/relationship/web) is untouched.

## Spec delta

See `spec-delta.md` (capability `canonical-v2-serving-runtime`, ADDED/MODIFIED
requirements).

## Verification

- RED artifact: `.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.
- New tests: transport-vs-integrity classification, fail-closed integrity,
  outer-wait cap, breaker open/close, base-url precedence, frozen-check field
  relaxation.
- Real end-to-end probe: a scratch serving instance driven through
  `/api/chat/stream` with `CANONICAL_V2_EMBEDDING_BASE_URL` pointed at a
  black-hole address, then with the real endpoint — raw SSE frames, trace lines
  and wall-clock recorded in `.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification.md`.
- Human-readable log (parent-owned): `docs/plans/` — this change does not write there.
