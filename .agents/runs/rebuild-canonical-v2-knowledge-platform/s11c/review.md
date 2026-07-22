# S11C Aggregate Consumer Acceptance Review

## Final verdict

- Reviewed at: `2026-07-21T18:56:43Z`.
- Critical: `0`.
- Important: `0`.
- Minor: `0`.
- YAGNI: `0`.
- Disposition: the S11C implementation and persisted evidence are eligible for Candidate. Accepted
  still requires the contract's exact generated-cache/protected-scope gate, final receipt, and
  atomic Tasks `11.1`-`11.5` closure.

## Review history

The first Candidate-evidence review found one Important execution-traceability gap: the four exact
predecessor reruns did not persist their launcher cwd, and the two guarded broad runs did not have
machine-validated UTC execution windows. No product or test-result regression was found.

The repair preserved all original broad artifacts and `predecessor-reruns-v1.json`. It added:

- `predecessor-reruns-v2.json`, which binds the preserved v1 raw hash and records exact repository-
  root cwd, strict UTC start/finish, Accepted command/pointer/hash, launcher argv, real exit code,
  stdout/stderr hashes, and eleven passing JUnit cross-links for all four reruns; and
- `guarded-execution-provenance-v1.json`, which binds the raw guarded receipt, failure ledger, and
  two original JUnit files and derives UTC windows from each JUnit testsuite timestamp plus duration.

The final independent re-review confirmed that the validator recomputes and rejects missing or
tampered cwd, UTC, source hashes, v1 supersession, and cross-links. The exclusive-create capture
helper cannot overwrite v1, broad evidence, or an existing v2/provenance artifact. One duplicate
non-authoritative rerun attempt reached `FileExistsError` after the authoritative v2 receipt already
existed; it changed no receipt or predecessor/broad artifact and is not acceptance evidence.

## Exact reviewed identities

- Aggregate validator:
  `3924a00af6dbe183f0a1199ed7b9977b5475dad3ee558b4fa4fd7758f9ca62bb`.
- Traceability capture helper:
  `a1bbf4d60ee2e73aee93a27ff3d75a6d94526f08d4701c243c40ca204da7bdf4`.
- Traceability capture owner:
  `060c7ab2979bb9d69b6a30533660205d226ef5bb660cd62897616ddff171db8c`.
- Guarded execution provenance:
  `8b307160f9f1231896d11f43d71b06daed329824a50f3255a127d922aa35f467`.
- Preserved predecessor receipt v1:
  `84507b7c3fd6a441547922cfc7012c58a74b6a11c82ec001ffe8e300ffc5eb11`.
- Authoritative predecessor receipt v2:
  `6043e991ff2971aba8bb5a1492261be302412aab1cb272b9027ac24009282d8d`.
- Guarded partitions receipt:
  `9b5e1c786bc62e6df5b7736e3fd9f1bf47ef6b5a26ea46c8f1338172b3245493`.
- Retired-failure ledger:
  `271f4f9808a206e06cd616c95a778178f453fb67cf9284e9b93c33623fb75e7d`.
- Disposable PostgreSQL receipt:
  `51278f966935dfa8f988f72905cfe72ffda13ccb7a520c2b5f8a7f59bd53e712`.
- Focused JUnit / postflight receipt:
  `7183f3b8a41958ed0c4199649834d42f605dd679b35a07b2a036e65e75fc0cbb` /
  `eabd02a7da2561b697fb31cd66e42ca3e96859eefa9460f664b4e8eaa4c57172`.

## Fresh review checks

- Traceability capture owner: `2 passed`.
- Exact aggregate validator: `1 passed`.
- Complete validator file: `55 passed`.
- Ruff check and format check: passed.
- Python compile check: passed.
- Changed-scope Pyright: `0 errors`.
- Strict OpenSpec validation: passed.
- `git diff --check`: passed.

The persisted Task `11.2` evidence remains pass-only for S2C Task `2.7` (`11`), interface/trace
(`22`), release/index (`70`), disposable PostgreSQL (`122`), S11A HTTP/session (`7`), S11B admin/
quarantine (`1 + 2`), and S10O operations (`1`). The broad ledger reconciles all `22` Admin
failure/error rows as `6 retired_replaced + 5 retired_reference_only + 11 unrelated_preexisting`;
the Canonical V2 predecessor partition has no failure/error. The focused file union remains exactly
`47` predecessor files plus the one S11C owner.

## Scope and invariant conclusion

No production implementation, schema, migration, Accepted predecessor, frozen inventory, original
PostgreSQL, original Milvus, forensic source, release pointer, or remote Git state changed during
the repair or re-review. S2C Task `2.8` remains an S8/S9 acceptance-oracle gate and is not an S11C
blocker. No Commit, Push, PR, Archive, promotion, or Cutover occurred.
