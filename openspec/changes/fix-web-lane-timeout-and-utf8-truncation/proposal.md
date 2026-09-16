# Proposal: fix-web-lane-timeout-and-utf8-truncation

> Hotfix line on the canonical-v2 isolated serving stack (18188).
> Human docs: `docs/plans/2026-08-28-web-lane-waseda-outage.md` + log.
> Parent effort: P1–P8 systematic fix round / `full-column-serving-pack-rebuild`
> serving smoke exposed these defects.

## Why

The test-set query `毕业于早稻田，且在深圳专注在机器人行业的企业家有谁`
failed on EVERY recorded turn on the current stack (8 turns: 5 internal_error,
3 outage-wording). Vendor blame was ruled out with a live experiment
(2026-08-28, `/tmp/bocha-latency-log.json`): Bocha answered 16/16 requests in
280–403 ms with valid UTF-8 JSON and 9–10 results per query, on both
`api.bochaai.com` and `api.bocha.cn`. All three failure chains are ours:

1. **UTF-8 byte truncation crash.** Four sites build web evidence snapshots as
   `.encode("utf-8")[:max_snapshot_bytes]` (cap 16 384). A slice boundary
   inside a multi-byte CJK character produces invalid UTF-8; the contract
   round-trip `model_dump(mode="json")` in `knowledge_read._validate_recorded`
   then raises `UnicodeDecodeError` and kills the whole turn
   (reproduced standalone: slice at a char boundary-splitting offset → same
   error, byte 0xe5 at position 16384).
2. **Starved provider timeouts made the lane single-legged.**
   `_DualWebLaneAdapter.__init__` derives ONE per-provider HTTP timeout as
   `timeout_ms * 0.00045` (main lane 1 500 ms → 0.675 s; person probes 3 000 ms
   → 1.35 s) while its own comment promises Serper ~2 s and probes 3 s.
   Measured from this host: Bocha 0.3–0.4 s (fits), Serper 1.7–2.8 s
   (ALWAYS times out). Every Serper attempt fails → 3 consecutive failures
   open the breaker for 60 s → when Bocha jitters past 0.675 s both legs are
   down and the lane reports `web-lane-unavailable` → the
   “网络检索暂不可用” outage wording.
3. **All-or-nothing budget degradation.** A supplemental budget receipt that
   exceeds only `max_wall_time_ms` (measured 11.4–29.6 s vs 10 s cap, with
   provider_calls 1/2, retries 0/0) causes `_degrade_evidence_to_local` to
   strip ALL web evidence — including results already fetched and valid —
   forcing the outage wording even though the data arrived.

## What Changes

1. `knowledge_serving_isolated.py`: add `_utf8_truncated()` (encode, cap by
   bytes, back off to a complete character boundary) and use it at all four
   snapshot sites. No snapshot schema change; snapshots are per-fetch objects
   with no cross-version fingerprint contract.
2. `_DualWebLaneAdapter`: per-provider attempt timeouts
   (`bocha-v1` ≥ 2.0 s, `serper-v1` ≥ 4.0 s, both scaling with `timeout_ms`);
   per-provider outer wait = attempt timeout + 0.5 s margin (was a single
   `timeout_ms/1000` for both).
3. `canonical_v2_admin._validated_evidence_set`: graded degradation — a
   receipt that exceeds ONLY wall time keeps its web evidence (logged as
   late-but-valid); resource overruns (provider_calls / retries / cost /
   attempts) still strip to local-only.

## Impact

- Affected code: `apps/miroflow-agent/src/data_agents/canonical_v2/
  knowledge_serving_isolated.py`,
  `apps/admin-console/backend/services/canonical_v2_admin.py`.
- Behavior: web lane stops losing valid results to self-inflicted timeouts,
  person-constraint queries stop crashing/wording-out, dual-provider
  corroboration is restored (Serper leg becomes reachable).
- Non-goals: no bundle value changes (`web_timeout_ms` stays 1500), no
  breaker tuning, no prompt/answer-policy changes, no provider endpoint
  change (`api.bochaai.com` verified equivalent to the documented
  `api.bocha.cn`).
