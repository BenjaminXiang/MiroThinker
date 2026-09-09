# ADR-014: Canonical V2 keeps Person internal to the four public domains

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Person identity, Person projection); OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S6R catalog, S7 indexes, and S8 retrieval
- **Contract:** carried by the active OpenSpec change before the affected catalog/index/query
  slices are implemented or accepted as dependencies

## Context and decision

The product must answer person-oriented questions that cross education, Company roles, Paper
authorship, and Patent inventorship, including people who are not Professors. Treating every person
as a Professor is incorrect, while retaining independent author strings and Company team rows makes
identity, evidence, and cross-domain traversal unstable. Making Person a fifth public domain would
broaden the confirmed four-domain product and require a separate inclusion policy before that scope
has been approved.

Canonical V2 will keep Professor, Company, Paper, and Patent as the four public PRD domains and add
two internal shared surfaces:

- `PersonIdentity` is a role-neutral canonical identity with reversible source-identity resolution;
- `PersonProjection` is a release-scoped, evidence-backed read projection over resolved Person
  identities and typed education, work, and role relations.

Professor projections and resolved Company personnel, Paper author, and Patent inventor references
may point to the same Person identity. An unresolved source name remains an evidence-bearing source
reference and is never forced into a shared Person identity. Person-oriented retrieval may use the
internal projection, but Person has no independent public-domain inclusion policy or unrestricted
national-person corpus.

## Consequences

- The S6R correction to the historical S6 catalog/shared identity contract must distinguish a
  role-neutral Person identity from the
  Professor domain projection and from unresolved `NamedReference` values.
- S7 may build an internal Person retrieval projection only from accepted release evidence anchored
  to the four public domains; it is not a fifth independently published business-domain index.
- S8 can answer filters such as education + Company role + geography through typed Person relations
  while reporting the originating public-domain evidence and enumeration coverage.
- Merge/split, alias, temporal, claim-evidence, and release rules apply to resolved Person identities;
  unresolved author/inventor/team names remain explicit rather than being guessed into continuity.
- This ADR records the boundary decision but does not itself change the active OpenSpec behavior or
  reopen an Accepted slice; the V2 design owner must reconcile the affected S6R/S7/S8 contracts
  first.

## Alternatives rejected

- **Fifth public Person domain:** expressive, but expands the confirmed product scope and requires a
  new inclusion, publication, API, index, and acceptance contract.
- **Only Professor plus nested/string personnel:** preserves the current schema but cannot reliably
  answer non-Professor person queries or maintain one identity across roles and domains.
