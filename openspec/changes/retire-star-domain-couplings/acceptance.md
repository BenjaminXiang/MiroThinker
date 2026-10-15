# Acceptance: retire-star-domain-couplings

## Slice 1 — local defaults (must all hold before Candidate)

- A1. `resolve_professor_llm_settings(profile_name="gemma4",
  apply_endpoint_env_overrides=False)["local_llm_base_url"]` contains no
  `star.sustech` and equals `http://100.64.0.27:1231/v1`.
- A2. `providers/rerank._DEFAULT_RERANK_URL` contains no `star.sustech` and
  equals `http://100.64.0.27:18006`.
- A3. Every profile name used as a **default** in
  `apps/miroflow-agent/scripts/*.py` and in the seed-refresh path resolves to a
  non-star `local_llm_base_url` (source-scan test, self-maintaining).
- A4. The only profiles whose `local` endpoint still contains `star.sustech`
  are exactly `{qwen35, mirothinker, ark}` (allowlist test; these are
  non-default options).
- A5. New tests: RED before the edits (reproducing the star default), GREEN
  after; adjacent suites (`tests/providers/test_rerank.py`,
  `tests/data_agents/professor/test_llm_profiles.py`, the console suite that
  covers the seed publication profile) stay green.
- A6. Fresh-process check: importing the edited modules in a new interpreter
  prints non-star endpoints for gemma4 + rerank.
- A7. Digest neutrality: `git diff` touches no `canonical_v2/*.py`; the live
  serving pack's reader-contract digest is unchanged (no re-seal needed).

## Slice 2 — target machine shim

- B1. `miro-embed-shim.conf` renamed to a timestamped `.bak` and **not loaded**
  (`nginx -T` has no star reference).
- B2. No process listens on `100.64.0.27:18005`; `nginx -t` passes.
- B3. Site health after reload: `http://127.0.0.1:18188/api/health` = 200,
  `/chat` = 200, one real question answered with no `event: error`.
- B4. A passive connection capture on the service pid during a keep-warm turn
  shows no connection to `172.18.24.245` (star).
  **Evidence**: 3.5-minute capture before the shim removal (2026-10-15,
  16:11–16:16 CST) — outbound = DeepSeek (116.196.150.245 / 119.188.175.46),
  Serper, Bocha, localhost; **star count 0**. After the removal the only
  star-facing server block on the machine is gone (`nginx -T` = 0 star lines),
  which is strictly stronger for this port; a fresh post-removal capture was
  not run because the deploy in progress (see log) makes app-side timing
  noisy.

## Slice 3 — registration

- C1. `deploy/retire-star-entry.sh` exists, is idempotent, and is documented as
  "not executed yet" in `deploy/README.md`.
- C2. Human docs written: plan + log + index line (Chinese), cross-linked to
  this change; OpenSpec proposal/design/tasks/acceptance in English.

## Not accepted by this change

- Removing the school-side `/guoxian` gateway rule (external dependency).
- Repointing `qwen35` / `mirothinker` / `ark.local` (no verified endpoint).
- Editing the `canonical_v2` fallback constant (needs a re-seal).
