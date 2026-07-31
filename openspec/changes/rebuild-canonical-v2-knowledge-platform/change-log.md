# Change Log

## 2026-07-25 — Task 2.8 human-readable review presentation repair

- Replaced raw JSON as the primary surface for contract, exclusion, and blind-calibration tasks with
  a deterministic, testable Chinese presentation layer. The page now states what is being reviewed,
  the relevant frozen requirements/evidence, all-or-nothing approval criteria, and how to choose a
  decision. Raw structures remain expandable audit material and do not control human interpretation.
- The translator covers all 29 frozen contracts, including safety prohibitions/qualified outcomes and
  near-name Company constraints. Any future unsupported contract structure fails closed by disabling
  contract approval instead of silently presenting a machine object. Renderer identity advances to
  `canonical-v2-human-review-renderer-v2` and content-binds the new presentation asset.
- Focused translation tests and the full Admin review matrix pass at `121 passed`. Browser verification
  covers readable contract/exclusion/calibration screens and a 390 px layout without overlap or
  console/page errors. The earlier zero-decision formal v2 ledger is retained because its v1 renderer
  hash correctly rejects the changed assets; a separate empty v3 ledger now serves the same isolated
  review endpoint.
- This is a usability and evidence-presentation correction only. It creates no human decision, judge
  result, export, reviewed-v2 corpus, Task 2.8 acceptance, downstream task acceptance, production
  data/index mutation, commit, Push, PR, promotion, archive, cleanup, or Cutover.

## 2026-07-24 — Task 2.8 single-human review workbench reached Candidate

- Implemented the isolated single-human review workbench over the frozen 29 contract candidates,
  23 exclusion candidates, and five-stratum 60-probe blind calibration workload. The dedicated
  SQLite ledger, same-origin FastAPI/static page, append-only decisions, crash recovery, sealed
  evidence-bounded judge path, canonical audit/acceptance exports, and explicit `0.0.0.0` launcher
  do not connect to Canonical PostgreSQL, open Milvus, or alter an active release.
- Added an Admin-independent export validator, the only reviewed-v2 application entry point, and an
  explicit evaluator-v2 admission path. They independently bind frozen source identities, event and
  judge chains, Global-60 metrics, the exact 29/23/60 accounting, and predecessor-v1 identities;
  application creates seven new v2 artifacts atomically and never rewrites v1.
- Focused Admin tests are `117 passed`; the complete S2C artifact/review suite is `105 passed`; the
  existing Candidate boundary matrix is `12 passed`. Ruff, Pyright, strict OpenSpec, JavaScript
  syntax, and diff checks pass. Browser verification covered attribution, all three task kinds,
  blind pre-seal rendering, reload, stale-tab `409` recovery with explicit supersession, canonical
  audit export, and 375 px layout without horizontal overflow. Independent reviews ended at
  Critical `0`, Important `0`.
- This is implementation Candidate evidence only. The observed browser export was explicitly
  `implementation_test`, `review_evidence`, non-accepting, and Task-2.8-ineligible. No real human
  decision, real judge result, reviewed-v2 corpus, Task 2.8 acceptance, downstream task acceptance,
  commit, Push, PR, promotion, archive, cleanup, or Cutover was created.

## 2026-07-24 — Task 2.8 single-human review policy replacement

- By explicit owner decision, the historical two-human/per-family-50 S2C3C2 review slice is
  Rejected/Superseded by `single-human-global-stratified-v2`: one attributable human reviews the
  exact 29 contracts and 23 proposed exclusions, then blindly labels one pre-frozen five-stratum
  60-probe workload with quotas `20/10/10/10/10`. The acceptance gates are agreement `>= 0.80`, at
  least 10 human-supported and 10 human-unsupported labels, at least five human-unsupported critical
  probes, and zero critical false accepts. Judge output remains hidden until all 60 labels are
  sealed. `review_evidence` is available at any review state but audit-only; only an independently
  validated, gate-passing
  `acceptance_candidate` export may feed reviewed-v2 application. This records the approved policy
  and starts the replacement workbench slice; it supplies no human decision or acceptance evidence.
  The new unchecked gate changes the acceptance ledger from `49/97` to `49/98` without changing the
  passing count.
  Tasks 2.8, 8.1, 8.8, and 9.8 remain unchecked, and no Accepted v1 packet/corpus/snapshot, S12A
  artifact, original PostgreSQL, or original Milvus state changed.

## 2026-07-22

- The user designated the accumulated Canonical V2 S11 worktree as the sole implementation
  authority, paused S12, and required a durable, non-destructive development baseline before any
  further feature work. A permission-restricted archive captured and independently rehashed all 354
  changed/nonignored paths. Aggregate recovery commit
  `8fd5f26c0749599860d4a08a26e6a9694d05a017` preserves the exact worktree, and aggregate import
  commit `641278f01b005c66bd356533d4df0fd11b678394` retains 299 formal implementation/acceptance paths
  while keeping 55 preview-only paths solely in recovery. This is an honest current-state import,
  not fabricated task-level history. Tasks 2.8, 8.1, 8.8, 9.8, and 12.1-12.6 remain open; `main`
  remains `f0e6224`. Successor correction `438c715190d4f8b5c2bbf9f29b6abe3899ec2330`
  separates the current evidence locator from frozen S11C execution roots and uses lexical checks
  for historical temp paths; no historical receipt changed. The safe S7/S8 matrix passed 26 cases,
  the current S11C/S11B owner matrix passed 58, and the current S11A Admin owner passed 7 without its
  historical ignored root helper. The consolidation branch is Accepted as the sole parent for
  subsequent Ready development. No push, PR, Cutover, product-data/index promotion, original-source
  mutation, branch deletion, or S12 implementation occurred.

## 2026-07-21

- Accepted S11C and Tasks 11.1-11.5 atomically at `2026-07-21T19:10:41Z`, moving the formal ledger
  `65/80 -> 70/80`. Exact S11A/S11B reruns, structural claim-level owners, interface/trace owners,
  122 real-disposable PostgreSQL cases, 70 release/index cases, guarded broad JUnit, and a complete
  22-row failure ledger prove that accepted behavior has no removed legacy dependency. The final
  traceability repair binds exact predecessor cwd/UTC and raw JUnit execution windows; independent
  evidence and protected-scope reviews are `Critical=0 / Important=0`, with generated artifacts and
  S11C-owned temp targets cleaned. Receipt SHA-256:
  `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`. S12A/Task 12.1 is next;
  S2C Task 2.8 remains only the S8/S9 acceptance-oracle gate. No Commit, Push, PR, Archive,
  promotion, original-source mutation, or Cutover occurred.

- Accepted S11B at `2026-07-21T12:54:16Z` without changing the formal `65/80` ledger or any task or
  acceptance checkbox. The candidate HTTP/UI/feedback graph now uses only release-bound S11A/S10O/
  S11B interfaces; the explicit ingest/smoke/baseline CLIs and immutable inventory quarantine every
  V042 writer, direct SQL/retrieval, old-index, global-readiness, and legacy-React path from accepted
  consumers. Focused owners are `34 passed`; the guarded broad baseline binds 530 Canonical V2 and
  596 Admin nodeids, 22 exact retained failure/error signatures, 15 attributable blocked attempts,
  zero forbidden attempts, and complete cleanup. Final review is `Critical=0 / Important=0`.
  Receipt SHA-256: `cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945`.
  Tasks 11.1-11.5 remained open and S11C remained Specified at that historical checkpoint. No Commit, Push, PR, Archive,
  promotion, source/database/index write, or Cutover occurred.

- Accepted S9J at `2026-07-21T09:57:11Z` without changing the formal `65/80` ledger or any task or
  acceptance checkbox. The correction keeps SHA/typed IDs/raw execution enums structured-only and
  makes every unspecialized material `missing`/`conflicting` outcome produce one typed limitation
  plus one bounded user-facing gap sentence across normal, suppression, and degraded paths. Exact
  HTTP/Node owners cover the recorded revenue-gap and continuation mapping; a separate real-data
  two-turn browser/API replay covers Web evidence, session binding, responsive rendering, and
  public-copy sanitation. Final reviews have zero open Critical/Important findings. Receipt
  SHA-256: `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`.
  No Commit, Push, PR, Archive, promotion, source/database/index write, or Cutover occurred; S11B
  resumes next.

## 2026-07-20

- Accepted S11A at `2026-07-20T19:56:07Z` without changing the formal `65/80` ledger or checking
  Tasks 11.1-11.5. The registered `POST /api/chat` now uses one explicitly installed release-bound
  Canonical V2 planner/Read/Answer adapter with typed continuation/session binding, bounded
  evidence/claim/session trace, preserved executable browse citations, and an immutable feedback
  checkpoint committed atomically with the displayed turn. Missing runtime and invalid/release-
  mismatched selections fail closed; no legacy SQL/fixed-handler fallback exists. Focused,
  predecessor, physical, complete Canonical V2, guarded Admin, static/package/source/protected, and
  independent review gates have zero S11A-related unexpected or open Critical/Important findings.
  Receipt SHA-256:
  `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`. No Commit, Push, PR,
  Archive, promotion, source/index/database write, or Cutover occurred; S11B is next.

- Accepted S10O and Tasks 10.3/10.4/10.5 at `2026-07-20T13:25:40Z`, moving the formal ledger
  `62/80 -> 65/80`. C2_0011 and the explicit-target Postgres adapter persist append-only gap and
  remediation history, require exact Accepted release/build-manifest/effect truth before resolution,
  and expose bounded V2-only admin list/detail operations plus a visibly separate minimal Gaps UI.
  The real `KnowledgeRead -> KnowledgeAnswer -> durable gap` owner and separate offline
  linked-to-resolved rehearsal prove that only `ops.*` rows change; canonical assertions/decisions,
  publication state, index adapter state, original Milvus, and active pointers remain unchanged.
  Review-driven counterexamples closed six Important categories; final review is `C=0/I=0`, real
  PostgreSQL/online evidence is `7 passed`, and no-external Canonical V2 is `357 passed, 148
  skipped`. No production-like database/index, original source, Commit, Push, PR, Archive,
  promotion, or Cutover changed.

- Accepted S9I and Tasks 9.2/9.4/9.6 at `2026-07-20T12:03:04Z`, moving the formal ledger
  `59/80 -> 62/80`. One public `KnowledgeAnswer` now fail-closes complete claim/conflict/inference
  bindings, sanitizes selector drafts, exposes answer/assessment decision traces and visible
  degradation, executes evidence-relevant free per-turn assessment dimensions, uses typed
  release-bound session directives, and renders bounded server-owned safety guidance. A real
  `KnowledgeRead.execute -> KnowledgeAnswer.answer` owner passes without a manually constructed
  evidence set. Review-driven counterexample RED closed four Important boundaries and one Minor;
  final review is `C=0/I=0/M=0/YAGNI=0`, and complete no-external Canonical V2 is `357 passed, 141
  skipped`. Task 9.8 and aggregate claim-level/provider/latency acceptance remain pending S2C. No
  provider/network, original source/index/database, pointer, Commit, Push, PR, Archive, promotion,
  or Cutover changed.

- Accepted S8C and Tasks 8.3/8.5/8.7 at `2026-07-20T10:50:22Z`, moving the formal ledger
  `56/80 -> 59/80`. One public release-bound `KnowledgeRead` now executes the seven accepted lanes,
  forwards identity fusion, late rerank, sufficiency, supplemental search, Web-handle resolution,
  accepted-identity lookup, and TTL, and admits only exact-release/exact-session lane-free handle
  replay. The integration RED exposed and closed the prior planner-owned replay rejection without
  capturing the internal delegate. Final focused/detailed/physical/full results are `1`, `8`, `13`,
  and `351` passes; final review is `C=0/I=0/M=0`. Tasks 8.1/8.8 and claim-level/provider aggregate
  acceptance remain pending S2C. No provider/network, original source/index/database, pointer,
  Commit, Push, PR, Archive, promotion, or Cutover changed.

- Accepted S8R5, the displayed Patent-to-Company applicant predecessor for Task 8.3, at
  `2026-07-20T09:38:32Z` without checking Task 8.3 or changing the formal `56/80` ledger. The
  planner path replays exact S8R2 `patent_has_applicant@canonical-v2-relationship-v1` authority,
  preserves Patent-to-Company orientation and applicant-only evidence, keeps the displayed Patent
  as source witness, and returns Company. Review repair added the authoritative-count-before-caller-
  cap ordering regression and same-Company Web alias/direct-Canonical/other-Canonical-subject
  boundary matrix. Final focused/relationship/full results are `1 passed`, `6 passed`, and
  `350 passed, 141 skipped` with three intentional hostile-serializer warnings; static, strict,
  package/source-parity, scope, secret, cache, and frozen-target gates pass. Final review reports
  `C=0/I=0/M=0/YAGNI=0`. No provider/network, persistence, original source/index/database, pointer,
  Commit, Push, PR, Archive, promotion, or Cutover changed.
- Accepted S8R4, the displayed Paper-to-Professor inverse attribution predecessor for Task 8.3, at
  `2026-07-20T08:53:38Z` without checking Task 8.3 or changing the formal `56/80` ledger. The
  planner path replays exact accepted current
  `professor_attributed_to_paper@canonical-v2-relationship-v1` authority, preserves the Canonical
  Professor-to-Paper claim, keeps the displayed Paper as the protected source witness, and returns
  fully traced Professor identities. Review-driven RED/GREEN closed inverse pre-filter result-cap
  loss, Canonical/Web evidence crosswires, finite Web identity-state bypasses, and the conflict
  between direct Canonical evidence binding and Accepted Web evidence-subject aliases. Final
  focused/relationship/full results are `1 passed`, `5 passed`, and `349 passed, 141 skipped` with
  three intentional hostile-serializer warnings; complete static, strict, package/source-parity,
  scope, secret, cache, and frozen-target gates pass. Final independent review reports
  `C=0/I=0/M=0/YAGNI=0`. No provider/network, persistence, original source/index/database, pointer,
  Commit, Push, PR, Archive, promotion, or Cutover changed.
