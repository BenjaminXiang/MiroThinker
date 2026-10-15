# Change log: retire-star-domain-couplings

## 2026-10-15 — slice 1+2 executed; slice 3 (entry) registered only

**Verified evidence**

- Guard tests RED first (4 failed on the star defaults), GREEN after:
  `tests/data_agents/test_star_domain_retirement.py` + `test_llm_profiles.py` +
  `test_rerank.py` = **31 passed**;
  `tests/test_star_coupling_defaults.py` + `test_canonical_v2_runtime_sources.py`
  + `test_seeds_api.py` = **16 passed / 28 skipped**.
- Fresh-process probe: `gemma4 → http://100.64.0.27:1231/v1` (the same model
  `qwen3.6-35b-a3b` that star's `qwen36` path serves, verified by `/v1/models`
  on both hosts); `rerank → http://100.64.0.27:18006`; remaining star profiles
  = `['ark','mirothinker','qwen35']` (allowlist, never defaults).
- Digest neutrality: `git diff --name-only` shows **no**
  `apps/miroflow-agent/src/data_agents/canonical_v2/*` change → no re-seal.
- Target machine (100.64.0.96): `miro-embed-shim.conf` +
  `gxzx-origin-map.conf` renamed `.disabled-20261015` (backups `.bak-20261015`);
  `nginx -t` ok + reload; **listener `100.64.0.27:18005` = 0**,
  `nginx -T` star lines = **0**, app `/api/health` **200**, `/chat` **200**
  (direct and via the vhost).
- Redirected evidence: 3.5-min passive capture on the target's live pid
  (before the removal) showed **0** connections to star.

**Discovered**

- The star domain's backend is dbg21 (100.64.0.34) — model paths and our
  `/guoxian` entry live in the same `sustech-ai.conf`.
- Star's model traffic (418–456/day, flat 24h) matches the customer's retired
  run-9 keep-warm profile (144 turns/day) and went to zero on Oct 12–13;
  residual Oct 13/14 requests await the gateway owner's client-IP check.
- `qwen35` / `mirothinker` on star already serve HTML (dead model paths) →
  those profiles are dead options, not usable ones.
- The target machine was mid-deploy by another work stream during execution
  (`serving-pack-fembed-v2-aliasfoothold`, 16:48 CST) — unrelated to the nginx
  change; verification used health/chat/nginx checks.

**Deviations / honestly not done**

- The running 18188 keeps the old defaults in memory until its next restart
  (dormant paths; behaviour identical).
- Target code tree keeps the same star defaults (12 files, incl. tests); no
  reachable path today (no `.sglang_api_key`, collection never ran) — follow-up
  L6.
- `canonical_v2` fallback constant (`gemma4`, 6 sites) untouched on purpose —
  needs a re-seal (follow-up L2).
- dbg21 entry removal and firewall tightening not executed (user decision:
  wait for the school's date).

## 2026-10-15 (round 2) — user asked for certainty; both non-automatic residuals cleared

**Trigger**: "国先·问渠 (local + target) definitely no longer uses star, right?"
Round 1 left two human-triggerable residuals; user approved closing both.

**Local 18188 restarted** (19:36 → healthy 290 s later, pid 256767 @ 19:41:56):
- Loaded code confirmed on the live PYTHONPATH: `llm_profiles.py → http://100.64.0.27:1231/v1`,
  `rerank.py → http://100.64.0.27:18006`.
- The in-memory old table (management-page profile test card, in-process seed path) is gone.
- Entry unaffected: `https://star.sustech.edu.cn/guoxian/chat` = 200.
- Post-restart real question: 19.6 s / 2167 frames, outbound = web-fetch targets only
  (UnionPay International, Tencent CDN, an Aliyun placeholder-cert host) + localhost;
  **star = 0**.

**Target 100.64.0.96 hardened**:
- `miro-fullstack` (run-9): key renamed `.sglang_api_key.disabled-20261015`
  (`find /root/deploy -maxdepth 4 -name .sglang_api_key` = 0);
  unit file moved aside + `/dev/null` symlink + `daemon-reload` → `is-enabled = masked`,
  `systemctl start` refused (evidence captured). v2 line unaffected (active, health 200).
- Fresh 4-min capture on the new pack (`fembed-v2-aliasfoothold`): outbound =
  DeepSeek / Serper / Bocha / web-fetch targets / localhost; **star = 0**;
  `CHAT_LLM_HEDGE_PROFILE=gemma4` proven inert (no reader in the v2 code).

**Remaining star references (all explicit, none default, none reachable as a working call
except the local `ark` test button)**:
- `qwen35` / `mirothinker` / `ark` profile definitions (allowlist test).
- `canonical_v2` `gemma4` fallback constant (rides the next re-seal).
- Target v2 code tree defaults (no `.sglang_api_key` anywhere under `/root/deploy/fullstack-v2`
  → attempts would 401).
