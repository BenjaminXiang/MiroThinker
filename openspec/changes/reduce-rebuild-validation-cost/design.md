# Design: reduce-rebuild-validation-cost

The minimal designs are owned by the human-doc analysis and are **not
duplicated** here:

- workstream 1 → `docs/plans/2026-09-14-rebuild-cost-analysis.md` §12.4
  (minimal design) and §12.5 (acceptance line);
- workstream 2 → the same file §13.4 / §13.5.

This file fixes only the implementation shape, sequencing, and equivalence
argument.

## Workstream 1 — hot paths

| Site | Today | Change |
|---|---|---|
| `canonical_identity_resolution.py:423-430` | per-source full scan of all identity assertions | one pass into `assertions_by_source` |
| `canonical_identity_resolution.py:1099-1106` → `:2414` | `_has_evidence_bound_internal_identifier` rescans the whole assertion set per call | build `(source_id, field_path)` index once, look up |
| `C2_0007_bind_human_review_provenance.py:1156-1265`, mounted at `:1464` (`DEFERRABLE INITIALLY DEFERRED FOR EACH ROW`) | per-row JSONB `EXISTS` over 417k decisions, no usable index | release-level guard (no human-review decisions in this release ⇒ skip the scan), expression/partial index, statement-level or batched trigger |
| `C2_0009_typed_domain_projections.py:1140` (domain inclusion), `C2_0007...:1486` (relationship) | same shape, smaller N | same repair, via a mandatory sibling sweep |

**Equivalence argument.** Every guard keeps the same predicate; the guard only
skips work that provably cannot fail (`no human-review decisions ⇒ the EXISTS is
false for every row`). The rejecting paths must be pinned by regression tests —
including the case where reviews *do* exist.

## Workstream 2 — envelope / authority contract

Split the release authority into (a) a small manifest, (b) content-addressed
authority parts verified **once** at seal time, (c) a verification token that
consumers check instead of re-deriving the whole canonical hash. The serving
pack stays the seconds-level boot input; the 8GB envelope becomes an offline
artefact rather than something every consumer re-parses.

## Sequencing

1. Workstream 1 first: independent, measurable, and it removes the single
   largest cost (12h40m `COMMIT`). Confirm with a real rebuild before touching
   the contract.
2. Workstream 2 second: needs a format/migration decision and touches the runner
   sink + readback and `s12c/build_serving_pack.py`.

## Verification strategy

Primary measurement is the rebuild itself (per-phase timings before/after);
equivalence evidence is a byte-comparable envelope for identical inputs (or
equal projection digests + row counts). Full list in `acceptance.md`.

## Step 1 implementation result (2026-09-15, `perf/rebuild-trigger-fix`)

Migration `C2_0014_guard_review_binding_scans` = six partial indexes
(`method = 'human_review'`) + the three binding validators with a release-level
guard. No trigger is added, removed, or re-scoped; every predicate and every
`RAISE … 23514` stays byte-identical; `downgrade()` restores the C2_0007 bodies
exactly (verified by `check_function_bodies.py`).

### Granularity decision (task 3 — not taken, with data)

Measured on a copy of the run15 candidate DB (`measure-before-after.jsonl`):

| mechanism | field assertion branch, per row | 846,986 rows |
|---|---|---|
| as shipped (unindexed `EXISTS`) | 41,900 µs | ≈ 9.9 h (run15 measured 12 h 40 m for the commit) |
| guard only (indexes dropped) | 42,884 µs | ≈ 10 h — **the guard alone buys nothing** |
| guard + index (C2_0014) | 28.7 µs | ≈ 24 s |

So the whole win comes from removing the unindexed scan; a statement-level
(`FOR EACH STATEMENT` + transition table) rewrite would attack the remaining
~24 s of deferred-event dispatch and the second per-row PK probe. That is not
worth its risk here: PostgreSQL forbids transition tables on constraint triggers,
so a statement-level form would have to re-check the whole release per statement
(O(release) per `INSERT … SELECT` batch, losing the per-row `NEW` context that
the `RAISE` messages carry), while the deferred, fail-closed property has to be
preserved exactly. If run16 shows the residual matters, the follow-up is a
*batched* validator (one set-based check per batch, per the analysis §12.4 item
3), not a trigger-granularity rewrite.

The guard is still worth keeping: it makes "when can this scan be skipped"
explicit and reviewable, and it is the shape the sibling families need (see
`verification.md` §5). It is documented as defence-in-depth, **not** as the
performance fix.

### Sibling sweep result (task 1.1)

Same defect (per-row `EXISTS` on a review-decision table without a supporting
index): field (41.9 ms/row), relationship (2.09 ms/row), identity (6.08 ms/row,
9 mounts). Different defect, recorded not fixed:
`validate_identity_resolution_release` (release-level topology re-derived per
row, 14 mounts, ≈704,760 events; probe 1.65 s/event, faithfulness unproven — see
`verification.md` §5) and `validate_field_temporal_binding` (1.27 M events ×
153 µs; index-backed parts already cheap). Not a defect at all:
`domain_inclusion_decision_assertion`'s owner validator measured 1.67 µs/row on
424,440 rows (already index-backed), answering the analysis' sibling guess with
data instead of a speculative rewrite.

