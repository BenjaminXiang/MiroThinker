# S6R Aggregate Reacceptance Review

## Disposition

- Slice: `s6r5-aggregate-s6-reacceptance`
- OpenSpec task: `6.11`
- Accepted at: `2026-07-14T02:05:34Z`
- Review bar: zero open Critical or Important findings
- Result: Accepted; S7 release/index RED is the next Ready critical-path work

S6R reaccepts the complete S6 foundation after the additive internal Person and Technology
reconciliation. It does not publish a release, build an index, call a provider, create a fifth public
domain, add `product_has_capability`, or write an original, recovery, or durable-candidate target.

## Contract and boundary accounting

- Public domains remain exactly `company`, `paper`, `patent`, and `professor`.
- Internal auxiliary reference types are exactly `person`, `technology_concept`, and
  `technology_route`; they are release-scoped build inputs rather than public inclusion domains.
- Published paths remain exactly `exact_lookup`, `structured_filter`,
  `verified_relationship_traversal`, `semantic_recall`, `recommendation`, and `ranking`.
- The historical v1 catalog remains byte-identical: file SHA-256
  `b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0`; its content SHA-256 is
  `8ad9e719579b834f51128788f49d091913c0c90e3b047aac9b2f83cc794441d7`.
- The additive internal-reference evidence and packaged catalogs are byte-identical: file SHA-256
  `84d778384f8dfb27118f39e498f28a3c51026c2c488d64a9b467f6d23491dbbf`; validated content SHA-256
  `ff347833ce4e86f06ead0282c566e691e983cc19d3a1c81a294d3bdb378a45a7`.
- The legacy relationship registry retains 34 rows. The installed combined registry contains 40
  exact `(relationship_type_id, version)` pairs: the 34 historical rows plus six additive Person/
  Technology rows. `product_has_capability` and an Industry Brief canonical fact remain absent.
- The combined registry content hash is
  `bdf3045650a0ed7954cac4f64ac405a156f89ccef4f84d1570cdffaecfdd5ee7`; final-row and legacy-row
  fingerprints are `b765797d6b074bfabbef03d79927fb0635961f6b5d7702cf9566f4963267b54d` and
  `2a1339cc...8310`, respectively.

The accepted fixture projections remain deterministic. Resolved Person produces eight anchors, one
Person, eight resolved references, and no unresolved reference (SHA-256
`144b827889043d0b1701b92c659fefaaa3b0362e293abc5b3f11017da18c9cfa`). Unresolved Person produces
two anchors, no Person, and two unresolved references (SHA-256
`e7c6ab6611681055dc68a56afb9afc12008bc0f59b371fb43104ab55a30adc6a`). Resolved Technology
produces three anchors, two concepts, one route, and no unresolved reference (SHA-256
`bf3ae38726c1bcefefc2eed9ccfcce252da490e8778a45602ffb018519c2b97b`). Unresolved Technology
produces three anchors, two concepts, no route, and one unresolved reference (SHA-256
`edba2ab30c16d022a044e767d3cbb375ac8ca8b360acdf49cfde611909022092`).

## Verification evidence

- Catalog builder/validator: `13 passed`; deterministic `--check` passed; evidence/package `cmp`
  passed.
- Complete S6/S6R pure aggregate: `167 passed`.
- Complete no-external-database Canonical V2: `265 passed, 139 skipped, 4 expected xfailed`. The four
  xfails are exactly the future `KnowledgeBuild`, `KnowledgeRead`, `KnowledgeAnswer`, and
  `ReleasePublication` interfaces.
- Identity exact-pair contract: `53 passed`; identity plus internal-reference projection: `79 passed`.
- Catalog/shared current contract: `32 passed`.
- Real disposable PostgreSQL identity/domain/relationship matrix: `68 passed in 73.11s`. The owned
  base retained zero non-system tables and no sibling database; PGDATA was tmpfs, the only host
  binding was loopback port `55444`, and the owned container was removed. The unchanged integrity
  matrix had already returned `27 passed` at `C2_0010` with 83 non-system tables before cleanup.
- Ruff check passed. Focused format check reported 17 S6R-owned files already formatted. Pyright
  reported `0 errors, 0 warnings, 0 informations` over the complete Canonical V2 source/test/migration
  surface. A broad format probe identified only four unchanged future-interface RED tests; they were
  not modified.
- A fresh wheel contained 266 entries, including the seven required S6R modules/catalog resources,
  and zero `.agents` entries. Nine package imports passed, historical `domain_catalog` retained lazy
  loading, and the unique Alembic head remained `C2_0010`.
- Strict OpenSpec validation, `git diff --check`, migration scope, generated-cache scope,
  high-confidence secret scan, and import checks passed.
- The formal S2B gate remained `accepted` for 50 sources, with backup manifest
  `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8` and restore verification
  `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231`. Original `pgtest` remained
  paused and running; it was not connected to or written.
- Two final independent re-reviews returned zero Critical, zero Important, and zero Minor findings
  for the final identity delta. Earlier aggregate review recorded only the two nonblocking hardening
  items below.

The historical v1 catalog's live documentation citations have moved since its acceptance. Current
documentation hashes are therefore not substituted into the immutable v1 artifact. Its accepted
bytes and 14-source/four-domain snapshot audit prove preservation; the additive S6R catalog's own
current source-hash validator proves current-source binding.

## Pattern-fix report

- Reported case fixed: unresolved internal Person/Technology evidence can no longer manufacture a
  provisional canonical owner; accepted stable-ID singletons survive later same-name ambiguity;
  exact request/result pairs cannot delete, fabricate, cross-wire, or misrepresent current topology.
- Defect class: L4+C1 identity continuity. Result-local validity and content hashes existed, but
  request-to-result semantic continuity was one-directional and internal unresolved policy was
  enforced only downstream.
- Sibling patterns searched: Person, Technology, generic public identities, current owners,
  assignments, history, recalled components, verdicts, contexts, and all create/link/merge/split/
  reverse/reject lifecycle actions, including PostgreSQL restart/replay.
- Sibling issues fixed: method/entity binding, one-verdict-per-component coverage, exact current
  owner/assignment/history preservation, action-specific output reconstruction, accepted topology,
  owner-membership-to-decision-source binding, terminal reject representation, and standalone split
  while preserving named-merge reversal.
- Not fixed and why: the combined relationship-registry hash is not a direct final-row fingerprint,
  and the two catalog copies are atomically replaced one at a time rather than transactionally as a
  pair. Existing factories/validators prevent a current bypass and deterministic `--check` detects
  catalog divergence; per user direction these are recorded Minor/YAGNI hardening items and do not
  expand S6R5.
- New invariant/helper/contract/test: an exact identity result is a deterministic transition from
  the immutable exact request. Every recalled component has exactly one verdict, unresolved internal
  evidence owns nothing, and decision sources, input owners, outputs, assignments, and history close
  bidirectionally for each lifecycle action.
- Remaining systemic risk: S7 must consume the public validators and must not persist unchecked
  internal-reference outputs. The generic identity persistence seam remains release/run scoped and
  should not be broadened implicitly while S7 defines publication ownership.

## Review conclusion and rollback

S6R1 through S6R5 and Tasks 6.9 through 6.11 satisfy their existing contracts. Minor/YAGNI items are
recorded and nonblocking under the user's explicit acceptance direction. Rollback is limited to the
S6R implementation/evidence diff; no product database, candidate release, index, provider, active
pointer, commit, push, PR, archive, or cutover exists to undo.
