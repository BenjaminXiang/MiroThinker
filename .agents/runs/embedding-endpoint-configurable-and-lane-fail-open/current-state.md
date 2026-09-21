# Current state (before implementation)

Worktree: `.worktrees/embedding-lane-f1f2`, branch `fix/embedding-lane-f1f2`,
based on the live tree's HEAD `36df47b8` (verified by code reading there).

## What the running stack does today

Ordinary questions are planned by `knowledge_serving_isolated.py:663` with five
lanes `("exact","structured","lexical","vector","web")`. The vector lane embeds
the query through `_ValidatingEmbeddingAdapter`
(`knowledge_read_isolated.py:280`) → `_OpenAICompatibleEmbeddingAdapter`
(`knowledge_build_isolated.py:7967`) → `EmbeddingClient` from
`company/vectorizer.py` (imported at `knowledge_build_isolated.py:47` as
`_OpenAIEmbeddingClient`). The address is the bundle's frozen literal
`http://100.64.0.27:18005/v1`.

On a network that cannot reach that host:

1. `httpx` raises `httpx.ConnectError` / `httpx.ReadTimeout` (not the builtins).
2. `_ValidatingEmbeddingAdapter.embed_batch` (`knowledge_read_isolated.py:325-331`)
   catches `Exception` and re-raises `IsolatedKnowledgeReadIntegrityError`.
3. `_invoke_lane` (`knowledge_read.py:7546-7562`) fails open only on the builtins,
   so it never fires; the integrity error escapes the future and propagates out of
   `execute()`.
4. `KnowledgeReadIntegrityError` is caught in
   `apps/admin-console/backend/api/canonical_v2_chat.py:434-451` and turned into
   `enqueue("error", {"detail": "canonical_v2_release_mismatch"})` — the red bubble.
5. `execute()` gives non-web lanes `timeout_seconds=None`
   (`knowledge_read.py:7690-7698`), so a black-holed route holds the turn until the
   client's 180 s timeout.

The endpoint cannot be moved: `CANONICAL_V2_EMBEDDING_BASE_URL` is projected from
the managed setting `extraction_endpoints.embedding_base_url`
(`managed_config.py:74`) but has **no reader**; the bundle loader compares the whole
document including `base_url` (`knowledge_build_isolated.py:8186-8199`); the admin
resolver reports the frozen default (`canonical_v2_runtime_sources.py:281-330`) and
the field is display-only (`PAGE_READONLY_FIELDS`).

## Baseline facts used by the verification contract

- `httpx.__version__ == 0.28.1`; `TimeoutException → TransportError →
  RequestError → HTTPError → Exception`; `ConnectError → NetworkError →
  TransportError`; `ReadTimeout → TimeoutException`.
- The embedding bundle at `.../s12c/qwen-embedding-bundle-v1.json` records
  `base_url: http://100.64.0.27:18005/v1`, `model_id: Qwen/Qwen3-Embedding-8B`,
  `dimension: 4096`, `content_sha256: 05473fab…`, `timeout_seconds: 180`.
- Serving probe assets: pack `/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound`,
  index root `/var/tmp/mirothinker-data-v2/index-v3-v2`, serve wrapper
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/serve_s12e_port.py`.

## Scratch-instance rules observed

- Never bind `18188` (live), never touch the live/commented trees' `.git`.
- Scratch port from the 1828x/1829x range; scratch state dirs under `/var/tmp`.
