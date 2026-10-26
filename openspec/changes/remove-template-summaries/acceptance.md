# Acceptance: remove-template-summaries

| # | Criterion | Evidence |
|---|---|---|
| A1 | Fallback no longer pads | unit test `test_fallback_summary_no_longer_pads`; facts kept |
| A2 | Padding never reaches a claim | unit test `test_claim_rendering_drops_template_summary` |
| A3 | Unrelated text untouched | unit test `test_filler_filter_keeps_unrelated_text` |
| A4 | No claim becomes empty | pack scan: 2,149 records contain padding, **0** are filler-dominated |
| A5 | No regression on the golden set | 27-turn gate after deploy |

Status: candidate (code + 5 tests done); deploy + gate pending.