- Accepted S8R3, the displayed Professor-to-Paper attribution traversal predecessor for Task 8.3,
  at `2026-07-20T02:13:12Z` without checking Task 8.3 or changing the formal `56/80` ledger. The
  planner path maps only to exact accepted current
  `professor_attributed_to_paper@canonical-v2-relationship-v1` authority, keeps the displayed
  Professor as the protected source witness, and returns fully traced Paper identities under honest
  representative open-world coverage. Review-driven RED/GREEN closed same-Paper Web constraint
  replay, fabricated Web relationship claims, fused provenance/receipt/handle ownership, endpoint/
  retained-source crosswires, and a Candidate-review path-without-relationship-lane bypass before
  Web effects. Final focused/predecessor/physical/relationship+publication/read+planning/full
  results are 1/9/59/15/17/348 passes, with two physical and 141 expected external skips; final
  implementation, targeted repair, and evidence reviews report zero Critical/Important/Minor/
  YAGNI. Static, strict, package, scope, secret, cache, and frozen-target gates pass. No provider/
  network, persistence, original source/index/database, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed.

## 2026-07-19

- Accepted S8R2, the displayed Company-to-Patent applicant traversal predecessor for Task 8.3, at
  `2026-07-19T22:19:19Z` without checking Task 8.3 or changing the formal `56/80` ledger. The
  planner's public path reverse-traverses only exact accepted current
  `patent_has_applicant@canonical-v2-relationship-v1` authority, keeps the displayed Company as a
  protected source witness, and returns one fully traced Patent identity. Complete lineage,
  temporal disclosure, valid-zero/constraint behavior, legitimate same-Patent Web fusion, and
  hostile envelope/evidence/trace/coverage ownership are bound in memory. Final predecessor/
  physical/relationship+publication/read+planning/full results are 8/58/15/17/347 passes, with two
  physical and 141 expected external skips; three final reviews report zero Critical/Important.
  Static, strict, package, scope, secret, cache, and frozen-target gates pass. One wording Minor is
  recorded but nonblocking. No provider/network, persistence, source/index/database, pointer,
  Commit, Push, PR, Archive, promotion, or Cutover changed.
- Accepted S8R1, the release-scoped Technology relationship traversal predecessor for Task 8.3, at
  `2026-07-19T20:05:54Z` without checking Task 8.3 or changing the formal `56/80` ledger. The exact
  S7K relationship pair plus S7 index/internal authority now executes one frozen
  `technology_route -> company` family for discussion/mention, claimed adoption, and demonstrated
  use entirely in memory. Claims remain Product-scoped, Company identity is locator-only, path
  limitations and snapshot freshness stay visible, and Product capability is never inferred.
  Review-driven RED/GREEN closed seven Important request/authority/postvalidation findings; final
  review is zero Critical/Important/Minor/YAGNI with `Accept`. Final predecessor/physical/
  relationship+publication/read+planning/full results are 13/56/15/17/345 passes, with two physical
  and 141 expected external skips. Static, strict, package, scope, secret, cache, and frozen-target
  gates pass. Task 8.3 remains open for the next real relationship family. No provider/network,
  persistence, source/index/database, pointer, Commit, Push, PR, Archive, promotion, or Cutover
  changed.
- Accepted S7K, the release-scoped relationship-publication authority correction, at
  `2026-07-19T17:05:53Z` without changing any Task checkbox or the formal `56/80` ledger. A present
  `IsolatedReleaseBundle` relationship pair now exact-replays the installed combined registry and
  internal-reference graph, the release's seven projection manifests, and the relationship section
  role/release/schema/current-count/result hash. Legacy no-pair zero bundles remain compatible but
  non-authoritative; an authoritative zero result retains a pair. Publication preflight rejects
  stale manifest hashes, subclasses/model construction, and all pair/graph/manifest cross-wires
  before backup/target/index/PostgreSQL effects, then uses only fresh validated copies. Exact RED/
  GREEN and final focused/physical/persistence/full results are `1 xfailed` → `1 passed`, `55 passed,
  2 skipped`, `19 passed`, and `344 passed, 141 skipped`; final review is zero Critical/Important/
  Minor/YAGNI with `Accept`. Static, strict, package, scope, secret, cache, and frozen-target gates
  pass. Task 8.3 remains open for S8R1 relationship retrieval. No provider, source/original database
  or index, active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed.
- Accepted S8IR1, the release-scoped internal-reference predecessor for Task 8.3, at
  `2026-07-19T16:07:14Z` without checking Task 8.3 or changing the formal `56/80` ledger. The S8E1
  composition installs the lane only with paired index-request/institution-catalog replay
  authority, checks all four internal planning-binding hashes before effects, audits exact physical
  Person/Technology lookup documents, and validates returned trace/fusion/handle identity from the
  in-memory release graph without a second physical read. Resolved Person filters retain exact
  education/Company-role/geography facts while unresolved, nonmatching, and zero-match references
  remain trace-only. Technology emits only an exact route-definition claim plus a separate public-
  origin locator and no relationship/adoption/use/Product-capability semantics. Review-driven
  RED/GREEN closed one Important zero-match Person lane failure; final review is zero Critical/
  Important/Minor/YAGNI with `Accept`. Final focused/predecessor/physical/read+planning/full results
  are 1/9/54/17/343 passes, with two physical and 141 expected external skips. Static, strict,
  package, scope, secret, cache, and frozen-target gates pass. Task 8.3 remains open for the
  relationship-publication correction and real relationship adapter. No provider/network,
  persistence, source/index/database, pointer, Commit, Push, PR, Archive, promotion, or Cutover
  changed.
- Accepted S8V2, the Professor typed vector-view predecessor for Task 8.3, at
  `2026-07-19T14:45:45Z` without checking Task 8.3 or changing the formal `56/80` ledger. One finite
  recorded selector now propagates proposal→nonblocking plan→vector request, chooses accepted
  identity/research/both points before the unchanged score/bound, derives research display identity
  from one audited same-release Professor lookup authority, and rejects unselected views or forged
  fused/handle names at the release seam. Literal absent-field JSON/SHA identities remain unchanged.
  Review RED reproduced one self-consistent different-source duplicate-authority bypass; structural
  uniqueness before hash continuity closed it, and final review is zero Critical/Important/Minor/
  YAGNI with `Accept`. Final focused/predecessor/physical/read+planning/full results are
  1/8/53/17/342 passes, with two physical and 141 expected external skips. Static, strict, package,
  scope, secret, cache, and frozen-target gates pass. S8IR1 internal-reference lookup/filter is the
  next independent real-lane slice. No provider/network, persistence, source/index/database,
  pointer, Commit, Push, PR, Archive, promotion, or Cutover changed.
- Accepted S8V1, the audited release-scoped vector predecessor for Task 8.3, at
  `2026-07-19T10:16:54Z` without checking Task 8.3 or changing the formal `56/80` ledger. The S8E1
  composition owns the vector adapter only with an explicit release-model embedding port; it
  audits the complete marked snapshot, compares every receipt/point/lookup bundle axis, performs
  bounded deterministic cosine recall over public points, and emits full S7J/query/publication/
  physical lineage under the unchanged local-trace key. Review-driven RED/GREEN closes one
  Important opaque-authority gap by revalidating returned vector evidence against the bound release
  and recomputed query embedding/cosine. Final focused/predecessor/physical/read/full results are
  1/8/51/17/340 passes, with two physical and 141 expected external skips; final review is zero
  Critical/Important and `Accept`. One broad-exception-test Minor is nonblocking. Task 8.3 remains
  open for Professor typed-view, relationship, and internal-reference execution; S8V2 is next. No
  provider/network, persistence, database/index/source, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed.
- Accepted S7J, the mandatory vector eligibility-lineage correction found by the S8V1 design gate,
  at `2026-07-19T09:11:49Z` without changing any Task checkbox or the formal `56/80` ledger. Public
  vector points now retain exact replayed semantic decision ID/outcome/limitations; internal Person/
  Technology points remain decision-free admitted auxiliaries. One canonical full-point-envelope
  hash is shared by index manifests and release inventory verification. A fourteen-row mutation
  matrix and an equal-point/equal-old-manifest rejection prove complete binding and inventory-only
  failure isolation. Final focused/release/S8-successor/physical/full results are 1/6/4/50/339
  passes, with two physical and 141 expected external skips; final review is zero Critical/
  Important/Minor/YAGNI and `Accept`. No point population/ID/vector, Milvus schema, provider,
  source, pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. S8V1 may now proceed.
- Accepted S8L3, the release-scoped lexical lookup predecessor for Task 8.3, at
  `2026-07-19T08:35:45Z` without checking Task 8.3 or changing the formal `56/80` ledger. The
  Accepted S8E1 composition now owns a real lexical adapter over the guarded release bundle: one
  bounded normalized phrase matches typed public scalar content while retaining release/
  publication/physical/eligibility lineage and distinct exact-versus-lexical evidence identities.
  A no-protected-slot substring probe and finite quote/exact-marker/NFKC/casefold/whitespace matrix
  close every Critical/Important review finding. Final focused/predecessor/physical/read/full
  results are 1/6/49/17/338 passes, with two physical and 141 expected external skips; final review
  is zero Critical/Important and `Accept`. One multi-hit-ordering Minor is recorded but nonblocking.
  Task 8.3 still requires vector, relationship, and internal-reference real adapters; S8V1 is next.
  No external provider/network, persistence, database/index/source, pointer, Commit, Push, PR,
  Archive, promotion, or Cutover changed.
- Accepted S8E1, the release-bound `KnowledgeRead` composition predecessor for Task 8.3, at
  `2026-07-19T08:08:07Z` without checking Task 8.3 or changing the formal `56/80` ledger. One
  package-internal factory now hides the real exact/structured physical adapters, accepts only a
  bounded Universal-Web/snapshot port, and exact-validates each plan's execution-relevant release,
  publication, manifest, and index-result binding before effects. Review-driven hardening covers
  every owned binding mutation, explicit zero-call reader/Web spies, invalid Web-policy bounds, and
  accepted/oversize/missing snapshot receipts with local evidence preservation. Final focused/
  predecessor/physical/read/full results are 1/6/48/17/337 passes, with two physical and 141 expected
  external skips; final review is zero Critical/Important/Minor/YAGNI. Task 8.3 still requires real
  lexical, vector, relationship, and internal-reference adapters; S8L3 lexical is next. No external
  provider/network, persistence, database/index/source, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed.
- Accepted S8P2/Task 8.2 at `2026-07-19T07:28:02Z`, moving the formal ledger from `55/80` to
  `56/80`. The existing release-bound planner now validates a finite proposal taxonomy and
  cross-field safety matrix, server-owned official-Web domains and bounded budgets, expected
  material answer parts, and one open lightweight assessment intent with ordered user criteria.
  Review-driven regressions close arbitrary official-domain authority, unbounded/zero Web budget,
  absent material-part, and non-information ambiguity-overwrite defects while preserving frozen
  S8P1 identities. Final focused/query/physical/read/answer/full results are 2/5/47/17/13/336 passes,
  with two physical skips and 141 expected external skips; two independent final reviews report
  zero Critical/Important and `Accept`. Minor/YAGNI notes are recorded but nonblocking. No provider,
  persistence, database/index/source, pointer, Commit, Push, PR, Archive, promotion, or Cutover
  changed. S2C3C2 remains only the external reviewed-oracle gate for Task 8.1 calibration and later
  S8/S9 claim-level acceptance execution.

## 2026-07-16

- Accepted S8P1, the release-bound query-planning predecessor for Task 8.2, at
  `2026-07-16T08:02:11Z` without checking Task 8.2 or changing the formal 55/80 ledger. It exact-
  replays one accepted isolated S7 graph, recomputes manifest identity, validates the release-
  observed institution catalog and four-domain/lane policy, derives evidence-bound resolved/
  unresolved Person and Technology-route records, and attaches a content-bound publication/
  release/graph/catalog/policy trace while preserving legacy unbound plan JSON/hash identity.
  Review-driven repairs close manifest-order, model-valid binding cross-wire, multi-Company fact,
  exact lineage/hash, and missing/shared-alias gaps; targeted re-review is zero Critical/Important.
  Focused/shared/query-owner/read-owner/full results are 2/46/4/16/334 passes with 141 expected
  external skips and zero xfails; static, strict, package/source, scope, secret, cache, and frozen-
  target gates pass. S8P2 is next Ready. No provider, persistence, database/index/source write,
  pointer change, Commit, Push, PR, archive, promotion, or Cutover occurred.
- Accepted S8L2, the release-scoped displayed-set structured lookup predecessor for Task 8.3, at
  `2026-07-16T06:17:22Z` without checking Tasks 8.3/8.5 or changing the formal 55/80 ledger. It
  reuses S8L1's real guarded bundle read, snapshot/typed/internal/eligibility checks, short-circuits
  empty displayed sets, fails protected-set disagreement before read, and binds exact versus
  structured execution lanes without changing legacy exact raw/evidence/content identities. Exact/
  structured duplicates fuse to one Canonical identity while retaining distinct evidence. Final
  focused/shared/owner/full results are 1/44/16/332 passes with 141 expected external skips and zero
  xfails; static, strict, package, source, scope, secret, and cache gates pass. Review-driven legacy-
  replay and model-valid cross-lane regressions close both Important findings; final re-review is
  zero Critical/Important/Minor/YAGNI. No DSL, provider, database/index/source write, pointer change,
  Commit, Push, PR, archive, promotion, or Cutover occurred.
