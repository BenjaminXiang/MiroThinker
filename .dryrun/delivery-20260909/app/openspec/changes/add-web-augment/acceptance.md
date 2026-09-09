# Acceptance: add-web-augment

> Proposed (skeleton). All unchecked — implementation deferred (blocked on Serper credential).

- [ ] Serper 403 resolved; `_augment_with_web` no longer logs `403 Unauthorized`.
- [ ] Web-augment behavior matches spec scenarios (absent entity surfaced; failure degrades
      gracefully).
- [ ] Every web candidate carries `source_url`; precision oracle `unsourced_web = 0` with web
      alive.
- [ ] Precision oracle re-run; web-rescued entities labeled; false-positive rate recorded.
- [ ] `openspec validate add-web-augment --strict` exits 0.

## Honest scope (not blocked-on)
- [ ] Ingest of the 6 absent entities (`fm1a-ingest-decision`) is the durable recall fix; web
      rescue is a partial, fragile supplement — NOT a substitute for ingest.
