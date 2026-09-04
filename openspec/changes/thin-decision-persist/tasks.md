# Tasks

- [x] 1. Verification contract before production edits
- [x] 2. Raw-tuple multiset verification replaces both in-transaction
      full read-backs (`_written_batches` + `_verify_written_batch`)
- [x] 3. Idempotent replay short-circuit (returns validated; replay-conflict
      error preserved, message-compatible)
- [x] 4. Set-based supersession gate (2 batched queries per family,
      20k-element chunks; same error semantics)
- [x] 5. Post-commit canary rebuild (≤5,000 decisions; env
      CANONICAL_V2_DECISION_REBUILD_CHECK=always|off|auto)
- [x] 6. New tests 3/3 green; existing decision PG suite 46/46; combined
      49/49; lint clean on new code (2 pre-existing F821s untouched)
- [x] 7. Performance recorded (supersession 11x; negative finding on
      dominance honestly logged); evidence
      `.agents/runs/thin-decision-persist/verification.md`
