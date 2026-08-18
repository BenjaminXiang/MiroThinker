# Acceptance: enforce-never-refuse-contracts

Evidence collected 2026-08-18. Replay/fault evidence under
`.agents/runs/enforce-never-refuse-contracts/`.

## Unit-level (deterministic guards)

| # | Requirement | Evidence |
|---|---|---|
| U1 | Never-refuse fallback contract form | `tests/test_never_refuse_contracts.py` 7/7 RED→GREEN; 4 old refusal-wording tests updated to contract form with rationale |
| U2 | Deflection guard (国知局/PatSwap/Incopat, zero patent evidence → gap-naming rewrite; grounded recommendation kept) | same suite, verbatim G4 form as input |
| U3 | Lane-outage semantics (negative world claims rewritten to 网络检索暂不可用; healthy answers untouched) | same suite + `_web_lane_unavailable_from_traces` detection tests |

## Replay/fault-level

| # | Requirement | Evidence | Notes |
|---|---|---|---|
| V1 | Fault-injected both-provider outage: no negative world claims over web-only subject; trace token | 国先中心 (web-only) with both keys invalid: answer = 「当前本地库暂未建立关于"国际先进技术应用推进中心（深圳）"的关联信息（数据覆盖缺口）」+ industry background — subject named, system-state framing, 未找到 absent; trace degradation=web-lane-unavailable | Compliant phrasing came from the prompt contract (本地库覆盖缺口 form); the literal 网络检索暂不可用 string is enforced by the deterministic guard when a negative claim would ship (unit-proven) — accepted as substance-over-letter |
| V1b | Local-rich subject under outage keeps full local answer | 优必选 with both keys dead: full local answer, no refusal/outage claims; guard correctly did not intervene |
| V2 | Full seven-session replay on Phase 2 code | G4 patents **PASS**（外甩消失——P5 话术形态修复）; G3/G5 still RED (Phase 3 roots, expected); G6/G7 PASS | G2 flipped FAIL + G1 flipped PASS — both are variance-window flips of the P1-family anchor drift (G2 T2 answered about 中科院深理工, a wrong entity — quoted in log). Phase 2 never claimed subject-correctness; evidence recorded for Phase 3 |

## Regression

- Admin suites 163/163 green; agent serving suite 237 green after prompt edit.
