# Proposal: retire-star-domain-couplings

## Why

`star.sustech.edu.cn` (the campus gateway in front of **dbg21**, our machine
`100.64.0.34`) is going to be retired. Two kinds of coupling exist today:

1. **We call star** — code/config defaults that would resolve to
   `https://star.sustech.edu.cn/service/model/*`. Measured on 2026-10-15: the
   *live* lines on both machines make **zero** calls to star (a real question on
   gpu01:18188 produced connections only to `api.deepseek.com`,
   `google.serper.dev`, `api.bochaai.com`; the same for 100.64.0.96 during a
   keep-warm turn). What remains is a set of **dormant defaults**.
2. **Star fronts us** — `https://star.sustech.edu.cn/guoxian` → dbg21:3001 →
   gpu01:18188 (public demo entry, public+basic-auth zones).

Who used star's model paths (evidence, 2026-10-15): dbg21's access logs show
418–456 requests/day, flat across all 24 hours, Oct 1–11 — a scheduled
keep-warm profile. It collapsed on Oct 12 (157) / Oct 13 (45) / Oct 14 (29) and
is **0 today** (only a 3-request read-only probe). The pattern matches the
customer's pre-migration line (100.64.0.96 run-9: keep-warm = 144 turns/day,
its frozen embedding bundle records the star URL, and its `run.sh` hedge
defaults to `gemma4` with a "star 网关" comment); run-9's `serve.log` stops at
2026-10-12 16:41. Residual Oct 13/14 traffic includes `/service/model/mirothinker/*`
probes and is not fully attributed — the star-gateway owner must confirm client
IPs before the school closes anything.

User decisions (2026-10-15):

- **Scope**: retire *our own* couplings only — do **not** touch the campus model
  backends (`172.18.41.222` = tailnet `100.64.0.27`) nor other projects' apps on
  dbg21.
- **Entry**: `/guoxian` stays up until the school gives a shutdown date
  (registered, not removed today).
- **Target machine**: legacy run-9 line retires **with** star; delete the
  nginx embedding shim.
- **Local defaults**: change the defaults + add regression tests (this change).

## What changes

1. **Local default endpoints move off star, same model**:
   - `professor/llm_profiles.py`: `gemma4.local.base_url` →
     `http://100.64.0.27:1231/v1` (verified: that endpoint serves
     `qwen3.6-35b-a3b`, the same model star's `qwen36` path served). This single
     edit removes star from **every default** that resolves through the profile
     table: the 12 collection/seed scripts whose `--llm-profile` defaults to
     `gemma4`, `ADMIN_SEED_LLM_PUBLICATION_PROFILE`, and the monthly
     `miroflow-medium-rescan` guard.
   - `providers/rerank.py`: `_DEFAULT_RERANK_URL` →
     `http://100.64.0.27:18006` (the rerank service already used by the
     bare-metal kit's frozen fallback).
   - `deploy/preflight.sh` (bare-metal kit): `DEFAULT_LLM_URL` → the same local
     qwen36 endpoint (probe fallback only).
2. **Target machine (100.64.0.96)**: disable the nginx shim
   `/etc/nginx/conf.d/miro-embed-shim.conf` (listens on `100.64.0.27:18005`
   and proxies `/v1/*` to star's embedding path). It has served **0** requests
   (nginx logs contain no `embeddings` hit) and only existed to satisfy the
   frozen legacy address of the retired run-9 line. Backup + `nginx -t` +
   reload + verification.
3. **Invariants/tests**: a regression suite that fails if any *default* profile
   or the rerank default can resolve to `star.sustech`, plus an allowlist test
   naming the only remaining star endpoints (explicit, non-default options).
4. **Registration (no execution today)**: dbg21 `/guoxian` removal procedure +
   script; `deploy/README.md` notes the entry's retirement status.

## Impact / risks

- Nothing on the live query path changes: both live lines pin `deepseekv4flash`
  + the `qwen3.7-text-embedding-flash` gateway; the edited files are outside the
  serving package (`canonical_v2/*.py` untouched) so the sealed pack's
  reader-contract digest is unchanged (no re-seal, no slow-boot penalty).
- Collection/guard runs that default to `gemma4` keep the *same model* (campus
  host instead of the star gateway) — behaviour-equivalent, star-free.
- The customer's run-9 rollback line stops being able to serve embeddings once
  its shim is removed; it is inactive/disabled and explicitly retired with star
  (user decision).
- `qwen35`, `mirothinker`, `ark.local` profiles still point at star: no verified
  equivalent endpoint exists on our host, and **they are not defaults anywhere**;
  they are recorded in the allowlist test and will be repointed or deleted when
  the school turns the domain off.

## Out of scope

- The campus model backends (`172.18.41.222` / `100.64.0.27`) themselves.
- Other applications on dbg21 (`/zs-ai`, `/major-ai`, `/sucai`, …).
- Removing the star gateway's `/guoxian` rule (school-side; pending date).
- Changing the `CHAT_LLM_PROFILE` fallback constant inside
  `canonical_v2/*.py` (`gemma4`): that would change the sealed pack's reader
  contract digest and cost a 42-minute re-seal. Both live lines pin the profile
  explicitly (managed settings + `run.sh`); recorded as a follow-up to ride the
  next re-seal.
