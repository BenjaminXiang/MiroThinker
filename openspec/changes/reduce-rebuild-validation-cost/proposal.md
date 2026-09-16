# Proposal: reduce-rebuild-validation-cost

## Why

One full Canonical V2 candidate rebuild currently costs **~20–23 hours** wall
clock (run15: 09-13 23:31 → 09-14 ~22:30; run14: 20h04m). That makes the planned
weekly refresh (W6) and the monthly one-click publish (W7 / plan §5.4)
infeasible. Three read-only reviews localised the cost and judged the mechanisms
over-designed; **the rules themselves are legitimate and stay**.

| Evidence (2026-09-14) | Finding | Human doc |
|---|---|---|
| 09:15 `EXPLAIN ANALYZE` on the run14 DB | the decision-batch deferred constraint trigger re-verifies "this release has no human-review decisions" **once per assertion row**, with no usable index → 834,240 rows × ~43 ms | §5, §11.1 |
| 18:14 measurement | that single `COMMIT` took **12h40m** wall (≈11.5h backend CPU); 0 rows were actually rejected | §11.2 |
| design review | four checkable over-design criteria all hit; minimal design + acceptance line written | §12.2 / §12.4 / §12.5 |
| seal measurement | one 8.18GB envelope authority is parsed + canonicalised + rehashed **three times per release** (build readback ≈1h45m, `phase=envelope_validate 2071s`, dogfood reload 351s) | §13.2 / §13.4 / §13.5 |

## What changes (two workstreams, in this order)

1. **Trigger / validator hot paths (biggest win, cheapest first).** Guard the
   `validate_field_human_review_binding` family so the per-row scan is skipped
   when the release has no human-review decisions; add the missing
   expression/partial indexes; move row-level deferred constraint triggers to a
   statement-level (transition-table) or batched form. Same pattern-repair sweep
   for `domain_inclusion_decision_assertion` (≈418k assertions) and
   `relationship_decision_assertion` (≈21.5k), plus the two Python-side
   per-entity full scans (`canonical_identity_resolution.py:423-430` and
   `:1099-1106` → `:2414`).
2. **Envelope / authority contract slimming.** Stop shipping one 8GB JSON as the
   release authority: split it into content-addressed parts plus a small manifest
   and a one-time verification token, so each consumer stops paying
   "parse + canonicalise + rehash" in hours.

## Out of scope / invariants

- **No relaxation of fail-closed semantics.** Every validator that exists today
  must still reject the same inputs; §12.5/§13.5 require a regression test that
  proves the reviewed-field immutability guard still raises (ERRCODE 23514).
- No change to served data, release contents, the serving-pack contract, or
  query classification A–G.
- Alembic migrations stay reversible; no historical migration is rewritten.

## Rollback

Both workstreams are code/migration-scoped and land on their own branch: the
trigger/index migration is reversible in place, and the envelope-contract change
is additive until the second consumer switches over.
