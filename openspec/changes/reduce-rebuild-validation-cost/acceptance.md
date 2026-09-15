# Acceptance: reduce-rebuild-validation-cost

| # | Criterion (counts as fixed) | Evidence required | Status |
|---|---|---|---|
| A1 | Decision-batch `COMMIT` drops from **~12h40m to minutes** on identical input | before/after phase timings + identical row counts | pending |
| A2 | Identity-resolution phase drops from hours to minutes | before/after phase timings | pending |
| A3 | The release authority is no longer parsed + canonicalised three times per release (`phase=envelope_validate` 2071s ⇒ minutes) | sealer phase table before/after | pending |
| A4 | Identical inputs produce a **byte-comparable envelope** (or equal projection digests + row counts) | diff / digest artefact | pending |
| A5 | Reviewed-field immutability still rejects (ERRCODE 23514) | new regression test, RED before / GREEN after | pending |
| A6 | `apps/miroflow-agent` canonical_v2 suites green **and** one full rebuild passes end-to-end | suite output + envelope receipt | pending |
| A7 | No fail-closed validator was weakened, deleted, or bypassed | reviewer checklist against §12.5 / §13.5 | pending |

## Out of scope

Served data, release contents, the serving-pack contract, and query
classification A–G semantics. No migration is rewritten; DDL changes stay
reversible.