- Accepted S8L1, the release-bundle-bound physical exact lookup predecessor for Task 8.3, at
  `2026-07-16T05:31:12Z` without checking Task 8.3 or changing the formal 55/80 ledger. One internal
  adapter dump-revalidates a serviceable `PublishedRelease` plus complete `IsolatedReleaseBundle`,
  real-reads the guarded lookup target, requires exact bundle snapshot equality, revalidates four-
  domain typed projection content, retains S7I eligibility limitations, and emits content-bound
  local evidence/candidate traces. Review-driven repairs close original/planner lane text, empty/
  cross-domain output, and complete typed-content exclusion gaps. Focused/shared/owner/full results
  are 1/43/16/331 passes with 141 expected external skips and zero xfails; static, strict, package,
  source, scope, secret, and cache gates pass. Targeted re-review is zero Critical/Important. One
  naming Minor and redundant-check YAGNI are recorded but nonblocking. No provider, database/index/
  source write, pointer change, Commit, Push, PR, archive, promotion, or Cutover occurred.
- Accepted S7I, the narrow lookup-eligibility lineage correction, at `2026-07-16T04:55:58Z`
  without changing the formal 55/80 ledger. Public lookup documents now retain their exact
  replay-validated decision ID, admitted/limited outcome, and sorted limitations; internal
  auxiliaries remain decision-free admitted records, and manifest parity hashes the complete
  normalized document envelope. Exact RED/GREEN, shared S7, sibling, full no-external, static,
  strict, package, frozen-source, and independent-review gates pass with zero Critical/Important.
  No policy semantics, document population/ID/content, schema, provider, external state, Commit,
  Push, PR, archive, promotion, or Cutover changed. S8L1 may now be revised against the corrected
  document plus `IsolatedReleaseBundle` boundary.
- Accepted S9C1/Task 9.7 at `2026-07-16T04:08:02Z`, moving the formal ledger to 55/80. The existing
  `KnowledgeAnswer` now accepts only the six frozen continuation reason/operation/target contracts,
  replaces caller factual labels with neutral server labels, requires a relationship type only for
  executable next-hop traversal, and rejects relationship facts on non-traversal options. One new
  group proved exact RED, preserved all valid option/selection bindings, and returns no offer for an
  invalid-only set. The merged review found and closed one Important missing/stray relation-type
  gap; targeted re-review is zero Critical/Important/Minor/YAGNI. Focused/multi-turn/answer-owner/
  full results are 1/5/14/329 passes with 141 expected external skips and zero xfails; static,
  strict, package, source, diff, scope, secret, and cache gates pass. No provider, safety policy,
  durable session, reviewed-oracle execution, external state, Commit, Push, PR, archive, or Cutover
  changed; Tasks 9.2/9.4/9.6/9.8 and aggregate S9 remain open.
- Accepted S9AG, the atomic synthetic KnowledgeAnswer mechanics GREEN predecessor, at
  `2026-07-16T03:36:43Z` without checking Tasks 9.2/9.4/9.6/9.7/9.8 or changing the 54/80 ledger.
  One deep module makes all 13 S3A/S9A/S9G/S9M/trust-boundary owners GREEN with content-bound
  proposals, exact grounded claims/citations/conflicts, answer-scoped Product and Industry-Brief
  semantics, per-turn assessment, deterministic fallback, Canonical/Web multi-turn context, typed
  traversal, ambiguity, topic switch, and conditional continuation. The merged review found and
  closed three Important combination defects: rejected output state pollution, Product claim
  synthesis during claim suppression, and first-turn unresolved-Web traversal. Final owner/full
  results are 13/328 passes with 141 expected external skips and zero xfails; static, strict,
  package, source, diff, scope, secret, and cache gates pass. Targeted re-review is zero Critical/
  Important/Minor/YAGNI. No reviewed-oracle execution, real provider, durable session, consumer,
  external state, Commit, Push, PR, archive, or Cutover changed.
- Re-Accepted S8RG at `2026-07-16T02:12:44Z` after the S9 readiness audit exposed one narrow
  successor-shape mismatch: non-`partial_coverage` continuation candidates legitimately carry no
  coverage state. `coverage_state` is now optional, and both explicit `"open_world"` and `None`
  variants survive the complete JSON `EvidenceSet` round trip. Focused/owner/full results remain
  2/16/315 passes, with 141 skips and the same 12 untouched KnowledgeAnswer/S9 xfails. Static,
  strict, package, source, diff, secret, and cache checks pass; targeted re-review is zero Critical/
  Important/Minor/YAGNI. No task checkbox or external state changed, so the ledger remains 54/80.

## 2026-07-15

- Accepted S8RG, the atomic synthetic KnowledgeRead mechanics GREEN predecessor, at
  `2026-07-15T16:17:31Z` without checking Tasks 8.1-8.3/8.5/8.7-8.8 or changing the 54/80 ledger.
  One deep module makes the two ambiguity/snapshot atomic groups plus all 14 Accepted read owners
  GREEN while preserving planning, Universal Web, seven-lane/full-candidate trace, identity-late
  fusion, hard constraints, rerank degradation, sufficiency/enumeration, bounded supplemental
  retrieval, and evidence-bound Web-handle behavior. Final repairs reject non-finite/negative
  supplemental budgets and forged lanes, retain max-results-dropped raw candidates as fully traced
  `result_limit_rejected`, and close identity/evidence/handle/constraint/supplemental trace bypasses.
  Focused/owner/full results are 2/16/315 passes, with 141 skips and 12 untouched KnowledgeAnswer/S9
  xfails. Static/strict/package/source/diff/scope/secret/cache gates pass; comprehensive and exact-
  SHA delta reviews leave zero Critical/Important. One conservative-negation recall Minor and named
  provider/session/multi-snapshot YAGNI remain nonblocking. No provider, persistence, database/index/
  source, active pointer, Commit, Push, PR, archive, or Cutover changed.
- Accepted S8RF, the three-group fixture-only RED predecessor for the mechanically decidable parts
  of Tasks 8.3/8.5, at `2026-07-15T07:29:28Z` without checking either task or changing the 54/80
  ledger. It freezes one seven-lane batch with real independent overlap and full raw-candidate/
  auxiliary trace, accepted-identity/evidence-late fusion plus hard constraints and structured
  rerank degradation, and session-bound Web snapshot/handle tamper/provider-change/expiry/URL-
  collision/read-only-resolution mechanics. Normal/forced execution is three xfails/three exact
  `_MissingKnowledgeReadModule` sentinels; the read-owner matrix is 14 named xfails and complete no-
  external Canonical V2 is 299 passes, 141 skips, and 26 named xfails. Static/strict/package/source/
  diff/scope/secret/cache gates pass; two exact-identity final reviews end zero Critical/Important/
  Minor/YAGNI. Ambiguity execution handoff, cross-session enforcement, max-bytes policy, and broader
  provider/schema permutations remain later scoped work, not blockers. No production/shared code,
  external state, Commit, Push, PR, archive, or Cutover changed.
- Accepted S10D, the pure gap-remediation mechanics GREEN predecessor for Task 10.3, at
  `2026-07-15T06:47:34Z` without checking Task 10.3 or changing the 54/80 ledger. The existing
  `KnowledgeGapFeedback` deep module now owns strict content-bound offline receipts, exact release/
  effect lineage, immutable linked/resolved transitions, and stable ephemeral replay. Final review
  closed source-release self-closure, stale-request time reversal, equal-time effect verification,
  and advancing-clock replay findings. Focused/owner/full results are 3/18/299 passes, with 141
  skips and the unchanged 23 named future-read/answer xfails. Static/strict/package/source/diff/
  scope/secret/cache gates pass; two independent reviews end zero Critical/Important. Minor/YAGNI
  lifecycle, opaque-ID, exact stale-input assertion, external-truth, universal-kind, and durable-
  replay notes remain nonblocking. No persistence, provider, external state, Commit, Push, PR,
  archive, or Cutover changed. Tasks 10.3-10.5 and aggregate S10 remain open.
- Accepted S8Q1, the fixture-only RED predecessor for the mechanically decidable part of Task 8.1,
  at `2026-07-15T06:16:26Z` without checking Task 8.1 or changing the 54/80 ledger. Four exact-
  target groups freeze A-G/safety/enumeration planning, protected slots/displayed-set rewrites and
  a catalog-driven institution matrix, explicitly injected ambiguity mechanics, and internal
  Person/Technology plan semantics. Normal/forced execution is four xfails/four exact
  `_MissingKnowledgeReadModule` sentinels; the read-owner matrix is 11 named xfails and complete no-
  external Canonical V2 is 296 passes, 141 skips, and 26 named xfails. Static/strict/package/source/
  diff/scope/secret/cache gates pass; contract and two test review tracks end zero Critical/
  Important/Minor/YAGNI. Reviewed ambiguity calibration and claim-level oracle execution still
  await S2C; no numeric product defaults were frozen. No production/shared code, external state,
  Commit, Push, PR, archive, or Cutover changed. Tasks 8.1-8.3, 8.5, and 8.7-8.8 remain open.
- Accepted S10C, the fixture-only RED predecessor for Task 10.3, at `2026-07-15T05:35:23Z`
  without checking Task 10.3 or changing the 54/80 ledger. Three exact-target groups freeze reviewed
  offline relationship-repair linkage without premature closure, exact accepted-candidate plus
  release-parity and intended-effect proof for closure, and fail-closed cross-gap/release/domain/
  path/run/source/build/manifest/review/trace/scenario/time, tamper, duplicate, caller-final-gap, and
  online-only matrices. Normal/forced execution is three xfails/three exact
  `_MissingKnowledgeGapRemediationContract` sentinels; owner regressions are 15 passes and complete
  no-external Canonical V2 is 296 passes, 141 skips, and 22 named xfails. Static/strict/package/
  source/diff/scope/secret/cache gates pass; two final review tracks end zero Critical/Important.
  Two compatibility-matrix/transition-ID YAGNI notes remain nonblocking. No production/shared code,
  S2C oracle, external state, Commit, Push, PR, archive, or Cutover changed. Tasks 10.3-10.5 and
  aggregate S10 remain open.
- Accepted S9G/Task 9.1 at `2026-07-15T04:58:03Z`, moving the ledger to 54/80. Four exact-target
  strict RED groups freeze exact material claim/evidence/citation binding with orthogonal semantic
  traps, proportional local/Web conflict and model-inference disclosure, direct named-Product
  capability/status without canonical propagation, and a scoped/as-of derived Industry Brief with
  exact route semantics, representative coverage, top-level result closure, and deterministic prose-
  failure fallback. Normal/forced execution is four xfails/four exact `knowledge_answer` sentinels;
  complete no-external Canonical V2 is 296 passes, 141 skips, and 19 named xfails. Static/strict/
  package/source/diff/scope/secret/cache gates pass; two review tracks end zero Critical/Important.
  One fallback-SHA content-binding Minor and two unchanged historical format-inventory files remain
  nonblocking. No S2C oracle, production answer/provider code, external state, Commit, Push, PR,
  archive, or Cutover changed. Task 9.2 and Tasks 9.4/9.6-9.8 remain open.
- Accepted S9M/Task 9.5 at `2026-07-15T04:19:34Z`, moving the ledger to 53/80. Four exact-target
  strict RED groups freeze Canonical anchor versus ordered displayed-set semantics, registered typed
  traversal with hidden-member exclusion and protected coverage lineage, evidence-bound unresolved
  Web-handle coreference/traversal refusal, blocking/non-blocking ambiguity with exact Canonical/Web
  option selection, all six conditional continuation reasons plus unavailable/no-trigger cases, and
  explicit topic-switch active-state replacement. Normal/forced execution is four xfails/four exact
  `knowledge_answer` sentinels; complete no-external Canonical V2 is 296 passes, 141 skips, and 15
  named xfails. Static/strict/package/source/diff/scope/secret/cache gates pass; an external mirror
  TLS failure on the first isolated wheel attempt was bypassed only by a successful locked offline
  build with the unchanged wheel hash. Two review tracks and Candidate identity review end zero
  Critical/Important. Minor naming/cross-release/dedicated-first-path notes remain nonblocking. No
  S2C oracle, production answer/session/provider code, external state, Commit, Push, PR, archive, or
  Cutover changed. Tasks 9.1-9.2 and 9.4/9.6-9.8 remain open.
- Accepted S8S/Task 8.6 at `2026-07-15T03:28:45Z`, moving the ledger to 52/80. Three exact-target
  strict RED groups freeze content-bound supported/conflicting/missing decisions with direct named-
  Product capability binding, complete non-fabricated accounting for all three enumeration modes,
  and targeted supplemental retrieval stopped independently by wall-time/provider-call/retry/cost
  budgets while retaining initial evidence and exact receipt/limitation/continuation state. Normal/
  forced execution is three xfails/three exact `knowledge_read` sentinels; complete no-external
  Canonical V2 is 296 passes, 141 skips, and 11 named xfails. Static/strict/package/source/diff/
  scope/secret/cache gates pass. Two independent targeted reviews and the candidate identity review
  end zero Critical/Important; no Minor/YAGNI finding blocks the test-only slice. No S2C oracle,
  production read/provider code, external state, Commit, Push, PR, archive, or Cutover changed.
  Tasks 8.1-8.3, 8.5, and 8.7-8.8 remain open.
