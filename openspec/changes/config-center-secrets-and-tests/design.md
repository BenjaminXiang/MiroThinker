# Design: config-center-secrets-and-tests

## 1. Two files, one mechanism

W1 established `config/managed/settings.json` for non-sensitive operator values with the rule
`env > file > default`. Credentials cannot live there: the W1 schema rejects credential-shaped keys by
construction, and that rejection is load-bearing (it is what keeps the settings file safe to read,
print, diff and audit).

This slice therefore adds a sibling carrier with the same lifecycle and the same precedence rule:

| | settings | secrets |
|---|---|---|
| path | `config/managed/settings.json` | `config/managed/secrets.json` |
| override env | `CANONICAL_V2_MANAGED_SETTINGS` | `CANONICAL_V2_MANAGED_SECRETS` |
| mode | 0600 | 0600 |
| audit | `config/managed/audit.jsonl` (before/after values) | `config/managed/secrets-audit.jsonl` (names + tails only) |
| read | page shows values | page shows mask + configured + origin |
| consumed | startup bootstrap → environment | startup bootstrap → environment |

Nothing in this slice reads either file on a request path (R16: one uniform "read at service startup").

## 2. Precedence and origin

Resolution order for a connection credential: `env` → `managed secrets file` → `legacy key file`
(`.bocha_api_key`, `.serper_api_key`, …; read-only, never written by this slice).

The bootstrap writes file-owned values into `os.environ` **only when the variable is unset**, so the
service unit still pins behaviour. The read endpoint reports the origin so the operator can tell why a
value is winning:

- `env` — set in the environment and different from (or absent from) the managed file;
- `managed-file` — the file owns it (and the process picked it up at startup);
- `legacy-file:<name>` — an approved repository key file;
- `none`.

`applied_to_process_env` is reported separately, which is exactly what makes "settings → restart →
effective" observable without printing the credential.

## 3. Mask contract

`mask(value)` returns a rendering that reveals at most 3 leading and 4 trailing characters and is never
longer than 12 characters; anything shorter than 12 characters is rendered as `•••` + tail(4) or fully
hidden. The mask is a one-way display artefact: it is derived at read time and never stored. The audit
records the same tail only.

## 4. Connection tests

Five connections, each with a spec (key, label, kind, default base URL, default model, secret field,
env names). A test performs exactly one minimal call:

| connection | call | body |
|---|---|---|
| bocha | `POST https://api.bochaai.com/v1/web-search` | `{"query": "ping", "count": 1}` |
| serper | `POST https://google.serper.dev/search` | `{"q": "ping", "num": 1}` |
| rerank | `POST {base}/v1/rerank` | `{"model": …, "query": "ping", "documents": ["ping"], "top_n": 1}` |
| embedding | `POST {base}/v1/embeddings` | `{"model": …, "input": "ping"}` |
| llm | `POST {base}/v1/chat/completions` | `{"model": …, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}` |

Rules:

- **Values come from the request when supplied** (test-before-save), otherwise from the effective
  configuration/secret resolution. A supplied value is never persisted by the test route.
- The transport is injected (`post_json`), so unit tests use a fake and no real call is made.
- Only status, latency, error class and a sanitized reason are returned; response bodies are discarded.
  A 401/403 is reported as "reachable but rejected" (the endpoint answered).
- **Rate limit**: sliding window, per connection **and** per client, default 6/minute with a 1 s minimum
  interval. Rejection is HTTP 429 with `retry_after_seconds`; the transport is not called.

## 5. Startup bootstrap

```python
apply_managed_runtime_config(environ=None, *, settings_store=None, secrets_store=None) -> dict
```

- Projects every `serving`-section field **explicitly set in the file** into its environment variable.
- Projects every managed secret into its environment variable.
- Never overwrites an existing environment variable; counts `applied` / `skipped_env`.
- Returns paths + counts only (no values) so the receipt can be logged.
- Fail-open: an unreadable file is a no-op, never a boot failure.

Call sites: `open_serving_pack_authority()` (serving process, once per boot) and the V2 shell's FastAPI
startup event (admin-console process). Both are the "startup read" the page tells the operator about.

## 6. New switches — page-suitability judgement

| env var | managed field | page | reason |
|---|---|---|---|
| `CANONICAL_V2_WEB_TOPICAL_FLOOR` | `serving.web_topical_floor` | **editable** | kill switch / tuning knob whose value is a product-visible recall floor; the point of R16 is to change it without a shell session |
| `CANONICAL_V2_RERANK_TIMEOUT_SECONDS` | `serving.rerank_timeout_seconds` | **editable** | latency budget, bounded numeric range |
| `CANONICAL_V2_RERANK_MAX_DOCUMENTS` | `serving.rerank_max_documents` | **editable** | cost/latency bound, bounded numeric range |
| `CANONICAL_V2_SERVING_RECEIPT_PATH` | `serving.mount_receipt_path` | read-only display | forensics artefact path pinned by the service unit; showing it aids debugging, letting the page move it would silently scatter receipts |
| `CANONICAL_V2_TURN_DEBUG_DIR` | `serving.turn_debug_dir` | read-only display | debug-output directory; enabling it from a page writes raw turn dumps to disk — must stay an explicit deployment decision |
| `CANONICAL_V2_SERVING_FULL_VERIFY` | `serving.full_verify` | read-only display | boot-cost switch (full re-hash at startup); a page toggle would let an operator turn a 1 s boot into a multi-minute boot |
| `CANONICAL_V2_RERANK_BASE_URL` / `_MODEL`, `CANONICAL_V2_EMBEDDING_BASE_URL` / `_MODEL`, `LOCAL_LLM_BASE_URL` / `_MODEL` | already `extraction_endpoints.*` (W1) | **editable** | unchanged; the connection test consumes the same fields so endpoint edits can be probed before saving |

Read-only fields are still validated and return `editable=false` plus `readonly_reason` in the config
payload, so the page renders them disabled with the reason and never sends them in a patch.

## 7. Failure modes

| failure | behaviour |
|---|---|
| secrets file unreadable/corrupt | read endpoint reports `configured=false` + reason; bootstrap no-ops; no 5xx |
| file permissions looser than 0600 | read endpoint flags `permissions_ok=false` (page shows a warning); no plaintext involved |
| connection test timeout / transport error | `ok=false`, error class + latency; never an exception |
| rate limit exceeded | HTTP 429 + `retry_after_seconds`; no outbound call |
| unknown connection key | HTTP 422, field whitelist error |
| env var already set | bootstrap skips; origin reported as `env` |
