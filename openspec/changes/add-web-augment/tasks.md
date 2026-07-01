# Tasks: add-web-augment

> Proposed (skeleton). Implementation deferred — blocked on the Serper credential (user-owned).
> This round only records the defect + contract obligations.

- [ ] 1. Restore a valid Serper credential (runtime/config; owner: user). Verify
      `_augment_with_web` no longer logs `403 Unauthorized`.
- [ ] 2. Contract web-augment behavior: `_augment_with_web` (retrieval.py:451) types web
      Evidence, dedups/fuses with DB results per spec scenarios.
- [ ] 3. Provenance: every web candidate carries `source_url`; the precision oracle flags
      unsourced web (currently 0 — Serper dead).
- [ ] 4. Re-run precision oracle after Serper fix; label web-rescued entities for correctness
      (false positives from web are a 准 risk).
- [ ] 5. openspec validate add-web-augment --strict exits 0.
- [ ] 6. Claude review; accept / revise / reject.