- Accepted S8W/Task 8.4 at `2026-07-15T02:55:04Z`, moving the ledger to 51/80. Three exact-target
  strict RED groups freeze server-owned Universal Web for A/B/C/D/E/G despite caller/model opt-out,
  four non-retrieval/default-safety skip modes, bounded official-only safety lookup with minimal
  content-addressed snapshot grounding, and timeout/connection/invalid-output degradation that
  retains local evidence and exposes a freshness limitation. Normal/forced is three xfails/three
  exact `knowledge_read` sentinels; complete no-external Canonical V2 is 296 passes, 141 skips, and
  eight named xfails. Static/strict/package/source/diff/scope/secret/cache gates pass. Two pre-review
  correction sets closed four Important false-green gaps; two targeted re-reviews end zero Critical/
  Important. One plan-policy redundancy YAGNI remains nonblocking. No S2C oracle, production read/
  provider code, external state, Commit, Push, PR, archive, or Cutover changed. Tasks 8.1-8.3 and
  8.5-8.8 remain open.
- Accepted S9A/Task 9.3 at `2026-07-15T02:32:31Z`, moving the ledger to 50/80. Three exact-target
  strict RED groups freeze all four named assessment families, explicit user-criterion precedence,
  small per-turn question/evidence-selected dimensions, and supported/conflicting/missing outcomes
  with evidence, conclusion/insufficiency, uncertainty, and conditional answer-scoped synthesis.
  Normal/forced execution is three xfails/three exact `knowledge_answer` sentinels; complete no-
  external Canonical V2 is 296 passes, 141 skips, and five named KnowledgeRead/KnowledgeAnswer/S9A
  xfails. Static/strict/package/source/diff/scope/secret/cache gates pass. Review closed two Important
  false-green gaps and ends zero Critical/Important; two assertion-shape YAGNI notes are recorded
  nonblocking. No S2C/S8 oracle, production answer/read code, external state, Commit, Push, PR,
  archive, or Cutover changed. Tasks 9.1-9.2 and 9.4-9.8 remain open.
- Accepted S10B/Task 10.2 at `2026-07-15T02:10:55Z`, moving the ledger to 49/80. One pure deep
  module turns typed observation-only `GapSignal` values into content-bound, immutable open/
  unreviewed `KnowledgeGap` results. It owns gap identity, initial classification/confidence,
  demand/trigger-family accounting, severity, owner/remediation, and lifecycle. A narrow recorded
  classifier may propose ambiguous outcomes; wrong-bound, invalid-schema, timeout, and connection
  results degrade deterministically, while programmer defects propagate and constructed Pydantic
  instances are revalidated. All four protected triggers resist hostile proposals; Product demand
  remains direct-evidence collection only. Pre-GREEN RED was five xfails/five exact sentinels;
  final focused/shared/full results are 5, 21, and 296 passes with 141 skips/two existing xfails.
  Static/strict/package/source/diff/scope/secret/cache gates pass; two final reviews are zero
  Critical/Important. Three coarse-mapping/cost/dedup YAGNI notes remain nonblocking. Tasks 10.3-10.5
  and aggregate S10 stay open. No external state, Commit, Push, PR, archive, or Cutover changed.

## 2026-07-14

- Accepted S10A/Task 10.1 at `2026-07-14T19:23:58Z`, moving the ledger to 48/80. Three strict RED
  groups cover all eight named no-result/evidence/Web/Product-capability/relationship/feedback/
  benchmark/index-parity triggers through one future `KnowledgeGapFeedback.record` interface.
  Signal fixtures carry observation/trace facts while the future module owns gap identity,
  classification, confidence/review, demand/PRD-impact accounting, priority, remediation, and
  lifecycle. Product demand binds a named Product/capability/direct-evidence gap and only permits
  offline direct-evidence collection, never a canonical Product-capability relation. Normal/forced
  RED is three xfails/three exact target-sentinel failures; shared and complete no-external matrices
  are 16 passes/three xfails and 291 passes/141 skips/five named xfails. Static/strict/package/source/
  diff/scope/secret/cache gates pass; final independent review is zero Critical/Important with one
  construction-helper YAGNI recorded nonblocking. Task 10.2 and aggregate S10 remain open. No
  production/shared contract, external state, Commit, Push, PR, archive, or Cutover changed.
- Accepted S2C3C1 at `2026-07-14T18:48:51Z` without checking Task 2.8 or changing 47/80. One
  deterministic, content-addressed packet accounts for all 52 exact cases as 29 null decision
  templates plus 23 unaccepted evidence-gap exclusion candidates, with 18 null per-family
  calibration templates and no selected judge model. The builder reuses only the public S2C3B
  admission seam and post-binds the exact captured bytes, closing one TOCTOU Important. Initial RED
  was one xfail/one forced sentinel; final packet/combined/historical verification is 1/17/20 passes;
  write/check, static/strict/diff/source/secret/cache gates and final independent zero-C/I/M review
  pass. S2C3C2 is Ready but awaits real attributable human decisions, a second calibration reviewer,
  judge authorization, measured calibration, and explicit exclusion decisions. No human approval,
  runtime/database/index/source state, Commit, Push, PR, archive, or Cutover changed.
- Accepted S2C3B at `2026-07-14T18:27:07Z` without checking Task 2.8 or changing 47/80. The one
  run-local deep seam makes all five Accepted RED groups GREEN and content-binds exact artifacts,
  atomic/stage/enumeration outcomes, evidence-bounded recorded judging, and a deeply immutable
  synthetic-only human/calibration acceptance record. Final focused/combined/historical verification
  is 5/16/20 passes; the Accepted RED remains exactly recoverable when the target is absent. Builder,
  Ruff/format/Pyright, strict OpenSpec, diff/source/secret/cache gates pass. Multiple coherent cross-
  wire, JSON-type, forbidden-semantics, judge-degradation, stage-localization, and mutability findings
  were closed; two final reviews report zero Critical/Important. Three Minor/YAGNI notes remain
  nonblocking and are assigned to S2C3C where applicable. No real human approval, live provider,
  runtime/database/index/source state, Commit, Push, PR, archive, or Cutover changed.
- Accepted S2C3A at `2026-07-14T17:36:19Z` without checking Task 2.8 or changing the 47/80 ledger.
  Exactly five strict RED groups freeze atomic hard-case closure/stage localization, exact artifact
  and coherent cross-wire admission, evidence-bounded recorded judging with conservative unresolved
  degradation, and human-review/calibration acceptance identities. Normal execution is exactly five
  xfails; forced execution is exactly five absent-target sentinel failures; combined S2C is 11
  passes/five xfails and historical S2 is 20 passes. Builder/static/strict/source/scope/secret/cache
  gates pass, Accepted S2C2 bytes are unchanged, and two final reviews report zero Critical/
  Important/Minor. S2C3B owns the evaluator GREEN; S2C3C still owns real human review, mixed
  exclusions, Task 2.8, and aggregate S2C acceptance. No runtime/provider/database/index/source
  state, Commit, Push, PR, archive, or Cutover changed.
- Accepted S2C2/Task 2.7 at `2026-07-14T16:53:22Z`, moving the ledger to 47/80. The strict run-local
  schema/validator and deterministic migration account for all 52 frozen S2 cases and 53 retained
  snapshots: 29 pending review, 23 blocked on claim evidence, zero human-reviewed, and zero eligible.
  Reference prose stays non-normative; safety/near-name/enumeration obligations are structured; deep
  immutability, stable revalidation, hard-ID/entity closure, snapshot/source/manifest tamper, and
  stale-instance rejection are executable. Focused 11 and historical S2 20 pass; builder/static/
  strict/scope/cache gates pass; two final reviews are zero Critical/Important. S2C3/Task 2.8 still
  owns human review, judge calibration, aggregate S2C acceptance, and S8/S9 unlock. No runtime,
  database/index, Commit, Push, PR, archive, or Cutover changed.
- Accepted S2C1, the six-group claim-level case-contract RED Slice, at
  `2026-07-14T15:46:46Z` without checking Task 2.7 or changing the 46/80 ledger. Normal execution is
  exactly six strict xfails; forced execution is exactly six absent-target sentinel failures. The
  contract freezes strict version/content identity, atomic required/forbidden claims/entities,
  allowed variants, source snapshots/as-of, enumeration coverage, observable stage oracles, closed
  per-case hard outcomes, and non-normative reference prose. Historical S2 bytes, production code,
  runtime/data/index state, and user boundaries remain unchanged. Final independent review is zero
  Critical/Important/Minor; S2C2 owns implementation and migration. No Commit, Push, PR, archive,
  or Cutover occurred.
- Accepted S7H/Task 7.7 and aggregate S7 at `2026-07-14T12:46:02Z`, moving the ledger to 46/80.
  Complete physical audit now enumerates Milvus independently of receipt IDs and validates exact
  target/receipt/lookup/manifest/point/vector/release metadata. The package-internal isolated adapter
  reuses S7F verification/publication, re-audits before promotion/rollback, and atomically changes one
  disposable PostgreSQL pointer row. Fresh current-code rehearsal is exactly three passes; the
  existing pointer invariant, sibling/full/static/package/strict/frozen-target/cleanup gates pass.
  One review Important for omitted SQLite release metadata was fixed and independently replayed;
  final reviews are zero Critical/Important. The secret-free receipt is under the S7H run directory.
  S2C is next before S8/S9; no Commit, Push, PR, production promotion, archive, or Cutover occurred.
- Accepted S7G, the RED half of Task 7.7, at `2026-07-14T11:49:32Z` without checking Task 7.7 or
  changing the 45/80 ledger. Exactly three strict scenarios now require complete physical index
  inventory plus disposable-PostgreSQL promote/rollback, refusal/evidence for an unreceipted extra
  point, and fail-closed explicit database/index/release identity before any client or pointer write.
  Normal execution is exactly three xfails; forced execution is exactly three absent-target sentinel
  failures. S7E/S7F sibling and complete no-external suites, static/strict/scope/frozen-target gates,
  and two independent reviews pass with zero Critical/Important findings. Minor/YAGNI remains
  recorded and nonblocking. S7H GREEN is Ready; no production module, external target, commit, push,
  PR, promotion, rollback, or cutover was created or changed.
- Accepted S7F/Task 7.6 at `2026-07-14T11:00:20Z`. `ReleasePublication` now deterministically binds
  both expected and actual manifests/point inventories, persists mutually exclusive and repairable
  missing/extra/stale/cross-release evidence, refuses promotion without exact accepted verification,
  atomically rehearses the injected three-release snapshot transition, and restores its recorded
  prior snapshot without deleting evidence. Three executable reconciliation Important findings were
  closed with focused RED/GREEN cases; final review is zero Critical/Important. Owner is six passes,
  S7E owner plus publication is 46 passes, and complete no-external Canonical V2 is 290 passes/139
  skips/two named future-interface xfails. Ruff, format, Pyright, 271-entry wheel, strict OpenSpec,
  diff/scope/secret/cache, and frozen-source checks pass. The ledger is 45/80 and Task 7.7 is Ready;
  no real pointer/DB/index publication, commit, push, PR, promotion, rollback, or cutover occurred.
- Accepted S7E/Task 7.5 at `2026-07-14T10:22:52Z`. The exact-replay index builder now emits stable
  release-scoped points/documents and complete eight-vector/seven-lookup owner manifests, including
  typed Professor views and evidence-anchored internal Person/Technology auxiliaries. A guarded
  package-internal adapter performed and fully read back the first fresh isolated build in real
  Milvus Lite plus SQLite after two Accepted-S2B checks; retained evidence records six points, five
  documents, artifact hashes, and unchanged frozen targets. Final owner was 40 passes; owner plus
  release interfaces was 40 passes/three Task 7.6 xfails; complete no-external Canonical V2 was 284
  passes/139 skips/five named future-interface xfails. Ruff, format, Pyright, fresh 270-entry wheel,
  strict OpenSpec, diff/scope/secret/cache, frozen-source checks, and three independent reviews pass
  with zero Critical/Important findings. Minor/YAGNI remains nonblocking. The ledger is 44/80 and
  Task 7.6 is Ready; no commit, push, PR, publication, promotion, rollback, or cutover occurred.
- Accepted S7D/Task 7.4 at `2026-07-14T08:11:49Z` as four minimal strict RED scenarios: exact
  release/object/content/version and eligible-point metadata with typed Professor identity/research
  split; release-scoped evidence-anchored internal Person/Technology ownership without a fifth public
  domain; derived initial/schema/embedding/path-policy full rebuild; and repairable point-level
  missing/extra/stale/cross-release classification through future ReleasePublication. Exact
  CandidateProjection/PathEligibility replay and a real denied semantic-recall case prevent a global
  readiness bypass. Normal RED was four xfails, forced RED was three exact missing index targets plus
  one exact missing publication target, owner files were 28 passes/six xfails, shared contracts were
  16 passes, and complete no-external Canonical V2 was 272 passes/139 skips/eight named future-
  interface xfails. Ruff, format, complete Pyright, 268-entry wheel, strict OpenSpec, diff/scope/
  secret/cache, and final independent review passed with zero Critical/Important/Minor findings.
  Fixture extraction and physical collection/vector-dimension/durable-adapter details remain
  nonblocking YAGNI. The ledger is 43/80 and Task 7.5 is Ready; no production module, external-state
  write, commit, push, PR, publication, or cutover occurred, and no Release/Milvus acceptance box
  closed.
- Accepted S7C/Task 7.3 at `2026-07-14T06:57:15Z`. The pure package-internal candidate projection
  composer replays the exact accepted S6R closed request/result and emits typed records plus
  owner-local deterministic manifests for exactly Company, Paper, Patent, Professor, internal
  Person, Technology concept, and Technology route; empty owners retain zero-count envelopes and
  unresolved references never become records. Manifest scope prevents a fifth public domain, and
  no pointer-capable, relationship/eligibility, index, lookup/vector, database, or publication seam
  enters this Slice. Initial RED was four exact xfails/four exact forced failures; final focused was
  four passes, full Internal Reference was 28 passes, shared contracts were 16 passes, and complete
  no-external Canonical V2 was 272 passes/139 skips/four future-interface xfails. Ruff, format,
  complete Pyright, 268-entry wheel inclusion, strict OpenSpec, diff/scope/secret/cache, and
  independent review passed with zero Critical/Important findings. Task 7.4-7.6 work remains
  intentionally deferred YAGNI. The ledger is 42/80 and Task 7.4 is Ready; no external-state write,
  commit, push, PR, publication, or cutover occurred.
