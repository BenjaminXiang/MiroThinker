# Tasks: config-center-secrets-and-tests

## 1. Managed secrets store

- [x] 1.1 `managed_secrets.py`: whitelist of the five connection credentials with env names + legacy key
      files; `ManagedSecretsStore` with `describe` / `resolve` / `patch` / `clear` / `apply_to_environ`.
- [x] 1.2 Atomic write (tmp + `os.replace`) with mode 0600; append-only audit with names + 4-char tails.
- [x] 1.3 Mask helper: ≤ 3 leading, ≤ 4 trailing, ≤ 12 characters total; short values reduced further.
- [x] 1.4 Refuse credential material anywhere else (existing settings store rejection unchanged).
- [x] 1.5 `config/managed/secrets.example.json` template committed; runtime file git-ignored.

## 2. Startup bootstrap

- [x] 2.1 `managed_runtime.py`: `apply_managed_runtime_config()` — file-owned values only, env wins,
      value-free receipt, fail-open.
- [x] 2.2 Call from `open_serving_pack_authority()` (serving process).
- [x] 2.3 Call from the V2 shell startup event (admin-console process).
- [x] 2.4 `settings_status.py` reports the managed-secret origin in `--check-keys`.

## 3. Managed settings additions

- [x] 3.1 `serving` section (`web_topical_floor`, `rerank_timeout_seconds`, `rerank_max_documents`,
      `mount_receipt_path`, `turn_debug_dir`, `full_verify`) + env mapping.
- [x] 3.2 Per-field page policy: debug/boot-cost fields read-only with `readonly_reason`; patch rejects
      them.

## 4. Connection tests

- [x] 4.1 `canonical_v2_connection_tests.py`: five specs, one minimal call each, injectable transport,
      sanitized failures, latency.
- [x] 4.2 Rate limiter (sliding window, per connection + client, injectable clock/limits).
- [x] 4.3 Test-before-save: body values win over stored values and are never persisted.

## 5. Admin API + page

- [x] 5.1 `GET/PATCH /api/canonical-v2/admin/secrets` (mask-only payload, `restart_required`).
- [x] 5.2 `POST /api/canonical-v2/admin/connections/test` (429 on rate limit).
- [x] 5.3 `admin.html`: credentials card (mask/status/origin, write-only input, save/clear/test,
      latency + rate feedback, restart notice).
- [x] 5.4 W1 surfaces unchanged (`/admin`, `/config`, `/system-status`, `/providers/health-check`).

## 6. Verification

- [x] 6.1 `verification-contract.md` written before production code (RED assertions R1–R9).
- [x] 6.2 Unit + HTTP tests for R1–R9 (`test_managed_secrets_store.py`,
      `test_managed_runtime_bootstrap.py`, `test_canonical_v2_connection_tests.py`,
      `test_canonical_v2_admin_secrets_api.py`).
- [x] 6.3 E2E on scratch port 18297 + scratch config dir (set → mask → test → clear → set again).
- [x] 6.4 Admin-console suite before/after failure-set comparison (no new red).
- [x] 6.5 Evidence + human log + index row + ledger entry.

## 7. Documentation

- [x] 7.1 `docs/plans/2026-09-15-config-center-secrets-log.md` (Chinese, append-only).
- [x] 7.2 `docs/plans/index.md` row.
- [x] 7.3 `openspec/change-ledger.md` entry.

## 9. Runtime alignment (follow-up, 2026-09-15)

- [x] 9.1 `canonical_v2_runtime_sources.py`: resolve endpoints/credentials through the
      serving code paths (5 connections), with file:line pointers in the module docstring.
- [x] 9.2 Remove the invented defaults: rerank/embedding/LLM endpoints come from the
      runtime, never from a page-side guess; rerank reports "not enabled" without a call.
- [x] 9.3 Credential metadata: `embedding.api_key` → `SGLANG_API_KEY` (+ `API_KEY`/
      `OPENAI_API_KEY` as resolution aliases), `llm.api_key` → the active profile's
      `api_key_env` (per-process), `rerank.api_key` unchanged (`CANONICAL_V2_RERANK_API_KEY`).
- [x] 9.4 Effective-now vs pending-restart reporting; probe prefers the just-saved value
      and labels it `managed-file(pending-restart)`.
- [x] 9.5 Page: runtime pill + note per connection, runtime endpoint/model placeholders,
      "未发起调用" surfacing.
- [x] 9.6 Tests: `test_canonical_v2_runtime_sources.py` (13) incl. an anti-drift
      cross-check against `resolve_professor_llm_settings`; ambient credential scrubbing
      and value redaction in the API test recorder.
- [x] 9.7 Re-run the five-connection acceptance (real endpoints, ≤1 call each) and record
      it: bocha/serper/embedding/llm OK, rerank reported as not enabled (0 calls).
- [x] 9.8 Evidence + human log + ledger updated.
- [ ] 9.9 Deploy: requires one 18188 restart (scheduled by the user; not performed here).

## Deferred (explicitly not done in this slice)

- [ ] 8.1 Hot reload of any value (out of scope by R16).
- [ ] 8.2 Real-endpoint connectivity calls from automated tests (manual only, counted).
- [ ] 8.3 Restarting the live 18188 service so the new routes/page go live (deployment step, needs the
      replay gate + explicit go-ahead).
