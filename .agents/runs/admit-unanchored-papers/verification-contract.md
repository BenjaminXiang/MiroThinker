# Verification contract: admit-unanchored-papers (+ G3 seeding)

Written BEFORE production edits.

## Behavior under test

B1 (inclusion): an in-scope paper candidate WITHOUT a Professor anchor →
`admitted` with `limitations=("paper_unanchored",)` (was: hard-excluded).
Anchored in-scope → admitted, no limitation (unchanged). Out-of-scope →
excluded (unchanged).

B2 (gate): `_map_public_authority` no longer removes unanchored papers —
they flow into identity/decision/projection; the per-paper typed gap is
still recorded.

B3 (propagation): a lookup document over a limitation-carrying admitted
path decision keeps `eligibility_outcome="admitted"` and
`eligibility_limitations=("paper_unanchored",)` (model + index builder).

B4 (seeding): patents in `bound_company_ids_by_patent` produce
`patent_has_applicant` seeds with canonical company targets; existing
`core_facts.company_ids` and name-resolution paths unchanged.

## Test levels

L1 unit (agent): new `test_admit_unanchored_papers.py` —
- inclusion rule: unanchored in-scope → admitted+limitation (RED)
- inclusion rule: anchored/out-of-scope controls (regression guards)
- seeds: bound mapping → patent_has_applicant seed (RED)
L2 regression: `test_domain_inclusion_contract.py`,
`test_knowledge_build_isolated.py`, p4 merge tests — updated where they
pin the old exclude/pop behavior (documented in the change).
L3 e2e: run 12 rebuild → reconcile (expect papers ~34k, patent_has_applicant
decisions ~7.6k, per-batch ledgers all-visible) → golden set rerun.

## Fix surface

- `knowledge_build_isolated.py` (gate block ~5822-5855; seeds function +
  `_relationship_authority` caller)
- `domain_inclusion.py` (paper rule ~493-501)

## Rollback

Single-commit revert restores the anchoring gate (papers back to 41%).
