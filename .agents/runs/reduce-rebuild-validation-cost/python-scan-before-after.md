# Python scan evidence — canonical_identity_resolution.py

Command: pytest -k indexes_assertions_by_source_once (parametrised N=4, 32).
The counter wraps `identity_assertions` and counts full iterations of the tuple
during `IdentityResolutionRequest.validate_request()` — the validator the run15
py-spy stack showed at line 427.

## BEFORE (source fix stashed)
```
E       assert 5 <= 2
E       assert 33 <= 2
2 failed, 58 deselected in 7.57s
```

## AFTER (this branch)
```
2 passed, 58 deselected in 7.29s
```

## Time-based benchmark (`bench-identity-validation.txt`)

`validate_identity_resolution_result` on person-method batches (half assigned /
half name-only, the internal-reference recall shape), best of 3 repeats:

| sources = assertions | before | after | speed-up |
|---|---|---|---|
| 500 | 0.1475 s | 0.1265 s | 1.17× |
| 2,000 | 1.1325 s | 0.7420 s | 1.53× |
| 10,000 | 20.4200 s | 10.4951 s | 1.95× |

The gap grows with batch size, i.e. the removed work is the per-item rescan of
the assertion set (run15: 47,075 sources × 620,798 assertions ≈ 2.9×10¹⁰
comparisons in `validate_request` alone).

## Same-shape siblings swept in this function (pattern repair)

- `validate_identity_resolution_result` built `expected_assertion_ids` by
  filtering **all** identity assertions once per candidate verdict, and
  `component_sources` by filtering **all** sources once per verdict. Both are now
  a pre-built `source_id → assertion_ids` map plus a positional order index.
  run15 scale: 491 verdicts × 620,798 assertions ≈ 3×10⁸ element tests removed.
  Note: the synthetic benchmark above does **not** build candidate verdicts, so
  it does not show this win — the justification is the run15 row counts
  (`identity_candidate_verdict` = 491, `source_assertion` = 620,798), and the
  ordering is preserved exactly (see `test_identity_request_validation_…` and the
  60 green contract tests).
- `cProfile` at 2,000 sources after the change shows the residual cost is
  pydantic model revalidation / JSON encoding / `_require_unique`, not scanning —
  i.e. the defect class is gone, and what is left is the contract's own
  fail-closed revalidation.