- Accepted S7B/Task 7.2 at `2026-07-14T06:00:15Z`. The new deep `KnowledgeBuild` module exposes only
  `build(BuildCandidateRequest) -> CandidateRelease` and composes already-materialized decision,
  object, relationship, eligibility, public/internal projection, and expected-index sections into a
  canonical-JSON-hashed immutable manifest and isolated candidate. Named source and parser/policy/
  model versions are normalized; nested maps reject mutation; same-ID conflicts cannot overwrite
  retained candidates; materialization failure records retryable evidence without changing active
  canonical/published/index state. Final owner verification was three passes, combined release
  interfaces were three passes/two Task 7.6 xfails, shared contracts were 16 passes, and complete
  no-external Canonical V2 was 268 passes/139 skips/four named future-interface xfails. Ruff, format,
  complete Pyright, wheel inclusion, strict OpenSpec, diff/scope/secret/cache, and independent review
  passed with zero Critical/Important findings. One durable transaction/failure-receipt YAGNI is
  deferred. The ledger is 41/80 and Task 7.3 is Ready; no database/index/pointer/provider write,
  commit, push, PR, publication, or cutover occurred.
- Accepted S7A/Task 7.1 at `2026-07-14T02:39:06Z` as a five-scenario strict RED contract for isolated
  candidate failure/retry, candidate-bound immutable deterministic public/auxiliary manifests,
  parity-mismatch refusal, one-release promotion, and auditable rollback. The tests drive future
  concrete package-internal compositions through only the frozen build/verify/promote/rollback
  methods; exact target-module sentinels cannot mask nested missing dependencies. Normal RED was five
  xfails, forced RED was five exact failures, shared release controls were 16 passed, and complete
  no-external Canonical V2 was 265 passed/139 skipped/7 named future-interface xfails. Ruff, format,
  Pyright, strict OpenSpec, diff/scope/secret/cache, and independent review passed with zero open
  Critical/Important findings. One representative-coverage Minor is deferred to Tasks 7.3/7.4. The
  ledger is 40/80 and Task 7.2 is Ready; no implementation, database/index/pointer write, commit,
  push, PR, or cutover occurred.
- Accepted S6R5, aggregate S6R, and Task 6.11 at `2026-07-14T02:05:34Z`. The aggregate review proves
  the preserved four-public-domain/six-path boundary, internal Person/Technology auxiliary
  projections, exact identity request-to-result lifecycle continuity, legacy/additive relationship
  version coexistence, source-bound catalogs, and absence of a canonical Product-capability relation
  or Industry Brief fact. Final verification was 167 pure aggregate passes; 265 no-external passes,
  139 explicit PostgreSQL skips, and four named future-interface xfails; 13 catalog-builder passes;
  and 68 real-disposable PostgreSQL identity/domain/relationship passes with empty-base and owned-
  resource cleanup proof. Ruff, focused format, Pyright, wheel, import, unique C2_0010 head, strict
  OpenSpec, formal S2B, frozen-source, diff/scope/secret/cache, and original-Postgres pause checks
  passed. Final independent re-reviews reported zero Critical/Important findings. Two aggregate
  hardening Minors remain recorded and explicitly nonblocking; the ledger is 39/80 and S7
  release/index RED is Ready. No commit, push, PR, publication, candidate/index write, or cutover
  occurred.

## 2026-07-13

- Accepted the S6R4 Technology/relationship increment and Task 6.10 at
  `2026-07-13T22:30:44Z`. Versioned Technology identity and pure internal concept/route projection
  now preserve exact alias, definition, hierarchy, evidence, time, source, release, and field
  lineage; sparse unresolved terms remain noncanonical. The explicit combined relationship registry
  admits only checked Person/Technology endpoints, distinguishes discussion-or-mention, claimed
  adoption, and demonstrated use, binds retained assertion/artifact semantics, and preserves legacy
  replay plus exact `(relationship_type_id, version)` coexistence without adding a fifth public
  domain, Product-capability relation, Industry Brief fact, or S7 persistence. Focused pure
  verification was 75 passed with 14 explicit PostgreSQL skips; full no-external Canonical V2 was
  244 passed, 139 skipped, and four expected future-module xfails; the owned disposable PostgreSQL
  relationship suite was 19 passed and its container/sibling databases were removed. Three final
  independent reviews reported zero Critical/Important findings. The ledger is 38/80; S6R5
  aggregate S6 reacceptance is Ready and S7 remains blocked.
- Accepted the S6R3 Person-reference projection increment at `2026-07-13T20:37:07Z` without
  closing Task 6.10 or changing the 37/80 ledger. The pure internal-reference builder consumes and
  deterministically revalidates exact domain-projection and Person-identity request/result pairs,
  derives resolved/unresolved Person references, retains assignment/topology/evidence/time/catalog
  lineage, and exposes a full replay verifier. Separate domain/identity assertions connect through
  shared records plus an exact object-level crosswalk; normalized and typed ORCID evidence fails
  closed on missing or cross-wired ownership while permitting a retained profile assertion from
  another record owned by the same source identity. Focused Person/reference was 14 passed with
  three exact S6R4 xfails; full no-external Canonical V2 was 229 passed, 137 skipped, and seven
  expected xfails. Two independent reviews returned `Ready: Yes` with zero findings. S6R4
  Technology/relationship integration is Ready; aggregate S6R and S7 remain blocked.
- Accepted the S6R2 catalog/shared-boundary increment at `2026-07-13T18:57:32Z` without closing
  Task 6.10 or changing the 37/80 ledger. A new source-hash-bound additive reference catalog defines
  internal Person, TechnologyConcept, and TechnologyRoute plus exact Person v2 and three-state
  Technology relationship rows while preserving the historical four-domain v1 bytes. Projection/
  index manifests now require explicit `public_domain`/`internal_auxiliary` ownership under build
  manifest v2, and historical `domain_catalog` consumers load the new deep module only on opt-in.
  Full no-external-database Canonical V2 was `214 passed, 137 skipped, 9 expected xfailed`; builder/
  validator was 13 passed; catalog/shared was 32 passed with five later S6R xfails. Two review gates
  closed six Important defects and returned `Ready: Yes`; S6R3 Person projection is Ready.
- Accepted S6R1/Task 6.9 at `2026-07-13T18:21:59Z` as a test-only correction contract. Seven strict
  RED groups cover additive internal-reference catalog boundaries, public versus auxiliary manifest
  scope, resolved and unresolved Person behavior across all four public evidence domains,
  Technology definition/hierarchy/source/time lineage and exact three-state relationship semantics,
  exact relationship version coexistence, checked internal endpoints, and the Product-capability/
  public-domain negatives. Normal RED was exactly seven xfails; forced RED was exactly seven intended
  failures; the historical inclusion/domain/path matrix was 45 passed. Static, strict OpenSpec,
  diff/scope/secret/cache checks passed, and final independent review returned `Ready: Yes` with no
  findings. The ledger is 37/80; S6R2 is Ready, Task 6.10 remains unchecked, and S7 remains blocked.
- Closed the ADR-013-ADR-022 reconciliation gate after two independent review rounds. The first
  review found missing end-to-end Person/Technology user effects, dependency ambiguity, historical
  S2 wording drift, incomplete G/Web-handle/hard-invariant coverage, and assessment-stage overlap.
  Corrections now require Person typed-filter retrieval, Technology route comparison and scoped
  Industry Briefs, explicit S6R/S2C/S7 dependencies, unconditional evidenced ambiguity switching,
  bounded Web-handle lifecycle replay, and a separate internal-reference deep module. Fresh strict
  OpenSpec and diff checks pass with zero open Critical/Important findings; S6R1 is Ready.
- Reconciled the user-confirmed requirement audit through ADR-013-ADR-022. Canonical V2 now specifies
  hybrid enumeration coverage, internal Person/Technology reference projections, answer-scoped
  Product capability, evidence-bound Web entity handles, machine-readable claim-level case contracts,
  conditional structured ContinuationOffer, narrow local safety guidance, confidence-gated ambiguity,
  and lightweight per-turn LLM-selected assessment dimensions.
- Added pending S2C/tasks 2.7-2.8 and S6R/tasks 6.9-6.11. S2C must replace prose/key-point pass/fail
  semantics before S8/S9 acceptance; S6R must reconcile the Accepted S6 catalog boundary before S7.
  These gates preserve, rather than retroactively rewrite, historical S2/S6 acceptance evidence. The
  current task accounting is 36/80; the five new tasks are pending.
- Added the `claim-level-acceptance` capability and updated proposal, design, canonical/release/query/
  answer/gap specs, tasks, acceptance, source/slice links, and verification intent. No runtime code,
  corpus, database, index, or production-like target changed during this specification consolidation.
- The user selected Canonical V2 as the implementation mainline and froze overlapping legacy
  retrieval/Web changes as implementation authorities pending evidence/obligation mapping.
- Code-grounded audit found the V2 integration line at 30/74 tasks before this correction, with
  S1-S5 plus Tasks 6.1/6.2/6.6 Accepted and Task 6.3 In Progress.
- Accepted ADR-012: preserve date-only versus instant temporal precision; never invent UTC midnight.
- Added and Accepted Task 5.7/S5G as a narrow shared-contract correction. The shared contract,
  decision/history engine, C2_0008 storage, identity/decision adapters, restart reconstruction, and
  typed-projection consumer preserve date-only versus instant validity without UTC-midnight
  fabrication. The task count is now 31/75 and Task 6.3 may resume.
- Selected `explicit-calendar-v1`: cross-precision comparison requires caller-supplied Gregorian
  calendar/timezone context and returns `indeterminate` without it. S5G was Accepted at
  `2026-07-13T09:19:45Z` after pure, real-disposable PostgreSQL, static, strict OpenSpec, scope, and
  merged specification/code-quality review evidence reached zero open Critical/Important findings.
- Selected aggregate S6 acceptance as the Git `main` fast-forward checkpoint. Promotion is
  fast-forward-only, requires clean/integrated worktrees and side branches plus current verification,
  and does not authorize push or product/data/index cutover.
- Completed and Accepted Task 6.3 at `2026-07-13T09:56:27Z`. Four versioned inclusion adapters and
  explicit Professor, Company, Paper, and Patent projections cover all frozen fields/subobjects,
  preserve exact S5 evidence/decision/temporal lineage, package the Accepted catalog, and restart
  exactly through C2_0009 on an owned disposable PostgreSQL target. The task count is now 32/75.
- Completed and Accepted Task 6.5 at `2026-07-13T13:54:12Z`. The Accepted pure relationship seam now
  uses explicit upstream durable decision/relationship IDs and content-bound results. C2_0010 plus
  an explicit backup-gated disposable PostgreSQL adapter retain typed relationship assertions,
  decisions, outcomes, shared-ledger memberships, and one unified current surface without
  duplicating existing Canonical V2 shared assertion/decision rows.
- Exact replay/restart, advisory-lock convergence, atomic rollback, append-only/candidate release,
  endpoint ownership, retained artifact/source-record lineage, shared same-hash/wrong-content,
  run-envelope integrity, empty downgrade/re-upgrade, and populated downgrade refusal pass on owned
  sibling databases. Focused PostgreSQL was `13 passed`; full no-external Canonical V2 was
  `202 passed, 137 skipped, 9 expected xfailed`; catalog/shared was `24 passed`; Ruff, Pyright,
  strict OpenSpec, and head inventory passed. The task count is now 34/75 and Task 6.7 is next.
- Completed and Accepted Task 6.7 at `2026-07-13T14:18:02Z`. One deterministic package-internal
  path-policy seam now returns content-bound shared decisions for all six published paths, keeps
  inclusion review separate from path admission, retains ordinary quality as visible limitations/
  gaps, applies evidence-backed hard exclusions only to their named paths, validates all eight
  installed catalog traversal orientations, and resolves merged predecessors only to one current
  survivor. No global `ready` field exists.
- The merged review closed duplicate cross-projection quality codes, partial policy identity,
  release/subject/path/evidence cross-wires, incomplete target endpoint lineage, unused relationship
  input, and inclusion-review promotion. Focused path policy was `9 passed`; full no-external
  Canonical V2 was `211 passed, 137 skipped, 4 expected xfailed`; catalog/shared was `24 passed`;
  Ruff and Pyright passed. The task count is now 35/75 and Task 6.8/Aggregate S6 is next.
- The merged review closed permanent-head coupling, precision-bearing storage, scope-evidence and
  Company-validation cross-wiring, candidate-assertion ownership, and active-release direct-SQL
  write bypass. Final review has zero open Critical/Important findings; relationship RED integration
  is the next slice.
- Integrated and Accepted Task 6.4 at `2026-07-13T10:12:13Z` after comparing its side branch against
  the current S5G/S6c line rather than blindly cherry-picking it. Nine strict RED groups cover all
  seven relationship families, all eight directions, typed endpoints, retained evidence, time/
  state/role semantics, layers, and non-fabrication. The task count is now 33/75.
- Integration review closed one additional Important issue: relationship endpoints now bind the
  exact content-validated Task 6.3 domain roots and nested typed subobjects, with explicit dangling
  canonical-identity and typed-subobject REDs. Normal RED is exactly nine xfails; forced RED is
  exactly nine missing-target failures; Ruff and Pyright are green.
