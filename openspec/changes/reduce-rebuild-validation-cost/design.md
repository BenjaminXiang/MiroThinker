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
