# Acceptance: add-synthesis-timeout

- [ ] Default timeout is 60s; `CHAT_SYNTHESIS_TIMEOUT` overrides it (unit-checkable: read the
      env-wired constant at chat.py:70).
- [ ] No streaming/retry added (scope guard).
- [ ] `openspec validate add-synthesis-timeout --strict` exits 0.
- [ ] Existing chat tests green (the 60s default is already matched by test 8da9053).

## Evidence to report
- chat.py:70 + :1180 diff confirmation; env-override unit check; test status.
