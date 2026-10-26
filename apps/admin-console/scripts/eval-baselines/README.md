# Eval baselines

`baseline-full.json` is the reference run the golden-set gate compares against.

## Provenance

| field | value |
|---|---|
| measured | 2026-10-26 22:52 CST |
| target | `https://gxzx-coze-api.idea.edu.cn` (customer site, 100.64.0.96) |
| mode | `full` — 19 conversations / 27 turns, one cookie jar per conversation |
| fixture | `apps/admin-console/tests/fixtures/test_cases.yaml` (27 cases, 19 head turns) |
| required recall | **77/120 (64%)** |
| product pass | **26/27** |
| forbidden / refusal-miss / errors | 0 / 0 / 0 |
| latency | mean 14.51 s, max 84.01 s (q15, 光基多维力传感) |
| label | `baseline-2026-10-26` |

The single product-axis failure is **q2** (`他是否有参与哪些企业的创立`, a
follow-up to q1): the turn fell back to a clarification with no citation, so the
multi-turn referent was lost. Kept as a failure — that is the real gap.

## Why two axes

- `required_recall` counts exact required entities. It is the **regression**
  axis: it must not go down, but it under-reports an honest answer that phrases
  the same fact differently (q20/q22/q23).
- `product_pass` is the **usability** axis: the turn answered with at least one
  citation, or refused when a refusal was expected, and carried no forbidden
  entity. This is the number a product decision can use.

## Refresh policy

Refresh only when the target deployment changes in a way that *should* move the
score (new pack, new answer model, a batch of gold-set fixes), and commit the
reason in the message. Never refresh to make a red gate green — investigate the
per-turn diff first. Keep one baseline; `git log` is the history.

## Tolerance

The composer is a model: the same question rephrased can lose one exact token.
The gate treats that as noise instead of failing on it.

- single turn losing **1** entity → `fluctuations` (reported, not fatal)
- single turn losing **≥ 2** entities → regression
- total dropping by more than `DEFAULT_TOTAL_TOLERANCE` (3, `--tolerance`)
  → regression
- forbidden / refusal-miss / error counters rising → regression
- a turn that no longer runs → regression
