# Proposal: alias passthrough and local foothold

## Why

`国先中心（深圳）` — a name the customer uses daily — does not reach the local
record, although the entity and its full official summary are already in the
serving pack (`company-c-3970adda34eb223ab03821ff`, `profile_summary` verbatim;
alias `深圳国先中心`). Content was never the gap; routing is.

Routing is decided by two purely lexical functions in
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`:
`_infer_domains()` (domain words / suffixes) and `_has_local_scope_foothold()`
(foothold). A query whose subject shape no extractor recognizes holds no
foothold and executes as **Web-only**. Round-47 measurements on the live line:

| ask (verbatim) | lanes | outcome |
|---|---|---|
| `国先中心（深圳）是什么公司` | exact 2 + vector 16 + web 16 | ✅ official summary, 12.7 s (a domain word saved it) |
| `介绍一下 国际先进技术应用推进中心（深圳）` | web only (5) | ⚠️ web narrative, official points missing |
| `国先中心（深圳）的详细信息` | web only (**0**) | ❌ "暂未找到对应机构" while the pack holds the full record |

The function's own docstring states the gap: a name whose shape no extractor
recognizes holds no foothold, and "widening this needs a real name-shape
decision, not another marker guess."

## What Changes

Three layers, in order of preference (each independently testable):

1. **Foothold extension — the real name-shape decision.** Before falling back
   to lexical extractors, look the query's candidate name tokens up in the
   repository's own entity-name/alias index: if a known local entity name or
   alias matches (including bracket-reordered forms —
   `国先中心（深圳）` → `深圳国先中心`), the query holds a foothold. No new
   word lists, no new shape guesses: the decision comes from pack data.
2. **Query-time alias resolution.** Resolve the matched form to the canonical
   entity id so the local lanes receive a canonical subject instead of an
   unrecognized string (same `canonical_ref` the manual-recall point binds).
3. **Local fallback.** When the web lane returns 0 results and the query
   resolves to a local entity, run the local lanes and answer from the pack
   instead of reporting "未找到".

## Out of Scope

- Alias-table completeness / data-side alias work (R15, data line).
- Answer synthesis policy (window sizes, answer form) — slice ①min.
- The "0 domain" contract question (round 41) and handle-anchor binding
  (round 42) — slice ③④.
- Any change to `_infer_domains()` semantics beyond the foothold check.

## Risks

- Foothold widening could pull concept/general questions into local lanes (the
  round-41 "出示门槛" regression class). Mitigation: foothold requires an
  actual name/alias match against the pack index — shape guesses are excluded.
  Regression gate: replay 7/7 + recall-gate `--diff` 0 fail + the round-41
  route A/B set re-run for concept-question families.
- Kill switch: `CANONICAL_V2_ALIAS_FOOTHOLD=0|false|off|no` → byte-identical old
  behavior.