- Accepted corrective S6A2 at `2026-07-13T10:49:49Z`: S5G had changed the OpenSpec design and
  canonical-knowledge spec after Task 6.1 without rebinding their full-file catalog source hashes.
  A 14-source sibling scan found exactly those two drifts. The deterministic catalog set now binds
  content/file SHA-256 `8ad9e719…41d7` / `b227285f…83c0`; semantic rows are unchanged and the 24-test
  catalog/shared baseline is green. Later S6 and promotion gates must rerun this invariant.
- Accepted Task 6.5 pure projection sub-slice S6E at `2026-07-13T12:35:08Z`. The installed-catalog
  relationship module now enforces all seven families, exact typed endpoints, retained evidence and
  assertion/decision continuity, roles/state/time semantics, layers, and eight directions. Review
  additionally closed concrete subobject-type, shared assertion, decision-shape, direction-registry,
  and explicit-calendar currentness gaps. Focused `9 passed`, full no-external Canonical V2
  `201 passed, 125 skipped, 9 expected xfailed`, and static/catalog gates are green. Task 6.5 remains
  unchecked at 33/75 until relationship persistence is independently Accepted.

## 2026-07-11

- Created the breaking pre-launch Canonical V2 Epic from the user-confirmed PRD/effect grill.
- Selected a clean typed platform over V042 sidecars and a fully generic knowledge graph.
- Added six new capability specs and modified Paper identity and Professor split-index behavior.
- Added staged tasks, acceptance gates, source/agent links, and the verification contract.
- Implemented and accepted S1 database-target safety: dedicated destructive target inputs,
  server-side database identity marker, fail-closed Alembic enforcement, direct seed-loader sibling
  protection, RED/GREEN coverage, and a real isolated upgrade/downgrade cycle.
- Original Postgres and Milvus remained frozen; no recovery replay, Canonical V2 schema, broad
  migration suite, or cutover was performed.
- Completed S2 task 2.1 at the S1 checkpoint: deterministic read-only inventory covers authoritative
  PRDs, workbook/backfills, ignored historical SQLite/JSONL/XLSX/cache/release/PDF families,
  forensic recovery artifacts, and recovery-database counts. Original Milvus remains hash-only
  because no verified copy exists.
- Completed S2 task 2.2: the reviewed source-to-PRD matrix maps four domains, typed sub-objects,
  relationship families, retrieval/answer paths, and all six north-star effects to inventoried
  evidence, explicit ceilings, and future owning slices.
- Completed S2 task 2.3: froze deterministic 40-case regression and 12-case challenge corpora with
  source/protected-slot/A-G metadata. User-confirmed workbook answers/key points are case-specific
  reference ground truth, including an explicitly marked known-bad historical response; generated
  PRD/challenge expectations remain pending review and are not treated as factual gold.
- Added the user-confirmed pre-rebuild safety gate: task 2.6/S2B must back up and independently
  restore-verify original PostgreSQL, Milvus, WAL/FPI, salvage, and every inventoried historical
  source family before task 3.2 or any Canonical V2/landing write. Also made offline data builds the
  sole canonical-identity mutation authority; query/answer paths are identity-read-only.
- Completed S2 task 2.4: the deterministic nine-dimension report separates current measurements,
  legacy evidence, and unavailable metrics. Current offline intent fallback is 100/100; current
  retrieval/answer/Web/provider metrics remain unavailable, and legacy precision is explicitly
  unscored rather than treated as zero-false-positive acceptance.
- Completed and accepted S2 task 2.5: froze 24 PRD minima, 25 hard invariants, and 34 calibrated
  product-effect gates. The Accepted registry is cryptographically bound to the exact reviewed
  Candidate; the user also accepted the corpus ground-truth policy and S2 tasks 2.1–2.5. Task 2.6
  remains the mandatory backup/independent-restore gate before any rebuild write.
- Completed and accepted task 2.6/S2B under the user's objective-verification self-approval
  authorization. Content-addressed backup and independent restore cover 48 frozen inventory records
  plus original PostgreSQL and the forensic/WAL/FPI tree; PostgreSQL, Milvus, and forensic probes
  passed. A shared mount-policy repair also removed seven attributable empty anonymous volumes and
  prevents Postgres-image implicit volumes in S2B tool containers.
- Completed and accepted task 3.1 as a test-only RED slice: five strict-xfail contracts freeze the
  typed public seams and observable outcomes for EvidenceLanding, KnowledgeBuild, KnowledgeRead,
  KnowledgeAnswer, and ReleasePublication. Normal pytest stays green while `--runxfail` proves five
  genuine missing-module RED failures; no production module or database write was added.
- Completed and accepted task 3.2: an independent `C2_0001` Alembic history verifies the exact S2B
  admission before engine creation and target identity before DDL, then creates eight empty
  Canonical V2 namespaces without replaying V001–V042. A new network-none/no-port, marked candidate
  passed upgrade/downgrade/re-upgrade and remains at the clean baseline with no business rows.
- Completed and accepted task 3.3: one storage-independent Pydantic seam now defines strict artifact,
  record/assertion, decision, identity, canonical/derived/session relationship, policy, gap,
  release, and manifest values. It rejects hard semantic contradictions while preserving partial
  evidence, unresolved conflict, soft limitations, extensible catalogs, and opaque IDs.
- Completed and accepted task 3.4: C2_0002 adds the constraint-backed shared landing/knowledge/
  publish foundation and passes real disposable FK, uniqueness, append-only, reversal, release-
  scope, pointer, transaction, and downgrade/re-upgrade tests. The empty durable candidate was
  forward-upgraded only; a deterministic pg_dump fingerprint repair also replaced volatile raw
  schema hashes and made destructive baseline tests disposable-only.
- Completed and accepted task 3.5/S3 after independent review. C2_0003 repairs hash-bound parent
  lineage, record/identity provenance, bulk and mutable-history erasure, cross-release/self/wrong-
  subject decision lineage, and persisted structured-LLM traces; strict RED interfaces now reuse
  shared types, and the Canonical V2 test subtree prevents default xdist migration races. The empty
  durable candidate matches the reviewed disposable fingerprint and remains isolated at C2_0003.
- Completed and accepted task 4.1 as a test-only RED slice. Four strict scenarios freeze exact byte/
  copy lineage, parser-version replay without mutation, typed partial/corrupt preservation, and zero
  placeholder/canonical invention through the `EvidenceLanding.ingest/stream` seam. Forced RED is
  exactly four absent-module failures; no landing implementation or source/database write began.
- Completed and accepted task 4.2. A storage-independent `EvidenceLanding` core now verifies exact
  bytes and parent/copy lineage before atomically exposing deterministic replay records. Offline
  adapters cover verified WAL/FPI salvage envelopes, historical JSONL/JSON/CSV/XLSX/SQLite bytes,
  verified Milvus copy exports, and already-collected response envelopes while preserving readable
  partial evidence and typed failures. Two self-review RED/GREEN passes closed complete-run
  idempotency, detached snapshot immutability, duplicate/misaligned structured fields, strict JSON,
  source-identifier, and response-provenance defect classes across sibling paths. No durable landing
  row, source, Milvus client, provider, canonical, publication, index, or runtime consumer was
  touched; task 4.3 remains the persistence boundary.
- Completed and accepted task 4.3. C2_0004 adds an immutable ingest-run identity, parser options,
  ordered record positions, and fail-closed nonempty-C2_0003 admission; a PostgreSQL repository now
  verifies the Accepted backup gate, explicit target marker, and revision before transactionally
  retaining artifact/parser/record/error/run state. Restart, exact/conflicting/concurrent runs,
  shared-artifact races, parent/parser replay, append-only guards, forced rollback, relative-gate
  rejection, and invalid-JSON degradation passed on a new disposable database. The disposable was
  deleted; the durable candidate remains untouched at C2_0003/zero rows, and task 4.4 remains the
  actual-source replay boundary.
- Completed task 4.4 as a reviewable Candidate. The exact Accepted S2B backup/restore checkpoint now
  drives a bounded six-family WAL/FPI, SQLite, JSONL, XLSX, verified-Milvus-copy, and recorded-
  response matrix through the public landing interface. Streaming file-manifest registration and
  explicit backup -> restore -> derived lineage avoid loading the 1.3 GB Milvus copy as parser
  bytes; deterministic selectors retain 21 records and six typed errors in 15 immutable artifacts.
  The isolated candidate was forward-upgraded only to C2_0004 and idempotent replay produced the
  same checkpoint bytes without canonical/release rows. Task 4.5 still owns independent landing
  review, acceptance, and the candidate dump/manifest checkpoint.
- Completed and accepted task 4.5/S4 after two independent read-only `Ready` reviews and repair of
  replay target/source binding, immutable output separation, complete table/integrity snapshots,
  and owned disposable-restore lifecycle safety. A fresh guarded six-family replay remained
  byte-identical to `a88b44fa...e80b5`; checkpoint manifest `ab091aac...966b1` and restore evidence
  `caf789ae...f0acc` prove exact C2_0004 schema/26-table/logical parity across distinct PostgreSQL
  system identifiers. The external dump tree `4ae5f2ce...b05012` is frozen read-only, all temporary
  containers/sockets are absent, and Docker volumes are unchanged.
- Accepted the response-family requirement through two complementary observable paths: the Task 4.2
  complete `newly_collected_response` contract and the Task 4.4 real degraded
  `recorded_collected_response` evidence. No live Web/provider call or unknown HTTP provenance was
  invented. All five Evidence Landing acceptance checks are now closed; task 5.1 has not started,
  and no canonical/release/index or production-like state was created.
- Completed and accepted task 5.1 as a test-only RED slice. Five strict scenarios define retained
  field/relationship assertions, deterministic constraint outcomes before LLM evidence, content-
  bound structured adjudication, unresolved no-projection behavior, order-independent decisions,
  and evidence-backed generic current selections through one package-internal decision-module seam.
  Two review passes closed exact missing-module masking, policy/config binding, structured-output
  hash binding, relationship-unresolved coverage, and explicit Task 5.2 contract/schema handoff.
  No production module, shared contract, migration, database row, source, provider, typed domain,
  candidate release, publication, index, or runtime behavior changed.
- Clarified the future S8 institution-query invariant after identifying the legacy Tsinghua topic-
  stopword case as a systemic single-case patch. S8 must resolve a typed, release-scoped
  institution slot from one canonical/alias catalog before span-aware pure-topic rewriting and must
  cover multi-institution full-name/alias, ambiguous/unknown/absent, and overlap scenarios. Task 5.2
  and legacy `chat.py` remain unchanged.
- Completed and accepted task 5.2. A storage-independent decision engine now retains every field and
  relationship assertion, applies deterministic identity/type/path/time constraints before optional
  recorded structured adjudication, emits explicit outcomes/conflicts, and derives only evidence-
  backed current selections. Decision IDs bind the complete decision, assertion-group manifest,
  deterministic outcomes, policy/model/trace data, and decision-time identity context.
- Added C2_0005 and an explicit disposable-only PostgreSQL store. Structured LLM bytes and validated
  JSON are content-bound; selected/conflicting roles are disjoint; outcome and per-family identity-
  context snapshot ledgers are FK-linked, hash-checked by the adapter, append-only, transactionally
  replayable, and protected by downgrade locks/refusal. C2_0005 fails with SQLSTATE `55000` rather
  than inventing snapshots when C2_0004 already contains field or relationship decisions.
- Closed the systemic Alembic URL interpolation defect with one boundary helper used by all affected
  tests, including encoded Unix-socket and reserved-character URLs. Final review found zero open
  Critical/Important findings. Disposable databases/container/socket/wheel artifacts were removed;
  the accepted C2_0004 candidate and all original sources remained unchanged. Task 5.3 has not
  started.

## 2026-07-12

- Completed and accepted task 5.3 as a strict test-only RED slice. Five scenarios now define a deep
  offline identity-resolution seam for deterministic Paper strong-ID merge, content-bound
  cross-format Professor LLM adjudication, same-name Professor separation, named Company merge
  reversal with exact 1-to-N assignments, and recovered Patent linkage without legacy-ID
  compatibility.
- Candidate comparison verdicts are separate from applied identity actions; `different_entities`
  never terminally rejects valid objects. Current active identities, terminal history, exact source
  assignments, decision provenance, assertion/record evidence, recorded LLM bytes, manifests, and
  mutation-sensitive hashes are independently checked. One merged review closed all Important
  findings and returned `APPROVED`.
- Checkpoint regression and frozen-source audits passed without a database write or provider/index
  call. The durable candidate remains C2_0004 with its accepted landing checkpoint and zero
  knowledge/publish rows. Task 5.4 production/storage work has not started.
- Completed and accepted task 5.4. One package-internal offline identity module now resolves complete
  multi-component releases across Professor, Company, Paper, and Patent through versioned
  normalization, strong/composite candidate recall, deterministic rules, and content-bound recorded
  structured adjudication. Candidate verdicts remain distinct from applied create/link/merge/split/
  reverse/reject actions; low-confidence or ambiguous evidence degrades without flattening valid
  identities or relabeling component-wide LLM evidence as decision-local evidence.
- Added C2_0006 and an explicit offline/disposable-only PostgreSQL store for identity runs, verdicts,
  immutable decision-time contexts, assertion/source/record evidence, output-specific source
  allocation, current membership, terminal history, and lineage. Deferred constraints enforce exact
  action shapes, evidence/context sets, allocation partitions, current ownership, state transitions,
  and lineage. Store, upgrade, and downgrade share one parent-first lock order; unsafe populated
  downgrade or unreconstructable pre-existing history fails closed without inferred backfill.
