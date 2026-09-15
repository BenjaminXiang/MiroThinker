# Verification contract — web-lane topical floor (fix/web-lane-topical-floor)

RED artifacts come from `red-case.md` (T1 reproduction on the current tree).
Written before any production-code edit, per AGENTS.md §4 TDD boundary.

## Claim under test

The web lane admits pages that share no topical token with the user query.
Reported case (live 18188, session `bKkX9SSixSj6`, turn 3,
`turn-debug-bKkX9SSixSj6-03.json`): `详细介绍一下 国先中心（深圳）` returned three
web items, one of them `多彩深圳——减肥达人训练营深圳国贸营地简介` (sohu.com).

Fix: a deterministic, model-free topical floor over the web lane only,
applied after `_apply_web_subject_consistency` and after the enumeration
refinement merge.

## RED assertions (must fail before the implementation, pass after)

| # | Assertion | Fixture source |
|---|---|---|
| R1 | With `bound_entity_names=(深圳国际先进技术应用推进中心,)` and the reported query, the diet-camp result is dropped | reported turn, title/url verbatim, snippet reconstructed |
| R2 | A result whose title+snippet share **only** the location token (深圳) with the query is dropped | constructed from the same reported turn |
| R3 | A refinement-round result (second argument of the post-merge floor call) with no core-token overlap is dropped | constructed; mirrors the enumeration refinement merge |

## GREEN assertions (implementation must satisfy)

| # | Assertion |
|---|---|
| G1 | Official/registry page naming the bound entity (`深圳国际先进技术应用推进中心（深圳）...`) survives even with zero core-token overlap |
| G2 | Identity exemption: pinyin brand domain (`bytedance.com`) plus bound name `字节跳动` survives with zero character overlap |
| G3 | Enumeration query `深圳有哪些做机器人的公司` keeps `人形机器人企业盘点` (shares 机器/器人) |
| G4 | fail-open: query with no core tokens (`介绍一下`) → nothing dropped; empty title+snippet → nothing dropped |
| G5 | kill switch `CANONICAL_V2_WEB_TOPICAL_FLOOR=0` → byte-identical old behavior |
| G6 | Determinism: two calls with the same input give the same output |
| G7 | Trace: dropped results are counted as `record_gate_drop("web_topical_floor", n)`; no drop ⇒ no record |
| G8 | Perf: ≤5 ms for 64 results (micro-benchmark, no model, no network) |

## Scope boundary

Not in this change: model-based rerank, retrieval-side ranking, subject-gate
semantics (`_apply_web_subject_consistency` is untouched), local lanes.
