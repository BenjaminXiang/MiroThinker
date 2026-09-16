# Proposal: admit-unanchored-papers (+ applicant-binding relationship seeding)

> Implements the G4/G6 admission-matrix decision for the paper domain and
> closes the G3 relationship derivation gap. Grounded in the run-10/11
> post-mortem: the professor-anchoring gate (by design) removed 14k+ real
> in-scope papers entirely; the applicant-binding merge's 7,650 resolved
> bindings never seeded patent_has_applicant relationships.

## Why

1. **G4 (papers unreachable)**: `_map_public_authority` pops every paper
   without a Professor anchor (identity + assertions + all maps), and
   `domain_inclusion`'s paper rule hard-excludes unanchored candidates
   (`outside_paper_discovery_scope`). Result: pool papers 24,101 → pack
   10,390 (41% coverage) while the goal function (可达 × 诚实分级,
   user-ruled 2026-09-03) requires every real in-scope entity reachable
   with honest tiering.
2. **G3 (bindings invisible to relationships)**: the applicant-binding
   merge rewrites the patents' `applicants` FIELD ASSERTIONS with canonical
   company ids (verified: 7,078 assertions carry `company-c-*` ids), but
   `_typed_relationship_seeds` reads only `core_facts.company_ids` (absent
   for P4 patents) or re-resolves applicant names against released
   companies — the binding work never seeds `patent_has_applicant`
   relationships (0 decisions in run 10/11).

## What Changes

1. **Anchoring gate → honest limitation** (Option B, no projection-model
   changes): `_map_public_authority` KEEPS unanchored papers (typed gap
   still recorded per paper); `domain_inclusion`'s paper rule admits
   in-scope-but-unanchored papers as `admitted` with
   `limitations=("paper_unanchored",)` — the label propagates through the
   path-eligibility engine into the lookup/vector documents'
   `eligibility_limitations` (public docs may carry limitations while
   admitted; only limited outcomes REQUIRE them — model-verified). Out of
   scope stays excluded; anchored stays admitted-without-limitation.
2. **Binding-driven relationship seeding**: `_typed_relationship_seeds`
   gains `bound_company_ids_by_patent` (patent object id → canonical
   company ids, built by `_relationship_authority` from the remapped
   applicants assertions in `decision_result`) and seeds
   `patent_has_applicant` from resolved bindings FIRST (evidence kind
   `patent_applicant_assertion`, match_kind `resolved_binding`), before
   the existing core_facts/name-resolution paths.

## Impact

- Paper coverage 41% → ~100% of the in-scope pool; every previously
  "missing" paper becomes reachable with an honest `paper_unanchored`
  limitation the answer layer can disclose.
- Company→patent relationships: 0 → ~7.6k seeded from resolved bindings
  (G3's data finally traversable; P5's data root cause closed).
- Serving side unchanged (public docs with limitations are accepted;
  lookup/vector/relationship lanes already verified for
  admitted/limited).
- Tests pinning the old exclude/pop behavior are updated per this change.
- Non-goal: professor quality fields (G5), alias closure (G2b), needs_review
  professor tiering (G6 professor leg).