- Exact restart load, idempotent/concurrent replay, same-ID content conflicts, mid-transaction
  rollback, structured-trace binding, create-to-merge-to-reverse lifecycle, and migration races pass
  on a real network-none/no-port/tmpfs PostgreSQL disposable. C2_0005 decision persistence remains
  compatible and now refuses ambiguous legacy multi-output ownership rather than smearing sources.
- The single merged specification/code-quality review and focused migration-safety review findings
  were closed with zero open Critical/Important items. Complete Canonical V2, S1, S2/S2B, and S4
  checkpoints plus Ruff, Pyright, wheel contents, strict OpenSpec, formal gate, source/candidate
  read-only audits, and cleanup checks passed. Original sources and the C2_0004 durable candidate are
  unchanged; task 5.5 has not started.
- Completed and accepted task 5.5 without a new migration. The existing decision seam now retains
  exact observation/source-event/validity times, copies one exact selected evidence interval into
  relationship decisions and generic current selections, and derives `current_fields` and
  `current_relationships` as the half-open `[valid_from, valid_to)` subset at the offline build's
  `as_of`. Prior and future selected decisions remain immutable history; unknown validity is not a
  hard gate; equal values or attributes with different intervals do not auto-merge.
- Canonical V2 aware datetimes are normalized to UTC before IDs, JSON hashes, fingerprints, or
  persistence. Equivalent `+08:00` input and an `Asia/Shanghai` PostgreSQL session restart now
  produce byte-identical decisions and content hashes. Validation-time interval disagreement uses
  `ValueError`, structured generation maps it to a typed adjudication error, and corrupt durable
  replay remains behind the store persistence-error abstraction.
- A real network-none/no-port/tmpfs disposable proved affiliation-like history/current restart,
  exact time retention, replay, tamper rejection, and atomic rollback. The one merged review closed
  both Important findings and returned `APPROVED`; complete Canonical V2, S1, S2/S2B, and S4
  checkpoints plus static, packaging, strict OpenSpec, formal gate, frozen-source/candidate audits,
  and owned cleanup passed. Original sources and the C2_0004 durable candidate are unchanged; task
  5.6 owns aggregate S5 review queues and superseded-decision history semantics.
- Completed and accepted task 5.6. Deterministic unresolved field, relationship, and identity
  outcomes now expose immutable evidence-bound review cases; admissible human resolutions create a
  new offline `human_review` decision or verdict without mutating the originating history. Review
  IDs and resolution content bind the logical subject, exact candidates/conflicts, policy/method,
  reviewer, outcome, rationale, and reviewed time; unsupported, stale, cross-wired, or invented
  resolutions fail closed.
- A generic decision-history projection now retains every assertion, review case, and decision while
  deriving only the unique as-of-valid unsuperseded head as current. Replacement, withdrawal,
  rejected/unresolved, future, ended, and accepted lineages reconstruct identically after restart;
  reviewed identity merge/split/reversal preserves exact source allocation. C2_0007 durably retains
  human-review provenance and enforces one logical root, one child per predecessor, strict release
  ancestry, subject continuity, cycle refusal, append-only replay, and safe downgrade refusal in
  adapter and direct-SQL paths.
- The focused migration/safety review and the single merged task review ended with zero open
  Critical/Important findings. Final checkpoint regression passed in no-database and real
  disposable modes, including C2_0001 through C2_0007 upgrade/downgrade, S4C compatibility, prior
  S1/S2/S2B/S4 gates, static typing/lint, wheel contents, strict OpenSpec, formal admission,
  frozen-source/read-only-candidate audit, and owned cleanup. Original sources and the C2_0004
  durable candidate remain unchanged; task 6.1 has not started.
- Completed and accepted Task 6.1 as an evidence-only PRD catalog freeze. A deterministic,
  content-hashed artifact binds 14 authority files and 27 exact citations to 9 shared fields,
  101 four-domain fields, 28 typed sub-objects, 34 canonical relationship types across all seven
  required families, three relationship-layer boundaries, 42 source-accounting scenarios, and all
  eight approved cross-domain traversal directions. Supported/absent/insufficient-evidence labels
  describe source potential and never claim a built or accepted edge.
- The systemic review repair removed an unsupported canonical alias edge, replaced broad family
  citations with exact lineage/business/multi-turn evidence, made identity endpoint bindings and
  business-role ownership proportional, separated Professor-Paper evidence from business roles,
  constrained union endpoints against cross-domain identity mistakes, reconciled locked Paper/
  Professor requiredness without a global completeness gate, and confined builder output to
  validated atomic replacement inside the S6 root.
- The single merged specification/code-quality review closed five Important findings and returned
  final `Ready: Yes`. Deterministic build/check, 24 Task 6.1/shared-contract tests, Ruff,
  app-environment Pyright, strict source/hash validation, and the formal Accepted S2B gate passed.
  No production code, migration, database/Milvus/provider/candidate write, runtime/query change,
  push, PR, or cutover occurred; Tasks 6.2–6.7 retain their declared ownership.
- Completed and accepted Task 6.2 as a strict test-only RED slice. Five scenarios freeze versioned,
  evidence-bound inclusion for approved/unapproved Professor seeds, roster/global Paper discovery,
  approved/unapproved Patent exports, Company skeleton/incremental/review/contrary scope, and
  query-time Web-only Companies through one future `DomainInclusionEngine` seam.
- Approved source scope is deterministic and content-bound to retained artifact hashes; results bind
  the manifest hash and tampering fails closed. Professor evaluation uses operator-approved seed
  membership without a runtime institution whitelist; Paper existence is independent of authorship;
  Patent export membership is not narrowed by topic/linkage/completeness; Company incremental
  admission requires four offline evidence dimensions while ambiguous evidence remains reviewable.
- The single merged review closed two Important evidence-binding findings. Focused normal/forced RED,
  no-database contract checks, Ruff, Pyright, strict OpenSpec, and diff/scope checks passed. No
  production code, migration, database/source/Candidate/Milvus/provider/runtime state changed;
  Task 6.3 owns GREEN implementation.
- Completed and accepted Task 6.6 in its independent worktree as a strict test-only RED slice. Five
  scenario families freeze four-domain partial exact reach, all eight cross-domain traversal
  directions, ordinary soft-quality behavior, path-scoped hard exclusions/merge redirect, and six
  published path decisions independent of global `ready`.
- The merged review repaired lifecycle/domain-status conflation, reversed canonical edge fixtures,
  global broken-reference poisoning, a false merged predecessor projection, and rejected
  Professor-Paper attribution leaking into Paper identity. Final tests consume future Task 6.3/6.5
  outputs as typed inputs without implementing or fabricating them.
- Focused normal/forced RED, 24 Accepted catalog/shared tests, Ruff, Pyright, strict OpenSpec, and
  diff/scope checks passed. No production/shared/migration/database/source/Candidate/Milvus/provider
  state changed; Tasks 6.3, 6.5, and 6.7 retain GREEN ownership.
- Completed and accepted Task 6.8/Aggregate S6. The bounded review accounts for four typed domains,
  101 domain fields, 28 typed subobjects, all 34 relationship types/seven families, eight
  cross-domain traversal directions, and six independent published paths. Focused pure S6 was 54
  passed; no-external Canonical V2 was 211 passed/137 skipped/4 expected xfailed.
- The first complete real-PostgreSQL aggregate run exposed one systemic historical-fixture defect:
  four relationship-integrity tests inserted decisions after creating an already accepted release,
  so C2_0010's candidate-write guard caused three early failures and one false positive. All four
  now exercise candidate writes and real predecessor acceptance before successor construction.
  Focused GREEN was 4 passed; the corrected real matrix was 338 passed/4 expected xfailed plus 10
  fixed-name S4C passes. C2_0010 production behavior was not weakened.
- Every Canonical V2 side branch/worktree patch is accounted for as integrated, strengthened, or
  intentionally superseded. All owned PostgreSQL targets were removed, the S6c base remains empty,
  `pgtest` remains paused, and the original Milvus hash is unchanged. Zero open Critical/Important
  findings remain; Tasks 6.1-6.8 are Accepted at 36/75. S7, release/index publication, product/data
  cutover, push, PR, and OpenSpec archive remain unstarted/forbidden.

## 2026-07-22 — S12A Task 12.1 reached isolated Candidate

- Added the deep isolated `KnowledgeBuild.build` implementation, source-build manifest, recorded
  offline adapters, one-call runner, no-overwrite content-addressed envelope sink, and focused
  contract owners. The user authorized behavior-preserving identity-resolution and
  DomainProjection performance prerequisites; their owner matrix reports `87 passed`.
- The final focused builder/runner matrix reports `67 passed`. The successful r10 run produced
  release `candidate-s12a-20260722-r10`, run `s12a-build-20260722-r10`, and evidence file
  `complete-candidate-build-envelope-r10.json` with raw SHA-256
  `2f797e0df058a9a3969a7d01b97df2492a156a64ff1436aa33588100bc6831e7`.
- Independent model, PostgreSQL, and physical-index readback passed: 5,561 landing records, 1,037
  Company projections, zero Paper/Patent/Professor/relationship projections, 5,561 one-to-one
  evidence-bound gaps, and 1,037 points plus 1,037 lookup documents with zero parity deviation.
  `publish.active_release` remains absent, original PostgreSQL remains paused, and original Milvus
  was not opened.
- Production serving remains fail-closed. Task `12.2` owns the content-addressed serving bundle and
  live query/answer/Web gates. No promotion, Cutover, production access, destructive cleanup, Push,
  PR, or `main` movement occurred.
- Final named-only independent review returned GO for the isolated Candidate with zero open Critical
  or Important findings and explicitly did not grant external acceptance.
- This is Candidate evidence only. Task `12.1` remains unchecked pending system/independent
  acceptance. Counts remain `70/80` tasks and `49/97` acceptance checks; no ledger delta or local
  commit was created.

## 2026-07-23 — S12A Task 12.1 accepted on fresh r12 evidence

- Hardened the isolated builder after r11 review: SQLite parsing is bound to admitted bytes across
  pathname replacement, duplicate/deep JSON fails closed, complete payload/evidence paths are
  audited, PostgreSQL accepts only an explicit numeric-loopback pinned session, and pre-effect live
  schema validation binds the complete semantic catalog rather than table names alone.
- Final implementation/test/runner/runner-test SHA-256 values are `85b4ca8b...98efa`,
  `d8c8174f...dff4`, `0279b242...682`, and `a85ea8da...403`. The focused builder/runner matrix is
  `104 passed`; identity/domain is `87 passed`; the exact owner matrix is `169 passed, 2 skipped`;
  complete no-external Canonical V2 is `542 passed, 148 skipped, 3 warnings`. Ruff, format, Pyright,
  offline lock/wheel source parity, strict OpenSpec, and diff checks pass.
- Fresh release `candidate-s12a-20260723-r12` / run `s12a-build-20260723-r12` emitted raw envelope
  SHA-256 `a2684f9b...f9cbc`; canonical envelope/receipt/handoff hashes are `77cde16c...88383`,
  `5ae974b6...437a8`, and `f18af185...f00bc`. Independent model/database/index readback confirms
  5,561 landing records, 1,037 Company projections, zero other domains/relationships, 5,561
  one-to-one evidence-bound gaps, 1,037 points/documents, exact durable registry/physical hashes,
  zero parity deviation, and no active release.
- Final source/safety/evidence reviews report GO with zero Critical/Important findings. Original
  PostgreSQL remains paused and original Milvus was not opened or rehashed. r10/r11 remain stale
  historical evidence; the unsuffixed r6 envelope was restored byte-for-byte.
- S12A and exactly Task `12.1` are Accepted. The task ledger moves `70/80 -> 71/80`; acceptance stays
  `49/97`. Tasks `2.8`, `8.1`, `8.8`, `9.8`, and `12.2`-`12.6` remain open behind documented human,
  population, provider, final-user-acceptance, and Cutover gates. No commit, Push, PR, promotion,
  archive, or destructive cleanup occurred.

## 2026-07-26 — Lean customer-benchmark E2E rebaseline

- The user confirmed that `docs/测试集答案.xlsx` is the customer-provided Ground Truth for its 17
  conversation groups and 25 query turns. Query, answer, and key points are interpreted together;
  key-point corrections override inaccurate historical answer fragments, while valid semantic
  paraphrases remain acceptable.
- The user canceled Task `2.8` and the contract/exclusion/blind-calibration review workflow after
  direct use showed that it did not evaluate the intended product outcome. Tasks `8.1`, `8.8`, and
  `9.8` are also retired as separate claim-level gates. Existing code, ledgers, packets, tests, and
  receipts remain non-normative history and were not deleted or reinterpreted as passing evidence.
- Final work is reduced to Tasks `12.2`-`12.6`: construct a serviceable four-domain isolated
  Candidate and serving bundle, replay the workbook through the real chat runtime, run minimal
  safety/changed-surface checks, obtain direct user acceptance, and keep Cutover separately
  authorized. The ledger becomes `75/80` with exactly five open tasks.
- Web augmentation is now evidence-driven rather than universal: it runs for requested-current,
  missing, stale, or conflicting material evidence. Adequate fresh local evidence may answer without
  a Web call.
- This documentation-only rebaseline did not run or change the Candidate, original PostgreSQL,
  original Milvus, active release pointers, production resources, or review state. No commit, Push,
  PR, promotion, archive, cleanup, or Cutover occurred.

## 2026-07-26 — S12B Task 12.2 serviceable four-domain Candidate

- Fresh isolated r5 built 1,037 Company, 251 Paper, 1,931 Patent, and 557 Professor projections from
  5,561 admitted landing records. It also built 328 evidence-backed relationships across the three
  required customer paths and retained 5,874 typed gaps rather than inventing missing facts.
