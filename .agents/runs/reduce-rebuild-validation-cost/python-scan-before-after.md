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
