# RED case — alias foothold (round 47 verbatim)

## Reported asks (live 18188, 2026-10-15, migration-log round 47)

| ask | lanes | outcome |
|---|---|---|
| 国先中心（深圳）是什么公司 | exact 2 + vector 16 + web 16 | ✅ official summary, 12.7s (a domain word already gave a foothold) |
| 介绍一下 国际先进技术应用推进中心（深圳） | web only (5) | ⚠️ web narrative, official points missing |
| 国先中心（深圳）的详细信息 | web only (0) | ❌ "暂未找到对应机构" while the pack holds the full record |

## Root cause (code)

`_has_local_scope_foothold` (`knowledge_serving_isolated.py`) is lexical only:
domain inference / `_PLATFORM_TOPIC_MARKERS` / three name-shape extractors.
Neither failing ask trips any of them; the pack entity
(`company-c-3970adda34eb223ab03821ff`, alias `深圳国先中心`) is never
consulted at planning time, so the turn executes Web-only.

## In-suite proof of the gap (ships with the slice's tests)

`tests/canonical_v2/test_alias_foothold.py::test_foothold_uses_the_linker_when_lexical_checks_fail`
asserts `_has_local_scope_foothold(<both failing asks>) is False` without a
linker — the pre-fix decision, captured next to the fix so a regression
re-opens it — then asserts `True` with the pack-name linker.

## Live E2E (T7, pending)

Scratch boot + the 4-form acceptance matrix (full name / 短名 国先中心（深圳）
/ 简称 国先中心 / 带领域词) + replay gate + recall-gate `--diff` — to be
recorded here and in `verification.md` before any cutover.