- The exact Candidate produced 4,333 vector points and 3,776 lookup documents. Their expected
  manifests equal physical contents; the intentional difference is the Professor identity/research
  two-view vector contract. The serving-bundle content hash is `887689cc...58df1`, and the envelope
  canonical content hash is `abe56cc3...b560`.
- The content-addressed, secret-free bundle now binds the normal `/api/chat` and `/chat` runtime to
  release `candidate-s12b-20260726-r5` without active-pointer discovery or writes. The service is
  running on `0.0.0.0:18188`; health, UI, structured success, and fail-closed error paths executed.
- The first exact-name chat smoke selected unrelated Patent evidence for 丁文伯. This is a real
  Task 12.3 answer-quality badcase, not a Task 12.2 infrastructure failure, and no product-acceptance
  claim is made. Task 12.2 closes at `76/80`; Tasks 12.3-12.6 remain open.
- Original PostgreSQL remains paused, original Milvus and active pointers remain unchanged, and no
  promotion, Cutover, archive, destructive cleanup, commit, Push, or PR occurred.

## 2026-07-26 — S12C Tasks 12.3/12.4 customer replay Candidate

- Rebuilt the isolated release as `candidate-s12c-20260726-r8`: 1,037 Company, 262 Paper, 1,931
  Patent, and 554 Professor projections; 339 relationships; 4,338 vector points; and 3,784 lookup
  documents. Candidate/index parity passes without changing an active pointer.
- Repaired the replayed defect classes generically: strong-evidence Professor identity merge,
  answer-eligible evidence closure, exact/lexical identifier ownership, exact-entity answer
  selection, bounded near-name matching, focused missing-entity behavior, and independent-turn topic
  switching so active session anchors follow explicit exact results.
- Final `customer-workbook-replay-r6` ran 17 distinct sessions and all 25 ordered turns through the
  real `/api/chat` path with `25 ok / 0 failure`. The readable report retains Ground Truth, actual
  answers, citations/evidence, limitations, HTTP status, and timing; it does not grant semantic
  acceptance.
- Exact Ding Wenbo, Wujie Zhihang near-name exclusion, pFedGPA two-turn anchoring, targeted Company
  answers, and `CN117873146A` pass focused real-chat checks. Missing headquarters fields, Waseda/Wang
  Xueqian evidence, the pFedGPA URL, embodied-data-route modeling, and incomplete broad analyses are
  recorded as product gaps. Two Web timeouts remain explicit while local answers stay grounded.
- Changed-module tests report `27 passed`, `11 passed`, and `2 passed`; focused Ruff and Pyright are
  clean; strict OpenSpec and `git diff --check` pass. Original `pgtest` remains paused, original
  Milvus SHA-256 remains `43ef203e...867cc`, and active release row count remains zero.
- Tasks 12.3 and 12.4 close at `78/80` tasks and `26/35` acceptance checks. The release remains a
  Candidate until direct user acceptance (Task 12.5); Cutover (Task 12.6) requires separate explicit
  authorization. No commit, Push, PR, promotion, archive, cleanup, or Cutover occurred.

## 2026-07-27 — S12C runtime Web-gap repair

- Repaired the real Candidate's Web augmentation path without rebuilding or promoting the release:
  Web now receives the planned lane query, multi-turn searches include the displayed entity name,
  explicit Web-gap evidence survives late reranking, and the provider's request/fallback timeouts fit
  inside the server-owned lane budget.
- Bound ephemeral Web handles to the chat session and corrected release-authority validation so an
  unselected audit-only Professor vector candidate does not require a displayed answer handle. This
  removes the observed timeout and false 409 classes while retaining release/index validation.
- Focused tests report `29 passed`, `1 passed`, `5 passed`, and `11 passed`; changed-file Ruff,
  formatting, and targeted Pyright are clean. Strict OpenSpec validation and `git diff --check` pass.
- Real HTTP smoke returned 200 with successful current-Web retrieval for the Wang Xueqian assessment,
  the pFedGPA URL follow-up, and the Shenzhen embodied-intelligence supplier query. The pFedGPA link
  gap is now visibly supplemented. Same-name assessment disambiguation and a complete supplier-by-
  supplier data-route comparison remain visible answer-quality gaps for direct user evaluation.
- The ledger remains `78/80`. Task 12.5 is explicit direct-user acceptance; Task 12.6 is separate
  authorization for any production-like Cutover, archive, or destructive cleanup. Original sources,
  active pointers, HEAD, and `main` remain unchanged, and no canonical write or promotion occurred.

## 2026-07-27 — S12D direct-user answer and public-evidence correction

- Direct user evaluation rejected deterministic projection-copy answers and restored bounded Web
  search for every normal information request. The accepted target is local plus current-Web
  evidence followed by evidence-bound LLM synthesis, with deterministic text only on typed failure.
- Public chat must default-collapse `查看依据`, show only validated official public links, and expose
  no `/browse` link or internal evidence/trace metadata. `/browse` remains an internal tool governed
  by existing deployment network or reverse-proxy controls; this slice adds no authentication work.
- Tasks 12.5a-12.5c and the Ready S12D slice own the correction before direct user acceptance.
- S12D is now Candidate: the shared `/gemma4/v1` route is configured for the currently served
  `qwen3.6-35b-a3b-fp8` model, normal answers use the real LLM renderer, and founder-role prose
  retains the evidence-backed `participated in founding` relation instead of copying a Company
  projection or weakening the relationship.
- Public chat now emits only validated official URLs, clears raw evidence and structured trace from
  the browser envelope, removes the visible `/browse` navigation, and renders a closed `查看依据`.
  The internal feedback checkpoint remains complete on the server.
- Focused tests, Ruff, Pyright, strict OpenSpec, real Ding Wenbo two-turn HTTP, one non-case-specific
  Patent request, and desktop/mobile browser checks pass. The Candidate remains read-only on
  `0.0.0.0:18188`; Task 12.5 still requires direct user acceptance and Task 12.6 remains separately
  authorized.

## 2026-07-28 — S12D dual-Web and long-idle latency design approved

- Direct user evaluation identified long-idle first-request latency as the critical remaining
  experience defect and selected full-path adaptive keep-warm.
- The approved Web policy runs Bocha and Serper concurrently inside the existing outer Web budget,
  deduplicates normalized URLs, prefers richer Bocha content for duplicates, and retains both actual
  provider versions in the content-bound snapshot.
- The approved keep-warm policy runs at most one bounded background cycle after each complete idle
  interval, touches Bocha, Serper, embedding, and prose-LLM paths concurrently, never blocks a real
  request, stops with the app, and creates no business-data writes.
- S12D returns from Candidate to In Progress for Tasks 12.5d-12.5f. Task 12.5 remains direct user
  acceptance and Task 12.6 remains separately authorized Cutover.

## 2026-07-28 — S12D dual-Web and adaptive idle keep-warm Candidate

- Replaced the single-provider Web lane with bounded concurrent Bocha plus Serper calls. The merge
  normalizes URLs, keeps one result position per normalized URL, prefers richer Bocha content for a
  duplicate, retains primary and corroborating provider versions, and preserves usable results when
  either provider fails.
- Added one app-lifecycle-owned 300-second adaptive idle keep-warm cycle for Bocha, Serper,
  embedding, and prose LLM paths. Chat activity resets the deadline, cycles cannot overlap, provider
  failures cannot stop the worker, shutdown joins it, and the cycle bypasses chat/session/evidence
  and business-data write paths.
- The first persistent prose-client implementation exposed a real HTTP 500 because answer-session
  `deepcopy` traversed the client's lock. The corrected boundary keeps the process-scoped renderer
  and client outside copied session state; a regression now forks the real answer object and proves
  the renderer remains shared.
- On the restarted `0.0.0.0:18188` Candidate, the first post-start Ding Wenbo profile returned 200
  in 8.361 seconds, an immediate same-query turn returned 200 in 2.342 seconds, and a fresh request
  after more than six idle minutes returned 200 in 2.720 seconds. The post-idle result remains
  `llm_synthesized`, exposes `evidence=[]`, and cites only the official Tsinghua homepage. The
  same-session founder follow-up returned 200 and states that Ding Wenbo participated in founding
  Shenzhen Wujie Zhihang Technology Co., Ltd.
- Tasks 12.5d-12.5f and their objective acceptance checks are complete, so S12D returns to
  Candidate. Task 12.5 remains open for direct user acceptance; Task 12.6 remains a separate,
  unauthorized Cutover decision.

## 2026-07-29 — S12D recall-first mixed-evidence repair opened

- Direct user evaluation found a systemic late-selection failure: both Web providers returned
  relevant Product-capability evidence for a displayed Company set, but local-first ranking and the
  shared candidate/claim cap removed it before final LLM synthesis.
- The approved repair is recall-first and bounded. Local and current-Web lanes retain independent
  capacity, complementary evidence reaches the existing final LLM in one call, and deterministic
  code continues to enforce evidence binding, budgets, fallback, privacy, and official-source
  validation.
- Keyword expansion and a multi-stage LLM agent chain are explicitly rejected. Tasks 12.5g-12.5i
  return S12D to In Progress for a systemic regression repair and real three-turn verification.

## 2026-07-29 — S12D recall-first core repair verified with residuals

- Repaired the shared evidence-starvation class by reserving local and current-Web capacity through
  reranking and claim selection, increasing the final bounded plan from 8 shared candidates to 8
  local plus 5 Web candidates, and interleaving Bocha/Serper results so one provider cannot consume
  the complete Web budget.
- Kept one final LLM call and strengthened generic Product-capability, headquarters, and evidence
  selection instructions. Contextual Web queries now remove conversational scaffolding, retain
  product scope, diversify exact and relaxed provider queries, and uniquely bind city-prefixed legal
  Company names to sufficiently long brand mentions in Web results.
- The final real hotel-robot sequence identifies only Shenzhen Pudu Technology and names FlashBot Arm
  with direct mechanical-arm elevator-button evidence. Public evidence and structured trace payloads
  remain empty; unvalidated Web and internal URLs remain hidden.
- Tasks 12.5g and 12.5h are complete. Task 12.5i and S12D remain In Progress because a real
  swipe-card/door sibling follow-up still returns an evidence-insufficient false negative, and the
  headquarters turn still incorrectly includes Yunji Technology among Shenzhen-headquartered
  companies. Task 12.5 and Cutover remain open.

## 2026-07-29 — S12D relation-aware Web and LLM repair Candidate

- Added one deterministic question frame for relation semantics and retained displayed Company
  anchors in both Web-provider queries. Direct headquarters and conjunctive Product-capability
  evidence is prioritized before the unchanged five-result Web cap.
- The existing final Qwen call now synthesizes local plus Web material and returns validated
  claim/entity indexes. Only the selected answer scope is committed to the next turn; no additional
  model or provider call was introduced.
- Web identity now recognizes bounded short-brand context and a Chinese brand's pinyin plus a small
  set of organization-domain suffixes. This binds official Product pages such as `pudutech.com`
  while rejecting deceptive suffixes and unrelated robot brands; source authority remains governed
  by the existing public-citation policy.
- A real same-session four-turn replay completed in 7.961, 3.757, 1.565, and 1.274 seconds. It
  excludes Yunji from Shenzhen headquarters, identifies FlashBot Arm for mechanical-arm elevator
  operation, and confirms access-card/door operation. Public citations and evidence remain empty.
- The public root now redirects to `/chat`; `/browse` remains an unadvertised internal tool. The
  running read-only Candidate is bound to `0.0.0.0:18188`. Task 12.5i is complete, while Task 12.5
  still requires direct user acceptance and Task 12.6 remains an unauthorized Cutover decision.

## 2026-07-31 — S12D referent, recall, and serving-pack repair round

- Referent resolution is now type-aware across the whole chat path: singular pronouns no longer
  bind mismatched anchors, a bounded per-session referent history (cap 4) keeps pre-switch anchors
  and displayed sets bindable across topic switches, explicitly named new subjects always win over
  session context, and intra-query set antecedents ("…厂商，他们…") no longer trigger the
  no-referent clarification.
- Web fallback is now structurally reliable: every Web result carries a claim binding,
  question-scoped aggregate evidence binds to the turn scope instead of being dropped, and
  part-subject evidence stays admissible when the candidate window is full. Supplemental probes
  cover person-criteria (founder/education with constraint-seeded discovery), displayed-set
  relations, and theme verification for enumeration candidates, with a 3 s provider deadline,
  page-fetch enrichment, and a 6.0-cost budget.
- Recall engineering: enumeration queries widen the candidate window to 24 and the local claim
  limit to 16, Web results rise to 8, list-style turns fetch the top 5 pages, and an environment-LLM
  query rewriter decomposes multi-intent/thematic questions into up to three keyword views executed
  concurrently with a deterministic fallback view (2 s hard bound, zero behavior change on
  failure). Presentation discipline (prose v8) requires proper-noun fidelity, semantic
  capability coverage, no named-unconfirmed lists, and completeness-first list answers; the
  deterministic gap sentence no longer contradicts prose answers.
- Startup engineering: a manifest-verified fast boot skips only the vector re-embedding audit, and
  an opt-in Serving Pack (`--serving-pack` / `CANONICAL_V2_SERVING_PACK`) replaces the 426 MB
  envelope and Postgres at serve time. Measured on identical index bytes: 811.3 s / 8.49 GB to
  27.5 s / 1.85 GB with plan and evidence-set byte equality.
- Verification: miroflow 672 passed, admin canonical-v2 71 passed, zero lint/type errors. The final
  workbook replay passes 25/25 turns with zero degenerate turns in both independent-session and
  single-session cross-topic modes; one residual KEY failure remains (开普勒/九号 in the
  hotel-supplier list) and is tracked as a data-enrichment backlog item together with provider
  variance hardening, pack generation at build/promote time, and the pre-existing internal-reference
  and review-workspace failures.
