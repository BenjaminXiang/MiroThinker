# Design: retire-star-domain-couplings

## D1. Fix the default in **one** place (profile table), not in 12 scripts

Twelve collection/seed scripts and the seed-refresh path default to the profile
name `gemma4`; its `local` endpoint was the star URL. Options:

| Option | Diff size | Behaviour | Verdict |
|---|---|---|---|
| Edit each script's default to `deepseekv4flash` | 12 files + seeds.py + guard unit | changes the model used by every internal batch job (and adds cloud cost) | rejected — wider blast radius, changes outputs |
| **Repoint `gemma4.local.base_url` to our own qwen36 host** | **1 file** | same model (`qwen3.6-35b-a3b`), same key slot (`API_KEY` / `.sglang_api_key`), same client | **chosen** — smallest, behaviour-equivalent, kills the default everywhere at once |

Probe evidence: `GET http://100.64.0.27:1231/v1/models` (repo key loader) returns
`['qwen3.6-35b-a3b']`; `GET https://star.sustech.edu.cn/service/model/qwen36/v1/models`
returns the same model. dbg21 also proxies `/service/model/qwen36/` to
`172.18.41.222:1231`, i.e. the star path is a front for the same campus backend.

## D2. Rerank default → `http://100.64.0.27:18006`

The legacy retrieval path (`deps.py::_get_reranker_client`) constructs
`RerankerClient()` with only a key; its class default was the star rerank URL.
`100.64.0.27:18006` is the same service class (`POST /rerank` answers 400 with
an empty body, i.e. the route exists) and is already the frozen fallback in the
bare-metal kit (`deploy/preflight.sh::FROZEN_RERANK_URL`).

## D3. Do **not** edit `canonical_v2/*.py` in this change

Six call sites in the sealed serving package fall back to
`os.getenv("CHAT_LLM_PROFILE", "gemma4")`. Editing them changes
`reader_contract_sha256` (python patch + pydantic + every `canonical_v2/*.py`
byte) and forces a 42-minute re-seal or a 137–190 s slow-boot penalty per start.
Both live lines pin `CHAT_LLM_PROFILE` explicitly (managed settings +
`run.sh`), and the kits pre-seed `chat_llm_profile=deepseekv4flash`; the
fallback is therefore unreachable in practice. Recorded as a follow-up to ride
the next re-seal. This keeps the change **digest-neutral**: no restart is
required for correctness, and the running service picks the new defaults up at
its next planned restart.

## D4. `qwen35` / `mirothinker` / `ark.local` stay on star (allowlisted)

No endpoint on our host currently serves `qwen3.5-35b-a3b` or
`mirothinker-1.7-235b-fp8` (port probe over the model host found only
`1231` / `18005` / `18006`). These profiles are **not defaults anywhere**, so
they neither break nor bind us when the domain closes; the allowlist test in
`tests/data_agents/test_star_domain_retirement.py` names them explicitly so no
new star default can slip in, and the follow-up list repoints/deletes them on
the school's shutdown date.

## D5. Target machine: disable the shim, keep a backup

`/etc/nginx/conf.d/miro-embed-shim.conf` (listen `100.64.0.27:18005` →
`https://star.sustech.edu.cn/service/model/embedding/v1/`) exists only because
the retired run-9 line's sealed bundle pinned `http://100.64.0.27:18005/v1`.
It has served zero requests. Retiring it = client decision ("run-9 retires with
star"): rename with a timestamp suffix (nginx only loads `*.conf`), `nginx -t`,
reload, then verify listener gone + site healthy + no star in `nginx -T`.

`gxzx-origin-map.conf` (mirror-era `map` for CSRF origin rewriting) is kept or
removed depending on whether the active snippet still references it (checked at
execution time; it makes no outbound calls either way).

## D6. dbg21 entry: prepare, do not execute

User decision: `/guoxian` stays until the school fixes a date. A ready-to-run
script (`deploy/retire-star-entry.sh`) does the backup → block removal →
`nginx -t` → reload → three-way verification, so the actual removal is a
one-command, reversible operation on the agreed day.
