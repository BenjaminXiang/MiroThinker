# Acceptance: alias passthrough and local foothold

## Acceptance criteria

| # | Criterion | Evidence type |
|---|---|---|
| AC1 | `国先中心（深圳）的详细信息` holds a local foothold; the answer contains the official points (国家发展改革委 / 深圳市政府支持指导 / 深圳市科技创新局业务主管 / 依托粤港澳大湾区数字经济研究院 / 世界级平台 / 人工智能·具身智能·低空经济) | live ask on scratch, then 18188 + field |
| AC2 | `介绍一下 国际先进技术应用推进中心（深圳）` engages local lanes; answer contains the official points (currently web-only) | live ask |
| AC3 | The four forms — full name / short form `国先中心（深圳）` / short form `国先中心` / with domain word — all answer with the official points | live ask ×4 |
| AC4 | None of the four answers describes a 大湾区 or 合肥 organization | manual read, quoted in verification.md |
| AC5 | web 0 results + local entity match ⇒ answer from local, no "暂未找到" | live ask |
| AC6 | replay gate 7/7 | `apps/admin-console/scripts/replay_fix_round1.py` |
| AC7 | Recall gate: no fail-level diff vs the frozen baseline; the round-41 route A/B set shows zero new enterprise-list leakage on concept-question families | `--diff`, route A/B |
| AC8 | Kill switch `CANONICAL_V2_ALIAS_FOOTHOLD=0` restores byte-identical old behavior | unit test |
| AC9 | Reseal is manifest-only via the s12g path; reseal receipt recorded; rollback asset (current pack) kept byte-identical | reseal log |

## Non-goals

- `无界智航` / bare person-name cases from the docstring are fixed **only if**
  they match the same data-driven mechanism (pack name/alias); they are not a
  separate lexical carve-out. If they do not match, they stay web-only and are
  recorded as remaining scope.
- No promise on answer wording beyond the official-points checklist; synthesis
  depth is slice ①min.
