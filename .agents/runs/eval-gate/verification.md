# Verification: eval-gate (gate 2)

Date: 2026-10-26 (CST). Branch `feat/eval-gate` (off `hotfix/customer-20261026`).
Target for all runs: `https://gxzx-coze-api.idea.edu.cn` (customer site, 100.64.0.96).

## Baseline measurement

```
python scripts/eval_full_testset.py --base https://gxzx-coze-api.idea.edu.cn \
    --mode full --out scripts/eval-baselines/baseline-full.json
```

- 19 conversations / 27 turns, one cookie jar per conversation, 0 errors.
- required **77/120 (64%)**, product_pass **26/27**, forbidden 0,
  refusal-miss 0, mean 14.51 s, max 84.01 s (q15).
- Only product-axis failure: q2 (`他是否有参与哪些企业的创立` → clarification,
  0 citations). Kept as a failure: the multi-turn referent was lost.

## Gate self-check (second run against the same baseline)

```
python scripts/eval_full_testset.py --base https://gxzx-coze-api.idea.edu.cn \
    --mode full --out /tmp/eval-gate-second-run.json \
    --baseline scripts/eval-baselines/baseline-full.json --fail-on-regression
```

```
=== BASELINE ===
baseline verdict: pass
  fluctuations (within tolerance): qid 25 4->3
  totals: required 77->76, product_pass 26->26, forbidden 0->0, refusal_miss 0->0, errors 0->0
=== SUMMARY ===
  required_recall: 76/120 (63%)
  product_pass_rate: 0.963
  ...
exit=0
```

This is the intended behaviour: one-entity phrasing noise is reported, not failed;
the exit code stays 0. A two-entity dip, a total dip beyond `--tolerance` (3), a
rising forbidden/refusal/error counter, or a disappearing turn flips it to 1.

## Unit tests

`pytest tests/test_eval_gate.py` → **14 passed** (no network):

| cluster | locks |
|---|---|
| `_hits` / `_normalize` | whitespace-split standard phrases (q23), case-insensitive English |
| `groups_for` | head = 19 singleton conversations; full = 27 turns across 19 groups |
| `summarize` | required/product/forbidden totals and rates |
| `_product_pass` | refusal turns pass on refusal; answers need a citation; forbidden fails |
| `compare_to_baseline` | hard turn drop (≥2), single-entity fluctuation, total tolerance, disappearing turn, worse counters |
| `format_comparison` | verdict and fluctuation lines are legible |

## Design notes / limits

- **Latency is reported, never gated.** Baseline mean 14.51 s vs second run
  5.41 s — the difference is answer-cache warmth, not performance.
- **Exact recall is not an acceptance score.** q27 scores 0/4 exact but passes
  the product axis (answer with 12 professor citations).
- `head` mode has no baseline yet; only `full` is gated.
- No CI wiring yet: `just eval-gate` is manual.
- The fixture (`tests/fixtures/test_cases.yaml`) predates this slice; it is
  regenerated from `docs/测试集答案.xlsx` by `scripts/parse_testset.py`.
